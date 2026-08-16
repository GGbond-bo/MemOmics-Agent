# -*- coding: utf-8 -*-
"""执行保护硬阻断残留回归测试（12G Seurat 对象读取死锁案例）。

复现：rail_review(post) 未通过 → es.blocked 残留 → execute_r/terminal 永久被拦；
旧逻辑只有同阶段审查通过才解绑 + 新用户消息不重置 → 死锁。
修复后：任一阶段审查通过即解绑；新用户消息 clear_hard_block 重置本轮。
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


sid = "e2e-block-test"
session = {"id": sid, "results_dir": "x", "messages": []}
events = []
cbs = create_enforcement_callbacks(session, lambda s, m: events.append(m), None)
es = get_enforcement(sid)

# 场景 1: post 失败 → 硬阻断置位
cbs["tool_complete_callback"]("r1", "rail_review", json.dumps({"phase": "post"}),
                              json.dumps({"phase": "post", "passed": False, "issues": ["产物缺失"]}))
check("S1 post 失败→es.blocked 置位", es.blocked and es._block_kind == "rail_post")

# 场景 2: execute_r 被拦，且提示含解除方式
r = cbs["tool_start_callback"]("r2", "execute_r", {"code": "readRDS('12G.rds')"})
check("S2 execute_r 被硬阻断", bool(r and r.get("blocked")))
check("S2b 提示含解除方式", r and "重新 rail_review" in r["message"] and "新消息" in r["message"])

# 场景 3: 跨阶段解绑 —— 重跑 pre 通过 → 解绑（旧逻辑解不开 = 死锁）
cbs["tool_complete_callback"]("r3", "rail_review", json.dumps({"phase": "pre"}),
                              json.dumps({"phase": "pre", "should_proceed": True}))
check("S3 pre 通过→跨阶段解绑(旧逻辑死锁点)", not es.blocked and es._block_kind == "")

# 场景 4: 解绑后 execute_r 放行
r4 = cbs["tool_start_callback"]("r4", "execute_r", {"code": "readRDS('12G.rds')"})
check("S4 解绑后 execute_r 放行", not r4)

# 场景 5: 再次 post 失败 → 又置位；新用户消息 → clear_hard_block 重置
cbs["tool_complete_callback"]("r5", "rail_review", json.dumps({"phase": "post"}),
                              json.dumps({"phase": "post", "passed": False, "issues": ["x"]}))
check("S5 post 再次失败→置位", es.blocked)
was = clear_hard_block(sid)
r5 = cbs["tool_start_callback"]("r6", "terminal", {"command": "Rscript fig.R"})
check("S6 新用户消息→重置阻断(含 terminal/record 门禁)", was and not es.blocked and not r5 and not es._pending_record)

print(f"\n结果: PASS {PASS} / FAIL {FAIL}")
sys.exit(1 if FAIL else 0)
