"""Offline regression tests for project and multi-server isolation.

These tests use only temporary SQLite/config data.  They deliberately do not
open SSH connections or construct a WebUI/LLM agent.
"""

from __future__ import annotations

import concurrent.futures
import asyncio
import json
import os
import tempfile
from types import SimpleNamespace
from pathlib import Path

import pytest

from memomics.session_metadata import MetadataError, SessionMetadataStore
from memomics.bio_tools import remote_cluster as rc
from memomics.bio_tools import cluster_kernel as ck
from memomics.bio_tools import cluster_session as cs
import server as web_server


def _cfg(nodes):
    return {
        "enabled": True,
        "host": "",
        "user": "shared-user",
        "port": 22,
        "key": "C:/keys/shared",
        "workdir": "/shared",
        "scheduler": "auto",
        "job_dir": "/shared/memomics_jobs",
        "extra_ssh_options": [],
        "nodes": nodes,
        "default_node": "",
        "allow_unlisted_nodes": True,
    }


def test_project_delete_unassigns_without_deleting_metadata(tmp_path):
    store = SessionMetadataStore(tmp_path / "state.db")
    project = store.create_project("Project A")
    store.set_session_project("memomics-a1b2c3d4", project["id"])
    store.set_session_cluster_server("memomics-a1b2c3d4", "server-a")

    assert store.delete_project(project["id"]) == 1
    meta = store.get_session_metadata("memomics-a1b2c3d4")
    assert meta == {"project_id": None, "cluster_server_id": "server-a"}


def test_metadata_writes_are_safe_under_parallel_session_moves(tmp_path):
    store = SessionMetadataStore(tmp_path / "state.db")
    left = store.create_project("Left")
    right = store.create_project("Right")
    sid = "memomics-a1b2c3d4"

    def move(index):
        store.set_session_project(sid, left["id"] if index % 2 else right["id"])
        store.set_session_cluster_server(sid, "server-a" if index % 2 else "server-b")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(move, range(100)))
    meta = store.get_session_metadata(sid)
    assert meta["project_id"] in {left["id"], right["id"]}
    assert meta["cluster_server_id"] in {"server-a", "server-b"}


def test_legacy_binding_does_not_constrain_explicit_profile_or_default_policy(monkeypatch):
    cfg = _cfg({
        "server-a": {"host": "a.example", "user": "alice", "port": 2201, "key": "a.key"},
        "server-b": {"host": "b.example", "user": "bob", "port": 2202, "key": "b.key"},
    })
    # A stale stored A preference is metadata only.  It cannot redirect or
    # reject an explicit B request, and it cannot suppress normal needs_node.
    monkeypatch.setattr(rc, "bound_server_for_session", lambda sid: "server-a")
    node, name, err = rc.select_node_for_session(cfg, "server-b", "memomics-a1b2c3d4")
    assert err is None and name == "server-b" and node["host"] == "b.example"

    _node, _name, err = rc.select_node_for_session(cfg, "", "memomics-a1b2c3d4")
    assert json.loads(err)["status"] == "needs_node"



def test_metadata_read_failure_does_not_block_current_or_historical_target(monkeypatch):
    cfg = _cfg({"server-a": {"host": "a.example", "user": "alice"}})
    monkeypatch.setattr(rc, "bound_server_for_session", lambda sid: (_ for _ in ()).throw(RuntimeError("db locked")))
    node, name, err = rc.select_node_for_session(cfg, "", "memomics-a1b2c3d4")
    assert err is None and name == "server-a" and node["host"] == "a.example"

    node, name, err = rc.select_node_for_session(
        cfg, "server-a", "memomics-a1b2c3d4", recorded_target=True
    )
    assert err is None and name == "server-a" and node["host"] == "a.example"


def test_agent_dispatch_allows_any_explicit_profile_and_keeps_chat_as_attribution(monkeypatch):
    cfg = _cfg({
        "server-a": {"host": "a.example", "user": "alice", "port": 2201},
        "server-b": {"host": "b.example", "user": "bob", "port": 2202},
    })
    dispatched = []

    def fake_run(node, args):
        dispatched.append((dict(node), dict(args)))
        return json.dumps({"ok": True, "node": args["node"]})

    monkeypatch.setattr(rc, "_load_remote_config", lambda *args, **kwargs: cfg)
    # Simulate a legacy preference and an unavailable metadata backend.  The
    # handler must never call it for current-work target selection.
    monkeypatch.setattr(rc, "bound_server_for_session", lambda _sid: (_ for _ in ()).throw(RuntimeError("metadata down")))
    monkeypatch.setattr(rc, "touch_session", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(rc._ACTIONS, "run", fake_run)

    result = json.loads(rc.remote_cluster_handler({
        "action": "run", "node": "server-b", "chat_session_id": "memomics-a1b2c3d4",
    }))
    assert result == {"ok": True, "node": "server-b"}
    assert dispatched[-1][0]["host"] == "b.example"
    assert dispatched[-1][1]["chat_session_id"] == "memomics-a1b2c3d4"

    needs_node = json.loads(rc.remote_cluster_handler({
        "action": "run", "chat_session_id": "memomics-a1b2c3d4",
    }))
    assert needs_node["status"] == "needs_node"
    assert len(dispatched) == 1


def test_kernel_connection_fingerprint_changes_after_same_server_profile_edit(monkeypatch):
    first = _cfg({"server-a": {"host": "old.example", "user": "alice", "port": 2201, "key": "old.key"}})
    second = _cfg({"server-a": {"host": "new.example", "user": "alice", "port": 2201, "key": "new.key"}})
    monkeypatch.setattr(ck, "_cluster_cfg", lambda: first)
    old = ck._resolve_target(session_id="")
    monkeypatch.setattr(ck, "_cluster_cfg", lambda: second)
    new = ck._resolve_target(session_id="")
    assert old["server_id"] == new["server_id"] == "server-a"
    assert old["connection_fingerprint"] != new["connection_fingerprint"]
    assert ck._kernel_key("s", old, "python", "RNA") != ck._kernel_key("s", new, "python", "RNA")


def test_recorded_r_session_uses_complete_snapshot_after_profile_disappears():
    record = {
        "node": "server-a", "host": "old.example", "user": "alice", "port": 2201,
        "key": "C:/keys/old", "workdir": "/old/work", "extra_ssh_options": ["-J", "jump"],
    }
    node, name, err = cs._snapshot_node_for_record(_cfg({}), record)
    assert err is None and name == "server-a"
    assert node["host"] == "old.example" and node["user"] == "alice"
    assert node["port"] == 2201 and node["key"] == "C:/keys/old"
    assert node["extra_ssh_options"] == ["-J", "jump"]


def test_recorded_r_session_keeps_explicit_empty_key_and_options():
    """New snapshots must not borrow credentials from an edited profile."""
    cfg = _cfg({"server-a": {
        "host": "new.example", "user": "new-user", "port": 2222,
        "key": "C:/keys/new", "extra_ssh_options": ["-J", "new-bastion"],
    }})
    record = {
        "node": "server-a", "host": "old.example", "user": "alice", "port": 2201,
        "key": "", "workdir": "/old/work", "extra_ssh_options": [],
        "job_dir": "/old/work/jobs", "scheduler": "gridengine", "partition": "",
        "queue": "", "proxy_jump": "", "session": {},
        "connection_snapshot_version": 1,
    }
    node, _name, err = cs._snapshot_node_for_record(cfg, record)
    assert err is None
    assert node["host"] == "old.example" and node["port"] == 2201
    assert node["key"] == ""
    assert node["extra_ssh_options"] == []
    assert node["proxy_jump"] == "" and node["session"] == {}


def test_kernel_job_snapshot_keeps_explicit_empty_values_and_drops_error_payload():
    target = ck._target_from_job_record({
        "host": "old.example", "user": "", "port": 2201, "key": "",
        "extra_opts": [], "workdir": "", "node": "server-a", "server_id": "server-a",
    }, {
        "user": "new-user", "port": 2222, "key": "C:/keys/new",
        "extra_opts": ["-J", "new-bastion"], "workdir": "/new/work",
        "error_payload": {"status": "bound_server_missing"},
    })
    assert "error_payload" not in target
    assert target["host"] == "old.example" and target["port"] == 2201
    assert target["user"] == "" and target["key"] == ""
    assert target["extra_opts"] == []
    assert target["workdir"] == "~"


def test_submit_records_complete_connection_snapshot(monkeypatch):
    """No SSH: fake submit and inspect the immutable record written locally."""
    cfg = _cfg({})
    cfg.update({
        "host": "old.example", "user": "alice", "port": 2201,
        "key": "C:/keys/old", "workdir": "/old/work", "job_dir": "/old/work/jobs",
        "scheduler": "slurm", "partition": "old-part", "queue": "old-queue",
        "proxy_jump": "old-bastion", "extra_ssh_options": ["-J", "old-bastion"],
        "timeout": 30, "_name": "server-a",
    })
    captured = []

    class FakeConn:
        def execute(self, command, **_kwargs):
            assert command.startswith("sbatch ")
            return {"output": "Submitted batch job 7788", "returncode": 0}

    monkeypatch.setattr(rc, "_get_conn", lambda _cfg: FakeConn())
    monkeypatch.setattr(rc, "_upload_script", lambda *_args: "/old/work/jobs/script.sh")
    monkeypatch.setattr(rc, "_build_job_script", lambda *_args: ("#!/bin/bash", "/old/out", "/old/err", "/old/pid"))
    monkeypatch.setattr(rc, "_record_job", lambda record: captured.append(dict(record)))
    monkeypatch.setattr(rc, "update_job_state", lambda *_args, **_kwargs: None)

    result = json.loads(rc._action_submit(cfg, {"command": "echo snapshot"}))
    assert result["status"] == "submitted" and len(captured) == 1
    record = captured[0]
    assert record["connection_snapshot_version"] == 1
    # Managed-route provenance markers are intentionally optional: a legacy
    # snapshot must retain its historic wire shape rather than emitting an
    # empty field that a later reader could misinterpret as V4/V5 provenance.
    legacy_required_fields = tuple(
        field for field in rc._CONNECTION_SNAPSHOT_FIELDS
        if field not in {"catalog_v4_ssh_route", "catalog_v5_ssh_route"}
    )
    for field in legacy_required_fields:
        assert field in record
    assert "catalog_v4_ssh_route" not in record
    assert "catalog_v5_ssh_route" not in record
    assert record["node"] == record["server_id"] == "server-a"
    assert record["host"] == "old.example" and record["port"] == 2201
    assert record["key"] == "C:/keys/old"
    assert record["extra_ssh_options"] == ["-J", "old-bastion"]
    assert record["proxy_jump"] == "old-bastion"


def test_historical_job_reconnects_from_snapshot_after_all_servers_are_removed(monkeypatch):
    """No SSH: handler must dispatch a historical job even with disabled config."""
    cfg = _cfg({})
    cfg.update({"enabled": False, "host": "", "user": "", "workdir": "", "nodes": {}})
    record = {
        "job_id": "job-8", "node": "retired-a", "server_id": "retired-a",
        "host": "old.example", "user": "alice", "port": 2201, "key": "C:/keys/old",
        "workdir": "/old/work", "job_dir": "/old/work/jobs", "scheduler": "gridengine",
        "partition": "old-part", "queue": "old-queue", "extra_ssh_options": [],
        "proxy_jump": "", "session": {}, "connection_snapshot_version": 1,
    }
    captured = {}

    def fake_logs(node, args):
        captured["node"] = dict(node)
        captured["args"] = dict(args)
        return json.dumps({"ok": True, "offline": True})

    monkeypatch.setattr(rc, "_load_remote_config", lambda *args, **kwargs: cfg)
    monkeypatch.setattr(rc, "_iter_jobs", lambda *args, **kwargs: [record])
    monkeypatch.setattr(rc, "touch_session", lambda *args, **kwargs: None)
    monkeypatch.setitem(rc._ACTIONS, "logs", fake_logs)

    result = json.loads(rc.remote_cluster_handler({"action": "logs", "job_id": "job-8",
                                                    "chat_session_id": "memomics-a1b2c3d4"}))
    assert result == {"ok": True, "offline": True}
    assert captured["args"]["node"] == "retired-a"
    assert captured["node"]["host"] == "old.example" and captured["node"]["port"] == 2201
    assert captured["node"]["key"] == "C:/keys/old"
    assert captured["node"]["extra_ssh_options"] == []


def test_historical_r_session_reconnects_from_snapshot_after_all_servers_are_removed(monkeypatch):
    """No SSH: recorded daemon actions do not need a currently configured server."""
    cfg = _cfg({})
    cfg.update({"enabled": False, "host": "", "user": "", "workdir": "", "nodes": {}})
    record = {
        "id": "s-old", "node": "retired-r", "server_id": "retired-r",
        "host": "r-old.example", "user": "alice", "port": 2201, "key": "",
        "workdir": "/old/r", "job_dir": "/old/r/jobs", "scheduler": "none",
        "partition": "", "queue": "", "extra_ssh_options": [], "proxy_jump": "",
        "session": {}, "connection_snapshot_version": 1,
    }
    captured = {}

    def fake_status(node, args):
        captured["node"] = dict(node)
        captured["args"] = dict(args)
        return json.dumps({"ok": True, "offline": True})

    monkeypatch.setattr(rc, "_load_remote_config", lambda *args, **kwargs: cfg)
    monkeypatch.setattr(cs, "find_session", lambda sid: dict(record) if sid == "s-old" else None)
    monkeypatch.setattr(rc, "touch_session", lambda *args, **kwargs: None)
    monkeypatch.setitem(rc._ACTIONS, "session_status", fake_status)

    result = json.loads(rc.remote_cluster_handler({"action": "session_status", "session_id": "s-old",
                                                    "chat_session_id": "memomics-a1b2c3d4"}))
    assert result == {"ok": True, "offline": True}
    assert captured["args"]["node"] == "retired-r"
    assert captured["node"]["host"] == "r-old.example" and captured["node"]["port"] == 2201
    assert captured["node"]["key"] == "" and captured["node"]["extra_ssh_options"] == []


def test_first_named_server_preserves_legacy_single_host_bindings_and_default(monkeypatch):
    """Promoting a single-host config must retain old binding/default semantics."""
    remote = {
        "enabled": True, "host": "old.example", "user": "alice", "port": 2201,
        "key": "C:/keys/old", "workdir": "/old/work", "job_dir": "/old/work/jobs",
        "scheduler": "gridengine", "partition": "old-part", "queue": "old-queue",
        "timeout": 45, "proxy_jump": "old-bastion",
        "extra_ssh_options": ["-J", "old-bastion"],
    }
    nodes = {}
    assert web_server._promote_legacy_single_server(remote, nodes) is True
    nodes["server-b"] = {"host": "new.example", "user": "bob", "port": 2202,
                         "key": "C:/keys/new", "workdir": "/new/work"}
    assert remote["default_node"] == "legacy-default"
    legacy = nodes["legacy-default"]
    assert legacy["host"] == "old.example" and legacy["port"] == 2201
    assert legacy["key"] == "C:/keys/old"
    assert legacy["extra_ssh_options"] == ["-J", "old-bastion"]

    cfg = _cfg(nodes)
    cfg.update({key: value for key, value in remote.items() if key != "nodes"})
    cfg["nodes"] = nodes
    monkeypatch.setattr(rc, "bound_server_for_session", lambda _sid: "legacy-default")
    bound, bound_name, err = rc.select_node_for_session(cfg, "", "memomics-a1b2c3d4")
    assert err is None and bound_name == "legacy-default"
    assert bound["host"] == "old.example" and bound["port"] == 2201
    assert bound["key"] == "C:/keys/old"
    unbound, unbound_name, err = rc.select_node_for_session(cfg, "", "")
    assert err is None and unbound_name == "legacy-default"
    assert unbound["host"] == "old.example" and unbound["port"] == 2201


def test_kernel_logs_uses_job_snapshot_even_when_current_binding_read_fails(monkeypatch):
    """No SSH: assert the generated subprocess argv uses the stored target."""
    from memomics.bio_tools import node_state as ns

    record = {
        "job_id": "job-7", "host": "old.example", "user": "alice", "port": 2201,
        "key": "C:/keys/old", "extra_opts": ["-J", "jump"], "workdir": "/old/work",
        "node": "server-a", "log": "$HOME/jobs/out.log", "status": "running",
    }
    monkeypatch.setattr(ns, "list_jobs", lambda *args, **kwargs: [record])
    monkeypatch.setattr(rc, "bound_server_for_session", lambda sid: (_ for _ in ()).throw(RuntimeError("db locked")))
    captured = {}

    def fake_ssh(host, user="", port=22, key="", extra_opts=None):
        captured.update(host=host, user=user, port=port, key=key, extra_opts=list(extra_opts or []))
        return ["ssh", "fake"]

    monkeypatch.setattr(ck, "_ssh_cmd", fake_ssh)
    monkeypatch.setattr(ck.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="old log", stderr="", returncode=0))
    result = json.loads(ck.cluster_kernel_tool(action="logs", job_id="job-7"))
    assert result["ok"] is True
    assert captured == {"host": "old.example", "user": "alice", "port": 2201,
                        "key": "C:/keys/old", "extra_opts": ["-J", "jump"]}


def test_managed_account_profiles_do_not_inherit_legacy_credentials_or_share_connections():
    raw_nodes = {
        "account-alice": {
            "connection_profile": True, "host": "shared.example", "user": "alice",
            "key": "C:/keys/alice", "workdir": "/home/alice", "extra_ssh_options": ["-J", "jump-a"],
        },
        "account-bob": {
            "connection_profile": True, "host": "shared.example", "user": "bob",
            "key": "", "workdir": "/home/bob", "extra_ssh_options": ["-J", "jump-b"],
        },
        "incomplete": {"connection_profile": True, "user": "nobody"},
        "legacy-alias": {},
    }
    cfg = _cfg(rc._normalize_nodes(raw_nodes))
    cfg.update({"host": "legacy.example", "user": "legacy-user", "key": "C:/keys/legacy",
                "workdir": "/legacy", "port": 2299, "extra_ssh_options": ["-J", "legacy-jump"]})
    table = rc._node_table(cfg)
    assert table["account-alice"]["host"] == table["account-bob"]["host"] == "shared.example"
    assert table["account-alice"]["user"] == "alice" and table["account-bob"]["user"] == "bob"
    assert table["account-bob"]["key"] == ""
    assert table["account-bob"]["workdir"] == "/home/bob"
    assert table["account-bob"]["extra_ssh_options"] == ["-J", "jump-b"]
    assert rc._conn_key(table["account-alice"]) != rc._conn_key(table["account-bob"])
    assert table["incomplete"]["host"] == ""
    assert table["legacy-alias"]["host"] == "legacy-alias"
    assert table["legacy-alias"]["user"] == "legacy-user"


def test_legacy_node_label_edit_keeps_shared_inheritance():
    edited = web_server._server_payload_to_node({"name": "Renamed legacy"}, {"host": "legacy-alias"})
    assert "connection_profile" not in edited
    cfg = _cfg({"legacy-alias": edited})
    cfg.update({"host": "old.example", "user": "legacy-user", "key": "C:/keys/legacy", "workdir": "/legacy"})
    node = rc._node_table(cfg)["legacy-alias"]
    assert node["user"] == "legacy-user" and node["key"] == "C:/keys/legacy"


def test_partial_cluster_config_save_preserves_raw_managed_profiles(tmp_path, monkeypatch):
    import yaml

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "remote:\n"
        "  enabled: false\n"
        "  user: legacy-user\n"
        "  nodes:\n"
        "    account-a:\n"
        "      connection_profile: true\n"
        "      host: shared.example\n"
        "      user: alice\n"
        "      key: ''\n"
        "      workdir: ''\n"
        "      extra_ssh_options: []\n"
        "    account-b:\n"
        "      connection_profile: true\n"
        "      host: shared.example\n"
        "      user: bob\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rc, "_get_config_path", lambda: config_path)
    monkeypatch.setattr(rc, "_CFG_CACHE", {"mtime": None, "cfg": None})
    monkeypatch.setattr(web_server, "_cluster_mod", lambda: rc)
    web_server._cluster_write_config({"enabled": True})
    remote = yaml.safe_load(config_path.read_text(encoding="utf-8"))["remote"]
    assert remote["nodes"]["account-a"]["connection_profile"] is True
    assert remote["nodes"]["account-a"]["key"] == ""
    assert remote["nodes"]["account-a"]["extra_ssh_options"] == []
    assert remote["nodes"]["account-b"]["user"] == "bob"


def test_retired_binding_shim_never_reads_chat_metadata(monkeypatch):
    """Kernel/tool compatibility callers cannot turn a stale preference into a gate."""
    monkeypatch.setattr(rc, "_get_config_path", lambda: (_ for _ in ()).throw(RuntimeError("metadata/config unavailable")))
    assert rc.bound_server_for_session("memomics-a1b2c3d4") == ""


def test_historical_target_without_snapshot_never_uses_deleted_profile_as_literal_host():
    _node, _name, err = rc.select_node_for_session(_cfg({}), "retired-server", "memomics-a1b2c3d4",
                                                    recorded_target=True)
    assert json.loads(err)["status"] == "historical_target_missing"


def test_kernel_jobs_uses_recorded_fallback_and_hides_internal_record_key_when_binding_fails(monkeypatch):
    from memomics.bio_tools import debate_analysis, node_state as ns

    sid = "memomics-a1b2c3d4"
    records = [{"job_id": "job-1", "session_id": sid, "host": "old.example", "user": "alice",
                "port": 2201, "key": "", "extra_opts": [], "_record_key": "job-1@internal"}]
    polled = []
    monkeypatch.setattr(debate_analysis, "get_session_sid", lambda: sid)
    monkeypatch.setattr(ck, "_cluster_cfg", lambda: {"host": "", "nodes": {}})
    monkeypatch.setattr(rc, "bound_server_for_session", lambda _sid: "deleted-profile")
    monkeypatch.setattr(ns, "promote_queued", lambda: {"ok": True})
    monkeypatch.setattr(ns, "poll_jobs", lambda *args: polled.append(args) or {"checked": 1})
    monkeypatch.setattr(ns, "list_jobs", lambda *args, **kwargs: [dict(item) for item in records])
    result = json.loads(ck.cluster_kernel_tool(action="jobs"))
    assert result["ok"] is True and result["node"] == "recorded"
    assert result["target_fallback"] == "recorded" and polled[-1][:2] == ("", "")
    assert "_record_key" not in result["jobs"][0]


def test_cluster_config_metadata_read_failure_blocks_mutation(monkeypatch):
    class BrokenStore:
        def sessions_bound_to_server(self, _server_id):
            raise RuntimeError("state db locked")

    monkeypatch.setattr(web_server, "_session_metadata", lambda: BrokenStore())
    with pytest.raises(MetadataError, match="cannot verify bound chat sessions"):
        web_server._active_bound_sessions("server-a")


def test_deprecated_binding_preference_does_not_block_a_running_chat(monkeypatch):
    sid = "memomics-a1b2c3d4"
    sessions = {sid: {"id": sid, "running_task": None, "running_agent": None}}
    writes = []

    class Store:
        def set_session_cluster_server(self, got_sid, server_id):
            writes.append((got_sid, server_id))
            return {"cluster_server_id": server_id}

    class Request:
        async def json(self):
            sessions[sid]["running_task"] = "became-running-during-await"
            return {"cluster_server_id": "server-a"}

    monkeypatch.setattr(web_server, "_sessions", sessions)
    monkeypatch.setattr(web_server, "_session_metadata", lambda: Store())
    monkeypatch.setattr(web_server, "_cluster_server_by_id", lambda _id: {"id": "server-a", "node_id": "server-a"})
    response = asyncio.run(web_server.set_session_cluster_server(sid, Request()))
    assert response["ok"] is True and response["deprecated"] is True
    assert writes == [(sid, "server-a")]


def test_new_session_ignores_legacy_cluster_server_id(monkeypatch):
    created = []

    class Store:
        def has_project(self, _project_id):
            return True

        def get_session_metadata(self, _sid):
            return {"project_id": None, "cluster_server_id": None}

        def set_session_project(self, _sid, project_id):
            assert project_id is None
            return {"project_id": None, "cluster_server_id": None}

    class Request:
        async def body(self):
            return b'{"cluster_server_id":"missing-server"}'

    monkeypatch.setattr(web_server, "_session_metadata", lambda: Store())
    monkeypatch.setattr(web_server, "_cluster_server_by_id", lambda _id: None)
    monkeypatch.setattr(web_server, "_sessions", {})
    monkeypatch.setattr(web_server, "_create_session", lambda title: created.append(title) or {
        "id": "memomics-a1b2c3d4", "title": title, "model_config": {},
    })
    response = asyncio.run(web_server.new_session(Request()))
    assert response["id"] == "memomics-a1b2c3d4"
    assert response["cluster_server_id"] is None
    assert created == ["新会话"]


def test_cluster_exec_skips_broken_metadata_for_all_current_work(monkeypatch):
    captured = []

    class BrokenStore:
        def get_session_metadata(self, _sid):
            raise RuntimeError("state db unavailable")

    class Request:
        def __init__(self, payload):
            self.payload = payload

        async def json(self):
            return self.payload

    def handler(args):
        captured.append(dict(args))
        return json.dumps({"ok": True})

    monkeypatch.setattr(web_server, "_known_session", lambda _sid: {"id": _sid})
    monkeypatch.setattr(web_server, "_session_metadata", lambda: BrokenStore())
    monkeypatch.setattr(web_server, "_cluster_mod", lambda: SimpleNamespace(remote_cluster_handler=handler))
    historical = asyncio.run(web_server.api_cluster_exec(Request({
        "action": "logs", "job_id": "8", "node": "retired-a", "chat_session_id": "memomics-a1b2c3d4",
    })))
    assert historical["ok"] is True and captured[-1]["chat_session_id"] == "memomics-a1b2c3d4"
    current = asyncio.run(web_server.api_cluster_exec(Request({
        "action": "run", "command": "allowed", "node": "server-b", "chat_session_id": "memomics-a1b2c3d4",
    })))
    assert current["ok"] is True and len(captured) == 2
    assert captured[-1]["node"] == "server-b"


def test_duplicate_historical_job_ids_are_disambiguated_or_rejected_without_dispatch(monkeypatch):
    records = [
        {"job_id": "42", "server_id": "server-a", "node": "server-a", "session_id": "chat-a",
         "host": "a.example", "user": "alice", "port": 2201, "key": "", "workdir": "/a",
         "extra_ssh_options": [], "proxy_jump": "", "scheduler": "none", "session": {}},
        {"job_id": "42", "server_id": "server-b", "node": "server-b", "session_id": "chat-b",
         "host": "b.example", "user": "bob", "port": 2202, "key": "", "workdir": "/b",
         "extra_ssh_options": [], "proxy_jump": "", "scheduler": "none", "session": {}},
    ]
    dispatched = []
    monkeypatch.setattr(rc, "_iter_jobs", lambda *_a, **_k: records)
    monkeypatch.setattr(rc, "_load_remote_config", lambda *_a, **_k: _cfg({}))
    monkeypatch.setattr(rc, "touch_session", lambda *_a, **_k: None)
    monkeypatch.setitem(rc._ACTIONS, "cancel", lambda node, args: dispatched.append((dict(node), dict(args))) or "{}")
    ambiguous = json.loads(rc.remote_cluster_handler({"action": "cancel", "job_id": "42"}))
    assert ambiguous["status"] == "ambiguous_job" and dispatched == []
    selected = json.loads(rc.remote_cluster_handler({"action": "cancel", "job_id": "42", "chat_session_id": "chat-a"}))
    assert selected == {}
    assert dispatched[-1][0]["host"] == "a.example" and dispatched[-1][0]["port"] == 2201


def test_selected_historical_job_record_reaches_real_status_logs_and_cancel_actions(monkeypatch):
    """A full-ledger, chat-owned record must not be re-resolved to a newer twin."""
    cfg = _cfg({})
    cfg.update({"enabled": False, "host": "", "user": "", "nodes": {},
                "timeout": 300, "max_output_chars": 20_000})
    selected = {
        "job_id": "42", "node": "server-a", "server_id": "server-a", "session_id": "chat-b",
        "host": "snapshot.example", "user": "alice", "port": 2201, "key": "",
        "workdir": "/snapshot/work", "job_dir": "/snapshot/jobs", "scheduler": "none",
        "partition": "", "queue": "", "timeout": 30, "extra_ssh_options": [], "proxy_jump": "",
        "stdout": "/logs/chat-b.out", "stderr": "/logs/chat-b.err", "pid_file": "/pids/chat-b.pid",
        "name": "chat-b-job", "connection_snapshot_version": 1,
    }
    wrong = dict(selected, session_id="chat-a", stdout="/logs/chat-a.out", stderr="/logs/chat-a.err",
                 pid_file="/pids/chat-a.pid", name="chat-a-job")
    records = [selected] + [{"job_id": "noise-%03d" % index, "node": "server-a"} for index in range(600)] + [wrong]
    commands = []

    class Conn:
        def execute(self, command, **_kwargs):
            commands.append(command)
            return {"output": "STATE=RUNNING", "returncode": 0}

    def iter_records(limit=200):
        return list(records) if limit is None else list(records[-limit:])

    monkeypatch.setattr(rc, "_load_remote_config", lambda *args, **kwargs: cfg)
    monkeypatch.setattr(rc, "_iter_jobs", iter_records)
    monkeypatch.setattr(rc, "_get_conn", lambda _cfg: Conn())
    monkeypatch.setattr(rc, "touch_session", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rc, "update_job_state", lambda *_args, **_kwargs: None)

    for action, marker in (("status", "/pids/chat-b.pid"), ("logs", "/logs/chat-b.out"),
                           ("cancel", "/pids/chat-b.pid")):
        result = json.loads(rc.remote_cluster_handler({
            "action": action, "job_id": "42", "chat_session_id": "chat-b",
        }))
        assert result.get("status") == "ok"
        assert marker in commands[-1]
        assert "chat-a" not in commands[-1]


def test_unrecorded_explicit_job_target_remains_compatible(monkeypatch):
    """Explicit current targets may still query a scheduler job absent from the ledger."""
    cfg = _cfg({"server-a": {"host": "a.example", "user": "alice", "scheduler": "none"}})
    cfg.update({"timeout": 300, "max_output_chars": 20_000})
    commands = []

    class Conn:
        def execute(self, command, **_kwargs):
            commands.append(command)
            return {"output": "not running", "returncode": 0}

    monkeypatch.setattr(rc, "_load_remote_config", lambda *args, **kwargs: cfg)
    monkeypatch.setattr(rc, "_iter_jobs", lambda limit=200: [])
    monkeypatch.setattr(rc, "_get_conn", lambda _cfg: Conn())
    monkeypatch.setattr(rc, "touch_session", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rc, "update_job_state", lambda *_args, **_kwargs: None)

    result = json.loads(rc.remote_cluster_handler({"action": "status", "job_id": "unrecorded", "node": "server-a"}))
    assert result.get("status") == "ok"
    assert "unrecorded" in commands[-1]
