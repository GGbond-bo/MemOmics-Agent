"""Additive API for the remote ``server -> node -> account`` catalog.

The adapter supplied by ``webui.server`` remains the only bridge to
``remote.nodes``.  That protects the legacy execution/binding contract while
this router stores only non-secret grouping data in SQLite.
"""

from __future__ import annotations

import copy
from contextlib import nullcontext
from functools import partial
import hashlib
from pathlib import Path
from typing import Any, Callable

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from memomics.cluster_catalog import CatalogError, ClusterCatalogStore, _scheduler, is_usable_login_node
from memomics.cluster_credentials import CredentialError, CredentialManagerStore, CredentialRecord, validate_password


_ACCOUNT_RESPONSE_FIELDS = {
    "id", "profile_id", "name", "user", "host", "port", "workdir", "job_dir", "local_root",
    "remote_root", "timeout", "proxy_jump", "has_extra_ssh_options", "scheduler",
    "has_key", "configured", "legacy", "is_running", "status",
    "endpoint_mismatch",
}
_NODE_CONNECTION_FIELDS = {"host", "port", "scheduler", "partition", "queue"}
_SAFE_CATALOG_ERROR_CODES = {
    "catalog_invalid", "server_not_found", "node_not_found", "profile_not_found", "profile_not_linked",
    "server_has_nodes", "node_has_accounts", "node_has_accounts_connection_locked",
    "profile_already_linked", "profile_node_mismatch", "server_name_conflict", "node_name_conflict",
    "binding_unavailable", "activity_unavailable", "node_endpoint_incomplete", "catalog_link_failed",
    "profile_recovery_required", "profile_delete_failed", "profile_transaction_unavailable",
    "profile_update_failed", "account_fields_invalid",
    # V4 staged server/node/account/connection contract.
    "workflow_changed", "account_not_found", "connection_not_found", "route_invalid",
    "connection_server_mismatch", "gateway_not_found", "gateway_server_mismatch", "gateway_not_login",
    "route_cycle", "connection_pair_exists", "profile_already_connected", "connection_invalid",
    "match_unavailable", "test_unavailable", "profile_persist_failed", "connection_probe_failed",
    "catalog_changed_retry",
    # V5 password-account errors are deliberately fixed strings.  A browser
    # must never receive a Credential Manager exception (which can otherwise
    # carry a target name or implementation detail), much less a password.
    "credential_password_required", "credential_password_invalid", "credential_password_too_long",
    "credential_store_unavailable", "credential_update_failed", "credential_missing_reconfigure",
    "credential_metadata_recovery_required", "credential_rollback_failed",
    "gateway_login_connection_required", "gateway_selection_required",
    "profile_auth_provenance_invalid",
    "server_requires_login_setup", "login_replacement_required", "login_replacement_invalid",
    "last_login_node", "login_node_has_gateway_dependents", "node_has_connections_connection_locked",
    "account_has_connections_user_locked", "legacy_migration_failed",
}
_ACCOUNT_WRITE_FIELDS = {
    "name", "user", "key_path", "workdir", "job_dir", "local_root", "remote_root", "timeout",
    "proxy_jump", "extra_ssh_options",
}

# This object is intentionally identity-only and exists solely for the retained
# V2/V4 offline regression fixtures.  ``None``, strings, truthy values, or a
# partial provider must never reopen the legacy write API in a real server.
LEGACY_V4_TEST_COMPATIBILITY = object()


class _UnavailableV5CredentialProvider:
    """Fail closed when a default Windows store cannot be constructed."""

    @staticmethod
    def _unavailable(*_args: Any, **_kwargs: Any):
        raise CredentialError("credential_store_unavailable")

    get = _unavailable
    put = _unavailable
    delete = _unavailable
    restore = _unavailable
    state = _unavailable
    target_for = _unavailable


def _has_v5_credential_provider_contract(value: Any) -> bool:
    """Validate method presence without probing/reading a credential target."""
    try:
        return all(callable(getattr(value, name, None)) for name in (
            "get", "put", "delete", "restore", "state", "target_for",
        ))
    except Exception:
        return False


def _status_for(error: CatalogError) -> int:
    if error.code in {
        "server_not_found", "node_not_found", "profile_not_found", "profile_not_linked",
        "account_not_found", "connection_not_found", "gateway_not_found",
    }:
        return 404
    if error.code in {
        "server_has_nodes", "node_has_accounts", "node_has_accounts_connection_locked",
        "profile_already_linked", "profile_node_mismatch", "server_name_conflict", "node_name_conflict",
        "workflow_changed", "connection_server_mismatch", "gateway_server_mismatch", "gateway_not_login",
        "route_cycle", "connection_pair_exists", "profile_already_connected", "server_requires_login_setup",
        "login_replacement_required", "login_replacement_invalid", "last_login_node",
        "login_node_has_gateway_dependents", "node_has_connections_connection_locked",
        "account_has_connections_user_locked",
        "catalog_changed_retry",
        "gateway_login_connection_required", "gateway_selection_required",
    }:
        return 409
    if error.code == "profile_auth_provenance_invalid":
        return 500
    return 400


def _error(error: Exception, *, status: int | None = None, **extra: Any) -> JSONResponse:
    if bool(getattr(error, "catalog_recovery_required", False)):
        code = "profile_recovery_required"
        code_status = 500
        message = "catalog recovery is required before retrying this operation"
        backup_id = str(getattr(error, "backup_id", "") or "").strip()
        if backup_id:
            extra["backup_id"] = backup_id
    elif isinstance(error, CatalogError):
        code = error.code
        code_status = _status_for(error)
        # Only catalog-owned, enumerated messages are fit for a browser.  An
        # adapter must not be able to surface an arbitrary exception merely by
        # wrapping it in CatalogError.
        message = str(error) if code in _SAFE_CATALOG_ERROR_CODES else "catalog request failed"
    else:
        code = "catalog_error"
        code_status = 500
        # Adapter/configuration errors can include SSH arguments, a key path,
        # or other private details.  They are never part of an HTTP response.
        message = "catalog operation failed"
    body: dict[str, Any] = {"ok": False, "error": message, "code": code}
    body.update(extra)
    return JSONResponse(body, status_code=status if status is not None else code_status)


def _payload_error(message: str) -> CatalogError:
    return CatalogError(message, "catalog_invalid")


async def _body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise _payload_error("request body must be valid JSON") from exc
    if not isinstance(body, dict):
        raise _payload_error("request body must be an object")
    return body


def _adapter_lock(adapter: Any):
    lock = getattr(adapter, "lock", None)
    if callable(lock) and not hasattr(lock, "__enter__"):
        lock = lock()
    return lock if lock is not None else nullcontext()


async def _run_catalog_worker(operation: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Run a potentially slow local SSH operation without holding router state.

    The frozen input has already been validated while the short catalog lock
    was held.  This helper must never be called from that locked section:
    verification can take tens of seconds and the worker deliberately does not
    own the adapter/catalog lock.  Its result is always revalidated under a
    second short lock before metadata or YAML can be committed.
    """
    return await anyio.to_thread.run_sync(
        partial(operation, *args, **kwargs), abandon_on_cancel=False,
    )


def _profile_transaction(adapter: Any):
    transaction = getattr(adapter, "profile_transaction", None)
    if not callable(transaction):
        raise CatalogError("catalog profile transaction is unavailable", "profile_transaction_unavailable")
    return transaction()


def _clean_text(value: Any, field: str, maximum: int, *, required: bool = False) -> str:
    text = "" if value is None else str(value)
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise CatalogError(f"{field} cannot contain control characters", "account_fields_invalid")
    text = text.strip()
    if required and not text:
        raise CatalogError(f"{field} is required", "account_fields_invalid")
    if len(text) > maximum:
        raise CatalogError(f"{field} is too long", "account_fields_invalid")
    return text


def _account_payload(body: Any, *, creating: bool) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise CatalogError("account must be an object", "account_fields_invalid")
    unknown = set(body) - _ACCOUNT_WRITE_FIELDS
    if unknown:
        raise CatalogError("unsupported account fields: " + ", ".join(sorted(unknown)), "account_fields_invalid")
    if creating and ("name" not in body or "user" not in body):
        raise CatalogError("account name and user are required", "account_fields_invalid")
    out: dict[str, Any] = {}
    for field, maximum, required in (
        ("name", 120, creating), ("user", 253, creating), ("key_path", 2048, False),
        ("workdir", 2048, False), ("job_dir", 2048, False), ("local_root", 2048, False),
        ("remote_root", 2048, False), ("proxy_jump", 1024, False),
    ):
        if field in body:
            out[field] = _clean_text(body.get(field), field, maximum, required=required)
    if "timeout" in body:
        raw = body.get("timeout")
        if raw in (None, ""):
            # The underlying remote configuration stores only a concrete
            # timeout.  Clearing the optional form field restores its normal
            # default rather than passing a malformed empty value downstream.
            out["timeout"] = 300
        else:
            try:
                timeout = int(str(raw).strip())
            except Exception as exc:
                raise CatalogError("timeout must be an integer", "account_fields_invalid") from exc
            # Match remote_cluster/server validation exactly so a form error is
            # reported before any profile transaction begins.
            if not 1 <= timeout <= 7_200:
                raise CatalogError("timeout must be between 1 and 7200", "account_fields_invalid")
            out["timeout"] = timeout
    if "extra_ssh_options" in body:
        options = body.get("extra_ssh_options")
        if not isinstance(options, list) or len(options) > 64:
            raise CatalogError("extra_ssh_options must be a list of at most 64 values", "account_fields_invalid")
        out["extra_ssh_options"] = [
            _clean_text(item, "extra_ssh_options", 512, required=True) for item in options
        ]
    return out


def _node_payload(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise CatalogError("node must be an object", "catalog_invalid")
    allowed = {"name", "host", "port", "scheduler", "partition", "queue", "role", "note"}
    unknown = set(body) - allowed
    if unknown:
        raise CatalogError("unsupported node fields: " + ", ".join(sorted(unknown)), "catalog_invalid")
    if not str(body.get("name") or "").strip() or not str(body.get("host") or "").strip():
        raise CatalogError("node name and host are required", "catalog_invalid")
    payload = dict(body)
    payload["port"] = _request_port(payload.get("port"))
    payload["scheduler"] = str(payload.get("scheduler") or "auto")
    return payload


def _profile_payload(node: dict[str, Any], account: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "name": account["name"], "user": account["user"], "host": node["host"],
        "port": node.get("port") or 22, "scheduler": node.get("scheduler") or "auto",
        "partition": node.get("partition") or "", "queue": node.get("queue") or "",
    }
    for field in _ACCOUNT_WRITE_FIELDS - {"name", "user"}:
        if field in account and account[field] is not None:
            payload[field] = account[field]
    return payload


def _existing_profile_ids(adapter: Any, profile_ids: list[str]) -> list[str]:
    existing: list[str] = []
    for profile_id in profile_ids:
        if adapter.get_profile(profile_id):
            existing.append(profile_id)
    return existing


def _profile_id(profile: dict[str, Any]) -> str:
    return str(profile.get("profile_id") or profile.get("id") or "").strip()


def _port(value: Any) -> int:
    try:
        return int(value or 22)
    except Exception:
        return 22


def _timeout(value: Any) -> int:
    try:
        timeout = int(value)
    except Exception:
        return 300
    return timeout if 1 <= timeout <= 7_200 else 300


def _request_port(value: Any) -> int:
    """Parse request input strictly; response parsing may still default to 22."""
    if value in (None, ""):
        return 22
    if isinstance(value, bool):
        raise CatalogError("port must be an integer", "catalog_invalid")
    raw = str(value).strip()
    if not raw.isdigit():
        raise CatalogError("port must be an integer", "catalog_invalid")
    port = int(raw)
    if not 1 <= port <= 65535:
        raise CatalogError("port must be between 1 and 65535", "catalog_invalid")
    return port


def _same_endpoint(node: dict[str, Any], profile: dict[str, Any]) -> bool:
    node_host = str(node.get("host") or "").strip().lower()
    profile_host = str(profile.get("host") or "").strip().lower()
    return bool(node_host and profile_host and node_host == profile_host and _port(node.get("port")) == _port(profile.get("port")))


def _node_status(node: dict[str, Any]) -> str:
    if not str(node.get("host") or "").strip():
        return "draft"
    return "configured" if int(node.get("account_count") or 0) else "ready"


def _account_summary(adapter: Any, profile: dict[str, Any], *, endpoint_mismatch: bool = False) -> dict[str, Any]:
    pid = _profile_id(profile)
    if not pid:
        raise CatalogError("profile has no stable id", "profile_not_found")
    try:
        running = bool(adapter.is_profile_running(pid))
    except Exception:
        # Catalog rendering must remain useful when a historical-job lookup is
        # temporarily unavailable.  Activity is advisory only and no longer
        # controls profile access or deletion.
        running = False
    result = {
        "id": pid,
        "profile_id": pid,
        "name": str(profile.get("name") or pid),
        "user": str(profile.get("user") or ""),
        "host": str(profile.get("host") or ""),
        "port": _port(profile.get("port")),
        "workdir": str(profile.get("workdir") or ""),
        "job_dir": str(profile.get("job_dir") or ""),
        "local_root": str(profile.get("local_root") or ""),
        "remote_root": str(profile.get("remote_root") or ""),
        "timeout": _timeout(profile.get("timeout")),
        "proxy_jump": str(profile.get("proxy_jump") or ""),
        # The edit form only needs to tell the user that options are present;
        # raw SSH flags can disclose an internal bastion/address and never
        # cross this API boundary.
        "has_extra_ssh_options": bool(
            profile.get("has_extra_ssh_options") or profile.get("extra_ssh_options")
        ),
        "scheduler": str(profile.get("scheduler") or "auto"),
        "has_key": bool(profile.get("has_key")),
        "configured": bool(profile.get("configured")),
        "legacy": bool(profile.get("legacy")),
        "is_running": running,
        "status": "untested" if str(profile.get("host") or "").strip() and str(profile.get("user") or "").strip() else "incomplete",
        "endpoint_mismatch": bool(endpoint_mismatch),
    }
    return {key: result[key] for key in _ACCOUNT_RESPONSE_FIELDS if key in result}


def _profiles(adapter: Any) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    result = adapter.list_profiles()
    if not isinstance(result, tuple) or len(result) != 3:
        raise RuntimeError("cluster catalog adapter returned an invalid profile listing")
    cfg, rows, legacy = result
    if not isinstance(rows, list):
        raise RuntimeError("cluster catalog adapter returned invalid profile rows")
    return (cfg if isinstance(cfg, dict) else {}, [dict(item) for item in rows if isinstance(item, dict)], bool(legacy))


def _delete_new_profile(adapter: Any, profile_id: str) -> bool:
    """Delete only a profile created by this request and verify the outcome.

    A false ``ok`` is not a successful compensating action.  The caller must
    then make the saved, unassigned profile explicit to the user instead of
    pretending that it vanished.
    """
    try:
        result = adapter.delete_profile(profile_id)
    except Exception:
        return False
    return result is True or (isinstance(result, dict) and result.get("ok") is True)


def _unassigned_recovery(profile_id: str) -> JSONResponse:
    return _error(
        CatalogError("account profile was saved but could not be linked or removed", "catalog_link_failed"),
        status=500,
        profile_id=profile_id,
        recovery="unassigned",
    )


def _catalog(adapter: Any, store: ClusterCatalogStore) -> dict[str, Any]:
    _cfg, profiles, _legacy = _profiles(adapter)
    profile_by_id = {_profile_id(profile): profile for profile in profiles if _profile_id(profile)}
    links = store.list_links()
    links_by_node: dict[str, list[str]] = {}
    linked_ids: set[str] = set()
    orphan_links: list[dict[str, Any]] = []
    for link in links:
        pid = str(link["profile_id"])
        nid = str(link["node_id"])
        if pid not in profile_by_id:
            orphan_links.append({
                "profile_id": pid,
                "node_id": nid,
                "server_id": str(link["server_id"]),
                "node_name": str(link["node_name"]),
                "created_at": str(link["created_at"]),
            })
            continue
        links_by_node.setdefault(nid, []).append(pid)
        linked_ids.add(pid)

    nodes_by_server: dict[str, list[dict[str, Any]]] = {}
    for node in store.list_nodes():
        accounts = []
        for pid in links_by_node.get(node["id"], []):
            profile = profile_by_id[pid]
            accounts.append(_account_summary(adapter, profile, endpoint_mismatch=not _same_endpoint(node, profile)))
        node_view = {
            **{key: node[key] for key in (
                "id", "server_id", "name", "host", "port", "scheduler", "partition", "queue", "role", "note",
                "created_at", "updated_at",
            )},
            "status": _node_status(node),
            "connection_fields_locked": bool(node.get("account_count")),
            "accounts": accounts,
        }
        nodes_by_server.setdefault(node["server_id"], []).append(node_view)

    servers = []
    for server in store.list_servers():
        nodes = nodes_by_server.get(server["id"], [])
        servers.append({
            "id": server["id"],
            "name": server["name"],
            "description": server["description"],
            "created_at": server["created_at"],
            "updated_at": server["updated_at"],
            "node_count": len(nodes),
            "nodes": nodes,
        })
    unassigned = [_account_summary(adapter, profile) for profile in profiles if _profile_id(profile) not in linked_ids]
    return {
        "schema_version": 1,
        "binding_target": "account_profile",
        "servers": servers,
        "unassigned_profiles": unassigned,
        "orphan_links": orphan_links,
    }


def _build_v3_retired_router(adapter: Any, db_path_provider: Callable[[], str]) -> APIRouter:
    """Retained V3 implementation for source history; V4 build_router is below."""

    router = APIRouter()

    def store() -> ClusterCatalogStore:
        return ClusterCatalogStore(db_path_provider())

    @router.get("/api/cluster/catalog")
    async def get_catalog():
        try:
            with _adapter_lock(adapter):
                return _catalog(adapter, store())
        except Exception as exc:
            return _error(exc)

    def delete_profiles(profile_ids: list[str]) -> list[str]:
        unique = list(dict.fromkeys(str(value) for value in profile_ids if str(value)))
        if not unique:
            return []
        operation = getattr(adapter, "delete_profiles", None)
        if not callable(operation):
            raise CatalogError("catalog profile deletion is unavailable", "profile_delete_failed")
        result = operation(unique)
        if result is False or (isinstance(result, dict) and result.get("ok") is False):
            raise CatalogError("profile deletion failed", "profile_delete_failed")
        return unique

    def set_remote_enabled(value: bool) -> bool:
        operation = getattr(adapter, "set_remote_enabled", None)
        if not callable(operation):
            raise CatalogError("remote enable control is unavailable", "profile_transaction_unavailable")
        operation(value)
        return value

    @router.post("/api/cluster/catalog/servers")
    async def create_server(request: Request):
        """Create a server with its first complete node and login account.

        Empty grouping rows were the source of a misleading configuration UI.
        V3 creates the remote profile and all catalog rows as one reversible
        local operation: YAML/profile rollback happens if SQLite rejects the
        bundle, while the SQLite transaction rejects partial hierarchy rows.
        """
        try:
            body = await _body(request)
            allowed = {"name", "description", "node", "account"}
            unknown = set(body) - allowed
            if unknown:
                raise _payload_error("unsupported server fields: " + ", ".join(sorted(unknown)))
            node_payload = _node_payload(body.get("node"))
            account_payload = _account_payload(body.get("account"), creating=True)
            flat_profile = _profile_payload(node_payload, account_payload)
            with _adapter_lock(adapter):
                with _profile_transaction(adapter):
                    created = adapter.create_profile(flat_profile)
                    if not isinstance(created, dict) or not _profile_id(created):
                        raise CatalogError("new account profile was not returned by the adapter", "catalog_link_failed")
                    # A newly completed connection must be usable immediately.
                    # Only this first-server flow changes the global switch;
                    # later node/account edits and destructive operations leave
                    # it untouched.
                    set_remote_enabled(True)
                    catalog_store = store()
                    server, node = catalog_store.create_server_bundle(
                        body.get("name"), body.get("description", ""), node_payload, _profile_id(created),
                    )
                    account = _account_summary(adapter, created)
            return JSONResponse(
                {"ok": True, "server": server, "node": node, "account": account,
                 "remote_enabled": True},
                status_code=201,
            )
        except Exception as exc:
            return _error(exc)

    @router.patch("/api/cluster/catalog/servers/{server_id}")
    async def update_server(server_id: str, request: Request):
        try:
            body = await _body(request)
            with _adapter_lock(adapter):
                server = store().update_server(server_id, body)
            return {"ok": True, "server": server}
        except Exception as exc:
            return _error(exc)

    @router.delete("/api/cluster/catalog/servers/{server_id}")
    async def delete_server(server_id: str):
        try:
            _v5_require_available_credential_store(credential_provider)
            with _adapter_lock(adapter):
                catalog_store = store()
                plan = catalog_store.server_delete_plan(server_id)
                with _profile_transaction(adapter):
                    delete_profiles(_existing_profile_ids(adapter, list(plan["profile_ids"])))
                    result = catalog_store.delete_server_cascade(server_id)
            return {"ok": True, "deleted": {"server_id": server_id}, "deleted_profile_ids": result["deleted_profile_ids"],
                    "cascade": {"nodes": len(result["deleted_node_ids"]), "accounts": len(result["deleted_profile_ids"])}}
        except Exception as exc:
            return _error(exc)

    @router.post("/api/cluster/catalog/servers/{server_id}/nodes")
    async def create_node(server_id: str, request: Request):
        try:
            body = await _body(request)
            allowed = {"node", "account"}
            unknown = set(body) - allowed
            if unknown:
                raise _payload_error("V3 node creation requires node and account objects")
            node_payload = _node_payload(body.get("node"))
            account_payload = _account_payload(body.get("account"), creating=True)
            flat_profile = _profile_payload(node_payload, account_payload)
            with _adapter_lock(adapter):
                with _profile_transaction(adapter):
                    created = adapter.create_profile(flat_profile)
                    if not isinstance(created, dict) or not _profile_id(created):
                        raise CatalogError("new account profile was not returned by the adapter", "catalog_link_failed")
                    node = store().create_node_bundle(server_id, node_payload, _profile_id(created))
                    account = _account_summary(adapter, created)
            return JSONResponse({"ok": True, "node": node, "account": account}, status_code=201)
        except Exception as exc:
            return _error(exc)

    @router.patch("/api/cluster/catalog/nodes/{node_id}")
    async def update_node(node_id: str, request: Request):
        try:
            body = await _body(request)
            with _adapter_lock(adapter):
                node = store().update_node(node_id, body)
            return {"ok": True, "node": node}
        except Exception as exc:
            return _error(exc)

    @router.delete("/api/cluster/catalog/nodes/{node_id}")
    async def delete_node(node_id: str):
        try:
            with _adapter_lock(adapter):
                catalog_store = store()
                plan = catalog_store.node_delete_plan(node_id)
                with _profile_transaction(adapter):
                    delete_profiles(_existing_profile_ids(adapter, list(plan["profile_ids"])))
                    result = catalog_store.delete_node_cascade(node_id)
            return {"ok": True, "deleted": {"node_id": node_id}, "deleted_profile_ids": result["deleted_profile_ids"],
                    "cascade": {"accounts": len(result["deleted_profile_ids"])}}
        except Exception as exc:
            return _error(exc)

    @router.post("/api/cluster/catalog/nodes/{node_id}/adopt")
    async def adopt_account(node_id: str, request: Request):
        try:
            body = await _body(request)
            profile_id = body.get("profile_id")
            if not profile_id:
                raise _payload_error("profile_id is required")
            with _adapter_lock(adapter):
                catalog_store = store()
                node = catalog_store.get_node(node_id)
                profile = adapter.get_profile(str(profile_id))
                if not profile:
                    raise CatalogError("account profile not found", "profile_not_found")
                if not _same_endpoint(node, dict(profile)):
                    raise CatalogError(
                        "account profile endpoint differs from this node; create a matching node from the profile instead",
                        "profile_node_mismatch",
                    )
                # Compute the response before mutating catalog linkage.  A
                # failed binding/activity lookup must not leave a link that a
                # user cannot safely retry or detach from the response.
                account = _account_summary(adapter, dict(profile))
                catalog_store.link_profile(node_id, profile_id)
            return {"ok": True, "node_id": node_id, "account": account}
        except Exception as exc:
            return _error(exc)

    @router.post("/api/cluster/catalog/nodes/{node_id}/accounts")
    async def create_account(node_id: str, request: Request):
        try:
            body = await _body(request)
            account_payload = _account_payload(body, creating=True)
            with _adapter_lock(adapter):
                with _profile_transaction(adapter):
                    catalog_store = store()
                    node = catalog_store.get_node(node_id)
                    if not str(node.get("host") or "").strip():
                        raise CatalogError("a node needs a host before an account can be added", "node_endpoint_incomplete")
                    created = adapter.create_profile(_profile_payload(node, account_payload))
                    if not isinstance(created, dict) or not _profile_id(created):
                        raise CatalogError("new account profile was not returned by the adapter", "catalog_link_failed")
                    account = _account_summary(adapter, created)
                    catalog_store.link_profile(node_id, _profile_id(created))
            return JSONResponse({"ok": True, "node_id": node_id, "account": account}, status_code=201)
        except Exception as exc:
            return _error(exc)

    @router.patch("/api/cluster/catalog/nodes/{node_id}/accounts/{profile_id}")
    async def update_account(node_id: str, profile_id: str, request: Request):
        try:
            payload = _account_payload(await _body(request), creating=False)
            if not payload:
                raise _payload_error("no account fields supplied")
            with _adapter_lock(adapter):
                catalog_store = store()
                catalog_store.account_delete_plan(node_id, profile_id)
                current = adapter.get_profile(profile_id)
                if not current:
                    raise CatalogError("account profile not found", "profile_not_found")
                operation = getattr(adapter, "update_profile", None)
                if not callable(operation):
                    raise CatalogError("catalog profile update is unavailable", "profile_update_failed")
                with _profile_transaction(adapter):
                    updated = operation(profile_id, payload)
                    if not isinstance(updated, dict):
                        raise CatalogError("account profile update failed", "profile_update_failed")
                    account = _account_summary(adapter, updated)
            return {"ok": True, "node_id": node_id, "account": account}
        except Exception as exc:
            return _error(exc)

    @router.delete("/api/cluster/catalog/nodes/{node_id}/accounts/{profile_id}")
    async def delete_account(node_id: str, profile_id: str):
        try:
            with _adapter_lock(adapter):
                catalog_store = store()
                plan = catalog_store.account_delete_plan(node_id, profile_id)
                with _profile_transaction(adapter):
                    delete_profiles(_existing_profile_ids(adapter, list(plan["profile_ids"])))
                    result = catalog_store.delete_account_cascade(node_id, profile_id)
            return {"ok": True, "deleted": {"node_id": node_id, "profile_id": profile_id},
                    "deleted_profile_ids": result["deleted_profile_ids"]}
        except Exception as exc:
            return _error(exc)

    @router.delete("/api/cluster/catalog/profiles/{profile_id}")
    async def delete_unassigned_profile(profile_id: str):
        """Remove a legacy/unassigned local profile and any stale catalog link."""
        try:
            with _adapter_lock(adapter):
                catalog_store = store()
                plan = catalog_store.profile_delete_plan(profile_id)
                if plan["node_ids"]:
                    raise CatalogError(
                        "account profile is assigned to a node; delete it from that node instead",
                        "profile_already_linked",
                    )
                with _profile_transaction(adapter):
                    delete_profiles(_existing_profile_ids(adapter, list(plan["profile_ids"])))
                    result = catalog_store.delete_profile_anywhere(profile_id)
            return {"ok": True, "deleted": {"profile_id": profile_id},
                    "deleted_profile_ids": result["deleted_profile_ids"]}
        except Exception as exc:
            return _error(exc)

    return router


# ---------------------------------------------------------------------------
# V5 password-account catalog API.
#
# V4 was deliberately kept above as a narrowly-scoped compatibility router for
# callers that do not supply a credential provider (notably the old offline
# regression fixtures).  Production supplies a Windows Credential Manager
# provider and always reaches this V5 router.  Keeping the switch at router
# construction time, rather than branching individual mutations, makes it
# impossible for one password-account operation to silently fall back to a
# key-based V4 operation.

_V5_ACCOUNT_FIELDS = {"name", "user", "note", "password"}
_V5_CONNECTION_FIELDS = {
    "name", "display_name", "workdir", "job_dir", "local_root", "remote_root",
    "timeout", "scheduler", "partition", "queue", "note", "clear_fields",
}
_V5_CREDENTIAL_CODES = {
    "credential_password_required", "credential_password_invalid", "credential_password_too_long",
    "credential_store_unavailable", "credential_update_failed", "credential_missing_reconfigure",
    "credential_metadata_recovery_required", "credential_rollback_failed",
}


def _v5_credential_error(error: Exception | None = None, *, fallback: str = "credential_store_unavailable") -> CatalogError:
    """Translate credential-store failures without preserving native details."""
    code = getattr(error, "code", None)
    if code not in _V5_CREDENTIAL_CODES:
        code = fallback
    messages = {
        "credential_password_required": "a login password is required",
        "credential_password_invalid": "the login password contains unsupported characters",
        "credential_password_too_long": "the login password is too long",
        "credential_store_unavailable": "the local encrypted credential store is unavailable",
        "credential_update_failed": "the local login password could not be updated",
        "credential_missing_reconfigure": "the saved login password is missing; edit the user and set it again",
        "credential_metadata_recovery_required": "credential metadata recovery is required before retrying",
        "credential_rollback_failed": "credential rollback could not be verified; re-open the catalog before retrying",
    }
    return CatalogError(messages[code], str(code))


def _v5_require_available_credential_store(credential_provider: Any) -> None:
    """Reject a router's intentional fail-closed provider before metadata work.

    ``build_router`` replaces a missing or partial production provider with
    ``_UnavailableV5CredentialProvider``.  That replacement must fail at the
    request boundary: creating catalog metadata first would turn a simple
    local-store outage into an avoidable metadata-recovery workflow.  Real
    providers retain their normal compensated-write handling below, since a
    native ``put`` can still fail after persistence.
    """
    if isinstance(credential_provider, _UnavailableV5CredentialProvider):
        raise _v5_credential_error()


def _v5_credential_call(operation: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Call a credential-provider method without ever reflecting its exception."""
    try:
        return operation(*args, **kwargs)
    except CredentialError as exc:
        raise _v5_credential_error(exc) from None
    except CatalogError:
        raise
    except Exception:
        raise _v5_credential_error() from None


def _v5_credential_state(credential_provider: Any, account_id: str) -> str:
    state = _v5_credential_call(credential_provider.state, str(account_id))
    if state not in {"configured", "missing"}:
        raise _v5_credential_error()
    return str(state)


def _v5_credential_record(credential_provider: Any, account_id: str) -> CredentialRecord:
    record = _v5_credential_call(credential_provider.get, str(account_id))
    if record is None:
        raise _v5_credential_error(fallback="credential_missing_reconfigure")
    revision = getattr(record, "revision", None)
    if isinstance(revision, bool) or not isinstance(revision, int) or not 1 <= revision <= 0x7FFFFFFFFFFFFFFF:
        raise _v5_credential_error()
    # Do not inspect or serialize record.password here.  The provider owns the
    # secret; this router needs only a monotonically increasing public revision.
    return record


def _v5_credential_revisions(credential_provider: Any, account_ids: list[str]) -> dict[str, int]:
    revisions: dict[str, int] = {}
    for account_id in dict.fromkeys(str(value) for value in account_ids if str(value)):
        record = _v5_credential_record(credential_provider, account_id)
        revisions[account_id] = int(record.revision)
    return revisions


def _v5_current_revisions_match(credential_provider: Any, expected: dict[str, Any]) -> bool:
    """Re-read exact target/gateway revisions before committing a SSH receipt."""
    try:
        current = _v5_credential_revisions(credential_provider, list(expected))
    except CatalogError:
        raise
    return current == {str(key): value for key, value in expected.items()}


def _v5_account_payload(value: Any, *, creating: bool) -> tuple[dict[str, Any], str | None]:
    """Split public account metadata from the one local-only password field."""
    if not isinstance(value, dict):
        raise CatalogError("account must be an object", "account_fields_invalid")
    if set(value) - _V5_ACCOUNT_FIELDS:
        raise CatalogError("unsupported account fields", "account_fields_invalid")
    if creating and ("name" not in value or "user" not in value):
        raise CatalogError("account name and user are required", "account_fields_invalid")
    metadata = {key: value[key] for key in ("name", "user", "note") if key in value}
    supplied = "password" in value
    password = value.get("password") if supplied else None
    if creating:
        if not supplied:
            raise _v5_credential_error(fallback="credential_password_required")
        try:
            # Validation deliberately does not trim: spaces can be valid SSH
            # passwords.  It also runs before SQLite changes are made.
            password = validate_password(password)
        except CredentialError as exc:
            raise _v5_credential_error(exc) from None
    elif supplied:
        if not isinstance(password, str):
            raise _v5_credential_error(fallback="credential_password_invalid")
        # Empty means "leave the existing local password unchanged" in the
        # edit dialog.  A non-empty space-only password is valid and retained.
        if password == "":
            password = None
        else:
            try:
                password = validate_password(password)
            except CredentialError as exc:
                raise _v5_credential_error(exc) from None
    if not creating and not metadata and password is None:
        raise CatalogError("no account fields supplied", "account_fields_invalid")
    return metadata, password


def _v5_connection_payload(value: Any) -> dict[str, Any]:
    """V5 connection preferences; identity/auth/routing never come from HTTP."""
    if not isinstance(value, dict):
        raise CatalogError("connection must be an object", "connection_invalid")
    if set(value) - _V5_CONNECTION_FIELDS:
        raise CatalogError("unsupported connection fields", "connection_invalid")
    result: dict[str, Any] = {}
    text_fields = ("name", "display_name", "workdir", "job_dir", "local_root", "remote_root", "partition", "queue", "note")
    for field in text_fields:
        if field not in value:
            continue
        raw = value.get(field)
        if raw is not None and not isinstance(raw, str):
            raise CatalogError(f"{field} must be text", "connection_invalid")
        cleaned = _clean_text(raw, field, 2048 if field not in {"name", "display_name"} else 120)
        if cleaned:
            result[field] = cleaned
    if "name" in result and "display_name" in result:
        raise CatalogError("provide only one connection name", "connection_invalid")
    if "display_name" in result:
        result["name"] = result.pop("display_name")
    if "scheduler" in value:
        if not isinstance(value.get("scheduler"), str):
            raise CatalogError("scheduler must be text", "connection_invalid")
        result["scheduler"] = _scheduler(value.get("scheduler"))
    if "timeout" in value:
        raw_timeout = value.get("timeout")
        if isinstance(raw_timeout, bool) or not str(raw_timeout).strip().isdigit():
            raise CatalogError("timeout must be an integer", "connection_invalid")
        timeout = int(str(raw_timeout).strip())
        if not 1 <= timeout <= 7_200:
            raise CatalogError("timeout must be between 1 and 7200", "connection_invalid")
        result["timeout"] = timeout
    if "clear_fields" in value:
        clear_fields = value.get("clear_fields")
        allowed_clear = {"workdir", "job_dir", "local_root", "remote_root", "timeout", "scheduler", "partition", "queue", "note"}
        if not isinstance(clear_fields, list) or len(clear_fields) > len(allowed_clear):
            raise CatalogError("clear_fields must be a short list", "connection_invalid")
        if any(not isinstance(field, str) or field not in allowed_clear for field in clear_fields):
            raise CatalogError("clear_fields contains an unsupported field", "connection_invalid")
        if len(set(clear_fields)) != len(clear_fields) or set(clear_fields).intersection(set(value) - {"clear_fields"}):
            raise CatalogError("clear_fields overlaps supplied connection values", "connection_invalid")
        result["clear_fields"] = list(clear_fields)
    return result


def _v5_gateway_choice(record: dict[str, Any]) -> dict[str, str]:
    """Safe, non-secret candidate context for an explicit gateway choice."""
    node, account = record.get("node") or {}, record.get("account") or {}
    return {
        "profile_id": str(record.get("profile_id") or ""),
        "node_id": str(node.get("id") or ""), "node_name": str(node.get("name") or ""),
        "account_id": str(account.get("id") or ""), "account_name": str(account.get("name") or ""),
        "user": str(account.get("user") or ""),
    }


def _v5_gateway_candidates(catalog_store: ClusterCatalogStore, server_id: str, account_id: str) -> list[dict[str, Any]]:
    direct_login = []
    for record in catalog_store.v4_list_connection_records(server_id):
        route = record.get("route") or {}
        if (
            str(route.get("mode") or "") == "direct"
            and not bool(route.get("legacy_route_needs_review"))
            and bool(record.get("last_connected_at"))
            and is_usable_login_node(record.get("node") or {})
        ):
            direct_login.append(record)
    same_account = [record for record in direct_login if str(record.get("account_id") or "") == str(account_id)]
    return same_account or direct_login


def _v5_gateway_selection_error(candidates: list[dict[str, Any]], *, empty: bool = False) -> CatalogError:
    error = CatalogError(
        "a verified login-node connection is required before matching this node" if empty
        else "choose one verified login-node connection",
        "gateway_login_connection_required" if empty else "gateway_selection_required",
    )
    # Deliberately attach a fixed safe DTO rather than a connection/profile row
    # which could grow new configuration fields in a future release.
    error.gateway_candidates = [_v5_gateway_choice(record) for record in candidates]
    return error


def _v5_match_records(
    catalog_store: ClusterCatalogStore, server_id: str, node_id: Any, account_id: Any, gateway_profile_id: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    server = catalog_store.v4_get_server(server_id)
    if server.get("requires_login_setup"):
        raise CatalogError("server needs a concrete login node before matching", "server_requires_login_setup")
    node = catalog_store.v4_get_node(node_id)
    account = catalog_store.v4_get_account(account_id)
    if node["server_id"] != server_id or account["server_id"] != server_id:
        raise CatalogError("node and account must belong to this server", "connection_server_mismatch")
    if not node.get("host") or not node.get("port"):
        raise CatalogError("node endpoint is incomplete", "connection_invalid")
    requested_gateway = None if gateway_profile_id in (None, "") else str(gateway_profile_id)
    if is_usable_login_node(node):
        if requested_gateway is not None:
            raise CatalogError("a login node is always connected directly", "route_invalid")
        return server, node, account, None, {"mode": "direct"}

    candidates = _v5_gateway_candidates(catalog_store, server_id, str(account["id"]))
    if not candidates:
        raise _v5_gateway_selection_error([], empty=True)
    selected: dict[str, Any] | None = None
    if requested_gateway is not None:
        try:
            requested = catalog_store.v4_get_connection_record(requested_gateway)
        except CatalogError as exc:
            if exc.code == "connection_not_found":
                raise _v5_gateway_selection_error(candidates) from None
            raise
        if any(str(record.get("profile_id")) == str(requested.get("profile_id")) for record in candidates):
            selected = requested
        else:
            raise _v5_gateway_selection_error(candidates)
    elif len(candidates) == 1:
        selected = candidates[0]
    else:
        raise _v5_gateway_selection_error(candidates)
    assert selected is not None
    return server, node, account, selected, {"mode": "via_login", "gateway_profile_id": str(selected["profile_id"])}


def _v5_frozen_match(
    server_id: str, server: dict[str, Any], node: dict[str, Any], account: dict[str, Any], route: dict[str, Any],
    connection: dict[str, Any], gateway_connection: dict[str, Any] | None, existing: dict[str, Any] | None,
    credential_revisions: dict[str, int],
) -> dict[str, Any]:
    frozen = _v4_frozen_match(
        server_id, server, node, account, route, connection, gateway_connection, existing,
    )
    frozen["schema"] = "v5-password-match-frozen-1"
    frozen["credential_revisions"] = dict(credential_revisions)
    return frozen


def _v5_frozen_test(profile_id: str, profile: dict[str, Any], credential_revisions: dict[str, int]) -> dict[str, Any]:
    return {
        "schema": "v5-password-test-frozen-1", "profile_id": str(profile_id),
        "profile": copy.deepcopy(profile), "credential_revisions": dict(credential_revisions),
    }


def _v5_catalog(adapter: Any, catalog_store: ClusterCatalogStore, credential_provider: Any) -> dict[str, Any]:
    catalog = _v4_catalog(adapter, catalog_store)
    profile_by_id = {
        _v4_profile_id(profile): profile for profile in _v4_profiles(adapter) if _v4_profile_id(profile)
    }
    for server in catalog.get("servers") or []:
        for account in server.get("accounts") or []:
            # This is the sole credential-related HTTP field.  It is a two-way
            # state label, not a target, revision, password, or key indicator.
            account["credential_state"] = _v5_credential_state(credential_provider, str(account.get("id") or ""))
        # _v4_catalog already shaped the record with node/account/route data;
        # rebuild each public DTO to remove its legacy key hint and attach an
        # exact, fail-closed password provenance label.
        server["connections"] = [
            _v5_connection_view(connection, profile_by_id.get(str(connection.get("profile_id") or "")))
            for connection in server.get("connections") or []
        ]
    for profile in catalog.get("unassigned_profiles") or []:
        profile.pop("has_key", None)
        profile["auth_mode"] = _v5_profile_auth_mode(profile_by_id.get(str(profile.get("profile_id") or profile.get("id") or "")))
    return catalog


def _v5_restore_credentials(credential_provider: Any, originals: dict[str, CredentialRecord | None]) -> None:
    """Restore every touched credential and verify content without exposing it."""
    failure = False
    for account_id, original in originals.items():
        try:
            _v5_credential_call(credential_provider.restore, account_id, original)
            current = _v5_credential_call(credential_provider.get, account_id)
            if original is None:
                failure = failure or current is not None
            else:
                # This comparison remains wholly in process and intentionally
                # avoids formatting either password in an exception or DTO.
                failure = failure or current is None or current.password != original.password
        except Exception:
            failure = True
    if failure:
        raise _v5_credential_error(fallback="credential_rollback_failed")


def _v5_delete_credentials(credential_provider: Any, account_ids: list[str]) -> dict[str, CredentialRecord | None]:
    originals: dict[str, CredentialRecord | None] = {}
    ordered = list(dict.fromkeys(str(value) for value in account_ids if str(value)))
    try:
        for account_id in ordered:
            originals[account_id] = _v5_credential_call(credential_provider.get, account_id)
        for account_id in ordered:
            _v5_credential_call(credential_provider.delete, account_id)
        return originals
    except Exception:
        try:
            _v5_restore_credentials(credential_provider, originals)
        except Exception:
            raise _v5_credential_error(fallback="credential_rollback_failed") from None
        raise


def _v5_error(error: Exception) -> JSONResponse:
    """Add only sanctioned V5 context to otherwise generic API failures."""
    if isinstance(error, CatalogError) and error.code == "credential_missing_reconfigure":
        return _error(error, stage="credential")
    candidates = getattr(error, "gateway_candidates", None)
    if isinstance(error, CatalogError) and isinstance(candidates, list):
        return _error(error, candidates=candidates)
    return _error(error)


# ---------------------------------------------------------------------------
# V4 canonical catalog API.  It is deliberately defined after the retired V3
# router above so existing imports keep working while all new registrations use
# the staged server -> node/account -> match contract below.

_V4_CONNECTION_FIELDS = {
    "name", "display_name", "key_path", "workdir", "job_dir", "local_root", "remote_root",
    "timeout", "scheduler", "partition", "queue", "note", "clear_fields",
}
_V4_PROBE_STAGES = {
    "validate", "tcp", "key_auth", "target_password", "gateway_password", "install_key", "nodes_probe",
}
_V4_PROBE_MESSAGES = {
    "invalid_connection": "The connection settings are invalid.",
    "unsupported_connection_field": "The connection includes an unsupported setting.",
    "probe_unavailable": "The local SSH probe is unavailable.",
    "key_path_unavailable": "The selected local key path is unavailable.",
    "key_permissions": "The app-generated SSH key has insecure file permissions.",
    "gateway_key_mismatch": "The gateway key does not match the saved gateway connection.",
    "gateway_key_path_unsupported": "The gateway connection needs a supported local key path.",
    "missing_dependency": "A required local SSH dependency is unavailable.",
    "gateway_tcp_failed": "The gateway endpoint could not be reached.",
    "target_tcp_failed": "The target endpoint could not be reached.",
    "gateway_password_required": "A gateway password is required for this one-time setup.",
    "target_password_required": "A target password is required for this one-time setup.",
    "gateway_auth_failed": "Gateway authentication did not succeed.",
    "target_auth_failed": "Target authentication did not succeed.",
    "gateway_ssh_failed": "The gateway SSH validation did not succeed.",
    "target_ssh_failed": "The target SSH validation did not succeed.",
    "gateway_key_install_failed": "Installing the gateway public key did not succeed.",
    "target_key_install_failed": "Installing the target public key did not succeed.",
    "host_key_changed": "The SSH host key changed and requires review.",
    "nodes_probe_failed": "The remote nodes validation did not succeed.",
    "profile_not_found": "The saved connection profile was not found.",
}


def _v4_profile_id(profile: dict[str, Any]) -> str:
    return str(profile.get("profile_id") or profile.get("id") or "").strip()


def _v4_new_profile_id(server_id: str, node_id: str, account_id: str) -> str:
    """Stable retry id for a new V4 pair; no password/config data participates."""
    digest = hashlib.sha256((server_id + "\x1f" + node_id + "\x1f" + account_id).encode("utf-8")).hexdigest()
    return "connection-" + digest[:24]


def _v4_profiles(adapter: Any) -> list[dict[str, Any]]:
    _cfg, profiles, _legacy = _profiles(adapter)
    return profiles


def _v4_safe_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Render only execution-safe profile facts; no key/path/options/proxy."""
    pid = _v4_profile_id(profile)
    if not pid:
        raise CatalogError("profile has no stable id", "profile_not_found")
    try:
        port = int(profile.get("port") or 22)
    except Exception:
        port = 22
    if not 1 <= port <= 65535:
        port = 22
    return {
        "id": pid, "profile_id": pid, "name": str(profile.get("name") or pid),
        "user": str(profile.get("user") or ""), "host": str(profile.get("host") or ""), "port": port,
        "has_key": bool(profile.get("has_key")), "configured": bool(profile.get("configured")),
        "legacy": bool(profile.get("legacy")),
    }


def _v4_endpoint_host(value: Any) -> str:
    """Compare IPv6 endpoint spellings without changing stored user input."""
    host = str(value or "").strip().lower()
    return host[1:-1] if host.startswith("[") and host.endswith("]") else host


def _v4_connection_view(record: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
    node = dict(record["node"])
    account = dict(record["account"])
    summary = _v4_safe_profile(profile) if isinstance(profile, dict) else None
    endpoint_mismatch = False
    if summary:
        endpoint_mismatch = (
            _v4_endpoint_host(summary.get("host")) != _v4_endpoint_host(node.get("host"))
            or int(summary.get("port") or 22) != int(node.get("port") or 22)
            or str(summary.get("user") or "") != str(account.get("user") or "")
        )
    return {
        "id": record["profile_id"], "profile_id": record["profile_id"],
        "server_id": record["server_id"], "node_id": record["node_id"], "account_id": record["account_id"],
        "name": (summary or {}).get("name") or account["name"], "node": node, "account": account,
        "route": dict(record["route"]), "last_connected_at": record.get("last_connected_at"),
        "has_key": bool((summary or {}).get("has_key")), "configured": bool((summary or {}).get("configured")),
        "status": "missing" if summary is None else ("connected" if record.get("last_connected_at") else "matched"),
        "endpoint_mismatch": endpoint_mismatch,
    }


def _v4_catalog(adapter: Any, catalog_store: ClusterCatalogStore) -> dict[str, Any]:
    profiles = _v4_profiles(adapter)
    # This is metadata-only and idempotent.  A bad historical row is retained,
    # not guessed, so a GET cannot create a credential-bearing profile.
    catalog_store.v4_migrate_legacy_links(profiles)
    profile_by_id = {_v4_profile_id(profile): profile for profile in profiles if _v4_profile_id(profile)}
    records = catalog_store.v4_list_connection_records()
    record_by_server: dict[str, list[dict[str, Any]]] = {}
    connection_ids: set[str] = set()
    for record in records:
        connection_ids.add(str(record["profile_id"]))
        record_by_server.setdefault(str(record["server_id"]), []).append(
            _v4_connection_view(record, profile_by_id.get(str(record["profile_id"])))
        )
    nodes_by_server: dict[str, list[dict[str, Any]]] = {}
    for node in catalog_store.v4_list_nodes():
        nodes_by_server.setdefault(str(node["server_id"]), []).append(node)
    accounts_by_server: dict[str, list[dict[str, Any]]] = {}
    for account in catalog_store.v4_list_accounts():
        accounts_by_server.setdefault(str(account["server_id"]), []).append(account)
    servers = []
    for server in catalog_store.v4_list_servers():
        sid = str(server["id"])
        servers.append({
            **server, "nodes": nodes_by_server.get(sid, []), "accounts": accounts_by_server.get(sid, []),
            "connections": record_by_server.get(sid, []),
        })
    orphan_links: list[dict[str, Any]] = []
    for link in catalog_store.list_links():
        pid = str(link["profile_id"])
        if pid not in profile_by_id:
            orphan_links.append({
                "profile_id": pid, "node_id": str(link["node_id"]), "server_id": str(link["server_id"]),
                "node_name": str(link["node_name"]), "created_at": str(link["created_at"]),
            })
    unassigned = [_v4_safe_profile(profile) for profile in profiles if _v4_profile_id(profile) not in connection_ids]
    return {
        "schema_version": 2, "binding_target": "connection_profile", "servers": servers,
        "unassigned_profiles": unassigned, "orphan_links": orphan_links,
    }


async def _v4_optional_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {}
    return await _body(request)


def _v4_connection_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogError("connection must be an object", "connection_invalid")
    if set(value) - _V4_CONNECTION_FIELDS:
        # Do not reflect unknown field names: a caller may have used a secret
        # as a field name, and this endpoint has a strict no-secret response.
        raise CatalogError("unsupported connection fields", "connection_invalid")
    result: dict[str, Any] = {}
    text_fields = ("name", "display_name", "key_path", "workdir", "job_dir", "local_root", "remote_root", "partition", "queue", "note")
    for field in text_fields:
        if field in value:
            raw = value.get(field)
            if raw is not None and not isinstance(raw, str):
                raise CatalogError(f"{field} must be text", "connection_invalid")
            cleaned = _clean_text(raw, field, 2048 if field not in {"name", "display_name"} else 120)
            # In a rematch, omitted and empty text values both mean preserve
            # the trusted saved value.  Clearing requires the explicit,
            # narrowly allowlisted clear_fields marker below.
            if cleaned:
                result[field] = cleaned
    if "name" in result and "display_name" in result:
        raise CatalogError("provide only one connection name", "connection_invalid")
    if "display_name" in result:
        result["name"] = result.pop("display_name")
    if "scheduler" in value:
        if not isinstance(value.get("scheduler"), str):
            raise CatalogError("scheduler must be text", "connection_invalid")
        result["scheduler"] = _scheduler(value.get("scheduler"))
    if "timeout" in value:
        raw = value.get("timeout")
        if isinstance(raw, bool) or not str(raw).strip().isdigit():
            raise CatalogError("timeout must be an integer", "connection_invalid")
        timeout = int(str(raw).strip())
        if not 1 <= timeout <= 7_200:
            raise CatalogError("timeout must be between 1 and 7200", "connection_invalid")
        result["timeout"] = timeout
    if "clear_fields" in value:
        clear_fields = value.get("clear_fields")
        # Explicit reset remains narrow and mirrors the legacy safe editable
        # connection fields.  Endpoint identity, user, route, proxy/jump and
        # arbitrary SSH flags are never clearable through this API.
        allowed_clear = {
            "key_path", "workdir", "job_dir", "local_root", "remote_root", "timeout",
            "scheduler", "partition", "queue", "note",
        }
        if not isinstance(clear_fields, list) or len(clear_fields) > len(allowed_clear):
            raise CatalogError("clear_fields must be a short list", "connection_invalid")
        if any(not isinstance(field, str) or field not in allowed_clear for field in clear_fields):
            raise CatalogError("clear_fields contains an unsupported field", "connection_invalid")
        if len(set(clear_fields)) != len(clear_fields) or set(clear_fields).intersection(set(value) - {"clear_fields"}):
            raise CatalogError("clear_fields overlaps supplied connection values", "connection_invalid")
        result["clear_fields"] = list(clear_fields)
    return result


def _v4_password(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 4096:
        raise CatalogError(f"{field} must be short text", "connection_invalid")
    return value


def _v4_probe_error(result: Any) -> JSONResponse:
    stage = "validate"
    password_required = None
    code = "connection_probe_failed"
    if isinstance(result, dict):
        candidate = str(result.get("stage") or "")
        if candidate in _V4_PROBE_STAGES:
            stage = candidate
        candidate_code = str(result.get("code") or "")
        if candidate_code in _V4_PROBE_MESSAGES:
            code = candidate_code
        required = result.get("password_required")
        if required in {"target", "gateway"}:
            password_required = required
    if password_required is None and code == "target_password_required":
        password_required = "target"
    if password_required is None and code == "gateway_password_required":
        password_required = "gateway"
    message = _V4_PROBE_MESSAGES.get(code, "Connection validation did not succeed.")
    extra: dict[str, Any] = {"stage": stage, "code": code, "message": message}
    if password_required:
        extra["password_required"] = password_required
    return JSONResponse({"ok": False, "error": message, **extra}, status_code=400)


def _v4_delete_existing_profiles(adapter: Any, profile_ids: list[str]) -> list[str]:
    existing = [pid for pid in dict.fromkeys(profile_ids) if adapter.get_profile(pid)]
    if not existing:
        return []
    operation = getattr(adapter, "delete_profiles", None)
    if not callable(operation):
        raise CatalogError("catalog profile deletion is unavailable", "profile_delete_failed")
    result = operation(existing)
    if result is False or (isinstance(result, dict) and result.get("ok") is False):
        raise CatalogError("profile deletion failed", "profile_delete_failed")
    return existing


def _v4_match_records(
    catalog_store: ClusterCatalogStore, server_id: str, node_id: Any, account_id: Any, route: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    server = catalog_store.v4_get_server(server_id)
    if server.get("requires_login_setup"):
        raise CatalogError("server needs a concrete login node before matching", "server_requires_login_setup")
    node = catalog_store.v4_get_node(node_id)
    account = catalog_store.v4_get_account(account_id)
    if node["server_id"] != server_id or account["server_id"] != server_id:
        raise CatalogError("node and account must belong to this server", "connection_server_mismatch")
    if not node.get("host") or not node.get("port"):
        raise CatalogError("node endpoint is incomplete", "connection_invalid")
    mode, gateway_id = catalog_store._v4_route_values(route)
    route_value: dict[str, Any] = {"mode": mode}
    gateway_connection = None
    if gateway_id:
        gateway_connection = catalog_store.v4_get_connection_record(gateway_id)
        if gateway_connection["server_id"] != server_id:
            raise CatalogError("gateway connection must belong to the same server", "gateway_server_mismatch")
        if not is_usable_login_node(gateway_connection["node"]):
            raise CatalogError("gateway connection must use a login node", "gateway_not_login")
        if gateway_connection["route"].get("mode") != "direct" or gateway_connection["route"].get("legacy_route_needs_review"):
            raise CatalogError("gateway connection must be an explicit direct match", "route_cycle")
        route_value["gateway_profile_id"] = gateway_id
    return server, node, account, gateway_connection, route_value


def _v4_frozen_match(
    server_id: str,
    server: dict[str, Any],
    node: dict[str, Any],
    account: dict[str, Any],
    route: dict[str, Any],
    connection: dict[str, Any],
    gateway_connection: dict[str, Any] | None,
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    """Freeze all catalog-owned sources before the unlocked SSH worker phase.

    This is a complete source snapshot, not an opaque adapter receipt.  It
    contains no password/key material.  The adapter fingerprints this exact
    shape while retaining its verified candidate privately; this router later
    recreates the same structure under its short lock and refuses to commit if
    even a server-level source field changed.
    """
    existing_profile_id = str(existing["profile_id"]) if existing else None
    profile_id = existing_profile_id or _v4_new_profile_id(server_id, node["id"], account["id"])
    return {
        "schema": "v4-match-frozen-1",
        "server_id": str(server_id),
        "server": copy.deepcopy(server),
        "node": copy.deepcopy(node),
        "account": copy.deepcopy(account),
        "route": copy.deepcopy(route),
        "connection": copy.deepcopy(connection),
        "gateway_connection": copy.deepcopy(gateway_connection),
        "existing_profile_id": existing_profile_id,
        "profile_id": profile_id,
    }


def _v4_frozen_test(profile_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Freeze safe facts for a saved-profile probe; adapter hashes YAML itself."""
    return {
        "schema": "v4-test-frozen-1",
        "profile_id": str(profile_id),
        "profile": copy.deepcopy(profile),
    }


def _v4_catalog_changed_retry() -> JSONResponse:
    """Controlled stale-snapshot response; never reveal adapter/YAML details."""
    return _error(CatalogError(
        "catalog data changed while connection verification was running; retry the request",
        "catalog_changed_retry",
    ))


def _v4_adapter_stale(value: Any) -> bool:
    """Recognize only the fixed adapter stale signal, not arbitrary messages."""
    return isinstance(value, dict) and value.get("ok") is False and value.get("code") == "catalog_changed_retry"


_V4_SNAPSHOT_STALE_CODES = {
    "server_not_found", "node_not_found", "account_not_found", "connection_not_found", "gateway_not_found",
    "connection_server_mismatch", "gateway_server_mismatch", "gateway_not_login", "route_cycle",
    "route_invalid", "connection_invalid", "server_requires_login_setup",
}


def _v4_snapshot_changed(error: CatalogError) -> bool:
    """Whether a Phase-2 catalog exception represents expected source drift."""
    return error.code in _V4_SNAPSHOT_STALE_CODES


def _build_v4_router(adapter: Any, db_path_provider: Callable[[], str]) -> APIRouter:
    """Build the V4 canonical staged catalog router.

    The only YAML bridge is the server-owned adapter.  This router stores no
    secret and never calls a real SSH implementation itself; tests inject a
    fake adapter with the same probe/persist transaction boundary.
    """
    router = APIRouter()

    def store() -> ClusterCatalogStore:
        return ClusterCatalogStore(db_path_provider())

    @router.get("/api/cluster/catalog")
    async def get_catalog():
        try:
            with _adapter_lock(adapter):
                return _v4_catalog(adapter, store())
        except Exception as exc:
            return _error(exc)

    @router.post("/api/cluster/catalog/servers")
    async def create_server(request: Request):
        try:
            body = await _body(request)
            if {"node", "account"}.intersection(body):
                raise CatalogError("server creation now requires login_node; add users and match separately", "workflow_changed")
            if set(body) - {"name", "description", "login_node"}:
                raise _payload_error("unsupported server fields")
            if "login_node" not in body:
                raise CatalogError("login_node is required", "catalog_invalid")
            with _adapter_lock(adapter):
                server, node = store().v4_create_server(body.get("name"), body.get("description", ""), body.get("login_node"))
            return JSONResponse({"ok": True, "server": server, "node": node}, status_code=201)
        except Exception as exc:
            return _error(exc)

    @router.patch("/api/cluster/catalog/servers/{server_id}")
    async def update_server(server_id: str, request: Request):
        try:
            with _adapter_lock(adapter):
                server = store().v4_update_server(server_id, await _body(request))
            return {"ok": True, "server": server}
        except Exception as exc:
            return _error(exc)

    @router.delete("/api/cluster/catalog/servers/{server_id}")
    async def delete_server(server_id: str):
        try:
            with _adapter_lock(adapter):
                catalog_store = store()
                catalog_store.v4_migrate_legacy_links(_v4_profiles(adapter))
                plan = catalog_store.v4_server_delete_plan(server_id)
                with _profile_transaction(adapter):
                    deleted_remote = _v4_delete_existing_profiles(adapter, list(plan["profile_ids"]))
                    result = catalog_store.v4_delete_server_metadata(plan)
            return {
                "ok": True, "deleted": {"server_id": server_id},
                "deleted_profile_ids": result["deleted_profile_ids"], "deleted_remote_profile_ids": deleted_remote,
                "cascade": {"nodes": len(result["deleted_node_ids"]), "accounts": len(result["deleted_account_ids"])},
            }
        except Exception as exc:
            return _error(exc)

    @router.post("/api/cluster/catalog/servers/{server_id}/nodes")
    async def create_node(server_id: str, request: Request):
        try:
            body = await _body(request)
            if {"node", "account"}.intersection(body):
                raise CatalogError("node and user creation are now separate; match only after both exist", "workflow_changed")
            with _adapter_lock(adapter):
                node = store().v4_create_node(server_id, body)
            return JSONResponse({"ok": True, "node": node}, status_code=201)
        except Exception as exc:
            return _error(exc)

    @router.patch("/api/cluster/catalog/nodes/{node_id}")
    async def update_node(node_id: str, request: Request):
        try:
            with _adapter_lock(adapter):
                node = store().v4_update_node(node_id, await _body(request))
            return {"ok": True, "node": node}
        except Exception as exc:
            return _error(exc)

    @router.delete("/api/cluster/catalog/nodes/{node_id}")
    async def delete_node(node_id: str, request: Request):
        try:
            body = await _v4_optional_body(request)
            if set(body) - {"replacement_node_id"}:
                raise _payload_error("unsupported node deletion fields")
            with _adapter_lock(adapter):
                catalog_store = store()
                catalog_store.v4_migrate_legacy_links(_v4_profiles(adapter))
                plan = catalog_store.v4_node_delete_plan(node_id, body.get("replacement_node_id"))
                with _profile_transaction(adapter):
                    deleted_remote = _v4_delete_existing_profiles(adapter, list(plan["profile_ids"]))
                    result = catalog_store.v4_delete_node_metadata(plan)
            return {
                "ok": True, "deleted": {"node_id": node_id}, "deleted_profile_ids": result["deleted_profile_ids"],
                "deleted_remote_profile_ids": deleted_remote, "promoted_node_id": result.get("promoted_node_id"),
            }
        except Exception as exc:
            return _error(exc)

    @router.post("/api/cluster/catalog/servers/{server_id}/accounts")
    async def create_account(server_id: str, request: Request):
        try:
            with _adapter_lock(adapter):
                account = store().v4_create_account(server_id, await _body(request))
            return JSONResponse({"ok": True, "account": account}, status_code=201)
        except Exception as exc:
            return _error(exc)

    @router.patch("/api/cluster/catalog/accounts/{account_id}")
    async def update_account(account_id: str, request: Request):
        try:
            with _adapter_lock(adapter):
                account = store().v4_update_account(account_id, await _body(request))
            return {"ok": True, "account": account}
        except Exception as exc:
            return _error(exc)

    @router.delete("/api/cluster/catalog/accounts/{account_id}")
    async def delete_account(account_id: str):
        try:
            with _adapter_lock(adapter):
                catalog_store = store()
                catalog_store.v4_migrate_legacy_links(_v4_profiles(adapter))
                plan = catalog_store.v4_account_delete_plan(account_id)
                with _profile_transaction(adapter):
                    deleted_remote = _v4_delete_existing_profiles(adapter, list(plan["profile_ids"]))
                    result = catalog_store.v4_delete_account_metadata(plan)
            return {
                "ok": True, "deleted": {"account_id": account_id},
                "deleted_profile_ids": result["deleted_profile_ids"], "deleted_remote_profile_ids": deleted_remote,
            }
        except Exception as exc:
            return _error(exc)

    @router.post("/api/cluster/catalog/servers/{server_id}/connections/match")
    async def match_connection(server_id: str, request: Request):
        try:
            body = await _body(request)
            allowed = {"node_id", "account_id", "route", "connection", "target_password", "gateway_password"}
            if set(body) - allowed:
                raise CatalogError("unsupported match fields", "connection_invalid")
            if "node_id" not in body or "account_id" not in body or "route" not in body or "connection" not in body:
                raise CatalogError("node_id, account_id, route, and connection are required", "connection_invalid")
            connection = _v4_connection_payload(body.get("connection"))
            target_password = _v4_password(body.get("target_password"), "target_password")
            gateway_password = _v4_password(body.get("gateway_password"), "gateway_password")

            # Phase 1: obtain a complete, trusted snapshot while the adapter
            # lock is held only for local catalog/YAML reads.  Do not move the
            # actual SSH validation into this section: it may take seconds.
            with _adapter_lock(adapter):
                catalog_store = store()
                catalog_store.v4_migrate_legacy_links(_v4_profiles(adapter))
                server, node, account, gateway_connection, route_value = _v4_match_records(
                    catalog_store, server_id, body.get("node_id"), body.get("account_id"), body.get("route"),
                )
                existing = catalog_store.v4_connection_for_pair(server_id, node["id"], account["id"])
                frozen = _v4_frozen_match(
                    server_id, server, node, account, route_value, connection, gateway_connection, existing,
                )

            probe = getattr(adapter, "probe_verified_candidate", None)
            if not callable(probe):
                raise CatalogError("connection matching is unavailable", "match_unavailable")
            # Phase 1.5: run all slow SSH work outside the event loop and the
            # adapter/catalog lock.  Passwords exist only in this worker call,
            # never in ``frozen`` or a SQLite/YAML catalog record.
            probe_result = await _run_catalog_worker(
                probe, copy.deepcopy(frozen), {
                    "target_password": target_password,
                    "gateway_password": gateway_password,
                },
            )
            if not isinstance(probe_result, dict) or probe_result.get("ok") is not True:
                return _v4_probe_error(probe_result)

            # Phase 2: reacquire the short lock, recreate the entire catalog
            # source snapshot, and commit only the adapter-local candidate
            # verified above.  Any catalog or effective YAML drift must retry
            # rather than persisting a stale endpoint/account/route.
            with _adapter_lock(adapter):
                catalog_store = store()
                try:
                    catalog_store.v4_migrate_legacy_links(_v4_profiles(adapter))
                    fresh_server, fresh_node, fresh_account, fresh_gateway, fresh_route = _v4_match_records(
                        catalog_store, frozen["server_id"], frozen["node"]["id"], frozen["account"]["id"], frozen["route"],
                    )
                    fresh_existing = catalog_store.v4_connection_for_pair(
                        frozen["server_id"], fresh_node["id"], fresh_account["id"],
                    )
                    fresh = _v4_frozen_match(
                        frozen["server_id"], fresh_server, fresh_node, fresh_account, fresh_route,
                        connection, fresh_gateway, fresh_existing,
                    )
                except CatalogError as exc:
                    if _v4_snapshot_changed(exc):
                        return _v4_catalog_changed_retry()
                    raise
                if fresh != frozen:
                    return _v4_catalog_changed_retry()
                persist = getattr(adapter, "persist_verified_candidate", None)
                enable = getattr(adapter, "set_remote_enabled", None)
                if not callable(persist) or not callable(enable):
                    raise CatalogError("connection persistence is unavailable", "profile_persist_failed")
                with _profile_transaction(adapter):
                    persisted = persist(copy.deepcopy(fresh))
                    if _v4_adapter_stale(persisted):
                        raise CatalogError(
                            "catalog data changed while connection verification was running; retry the request",
                            "catalog_changed_retry",
                        )
                    profile_id = fresh["profile_id"]
                    returned_id = _v4_profile_id(persisted) if isinstance(persisted, dict) else ""
                    if returned_id and returned_id != profile_id:
                        raise CatalogError("persisted connection id changed unexpectedly", "profile_persist_failed")
                    enable(True)
                    catalog_store.v4_upsert_connection(
                        fresh["server_id"], fresh_node["id"], fresh_account["id"], profile_id, fresh_route, connected=True,
                    )
                record = catalog_store.v4_get_connection_record(profile_id)
                saved_profile = adapter.get_profile(profile_id)
            return JSONResponse({
                "ok": True, "stage": "nodes_probe", "code": "ok",
                "connection": _v4_connection_view(record, saved_profile), "remote_enabled": True,
            }, status_code=201)
        except Exception as exc:
            return _error(exc)

    @router.post("/api/cluster/catalog/connections/{profile_id}/test")
    async def test_connection(profile_id: str):
        try:
            # As with matching, only short local reads are protected by the
            # adapter lock.  The remote nodes probe runs in a worker below.
            with _adapter_lock(adapter):
                catalog_store = store()
                source_record = catalog_store.v4_get_connection_record(profile_id)
                source_profile = adapter.get_profile(profile_id)
                if not isinstance(source_profile, dict):
                    raise CatalogError("saved connection profile was not found", "profile_not_found")
                frozen = _v4_frozen_test(profile_id, _v4_safe_profile(source_profile))

            operation = getattr(adapter, "probe_saved_connection", None)
            if not callable(operation):
                raise CatalogError("connection testing is unavailable", "test_unavailable")
            result = await _run_catalog_worker(operation, copy.deepcopy(frozen))
            if not isinstance(result, dict) or result.get("ok") is not True:
                return _v4_probe_error(result)

            with _adapter_lock(adapter):
                catalog_store = store()
                try:
                    fresh_record = catalog_store.v4_get_connection_record(profile_id)
                except CatalogError as exc:
                    if _v4_snapshot_changed(exc):
                        return _v4_catalog_changed_retry()
                    raise
                fresh_profile = adapter.get_profile(profile_id)
                if not isinstance(fresh_profile, dict):
                    return _v4_catalog_changed_retry()
                fresh = _v4_frozen_test(profile_id, _v4_safe_profile(fresh_profile))
                if fresh_record != source_record or fresh != frozen:
                    return _v4_catalog_changed_retry()
                confirm = getattr(adapter, "confirm_tested_connection", None)
                if not callable(confirm):
                    raise CatalogError("connection testing is unavailable", "test_unavailable")
                confirmed = confirm(copy.deepcopy(fresh))
                if _v4_adapter_stale(confirmed):
                    return _v4_catalog_changed_retry()
                if not isinstance(confirmed, dict) or confirmed.get("ok") is not True:
                    return _v4_probe_error(confirmed)
                catalog_store.v4_touch_connection(profile_id)
                record = catalog_store.v4_get_connection_record(profile_id)
                saved_profile = adapter.get_profile(profile_id)
            return {
                "ok": True, "stage": "nodes_probe", "code": "ok",
                "connection": _v4_connection_view(record, saved_profile),
            }
        except Exception as exc:
            return _error(exc)

    @router.delete("/api/cluster/catalog/connections/{profile_id}")
    async def delete_connection(profile_id: str):
        try:
            with _adapter_lock(adapter):
                catalog_store = store()
                plan = catalog_store.v4_connection_delete_plan(profile_id)
                with _profile_transaction(adapter):
                    deleted_remote = _v4_delete_existing_profiles(adapter, list(plan["profile_ids"]))
                    result = catalog_store.v4_delete_connection_metadata(plan)
            return {
                "ok": True, "deleted": {"profile_id": profile_id},
                "deleted_profile_ids": result["deleted_profile_ids"], "deleted_remote_profile_ids": deleted_remote,
            }
        except Exception as exc:
            return _error(exc)

    @router.delete("/api/cluster/catalog/profiles/{profile_id}")
    async def delete_unassigned_profile(profile_id: str):
        """Safe compatibility cleanup for a profile not mapped by V4."""
        try:
            with _adapter_lock(adapter):
                catalog_store = store()
                try:
                    catalog_store.v4_get_connection_record(profile_id)
                except CatalogError as exc:
                    if exc.code != "connection_not_found":
                        raise
                else:
                    raise CatalogError("profile is a matched V4 connection; delete that connection instead", "profile_already_connected")
                with _profile_transaction(adapter):
                    deleted_remote = _v4_delete_existing_profiles(adapter, [profile_id])
                    deleted_metadata = catalog_store.v4_cleanup_deleted_profile(profile_id)
            return {
                "ok": True, "deleted": {"profile_id": profile_id},
                "deleted_profile_ids": deleted_metadata, "deleted_remote_profile_ids": deleted_remote,
            }
        except Exception as exc:
            return _error(exc)

    # Explicit controlled replies for retired V3 one-shot account paths.  They
    # must not fall through to 404 or silently create a profile outside match.
    @router.api_route("/api/cluster/catalog/nodes/{node_id}/adopt", methods=["POST"])
    @router.api_route("/api/cluster/catalog/nodes/{node_id}/accounts", methods=["POST"])
    @router.api_route("/api/cluster/catalog/nodes/{node_id}/accounts/{profile_id}", methods=["PATCH", "DELETE"])
    async def retired_v3_account_workflow(node_id: str, profile_id: str | None = None):
        _ = node_id, profile_id
        return _error(CatalogError("this V3 one-step account workflow was replaced by server accounts and match", "workflow_changed"))

    return router


def _v5_affected_connection_records(catalog_store: ClusterCatalogStore, account_id: str) -> list[dict[str, Any]]:
    """Return profiles whose target or gateway identity depends on an account."""
    records = catalog_store.v4_list_connection_records()
    by_profile = {str(record.get("profile_id") or ""): record for record in records}
    affected: list[dict[str, Any]] = []
    for record in records:
        gateway_id = str((record.get("route") or {}).get("gateway_profile_id") or "")
        gateway = by_profile.get(gateway_id)
        if str(record.get("account_id") or "") != account_id and (
            not gateway or str(gateway.get("account_id") or "") != account_id
        ):
            continue
        public_record = copy.deepcopy(record)
        if gateway is not None:
            public_record["gateway_connection"] = copy.deepcopy(gateway)
        affected.append(public_record)
    return affected


def _v5_affected_credential_ids(records: list[dict[str, Any]]) -> list[str]:
    account_ids: list[str] = []
    for record in records:
        account_ids.append(str(record.get("account_id") or ""))
        gateway = record.get("gateway_connection")
        if isinstance(gateway, dict):
            account_ids.append(str(gateway.get("account_id") or ""))
    return [value for value in account_ids if value]


_V5_PROFILE_AUTH_MODE = "catalog_password_v5"
_V5_PROFILE_ROUTE_MARKER = "v5-password-route-1"


def _v5_profile_auth_mode(profile: dict[str, Any] | None) -> str:
    """Classify profile provenance without treating partial V5 state as legacy."""
    if not isinstance(profile, dict):
        return "missing"
    auth_mode = str(profile.get("auth_mode") or "")
    route_marker = str(profile.get("catalog_v5_ssh_route") or "")
    if auth_mode == _V5_PROFILE_AUTH_MODE and route_marker == _V5_PROFILE_ROUTE_MARKER:
        return "password"
    if auth_mode or route_marker:
        # A partial/incorrect V5 marker could otherwise route this profile via
        # legacy key behavior.  Fail closed so the user has to reconfigure it.
        raise CatalogError("saved password connection provenance is incomplete", "profile_auth_provenance_invalid")
    return "legacy"


def _v5_profile_password_route(profile: dict[str, Any]) -> bool:
    return _v5_profile_auth_mode(profile) == "password"


def _v5_connection_view(record: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
    """V5 public connection DTO: never disclose key/auth implementation data."""
    view = _v4_connection_view(record, profile)
    view.pop("has_key", None)
    view["auth_mode"] = _v5_profile_auth_mode(profile)
    return view


def _build_v5_router(adapter: Any, db_path_provider: Callable[[], str], credential_provider: Any) -> APIRouter:
    """Build the strict V5 password-account router.

    Credentials are deliberately injected so tests use ``MemoryCredentialStore``
    and production owns its Windows Credential Manager instance.  The router
    has no fallback store and no key/public-key API path.
    """
    router = APIRouter()

    def store() -> ClusterCatalogStore:
        return ClusterCatalogStore(db_path_provider())

    @router.get("/api/cluster/catalog")
    async def get_catalog():
        try:
            with _adapter_lock(adapter):
                return _v5_catalog(adapter, store(), credential_provider)
        except Exception as exc:
            return _v5_error(exc)

    @router.post("/api/cluster/catalog/servers")
    async def create_server(request: Request):
        try:
            body = await _body(request)
            if {"node", "account"}.intersection(body):
                raise CatalogError("server creation now requires login_node; add users and match separately", "workflow_changed")
            if set(body) - {"name", "description", "login_node"}:
                raise _payload_error("unsupported server fields")
            if "login_node" not in body:
                raise CatalogError("login_node is required", "catalog_invalid")
            with _adapter_lock(adapter):
                server, node = store().v5_create_server(body.get("name"), body.get("description", ""), body.get("login_node"))
            return JSONResponse({"ok": True, "server": server, "node": node}, status_code=201)
        except Exception as exc:
            return _v5_error(exc)

    @router.patch("/api/cluster/catalog/servers/{server_id}")
    async def update_server(server_id: str, request: Request):
        try:
            with _adapter_lock(adapter):
                server = store().v4_update_server(server_id, await _body(request))
            return {"ok": True, "server": server}
        except Exception as exc:
            return _v5_error(exc)

    @router.delete("/api/cluster/catalog/servers/{server_id}")
    async def delete_server(server_id: str):
        try:
            with _adapter_lock(adapter):
                catalog_store = store()
                catalog_store.v4_migrate_legacy_links(_v4_profiles(adapter))
                plan = catalog_store.v4_server_delete_plan(server_id)
                originals: dict[str, CredentialRecord | None] = {}
                try:
                    with _profile_transaction(adapter):
                        # Delete account credentials before the metadata half;
                        # every later failure restores and verifies them below.
                        originals = _v5_delete_credentials(credential_provider, list(plan["account_ids"]))
                        deleted_remote = _v4_delete_existing_profiles(adapter, list(plan["profile_ids"]))
                        result = catalog_store.v4_delete_server_metadata(plan)
                except Exception:
                    if originals:
                        try:
                            _v5_restore_credentials(credential_provider, originals)
                        except Exception:
                            raise _v5_credential_error(fallback="credential_rollback_failed") from None
                    raise
            return {
                "ok": True, "deleted": {"server_id": server_id},
                "deleted_profile_ids": result["deleted_profile_ids"], "deleted_remote_profile_ids": deleted_remote,
                "cascade": {"nodes": len(result["deleted_node_ids"]), "accounts": len(result["deleted_account_ids"])},
            }
        except Exception as exc:
            return _v5_error(exc)

    @router.post("/api/cluster/catalog/servers/{server_id}/nodes")
    async def create_node(server_id: str, request: Request):
        try:
            body = await _body(request)
            if {"node", "account"}.intersection(body):
                raise CatalogError("node and user creation are now separate; match only after both exist", "workflow_changed")
            with _adapter_lock(adapter):
                node = store().v5_create_node(server_id, body)
            return JSONResponse({"ok": True, "node": node}, status_code=201)
        except Exception as exc:
            return _v5_error(exc)

    @router.patch("/api/cluster/catalog/nodes/{node_id}")
    async def update_node(node_id: str, request: Request):
        try:
            with _adapter_lock(adapter):
                node = store().v4_update_node(node_id, await _body(request))
            return {"ok": True, "node": node}
        except Exception as exc:
            return _v5_error(exc)

    @router.delete("/api/cluster/catalog/nodes/{node_id}")
    async def delete_node(node_id: str, request: Request):
        try:
            body = await _v4_optional_body(request)
            if set(body) - {"replacement_node_id"}:
                raise _payload_error("unsupported node deletion fields")
            with _adapter_lock(adapter):
                catalog_store = store()
                catalog_store.v4_migrate_legacy_links(_v4_profiles(adapter))
                plan = catalog_store.v4_node_delete_plan(node_id, body.get("replacement_node_id"))
                with _profile_transaction(adapter):
                    # Node deletion intentionally retains account credentials:
                    # users can attach the same server user to another node.
                    deleted_remote = _v4_delete_existing_profiles(adapter, list(plan["profile_ids"]))
                    result = catalog_store.v4_delete_node_metadata(plan)
            return {
                "ok": True, "deleted": {"node_id": node_id}, "deleted_profile_ids": result["deleted_profile_ids"],
                "deleted_remote_profile_ids": deleted_remote, "promoted_node_id": result.get("promoted_node_id"),
            }
        except Exception as exc:
            return _v5_error(exc)

    @router.post("/api/cluster/catalog/servers/{server_id}/accounts")
    async def create_account(server_id: str, request: Request):
        try:
            metadata, password = _v5_account_payload(await _body(request), creating=True)
            assert password is not None
            _v5_require_available_credential_store(credential_provider)
            with _adapter_lock(adapter):
                catalog_store = store()
                account = catalog_store.v4_create_account(server_id, metadata)
                try:
                    _v5_credential_call(credential_provider.put, str(account["id"]), password)
                except Exception:
                    # A native Credential Manager write can fail after it has
                    # actually persisted.  Remove and verify the new target
                    # *before* deleting SQLite metadata, otherwise an orphan
                    # password could remain for a now-unreachable account id.
                    try:
                        _v5_credential_call(credential_provider.delete, str(account["id"]))
                        if _v5_credential_call(credential_provider.get, str(account["id"])) is not None:
                            raise _v5_credential_error(fallback="credential_rollback_failed")
                    except Exception:
                        raise _v5_credential_error(fallback="credential_metadata_recovery_required") from None
                    try:
                        rollback_plan = catalog_store.v4_account_delete_plan(account["id"])
                        catalog_store.v4_delete_account_metadata(rollback_plan)
                    except Exception:
                        raise _v5_credential_error(fallback="credential_metadata_recovery_required") from None
                    raise
                account["credential_state"] = "configured"
            return JSONResponse({"ok": True, "account": account}, status_code=201)
        except Exception as exc:
            return _v5_error(exc)

    @router.patch("/api/cluster/catalog/accounts/{account_id}")
    async def update_account(account_id: str, request: Request):
        try:
            metadata, password = _v5_account_payload(await _body(request), creating=False)
            _v5_require_available_credential_store(credential_provider)
            with _adapter_lock(adapter):
                catalog_store = store()
                before = catalog_store.v4_get_account(account_id)
                # Normalize public metadata before calculating the prospective
                # identity that the adapter will receive.
                normalized = catalog_store._v4_account_values(metadata, creating=False) if metadata else {}
                account_after = {**before, **normalized}
                affected = _v5_affected_connection_records(catalog_store, str(before["id"]))
                # A matched account is part of durable historical job/profile
                # identity.  Do not rebind that account id to a different
                # username: old jobs could otherwise read the new user's local
                # password.  Display metadata and the password itself remain
                # editable, with password changes converted atomically below.
                # The edit dialog always sends its current username together
                # with a password change.  Lock only a real identity change;
                # rejecting an unchanged normalized value would make the
                # documented offline password update unusable for any matched
                # account.
                if affected and "user" in normalized and normalized["user"] != before["user"]:
                    raise CatalogError(
                        "account user is locked while matched connections exist; delete or rematch the connection first",
                        "account_has_connections_user_locked",
                    )
                must_convert = bool(affected) and password is not None
                original_credential: CredentialRecord | None = None

                if must_convert:
                    # Both the target and any gateway users must be configured
                    # before a profile becomes V5/password-only.  This is also
                    # a clean failure boundary for a legacy key profile: there
                    # is no fallback to its old key after conversion starts.
                    prerequisite_ids = _v5_affected_credential_ids(affected)
                    if password is not None:
                        # The supplied password is the deliberate repair for a
                        # missing target credential.  Other target/gateway
                        # accounts must already be configured, but this one is
                        # saved before the adapter converts any legacy profile.
                        prerequisite_ids = [
                            value for value in prerequisite_ids if value != str(before["id"])
                        ]
                    _v5_credential_revisions(credential_provider, prerequisite_ids)
                    if password is not None:
                        original_credential = _v5_credential_call(credential_provider.get, str(before["id"]))
                    converter = getattr(adapter, "convert_catalog_account_to_v5", None)
                    if not callable(converter):
                        raise CatalogError("password profile conversion is unavailable", "profile_update_failed")
                    try:
                        with _profile_transaction(adapter):
                            if password is not None:
                                _v5_credential_call(credential_provider.put, str(before["id"]), password)
                            converted = converter(copy.deepcopy(account_after), copy.deepcopy(affected))
                            if isinstance(converted, dict) and converted.get("ok") is False:
                                raise CatalogError("password profile conversion failed", "profile_update_failed")
                            if normalized:
                                account = catalog_store.v4_update_account(account_id, normalized)
                            else:
                                account = before
                    except Exception:
                        if password is not None:
                            try:
                                _v5_restore_credentials(credential_provider, {str(before["id"]): original_credential})
                            except Exception:
                                raise _v5_credential_error(fallback="credential_rollback_failed") from None
                        raise
                else:
                    # No connected profile needs rewriting.  Metadata and the
                    # local credential still form a compensated pair.
                    account = before
                    metadata_changed = bool(normalized)
                    original_credential = _v5_credential_call(credential_provider.get, str(before["id"])) if password is not None else None
                    try:
                        if normalized:
                            account = catalog_store.v4_update_account(account_id, normalized)
                        if password is not None:
                            _v5_credential_call(credential_provider.put, str(before["id"]), password)
                    except Exception:
                        recovery_failed = False
                        if password is not None:
                            try:
                                _v5_restore_credentials(credential_provider, {str(before["id"]): original_credential})
                            except Exception:
                                recovery_failed = True
                        if metadata_changed:
                            try:
                                catalog_store.v4_update_account(account_id, {
                                    "name": before["name"], "user": before["user"], "note": before["note"],
                                })
                            except Exception:
                                recovery_failed = True
                        if recovery_failed:
                            raise _v5_credential_error(fallback="credential_metadata_recovery_required") from None
                        raise
                account["credential_state"] = _v5_credential_state(credential_provider, str(account["id"]))
            return {"ok": True, "account": account}
        except Exception as exc:
            return _v5_error(exc)

    @router.delete("/api/cluster/catalog/accounts/{account_id}")
    async def delete_account(account_id: str):
        try:
            _v5_require_available_credential_store(credential_provider)
            with _adapter_lock(adapter):
                catalog_store = store()
                catalog_store.v4_migrate_legacy_links(_v4_profiles(adapter))
                plan = catalog_store.v4_account_delete_plan(account_id)
                originals: dict[str, CredentialRecord | None] = {}
                try:
                    with _profile_transaction(adapter):
                        originals = _v5_delete_credentials(credential_provider, [str(plan["account_id"])])
                        deleted_remote = _v4_delete_existing_profiles(adapter, list(plan["profile_ids"]))
                        result = catalog_store.v4_delete_account_metadata(plan)
                except Exception:
                    if originals:
                        try:
                            _v5_restore_credentials(credential_provider, originals)
                        except Exception:
                            raise _v5_credential_error(fallback="credential_rollback_failed") from None
                    raise
            return {
                "ok": True, "deleted": {"account_id": account_id},
                "deleted_profile_ids": result["deleted_profile_ids"], "deleted_remote_profile_ids": deleted_remote,
            }
        except Exception as exc:
            return _v5_error(exc)

    @router.post("/api/cluster/catalog/servers/{server_id}/connections/match")
    async def match_connection(server_id: str, request: Request):
        try:
            body = await _body(request)
            allowed = {"node_id", "account_id", "connection", "gateway_profile_id"}
            if set(body) - allowed:
                raise CatalogError("unsupported match fields", "connection_invalid")
            if "node_id" not in body or "account_id" not in body or "connection" not in body:
                raise CatalogError("node_id, account_id, and connection are required", "connection_invalid")
            connection = _v5_connection_payload(body.get("connection"))
            _v5_require_available_credential_store(credential_provider)

            # Phase 1 freezes only public catalog data and Credential Manager
            # revision numbers.  The slow SSH worker receives no password from
            # this router; the server-owned adapter reads it directly in memory.
            with _adapter_lock(adapter):
                catalog_store = store()
                catalog_store.v4_migrate_legacy_links(_v4_profiles(adapter))
                server, node, account, gateway_connection, route_value = _v5_match_records(
                    catalog_store, server_id, body.get("node_id"), body.get("account_id"), body.get("gateway_profile_id"),
                )
                account_ids = [str(account["id"])]
                if gateway_connection is not None:
                    account_ids.append(str(gateway_connection["account_id"]))
                revisions = _v5_credential_revisions(credential_provider, account_ids)
                existing = catalog_store.v4_connection_for_pair(server_id, node["id"], account["id"])
                frozen = _v5_frozen_match(
                    server_id, server, node, account, route_value, connection, gateway_connection, existing, revisions,
                )

            probe = getattr(adapter, "probe_verified_candidate", None)
            if not callable(probe):
                raise CatalogError("connection matching is unavailable", "match_unavailable")
            probe_result = await _run_catalog_worker(
                probe, copy.deepcopy(frozen), credential_revisions=copy.deepcopy(revisions),
            )
            # The production adapter can notice that the catalog or a
            # Credential Manager revision changed while its worker was
            # authenticating.  Preserve that explicit stale receipt instead
            # of turning it into the generic 400 probe failure below.
            if _v4_adapter_stale(probe_result):
                return _v4_catalog_changed_retry()
            if not isinstance(probe_result, dict) or probe_result.get("ok") is not True:
                return _v4_probe_error(probe_result)

            # Phase 2 repeats both catalog and exact credential revision reads
            # before profile/SQLite mutation.  A password rotation, deletion,
            # or restoration during the probe can therefore never commit a
            # candidate authenticated with a stale secret.
            with _adapter_lock(adapter):
                catalog_store = store()
                try:
                    catalog_store.v4_migrate_legacy_links(_v4_profiles(adapter))
                    fresh_server, fresh_node, fresh_account, fresh_gateway, fresh_route = _v5_match_records(
                        catalog_store, frozen["server_id"], frozen["node"]["id"], frozen["account"]["id"],
                        frozen["route"].get("gateway_profile_id"),
                    )
                    fresh_ids = [str(fresh_account["id"])]
                    if fresh_gateway is not None:
                        fresh_ids.append(str(fresh_gateway["account_id"]))
                    fresh_revisions = _v5_credential_revisions(credential_provider, fresh_ids)
                    fresh_existing = catalog_store.v4_connection_for_pair(
                        frozen["server_id"], fresh_node["id"], fresh_account["id"],
                    )
                    fresh = _v5_frozen_match(
                        frozen["server_id"], fresh_server, fresh_node, fresh_account, fresh_route,
                        connection, fresh_gateway, fresh_existing, fresh_revisions,
                    )
                except CatalogError as exc:
                    if exc.code == "credential_missing_reconfigure":
                        return _v5_error(exc)
                    if _v4_snapshot_changed(exc) or exc.code in {"gateway_login_connection_required", "gateway_selection_required"}:
                        return _v4_catalog_changed_retry()
                    raise
                if fresh != frozen:
                    return _v4_catalog_changed_retry()
                persist = getattr(adapter, "persist_verified_candidate", None)
                enable = getattr(adapter, "set_remote_enabled", None)
                if not callable(persist) or not callable(enable):
                    raise CatalogError("connection persistence is unavailable", "profile_persist_failed")
                with _profile_transaction(adapter):
                    persisted = persist(copy.deepcopy(fresh))
                    if _v4_adapter_stale(persisted):
                        raise CatalogError(
                            "catalog data changed while connection verification was running; retry the request",
                            "catalog_changed_retry",
                        )
                    profile_id = fresh["profile_id"]
                    returned_id = _v4_profile_id(persisted) if isinstance(persisted, dict) else ""
                    if returned_id and returned_id != profile_id:
                        raise CatalogError("persisted connection id changed unexpectedly", "profile_persist_failed")
                    enable(True)
                    catalog_store.v4_upsert_connection(
                        fresh["server_id"], fresh_node["id"], fresh_account["id"], profile_id, fresh_route, connected=True,
                    )
                record = catalog_store.v4_get_connection_record(profile_id)
                saved_profile = adapter.get_profile(profile_id)
                if _v5_profile_auth_mode(saved_profile) != "password":
                    raise CatalogError("saved password connection provenance is incomplete", "profile_auth_provenance_invalid")
            return JSONResponse({
                "ok": True, "stage": "nodes_probe", "code": "ok",
                "connection": _v5_connection_view(record, saved_profile), "remote_enabled": True,
            }, status_code=201)
        except Exception as exc:
            return _v5_error(exc)

    @router.post("/api/cluster/catalog/connections/{profile_id}/test")
    async def test_connection(profile_id: str):
        try:
            with _adapter_lock(adapter):
                catalog_store = store()
                source_record = catalog_store.v4_get_connection_record(profile_id)
                source_profile = adapter.get_profile(profile_id)
                if not isinstance(source_profile, dict):
                    raise CatalogError("saved connection profile was not found", "profile_not_found")
                if _v5_profile_password_route(source_profile):
                    gateway = None
                    gateway_id = (source_record.get("route") or {}).get("gateway_profile_id")
                    if gateway_id:
                        gateway = catalog_store.v4_get_connection_record(gateway_id)
                    account_ids = [str(source_record["account_id"])]
                    if gateway is not None:
                        account_ids.append(str(gateway["account_id"]))
                    revisions = _v5_credential_revisions(credential_provider, account_ids)
                    frozen = _v5_frozen_test(profile_id, _v4_safe_profile(source_profile), revisions)
                    v5_route = True
                else:
                    # Historical key profiles remain readable/retestable for
                    # compatibility.  New V5 profiles never execute this path.
                    frozen = _v4_frozen_test(profile_id, _v4_safe_profile(source_profile))
                    revisions = None
                    v5_route = False
            operation = getattr(adapter, "probe_saved_connection", None)
            if not callable(operation):
                raise CatalogError("connection testing is unavailable", "test_unavailable")
            if v5_route:
                result = await _run_catalog_worker(operation, copy.deepcopy(frozen), credential_revisions=copy.deepcopy(revisions))
            else:
                result = await _run_catalog_worker(operation, copy.deepcopy(frozen))
            if not isinstance(result, dict) or result.get("ok") is not True:
                return _v4_probe_error(result)

            with _adapter_lock(adapter):
                catalog_store = store()
                try:
                    fresh_record = catalog_store.v4_get_connection_record(profile_id)
                except CatalogError as exc:
                    if _v4_snapshot_changed(exc):
                        return _v4_catalog_changed_retry()
                    raise
                fresh_profile = adapter.get_profile(profile_id)
                if not isinstance(fresh_profile, dict):
                    return _v4_catalog_changed_retry()
                if v5_route:
                    gateway = None
                    gateway_id = (fresh_record.get("route") or {}).get("gateway_profile_id")
                    if gateway_id:
                        gateway = catalog_store.v4_get_connection_record(gateway_id)
                    ids = [str(fresh_record["account_id"])]
                    if gateway is not None:
                        ids.append(str(gateway["account_id"]))
                    fresh_revisions = _v5_credential_revisions(credential_provider, ids)
                    fresh = _v5_frozen_test(profile_id, _v4_safe_profile(fresh_profile), fresh_revisions)
                else:
                    fresh = _v4_frozen_test(profile_id, _v4_safe_profile(fresh_profile))
                if fresh_record != source_record or fresh != frozen:
                    return _v4_catalog_changed_retry()
                confirm = getattr(adapter, "confirm_tested_connection", None)
                if not callable(confirm):
                    raise CatalogError("connection testing is unavailable", "test_unavailable")
                if v5_route:
                    confirmed = confirm(copy.deepcopy(fresh), credential_revisions=copy.deepcopy(fresh.get("credential_revisions") or {}))
                else:
                    confirmed = confirm(copy.deepcopy(fresh))
                if _v4_adapter_stale(confirmed):
                    return _v4_catalog_changed_retry()
                if not isinstance(confirmed, dict) or confirmed.get("ok") is not True:
                    return _v4_probe_error(confirmed)
                catalog_store.v4_touch_connection(profile_id)
                record = catalog_store.v4_get_connection_record(profile_id)
                saved_profile = adapter.get_profile(profile_id)
            return {
                "ok": True, "stage": "nodes_probe", "code": "ok",
                "connection": _v5_connection_view(record, saved_profile),
            }
        except Exception as exc:
            return _v5_error(exc)

    @router.delete("/api/cluster/catalog/connections/{profile_id}")
    async def delete_connection(profile_id: str):
        try:
            with _adapter_lock(adapter):
                catalog_store = store()
                plan = catalog_store.v4_connection_delete_plan(profile_id)
                with _profile_transaction(adapter):
                    # Deleting a connection is not deleting its account.  Keep
                    # the local credential for a later rematch/new node.
                    deleted_remote = _v4_delete_existing_profiles(adapter, list(plan["profile_ids"]))
                    result = catalog_store.v4_delete_connection_metadata(plan)
            return {
                "ok": True, "deleted": {"profile_id": profile_id},
                "deleted_profile_ids": result["deleted_profile_ids"], "deleted_remote_profile_ids": deleted_remote,
            }
        except Exception as exc:
            return _v5_error(exc)

    @router.delete("/api/cluster/catalog/profiles/{profile_id}")
    async def delete_unassigned_profile(profile_id: str):
        try:
            with _adapter_lock(adapter):
                catalog_store = store()
                try:
                    catalog_store.v4_get_connection_record(profile_id)
                except CatalogError as exc:
                    if exc.code != "connection_not_found":
                        raise
                else:
                    raise CatalogError("profile is a matched V5 connection; delete that connection instead", "profile_already_connected")
                with _profile_transaction(adapter):
                    deleted_remote = _v4_delete_existing_profiles(adapter, [profile_id])
                    deleted_metadata = catalog_store.v4_cleanup_deleted_profile(profile_id)
            return {
                "ok": True, "deleted": {"profile_id": profile_id},
                "deleted_profile_ids": deleted_metadata, "deleted_remote_profile_ids": deleted_remote,
            }
        except Exception as exc:
            return _v5_error(exc)

    @router.api_route("/api/cluster/catalog/nodes/{node_id}/adopt", methods=["POST"])
    @router.api_route("/api/cluster/catalog/nodes/{node_id}/accounts", methods=["POST"])
    @router.api_route("/api/cluster/catalog/nodes/{node_id}/accounts/{profile_id}", methods=["PATCH", "DELETE"])
    async def retired_v3_account_workflow(node_id: str, profile_id: str | None = None):
        _ = node_id, profile_id
        return _v5_error(CatalogError(
            "this V3 one-step account workflow was replaced by server accounts and match", "workflow_changed",
        ))

    return router


def build_router(
    adapter: Any, db_path_provider: Callable[[], str], credential_provider: Any | None = None,
) -> APIRouter:
    """Build fail-closed V5 by default; V4 exists only for explicit tests.

    A missing server injection must not turn a password/catalog installation
    back into a key-write API.  On Windows the default binds Credential Manager
    to the directory holding the catalog state database.  If construction
    cannot succeed, the V5 endpoints stay registered but report the controlled
    ``credential_store_unavailable`` error.  The only V4 route selection is
    the object-identity sentinel used by legacy offline fixtures.
    """
    if credential_provider is LEGACY_V4_TEST_COMPATIBILITY:
        return _build_v4_router(adapter, db_path_provider)
    if credential_provider is None:
        try:
            credential_provider = CredentialManagerStore(Path(db_path_provider()).parent)
        except Exception:
            credential_provider = _UnavailableV5CredentialProvider()
    if not _has_v5_credential_provider_contract(credential_provider):
        credential_provider = _UnavailableV5CredentialProvider()
    return _build_v5_router(adapter, db_path_provider, credential_provider)
