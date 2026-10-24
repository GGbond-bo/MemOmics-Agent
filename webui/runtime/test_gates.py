"""P1-A/P1-B/P1-C 模块回归测试（python webui/runtime/test_gates.py 运行）。

覆盖：run_gate 状态机、loopx_bridge 全 API、retry_backoff 退避、session_locks 互斥。
注意：不得 `from webui.runtime import ...`（会触发 webui/__init__.py 加载 torch 等重量级
依赖导致 import 卡死）；一律用 importlib 文件级加载。
"""
import importlib.util
import os
import sys
import tempfile
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_MEMOMICS = os.path.join(_ROOT, "memomics")
sys.path.insert(0, _MEMOMICS)  # loopx_bridge


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run_gate = _load_module("run_gate", os.path.join(_HERE, "run_gate.py"))
retry_backoff = _load_module("retry_backoff", os.path.join(_HERE, "retry_backoff.py"))
session_locks = _load_module("session_locks", os.path.join(_HERE, "session_locks.py"))
loopx_bridge = _load_module("loopx_bridge", os.path.join(_MEMOMICS, "loopx_bridge.py"))

FAILS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    if not cond:
        FAILS.append(name)
    print(f"[{status}] {name} {detail}")


# ── run_gate ────────────────────────────────────────────────────────────────
rd = tempfile.mkdtemp(prefix="gate_test_")
check("gate: 初始 pending 放行", run_gate.check_gate(rd, is_auto_wake=True)[0] == "run")
run_gate.mark_done(rd, "test done")
check("gate: done 后自动唤醒被拦",
      run_gate.check_gate(rd, is_auto_wake=True)[0] == "stop")
check("gate: done 后用户消息未命中→ask_user",
      run_gate.check_gate(rd, user_message="看看结果", is_auto_wake=False)[0] == "ask_user")
check("gate: 命中继续词表→重置+放行",
      run_gate.check_gate(rd, user_message="继续分析", is_auto_wake=False)[0] == "run")
check("gate: 重置后状态为 pending", run_gate.load_state(rd)["state"] == "pending")
run_gate.mark_done(rd)
check("gate: 中断优先于一切",
      run_gate.check_gate(rd, interrupt_requested=True, user_message="继续", is_auto_wake=False)[0] == "stop")
check("gate: 原子写无 .tmp 残留", not [f for f in os.listdir(rd) if f.endswith(".tmp")])
check("gate: 持久化文件存在", os.path.isfile(run_gate._state_path(rd)))

# cancelled 状态：用户放弃任务
run_gate.mark_cancelled(rd, "user cancelled")
check("gate: cancelled 自动唤醒被拦",
      run_gate.check_gate(rd, is_auto_wake=True)[0] == "stop")
check("gate: cancelled 用户新消息→ask_user（未命中继续词）",
      run_gate.check_gate(rd, user_message="看看结果", is_auto_wake=False)[0] == "ask_user")
check("gate: cancelled 命中继续词→重置放行",
      run_gate.check_gate(rd, user_message="继续分析", is_auto_wake=False)[0] == "run")
check("gate: is_retired 判定 done/cancelled",
      run_gate.mark_done(rd) and run_gate.is_retired(rd) and
      run_gate.mark_cancelled(rd) and run_gate.is_retired(rd))
check("gate: is_retired 对 pending 为 False",
      run_gate.mark_running(rd) and not run_gate.is_retired(rd))

# ── loopx_bridge ────────────────────────────────────────────────────────────
LoopXBridge = loopx_bridge.LoopXBridge
rd2 = tempfile.mkdtemp(prefix="bridge_test_")
b = LoopXBridge("sess-reg-001", rd2, user_online=True)
check("bridge: goal 注册", b._goal_id == "sess-reg-001" and b.registry_path.exists())
d = b.should_run()
check("bridge: 用户在场 gate 豁免", d["should_run"] is True and d["gate_waived"] is True)
b2 = LoopXBridge("sess-reg-002", rd2, user_online=False)
check("bridge: 离线用户保留 operator_gate",
      b2.should_run()["state"] == "operator_gate" and not b2.should_run()["should_run"])
check("bridge: 心跳文本非空", len(b.heartbeat_prompt("full")) > 0)
check("bridge: 轮询间隔返回 int", isinstance(b.next_poll_interval(), int))
check("bridge: 事件溯源幂等 append",
      b.append_event("goal_started") and b.append_event("heartbeat"))
import json as _json
ev_path = os.path.join(rd2, ".loopx", "events.jsonl")
if os.path.isfile(ev_path):
    lines = open(ev_path, encoding="utf-8").read().splitlines()
    check("bridge: 事件落盘 2 行", len(lines) == 2)
    check("bridge: 事件类型正确", _json.loads(lines[0])["event_type"] == "refresh_recorded")

# ── retry_backoff（P1-B）────────────────────────────────────────────────────
build_structured_error = retry_backoff.build_structured_error
RetryBackoff = retry_backoff.RetryBackoff
rb = RetryBackoff(base_delays=(0.01, 0.02, 0.05, 0.1))
t0 = time.time()
seq = rb.next_delay(1), rb.next_delay(2), rb.next_delay(3)
check("backoff: 指数序列", seq == (0.01, 0.02, 0.05), f"{seq}")
check("backoff: 达到上限判定", rb.exhausted(2) is False and rb.exhausted(3) is True)
se = build_structured_error("Rscript test.R", 2, "Error in test.R: boom")
check("backoff: 结构化错误字段",
      se["exit_code"] == 2 and "boom" in se["traceback_tail"] and "Rscript test.R" in se["command"])
# 可中断性：分段 sleep 在 interrupt 后快速退出
rb2 = RetryBackoff(base_delays=(0.5, 1.0))
interrupted = {"flag": False}


def _do_interrupt():
    time.sleep(0.1)
    interrupted["flag"] = True


th = threading.Thread(target=_do_interrupt)
th.start()
t0 = time.time()
rb2.wait_interruptible(0.5, lambda: interrupted["flag"])
elapsed = time.time() - t0
check("backoff: 中断后快速退出", elapsed < 0.45, f"elapsed={elapsed:.2f}s")
th.join()

# ── session_locks（P1-C）────────────────────────────────────────────────────
SessionLocks = session_locks.SessionLocks
sl = SessionLocks()
lk = sl.lock("sess-a")
got = sl.try_lock("sess-a")
check("locks: 同会话互斥拒绝", got is None)
got_b = sl.try_lock("sess-b")
check("locks: 异会话并行允许", got_b is not None)
sl.release("sess-b")
sl.release("sess-a")
check("locks: 释放后可再获取", sl.try_lock("sess-a") is not None)
sl.release("sess-a")

# ── M2 armed（重启后重新授权，DSH 语义迁移）──────────────────────────────────
import json as _json3
rd3 = tempfile.mkdtemp(prefix="armed_test_")
check("M2: 新目录默认武装（用户在场创建）", run_gate.is_armed(rd3) is True)
run_gate.disarm(rd3, "test restart")
check("M2: disarm 后自动唤醒被拦",
      run_gate.check_gate(rd3, is_auto_wake=True)[0] == "stop")
check("M2: 未武装 + 用户消息 → 放行（调用方负责 arm）",
      run_gate.check_gate(rd3, is_auto_wake=False, user_message="继续跑")[0] == "run")
run_gate.arm(rd3, by="user_message")
check("M2: 重新武装后自动唤醒放行",
      run_gate.check_gate(rd3, is_auto_wake=True)[0] == "run")
# 2026-10-18 语义迁移：许可改为"进程内"（借鉴 DSH goal）——
# 旧文件（armed=False 且无 paused 标记）应迁移为 armed，不再永久冻结。
with open(run_gate._state_path(rd3), "w", encoding="utf-8") as _f:
    _json3.dump({"state": "running", "reason": "legacy", "armed": False}, _f)
check("M2: 旧文件（armed=False 无暂停标记）→ 迁移为武装",
      run_gate.is_armed(rd3) is True)
check("M2: 旧文件迁移后自动唤醒放行（进程内许可）",
      run_gate.check_gate(rd3, is_auto_wake=True)[0] == "run")
# 显式暂停：只改许可，不改状态机 phase
run_gate.disarm(rd3, "user stop")
check("M2: 显式暂停只改许可、不改 phase",
      run_gate.load_state(rd3)["state"] == "running"
      and run_gate.load_state(rd3)["activation"] == "paused"
      and run_gate.is_paused(rd3) is True)
run_gate.arm(rd3, by="user_message")
check("M2: arm 记录 by/at", run_gate.load_state(rd3)["armed_by"] == "user_message" and
      run_gate.load_state(rd3)["armed_at"] > 0)

# ── M3 硬轮数预算（DSH maxGoalRounds 语义迁移）───────────────────────────────
rd4 = tempfile.mkdtemp(prefix="budget_test_")
run_gate.save_state(rd4, "running", "budget", max_rounds=3)
check("M3: admit_round 累计", run_gate.admit_round(rd4) and run_gate.admit_round(rd4) and
      run_gate.round_budget(rd4)["rounds_started"] == 2)
run_gate.admit_round(rd4)
check("M3: 预算耗尽后 admit 拒绝", run_gate.admit_round(rd4) is False)
check("M3: 预算耗尽 → 自动唤醒 stop",
      run_gate.check_gate(rd4, is_auto_wake=True)[0] == "stop")
check("M3: 预算耗尽 + 用户消息 → 放行",
      run_gate.check_gate(rd4, is_auto_wake=False, user_message="继续")[0] == "run")
run_gate.reset_rounds(rd4)
check("M3: 用户刷新预算后自动唤醒恢复",
      run_gate.check_gate(rd4, is_auto_wake=True)[0] == "run")
check("M3: 默认上限 256", run_gate.DEFAULT_MAX_ROUNDS == 256)
check("M3: 退役任务 admit 拒绝",
      run_gate.mark_done(rd4) and run_gate.admit_round(rd4) is False)

# ── M4 启动一致性对账 ────────────────────────────────────────────────────────
rd5 = tempfile.mkdtemp(prefix="reconcile_test_")
with open(os.path.join(rd5, "task_plan.md"), "w", encoding="utf-8") as _f:
    _f.write("# Goal\npending stuff\n")
run_gate.mark_done(rd5, "done")
_notes5 = run_gate.reconcile(rd5)
check("M4: done 且 task_plan 未归档 → 自动归档",
      os.path.isfile(os.path.join(rd5, "task_plan.done.md")) and
      not os.path.isfile(os.path.join(rd5, "task_plan.md")) and
      any("归档" in n for n in _notes5))
rd6 = tempfile.mkdtemp(prefix="reconcile2_test_")
run_gate.save_state(rd6, "running", "orphan")
_notes6 = run_gate.reconcile(rd6)
check("M4: 非退役无 plan → 孤儿告警", any("孤儿" in n for n in _notes6))
rd7 = tempfile.mkdtemp(prefix="reconcile3_test_")
with open(os.path.join(rd7, "task_plan.md"), "w", encoding="utf-8") as _f:
    _f.write("# Goal\npending\n")
run_gate.save_state(rd7, "running", "normal")
run_gate.disarm(rd7, "restart")
_notes7 = run_gate.reconcile(rd7)
check("M4: 非退役未武装 → 提示重新授权", any("M2 预期" in n for n in _notes7))

import shutil
shutil.rmtree(rd, ignore_errors=True)
shutil.rmtree(rd2, ignore_errors=True)
shutil.rmtree(rd3, ignore_errors=True)
shutil.rmtree(rd4, ignore_errors=True)
shutil.rmtree(rd5, ignore_errors=True)
shutil.rmtree(rd6, ignore_errors=True)
shutil.rmtree(rd7, ignore_errors=True)
print("\n" + ("ALL PASS" if not FAILS else f"FAILED: {FAILS}"))
sys.exit(1 if FAILS else 0)
