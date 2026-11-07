"""Offline V5 password-account catalog regressions.

The suite injects an in-memory credential provider and adapter.  It never
opens SSH, calls Credential Manager, writes a password to SQLite/YAML, or uses
any real user credential.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient

from memomics.cluster_catalog import ClusterCatalogStore
from memomics.cluster_credentials import CredentialError, MemoryCredentialStore
import cluster_catalog_api as catalog_api
from cluster_catalog_api import build_router


class V5Adapter:
    """Small non-network adapter matching the V5 router receipt contract."""

    def __init__(self):
        self.lock = threading.RLock()
        self.profiles = {}
        self.remote_enabled = False
        self._transaction_depth = 0
        self._prepared = {}
        self._prepared_tests = {}
        self.convert_calls = []
        self.fail_delete = False
        self.probe_started = None
        self.probe_release = None
        self.test_started = None
        self.test_release = None
        self.saved_probe_calls = 0
        self.candidate_probe_calls = 0
        self.credential_store = None
        self.conversion_revision_hook = None
        self.conversion_revisions = []
        self.probe_result = None

    def list_profiles(self):
        return {"remote": {"enabled": self.remote_enabled}}, [copy.deepcopy(row) for row in self.profiles.values()], False

    def get_profile(self, profile_id):
        row = self.profiles.get(str(profile_id))
        return copy.deepcopy(row) if row else None

    @contextmanager
    def profile_transaction(self):
        before = copy.deepcopy(self.profiles), self.remote_enabled
        self._transaction_depth += 1
        try:
            yield
        except Exception:
            self.profiles, self.remote_enabled = before
            self._transaction_depth -= 1
            raise
        else:
            self._transaction_depth -= 1

    def _require_transaction(self):
        if not self._transaction_depth:
            raise RuntimeError("mutation must use profile_transaction")

    def set_remote_enabled(self, value):
        self._require_transaction()
        self.remote_enabled = bool(value)

    def delete_profiles(self, profile_ids):
        self._require_transaction()
        if self.fail_delete:
            raise RuntimeError("simulated remote deletion failure")
        for profile_id in profile_ids:
            self.profiles.pop(str(profile_id), None)
        return {"ok": True, "deleted": list(profile_ids)}

    @staticmethod
    def _fingerprint(frozen):
        return repr(frozen)

    def probe_verified_candidate(self, frozen, credential_revisions=None):
        self.candidate_probe_calls += 1
        assert frozen["schema"] == "v5-password-match-frozen-1"
        assert frozen["credential_revisions"] == credential_revisions
        assert all("password" not in str(key).lower() for key in frozen if key != "schema")
        if self.probe_started is not None:
            self.probe_started.set()
            assert self.probe_release is not None and self.probe_release.wait(5)
        if self.probe_result is not None:
            return copy.deepcopy(self.probe_result)
        self._prepared[self._fingerprint(frozen)] = copy.deepcopy(frozen)
        return {"ok": True, "stage": "nodes_probe", "code": "ok"}

    def persist_verified_candidate(self, frozen):
        self._require_transaction()
        if self._prepared.pop(self._fingerprint(frozen), None) is None:
            return {"ok": False, "code": "catalog_changed_retry"}
        node, account = frozen["node"], frozen["account"]
        gateway = frozen.get("gateway_connection") or {}
        profile = {
            "id": frozen["profile_id"], "profile_id": frozen["profile_id"],
            "name": frozen["connection"].get("name") or account["name"],
            "host": node["host"], "port": node["port"], "user": account["user"],
            "configured": True, "legacy": False,
            "auth_mode": "catalog_password_v5", "catalog_v5_ssh_route": "v5-password-route-1",
            "catalog_account_id": account["id"],
            "gateway_account_id": gateway.get("account_id") if gateway else "",
        }
        self.profiles[profile["id"]] = profile
        return copy.deepcopy(profile)

    def probe_saved_connection(self, frozen, credential_revisions=None):
        self.saved_probe_calls += 1
        if frozen["schema"] == "v5-password-test-frozen-1":
            assert frozen["credential_revisions"] == credential_revisions
        if self.test_started is not None:
            self.test_started.set()
            assert self.test_release is not None and self.test_release.wait(5)
        self._prepared_tests[self._fingerprint(frozen)] = copy.deepcopy(frozen)
        return {"ok": True, "stage": "nodes_probe", "code": "ok"}

    def confirm_tested_connection(self, frozen, credential_revisions=None):
        if frozen["schema"] == "v5-password-test-frozen-1":
            assert frozen["credential_revisions"] == credential_revisions
        if self._prepared_tests.pop(self._fingerprint(frozen), None) is None:
            return {"ok": False, "code": "catalog_changed_retry"}
        return {"ok": True, "stage": "nodes_probe", "code": "ok"}

    def convert_catalog_account_to_v5(self, account_after, connection_records):
        self._require_transaction()
        self.convert_calls.append({"account": copy.deepcopy(account_after), "records": copy.deepcopy(connection_records)})
        if self.credential_store is not None:
            account_ids = []
            for record in connection_records:
                account_ids.append(str(record.get("account_id") or ""))
                gateway = record.get("gateway_connection")
                if isinstance(gateway, dict):
                    account_ids.append(str(gateway.get("account_id") or ""))
            revisions = {}
            for account_id in dict.fromkeys(value for value in account_ids if value):
                credential = self.credential_store.get(account_id)
                assert credential is not None
                revisions[account_id] = credential.revision
            self.conversion_revisions.append(revisions)
            if self.conversion_revision_hook is not None:
                self.conversion_revision_hook()
            for account_id, revision in revisions.items():
                credential = self.credential_store.get(account_id)
                if credential is None or credential.revision != revision:
                    raise RuntimeError("simulated local credential revision race")
        for record in connection_records:
            profile_id = str(record["profile_id"])
            profile = self.profiles.get(profile_id)
            if not profile:
                raise RuntimeError("missing test profile")
            profile.update({
                "auth_mode": "catalog_password_v5", "catalog_v5_ssh_route": "v5-password-route-1",
            })
            if str(record.get("account_id")) == str(account_after["id"]):
                profile["user"] = account_after["user"]
        return {"ok": True, "converted_profile_ids": [row["profile_id"] for row in connection_records]}


class AmbiguousPutStore(MemoryCredentialStore):
    """Test a native write that succeeds but reports an error afterward."""

    def __init__(self):
        super().__init__()
        self.fail_after_write = True

    def put(self, account_id, password):
        record = super().put(account_id, password)
        if self.fail_after_write:
            raise CredentialError("credential_store_unavailable")
        return record


def make_client(tmp_path, credentials=None):
    adapter = V5Adapter()
    credentials = credentials or MemoryCredentialStore()
    adapter.credential_store = credentials
    app = FastAPI()
    app.include_router(build_router(adapter, lambda: str(tmp_path / "state.db"), credentials))
    return TestClient(app), adapter, credentials, ClusterCatalogStore(tmp_path / "state.db")


def create_server(client, name="Cluster"):
    response = client.post("/api/cluster/catalog/servers", json={
        "name": name,
        "login_node": {"name": "Login", "host": "login.example", "port": 22, "is_login": True, "is_compute": False},
    })
    assert response.status_code == 201, response.text
    return response.json()


def create_account(client, server_id, *, name="Alice", user="alice", password="local-test-password"):
    response = client.post("/api/cluster/catalog/servers/%s/accounts" % server_id, json={
        "name": name, "user": user, "password": password,
    })
    assert response.status_code == 201, response.text
    return response.json()["account"]


def match(client, server_id, node_id, account_id, **extra):
    payload = {"node_id": node_id, "account_id": account_id, "connection": {"name": "Catalog match"}}
    payload.update(extra)
    response = client.post("/api/cluster/catalog/servers/%s/connections/match" % server_id, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["connection"]


def test_v5_omitted_or_partial_provider_never_selects_legacy_router(tmp_path, monkeypatch):
    constructed = []
    injected = MemoryCredentialStore()

    def fake_default_provider(home):
        constructed.append(str(home))
        return injected

    monkeypatch.setattr(catalog_api, "CredentialManagerStore", fake_default_provider)
    app = FastAPI()
    app.include_router(build_router(V5Adapter(), lambda: str(tmp_path / "default" / "state.db")))
    with TestClient(app) as client:
        made = create_server(client)
        # V4 would accept this legacy no-password account write.  Strict V5
        # reaches password validation before attempting any credential write.
        missing = client.post("/api/cluster/catalog/servers/%s/accounts" % made["server"]["id"], json={
            "name": "No password", "user": "none",
        })
        assert missing.status_code == 400 and missing.json()["code"] == "credential_password_required"
    assert constructed == [str((tmp_path / "default").resolve())]

    class PartialProvider:
        pass

    app = FastAPI()
    app.include_router(build_router(V5Adapter(), lambda: str(tmp_path / "partial" / "state.db"), PartialProvider()))
    with TestClient(app) as client:
        made = create_server(client)
        failed = client.post("/api/cluster/catalog/servers/%s/accounts" % made["server"]["id"], json={
            "name": "Cannot store", "user": "none", "password": "fixture-password",
        })
        assert failed.status_code == 400 and failed.json()["code"] == "credential_store_unavailable"
    # The fail-closed replacement rejects before allocating a metadata row;
    # a missing provider must not leave an account that cannot be used.
    assert ClusterCatalogStore(tmp_path / "partial" / "state.db").v4_list_accounts(made["server"]["id"]) == []


def test_v5_login_only_server_and_password_catalog_view_never_expose_secret_or_key(tmp_path):
    client, _adapter, _credentials, _store = make_client(tmp_path)
    with client:
        made = create_server(client)
        assert made["server"]["node_count"] == 1
        assert made["node"]["is_login"] is True and made["node"]["is_compute"] is False
        account = create_account(client, made["server"]["id"])
        connection = match(client, made["server"]["id"], made["node"]["id"], account["id"])
        assert connection["auth_mode"] == "password" and "has_key" not in connection
        catalog = client.get("/api/cluster/catalog")
        assert catalog.status_code == 200
        body = catalog.json()
        rendered = catalog.text
        assert "local-test-password" not in rendered and "key_path" not in rendered
        saved = body["servers"][0]
        assert saved["accounts"][0]["credential_state"] == "configured"
        assert saved["connections"][0]["auth_mode"] == "password"
        assert "has_key" not in saved["connections"][0]


def test_v5_create_account_requires_password_and_ambiguous_write_cleans_secret_before_metadata(tmp_path):
    client, _adapter, _credentials, store = make_client(tmp_path)
    with client:
        made = create_server(client)
        missing = client.post("/api/cluster/catalog/servers/%s/accounts" % made["server"]["id"], json={"name": "No password", "user": "none"})
        assert missing.status_code == 400 and missing.json()["code"] == "credential_password_required"

    ambiguous = AmbiguousPutStore()
    client, _adapter, _credentials, store = make_client(tmp_path / "ambiguous", ambiguous)
    with client:
        made = create_server(client)
        failed = client.post("/api/cluster/catalog/servers/%s/accounts" % made["server"]["id"], json={
            "name": "Fails", "user": "fails", "password": "test-write-then-fail",
        })
        assert failed.status_code == 400
        assert failed.json()["code"] == "credential_store_unavailable"
        assert store.v4_list_accounts(made["server"]["id"]) == []
        assert ambiguous._records == {}
        assert "test-write-then-fail" not in failed.text


def test_v5_connected_account_password_only_patch_converts_legacy_and_user_is_locked(tmp_path):
    client, adapter, credentials, _store = make_client(tmp_path)
    with client:
        made = create_server(client)
        account = create_account(client, made["server"]["id"])
        connection = match(client, made["server"]["id"], made["node"]["id"], account["id"])
        # Represent a retained V4 profile that has no local password yet.
        profile = adapter.profiles[connection["profile_id"]]
        profile.pop("auth_mode")
        profile.pop("catalog_v5_ssh_route")
        profile["key_path"] = "legacy-key-not-in-http"
        credentials.delete(account["id"])
        before_probes = (adapter.candidate_probe_calls, adapter.saved_probe_calls)

        # Match the real edit dialog: it always includes the unchanged user
        # and display name with an optional new local password.
        changed = client.patch("/api/cluster/catalog/accounts/%s" % account["id"], json={
            "name": account["name"], "user": account["user"], "password": "replacement-password",
        })
        assert changed.status_code == 200, changed.text
        assert changed.json()["account"]["credential_state"] == "configured"
        assert changed.json()["account"]["user"] == account["user"]
        assert len(adapter.convert_calls) == 1
        assert adapter.profiles[connection["profile_id"]]["auth_mode"] == "catalog_password_v5"
        assert adapter.conversion_revisions[-1] == {account["id"]: 1}
        # Password saving is a local credential/profile conversion.  It does
        # not wait for or silently issue a remote probe; fresh auth happens on
        # the next explicit match/test instead.
        assert (adapter.candidate_probe_calls, adapter.saved_probe_calls) == before_probes
        assert "replacement-password" not in changed.text

        blocked = client.patch("/api/cluster/catalog/accounts/%s" % account["id"], json={"user": "different-user"})
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "account_has_connections_user_locked"


def test_v5_connected_password_patch_is_offline_and_compensates_revision_races(tmp_path):
    """A local password save never probes SSH and leaves no stale profile pair."""
    client, adapter, credentials, store = make_client(tmp_path)
    with client:
        made = create_server(client)
        account = create_account(client, made["server"]["id"], password="original-local-password")
        connection = match(client, made["server"]["id"], made["node"]["id"], account["id"])
        original_profile = copy.deepcopy(adapter.profiles[connection["profile_id"]])
        original_account = copy.deepcopy(store.v4_get_account(account["id"]))
        original_credential = credentials.get(account["id"])
        assert original_credential is not None
        before_probes = (adapter.candidate_probe_calls, adapter.saved_probe_calls)

        # The adapter snapshots the local revision, then observes a local
        # rotation before persistence.  It raises before profile/SQLite write;
        # the API must restore the old secret as a *new* revision so in-flight
        # match/test receipts cannot accept it as unchanged.
        adapter.conversion_revision_hook = lambda: credentials.put(account["id"], "raced-local-password")
        response = client.patch("/api/cluster/catalog/accounts/%s" % account["id"], json={
            "name": "Should roll back", "password": "requested-local-password",
        })
        assert response.status_code >= 500
        assert "requested-local-password" not in response.text
        assert "raced-local-password" not in response.text
        assert (adapter.candidate_probe_calls, adapter.saved_probe_calls) == before_probes
        assert adapter.profiles[connection["profile_id"]] == original_profile
        assert store.v4_get_account(account["id"]) == original_account
        restored = credentials.get(account["id"])
        assert restored is not None
        assert restored.password == original_credential.password
        assert restored.revision > original_credential.revision
        assert adapter.conversion_revisions[-1][account["id"]] > original_credential.revision


def test_v5_match_rejects_key_password_and_client_route_inputs(tmp_path):
    client, _adapter, _credentials, _store = make_client(tmp_path)
    with client:
        made = create_server(client)
        account = create_account(client, made["server"]["id"])
        base = {"node_id": made["node"]["id"], "account_id": account["id"], "connection": {"name": "x"}}
        for payload in (
            {**base, "route": {"mode": "direct"}},
            {**base, "target_password": "not-accepted"},
            {**base, "connection": {"name": "x", "key_path": "C:/not-accepted"}},
        ):
            response = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json=payload)
            assert response.status_code == 400 and response.json()["code"] == "connection_invalid"
            assert "not-accepted" not in response.text


def test_v5_compute_match_auto_selects_unique_gateway_and_requires_choice_when_ambiguous(tmp_path):
    client, _adapter, _credentials, _store = make_client(tmp_path)
    with client:
        made = create_server(client)
        sid, login = made["server"]["id"], made["node"]
        first = create_account(client, sid, name="First", user="first", password="first-test-password")
        first_gateway = match(client, sid, login["id"], first["id"])
        compute_response = client.post("/api/cluster/catalog/servers/%s/nodes" % sid, json={
            "name": "Compute", "host": "compute.example", "port": 22,
        })
        assert compute_response.status_code == 201, compute_response.text
        compute = compute_response.json()["node"]
        assert compute["is_login"] is False and compute["is_compute"] is True

        target = create_account(client, sid, name="Target", user="target", password="target-test-password")
        auto = match(client, sid, compute["id"], target["id"])
        assert auto["route"]["mode"] == "via_login"
        assert auto["route"]["gateway_profile_id"] == first_gateway["profile_id"]

        second = create_account(client, sid, name="Second", user="second", password="second-test-password")
        second_gateway = match(client, sid, login["id"], second["id"])
        third = create_account(client, sid, name="Third", user="third", password="third-test-password")
        ambiguous = client.post("/api/cluster/catalog/servers/%s/connections/match" % sid, json={
            "node_id": compute["id"], "account_id": third["id"], "connection": {"name": "ambiguous"},
        })
        assert ambiguous.status_code == 409 and ambiguous.json()["code"] == "gateway_selection_required"
        candidates = ambiguous.json()["candidates"]
        assert {item["profile_id"] for item in candidates} == {first_gateway["profile_id"], second_gateway["profile_id"]}
        selected = match(client, sid, compute["id"], third["id"], gateway_profile_id=second_gateway["profile_id"])
        assert selected["route"]["gateway_profile_id"] == second_gateway["profile_id"]


def test_v5_match_rejects_credential_revision_change_during_probe(tmp_path):
    client, adapter, credentials, _store = make_client(tmp_path)
    with client:
        made = create_server(client)
        account = create_account(client, made["server"]["id"])
        adapter.probe_started, adapter.probe_release = threading.Event(), threading.Event()
        holder = {}

        def run_match():
            holder["response"] = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
                "node_id": made["node"]["id"], "account_id": account["id"], "connection": {"name": "race"},
            })

        worker = threading.Thread(target=run_match)
        worker.start()
        assert adapter.probe_started.wait(5)
        credentials.put(account["id"], "rotated-test-password")
        adapter.probe_release.set()
        worker.join(5)
        response = holder["response"]
        assert response.status_code == 409 and response.json()["code"] == "catalog_changed_retry"
        assert adapter.profiles == {}


def test_v5_match_preserves_adapter_stale_probe_receipt_as_retry(tmp_path):
    """A native revision check may fail before Phase 2; it is still a retry."""
    client, adapter, _credentials, _store = make_client(tmp_path)
    with client:
        made = create_server(client)
        account = create_account(client, made["server"]["id"])
        adapter.probe_result = {
            "ok": False,
            "stage": "validate",
            "code": "catalog_changed_retry",
            "message": "catalog changed while worker was running",
        }
        response = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
            "node_id": made["node"]["id"], "account_id": account["id"],
            "connection": {"name": "stale-adapter-receipt"},
        })
        assert response.status_code == 409 and response.json()["code"] == "catalog_changed_retry"
        assert adapter.profiles == {}


def test_v5_account_and_server_delete_restore_credentials_when_remote_delete_fails(tmp_path):
    client, adapter, credentials, _store = make_client(tmp_path)
    with client:
        made = create_server(client)
        account = create_account(client, made["server"]["id"])
        match(client, made["server"]["id"], made["node"]["id"], account["id"])
        adapter.fail_delete = True
        account_failure = client.delete("/api/cluster/catalog/accounts/%s" % account["id"])
        assert account_failure.status_code == 500
        assert credentials.state(account["id"]) == "configured"

    client, adapter, credentials, _store = make_client(tmp_path / "server", MemoryCredentialStore())
    with client:
        made = create_server(client)
        account = create_account(client, made["server"]["id"])
        match(client, made["server"]["id"], made["node"]["id"], account["id"])
        adapter.fail_delete = True
        server_failure = client.delete("/api/cluster/catalog/servers/%s" % made["server"]["id"])
        assert server_failure.status_code == 500
        assert credentials.state(account["id"]) == "configured"


def test_v5_patch_omitted_or_blank_password_preserves_exact_credential(tmp_path):
    client, _adapter, credentials, _store = make_client(tmp_path)
    with client:
        made = create_server(client)
        account = create_account(client, made["server"]["id"])
        before = credentials.get(account["id"])
        assert before is not None
        metadata_only = client.patch("/api/cluster/catalog/accounts/%s" % account["id"], json={"name": "Renamed"})
        assert metadata_only.status_code == 200, metadata_only.text
        after_metadata = credentials.get(account["id"])
        assert after_metadata is not None
        assert after_metadata.revision == before.revision and after_metadata.password == before.password
        blank = client.patch("/api/cluster/catalog/accounts/%s" % account["id"], json={"note": "note", "password": ""})
        assert blank.status_code == 200, blank.text
        after_blank = credentials.get(account["id"])
        assert after_blank is not None
        assert after_blank.revision == before.revision and after_blank.password == before.password


def test_v5_successful_account_and_server_deletes_remove_only_their_credentials(tmp_path):
    client, _adapter, credentials, store = make_client(tmp_path)
    with client:
        made = create_server(client)
        account = create_account(client, made["server"]["id"])
        match(client, made["server"]["id"], made["node"]["id"], account["id"])
        deleted = client.delete("/api/cluster/catalog/accounts/%s" % account["id"])
        assert deleted.status_code == 200, deleted.text
        assert credentials.state(account["id"]) == "missing"
        assert all(row["id"] != account["id"] for row in store.v4_list_accounts(made["server"]["id"]))

    client, _adapter, credentials, store = make_client(tmp_path / "server-success", MemoryCredentialStore())
    with client:
        made = create_server(client)
        first = create_account(client, made["server"]["id"], name="First", user="first", password="first-delete-password")
        second = create_account(client, made["server"]["id"], name="Second", user="second", password="second-delete-password")
        match(client, made["server"]["id"], made["node"]["id"], first["id"])
        deleted = client.delete("/api/cluster/catalog/servers/%s" % made["server"]["id"])
        assert deleted.status_code == 200, deleted.text
        assert credentials.state(first["id"]) == credentials.state(second["id"]) == "missing"
        assert store.v4_list_accounts() == []


def _gateway_setup(client):
    made = create_server(client)
    sid, login = made["server"]["id"], made["node"]
    gateway_account = create_account(client, sid, name="Gateway", user="gateway", password="gateway-test-password")
    gateway = match(client, sid, login["id"], gateway_account["id"])
    compute = client.post("/api/cluster/catalog/servers/%s/nodes" % sid, json={
        "name": "Compute", "host": "compute.example", "port": 22,
    }).json()["node"]
    target_account = create_account(client, sid, name="Target", user="target", password="target-test-password")
    return made, gateway_account, gateway, compute, target_account


def test_v5_gateway_credential_revision_change_rejects_match_commit(tmp_path):
    client, adapter, credentials, _store = make_client(tmp_path)
    with client:
        made, gateway_account, _gateway, compute, target_account = _gateway_setup(client)
        adapter.probe_started, adapter.probe_release = threading.Event(), threading.Event()
        holder = {}

        def run_match():
            holder["response"] = client.post("/api/cluster/catalog/servers/%s/connections/match" % made["server"]["id"], json={
                "node_id": compute["id"], "account_id": target_account["id"], "connection": {"name": "gateway-race"},
            })

        worker = threading.Thread(target=run_match)
        worker.start()
        assert adapter.probe_started.wait(5)
        credentials.put(gateway_account["id"], "gateway-rotated-password")
        adapter.probe_release.set()
        worker.join(5)
        response = holder["response"]
        assert response.status_code == 409 and response.json()["code"] == "catalog_changed_retry"
        assert len(adapter.profiles) == 1  # only the already verified login gateway


def test_v5_saved_test_rejects_target_and_gateway_credential_rotations(tmp_path):
    client, adapter, credentials, store = make_client(tmp_path)
    with client:
        made, gateway_account, _gateway, compute, target_account = _gateway_setup(client)
        connection = match(client, made["server"]["id"], compute["id"], target_account["id"])
        before = store.v4_get_connection_record(connection["profile_id"])["last_connected_at"]

        for account_id, replacement in ((target_account["id"], "target-rotated-password"),
                                        (gateway_account["id"], "gateway-rotated-password")):
            adapter.test_started, adapter.test_release = threading.Event(), threading.Event()
            holder = {}

            def run_test():
                holder["response"] = client.post("/api/cluster/catalog/connections/%s/test" % connection["profile_id"])

            worker = threading.Thread(target=run_test)
            worker.start()
            assert adapter.test_started.wait(5)
            credentials.put(account_id, replacement)
            adapter.test_release.set()
            worker.join(5)
            response = holder["response"]
            assert response.status_code == 409 and response.json()["code"] == "catalog_changed_retry"
            assert store.v4_get_connection_record(connection["profile_id"])["last_connected_at"] == before


def test_v5_partial_profile_provenance_fails_closed_and_get_has_no_sensitive_fields(tmp_path):
    client, adapter, _credentials, _store = make_client(tmp_path)
    with client:
        made = create_server(client)
        account = create_account(client, made["server"]["id"])
        connection = match(client, made["server"]["id"], made["node"]["id"], account["id"])
        profile = adapter.profiles[connection["profile_id"]]
        profile.pop("auth_mode")  # marker without auth_mode must not become legacy
        profile["catalog_v5_ssh_route"] = "v5-password-route-1"
        before_calls = adapter.saved_probe_calls
        failed_test = client.post("/api/cluster/catalog/connections/%s/test" % connection["profile_id"])
        assert failed_test.status_code == 500 and failed_test.json()["code"] == "profile_auth_provenance_invalid"
        assert adapter.saved_probe_calls == before_calls
        failed_get = client.get("/api/cluster/catalog")
        assert failed_get.status_code == 500 and failed_get.json()["code"] == "profile_auth_provenance_invalid"

    client, _adapter, _credentials, _store = make_client(tmp_path / "safe-get", MemoryCredentialStore())
    with client:
        made = create_server(client)
        account = create_account(client, made["server"]["id"], password="recursive-sensitive-test-password")
        match(client, made["server"]["id"], made["node"]["id"], account["id"])
        response = client.get("/api/cluster/catalog")
        assert response.status_code == 200
        forbidden = {
            "password", "target_password", "gateway_password", "key_path", "has_key", "revision",
            "credential_revisions", "catalog_v5_target_alias", "catalog_v5_gateway_alias",
        }

        def assert_public(value):
            if isinstance(value, dict):
                assert not (set(value) & forbidden), value.keys()
                for child in value.values():
                    assert_public(child)
            elif isinstance(value, list):
                for child in value:
                    assert_public(child)

        assert_public(response.json())
        assert "recursive-sensitive-test-password" not in response.text
