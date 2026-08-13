# -*- coding: utf-8 -*-
"""P1-15 LoopX cadence 映射修正验证：bridge.next_poll_interval 读真实契约字段。"""
import os, sys, json, types

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "hermes-agent"))
FAILED = []

def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)

import memomics.loopx_bridge as lb
from memomics.loopx_bridge import LoopXBridge

# 1. 真实 vendor 可加载（空壳质疑的再确认）
api = lb._load_loopx()
check("vendor loopx 已加载（4 API）", len(api) == 4, f"api keys={list(api.keys())}")

# 2. mock build_scheduler_hint 按 cadence 返回 → 验证映射
cases = [
    ("active_work", 3, None),
    ("unchanged_noop", 60, None),
    ("agent_scope_wait", 10, None),
    ("monitor_wait", 15, None),
    ("quiet_wait", 30, None),
    ("human_gate", None, None),
    ("quota_paused", None, None),
    ("terminal_no_followup", None, None),
    ("control_plane_repair", None, None),
    ("agent_monitor_only", None, None),
]
fake_api = {}
for cc, rec_min, _ in cases:
    def _hint(payload, scheduler_execution_context=None, _cc=cc, _rm=rec_min):
        ls = {}
        if _rm is not None:
            ls["recommended_interval_minutes"] = _rm
        return {"cadence_class": _cc, "local_scheduler": ls}
    fake_api[cc] = _hint

orig_load = lb._load_loopx
orig_collect = LoopXBridge.collect
lb._load_loopx = lambda: {"build_scheduler_hint": fake_api["active_work"], "collect_status": api.get("collect_status"), "build_quota_should_run": api.get("build_quota_should_run"), "build_heartbeat_prompt": api.get("build_heartbeat_prompt")}
LoopXBridge.collect = lambda self, limit=40: {"goal": {"status": "running"}}  # 非空，走 hint

b = LoopXBridge("test-sid", "E:/MemOmics-Agent/results/test")
try:
    # active_work → 60s 档（rec=3min→180s，clamp 到 60-600 → 180）
    r = b.next_poll_interval(300)
    check(f"active_work → {r}s（区间 60-600）", 60 <= r <= 600, f"r={r}")
    # 逐个 cadence 测
    for cc, rm, _ in cases:
        lb._load_loopx = lambda cc=cc: {"build_scheduler_hint": fake_api[cc]}
        r = b.next_poll_interval(300)
        if cc in ("quota_paused", "terminal_no_followup", "control_plane_repair", "agent_monitor_only"):
            check(f"{cc} → {r}s（=2400 暂停态）", r == 2400, f"r={r}")
        elif cc == "human_gate":
            check(f"{cc} → {r}s（=600 等用户）", r == 600, f"r={r}")
        elif cc in ("unchanged_noop", "agent_scope_wait", "monitor_wait", "quiet_wait"):
            expect = int(rm * 60) if rm else 300
            check(f"{cc} → {r}s（rec={rm}min→{expect}s，封顶 2400）", r == max(60, min(expect, 2400)), f"r={r}")
        else:
            check(f"{cc} → {r}s", 60 <= r <= 600, f"r={r}")
    # 降级路径：api 为空 → default
    lb._load_loopx = lambda: {}
    r = b.next_poll_interval(300)
    check(f"vendor 缺失降级 → {r}s（=default）", r == 300, f"r={r}")
finally:
    lb._load_loopx = orig_load
    LoopXBridge.collect = orig_collect

# 3. 真实 vendor smoke：build_scheduler_hint 真调用（最小 payload）
try:
    hint = api["build_scheduler_hint"](
        {"goal": {"id": "smoke", "status": "running"}},
        scheduler_execution_context=lb._SCHEDULER_CTX,
    )
    cc = hint.get("cadence_class")
    ls = hint.get("local_scheduler") or {}
    print(f"  真实 vendor smoke: cadence_class={cc} | local_scheduler 键={sorted(ls.keys())[:5]}")
    check("vendor hint 返回含 cadence_class", bool(cc), f"hint={str(hint)[:150]}")
    check("vendor hint 含 local_scheduler 契约", "recommended_interval_minutes" in ls or cc in ("control_plane_repair",), f"ls={ls}")
except Exception as e:
    check("vendor smoke 调用", False, repr(e)[:200])

print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败: {FAILED}")
    sys.exit(1)
print("✅ P1-15 LoopX cadence 映射验证通过")
