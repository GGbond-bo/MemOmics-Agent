# -*- coding: utf-8 -*-
"""回归：欢迎界面 = 极简 + 只出现一次（用户 2026-10-24 最终口径）

设计契约：
  1. 欢迎界面极简：只有一句欢迎 + 「开始使用」按钮，没有任何 API/配置引导
  2. 只出现一次：服务端记 welcome_shown（ui_prefs.json），弹出即记账，之后永不再弹
  3. needs_config 判据收窄：只有「一条可用 Key 都没有」才算未配置
  4. 会话级切换模型时，把配置同步到全局 _current_model（修「切模型又被要求配置」）
  5. 未配置就发消息 → 只剩一个「去设置」小按钮（无任何引导流程）
"""
import io
import os
import unittest

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server.py"))
INDEX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "index.html"))


class TestMinimalWelcome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = io.open(SERVER, encoding="utf-8").read()
        cls.h = io.open(INDEX, encoding="utf-8").read()

    # ── 1. 欢迎界面极简、无引导 ──────────────────────────────────────────
    def test_welcome_has_no_api_guidance(self):
        i = self.h.find("function showWelcome()")
        self.assertGreater(i, 0, "缺少 showWelcome()")
        body = self.h[i:i + 1600]
        for forbidden in ("setup-apikey", "setup-provider-select", "setup-model",
                          "submitSetup", "goConfigureApi", "配置 API", "提供商", "API Key"):
            self.assertNotIn(forbidden, body, f"欢迎界面不该出现 {forbidden}")

    def test_welcome_has_close_button(self):
        i = self.h.find("function showWelcome()")
        body = self.h[i:i + 1600]
        self.assertIn("closeWelcome", body)
        self.assertIn("开始使用", body)

    def test_old_wizard_code_removed(self):
        for gone in ("function submitSetup", "function loadSetupProviders",
                     "function onSetupProviderSelect", "function goConfigureApi",
                     "function showSetupModal"):
            self.assertNotIn(gone, self.h, f"{gone} 应已删除")

    # ── 2. 只出现一次（服务端记账）───────────────────────────────────────
    def test_welcome_marked_on_display(self):
        self.assertIn("function markWelcomeShown", self.h)
        i = self.h.find("async function checkFirstRun()")
        body = self.h[i:i + 1100]
        self.assertIn("d.welcome_shown", body)
        self.assertIn("markWelcomeShown()", body)

    def test_server_persists_welcome_flag(self):
        for k in ("_welcome_shown_get", "_welcome_shown_set", '"welcome_shown": _welcome_shown',
                  "ui_prefs.json", '@app.post("/api/setup/dismiss")'):
            self.assertIn(k, self.s, f"后端缺少 {k}")

    def test_dismiss_endpoint_sets_welcome_shown(self):
        i = self.s.find("async def setup_dismiss")
        body = self.s[i:i + 800]
        self.assertIn("_welcome_shown_set(flag)", body)
        self.assertIn('"welcome_shown": flag', body)

    def test_welcome_not_tied_to_needs_config(self):
        """欢迎界面不再依据 needs_config 决定（否则会反复打扰）"""
        i = self.h.find("async function checkFirstRun()")
        body = self.h[i:i + 1100]
        self.assertNotIn("needs_config", body)

    def test_welcome_guarded_against_old_backend(self):
        """事故回归（2026-10-24）：常驻进程未重启 = 新前端 + 旧后端，
        旧后端不返回 welcome_shown → 前端若判 undefined 会每次刷新都弹。
        契约：字段缺失 / 请求失败 / 本地已看过 → 一律不弹。"""
        i = self.h.find("async function checkFirstRun()")
        body = self.h[i:i + 1400]
        self.assertIn("typeof d.welcome_shown !== 'boolean'", body, "缺少字段类型校验")
        self.assertIn("if (!r.ok) return;", body, "缺少请求失败保护")
        self.assertIn("_localSeen", body, "缺少本地兜底标记")

    # ── 3. needs_config 判据收窄 ────────────────────────────────────────
    def test_needs_config_requires_no_saved_key(self):
        self.assertIn("_any_saved_key", self.s)
        self.assertIn("_model_ready", self.s)

    # ── 4. 会话切换模型同步全局 ──────────────────────────────────────────
    def test_session_switch_syncs_global_model(self):
        i = self.s.find("会话级切换只改会话配置")
        self.assertGreater(i, 0, "缺少同步全局配置的代码块")
        seg = self.s[i:i + 700]
        self.assertIn("_current_model[_k] = new_cfg[_k]", seg)
        self.assertIn("_save_model_config()", seg)

    # ── 5. 未配置时只有一个「去设置」按钮 ────────────────────────────────
    def test_need_setup_only_settings_button(self):
        self.assertIn("showNeedSetupAction", self.h)
        i = self.h.find("function showNeedSetupAction()")
        self.assertGreater(i, 0, "缺少 showNeedSetupAction()")
        body = self.h[i:i + 900]
        self.assertIn("switchView", body)
        self.assertIn("settings", body)
        self.assertIn("去设置", body)
        self.assertNotIn("goConfigureApi", self.h)
        # 旧「重开向导」逻辑必须消失（注意：localStorage.removeItem 在别处另有合法用途，只查本流程）
        self.assertNotIn("memomics_setup_dismissed", self.h)
        i2 = self.h.find("async function checkFirstRun()")
        self.assertNotIn("removeItem", self.h[i2:i2 + 1100])


if __name__ == "__main__":
    unittest.main(verbosity=2)