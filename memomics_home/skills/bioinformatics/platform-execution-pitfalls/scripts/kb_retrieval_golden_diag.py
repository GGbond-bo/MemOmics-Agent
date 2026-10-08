#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""KB 检索归因探针 —— 「黄金检索集红了，是数据漂移还是代码回归？」

用途：`webui/tests/test_kb_retrieval_golden.py` 或任何依赖具体排名的检索用例失败时，
一次打印判定所需的四组事实（见 references/kb-golden-retrieval-drift.md §3）：

  ① 该 query 的**真实排名**（目标文件到底排第几 ⇒ 是「被挤下去」还是「检索崩了」）
  ② 该 query 在 fixture 里的**期望口径**（top5 必须命中什么）
  ③ **污染源计数**：knowledge_base 里参与排名的 `*_empirical.yaml`（自进化 record_run 写入的运行记录）
  ④ **代码侧是否被改**：kb_search.py / 测试 / fixture 的 `git status`（交给调用者看，脚本只提示命令）

用法（Windows 项目根固定，可用 --repo 覆盖）：
    .venv/Scripts/python.exe kb_retrieval_golden_diag.py --query "差异表达分析 方法"
    ... --query "差异表达分析 方法" --fixture webui/tests/fixtures/kb_retrieval_golden.json

⛔ 只读探针：不写任何文件、不改 KB、不改 ranker。判为数据漂移后的处置候选（**需用户批准**）见参考文档 §5。
⚠️ 不要在本探针里写 `__file__`（若经 execute_python 的 exec(open(...)) 跑会 NameError）；用 --repo 或常量 BASE。
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import pathlib
import sys

BASE = r"E:/MemOmics-Agent"          # 项目根常量（可 --repo 覆盖，不用 __file__）


def load_kb_search(repo: pathlib.Path):
    """按路径加载 kb_search（同测试的做法：走包导入会拉起 hermes-agent 依赖）。"""
    path = repo / "memomics" / "bio_tools" / "kb_search.py"
    spec = importlib.util.spec_from_file_location("kb_diag_search", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fixture_expectation(fixture: pathlib.Path, query: str):
    """在黄金集 fixture 里找这条 query 的期望口径（找不到返回 None）。"""
    if not fixture or not fixture.exists():
        return None
    data = json.loads(fixture.read_text(encoding="utf-8"))
    for case in data.get("cases", []):
        if case.get("query") == query:
            return {
                "id": case.get("id"),
                "known_gap": bool(case.get("known_gap")),
                "top_k": data.get("top_k", 5),
                "expect_prefix": case.get("expect_prefix", []),
                "expect_contains": case.get("expect_contains", []),
            }
    return None


def expectation_hit(expect, ranked_files: list[str]) -> str:
    """期望口径是否落在前 top_k 名内（返回人类可读判定）。"""
    if not expect:
        return "（fixture 未提供该 query 的期望，跳过判定）"
    k = expect["top_k"]
    top = [f.replace("\\", "/").lower() for f in ranked_files[:k]]
    subs = [s.lower() for s in (expect.get("expect_prefix", []) + expect.get("expect_contains", []))]
    hit = next((f for f in top if any(s in f for s in subs)), None)
    return f"期望 {subs} @ top{k} → {'命中 ' + hit if hit else '★未命中（越出 top_k ⇒ 用例会红）'}"


def main() -> int:
    ap = argparse.ArgumentParser(description="KB 检索排名归因探针（只读）")
    ap.add_argument("--query", required=True, help="黄金集里的原查询串")
    ap.add_argument("--species", default="")
    ap.add_argument("--tissue", default="")
    ap.add_argument("--direction", default="")
    ap.add_argument("--top", type=int, default=12, help="打印前 N 名（默认 12）")
    ap.add_argument("--repo", default=BASE, help="项目根（默认常量 BASE）")
    ap.add_argument("--fixture", default="webui/tests/fixtures/kb_retrieval_golden.json")
    ap.add_argument("--keyword", default="deg", help="要统计的「文件名关键词」，如 deg / cellchat")
    a = ap.parse_args()

    repo = pathlib.Path(a.repo)
    kb = repo / "memomics" / "knowledge_base"
    print("=" * 72)
    print(f"query     = {a.query!r}   species={a.species!r} tissue={a.tissue!r} direction={a.direction!r}")
    print(f"repo      = {repo}")
    print("-" * 72)

    # ② 期望口径（先给判据，再看排名）
    expect = fixture_expectation(repo / a.fixture if not pathlib.Path(a.fixture).is_absolute()
                                 else pathlib.Path(a.fixture), a.query)
    if expect:
        print(f"[② 期望] case={expect['id']} top_k={expect['top_k']} known_gap={expect['known_gap']} "
              f"prefix={expect['expect_prefix']} contains={expect['expect_contains']}")
    else:
        print("[② 期望] fixture 里没有这条 query（或 --fixture 未给）")

    # ① 真实排名
    m = load_kb_search(repo)
    res = m._search_kb(a.query, a.species, a.tissue, a.direction)
    files = [r["file"] for r in res.get("results", [])]
    print(f"[① 排名] total={res.get('total')}")
    for i, f in enumerate(files[:a.top], 1):
        print(f"   {i:>2}  {f}")
    print(f"[① 判定] {expectation_hit(expect, files)}")

    # ③ 污染源计数
    print("-" * 72)
    emp = sorted(kb.rglob("*_empirical.yaml")) if kb.exists() else []
    print(f"[③ 污染源] *_empirical.yaml（自进化 record_run 写入，参与 BM25 排名）= {len(emp)} 个")
    for f in emp[:10]:
        print("    ", f.relative_to(repo).as_posix())
    if len(emp) > 10:
        print(f"     … 另有 {len(emp) - 10} 个")

    key = [f for f in (kb.rglob("*.yaml") if kb.exists() else []) if a.keyword.lower() in f.name.lower()]
    print(f"[③ 关键词] 文件名含 {a.keyword!r} 的 yaml = {len(key)} 个")
    for f in sorted(key)[:10]:
        print("    ", f.relative_to(repo).as_posix())

    cut = datetime.datetime.combine(datetime.date.today(), datetime.time()).timestamp()
    today = [f for f in (kb.rglob("*.yaml") if kb.exists() else []) if f.stat().st_mtime >= cut]
    print(f"[③ 今日写入] KB yaml（今天 mtime）= {len(today)} 个")

    # ④ 代码侧（只提示命令，不代替 git 判断）
    print("-" * 72)
    print("[④ 代码侧] 请跑：git status --porcelain memomics/bio_tools/kb_search.py "
          "webui/tests/test_kb_retrieval_golden.py " + a.fixture)
    print("           三处皆空 = 代码侧未改 ⇒ 结合 ① 判定「数据漂移，非代码回归」")
    print("=" * 72)
    print("⛔ 只读结论，不改 KB / ranker / 黄金集期望值 —— 处置候选须用户批准（见 references/kb-golden-retrieval-drift.md §5）")
    return 0


if __name__ == "__main__":
    sys.exit(main())