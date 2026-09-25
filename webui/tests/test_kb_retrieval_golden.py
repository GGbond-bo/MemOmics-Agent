"""黄金检索集回归：kb_search 必须把「问什么」回到「对应目录」。

背景（2026-08 实测，三处硬伤都已修，本测试是它们的回归护栏）：
1) FTS5 的 rank 是 bm25()，**越负越相关**；旧代码 100 + int(rank) 把强匹配算成了低分，
   排序整个反过来（问 CellChat，命中 cellchat.yaml 的候选排在只沾一个通用词的 method 后面）。
2) 只要查询里出现任何一个 <3 字符的词（中文双字词、单字母缩写，同义词表里满地都是），
   整条查询就退回 os.walk 子串打分；退回去的评分是纯词频 —— 谁的文件大谁赢
   （biology_knowledge.yaml 永远第一）。
3) 物种/组织/方向的路径权重只有 +25/+15/+10，压不过 BM25 量级：问「人骨骼肌衰老」，
   第一名是 exercise 目录、第三名是肝；问「小鼠肝衰老」，人肝排在小鼠肝前面。

期望值按**意图**写（问人骨骼肌衰老就该回到 Homo_sapiens/skeletal_muscle/aging/），
不是把当前输出抄成快照 —— 否则检索退化了测试也照样绿。known_gap 的用例只统计不断言。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.kb

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kb_retrieval_golden.json"


def _load_kb_search():
    """按路径加载 kb_search（memomics.bio_tools.__init__ 会拉起 hermes-agent 依赖，不能走包导入）。"""
    path = REPO_ROOT / "memomics" / "bio_tools" / "kb_search.py"
    spec = importlib.util.spec_from_file_location("memomics_kb_search_golden", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def kb_search():
    return _load_kb_search()


@pytest.fixture(scope="module")
def golden():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _norm(p: str) -> str:
    return p.replace("\\", "/").lower()


def _evaluate(kb_search, case, top_k):
    res = kb_search._search_kb(case["query"], case.get("species", ""),
                               case.get("tissue", ""), case.get("direction", ""))
    top = [_norm(r["file"]) for r in res.get("results", [])[:top_k]]
    if case.get("expect_none"):
        return res["total"] == 0, res["total"], top
    for pref in case.get("expect_prefix", []):
        if any(f.startswith(_norm(pref)) for f in top):
            return True, res["total"], top
    for sub in case.get("expect_contains", []):
        if any(_norm(sub) in f for f in top):
            return True, res["total"], top
    return False, res["total"], top


def test_golden_retrieval_cases(kb_search, golden):
    top_k = golden.get("top_k", 5)
    failures, gaps, passed = [], [], 0
    for case in golden["cases"]:
        ok, total, top = _evaluate(kb_search, case, top_k)
        if case.get("known_gap"):
            if not ok:
                gaps.append(case["id"])
            continue
        if ok:
            passed += 1
        else:
            failures.append("%s query=%r total=%d top%d=%s" % (
                case["id"], case["query"], total, top_k, top[:3]))
    strict = len([c for c in golden["cases"] if not c.get("known_gap")])
    print("黄金检索集: %d/%d 通过; 已知覆盖缺口: %s" % (passed, strict, gaps or "无"))
    assert not failures, "黄金检索集未通过：\n" + "\n".join(failures)


def test_golden_fixture_shape(golden):
    """fixture 自身要有意义：每条用例至少有一个判据，id 唯一。"""
    ids = [c["id"] for c in golden["cases"]]
    assert len(ids) == len(set(ids)), "用例 id 重复"
    assert len(ids) >= 20, "黄金集太小，起不到护栏作用"
    for c in golden["cases"]:
        has_judgement = c.get("expect_none") or c.get("expect_prefix") or c.get("expect_contains")
        assert has_judgement or c.get("known_gap"), "%s 既没有判据也不是已知缺口" % c["id"]
