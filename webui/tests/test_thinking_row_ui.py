# -*- coding: utf-8 -*-
"""思考行（💭「思考过程」那一行）—— 2026-09-25。

需求（用户原话，第二轮修正）：
    "💭 思考过程 (点击展开)，你不应该放在这里吗？新建一行干什么？
     而且点开可以看到全文，还能看到持续更新的内容"

也就是说：不要另外新起一行 —— 就用消息里原来那一行「💭 思考过程」：
  1) 那一行默认只显示最新一条思考（快速闪过），不是干巴巴的固定文案；
  2) 点开（原生 details）就是全文，运行中还能看到持续更新的内容（自动跟到最新）；
  3) 收尾后仍可点开看全文，提示里带字数。

本文件两层验证：
1) 静态接线断言 —— 结构/样式/调用点真的在 index.html 里，且旧方案（输入框上方的思考条 +
   全文浮层）已经完全移除，没有留下"多一行"的残留；
2) 真行为测试 —— 把前端函数抠出来在桩 DOM 上跑（thinking_row_frontend.cjs）。
   index.html 没有构建步骤，所以这是最接近真机的自动化验证；浏览器端另用 CDP 实跑一轮。
"""
import os
import shutil
import subprocess

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(TESTS_DIR, "..", "index.html")

with open(HTML_PATH, encoding="utf-8") as _f:
    HTML = _f.read()

# 思考行那段代码（用来断言它没偷偷调后端）
_i = HTML.index("// === 思考行")
ROW_CODE = HTML[_i:HTML.index("function addToolBlock(", _i)]


class TestThinkingRowIsTheOldLine:
    """核心：复用的就是原来那一行，没有新增任何一行。"""

    def test_no_extra_row_in_composer(self):
        for gone in ('id="think-strip"', 'class="think-strip"', 'think-strip-text',
                     'id="think-overlay"', 'class="think-box"', 'class="think-body"'):
            assert gone not in HTML, gone

    def test_old_mechanism_fully_removed(self):
        for gone in ("updateThinkStrip", "openThinkModal", "closeThinkModal",
                     "_thinkStripShown", "ts-more", "ts-icon"):
            assert gone not in HTML, gone

    def test_summary_is_the_thinking_line(self):
        assert '<summary><span class="rb-icon">💭</span><span class="rb-text">思考过程</span>' \
               '<span class="rb-meta">展开</span></summary>' in HTML
        assert '<div class="reasoning-content"></div>' in HTML

    def test_row_lives_in_message_flow_not_composer(self):
        """思考行必须挂在回答气泡里（.bubble 之前），跟交互框那一块毫无关系。"""
        assert "if (bubble) bubble.before(block); else hostEl.appendChild(block);" in HTML
        for gone in ("chat-input", "input-row", "input-grip"):
            assert gone not in ROW_CODE, gone   # 思考行代码不碰交互框


class TestThinkingRowStyles:
    def test_latest_line_styles(self):
        assert ".reasoning-block summary { display:flex; align-items:center; gap:6px; }" in HTML
        assert ".reasoning-block .rb-text {" in HTML
        assert "text-overflow:ellipsis" in HTML
        assert ".reasoning-block .rb-text.rb-flash { animation:tsFlash .45s ease-out; }" in HTML
        assert "@keyframes tsFlash" in HTML           # "快速闪过"
        assert "@keyframes tsPulse" in HTML           # 运行中 💭 呼吸
        assert ".reasoning-block.running .rb-icon" in HTML

    def test_full_text_scrolls(self):
        # 全文容器保持可滚动（老样式），展开时才有"持续更新"的观感
        assert ".reasoning-block .reasoning-content { padding:8px 12px;" in HTML
        assert "max-height:300px; overflow-y:auto;" in HTML


class TestThinkingRowWiring:
    def test_functions_defined(self):
        for fn in ("function _thinkLatestLine(", "function _thinkLineIn(", "function _rbRender(",
                   "function updateReasoningBlock(", "function finishReasoningBlock("):
            assert fn in HTML, fn

    def test_reasoning_event_shows_latest_line(self):
        i = HTML.index("msg.type === 'reasoning'")
        block = HTML[i:i + 400]
        assert "reasoningText += (msg.content || '');" in block
        assert "updateReasoningBlock(true);" in block

    def test_replay_restores_running_state(self):
        assert "updateReasoningBlock(!!msg.is_running);" in HTML

    def test_turn_end_finalizes(self):
        assert HTML.count("finishReasoningBlock();") == 3   # complete / error / cancelled

    def test_toggle_updates_hint(self):
        assert "block.addEventListener('toggle', function() {" in HTML
        assert "if (m) m.textContent = _rbMetaText(block);" in HTML

    def test_live_follow_scroll(self):
        """展开 + 运行中要跟着最新内容走，但用户自己往上翻时不抢滚动。"""
        assert "var stick = running && existing.open &&" in HTML
        assert "(content.scrollHeight - content.scrollTop - content.clientHeight) < 40;" in HTML
        assert "if (stick) content.scrollTop = content.scrollHeight;" in HTML

    def test_follow_decides_before_writing(self):
        """必须先判断"更新前是否贴底"再写新内容 —— 顺序写反了内容一长就永远跟不上
        （真机实测过：写反时 0/9 次跟随，改回来后 9/9；harness 里也有这条断言）。"""
        i_stick = HTML.index("var stick = running && existing.open &&")
        i_write = HTML.index("content.textContent = reasoningText;", i_stick)
        assert i_stick < i_write

    def test_history_row_restore(self):
        """刷新/切会话后，服务端持久化的思考要挂回最后一条回答（💭 行 → 点开是全文）。"""
        assert "function _rbAttach(hostEl, text, running) {" in HTML
        assert "function _rbRestoreHistoryRow() {" in HTML
        assert "_rbAttach(host, reasoningText, agentRunning);" in HTML
        assert HTML.count("_rbRestoreHistoryRow();") == 2        # 历史渲染完 + HTTP 进度兜底
        assert "if (d.reasoning_log && d.reasoning_log.length) {" in HTML   # HTTP 兜底也恢复思考
        assert "if (!currentAssistantEl && !running) {" in HTML   # 回放已完成任务 → 挂到真实回答，不造空气泡
        assert "if (!currentAssistantEl) return;" in HTML         # 注入消息被过滤时不留空宿主
        assert "existing._rbLen = reasoningText ? reasoningText.length : 0;" in HTML
        assert "block._rbLen = text.length;" in HTML              # 历史行按自己那份算字数

    def test_only_flashes_on_change(self):
        assert "if (line && line !== _rbLineShown) {" in HTML
        assert "void el.offsetWidth;" in HTML   # 强制重排才能重放同一动画

    def test_session_switch_needs_no_extra_work(self):
        # 思考行随 messageHtml 一起还原（含展开状态），不需要额外恢复逻辑
        assert "💭 行随 messageHtml 一起还原" in HTML

    def test_no_extra_server_state(self):
        """纯前端特性：不新增后端路由/接口，避免又要动冻结路由清单。"""
        assert "fetch(" not in ROW_CODE
        assert "/api/" not in ROW_CODE
        assert "reasoning_log" in HTML   # 历史思考仍走老字段回放

    def test_route_manifest_untouched(self):
        manifest = os.path.join(TESTS_DIR, "..", "middleware_routes.json")
        if not os.path.exists(manifest):
            pytest.skip("没有路由清单")
        with open(manifest, encoding="utf-8") as f:
            assert "think" not in f.read().lower()


class TestThinkingRowBehavior:
    def test_frontend_harness_passes(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("node 不可用")
        harness = os.path.join(TESTS_DIR, "thinking_row_frontend.cjs")
        env = dict(os.environ, THINK_INDEX_HTML=os.path.abspath(HTML_PATH))
        r = subprocess.run([node, harness], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env, timeout=120)
        out = (r.stdout or "") + (r.stderr or "")
        assert "0 fail" in out, out[-3000:]
        assert r.returncode == 0, out[-3000:]
