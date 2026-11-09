"""Offline V4 catalog coverage: staged match, migration, route safety, rollback.

All SSH operations are represented by ``V4Adapter``.  The tests never inspect
real key files, invoke SSH, or connect to a model/service.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
import sqlite3
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient

from memomics.cluster_catalog import ClusterCatalogStore
from cluster_catalog_api import LEGACY_V4_TEST_COMPATIBILITY, build_router


class V4Adapter:
    """In-memory implementation of the V4 server adapter contract."""

    _MATCH_FROZEN_KEYS = {
        "schema", "server_id", "server", "node", "account", "route", "connection",
        "gateway_connection", "existing_profile_id", "profile_id",
    }
    _TEST_FROZEN_KEYS = {"schema", "profile_id", "profile"}

    def __init__(self, profiles=None):
        self.lock = threading.RLock()
        self.profiles = {row["id"]: copy.deepcopy(row) for row in (profiles or [])}
        self.remote_enabled = False
        self.transaction_depth = 0
        self.match_result = {"ok": True, "stage": "nodes_probe", "code": "ok"}
        self.test_result = {"ok": True, "stage": "nodes_probe", "code": "ok"}
        self.probe_calls = []
        self.persisted_ids = []
        self.tested_ids = []
        self.fail_persist = False
        self._prepared_matches = {}
        self._prepared_tests = {}
        self.probe_started = None
        self.probe_release = None
        self.test_probe_started = None
        self.test_probe_release = None

    def list_profiles(self):
        return {"remote": {"enabled": self.remote_enabled}}, [copy.deepcopy(row) for row in self.profiles.values()], False

    def get_profile(self, profile_id):
        row = self.profiles.get(str(profile_id))
        return copy.deepcopy(row) if row else None

    @contextmanager
    def profile_transaction(self):
        profiles, enabled = copy.deepcopy(self.profiles), self.remote_enabled
        self.transaction_depth += 1
        try:
            yield
        except Exception:
            self.transaction_depth -= 1
            self.profiles, self.remote_enabled = profiles, enabled
            raise
        else:
            self.transaction_depth -= 1

    def _transaction_required(self):
        if not self.transaction_depth:
            raise RuntimeError("remote mutation outside profile transaction")

    def set_remote_enabled(self, value):
        self._transaction_required()
        self.remote_enabled = bool(value)

    def delete_profiles(self, profile_ids):
        self._transaction_required()
        for profile_id in profile_ids:
            self.profiles.pop(str(profile_id), None)
        return {"ok": True, "deleted_profile_ids": list(profile_ids)}

    def probe_verified_candidate(self, frozen, passwords=None):
        """Fake the worker-only Phase 1 adapter contract without secrets."""
        assert isinstance(frozen, dict) and set(frozen) == self._MATCH_FROZEN_KEYS
        assert frozen["schema"] == "v4-match-frozen-1"
        assert frozen["server"]["id"] == frozen["server_id"]
        assert all("password" not in str(key).lower() for key in frozen)
        server_id, node, account = frozen["server_id"], frozen["node"], frozen["account"]
        route, connection = frozen["route"], frozen["connection"]
        if self.probe_started is not None:
            self.probe_started.set()
            assert self.probe_release is not None and self.probe_release.wait(5)
        # Emulate the adapter's trusted rematch merge before probe.  Password
        # text never enters fake state or the opaque prepared candidate.
        candidate = copy.deepcopy(self.profiles.get(frozen.get("existing_profile_id")) or {})
        for field in ("name", "key_path", "workdir", "job_dir", "local_root", "remote_root", "timeout", "scheduler", "partition", "queue", "note"):
            if field in connection:
                candidate[field] = connection[field]
        for field in connection.get("clear_fields") or []:
            candidate[field] = ""
        self.probe_calls.append({
            "server_id": server_id, "node_id": node["id"], "account_id": account["id"],
            "profile_id": frozen["profile_id"],
            "route": copy.deepcopy(route),
            "existing_profile_id": frozen.get("existing_profile_id"),
            "candidate": candidate, "password_supplied": bool(
                isinstance(passwords, dict) and (
                    passwords.get("target_password") is not None or passwords.get("gateway_password") is not None
                )
            ),
        })
        result = copy.deepcopy(self.match_result)
        if result.get("ok") is True:
            self._prepared_matches[frozen["profile_id"]] = {
                "frozen": copy.deepcopy(frozen), "candidate": candidate,
            }
        return result

    def persist_verified_candidate(self, frozen):
        self._transaction_required()
        assert isinstance(frozen, dict) and set(frozen) == self._MATCH_FROZEN_KEYS
        assert frozen["schema"] == "v4-match-frozen-1"
        profile_id = frozen["profile_id"]
        self.persisted_ids.append(profile_id)
        if self.fail_persist:
            raise RuntimeError("simulated remote persistence failure")
        prepared = self._prepared_matches.get(profile_id)
        if not prepared or prepared["frozen"] != frozen:
            return {"ok": False, "code": "catalog_changed_retry"}
        node, account = frozen["node"], frozen["account"]
        base = copy.deepcopy(prepared["candidate"])
        base.update({
            "id": profile_id, "name": base.get("name") or account["name"], "user": account["user"],
            "host": node["host"], "port": node["port"], "configured": True,
            "has_key": bool(base.get("key_path")), "legacy": False,
            "proxy_jump": "trusted-derived" if frozen.get("gateway_connection") else "",
        })
        self.profiles[profile_id] = base
        self._prepared_matches.pop(profile_id, None)
        return copy.deepcopy(base)

    def probe_saved_connection(self, frozen):
        assert isinstance(frozen, dict) and set(frozen) == self._TEST_FROZEN_KEYS
        assert frozen["schema"] == "v4-test-frozen-1"
        profile_id = str(frozen["profile_id"])
        if profile_id not in self.profiles:
            return {"ok": False, "stage": "validate", "code": "profile_not_found"}
        if self.test_probe_started is not None:
            self.test_probe_started.set()
            assert self.test_probe_release is not None and self.test_probe_release.wait(5)
        result = copy.deepcopy(self.test_result)
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
        self.tested_ids.append(profile_id)
        return {"ok": True, "stage": "nodes_probe", "code": "ok"}


def make_client(tmp_path, profiles=None):
    adapter = V4Adapter(profiles)
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    app.include_router(build_router(adapter, lambda: str(tmp_path / "state.db"), LEGACY_V4_TEST_COMPATIBILITY))
    return TestClient(app), adapter, ClusterCatalogStore(tmp_path / "state.db")


def login_node(**extra):
    return {"name": "Login", "host": "login.example", "port": 22, "is_compute": False, **extra}


def compute_node(**extra):
    return {"name": "Compute", "host": "compute.example", "port": 22, "is_login": False, "is_compute": True, **extra}


def make_server(client, name="Cluster"):
    response = client.post("/api/cluster/catalog/servers", json={"name": name, "login_node": login_node()})
    assert response.status_code == 201, response.json()
    return response.json()


def make_account(client, server_id, name="Alice", user="alice"):
    response = client.post("/api/cluster/catalog/servers/%s/accounts" % server_id, json={"name": name, "user": user})
    assert response.status_code == 201, response.json()
    return response.json()["account"]


def match(client, server_id, node_id, account_id, *, route=None, connection=None, **extra):
    payload = {
        "node_id": node_id, "account_id": account_id, "route": route or {"mode": "direct"},
        "connection": {"name": "Match", "key_path": "C:/fake/key", **(connection or {})},
    }
    payload.update(extra)
    response = client.post("/api/cluster/catalog/servers/%s/connections/match" % server_id, json=payload)
    assert response.status_code == 201, response.json()
    assert response.json()["stage"] == "nodes_probe" and response.json()["code"] == "ok"
    return response.json()["connection"]


def test_v4_new_server_node_and_account_do_not_create_remote_profile(tmp_path):
    client, adapter, _store = make_client(tmp_path)
    with client:
        made = make_server(client)
        assert made["server"]["node_count"] == 1 and made["node"]["is_login"] is True
        added = client.post("/api/cluster/catalog/servers/%s/nodes" % made["server"]["id"], json=compute_node())
        assert added.status_code == 201
        account = make_account(client, made["server"]["id"])
        assert account["connection_count"] == 0 and adapter.profiles == {} and adapter.remote_enabled is False
        tree = client.get("/api/cluster/catalog").json()
        assert tree["schema_version"] == 2
        assert len(tree["servers"][0]["nodes"]) == 2 and len(tree["servers"][0]["accounts"]) == 1
        old = client.post("/api/cluster/catalog/servers", json={"name": "old", "node": login_node(), "account": {"name": "x", "user": "x"}})
        assert old.status_code == 409 and old.json()["code"] == "workflow_changed" and adapter.profiles == {}


def test_v4_legacy_migration_is_idempotent_keeps_profile_and_marks_proxy_review(tmp_path):
    store = ClusterCatalogStore(tmp_path / "state.db")
    sid, draft_id, nid, pid = "cluster-aaaaaaaaaaaa", "node-111111111111", "node-bbbbbbbbbbbb", "legacy-profile"
    conn = sqlite3.connect(tmp_path / "state.db")
    # Construct the pre-V4 database first.  The first V4 ensure_schema call
    # must promote its earliest concrete node exactly once.
    conn.execute("CREATE TABLE memomics_cluster_servers (id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
    conn.execute("""CREATE TABLE memomics_cluster_nodes (
        id TEXT PRIMARY KEY,server_id TEXT NOT NULL,name TEXT NOT NULL,host TEXT NOT NULL DEFAULT '',port INTEGER,
        scheduler TEXT NOT NULL DEFAULT '',partition_name TEXT NOT NULL DEFAULT '',queue_name TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT '',note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL
    )""")
    conn.execute("CREATE TABLE memomics_cluster_account_links (profile_id TEXT PRIMARY KEY,node_id TEXT NOT NULL,created_at TEXT NOT NULL)")
    conn.execute("INSERT INTO memomics_cluster_servers VALUES(?,?,?,?,?)", (sid, "legacy", "", "t", "t"))
    conn.execute(
        """INSERT INTO memomics_cluster_nodes(
          id,server_id,name,host,port,scheduler,partition_name,queue_name,role,note,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (draft_id, sid, "draft", "", None, "", "", "", "compute", "", "2026-01-01", "2026-01-01"),
    )
    conn.execute(
        """INSERT INTO memomics_cluster_nodes(
          id,server_id,name,host,port,scheduler,partition_name,queue_name,role,note,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (nid, sid, "old", "legacy.example", 22, "slurm", "", "", "compute", "", "2026-01-02", "2026-01-02"),
    )
    conn.execute("INSERT INTO memomics_cluster_account_links(profile_id,node_id,created_at) VALUES(?,?,?)", (pid, nid, "t"))
    conn.commit()
    conn.close()
    legacy = {"id": pid, "name": "Legacy user", "user": "legacy", "host": "legacy.example", "port": 22,
              "key_path": "C:/fake/legacy", "proxy_jump": "old-bastion", "configured": True, "has_key": True}
    before = copy.deepcopy(legacy)
    client, adapter, store = make_client(tmp_path, [legacy])
    with client:
        first = client.get("/api/cluster/catalog").json()
        server = first["servers"][0]
        nodes = {node["id"]: node for node in server["nodes"]}
        assert nodes[draft_id]["is_login"] is False and nodes[nid]["is_login"] is True  # earliest usable promotion
        connection = server["connections"][0]
        assert connection["profile_id"] == pid and connection["route"]["legacy_route_needs_review"] is True
        again = client.get("/api/cluster/catalog").json()
        assert len(again["servers"][0]["accounts"]) == len(again["servers"][0]["connections"]) == 1
        assert adapter.get_profile(pid) == before
        deleted = client.delete("/api/cluster/catalog/connections/%s" % pid)
        assert deleted.status_code == 200
        raw = sqlite3.connect(tmp_path / "state.db")
        assert raw.execute("SELECT COUNT(*) FROM memomics_cluster_account_links WHERE profile_id=?", (pid,)).fetchone()[0] == 0
        assert raw.execute("SELECT COUNT(*) FROM memomics_cluster_legacy_link_migrations WHERE profile_id=?", (pid,)).fetchone()[0] == 0
        raw.close()
        assert store.v4_list_connection_records() == [] and {node["id"] for node in store.v4_list_nodes()} == {draft_id, nid}


def test_v4_invalid_legacy_login_flag_is_not_a_usable_entry_or_retention_guard(tmp_path):
    primary_sid, empty_sid = "cluster-121212121212", "cluster-343434343434"
    invalid_id, usable_id, only_invalid_id = "node-565656565656", "node-787878787878", "node-909090909090"
    raw = sqlite3.connect(tmp_path / "state.db")
    raw.execute("CREATE TABLE memomics_cluster_servers (id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
    raw.execute("""CREATE TABLE memomics_cluster_nodes (
        id TEXT PRIMARY KEY,server_id TEXT NOT NULL,name TEXT NOT NULL,host TEXT NOT NULL DEFAULT '',port INTEGER,
        scheduler TEXT NOT NULL DEFAULT '',partition_name TEXT NOT NULL DEFAULT '',queue_name TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT '',note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL
    )""")
    raw.executemany("INSERT INTO memomics_cluster_servers VALUES(?,?,?,?,?)", [
        (primary_sid, "mixed legacy", "", "t", "t"),
        (empty_sid, "only invalid legacy", "", "t", "t"),
    ])
    raw.executemany(
        """INSERT INTO memomics_cluster_nodes(
          id,server_id,name,host,port,scheduler,partition_name,queue_name,role,note,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (invalid_id, primary_sid, "invalid login", "", None, "", "", "", "login", "", "2026-01-01", "2026-01-01"),
            (usable_id, primary_sid, "usable compute", "usable.example", 22, "", "", "", "compute", "", "2026-01-02", "2026-01-02"),
            (only_invalid_id, empty_sid, "only invalid", "   ", 22, "", "", "", "gateway", "", "2026-01-03", "2026-01-03"),
        ],
    )
    raw.commit()
    raw.close()
    client, _adapter, _store = make_client(tmp_path)
    with client:
        catalog = client.get("/api/cluster/catalog").json()
        servers = {server["id"]: server for server in catalog["servers"]}
        primary_nodes = {node["id"]: node for node in servers[primary_sid]["nodes"]}
        # Legacy role markers remain inspectable, but only a concrete endpoint
        # is counted as an operational login.  The earliest usable node is
        # therefore promoted even though the broken legacy flag is retained.
        assert primary_nodes[invalid_id]["is_login"] is True
        assert primary_nodes[usable_id]["is_login"] is True
        assert servers[primary_sid]["requires_login_setup"] is False
        assert servers[empty_sid]["requires_login_setup"] is True

        # A broken historical flag is not a required entry point and can be
        # removed without a replacement.  The actual sole usable login still
        # cannot be demoted or deleted merely because that broken flag existed.
        assert client.delete("/api/cluster/catalog/nodes/%s" % invalid_id).status_code == 200
        demote = client.patch("/api/cluster/catalog/nodes/%s" % usable_id, json={"is_login": False})
        assert demote.status_code == 409 and demote.json()["code"] == "last_login_node"
        deleted = client.delete("/api/cluster/catalog/nodes/%s" % usable_id)
        assert deleted.status_code == 409 and deleted.json()["code"] == "login_replacement_required"


def test_v4_failed_probe_persists_no_secret_or_local_profile(tmp_path):
    client, adapter, store = make_client(tmp_path)
    adapter.match_result = {"ok": False, "stage": "target_password", "code": "target_password_required"}
    with client:
        made = make_server(client)
        account = make_account(client, made["server"]["id"])
        secret = "NEVER_WRITE_ME"
        response = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account["id"], "route": {"mode": "direct"},
            "connection": {"name": "candidate", "key_path": "C:/fake/key"}, "target_password": secret,
        })
        assert response.status_code == 400
        assert response.json()["code"] == "target_password_required"
        assert response.json()["password_required"] == "target" and secret not in response.text
        assert adapter.profiles == {} and store.v4_list_connection_records() == [] and adapter.remote_enabled is False
        blob = b"".join(path.read_bytes() for path in tmp_path.rglob("*") if path.is_file())
        assert secret.encode() not in blob


def test_v4_failed_password_probe_retries_with_the_same_deterministic_profile_id(tmp_path):
    client, adapter, store = make_client(tmp_path)
    with client:
        made = make_server(client)
        account = make_account(client, made["server"]["id"])
        adapter.match_result = {"ok": False, "stage": "target_password", "code": "target_password_required"}
        first = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account["id"], "route": {"mode": "direct"},
            "connection": {"name": "retry", "key_path": "C:/fake/key"}, "target_password": "transient-token",
        })
        assert first.status_code == 400 and store.v4_list_connection_records() == []
        failed_profile_id = adapter.probe_calls[-1]["profile_id"]
        adapter.match_result = {"ok": True, "stage": "nodes_probe", "code": "ok"}
        retried = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account["id"], "route": {"mode": "direct"},
            "connection": {"name": "retry", "key_path": "C:/fake/key"},
        })
        assert retried.status_code == 201, retried.json()
        assert retried.json()["connection"]["profile_id"] == failed_profile_id


def test_v4_key_permissions_probe_failure_is_safe_and_does_not_expose_a_path(tmp_path):
    client, adapter, store = make_client(tmp_path)
    private_path = r"C:\Users\example\.memomics\generated_keys\id_ed25519"
    adapter.match_result = {
        "ok": False, "stage": "key_auth", "code": "key_permissions",
        "message": "refused insecure private key at %s" % private_path,
    }
    with client:
        made = make_server(client)
        account = make_account(client, made["server"]["id"])
        response = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account["id"], "route": {"mode": "direct"},
            "connection": {"name": "candidate"},
        })
        assert response.status_code == 400
        assert response.json() == {
            "ok": False, "error": "The app-generated SSH key has insecure file permissions.",
            "stage": "key_auth", "code": "key_permissions",
            "message": "The app-generated SSH key has insecure file permissions.",
        }
        assert private_path not in response.text
        assert adapter.profiles == {} and store.v4_list_connection_records() == [] and adapter.remote_enabled is False


def test_v4_catalog_defers_key_discovery_and_allows_only_explicit_safe_clears(tmp_path):
    client, adapter, _store = make_client(tmp_path)
    with client:
        made = make_server(client)
        account = make_account(client, made["server"]["id"])
        auto = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account["id"], "route": {"mode": "direct"},
            "connection": {"name": "use-helper-key-discovery"},
        })
        assert auto.status_code == 201, auto.json()
        profile_id = auto.json()["connection"]["profile_id"]
        assert adapter.probe_calls[-1]["password_supplied"] is False and adapter.profiles[profile_id]["has_key"] is False
        explicit = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account["id"], "route": {"mode": "direct"},
            "connection": {"name": "clear-safe", "clear_fields": ["key_path", "workdir", "timeout"]},
        })
        assert explicit.status_code == 201, explicit.json()
        assert adapter.probe_calls[-1]["candidate"]["key_path"] == ""
        forbidden = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account["id"], "route": {"mode": "direct"},
            "connection": {"clear_fields": ["host"]},
        })
        assert forbidden.status_code == 400 and forbidden.json()["code"] == "connection_invalid"


def test_v4_rematch_has_deterministic_profile_id_and_preserves_omitted_values(tmp_path):
    client, adapter, store = make_client(tmp_path)
    with client:
        made = make_server(client)
        account = make_account(client, made["server"]["id"])
        adapter.fail_persist = True
        first = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account["id"], "route": {"mode": "direct"},
            "connection": {"name": "first", "key_path": r"D:\offline\keys\id_ed25519", "workdir": "/original"},
        })
        assert first.status_code == 500 and adapter.profiles == {} and store.v4_list_connection_records() == []
        failed_id = adapter.persisted_ids[-1]
        adapter.fail_persist = False
        connected = match(client, made["server"]["id"], made["node"]["id"], account["id"], connection={"name": "first", "key_path": r"D:\offline\keys\id_ed25519", "workdir": "/original"})
        assert connected["profile_id"] == failed_id
        rematch_response = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account["id"], "route": {"mode": "direct"},
            "connection": {"name": "renamed"},
        })
        assert rematch_response.status_code == 201, rematch_response.json()
        rematched = rematch_response.json()["connection"]
        assert rematched["profile_id"] == connected["profile_id"]
        assert adapter.probe_calls[-1]["existing_profile_id"] == connected["profile_id"]
        candidate = adapter.probe_calls[-1]["candidate"]
        final = adapter.profiles[connected["profile_id"]]
        assert candidate["key_path"] == final["key_path"] == r"D:\offline\keys\id_ed25519"
        assert candidate["workdir"] == final["workdir"] == "/original"


def test_v4_gateway_dependency_and_delete_preserve_node_user_metadata(tmp_path):
    client, adapter, store = make_client(tmp_path)
    with client:
        made = make_server(client)
        gateway_user = make_account(client, made["server"]["id"], "Gateway", "gateway")
        gateway = match(client, made["server"]["id"], made["node"]["id"], gateway_user["id"])
        compute = client.post("/api/cluster/catalog/servers/%s/nodes" % made["server"]["id"], json=compute_node()).json()["node"]
        target_user = make_account(client, made["server"]["id"], "Target", "target")
        target = match(
            client, made["server"]["id"], compute["id"], target_user["id"],
            route={"mode": "via_login", "gateway_profile_id": gateway["profile_id"]},
        )
        deleted = client.delete("/api/cluster/catalog/connections/%s" % gateway["profile_id"])
        assert deleted.status_code == 200 and set(deleted.json()["deleted_profile_ids"]) == {gateway["profile_id"], target["profile_id"]}
        assert adapter.profiles == {} and store.v4_list_connection_records() == []
        tree = client.get("/api/cluster/catalog").json()["servers"][0]
        assert len(tree["nodes"]) == 2 and len(tree["accounts"]) == 2


def test_v4_connection_view_treats_bracketed_ipv6_as_the_same_endpoint(tmp_path):
    client, adapter, _store = make_client(tmp_path)
    with client:
        response = client.post("/api/cluster/catalog/servers", json={
            "name": "IPv6 cluster",
            "login_node": login_node(host="2001:db8:0:1::17"),
        })
        assert response.status_code == 201, response.json()
        made = response.json()
        account = make_account(client, made["server"]["id"])
        connected = match(client, made["server"]["id"], made["node"]["id"], account["id"])
        adapter.profiles[connected["profile_id"]]["host"] = "[2001:db8:0:1::17]"
        tree = client.get("/api/cluster/catalog").json()
        connection = tree["servers"][0]["connections"][0]
        assert connection["profile_id"] == connected["profile_id"]
        assert connection["endpoint_mismatch"] is False


def test_v4_worker_probe_keeps_health_and_mutation_live_then_rejects_stale_commit(tmp_path):
    client, adapter, store = make_client(tmp_path)
    with client:
        made = make_server(client)
        account = make_account(client, made["server"]["id"])
        adapter.probe_started, adapter.probe_release = threading.Event(), threading.Event()
        match_done, health_done, mutation_done = threading.Event(), threading.Event(), threading.Event()
        result, health, mutation = {}, {}, {}
        payload = {
            "node_id": made["node"]["id"], "account_id": account["id"], "route": {"mode": "direct"},
            "connection": {"name": "slow", "key_path": "C:/fake/key"},
        }

        def post_match():
            try:
                result["response"] = client.post(
                    "/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json=payload,
                )
            finally:
                match_done.set()

        def get_health():
            try:
                health["response"] = client.get("/health")
            finally:
                health_done.set()

        def mutate_account():
            try:
                mutation["response"] = client.patch(
                    "/api/cluster/catalog/accounts/%s" % account["id"], json={"user": "alice-mutated"},
                )
            finally:
                mutation_done.set()

        match_thread = threading.Thread(target=post_match, daemon=True)
        health_thread = threading.Thread(target=get_health, daemon=True)
        mutation_thread = threading.Thread(target=mutate_account, daemon=True)
        match_thread.start()
        try:
            assert adapter.probe_started.wait(2)
            health_thread.start()
            mutation_thread.start()
            # Both requests must be served while the worker is deliberately
            # hung.  The former implementation blocked this event loop/lock.
            assert health_done.wait(2)
            assert mutation_done.wait(2)
        finally:
            adapter.probe_release.set()
            match_thread.join(5)
            if health_thread.is_alive():
                health_thread.join(5)
            if mutation_thread.is_alive():
                mutation_thread.join(5)
        assert health["response"].status_code == 200 and health["response"].json() == {"ok": True}
        assert mutation["response"].status_code == 200, mutation["response"].json()
        assert match_done.is_set() and result["response"].status_code == 409, result.get("response")
        assert result["response"].json()["code"] == "catalog_changed_retry"
        assert adapter.profiles == {} and adapter.persisted_ids == [] and adapter.remote_enabled is False
        assert store.v4_list_connection_records() == []


def test_v4_worker_probe_rejects_concurrent_account_delete_without_persistence(tmp_path):
    client, adapter, store = make_client(tmp_path)
    with client:
        made = make_server(client)
        account = make_account(client, made["server"]["id"])
        adapter.probe_started, adapter.probe_release = threading.Event(), threading.Event()
        completed, result = threading.Event(), {}

        def match_in_background():
            try:
                result["response"] = client.post(
                    "/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"],
                    json={
                        "node_id": made["node"]["id"], "account_id": account["id"], "route": {"mode": "direct"},
                        "connection": {"name": "deleted during probe", "key_path": "C:/fake/key"},
                    },
                )
            finally:
                completed.set()

        thread = threading.Thread(target=match_in_background, daemon=True)
        thread.start()
        try:
            assert adapter.probe_started.wait(2)
            deleted = client.delete("/api/cluster/catalog/accounts/%s" % account["id"])
            assert deleted.status_code == 200, deleted.json()
        finally:
            adapter.probe_release.set()
            thread.join(5)
        assert completed.is_set() and result["response"].status_code == 409, result.get("response")
        assert result["response"].json()["code"] == "catalog_changed_retry"
        assert adapter.profiles == {} and adapter.persisted_ids == [] and adapter.remote_enabled is False
        assert store.v4_list_connection_records() == []


def test_v4_retest_drift_does_not_touch_connection_timestamp(tmp_path):
    client, adapter, store = make_client(tmp_path)
    with client:
        made = make_server(client)
        account = make_account(client, made["server"]["id"])
        connected = match(client, made["server"]["id"], made["node"]["id"], account["id"])
        before = store.v4_get_connection_record(connected["profile_id"])["last_connected_at"]
        adapter.test_probe_started, adapter.test_probe_release = threading.Event(), threading.Event()
        completed, result = threading.Event(), {}

        def retest():
            try:
                result["response"] = client.post("/api/cluster/catalog/connections/%s/test" % connected["profile_id"])
            finally:
                completed.set()

        thread = threading.Thread(target=retest, daemon=True)
        thread.start()
        try:
            assert adapter.test_probe_started.wait(2)
            changed = client.patch("/api/cluster/catalog/nodes/%s" % made["node"]["id"], json={"note": "changed during test"})
            assert changed.status_code == 200, changed.json()
        finally:
            adapter.test_probe_release.set()
            thread.join(5)
        assert completed.is_set() and result["response"].status_code == 409, result.get("response")
        assert result["response"].json()["code"] == "catalog_changed_retry"
        assert store.v4_get_connection_record(connected["profile_id"])["last_connected_at"] == before
        assert adapter.tested_ids == []


def test_v4_failed_sqlite_half_restores_remote_batch_and_rejects_draft_replacement(tmp_path, monkeypatch):
    client, adapter, store = make_client(tmp_path)
    with client:
        made = make_server(client)
        account = make_account(client, made["server"]["id"])
        connected = match(client, made["server"]["id"], made["node"]["id"], account["id"])
        draft_id = "node-dddddddddddd"
        raw = sqlite3.connect(tmp_path / "state.db")
        raw.execute(
            """INSERT INTO memomics_cluster_nodes(
              id,server_id,name,host,port,scheduler,partition_name,queue_name,role,note,is_login,is_compute,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (draft_id, made["server"]["id"], "Draft", "", None, "", "", "", "", "", 0, 1, "t", "t"),
        )
        raw.commit()
        raw.close()
        invalid = client.request("DELETE", "/api/cluster/catalog/nodes/%s" % made["node"]["id"], json={"replacement_node_id": draft_id})
        assert invalid.status_code == 409 and connected["profile_id"] in adapter.profiles
        replacement = client.post("/api/cluster/catalog/servers/%s/nodes" % made["server"]["id"], json=compute_node(name="Replacement", host="replacement.example")).json()["node"]
        monkeypatch.setattr(ClusterCatalogStore, "v4_delete_node_metadata", lambda *_args: (_ for _ in ()).throw(sqlite3.OperationalError("fail")))
        failed = client.request("DELETE", "/api/cluster/catalog/nodes/%s" % made["node"]["id"], json={"replacement_node_id": replacement["id"]})
        assert failed.status_code == 500 and connected["profile_id"] in adapter.profiles
        assert store.v4_get_node(made["node"]["id"])["id"] == made["node"]["id"]


def test_v4_empty_legacy_server_remains_visible_and_connection_test_only_touches_success(tmp_path):
    # Build a V3 source containing both an empty group and an all-draft group.
    # Neither may acquire a fabricated endpoint/login during V4 migration.
    empty_sid, draft_sid, draft_id = "cluster-cccccccccccc", "cluster-dddddddddddd", "node-eeeeeeeeeeee"
    raw = sqlite3.connect(tmp_path / "state.db")
    raw.execute("CREATE TABLE memomics_cluster_servers (id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
    raw.execute("""CREATE TABLE memomics_cluster_nodes (
        id TEXT PRIMARY KEY,server_id TEXT NOT NULL,name TEXT NOT NULL,host TEXT NOT NULL DEFAULT '',port INTEGER,
        scheduler TEXT NOT NULL DEFAULT '',partition_name TEXT NOT NULL DEFAULT '',queue_name TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT '',note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL
    )""")
    raw.execute("INSERT INTO memomics_cluster_servers VALUES(?,?,?,?,?)", (empty_sid, "empty", "", "t", "t"))
    raw.execute("INSERT INTO memomics_cluster_servers VALUES(?,?,?,?,?)", (draft_sid, "draft", "", "t", "t"))
    raw.execute(
        "INSERT INTO memomics_cluster_nodes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (draft_id, draft_sid, "draft", "", None, "", "", "", "compute", "", "t", "t"),
    )
    raw.commit()
    raw.close()
    client, adapter, store = make_client(tmp_path)
    with client:
        legacy_servers = {row["id"]: row for row in client.get("/api/cluster/catalog").json()["servers"]}
        assert legacy_servers[empty_sid]["node_count"] == 0 and legacy_servers[empty_sid]["requires_login_setup"] is True
        assert legacy_servers[draft_sid]["node_count"] == 1 and legacy_servers[draft_sid]["requires_login_setup"] is True
        assert legacy_servers[draft_sid]["nodes"][0]["id"] == draft_id and legacy_servers[draft_sid]["nodes"][0]["is_login"] is False
        made = make_server(client, "live")
        account = make_account(client, made["server"]["id"])
        connected = match(client, made["server"]["id"], made["node"]["id"], account["id"])
        before = store.v4_get_connection_record(connected["profile_id"])["last_connected_at"]
        adapter.test_result = {"ok": False, "stage": "key_auth", "code": "target_auth_failed"}
        failed = client.post("/api/cluster/catalog/connections/%s/test" % connected["profile_id"])
        assert failed.status_code == 400 and store.v4_get_connection_record(connected["profile_id"])["last_connected_at"] == before
        adapter.test_result = {"ok": True, "stage": "nodes_probe", "code": "ok"}
        passed = client.post("/api/cluster/catalog/connections/%s/test" % connected["profile_id"])
        assert passed.status_code == 200 and passed.json()["stage"] == "nodes_probe" and passed.json()["code"] == "ok"
        assert adapter.tested_ids[-1] == connected["profile_id"]
