"""Offline catalog regression coverage updated for V4 staged ownership and rollback."""

from __future__ import annotations

from contextlib import contextmanager
import concurrent.futures
import copy
import json
import sqlite3
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from memomics.cluster_catalog import ClusterCatalogStore
from cluster_catalog_api import LEGACY_V4_TEST_COMPATIBILITY, build_router


class RecoveryRequired(RuntimeError):
    catalog_recovery_required = True

    def __init__(self):
        super().__init__("rollback failed: key_path=C:/fake-secret-key")
        self.backup_id = "fake-recovery-01"


class FakeAdapter:
    """In-memory adapter with the same reversible boundary as server.py."""

    _MATCH_FROZEN_KEYS = {
        "schema", "server_id", "server", "node", "account", "route", "connection",
        "gateway_connection", "existing_profile_id", "profile_id",
    }
    _TEST_FROZEN_KEYS = {"schema", "profile_id", "profile"}

    def __init__(self, profiles=None):
        self.lock = threading.RLock()
        self.profiles = {row["id"]: dict(row) for row in (profiles or [])}
        self.remote_enabled = False
        self.next_id = 1
        self.deleted = []
        self.bound_error = None
        self.activity_error = None
        self.list_error = None
        self.restore_failure = False
        self.transaction_depth = 0
        self.probe_result = {"ok": True, "stage": "nodes_probe", "code": "ok"}
        self.test_result = {"ok": True, "stage": "nodes_probe", "code": "ok"}
        self.probe_calls = []
        self.persisted_ids = []
        self._prepared_matches = {}
        self._prepared_tests = {}

    def list_profiles(self):
        if self.list_error:
            raise self.list_error
        # Match the production adapter: catalog readers receive a sanitized
        # summary flag rather than the raw SSH option list or key path.
        rows = []
        for saved in self.profiles.values():
            row = dict(saved)
            row["has_extra_ssh_options"] = bool(row.get("extra_ssh_options"))
            row.pop("extra_ssh_options", None)
            row.pop("key_path", None)
            rows.append(row)
        return {"remote": {"enabled": self.remote_enabled}}, rows, False

    def get_profile(self, profile_id):
        row = self.profiles.get(str(profile_id))
        return dict(row) if row else None

    @contextmanager
    def profile_transaction(self):
        before_profiles, before_enabled = copy.deepcopy(self.profiles), self.remote_enabled
        self.transaction_depth += 1
        try:
            yield
        except Exception:
            self.transaction_depth -= 1
            if self.restore_failure:
                raise RecoveryRequired() from None
            self.profiles, self.remote_enabled = before_profiles, before_enabled
            raise
        else:
            self.transaction_depth -= 1

    def _in_transaction(self):
        if not self.transaction_depth:
            raise RuntimeError("profile write outside transaction")

    def set_remote_enabled(self, enabled):
        self._in_transaction()
        self.remote_enabled = bool(enabled)

    def create_profile(self, payload):
        self._in_transaction()
        profile_id = "profile-new-%s" % self.next_id
        self.next_id += 1
        row = {
            "id": profile_id, "name": str(payload["name"]), "user": str(payload["user"]),
            "host": str(payload["host"]), "port": int(payload.get("port") or 22),
            "scheduler": str(payload.get("scheduler") or "auto"),
            "partition": str(payload.get("partition") or ""), "queue": str(payload.get("queue") or ""),
            "workdir": str(payload.get("workdir") or ""), "job_dir": str(payload.get("job_dir") or ""),
            "local_root": str(payload.get("local_root") or ""), "remote_root": str(payload.get("remote_root") or ""),
            "timeout": payload.get("timeout"), "proxy_jump": str(payload.get("proxy_jump") or ""),
            "extra_ssh_options": list(payload.get("extra_ssh_options") or []),
            "key_path": str(payload.get("key_path") or ""), "has_key": bool(payload.get("key_path")),
            "configured": True, "legacy": False,
        }
        self.profiles[profile_id] = row
        return dict(row)

    def update_profile(self, profile_id, payload):
        self._in_transaction()
        row = self.profiles.get(str(profile_id))
        if not row:
            return None
        row.update(copy.deepcopy(payload))
        row["has_key"] = bool(row.get("key_path"))
        return dict(row)

    def delete_profiles(self, profile_ids):
        self._in_transaction()
        for profile_id in profile_ids:
            self.deleted.append(str(profile_id))
            self.profiles.pop(str(profile_id), None)
        return {"ok": True, "deleted_profile_ids": list(profile_ids)}

    def probe_verified_candidate(self, frozen, passwords=None):
        """Phase 1: validate a frozen request without mutating saved profiles."""
        assert isinstance(frozen, dict) and set(frozen) == self._MATCH_FROZEN_KEYS
        assert frozen["schema"] == "v4-match-frozen-1"
        assert frozen["server"]["id"] == frozen["server_id"]
        assert all("password" not in str(key).lower() for key in frozen)
        server_id, node_data, account_data = frozen["server_id"], frozen["node"], frozen["account"]
        route, connection = frozen["route"], frozen["connection"]
        candidate = copy.deepcopy(self.profiles.get(frozen.get("existing_profile_id")) or {})
        for field in ("name", "key_path", "workdir", "job_dir", "local_root", "remote_root", "timeout", "scheduler", "partition", "queue", "note"):
            if field in connection:
                candidate[field] = connection[field]
        for field in connection.get("clear_fields") or []:
            candidate[field] = ""
        self.probe_calls.append({
            "server_id": server_id, "node_id": node_data["id"], "account_id": account_data["id"],
            "profile_id": frozen["profile_id"], "route": copy.deepcopy(route),
            "existing_profile_id": frozen.get("existing_profile_id"), "candidate": candidate,
            "password_supplied": bool(isinstance(passwords, dict) and (
                passwords.get("target_password") is not None or passwords.get("gateway_password") is not None
            )),
        })
        result = copy.deepcopy(self.probe_result)
        if result.get("ok") is True:
            self._prepared_matches[frozen["profile_id"]] = {
                "frozen": copy.deepcopy(frozen), "candidate": candidate,
            }
        return result

    def persist_verified_candidate(self, frozen):
        """Phase 2: consume only an exact successful Phase-1 receipt."""
        self._in_transaction()
        assert isinstance(frozen, dict) and set(frozen) == self._MATCH_FROZEN_KEYS
        assert frozen["schema"] == "v4-match-frozen-1"
        profile_id = frozen["profile_id"]
        self.persisted_ids.append(profile_id)
        prepared = self._prepared_matches.get(profile_id)
        if not prepared or prepared["frozen"] != frozen:
            return {"ok": False, "code": "catalog_changed_retry"}
        node_data, account_data = frozen["node"], frozen["account"]
        prior = copy.deepcopy(prepared["candidate"])
        prior.update({
            "id": profile_id, "name": prior.get("name") or account_data["name"], "user": account_data["user"],
            "host": node_data["host"], "port": node_data["port"], "configured": True,
            "has_key": bool(prior.get("key_path")), "legacy": False,
            "proxy_jump": "trusted-derived" if frozen.get("gateway_connection") else "",
        })
        self.profiles[profile_id] = prior
        self._prepared_matches.pop(profile_id, None)
        return dict(prior)

    def test_connection(self, _profile_id):
        return copy.deepcopy(self.test_result)

    def probe_saved_connection(self, frozen):
        assert isinstance(frozen, dict) and set(frozen) == self._TEST_FROZEN_KEYS
        assert frozen["schema"] == "v4-test-frozen-1"
        profile_id = str(frozen["profile_id"])
        if profile_id not in self.profiles:
            return {"ok": False, "stage": "validate", "code": "profile_not_found"}
        result = self.test_connection(profile_id)
        if result.get("ok") is True:
            self._prepared_tests[profile_id] = copy.deepcopy(frozen)
        return result

    def confirm_tested_connection(self, frozen):
        assert isinstance(frozen, dict) and set(frozen) == self._TEST_FROZEN_KEYS
        assert frozen["schema"] == "v4-test-frozen-1"
        profile_id = str(frozen["profile_id"])
        if self._prepared_tests.get(profile_id) != frozen:
            return {"ok": False, "code": "catalog_changed_retry"}
        self._prepared_tests.pop(profile_id, None)
        return {"ok": True, "stage": "nodes_probe", "code": "ok"}

    def bound_session_ids(self, profile_id):
        if self.bound_error:
            raise self.bound_error
        return []

    def is_profile_running(self, profile_id):
        if self.activity_error:
            raise self.activity_error
        return False


def profile(profile_id, *, host="login.example", port=22, user="alice", **extra):
    return {"id": profile_id, "name": extra.pop("name", profile_id), "host": host, "port": port,
            "user": user, "workdir": extra.pop("workdir", "/work/" + user),
            "scheduler": extra.pop("scheduler", "slurm"), "has_key": extra.pop("has_key", True),
            "configured": extra.pop("configured", True), "legacy": extra.pop("legacy", False), **extra}


def make_client(tmp_path, profiles=None):
    adapter = FakeAdapter(profiles)
    app = FastAPI()
    app.include_router(build_router(adapter, lambda: str(tmp_path / "state.db"), LEGACY_V4_TEST_COMPATIBILITY))
    return TestClient(app), adapter, ClusterCatalogStore(tmp_path / "state.db")


def account(name="Alice", user="alice", **extra):
    return {"name": name, "user": user, "key_path": "C:/keys/%s" % user,
            "workdir": "/home/%s/project" % user, "job_dir": "/home/%s/jobs" % user,
            "local_root": "D:/data/%s" % user, "remote_root": "/remote/%s" % user,
            "timeout": 480, "proxy_jump": "gate.example",
            "extra_ssh_options": ["-o", "ServerAliveInterval=30"], **extra}


def node(name="login", host="login.example", **extra):
    return {"name": name, "host": host, "port": 2202, "scheduler": "slurm", "partition": "cpu",
            "queue": "", "role": "login", "note": "offline QA", **extra}


def create_server(client, name="Genome cluster", *, node_data=None, account_data=None):
    response = client.post("/api/cluster/catalog/servers", json={
        "name": name, "description": "offline QA", "node": node_data or node(), "account": account_data or account(),
    })
    assert response.status_code == 201, response.json()
    return response.json()


def create_node(client, server_id, *, node_data=None, account_data=None):
    response = client.post("/api/cluster/catalog/servers/%s/nodes" % server_id, json={
        "node": node_data or node("compute", "compute.example"),
        "account": account_data or account("Bob", "bob"),
    })
    assert response.status_code == 201, response.json()
    return response.json()


def v4_login_node(**extra):
    return {"name": "Login", "host": "login.example", "port": 22, "is_compute": False, **extra}


def v4_compute_node(**extra):
    return {"name": "Compute", "host": "compute.example", "port": 22, "is_login": False, "is_compute": True, **extra}


def v4_server(client, name="Genome cluster"):
    response = client.post("/api/cluster/catalog/servers", json={"name": name, "description": "offline QA", "login_node": v4_login_node()})
    assert response.status_code == 201, response.json()
    return response.json()


def v4_account(client, server_id, name="Alice", user="alice"):
    response = client.post("/api/cluster/catalog/servers/%s/accounts" % server_id, json={"name": name, "user": user, "note": "offline QA"})
    assert response.status_code == 201, response.json()
    return response.json()["account"]


def v4_match(client, server_id, node_id, account_id, *, route=None, connection=None):
    response = client.post("/api/cluster/catalog/servers/%s/connections/match" % server_id, json={
        "node_id": node_id, "account_id": account_id, "route": route or {"mode": "direct"},
        "connection": {"name": "matched", "key_path": "C:/fake/key", **(connection or {})},
    })
    assert response.status_code == 201, response.json()
    assert response.json()["stage"] == "nodes_probe" and response.json()["code"] == "ok"
    return response.json()["connection"]


def test_schema_is_additive_and_never_persists_secret_columns(tmp_path):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE memomics_projects (id TEXT PRIMARY KEY, cwd TEXT)")
    conn.commit()
    conn.close()
    store = ClusterCatalogStore(db)
    store.ensure_schema()
    conn = sqlite3.connect(db)
    assert "memomics_projects" in {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in ("memomics_cluster_servers", "memomics_cluster_nodes", "memomics_cluster_account_links"):
        columns = {row[1].lower() for row in conn.execute("PRAGMA table_info(%s)" % table)}
        assert not columns.intersection({"key", "key_path", "password", "private_key", "api_key", "token", "user"})
    conn.close()


def test_complete_server_creates_login_node_without_profile_or_remote_enable(tmp_path):
    client, adapter, _store = make_client(tmp_path)
    with client:
        made = v4_server(client)
        assert adapter.profiles == {} and adapter.remote_enabled is False
        assert made["server"]["node_count"] == 1 and made["node"]["is_login"] is True
        catalog = client.get("/api/cluster/catalog").json()
        server = catalog["servers"][0]
        assert server["accounts"] == [] and server["connections"] == [] and server["requires_login_setup"] is False


def test_complete_node_and_multiple_accounts_are_distinct_until_match(tmp_path):
    client, adapter, _store = make_client(tmp_path)
    with client:
        root = v4_server(client)
        response = client.post("/api/cluster/catalog/servers/%s/nodes" % root["server"]["id"], json=v4_compute_node())
        assert response.status_code == 201, response.json()
        node_id = response.json()["node"]["id"]
        bob = v4_account(client, root["server"]["id"], "Bob", "bob")
        carol = v4_account(client, root["server"]["id"], "Carol", "carol")
        assert bob["id"] != carol["id"] and adapter.profiles == {}
        catalog = client.get("/api/cluster/catalog").json()["servers"][0]
        assert {row["id"] for row in catalog["accounts"]} == {bob["id"], carol["id"]}
        assert next(row for row in catalog["nodes"] if row["id"] == node_id)["connection_count"] == 0


@pytest.mark.parametrize("login_node", [
    {"name": "Login", "host": "login.example", "port": 70000, "is_compute": False},
    {"name": "Login", "host": "login.example", "port": "ssh", "is_compute": False},
    {"name": "Login", "host": "login.example", "port": True, "is_compute": False},
    {"name": "Login", "host": "login.example", "port": 22},
])
def test_incomplete_or_secret_create_rejects_without_residue(tmp_path, login_node):
    client, adapter, store = make_client(tmp_path)
    with client:
        response = client.post("/api/cluster/catalog/servers", json={"name": "bad", "login_node": login_node})
        assert response.status_code == 400, response.json()
        old_flow = client.post("/api/cluster/catalog/servers", json={"name": "old", "node": node(), "account": account()})
        assert old_flow.status_code == 409 and old_flow.json()["code"] == "workflow_changed"
        assert adapter.profiles == {} and store.v4_list_servers() == []
        assert "C:/keys/alice" not in old_flow.text


def test_account_node_and_server_force_delete_cascade_matched_profiles(tmp_path):
    client, adapter, store = make_client(tmp_path)
    with client:
        first = v4_server(client)
        sid, login_id = first["server"]["id"], first["node"]["id"]
        first_account = v4_account(client, sid, "A1", "a1")
        first_connection = v4_match(client, sid, login_id, first_account["id"])
        second_account = v4_account(client, sid, "A2", "a2")
        second_connection = v4_match(client, sid, login_id, second_account["id"])
        assert client.delete("/api/cluster/catalog/accounts/%s" % second_account["id"]).status_code == 200
        assert adapter.get_profile(second_connection["profile_id"]) is None
        replacement = client.post("/api/cluster/catalog/servers/%s/nodes" % sid, json=v4_compute_node(name="Replacement", host="replacement.example")).json()["node"]
        deleted = client.request("DELETE", "/api/cluster/catalog/nodes/%s" % login_id, json={"replacement_node_id": replacement["id"]})
        assert deleted.status_code == 200 and adapter.get_profile(first_connection["profile_id"]) is None
        assert store.v4_get_account(first_account["id"])["id"] == first_account["id"]
        second = v4_server(client, "Second")
        second_account = v4_account(client, second["server"]["id"], "B1", "b1")
        second_connection = v4_match(client, second["server"]["id"], second["node"]["id"], second_account["id"])
        response = client.delete("/api/cluster/catalog/servers/%s" % second["server"]["id"])
        assert response.status_code == 200 and adapter.get_profile(second_connection["profile_id"]) is None


def test_legacy_unassigned_can_be_force_deleted_but_not_adopted_through_v3_route(tmp_path):
    client, adapter, _store = make_client(tmp_path, [profile("legacy-profile", host="legacy.example", port=2202, user="old", legacy=True)])
    with client:
        made = v4_server(client)
        retired = client.post("/api/cluster/catalog/nodes/%s/adopt" % made["node"]["id"], json={"profile_id": "legacy-profile"})
        assert retired.status_code == 409 and retired.json()["code"] == "workflow_changed"
        deleted = client.delete("/api/cluster/catalog/profiles/legacy-profile")
        assert deleted.status_code == 200 and adapter.get_profile("legacy-profile") is None


def test_sql_failures_roll_back_created_or_deleted_profile_state(tmp_path, monkeypatch):
    client, adapter, store = make_client(tmp_path)
    with client:
        made = v4_server(client)
        account_row = v4_account(client, made["server"]["id"])
        monkeypatch.setattr(ClusterCatalogStore, "v4_upsert_connection", lambda *_a, **_k: (_ for _ in ()).throw(sqlite3.OperationalError("write failure")))
        bad = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account_row["id"], "route": {"mode": "direct"},
            "connection": {"name": "rollback", "key_path": "C:/fake/key"},
        })
        assert bad.status_code == 500 and adapter.profiles == {} and adapter.remote_enabled is False and store.v4_list_connection_records() == []
        monkeypatch.undo()
        connection = v4_match(client, made["server"]["id"], made["node"]["id"], account_row["id"])
        replacement = client.post("/api/cluster/catalog/servers/%s/nodes" % made["server"]["id"], json=v4_compute_node(name="Replacement", host="replacement.example")).json()["node"]
        monkeypatch.setattr(ClusterCatalogStore, "v4_delete_node_metadata", lambda *_a, **_k: (_ for _ in ()).throw(sqlite3.OperationalError("delete fail")))
        failed = client.request("DELETE", "/api/cluster/catalog/nodes/%s" % made["node"]["id"], json={"replacement_node_id": replacement["id"]})
        assert failed.status_code == 500 and adapter.get_profile(connection["profile_id"]) is not None


def test_restore_failure_is_generic_and_returns_only_recovery_id(tmp_path, monkeypatch):
    client, adapter, _store = make_client(tmp_path)
    with client:
        made = v4_server(client)
        account_row = v4_account(client, made["server"]["id"])
        adapter.restore_failure = True
        monkeypatch.setattr(ClusterCatalogStore, "v4_upsert_connection", lambda *_a, **_k: (_ for _ in ()).throw(sqlite3.OperationalError("fail")))
        response = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account_row["id"], "route": {"mode": "direct"},
            "connection": {"name": "recovery", "key_path": "C:/fake/key"},
        })
        assert response.status_code == 500 and response.json()["code"] == "profile_recovery_required"
        assert response.json()["backup_id"] == "fake-recovery-01"
        assert "fake-secret" not in response.text and "key_path" not in response.text


def test_catalog_read_ignores_legacy_binding_and_activity_errors(tmp_path):
    client, adapter, _store = make_client(tmp_path, [profile("legacy-safe", key_path="C:/fake-secret-key", proxy_jump="hidden-gateway", legacy=True)])
    with client:
        made = v4_server(client)
        adapter.bound_error = RuntimeError("key_path=C:/fake-secret-key")
        adapter.activity_error = RuntimeError("ProxyCommand=secret")
        response = client.get("/api/cluster/catalog")
        assert response.status_code == 200
        assert response.json()["schema_version"] == 2 and response.json()["servers"][0]["id"] == made["server"]["id"]
        assert "fake-secret" not in response.text and "ProxyCommand" not in response.text and "hidden-gateway" not in response.text


def test_account_patch_keeps_node_endpoint_and_rejects_password(tmp_path):
    client, adapter, _store = make_client(tmp_path)
    with client:
        made = v4_server(client)
        node_id = made["node"]["id"]
        account_row = v4_account(client, made["server"]["id"])
        connection = v4_match(client, made["server"]["id"], node_id, account_row["id"], connection={"workdir": "/new/work", "timeout": 600})
        renamed = client.patch("/api/cluster/catalog/accounts/%s" % account_row["id"], json={"name": "Renamed"})
        assert renamed.status_code == 200, renamed.json()
        locked_user = client.patch("/api/cluster/catalog/accounts/%s" % account_row["id"], json={"user": "other"})
        assert locked_user.status_code == 409 and locked_user.json()["code"] == "account_has_connections_user_locked"
        locked_node = client.patch("/api/cluster/catalog/nodes/%s" % node_id, json={"host": "other.example"})
        assert locked_node.status_code == 409 and locked_node.json()["code"] == "node_has_connections_connection_locked"
        forbidden = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": node_id, "account_id": account_row["id"], "route": {"mode": "direct"},
            "connection": {"name": "bad", "password": "do-not-save"},
        })
        assert forbidden.status_code == 400 and "do-not-save" not in forbidden.text
        assert adapter.get_profile(connection["profile_id"])["workdir"] == "/new/work"


def test_store_serializes_parallel_metadata_writes(tmp_path):
    store = ClusterCatalogStore(tmp_path / "state.db")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(
            lambda i: store.v4_create_server(
                "server-%03d" % i, "", v4_login_node(name="login-%03d" % i, host="login-%03d.example" % i),
            )[0]["id"],
            range(24),
        ))
    assert len(set(ids)) == 24 and len(store.v4_list_servers()) == 24
