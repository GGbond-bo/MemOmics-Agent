"""Non-secret hierarchy metadata for the remote-cluster catalog.

The execution configuration stays in ``remote.nodes``.  This module only
stores the user-facing grouping:

    cluster/server -> endpoint/node -> existing remote.nodes profile

Keeping that boundary makes the hierarchy additive: current chat bindings,
historical jobs, and private-key paths remain owned by the existing cluster
configuration.  No credential field is accepted or persisted here.
"""

from __future__ import annotations

import ipaddress
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_LOCK = threading.RLock()
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_SERVER_ID = re.compile(r"^cluster-[0-9a-f]{8,32}$")
_NODE_ID = re.compile(r"^node-[0-9a-f]{8,32}$")
_ACCOUNT_ID = re.compile(r"^account-[0-9a-f]{8,32}$")
_PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_HOSTNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,251}[A-Za-z0-9])?$")
_SCHEDULERS = {"", "auto", "slurm", "pbs", "gridengine", "none"}
_ROUTE_MODES = {"direct", "via_login"}
# A legacy role marker can be retained on a draft/broken node, but only this
# predicate makes a node an operational login entry point.  Keep its SQL form
# alongside ``is_usable_login_node`` so migration, mutation and route guards
# do not accidentally count an invalid historical flag as a usable gateway.
_V4_USABLE_LOGIN_SQL = "is_login=1 AND trim(host)<>'' AND port BETWEEN 1 AND 65535"


class CatalogError(ValueError):
    """A validation or consistency error that maps to a controlled API error."""

    def __init__(self, message: str, code: str = "catalog_invalid") -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: Any, field: str, maximum: int, *, required: bool = False) -> str:
    text = "" if value is None else str(value)
    if _CONTROL_CHARS.search(text):
        raise CatalogError(f"{field} cannot contain control characters")
    text = text.strip()
    if required and not text:
        raise CatalogError(f"{field} is required")
    if len(text) > maximum:
        raise CatalogError(f"{field} is too long")
    return text


def _server_id(value: Any) -> str:
    text = _text(value, "server id", 48, required=True)
    if not _SERVER_ID.fullmatch(text):
        raise CatalogError("invalid catalog server id")
    return text


def _node_id(value: Any) -> str:
    text = _text(value, "node id", 48, required=True)
    if not _NODE_ID.fullmatch(text):
        raise CatalogError("invalid catalog node id")
    return text


def _profile_id(value: Any) -> str:
    text = _text(value, "profile id", 80, required=True)
    if not _PROFILE_ID.fullmatch(text):
        raise CatalogError("invalid account profile id")
    return text


def _port(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        port = int(str(value).strip())
    except Exception as exc:
        raise CatalogError("port must be a number") from exc
    if not 1 <= port <= 65535:
        raise CatalogError("port must be between 1 and 65535")
    return port


def _scheduler(value: Any) -> str:
    scheduler = _text(value, "scheduler", 40).lower()
    if scheduler not in _SCHEDULERS:
        raise CatalogError("unsupported scheduler")
    return scheduler


def _v4_text(value: Any, field: str, maximum: int, *, required: bool = False) -> str:
    """Strict text validation for new V4 fields.

    V3 accepted broad coercions for its legacy metadata.  New staged catalog
    objects reject non-text values so a caller cannot smuggle an object, secret
    field, or shell-shaped payload into a later remote configuration step.
    """
    if value is not None and not isinstance(value, str):
        raise CatalogError(f"{field} must be text")
    return _text(value, field, maximum, required=required)


def _account_id(value: Any) -> str:
    text = _v4_text(value, "account id", 48, required=True)
    if not _ACCOUNT_ID.fullmatch(text):
        raise CatalogError("invalid catalog account id")
    return text


def _v4_host(value: Any) -> str:
    host = _v4_text(value, "host", 253, required=True)
    if any(ch.isspace() for ch in host) or any(ch in host for ch in "@/\\"):
        raise CatalogError("host is invalid")
    candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        if not _HOSTNAME.fullmatch(host) or ".." in host:
            raise CatalogError("host is invalid")
    return host


def _v4_port(value: Any, *, required: bool = False) -> int | None:
    if value in (None, ""):
        if required:
            raise CatalogError("port is required")
        return None
    if isinstance(value, bool):
        raise CatalogError("port must be an integer")
    raw = str(value).strip()
    if not raw.isdigit():
        raise CatalogError("port must be an integer")
    port = int(raw)
    if not 1 <= port <= 65535:
        raise CatalogError("port must be between 1 and 65535")
    return port


def _v4_bool(value: Any, field: str, *, required: bool = False) -> bool | None:
    if value is None:
        if required:
            raise CatalogError(f"{field} is required")
        return None
    if not isinstance(value, bool):
        raise CatalogError(f"{field} must be true or false")
    return value


def is_usable_login_node(node: Any) -> bool:
    """Whether a catalog node is an operational V4 login entry point.

    V3 data may preserve ``is_login`` as a historical role even when the
    endpoint is incomplete.  Such a row remains visible and editable, but it
    must not satisfy the requirement for a login entry or act as a gateway.
    ``sqlite3.Row`` and ordinary API dictionaries are both accepted.
    """
    try:
        if isinstance(node, dict):
            is_login, host, port = node.get("is_login"), node.get("host"), node.get("port")
        else:
            is_login, host, port = node["is_login"], node["host"], node["port"]
        numeric_port = int(port)
    except (KeyError, TypeError, ValueError):
        return False
    return is_login in (True, 1) and bool(str(host or "").strip()) and 1 <= numeric_port <= 65535


class ClusterCatalogStore:
    """SQLite metadata store for non-secret remote-catalog hierarchy.

    Each operation owns a short-lived connection and uses ``BEGIN IMMEDIATE``
    for mutations.  The module lock reduces in-process write contention while
    SQLite's busy timeout protects independent worker threads.
    """

    def __init__(self, db_path: str | os.PathLike[str]) -> None:
        self.db_path = str(Path(db_path))

    def _connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def ensure_schema(self) -> None:
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memomics_cluster_servers (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL COLLATE NOCASE,
                        description TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_memomics_cluster_servers_name "
                    "ON memomics_cluster_servers(name COLLATE NOCASE)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memomics_cluster_nodes (
                        id TEXT PRIMARY KEY,
                        server_id TEXT NOT NULL REFERENCES memomics_cluster_servers(id) ON DELETE RESTRICT,
                        name TEXT NOT NULL COLLATE NOCASE,
                        host TEXT NOT NULL DEFAULT '',
                        port INTEGER NULL,
                        scheduler TEXT NOT NULL DEFAULT '',
                        partition_name TEXT NOT NULL DEFAULT '',
                        queue_name TEXT NOT NULL DEFAULT '',
                        role TEXT NOT NULL DEFAULT '',
                        note TEXT NOT NULL DEFAULT '',
                        is_login INTEGER NOT NULL DEFAULT 0 CHECK(is_login IN (0,1)),
                        is_compute INTEGER NOT NULL DEFAULT 1 CHECK(is_compute IN (0,1)),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(server_id, name COLLATE NOCASE)
                    )
                    """
                )
                node_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(memomics_cluster_nodes)").fetchall()}
                if "is_login" not in node_columns:
                    conn.execute("ALTER TABLE memomics_cluster_nodes ADD COLUMN is_login INTEGER NOT NULL DEFAULT 0")
                if "is_compute" not in node_columns:
                    conn.execute("ALTER TABLE memomics_cluster_nodes ADD COLUMN is_compute INTEGER NOT NULL DEFAULT 1")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memomics_cluster_nodes_server "
                    "ON memomics_cluster_nodes(server_id)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memomics_cluster_account_links (
                        profile_id TEXT PRIMARY KEY,
                        node_id TEXT NOT NULL REFERENCES memomics_cluster_nodes(id) ON DELETE RESTRICT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memomics_cluster_account_links_node "
                    "ON memomics_cluster_account_links(node_id)"
                )
                # V4 owns only non-secret server-scoped users and their
                # matched profile relations.  V3 account_links stays intact as
                # an idempotent migration source and compatibility record.
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memomics_cluster_accounts (
                        id TEXT PRIMARY KEY,
                        server_id TEXT NOT NULL REFERENCES memomics_cluster_servers(id) ON DELETE RESTRICT,
                        name TEXT NOT NULL,
                        user TEXT NOT NULL,
                        note TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memomics_cluster_accounts_server "
                    "ON memomics_cluster_accounts(server_id,created_at,id)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memomics_cluster_connections (
                        profile_id TEXT PRIMARY KEY,
                        server_id TEXT NOT NULL REFERENCES memomics_cluster_servers(id) ON DELETE RESTRICT,
                        node_id TEXT NOT NULL REFERENCES memomics_cluster_nodes(id) ON DELETE RESTRICT,
                        account_id TEXT NOT NULL REFERENCES memomics_cluster_accounts(id) ON DELETE RESTRICT,
                        route_mode TEXT NOT NULL CHECK(route_mode IN ('direct','via_login')),
                        gateway_profile_id TEXT NULL,
                        legacy_route_needs_review INTEGER NOT NULL DEFAULT 0 CHECK(legacy_route_needs_review IN (0,1)),
                        last_connected_at TEXT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(node_id,account_id),
                        CHECK((route_mode='direct' AND gateway_profile_id IS NULL) OR
                              (route_mode='via_login' AND gateway_profile_id IS NOT NULL))
                    )
                    """
                )
                connection_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(memomics_cluster_connections)").fetchall()}
                if "legacy_route_needs_review" not in connection_columns:
                    conn.execute(
                        "ALTER TABLE memomics_cluster_connections "
                        "ADD COLUMN legacy_route_needs_review INTEGER NOT NULL DEFAULT 0"
                    )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memomics_cluster_connections_server "
                    "ON memomics_cluster_connections(server_id,node_id,account_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memomics_cluster_connections_gateway "
                    "ON memomics_cluster_connections(gateway_profile_id)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memomics_cluster_legacy_link_migrations (
                        profile_id TEXT PRIMARY KEY,
                        node_id TEXT NOT NULL,
                        account_id TEXT NOT NULL,
                        migrated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memomics_cluster_catalog_migrations (
                        name TEXT PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                self._ensure_v4_node_flags(conn)
            finally:
                conn.close()

    @staticmethod
    def _ensure_v4_node_flags(conn: sqlite3.Connection) -> None:
        """Map V3 roles/usable nodes without fabricating a legacy endpoint.

        Earlier catalog versions allowed an empty server or a draft node.  The
        migration preserves those records as incomplete instead of inventing a
        host/login endpoint or deleting the server.  For an ordinary non-empty
        legacy server with a real endpoint but no usable login, it promotes
        the deterministic earliest usable node so the old server retains an
        entry point.  A role-derived login flag on an incomplete legacy row is
        preserved as historical metadata, but does not suppress that
        promotion and is never an operational gateway.  Newly created V4
        servers are stricter and always have a concrete login node.
        """
        marker = "v4_node_flags"
        if conn.execute(
            "SELECT 1 FROM memomics_cluster_catalog_migrations WHERE name=?", (marker,)
        ).fetchone():
            return
        conn.execute(
            "UPDATE memomics_cluster_nodes SET is_login=1 "
            "WHERE lower(trim(role)) IN ('login','gateway','head')"
        )
        for row in conn.execute("SELECT id FROM memomics_cluster_servers ORDER BY id").fetchall():
            server_id = str(row[0])
            has_login = conn.execute(
                "SELECT 1 FROM memomics_cluster_nodes WHERE server_id=? AND "
                + _V4_USABLE_LOGIN_SQL + " LIMIT 1", (server_id,)
            ).fetchone()
            if has_login:
                continue
            usable = conn.execute(
                """SELECT id FROM memomics_cluster_nodes
                   WHERE server_id=? AND trim(host)<>'' AND port BETWEEN 1 AND 65535
                   ORDER BY created_at,id LIMIT 1""", (server_id,)
            ).fetchone()
            if usable:
                conn.execute("UPDATE memomics_cluster_nodes SET is_login=1 WHERE id=?", (str(usable[0]),))
        conn.execute(
            "INSERT INTO memomics_cluster_catalog_migrations(name,applied_at) VALUES(?,?)",
            (marker, _now()),
        )

    @staticmethod
    def _server_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _node_row(row: sqlite3.Row, *, account_count: int = 0) -> dict[str, Any]:
        return {
            "id": row["id"],
            "server_id": row["server_id"],
            "name": row["name"],
            "host": row["host"] or "",
            "port": int(row["port"]) if row["port"] is not None else None,
            "scheduler": row["scheduler"] or "",
            "partition": row["partition_name"] or "",
            "queue": row["queue_name"] or "",
            "role": row["role"] or "",
            "note": row["note"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "account_count": int(account_count),
        }

    def _server_exists(self, conn: sqlite3.Connection, server_id: str) -> bool:
        return bool(conn.execute("SELECT 1 FROM memomics_cluster_servers WHERE id=?", (server_id,)).fetchone())

    def _node_exists(self, conn: sqlite3.Connection, node_id: str) -> bool:
        return bool(conn.execute("SELECT 1 FROM memomics_cluster_nodes WHERE id=?", (node_id,)).fetchone())

    def list_servers(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT s.*, COUNT(n.id) AS node_count
                FROM memomics_cluster_servers s
                LEFT JOIN memomics_cluster_nodes n ON n.server_id=s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC, s.name COLLATE NOCASE
                """
            ).fetchall()
            out = []
            for row in rows:
                data = self._server_row(row)
                data["node_count"] = int(row["node_count"])
                out.append(data)
            return out
        finally:
            conn.close()

    def get_server(self, server_id: Any) -> dict[str, Any]:
        sid = _server_id(server_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM memomics_cluster_servers WHERE id=?", (sid,)).fetchone()
            if not row:
                raise CatalogError("catalog server not found", "server_not_found")
            data = self._server_row(row)
            data["node_count"] = int(conn.execute(
                "SELECT COUNT(*) FROM memomics_cluster_nodes WHERE server_id=?", (sid,)
            ).fetchone()[0])
            return data
        finally:
            conn.close()

    def create_server(self, name: Any, description: Any = "") -> dict[str, Any]:
        clean_name = _text(name, "name", 80, required=True)
        clean_description = _text(description, "description", 2_000)
        server_id = "cluster-" + uuid.uuid4().hex[:12]
        now = _now()
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO memomics_cluster_servers(id,name,description,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (server_id, clean_name, clean_description, now, now),
                )
                row = conn.execute("SELECT * FROM memomics_cluster_servers WHERE id=?", (server_id,)).fetchone()
                conn.execute("COMMIT")
                data = self._server_row(row)
                data["node_count"] = 0
                return data
            except sqlite3.IntegrityError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise CatalogError("a catalog server with this name already exists", "server_name_conflict") from exc
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def update_server(self, server_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
        sid = _server_id(server_id)
        allowed = {"name", "description"}
        unknown = set(payload or {}) - allowed
        if unknown:
            raise CatalogError("unsupported server fields: " + ", ".join(sorted(unknown)))
        if not payload:
            raise CatalogError("no server fields supplied")
        values: dict[str, Any] = {}
        if "name" in payload:
            values["name"] = _text(payload.get("name"), "name", 80, required=True)
        if "description" in payload:
            values["description"] = _text(payload.get("description"), "description", 2_000)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not self._server_exists(conn, sid):
                    raise CatalogError("catalog server not found", "server_not_found")
                fields = list(values)
                conn.execute(
                    "UPDATE memomics_cluster_servers SET " + ", ".join(f"{field}=?" for field in fields)
                    + ", updated_at=? WHERE id=?",
                    tuple(values[field] for field in fields) + (_now(), sid),
                )
                row = conn.execute("SELECT * FROM memomics_cluster_servers WHERE id=?", (sid,)).fetchone()
                count = conn.execute("SELECT COUNT(*) FROM memomics_cluster_nodes WHERE server_id=?", (sid,)).fetchone()[0]
                conn.execute("COMMIT")
                data = self._server_row(row)
                data["node_count"] = int(count)
                return data
            except sqlite3.IntegrityError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise CatalogError("a catalog server with this name already exists", "server_name_conflict") from exc
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def delete_server(self, server_id: Any) -> None:
        sid = _server_id(server_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not self._server_exists(conn, sid):
                    raise CatalogError("catalog server not found", "server_not_found")
                node_count = int(conn.execute(
                    "SELECT COUNT(*) FROM memomics_cluster_nodes WHERE server_id=?", (sid,)
                ).fetchone()[0])
                if node_count:
                    raise CatalogError("catalog server still contains nodes", "server_has_nodes")
                conn.execute("DELETE FROM memomics_cluster_servers WHERE id=?", (sid,))
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    @staticmethod
    def _node_values(
        payload: dict[str, Any], *, creating: bool, require_endpoint: bool = False,
    ) -> dict[str, Any]:
        allowed = {"name", "host", "port", "scheduler", "partition", "queue", "role", "note"}
        unknown = set(payload or {}) - allowed
        if unknown:
            raise CatalogError("unsupported node fields: " + ", ".join(sorted(unknown)))
        if creating and "name" not in payload:
            raise CatalogError("name is required")
        values: dict[str, Any] = {}
        if "name" in payload:
            values["name"] = _text(payload.get("name"), "name", 80, required=True)
        if "host" in payload:
            values["host"] = _text(payload.get("host"), "host", 253)
        if "port" in payload:
            values["port"] = _port(payload.get("port"))
        if "scheduler" in payload:
            values["scheduler"] = _scheduler(payload.get("scheduler"))
        for incoming, column, maximum in (
            ("partition", "partition_name", 160),
            ("queue", "queue_name", 160),
            ("role", "role", 160),
            ("note", "note", 2_000),
        ):
            if incoming in payload:
                values[column] = _text(payload.get(incoming), incoming, maximum)
        if require_endpoint:
            host = values.get("host", "")
            if not host:
                raise CatalogError("node host is required")
            # A catalog-created complete connection always has a concrete
            # endpoint.  The old draft-node method remains available only for
            # migration/compatibility callers, never for the V3 API.
            values["port"] = values.get("port") or 22
        return values

    @staticmethod
    def _begin(conn: sqlite3.Connection) -> None:
        conn.execute("BEGIN IMMEDIATE")

    @staticmethod
    def _rollback(conn: sqlite3.Connection) -> None:
        if conn.in_transaction:
            conn.execute("ROLLBACK")

    def _insert_node(
        self,
        conn: sqlite3.Connection,
        server_id: str,
        values: dict[str, Any],
        *,
        profile_id: str | None,
    ) -> dict[str, Any]:
        """Insert a node and its first strong account link in one SQLite tx."""
        node_id = "node-" + uuid.uuid4().hex[:12]
        now = _now()
        conn.execute(
            """
            INSERT INTO memomics_cluster_nodes(
                id,server_id,name,host,port,scheduler,partition_name,queue_name,role,note,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                node_id, server_id, values.get("name", ""), values.get("host", ""), values.get("port"),
                values.get("scheduler", ""), values.get("partition_name", ""), values.get("queue_name", ""),
                values.get("role", ""), values.get("note", ""), now, now,
            ),
        )
        if profile_id:
            if conn.execute(
                "SELECT 1 FROM memomics_cluster_account_links WHERE profile_id=?", (profile_id,)
            ).fetchone():
                raise CatalogError("account profile is already assigned to a node", "profile_already_linked")
            conn.execute(
                "INSERT INTO memomics_cluster_account_links(profile_id,node_id,created_at) VALUES(?,?,?)",
                (profile_id, node_id, now),
            )
        row = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (node_id,)).fetchone()
        return self._node_row(row, account_count=1 if profile_id else 0)

    def create_server_bundle(
        self,
        name: Any,
        description: Any,
        node_payload: dict[str, Any],
        profile_id: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Persist server, its first complete node, and first account link atomically.

        The caller has already created ``profile_id`` inside the adapter's
        reversible profile transaction.  If this SQLite transaction fails the
        caller rolls that profile creation back; no empty server/node is left.
        """
        clean_name = _text(name, "name", 80, required=True)
        clean_description = _text(description, "description", 2_000)
        values = self._node_values(node_payload, creating=True, require_endpoint=True)
        pid = _profile_id(profile_id)
        server_id = "cluster-" + uuid.uuid4().hex[:12]
        now = _now()
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                conn.execute(
                    "INSERT INTO memomics_cluster_servers(id,name,description,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (server_id, clean_name, clean_description, now, now),
                )
                node = self._insert_node(conn, server_id, values, profile_id=pid)
                server_row = conn.execute("SELECT * FROM memomics_cluster_servers WHERE id=?", (server_id,)).fetchone()
                conn.execute("COMMIT")
                server = self._server_row(server_row)
                server["node_count"] = 1
                return server, node
            except sqlite3.IntegrityError as exc:
                self._rollback(conn)
                raise CatalogError("a catalog server or node with this name already exists", "server_name_conflict") from exc
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def create_node_bundle(
        self, server_id: Any, node_payload: dict[str, Any], profile_id: Any,
    ) -> dict[str, Any]:
        """Persist a complete node and its first strong account link atomically."""
        sid = _server_id(server_id)
        values = self._node_values(node_payload, creating=True, require_endpoint=True)
        pid = _profile_id(profile_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                if not self._server_exists(conn, sid):
                    raise CatalogError("catalog server not found", "server_not_found")
                node = self._insert_node(conn, sid, values, profile_id=pid)
                conn.execute("COMMIT")
                return node
            except sqlite3.IntegrityError as exc:
                self._rollback(conn)
                raise CatalogError("a node with this name already exists in this server", "node_name_conflict") from exc
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def create_node(self, server_id: Any, payload: dict[str, Any], *, profile_id: Any | None = None) -> dict[str, Any]:
        sid = _server_id(server_id)
        values = self._node_values(payload, creating=True)
        node_id = "node-" + uuid.uuid4().hex[:12]
        profile = None if profile_id in (None, "") else _profile_id(profile_id)
        now = _now()
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not self._server_exists(conn, sid):
                    raise CatalogError("catalog server not found", "server_not_found")
                if profile and conn.execute(
                    "SELECT 1 FROM memomics_cluster_account_links WHERE profile_id=?", (profile,)
                ).fetchone():
                    raise CatalogError("account profile is already assigned to a node", "profile_already_linked")
                conn.execute(
                    """
                    INSERT INTO memomics_cluster_nodes(
                        id,server_id,name,host,port,scheduler,partition_name,queue_name,role,note,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        node_id, sid, values.get("name", ""), values.get("host", ""), values.get("port"),
                        values.get("scheduler", ""), values.get("partition_name", ""), values.get("queue_name", ""),
                        values.get("role", ""), values.get("note", ""), now, now,
                    ),
                )
                if profile:
                    conn.execute(
                        "INSERT INTO memomics_cluster_account_links(profile_id,node_id,created_at) VALUES(?,?,?)",
                        (profile, node_id, now),
                    )
                row = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (node_id,)).fetchone()
                conn.execute("COMMIT")
                return self._node_row(row, account_count=1 if profile else 0)
            except sqlite3.IntegrityError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise CatalogError("a node with this name already exists in this server", "node_name_conflict") from exc
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def get_node(self, node_id: Any) -> dict[str, Any]:
        nid = _node_id(node_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (nid,)).fetchone()
            if not row:
                raise CatalogError("catalog node not found", "node_not_found")
            count = conn.execute("SELECT COUNT(*) FROM memomics_cluster_account_links WHERE node_id=?", (nid,)).fetchone()[0]
            return self._node_row(row, account_count=count)
        finally:
            conn.close()

    def list_nodes(self, server_id: Any | None = None) -> list[dict[str, Any]]:
        sid = None if server_id in (None, "") else _server_id(server_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            sql = (
                "SELECT n.*, COUNT(l.profile_id) AS account_count FROM memomics_cluster_nodes n "
                "LEFT JOIN memomics_cluster_account_links l ON l.node_id=n.id "
            )
            params: tuple[Any, ...] = ()
            if sid:
                sql += "WHERE n.server_id=? "
                params = (sid,)
            sql += "GROUP BY n.id ORDER BY n.updated_at DESC, n.name COLLATE NOCASE"
            rows = conn.execute(sql, params).fetchall()
            return [self._node_row(row, account_count=row["account_count"]) for row in rows]
        finally:
            conn.close()

    def update_node(self, node_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
        nid = _node_id(node_id)
        values = self._node_values(payload, creating=False)
        if not values:
            raise CatalogError("no node fields supplied")
        connection_fields = {"host", "port", "scheduler", "partition_name", "queue_name"}
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (nid,)).fetchone()
                if not row:
                    raise CatalogError("catalog node not found", "node_not_found")
                account_count = int(conn.execute(
                    "SELECT COUNT(*) FROM memomics_cluster_account_links WHERE node_id=?", (nid,)
                ).fetchone()[0])
                if account_count and connection_fields.intersection(values):
                    raise CatalogError(
                        "node connection fields are locked while accounts are assigned; delete the accounts or create another node first",
                        "node_has_accounts_connection_locked",
                    )
                fields = list(values)
                conn.execute(
                    "UPDATE memomics_cluster_nodes SET " + ", ".join(f"{field}=?" for field in fields)
                    + ", updated_at=? WHERE id=?",
                    tuple(values[field] for field in fields) + (_now(), nid),
                )
                updated = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (nid,)).fetchone()
                conn.execute("COMMIT")
                return self._node_row(updated, account_count=account_count)
            except sqlite3.IntegrityError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise CatalogError("a node with this name already exists in this server", "node_name_conflict") from exc
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def delete_node(self, node_id: Any) -> None:
        nid = _node_id(node_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not self._node_exists(conn, nid):
                    raise CatalogError("catalog node not found", "node_not_found")
                account_count = int(conn.execute(
                    "SELECT COUNT(*) FROM memomics_cluster_account_links WHERE node_id=?", (nid,)
                ).fetchone()[0])
                if account_count:
                    raise CatalogError("catalog node still contains accounts", "node_has_accounts")
                conn.execute("DELETE FROM memomics_cluster_nodes WHERE id=?", (nid,))
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def link_profile(self, node_id: Any, profile_id: Any) -> None:
        nid = _node_id(node_id)
        pid = _profile_id(profile_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not self._node_exists(conn, nid):
                    raise CatalogError("catalog node not found", "node_not_found")
                if conn.execute("SELECT 1 FROM memomics_cluster_account_links WHERE profile_id=?", (pid,)).fetchone():
                    raise CatalogError("account profile is already assigned to a node", "profile_already_linked")
                conn.execute(
                    "INSERT INTO memomics_cluster_account_links(profile_id,node_id,created_at) VALUES(?,?,?)",
                    (pid, nid, _now()),
                )
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def unlink_profile(self, node_id: Any, profile_id: Any) -> None:
        nid = _node_id(node_id)
        pid = _profile_id(profile_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                deleted = conn.execute(
                    "DELETE FROM memomics_cluster_account_links WHERE node_id=? AND profile_id=?", (nid, pid)
                ).rowcount
                if not deleted:
                    raise CatalogError("account profile is not assigned to this node", "profile_not_linked")
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def account_delete_plan(self, node_id: Any, profile_id: Any) -> dict[str, Any]:
        """Return the exact local profile that a strong account delete removes."""
        nid = _node_id(node_id)
        pid = _profile_id(profile_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT n.id,n.server_id,n.name FROM memomics_cluster_nodes n "
                "JOIN memomics_cluster_account_links l ON l.node_id=n.id "
                "WHERE n.id=? AND l.profile_id=?",
                (nid, pid),
            ).fetchone()
            if not row:
                raise CatalogError("account profile is not assigned to this node", "profile_not_linked")
            return {"node_id": nid, "server_id": str(row["server_id"]), "profile_ids": [pid]}
        finally:
            conn.close()

    def node_delete_plan(self, node_id: Any) -> dict[str, Any]:
        """Read a force-delete plan without mutating SQLite or remote config."""
        nid = _node_id(node_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (nid,)).fetchone()
            if not row:
                raise CatalogError("catalog node not found", "node_not_found")
            profiles = [str(item[0]) for item in conn.execute(
                "SELECT profile_id FROM memomics_cluster_account_links WHERE node_id=? ORDER BY profile_id", (nid,)
            ).fetchall()]
            return {
                "node_id": nid,
                "server_id": str(row["server_id"]),
                "profile_ids": profiles,
                "account_count": len(profiles),
            }
        finally:
            conn.close()

    def server_delete_plan(self, server_id: Any) -> dict[str, Any]:
        """Read all local descendants for one force-delete operation."""
        sid = _server_id(server_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            if not self._server_exists(conn, sid):
                raise CatalogError("catalog server not found", "server_not_found")
            node_ids = [str(item[0]) for item in conn.execute(
                "SELECT id FROM memomics_cluster_nodes WHERE server_id=? ORDER BY id", (sid,)
            ).fetchall()]
            profiles: list[str] = []
            for nid in node_ids:
                profiles.extend(str(item[0]) for item in conn.execute(
                    "SELECT profile_id FROM memomics_cluster_account_links WHERE node_id=? ORDER BY profile_id", (nid,)
                ).fetchall())
            return {
                "server_id": sid,
                "node_ids": node_ids,
                "profile_ids": profiles,
                "node_count": len(node_ids),
                "account_count": len(profiles),
            }
        finally:
            conn.close()

    def profile_delete_plan(self, profile_id: Any) -> dict[str, Any]:
        """Plan removal of a legacy/unassigned profile and any stale link."""
        pid = _profile_id(profile_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT node_id FROM memomics_cluster_account_links WHERE profile_id=? ORDER BY node_id", (pid,)
            ).fetchall()
            return {"profile_ids": [pid], "node_ids": [str(row[0]) for row in rows]}
        finally:
            conn.close()

    def delete_account_cascade(self, node_id: Any, profile_id: Any) -> dict[str, Any]:
        """Commit metadata half of a force account deletion after YAML removal."""
        plan = self.account_delete_plan(node_id, profile_id)
        nid, pid = plan["node_id"], plan["profile_ids"][0]
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                deleted = conn.execute(
                    "DELETE FROM memomics_cluster_account_links WHERE node_id=? AND profile_id=?", (nid, pid)
                ).rowcount
                if not deleted:
                    raise CatalogError("account profile is not assigned to this node", "profile_not_linked")
                conn.execute("COMMIT")
                return {**plan, "deleted_profile_ids": [pid]}
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def delete_node_cascade(self, node_id: Any) -> dict[str, Any]:
        """Commit metadata half of a force node deletion after YAML removal."""
        plan = self.node_delete_plan(node_id)
        nid = plan["node_id"]
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                if not self._node_exists(conn, nid):
                    raise CatalogError("catalog node not found", "node_not_found")
                conn.execute("DELETE FROM memomics_cluster_account_links WHERE node_id=?", (nid,))
                conn.execute("DELETE FROM memomics_cluster_nodes WHERE id=?", (nid,))
                conn.execute("COMMIT")
                return {**plan, "deleted_node_ids": [nid], "deleted_profile_ids": list(plan["profile_ids"])}
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def delete_server_cascade(self, server_id: Any) -> dict[str, Any]:
        """Commit metadata half of a force server deletion after YAML removal."""
        plan = self.server_delete_plan(server_id)
        sid = plan["server_id"]
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                if not self._server_exists(conn, sid):
                    raise CatalogError("catalog server not found", "server_not_found")
                for nid in plan["node_ids"]:
                    conn.execute("DELETE FROM memomics_cluster_account_links WHERE node_id=?", (nid,))
                conn.execute("DELETE FROM memomics_cluster_nodes WHERE server_id=?", (sid,))
                conn.execute("DELETE FROM memomics_cluster_servers WHERE id=?", (sid,))
                conn.execute("COMMIT")
                return {**plan, "deleted_server_id": sid, "deleted_node_ids": list(plan["node_ids"]),
                        "deleted_profile_ids": list(plan["profile_ids"])}
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def delete_profile_anywhere(self, profile_id: Any) -> dict[str, Any]:
        """Remove stale catalog references after a legacy profile is removed."""
        plan = self.profile_delete_plan(profile_id)
        pid = plan["profile_ids"][0]
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                conn.execute("DELETE FROM memomics_cluster_account_links WHERE profile_id=?", (pid,))
                conn.execute("COMMIT")
                return {**plan, "deleted_profile_ids": [pid]}
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def unlink_profile_anywhere(self, profile_id: Any) -> bool:
        """Best-effort hook for legacy profile deletion; never deletes profiles."""
        pid = _profile_id(profile_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                return bool(conn.execute("DELETE FROM memomics_cluster_account_links WHERE profile_id=?", (pid,)).rowcount)
            finally:
                conn.close()

    def list_links(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT l.profile_id,l.node_id,l.created_at,n.server_id,n.name AS node_name
                FROM memomics_cluster_account_links l
                JOIN memomics_cluster_nodes n ON n.id=l.node_id
                ORDER BY l.created_at, l.profile_id
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # V4 server/node/account metadata.  These methods intentionally use
    # distinct names from the retired V3 one-shot helpers above, so a caller
    # cannot accidentally turn staged creation into profile creation.

    @staticmethod
    def _v4_server_row(
        row: sqlite3.Row, *, node_count: int = 0, requires_login_setup: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": str(row["id"]), "name": str(row["name"]),
            "description": str(row["description"] or ""),
            "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
            "node_count": int(node_count), "requires_login_setup": bool(requires_login_setup),
        }

    @staticmethod
    def _v4_node_row(row: sqlite3.Row, *, connection_count: int = 0) -> dict[str, Any]:
        return {
            "id": str(row["id"]), "server_id": str(row["server_id"]),
            "name": str(row["name"]), "host": str(row["host"] or ""),
            "port": int(row["port"]) if row["port"] is not None else None,
            "scheduler": str(row["scheduler"] or ""),
            "partition": str(row["partition_name"] or ""),
            "queue": str(row["queue_name"] or ""), "note": str(row["note"] or ""),
            "is_login": bool(row["is_login"]), "is_compute": bool(row["is_compute"]),
            "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
            "connection_count": int(connection_count),
        }

    @staticmethod
    def _v4_account_row(row: sqlite3.Row, *, connection_count: int = 0) -> dict[str, Any]:
        return {
            "id": str(row["id"]), "server_id": str(row["server_id"]),
            "name": str(row["name"]), "user": str(row["user"]),
            "note": str(row["note"] or ""), "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]), "connection_count": int(connection_count),
        }

    @staticmethod
    def _v4_node_values(
        payload: Any, *, creating: bool, require_endpoint: bool = False,
        require_compute: bool = False, force_login: bool | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise CatalogError("node must be an object")
        allowed = {"name", "host", "port", "scheduler", "partition", "queue", "note", "is_login", "is_compute"}
        unknown = set(payload) - allowed
        if unknown:
            raise CatalogError("unsupported node fields: " + ", ".join(sorted(unknown)))
        if creating and "name" not in payload:
            raise CatalogError("node name is required")
        values: dict[str, Any] = {}
        if "name" in payload:
            values["name"] = _v4_text(payload.get("name"), "node name", 80, required=True)
        if "host" in payload:
            values["host"] = _v4_host(payload.get("host"))
        if "port" in payload:
            values["port"] = _v4_port(payload.get("port"), required=True)
        if "scheduler" in payload:
            values["scheduler"] = _scheduler(payload.get("scheduler"))
        for incoming, column, maximum in (("partition", "partition_name", 160), ("queue", "queue_name", 160), ("note", "note", 2000)):
            if incoming in payload:
                values[column] = _v4_text(payload.get(incoming), incoming, maximum)
        if "is_login" in payload:
            values["is_login"] = _v4_bool(payload.get("is_login"), "is_login", required=True)
        if "is_compute" in payload:
            values["is_compute"] = _v4_bool(payload.get("is_compute"), "is_compute", required=True)
        if require_endpoint and ("host" not in values or "port" not in values):
            raise CatalogError("node host and port are required")
        if require_compute and "is_compute" not in values:
            raise CatalogError("is_compute is required")
        if force_login is not None:
            if "is_login" in values and values["is_login"] is not force_login:
                raise CatalogError("server login node must be a login node")
            values["is_login"] = force_login
        if creating:
            values.setdefault("scheduler", "auto")
            values.setdefault("partition_name", "")
            values.setdefault("queue_name", "")
            values.setdefault("note", "")
            values.setdefault("is_login", False)
        return values

    @staticmethod
    def _v4_account_values(payload: Any, *, creating: bool) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise CatalogError("account must be an object", "account_fields_invalid")
        allowed = {"name", "user", "note"}
        unknown = set(payload) - allowed
        if unknown:
            raise CatalogError("unsupported account fields: " + ", ".join(sorted(unknown)), "account_fields_invalid")
        if creating and ("name" not in payload or "user" not in payload):
            raise CatalogError("account name and user are required", "account_fields_invalid")
        values: dict[str, Any] = {}
        if "name" in payload:
            values["name"] = _v4_text(payload.get("name"), "account name", 120, required=True)
        if "user" in payload:
            values["user"] = _v4_text(payload.get("user"), "user", 253, required=True)
        if "note" in payload:
            values["note"] = _v4_text(payload.get("note"), "note", 2000)
        if creating:
            values.setdefault("note", "")
        return values

    @staticmethod
    def _v4_route_values(route: Any) -> tuple[str, str | None]:
        if not isinstance(route, dict):
            raise CatalogError("route must be an object", "route_invalid")
        unknown = set(route) - {"mode", "gateway_profile_id"}
        if unknown:
            raise CatalogError("unsupported route fields", "route_invalid")
        mode = _v4_text(route.get("mode"), "route mode", 20, required=True)
        if mode not in _ROUTE_MODES:
            raise CatalogError("route mode must be direct or via_login", "route_invalid")
        gateway = route.get("gateway_profile_id")
        if mode == "direct":
            if gateway not in (None, ""):
                raise CatalogError("direct route cannot have a gateway", "route_invalid")
            return mode, None
        return mode, _profile_id(gateway)

    @staticmethod
    def _v4_server_exists(conn: sqlite3.Connection, server_id: str) -> bool:
        return bool(conn.execute("SELECT 1 FROM memomics_cluster_servers WHERE id=?", (server_id,)).fetchone())

    def v4_list_servers(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT s.*, COUNT(n.id) AS node_count,
                       SUM(CASE WHEN n.is_login=1 AND trim(n.host)<>'' AND n.port BETWEEN 1 AND 65535 THEN 1 ELSE 0 END) AS usable_login_count
                FROM memomics_cluster_servers s
                LEFT JOIN memomics_cluster_nodes n ON n.server_id=s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC,s.name COLLATE NOCASE
                """
            ).fetchall()
            return [self._v4_server_row(
                row, node_count=int(row["node_count"]), requires_login_setup=not bool(row["usable_login_count"]),
            ) for row in rows]
        finally:
            conn.close()

    def v4_get_server(self, server_id: Any) -> dict[str, Any]:
        sid = _server_id(server_id)
        for server in self.v4_list_servers():
            if server["id"] == sid:
                return server
        raise CatalogError("catalog server not found", "server_not_found")

    def _v4_insert_node(self, conn: sqlite3.Connection, server_id: str, values: dict[str, Any]) -> dict[str, Any]:
        node_id = "node-" + uuid.uuid4().hex[:12]
        now = _now()
        conn.execute(
            """
            INSERT INTO memomics_cluster_nodes(
                id,server_id,name,host,port,scheduler,partition_name,queue_name,role,note,is_login,is_compute,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                node_id, server_id, values["name"], values["host"], values["port"],
                values.get("scheduler", "auto"), values.get("partition_name", ""), values.get("queue_name", ""),
                "login" if values.get("is_login") else "compute", values.get("note", ""),
                int(bool(values.get("is_login"))), int(bool(values.get("is_compute"))), now, now,
            ),
        )
        row = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (node_id,)).fetchone()
        return self._v4_node_row(row)

    def v4_create_server(self, name: Any, description: Any, login_node: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        clean_name = _v4_text(name, "name", 80, required=True)
        clean_description = _v4_text(description, "description", 2000)
        values = self._v4_node_values(
            login_node, creating=True, require_endpoint=True, require_compute=True, force_login=True,
        )
        server_id = "cluster-" + uuid.uuid4().hex[:12]
        now = _now()
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                conn.execute(
                    "INSERT INTO memomics_cluster_servers(id,name,description,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (server_id, clean_name, clean_description, now, now),
                )
                node = self._v4_insert_node(conn, server_id, values)
                row = conn.execute("SELECT * FROM memomics_cluster_servers WHERE id=?", (server_id,)).fetchone()
                conn.execute("COMMIT")
                return self._v4_server_row(row, node_count=1, requires_login_setup=False), node
            except sqlite3.IntegrityError as exc:
                self._rollback(conn)
                raise CatalogError("a catalog server or node with this name already exists", "server_name_conflict") from exc
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v5_create_server(self, name: Any, description: Any, login_node: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        """Create a V5 server with a true login-only entry point.

        V4 required callers to explicitly include ``is_compute`` on the first
        node.  V5's guided server form always creates a fixed login entry and
        must allow ``is_compute=False`` (or omit the implementation detail
        entirely).  The V4 method remains unchanged for legacy callers.
        """
        clean_name = _v4_text(name, "name", 80, required=True)
        clean_description = _v4_text(description, "description", 2000)
        values = self._v4_node_values(
            login_node, creating=True, require_endpoint=True, require_compute=False, force_login=True,
        )
        values.setdefault("is_compute", False)
        server_id = "cluster-" + uuid.uuid4().hex[:12]
        now = _now()
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                conn.execute(
                    "INSERT INTO memomics_cluster_servers(id,name,description,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (server_id, clean_name, clean_description, now, now),
                )
                node = self._v4_insert_node(conn, server_id, values)
                row = conn.execute("SELECT * FROM memomics_cluster_servers WHERE id=?", (server_id,)).fetchone()
                conn.execute("COMMIT")
                return self._v4_server_row(row, node_count=1, requires_login_setup=False), node
            except sqlite3.IntegrityError as exc:
                self._rollback(conn)
                raise CatalogError("a catalog server or node with this name already exists", "server_name_conflict") from exc
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v4_update_server(self, server_id: Any, payload: Any) -> dict[str, Any]:
        sid = _server_id(server_id)
        if not isinstance(payload, dict):
            raise CatalogError("server must be an object")
        unknown = set(payload) - {"name", "description"}
        if unknown:
            raise CatalogError("unsupported server fields: " + ", ".join(sorted(unknown)))
        if not payload:
            raise CatalogError("no server fields supplied")
        values: dict[str, Any] = {}
        if "name" in payload:
            values["name"] = _v4_text(payload.get("name"), "name", 80, required=True)
        if "description" in payload:
            values["description"] = _v4_text(payload.get("description"), "description", 2000)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                if not self._v4_server_exists(conn, sid):
                    raise CatalogError("catalog server not found", "server_not_found")
                conn.execute(
                    "UPDATE memomics_cluster_servers SET " + ", ".join(f"{field}=?" for field in values)
                    + ",updated_at=? WHERE id=?", tuple(values.values()) + (_now(), sid),
                )
                conn.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._rollback(conn)
                raise CatalogError("a catalog server with this name already exists", "server_name_conflict") from exc
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()
        return self.v4_get_server(sid)

    def v4_create_node(self, server_id: Any, payload: Any) -> dict[str, Any]:
        sid = _server_id(server_id)
        values = self._v4_node_values(payload, creating=True, require_endpoint=True, require_compute=True)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                if not self._v4_server_exists(conn, sid):
                    raise CatalogError("catalog server not found", "server_not_found")
                node = self._v4_insert_node(conn, sid, values)
                conn.execute("COMMIT")
                return node
            except sqlite3.IntegrityError as exc:
                self._rollback(conn)
                raise CatalogError("a node with this name already exists in this server", "node_name_conflict") from exc
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v5_create_node(self, server_id: Any, payload: Any) -> dict[str, Any]:
        """Create a non-login V5 node without exposing role plumbing in UI."""
        sid = _server_id(server_id)
        values = self._v4_node_values(
            payload, creating=True, require_endpoint=True, require_compute=False, force_login=False,
        )
        values.setdefault("is_compute", True)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                if not self._v4_server_exists(conn, sid):
                    raise CatalogError("catalog server not found", "server_not_found")
                node = self._v4_insert_node(conn, sid, values)
                conn.execute("COMMIT")
                return node
            except sqlite3.IntegrityError as exc:
                self._rollback(conn)
                raise CatalogError("a node with this name already exists in this server", "node_name_conflict") from exc
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v4_list_nodes(self, server_id: Any | None = None) -> list[dict[str, Any]]:
        sid = None if server_id in (None, "") else _server_id(server_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            sql = (
                "SELECT n.*,COUNT(c.profile_id) AS connection_count FROM memomics_cluster_nodes n "
                "LEFT JOIN memomics_cluster_connections c ON c.node_id=n.id "
            )
            params: tuple[Any, ...] = ()
            if sid:
                sql += "WHERE n.server_id=? "
                params = (sid,)
            sql += "GROUP BY n.id ORDER BY n.created_at,n.name COLLATE NOCASE"
            rows = conn.execute(sql, params).fetchall()
            return [self._v4_node_row(row, connection_count=int(row["connection_count"])) for row in rows]
        finally:
            conn.close()

    def v4_get_node(self, node_id: Any) -> dict[str, Any]:
        nid = _node_id(node_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (nid,)).fetchone()
            if not row:
                raise CatalogError("catalog node not found", "node_not_found")
            count = conn.execute("SELECT COUNT(*) FROM memomics_cluster_connections WHERE node_id=?", (nid,)).fetchone()[0]
            return self._v4_node_row(row, connection_count=int(count))
        finally:
            conn.close()

    def v4_update_node(self, node_id: Any, payload: Any) -> dict[str, Any]:
        nid = _node_id(node_id)
        values = self._v4_node_values(payload, creating=False)
        if not values:
            raise CatalogError("no node fields supplied")
        endpoint_fields = {"host", "port", "scheduler", "partition_name", "queue_name"}
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                row = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (nid,)).fetchone()
                if not row:
                    raise CatalogError("catalog node not found", "node_not_found")
                connection_count = int(conn.execute(
                    "SELECT COUNT(*) FROM memomics_cluster_connections WHERE node_id=?", (nid,)
                ).fetchone()[0])
                if connection_count and endpoint_fields.intersection(values):
                    raise CatalogError(
                        "node connection fields are locked while matched connections exist; rematch a new node instead",
                        "node_has_connections_connection_locked",
                    )
                was_usable_login = is_usable_login_node(row)
                prospective = {
                    "is_login": values.get("is_login", row["is_login"]),
                    "host": values.get("host", row["host"]),
                    "port": values.get("port", row["port"]),
                }
                will_be_usable_login = is_usable_login_node(prospective)
                if values.get("is_login") is True and not bool(row["is_login"]):
                    candidate_host = str(values.get("host", row["host"]) or "").strip()
                    candidate_port = values.get("port", row["port"])
                    if not candidate_host or candidate_port is None or not 1 <= int(candidate_port) <= 65535:
                        raise CatalogError("a login node needs a concrete host and port", "login_replacement_invalid")
                if was_usable_login and not will_be_usable_login:
                    other_usable_login_count = int(conn.execute(
                        "SELECT COUNT(*) FROM memomics_cluster_nodes WHERE server_id=? AND id<>? AND "
                        + _V4_USABLE_LOGIN_SQL, (str(row["server_id"]), nid),
                    ).fetchone()[0])
                    if not other_usable_login_count:
                        raise CatalogError("server must retain a login node", "last_login_node")
                    dependents = int(conn.execute(
                        """SELECT COUNT(*) FROM memomics_cluster_connections c
                           JOIN memomics_cluster_connections g ON g.profile_id=c.gateway_profile_id
                           WHERE g.node_id=?""", (nid,)
                    ).fetchone()[0])
                    if dependents:
                        raise CatalogError("login node is used by gateway connections", "login_node_has_gateway_dependents")
                fields = list(values)
                conn.execute(
                    "UPDATE memomics_cluster_nodes SET " + ",".join(f"{field}=?" for field in fields)
                    + ",updated_at=? WHERE id=?",
                    tuple(values[field] for field in fields) + (_now(), nid),
                )
                updated = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (nid,)).fetchone()
                conn.execute("COMMIT")
                return self._v4_node_row(updated, connection_count=connection_count)
            except sqlite3.IntegrityError as exc:
                self._rollback(conn)
                raise CatalogError("a node with this name already exists in this server", "node_name_conflict") from exc
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v4_create_account(self, server_id: Any, payload: Any) -> dict[str, Any]:
        sid = _server_id(server_id)
        values = self._v4_account_values(payload, creating=True)
        aid = "account-" + uuid.uuid4().hex[:12]
        now = _now()
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                if not self._v4_server_exists(conn, sid):
                    raise CatalogError("catalog server not found", "server_not_found")
                conn.execute(
                    "INSERT INTO memomics_cluster_accounts(id,server_id,name,user,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (aid, sid, values["name"], values["user"], values.get("note", ""), now, now),
                )
                row = conn.execute("SELECT * FROM memomics_cluster_accounts WHERE id=?", (aid,)).fetchone()
                conn.execute("COMMIT")
                return self._v4_account_row(row)
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v4_list_accounts(self, server_id: Any | None = None) -> list[dict[str, Any]]:
        sid = None if server_id in (None, "") else _server_id(server_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            sql = (
                "SELECT a.*,COUNT(c.profile_id) AS connection_count FROM memomics_cluster_accounts a "
                "LEFT JOIN memomics_cluster_connections c ON c.account_id=a.id "
            )
            params: tuple[Any, ...] = ()
            if sid:
                sql += "WHERE a.server_id=? "
                params = (sid,)
            sql += "GROUP BY a.id ORDER BY a.created_at,a.name COLLATE NOCASE,a.id"
            rows = conn.execute(sql, params).fetchall()
            return [self._v4_account_row(row, connection_count=int(row["connection_count"])) for row in rows]
        finally:
            conn.close()

    def v4_get_account(self, account_id: Any) -> dict[str, Any]:
        aid = _account_id(account_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM memomics_cluster_accounts WHERE id=?", (aid,)).fetchone()
            if not row:
                raise CatalogError("catalog account not found", "account_not_found")
            count = conn.execute("SELECT COUNT(*) FROM memomics_cluster_connections WHERE account_id=?", (aid,)).fetchone()[0]
            return self._v4_account_row(row, connection_count=int(count))
        finally:
            conn.close()

    def v4_update_account(self, account_id: Any, payload: Any) -> dict[str, Any]:
        aid = _account_id(account_id)
        values = self._v4_account_values(payload, creating=False)
        if not values:
            raise CatalogError("no account fields supplied", "account_fields_invalid")
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                row = conn.execute("SELECT * FROM memomics_cluster_accounts WHERE id=?", (aid,)).fetchone()
                if not row:
                    raise CatalogError("catalog account not found", "account_not_found")
                connection_count = int(conn.execute(
                    "SELECT COUNT(*) FROM memomics_cluster_connections WHERE account_id=?", (aid,)
                ).fetchone()[0])
                # Complete edit forms submit the unchanged username too.  A
                # matched account must forbid only an actual identity change,
                # not a display/password update that happens to include the
                # same user value.
                if connection_count and "user" in values and values["user"] != str(row["user"]):
                    raise CatalogError(
                        "account user is locked while matched connections exist; delete or rematch the connection first",
                        "account_has_connections_user_locked",
                    )
                conn.execute(
                    "UPDATE memomics_cluster_accounts SET " + ",".join(f"{field}=?" for field in values)
                    + ",updated_at=? WHERE id=?", tuple(values.values()) + (_now(), aid),
                )
                updated = conn.execute("SELECT * FROM memomics_cluster_accounts WHERE id=?", (aid,)).fetchone()
                conn.execute("COMMIT")
                return self._v4_account_row(updated, connection_count=connection_count)
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # V4 matched connections.  A connection is the only relation that owns a
    # remote profile id; nodes and accounts remain useful independently.

    @staticmethod
    def _v4_connection_row(row: sqlite3.Row) -> dict[str, Any]:
        route: dict[str, Any] = {"mode": str(row["route_mode"])}
        if row["gateway_profile_id"]:
            route["gateway_profile_id"] = str(row["gateway_profile_id"])
        if bool(row["legacy_route_needs_review"]):
            route["legacy_route_needs_review"] = True
        return {
            "profile_id": str(row["profile_id"]), "server_id": str(row["server_id"]),
            "node_id": str(row["node_id"]), "account_id": str(row["account_id"]),
            "route": route,
            "last_connected_at": str(row["last_connected_at"]) if row["last_connected_at"] else None,
            "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
        }

    def _v4_assert_entities(
        self, conn: sqlite3.Connection, server_id: str, node_id: str, account_id: str,
    ) -> tuple[sqlite3.Row, sqlite3.Row]:
        if not self._v4_server_exists(conn, server_id):
            raise CatalogError("catalog server not found", "server_not_found")
        node = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (node_id,)).fetchone()
        account = conn.execute("SELECT * FROM memomics_cluster_accounts WHERE id=?", (account_id,)).fetchone()
        if not node:
            raise CatalogError("catalog node not found", "node_not_found")
        if not account:
            raise CatalogError("catalog account not found", "account_not_found")
        if str(node["server_id"]) != server_id or str(account["server_id"]) != server_id:
            raise CatalogError("node and account must belong to this server", "connection_server_mismatch")
        return node, account

    @staticmethod
    def _v4_gateway_row(
        conn: sqlite3.Connection, server_id: str, gateway_profile_id: str, *, target_profile_id: str | None = None,
    ) -> sqlite3.Row:
        if target_profile_id and gateway_profile_id == target_profile_id:
            raise CatalogError("a connection cannot route through itself", "route_cycle")
        row = conn.execute(
            """SELECT c.*,n.is_login,n.host,n.port,n.server_id AS node_server_id
               FROM memomics_cluster_connections c
               JOIN memomics_cluster_nodes n ON n.id=c.node_id
               WHERE c.profile_id=?""", (gateway_profile_id,)
        ).fetchone()
        if not row:
            raise CatalogError("gateway connection not found", "gateway_not_found")
        if str(row["server_id"]) != server_id or str(row["node_server_id"]) != server_id:
            raise CatalogError("gateway connection must belong to the same server", "gateway_server_mismatch")
        if not is_usable_login_node(row):
            raise CatalogError("gateway connection must use a login node", "gateway_not_login")
        # Require a direct gateway.  This forbids loops and avoids implicit
        # multi-hop semantics that the remote executor does not support.
        if str(row["route_mode"]) != "direct":
            raise CatalogError("gateway connection must be direct", "route_cycle")
        return row

    def _v4_connection_records(
        self, conn: sqlite3.Connection, where: str = "", params: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT c.profile_id,c.server_id,c.node_id,c.account_id,c.route_mode,c.gateway_profile_id,
                   c.legacy_route_needs_review,c.last_connected_at,c.created_at AS c_created_at,c.updated_at AS c_updated_at,
                   n.id AS n_id,n.server_id AS n_server_id,n.name AS n_name,n.host AS n_host,n.port AS n_port,
                   n.scheduler AS n_scheduler,n.partition_name AS n_partition,n.queue_name AS n_queue,n.note AS n_note,
                   n.is_login AS n_is_login,n.is_compute AS n_is_compute,n.created_at AS n_created_at,n.updated_at AS n_updated_at,
                   a.id AS a_id,a.server_id AS a_server_id,a.name AS a_name,a.user AS a_user,a.note AS a_note,
                   a.created_at AS a_created_at,a.updated_at AS a_updated_at
            FROM memomics_cluster_connections c
            JOIN memomics_cluster_nodes n ON n.id=c.node_id
            JOIN memomics_cluster_accounts a ON a.id=c.account_id
            """ + where + " ORDER BY c.created_at,c.profile_id", params,
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            route: dict[str, Any] = {"mode": str(row["route_mode"])}
            if row["gateway_profile_id"]:
                route["gateway_profile_id"] = str(row["gateway_profile_id"])
            if bool(row["legacy_route_needs_review"]):
                route["legacy_route_needs_review"] = True
            connection = {
                "profile_id": str(row["profile_id"]), "server_id": str(row["server_id"]),
                "node_id": str(row["node_id"]), "account_id": str(row["account_id"]), "route": route,
                "last_connected_at": str(row["last_connected_at"]) if row["last_connected_at"] else None,
                "created_at": str(row["c_created_at"]), "updated_at": str(row["c_updated_at"]),
            }
            node = {
                "id": str(row["n_id"]), "server_id": str(row["n_server_id"]), "name": str(row["n_name"]),
                "host": str(row["n_host"] or ""), "port": int(row["n_port"]) if row["n_port"] is not None else None,
                "scheduler": str(row["n_scheduler"] or ""), "partition": str(row["n_partition"] or ""),
                "queue": str(row["n_queue"] or ""), "note": str(row["n_note"] or ""),
                "is_login": bool(row["n_is_login"]), "is_compute": bool(row["n_is_compute"]),
                "created_at": str(row["n_created_at"]), "updated_at": str(row["n_updated_at"]),
            }
            account = {
                "id": str(row["a_id"]), "server_id": str(row["a_server_id"]), "name": str(row["a_name"]),
                "user": str(row["a_user"]), "note": str(row["a_note"] or ""),
                "created_at": str(row["a_created_at"]), "updated_at": str(row["a_updated_at"]),
            }
            # ``connection`` is intentionally metadata only.  The adapter
            # receives it with trusted node/account records, never raw YAML.
            result.append({**connection, "node": node, "account": account, "connection": dict(connection)})
        return result

    def v4_list_connection_records(self, server_id: Any | None = None) -> list[dict[str, Any]]:
        sid = None if server_id in (None, "") else _server_id(server_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            return self._v4_connection_records(conn, "WHERE c.server_id=?" if sid else "", (sid,) if sid else ())
        finally:
            conn.close()

    def v4_get_connection_record(self, profile_id: Any) -> dict[str, Any]:
        pid = _profile_id(profile_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            rows = self._v4_connection_records(conn, "WHERE c.profile_id=?", (pid,))
            if not rows:
                raise CatalogError("catalog connection not found", "connection_not_found")
            return rows[0]
        finally:
            conn.close()

    def v4_connection_for_pair(self, server_id: Any, node_id: Any, account_id: Any) -> dict[str, Any] | None:
        sid, nid, aid = _server_id(server_id), _node_id(node_id), _account_id(account_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            rows = self._v4_connection_records(
                conn, "WHERE c.server_id=? AND c.node_id=? AND c.account_id=?", (sid, nid, aid),
            )
            return rows[0] if rows else None
        finally:
            conn.close()

    def v4_upsert_connection(
        self, server_id: Any, node_id: Any, account_id: Any, profile_id: Any, route: Any, *, connected: bool,
    ) -> dict[str, Any]:
        sid, nid, aid, pid = _server_id(server_id), _node_id(node_id), _account_id(account_id), _profile_id(profile_id)
        route_mode, gateway = self._v4_route_values(route)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                self._v4_assert_entities(conn, sid, nid, aid)
                if gateway:
                    self._v4_gateway_row(conn, sid, gateway, target_profile_id=pid)
                pair = conn.execute(
                    "SELECT profile_id FROM memomics_cluster_connections WHERE node_id=? AND account_id=?", (nid, aid),
                ).fetchone()
                existing = conn.execute(
                    "SELECT profile_id,node_id,account_id FROM memomics_cluster_connections WHERE profile_id=?", (pid,)
                ).fetchone()
                if pair and str(pair["profile_id"]) != pid:
                    raise CatalogError("node and account already have a different matched connection", "connection_pair_exists")
                if existing and (str(existing["node_id"]) != nid or str(existing["account_id"]) != aid):
                    raise CatalogError("profile id is already assigned to another connection", "profile_already_connected")
                now = _now()
                if existing:
                    conn.execute(
                        """UPDATE memomics_cluster_connections
                           SET route_mode=?,gateway_profile_id=?,legacy_route_needs_review=0,
                               last_connected_at=CASE WHEN ? THEN ? ELSE last_connected_at END,updated_at=?
                           WHERE profile_id=?""",
                        (route_mode, gateway, int(bool(connected)), now, now, pid),
                    )
                else:
                    conn.execute(
                        """INSERT INTO memomics_cluster_connections(
                               profile_id,server_id,node_id,account_id,route_mode,gateway_profile_id,
                               legacy_route_needs_review,last_connected_at,created_at,updated_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (pid, sid, nid, aid, route_mode, gateway, 0, now if connected else None, now, now),
                    )
                row = conn.execute("SELECT * FROM memomics_cluster_connections WHERE profile_id=?", (pid,)).fetchone()
                conn.execute("COMMIT")
                return self._v4_connection_row(row)
            except sqlite3.IntegrityError as exc:
                self._rollback(conn)
                raise CatalogError("connection relationship is invalid", "connection_invalid") from exc
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v4_touch_connection(self, profile_id: Any) -> dict[str, Any]:
        pid = _profile_id(profile_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                row = conn.execute("SELECT * FROM memomics_cluster_connections WHERE profile_id=?", (pid,)).fetchone()
                if not row:
                    raise CatalogError("catalog connection not found", "connection_not_found")
                now = _now()
                conn.execute(
                    "UPDATE memomics_cluster_connections SET last_connected_at=?,updated_at=? WHERE profile_id=?",
                    (now, now, pid),
                )
                row = conn.execute("SELECT * FROM memomics_cluster_connections WHERE profile_id=?", (pid,)).fetchone()
                conn.execute("COMMIT")
                return self._v4_connection_row(row)
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v4_migrate_legacy_links(self, profiles: Iterable[dict[str, Any]]) -> list[str]:
        """Migrate valid V3 links independently and retain all source rows.

        Missing profiles, missing users, empty servers, and legacy proxy routes
        are not guessed.  The latter receive an explicit review flag while the
        existing remote profile remains untouched.
        """
        profile_by_id = {
            str(item.get("id") or item.get("profile_id") or ""): dict(item)
            for item in profiles
            if isinstance(item, dict) and str(item.get("id") or item.get("profile_id") or "")
        }
        migrated: list[str] = []
        for link in self.list_links():
            pid = str(link["profile_id"])
            profile = profile_by_id.get(pid)
            if not profile:
                continue
            try:
                if self._v4_migrate_legacy_link(pid, str(link["node_id"]), profile):
                    migrated.append(pid)
            except CatalogError:
                # Keep the retained V3 link visible; an untrusted/malformed
                # historical profile must not block catalog rendering.
                continue
        return migrated

    def _v4_migrate_legacy_link(self, profile_id: str, node_id: str, profile: dict[str, Any]) -> bool:
        pid, nid = _profile_id(profile_id), _node_id(node_id)
        name = _v4_text(profile.get("name") or pid, "account name", 120, required=True)
        user = _v4_text(profile.get("user"), "user", 253, required=True)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                link = conn.execute(
                    "SELECT node_id FROM memomics_cluster_account_links WHERE profile_id=?", (pid,)
                ).fetchone()
                if not link or str(link["node_id"]) != nid:
                    conn.execute("COMMIT")
                    return False
                existing = conn.execute(
                    "SELECT account_id FROM memomics_cluster_connections WHERE profile_id=?", (pid,)
                ).fetchone()
                if existing:
                    conn.execute(
                        "INSERT OR IGNORE INTO memomics_cluster_legacy_link_migrations(profile_id,node_id,account_id,migrated_at) VALUES(?,?,?,?)",
                        (pid, nid, str(existing["account_id"]), _now()),
                    )
                    conn.execute("COMMIT")
                    return False
                node = conn.execute("SELECT server_id FROM memomics_cluster_nodes WHERE id=?", (nid,)).fetchone()
                if not node:
                    raise CatalogError("catalog node not found", "node_not_found")
                aid, now = "account-" + uuid.uuid4().hex[:12], _now()
                conn.execute(
                    "INSERT INTO memomics_cluster_accounts(id,server_id,name,user,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (aid, str(node["server_id"]), name, user, "Migrated from V3 profile", now, now),
                )
                needs_review = int(bool(str(profile.get("proxy_jump") or "").strip()))
                conn.execute(
                    """INSERT INTO memomics_cluster_connections(
                           profile_id,server_id,node_id,account_id,route_mode,gateway_profile_id,
                           legacy_route_needs_review,last_connected_at,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (pid, str(node["server_id"]), nid, aid, "direct", None, needs_review, None, now, now),
                )
                conn.execute(
                    "INSERT INTO memomics_cluster_legacy_link_migrations(profile_id,node_id,account_id,migrated_at) VALUES(?,?,?,?)",
                    (pid, nid, aid, now),
                )
                conn.execute("COMMIT")
                return True
            except sqlite3.IntegrityError as exc:
                self._rollback(conn)
                raise CatalogError("legacy profile migration failed", "legacy_migration_failed") from exc
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Destructive-plan helpers.  The API obtains a plan, changes remote YAML
    # inside its existing transaction, and then applies exactly this SQLite
    # half.  This keeps one remote batch + one SQLite transaction and lets the
    # remote-side journal remain the sole recovery authority.

    @staticmethod
    def _v4_expand_gateway_dependents(
        conn: sqlite3.Connection, profile_ids: Iterable[str], server_id: str,
    ) -> list[str]:
        ordered: list[str] = []
        queue = [str(value) for value in profile_ids]
        seen: set[str] = set()
        while queue:
            pid = queue.pop(0)
            if pid in seen:
                continue
            seen.add(pid)
            row = conn.execute(
                "SELECT profile_id,server_id FROM memomics_cluster_connections WHERE profile_id=?", (pid,)
            ).fetchone()
            if not row:
                continue
            if str(row["server_id"]) != server_id:
                raise CatalogError("cross-server gateway dependency is invalid", "gateway_server_mismatch")
            ordered.append(pid)
            queue.extend(str(item[0]) for item in conn.execute(
                "SELECT profile_id FROM memomics_cluster_connections WHERE gateway_profile_id=? ORDER BY profile_id", (pid,)
            ).fetchall())
        return ordered

    def v4_connection_delete_plan(self, profile_id: Any) -> dict[str, Any]:
        pid = _profile_id(profile_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM memomics_cluster_connections WHERE profile_id=?", (pid,)).fetchone()
            if not row:
                raise CatalogError("catalog connection not found", "connection_not_found")
            return {
                "server_id": str(row["server_id"]), "connection_profile_id": pid,
                "profile_ids": self._v4_expand_gateway_dependents(conn, [pid], str(row["server_id"])),
            }
        finally:
            conn.close()

    def v4_account_delete_plan(self, account_id: Any) -> dict[str, Any]:
        aid = _account_id(account_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            account = conn.execute("SELECT * FROM memomics_cluster_accounts WHERE id=?", (aid,)).fetchone()
            if not account:
                raise CatalogError("catalog account not found", "account_not_found")
            sid = str(account["server_id"])
            direct = [str(row[0]) for row in conn.execute(
                "SELECT profile_id FROM memomics_cluster_connections WHERE account_id=? ORDER BY profile_id", (aid,)
            ).fetchall()]
            return {
                "server_id": sid, "account_id": aid,
                "profile_ids": self._v4_expand_gateway_dependents(conn, direct, sid),
            }
        finally:
            conn.close()

    def v4_node_delete_plan(self, node_id: Any, replacement_node_id: Any | None = None) -> dict[str, Any]:
        nid = _node_id(node_id)
        replacement = None if replacement_node_id in (None, "") else _node_id(replacement_node_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            node = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (nid,)).fetchone()
            if not node:
                raise CatalogError("catalog node not found", "node_not_found")
            sid = str(node["server_id"])
            promote: str | None = None
            if is_usable_login_node(node):
                usable_login_count = int(conn.execute(
                    "SELECT COUNT(*) FROM memomics_cluster_nodes WHERE server_id=? AND "
                    + _V4_USABLE_LOGIN_SQL, (sid,)
                ).fetchone()[0])
                if usable_login_count <= 1:
                    if not replacement:
                        raise CatalogError(
                            "deleting the only login node requires a same-server replacement or deleting the server",
                            "login_replacement_required",
                        )
                    candidate = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (replacement,)).fetchone()
                    if (
                        not candidate or replacement == nid or str(candidate["server_id"]) != sid
                        or not str(candidate["host"] or "").strip()
                        or candidate["port"] is None or not 1 <= int(candidate["port"]) <= 65535
                    ):
                        raise CatalogError("replacement node must belong to the same server", "login_replacement_invalid")
                    promote = replacement
            direct = [str(row[0]) for row in conn.execute(
                "SELECT profile_id FROM memomics_cluster_connections WHERE node_id=? ORDER BY profile_id", (nid,)
            ).fetchall()]
            legacy = [str(row[0]) for row in conn.execute(
                "SELECT profile_id FROM memomics_cluster_account_links WHERE node_id=? ORDER BY profile_id", (nid,)
            ).fetchall()]
            profile_ids = self._v4_expand_gateway_dependents(conn, direct, sid)
            for pid in legacy:
                if pid not in profile_ids:
                    profile_ids.append(pid)
            return {
                "server_id": sid, "node_id": nid, "replacement_node_id": promote,
                "profile_ids": profile_ids, "legacy_profile_ids": legacy,
            }
        finally:
            conn.close()

    def v4_server_delete_plan(self, server_id: Any) -> dict[str, Any]:
        sid = _server_id(server_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            if not self._v4_server_exists(conn, sid):
                raise CatalogError("catalog server not found", "server_not_found")
            node_ids = [str(row[0]) for row in conn.execute(
                "SELECT id FROM memomics_cluster_nodes WHERE server_id=? ORDER BY id", (sid,)
            ).fetchall()]
            account_ids = [str(row[0]) for row in conn.execute(
                "SELECT id FROM memomics_cluster_accounts WHERE server_id=? ORDER BY id", (sid,)
            ).fetchall()]
            profile_ids = [str(row[0]) for row in conn.execute(
                "SELECT profile_id FROM memomics_cluster_connections WHERE server_id=? ORDER BY profile_id", (sid,)
            ).fetchall()]
            legacy = [str(row[0]) for row in conn.execute(
                """SELECT l.profile_id FROM memomics_cluster_account_links l
                   JOIN memomics_cluster_nodes n ON n.id=l.node_id
                   WHERE n.server_id=? ORDER BY l.profile_id""", (sid,)
            ).fetchall()]
            for pid in legacy:
                if pid not in profile_ids:
                    profile_ids.append(pid)
            return {
                "server_id": sid, "node_ids": node_ids, "account_ids": account_ids,
                "profile_ids": profile_ids, "legacy_profile_ids": legacy,
            }
        finally:
            conn.close()

    def v4_delete_connection_metadata(self, plan: dict[str, Any]) -> dict[str, Any]:
        profile_ids = [_profile_id(value) for value in plan.get("profile_ids") or []]
        if not profile_ids:
            raise CatalogError("connection deletion plan is empty", "connection_not_found")
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                conn.executemany("DELETE FROM memomics_cluster_connections WHERE profile_id=?", [(pid,) for pid in profile_ids])
                # A migrated V3 profile keeps its source link only while the
                # connection exists.  Otherwise a successful delete would
                # manufacture a misleading orphan on the next GET.
                conn.executemany("DELETE FROM memomics_cluster_account_links WHERE profile_id=?", [(pid,) for pid in profile_ids])
                conn.executemany("DELETE FROM memomics_cluster_legacy_link_migrations WHERE profile_id=?", [(pid,) for pid in profile_ids])
                conn.execute("COMMIT")
                return {"deleted_profile_ids": profile_ids}
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v4_delete_account_metadata(self, plan: dict[str, Any]) -> dict[str, Any]:
        aid = _account_id(plan.get("account_id"))
        profile_ids = [_profile_id(value) for value in plan.get("profile_ids") or []]
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                conn.executemany("DELETE FROM memomics_cluster_connections WHERE profile_id=?", [(pid,) for pid in profile_ids])
                conn.executemany("DELETE FROM memomics_cluster_account_links WHERE profile_id=?", [(pid,) for pid in profile_ids])
                conn.executemany("DELETE FROM memomics_cluster_legacy_link_migrations WHERE profile_id=?", [(pid,) for pid in profile_ids])
                deleted = conn.execute("DELETE FROM memomics_cluster_accounts WHERE id=?", (aid,)).rowcount
                if not deleted:
                    raise CatalogError("catalog account not found", "account_not_found")
                conn.execute("COMMIT")
                return {"deleted_account_id": aid, "deleted_profile_ids": profile_ids}
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v4_delete_node_metadata(self, plan: dict[str, Any]) -> dict[str, Any]:
        nid = _node_id(plan.get("node_id"))
        profile_ids = [_profile_id(value) for value in plan.get("profile_ids") or []]
        replacement = plan.get("replacement_node_id")
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                node = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (nid,)).fetchone()
                if not node:
                    raise CatalogError("catalog node not found", "node_not_found")
                if is_usable_login_node(node):
                    other_usable_logins = int(conn.execute(
                        "SELECT COUNT(*) FROM memomics_cluster_nodes WHERE server_id=? AND id<>? AND "
                        + _V4_USABLE_LOGIN_SQL,
                        (str(node["server_id"]), nid),
                    ).fetchone()[0])
                    if not other_usable_logins:
                        if not replacement:
                            raise CatalogError("server must retain a login node", "login_replacement_required")
                        candidate = conn.execute("SELECT * FROM memomics_cluster_nodes WHERE id=?", (_node_id(replacement),)).fetchone()
                        if (
                            not candidate or str(candidate["server_id"]) != str(node["server_id"])
                            or not str(candidate["host"] or "").strip()
                            or candidate["port"] is None or not 1 <= int(candidate["port"]) <= 65535
                        ):
                            raise CatalogError("replacement node must belong to the same server", "login_replacement_invalid")
                        conn.execute(
                            "UPDATE memomics_cluster_nodes SET is_login=1,updated_at=? WHERE id=?",
                            (_now(), _node_id(replacement)),
                        )
                conn.executemany("DELETE FROM memomics_cluster_connections WHERE profile_id=?", [(pid,) for pid in profile_ids])
                conn.executemany("DELETE FROM memomics_cluster_account_links WHERE profile_id=?", [(pid,) for pid in profile_ids])
                conn.executemany("DELETE FROM memomics_cluster_legacy_link_migrations WHERE profile_id=?", [(pid,) for pid in profile_ids])
                conn.execute("DELETE FROM memomics_cluster_account_links WHERE node_id=?", (nid,))
                deleted = conn.execute("DELETE FROM memomics_cluster_nodes WHERE id=?", (nid,)).rowcount
                if not deleted:
                    raise CatalogError("catalog node not found", "node_not_found")
                conn.execute("COMMIT")
                return {"deleted_node_id": nid, "deleted_profile_ids": profile_ids, "promoted_node_id": replacement}
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v4_delete_server_metadata(self, plan: dict[str, Any]) -> dict[str, Any]:
        sid = _server_id(plan.get("server_id"))
        profile_ids = [_profile_id(value) for value in plan.get("profile_ids") or []]
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                if not self._v4_server_exists(conn, sid):
                    raise CatalogError("catalog server not found", "server_not_found")
                conn.executemany("DELETE FROM memomics_cluster_connections WHERE profile_id=?", [(pid,) for pid in profile_ids])
                conn.executemany("DELETE FROM memomics_cluster_legacy_link_migrations WHERE profile_id=?", [(pid,) for pid in profile_ids])
                node_ids = [str(row[0]) for row in conn.execute(
                    "SELECT id FROM memomics_cluster_nodes WHERE server_id=?", (sid,)
                ).fetchall()]
                for nid in node_ids:
                    conn.execute("DELETE FROM memomics_cluster_account_links WHERE node_id=?", (nid,))
                conn.execute("DELETE FROM memomics_cluster_accounts WHERE server_id=?", (sid,))
                conn.execute("DELETE FROM memomics_cluster_nodes WHERE server_id=?", (sid,))
                conn.execute("DELETE FROM memomics_cluster_servers WHERE id=?", (sid,))
                conn.execute("COMMIT")
                return {
                    "deleted_server_id": sid, "deleted_node_ids": node_ids,
                    "deleted_account_ids": list(plan.get("account_ids") or []), "deleted_profile_ids": profile_ids,
                }
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def v4_cleanup_deleted_profile(self, profile_id: Any) -> list[str]:
        """Clean catalog mappings after an old console deletes one profile.

        This compatibility hook cannot delete dependent remote profiles, so it
        only removes their mappings.  They remain visible as unassigned remote
        profiles rather than becoming a dangling gateway route.
        """
        pid = _profile_id(profile_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                self._begin(conn)
                row = conn.execute("SELECT server_id FROM memomics_cluster_connections WHERE profile_id=?", (pid,)).fetchone()
                deleted_ids: list[str] = []
                if row:
                    deleted_ids = self._v4_expand_gateway_dependents(conn, [pid], str(row["server_id"]))
                    conn.executemany("DELETE FROM memomics_cluster_connections WHERE profile_id=?", [(value,) for value in deleted_ids])
                conn.execute("DELETE FROM memomics_cluster_account_links WHERE profile_id=?", (pid,))
                conn.execute("DELETE FROM memomics_cluster_legacy_link_migrations WHERE profile_id=?", (pid,))
                conn.execute("COMMIT")
                return deleted_ids or [pid]
            except Exception:
                self._rollback(conn)
                raise
            finally:
                conn.close()

    def unlink_profile_anywhere(self, profile_id: Any) -> bool:
        """Override the V3 hook with V4 connection/gateway cleanup."""
        return bool(self.v4_cleanup_deleted_profile(profile_id))
