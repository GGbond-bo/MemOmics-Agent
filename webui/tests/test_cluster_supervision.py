# -*- coding: utf-8 -*-
"""集群长任务监督：P0 本机证据 + P1 轮询唤醒（2026-10-09）。

背景（用户实测问题）：集群作业提交后本机没有任何痕迹，server 的「外部工作」判定
只看 process_registry + results_dir，于是：
  * 集群还在跑、本机 15 分钟没写盘 → _session_no_live_work=True → 可能被提前归档
  * 会话没有 task_plan/todos → 自检根本不调度 → 没人回来查作业
本文件锁定修复后的口径：

  * cluster_work_evidence 纯本地、不 ssh；归属优先 session_id，老记录靠触点表
  * 终态作业 / 过期记录 / 别人的作业 → 不算本会话的活跃工作（不误保护）
  * _session_no_live_work 遇集群活跃 → False（绝不当作完成信号）
  * poll_jobs 只把**状态变化**写成 transitions（幂等），节点连不上不炸
  * _poll_cluster_jobs_once：投递唤醒 / 会话忙则重排 / 无归属只落账本不猜会话

全部离线：monkeypatch 账本目录 + 假 conn，不碰真 SSH、不碰真集群。
"""
import asyncio
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from memomics import bio_tools as _bt  # noqa: E402
from memomics.bio_tools import remote_cluster as rc  # noqa: E402
from memomics.bio_tools import cluster_session as cs  # noqa: E402
import server  # noqa: E402  (webui 目录由 tests/conftest.py 加入 sys.path)

NOW = time.time()
MY_SID = "memomics-test-super"


def _module_instances(dotted, real):
    """同名模块可能被别的测试换成 importlib 加载的副本（test_cluster_session.py 的坑，
    2026-10-09 实测全量跑挂三条）。运行时 `from ... import x` 拿到的是 sys.modules 里那个，
    所以补丁必须打到**每一个**实例上，否则线上代码绕开补丁去读真账本。"""
    out = [real]
    for cand in (sys.modules.get(dotted), getattr(_bt, dotted.split(".")[-1], None)):
        if cand is not None and all(cand is not o for o in out):
            out.append(cand)
    return out


def _ts(hours_ago=0.0):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(NOW - hours_ago * 3600))


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """把 remote/ 账本目录整体指到 tmp（jobs.jsonl / job_states.json / 触点 / 会话注册表）。"""
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    for _r in _module_instances("memomics.bio_tools.remote_cluster", rc):
        monkeypatch.setattr(_r, "_records_path", lambda: remote_dir / "jobs.jsonl")
        monkeypatch.setattr(_r, "_supervision_dir", lambda: remote_dir)
    for _c in _module_instances("memomics.bio_tools.cluster_session", cs):
        monkeypatch.setattr(_c, "_sessions_path", lambda: remote_dir / "sessions.json")
    return remote_dir


def _job(node="ssh23", job_id="42", session_id="", hours_ago=0.0, **extra):
    rec = {"ts": _ts(hours_ago), "node": node, "host": "h", "user": "u",
           "scheduler": "none", "job_id": job_id, "name": "musc",
           "stdout": "/remote/log.txt", "stderr": "/remote/log.txt",
           "pid_file": "/remote/j.pid", "command": "Rscript x.R"}
    if session_id:
        rec["session_id"] = session_id
    rec.update(extra)
    return rec


def _write_jobs(remote_dir, *recs):
    with open(remote_dir / "jobs.jsonl", "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_states(remote_dir, states):
    (remote_dir / "job_states.json").write_text(
        json.dumps({"version": 1, "jobs": states}, ensure_ascii=False), encoding="utf-8")


def _state(node, job_id, state, checked_at=None):
    return {"%s|%s" % (node, job_id): {"node": node, "job_id": job_id, "state": state,
                                       "checked_at": checked_at or _ts(0.1)}}


def _write_sessions(remote_dir, reg):
    (remote_dir / "sessions.json").write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")


# ==================== P0：证据（纯本地） ====================

def test_my_running_job_is_live_evidence(ledger):
    _write_jobs(ledger, _job(session_id=MY_SID))
    _write_states(ledger, _state("ssh23", "42", "running"))
    ev = rc.cluster_work_evidence(MY_SID)
    assert ev["live"] is True
    assert ev["items"][0]["job_id"] == "42" and ev["items"][0]["state"] == "running"
    assert any("ssh23" in r for r in ev["reasons"])


def test_terminal_job_is_not_evidence(ledger):
    _write_jobs(ledger, _job(session_id=MY_SID))
    _write_states(ledger, _state("ssh23", "42", "done"))
    assert rc.cluster_work_evidence(MY_SID)["live"] is False


def test_failed_and_cancelled_are_terminal(ledger):
    for st in ("failed", "cancelled"):
        _write_jobs(ledger, _job(session_id=MY_SID))
        _write_states(ledger, _state("ssh23", "42", st))
        assert rc.cluster_work_evidence(MY_SID)["live"] is False, st


def test_submitted_state_counts_as_live_without_poll(ledger):
    """提交后、还没轮询过（24h 内）→ 算活跃（否则提交完就没人管了）。"""
    _write_jobs(ledger, _job(session_id=MY_SID, hours_ago=1.0))
    _write_states(ledger, _state("ssh23", "42", "submitted"))
    assert rc.cluster_work_evidence(MY_SID)["live"] is True


def test_ancient_submitted_without_refresh_drops_out(ledger):
    """8 天前提交、账本从没刷新 → 不再当活跃工作（避免永久挂住）。"""
    _write_jobs(ledger, _job(session_id=MY_SID, hours_ago=8 * 24))
    _write_states(ledger, _state("ssh23", "42", "submitted", checked_at=_ts(8 * 24)))
    assert rc.cluster_work_evidence(MY_SID)["live"] is False


def test_other_sessions_job_is_not_mine(ledger):
    _write_jobs(ledger, _job(session_id="memomics-other"))
    _write_states(ledger, _state("ssh23", "42", "running"))
    assert rc.cluster_work_evidence(MY_SID)["live"] is False


def test_legacy_record_needs_recent_touch(ledger):
    """老记录（没有 session_id）：只有本会话 12h 内碰过那个节点才算它的活。"""
    _write_jobs(ledger, _job(session_id=""))          # 老格式
    _write_states(ledger, _state("ssh23", "42", "running"))
    assert rc.cluster_work_evidence(MY_SID)["live"] is False
    rc.touch_session("ssh23", "status", session_id=MY_SID)
    assert rc.cluster_work_evidence(MY_SID)["live"] is True
    assert rc.cluster_work_evidence("memomics-someone-else")["live"] is False


def test_touch_on_other_node_does_not_attribute(ledger):
    _write_jobs(ledger, _job(node="ssh3", session_id=""))
    _write_states(ledger, _state("ssh3", "42", "running"))
    rc.touch_session("ssh23", "submit", session_id=MY_SID)
    assert rc.cluster_work_evidence(MY_SID)["live"] is False


def test_active_cluster_session_counts(ledger):
    """常驻 R 会话 status=active 且刚活动过 → 算活跃；停了/太旧不算。"""
    _write_jobs(ledger, _job(session_id="memomics-other"))   # 让作业不干扰
    _write_states(ledger, _state("ssh23", "42", "done"))
    _write_sessions(ledger, {"s-1": {"id": "s-1", "node": "ssh23", "status": "active",
                                     "updated": _ts(0.2), "title": "MuSC 常驻",
                                     "agent_session_id": MY_SID}})
    assert rc.cluster_work_evidence(MY_SID)["live"] is True
    # 注册表 updated 是「上次查询时间」不是心跳 → 30h 没查也还算活着（72h 窗口，宁枉勿纵）
    _write_sessions(ledger, {"s-1": {"id": "s-1", "node": "ssh23", "status": "active",
                                     "updated": _ts(30), "agent_session_id": MY_SID}})
    assert rc.cluster_work_evidence(MY_SID)["live"] is True
    _write_sessions(ledger, {"s-1": {"id": "s-1", "node": "ssh23", "status": "active",
                                     "updated": _ts(100), "agent_session_id": MY_SID}})
    assert rc.cluster_work_evidence(MY_SID)["live"] is False
    # 明确 stopped → 立刻不算（这是用户 stop 会话后的正确语义）
    _write_sessions(ledger, {"s-1": {"id": "s-1", "node": "ssh23", "status": "stopped",
                                     "updated": _ts(0.2), "agent_session_id": MY_SID}})
    assert rc.cluster_work_evidence(MY_SID)["live"] is False


def test_corrupt_ledgers_fail_open(ledger):
    """账本损坏 → 当无证据，绝不抛（失败开放给本机逻辑）。"""
    (ledger / "jobs.jsonl").write_text("{这不是 json\n", encoding="utf-8")
    (ledger / "job_states.json").write_text("{{{", encoding="utf-8")
    (ledger / "session_touches.json").write_text("nope", encoding="utf-8")
    (ledger / "sessions.json").write_text("[]", encoding="utf-8")
    ev = rc.cluster_work_evidence(MY_SID)
    assert ev["live"] is False and ev["items"] == []


def test_evidence_never_touches_ssh(ledger, monkeypatch):
    """证据链必须纯本地：任何 ssh 入口被调用都要炸测试。"""
    def _boom(*a, **kw):
        raise AssertionError("集群证据不该连 ssh")
    monkeypatch.setattr(rc, "_get_conn", _boom)
    monkeypatch.setattr(rc, "_select_node", _boom)
    _write_jobs(ledger, _job(session_id=MY_SID))
    _write_states(ledger, _state("ssh23", "42", "running"))
    assert rc.cluster_work_evidence(MY_SID)["live"] is True


# ==================== P0：server 侧接线 ====================

@pytest.fixture
def no_local_processes(monkeypatch):
    from tools.process_registry import process_registry
    monkeypatch.setattr(process_registry, "count_running", lambda: 0)
    return True


def test_no_live_work_false_when_cluster_live(ledger, tmp_path, no_local_processes):
    """集群在跑 → 绝不当作完成信号（这是提前归档的根因）。"""
    _write_jobs(ledger, _job(session_id=MY_SID))
    _write_states(ledger, _state("ssh23", "42", "running"))
    empty_rd = tmp_path / "results-mine"
    empty_rd.mkdir()
    s = {"id": MY_SID, "results_dir": str(empty_rd)}
    assert server._session_no_live_work(s) is False
    assert server._session_has_active_work(s) is True


def test_no_cluster_no_local_work_still_true(ledger, tmp_path, no_local_processes):
    """没有集群证据、本机也没活动 → 行为保持不变（不误保护）。"""
    empty_rd = tmp_path / "results-empty"
    empty_rd.mkdir()
    s = {"id": MY_SID, "results_dir": str(empty_rd)}
    assert server._session_no_live_work(s) is True
    assert server._session_has_active_work(s) is False


def test_cluster_evidence_failure_is_fail_open(monkeypatch, tmp_path, no_local_processes):
    """证据层炸了 → 按无证据处理（不能因为读台账失败卡死本机监督）。"""
    import memomics.bio_tools.remote_cluster as _rc

    def _boom(*a, **kw):
        raise RuntimeError("台账炸了")
    monkeypatch.setattr(_rc, "cluster_work_evidence", _boom)
    empty_rd = tmp_path / "results-empty2"
    empty_rd.mkdir()
    s = {"id": MY_SID, "results_dir": str(empty_rd)}
    assert server._cluster_work_evidence(s)["live"] is False
    assert server._session_no_live_work(s) is True


# ==================== P1：poll_jobs 状态回写 ====================

class _FakeConn:
    """假 SSH 连接：按队列顺序返回 output。"""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.cmds = []

    def execute(self, cmd, timeout=None):
        self.cmds.append(cmd)
        out = self.outputs.pop(0) if self.outputs else ""
        return {"output": out}


@pytest.fixture
def cluster_ok(monkeypatch):
    monkeypatch.setattr(rc, "remote_cluster_enabled", lambda: True)
    monkeypatch.setattr(rc, "_select_node",
                        lambda cfg, name="": ({"host": "h", "user": "u", "scheduler": "none",
                                               "timeout": 5, "max_output_chars": 400,
                                               "local_root": "", "remote_root": "",
                                               "_name": name}, name, None))
    return True


def test_poll_jobs_transition_then_idempotent(ledger, cluster_ok, monkeypatch):
    _write_jobs(ledger, _job(session_id=MY_SID))
    conn = _FakeConn(["STATE=RUNNING pid=99\nps …",
                      "STATE=RUNNING pid=99\nps …",
                      "[memomics] exit=0\nSTATE=NOT_RUNNING pid=99"])
    monkeypatch.setattr(rc, "_get_conn", lambda cfg, force_reconnect=False: conn)
    cfg = {"enabled": True}

    r1 = rc.poll_jobs(cfg=cfg)
    assert r1["checked"] == 1 and len(r1["transitions"]) == 1
    assert r1["transitions"][0]["state"] == "running"
    assert r1["transitions"][0]["session_id"] == MY_SID     # 归属随记录带出来
    assert rc.load_job_states()["ssh23|42"]["state"] == "running"

    r2 = rc.poll_jobs(cfg=cfg)
    assert r2["checked"] == 0 and r2["transitions"] == []   # 同状态 → 退避，不重复烧 ssh
    assert "ssh23|42" in r2["skipped"]

    r2f = rc.poll_jobs(cfg=cfg, force=True)
    assert r2f["checked"] == 1 and r2f["transitions"] == []  # force 绕过退避，仍不重复报（幂等）

    r3 = rc.poll_jobs(cfg=cfg, force=True)
    assert len(r3["transitions"]) == 1
    assert r3["transitions"][0]["state"] == "done"
    assert r3["transitions"][0]["finished_at"]
    st = rc.load_job_states()["ssh23|42"]
    assert st["state"] == "done"
    # 终态之后不再自动重探（省 ssh）；force=True 是人工复核用的「再查一遍」
    assert rc.poll_jobs(cfg=cfg)["checked"] == 0


def test_poll_backoff_grows_and_resets_on_change(ledger, cluster_ok, monkeypatch):
    """退避曲线：60→120→240…封顶 600；状态一变就重置回 60。"""
    assert rc._poll_backoff_sec(0) == 60.0 and rc._poll_backoff_sec(1) == 120.0
    assert rc._poll_backoff_sec(3) == 480.0 and rc._poll_backoff_sec(9) == 600.0
    _write_jobs(ledger, _job(session_id=MY_SID))
    conn = _FakeConn(["STATE=RUNNING pid=99", "STATE=RUNNING pid=99"])
    monkeypatch.setattr(rc, "_get_conn", lambda cfg, force_reconnect=False: conn)
    assert rc.poll_jobs(cfg={"enabled": True})["checked"] == 1
    assert rc.load_job_states()["ssh23|42"]["probe_count"] == 1
    # 立刻再查 → 被退避拦住
    assert rc.poll_jobs(cfg={"enabled": True})["checked"] == 0
    # 手动把 checked_ts 拨老 → 放行，且计数继续涨
    states = rc.load_job_states()
    states["ssh23|42"]["checked_ts"] = time.time() - 999
    rc.save_job_states(states)
    assert rc.poll_jobs(cfg={"enabled": True})["checked"] == 1
    assert rc.load_job_states()["ssh23|42"]["probe_count"] == 2


def test_poll_jobs_survives_dead_node(ledger, monkeypatch):
    monkeypatch.setattr(rc, "remote_cluster_enabled", lambda: True)
    monkeypatch.setattr(rc, "_select_node", lambda cfg, name="": (None, "", "节点不可用"))
    _write_jobs(ledger, _job(session_id=MY_SID))
    res = rc.poll_jobs(cfg={"enabled": True})
    assert res["ok"] is True and res["checked"] == 0
    assert res["errors"] and "节点不可用" in res["errors"][0]["error"]
    assert rc.load_job_states() == {}                       # 状态没被写坏


def test_poll_jobs_probe_exception_is_contained(ledger, cluster_ok, monkeypatch):
    _write_jobs(ledger, _job(session_id=MY_SID))
    monkeypatch.setattr(rc, "_get_conn", lambda cfg, force_reconnect=False: (_ for _ in ()).throw(OSError("ssh 掉了")))
    res = rc.poll_jobs(cfg={"enabled": True})
    assert res["checked"] == 0 and res["errors"]
    assert res["transitions"] == []


def test_poll_jobs_skips_ancient_records(ledger, cluster_ok):
    _write_jobs(ledger, _job(session_id=MY_SID, hours_ago=30 * 24))
    res = rc.poll_jobs(cfg={"enabled": True})
    assert res["checked"] == 0 and res["skipped"] == ["ssh23|42"]


def test_poll_jobs_disabled_remote_is_noop(ledger, monkeypatch):
    monkeypatch.setattr(rc, "remote_cluster_enabled", lambda: False)
    _write_jobs(ledger, _job(session_id=MY_SID))
    res = rc.poll_jobs(cfg={"enabled": False})
    assert res["checked"] == 0 and "未启用" in (res.get("note") or "")


# ==================== P1：唤醒投递（server 侧） ====================

class _FakeLoop:
    """假事件循环：立即在临时 loop 里执行回调（让 ensure_future 有 running loop）。"""

    def __init__(self):
        self.scheduled = 0

    def call_soon_threadsafe(self, fn, *a):
        self.scheduled += 1
        loop = asyncio.new_event_loop()
        try:
            loop.call_soon(fn)
            loop.run_until_complete(asyncio.sleep(0.05))
        finally:
            loop.close()


@pytest.fixture
def fake_turn(monkeypatch):
    calls = []

    async def _fake(session, text):
        calls.append((session.get("id"), text))
    monkeypatch.setattr(server, "_trigger_agent_turn", _fake)
    return calls


@pytest.fixture
def session_registry():
    """往 server._sessions 放一个测试会话，用完清掉（不污染别的测试）。"""
    sid = "memomics-test-super"
    added = []

    def _add(**extra):
        s = {"id": sid, "messages": [], "results_dir": "", "agent": None}
        s.update(extra)
        server._sessions[sid] = s
        added.append(sid)
        return s

    yield _add
    for k in added:
        server._sessions.pop(k, None)


def _tr(**extra):
    tr = {"node": "ssh23", "job_id": "42", "name": "musc", "state": "done",
          "state_raw": "COMPLETED", "from": "running", "session_id": "memomics-test-super",
          "stdout": "/remote/log.txt"}
    tr.update(extra)
    return tr


def test_dispatch_wakes_owner_session(session_registry, fake_turn):
    s = session_registry()
    loop = _FakeLoop()
    assert server._dispatch_cluster_job_event(_tr(), loop) == "dispatched"
    assert len(s["messages"]) == 1
    msg = s["messages"][0]
    assert msg["source"] == "cluster_job" and "42" in msg["content"] and "done" in msg["content"]
    assert loop.scheduled == 1
    assert fake_turn and fake_turn[0][0] == "memomics-test-super"
    assert "action='logs'" in fake_turn[0][1]


def test_dispatch_queues_when_busy_then_flushes(session_registry, fake_turn):
    s = session_registry(running_agent=object())
    loop = _FakeLoop()
    assert server._dispatch_cluster_job_event(_tr(), loop) == "queued"
    assert s["messages"] == [] and len(server._CLUSTER_EVENT_QUEUE) == 1
    # 会话闲下来 → 下一轮先补投
    s["running_agent"] = None
    out = server._poll_cluster_jobs_once(loop, poll=lambda: {"ok": True, "transitions": [], "checked": 0})
    assert out["pending"] == 0 and len(s["messages"]) == 1 and fake_turn


def test_dispatch_without_owner_only_ledgers(session_registry, fake_turn):
    s = session_registry()
    loop = _FakeLoop()
    assert server._dispatch_cluster_job_event(_tr(session_id=""), loop) == "no_session"
    assert server._dispatch_cluster_job_event(_tr(session_id="memomics-gone"), loop) == "no_session"
    assert s["messages"] == [] and server._CLUSTER_EVENT_QUEUE == []


def test_poll_once_dispatches_transitions(session_registry, fake_turn):
    s = session_registry()
    loop = _FakeLoop()
    out = server._poll_cluster_jobs_once(
        loop, poll=lambda: {"ok": True, "checked": 2, "transitions": [_tr(state="failed", from_="")],
                            "errors": [], "nodes": ["ssh23"]})
    assert out["transitions"] == 1 and out["checked"] == 2 and out["ok"] is True
    assert len(s["messages"]) == 1 and "❌" in s["messages"][0]["content"]
    assert "长任务按铁规 9" in s["messages"][0]["content"]


def test_poll_once_survives_poll_error(session_registry, fake_turn):
    def _boom():
        raise RuntimeError("poll 炸了")
    out = server._poll_cluster_jobs_once(_FakeLoop(), poll=_boom)
    assert out["ok"] is False and "poll 炸了" in out["error"]


def test_dispatch_respects_rungate_retired_task(session_registry, fake_turn, tmp_path):
    """任务已退役（RunGate stop）→ 事实留进会话但不自动唤醒（M2 同款语义）。"""
    rd = tmp_path / "results-retired"
    rd.mkdir()
    (rd / ".task_state.json").write_text(
        json.dumps({"state": "cancelled", "task_class": "long_running", "armed": False,
                    "rounds_started": 0, "max_rounds": 256}), encoding="utf-8")
    s = session_registry(results_dir=str(rd))
    loop = _FakeLoop()
    assert server._dispatch_cluster_job_event(_tr(), loop) == "notified_no_wake"
    assert len(s["messages"]) == 1 and "未自动唤醒" in s["messages"][0]["content"]
    assert loop.scheduled == 0 and not fake_turn


def test_dispatch_wakes_armed_session(session_registry, fake_turn, tmp_path):
    """armed 会话（正常状态）→ 正常唤醒（对照组，证明上面那条不是因为别的）。"""
    rd = tmp_path / "results-armed"
    rd.mkdir()
    (rd / ".task_state.json").write_text(
        json.dumps({"state": "pending", "task_class": "long_running", "armed": True,
                    "rounds_started": 0, "max_rounds": 256}), encoding="utf-8")
    s = session_registry(results_dir=str(rd))
    loop = _FakeLoop()
    assert server._dispatch_cluster_job_event(_tr(), loop) == "dispatched"
    assert loop.scheduled == 1 and fake_turn and not s["messages"][0]["content"].startswith("⏰ 集群作业状态变化")