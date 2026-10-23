# -*- coding: utf-8 -*-
"""「关键过程」折叠层 = 阶段小结文字 —— 2026-10-23（用户口径修订）。

用户反馈（要点）：不要「各种文件」式的工具/参数清单，太麻烦；
要看大模型在任务期间的**思考阶段性总结** —— 比如触发了哪些 skill、有没有调用知识库、
环境用的什么、用了什么方法、方法有没有成功、是不是换了哪些方法；全是文字，塞进折叠层。

本文件验证：
1) 静态：渲染层只输出阶段小结（proc-stage/proc-no/proc-say），旧的明细采集/渲染已清除；
   中间回合回复规范（server.py）已改成「阶段小结」口径，tool_details 管线已撤；
2) 行为：webui/tests/proc_detail_frontend.cjs（抠真实 _procBlockHtml + 桩 markdown/tf）。
"""
import os
import shutil
import subprocess

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(TESTS_DIR))
INDEX = os.path.join(REPO, "webui", "index.html")
SERVER = os.path.join(REPO, "webui", "server.py")

with open(INDEX, encoding="utf-8") as _f:
    HTML = _f.read()
with open(SERVER, encoding="utf-8") as _f:
    SERVER_SRC = _f.read()


class TestRendererIsPlainText:
    def test_renderer_exists(self):
        assert "function _procBlockHtml(segs, opt) {" in HTML
        assert "proc-stage" in HTML and "proc-no" in HTML and "proc-say" in HTML

    def test_summary_counts_stages(self):
        assert "'proc_block':'📋 关键过程 · {0} 个阶段{1}（点击展开/收起）'" in HTML
        assert "tf('proc_block', (stats.steps != null) ? stats.steps : segs.length, dur)" in HTML

    def test_no_tool_or_file_rows_left(self):
        for gone in ("proc-act", "proc-step", "proc-acts", "_procItemHtml", "_procPushDetail",
                     "_procToolDone", "_procDetailItems", "toggleProcAct", "fullSegItems", "fullSegLead"):
            assert gone not in HTML, "残留：%s" % gone

    def test_frontend_no_tool_details(self):
        assert "tool_details" not in HTML

    def test_history_path_still_uses_segments_only(self):
        assert "function _renderHistoryFlow(msgs) {" in HTML
        assert "procSegs: procSegs" in HTML
        assert "_procDetailItems" not in HTML

    def test_thinking_still_not_dumped(self):
        i = HTML.index("function _splitProcessConclusion() {")
        body = HTML[i:i + 1600]
        assert "reasoningText" not in body, "折叠块不能塞模型思考（用户口径：思考刷屏）"

    def test_fold_guard_folds_even_when_complete_is_longer(self):
        # complete 带更长整稿时也要折 —— 否则整轮阶段小结摊在聊天里（用户反馈：这部分应该折叠）
        assert "var joinedAll = fullSegs.join('').trim();" in HTML
        assert "fullTrim.indexOf(joinedAll) === 0" in HTML
        assert "// 额外收尾并入结论（保内容完整）" in HTML


class TestServerPromptAndPlumbing:
    def test_prompt_is_stage_summary_style(self):
        # 用户口径（2026-10-23 三轮）：通用优先 —— 思考过程 + 执行过程做成小阶段总结
        assert "阶段小结 + 逻辑链" in SERVER_SRC
        assert "【怎么做】方法与做法" in SERVER_SRC
        assert "不限学科与任务类型" in SERVER_SRC
        assert "把**思考过程与执行过程**做成小阶段总结" in SERVER_SRC
        assert "【应变】" in SERVER_SRC and "原来用什么、为什么换、换成什么" in SERVER_SRC
        assert "不要罗列文件路径或文件名清单" in SERVER_SRC

    def test_tool_details_pipeline_removed(self):
        assert "tool_details" not in SERVER_SRC
        assert "_fmt_tool_details" not in SERVER_SRC

    def test_server_still_crlf(self):
        raw = open(SERVER, "rb").read()
        assert raw.count(b"\n") == raw.count(b"\r\n"), "server.py 出现裸 LF（CRLF 被破坏）"


class TestHarness:
    def test_frontend_harness(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("本机没有 node")
        r = subprocess.run([node, os.path.join(TESTS_DIR, "proc_detail_frontend.cjs")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        assert "0 fail" in out, out[-3000:]
        assert r.returncode == 0, out[-3000:]