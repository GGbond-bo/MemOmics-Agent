# -*- coding: utf-8 -*-
"""M1-M4 极端压力测试：多意图 × 多场景 × 损坏输入 × 并发 × 多会话。

覆盖：
  A. 用户意图矩阵 × 各任务状态（继续/新任务/闲聊/空消息/英文大小写/blocked）
  B. M2 armed 极端：损坏 JSON / 损坏字段 / 旧格式 / 非 bool armed / 并发写 / unicode 路径
  C. M3 预算极端：边界 1/256 / 非法值 / done 后 admit / 无文件 admit / 300 次耗尽
  D. M1 兜底极端（真实 server 唤醒链 + stub）：连续 10 轮跳过不误杀 / 外部工作退出 /
     损坏 task_plan / 无 🏁 / 无 results_dir / busy 重排 3 次 / force_tool / urgent /
     抛异常 fail-open / 多会话独立
  E. M4 对账极端：幂等 / cancelled 归档 / 目标已存在 / 损坏状态 / 目录不存在 / plan 是目录
"""
import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_RUNTIME = os.path.join(_HERE, "..", "runtime")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # @dataclass 需要模块在 sys.modules 中
    spec.loader.exec_module(mod)
    return mod


run_gate = _load("run_gate", os.path.join(_RUNTIME, "run_gate.py"))

pytestmark = pytest.mark.unit

EMOJI = "\U0001f3c1"  # 🏁


# ── 工具 ────────────────────────────────────────────────────────────────────

def _seed(results_dir, state="running", *, armed=None, rounds=0, max_rounds=None):
    """直接写状态文件（可控字段，含损坏场景）。返回写入的 dict。"""
    os.makedirs(results_dir, exist_ok=True)
    payload = {
        "state": state, "reason": "extreme-seed", "updated_at": 1.0,
        "task_class": "normal", "armed": True, "armed_at": 1.0, "armed_by": "seed",
        "rounds_started": rounds, "max_rounds": max_rounds or run_gate.DEFAULT_MAX_ROUNDS,
    }
    if armed is not None:
        payload["armed"] = armed
    with open(os.path.join(results_dir, ".task_state.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return payload


def _seed_plan(results_dir, main="# Goal\n\n## Phase 1\n- [ ] step (pending)\n\n## " + EMOJI + "\n"):
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, "task_plan.md"), "w", encoding="utf-8") as f:
        f.write(main)


class _FakeAsyncio:
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


def _make_session(results_dir):
    sid = "wake-x-%s" % os.urandom(4).hex()
    return {
        "id": sid,
        "results_dir": results_dir,
        "todos": [{"status": "in_progress", "title": "step1", "estimated_minutes": 1}],
        "messages": [],
        "_self_check_count": 0,
    }


@pytest.fixture()
def wake_env(monkeypatch):
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


def _run_wakeup(wake_env):
    """执行下一个捕获的唤醒协程；返回是否触发了 agent 回合。"""
    server, fake = wake_env["server"], wake_env["fake"]
    n_before = len(wake_env["triggered"])
    if not fake.captured:
        return False
    asyncio.run(fake.captured.pop(0))
    return len(wake_env["triggered"]) > n_before


# ═══════════════════════════════════════════════════════════════════════════
# A. 用户意图矩阵 × 任务状态（check_gate 用户路径）
# ═══════════════════════════════════════════════════════════════════════════

def test_a_intent_matrix_across_states(tmp_path):
    """各种用户意图 × 各状态 → (verdict, 期望状态/武装变化)。"""
    rd = str(tmp_path / "intent")
    _seed(rd, "done")
    cases = [
        # (状态, 消息, 期望 verdict)
        ("done", "继续", "run"),
        ("done", "接着跑", "run"),
        ("done", "continue", "run"),
        ("done", "CONTINUE 分析", "run"),       # 英文大写 → lower 命中
        ("done", "New task please", "run"),      # 英文
        ("done", "看看结果", "ask_user"),        # 非继续词
        ("done", "你好", "ask_user"),            # 闲聊
        ("done", "", "ask_user"),                # 空消息
        ("done", "分析一下这个数据", "ask_user"),  # 新意图但无继续词
        ("cancelled", "重跑", "run"),
        ("cancelled", "看看", "ask_user"),
        ("blocked", "继续", "run"),
        ("blocked", "随便说", "run"),
        ("running", "继续", "run"),
        ("running", "你好", "run"),
    ]
    for state, msg, want in cases:
        _seed(rd, state)
        v, _ = run_gate.check_gate(rd, is_auto_wake=False, user_message=msg)
        assert v == want, f"state={state} msg={msg!r}: got {v}, want {want}"
        if v == "run" and state in ("done", "cancelled") and msg:
            st = run_gate.load_state(rd)
            assert st["state"] == "pending", f"word-match 应重置 pending: {msg!r}"

    # 用户路径永不返回 stop（除 interrupt）
    for msg in ("继续", "看看", "", "x" * 5000):
        _seed(rd, "running")
        v, _ = run_gate.check_gate(rd, is_auto_wake=False, user_message=msg)
        assert v != "stop"
    # interrupt 优先于一切
    _seed(rd, "running")
    v, _ = run_gate.check_gate(rd, is_auto_wake=False, user_message="继续",
                               interrupt_requested=True)
    assert v == "stop"


# ═══════════════════════════════════════════════════════════════════════════
# B. M2 armed 极端
# ═══════════════════════════════════════════════════════════════════════════

def test_b_corrupted_json_never_resurrects_task(tmp_path):
    """损坏状态文件 → pending+未武装（保守），绝不复活 done 任务。"""
    rd = str(tmp_path / "corrupt")
    os.makedirs(rd, exist_ok=True)
    with open(os.path.join(rd, ".task_state.json"), "w", encoding="utf-8") as f:
        f.write("{state: 'done', broken json!!")
    st = run_gate.load_state(rd)
    assert st["state"] == "pending"
    assert st["armed"] is False, "损坏=未知状态=不得自动唤醒"
    v, r = run_gate.check_gate(rd, is_auto_wake=True)
    assert v == "stop", f"损坏文件不得恢复自动唤醒: {r}"
    # 用户消息可恢复
    v, _ = run_gate.check_gate(rd, is_auto_wake=False, user_message="继续")
    assert v == "run"


def test_b_field_corruption_keeps_state_machine(tmp_path):
    """字段级损坏只修该字段，绝不整体回退（done 任务不得复活）。"""
    rd = str(tmp_path / "field")
    _seed(rd, "done", rounds=10)
    # rounds_started 写成字符串
    with open(os.path.join(rd, ".task_state.json"), "w", encoding="utf-8") as f:
        json.dump({"state": "done", "rounds_started": "abc"}, f)
    st = run_gate.load_state(rd)
    assert st["state"] == "done", "字段损坏不得重置状态机"
    assert st["rounds_started"] == 0
    v, _ = run_gate.check_gate(rd, is_auto_wake=True)
    assert v == "stop", "done 必须仍被退役闸门拦截"

    # max_rounds 非法
    _seed(rd, "running", rounds=5)
    with open(os.path.join(rd, ".task_state.json"), "w", encoding="utf-8") as f:
        json.dump({"state": "running", "max_rounds": -7}, f)
    st = run_gate.load_state(rd)
    assert st["max_rounds"] == run_gate.DEFAULT_MAX_ROUNDS
    assert st["state"] == "running"

    # rounds_started 负数 / 非数字 / 浮点
    for bad in (-3, "xyz", None):
        _seed(rd, "running", rounds=5)
        with open(os.path.join(rd, ".task_state.json"), "w", encoding="utf-8") as f:
            json.dump({"state": "running", "rounds_started": bad}, f)
        st = run_gate.load_state(rd)
        assert st["rounds_started"] == 0, f"bad rounds={bad!r} → 0"
        assert st["state"] == "running"
    # 浮点 → int 截断（防御性强制，不炸）
    _seed(rd, "running", rounds=5)
    with open(os.path.join(rd, ".task_state.json"), "w", encoding="utf-8") as f:
        json.dump({"state": "running", "rounds_started": 3.7}, f)
    st = run_gate.load_state(rd)
    assert st["rounds_started"] == 3 and st["state"] == "running"


def test_b_armed_non_bool_values(tmp_path):
    """armed 字段各种怪值 → bool 化且不炸。"""
    rd = str(tmp_path / "armedvals")
    for bad in ("yes", "false", 1, 0, None, [], {"x": 1}):
        _seed(rd, "running", armed=bad)
        st = run_gate.load_state(rd)
        assert st["armed"] is bool(st["armed"]), f"armed={bad!r} → bool"
        v, _ = run_gate.check_gate(rd, is_auto_wake=True)
        assert v in ("run", "stop")


def test_b_legacy_file_all_states(tmp_path):
    """旧格式（无 armed 字段）各状态 → 一律视为未武装（升级即暂停自动唤醒）。"""
    for state in ("pending", "running", "blocked"):
        rd = str(tmp_path / f"legacy_{state}")
        os.makedirs(rd, exist_ok=True)
        with open(os.path.join(rd, ".task_state.json"), "w", encoding="utf-8") as f:
            json.dump({"state": state, "reason": "legacy"}, f)
        st = run_gate.load_state(rd)
        assert st["armed"] is False
        v, _ = run_gate.check_gate(rd, is_auto_wake=True)
        assert v == "stop", f"legacy {state} 自动唤醒必须被拦"


def test_b_multi_task_isolation(tmp_path):
    """多任务目录隔离：A 未武装、B 武装互不影响。"""
    rd_a = str(tmp_path / "iso_a")
    rd_b = str(tmp_path / "iso_b")
    _seed(rd_a, "running", armed=False, rounds=3)
    _seed(rd_b, "running", armed=True, rounds=1)
    v_a, _ = run_gate.check_gate(rd_a, is_auto_wake=True)
    v_b, _ = run_gate.check_gate(rd_b, is_auto_wake=True)
    assert v_a == "stop" and v_b == "run"
    run_gate.arm(rd_a, by="user")
    assert run_gate.check_gate(rd_a, is_auto_wake=True)[0] == "run"
    # B 不受 A 影响
    assert run_gate.load_state(rd_b)["armed"] is True


def test_b_unicode_and_long_paths(tmp_path):
    """中文/emoji/超长路径下 armed 全流程可用。"""
    rd = str(tmp_path / ("中文任务-单细胞分析-🧬-" + "长" * 60))
    _seed(rd, "running", armed=False)
    assert run_gate.is_armed(rd) is False
    run_gate.arm(rd, by="用户消息")
    assert run_gate.is_armed(rd) is True
    assert run_gate.load_state(rd)["armed_by"] == "用户消息"
    run_gate.disarm(rd, "重启")
    assert run_gate.check_gate(rd, is_auto_wake=True)[0] == "stop"


def test_b_concurrent_writes_never_corrupt(tmp_path):
    """多线程并发 arm/disarm/save_state/admit_round → 文件始终合法、无 .tmp 残留。"""
    rd = str(tmp_path / "conc")
    _seed(rd, "running", armed=True)
    stop = threading.Event()
    errors = []

    def _worker(kind):
        try:
            for _ in range(60):
                if kind == "arm":
                    run_gate.arm(rd, by="t")
                elif kind == "disarm":
                    run_gate.disarm(rd, "t")
                elif kind == "save":
                    run_gate.save_state(rd, "running", "t")
                else:
                    run_gate.admit_round(rd)
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=_worker, args=(k,))
               for k in ("arm", "disarm", "save", "admit") for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    # 文件可解析、字段合法、无 tmp 残留
    st = run_gate.load_state(rd)
    assert st["state"] == "running"
    assert 0 <= st["rounds_started"] <= run_gate.DEFAULT_MAX_ROUNDS
    assert not [f for f in os.listdir(rd) if f.endswith(".tmp")], "原子写不得留 tmp"


# ═══════════════════════════════════════════════════════════════════════════
# C. M3 预算极端
# ═══════════════════════════════════════════════════════════════════════════

def test_c_budget_boundaries(tmp_path):
    """max_rounds=1 的精确边界 + 无文件 admit 拒绝 + 退役 admit 拒绝。"""
    rd = str(tmp_path / "b1")
    _seed(rd, "running", max_rounds=1)
    assert run_gate.admit_round(rd) is True
    assert run_gate.admit_round(rd) is False, "1/1 后必须拒绝"
    assert run_gate.check_gate(rd, is_auto_wake=True)[0] == "stop"
    # 用户刷新
    run_gate.reset_rounds(rd)
    assert run_gate.check_gate(rd, is_auto_wake=True)[0] == "run"

    # 无状态文件的目录：admit 必须拒绝（不凭空创建激活记录）
    rd2 = str(tmp_path / "b2")
    os.makedirs(rd2, exist_ok=True)
    assert run_gate.admit_round(rd2) is False
    assert not os.path.isfile(os.path.join(rd2, ".task_state.json")), "不得凭空创建"

    # 退役任务 admit 拒绝
    _seed(rd2, "done")
    assert run_gate.admit_round(rd2) is False
    _seed(rd2, "cancelled")
    assert run_gate.admit_round(rd2) is False


def test_c_exhaust_300_rounds(tmp_path):
    """连续 300 次 admit → 精确停在 256，此后 check_gate stop。"""
    rd = str(tmp_path / "b300")
    _seed(rd, "running")
    n = 0
    for _ in range(300):
        if run_gate.admit_round(rd):
            n += 1
    assert n == run_gate.DEFAULT_MAX_ROUNDS == 256
    assert run_gate.round_budget(rd)["rounds_started"] == 256
    assert run_gate.check_gate(rd, is_auto_wake=True)[0] == "stop"
    v, _ = run_gate.check_gate(rd, is_auto_wake=False, user_message="继续")
    assert v == "run"
    run_gate.reset_rounds(rd)
    assert run_gate.check_gate(rd, is_auto_wake=True)[0] == "run"


def test_c_budget_garbage_args(tmp_path):
    """save_state 显式预算参数传垃圾 → 防御为合法值。"""
    rd = str(tmp_path / "bg")
    run_gate.save_state(rd, "running", "x", rounds_started="abc", max_rounds="xyz")
    st = run_gate.load_state(rd)
    assert st["rounds_started"] == 0 and st["max_rounds"] == run_gate.DEFAULT_MAX_ROUNDS
    run_gate.save_state(rd, "running", "x", rounds_started=-5, max_rounds=0)
    st = run_gate.load_state(rd)
    assert st["rounds_started"] == 0 and st["max_rounds"] == run_gate.DEFAULT_MAX_ROUNDS
    # 非法 state / 空目录 → False 不炸
    assert run_gate.save_state(rd, "bogus_state", "x") is False
    assert run_gate.save_state("", "running", "x") is False


# ═══════════════════════════════════════════════════════════════════════════
# D. M1 兜底极端（真实 server 唤醒链）
# ═══════════════════════════════════════════════════════════════════════════

def test_d_long_silent_task_survives_20_round_gate(wake_env, tmp_path):
    """长任务长时间零产出（进程活着）→ 连续 10 轮兜底全部跳过：
    不唤醒 LLM、不耗预算、无进展计数不增长（20 轮闸门不得误杀）。"""
    rd = str(tmp_path / "silent")
    _seed(rd, "running")
    _seed_plan(rd)
    sess = _make_session(rd)
    wake_env["server"]._sessions[sess["id"]] = sess
    server, fake = wake_env["server"], wake_env["fake"]
    server._session_has_external_work = lambda s: True

    server._schedule_self_check(sess, object(), asyncio.new_event_loop(), trigger="turn_end")
    for _ in range(10):
        assert _run_wakeup(wake_env) is False, "零产出期间不得唤醒 LLM"
    assert wake_env["triggered"] == []
    assert run_gate.round_budget(rd)["rounds_started"] == 0, "跳过不耗预算"
    assert sess.get("_self_check_count", 0) <= 1, "跳过不算无进展（20 轮闸门不误杀）"
    assert len(fake.captured) == 1, "兜底循环保持挂起"


def test_d_external_work_exit_wakes_immediately(wake_env, tmp_path):
    """外部工作退出（进程死）→ 下一轮兜底立即唤醒 LLM 收结果。"""
    rd = str(tmp_path / "exit")
    _seed(rd, "running")
    _seed_plan(rd)
    sess = _make_session(rd)
    wake_env["server"]._sessions[sess["id"]] = sess
    server, fake = wake_env["server"], wake_env["fake"]
    ext = {"on": True}
    server._session_has_external_work = lambda s: ext["on"]
    server._schedule_self_check(sess, object(), asyncio.new_event_loop())
    assert _run_wakeup(wake_env) is False, "运行中应跳过"
    ext["on"] = False  # 进程退出
    assert _run_wakeup(wake_env) is True, "进程退出必须立即唤醒"
    assert run_gate.round_budget(rd)["rounds_started"] == 1


def test_d_corrupted_task_plan_signature_fallback(wake_env, tmp_path):
    """task_plan.md 含非法 UTF-8 → 签名走 mtime fallback，不崩、兜底逻辑正常。"""
    rd = str(tmp_path / "badplan")
    _seed(rd, "running")
    with open(os.path.join(rd, "task_plan.md"), "wb") as f:
        f.write(b"\xff\xfe\x00\x81broken\xc3\x28")
    sess = _make_session(rd)
    wake_env["server"]._sessions[sess["id"]] = sess
    server, fake = wake_env["server"], wake_env["fake"]
    server._session_has_external_work = lambda s: True
    server._schedule_self_check(sess, object(), asyncio.new_event_loop())
    assert _run_wakeup(wake_env) is False, "损坏 plan + 外部活跃 → 跳过（不崩）"
    # 修复 plan → 签名变化 → 唤醒
    _seed_plan(rd)
    assert _run_wakeup(wake_env) is True


def test_d_plan_without_flag_section(wake_env, tmp_path):
    """task_plan.md 无 🏁 段 → 全文哈希；进展（改文件）→ 唤醒。"""
    rd = str(tmp_path / "noflag")
    _seed(rd, "running")
    _seed_plan(rd, "# Goal\n\n## Phase 1\n- [ ] step (pending)\n")  # 无 🏁
    sess = _make_session(rd)
    wake_env["server"]._sessions[sess["id"]] = sess
    server, fake = wake_env["server"], wake_env["fake"]
    server._session_has_external_work = lambda s: True
    server._schedule_self_check(sess, object(), asyncio.new_event_loop())
    assert _run_wakeup(wake_env) is False
    _seed_plan(rd, "# Goal\n\n## Phase 1\n- [ ] step (pending, v2)\n")
    assert _run_wakeup(wake_env) is True


def test_d_no_results_dir_never_injects(wake_env, tmp_path):
    """会话无 results_dir（无任务）→ 调度但不注入、不计数、不创建状态文件。"""
    sess = _make_session("")
    wake_env["server"]._sessions[sess["id"]] = sess
    server, fake = wake_env["server"], wake_env["fake"]
    server._schedule_self_check(sess, object(), asyncio.new_event_loop())
    assert len(fake.captured) == 1, "无任务也应能调度（gate 链兜住）"
    assert _run_wakeup(wake_env) is False, "无任务不得注入"
    assert wake_env["triggered"] == []


def test_d_busy_retry_at_most_3_then_give_up(wake_env, tmp_path):
    """busy（用户回合/运行中）→ 重排 ≤3 次后放弃，重排 trigger 透传。"""
    rd = str(tmp_path / "busy")
    _seed(rd, "running")
    _seed_plan(rd)
    sess = _make_session(rd)
    wake_env["server"]._sessions[sess["id"]] = sess
    server, fake = wake_env["server"], wake_env["fake"]
    sess["running_agent"] = object()  # 忙
    server._schedule_self_check(sess, object(), asyncio.new_event_loop(), trigger="task_done")
    for i in range(1, 5):
        woke = _run_wakeup(wake_env)
        assert woke is False
        if i <= 3:
            assert len(fake.captured) >= 1, f"第 {i} 次 busy 应重排"
            assert sess.get("_wakeup_retry_n", 0) == i
        else:
            assert len(fake.captured) == 0, "超过 3 次不得再重排"
            assert "_wakeup_retry_n" not in sess, "重排计数应清零"
    assert wake_env["triggered"] == []
    assert run_gate.round_budget(rd)["rounds_started"] == 0, "busy 重排不耗预算"


def test_d_force_tool_and_urgent_bypass_fallback(wake_env, tmp_path):
    """force_tool / urgent 绕过兜底跳过，直接唤醒。"""
    rd = str(tmp_path / "bypass")
    _seed(rd, "running")
    _seed_plan(rd)
    sess = _make_session(rd)
    wake_env["server"]._sessions[sess["id"]] = sess
    server, fake = wake_env["server"], wake_env["fake"]
    server._session_has_external_work = lambda s: True

    sess["_force_tool_check"] = True  # 说而不做强制重跑
    server._schedule_self_check(sess, object(), asyncio.new_event_loop())
    assert _run_wakeup(wake_env) is True, "force_tool 必须绕过兜底跳过"

    sess["_urgent_wakeup"] = True
    server._schedule_self_check(sess, object(), asyncio.new_event_loop())
    assert _run_wakeup(wake_env) is True, "urgent 必须绕过兜底跳过"


def test_d_external_work_check_throws_fails_open(wake_env, tmp_path):
    """_session_has_external_work 抛异常 → fail-open 正常唤醒（不饿死）。"""
    rd = str(tmp_path / "throw")
    _seed(rd, "running")
    _seed_plan(rd)
    sess = _make_session(rd)
    wake_env["server"]._sessions[sess["id"]] = sess
    server, fake = wake_env["server"], wake_env["fake"]

    def _boom(s):
        raise RuntimeError("process_registry broken")

    server._session_has_external_work = _boom
    server._schedule_self_check(sess, object(), asyncio.new_event_loop())
    assert _run_wakeup(wake_env) is True, "外部工作判定异常必须 fail-open 唤醒"


def test_d_multi_session_independent(wake_env, tmp_path):
    """两会话各自 armed/预算/签名完全独立，互不污染。"""
    rd_a = str(tmp_path / "ind_a")
    rd_b = str(tmp_path / "ind_b")
    _seed(rd_a, "running", armed=False)
    _seed_plan(rd_a)
    _seed(rd_b, "running", armed=True, max_rounds=1)
    _seed_plan(rd_b)
    sa, sb = _make_session(rd_a), _make_session(rd_b)
    server, fake = wake_env["server"], wake_env["fake"]
    server._sessions[sa["id"]] = sa
    server._sessions[sb["id"]] = sb

    server._schedule_self_check(sa, object(), asyncio.new_event_loop())  # 未武装 → 拦
    server._schedule_self_check(sb, object(), asyncio.new_event_loop())  # 武装 → 调度
    assert len(fake.captured) == 1, "只有 B 调度"
    assert _run_wakeup(wake_env) is True
    assert run_gate.round_budget(rd_a)["rounds_started"] == 0
    assert run_gate.round_budget(rd_b)["rounds_started"] == 1
    # B 预算耗尽，A 仍拦
    server._schedule_self_check(sb, object(), asyncio.new_event_loop())
    assert len(fake.captured) == 0
    # A 用户消息武装后恢复
    run_gate.arm(rd_a, by="user")
    server._schedule_self_check(sa, object(), asyncio.new_event_loop())
    assert len(fake.captured) == 1
    assert _run_wakeup(wake_env) is True
    assert run_gate.round_budget(rd_a)["rounds_started"] == 1
    server._sessions.pop(sa["id"], None)
    server._sessions.pop(sb["id"], None)


def test_d_budget_exhausted_blocks_even_urgent_injection(wake_env, tmp_path):
    """预算耗尽：urgent 可绕过 check_gate 但注入级 admit_round 仍硬拦。"""
    rd = str(tmp_path / "hard")
    _seed(rd, "running", max_rounds=1)
    _seed_plan(rd)
    sess = _make_session(rd)
    wake_env["server"]._sessions[sess["id"]] = sess
    server, fake = wake_env["server"], wake_env["fake"]
    server._session_has_external_work = lambda s: False

    sess["_urgent_wakeup"] = True  # urgent：绕过 RunGate stop
    server._schedule_self_check(sess, object(), asyncio.new_event_loop())
    assert len(fake.captured) == 1, "urgent 绕过闸门仍会调度"
    assert _run_wakeup(wake_env) is True, "第 1 轮注入（预算 1/1）"
    # 第 2 轮 urgent：gate 绕过 → 调度 → 注入前 admit 拒绝
    sess["_urgent_wakeup"] = True
    server._schedule_self_check(sess, object(), asyncio.new_event_loop())
    assert len(fake.captured) == 1
    assert _run_wakeup(wake_env) is False, "预算耗尽即使 urgent 也不得注入"
    assert run_gate.round_budget(rd)["rounds_started"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# E. M4 对账极端
# ═══════════════════════════════════════════════════════════════════════════

def test_e_reconcile_idempotent(tmp_path):
    """对账幂等：跑两次第二次无归档告警。"""
    rd = str(tmp_path / "ridem")
    _seed_plan(rd)
    _seed(rd, "done")
    n1 = run_gate.reconcile(rd)
    assert os.path.isfile(os.path.join(rd, "task_plan.done.md"))
    n2 = run_gate.reconcile(rd)
    assert not any("归档" in x for x in n2), f"第二次不应再归档: {n2}"


def test_e_cancelled_also_archives(tmp_path):
    """cancelled + 未归档 plan → 同样归档。"""
    rd = str(tmp_path / "canc")
    _seed_plan(rd)
    _seed(rd, "cancelled")
    run_gate.reconcile(rd)
    assert os.path.isfile(os.path.join(rd, "task_plan.done.md"))
    assert not os.path.isfile(os.path.join(rd, "task_plan.md"))


def test_e_archive_target_exists(tmp_path):
    """归档目标已存在 → 覆盖归档（旧 done 归档被新归档替换）。"""
    rd = str(tmp_path / "over")
    _seed_plan(rd)
    _seed(rd, "done")
    with open(os.path.join(rd, "task_plan.done.md"), "w", encoding="utf-8") as f:
        f.write("old archive")
    notes = run_gate.reconcile(rd)
    assert os.path.isfile(os.path.join(rd, "task_plan.done.md"))
    assert not os.path.isfile(os.path.join(rd, "task_plan.md"))
    assert any("归档" in x for x in notes)


def test_e_plan_is_directory(tmp_path):
    """task_plan.md 是目录 → 归档失败仅告警不崩。"""
    rd = str(tmp_path / "pdir")
    os.makedirs(os.path.join(rd, "task_plan.md"), exist_ok=True)
    _seed(rd, "done")
    notes = run_gate.reconcile(rd)  # 不抛
    assert isinstance(notes, list)


def test_e_corrupt_state_and_missing_dir(tmp_path):
    """损坏状态文件 → 告警不崩；目录不存在 → 空列表。"""
    rd = str(tmp_path / "corr")
    os.makedirs(rd, exist_ok=True)
    with open(os.path.join(rd, ".task_state.json"), "w", encoding="utf-8") as f:
        f.write("@@@")
    notes = run_gate.reconcile(rd)
    assert isinstance(notes, list)
    assert run_gate.reconcile(str(tmp_path / "nope")) == []


def test_e_clean_done_no_plan(tmp_path):
    """done + plan 已归档（无 task_plan.md）→ 零告警（干净）。"""
    rd = str(tmp_path / "clean")
    _seed(rd, "done")
    with open(os.path.join(rd, "task_plan.done.md"), "w", encoding="utf-8") as f:
        f.write("done plan")
    assert run_gate.reconcile(rd) == []
