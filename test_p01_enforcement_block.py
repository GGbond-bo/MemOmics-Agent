# -*- coding: utf-8 -*-
"""P0-1 硬阻断验证：enforcement 回调返回值协议 + tool_executor 接线（离线，不启动 server）。"""
import sys, os, json, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILED = []

def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)

# --- 1. enforcement 回调协议 ---
print("[1] enforcement 回调返回值协议")
import webui.enforcement as enf
from webui.enforcement import get_enforcement, create_enforcement_callbacks

# 清空旧状态（用唯一 sid 保证干净）
sid = f"test_p01_{os.getpid()}"
try:
    import webui.enforcement as _m
    if hasattr(_m, "_ENF_STATES"):
        _m._ENF_STATES.pop(sid, None)
except Exception:
    pass

session = {"id": sid, "task_plan": None}
emits = []
def fake_emit(etype, **kw):
    emits.append((etype, kw))
    print(f"    emit: {etype} {str(kw)[:100]}")

cbs = create_enforcement_callbacks(session, fake_emit, agent_ref=[None])
t_start, t_complete = cbs["tool_start_callback"], cbs["tool_complete_callback"]
es = get_enforcement(sid)
es.analysis_level = "analysis"
es.skills_loaded = ["scrna-qc"]

# 1.1 初始状态：terminal 放行（返回 None）
r = t_start("id1", "terminal", {"command": "ls /tmp"})
check("初始 terminal 放行(None)", r is None, f"got {r!r}")

# 1.2 terminal 完成后 pending_record 置位 → 下一个 terminal 被硬阻断
t_complete("id1", "terminal", {"command": "ls /tmp"}, json.dumps({"success": True}))
r = t_start("id2", "terminal", {"command": "pwd"})
check("pending_record 阻断 terminal", isinstance(r, dict) and r.get("blocked"), f"got {r!r}")

# 1.3 skill_evolution(record_run) 解除 pending_record 门禁
t_complete("id3", "skill_evolution", {"action": "record_run", "skill_name": "scrna-qc"}, json.dumps({"ok": True}))
r = t_start("id4", "terminal", {"command": "pwd"})
check("record_run 后 terminal 放行", r is None, f"got {r!r}")

# 1.4 rail_review(pre) 失败 → es.blocked=True → execute_r 被拦
t_complete("id5", "rail_review", {"phase": "pre"}, json.dumps({"should_proceed": False, "issues": ["数据集未确认"]}))
check("rail_pre 失败后 es.blocked=True", es.blocked is True, f"blocked={es.blocked}")
r = t_start("id6", "execute_r", {"code": "library(Seurat)"})
check("es.blocked 拦 execute_r", isinstance(r, dict) and r.get("blocked"), f"got {r!r}")
r = t_start("id7", "execute_python", {"code": "import scanpy"})
check("es.blocked 拦 execute_python", isinstance(r, dict) and r.get("blocked"), f"got {r!r}")

# 1.5 修复类工具放行（防死锁）
r = t_start("id8", "rail_review", {"phase": "pre"})
check("rail_review 放行(修复类)", r is None, f"got {r!r}")
r = t_start("id9", "skill_view", {"name": "scrna-qc"})
check("skill_view 放行(修复类)", r is None, f"got {r!r}")

# 1.6 rail_review(pre) 通过 → 解除
t_complete("id10", "rail_review", {"phase": "pre"}, json.dumps({"should_proceed": True}))
check("rail_pre 通过后解除", es.blocked is False, f"blocked={es.blocked}")
r = t_start("id11", "execute_r", {"code": "library(Seurat)"})
check("解除后 execute_r 放行", r is None, f"got {r!r}")

# 1.7 rail_review(post) 失败 → 阻断（bug②键名 passed）
t_complete("id12", "rail_review", {"phase": "post"}, json.dumps({"passed": False, "issues": ["统计方法存疑"]}))
check("rail_post 失败后 es.blocked=True", es.blocked is True, f"blocked={es.blocked}")
r = t_start("id13", "terminal", {"command": "pwd"})
check("rail_post 失败拦 terminal", isinstance(r, dict) and r.get("blocked"), f"got {r!r}")
t_complete("id14", "rail_review", {"phase": "post"}, json.dumps({"passed": True}))
check("rail_post 通过后解除", es.blocked is False, f"blocked={es.blocked}")

# 1.8 自杀命令硬阻断（一次性，不置位 blocked）
r = t_start("id15", "terminal", {"command": "taskkill /IM python /F"})
check("自杀命令硬阻断", isinstance(r, dict) and r.get("blocked"), f"got {r!r}")
check("自杀命令不置位 blocked", es.blocked is False, f"blocked={es.blocked}")
r = t_start("id16", "terminal", {"command": "pwd"})
check("自杀拦截后正常 terminal 放行", r is None, f"got {r!r}")

# --- 2. tool_executor 接线 ---
print("[2] tool_executor._callback_block_result")
import ast
with open(os.path.join("hermes-agent", "agent", "tool_executor.py"), encoding="utf-8") as f:
    _tree = ast.parse(f.read())
_found = [n for n in ast.walk(_tree) if isinstance(n, ast.FunctionDef) and n.name == "_callback_block_result"]
check("_callback_block_result 已定义", len(_found) == 1, f"found={len(_found)}")
if _found:
    _body = ast.unparse(_found[0])
    check("含 blocked 判定", "blocked" in _body)
    check("返回 message", '"message"' in _body)
# 提取函数体执行验证
import types
_mod = types.ModuleType("te")
_mod.__dict__["Any"] = object
exec(ast.unparse(_found[0]), _mod.__dict__)
try:
    check("blocked dict 返回消息", _mod._callback_block_result({"blocked": True, "message": "X"}) == "X")
    check("None 放行", _mod._callback_block_result(None) is None)
    check("非 dict 放行", _mod._callback_block_result("ok") is None)
    check("blocked 假值放行", _mod._callback_block_result({"blocked": False}) is None)
except Exception as e:
    check("函数可执行", False, repr(e))

print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败: {FAILED}")
    sys.exit(1)
print("✅ P0-1 全部通过")
