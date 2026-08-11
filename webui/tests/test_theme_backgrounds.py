# -*- coding: utf-8 -*-
"""webUI 背景主题测试网：6 新主题 CSS + 装饰元素 + 资源可达 + JS 语法。"""
import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX = os.path.join(ROOT, "webui", "index.html")


def _html():
    with io.open(INDEX, encoding="utf-8") as f:
        return f.read()


NEW_THEMES = ["eye", "parchment", "anime", "sci", "sunset", "dusk"]


class TestThemeCSS:
    def test_all_new_themes_defined(self):
        src = _html()
        for t in NEW_THEMES:
            assert '[data-theme="%s"]' % t in src, "%s theme missing" % t

    def test_theme_presets_cover_all(self):
        src = _html()
        m = re.search(r"var THEME_PRESETS = \[(.*?)\];", src, re.S)
        assert m, "THEME_PRESETS not found"
        presets = re.findall(r"id:'([a-z]+)'", m.group(1))
        assert set(NEW_THEMES) <= set(presets), "presets missing: %s" % (set(NEW_THEMES) - set(presets))

    def test_background_layer_exists(self):
        src = _html()
        assert "body::before" in src
        assert "html[data-theme=\"anime\"] body::before" in src  # 渐变+Ken Burns
        assert "bg-kenburns" in src

    def test_thinking_styles(self):
        src = _html()
        assert "#thinking-badge" in src
        assert "body.thinking #thinking-badge" in src
        assert "think-pulse" in src


class TestDecoElements:
    def test_deco_elements_present(self):
        src = _html()
        for el in ['id="bg-particles"', 'id="anime-deco"', 'id="thinking-badge"',
                   'id="theme-options"', 'id="bg-anim-toggle"']:
            assert el in src, el + " missing"

    def test_penguin_asset_served(self, client):
        r = client.get("/assets/penguin.png")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/")


class TestThemeJS:
    def test_js_syntax_valid(self):
        esprima = pytest.importorskip("esprima")
        src = _html()
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", src, re.S)
        assert scripts, "no script blocks"
        for js in scripts:
            if len(js) > 2_000_000:
                continue
            esprima.parseScript(js)  # 抛异常即失败

    def test_theme_functions_present(self):
        src = _html()
        for fn in ["THEME_PRESETS", "renderThemeButtons", "setTheme", "cycleTheme",
                   "setBgAnim", "startParticles", "stopParticles", "setThinking"]:
            assert fn in src, fn + " missing"

    def test_settheme_whitelist_fallback(self):
        """未知主题值回退 light（白名单校验）。"""
        src = _html()
        assert "valid = THEME_PRESETS.some" in src or "if (!valid) theme = 'light'" in src
