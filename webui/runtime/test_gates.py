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

import shutil
shutil.rmtree(rd, ignore_errors=True)
shutil.rmtree(rd2, ignore_errors=True)
print("\n" + ("ALL PASS" if not FAILS else f"FAILED: {FAILS}"))
sys.exit(1 if FAILS else 0)
