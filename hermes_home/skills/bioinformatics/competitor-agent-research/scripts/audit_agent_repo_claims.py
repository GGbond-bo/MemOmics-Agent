#!/usr/bin/env python3
"""模式 E 探针：论文 claim ↔ 开源代码 审计的机械化部分。

用法:
    python audit_agent_repo_claims.py <repo_root> [--tool-dir biomni/tool] [--pkg biomni]

一条命令数出（全部来自真实代码，不引用论文数字）:
    · 工具"描述"条目数  <- agent/检索器实际看到的工具数（数 tool_description/*.py 的 list 条目）
    · 工具函数数        <- tool/*.py 的顶层 def 数（与上者常不一致，不一致本身就是发现）
    · 工具模块数 / 数据库 schema 数 / data_lake 数 / 软件清单数
    · 测试文件数        <- 论文声称"每工具带测试"时这是杀手锏
    · 每个函数的第三方 import 分布（**用 sys.stdlib_module_names 过滤**）
    · 无真实动作的函数清单（启发式，必须手工抽 1-2 个样本核查后再对外说 —— 见 references §4）
并打印 README 的版本/frozen 声明与 docs/known_conflicts.md 里的包名。

⛔ 不要用本脚本的直接输出对外下结论：先按 references/paper-vs-code-claim-audit.md §4 手工复核样本。
"""
from __future__ import annotations

import argparse
import ast
import os
import sys

STDLIB = set(sys.stdlib_module_names)
# 判定"有真实动作"的调用名（启发式；务必手工抽检）
ACTION_ATTRS = {
    "run", "Popen", "check_output", "check_call", "system",
    "get", "post", "put", "request",
    "read_csv", "read_table", "read_excel", "read_h5ad", "read_parquet", "read_json",
    "load", "loadtxt", "read", "imread", "savefig", "to_csv", "write",
    "gate", "subset", "compensate",
}
ACTION_NAMES = {"open", "exec", "eval", "compile"}


def _func_imports(fn: ast.AST) -> set[str]:
    """收集函数体内所有 import 的顶层模块名 —— 必须同时含 Import 与 ImportFrom。"""
    mods: set[str] = set()
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Import):
            for a in sub.names:
                mods.add(a.name.split(".")[0])
        elif isinstance(sub, ast.ImportFrom):
            if sub.module:
                mods.add(sub.module.split(".")[0])
    return mods


def _has_action_call(fn: ast.AST) -> bool:
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if isinstance(f, ast.Attribute) and f.attr in ACTION_ATTRS:
            return True
        if isinstance(f, ast.Name) and f.id in ACTION_NAMES:
            return True
    return False


def _list_len(node: ast.AST) -> int | None:
    """模块级 `x = [...]` / `x = [...]`(List) → 条目数。"""
    if isinstance(node, ast.List):
        return len(node.elts)
    return None


def scan_tool_modules(tool_dir: str):
    rows = []
    for name in sorted(os.listdir(tool_dir)):
        if not name.endswith(".py") or name in ("__init__.py", "tool_registry.py"):
            continue
        path = os.path.join(tool_dir, name)
        try:
            src = open(path, encoding="utf-8", errors="ignore").read()
            tree = ast.parse(src)
        except SyntaxError:
            rows.append(dict(module=name[:-3], n_func=0, funcs=[]))
            continue
        funcs = []
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            body = ast.get_source_segment(src, node) or ""
            mods = _func_imports(node)
            third = sorted(m for m in mods if m not in STDLIB and m != "biomni")
            funcs.append(dict(name=node.name, lines=body.count("\n"),
                              third=third, action=bool(third) or _has_action_call(node)))
        rows.append(dict(module=name[:-3], n_func=len(funcs), funcs=funcs))
    return rows


def scan_tool_descriptions(desc_dir: str) -> dict[str, int]:
    out = {}
    if not os.path.isdir(desc_dir):
        return out
    for name in sorted(os.listdir(desc_dir)):
        if not name.endswith(".py"):
            continue
        try:
            tree = ast.parse(open(os.path.join(desc_dir, name), encoding="utf-8",
                                  errors="ignore").read())
        except SyntaxError:
            continue
        n = 0
        for node in tree.body:
            if isinstance(node, ast.Assign):
                ln = _list_len(node.value)
                if ln:
                    n += ln
        out[name[:-3]] = n
    return out


def scan_env_dicts(path: str) -> dict[str, int]:
    out = {}
    if not os.path.isfile(path):
        return out
    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="ignore").read())
    except SyntaxError:
        return out
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = len(node.value.keys)
    return out


def find_tests(root: str) -> list[str]:
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", ".venv")]
        for f in filenames:
            if f.startswith("test_") and f.endswith(".py") or f.endswith("_test.py"):
                hits.append(os.path.relpath(os.path.join(dirpath, f), root))
    return hits


def show_readme_notes(root: str) -> None:
    for fn in ("README.md", "README.rst"):
        p = os.path.join(root, fn)
        if not os.path.isfile(p):
            continue
        txt = open(p, encoding="utf-8", errors="ignore").read()
        print(f"\n=== {fn}：版本/冻结/免责声明（逐字，交付时要引）===")
        keys = ("frozen", "Important Note", "not optimized", "privileges",
                "differs from", "release was")
        shown = set()
        for line in txt.splitlines():
            s = line.strip()
            if not s or s in shown:
                continue
            if any(k.lower() in s.lower() for k in keys):
                print("  •", s)
                shown.add(s)


def show_conflicts(root: str) -> None:
    for rel in ("docs/known_conflicts.md", "known_conflicts.md"):
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            txt = open(p, encoding="utf-8", errors="ignore").read()
            names = [l.split(". ", 1)[-1].strip() for l in txt.splitlines()
                     if l.strip().startswith(tuple("123456789")) and "." in l[:4]]
            print(f"\n=== {rel}：默认不安装 / 需手动启用的包 ===")
            for n in names:
                print("  •", n)
            return


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo_root")
    ap.add_argument("--pkg", default=None, help="包名（默认自动探测）")
    ap.add_argument("--tool-dir", default=None, help="tool 目录（默认 <pkg>/tool）")
    a = ap.parse_args()

    root = os.path.abspath(a.repo_root)
    if not os.path.isdir(root):
        print("!! repo_root 不是目录:", root)
        return 2

    pkg = a.pkg
    if pkg is None:
        cands = [d for d in os.listdir(root)
                 if os.path.isdir(os.path.join(root, d, "tool"))]
        pkg = cands[0] if cands else None
    if pkg is None:
        print("!! 找不到包目录（含 tool/ 的子目录），请用 --pkg 指定")
        return 2

    tool_dir = a.tool_dir or os.path.join(pkg, "tool")
    desc_dir = os.path.join(tool_dir, "tool_description")
    schema_dir = os.path.join(tool_dir, "schema_db")

    rows = scan_tool_modules(tool_dir)
    desc = scan_tool_descriptions(desc_dir)
    schema_n = len([f for f in os.listdir(schema_dir) if f.endswith(".pkl")]) \
        if os.path.isdir(schema_dir) else 0
    env_path = os.path.join(pkg, "env_desc.py")
    env = scan_env_dicts(env_path)
    tests = find_tests(root)

    n_func = sum(r["n_func"] for r in rows)
    n_desc = sum(desc.values())
    allf = [f for r in rows for f in r["funcs"]]
    no_action = [f for f in allf if not f["action"]]

    print("=" * 72)
    print(f"# 论文 claim ↔ 代码实测扫描   repo={root}   pkg={pkg}")
    print("=" * 72)
    print(f"工具『描述』条目数 (agent/检索器实际可见) : {n_desc}")
    print(f"工具函数数 (顶层 def)                    : {n_func}")
    print(f"工具模块数                                : {len(rows)}")
    print(f"数据库 schema (*.pkl)                     : {schema_n}")
    for k, v in env.items():
        print(f"env_desc.{k:28s}: {v}")
    print(f"测试文件数                                : {len(tests)}")
    if tests:
        for t in tests[:15]:
            print("    -", t)

    if n_desc and n_func and n_desc != n_func:
        print(f"\n⚠️ 描述数({n_desc}) ≠ 函数数({n_func}) —— 这个不一致本身就是发现，要写进交付表。")

    print(f"\n=== 第三方 import 直方图（已用 sys.stdlib_module_names 过滤）===")
    hist: dict[str, int] = {}
    for f in allf:
        for m in f["third"]:
            hist[m] = hist.get(m, 0) + 1
    for k, v in sorted(hist.items(), key=lambda x: -x[1])[:30]:
        print(f"  {k:28s} {v}")

    print(f"\n=== 无真实动作的候选函数（启发式！必须先手工抽 1-2 个样本核验再对外说）===")
    print(f"count = {len(no_action)} / {n_func}"
          f"  ({len(no_action)/n_func:.0%} 若不核验就报，极可能高估 —— 见 references §4)"
          if n_func else "")
    for f in no_action[:40]:
        print(f"  [{f['lines']:>4d}行] {f['name']}")

    show_readme_notes(root)
    show_conflicts(root)
    print("\n下一步：手读 agent 主文件 + retriever + 资源加载器，把结论落到『是什么』而不是『有多少』。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())