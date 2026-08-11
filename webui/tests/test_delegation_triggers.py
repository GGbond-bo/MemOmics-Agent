# -*- coding: utf-8 -*-
"""delegation 触发边界测试网（多场景 × 多角色 × 多角度）。

A. 规则覆盖矩阵：10+ 用户请求场景，断言每条都能映射到 SOUL.md 铁律 -7 的
   "应触发/不应触发"规则（防规则盲区）——多角色（生信分析/批量/文献/闲聊/辩论）
B. 工具可见性：delegate_task schema 暴露 + 黑名单剥离（子代理拿不到危险工具）
C. on_delegation 沉淀链路（子代理结论 → facts）
"""
import json
import os
import re

import pytest

from plugins.memory.holographic import HolographicMemoryProvider
from plugins.memory.holographic.store import MemoryStore

import session_state as ss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _soul_text():
    with open(os.path.join(ROOT, "hermes_home", "SOUL.md"), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# A. 规则覆盖矩阵：每条用户请求必须能在铁律 -7 找到明确处置
# ---------------------------------------------------------------------------

# 每项: (角色, 请求, 期望处置, 铁律-7 关键词/依据)
TRIGGER_MATRIX = [
    # —— 应触发（delegate_task 合理场景）——
    ("生信分析员", "分别跑一下样本 A/B/C 的 marker 分析，它们互不依赖",
     "trigger", "并行独立任务"),
    ("生信分析员", "把这 10 个样本跑相同的 QC 流程",
     "trigger", "批量同构任务"),
    ("文献专员", "帮我后台批量下载这 5 篇文献，期间我继续和你聊",
     "trigger", "长耗时后台任务"),
    ("调研员", "调研 ArchR 和 SnapATAC 的差异，内容比较多，别占用主对话",
     "trigger", "上下文隔离"),
    # —— 不应触发（delegate_task 禁用场景）——
    ("质控员", "这个差异分析结论可信吗？来一场正反辩论",
     "no_trigger", "辩论"),
    ("分析师", "把热图配色改成蓝白色",
     "no_trigger", "单步小任务"),
    ("分析师", "继续跑热图，用我之前给你的那个脚本",
     "no_trigger", "需要本会话记忆"),
    ("普通用户", "好的谢谢",
     "no_trigger", "非任务"),
    ("分析师", "帮我做一下差异分析的完整流程，按铁律走",
     "no_trigger", "需要走完整铁律链"),
    ("分析师", "帮我确认一下这个参数再跑，别自己决定",
     "no_trigger", "需要用户确认"),
]


class TestTriggerRuleMatrix:
    """每条请求都能在铁律 -7 找到明确处置（防规则盲区）。"""

    @pytest.fixture(scope="class")
    def soul(self):
        return _soul_text()

    def test_soul_has_rule7(self, soul):
        assert "铁律 -7" in soul and "delegate_task" in soul

    @pytest.mark.parametrize(
        "role,user_request,expect,rule",
        TRIGGER_MATRIX,
        ids=[f"case-{i}-{e}" for i, (_, _, e, _) in enumerate(TRIGGER_MATRIX)],
    )
    def test_scenario_covered(self, soul, role, user_request, expect, rule):
        # 铁律 -7 必须包含处置该场景的规则关键词
        assert rule in soul, f"规则 {rule!r} 不在铁律 -7 中——场景 {user_request!r} 无规则覆盖"
        # 分类器对该请求的意图应与场景角色一致（analysis 意图才可能触发）
        intent = ss.extract_entity(user_request)
        if expect == "trigger":
            assert intent, f"应触发场景无内容实体: {user_request!r}"

    def test_rule7_has_both_sides(self, soul):
        """铁律 -7 必须同时有启用表与禁用表（不能只写一边）。"""
        section = soul[soul.index("铁律 -7"):soul.index("铁律 -5")]
        assert "✅" in section and "❌" in section
        assert "并行独立任务" in section and "批量同构" in section
        assert "辩论" in section  # 辩论禁用决策必须显式写入


# ---------------------------------------------------------------------------
# B. 工具可见性 + 黑名单剥离（多角度）
# ---------------------------------------------------------------------------

class TestDelegationToolVisibility:
    def test_toolset_registered(self):
        from toolsets import TOOLSETS
        assert "delegation" in TOOLSETS
        assert TOOLSETS["delegation"]["tools"] == ["delegate_task"]

    def test_server_enables(self):
        src = open(os.path.join(ROOT, "webui", "server.py"), encoding="utf-8").read()
        m = re.search(r"enabled_toolsets=\[([^\]]*)\]", src)
        assert m and "delegation" in m.group(1)

    def test_blocked_tools_stripped_from_children(self):
        """子代理工具白名单必须剥离危险工具（黑名单机制）。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "delegate_tool", os.path.join(ROOT, "hermes-agent", "tools", "delegate_tool.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        blocked = mod.DELEGATE_BLOCKED_TOOLS
        assert "delegate_task" in blocked       # 禁递归
        assert "memory" in blocked              # 禁写共享记忆
        assert "clarify" in blocked             # 禁用户交互
        assert "execute_code" in blocked        # 禁写脚本
        assert "cronjob" in blocked             # 禁调度
        assert "send_message" in blocked        # 禁跨平台副作用

    def test_child_depth_flat_default(self):
        """默认 MAX_DEPTH=1：父→子扁平，无孙子代理。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "delegate_tool", os.path.join(ROOT, "hermes-agent", "tools", "delegate_tool.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.MAX_DEPTH == 1


# ---------------------------------------------------------------------------
# C. on_delegation 沉淀链路（多角色结论）
# ---------------------------------------------------------------------------

class TestDelegationSink:
    @pytest.fixture
    def provider(self, tmp_path):
        p = HolographicMemoryProvider(config={"db_path": str(tmp_path / "mem.db")})
        p.initialize(session_id="sess-parent")
        yield p
        p.shutdown()

    def test_bio_conclusion_sinks(self, provider):
        provider.on_delegation(
            task="跑 A 样本 marker",
            result="A 样本 top marker: CD3D(2.1), CD79A(3.4)",
            child_session_id="sa_bio_01",
        )
        facts = provider._store.list_facts(category="delegation", limit=10)
        assert len(facts) == 1
        f = facts[0]
        assert "CD3D" in f["content"] and "CD79A" in f["content"]
        assert f["tags"] == "subagent"

    def test_multi_child_conclusions_separate(self, provider):
        """多个子代理结论各自沉淀，互不覆盖。"""
        for i, (t, r) in enumerate([
            ("样本 A QC", "A: 过滤后 5200 cells"),
            ("样本 B QC", "B: 过滤后 6100 cells"),
            ("样本 C QC", "C: 过滤后 4800 cells"),
        ]):
            provider.on_delegation(task=t, result=r, child_session_id=f"sa_c{i}")
        facts = provider._store.list_facts(category="delegation", limit=10)
        assert len(facts) == 3
        contents = " ".join(f["content"] for f in facts)
        assert "5200" in contents and "6100" in contents and "4800" in contents

    def test_parent_facts_not_polluted(self, provider):
        """子代理结论不混入用户偏好/项目决策类。"""
        provider.on_delegation(task="调研", result="结论：ArchR 更适合 ATAC")
        provider._store.add_fact("用户偏好蓝白色", category="user_pref")
        provider._store.add_fact("项目统一用 pheatmap", category="project")
        cats = {f["category"] for f in provider._store.list_facts(limit=20)}
        assert "delegation" in cats and "user_pref" in cats and "project" in cats
        dl = provider._store.list_facts(category="delegation", limit=5)
        assert len(dl) == 1 and "ArchR" in dl[0]["content"]
