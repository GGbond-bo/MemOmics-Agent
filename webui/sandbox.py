"""P2-3 SandboxProvider —— 进程级能力沙箱（默认拒绝 / 全解析地址公网校验 / TTL 授权）。

设计纪律（和 P2-1/P2-2 一脉相承）：
- **默认拒绝**：没有任何 grant、没有任何 roots → 一律拒绝（unknown action 也拒绝）。
- **不改变默认行为**：本模块默认处于 **观察模式**——判定照算、账照记，但 gate() 不拦人；
  只有显式 MEMOMICS_SANDBOX_ENFORCE=1 才真的拦（.blocked 为 True 时调用方必须拒绝）。
- **防 DNS rebinding**：解析 host 得到**全部**地址，任何一个不是全球可路由就拒绝；
  判定结果里带回 pinned_ips，调用方只准连 pinned 里的地址；再次校验时地址集变了 → url_rebinding。
- **路径逃逸**：realpath（吃掉 .. 与符号链接）+ commonpath 包含判定 + Windows 专属
  （ADS 数据流、保留设备名、盘符相对路径、UNC）；normcase 处理大小写不敏感。
- **有界**：审计环形缓冲有上限；grant 表有过期清理；无网络、无后台线程。
- 内部异常 → 判定为拒绝（fail-closed），但**调用方的集成点**必须额外吞异常（见 security.py），
  保证沙箱自身的 bug 永远不会把老的读写路径打挂。

用法：
    from webui import sandbox
    sandbox.grant("fs.read", "E:/data", ttl_s=600, reason="用户导入")
    d = sandbox.gate("fs.read", "E:/data/a.csv", roots=["E:/data"])
    if d.blocked:            # 只有强制模式才会 True
        raise PermissionError(d.reason)
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import sys
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlsplit, urlunsplit

VERSION = "p2-3.1"

FS_ACTIONS = ("fs.read", "fs.write", "fs.list", "fs.delete")
#: net.fetch = 出网拉取公网资源（默认拒绝，需要授权）；
#: net.local = 本机服务发现（Ollama/LM Studio/vLLM 之类），只认环回、默认放行——
#:             两者策略相反，所以是两个动作，不能混成一个。
NET_ACTIONS = ("net.fetch", "net.local")
OTHER_ACTIONS = ("proc.exec",)
ACTIONS = FS_ACTIONS + NET_ACTIONS + OTHER_ACTIONS

#: 读语义的动作（对目录 roots 生效）
READ_LIKE = {"fs.read", "fs.list", "net.fetch", "net.local"}
#: 写语义的动作（需要可写授权）
WRITE_LIKE = {"fs.write", "fs.delete"}

DEFAULT_TTL_S = 3600.0
DEFAULT_MAX_AUDIT = 2000
_RESOURCE_MAX = 300
_WINDOWS = os.name == "nt"
# 拒绝码 → 人话理由：审计里直接给结论，不让读的人自己翻译代码
_DENY_REASONS = {
    "no_grant": "没有可用授权（默认拒绝）",
    "grant_expired": "授权已过期（TTL 到期），需要重新授权",
    "path_outside_root": "不在任何允许的根内",
    "unknown_action": "未知动作一律拒绝",
    "action_not_implemented": "该动作尚未接入沙箱，按拒绝处理",
}


def _reason_for(code: str, fallback: str = "") -> str:
    return _DENY_REASONS.get(code, fallback or code)


_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | \
                  {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}


class SandboxDenied(PermissionError):
    """强制模式下被沙箱拒绝。"""

    def __init__(self, code: str, message: str, decision: "Optional[Decision]" = None):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message
        self.decision = decision


class Grant:
    """一条显式授权：某动作 + 某资源（路径树 / 域名）+ 有效期。"""

    __slots__ = ("token", "action", "resource", "created_at", "expires_at", "reason",
                 "writable", "hits", "_clock")

    def __init__(self, token: str, action: str, resource: str, created_at: float,
                 expires_at: float, reason: str = "", writable: bool = True,
                 clock: Optional[Callable[[], float]] = None):
        # 时钟与 provider 保持一致：否则注入假时钟时 created_at/expires_at 用假时间、
        # ttl_left 用真实时间，同一条授权自己跟自己矛盾（测试会立刻抓出来）。
        self._clock = clock or time.time
        self.token = token
        self.action = action
        self.resource = resource
        self.created_at = created_at
        self.expires_at = expires_at
        self.reason = reason
        self.writable = writable
        self.hits = 0

    @property
    def ttl_left(self) -> float:
        return self.expires_at - self._clock()

    def as_dict(self) -> Dict[str, Any]:
        return {"token": self.token, "action": self.action, "resource": self.resource,
                "reason": self.reason, "writable": self.writable, "hits": self.hits,
                "created_at": round(self.created_at, 3),
                "expires_at": round(self.expires_at, 3),
                "ttl_left": round(self.ttl_left, 1)}


class Decision:
    """一次判定结果。allow 是策略真值；blocked 才是"会不会真的拦你"。"""

    __slots__ = ("action", "resource", "allow", "code", "reason", "grant", "pinned_ips",
                 "mode", "blocked", "checked_at")

    def __init__(self, action: str, resource: str, allow: bool, code: str, reason: str,
                 grant: Optional[str] = None, pinned_ips: Optional[Sequence[str]] = None,
                 mode: str = "observe", blocked: bool = False):
        self.action = action
        self.resource = resource
        self.allow = allow
        self.code = code
        self.reason = reason
        self.grant = grant
        self.pinned_ips = list(pinned_ips or ())
        self.mode = mode
        self.blocked = blocked
        self.checked_at = time.time()

    def as_dict(self) -> Dict[str, Any]:
        return {"action": self.action, "resource": self.resource, "allow": self.allow,
                "code": self.code, "reason": self.reason, "grant": self.grant,
                "pinned_ips": self.pinned_ips, "mode": self.mode, "blocked": self.blocked}

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return "<Decision %s %s allow=%s code=%s>" % (self.action, self.resource,
                                                       self.allow, self.code)


def classify_ip(ip: str) -> Optional[str]:
    """公网地址返回 None；否则返回拒绝码。"""
    try:
        addr = ipaddress.ip_address(ip.strip())
    except Exception:
        return "url_bad_ip"
    if addr.is_unspecified:
        return "url_reserved"          # 0.0.0.0 / ::（"本机所有地址"）
    if addr.is_loopback:
        return "url_loopback"          # 127.0.0.0/8, ::1
    if addr.is_link_local:
        return "url_link_local"        # 169.254.0.0/16, fe80::/10（云元数据 169.254.169.254）
    if addr.is_multicast:
        return "url_multicast"
    if addr.is_reserved:
        return "url_reserved"          # 240/4, 192.0.0/24 等
    if addr.is_private:
        return "url_private"           # 10/8, 172.16/12, 192.168/16, fc00::/7
    if not addr.is_global:
        return "url_not_global"        # 其余非全球可路由（含 100.64/10、192.0.2/24 等）
    return None


def _default_resolver(host: str) -> List[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({str(i[4][0]) for i in infos})


def _norm(path: str) -> str:
    """realpath + normcase：吃 .. 与符号链接，并在 Windows 上统一大小写。"""
    try:
        real = os.path.realpath(path)
    except Exception:
        return ""
    return os.path.normcase(os.path.normpath(real)) if real else ""


def _within(child: str, parent: str) -> bool:
    if not child or not parent:
        return False
    if child == parent:
        return True
    try:
        return os.path.commonpath([child, parent]) == parent
    except Exception:
        return False


def _safe_resource(resource: Any) -> str:
    """审计里只留可脱敏的形状：URL 去掉 query/fragment（可能带 token）。"""
    try:
        text = resource if isinstance(resource, str) else repr(resource)
    except Exception:
        text = "<unprintable>"
    if text[:1] in ("h", "H") and "://" in text[:12]:
        try:
            parts = urlsplit(text)
            text = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        except Exception:
            pass
    return text[:_RESOURCE_MAX]


class SandboxProvider:
    """一个沙箱实例。线程安全；没有后台任务；两个方向都可注入（clock / resolver）便于离线测试。"""

    def __init__(self, name: str = "default", *, clock: Callable[[], float] = time.time,
                 resolver: Optional[Callable[[str], Sequence[str]]] = None,
                 max_audit: int = DEFAULT_MAX_AUDIT,
                 default_ttl: float = DEFAULT_TTL_S):
        self.name = name
        self._clock = clock
        self._resolver = resolver or _default_resolver
        self._max_audit = max(10, int(max_audit))
        self._default_ttl = float(default_ttl)
        self._lock = threading.RLock()
        self._grants: Dict[str, Grant] = {}
        self._audit: deque = deque(maxlen=self._max_audit)
        self._codes: Dict[str, int] = {}
        self._seq = 0
        self.counts = {"allow": 0, "deny": 0, "would_deny": 0, "blocked": 0,
                       "granted": 0, "revoked": 0, "expired": 0, "disabled": 0}

    # ------------------------------------------------------------ 授权
    def grant(self, action: str, resource: str, ttl_s: Optional[float] = None,
              reason: str = "", writable: bool = True) -> Grant:
        """显式授权。默认拒绝的反面就是"必须有这一句"。"""
        if action not in ACTIONS:
            raise ValueError("未知动作，不能授权：%r" % (action,))
        if not isinstance(resource, str) or not resource:
            raise ValueError("资源必须是字符串")
        now = self._clock()
        ttl = self._default_ttl if ttl_s is None else float(ttl_s)
        if ttl <= 0:
            raise ValueError("ttl_s 必须为正（用 revoke 来收回授权）")
        norm = self._norm_resource(action, resource)
        with self._lock:
            self._seq += 1
            token = "%s-%d" % (action.replace(".", ""), self._seq)
            g = Grant(token, action, norm, now, now + ttl, reason, writable, clock=self._clock)
            self._grants[token] = g
            self.counts["granted"] += 1
        return g

    def revoke(self, token: str) -> bool:
        with self._lock:
            g = self._grants.pop(token, None)
            if g is not None:
                self.counts["revoked"] += 1
            return g is not None

    def grants(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [g.as_dict() for g in self._grants.values()]

    def purge_expired(self) -> int:
        now = self._clock()
        dead = []
        with self._lock:
            for token, g in list(self._grants.items()):
                if g.expires_at <= now:
                    dead.append(token)
                    self.counts["expired"] += 1
            for token in dead:
                self._grants.pop(token, None)
        return len(dead)

    def _norm_resource(self, action: str, resource: str) -> str:
        if action in FS_ACTIONS:
            return _norm(os.path.expanduser(resource)) or resource
        return resource.strip().lower()

    def _lookup(self, action: str, resource: str) -> Tuple[Optional[Grant], str]:
        """找可用授权。返回 (grant, 拒绝码)；没找到时码为 grant_expired 或 no_grant。"""
        now = self._clock()
        expired = False
        with self._lock:
            for g in self._grants.values():
                if g.action != action:
                    continue
                if g.expires_at <= now:
                    expired = True
                    continue
                if action in FS_ACTIONS:
                    base = _norm(os.path.expanduser(g.resource))
                    target = _norm(os.path.expanduser(resource))
                    if not _within(target, base):
                        continue
                    if action in WRITE_LIKE and not g.writable:
                        continue
                else:
                    host = resource.strip().lower().lstrip(".")
                    base = g.resource.lstrip(".")
                    if not (host == base or host.endswith("." + base)):
                        continue
                g.hits += 1
                return g, ""
        return None, ("grant_expired" if expired else "no_grant")

    # ------------------------------------------------------------ 判定
    def check(self, action: str, resource: Any, *, roots: Optional[Iterable[str]] = None,
              pinned_ips: Optional[Sequence[str]] = None, sid: str = "",
              source: str = "") -> Decision:
        """纯策略判定：只算不拦。任何内部异常都变成拒绝（fail-closed）。"""
        mode = "enforce" if enforce_enabled() else "observe"
        try:
            if action not in ACTIONS:
                return Decision(action, _safe_resource(resource), False, "unknown_action",
                                "未知动作一律拒绝：%r" % (action,), mode=mode)
            if action in FS_ACTIONS:
                return self._check_path(action, resource, roots, mode)
            if action in NET_ACTIONS:
                return self._check_host(action, resource, pinned_ips, mode)
            return Decision(action, _safe_resource(resource), False, "action_not_implemented",
                            "该动作没有实现执行通道，拒绝", mode=mode)
        except Exception as exc:                                  # pragma: no cover
            return Decision(str(action), _safe_resource(resource), False, "internal_error",
                            "沙箱内部异常（按拒绝处理）：%r" % (exc,), mode=mode)

    def _check_path(self, action: str, path: Any, roots: Optional[Iterable[str]],
                    mode: str) -> Decision:
        raw = path if isinstance(path, str) else ""
        if not isinstance(path, str) or not path.strip():
            return Decision(action, _safe_resource(path), False, "path_bad_type",
                            "路径必须是非空字符串", mode=mode)
        if "\x00" in path:
            return Decision(action, _safe_resource(path), False, "path_null_byte",
                            "路径含 NUL 字节", mode=mode)
        try:
            expanded = os.path.expanduser(path)
        except Exception:
            expanded = path
        if _WINDOWS:
            # 盘符相对（C:foo）在 isabs() 眼里"不是绝对路径"，但语义是"当前盘当前目录下"，
            # 必须单独拦——否则会被降级成普通的 path_not_absolute，丢掉这条明确的拒绝理由。
            drive, tail = os.path.splitdrive(expanded)
            if drive and not tail.startswith(("\\", "/")):
                return Decision(action, _safe_resource(expanded), False, "path_drive_relative",
                                "盘符相对路径（C:foo）语义绑定当前目录，拒绝", mode=mode)
        if not os.path.isabs(expanded):
            return Decision(action, _safe_resource(expanded), False, "path_not_absolute",
                            "只接受绝对路径（相对路径语义不可控）", mode=mode)
        if _WINDOWS:
            body = tail.replace("/", "\\")
            for part in [p for p in body.split("\\") if p]:
                if ":" in part:
                    return Decision(action, _safe_resource(expanded), False, "path_ads",
                                    "Windows 备用数据流（file:stream）拒绝", mode=mode)
                if part.split(".")[0].upper() in _RESERVED_NAMES:
                    return Decision(action, _safe_resource(expanded), False,
                                    "path_reserved_device",
                                    "Windows 保留设备名（%s）拒绝" % part, mode=mode)
        real = _norm(expanded)
        if not real:
            return Decision(action, _safe_resource(expanded), False, "path_unresolvable",
                            "路径无法解析", mode=mode)
        allowed_roots: List[str] = []
        for r in (roots or ()):
            if isinstance(r, str) and r.strip():
                rr = _norm(os.path.expanduser(r))
                if rr:
                    allowed_roots.append(rr)
        for r in allowed_roots:
            if _within(real, r):
                return Decision(action, real, True, "ok_callers_root",
                                "在调用方声明的根内：%s" % r, mode=mode)
        grant, code = self._lookup(action, expanded)
        if grant is not None:
            return Decision(action, real, True, "ok_grant",
                            "命中授权 %s（%s）" % (grant.token, grant.reason or "无备注"),
                            grant=grant.token, mode=mode)
        if allowed_roots:
            return Decision(action, real, False, "path_outside_root",
                            "不在任何允许的根内：%s" % real, mode=mode)
        return Decision(action, real, False, code, _reason_for(code, "没有可用授权（默认拒绝）"),
                        mode=mode)

    def _check_host(self, action: str, url: Any, pinned_ips: Optional[Sequence[str]],
                    mode: str) -> Decision:
        raw = url if isinstance(url, str) else ""
        if not isinstance(url, str) or not url.strip():
            return Decision(action, _safe_resource(url), False, "url_bad_type",
                            "URL 必须是非空字符串", mode=mode)
        try:
            parts = urlsplit(raw.strip())
        except Exception:
            return Decision(action, _safe_resource(raw), False, "url_unparsable",
                            "URL 解析失败", mode=mode)
        if parts.scheme.lower() not in ("http", "https"):
            return Decision(action, _safe_resource(raw), False, "url_bad_scheme",
                            "只允许 http/https，收到 %r" % (parts.scheme,), mode=mode)
        if "@" in (parts.netloc or ""):
            return Decision(action, _safe_resource(raw), False, "url_userinfo",
                            "URL 带 userinfo（user:pass@host）拒绝", mode=mode)
        host = (parts.hostname or "").strip()
        if not host:
            return Decision(action, _safe_resource(raw), False, "url_no_host",
                            "URL 没有主机名", mode=mode)
        if "%" in host:
            return Decision(action, _safe_resource(raw), False, "url_zone_id",
                            "IPv6 zone id（%25eth0）拒绝", mode=mode)
        host = host.rstrip(".") or host
        try:
            addrs = [str(ipaddress.ip_address(host))]
        except Exception:
            try:
                addrs = [str(a) for a in self._resolver(host)]
            except Exception as exc:
                return Decision(action, _safe_resource(raw), False, "url_dns_fail",
                                "域名解析失败：%r" % (exc,), mode=mode)
        addrs = sorted({a for a in addrs if a})
        if not addrs:
            return Decision(action, _safe_resource(raw), False, "url_dns_fail",
                            "域名没有解析出任何地址", mode=mode)
        if action == "net.local":
            # 「本机服务」与「公网请求」是两种相反的能力：
            # net.local 只认环回（自己机器上的 Ollama/LM Studio/vLLM），且默认放行；
            # 任何非环回地址都进不来——云元数据 169.254.169.254 属链路本地，同样挡在这里。
            for a in addrs:
                try:
                    loop = ipaddress.ip_address(a).is_loopback
                except Exception:
                    loop = False
                if not loop:
                    return Decision(action, _safe_resource(raw), False, "local_not_loopback",
                                    "net.local 只允许环回地址，%s（%s）不是本机" % (a, host),
                                    mode=mode, pinned_ips=addrs)
            return Decision(action, _safe_resource(raw), True, "ok_local",
                            "本机服务（环回）默认放行：%s" % host, mode=mode, pinned_ips=addrs)
        # 防 rebinding：**全部**解析地址都必须是公网；任何一个不合法就整条拒绝
        for a in addrs:
            bad = classify_ip(a)
            if bad:
                return Decision(action, _safe_resource(raw), False, bad,
                                "解析到非公网地址 %s（%s）" % (a, host), mode=mode,
                                pinned_ips=addrs)
        if pinned_ips:
            pinned = {str(p) for p in pinned_ips}
            if not pinned.issuperset(addrs) or not set(addrs).issuperset(pinned):
                return Decision(action, _safe_resource(raw), False, "url_rebinding",
                                "解析结果变了（旧 %s / 新 %s）——疑似 DNS rebinding"
                                % (sorted(pinned), addrs), mode=mode, pinned_ips=addrs)
        grant, code = self._lookup(action, host)
        if grant is None:
            return Decision(action, _safe_resource(raw), False, code,
                            "该域名没有授权（默认拒绝）", mode=mode, pinned_ips=addrs)
        return Decision(action, _safe_resource(raw), True, "ok_grant",
                        "命中授权 %s" % grant.token, grant=grant.token, mode=mode,
                        pinned_ips=addrs)

    # ------------------------------------------------------------ 门（会被真的拦）
    def gate(self, action: str, resource: Any, **kw: Any) -> Decision:
        """集成点用的门：观察模式只记账（blocked=False），强制模式拒绝（blocked=True）。"""
        if not enabled():
            self.counts["disabled"] += 1
            d = Decision(action, _safe_resource(resource), True, "disabled",
                         "MEMOMICS_SANDBOX=0，整体关闭", mode="off")
            self._record(d, kw.get("sid", ""), kw.get("source", ""), 0.0)
            return d
        t0 = time.perf_counter()
        d = self.check(action, resource, **kw)
        if d.allow:
            self.counts["allow"] += 1
        else:
            self.counts["deny"] += 1
            if d.mode == "enforce":
                d.blocked = True
                self.counts["blocked"] += 1
            else:
                self.counts["would_deny"] += 1
        self._record(d, kw.get("sid", ""), kw.get("source", ""),
                     (time.perf_counter() - t0) * 1000.0)
        return d

    def require(self, action: str, resource: Any, **kw: Any) -> Decision:
        """无条件按策略执行：不允许就抛 SandboxDenied（不看观察/强制开关，供内部与测试用）。"""
        d = self.check(action, resource, **kw)
        if not d.allow:
            raise SandboxDenied(d.code, d.reason, d)
        return d

    # ------------------------------------------------------------ 审计
    def _record(self, d: Decision, sid: str, source: str, dur_ms: float) -> None:
        with self._lock:
            self._seq += 1
            self._audit.append({
                "seq": self._seq,
                "ts": round(self._clock(), 3),
                "action": d.action,
                "resource": d.resource,
                "allow": d.allow,
                "code": d.code,
                "reason": d.reason,
                "grant": d.grant,
                "mode": d.mode,
                "blocked": d.blocked,
                "sid": (sid or "")[:32],
                "source": (source or "")[:64],
                "pinned_ips": d.pinned_ips,
                "dur_ms": round(dur_ms, 3),
            })
            self._codes[d.code] = self._codes.get(d.code, 0) + 1

    def audit(self, limit: int = 50, codes: bool = False) -> Dict[str, Any]:
        with self._lock:
            items = list(self._audit)[-max(1, int(limit)):][::-1]
            out: Dict[str, Any] = {"name": self.name, "enabled": enabled(),
                                   "enforce": enforce_enabled(), "mode": sandbox_mode(),
                                   "total": len(self._audit), "max": self._max_audit,
                                   "counts": dict(self.counts), "items": items,
                                   "grants": self.grants(), "version": VERSION}
            if codes:
                out["codes"] = dict(sorted(self._codes.items(),
                                           key=lambda kv: (-kv[1], kv[0])))
            return out

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"name": self.name, "enabled": enabled(), "enforce": enforce_enabled(),
                    "mode": sandbox_mode(),
                    "counts": dict(self.counts), "audited": len(self._audit),
                    "max": self._max_audit, "grants": len(self._grants),
                    "codes": len(self._codes), "actions": list(ACTIONS),
                    "version": VERSION}

    def reset(self) -> None:
        with self._lock:
            self._grants.clear()
            self._audit.clear()
            self._codes.clear()
            self._seq = 0
            for k in self.counts:
                self.counts[k] = 0


# ============================================================== 进程级门面
_PROVIDER = SandboxProvider()
_PROVIDER_LOCK = threading.RLock()


def provider() -> SandboxProvider:
    return _PROVIDER


def set_provider(p: SandboxProvider) -> SandboxProvider:
    global _PROVIDER
    with _PROVIDER_LOCK:
        old, _PROVIDER = _PROVIDER, p
    return old


def enabled() -> bool:
    return os.environ.get("MEMOMICS_SANDBOX", "1") not in ("0", "false", "no", "off")


def enforce_enabled() -> bool:
    return os.environ.get("MEMOMICS_SANDBOX_ENFORCE", "") not in ("", "0", "false", "no")


def sandbox_mode() -> str:
    """一句话说清当前状态：disabled（整体关）/ enforce（真拦）/ observe（只记账）。"""
    if not enabled():
        return "disabled"
    return "enforce" if enforce_enabled() else "observe"


def grant(action: str, resource: str, ttl_s: Optional[float] = None, reason: str = "",
          writable: bool = True) -> Grant:
    return _PROVIDER.grant(action, resource, ttl_s, reason, writable)


def revoke(token: str) -> bool:
    return _PROVIDER.revoke(token)


def check(action: str, resource: Any, **kw: Any) -> Decision:
    return _PROVIDER.check(action, resource, **kw)


def gate(action: str, resource: Any, **kw: Any) -> Decision:
    return _PROVIDER.gate(action, resource, **kw)


def require(action: str, resource: Any, **kw: Any) -> Decision:
    return _PROVIDER.require(action, resource, **kw)


def purge_expired() -> int:
    return _PROVIDER.purge_expired()


def grants() -> List[Dict[str, Any]]:
    """当前授权清单（含 TTL 余量）——"我到底授权了什么"必须随时能看见。"""
    return _PROVIDER.grants()


def audit(limit: int = 50, codes: bool = False) -> Dict[str, Any]:
    return _PROVIDER.audit(limit, codes)


def stats() -> Dict[str, Any]:
    return _PROVIDER.stats()


def reset() -> None:
    _PROVIDER.reset()


__all__ = [
    "VERSION", "ACTIONS", "FS_ACTIONS", "NET_ACTIONS", "OTHER_ACTIONS",
    "READ_LIKE", "WRITE_LIKE", "DEFAULT_TTL_S", "DEFAULT_MAX_AUDIT",
    "SandboxDenied", "Grant", "Decision", "SandboxProvider",
    "classify_ip", "provider", "set_provider", "enabled", "enforce_enabled",
    "grant", "revoke", "grants", "purge_expired", "check", "gate", "require",
    "audit", "stats", "reset",
]


def _selftest() -> None:  # pragma: no cover - 手工验证用
    p = SandboxProvider(name="selftest", resolver=lambda h: ["93.184.216.34"])
    print("默认拒绝:", p.require.__name__, "->", p.check("fs.read", "E:/x").code)
    print("未知动作 :", p.check("os.reboot", "x").code)
    g = p.grant("fs.read", "E:/data", ttl_s=1)
    print("授权后   :", p.check("fs.read", "E:/data/a.csv").code, g.token)
    print("逃逸     :", p.check("fs.read", "E:/data/../secret").code)
    print("公网     :", p.check("net.fetch", "https://example.com/a").code)
    print("内网     :", p.check("net.fetch", "http://169.254.169.254/latest").code)
    print("本地     :", p.check("net.fetch", "http://127.0.0.1:8899/api/version").code)


if __name__ == "__main__":  # pragma: no cover
    if "--selftest" in sys.argv:
        _selftest()
    elif "--stats" in sys.argv:
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
    else:
        print(__doc__)
