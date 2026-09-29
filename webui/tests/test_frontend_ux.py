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


# ---------------------------------------------------------------- 场景5：悬浮浮条结构（仅"回到底部"，无重复停止按钮）
class TestFloatBarStructure:
    """多角度：唯一元素、onclick 绑定、CSS 定位、停止按钮不重复"""

    def test_goto_bottom_exists(self):
        assert 'id="float-goto-bottom"' in HTML
        assert 'id="chat-float-bar"' in HTML

    def test_stop_button_removed(self):
        # 停止按钮在底部输入区已有，悬浮条不重复：无 float-stop 元素/样式/绑定
        assert 'id="float-stop"' not in HTML
        assert "float-stop-btn" not in HTML

    def test_goto_bottom_binds_resume(self):
        assert 'onclick="resumeAutoScroll()"' in HTML

    def test_css_absolute_positioned(self):
        assert ".chat-float-bar { position:absolute" in HTML
        assert "z-index:50" in HTML

    def test_float_bar_hidden_by_default(self):
        # 初始 display:none，运行中才按需显示
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
        # 运行状态关闭时 _refreshGotoBottom 强制隐藏容器与按钮
        assert "_floatBarActive = !!show" in HTML
        assert "if (!_floatBarActive) { bar.style.display = 'none'; gb.style.display = 'none'; return; }" in HTML


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
        # 2026-08-27: 增量渲染器在新增 mermaid 块时触发 initMermaid（替代全文 hash 比较）
        assert "renderBubbleIncremental" in HTML
        assert "state.mermaidDirty" in HTML

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
        # 运行中（_floatBarActive）离开底部 → _refreshGotoBottom 显示；回到底部隐藏
        assert "function _refreshGotoBottom()" in HTML
        assert "if (!_floatBarActive) { bar.style.display = 'none'; gb.style.display = 'none'; return; }" in HTML
        assert "gb.style.display = atBottom ? 'none' : '';" in HTML

    def test_container_released_with_button(self):
        # 回归：容器 chat-float-bar 初始 display:none，显示按钮时必须同步放开容器
        # （历史 bug：只放按钮 display 不放容器 → 按钮永远不可见）
        idx = HTML.find("function _refreshGotoBottom")
        assert idx != -1
        seg = HTML[idx:idx + 700]
        assert "bar.style.display = atBottom ? 'none' : '';" in seg
        assert "gb.style.display = atBottom ? 'none' : '';" in seg

    def test_resume_hides_container_too(self):
        # 点击"回到底部"后容器与按钮一起隐藏
        idx = HTML.find("function resumeAutoScroll")
        assert idx != -1
        seg = HTML[idx:idx + 400]
        assert "bar.style.display = 'none'" in seg
        assert "gb.style.display = 'none'" in seg

    def test_grip_affordance(self):
        # grip 视觉可发现性（⋮⋮ 符号 + hover 高亮）
        assert "⋮⋮" in HTML
        assert ".chat-input .input-grip:hover" in HTML


# ---------------------------------------------------------------- 场景10：脚本结构完整性
class TestScriptIntegrity:
    """多角度：内联 script 块结构、关键函数不缺失、无残留旧函数"""

    def test_inline_script_blocks(self):
        """内联 script 结构（2026-09-28 现状）：i18n 字典块 + 主应用块 + 片头动画块，共 3 块。

        原来整页只有 1 个 script 块，P5 界面双语把 i18n 拆成了独立块（14KB），
        主块 470KB；2026-09-28 加入片头动画（开场动画）时又追加了第 3 块，
        它自成一体（片源/时机/画面选择 + 播放器），刻意不并进主块以便整块摘除。
        这里守的是「只有这几块、没有重复注入/残留的空块」，
        块数变了必须同步改这个用例（别再让"既有失败"挂着）。
        """
        blocks = _script_blocks()
        assert len(blocks) == 3, "内联 script 块数变了：%d" % len(blocks)
        assert not any(not b.strip() for b in blocks), "存在空 script 块"
        assert any("var I18N = {" in b for b in blocks), "i18n 块丢了"
        assert any("let currentSid = null;" in b for b in blocks), "主应用块丢了"
        # 片头块：自带片源清单与这两个入口，任一丢失都说明被误删/截断
        assert any("INTRO_CLIPS" in b and "function maybePlayIntro" in b for b in blocks), "片头动画块丢了"

    def test_intro_sidebar_entry_replaced_theme_cycler(self):
        """侧栏入口：原「🎨 背景」换成「🎬 片头设置」，且设置页的配色主题仍在。

        背景快捷切换（cycleTheme）在 2026-09-28 被片头设置入口取代；该函数本身
        保留未删，配色主题的正规入口一直是「设置 → 配色主题」，不许被一起删掉。
        """
        assert 'onclick="openIntroSettings()"' in HTML, "片头设置入口丢了"
        assert 'onclick="cycleTheme()"' not in HTML, "侧栏旧「背景」入口应已移除"
        assert 'id="theme-options"' in HTML, "设置页的配色主题选择器不应被删"
        assert "function cycleTheme()" in HTML, "cycleTheme 函数应保留（未删除）"
        assert "function openIntroSettings()" in HTML and "function renderIntroSettings()" in HTML

    def test_intro_clips_are_local_assets(self):
        """片头素材必须落在 /assets/intro/<品牌>/ 下，四段片源都在清单里。

        片头是本地文件（webui/assets/intro/{memomics,deepseek}/*.mp4，由 /assets 静态
        挂载提供），不引任何外链——离线安装包里也必须能播。
        """
        assert "/assets/intro/" in HTML
        for clip in ("brand", "cyberpunk", "awakening", "startup"):
            assert "'" + clip + "'" in HTML, "片源清单缺 " + clip
        # 地址由 introSrc() 拼出：/assets/intro/<品牌>/<片名>.mp4
        assert "function introSrc(clipId, brand)" in HTML
        assert "'/assets/intro/' + b + '/' + clipId + '.mp4'" in HTML
        # 只看 introSrc 的函数体：地址必须是本地路径，不许出现任何 http(s) 外链
        _src_fn = HTML.split("function introSrc")[1].split("\n}")[0]
        assert "http" not in _src_fn, "片源地址不许出现外链"

    def test_intro_brand_mode_switch(self):
        """「品牌」模式：默认 MemOmics 版，可切回 DeepSeek 原版（片内标识是烧进视频的，
        只能靠两套文件而不是 CSS 覆盖，所以两套文件都必须随包发）。"""
        assert "INTRO_BRANDS" in HTML, "品牌清单丢了"
        assert "'memomics'" in HTML and "'deepseek'" in HTML
        assert "intro-brand-options" in HTML, "对话框缺「品牌」分组"
        # 默认必须是 MemOmics（除非用户显式存过 deepseek）
        assert "c.brand === 'deepseek' ? 'deepseek' : 'memomics'" in HTML
        # 预览/播放都走 introSrc，不能有人绕过品牌直接读死路径
        assert "v.src = introSrc(clip.id, introCfg().brand)" in HTML

    def test_intro_settings_persist_and_can_be_disabled(self):
        """片头选择存 localStorage，且「关闭」是合法取值（用户有权不要片头）。"""
        assert "memomics-intro" in HTML
        assert "localStorage.setItem(INTRO_KEY" in HTML
        assert "'off'" in HTML, "必须支持关闭片头"
        # 与既有主题同一个 localStorage 套路
        assert "memomics-theme" in HTML

    def test_removed_old_min_48(self):
        # 旧 min=48 逻辑已移除
        assert "Math.max(48" not in HTML

    def test_resume_autoscroll_not_duplicated(self):
        assert HTML.count("function resumeAutoScroll") == 1

    def test_setfloatbar_not_duplicated(self):
        assert HTML.count("function setFloatBar") == 1

    def test_modified_segments_balanced(self):
        # 3 个核心交互区块必须括号配平（字符串/注释已剥离，区块内无正则量词）。
        # 标记随代码重构会改名：找不到标记说明这里过期了，按现状更新（不是"既有失败"）。
        def seg(start, end):
            i = HTML.find(start)
            assert i != -1, "marker not found: %s" % start
            j = HTML.find(end, i)
            assert j != -1, "end marker not found: %s" % end
            return _strip_strings_and_comments(HTML[i:j + len(end)])

        segments = [
            # 区块1：grip 拖拽 IIFE
            ("// === 输入框拖拽拉伸（2026-08-11", "})();"),
            # 区块2：流式渲染节流 + 阅读锚点补偿（2026-08-27 重构；旧的
            #        「// 防跳动：用户在上方阅读时」注释已随重命名消失）
            ("// === 流式渲染节流（2026-08-27", "}, 150);\n}"),
            # 区块3：智能滚动 + 回到底部浮条
            ("// 智能滚动：用户离开底部阅读时", "m.scrollTop = m.scrollHeight;\n}"),
        ]
        for start, end in segments:
            t = seg(start, end)
            for a, z in [("{", "}"), ("(", ")"), ("[", "]")]:
                assert t.count(a) == t.count(z), (
                    "segment %r unbalanced %s%s: %d vs %d" % (start, a, z, t.count(a), t.count(z))
                )


# --- 粘贴：文字优先，别把文字粘成图片（2026-09 用户报） -----------------------

def _fn_body(name):
    """按大括号配平抽出 index.html 里某个顶层函数的源码。"""

    at = HTML.find("function %s(" % name)
    assert at != -1, "index.html 里找不到 %s()" % name
    i = HTML.index("{", at)
    depth = 0
    for j in range(i, len(HTML)):
        if HTML[j] == "{":
            depth += 1
        elif HTML[j] == "}":
            depth -= 1
            if depth == 0:
                return HTML[at:j + 1]
    raise AssertionError("%s() 的大括号没闭合" % name)


def test_paste_prefers_text_over_clipboard_image():
    """从网页/Excel/Word 复制文字时，剪贴板里同时有文字和一份位图。

    旧实现只要发现 image 就 preventDefault，把整次粘贴吞掉：用户粘一段文字，
    结果贴进来一张图、文字没了（浏览器实测：剪贴板带 text/plain + image/png 时，
    输入框文字为空、图片附件 +1）。有文字的剪贴板必须完全不插手。
    """
    body = _fn_body("handlePaste")
    assert "_clipboardHasText" in body, "handlePaste 没判断剪贴板里有没有文字"
    i_text = body.index("_clipboardHasText")
    i_prevent = body.index("preventDefault")
    assert i_text < i_prevent, "preventDefault 排在判断文字之前，文字照样会被吞"
    assert "return" in body[i_text:i_prevent], "判断有文字后没有提前返回"

    helper = _fn_body("_clipboardHasText")
    assert "text/plain" in helper, "没检查 text/plain"
    assert "text/html" in helper, "没检查 text/html"


def test_paste_still_attaches_pure_image():
    """回归：纯截图（剪贴板里没有文字）仍然要能当附件贴进来。"""

    body = _fn_body("handlePaste")
    assert "addImagePreview" in body, "纯图粘贴这条路被删掉了"
    assert "getAsFile" in body, "没取图片 blob"
    assert "indexOf('image')" in body, "没判 image 类型"


def test_paste_of_text_only_is_never_intercepted():
    """边界：剪贴板里根本没有图片时，一个字节都不该拦。"""

    body = _fn_body("handlePaste")
    i_guard = body.index("if (!imageItem) return;")
    i_prevent = body.index("preventDefault")
    assert i_guard < i_prevent, "没有图片时也可能走到 preventDefault"


def test_drop_only_intercepts_images():
    """同类问题：拖进来的不是图片时不能拦，否则拖一段文字进输入框毫无反应。"""

    body = _fn_body("handleDrop")
    i_has = body.index("hasImage")
    i_prevent = body.index("preventDefault")
    assert i_has < i_prevent, "没先判断有没有图片就 preventDefault"
    assert "if (!hasImage) return;" in body, "非图片没有提前返回"
    assert "addImagePreview" in body, "图片拖放这条路被删掉了"
    # dragover 仍须无条件 preventDefault，否则元素不是合法放置目标
    over = _fn_body("handleDragOver")
    assert "preventDefault" in over, "dragover 不再 preventDefault，图片就拖不进来了"


def test_multi_image_callbacks_capture_their_own_file():
    """多图回调必须各自捕获自己的 file。

    循环里的 var 是共享的，用 IIFE 固定住才不会让所有回调都拿到最后一个文件名
    （图片字节取自 dataUrl，所以内容没错，错的是文件名）。
    """
    for fn in ("handleDrop", "handleFileSelect"):
        body = _fn_body(fn)
        assert "})(file);" in body or "})(file)" in body, \
            "%s 里的 file 没被 IIFE 固定住（多选/多拖时文件名会串）" % fn
