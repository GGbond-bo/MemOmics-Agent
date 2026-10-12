# -*- coding: utf-8 -*-
"""「刷新一次就弹一次欢迎／请填 API Key」的回归（2026-10-12）。

用户反馈：新版本里刷新页面就被「🧬 欢迎使用 MemOmics」弹窗拦住要求重填 Key。

真因：`/api/setup/status` 只看 `_current_model`（来源：model_config.json / config.yaml）。
两处缺失、或里面还是打包模板的占位符（YOUR_API_KEY_HERE）时，即便用户在设置页
**已经存过 Key**（落 provider_keys.json），每次刷新都会判 `needs_config=true` → 弹窗。

本文件锁死三条：
  ① 占位符 key + provider_keys 有真 key → 自愈为「已配置」，不再弹（并把 model 补上）；
  ② provider_keys 里没有任何有效 key → 仍然如实报 needs_config（该弹还得弹）；
  ③ 正常已配置 → 原样放行，不做多余动作。
"""
import server


def _stub_save(monkeypatch):
    """自愈会回写配置文件 —— 测试里绝不允许碰真实 memomics_home。"""
    monkeypatch.setattr(server, "_save_model_config", lambda *a, **k: True, raising=False)


def test_placeholder_key_but_saved_provider_key_heals(client, monkeypatch):
    _stub_save(monkeypatch)
    monkeypatch.setattr(server, "_provider_keys", {
        "dcs-cloud": {
            "api_key": "sk-" + "abc123xyz" * 4,
            "base_url": "https://dcsapi.dcs.cloud/api/aigress/unified/v1",
            "models": [{"id": "deepseek-flash", "name": "DeepSeek Flash"}],
        },
    }, raising=False)
    monkeypatch.setattr(server, "_current_model", {
        "provider": "openai",
        "base_url": "https://dcsapi.dcs.cloud/api/aigress/unified/v1",
        "api_key": "YOUR_API_KEY_HERE",           # 打包模板占位符
        "model": "",                              # 模型也没写上
    }, raising=False)

    d = client.get("/api/setup/status").json()
    assert d["needs_config"] is False, d
    assert d["healed"] is True, d
    assert d["current"]["has_key"] is True, d
    assert d["current"]["model"] == "deepseek-flash", d


def test_no_key_anywhere_still_reports_needs_config(client, monkeypatch):
    _stub_save(monkeypatch)
    monkeypatch.setattr(server, "_provider_keys", {}, raising=False)
    monkeypatch.setattr(server, "_current_model", {
        "provider": "openai", "base_url": "", "api_key": "", "model": "",
    }, raising=False)
    d = client.get("/api/setup/status").json()
    assert d["needs_config"] is True, d
    assert d["healed"] is False, d


def test_healthy_config_is_left_alone(client, monkeypatch):
    _stub_save(monkeypatch)
    monkeypatch.setattr(server, "_provider_keys", {}, raising=False)
    monkeypatch.setattr(server, "_current_model", {
        "provider": "openai",
        "base_url": "https://dcsapi.dcs.cloud/api/aigress/unified/v1",
        "api_key": "sk-" + "realKey9988" * 3,
        "model": "deepseek-flash",
    }, raising=False)
    d = client.get("/api/setup/status").json()
    assert d["needs_config"] is False and d["healed"] is False, d
    assert d["current"]["model"] == "deepseek-flash", d