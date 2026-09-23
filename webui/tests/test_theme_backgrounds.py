# -*- coding: utf-8 -*-
"""webUI 背景配色测试网（简化版）：护眼/科研/羊皮纸 3 主题 + JS 语法 + 白名单。"""
import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX = os.path.join(ROOT, "webui", "index.html")


def _html():
    with io.open(INDEX, encoding="utf-8") as f:
        return f.read()


NEW_THEMES = ["eye", "sci", "parchment"]


class TestThemeColors:
    def test_new_themes_defined(self):
        src = _html()
        for t in NEW_THEMES:
            assert '[data-theme="%s"]' % t in src, "%s theme missing" % t

    def test_original_themes_kept(self):
        src = _html()
        assert ":root" in src  # light 是默认（:root），无独立 [data-theme] 块
        for t in ["dark", "blue"]:
            assert '[data-theme="%s"]' % t in src, "%s theme missing" % t

    def test_presets_cover_new_themes(self):
        src = _html()
        m = re.search(r"var THEME_PRESETS = \[(.*?)\];", src, re.S)
        assert m, "THEME_PRESETS not found"
        ids = re.findall(r"id:'([a-z]+)'", m.group(1))
        assert set(NEW_THEMES) <= set(ids)
        # 主题清单以 CSS 为准（light 是 :root 默认，没有独立 [data-theme] 块）：
        # 每个有样式的主题都必须有对应预设，预设也不许多出没有样式的 id。
        # 原来这里写死 6，2026-09 加了第 7 个主题（pink）就过期了。
        css_themes = set(re.findall(r'\[data-theme="([a-z]+)"\]', src)) | {"light"}
        assert css_themes == set(ids), (
            "CSS 主题 %s 与 THEME_PRESETS %s 不一致（加主题时两处都要改）"
            % (sorted(css_themes), sorted(ids))
        )
        assert len(ids) == len(set(ids)), "THEME_PRESETS 有重复 id"

    def test_parchment_has_texture_only(self):
        """羊皮纸有质感层；其他主题无背景层；无粒子/装饰/角标。"""
        src = _html()
        # parchment 专属纹理
        assert 'html[data-theme="parchment"] body::before' in src
        assert "repeating-radial-gradient" in src  # 纸纹噪点
        assert "radial-gradient(ellipse" in src    # 边缘暗角
        # 其他主题不应有背景层规则
        for t in ["light", "dark", "blue", "eye", "sci"]:
            assert 'html[data-theme="%s"] body::before' % t not in src, \
                "%s should have no bg layer" % t
        # 无花活
        for junk in ["bg-particles", "thinking-badge", "anime-deco"]:
            assert junk not in src, "%s should be removed (keep it simple)" % junk


class TestDarkSurfaceText:
    """2026-09-23：深底容器（--code-bg）里的文字必须用 --code-fg。

    事故：技能详情页「技能文件」树 .sk-tree 底色是 --code-bg（深色），
    子项 .sk-tree-f/.sk-tree-d 却用 --text/--text-light（浅色主题下是深色），
    实测对比度 1.02~1.52:1 —— 用户反馈"太黑了，看不到"。
    规则：深底容器内的文字一律跟 --code-fg 走（同 .rv-pre/.bubble pre）。
    """

    # 已知合理地"深底浅字"由子元素各自负责的容器（在此登记豁免）
    _EXEMPT = set()

    @staticmethod
    def _lum(hexcolor):
        h = hexcolor.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        parts = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
        parts = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]

    @classmethod
    def _ratio(cls, a, b):
        la, lb = cls._lum(a), cls._lum(b)
        hi, lo = max(la, lb), min(la, lb)
        return (hi + 0.05) / (lo + 0.05)

    @staticmethod
    def _theme_vars(src):
        """解析每个主题的 --code-bg/--code-fg/--text/--text-light。"""
        out = {}
        # :root 默认（light）+ 各 [data-theme="x"] 块
        blocks = [("light", re.search(r":root\s*\{(.*?)\}", src, re.S))]
        for tid in re.findall(r'\[data-theme="([a-z]+)"\]\s*\{', src):
            m = re.search(r'\[data-theme="%s"\]\s*\{(.*?)\}' % tid, src, re.S)
            if m:
                blocks.append((tid, m))
        for name, m in blocks:
            if not m:
                continue
            body = m.group(1)
            def pick(var, default=None):
                mm = re.search(r"--%s:\s*([#0-9a-zA-Z(),.\s]+?);" % var, body)
                return mm.group(1).strip() if mm else default
            cbg = pick("code-bg")
            cfg = pick("code-fg")
            panel = pick("panel")
            text = pick("text")
            if cbg and cfg:
                entry = {"code-bg": cbg, "code-fg": cfg}
                if panel and text:
                    entry["panel"] = panel
                    entry["text"] = text
                out[name] = entry
        return out

    def test_sk_tree_is_a_list_not_a_code_slab(self):
        """技能文件树是「文件列表」，不该借代码块的深色底 --code-bg。

        事故现场：容器用 --code-bg（浅色主题下近黑），子项却用 --text
        → 对比度 1.02~1.52:1，用户反馈"太黑了，看不到"。
        """
        src = _html()
        m = re.search(r"\.sk-tree\s*\{([^}]*)\}", src)
        assert m, ".sk-tree 规则缺失"
        assert "var(--code-bg" not in m.group(1), (
            ".sk-tree 不该用 --code-bg 深色底（它是文件列表，不是代码块）；"
            "用 --panel 与同面板 .skp-item 保持一致"
        )
        assert "var(--panel)" in m.group(1), ".sk-tree 应该用 --panel 浅底"

    def test_sk_tree_text_contrast_readable_in_every_theme(self):
        """按主题实测：文件树文字 vs 实际底色必须 >= 4.5:1（正文合格线）。"""
        src = _html()
        themes = self._theme_vars(src)
        assert themes, "解析不到主题变量"
        fm = re.search(r"\.sk-tree-f\s*\{([^}]*)\}", src)
        assert fm, ".sk-tree-f 缺失"
        # 子项用 --text，底色是 --panel
        assert "var(--text)" in fm.group(1), ".sk-tree-f 应该用 --text"
        for name, tv in themes.items():
            panel = tv.get("panel")
            assert panel, "主题 %s 缺 --panel" % name
            r = self._ratio(panel, tv["text"])
            assert r >= 4.5, (
                "主题 %s：文件树文字 --text 在 --panel 上只有 %.2f:1，读不清"
                % (name, r)
            )

    def test_dark_surface_rules_bring_their_own_text_color(self):
        """兜底：任何把 --code-bg 当背景的规则，必须自带 color:var(--code-fg)。

        这是 .sk-tree 事故的通用形态 —— 消费了深色变量却没配文字色，
        在浅色主题下必然变成"深字压深底"。
        """
        src = _html()
        # 逐个 CSS 规则检查（简单按 } 切；够用且不引入依赖）
        offenders = []
        for m in re.finditer(r"([^{}]+)\{([^}]*)\}", src):
            sel, body = m.group(1).strip(), m.group(2)
            if "background:var(--code-bg" not in body and "background: var(--code-bg" not in body:
                continue
            sel_last = sel.split(",")[-1].strip().split("\n")[-1].strip()
            if any(e in sel for e in self._EXEMPT):
                continue
            if "var(--code-fg" not in body:
                offenders.append(sel_last)
        assert not offenders, (
            "这些规则用了深色底 --code-bg 但没配 --code-fg 文字色，"
            "浅色主题下会看不见：%s" % offenders
        )


class TestThemeJS:
    def test_js_syntax_valid(self):
        esprima = pytest.importorskip("esprima")
        src = _html()
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", src, re.S)
        for js in scripts:
            if len(js) > 2_000_000:
                continue
            esprima.parseScript(js)

    def test_settheme_whitelist(self):
        src = _html()
        assert "if (!valid) theme = 'light'" in src

    def test_render_theme_buttons_called(self):
        src = _html()
        assert "renderThemeButtons();" in src


class TestThemeServed:
    def test_page_served(self, client):
        r = client.get("/")
        assert r.status_code == 200
        body = r.text
        assert 'data-theme="eye"' in body and 'data-theme="parchment"' in body
