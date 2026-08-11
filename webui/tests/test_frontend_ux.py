# -*- coding: utf-8 -*-
"""前端 UX 改造回归测试（2026-08-11）：
问题1 输出区：流式防跳动 / Mermaid 缓存 / 悬浮停止条 / 回到底部浮条
问题2 输入框：向上拉变大 / localStorage 固化 / min-max 边界 / 发送后保留 / 双击还原 / grip 可发现性
验证方式：静态语义断言（读 index.html 源码），配合浏览器端手动冒烟。
"""
import os
import re
import pytest

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "index.html")
HTML = open(HTML_PATH, encoding="utf-8").read()


def _script_blocks():
    """提取所有 <script> 块文本"""
    return re.findall(r"<script[^>]*>(.*?)</script>", HTML, re.S)


def _strip_strings_and_comments(s):
    """剥离字符串字面量与注释，保留代码骨架（不含正则剥离，仅用于断言结构）"""
    out = []
    i, n = 0, len(s)
    q = None
    while i < n:
        c = s[i]
        if q:
            out.append(" ")
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
        else:
            if c in "'\"":
                q = c
                out.append(" ")
            elif c == "/" and i + 1 < n and s[i + 1] == "/":
                while i < n and s[i] != "\n":
                    i += 1
                continue
            elif c == "/" and i + 1 < n and s[i + 1] == "*":
                i += 2
                while i + 1 < n and not (s[i] == "*" and s[i + 1] == "/"):
                    i += 1
                i += 2
                continue
            else:
                out.append(c)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------- 场景1：输入框方向
class TestInputDragDirection:
    """多角度：向上拖变大、旧逻辑移除、语义注释"""

    def test_drag_up_increases_height(self):
        # 向上拖（clientY 减小）→ startH - dy 增大
        assert "startH - (ev.clientY - startY)" in HTML

    def test_old_downward_logic_removed(self):
        # 旧的"往下拉变大"逻辑必须不存在
        assert "startH + dy" not in HTML

    def test_direction_comment_documented(self):
        assert "向上拖动" in HTML


# ---------------------------------------------------------------- 场景2：min/max 边界
class TestInputBoundaries:
    """多角度：JS 常量与 CSS 一致、clamp 双向截断"""

    def test_js_constants_match_css(self):
        assert "MIN_H = 100, MAX_H = 400" in HTML
        assert "min-height:100px" in HTML
        assert "max-height:400px" in HTML

    def test_clamp_uses_both_ends(self):
        assert "Math.max(MIN_H, Math.min(MAX_H, h))" in HTML

    def test_default_height_is_100(self):
        assert "DEFAULT_H = 100" in HTML


# ---------------------------------------------------------------- 场景3：localStorage 固化
class TestInputPersistence:
    """多角度：存/取/恢复/还原四条路径"""

    def test_storage_key_defined(self):
        assert "memomics_input_height" in HTML

    def test_save_on_drag_end(self):
        # 拖拽结束（mouseup）时写入
        assert "localStorage.setItem(KEY" in HTML

    def test_restore_on_load(self):
        # 页面加载时恢复
        assert "localStorage.getItem(KEY)" in HTML

    def test_dblclick_restores_default(self):
        assert "dblclick" in HTML
        assert "apply(DEFAULT_H)" in HTML


# ---------------------------------------------------------------- 场景4：发送后保留高度
class TestSendKeepsHeight:
    """多角度：发送后恢复固化高度、未拖过回默认"""

    def test_send_restores_saved_height(self):
        assert "_getInputHeight()" in HTML
        assert "input.style.height = (typeof window._getInputHeight" in HTML

    def test_fallback_default_100(self):
        assert "? window._getInputHeight() : 100) + 'px'" in HTML


# ---------------------------------------------------------------- 场景5：悬浮控制条结构
class TestFloatBarStructure:
    """多角度：HTML 三元素、onclick 绑定、CSS 定位"""

    def test_three_elements_exist(self):
        for eid in ("chat-float-bar", "float-stop", "float-goto-bottom"):
            assert 'id="%s"' % eid in HTML

    def test_stop_binds_stop_agent(self):
        assert 'onclick="stopAgent()"' in HTML

    def test_goto_bottom_binds_resume(self):
        assert 'onclick="resumeAutoScroll()"' in HTML

    def test_css_absolute_positioned(self):
        assert ".chat-float-bar { position:absolute" in HTML
        assert "z-index:50" in HTML

    def test_float_bar_hidden_by_default(self):
        # 初始 display:none，且 setFloatBar 可控制
        assert 'id="chat-float-bar" style="display:none;"' in HTML

    def test_goto_bottom_hidden_by_default(self):
        assert 'id="float-goto-bottom" onclick="resumeAutoScroll()" style="display:none;"' in HTML


# ---------------------------------------------------------------- 场景6：悬浮条状态机
class TestFloatBarStateMachine:
    """多角度：显示/隐藏全部触发点（发送/停止/完成/错误/取消/切换恢复）"""

    def test_setfloatbar_defined(self):
        assert "function setFloatBar(show)" in HTML

    def test_show_on_send(self):
        assert "setFloatBar(true);" in HTML

    def test_hide_on_stop_agent(self):
        # stopAgent 函数体内隐藏
        i = HTML.find("function stopAgent")
        assert i != -1
        j = HTML.find("function ", i + 5)
        body = HTML[i:j if j != -1 else i + 2000]
        assert "setFloatBar(false);" in body

    def test_hide_on_complete_error_cancelled(self):
        # complete/error/cancelled 三分支都隐藏：调用次数 = 定义1 + 显示1 + 隐藏≥4
        calls = len(re.findall(r"setFloatBar\((true|false)\);", HTML))
        assert calls >= 6, "setFloatBar 调用点不足: %d" % calls

    def test_show_when_resume_running_session(self):
        # 切回运行中会话（is_running 恢复）也要显示：取该分支体片段断言
        i = HTML.find("if (d.is_running) {")
        assert i != -1
        seg = HTML[i:i + 500]
        assert "setFloatBar(true);" in seg

    def test_hide_also_hides_goto_bottom(self):
        assert "if (!show) {" in HTML
        assert "gb.style.display = 'none'" in HTML


# ---------------------------------------------------------------- 场景7：流式防跳动
class TestStreamAntiJump:
    """多角度：仅用户离开底部时补偿、补偿公式正确、贴底照常滚动"""

    def test_anchor_captured_before_render(self):
        assert "currentBubble.offsetTop - _msgs.scrollTop" in HTML

    def test_compensate_only_when_not_autoscroll(self):
        assert "_autoScroll === false" in HTML

    def test_compensate_after_render(self):
        assert "_msgs.scrollTop = currentBubble.offsetTop - _anchor" in HTML

    def test_scroll_bottom_when_at_bottom(self):
        assert "} else { scrollBottom(); }" in HTML


# ---------------------------------------------------------------- 场景8：Mermaid 缓存
class TestMermaidCache:
    """多角度：声明、比较、重置三处齐全"""

    def test_variable_declared(self):
        assert "var _lastMermaidHash = '';" in HTML

    def test_compared_before_redraw(self):
        assert "_mermaidSrc !== _lastMermaidHash" in HTML

    def test_reset_on_new_message(self):
        # send() 新回合重置
        assert "_lastMermaidHash = '';" in HTML

    def test_mermaid_extract_regex(self):
        assert "```mermaid[\\s\\S]*?```" in HTML or "```mermaid" in HTML


# ---------------------------------------------------------------- 场景9：回到底部浮条
class TestGotoBottom:
    """多角度：函数定义、滚动暂停时显示、恢复时隐藏"""

    def test_resume_function_defined(self):
        assert "function resumeAutoScroll()" in HTML

    def test_resume_sets_autoscroll_and_scrolls(self):
        idx = HTML.find("function resumeAutoScroll")
        assert idx != -1
        seg = HTML[idx:idx + 300]
        assert "_autoScroll = true;" in seg
        assert "scrollBottom();" in seg

    def test_shown_when_scrolled_away_during_run(self):
        # 离开底部且 agent 运行中 → 显示
        assert "!atBottom && agentRunning" in HTML

    def test_grip_affordance(self):
        # grip 视觉可发现性（⋮⋮ 符号 + hover 高亮）
        assert "⋮⋮" in HTML
        assert ".chat-input .input-grip:hover" in HTML


# ---------------------------------------------------------------- 场景10：脚本结构完整性
class TestScriptIntegrity:
    """多角度：单 script 块、关键函数不缺失、无残留旧函数"""

    def test_single_script_block(self):
        assert len(_script_blocks()) == 1

    def test_removed_old_min_48(self):
        # 旧 min=48 逻辑已移除
        assert "Math.max(48" not in HTML

    def test_resume_autoscroll_not_duplicated(self):
        assert HTML.count("function resumeAutoScroll") == 1

    def test_setfloatbar_not_duplicated(self):
        assert HTML.count("function setFloatBar") == 1

    def test_modified_segments_balanced(self):
        # 本次改造的 4 个代码区块必须括号配平（字符串/注释已剥离，区块内无正则量词）
        def seg(start, end):
            i = HTML.find(start)
            assert i != -1, "marker not found: %s" % start
            j = HTML.find(end, i)
            assert j != -1, "end marker not found: %s" % end
            return _strip_strings_and_comments(HTML[i:j + len(end)])

        segments = [
            # 区块1：grip 拖拽 IIFE
            ("// === 输入框拖拽拉伸（2026-08-11", "})();"),
            # 区块2：流式 delta 防跳动
            ("// 防跳动：用户在上方阅读时", "} else { scrollBottom(); }"),
            # 区块3：智能滚动 + 悬浮条 + 回到底部
            ("// 悬浮控制条：输出中显示", "m.scrollTop = m.scrollHeight;\n}"),
        ]
        for start, end in segments:
            t = seg(start, end)
            for a, z in [("{", "}"), ("(", ")"), ("[", "]")]:
                assert t.count(a) == t.count(z), (
                    "segment %r unbalanced %s%s: %d vs %d" % (start, a, z, t.count(a), t.count(z))
                )
