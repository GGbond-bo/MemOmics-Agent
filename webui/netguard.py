# -*- coding: utf-8 -*-
"""P2-3b 出网闸门：WebUI 自己发起的外部请求统一从这里走（2026-09-23）

为什么非要有这一层——不是"再包一层装饰"，而是判定和连接之间那个洞：
    判定时 DNS 说 example.com 是 93.184.216.34（公网，批准），
    连接时同一台机器上的 DNS 被翻转成 127.0.0.1 或 169.254.169.254，
    检查就全白做了。这就是经典的 TOCTOU / DNS rebinding。
本模块的做法是**把批准的地址钉住**：判定返回的那组 IP 就是这次连接唯一允许去的地方，
Host 头与 TLS SNI 仍用真实域名（证书校验照旧按域名走），解析结果再变也影响不了这一次握手。
重定向不是"首跳过闸就一路放行"，而是**每一跳都重新过门**——跳到 file:// / ftp:// 直接拒。

三种模式下的行为（和沙箱保持一致）：
    MEMOMICS_SANDBOX=0        → 完全按老路径走（等于本模块不存在）
    observe（默认）           → 判定照算、账照记，但请求仍走老路径，行为零变更
    enforce=1                 → 不允许就抛 SandboxDenied（一个字节都不发出去）；
                                允许则走"钉住 IP"的直连
代理场景（有 HTTPS_PROXY 时）无法钉 IP——DNS 在代理侧解析，钉了也没意义。
这时诚实降级：仍然过门、仍然记账，但请求交给代理直连完成；环回目标永不走代理。
"""

from __future__ import annotations

import http.client
import os
import socket
import ssl
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:                                    # 包内导入（webui 作为包）
    from webui import sandbox as _sandbox
except ImportError:                     # 直接以脚本/单文件方式运行
    import sandbox as _sandbox          # type: ignore

VERSION = "p2-3b.2"

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_REDIRECTS = 5
_REDIRECT_CODES = (301, 302, 303, 307, 308)
_SCHEMES = ("http", "https")


class NetError(RuntimeError):
    """出网失败（连不上 / 重定向异常 / 响应超限）。被沙箱拒绝时抛的是 SandboxDenied。"""


#: 出网计数（进程内累计）：pinned=钉住 IP 直连，proxy=走代理（无法钉 IP），plain=观察/关闭模式的老路径
_COUNTERS = {"fetch": 0, "pinned": 0, "plain": 0, "proxy": 0, "redirect": 0, "truncated": 0}


def counters() -> Dict[str, int]:
    """看清"这一段时间出网到底是怎么发出去的"——尤其是有多少走了代理（钉不住 IP）。"""
    return dict(_COUNTERS)


def _effective_proxy(url: str, proxy: Optional[str]) -> Optional[str]:
    """谁来做 DNS：显式 proxy > 环境变量 > 直连。环回目标永不走代理。"""
    host = (urllib.parse.urlsplit(url).hostname or "").strip().lower()
    if host in ("localhost", "127.0.0.1", "::1", "[::1]"):
        return None
    if proxy is not None:
        return proxy or None
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = os.environ.get(key)
        if val:
            return val
    return None


def _host_of(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").strip().rstrip(".")


def _connect_direct(ip: str, port: int, host: str, tls: bool, timeout: float):
    """连到**批准过的** IP；TLS 的 SNI 与证书校验都用真实域名，所以钉 IP 不等于放弃校验。"""
    sock = socket.create_connection((ip, port), timeout=timeout)
    if tls:
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(sock, server_hostname=host)
    return sock


class NetResponse:
    """urllib 响应的最小替身：只实现 call site 真正用到的那几个方法。"""

    def __init__(self, status: int, headers: Any, url: str, stream: Any = None,
                 cap: int = DEFAULT_MAX_BYTES, conn: Any = None,
                 pinned_ips: Optional[Sequence[str]] = None, via_proxy: bool = False):
        self.status = int(status)
        self.status_code = self.status
        self.headers = headers
        self.url = url
        self.pinned_ips = list(pinned_ips or ())
        self.via_proxy = bool(via_proxy)
        self.truncated = False
        self._stream = stream
        self._conn = conn
        self._cap = max(1, int(cap))
        self._read = 0
        self._buf = b""

    # ---- urllib 兼容面 ----
    def read(self, n: int = -1) -> bytes:
        if self._stream is None:
            return b""
        remaining = max(0, self._cap - self._read)
        want = remaining if (n is None or n < 0) else min(int(n), remaining)
        if want <= 0:
            if remaining == 0 and self._peek_more():
                self.truncated = True
            return b""
        chunk = self._stream.read(want) or b""
        self._read += len(chunk)
        if chunk:
            self._buf += chunk
        if len(chunk) == want and self._read >= self._cap and self._peek_more():
            self.truncated = True
        return chunk

    def _peek_more(self) -> bool:
        try:
            return bool(self._stream.read(1))
        except Exception:
            return False

    def geturl(self) -> str:
        return self.url

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        for obj in (self._stream, self._conn):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        self._stream = None
        self._conn = None

    def __enter__(self) -> "NetResponse":
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.close()
        return False


# ------------------------------------------------------------------ 三条请求路径
def _plain_request(url: str, timeout: float, headers: Dict[str, str], data: Any,
                   method: str, max_bytes: int, proxy: Optional[str]) -> NetResponse:
    """老路径（urllib）：观察模式与代理场景都走它，行为与改造前逐字节一致。"""
    req = urllib.request.Request(url, data=data, headers=dict(headers or {}), method=method)
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    r = opener.open(req, timeout=timeout)
    return NetResponse(getattr(r, "status", 200), r.headers, r.geturl(),
                       stream=r, cap=max_bytes, via_proxy=bool(proxy))


def _pinned_request(url: str, ips: Sequence[str], timeout: float, headers: Dict[str, str],
                    data: Any, method: str, max_bytes: int,
                    connector: Any = None) -> NetResponse:
    """钉住 IP 的直连：只连批准过的地址，Host 与 SNI 用真域名。"""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").strip()
    tls = parts.scheme.lower() == "https"
    port = parts.port or (443 if tls else 80)
    want_host = host if port in (80, 443) else "%s:%d" % (host, port)
    given = {str(k).lower(): v for k, v in (headers or {}).items()}
    if "host" in given and str(given["host"]).strip().lower() != want_host.lower():
        # HTTP 层的"换目标"：URL 指 A、Host 头指 B（虚拟主机绕过）
        raise _sandbox.SandboxDenied("host_header_mismatch",
                                     "Host 头与 URL 主机不一致：%s" % given["host"],
                                     _sandbox.Decision("net.fetch", url, False,
                                                       "host_header_mismatch",
                                                       "Host 头与 URL 主机不一致", mode="enforce"))
    connect = connector or _connect_direct
    sock, last = None, None
    for ip in list(ips):
        try:
            sock = connect(ip, port, host, tls, timeout)
            break
        except Exception as exc:                      # 一个地址不通就试下一个
            last = exc
            sock = None
    if sock is None:
        raise NetError("连接失败（已批准地址 %s）：%r" % (list(ips), last))
    cls = http.client.HTTPSConnection if tls else http.client.HTTPConnection
    conn = cls(host, port, timeout=timeout)
    conn.sock = sock                                   # 预置 socket：http.client 不会再自己解析域名
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    hdrs = {"Connection": "close"}
    hdrs.update({k: v for k, v in (headers or {}).items() if str(k).lower() != "host"})
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    return NetResponse(resp.status, resp.headers, url, stream=resp, cap=max_bytes,
                       conn=conn, pinned_ips=list(ips))


# ------------------------------------------------------------------ 主入口
def _decide(action: str, url: str, sid: str, source: str,
            pinned_ips: Optional[Sequence[str]] = None):
    """过一次门。被拦（enforce 且不允许）就抛 SandboxDenied；否则返回 Decision。"""
    d = _sandbox.gate(action, url, sid=sid, source=source, pinned_ips=pinned_ips)
    if d.blocked:
        raise _sandbox.SandboxDenied(d.code, d.reason, d)
    return d


def fetch(url: str, *, action: str = "net.fetch", timeout: float = DEFAULT_TIMEOUT,
          headers: Optional[Dict[str, str]] = None, data: Any = None,
          method: Optional[str] = None, max_bytes: int = DEFAULT_MAX_BYTES,
          max_redirects: int = DEFAULT_MAX_REDIRECTS, proxy: Optional[str] = None,
          sid: str = "", source: str = "netguard",
          connector: Any = None) -> NetResponse:
    """过门 + 发请求。重定向逐跳重新过门；响应体读取有上限。"""
    if not isinstance(url, str) or not url.strip():
        raise NetError("URL 必须是非空字符串")
    _COUNTERS["fetch"] += 1
    cur = url.strip()
    hdrs = dict(headers or {})
    body = data
    meth = (method or ("POST" if data is not None else "GET")).upper()
    hops = 0
    while True:
        # 渐进上线：只有 net.fetch 自己被强制时才钉 IP 直连；
        # 若只强制了 fs.* 而 net.fetch 还在观察，就走回老路径（不改变出网行为）。
        mode_enforce = _sandbox.enforce_action(action) if _sandbox is not None else False
        d = _decide(action, cur, sid, source)
        eff_proxy = _effective_proxy(cur, proxy)
        if mode_enforce and d.allow and not eff_proxy:
            _COUNTERS["pinned"] += 1
            resp = _pinned_request(cur, d.pinned_ips, timeout, hdrs, body, meth,
                                   max_bytes, connector)
        else:
            _COUNTERS["plain"] += 1
            if eff_proxy:
                _COUNTERS["proxy"] += 1
            resp = _plain_request(cur, timeout, hdrs, body, meth, max_bytes, eff_proxy)
        loc = resp.headers.get("Location") if resp.headers is not None else None
        if resp.status not in _REDIRECT_CODES or not loc:
            return resp
        nxt = urllib.parse.urljoin(cur, loc)
        resp.close()
        hops += 1
        if hops > max(0, int(max_redirects)):
            raise NetError("重定向超过 %d 跳（最后目标 %s）" % (max_redirects, nxt))
        _COUNTERS["redirect"] += 1
        if (urllib.parse.urlsplit(nxt).scheme or "").lower() not in _SCHEMES:
            _decide(action, nxt, sid, source + ".redirect")   # 记账，然后无条件拒绝
            raise NetError("重定向到不允许的 scheme：%s" % nxt)
        if resp.status in (301, 302, 303) and meth != "GET":
            meth, body = "GET", None
        cur = nxt


def urlopen(url: str, **kw: Any) -> NetResponse:
    """ulrlib.urlopen 的替代品（同名参数：timeout / data / headers / method）。"""
    return fetch(url, **kw)


def stats() -> Dict[str, Any]:
    return {"version": VERSION, "counters": counters(), "sandbox": _sandbox.stats(),
            "max_bytes": DEFAULT_MAX_BYTES, "max_redirects": DEFAULT_MAX_REDIRECTS}


if __name__ == "__main__":                                  # pragma: no cover
    import json
    print(json.dumps(stats(), ensure_ascii=False, indent=2)[:800])
