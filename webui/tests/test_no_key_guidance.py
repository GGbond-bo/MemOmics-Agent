# -*- coding: utf-8 -*-
"""回归测试：未配置 API Key 时发消息的引导行为（2026-10-24 用户反馈）

现象：全量包安装后，在欢迎向导点「稍后配置」→ 直接发消息 →
      「❌ Agent 创建失败: Provider 'openai' is set in config.yaml but no API key was found...」
契约：
  1. 后端存在 _current_model_config_error()，能针对 空 key / 占位 key / 缺 base_url / 缺 model
     分别给出中文可读提示；配置齐全时返回空串（可正常创建）
  2. 造 Agent 之前先调用它；未配置时发 need_setup 事件，不再抛 hermes-agent 的原始报错
  3. 兜底分支把 "no API key" 类原始错误前置一句人话
  4. 前端收到 need_setup 会重开配置向导
"""
import io
import os
import re
import unittest

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server.py"))
INDEX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "index.html"))


def _load():
    src = io.open(SERVER, encoding="utf-8").read()
    ns = {}
    i = src.find("_PLACEHOLDER_KEY_TOKENS")
    exec(src[i:src.find("\n\n", i)], ns)  # noqa: S102
    i = src.find("def _is_valid_api_key")
    exec(src[i:src.find("\ndef ", i + 10)], ns)  # noqa: S102
    i = src.find("def _current_model_config_error")
    exec(src[i:src.find("\ndef ", i + 10)], ns)  # noqa: S102
    return src, ns


class TestNoKeyGuidance(unittest.TestCase):
    def setUp(self):
        self.src, self.ns = _load()
        self.f = self.ns["_current_model_config_error"]

    def test_empty_key_gets_readable_hint(self):
        msg = self.f({"api_key": "", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"})
        self.assertIn("API Key", msg)
        self.assertIn("设置", msg)
        self.assertNotIn("RuntimeError", msg)

    def test_placeholder_key_gets_readable_hint(self):
        msg = self.f({"api_key": "YOUR_API_KEY_HERE", "base_url": "https://api.deepseek.com/v1",
                      "model": "deepseek-chat"})
        self.assertIn("API Key", msg)

    def test_missing_base_url_and_model(self):
        k = "sk-1234567890abcdef1234567890abcdef"
        self.assertIn("Base URL", self.f({"api_key": k, "base_url": "", "model": "x"}))
        self.assertIn("模型", self.f({"api_key": k, "base_url": "https://api.deepseek.com/v1", "model": ""}))

    def test_ready_config_has_no_hint(self):
        k = "sk-1234567890abcdef1234567890abcdef"
        self.assertEqual(self.f({"api_key": k, "base_url": "https://api.deepseek.com/v1",
                                 "model": "deepseek-chat"}), "")

    def test_guard_is_before_agent_creation(self):
        i = self.src.find('_cfg_err = _current_model_config_error(session.get("model_config"))')
        j = self.src.find('agent = _create_agent(session["model_config"]')
        self.assertGreater(i, 0, "缺少造 Agent 前的配置守卫")
        self.assertLess(i, j, "守卫必须在 _create_agent 之前")

    def test_need_setup_emitted_and_raw_error_wrapped(self):
        self.assertIn('"need_setup": True', self.src)
        self.assertIn("还没有配置 API Key（或 Key 无效）", self.src)

    def test_frontend_reopens_setup_modal(self):
        """2026-10-24 改版：不再是「重开向导」，而是给一个「去设置」小按钮。
        欢迎界面为一次性（welcome_shown），未配置只提示 + 一处入口。"""
        h = io.open(INDEX, encoding="utf-8").read()
        self.assertIn("msg.need_setup", h)
        self.assertIn("function showNeedSetupAction", h)
        body = h[h.find("function showNeedSetupAction()"):h.find("function showNeedSetupAction()") + 900]
        self.assertIn("去设置", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)