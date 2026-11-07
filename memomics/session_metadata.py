"""Small, application-owned metadata layer for MemOmics chat sessions.

The Hermes ``sessions`` table is deliberately left alone: its ``cwd`` field is
the durable results-directory pointer.  Projects and remote-server bindings
are therefore kept in two additive tables in the same ``state.db`` file.

This module has no WebUI dependency.  It is safe to use from tool worker
threads as well as FastAPI request handlers; every operation opens a short
lived SQLite connection and uses a bounded busy timeout.
"""

from __future__ import annotations

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
_PROJECT_ID = re.compile(r"^proj-[0-9a-f]{8,32}$")
MAX_NAME = 80
MAX_DESCRIPTION = 2_000


class MetadataError(ValueError):
    """Input or consistency failure suitable for an HTTP 4xx response."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_text(value: Any, *, field: str, maximum: int, required: bool = False) -> str:
    text = "" if value is None else str(value)
    if _CONTROL_CHARS.search(text):
        raise MetadataError(f"{field} cannot contain control characters")
    text = text.strip()
    if required and not text:
        raise MetadataError(f"{field} is required")
    if len(text) > maximum:
        raise MetadataError(f"{field} is too long (maximum {maximum} characters)")
    return text


def _clean_project_id(project_id: Any) -> str:
    value = str(project_id or "").strip()
    if not _PROJECT_ID.fullmatch(value):
        raise MetadataError("invalid project id")
    return value


def _clean_session_id(session_id: Any) -> str:
    value = str(session_id or "").strip()
    if not value or len(value) > 180 or _CONTROL_CHARS.search(value):
        raise MetadataError("invalid session id")
    return value


def _clean_server_id(server_id: Any) -> str:
    value = str(server_id or "").strip()
    if not value or len(value) > 80 or _CONTROL_CHARS.search(value):
        raise MetadataError("invalid server id")
    return value


class SessionMetadataStore:
    """Projects and per-chat metadata backed by an existing MemOmics state.db."""

    def __init__(self, db_path: str | os.PathLike[str]):
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
                    CREATE TABLE IF NOT EXISTS memomics_projects (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL COLLATE NOCASE,
                        description TEXT NOT NULL DEFAULT '',
                        workdir TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_memomics_projects_name "
                    "ON memomics_projects(name COLLATE NOCASE)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memomics_session_metadata (
                        session_id TEXT PRIMARY KEY,
                        project_id TEXT NULL REFERENCES memomics_projects(id) ON DELETE SET NULL,
                        cluster_server_id TEXT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memomics_session_metadata_project "
                    "ON memomics_session_metadata(project_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memomics_session_metadata_cluster_server "
                    "ON memomics_session_metadata(cluster_server_id)"
                )
            finally:
                conn.close()

    def _project_from_row(self, row: sqlite3.Row, *, count: int = 0) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"] or "",
            "workdir": row["workdir"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "session_count": int(count),
        }

    @staticmethod
    def _workdir(value: Any) -> str:
        text = _clean_text(value, field="workdir", maximum=1_000)
        if not text:
            return ""
        path = os.path.abspath(os.path.expanduser(text))
        if not os.path.isdir(path):
            raise MetadataError("workdir must be an existing directory")
        return os.path.normpath(path)

    def list_projects(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT p.*, COUNT(m.session_id) AS session_count
                FROM memomics_projects p
                LEFT JOIN memomics_session_metadata m ON m.project_id = p.id
                GROUP BY p.id
                ORDER BY p.updated_at DESC, p.name COLLATE NOCASE ASC
                """
            ).fetchall()
            return [self._project_from_row(row, count=row["session_count"]) for row in rows]
        finally:
            conn.close()

    def has_project(self, project_id: Any) -> bool:
        pid = _clean_project_id(project_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            return bool(conn.execute("SELECT 1 FROM memomics_projects WHERE id=?", (pid,)).fetchone())
        finally:
            conn.close()

    def create_project(self, name: Any, description: Any = "", workdir: Any = "") -> dict[str, Any]:
        clean_name = _clean_text(name, field="name", maximum=MAX_NAME, required=True)
        clean_description = _clean_text(description, field="description", maximum=MAX_DESCRIPTION)
        clean_workdir = self._workdir(workdir)
        project_id = "proj-" + uuid.uuid4().hex[:12]
        now = _now()
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO memomics_projects(id,name,description,workdir,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (project_id, clean_name, clean_description, clean_workdir, now, now),
                )
                row = conn.execute("SELECT * FROM memomics_projects WHERE id=?", (project_id,)).fetchone()
                conn.execute("COMMIT")
                return self._project_from_row(row)
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK")
                raise MetadataError("a project with this name already exists") from exc
            except Exception:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def update_project(self, project_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
        pid = _clean_project_id(project_id)
        allowed = {"name", "description", "workdir"}
        unknown = set(payload or {}) - allowed
        if unknown:
            raise MetadataError("unsupported project fields: " + ", ".join(sorted(unknown)))
        if not payload:
            raise MetadataError("no project fields supplied")
        values: dict[str, Any] = {}
        if "name" in payload:
            values["name"] = _clean_text(payload.get("name"), field="name", maximum=MAX_NAME, required=True)
        if "description" in payload:
            values["description"] = _clean_text(payload.get("description"), field="description", maximum=MAX_DESCRIPTION)
        if "workdir" in payload:
            values["workdir"] = self._workdir(payload.get("workdir"))
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                exists = conn.execute("SELECT 1 FROM memomics_projects WHERE id=?", (pid,)).fetchone()
                if not exists:
                    conn.execute("ROLLBACK")
                    raise MetadataError("project not found")
                fields = list(values)
                sql = "UPDATE memomics_projects SET " + ", ".join(f"{key}=?" for key in fields)
                sql += ", updated_at=? WHERE id=?"
                conn.execute(sql, tuple(values[key] for key in fields) + (_now(), pid))
                row = conn.execute("SELECT * FROM memomics_projects WHERE id=?", (pid,)).fetchone()
                count = conn.execute(
                    "SELECT COUNT(*) FROM memomics_session_metadata WHERE project_id=?", (pid,)
                ).fetchone()[0]
                conn.execute("COMMIT")
                return self._project_from_row(row, count=count)
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK")
                raise MetadataError("a project with this name already exists") from exc
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def delete_project(self, project_id: Any) -> int:
        """Remove a project container and leave its sessions unclassified."""
        pid = _clean_project_id(project_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                exists = conn.execute("SELECT 1 FROM memomics_projects WHERE id=?", (pid,)).fetchone()
                if not exists:
                    conn.execute("ROLLBACK")
                    raise MetadataError("project not found")
                count = conn.execute(
                    "SELECT COUNT(*) FROM memomics_session_metadata WHERE project_id=?", (pid,)
                ).fetchone()[0]
                conn.execute(
                    "UPDATE memomics_session_metadata SET project_id=NULL, updated_at=? WHERE project_id=?",
                    (_now(), pid),
                )
                conn.execute("DELETE FROM memomics_projects WHERE id=?", (pid,))
                conn.execute("COMMIT")
                return int(count)
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def _metadata(self, row: sqlite3.Row | None) -> dict[str, Any]:
        return {
            "project_id": (row["project_id"] if row else None),
            "cluster_server_id": (row["cluster_server_id"] if row else None),
        }

    def get_session_metadata(self, session_id: Any) -> dict[str, Any]:
        sid = _clean_session_id(session_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT project_id, cluster_server_id FROM memomics_session_metadata WHERE session_id=?", (sid,)
            ).fetchone()
            return self._metadata(row)
        finally:
            conn.close()

    def metadata_for_sessions(self, session_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = [_clean_session_id(sid) for sid in session_ids if str(sid or "").strip()]
        if not ids:
            return {}
        self.ensure_schema()
        placeholders = ",".join("?" for _ in ids)
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT session_id, project_id, cluster_server_id FROM memomics_session_metadata "
                f"WHERE session_id IN ({placeholders})",
                tuple(ids),
            ).fetchall()
            out = {sid: {"project_id": None, "cluster_server_id": None} for sid in ids}
            for row in rows:
                out[row["session_id"]] = self._metadata(row)
            return out
        finally:
            conn.close()

    def _upsert(self, conn: sqlite3.Connection, sid: str, *, project_id: Any = ...,
                cluster_server_id: Any = ...) -> None:
        old = conn.execute(
            "SELECT project_id, cluster_server_id FROM memomics_session_metadata WHERE session_id=?", (sid,)
        ).fetchone()
        current_project = old["project_id"] if old else None
        current_server = old["cluster_server_id"] if old else None
        new_project = current_project if project_id is ... else project_id
        new_server = current_server if cluster_server_id is ... else cluster_server_id
        conn.execute(
            "INSERT INTO memomics_session_metadata(session_id,project_id,cluster_server_id,updated_at) "
            "VALUES(?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET "
            "project_id=excluded.project_id,cluster_server_id=excluded.cluster_server_id,updated_at=excluded.updated_at",
            (sid, new_project, new_server, _now()),
        )

    def set_session_project(self, session_id: Any, project_id: Any | None) -> dict[str, Any]:
        sid = _clean_session_id(session_id)
        pid = None if project_id in (None, "") else _clean_project_id(project_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                if pid and not conn.execute("SELECT 1 FROM memomics_projects WHERE id=?", (pid,)).fetchone():
                    conn.execute("ROLLBACK")
                    raise MetadataError("project not found")
                self._upsert(conn, sid, project_id=pid)
                conn.execute("COMMIT")
                return self.get_session_metadata(sid)
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def set_session_cluster_server(self, session_id: Any, server_id: Any | None) -> dict[str, Any]:
        sid = _clean_session_id(session_id)
        value = None if server_id in (None, "") else _clean_server_id(server_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._upsert(conn, sid, cluster_server_id=value)
                conn.execute("COMMIT")
                return self.get_session_metadata(sid)
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def sessions_bound_to_server(self, server_id: Any) -> list[str]:
        value = _clean_server_id(server_id)
        self.ensure_schema()
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT session_id FROM memomics_session_metadata WHERE cluster_server_id=? ORDER BY session_id",
                (value,),
            ).fetchall()
            return [str(row[0]) for row in rows]
        finally:
            conn.close()

    def delete_session_metadata(self, session_id: Any) -> None:
        """Remove metadata when the owning chat session is permanently deleted."""
        sid = _clean_session_id(session_id)
        self.ensure_schema()
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM memomics_session_metadata WHERE session_id=?", (sid,))
            finally:
                conn.close()
