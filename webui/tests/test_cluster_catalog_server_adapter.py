"""Offline server-adapter regressions for V4/V5 cluster catalog adapters.

The tests use only a temporary config.yaml and SQLite catalog.  They never
open SSH, read private-key contents, or invoke a model.
"""

from __future__ import annotations

import asyncio
import copy
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import yaml

from memomics.bio_tools import remote_cluster as rc
from memomics.cluster_credentials import MemoryCredentialStore
import server


def _read(path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _write(path, value):
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


@pytest.fixture()
def adapter_home(monkeypatch, tmp_path):
    """Point the real server adapter at an isolated YAML/state directory."""
    config_path = tmp_path / "config.yaml"
    _write(config_path, {
        "model": {"provider": "kept-before-and-after-rollback"},
        "remote": {"enabled": False, "nodes": {}},
    })
    monkeypatch.setattr(server, "MEMOMICS_HOME_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_cluster_mod", lambda: rc)
    monkeypatch.setattr(rc, "_get_config_path", lambda: config_path)
    monkeypatch.setattr(rc, "_CFG_CACHE", {"mtime": None, "cfg": None})
    return config_path


def _profile_payload(name="alice", *, host="login.example", port=2201):
    return {
        "name": name,
        "host": host,
        "port": port,
        "user": name,
        "key_path": "C:/keys/%s" % name,
        "workdir": "/home/%s/work" % name,
        "job_dir": "/home/%s/jobs" % name,
        "local_root": "D:/data/%s" % name,
        "remote_root": "/scratch/%s" % name,
        "timeout": 45,
        "proxy_jump": "jump.example",
        "extra_ssh_options": ["-o", "ServerAliveInterval=30"],
        "scheduler": "slurm",
        "partition": "gpu",
        "queue": "batch",
    }


def _v5_match_frozen(*, server_id="catalog-v5-server", profile_id="catalog-v5-profile",
                     account_id="account-000000000001", revision=1, user="alice"):
    """Exact public V5 adapter input; intentionally contains no password."""
    return {
        "schema": "v5-password-match-frozen-1",
        "server_id": server_id,
        "server": {"id": server_id, "name": "V5 fixture"},
        "node": {
            "id": "node-v5-login", "server_id": server_id, "name": "Login",
            "host": "login.example", "port": 2222, "is_login": True,
            "is_compute": False, "scheduler": "slurm", "partition": "", "queue": "",
        },
        "account": {
            "id": account_id, "server_id": server_id, "name": "Alice", "user": user, "note": "",
        },
        "route": {"mode": "direct"},
        "connection": {"name": "Alice at login"},
        "gateway_connection": None,
        "existing_profile_id": None,
        "profile_id": profile_id,
        "credential_revisions": {account_id: revision},
    }


def _patch_v5_route_primitives(monkeypatch, candidate):
    """Keep adapter tests offline while exercising real receipt/YAML code."""
    target_alias = "memomics-v5-target-" + ("0" * 32)
    monkeypatch.setattr(rc, "_catalog_v5_candidate", lambda value: copy.deepcopy(value))
    monkeypatch.setattr(rc, "catalog_v5_ssh_policy_options", lambda _value: ["-F", "C:/fixture/v5-route.conf"])
    monkeypatch.setattr(rc, "_catalog_v5_aliases", lambda _value: (target_alias, ""))
    monkeypatch.setattr(rc, "catalog_v5_candidate_from_profile", lambda _profile: copy.deepcopy(candidate))


def test_catalog_http_v4_match_is_the_only_profile_creation_path(adapter_home, monkeypatch):
    """V4 creates metadata first and writes remote.nodes only after match."""
    # Production `server.app` is intentionally V5/password-only.  Exercise
    # the retained V4 compatibility router explicitly so this regression does
    # not create a Windows Credential Manager entry for a fixture account.
    try:
        from webui.cluster_catalog_api import build_router, LEGACY_V4_TEST_COMPATIBILITY
    except ImportError:
        from cluster_catalog_api import build_router, LEGACY_V4_TEST_COMPATIBILITY
    app = FastAPI()
    app.include_router(build_router(
        server._ClusterCatalogAdapter(), lambda: str(adapter_home.parent / "state.db"),
        credential_provider=LEGACY_V4_TEST_COMPATIBILITY,
    ))
    client = TestClient(app)

    # The removed V3 bundle endpoint must not leave a hidden YAML profile.
    legacy = client.post("/api/cluster/catalog/servers", json={
        "name": "old", "node": {"name": "login", "host": "old.example", "port": 22},
        "account": {"name": "alice", "user": "alice"},
    })
    assert legacy.status_code == 409 and legacy.json()["code"] == "workflow_changed"
    assert _read(adapter_home)["remote"]["nodes"] == {}

    created = client.post("/api/cluster/catalog/servers", json={
        "name": "Compute", "description": "shared compute cluster",
        "login_node": {
            "name": "login", "host": "login.example", "port": 2201,
            "scheduler": "slurm", "partition": "gpu", "queue": "batch",
            "is_login": True, "is_compute": True,
        },
    })
    assert created.status_code == 201, created.text
    server_id = created.json()["server"]["id"]
    node = created.json()["node"]

    account_response = client.post("/api/cluster/catalog/servers/%s/accounts" % server_id, json={
        "name": "alice", "user": "alice", "note": "login user",
    })
    assert account_response.status_code == 201, account_response.text
    account = account_response.json()["account"]
    # Metadata setup contains no executable YAML profile yet.
    assert _read(adapter_home)["remote"]["nodes"] == {}

    observed = {"match": [], "persist": [], "test": [], "confirm": [], "probe": [], "nodes": []}
    adapter_type = server._ClusterCatalogAdapter
    original_probe = adapter_type.probe_verified_candidate
    original_persist = adapter_type.persist_verified_candidate
    original_test = adapter_type.probe_saved_connection
    original_confirm = adapter_type.confirm_tested_connection
    match_keys = {
        "schema", "server_id", "server", "node", "account", "route", "connection",
        "gateway_connection", "existing_profile_id", "profile_id",
    }

    def checked_probe(self, frozen, passwords=None):
        assert set(frozen) == match_keys and frozen["schema"] == "v4-match-frozen-1"
        assert frozen["server"]["id"] == frozen["server_id"]
        observed["match"].append(dict(frozen))
        return original_probe(self, frozen, passwords)

    def checked_persist(self, frozen):
        assert set(frozen) == match_keys and frozen["schema"] == "v4-match-frozen-1"
        observed["persist"].append(dict(frozen))
        return original_persist(self, frozen)

    def checked_test(self, frozen):
        assert set(frozen) == {"schema", "profile_id", "profile"}
        assert frozen["schema"] == "v4-test-frozen-1"
        observed["test"].append(dict(frozen))
        return original_test(self, frozen)

    def checked_confirm(self, frozen):
        assert set(frozen) == {"schema", "profile_id", "profile"}
        assert frozen["schema"] == "v4-test-frozen-1"
        observed["confirm"].append(dict(frozen))
        return original_confirm(self, frozen)

    def fake_prepare(candidate, *, target_password=None, require_public_key=False):
        # This is the lowest identity-resolution boundary.  The real adapter
        # still freezes, fingerprints, receipts, persists, and retests it.
        prepared = dict(candidate)
        prepared["key"] = "C:/app-managed/id_ed25519"
        observed["prepared"] = dict(prepared)
        return prepared, None

    def fake_probe(candidate, *, target_password=None, gateway_password=None):
        observed["probe"].append((dict(candidate), target_password, gateway_password))
        return {"ok": True, "stage": "nodes_probe", "code": "ok", "message": "fake BatchMode passed"}

    def fake_policy(candidate):
        assert candidate["key"] == "C:/app-managed/id_ed25519"
        return ["-F", "C:/app-managed/catalog-route.conf"]

    def fake_nodes(payload):
        observed["nodes"].append(dict(payload))
        assert payload == {"action": "nodes", "node": profile_id}
        return '{"nodes": [{"reachable": true, "name": "fake"}]}'

    monkeypatch.setattr(adapter_type, "probe_verified_candidate", checked_probe)
    monkeypatch.setattr(adapter_type, "persist_verified_candidate", checked_persist)
    monkeypatch.setattr(adapter_type, "probe_saved_connection", checked_test)
    monkeypatch.setattr(adapter_type, "confirm_tested_connection", checked_confirm)
    monkeypatch.setattr(rc, "prepare_catalog_connection", fake_prepare)
    monkeypatch.setattr(rc, "probe_connection", fake_probe)
    monkeypatch.setattr(rc, "catalog_ssh_policy_options", fake_policy)
    matched = client.post("/api/cluster/catalog/servers/%s/connections/match" % server_id, json={
        "node_id": node["id"], "account_id": account["id"], "route": {"mode": "direct"},
        "connection": {
            "name": "alice@login", "key_path": "C:/keys/alice", "workdir": "/home/alice/work",
            "job_dir": "/home/alice/jobs", "local_root": "D:/data/alice", "remote_root": "/scratch/alice",
            "timeout": 45, "scheduler": "slurm", "partition": "gpu", "queue": "batch",
        },
    })
    assert matched.status_code == 201, (matched.text, observed)
    profile_id = matched.json()["connection"]["profile_id"]
    assert matched.json()["remote_enabled"] is True
    assert len(observed["match"]) == len(observed["persist"]) == 1
    assert observed["match"][0]["server_id"] == server_id
    assert observed["match"][0]["route"] == {"mode": "direct"}
    assert observed["probe"][0][0]["host"] == "login.example"
    assert "password" not in matched.text and "C:/keys/alice" not in matched.text

    raw = _read(adapter_home)
    saved = raw["remote"]["nodes"][profile_id]
    assert raw["remote"]["enabled"] is True
    for field in ("host", "user", "port", "key", "workdir", "job_dir", "local_root", "remote_root", "timeout"):
        assert field in saved
    assert saved["host"] == "login.example" and saved["user"] == "alice"
    assert saved["extra_ssh_options"] == ["-F", "C:/app-managed/catalog-route.conf"]

    # Retests are the original-nodes adapter operation; catalog updates its
    # timestamp only after this operation returns `ok`.
    monkeypatch.setattr(rc, "remote_cluster_handler", fake_nodes)
    tested = client.post("/api/cluster/catalog/connections/%s/test" % profile_id)
    assert tested.status_code == 200, tested.text
    assert tested.json()["connection"]["last_connected_at"]
    assert observed["nodes"] == [{"action": "nodes", "node": profile_id}]
    assert len(observed["test"]) == len(observed["confirm"]) == 1


def test_adapter_profile_transaction_rolls_back_only_remote_and_preserves_other_root_changes(adapter_home):
    adapter = server._ClusterCatalogAdapter()
    with pytest.raises(RuntimeError, match="sqlite failure after YAML write"):
        with adapter.profile_transaction():
            adapter.create_profile(_profile_payload("rollback"))
            # Model/provider writes are outside the remote section and must
            # survive a catalog transaction rollback.
            changed = _read(adapter_home)
            changed["model"] = {"provider": "written-during-transaction"}
            _write(adapter_home, changed)
            raise RuntimeError("sqlite failure after YAML write")

    restored = _read(adapter_home)
    assert restored["remote"] == {"enabled": False, "nodes": {}}
    assert restored["model"] == {"provider": "written-during-transaction"}
    assert not list(adapter_home.parent.glob(".cluster-catalog-remote-*.recovery.json"))


def test_adapter_profile_transaction_keeps_journal_and_raises_safe_recovery_error(adapter_home, monkeypatch):
    adapter = server._ClusterCatalogAdapter()
    fake_key_path = "C:/private/never-return-this.pem"
    monkeypatch.setattr(
        server,
        "_restore_cluster_remote_section",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(fake_key_path)),
    )

    with pytest.raises(server.ClusterCatalogRecoveryRequired) as caught:
        with adapter.profile_transaction():
            payload = _profile_payload("restore-failure")
            payload["key_path"] = fake_key_path
            adapter.create_profile(payload)
            raise RuntimeError("catalog store failed")

    error = caught.value
    assert error.catalog_recovery_required is True
    assert error.backup_id
    assert fake_key_path not in str(error)
    journals = list(adapter_home.parent.glob(".cluster-catalog-remote-*.recovery.json"))
    assert len(journals) == 1
    assert error.backup_id in journals[0].name


def test_batch_delete_is_local_only_and_legacy_default_cannot_reappear(adapter_home, monkeypatch):
    adapter = server._ClusterCatalogAdapter()
    with adapter.profile_transaction():
        first = adapter.create_profile(_profile_payload("first"))
        second = adapter.create_profile(_profile_payload("second", host="cpu.example", port=2222))

    invalidated = []
    monkeypatch.setattr(server, "_invalidate_cluster_server_cache",
                        lambda profile_id, _old=None, **kwargs: invalidated.append((profile_id, kwargs)))
    with adapter.profile_transaction():
        deleted = adapter.delete_profiles([first["id"], second["id"]])
    assert deleted == {"ok": True, "deleted": [first["id"], second["id"]]}
    assert {profile_id for profile_id, _kwargs in invalidated} == {first["id"], second["id"]}
    assert all(kwargs.get("preserve_remote_resources") is True for _profile_id, kwargs in invalidated)
    assert _read(adapter_home)["remote"]["nodes"] == {}

    # A flat legacy profile is promoted and removed in one write.  The old host
    # fallback is retired too, so a deleted legacy-default cannot come back.
    _write(adapter_home, {
        "remote": {"enabled": True, "host": "old.example", "user": "old", "default_node": "old.example"},
    })
    monkeypatch.setattr(rc, "_CFG_CACHE", {"mtime": None, "cfg": None})
    with adapter.profile_transaction():
        result = adapter.delete_profiles(["legacy-default"])
    assert result == {"ok": True, "deleted": ["legacy-default"]}
    retired = _read(adapter_home)["remote"]
    assert not retired.get("host") and not retired.get("default_node")
    assert rc._node_table(rc._load_remote_config(force=True)) == {}


def test_account_only_empty_patch_blocks_legacy_named_profile_inheritance(adapter_home, monkeypatch):
    """An explicit clear must beat top-level values for the edited legacy node."""
    _write(adapter_home, {
        "remote": {
            "enabled": True,
            "host": "shared.example",
            "user": "shared-user",
            "port": 2201,
            "key": "C:/keys/shared",
            "workdir": "/shared/work",
            "job_dir": "/shared/jobs",
            "local_root": "D:/shared",
            "remote_root": "/shared/remote",
            "timeout": 47,
            "extra_ssh_options": ["-o", "StrictHostKeyChecking=yes"],
            "nodes": {
                "legacy-named": {
                    "host": "login.example",
                    "proxy_jump": "old-jump.example",
                },
            },
        },
    })
    monkeypatch.setattr(rc, "_CFG_CACHE", {"mtime": None, "cfg": None})
    adapter = server._ClusterCatalogAdapter()
    before = rc._node_table(rc._load_remote_config(force=True))["legacy-named"]
    assert before["key"] == "C:/keys/shared"
    assert before["extra_ssh_options"] == ["-o", "StrictHostKeyChecking=yes", "-o", "ProxyJump=old-jump.example"]

    with adapter.profile_transaction():
        adapter.update_profile("legacy-named", {
            "key_path": "", "extra_ssh_options": [], "workdir": "", "job_dir": "",
            "local_root": "", "remote_root": "", "proxy_jump": "", "timeout": 300,
        })

    raw = _read(adapter_home)["remote"]
    edited = raw["nodes"]["legacy-named"]
    assert edited["key"] == "" and edited["extra_ssh_options"] == []
    for field in ("workdir", "job_dir", "local_root", "remote_root", "proxy_jump"):
        assert edited[field] == ""
    assert set(edited["_memomics_explicit_empty_overrides"]) == {
        "key", "extra_ssh_options", "workdir", "job_dir", "local_root", "remote_root", "proxy_jump",
    }
    # Shared configuration itself remains untouched, while this one legacy
    # profile now resolves with its deliberate clears instead of borrowing it.
    assert raw["key"] == "C:/keys/shared" and raw["extra_ssh_options"] == ["-o", "StrictHostKeyChecking=yes"]
    effective = rc._node_table(rc._load_remote_config(force=True))["legacy-named"]
    assert effective["key"] == "" and effective["extra_ssh_options"] == []
    assert effective["workdir"] == "~" and effective["job_dir"] == "~/memomics_jobs"
    assert effective["local_root"] == "" and effective["remote_root"] == ""
    assert effective["proxy_jump"] == "" and effective["timeout"] == 300


def test_production_adapter_v5_receipts_use_injected_store_and_reject_saved_test_revision_race(adapter_home, monkeypatch):
    """Exercise real V5 adapter receipts without SSH or Credential Manager."""
    credential_store = MemoryCredentialStore()
    account_id = "account-000000000001"
    first = credential_store.put(account_id, "fixture-password-one")
    frozen = _v5_match_frozen(account_id=account_id, revision=first.revision)
    candidate = {
        "host": "login.example", "user": "alice", "port": 2222, "account_id": account_id,
        "workdir": "~", "job_dir": "", "local_root": "", "remote_root": "",
        "timeout": 300, "scheduler": "slurm", "partition": "", "queue": "",
    }
    _patch_v5_route_primitives(monkeypatch, candidate)
    observed = []

    def fake_probe(value, *, credential_store=None):
        observed.append((copy.deepcopy(value), credential_store))
        return {"ok": True, "stage": "nodes_probe", "code": "ok"}

    monkeypatch.setattr(rc, "probe_catalog_v5_password_connection", fake_probe)
    adapter = server._ClusterCatalogAdapter(credential_store=credential_store)

    phase_one = adapter.probe_verified_candidate(
        copy.deepcopy(frozen), credential_revisions=copy.deepcopy(frozen["credential_revisions"]),
    )
    assert phase_one["ok"] is True
    assert observed == [(candidate, credential_store)]
    # The exact V5 receipt is consumed only from a profile transaction.
    with adapter.profile_transaction():
        persisted = adapter.persist_verified_candidate(copy.deepcopy(frozen))
    assert persisted["id"] == frozen["profile_id"]
    raw = _read(adapter_home)["remote"]["nodes"][frozen["profile_id"]]
    assert raw["auth_mode"] == "catalog_password_v5"
    assert raw["catalog_v5_ssh_route"] == "v5-password-route-1"
    assert raw["key"] == "" and "catalog_v4_ssh_route" not in raw
    assert "fixture-password-one" not in repr(raw)

    profile = adapter.get_profile(frozen["profile_id"])
    saved_frozen = {
        "schema": "v5-password-test-frozen-1", "profile_id": frozen["profile_id"],
        "profile": copy.deepcopy(profile), "credential_revisions": copy.deepcopy(frozen["credential_revisions"]),
    }
    assert adapter.probe_saved_connection(
        copy.deepcopy(saved_frozen), credential_revisions=copy.deepcopy(saved_frozen["credential_revisions"]),
    )["ok"] is True
    assert adapter.confirm_tested_connection(
        copy.deepcopy(saved_frozen), credential_revisions=copy.deepcopy(saved_frozen["credential_revisions"]),
    )["ok"] is True

    # A successful Phase-1 saved-test receipt must not survive a local password
    # rotation before Phase 2, even though no network call is needed to rotate it.
    second = credential_store.put(account_id, "fixture-password-two")
    stale_frozen = dict(saved_frozen, credential_revisions={account_id: second.revision})
    assert adapter.probe_saved_connection(
        copy.deepcopy(stale_frozen), credential_revisions=copy.deepcopy(stale_frozen["credential_revisions"]),
    )["ok"] is True
    credential_store.put(account_id, "fixture-password-three")
    confirmed = adapter.confirm_tested_connection(
        copy.deepcopy(stale_frozen), credential_revisions=copy.deepcopy(stale_frozen["credential_revisions"]),
    )
    assert confirmed == {
        "ok": False, "stage": "validate", "code": "catalog_changed_retry",
        "message": "连接配置已变化；请重新验证后再保存。",
    }
    assert all(store is credential_store for _candidate, store in observed)


def test_production_adapter_v5_password_conversion_is_local_only(adapter_home, monkeypatch):
    """Password edits rebuild V5 provenance without starting a SSH probe."""
    credential_store = MemoryCredentialStore()
    account_id = "account-000000000002"
    credential_store.put(account_id, "fixture-password")
    adapter = server._ClusterCatalogAdapter(credential_store=credential_store)
    profile_id = "catalog-v5-legacy"
    with adapter.profile_transaction():
        adapter.create_profile({**_profile_payload("legacy", host="legacy.example", port=2201), "id": profile_id})

    candidate = {
        "host": "legacy.example", "user": "alice", "port": 2201, "account_id": account_id,
        "workdir": "/home/alice/work", "job_dir": "/home/alice/jobs",
        "local_root": "D:/data/alice", "remote_root": "/scratch/alice",
        "timeout": 45, "scheduler": "slurm", "partition": "gpu", "queue": "batch",
    }
    _patch_v5_route_primitives(monkeypatch, candidate)
    monkeypatch.setattr(
        rc, "probe_catalog_v5_password_connection",
        lambda *_args, **_kwargs: pytest.fail("local password conversion must not probe SSH"),
    )
    server_id = "catalog-v5-server"
    account_after = {"id": account_id, "server_id": server_id, "name": "Alice", "user": "alice", "note": ""}
    record = {
        "profile_id": profile_id, "server_id": server_id,
        "node": {
            "id": "node-v5-login", "server_id": server_id, "name": "Login",
            "host": "legacy.example", "port": 2201, "is_login": True,
            "is_compute": False, "scheduler": "slurm", "partition": "gpu", "queue": "batch",
        },
        "account": copy.deepcopy(account_after), "route": {"mode": "direct"}, "gateway_connection": None,
    }
    with adapter.profile_transaction():
        converted = adapter.convert_catalog_account_to_v5(account_after, [record])
    assert converted == {"ok": True, "converted_profile_ids": [profile_id]}
    raw = _read(adapter_home)["remote"]["nodes"][profile_id]
    assert raw["auth_mode"] == "catalog_password_v5"
    assert raw["key"] == "" and raw["proxy_jump"] == ""
    assert "catalog_v4_ssh_route" not in raw


def test_production_v5_router_and_adapter_share_one_credential_store():
    """Import-time app registration must not split CRUD and SSH credentials."""
    assert server._CLUSTER_CATALOG_ROUTER_READY is True
    adapter = server._CLUSTER_CATALOG_ADAPTER
    credential_store = server._CLUSTER_CATALOG_CREDENTIAL_STORE
    assert adapter._credential_store is credential_store
    included = next(
        route.original_router
        for route in server.app.routes
        if type(route).__name__ == "_IncludedRouter"
        and any(
            getattr(child, "path", "") == "/api/cluster/catalog/servers/{server_id}/connections/match"
            for child in route.original_router.routes
        )
    )
    endpoint = next(
        route.endpoint for route in included.routes
        if getattr(route, "path", "") == "/api/cluster/catalog/servers/{server_id}/connections/match"
    )
    closure = dict(zip(endpoint.__code__.co_freevars, (cell.cell_contents for cell in endpoint.__closure__)))
    assert closure["adapter"] is adapter
    assert closure["credential_provider"] is credential_store


def test_retired_flat_cluster_mutations_never_fall_back_to_yaml_writes(monkeypatch):
    """Only the catalog workflow can mutate servers/nodes/accounts now."""
    monkeypatch.setattr(server, "_CLUSTER_CATALOG_ROUTER_READY", True)

    async def invoke_all():
        return [
            await server.cluster_node_delete(None),
            await server.create_cluster_server(None),
            await server.update_cluster_server("legacy-server", None),
            await server.delete_cluster_server("legacy-server"),
            await server.api_cluster_config(None),
        ]

    responses = asyncio.run(invoke_all())
    assert all(response.status_code == 410 for response in responses)
    assert all(b'"code":"workflow_changed"' in response.body for response in responses)

    # A registration fault leaves remote execution/read paths untouched but
    # must be explicit; it cannot reopen these retired write endpoints.
    monkeypatch.setattr(server, "_CLUSTER_CATALOG_ROUTER_READY", False)
    unavailable = asyncio.run(server.api_cluster_config(None))
    assert unavailable.status_code == 503
    assert b'"code":"catalog_unavailable"' in unavailable.body
