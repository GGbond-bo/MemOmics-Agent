# -*- coding: utf-8 -*-
"""交互框历史回放「同轮合并」测试（2026-10-07）。

用户报告：实时流里一轮回答是一个气泡，但刷新页面 / 切走再回来，同一个会话被拆成
一串碎片气泡（每片各带自己的 ⏱ 耗时 / 🛠 工具数 / 📋 复制按钮），并要求
「原本是怎么展示的，那么刷新或者切换回来都还是怎么展示的」。

根因：Hermes 每次 LLM 调用都存成独立的 assistant 消息（中间夹 role=tool 消息），
历史回放按「一条消息一个气泡」渲染；而实时流是把整轮的 delta 一直累加进
同一个 currentAssistantEl。修法：两条回放路径统一走 _renderHistoryFlow()，
按 turn（一条用户提问 = 一轮）把连续 assistant 片段合并回一个气泡。

本文件：① 静态约束（回放路径必须用合并渲染、旧逐条渲染已删除）；
② 行为测试走 webui/tests/history_merge_frontend.cjs（抠真实函数 + 桩 DOM，
   可选 HISTORY_FIXTURE=<json> 用真实会话数据跑）。
"""
import os
import shutil
import subprocess

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(TESTS_DIR))
INDEX = os.path.join(REPO, "webui", "index.html")

with open(INDEX, encoding="utf-8") as _f:
    HTML = _f.read()


class TestHistoryMergeStatic:
    def test_render_flow_exists(self):
        assert "function _renderHistoryFlow(msgs) {" in HTML

    def test_both_replay_paths_use_merge(self):
        """loadAllMessages（加载全部）与切会话路径都必须走合并渲染。"""
        assert HTML.count("_renderHistoryFlow(") >= 3, "应有一处定义 + 两处调用"
        assert "var msgEls = _renderHistoryFlow(d.messages || []);" in HTML, "loadAllMessages 没走合并渲染"
        assert "var msgEls = _renderHistoryFlow(msgs);" in HTML, "切会话回放没走合并渲染"

    def test_old_per_message_loops_removed(self):
        """旧的逐条 addAssistantMsg(m.content, m) 回放循环必须消失（否则又拆碎片）。"""
        assert "addAssistantMsg(m.content, m)" not in HTML
        assert "else addAssistantMsg(m.content, m);" not in HTML

    def test_group_by_turn(self):
        i = HTML.index("function _renderHistoryFlow(msgs) {")
        body = HTML[i:i + 4200]
        assert "group.turn === t" in body, "合并必须按轮（turn）分组"
        assert "flushGroup()" in body

    def test_empty_sentinel_skipped(self):
        """Hermes 空响应哨兵 "(empty)" 不能当正文拼进合并气泡（实时流也不显示）。"""
        i = HTML.index("function _renderHistoryFlow(msgs) {")
        body = HTML[i:i + 4200]
        assert "'(empty)'" in body

    def test_user_and_assistant_return_elements(self):
        """msgEls 需要元素：addUserMsg 必须返回 div（addAssistantMsg 本来就返回）。"""
        i = HTML.index("function addUserMsg(")
        body = HTML[i:HTML.index("\nfunction ", i + 10)]
        assert "return div;" in body

    def test_msg_els_stay_index_aligned(self):
        """被合并片段的槽位仍要占位（辩论时间线按 after_index 取 msgEls[rel-1]）。"""
        i = HTML.index("function _renderHistoryFlow(msgs) {")
        body = HTML[i:i + 4200]
        assert "msgEls[i] = el || lastEl || null;" in body


class TestHistoryMergeHarness:
    def test_harness_passes(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("本机没有 node")
        r = subprocess.run([node, os.path.join(TESTS_DIR, "history_merge_frontend.cjs")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
        assert "0 fail" in (r.stdout or ""), r.stdout

    def test_harness_with_real_fixture(self):
        """可选：HISTORY_FIXTURE 指向真实 /api/sessions/<sid>/messages 的 JSON。"""
        fx = os.environ.get("HISTORY_FIXTURE", "")
        node = shutil.which("node")
        if not node or not fx or not os.path.exists(fx):
            pytest.skip("未提供 HISTORY_FIXTURE")
        env = dict(os.environ)
        r = subprocess.run([node, os.path.join(TESTS_DIR, "history_merge_frontend.cjs")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
        assert "0 fail" in (r.stdout or ""), r.stdout