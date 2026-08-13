# -*- coding: utf-8 -*-
"""P0-2 完成契约验证：_completion_contract_check / _contract_output_paths / _task_plan_active（离线）。"""
import os, sys, ast, types, re, tempfile, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
FAILED = []

def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)

with open(os.path.join(ROOT, "webui", "server.py"), encoding="utf-8") as f:
    tree = ast.parse(f.read())
funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
need = ["_contract_output_paths", "_completion_contract_check", "_task_plan_active"]
check("三个函数均已定义", all(k in funcs for k in need), f"missing={[k for k in need if k not in funcs]}")

mod = types.ModuleType("m")
mod.__dict__.update({"re": re, "os": os})
for k in need:
    if k in funcs:
        exec(ast.unparse(funcs[k]), mod.__dict__)

tmp = tempfile.mkdtemp(prefix="p02_")

# 场景1: 契约满足 — 复选框全勾 + 产出文件真实存在非空
out1 = os.path.join(tmp, "qc.png")
with open(out1, "wb") as f:
    f.write(b"PNGDATA123")
plan1 = (
    "# Task Plan\n"
    "## Phases\n"
    "### Phase 1: QC\n"
    "- [x] 过滤低质量细胞\n"
    f"- 产出: {tmp.replace(chr(92), '/')}/qc.png\n"
    "**Status:** completed\n"
)
r = mod._completion_contract_check(plan1, tmp)
check("契约满足 → True", r is True, f"got {r}")

# 场景2: 复选框有未勾选 → False
plan2 = plan1.replace("- [x] 过滤低质量细胞", "- [ ] 过滤低质量细胞")
r = mod._completion_contract_check(plan2, tmp)
check("未勾选复选框 → False", r is False, f"got {r}")

# 场景3: 声明的产出文件不存在 → False
plan3 = plan1.replace("qc.png", "missing.rds")
r = mod._completion_contract_check(plan3, tmp)
check("产出文件缺失 → False", r is False, f"got {r}")

# 场景4: 声明的产出文件为空 → False
empty = os.path.join(tmp, "empty.csv")
open(empty, "wb").close()
plan4 = plan1.replace("qc.png", "empty.csv")
r = mod._completion_contract_check(plan4, tmp)
check("产出文件为空 → False", r is False, f"got {r}")

# 场景5: 相对路径产出（相对于 results_dir）→ 存在则 True
sub = os.path.join(tmp, "results")
os.makedirs(sub, exist_ok=True)
with open(os.path.join(sub, "umap.png"), "wb") as f:
    f.write(b"X")
plan5 = "# Task Plan\n## Phases\n### Phase 2: 聚类\n- [x] 聚类\n产出: results/umap.png\n**Status:** completed\n"
r = mod._completion_contract_check(plan5, tmp)
check("相对路径产出存在 → True", r is True, f"got {r}")

# 场景6: 相对路径产出缺失 → False
plan6 = plan5.replace("umap.png", "no_such.png")
r = mod._completion_contract_check(plan6, tmp)
check("相对路径产出缺失 → False", r is False, f"got {r}")

# 场景7: 无复选框的旧格式 plan（无未勾选）→ 只查产出文件；此处产出存在 → True
plan7 = "# Task Plan\n## Phases\n### Phase 1\n产出: E:/x.rds\n**Status:** completed\n".replace(
    "E:/x.rds", f"{tmp.replace(chr(92), '/')}/qc.png")
r = mod._completion_contract_check(plan7, tmp)
check("旧格式无复选框+产出存在 → True", r is True, f"got {r}")

# 场景8: Environment 表工具路径（.exe）不参与契约校验
plan8 = "# Task Plan\n## Environment\n| Rscript | E:/R/R-4.2.2/bin/Rscript.exe |\n- [x] done\n**Status:** completed\n"
r = mod._completion_contract_check(plan8, tmp)
check(".exe 工具路径不误伤 → True", r is True, f"got {r}")

# 场景9: _task_plan_active — 完成标记命中但存在未勾选复选框 → 仍活跃(True)
r = mod._task_plan_active(tmp)
check("(tmp 无 task_plan) → False", r is False, f"got {r}")
tp = os.path.join(tmp, "task_plan.md")
with open(tp, "w", encoding="utf-8") as f:
    f.write("## 完成情况\n✅ 全部完成\n- [ ] 其实还有一步没做\n")
r = mod._task_plan_active(tmp)
check("完成标记+未勾选复选框 → 活跃(True)", r is True, f"got {r}")
with open(tp, "w", encoding="utf-8") as f:
    f.write("## 完成情况\n✅ 全部完成\n- [x] a\n- [x] b\n")
r = mod._task_plan_active(tmp)
check("完成标记+全勾选 → 不活跃(False)", r is False, f"got {r}")

shutil.rmtree(tmp, ignore_errors=True)
print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败: {FAILED}")
    sys.exit(1)
print("✅ P0-2 全部通过")
