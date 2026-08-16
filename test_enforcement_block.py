# -*- coding: utf-8 -*-
"""执行保护门禁语义回归测试（2026-08-17 语义更新）。

新语义（用户要求）：
  - pre 审查未通过 → 硬阻断执行类工具（护栏：先审后跑），第 2 次起强制引导解绑
  - post 审查未通过 → 不硬阻断！产出已存在，给修复指引让 agent 继续解决问题
  - 任一审查通过 → 解绑；新用户消息 → clear_hard_block 重置
"""
import json
import sys

sys.path.insert(0, "E:/MemOmics-Agent")
sys.path.insert(0, "E:/MemOmics-Agent/hermes-agent")

from webui.enforcement import (
    create_enforcement_callbacks, get_enforcement, clear_hard_block,
)

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"[PASS] {name} — {detail}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} — {detail}")


sid = "e2e-block-new"
session = {"id": sid, "results_dir": "x", "messages": []}
events = []
cbs = create_enforcement_callbacks(session, lambda s, m: events.append(m), None)
es = get_enforcement(sid)

# S1: pre 失败 → 硬阻断
cbs["tool_complete_callback"]("r1", "rail_review", json.dumps({"phase": "pre"}),
                              json.dumps({"phase": "pre", "should_proceed": False, "issues": ["Missing packages: Seurat"]}))
check("S1 pre 失败→es.blocked 置位", es.blocked and es._block_kind == "rail_pre")

# S2: execute_r 被拦 + 提示含解除方式
r = cbs["tool_start_callback"]("r2", "execute_r", {"code": "readRDS('12G.rds')"})
check("S2 execute_r 被硬阻断", bool(r and r.get("blocked")))
check("S2b 提示含解除方式", r and "rail_review" in r["message"] and "新消息" in r["message"])

# S3: pre 通过 → 解绑
cbs["tool_complete_callback"]("r3", "rail_review", json.dumps({"phase": "pre"}),
                              json.dumps({"phase": "pre", "should_proceed": True}))
check("S3 pre 通过→解绑", not es.blocked and es._block_kind == "")
check("S3b 解绑后 execute_r 放行", not cbs["tool_start_callback"]("r3b", "execute_r", {"code": "x"}))

# S4: post 失败 → 不硬阻断 + 修复指引 require
cbs["tool_complete_callback"]("r4", "rail_review", json.dumps({"phase": "post"}),
                              json.dumps({"phase": "post", "passed": False, "issues": ["产物缺失"]}))
check("S4 post 失败→不置位 es.blocked", not es.blocked)
check("S4b post 失败→修复指引 require", any(
    e.get("action") == "require" and "修复后重新 rail_review" in e.get("message", "") for e in events))
r4 = cbs["tool_start_callback"]("r4b", "execute_r", {"code": "修复重跑"})
check("S4c post 失败后执行工具仍放行（可修复重跑）", not r4)

# S5: post 通过 → 保持放行（无硬阻断状态残留）
cbs["tool_complete_callback"]("r5", "rail_review", json.dumps({"phase": "post"}),
                              json.dumps({"phase": "post", "passed": True}))
check("S5 post 通过→放行", not es.blocked and es._blocked_attempts == 0)

# S6: pre 再失败 → 置位；新用户消息 clear_hard_block 重置（含 record_run 门禁）
cbs["tool_complete_callback"]("r6", "rail_review", json.dumps({"phase": "pre"}),
                              json.dumps({"phase": "pre", "should_proceed": False}))
check("S6 pre 再失败→置位", es.blocked)
was = clear_hard_block(sid)
r6 = cbs["tool_start_callback"]("r6b", "terminal", {"command": "Rscript fig.R"})
check("S7 新用户消息→重置阻断", was and not es.blocked and not r6 and not es._pending_record)

print(f"\n结果: PASS {PASS} / FAIL {FAIL}")
sys.exit(1 if FAIL else 0)
