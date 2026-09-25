# -*- coding: utf-8 -*-
"""交互框「最新思考」条（2026-09-25）。

需求（用户原话）：交互框那里展示一排最新的思考，点击可以查看全文思考，
默认只展示最新的思考，像 DSH 一样"思考快速闪过展示"。

本文件两层验证：
1) 静态接线断言 —— 标记/样式/函数真的在 index.html 里，且被正确调用；
2) 真行为测试 —— 把前端函数抠出来在桩 DOM 上跑（think_strip_frontend.cjs）。
   index.html 没有构建步骤，所以这是最接近真机的自动化验证；
   浏览器端仍按 test_frontend_ux.py 的老规矩人工冒烟一次。
"""
import os
import shutil
import subprocess

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(TESTS_DIR, "..", "index.html")

with open(HTML_PATH, encoding="utf-8") as _f:
    HTML = _f.read()


class TestThinkStripMarkup:
    def test_strip_and_overlay_exist_once(self):
        for _id in ('id="think-strip"', 'id="think-strip-text"', 'id="think-overlay"',
                    'id="think-body"', 'id="think-title"'):
            assert HTML.count(_id) == 1, _id

    def test_strip_sits_above_input_row(self):
        """条子必须在输入框上方（贴着交互框），不能跑到消息流里。"""
        i_strip = HTML.index('id="think-strip"')
        i_row = HTML.index('<div class="input-row">')
        i_ta = HTML.index('id="input"')
        assert i_strip < i_row < i_ta

    def test_click_opens_full_text_and_esc_closes(self):
        assert 'onclick="openThinkModal()"' in HTML
        assert "if(event.target===this)closeThinkModal()" in HTML   # 点背景关掉
        assert "ev.key !== 'Escape'" in HTML
        assert "if (ov && ov.classList.contains('show')) closeThinkModal();" in HTML

    def test_css_present(self):
        assert ".think-strip.show { display:flex; }" in HTML
        assert "@keyframes tsFlash" in HTML          # "快速闪过"动画
        assert "#think-overlay.show" in HTML
        assert ".think-strip .ts-text.ts-flash" in HTML


class TestThinkStripWiring:
    def test_functions_defined(self):
        for fn in ("function _thinkLatestLine(", "function updateThinkStrip(",
                   "function openThinkModal(", "function closeThinkModal("):
            assert fn in HTML, fn

    def test_reasoning_event_feeds_strip(self):
        """流式 reasoning 事件必须同时喂折叠块和最新思考条。"""
        i = HTML.index("msg.type === 'reasoning'")
        block = HTML[i:i + 400]
        assert "reasoningText += (msg.content || '');" in block
        assert "updateReasoningBlock();" in block
        assert "updateThinkStrip(true);" in block

    def test_new_turn_resets_strip(self):
        assert "_thinkStripShown = '';" in HTML
        assert "updateThinkStrip(false);   // 新一轮开始" in HTML

    def test_turn_end_marks_done(self):
        """complete / error / cancelled 三个收尾分支都要把条子转成"已完成"淡色。"""
        assert HTML.count('updateThinkStrip(false);   // 收尾') == 3   # complete / error / cancelled
        assert HTML.count("updateThinkStrip(false);") == 4              # 3 个收尾 + 1 个新一轮重置

    def test_session_switch_restores_strip(self):
        assert "updateThinkStrip(!!cache.running);" in HTML

    def test_no_extra_server_state(self):
        """纯前端特性：不新增后端路由/接口，避免又要动冻结路由清单。"""
        assert "/api/think" not in HTML
        assert "reasoning_log" in HTML   # 历史消息里的思考仍走老字段回放


class TestThinkStripBehavior:
    def test_frontend_harness_passes(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("node 不可用")
        harness = os.path.join(TESTS_DIR, "think_strip_frontend.cjs")
        env = dict(os.environ, THINK_INDEX_HTML=os.path.abspath(HTML_PATH))
        r = subprocess.run([node, harness], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env, timeout=120)
        out = (r.stdout or "") + (r.stderr or "")
        assert "0 fail" in out, out[-3000:]
        assert r.returncode == 0, out[-3000:]
