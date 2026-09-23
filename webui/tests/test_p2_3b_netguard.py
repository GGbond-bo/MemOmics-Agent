# -*- coding: utf-8 -*-
"""P2-3b 出网闸门测试（2026-09-23）

分六层：
  A. 门与三种模式（观察零行为变更 / 强制零 I-O / 关掉即老路径）
  B. 钉 IP 直连（Host 头与 SNI 用真域名、多地址回退、失败报错）
  C. 反 rebinding 的 TOCTOU 缝（判定后 DNS 翻转，连接仍只去批准过的地址）
  D. 重定向逐跳复核（换主机要再授权 / 跳 file:// 拒绝 / 跳数上限 / 303 降级 GET）
  E. 代理与 net.local（代理不能钉 IP、环回不走代理、本机服务默认放行、元数据地址进不来）
  F. 与真实 server 的接线（/api/models/local 真跑、更新检查真过门、强制模式自授权）

纪律：不外网。真实 socket 只打本机 127.0.0.1 的临时 HTTP 服务；公网主机名用注入 DNS。
"""
import json
import os
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import cleanup_session
import server
from webui import netguard as NG
from webui import sandbox as SB

PUB = "93.184.216.34"
PUB2 = "1.1.1.1"
DEAD_PUB = "8.8.8.8"


class FakeClock:
    def __init__(self, t=1_700_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt
        return self.t


class FakeResolver:
    def __init__(self, table=None, default=(PUB,)):
        self.table = dict(table or {})
        self.default = tuple(default)

    def __call__(self, host):
        val = self.table.get(host, self.default)
        if isinstance(val, BaseException):
            raise val
        return list(val)


@pytest.fixture()
def prov():
    p = SB.SandboxProvider(name="ng", clock=FakeClock(), resolver=FakeResolver(), max_audit=500)
    old = SB.set_provider(p)
    try:
        yield p
    finally:
        SB.set_provider(old)
        SB.reset()


_PROXY_ENV = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
              "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy")


def _clear_proxy_env(monkeypatch):
    """开发机常带着 HTTPS_PROXY——有代理时钉 IP 是钉不住的（DNS 在代理侧），
    要测钉 IP 就必须先把代理清干净，否则测的是代理路径。"""
    for k in _PROXY_ENV:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture()
def observe(monkeypatch):
    monkeypatch.delenv("MEMOMICS_SANDBOX_ENFORCE", raising=False)
    monkeypatch.delenv("MEMOMICS_SANDBOX", raising=False)
    _clear_proxy_env(monkeypatch)


@pytest.fixture()
def enforce(monkeypatch):
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "1")
    monkeypatch.delenv("MEMOMICS_SANDBOX", raising=False)
    _clear_proxy_env(monkeypatch)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body=b"", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if self.path == "/hello":
            self._send(200, b'{"ok":true,"from":"local"}', {"Content-Type": "application/json"})
        elif self.path == "/host":
            self._send(200, (self.headers.get("Host") or "").encode())
        elif self.path == "/redir":
            self._send(302, b"", {"Location": "/hello"})
        elif self.path == "/loop":
            self._send(302, b"", {"Location": "/loop"})
        elif self.path == "/tofile":
            self._send(302, b"", {"Location": "file:///etc/passwd"})
        elif self.path == "/toother":
            self._send(302, b"", {"Location": "http://other.example/hello"})
        elif self.path == "/see":
            self._send(303, b"", {"Location": "/method"})
        elif self.path == "/method":
            self._send(200, self.command.encode())
        elif self.path == "/big":
            self._send(200, b"x" * 5000)
        else:
            self._send(404, b"nope")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if self.path == "/see":
            self._send(303, b"", {"Location": "/method"})
        else:
            self._send(200, body or b"empty")

    def log_message(self, *a):          # 测试噪音静音
        pass


@pytest.fixture(scope="module")
def local_http():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        yield "http://127.0.0.1:%d" % srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture()
def connect_recorder(local_http):
    """记录 _connect_direct 的实参，然后真的连到本机服务——既验证"连的是哪个 IP"，也真跑通链路。"""
    real = NG._connect_direct
    calls = []
    port = int(urllib.parse.urlsplit(local_http).port)

    def fake(ip, p, host, tls, timeout):
        calls.append({"ip": ip, "port": p, "host": host, "tls": tls, "timeout": timeout})
        if ip == "10.9.9.9":                     # 模拟"这个地址连不上"
            raise OSError("connection refused (fake)")
        return real("127.0.0.1", port, host, False, timeout)

    monkeypatch_ok = True
    NG._connect_direct, old = fake, NG._connect_direct
    try:
        yield calls
    finally:
        NG._connect_direct = old
        assert monkeypatch_ok


@pytest.fixture()
def plain_spy(monkeypatch):
    """把老路径换掉：观察模式必须走它，强制模式必须不走它。"""
    calls = []

    def fake(url, timeout, headers, data, method, max_bytes, proxy):
        calls.append({"url": url, "method": method, "proxy": proxy})
        return NG.NetResponse(200, {"Content-Length": "2"}, url, stream=_MemStream(b"ok"),
                              via_proxy=bool(proxy))

    monkeypatch.setattr(NG, "_plain_request", fake)
    return calls


class _MemStream:
    def __init__(self, data):
        self._d = data

    def read(self, n=-1):
        if n is None or n < 0:
            out, self._d = self._d, b""
            return out
        out, self._d = self._d[:n], self._d[n:]
        return out

    def close(self):
        pass


# ====================================================== A. 门与三种模式
def test_a1_observe_mode_keeps_old_path_and_only_audits(prov, observe, plain_spy, connect_recorder):
    """观察模式：判定照算，请求仍走老路径——钉 IP 通道一次都不能碰。"""
    r = NG.urlopen("https://no-grant.example/x")
    assert r.read() == b"ok"
    assert len(plain_spy) == 1 and connect_recorder == []
    body = prov.audit(10, codes=True)
    assert body["codes"] == {"no_grant": 1}
    assert body["items"][0]["source"] == "netguard"
    assert body["items"][0]["mode"] == "observe"


def test_a2_enforce_denies_without_any_io(prov, enforce, plain_spy, connect_recorder):
    with pytest.raises(SB.SandboxDenied) as ei:
        NG.urlopen("https://no-grant.example/x")
    assert ei.value.code == "no_grant"
    assert plain_spy == [] and connect_recorder == [], "被拦时一个字节都不该发出去"
    assert prov.stats()["counts"]["blocked"] == 1


def test_a3_disabled_module_is_old_path(prov, monkeypatch, plain_spy):
    monkeypatch.setenv("MEMOMICS_SANDBOX", "0")
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "1")
    assert NG.urlopen("https://no-grant.example/x").read() == b"ok"
    assert len(plain_spy) == 1


def test_a4_bad_url_rejected_before_anything(prov, enforce, plain_spy):
    for bad in ("", "   ", None, 123):
        with pytest.raises(NG.NetError):
            NG.urlopen(bad)
    assert plain_spy == []


def test_a5_unknown_scheme_denied(prov, enforce, plain_spy):
    with pytest.raises(SB.SandboxDenied) as ei:
        NG.urlopen("file:///etc/passwd")
    assert ei.value.code == "url_bad_scheme"
    assert plain_spy == []


# ====================================================== B. 钉 IP 直连
def test_b1_pinned_connect_uses_approved_ip_and_real_host(prov, enforce, connect_recorder):
    prov.grant("net.fetch", "example.com", ttl_s=100)
    r = NG.urlopen("http://example.com/hello")
    assert r.status == 200 and json.loads(r.read())["ok"] is True
    assert connect_recorder[0]["ip"] == PUB          # 连的是批准过的地址
    assert connect_recorder[0]["host"] == "example.com"   # SNI/Host 用真域名
    assert r.pinned_ips == [PUB]


def test_b2_host_header_is_real_domain(prov, enforce, connect_recorder):
    prov.grant("net.fetch", "example.com", ttl_s=100)
    r = NG.urlopen("http://example.com/host")
    assert r.read().decode() == "example.com"        # 本机服务把它收到的 Host 头回显出来


def test_b3_first_ip_dead_falls_back_to_second(prov, enforce):
    prov._resolver.table["multi.example"] = ["10.9.9.9", PUB2]
    prov.grant("net.fetch", "multi.example", ttl_s=100)
    # 注意：连"回退"都必须用公网地址——10.9.9.9 是私网，会被策略在判定阶段就拦掉，
    # 那样测到的是"策略拒绝"，不是"连接器回退"。
    prov._resolver.table["multi.example"] = [DEAD_PUB, PUB2]

    class _Sock:
        def __init__(self):
            self.sent = []

        def sendall(self, data):
            self.sent.append(data)

        def makefile(self, *a, **k):
            raise OSError("stop here")                          # 到此为止，只验回退顺序

        def close(self):
            pass

    calls = []
    # 顺序由策略给（解析结果会被排序去重），所以"第一个"要问策略要，不能靠我猜
    approved = prov.check("net.fetch", "http://multi.example/x").pinned_ips
    assert len(approved) == 2
    first, second = approved[0], approved[1]

    def conn(ip, p, host, tls, timeout):
        calls.append(ip)
        if ip == first:
            raise OSError("refused")
        return _Sock()

    with pytest.raises(Exception):
        NG.fetch("http://multi.example/x", action="net.fetch", connector=conn)
    assert calls == [first, second], "第一个地址失败后必须试下一个"


def test_b4_all_addresses_dead_reports_them(prov, enforce):
    prov.grant("net.fetch", "dead.example", ttl_s=100)

    def conn(ip, p, host, tls, timeout):
        raise OSError("refused %s" % ip)

    with pytest.raises(NG.NetError) as ei:
        NG.fetch("http://dead.example/x", connector=conn)
    assert PUB in str(ei.value) and "refused" in str(ei.value)


def test_b5_sni_and_certificate_check_use_real_hostname(monkeypatch):
    recorded = {}

    class _Ctx:
        def wrap_socket(self, sock, server_hostname=None):
            recorded["sni"] = server_hostname
            return "tls-sock"

    monkeypatch.setattr(NG.socket, "create_connection", lambda addr, timeout=None: "raw-sock")
    monkeypatch.setattr(NG.ssl, "create_default_context", lambda: _Ctx())
    out = NG._connect_direct(PUB, 443, "example.com", True, 5.0)
    assert out == "tls-sock" and recorded["sni"] == "example.com"
    out2 = NG._connect_direct(PUB, 80, "example.com", False, 5.0)
    assert out2 == "raw-sock"


def test_b6_host_header_mismatch_blocked(prov, enforce):
    prov.grant("net.fetch", "example.com", ttl_s=100)
    with pytest.raises(SB.SandboxDenied) as ei:
        NG.urlopen("http://example.com/x", headers={"Host": "internal.example"})
    assert ei.value.code == "host_header_mismatch"


def test_b7_response_wrapper_basics(prov, enforce, connect_recorder):
    prov.grant("net.fetch", "example.com", ttl_s=100)
    with NG.urlopen("http://example.com/hello") as r:
        assert r.status == 200 and r.getcode() == 200
        assert r.geturl().startswith("http://example.com/")
        assert r.read(1) == b"{"
        rest = r.read()
        assert rest.endswith(b"}")
        assert r.truncated is False


def test_b8_max_bytes_truncates(prov, enforce, connect_recorder):
    prov.grant("net.fetch", "example.com", ttl_s=100)
    r = NG.urlopen("http://example.com/big", max_bytes=100)
    data = r.read()
    assert len(data) == 100 and r.truncated is True
    r.close()


# ====================================================== C. 反 rebinding（TOCTOU）
def test_c1_pinned_ip_wins_over_flipped_dns(prov, enforce, connect_recorder):
    """经典 TOCTOU 缝：判定时 DNS 说"公网"，连接前那一瞬翻成内网。

    实现只解析一次、随后只连批准过的那组地址，所以翻转影响不到这一次握手。
    （"翻转发生在判定之前"是另一回事——那种由门本身拦住，见 c2。）
    """
    prov.grant("net.fetch", "flip.example", ttl_s=1000)
    calls = {"n": 0}

    def flip(host):                       # 第一次（判定）返回公网，之后翻成环回
        calls["n"] += 1
        return [PUB] if calls["n"] == 1 else ["127.0.0.1"]

    prov._resolver = flip
    r = NG.urlopen("http://flip.example/hello")
    assert r.status == 200
    assert connect_recorder[0]["ip"] == PUB, "连接跟着 DNS 翻转了 = 钉 IP 没生效"
    assert calls["n"] == 1, "一次请求只该解析一次（再解析就是把 TOCTOU 缝重新打开）"
    assert prov.audit(5, codes=True)["codes"].get("ok_grant") == 1


def test_c2_flipped_dns_blocks_the_request_outright(prov, enforce, plain_spy):
    prov.grant("net.fetch", "flip2.example", ttl_s=1000)
    prov._resolver.table["flip2.example"] = ["169.254.169.254"]
    with pytest.raises(SB.SandboxDenied) as ei:
        NG.urlopen("http://flip2.example/x")
    assert ei.value.code == "url_link_local"
    assert plain_spy == []


def test_c3_pinned_set_mismatch_is_rebinding(prov, enforce):
    d1 = prov.check("net.fetch", "https://pin.example/")
    prov.grant("net.fetch", "pin.example", ttl_s=100)
    prov._resolver.table["pin.example"] = ["8.8.8.8"]
    d2 = prov.gate("net.fetch", "https://pin.example/", pinned_ips=d1.pinned_ips)
    assert d2.allow is False and d2.code == "url_rebinding"


# ====================================================== D. 重定向逐跳复核
def test_d1_redirect_same_host_reauth_each_hop(prov, enforce, connect_recorder):
    prov.grant("net.fetch", "example.com", ttl_s=100)
    r = NG.urlopen("http://example.com/redir")
    assert r.status == 200 and json.loads(r.read())["ok"] is True
    assert len(connect_recorder) == 2, "重定向的每一跳都要重新过门并重新连接"


def test_d2_redirect_to_other_host_needs_its_own_grant(prov, enforce, connect_recorder):
    prov.grant("net.fetch", "example.com", ttl_s=100)
    with pytest.raises(SB.SandboxDenied) as ei:
        NG.urlopen("http://example.com/toother")   # 目标主机没授权 → 第二跳被拦
    assert ei.value.code in ("no_grant", "url_bad_scheme")


def test_d3_redirect_to_file_scheme_always_refused(prov, enforce, connect_recorder):
    """强制模式：跳到 file:// 的新目标连门都过不了（scheme 非法）。"""
    prov.grant("net.fetch", "example.com", ttl_s=100)
    with pytest.raises(SB.SandboxDenied) as ei:
        NG.urlopen("http://example.com/tofile")    # 本机服务回 302 → file:///etc/passwd
    assert ei.value.code == "url_bad_scheme"


def test_d3b_file_redirect_refused_even_in_observe(prov, observe, monkeypatch):
    """观察模式：门只记账不拦人，但"跳到 file://"由闸门自己无条件拒绝——不该有任何模式放行它。"""
    def fake(url, timeout, headers, data, method, max_bytes, proxy):
        return NG.NetResponse(302, {"Location": "file:///etc/passwd"}, url,
                              stream=_MemStream(b""))

    monkeypatch.setattr(NG, "_plain_request", fake)
    with pytest.raises(NG.NetError) as ei:
        NG.urlopen("http://example.com/tofile")
    assert "scheme" in str(ei.value)
    assert prov.audit(5, codes=True)["codes"].get("url_bad_scheme") == 1


def test_d4_redirect_loop_is_bounded(prov, enforce, connect_recorder):
    prov.grant("net.fetch", "example.com", ttl_s=100)
    with pytest.raises(NG.NetError) as ei:
        NG.urlopen("http://example.com/loop", max_redirects=3)
    assert "重定向超过" in str(ei.value)
    assert len(connect_recorder) == 4              # 首跳 + 3 跳上限


def test_d5_303_downgrades_post_to_get(prov, enforce, connect_recorder):
    prov.grant("net.fetch", "example.com", ttl_s=100)
    r = NG.urlopen("http://example.com/see", data=b"payload", method="POST",
                   headers={"Content-Type": "text/plain"})
    # 本机服务把收到的方法回显出来：303 之后必须是 GET（带 body 重放是错的）
    assert r.status == 200 and r.read() == b"GET"


# ====================================================== E. 代理与 net.local
def test_e1_proxy_disables_pinning(prov, enforce, plain_spy, connect_recorder):
    prov.grant("net.fetch", "example.com", ttl_s=100)
    r = NG.urlopen("http://example.com/x", proxy="http://127.0.0.1:6478")
    assert connect_recorder == [], "代理场景不该走钉 IP 直连"
    assert plain_spy[0]["proxy"] == "http://127.0.0.1:6478"
    assert r.via_proxy is True and NG.counters()["proxy"] >= 1


def test_e2_loopback_never_goes_through_proxy(prov, enforce, plain_spy, local_http):
    r = NG.urlopen(local_http + "/hello", action="net.local", proxy="http://127.0.0.1:6478")
    assert plain_spy == [], "环回目标必须直连（否则代理把本机服务也代理走了）"
    assert json.loads(r.read())["ok"] is True


def test_e3_env_proxy_is_picked_up(prov, enforce, plain_spy, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:6478")
    prov.grant("net.fetch", "example.com", ttl_s=100)
    NG.urlopen("https://example.com/x")
    assert plain_spy and plain_spy[0]["proxy"] == "http://127.0.0.1:6478"


def test_e4_net_local_allows_loopback_by_default(prov, enforce, local_http):
    assert not prov.grants(), "net.local 默认放行不该依赖授权"
    r = NG.urlopen(local_http + "/hello", action="net.local")
    assert r.status == 200 and json.loads(r.read())["ok"] is True
    assert prov.audit(3, codes=True)["codes"]["ok_local"] == 1


def test_e5_net_local_refuses_non_loopback(prov, enforce, plain_spy):
    for url in ("http://169.254.169.254/latest/meta-data/", "http://10.0.0.7/x",
                "http://example.com/x"):
        with pytest.raises(SB.SandboxDenied) as ei:
            NG.urlopen(url, action="net.local")
        assert ei.value.code in ("local_not_loopback", "url_dns_fail")
    assert plain_spy == []


def test_e6_net_fetch_still_refuses_loopback(prov, enforce, local_http):
    with pytest.raises(SB.SandboxDenied) as ei:
        NG.urlopen(local_http + "/hello", action="net.fetch")
    assert ei.value.code == "url_loopback"


# ====================================================== F. 与真实 server 的接线
def test_f1_netguard_wired_into_server():
    assert server._net_guard is not None, "server.py 没挂上 netguard"
    assert server._net_guard.VERSION.startswith("p2-3b")


def test_f2_local_models_endpoint_runs_through_sandbox(client, prov, observe, monkeypatch):
    """/api/models/local 是老功能：默认设置下必须照旧工作，且每次探测进审计。"""
    r = client.get("/api/models/local")
    assert r.status_code == 200 and "models" in r.json()
    codes = prov.audit(20, codes=True)["codes"]
    assert codes.get("ok_local", 0) >= 1 or codes.get("local_not_loopback", 0) >= 1


def test_f3_local_models_endpoint_enforce_mode_still_ok(client, prov, enforce):
    """强制模式下本机探测不依赖授权，仍要能用（否则一开强制本地模型检测就死）。"""
    r = client.get("/api/models/local")
    assert r.status_code == 200
    assert prov.stats()["counts"]["blocked"] == 0


def test_f4_http_get_json_goes_through_gate(monkeypatch, prov, observe):
    seen = {}

    def fake(url, **kw):
        seen["url"] = url
        seen["action"] = kw.get("action")
        seen["proxy"] = kw.get("proxy")
        return NG.NetResponse(200, {}, url, stream=_MemStream(b'{"tag_name":"v0"}'))

    monkeypatch.setattr(server, "_net_guard", type("G", (), {"urlopen": staticmethod(fake),
                                                            "VERSION": NG.VERSION})())
    out = server._http_get_json("https://api.github.com/repos/x/y/releases/latest",
                                timeout=5, retries=1)
    assert out == {"tag_name": "v0"}
    assert seen["url"].startswith("https://api.github.com/")
    assert seen["action"] == "net.fetch"


def test_f5_app_grants_only_in_enforce_mode(prov, observe, monkeypatch):
    server._sandbox_ensure_app_grants()
    assert prov.grants() == [], "观察模式下不该自动打任何授权"
    monkeypatch.setenv("MEMOMICS_SANDBOX_ENFORCE", "1")
    server._sandbox_ensure_app_grants()
    gs = prov.grants()
    assert gs and gs[0]["resource"] == server._UPDATE_HOST
    assert "自更新" in gs[0]["reason"]
    server._sandbox_ensure_app_grants()          # 幂等：不能越打越多
    assert len(prov.grants()) == 1


def test_f6_benchmarker_uses_netguard():
    from webui import benchmarker as bm
    assert getattr(bm, "netguard", None) is not None
