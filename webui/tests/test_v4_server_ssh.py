"""Offline V4 session-reuse and SSH-match regressions.

Every SSH boundary is faked.  These tests intentionally exercise the real
BatchMode ``_action_nodes`` path with a fake connection object, but never open
a socket, spawn OpenSSH, read a private-key body, or contact a model.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from memomics.bio_tools import remote_cluster as rc
import server


class _CreateStore:
    def __init__(self, projects=()):
        self.projects = set(projects)
        self.metadata = {}
        self.assignments = []

    def has_project(self, project_id):
        return project_id in self.projects

    def metadata_for_sessions(self, session_ids):
        return {
            sid: dict(self.metadata.get(sid, {"project_id": None, "cluster_server_id": None}))
            for sid in session_ids
        }

    def set_session_project(self, sid, project_id):
        item = {"project_id": project_id, "cluster_server_id": None}
        self.metadata[sid] = item
        self.assignments.append((sid, project_id))
        return dict(item)


class _BodyRequest:
    def __init__(self, payload):
        self.payload = payload

    async def body(self):
        # Yield once, so gather() genuinely creates concurrent POST entrants.
        await asyncio.sleep(0)
        return json.dumps(self.payload).encode("utf-8")


def _empty_session(sid, *, project=None, last_active="2026-11-05 12:00:00"):
    return {
        "id": sid,
        "title": "new",
        "created": last_active,
        "last_active": last_active,
        "messages": [],
        "_messages_loaded": True,
        "_msg_count": 0,
        "model_config": {},
        "running_task": None,
        "running_agent": None,
        "_project": project,
    }


def test_new_session_reuses_one_blank_sid_under_concurrent_same_project_posts(monkeypatch):
    sessions = {}
    store = _CreateStore({"p-a", "p-b"})
    created = []

    def make_session(title):
        sid = "memomics-%08d" % (len(created) + 1)
        item = _empty_session(sid)
        item["title"] = title
        sessions[sid] = item
        created.append(sid)
        return item

    monkeypatch.setattr(server, "_sessions", sessions)
    monkeypatch.setattr(server, "_session_metadata", lambda: store)
    monkeypatch.setattr(server, "_create_session", make_session)

    async def post_many():
        return await asyncio.gather(*[
            server.new_session(_BodyRequest({"project_id": "p-a", "title": "ignored after first"}))
            for _ in range(6)
        ])

    responses = asyncio.run(post_many())
    assert created == ["memomics-00000001"]
    assert {item["id"] for item in responses} == {"memomics-00000001"}
    assert sum(not item["reused"] for item in responses) == 1
    assert sum(item["reused"] for item in responses) == 5
    assert store.assignments == [("memomics-00000001", "p-a")]


def test_new_session_reuse_respects_project_and_first_turn_memory_state(monkeypatch):
    store = _CreateStore({"p-a", "p-b"})
    sessions = {
        "memomics-empty-a": _empty_session("memomics-empty-a", last_active="2026-11-05 12:00:01"),
        # DB history is lazy, but this session already has a first user turn in
        # memory.  It must never be recycled even while _msg_count is stale.
        "memomics-memory-user": {
            **_empty_session("memomics-memory-user", last_active="2026-11-05 12:00:02"),
            "messages": [{"role": "user", "content": "first question"}],
            "_msg_count": 0,
        },
        # Claimed but not yet persisted is the other narrow first-turn window.
        "memomics-claimed": {
            **_empty_session("memomics-claimed", last_active="2026-11-05 12:00:03"),
            "_user_turn_active": True,
        },
    }
    store.metadata.update({sid: {"project_id": "p-a", "cluster_server_id": None} for sid in sessions})
    made = []

    def make_session(title):
        sid = "memomics-made-%d" % len(made)
        item = _empty_session(sid)
        sessions[sid] = item
        made.append(sid)
        return item

    monkeypatch.setattr(server, "_sessions", sessions)
    monkeypatch.setattr(server, "_session_metadata", lambda: store)
    monkeypatch.setattr(server, "_create_session", make_session)

    # The newest valid blank is empty-a; active/memory-backed candidates lose.
    reused = asyncio.run(server.new_session(_BodyRequest({"project_id": "p-a"})))
    assert reused["id"] == "memomics-empty-a" and reused["reused"] is True

    # A different project never steals its blank session from project A.
    separate = asyncio.run(server.new_session(_BodyRequest({"project_id": "p-b"})))
    assert separate["reused"] is False
    assert separate["id"] == "memomics-made-0"

    # Once the only blank A session has a first message, a new A POST creates.
    sessions["memomics-empty-a"]["messages"].append({"role": "user", "content": "now used"})
    after_first_question = asyncio.run(server.new_session(_BodyRequest({"project_id": "p-a"})))
    assert after_first_question["reused"] is False
    assert after_first_question["id"] == "memomics-made-1"


@pytest.mark.parametrize("payload", [{}, {"project_id": None}])
def test_plain_new_session_falls_back_to_fresh_unclassified_chat_when_metadata_is_unavailable(monkeypatch, payload):
    sessions = {}
    created = []

    def make_session(title):
        sid = "memomics-legacy-%d" % (len(created) + 1)
        item = _empty_session(sid)
        item["title"] = title
        sessions[sid] = item
        created.append(sid)
        return item

    def unavailable():
        raise RuntimeError("metadata schema is locked")

    monkeypatch.setattr(server, "_sessions", sessions)
    monkeypatch.setattr(server, "_session_metadata", unavailable)
    monkeypatch.setattr(server, "_create_session", make_session)
    response = asyncio.run(server.new_session(_BodyRequest(payload)))

    assert response["id"] == "memomics-legacy-1"
    assert response["reused"] is False
    assert response["project_id"] is None and response["cluster_server_id"] is None
    assert "未分类" in response["metadata_warning"]
    assert created == ["memomics-legacy-1"]


def test_plain_new_session_keeps_the_already_created_sid_when_null_metadata_write_fails(monkeypatch):
    sessions = {}
    created = []

    class Store:
        def metadata_for_sessions(self, _ids):
            return {}

        def set_session_project(self, _sid, project_id):
            assert project_id is None
            raise RuntimeError("metadata write lost its lock")

    def make_session(title):
        sid = "memomics-fresh-1"
        item = _empty_session(sid)
        item["title"] = title
        sessions[sid] = item
        created.append(sid)
        return item

    monkeypatch.setattr(server, "_sessions", sessions)
    monkeypatch.setattr(server, "_session_metadata", lambda: Store())
    monkeypatch.setattr(server, "_create_session", make_session)
    response = asyncio.run(server.new_session(_BodyRequest({})))

    assert response["id"] == "memomics-fresh-1"
    assert response["reused"] is False
    assert "metadata_warning" in response
    assert created == ["memomics-fresh-1"]
    assert set(sessions) == {"memomics-fresh-1"}


def test_plain_metadata_failure_never_reuses_existing_unknown_blank_sessions(monkeypatch):
    sessions = {
        "memomics-unknown-a": _empty_session("memomics-unknown-a", last_active="2099-01-01 00:00:01"),
        "memomics-unknown-b": _empty_session("memomics-unknown-b", last_active="2099-01-01 00:00:02"),
    }
    created = []

    def make_session(title):
        sid = "memomics-new-unclassified"
        item = _empty_session(sid)
        item["title"] = title
        sessions[sid] = item
        created.append(sid)
        return item

    monkeypatch.setattr(server, "_sessions", sessions)
    monkeypatch.setattr(
        server, "_session_metadata",
        lambda: (_ for _ in ()).throw(RuntimeError("metadata read denied")),
    )
    monkeypatch.setattr(server, "_create_session", make_session)
    response = asyncio.run(server.new_session(_BodyRequest({})))

    assert response["id"] == "memomics-new-unclassified"
    assert response["reused"] is False
    assert created == ["memomics-new-unclassified"]
    assert set(sessions) == {"memomics-unknown-a", "memomics-unknown-b", "memomics-new-unclassified"}


def test_explicit_project_new_session_fails_closed_and_compensates_after_metadata_write_failure(monkeypatch):
    sessions = {}
    created = []
    deleted_metadata = []

    class Store:
        def has_project(self, project_id):
            return project_id == "p-a"

        def metadata_for_sessions(self, _ids):
            return {}

        def set_session_project(self, _sid, _project_id):
            raise RuntimeError("metadata write lost its lock")

        def delete_session_metadata(self, sid):
            deleted_metadata.append(sid)

    def make_session(title):
        sid = "memomics-project-1"
        item = _empty_session(sid)
        item["title"] = title
        sessions[sid] = item
        created.append(sid)
        return item

    monkeypatch.setattr(server, "_sessions", sessions)
    monkeypatch.setattr(server, "_session_metadata", lambda: Store())
    monkeypatch.setattr(server, "_create_session", make_session)
    monkeypatch.setattr(server, "_get_session_db", lambda: None)
    response = asyncio.run(server.new_session(_BodyRequest({"project_id": "p-a"})))

    assert response.status_code == 500
    assert created == ["memomics-project-1"]
    assert deleted_metadata == ["memomics-project-1"]
    assert sessions == {}


def test_explicit_project_does_not_fallback_when_metadata_schema_is_unavailable(monkeypatch):
    created = []
    monkeypatch.setattr(server, "_session_metadata", lambda: (_ for _ in ()).throw(RuntimeError("metadata denied")))
    monkeypatch.setattr(server, "_create_session", lambda title: created.append(title))
    response = asyncio.run(server.new_session(_BodyRequest({"project_id": "p-a"})))
    assert response.status_code == 500
    assert created == []


def test_session_list_msg_count_is_conservative_for_lazy_and_claimed_turns(monkeypatch):
    lazy = _empty_session("memomics-lazy")
    lazy.update({"_messages_loaded": False, "_msg_count": 2, "_first_msg": "persisted"})
    claimed = _empty_session("memomics-claimed")
    claimed["_user_turn_active"] = True
    store = _CreateStore()
    monkeypatch.setattr(server, "_sessions", {lazy["id"]: lazy, claimed["id"]: claimed})
    monkeypatch.setattr(server, "_session_metadata", lambda: store)

    payload = asyncio.run(server.list_sessions())
    rows = {row["id"]: row for row in payload["sessions"]}
    assert rows["memomics-lazy"]["msg_count"] == 2
    # Claimed first turn has not appended a message yet, but the running flag
    # makes it unambiguously unusable for a concurrent create request.
    assert rows["memomics-claimed"]["is_running"] is False
    assert server._session_is_reusable_blank(claimed) is False


def test_session_reuse_is_based_on_first_user_turn_not_assistant_placeholders(monkeypatch):
    assistant_only = _empty_session("memomics-assistant")
    assistant_only["messages"] = [{"role": "assistant", "content": "welcome"}]
    system_only = _empty_session("memomics-system")
    system_only["messages"] = [{"role": "system", "content": "placeholder"}]
    asked = _empty_session("memomics-asked")
    asked["messages"] = [{"role": "user", "content": "real question"}]
    assert server._session_is_reusable_blank(assistant_only) is True
    assert server._session_is_reusable_blank(system_only) is True
    assert server._session_is_reusable_blank(asked) is False

    lazy = _empty_session("memomics-lazy-real-user")
    lazy.update({"_messages_loaded": False, "_msg_count": 1, "_first_msg": "not role-safe"})

    class LazyDB:
        def get_messages_as_conversation(self, sid, limit=None):
            assert sid == "memomics-lazy-real-user" and limit is None
            return [{"role": "user", "content": "persisted first question"}]

    monkeypatch.setattr(server, "_get_session_db", lambda: LazyDB())
    assert server._session_is_reusable_blank(lazy) is False


def _keypair(tmp_path: Path, *, default: bool = False) -> Path:
    root = tmp_path / ".ssh" if default else tmp_path / "keys"
    root.mkdir(parents=True, exist_ok=True)
    key = root / "id_ed25519"
    key.write_text("private key placeholder", encoding="utf-8")
    key.with_suffix(key.suffix + ".pub").write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest memomics", encoding="utf-8")
    return key


def _candidate(key_path, *, gateway=None):
    value = {
        "host": "target.example", "user": "targetuser", "port": 2222,
        "key_path": str(key_path), "workdir": "/work", "timeout": 30,
    }
    if gateway:
        value["gateway"] = gateway
    return value


def _offline_managed_store(monkeypatch, config_path: Path) -> Path:
    """Provide already-trusted V4 artifacts for an SSH-free probe fixture.

    These probe tests replace Paramiko and OpenSSH completely, so they cannot
    exercise the TOFU write or the native Windows DACL reader.  Seed the
    non-empty pin and replace only those security boundaries; policy tests in
    ``test_v4_managed_ssh_policy.py`` cover the real verifier separately.
    """
    root = config_path.parent / ".memomics-catalog-v4"
    root.mkdir(exist_ok=True)
    (root / "known_hosts").write_text(
        "[target.example]:2222 ssh-ed25519 AAAATESTPIN\n", encoding="utf-8",
    )
    monkeypatch.setattr(rc, "_catalog_managed_store_dir", lambda: root)
    monkeypatch.setattr(rc, "_catalog_ensure_managed_store", lambda: root)
    monkeypatch.setattr(rc, "_catalog_harden_managed_path", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rc, "_catalog_verify_managed_path", lambda *_args, **_kwargs: None)
    return root


def test_probe_connection_keeps_target_and_gateway_passwords_isolated_and_calls_nodes(monkeypatch, tmp_path):
    key = _keypair(tmp_path, default=True)
    real_expanduser = rc.os.path.expanduser
    monkeypatch.setattr(rc.os.path, "expanduser", lambda value: str(tmp_path) if value == "~" else real_expanduser(value))
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(rc, "_get_config_path", lambda: config_path)
    _offline_managed_store(monkeypatch, config_path)

    class AuthError(Exception):
        pass

    fake_paramiko = SimpleNamespace(ssh_exception=SimpleNamespace(
        AuthenticationException=AuthError, BadHostKeyException=type("BadKey", (Exception,), {}),
    ))
    calls = []

    class Transport:
        def open_channel(self, *_args):
            return object()

        def get_remote_server_key(self):
            return None

    class Client:
        def get_transport(self):
            return Transport()

        def close(self):
            return None

    def fake_connect(_paramiko, host, _port, _user, password, _key, sock_factory=None, *, known_hosts_path=None):
        calls.append((host, password, bool(sock_factory), known_hosts_path))
        if host == "gateway.example" and password == "":
            raise AuthError("gateway key rejected")
        if host == "target.example" and password == "":
            # First target key-only attempt fails, post-install verify succeeds.
            target_key_attempts = sum(item[0] == "target.example" and item[1] == "" for item in calls)
            if target_key_attempts == 1:
                raise AuthError("target key rejected")
            return Client(), "key"
        if host == "gateway.example":
            assert password == "gateway-secret"
            return Client(), "password"
        assert password == "target-secret"
        return Client(), "password"

    nodes_calls = []
    monkeypatch.setattr(rc, "_paramiko", lambda: fake_paramiko)
    monkeypatch.setattr(rc, "_catalog_tcp_handshake", lambda *_args: None)
    monkeypatch.setattr(rc, "_p_connect", fake_connect)
    monkeypatch.setattr(rc, "_exec_install", lambda *_args: "installed")
    monkeypatch.setattr(
        rc, "_action_nodes",
        lambda cfg, args: nodes_calls.append((cfg, args)) or json.dumps({
            "status": "ok", "nodes": [{"name": "catalog-probe", "reachable": True}],
        }),
    )

    result = rc.probe_connection(
        _candidate(key, gateway={"host": "gateway.example", "user": "gateuser", "port": 22, "key_path": str(key)}),
        target_password="target-secret", gateway_password="gateway-secret",
    )
    assert result["ok"] is True and result["stage"] == "nodes_probe"
    assert ("gateway.example", "gateway-secret") in {(host, password) for host, password, _sock, _known in calls}
    assert ("target.example", "target-secret") in {(host, password) for host, password, _sock, _known in calls}
    assert "target-secret" not in json.dumps(result)
    assert "gateway-secret" not in json.dumps(result)
    assert len(nodes_calls) == 1
    probe_cfg = nodes_calls[0][0]
    entry = probe_cfg["nodes"]["catalog-probe"]
    assert "proxy_jump" not in entry
    assert entry["extra_ssh_options"][0] == "-F"
    route_config = Path(entry["extra_ssh_options"][1])
    config_text = route_config.read_text(encoding="utf-8")
    assert "ProxyJump memomics-v4-gateway-" in config_text
    assert "StrictHostKeyChecking yes" in config_text
    assert "IdentitiesOnly yes" in config_text
    assert "Include " not in config_text and "ProxyCommand " not in config_text
    assert all("gateway-secret" not in str(value) and "target-secret" not in str(value)
               for value in entry["extra_ssh_options"])


def test_probe_missing_dependency_and_nondefault_gateway_fail_before_network(monkeypatch, tmp_path):
    key = _keypair(tmp_path)
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(rc, "_get_config_path", lambda: config_path)
    _offline_managed_store(monkeypatch, config_path)
    monkeypatch.setattr(rc, "_paramiko", lambda: None)
    tcp_calls = []
    monkeypatch.setattr(rc, "_catalog_tcp_handshake", lambda *args: tcp_calls.append(args))
    direct = rc.probe_connection(_candidate(key))
    assert direct == {
        "ok": False, "stage": "key_auth", "code": "missing_dependency",
        "message": "缺少 paramiko，无法进行一次性密码认证和公钥安装；请安装应用依赖后重试。",
    }
    assert tcp_calls == []

    # Controlled -F propagation now supports the same explicit application
    # key on both hops; dependency failure is reported before network/I/O.
    via = rc.probe_connection(_candidate(key, gateway={
        "host": "gateway.example", "user": "gateuser", "port": 22, "key_path": str(key),
    }))
    assert via["code"] == "missing_dependency"
    assert via["stage"] == "key_auth"
    assert tcp_calls == []


def test_probe_failure_redacts_secret_and_saved_test_uses_real_nodes_action(monkeypatch, tmp_path):
    key = _keypair(tmp_path)
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(rc, "_get_config_path", lambda: config_path)
    _offline_managed_store(monkeypatch, config_path)

    class AuthError(Exception):
        pass

    fake_paramiko = SimpleNamespace(ssh_exception=SimpleNamespace(
        AuthenticationException=AuthError, BadHostKeyException=type("BadKey", (Exception,), {}),
    ))
    monkeypatch.setattr(rc, "_paramiko", lambda: fake_paramiko)
    monkeypatch.setattr(rc, "_catalog_tcp_handshake", lambda *_args: None)
    monkeypatch.setattr(
        rc, "_p_connect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AuthError("password=top-secret-value")),
    )
    failed = rc.probe_connection(_candidate(key), target_password="top-secret-value")
    assert failed["code"] == "target_auth_failed"
    assert "top-secret-value" not in json.dumps(failed)

    class FakeConn:
        def execute(self, _command, **_kwargs):
            return {"returncode": 0, "output": ""}

    # This leaves _action_nodes intact: the real original BatchMode node action
    # consumes a fake SSH connection and is the only execution boundary.
    monkeypatch.setattr(rc, "_get_conn", lambda _cfg: FakeConn())
    saved = rc.probe_saved_connection(_candidate(key))
    assert saved["ok"] is True and saved["stage"] == "nodes_probe"


def test_adapter_rejects_untrusted_ssh_injection_before_probe(monkeypatch):
    adapter = server._ClusterCatalogAdapter()
    called = []
    monkeypatch.setattr(server, "_cluster_mod", lambda: SimpleNamespace(
        probe_connection=lambda *_args, **_kwargs: called.append(True) or {"ok": True},
    ))
    result = adapter.match_connection(
        "server-1",
        {"server_id": "server-1", "host": "target.example", "port": 22},
        {"server_id": "server-1", "user": "alice"},
        {"mode": "direct"},
        {"name": "bad", "key_path": "C:/safe/key", "extra_ssh_options": ["-o", "ProxyCommand=evil"]},
    )
    assert result["code"] == "unsupported_connection_field"
    assert called == []


@pytest.mark.parametrize(
    "location,field,value",
    [
        ("target", "host", "-target.example"),
        ("target", "host", "bad host"),
        ("target", "host", "bad@target"),
        ("target", "host", "bad/target"),
        ("target", "host", "bad\x00target"),
        ("gateway", "host", "-gateway.example"),
        ("gateway", "host", "bad gateway"),
        ("gateway", "host", "bad@gateway"),
        ("gateway", "host", "bad/gateway"),
        ("gateway", "host", "bad\x00gateway"),
        ("target", "user", "-alice"),
        ("target", "user", "alice/name"),
        ("target", "user", "alice\x00x"),
        ("gateway", "user", "-gate"),
        ("gateway", "user", "gate/name"),
        ("gateway", "user", "gate\x00x"),
        ("target", "port", 0),
        ("target", "port", 65536),
        ("target", "port", "not-a-port"),
        ("gateway", "port", 0),
        ("gateway", "port", 65536),
        ("gateway", "port", "not-a-port"),
    ],
)
def test_catalog_match_rejects_endpoint_injection_before_any_native_probe(monkeypatch, tmp_path, location, field, value):
    key = _keypair(tmp_path)
    candidate = _candidate(key)
    candidate["gateway"] = {
        "host": "gateway.example", "user": "gate", "port": 2201, "key_path": str(key),
    }
    target = candidate if location == "target" else candidate["gateway"]
    target[field] = value
    native_calls = []

    def native(name):
        def _called(*_args, **_kwargs):
            native_calls.append(name)
            raise AssertionError("native probe must not run for invalid match input")
        return _called

    monkeypatch.setattr(rc, "_catalog_ensure_managed_store", native("store"))
    monkeypatch.setattr(rc, "_paramiko", native("paramiko"))
    monkeypatch.setattr(rc, "_catalog_tcp_handshake", native("tcp"))
    monkeypatch.setattr(rc.subprocess, "run", native("subprocess"))

    result = rc.probe_connection(candidate)
    assert result["stage"] == "validate"
    assert result["code"] == "invalid_connection"
    assert native_calls == []


def _frozen_match(*, profile_id="connection-a", workdir="/work"):
    return {
        "schema": "v4-match-frozen-1",
        "server_id": "server-1",
        "server": {"id": "server-1", "name": "Server"},
        "node": {"id": "node-1", "server_id": "server-1", "host": "target.example", "port": 22},
        "account": {"id": "account-1", "server_id": "server-1", "user": "alice"},
        "route": {"mode": "direct"},
        "connection": {"name": "target", "workdir": workdir},
        "gateway_connection": None,
        "existing_profile_id": None,
        "profile_id": profile_id,
    }


def test_verified_candidate_receipt_is_one_shot_and_rejects_yaml_drift(monkeypatch):
    adapter = server._ClusterCatalogAdapter()
    frozen = _frozen_match()
    seen = []
    candidate = {
        "host": "target.example", "user": "alice", "port": 22, "key": "C:/managed/key",
        "workdir": "/work", "job_dir": "/work/jobs", "local_root": "", "remote_root": "",
        "timeout": 30, "scheduler": "auto", "partition": "", "queue": "",
        "known_hosts_path": "C:/managed/known_hosts",
    }
    monkeypatch.setattr(
        adapter, "_compose_prepared_match_candidate",
        lambda *_args, **kwargs: (dict(candidate), {"display_name": "target", "note": ""}, None),
    )
    monkeypatch.setattr(server, "_cluster_mod", lambda: SimpleNamespace(
        probe_connection=lambda *_args, **_kwargs: {"ok": True, "stage": "nodes_probe", "code": "ok"},
    ))
    yaml_state = {"value": "yaml-a"}
    monkeypatch.setattr(adapter, "_remote_yaml_fingerprint", lambda *_args: yaml_state["value"])
    monkeypatch.setattr(adapter, "_persist_prepared_candidate",
                        lambda profile_id, saved_candidate, metadata:
                        seen.append((profile_id, dict(saved_candidate), dict(metadata))) or {"id": profile_id})

    assert adapter.probe_verified_candidate(frozen, {"target_password": "secret"})["ok"] is True
    persisted = adapter.persist_verified_candidate(frozen)
    assert persisted == {"id": "connection-a"}
    assert seen[0][0] == "connection-a"
    assert "secret" not in json.dumps(seen[0])
    assert adapter.persist_verified_candidate(frozen)["code"] == "catalog_changed_retry"

    frozen_drift = _frozen_match(profile_id="connection-b", workdir="/other")
    assert adapter.probe_verified_candidate(frozen_drift, {})["ok"] is True
    yaml_state["value"] = "yaml-b"
    assert adapter.persist_verified_candidate(frozen_drift)["code"] == "catalog_changed_retry"


def test_saved_test_accepts_safe_profile_id_alias_and_requires_confirmation(monkeypatch):
    adapter = server._ClusterCatalogAdapter()
    frozen = {"schema": "v4-test-frozen-1", "profile_id": "connection-a", "profile": {
        "profile_id": "connection-a", "id": "connection-a", "host": "target.example", "user": "alice",
        "port": 22, "configured": True, "has_key": True, "legacy": False,
    }}
    monkeypatch.setattr(adapter, "get_profile", lambda _pid: {
        "id": "connection-a", "host": "target.example", "user": "alice", "port": 22,
        "configured": True, "has_key": True, "legacy": False,
    })
    yaml_state = {"value": "yaml-a"}
    monkeypatch.setattr(adapter, "_remote_yaml_fingerprint", lambda *_args: yaml_state["value"])
    monkeypatch.setattr(adapter, "test_connection", lambda _pid: {
        "ok": True, "stage": "nodes_probe", "code": "ok",
    })
    assert adapter.probe_saved_connection(frozen)["ok"] is True
    assert adapter.confirm_tested_connection(frozen)["ok"] is True
    assert adapter.confirm_tested_connection(frozen)["code"] == "catalog_changed_retry"


def test_v4_receipt_maps_are_bounded_under_successful_probe_bursts(monkeypatch):
    adapter = server._ClusterCatalogAdapter()
    monkeypatch.setattr(adapter, "_MATCH_RECEIPT_MAX_PER_KIND", 3)
    tables = (adapter._matched_receipts, adapter._verified_candidates, adapter._saved_test_receipts)
    with adapter._receipt_lock:
        for table in tables:
            for index in range(5):
                adapter._put_receipt(
                    table, ("profile-%d" % index, "fingerprint-%d" % index),
                    {"created_monotonic": float(index)},
                )
            assert len(table) == 3
            assert set(table) == {
                ("profile-2", "fingerprint-2"),
                ("profile-3", "fingerprint-3"),
                ("profile-4", "fingerprint-4"),
            }


def test_v4_profile_marker_is_private_and_copied_to_durable_connection_snapshots(monkeypatch):
    adapter = server._ClusterCatalogAdapter()
    candidate = {
        "host": "target.example", "user": "alice", "port": 22, "key": "C:/managed/key",
        "workdir": "/work", "job_dir": "/work/jobs", "local_root": "", "remote_root": "",
        "timeout": 30, "scheduler": "auto", "partition": "", "queue": "",
    }
    captured = {}
    monkeypatch.setattr(server, "_cluster_server_by_id", lambda _profile_id: None)
    monkeypatch.setattr(server, "_cluster_mod", lambda: SimpleNamespace(
        catalog_ssh_policy_options=lambda _candidate: ["-F", "generated-route.conf"],
    ))

    def create(payload, *, catalog_v4_route=False):
        captured["payload"] = dict(payload)
        captured["catalog_v4_route"] = catalog_v4_route
        return {"id": payload["id"]}

    monkeypatch.setattr(server, "_create_cluster_server_profile", create)
    assert adapter._persist_prepared_candidate("profile-a", candidate, {"display_name": "Target"}) == {
        "id": "profile-a",
    }
    assert captured["catalog_v4_route"] is True
    node = server._server_payload_to_node(captured["payload"], catalog_v4_route=True)
    assert node["catalog_v4_ssh_route"] == "v4-managed-route-1"
    snapshot = rc._connection_snapshot(node)
    assert snapshot["catalog_v4_ssh_route"] == "v4-managed-route-1"


def test_console_save_rejects_unknown_nonempty_v4_route_provenance():
    with pytest.raises(ValueError, match="provenance"):
        server._cluster_node_lines({
            "target": {
                "host": "target.example", "user": "alice",
                "catalog_v4_ssh_route": "v4-managed-route-corrupt",
            },
        })


def test_catalog_known_host_store_serializes_conflicts_and_merges_distinct_endpoints(monkeypatch, tmp_path):
    """No sockets: exercise the actual _p_connect TOFU lock + atomic merge."""
    store = tmp_path / ".memomics-catalog-v4"
    store.mkdir()
    known_hosts = store / "known_hosts"
    key = _keypair(tmp_path)
    monkeypatch.setattr(rc, "_catalog_managed_store_dir", lambda: store)
    monkeypatch.setattr(rc, "_catalog_ensure_managed_store", lambda: store)
    monkeypatch.setattr(rc, "_catalog_harden_managed_path", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rc, "_catalog_verify_managed_path", lambda *_args, **_kwargs: None)

    class Keys:
        def __init__(self):
            self.data = {}

        def load(self, path):
            self.data = json.loads(Path(path).read_text(encoding="utf-8"))

        def lookup(self, name):
            return self.data.get(name)

        def items(self):
            return self.data.items()

        def add(self, name, key_type, value):
            self.data.setdefault(name, {})[key_type] = value

        def save(self, path):
            Path(path).write_text(json.dumps(self.data, sort_keys=True), encoding="utf-8")

    class BadKey(Exception):
        pass

    class AuthError(Exception):
        pass

    class AutoPolicy:
        pass

    class RejectPolicy:
        pass

    local = threading.local()

    class Client:
        def __init__(self):
            self.keys = Keys()
            self.policy = None

        def load_host_keys(self, path):
            self.keys.load(path)

        def get_host_keys(self):
            return self.keys

        def set_missing_host_key_policy(self, policy):
            self.policy = policy

        def connect(self, *, hostname, port, **_kwargs):
            name = rc._known_host_lookup_names(hostname, port)[0]
            value = local.host_key
            known = self.keys.lookup(name)
            if isinstance(self.policy, RejectPolicy) and known and known.get("ssh-ed25519") != value:
                raise BadKey("host key changed")
            self.keys.add(name, "ssh-ed25519", value)

        def close(self):
            return None

    fake_paramiko = SimpleNamespace(
        SSHClient=Client, HostKeys=Keys, AutoAddPolicy=AutoPolicy, RejectPolicy=RejectPolicy,
        ssh_exception=SimpleNamespace(BadHostKeyException=BadKey, AuthenticationException=AuthError),
    )

    def connect(host, observed):
        local.host_key = observed
        return rc._p_connect(fake_paramiko, host, 2222, "alice", "", str(key),
                             known_hosts_path=str(known_hosts))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        same = [pool.submit(connect, "same.example", value) for value in ("key-a", "key-b")]
        outcomes = []
        for future in same:
            try:
                outcomes.append(("ok", future.result(timeout=10)))
            except Exception as exc:  # one conflict is the expected TOFU result
                outcomes.append(("error", exc))
    assert sum(kind == "ok" for kind, _value in outcomes) == 1
    conflict = next(value for kind, value in outcomes if kind == "error")
    assert rc._catalog_is_host_key_error(fake_paramiko, conflict)

    known_hosts.unlink()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(connect, host, value) for host, value in (
            ("one.example", "key-one"), ("two.example", "key-two"),
        )]
        for future in futures:
            future.result(timeout=10)
    saved = json.loads(known_hosts.read_text(encoding="utf-8"))
    assert saved["[one.example]:2222"]["ssh-ed25519"] == "key-one"
    assert saved["[two.example]:2222"]["ssh-ed25519"] == "key-two"
    assert rc._known_host_lookup_names("same.example", 2222) == ["[same.example]:2222"]


def test_known_host_fsync_failure_preserves_existing_pin_and_blocks_password_retry(monkeypatch, tmp_path):
    """An unsynced first sighting cannot become a second password TOFU decision."""
    store = tmp_path / ".memomics-catalog-v4"
    store.mkdir()
    known_hosts = store / "known_hosts"
    original = json.dumps({"[old.example]:2222": {"ssh-ed25519": "old-key"}}, sort_keys=True)
    known_hosts.write_text(original, encoding="utf-8")
    monkeypatch.setattr(rc, "_catalog_managed_store_dir", lambda: store)
    monkeypatch.setattr(rc, "_catalog_verify_managed_path", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rc, "_catalog_harden_managed_path", lambda *_args, **_kwargs: None)

    class Keys:
        def __init__(self):
            self.data = {}

        def load(self, path):
            self.data = json.loads(Path(path).read_text(encoding="utf-8"))

        def lookup(self, name):
            return self.data.get(name)

        def items(self):
            return self.data.items()

        def add(self, name, key_type, value):
            self.data.setdefault(name, {})[key_type] = value

        def save(self, path):
            Path(path).write_text(json.dumps(self.data, sort_keys=True), encoding="utf-8")

    observed = Keys()
    observed.add("[new.example]:2222", "ssh-ed25519", "new-key")
    client = SimpleNamespace(get_host_keys=lambda: observed)
    fake_paramiko = SimpleNamespace(HostKeys=Keys)
    fsync_calls = []

    def fail_fsync(fd):
        fsync_calls.append(fd)
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(rc.os, "fsync", fail_fsync)
    with pytest.raises(rc._CatalogHostKeyStoreError):
        rc._save_catalog_host_keys(client, fake_paramiko, known_hosts)
    assert fsync_calls
    assert known_hosts.read_text(encoding="utf-8") == original
    assert not list(store.glob(".known_hosts.*.tmp"))

    class AuthError(Exception):
        pass

    attempts = []

    class FailingClient:
        def connect(self, **kwargs):
            attempts.append("key" if "key_filename" in kwargs else "password")
            raise AuthError("auth failed after host-key observation")

        def close(self):
            return None

    failing_paramiko = SimpleNamespace(SSHClient=FailingClient)
    key = _keypair(tmp_path)
    monkeypatch.setattr(rc, "_configure_catalog_host_key_policy", lambda *_args: known_hosts)
    monkeypatch.setattr(
        rc, "_save_catalog_host_keys",
        lambda *_args: (_ for _ in ()).throw(rc._CatalogHostKeyStoreError("store unavailable")),
    )
    with pytest.raises(rc._CatalogHostKeyStoreError):
        rc._p_connect(failing_paramiko, "new.example", 2222, "alice", "password", str(key),
                      known_hosts_path=str(known_hosts))
    assert attempts == ["key"]


def test_authorized_keys_install_always_prefixes_a_safe_newline():
    public_line = "ssh-ed25519 AAAATEST memomics-catalog@local"
    command = rc._install_cmd(public_line)
    assert "grep -qF 'ssh-ed25519 AAAATEST memomics-catalog@local'" in command
    assert "printf '\\n%s\\n' 'ssh-ed25519 AAAATEST memomics-catalog@local' >> ~/.ssh/authorized_keys" in command
    assert "echo 'ssh-ed25519 AAAATEST memomics-catalog@local' >>" not in command


def test_managed_windows_acl_requires_an_exact_protected_whitelist(monkeypatch, tmp_path):
    path = tmp_path / "managed-artifact"
    path.write_text("x", encoding="utf-8")
    captured = {}
    monkeypatch.setattr(rc, "_catalog_windows_current_sid", lambda: "S-1-5-21-42")
    monkeypatch.setattr(rc, "_catalog_set_windows_dacl",
                        lambda _path, sddl: captured.setdefault("sddl", sddl))
    monkeypatch.setattr(rc, "_catalog_windows_sddl",
                        lambda _path: "D:P(A;;FA;;;S-1-5-21-42)(A;;FA;;;SY)(A;;FA;;;BA)")
    rc._catalog_harden_windows_acl(path, directory=False)
    assert captured["sddl"] == "D:P(A;;FA;;;S-1-5-21-42)(A;;FA;;;SY)(A;;FA;;;BA)"

    monkeypatch.setattr(rc, "_catalog_windows_sddl",
                        lambda _path: "D:P(A;;FA;;;S-1-5-21-42)(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;WD)")
    with pytest.raises(rc._CatalogManagedStorePermissionError):
        rc._catalog_harden_windows_acl(path, directory=False)


def test_managed_windows_acl_resolves_la_only_when_it_is_the_current_sid(monkeypatch):
    """A textual LA trustee is safe only after exact SID canonicalization."""
    aliases = {
        "LA": "S-1-5-21-9-9-9-500",
        "SY": "S-1-5-18",
        "BA": "S-1-5-32-544",
    }
    monkeypatch.setattr(rc, "_catalog_windows_canonical_sid", lambda value: aliases.get(str(value), str(value)))
    sddl = "D:P(A;;FA;;;LA)(A;;FA;;;SY)(A;;FA;;;BA)"

    rc._catalog_assert_windows_acl(sddl, "S-1-5-21-9-9-9-500", directory=False)
    with pytest.raises(rc._CatalogManagedStorePermissionError):
        rc._catalog_assert_windows_acl(sddl, "S-1-5-21-9-9-9-1002", directory=False)


def test_existing_managed_store_with_extra_ace_is_verified_not_repaired(monkeypatch, tmp_path):
    if rc.os.name != "nt":
        pytest.skip("Windows DACL verification is platform-specific")
    root = tmp_path / ".memomics-catalog-v4"
    root.mkdir()
    set_calls = []
    monkeypatch.setattr(rc, "_catalog_managed_store_dir", lambda: root)
    monkeypatch.setattr(rc, "_catalog_windows_current_sid", lambda: "S-1-5-21-42")
    monkeypatch.setattr(
        rc, "_catalog_windows_sddl",
        lambda _path: "D:P(A;OICI;FA;;;S-1-5-21-42)(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;WD)",
    )
    monkeypatch.setattr(rc, "_catalog_set_windows_dacl", lambda *_args: set_calls.append(True))

    with pytest.raises(rc._CatalogManagedStorePermissionError):
        rc._catalog_ensure_managed_store()
    assert set_calls == []
