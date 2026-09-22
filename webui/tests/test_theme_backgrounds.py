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
