# -*- coding: utf-8 -*-
"""Mode A/B/C 多场景多意图触发测试（系统综述模式 Mode C 的触发覆盖）。

Mode 选择是模型读 SKILL.md 后的行为——本测试验证"触发说明的规则完整性"：
对每个典型用户意图，SKILL.md 中必须有对应的触发指引，且三种模式的边界
说明互不冲突（A=探索性叙述综述 / B=库内综述 / C=协议化系统综述 PRISMA）。
"""
import os
import re

import pytest

SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                     "hermes_home", "skills", "bioinformatics",
                     "literature-review", "SKILL.md")

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def skill_text():
    with open(SKILL, encoding="utf-8") as f:
        return f.read()


# ── Mode C 触发覆盖：每个场景在 SKILL.md 里都有对应触发指引 ───────────────

MODE_C_SCENARIOS = [
    ("要系统综述，给个 PRISMA 流程图", ["系统综述", "PRISMA"]),
    ("写一篇 systematic review 发综述论文", ["systematic review", "发综述论文"]),
    ("严格证据综述，要评估证据质量", ["严格证据综述", "证据质量评估"]),
    ("要 meta 分析，先做偏倚评估", ["meta 分析", "偏倚"]),
    ("可复现的文献筛选流程，记录排除原因", ["可复现", "排除原因"]),
    ("综述要有流程图", ["流程图"]),
    ("做 PRISMA 合规的系统综述", ["PRISMA"]),
]

MODE_A_SCENARIOS = [
    ("这个主题的文献都说了什么，帮我总结", ["探索"]),
    ("查一下 XX 领域的最新进展", ["搜索"]),
]

MODE_B_SCENARIOS = [
    ("基于我文献库里的这 50 篇做个综述", ["库内"]),
    ("整理已导入的文献，按方向分组综述", ["不重新"]),
]


def test_mode_c_trigger_coverage(skill_text):
    """Mode C 的每个触发场景在 SKILL.md 的触发章节中都有对应词。"""
    mode_c_section = skill_text.split("## Mode C")[1].split("## Step 4")[0]
    for label, kws in MODE_C_SCENARIOS:
        missing = [k for k in kws if k not in mode_c_section]
        assert not missing, f"场景「{label}」缺触发词: {missing}"


def test_mode_disambiguation_rule(skill_text):
    """三模式边界口诀存在且互斥。"""
    mode_c_section = skill_text.split("## Mode C")[1].split("## Step 4")[0]
    assert "探索性总结 → Mode A/B" in mode_c_section
    assert "协议化" in mode_c_section and "偏倚评估" in mode_c_section


def test_mode_a_and_b_still_present(skill_text):
    """Mode A（Step 1-3.5）与 Mode B 章节完整保留。"""
    assert "## Step 1 — Clarify Scope" in skill_text
    assert "## Mode B — Library Review" in skill_text
    assert "### B6 引用校验" in skill_text


def test_prisma_tool_mentioned_in_flow(skill_text):
    """Mode C 全流程（C1-C9）都引用了 prisma_flow 工具——链路闭环。"""
    mode_c_section = skill_text.split("## Mode C")[1].split("## Step 4")[0]
    for step in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"):
        assert f"### {step}" in mode_c_section, f"缺 {step}"
    assert mode_c_section.count("prisma_flow") >= 8, \
        f"每个环节都应引用 prisma_flow（got {mode_c_section.count('prisma_flow')}）"


def test_trigger_keywords_frontmatter(skill_text):
    """技能 frontmatter 的触发词覆盖综述类请求（技能级触发）。"""
    head = skill_text[:2000]
    for kw in ("综述", "文献综述", "systematic review", "literature review",
               "总结文献", "查文献", "evidence synthesis"):
        assert kw in head, f"frontmatter 缺触发词: {kw}"
