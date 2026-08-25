# -*- coding: utf-8 -*-
"""M1/M2/M3 唤醒引擎集成测试（离线，不走 LLM）。

验证对象是真实 webui/server.py 的 _schedule_self_check 唤醒链：
  - M2: 未武装（重启后）→ 自动唤醒被 RunGate 拦；武装后恢复调度
  - M3: 硬轮数预算——真正注入才 +1，耗尽即停，用户消息刷新预算
  - M1: 兜底便宜检查——外部工作活跃且无新进展 → 不唤醒 LLM 只重排；
        有新进展 → 正常唤醒
  - M1: TaskSupervisor 完成事件监听（tasks.py 事件底座）

实现：monkeypatch server.asyncio 为记录型假件（捕获 _wakeup 协程而非真正调度），
stub _trigger_agent_turn 记录注入；用 asyncio.run 手动执行捕获的唤醒协程。
"""
import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_RUNTIME = os.path.join(_HERE, "..", "runtime")
_ROOT = os.path.join(_HERE, "..", "..")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # @dataclass 需要模块在 sys.modules 中
    spec.loader.exec_module(mod)
    return mod


run_gate = _load("run_gate", os.path.join(_RUNTIME, "run_gate.py"))
tasks_mod = _load("tasks", os.path.join(_RUNTIME, "tasks.py"))

pytestmark = pytest.mark.unit


# ── 工具 ────────────────────────────────────────────────────────────────────

class _FakeAsyncio:
    """记录型 asyncio 假件：捕获 run_coroutine_threadsafe/ensure_future 的协程。"""

    def __init__(self, real):
        self._real = real
        self.captured = []

    def run_coroutine_threadsafe(self, coro, loop):
        self.captured.append(coro)
        return None

    def ensure_future(self, coro):
        self.captured.append(coro)
        return None

    def get_event_loop(self):
        return self._real.get_event_loop()

    def sleep(self, delay):
        return self._real.sleep(0)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _seed_task(results_dir, *, armed=True, max_rounds=None, rounds=0):
    """种子一个"进行中任务"目录：task_plan.md（主线区含 pending，避免触发完成分支）
    + .task_state.json（running）。"""
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, "task_plan.md"), "w", encoding="utf-8") as f:
        f.write("# Goal\n\n## Phase 1\n- [ ] step (pending)\n\n## \U0001f3c1\n")
    kwargs = {}
    if max_rounds is not None:
        kwargs["max_rounds"] = max_rounds
    run_gate.save_state(results_dir, "running", "seed", armed=armed,
                        rounds_started=rounds, **kwargs)


def _make_session(results_dir):
    sid = "wake-test-%s" % os.urandom(4).hex()
    return {
        "id": sid,
        "results_dir": results_dir,
        "todos": [{"status": "in_progress", "title": "step1", "estimated_minutes": 1}],
        "messages": [],
        "_self_check_count": 0,
    }


@pytest.fixture()
def wake_env(monkeypatch):
    """挂好真实 server 模块 + 假 asyncio + stub 触发器，返回可操作句柄。"""
    import server
    monkeypatch.setattr(server, "_session_has_external_work", lambda s: False)
    fake = _FakeAsyncio(asyncio)
    monkeypatch.setattr(server, "asyncio", fake)
    state = {"triggered": []}

    async def _fake_trigger(session, message):
        state["triggered"].append(message)

    monkeypatch.setattr(server, "_trigger_agent_turn", _fake_trigger)
    state["server"] = server
    state["fake"] = fake
    return state


@pytest.fixture()
def seeded_session(wake_env):
    rd = tempfile.mkdtemp(prefix="wake_seed_")
    _seed_task(rd)
    sess = _make_session(rd)
    wake_env["server"]._sessions[sess["id"]] = sess
    yield wake_env, sess
    wake_env["server"]._sessions.pop(sess["id"], None)
    shutil.rmtree(rd, ignore_errors=True)


# ── M2 重启后重新授权 ───────────────────────────────────────────────────────

def test_m2_unarmed_blocks_auto_wake(wake_env):
    rd = tempfile.mkdtemp(prefix="wake_m2_")
    try:
        _seed_task(rd, armed=False)  # 重启恢复后：非退役但未武装
        sess = _make_session(rd)
        wake_env["server"]._sessions[sess["id"]] = sess
        server, fake = wake_env["server"], wake_env["fake"]
        server._schedule_self_check(sess, object(), asyncio.new_event_loop())
        assert fake.captured == [], "未武装时不得调度唤醒"
        # 用户消息武装（等价于 WS 用户消息路径的 arm()）
        run_gate.arm(rd, by="user_message")
        server._schedule_self_check(sess, object(), asyncio.new_event_loop())
        assert len(fake.captured) == 1, "武装后应恢复调度"
        asyncio.run(fake.captured.pop(0))
        assert len(wake_env["triggered"]) == 1
    finally:
        wake_env["server"]._sessions.pop(sess["id"], None)
        shutil.rmtree(rd, ignore_errors=True)


# ── M3 硬轮数预算 ───────────────────────────────────────────────────────────

def test_m3_budget_counts_and_blocks(wake_env):
    rd = tempfile.mkdtemp(prefix="wake_m3_")
    try:
        _seed_task(rd, max_rounds=2)
        sess = _make_session(rd)
        wake_env["server"]._sessions[sess["id"]] = sess
        server, fake = wake_env["server"], wake_env["fake"]

        # 第 1 轮：调度 → 注入 → 预算 +1
        server._schedule_self_check(sess, object(), asyncio.new_event_loop())
        assert len(fake.captured) == 1
        asyncio.run(fake.captured.pop(0))
        assert len(wake_env["triggered"]) == 1
        assert run_gate.round_budget(rd)["rounds_started"] == 1

        # 第 2 轮：预算 2/2
        server._schedule_self_check(sess, object(), asyncio.new_event_loop())
        asyncio.run(fake.captured.pop(0))
        assert len(wake_env["triggered"]) == 2
        assert run_gate.round_budget(rd)["rounds_started"] == 2

        # 第 3 轮：check_gate 预算耗尽 → 不再调度
        server._schedule_self_check(sess, object(), asyncio.new_event_loop())
        assert fake.captured == [], "预算耗尽后不得调度"

        # 用户消息刷新预算 → 恢复
        run_gate.reset_rounds(rd)
        server._schedule_self_check(sess, object(), asyncio.new_event_loop())
        assert len(fake.captured) == 1
        fake.captured.pop(0).close()  # 不执行，避免 never-awaited 警告
    finally:
        wake_env["server"]._sessions.pop(sess["id"], None)
        shutil.rmtree(rd, ignore_errors=True)


def test_m3_retired_between_schedule_and_fire(wake_env):
    """调度后、注入前任务退役 → admit_round 拒绝注入（DSH"真正进入才计数"）。"""
    rd = tempfile.mkdtemp(prefix="wake_m3r_")
    try:
        _seed_task(rd)
        sess = _make_session(rd)
        wake_env["server"]._sessions[sess["id"]] = sess
        server, fake = wake_env["server"], wake_env["fake"]
        server._schedule_self_check(sess, object(), asyncio.new_event_loop())
        assert len(fake.captured) == 1
        run_gate.mark_done(rd, "completed while sleeping")
        asyncio.run(fake.captured.pop(0))
        assert wake_env["triggered"] == [], "退役后不得注入"
        assert run_gate.round_budget(rd)["rounds_started"] == 0, "未注入不得计数"
    finally:
        wake_env["server"]._sessions.pop(sess["id"], None)
        shutil.rmtree(rd, ignore_errors=True)


# ── M1 兜底便宜检查 + 事件驱动 ──────────────────────────────────────────────

def test_m1_fallback_skips_llm_when_external_work_running(wake_env):
    rd = tempfile.mkdtemp(prefix="wake_m1_")
    try:
        _seed_task(rd)
        sess = _make_session(rd)
        wake_env["server"]._sessions[sess["id"]] = sess
        server, fake = wake_env["server"], wake_env["fake"]
        # 模拟外部工作（Rscript/batch）在跑
        server._session_has_external_work = lambda s: True

        # 回合结束 → 调度
        server._schedule_self_check(sess, object(), asyncio.new_event_loop())
        assert len(fake.captured) == 1
        # 兜底触发：签名未变 + 外部工作活跃 → 不唤醒 LLM，只重排 fallback
        asyncio.run(fake.captured.pop(0))
        assert wake_env["triggered"] == [], "无新进展时不得唤醒 LLM"
        assert len(fake.captured) == 1, "应重排兜底"
        # 预算未消耗（没有真正注入）
        assert run_gate.round_budget(rd)["rounds_started"] == 0

        # 外部工作产生新进展（主线区变化）→ 正常唤醒。
        # 回归：签名是 hash%2^31 的不透明值、非单调——显式找一个"哈希值变小"的
        # 变体，确保任何方向的变化都被判定为"有新进展"（旧实现用 <= 会误跳过）。
        _orig = open(os.path.join(rd, "task_plan.md"), encoding="utf-8").read()
        _base_main = "# Goal\n\n## Phase 1\n- [ ] step"
        _tail = _orig.split("- [ ] step")[1]
        _last_sig = sess.get("_self_check_last_sig", 0.0)
        _lower = None
        for _i in range(300):
            _cand = f"{_base_main} (v{_i}){_tail}"
            if float(hash(_cand.split('## \U0001f3c1')[0]) % (2 ** 31)) < _last_sig:
                _lower = _cand
                break
        assert _lower is not None, "测试前提：应能找到哈希变小的变体"
        with open(os.path.join(rd, "task_plan.md"), "w", encoding="utf-8") as f:
            f.write(_lower)
        assert server._session_progress_signature(sess) < _last_sig, "变体签名应确实变小"
        asyncio.run(fake.captured.pop(0))
        assert len(wake_env["triggered"]) == 1, "哈希变小也是新进展，应唤醒"
        assert run_gate.round_budget(rd)["rounds_started"] == 1
    finally:
        wake_env["server"]._sessions.pop(sess["id"], None)
        shutil.rmtree(rd, ignore_errors=True)


def test_m1_wake_on_progress_without_external_work(wake_env):
    """无外部工作（agent 自己的待办）→ 兜底不跳过，正常唤醒继续干活。"""
    rd = tempfile.mkdtemp(prefix="wake_m1b_")
    try:
        _seed_task(rd)
        sess = _make_session(rd)
        wake_env["server"]._sessions[sess["id"]] = sess
        server, fake = wake_env["server"], wake_env["fake"]
        server._session_has_external_work = lambda s: False  # 无外部工作
        server._schedule_self_check(sess, object(), asyncio.new_event_loop())
        asyncio.run(fake.captured.pop(0))
        assert len(wake_env["triggered"]) == 1, "agent 自有待办应继续唤醒"
    finally:
        wake_env["server"]._sessions.pop(sess["id"], None)
        shutil.rmtree(rd, ignore_errors=True)


def test_m1_task_done_event_fires_listener():
    """tasks.py 事件底座：后台任务完成 → done listener 收到终态快照。"""
    sup = tasks_mod.TaskSupervisor(store=None)
    seen = []
    sup.add_done_listener(lambda rec: seen.append(rec))

    async def _run():
        async def _work():
            await asyncio.sleep(0.01)
            return 42
        t = asyncio.ensure_future(_work())
        sup.register("sess-bg", t, label="background_rscript")
        await t
        await asyncio.sleep(0.05)  # 等 done callback 执行

    asyncio.run(_run())
    assert len(seen) == 1
    assert seen[0]["session_id"] == "sess-bg"
    assert seen[0]["label"] == "background_rscript"
    assert seen[0]["state"] == "succeeded"
    assert seen[0]["finished_at"]
