# -*- coding: utf-8 -*-
"""更新检查 TLS 加固回归测试（2026-09-23）

用户报障：点"检查更新"出现
  <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
   unable to get local issuer certificate (_ssl.c:1010)>

根因：urllib 默认 SSL 上下文在 Windows 上信任锚取自系统证书存储
（ssl.enum_certificates 先 LocalMachine 后退 CurrentUser），实测本机只载入 54 张，
而随包 certifi 有 119 张 —— 系统存储缺签发链时 GitHub 证书验不过，检查直接失败。

本测试锁死三条不变量：
1. 更新检查/下载一律使用 _ssl_context()（优先 certifi），而不是裸 build_opener()；
2. 绝不为了"能连上"而关闭证书校验（check_hostname=False / CERT_NONE 是禁止项）；
3. TLS 类失败必须翻译成可操作的中文提示，而不是把 _ssl.c 原始堆栈丢给用户。
"""
import re
import os
import ssl
import pytest

import server


pytestmark = pytest.mark.update_check

SRC = open(os.path.join(os.path.dirname(server.__file__), "server.py"), encoding="utf-8").read()


class TestTlsContext:
    def test_context_prefers_certifi(self):
        """信任锚应来自 certifi（119 张），明显多于 Windows 系统存储（本机 54 张）"""
        ctx = server._ssl_context()
        n = len(ctx.get_ca_certs())
        assert n >= 100, f"信任锚过少（{n}），疑似回退到系统存储"

    def test_context_is_cached(self):
        """重复调用返回同一上下文（避免每次请求重建）"""
        assert server._ssl_context() is server._ssl_context()

    def test_verification_stays_on(self):
        """校验必须开着：绝不 verify_mode=CERT_NONE / check_hostname=False"""
        ctx = server._ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True

    def test_no_verification_disabled_in_source(self):
        """源码里不许出现关闭证书校验的写法"""
        for bad in ("CERT_NONE", "_create_unverified_context", "check_hostname = False",
                    "check_hostname=False", "verify_mode = ssl.CERT_NONE"):
            assert bad not in SRC, f"更新链路禁止关闭证书校验：出现 {bad}"

    def test_opener_carries_context(self):
        """_url_opener 必须挂带 TLS 上下文的 HTTPSHandler"""
        import urllib.request as _ur
        op = server._url_opener(None)
        https = [h for h in getattr(op, "handlers", []) if isinstance(h, _ur.HTTPSHandler)]
        assert https, "opener 缺少 HTTPSHandler（TLS 上下文没生效）"
        assert https[0]._context is server._ssl_context(), "HTTPSHandler 没挂上 certifi 上下文"

    def test_direct_branch_is_really_direct(self):
        """proxy=None 必须真直连，不能静默复用系统代理

        历史缺陷：build_opener() 自动挂的 ProxyHandler 读系统注册表；
        本机 ProxyEnable=1 指向 127.0.0.1:6478，于是所谓"失败降级直连"
        仍走同一代理、同一失败原因 —— 双路兜底形同虚设。

        实现说明：ProxyHandler({}) 不注册任何协议方法，因此不会出现在
        opener.handlers 里，它的作用是压掉那个读系统代理的默认 ProxyHandler。
        所以"真直连"的判据是：handlers 里不存在任何 ProxyHandler。
        """
        import urllib.request as _ur
        op = server._url_opener(None)
        ph = [h for h in getattr(op, "handlers", []) if isinstance(h, _ur.ProxyHandler)]
        assert not ph, f"proxy=None 时不应有任何代理处理器，实际 {[h.proxies for h in ph]}"

    def test_proxy_branch_actually_routes(self):
        """指定代理时 ProxyHandler 必须真的挂上并按协议生效"""
        import urllib.request as _ur
        op = server._url_opener(server._PROXY)
        ph = [h for h in getattr(op, "handlers", []) if isinstance(h, _ur.ProxyHandler)]
        assert ph, "指定代理却没有代理处理器"
        assert server._PROXY in (ph[0].proxies or {}).values()
        assert hasattr(ph[0], "https_open"), "https 代理未生效（更新包下载会失败）"

    def test_opener_uses_proxy_when_given(self):
        import urllib.request as _ur
        op = server._url_opener(server._PROXY)
        ph = [h for h in getattr(op, "handlers", []) if isinstance(h, _ur.ProxyHandler)]
        assert ph, "指定代理时缺少 ProxyHandler"
        assert server._PROXY in (ph[0].proxies or {}).values(), "代理没生效（更新包会下载失败）"


class TestErrorTranslation:
    def test_cert_error_becomes_actionable_chinese(self):
        """缺签发链 → 中文可操作提示（含 certifi 与手动更新指引）"""
        err = ssl.SSLCertVerificationError(
            1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
               "unable to get local issuer certificate (_ssl.c:1010)")
        hint = server._net_error_hint(err)
        assert "证书" in hint and "certifi" in hint
        assert "手动" in hint, "应给出兜底出路，而不是只报错"

    def test_timeout_hint(self):
        assert "超时" in server._net_error_hint(TimeoutError("timed out"))

    def test_dns_hint(self):
        assert "DNS" in server._net_error_hint(OSError("[Errno 11001] getaddrinfo failed"))

    def test_unknown_error_is_truncated(self):
        hint = server._net_error_hint(RuntimeError("x" * 500))
        assert len(hint) <= 200

    def test_update_check_reports_translated_error(self, monkeypatch):
        """端到端：API 与 CDN 双双 TLS 失败时，error 必须是中文可操作提示

        注意：仅 API 失败已不足以判失败 —— 会先回退 CDN（见 TestRateLimitFallback），
        所以这里要两条路都断掉，才代表"真的连不上"。
        """
        import asyncio

        def _boom(*a, **k):
            raise ssl.SSLCertVerificationError(
                1, "certificate verify failed: unable to get local issuer certificate")
        monkeypatch.setattr(server, "_http_get_json", _boom)
        monkeypatch.setattr(server, "_http_get_text", _boom)
        r = asyncio.run(server.update_check())
        assert r["status"] == "unable_to_check"
        assert "证书" in r["error"]
        assert "_ssl.c" not in r["error"], "不许把原始 OpenSSL 堆栈直接甩给用户"


class TestAssetSelection:
    def test_update_zip_preferred_over_full_package(self, monkeypatch):
        """有 MemOmics-update.zip 时优先轻量包，而不是 700MB 完整包"""
        assets = [
            {"name": "MemOmics-Windows.zip", "size": 700 * 1048576,
             "browser_download_url": "https://example.invalid/full.zip"},
            {"name": "MemOmics-update.zip", "size": 88 * 1048576,
             "browser_download_url": "https://example.invalid/upd.zip"},
        ]
        monkeypatch.setattr(server, "_http_get_json", lambda *a, **k: {
            "tag_name": "v2099-01-01", "published_at": "2099-01-01T00:00:00Z", "assets": assets})
        monkeypatch.setattr(server, "_local_version_info", lambda: {
            "version": "v2000-01-01", "rev": "abc", "date": "2000-01-01",
            "fix_bundle": "x", "has_git": False})
        import asyncio
        r = asyncio.run(server.update_check())
        assert r["status"] == "update_available"
        assert r["remote"]["asset_name"] == "MemOmics-update.zip"
        assert r["remote"]["asset_kind"] == "update"
        assert r["remote"]["asset_size_mb"] < 100, "应选轻量包（用户下载量差 8 倍）"
        assert r["update_mode"] == "zip_overlay"

    def test_no_asset_yields_manual_mode(self, monkeypatch):
        """release 没有任何资产 → manual，前端据此提示手动更新（不静默）"""
        monkeypatch.setattr(server, "_http_get_json", lambda *a, **k: {
            "tag_name": "v2099-01-01", "published_at": "2099-01-01T00:00:00Z", "assets": []})
        monkeypatch.setattr(server, "_local_version_info", lambda: {
            "version": "v2000-01-01", "rev": "abc", "date": "2000-01-01",
            "fix_bundle": "x", "has_git": False})
        import asyncio
        r = asyncio.run(server.update_check())
        assert r["update_mode"] == "manual"
        assert r["remote"]["asset_name"] == ""


class TestRateLimitFallback:
    """GitHub 匿名 API 配额（60 次/小时）用尽时的 CDN 回退（2026-09-23 实测报障）"""

    def _limit(self, monkeypatch, assets=None):
        import urllib.error

        def _json(url, *a, **k):
            if "api.github.com" in url:
                raise urllib.error.HTTPError(url, 403, "rate limit exceeded", None, None)
            raise AssertionError("非 API 主机不该走 JSON 通道")
        monkeypatch.setattr(server, "_http_get_json", _json)
        monkeypatch.setattr(server, "_http_get_text", lambda *a, **k: "v2099-01-01\n")
        monkeypatch.setattr(server, "_asset_exists", lambda tag, name, **k: True)
        monkeypatch.setattr(server, "_local_version_info", lambda: {
            "version": "v2000-01-01", "rev": "abc", "date": "2000-01-01",
            "fix_bundle": "x", "has_git": False})

    def test_cdn_fallback_still_reports_update(self, monkeypatch):
        """限流不再等于"无法检查"：仍应给出新版本与可下载的资产 URL"""
        self._limit(monkeypatch)
        import asyncio
        r = asyncio.run(server.update_check())
        assert r["status"] == "update_available", "限流应回退 CDN 而不是直接判失败"
        assert r["source"] == "cdn"
        assert r["remote"]["tag"] == "v2099-01-01"
        assert r["remote"]["asset_url"].endswith("MemOmics-update.zip")
        assert r["update_mode"] == "zip_overlay", "回退时也要能一键更新"

    def test_cdn_fallback_marks_asset_kind_update(self, monkeypatch):
        """回退推导的资产仍要正确标成轻量更新包（前端文案据此区分）"""
        self._limit(monkeypatch)
        import asyncio
        r = asyncio.run(server.update_check())
        assert r["remote"]["asset_kind"] == "update"

    def test_rate_limit_hint_is_human(self):
        import urllib.error
        err = urllib.error.HTTPError("https://api.github.com/x", 403, "rate limit exceeded", None, None)
        hint = server._net_error_hint(err)
        assert "配额" in hint or "受限" in hint
        assert "手动" in hint or "重试" in hint

    def test_no_asset_when_nothing_exists(self, monkeypatch):
        """资产都不存在 → 不给用户一个 404 按钮，落回 manual"""
        import urllib.error

        def _json(url, *a, **k):
            raise urllib.error.HTTPError(url, 403, "rate limit exceeded", None, None)
        monkeypatch.setattr(server, "_http_get_json", _json)
        monkeypatch.setattr(server, "_http_get_text", lambda *a, **k: "v2099-01-01\n")
        monkeypatch.setattr(server, "_asset_exists", lambda tag, name, **k: False)
        monkeypatch.setattr(server, "_local_version_info", lambda: {
            "version": "v2000-01-01", "rev": "abc", "date": "2000-01-01",
            "fix_bundle": "x", "has_git": False})
        import asyncio
        r = asyncio.run(server.update_check())
        assert r["remote"]["asset_name"] == ""
        assert r["update_mode"] == "manual"

    def test_version_parse_rejects_garbage(self, monkeypatch):
        """CDN VERSION 内容异常时不得编造版本号"""
        import urllib.error

        def _json(url, *a, **k):
            raise urllib.error.HTTPError(url, 403, "rate limit exceeded", None, None)
        monkeypatch.setattr(server, "_http_get_json", _json)
        monkeypatch.setattr(server, "_http_get_text", lambda *a, **k: "<html>404 not found</html>")
        import asyncio
        r = asyncio.run(server.update_check())
        assert r["status"] == "unable_to_check"
        assert "CDN" in r["error"] or "受限" in r["error"]


class TestFrontendUpdatePanel:
    HTML = open(os.path.join(os.path.dirname(server.__file__), "index.html"), encoding="utf-8").read()

    def test_failure_branch_offers_retry(self):
        """失败分支必须有重试按钮（用户不用刷新整页）"""
        assert "checkForUpdate(true)" in self.HTML

    def test_failure_branch_links_release_page(self):
        """失败分支给出可点击的 Release 页作为兜底出路"""
        assert "releases/latest" in self.HTML

    def test_check_calls_real_endpoint(self):
        assert "/api/update/check" in self.HTML
