# -*- coding: utf-8 -*-
"""超长上下文改造（2026-08-21 b/c）离线单测：
- (b) _strip_scaffold_text / _build_memory_digest：脚手架剥离与收紧
- (c) _maybe_rollup_history / _build_rollup_checkpoint：超预算折叠 + 尾窗保留
全部离线，不触发 LLM/网络。
"""
import os

import pytest

import server

pytestmark = pytest.mark.unit


def _digest(session, text):
    return server._build_memory_digest(session, text)


def _fake_session(sid="e2e-unit-test"):
    return {"id": sid, "results_dir": ""}


class TestStripScaffold:
    def test_digest_plus_question_strips_to_question(self):
        raw = (
            "[相关历史记忆 · 若与当前问题无关请忽略]\n"
            "- task_plan 设计原则：只放任务特有内容\n"
            "\n"
            "[会话锚点 · 跨压缩持久 · 重要文件/路径/脚本以这里为准]\n"
            "📁 E:/MemOmics-Agent/results/x/figures/Fig1.png\n"
            "\n"
            "不错，图呢？"
        )
        assert server._strip_scaffold_text(raw) == "不错，图呢？"

    def test_wake_notice_is_pure_scaffold(self):
        assert server._strip_scaffold_text("[系统唤醒 #0] 检查主线任务进度\n1. 读 task_plan.md") is None
        assert server._strip_scaffold_text("📊 LoopX 状态：\ngoal: active") is None
        assert server._strip_scaffold_text("[System: The previous response was cut off]") is None

    def test_normal_user_text_unchanged(self):
        assert server._strip_scaffold_text("怎么没有结果呢？") == "怎么没有结果呢？"

    def test_memory_digest_is_bounded(self):
        d = _digest(_fake_session(), "骨骼肌 衰老 运动")
        assert isinstance(d, str)
        assert len(d) <= 3000
        assert d == "" or d.startswith(("[相关历史记忆", "[会话锚点"))


def _msg(role, content):
    return {"role": role, "content": content}


class TestRollup:
    def _big_history(self, n=30):
        return [_msg("user" if i % 2 == 0 else "assistant", f"第 {i} 条消息：基因集打分 {i} 与亚群 {i%7} 的关系分析")
                for i in range(n)]

    def test_below_budget_unchanged(self, monkeypatch):
        monkeypatch.setenv("MEMOMICS_ROLLUP_BUDGET", "200000")
        h = self._big_history(30)
        out = server._maybe_rollup_history(_fake_session(), h)
        assert len(out) == len(h)
        assert out == h

    def test_over_budget_folds_head_keeps_tail(self, monkeypatch):
        monkeypatch.setenv("MEMOMICS_ROLLUP_BUDGET", "50")
        monkeypatch.setenv("MEMOMICS_ROLLUP_TAIL", "5")
        h = self._big_history(30)
        out = server._maybe_rollup_history(_fake_session(), h)
        assert len(out) == 6, f"expected 1 checkpoint + 5 tail, got {len(out)}"
        assert out[0]["role"] == "system"
        assert "[会话检查点" in out[0]["content"]
        # 尾窗逐字保留最后 5 条
        assert [m["content"] for m in out[1:]] == [m["content"] for m in h[-5:]]

    def test_tiny_history_skipped(self, monkeypatch):
        monkeypatch.setenv("MEMOMICS_ROLLUP_BUDGET", "10")
        h = self._big_history(5)
        out = server._maybe_rollup_history(_fake_session(), h)
        assert out == h

    def test_checkpoint_has_structured_sections(self):
        ck = server._build_rollup_checkpoint(_fake_session(), self._big_history(12))
        assert "## 会话" in ck
        assert "## 提示" in ck
        assert ck.startswith("[会话检查点")


def test_est_message_tokens_positive():
    assert server._est_message_tokens({"content": "中文内容，基因集打分亚群分析"}) >= 4
    assert server._est_message_tokens({"content": ""}) == 4
