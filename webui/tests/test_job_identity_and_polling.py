"""Offline regression coverage for multi-server job identity.

These tests only read/write a temporary ``cluster_jobs.json`` and monkeypatch
the SSH subprocess boundary.  They never contact a real cluster.
"""

from __future__ import annotations

import concurrent.futures
import threading
from types import SimpleNamespace

import pytest

from memomics.bio_tools import job_watcher as watcher
from memomics.bio_tools import node_state as state


def _use_temporary_jobs(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMOMICS_HOME", str(tmp_path))
    monkeypatch.setattr(state, "_current_sid", lambda: "")


def _record_for(rows, *, user):
    return next(row for row in rows if row.get("user") == user)


def test_legacy_bare_key_is_readable_and_uniquely_updatable(monkeypatch, tmp_path):
    _use_temporary_jobs(monkeypatch, tmp_path)
    state.save_jobs({"jobs": {
        "legacy-19": {
            "job_id": "legacy-19", "status": "running", "pid": "19",
            "host": "legacy.example", "user": "alice", "port": 2201,
            "key": "", "extra_opts": [],
        },
    }})

    rows = state.list_jobs()
    assert rows == [{**rows[0], "_record_key": "legacy-19"}]
    assert rows[0]["job_id"] == "legacy-19"
    assert state.update_job("legacy-19", status="done") is True

    raw = state.load_jobs()["jobs"]
    assert raw["legacy-19"]["status"] == "done"
    assert "_record_key" not in raw["legacy-19"]


def test_same_scheduler_id_on_two_logins_is_not_overwritten_or_bare_updated(monkeypatch, tmp_path):
    _use_temporary_jobs(monkeypatch, tmp_path)
    for user, port, key in (("alice", 2201, "C:/keys/alice"), ("bob", 2202, "")):
        state.register_job("7788", status="running", pid="100", host="login.example",
                           user=user, port=port, key=key, extra_opts=[], session_id=user,
                           server_id="server-%s" % user)

    rows = state.list_jobs()
    assert len(rows) == 2
    assert len({row["_record_key"] for row in rows}) == 2
    assert all(row["_record_key"].startswith("7788@") for row in rows)
    assert state.update_job("7788", status="cancelled") is False
    assert all(row["status"] == "running" for row in state.list_jobs())

    assert state.update_job("7788", server_id="server-bob", status="queued") is True
    assert _record_for(state.list_jobs(), user="bob")["status"] == "queued"

    alice = _record_for(rows, user="alice")
    assert state.update_job("7788", record_key=alice["_record_key"], status="done") is True
    after = {row["user"]: row for row in state.list_jobs()}
    assert after["alice"]["status"] == "done"
    assert after["bob"]["status"] == "queued"
    assert after["bob"]["key"] == "" and after["bob"]["extra_opts"] == []


def test_poll_groups_same_host_by_each_record_connection_and_honors_empty_values(monkeypatch, tmp_path):
    _use_temporary_jobs(monkeypatch, tmp_path)
    profiles = (
        ("alice", 2201, "C:/keys/alice", ["-J", "alice-jump"]),
        ("bob", 2202, "C:/keys/bob", ["-J", "bob-jump"]),
        ("", 2203, "", []),
    )
    for index, (user, port, key, options) in enumerate(profiles):
        state.register_job(str(900 + index), status="running", pid=str(100 + index),
                           host="shared-login.example", user=user, port=port, key=key,
                           extra_opts=options, session_id="chat-%s" % index)

    calls = []

    def fake_poll(host, jobs, user="", port=22, key="", extra_opts=None):
        calls.append((host, user, port, key, tuple(extra_opts or []), set(jobs)))
        return {"checked": len(jobs), "jobs": {}}

    monkeypatch.setattr(state, "_poll_one_host", fake_poll)
    result = state.poll_jobs("fallback.example", "fallback-user", 2299,
                             "C:/keys/fallback", ["-J", "fallback-jump"])

    assert result["checked"] == 3
    got = {(host, user, port, key, options) for host, user, port, key, options, _ in calls}
    assert got == {
        ("shared-login.example", "alice", 2201, "C:/keys/alice", ("-J", "alice-jump")),
        ("shared-login.example", "bob", 2202, "C:/keys/bob", ("-J", "bob-jump")),
        ("shared-login.example", "", 2203, "", ()),
    }
    assert all(len(record_keys) == 1 and next(iter(record_keys)).startswith("9")
               for *_, record_keys in calls)


def test_poll_uses_fallback_only_for_missing_legacy_connection_fields(monkeypatch, tmp_path):
    _use_temporary_jobs(monkeypatch, tmp_path)
    state.save_jobs({"jobs": {
        "legacy-missing": {"job_id": "legacy-missing", "status": "running", "pid": "17"},
    }})
    calls = []
    monkeypatch.setattr(
        state, "_poll_one_host",
        lambda host, jobs, user="", port=22, key="", extra_opts=None:
        (calls.append((host, user, port, key, tuple(extra_opts or []), set(jobs))) or
         {"checked": len(jobs), "jobs": {}}),
    )

    state.poll_jobs("fallback.example", "fallback-user", 2299,
                    "C:/keys/fallback", ["-J", "fallback-jump"])
    assert calls == [("fallback.example", "fallback-user", 2299, "C:/keys/fallback",
                      ("-J", "fallback-jump"), {"legacy-missing"})]


def test_live_state_cache_isolated_by_full_login_identity(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "_state_cache", {})

    def fake_probe(host, user="", port=22, key="", extra_opts=None, workdir="~"):
        calls.append((host, user, port, key, tuple(extra_opts or []), workdir))
        return {"ok": True, "host": host, "user": user, "port": port}

    monkeypatch.setattr(state, "probe", fake_probe)
    first = state.node_state("shared-login.example", "alice", 2201, "C:/keys/alice",
                             ["-J", "alice-jump"], "/work")
    second = state.node_state("shared-login.example", "bob", 2202, "C:/keys/bob",
                              ["-J", "bob-jump"], "/work")
    first_again = state.node_state("shared-login.example", "alice", 2201, "C:/keys/alice",
                                   ["-J", "alice-jump"], "/work")

    assert first["cached"] is False and second["cached"] is False
    assert first_again["cached"] is True
    assert calls == [
        ("shared-login.example", "alice", 2201, "C:/keys/alice", ("-J", "alice-jump"), "/work"),
        ("shared-login.example", "bob", 2202, "C:/keys/bob", ("-J", "bob-jump"), "/work"),
    ]


def test_concurrent_same_job_id_registrations_keep_both_login_accounts(monkeypatch, tmp_path):
    _use_temporary_jobs(monkeypatch, tmp_path)
    start = threading.Barrier(2)

    def register(user, port):
        start.wait(timeout=5)
        state.register_job("parallel-id", status="running", pid=str(port),
                           host="shared-login.example", user=user, port=port,
                           key="C:/keys/%s" % user, extra_opts=[], session_id="chat-%s" % user)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(register, "alice", 2201), pool.submit(register, "bob", 2202)]
        for future in futures:
            future.result(timeout=10)

    rows = [row for row in state.list_jobs() if row["job_id"] == "parallel-id"]
    assert {row["user"] for row in rows} == {"alice", "bob"}
    assert len({row["_record_key"] for row in rows}) == 2


def test_concurrent_exact_record_updates_keep_both_fields(monkeypatch, tmp_path):
    _use_temporary_jobs(monkeypatch, tmp_path)
    state.register_job("parallel-update", status="running", pid="111", host="cluster.example",
                       user="alice", port=2201, key="C:/keys/alice", extra_opts=[])
    row = state.list_jobs()[0]
    start = threading.Barrier(2)

    def update(**fields):
        start.wait(timeout=5)
        assert state.update_job("parallel-update", record_key=row["_record_key"], **fields) is True

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update, checkpoint_a=True), pool.submit(update, checkpoint_b=True)]
        for future in futures:
            future.result(timeout=10)

    saved = state.list_jobs()[0]
    assert saved["checkpoint_a"] is True and saved["checkpoint_b"] is True


@pytest.mark.parametrize(("exit_code", "expected"), (("0", "done"), ("7", "failed")))
def test_composite_record_exit_file_updates_the_exact_job(monkeypatch, tmp_path, exit_code, expected):
    _use_temporary_jobs(monkeypatch, tmp_path)
    state.register_job("same-id", status="running", pid="4242", host="cluster.example",
                       user="alice", port=2201, key="C:/keys/alice", extra_opts=[],
                       exit_file="/tmp/same-id.exit", session_id="chat-a")
    row = state.list_jobs()[0]

    def fake_run(argv, **_kwargs):
        script = argv[-1]
        assert "EXIT|%s|" % row["_record_key"] in script
        return SimpleNamespace(
            stdout="DEAD|4242\nEXIT|%s|EXIT:%s\n" % (row["_record_key"], exit_code),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(state.subprocess, "run", fake_run)
    result = state.poll_jobs()
    assert result["checked"] == 1
    updated = state.list_jobs()[0]
    assert updated["status"] == expected
    assert updated["_record_key"] == row["_record_key"]


def test_watcher_marks_duplicate_scheduler_ids_with_their_own_record_keys(monkeypatch, tmp_path):
    _use_temporary_jobs(monkeypatch, tmp_path)
    for user in ("alice", "bob"):
        state.register_job("shared-complete", status="done", host="login.example", user=user,
                           port=2201 if user == "alice" else 2202,
                           key="C:/keys/%s" % user, extra_opts=[], session_id="chat-%s" % user)
    state.register_job("keep-watcher-active", status="running", pid="123", host="login.example",
                       user="runner", port=2299, key="C:/keys/runner", extra_opts=[],
                       session_id="chat-active")
    monkeypatch.setattr(state, "_poll_one_host",
                        lambda _host, jobs, *_args, **_kwargs:
                        {"checked": len(jobs), "jobs": {}})
    monkeypatch.setattr(state, "promote_queued", lambda: {"ok": True, "started": []})
    monkeypatch.setattr(watcher, "append_notification", lambda *_args, **_kwargs: None)

    result = watcher.tick(do_first_check=False)
    assert len(result["notified"]) == 2
    completed = [row for row in state.list_jobs() if row["job_id"] == "shared-complete"]
    assert len(completed) == 2
    assert all(row.get("notified") is True for row in completed)
