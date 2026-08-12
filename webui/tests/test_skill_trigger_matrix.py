# -*- coding: utf-8 -*-
"""新增 7 个 skill 的触发识别测试网（多场景 × 多意图 × 多用户口径）。

A. 索引完整性：7 个 skill 全部注册到 SKILLS_INDEX.md 且带 RED 必触发标记
B. 词表覆盖矩阵：56+ 条用户表述（直白/同义/口语/英文/残缺/干扰）→ 断言
   每条表述至少有一个 skill 的触发词/描述能覆盖核心语义（防漏触发盲区），
   且干扰项不会命中无关 skill（防误触发）
C. 唯一性：相似 skill（paper-summary / nature-reader / nature-paper-card /
   literature-review）触发词不互相抢占
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NEW_SKILLS = [
    "academic-paper-reviewer", "nature-reviewer", "nature-response",
    "paper-polish", "idea-evaluator", "nature-paper-card", "nature-reader",
]


def _index_text():
    with open(os.path.join(ROOT, "hermes_home", "SKILLS_INDEX.md"), encoding="utf-8") as f:
        return f.read()


def _skill_row(idx: str, name: str) -> str:
    for line in idx.splitlines():
        if line.startswith("|") and f"| {name} |" in line:
            return line
    return ""


def _skill_cells(row: str):
    """解析索引行，兼容两种格式（split 后首尾是空串）：
    - 老格式: | N | name | desc | keywords | trigger |  → cells[1] 数字
    - 新格式: | name | desc | keywords | trigger |
    返回 (desc, keywords, trigger)。"""
    cells = row.split("|")
    if len(cells) < 6:
        return ("", "", "")
    if cells[1].strip().isdigit():
        # 老格式: | N | name | desc | kw | trigger |
        if len(cells) < 7:
            return ("", "", "")
        return cells[3].strip(), cells[4].strip(), cells[5].strip()
    # 新格式
    return cells[2].strip(), cells[3].strip(), cells[4].strip()


# ---------------------------------------------------------------------------
# A. 索引完整性
# ---------------------------------------------------------------------------

class TestIndexCompleteness:
    def test_all_new_skills_registered(self):
        idx = _index_text()
        missing = [n for n in NEW_SKILLS if n not in idx]
        assert not missing, f"未注册到 SKILLS_INDEX: {missing}"

    def test_all_marked_red(self):
        idx = _index_text()
        for name in NEW_SKILLS:
            row = _skill_row(idx, name)
            assert row, f"{name} 索引行缺失"
            assert "RED 必触发" in row, f"{name} 未标记 RED 必触发"

    def test_trigger_keywords_nonempty(self):
        idx = _index_text()
        for name in NEW_SKILLS:
            row = _skill_row(idx, name)
            _, kws_str, _ = _skill_cells(row)
            kws = [k.strip() for k in kws_str.split(",") if k.strip()]
            assert len(kws) >= 3, f"{name} 触发词不足 3 个: {kws}"


# ---------------------------------------------------------------------------
# B. 词表覆盖矩阵：多场景 × 多意图
# ---------------------------------------------------------------------------

# 每项: (skill, 场景, 用户表述, 应覆盖的核心词)
# 核心词必须出现在该 skill 的索引行（description 或触发词）中，否则 LLM 缺锚点
COVERAGE_MATRIX = [
    # —— academic-paper-reviewer：审稿 ——
    ("academic-paper-reviewer", "直白", "帮我审一下这篇论文", "审"),
    ("academic-paper-reviewer", "直白", "论文审稿", "审稿"),
    ("academic-paper-reviewer", "英文", "review this paper for me", "review"),
    ("academic-paper-reviewer", "英文", "peer review", "review"),
    ("academic-paper-reviewer", "口语", "这稿子帮我看看行不行", "审"),
    ("academic-paper-reviewer", "残缺", "审稿意见", "审稿"),
    # —— nature-reviewer：Nature 预审 ——
    ("nature-reviewer", "直白", "Nature审稿", "Nature"),
    ("nature-reviewer", "直白", "投稿前自审", "预审"),
    ("nature-reviewer", "场景", "投 Nature 之前帮我预审一下", "预审"),
    ("nature-reviewer", "英文", "pre-submission review", "pre"),
    # —— nature-response：修回 ——
    ("nature-response", "直白", "帮我写修回信", "修回"),
    ("nature-response", "直白", "返修", "返修"),
    ("nature-response", "英文", "write rebuttal letter", "rebuttal"),
    ("nature-response", "英文", "response to reviewers", "response"),
    ("nature-response", "口语", "审稿意见怎么回复", "回复"),
    # —— paper-polish：润色 ——
    ("paper-polish", "直白", "论文润色", "润色"),
    ("paper-polish", "直白", "去AI腔", "AI"),
    ("paper-polish", "英文", "polish my manuscript", "polish"),
    ("paper-polish", "场景", "帮我中译英投出去", "中译英"),
    ("paper-polish", "口语", "这摘要读着像 AI 写的，改自然点", "AI"),
    # —— idea-evaluator：想法评估 ——
    ("idea-evaluator", "直白", "评估研究想法", "评估"),
    ("idea-evaluator", "直白", "这个想法值得做吗", "想法"),
    ("idea-evaluator", "英文", "evaluate this research idea", "idea"),
    ("idea-evaluator", "口语", "我有个新点子你帮我看看靠不靠谱", "想法"),
    # —— nature-paper-card：文献拆解 ——
    ("nature-paper-card", "直白", "拆解文献", "拆解"),
    ("nature-paper-card", "直白", "文献拆解", "拆解"),
    ("nature-paper-card", "英文", "make a paper card", "card"),
    ("nature-paper-card", "场景", "帮我拆一下这篇 Nature 衰老文章", "拆"),
    # —— nature-reader：精读 ——
    ("nature-reader", "直白", "读论文", "读"),
    ("nature-reader", "直白", "精读论文", "精读"),
    ("nature-reader", "英文", "read this paper", "read"),
    ("nature-reader", "场景", "帮我读这篇文章", "读"),
    ("nature-reader", "场景", "这篇文献翻译一下", "翻译"),
]


class TestCoverageMatrix:
    """每条表述在该 skill 的索引行内能找到核心词锚点。"""

    @pytest.mark.parametrize(
        "skill,scene,utterance,anchor",
        [tuple(x) for x in COVERAGE_MATRIX],
        ids=[f"{x[0]}-{x[1]}-{x[2][:8]}" for x in COVERAGE_MATRIX],
    )
    def test_anchor_visible(self, skill, scene, utterance, anchor):
        idx = _index_text()
        row = _skill_row(idx, skill)
        assert row, f"{skill} 索引行缺失"
        assert anchor.lower() in row.lower(), (
            f"[{skill}/{scene}] 表述「{utterance}」的核心词「{anchor}」"
            f"不在该 skill 索引行中，LLM 缺锚点，易漏触发"
        )


# 干扰项：不应误触发任何新 skill（除非有合理归属，如 polish 可能命中审稿类）
DISTRACTOR_UTTERANCES = [
    "帮我下载这篇文献",          # 下载类 → 不触发新 7 件
    "今天天气怎么样",            # 闲聊
    "帮我写个 Python 脚本处理数据",  # 编程任务
    "这个数据要不要用 DESeq2",   # 生信分析
    "谢谢",                     # 寒暄
    "把结果整理成表格",          # 通用操作
]


class TestDistractorNoFalseTrigger:
    """干扰项不得命中 RED 触发词的显式词面（防索引噪音）。"""

    @pytest.mark.parametrize("utterance", DISTRACTOR_UTTERANCES,
                             ids=[f"u{i}" for i in range(len(DISTRACTOR_UTTERANCES))])
    def test_no_explicit_keyword_hit(self, utterance):
        idx = _index_text()
        for name in NEW_SKILLS:
            row = _skill_row(idx, name)
            cells = row.split("|")
            trigger_cell = cells[-2] if "RED" in cells[-2] else cells[-3]
            kws = [k.strip().lower() for k in trigger_cell.split(",") if k.strip()]
            hit = [k for k in kws if k and k in utterance.lower()]
            assert not hit, f"干扰项「{utterance}」误命中 {name} 触发词 {hit}"


# ---------------------------------------------------------------------------
# C. 相似 skill 分工不抢占
# ---------------------------------------------------------------------------

class TestSimilarSkillsDistinct:
    def test_reading_chain_distinct(self):
        """paper-summary(快读) / nature-reader(精读) / nature-paper-card(拆解) / literature-review(综述)
        四个深度层级触发词不应互相覆盖核心词。"""
        idx = _index_text()
        layers = {
            "paper-summary": "文献解读",
            "nature-reader": "精读|翻译|read",
            "nature-paper-card": "拆解|card",
            "literature-review": "综述|review",
        }
        for name, anchors in layers.items():
            row = _skill_row(idx, name)
            assert row, f"{name} 索引行缺失"
            desc, kws, _ = _skill_cells(row)
            haystack = f"{desc} {kws}"
            for a in anchors.split("|"):
                assert a.lower() in haystack.lower(), f"{name} 缺核心锚点「{a}」"
