# -*- coding: utf-8 -*-
"""P2-1 入口侧中间件链：一次请求一条链，每一段只管一件事。

背景（2026-09-23 实测）：webui/server.py 有 119 个装饰器端点 / 134 条路由，
却一个中间件都没有（@app.middleware 0 处、Depends() 0 处），于是
"Session not found" 这句在 6+ 个处理函数里各写一遍，请求日志、限流、
审计各端点各写各的。本模块把这些收成一条链：

    请求 → request_id → 归类(policy) → session_guard → rate_limit → 业务处理 → audit

为了「接了链但行为不变」，三条硬约束：
1. 纯 ASGI 中间件：不缓冲响应体；websocket / lifespan 原样透传（/ws 是活的）。
2. 默认只观察不拦截。只有显式设了环境变量才拦，所以默认行为与接链前一致；
   test_p2_1_middleware.py 里有 A/B 对拍用例证明这一点。
3. 整条链可一键关闭：MEMOMICS_MW=0（连请求头都不加）。

本模块不 import server.py（避免循环依赖）：需要的能力（会话是否存在）由
server.py 启动时用 configure() 注入；没注入就只标记不判断。

环境变量：
    MEMOMICS_MW=0                   整条链不生效（退回接链前的行为）
    MEMOMICS_MW_SESSION_ENFORCE=1   会话守卫真的返回 404（默认只标记）
    MEMOMICS_MW_RATE_LIMIT=120      每 60 秒每 IP+路径前缀的请求上限（默认不限）
    MEMOMICS_MW_ERROR_ENVELOPE=1    未捕获异常返回带 request_id 的 JSON 500

路由清单：webui/middleware_routes.json 是冻结的全部路由模板与归类，
python webui/entry_middleware.py --snapshot 可重新生成；门禁测试会比对，
新增端点若没同步清单就会失败——这就是「新增端点不挂链会被拦下」。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

REQUEST_ID_HEADER = "x-request-id"
REQUEST_ID_HEADER_BYTES = b"x-request-id"

# 路由归类（policy）----------------------------------------------------------
POLICY_STATIC = "static"      # 静态页/资源/自动文档，无副作用
POLICY_PUBLIC = "public"      # 无会话参数的本机接口
POLICY_SESSION = "session"    # 路径里带 {sid}，属于某个会话
POLICY_LOCAL = "local"        # 只对本机有意义的运维口（更新、开文件夹、环境探测）
POLICY_WS = "ws"              # 长连接
POLICY_OBSERVE = "observe"    # 没匹配上任何规则：只观察并记账，绝不拦

# (规则, 归类, 模式)：模式 exact 表示整条路径相等，prefix 表示按段前缀匹配；
# 规则里的 {xxx} 段匹配任意一段，路径更深的路由优先（最长前缀赢）。
ROUTE_RULES: Tuple[Tuple[str, str, str], ...] = (
    ("/", POLICY_STATIC, "exact"),
    ("/openapi.json", POLICY_STATIC, "exact"),
    ("/docs", POLICY_STATIC, "exact"),
    ("/redoc", POLICY_STATIC, "exact"),
    ("/docs/oauth2-redirect", POLICY_STATIC, "exact"),
    ("/assets", POLICY_STATIC, "prefix"),
    ("/uploads", POLICY_STATIC, "prefix"),
    ("/ws", POLICY_WS, "exact"),
    ("/api/version", POLICY_PUBLIC, "exact"),
    ("/api/health", POLICY_PUBLIC, "exact"),
    ("/api/runtime", POLICY_PUBLIC, "exact"),
    ("/api/resources", POLICY_PUBLIC, "exact"),
    ("/api/ui/lang", POLICY_PUBLIC, "exact"),
    ("/api/update", POLICY_LOCAL, "prefix"),
    ("/api/file", POLICY_LOCAL, "prefix"),
    ("/api/env", POLICY_LOCAL, "prefix"),
    ("/api/sessions/{sid}", POLICY_SESSION, "prefix"),
    ("/api/results/{sid}", POLICY_SESSION, "prefix"),
    ("/api/todos/{sid}", POLICY_SESSION, "prefix"),
    ("/api/enforcement/{sid}", POLICY_SESSION, "prefix"),
    ("/api", POLICY_PUBLIC, "prefix"),
)

# 只有这些 GET 路由在「会话不存在」时返回 404，会话守卫的强制模式只对它们生效，
# 且只认 GET（无副作用）。这份名单是实测出来的，测试会拿真实处理函数逐条复核：
#   /api/sessions/{sid}/skills    → 200（返回空 pinned/used，不是错误）
#   /api/enforcement/{sid}        → 200（返回默认 chat 级别，不是错误）
# 这两个刻意不在名单里——它们「找不到会话」不算错，拦了才是破坏行为。
SESSION_ENFORCE_PATHS: Tuple[str, ...] = (
    "/api/sessions/{sid}/messages",
    "/api/sessions/{sid}/outline",
    "/api/sessions/{sid}/goal",
    "/api/sessions/{sid}/changes",
    "/api/sessions/{sid}/progress",
    "/api/sessions/{sid}/citations",
    "/api/todos/{sid}",
)

SESSION_NOT_FOUND_BODY = {"error": "Session not found"}
SESSION_NOT_FOUND_STATUS = 404

MAX_AUDIT = 1000
MAX_REQUEST_ID = 64
MAX_TEMPLATE_CHARS = 160


def _clip(text: Any, limit: int = MAX_TEMPLATE_CHARS) -> str:
    """审计里存的东西都要有上限：超长路径不能把内存吃光。"""
    s = str(text or "")
    return s if len(s) <= limit else s[:limit] + "..."


# --- 开关 -------------------------------------------------------------------

def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


_ENABLED = _env_flag("MEMOMICS_MW", True)
_lock = threading.Lock()
_session_exists: Optional[Callable[[str], bool]] = None
_audit: deque = deque(maxlen=MAX_AUDIT)
_counters: Dict[str, Any] = {
    "total": 0, "enforced": 0, "errors": 0, "unclassified": 0,
    "by_policy": {}, "by_status": {},
}


def enabled() -> bool:
    """链是否生效（MEMOMICS_MW=0 时整条链不介入）。"""
    return _ENABLED


def set_enabled(flag: bool) -> None:
    """测试用：临时开关整条链，方便 A/B 对拍。"""
    global _ENABLED
    _ENABLED = bool(flag)


def configure(session_exists: Optional[Callable[[str], bool]] = None) -> None:
    """由 server.py 注入「会话是否存在」；不注入时守卫只标记不判断。"""
    global _session_exists
    if session_exists is not None:
        _session_exists = session_exists


def session_exists_hook() -> Optional[Callable[[str], bool]]:
    return _session_exists


def session_enforce_enabled() -> bool:
    return _env_flag("MEMOMICS_MW_SESSION_ENFORCE", False)


def error_envelope_enabled() -> bool:
    return _env_flag("MEMOMICS_MW_ERROR_ENVELOPE", False)


def rate_limit_per_minute() -> int:
    try:
        return max(0, int(str(os.environ.get("MEMOMICS_MW_RATE_LIMIT", "0")).strip() or 0))
    except Exception:
        return 0


# --- 归类 -------------------------------------------------------------------

def _segs(path: str) -> List[str]:
    return [s for s in (path or "/").split("/") if s]


def classify(path: str) -> Tuple[str, str]:
    """返回 (归类, 命中的规则)。按段做最长前缀匹配，{xxx} 段匹配任意一段。"""
    psegs = _segs(path)
    best_len, best_policy, best_rule = -1, POLICY_OBSERVE, ""
    for rule, policy, mode in ROUTE_RULES:
        rsegs = _segs(rule)
        if mode == "exact" and len(psegs) != len(rsegs):
            continue
        if len(rsegs) > len(psegs):
            continue
        hit = True
        for rs, ps in zip(rsegs, psegs):
            if rs.startswith("{") and rs.endswith("}"):
                continue
            if rs != ps:
                hit = False
                break
        if hit and len(rsegs) > best_len:
            best_len, best_policy, best_rule = len(rsegs), policy, rule
    return best_policy, best_rule


def extract_sid(path: str, rule: str) -> Optional[str]:
    """从命中的规则里取出 {sid} 那一段的真实值。"""
    rsegs, psegs = _segs(rule), _segs(path)
    for i, rs in enumerate(rsegs):
        if rs in ("{sid}", "{session_id}") and i < len(psegs):
            return psegs[i]
    return None


def _template_of(rule: str, path: str) -> str:
    """把实际路径按规则还原成模板（审计里只记模板，不记真实会话号）。

    保留整条路径，只把规则里 {xxx} 那几段换回占位符：
    /api/sessions/abc/messages -> /api/sessions/{sid}/messages
    （只还原规则前缀会丢掉 /messages 尾巴，白名单和审计都对不上。）
    """
    rsegs, psegs = _segs(rule), _segs(path)
    if not rsegs:
        return path
    out = []
    for i, ps in enumerate(psegs):
        rs = rsegs[i] if i < len(rsegs) else None
        out.append(rs if (rs and rs.startswith("{") and rs.endswith("}")) else ps)
    return "/" + "/".join(out)


# --- 请求上下文（一次请求一个对象，谁持有写清楚）-----------------------------

@dataclass
class RequestContext:
    request_id: str
    method: str
    path: str
    query: str = ""
    policy: str = POLICY_OBSERVE
    rule: str = ""
    template: str = ""
    sid: Optional[str] = None
    client: str = ""
    started: float = field(default_factory=time.time)
    status: int = 0
    stages: List[str] = field(default_factory=list)
    decision: str = "allow"
    reason: str = ""
    done: bool = False

    def note(self, stage: str) -> None:
        self.stages.append(stage)

    def as_record(self) -> Dict[str, Any]:
        return {
            "id": self.request_id,
            "ts": round(self.started, 3),
            "m": self.method,
            "t": _clip(self.template or self.path),
            "pol": self.policy,
            "st": self.status,
            "ms": round((time.time() - self.started) * 1000, 1),
            "sid": self.sid or "",
            "ip": self.client,
            "dec": self.decision,
            "why": self.reason,
        }


def _client_of(scope: Dict[str, Any]) -> str:
    client = scope.get("client") or ()
    try:
        return str(client[0])
    except Exception:
        return ""


def _clean_request_id(raw: str) -> str:
    keep = "".join(c for c in str(raw or "") if c.isalnum() or c in "-_")
    return keep[:MAX_REQUEST_ID]


def new_context(scope: Dict[str, Any], headers: Optional[List[Tuple[bytes, bytes]]] = None) -> RequestContext:
    path = scope.get("path") or "/"
    query = scope.get("query_string") or b""
    if isinstance(query, bytes):
        query = query.decode("utf-8", "replace")
    rid = ""
    for k, v in (headers or scope.get("headers") or []):
        if k.lower() == REQUEST_ID_HEADER_BYTES:
            rid = _clean_request_id(v.decode("utf-8", "replace"))
            break
    policy, rule = classify(path)
    return RequestContext(
        request_id=rid or uuid.uuid4().hex[:16],
        method=str(scope.get("method") or "GET").upper(),
        path=path,
        query=query,
        policy=policy,
        rule=rule,
        template=_template_of(rule, path) if rule else path,
        sid=extract_sid(path, rule) if rule else None,
        client=_client_of(scope),
    )


# --- 限流（默认关）----------------------------------------------------------

_rate_lock = threading.Lock()
_rate_state: Dict[str, List[float]] = {}


def _rate_key(ctx: RequestContext) -> str:
    segs = _segs(ctx.path)[:2]
    return ctx.client + "|" + "/" + "/".join(segs)


def rate_limit_hit(ctx: RequestContext, limit: Optional[int] = None) -> bool:
    """令牌桶（按 IP+路径前缀）。未启用时永远返回 False。"""
    per_min = rate_limit_per_minute() if limit is None else int(limit)
    if per_min <= 0:
        return False
    now = time.time()
    key = _rate_key(ctx)
    with _rate_lock:
        if len(_rate_state) > 5000:  # 防内存无限增长
            for k in [k for k, v in _rate_state.items() if not v or now - v[-1] > 120]:
                _rate_state.pop(k, None)
        q = [t for t in _rate_state.get(key, []) if now - t < 60]
        if len(q) >= per_min:
            _rate_state[key] = q
            return True
        q.append(now)
        _rate_state[key] = q
    return False


def reset_rate_limit() -> None:
    with _rate_lock:
        _rate_state.clear()


# --- 审计 -------------------------------------------------------------------

def record(ctx: RequestContext) -> None:
    if ctx.done:
        return
    ctx.done = True
    rec = ctx.as_record()
    with _lock:
        _audit.append(rec)
        _counters["total"] += 1
        _counters["by_policy"][ctx.policy] = _counters["by_policy"].get(ctx.policy, 0) + 1
        _counters["by_status"][str(ctx.status)] = _counters["by_status"].get(str(ctx.status), 0) + 1
        if ctx.policy == POLICY_OBSERVE:
            _counters["unclassified"] += 1
        if ctx.decision != "allow":
            _counters["enforced"] += 1


def note_error(ctx: RequestContext) -> None:
    with _lock:
        _counters["errors"] += 1


def recent(n: int = 50) -> List[Dict[str, Any]]:
    n = max(1, min(int(n or 50), MAX_AUDIT))
    with _lock:
        return list(_audit)[-n:][::-1]


def stats() -> Dict[str, Any]:
    with _lock:
        return {
            "enabled": enabled(),
            "session_enforce": session_enforce_enabled(),
            "rate_limit_per_minute": rate_limit_per_minute(),
            "error_envelope": error_envelope_enabled(),
            "session_exists_hook": _session_exists is not None,
            "audit_size": len(_audit),
            "max_audit": MAX_AUDIT,
            "policies": list(_counters["by_policy"].items()),
            "statuses": list(_counters["by_status"].items()),
            "total": _counters["total"],
            "enforced": _counters["enforced"],
            "errors": _counters["errors"],
            "unclassified": _counters["unclassified"],
        }


def reset_audit() -> None:
    with _lock:
        _audit.clear()
        for k in ("total", "enforced", "errors", "unclassified"):
            _counters[k] = 0
        _counters["by_policy"] = {}
        _counters["by_status"] = {}


# --- 守卫 -------------------------------------------------------------------

def session_guard(ctx: RequestContext) -> Optional[Tuple[int, Dict[str, Any]]]:
    """会话守卫。默认只标记（session_exists 字段进审计），开了开关才拦。

    只对 GET + SESSION_ENFORCE_PATHS 里列出的模板生效，避免误伤
    「找不到会话但也不算错」的接口（例如 results 目录为空）。
    """
    if not ctx.sid:
        ctx.note("session_guard:skip")
        return None
    known = None
    if _session_exists is not None:
        try:
            known = bool(_session_exists(ctx.sid))
        except Exception:
            known = None
    ctx.note("session_guard:%s" % ("known" if known else ("unknown" if known is False else "unchecked")))
    if known is not False:
        return None
    if not session_enforce_enabled():
        return None
    if ctx.method != "GET" or ctx.template not in SESSION_ENFORCE_PATHS:
        return None
    ctx.decision, ctx.reason = "deny", "session_not_found"
    return SESSION_NOT_FOUND_STATUS, dict(SESSION_NOT_FOUND_BODY)


def precheck(ctx: RequestContext) -> Optional[Tuple[int, Dict[str, Any]]]:
    """链上的判断段（request_id / 归类 / 守卫 / 限流），返回即短路。"""
    ctx.note("request_id")
    ctx.note("policy:%s" % ctx.policy)
    if ctx.policy == POLICY_OBSERVE:
        ctx.reason = ctx.reason or "unclassified_route"
    short = session_guard(ctx)
    if short is not None:
        return short
    if rate_limit_hit(ctx):
        ctx.decision, ctx.reason = "deny", "rate_limited"
        ctx.note("rate_limit:deny")
        return 429, {"error": "Too Many Requests", "request_id": ctx.request_id}
    ctx.note("rate_limit:ok")
    return None


# --- ASGI 中间件 -------------------------------------------------------------

def _json_bytes(body: Dict[str, Any]) -> bytes:
    """与 starlette.responses.JSONResponse 完全同参，保证字节一致。

    这样「守卫拦下的 404」和「处理函数自己返回的 404」是同一串字节，
    A/B 对拍才有意义（Starlette 用 separators=(",", ":")，没有空格）。
    """
    return json.dumps(body, ensure_ascii=False, allow_nan=False, indent=None, separators=(",", ":")).encode("utf-8")


async def _send_json(send: Callable, status: int, body: Dict[str, Any], ctx: RequestContext) -> None:
    payload = _json_bytes(body)
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(payload)).encode()),
        (REQUEST_ID_HEADER_BYTES, ctx.request_id.encode()),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload, "more_body": False})


class EntryMiddleware:
    """入口侧中间件链（纯 ASGI，不缓冲响应体）。"""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or not _ENABLED:
            await self.app(scope, receive, send)
            return

        ctx = new_context(scope)
        short = precheck(ctx)
        if short is not None:
            await _send_json(send, short[0], short[1], ctx)
            ctx.status = short[0]
            ctx.note("short_circuit")
            record(ctx)
            return

        started = False

        async def send_wrapper(message: Dict[str, Any]) -> None:
            nonlocal started
            mtype = message.get("type")
            if mtype == "http.response.start":
                started = True
                ctx.status = int(message.get("status") or 200)
                headers = [(k, v) for (k, v) in (message.get("headers") or []) if k.lower() != REQUEST_ID_HEADER_BYTES]
                headers.append((REQUEST_ID_HEADER_BYTES, ctx.request_id.encode()))
                message = dict(message, headers=headers)
            elif mtype == "http.response.body":
                if not message.get("more_body"):
                    ctx.note("audit")
                    record(ctx)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            note_error(ctx)
            if started or not error_envelope_enabled():
                raise
            ctx.status = 500
            ctx.decision, ctx.reason = "error", "unhandled_exception"
            await _send_json(send, 500, {"error": "Internal Server Error", "request_id": ctx.request_id}, ctx)
            record(ctx)


# --- 安装 -------------------------------------------------------------------

def install(app: Any, session_exists: Optional[Callable[[str], bool]] = None) -> bool:
    """把链挂到 FastAPI 应用上。返回是否真的挂了。

    必须在应用启动前调用（server.py 在 import 阶段调用）。
    任何异常都不许影响 server.py 启动：调用方 server.py 还包了一层 try/except。
    """
    if session_exists is not None:
        configure(session_exists)
    if not _ENABLED:
        return False
    app.add_middleware(EntryMiddleware)
    return True


# --- 路由清单（冻结）--------------------------------------------------------

ROUTES_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "middleware_routes.json")


def snapshot_from_app(app: Any) -> Dict[str, str]:
    """从 FastAPI 应用里读出全部路由模板 → 归类（生成清单用，也在测试里比对）。"""
    out: Dict[str, str] = {}
    for route in getattr(app, "routes", []) or []:
        path = getattr(route, "path", None)
        if not path:
            continue
        policy, _rule = classify(path)
        out[path] = policy
    return dict(sorted(out.items()))


def load_route_manifest() -> Dict[str, str]:
    try:
        with open(ROUTES_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): str(v) for k, v in (data or {}).items()}
    except Exception:
        return {}


def route_audit(app: Any) -> Dict[str, Any]:
    """比对「应用里真实的路由」与「冻结清单」，用于门禁。"""
    actual = snapshot_from_app(app)
    frozen = load_route_manifest()
    return {
        "actual": actual,
        "frozen": frozen,
        "added": sorted(set(actual) - set(frozen)),
        "removed": sorted(set(frozen) - set(actual)),
        "reclassified": sorted(k for k in set(actual) & set(frozen) if actual[k] != frozen[k]),
        "unclassified": sorted(k for k, v in actual.items() if v == POLICY_OBSERVE),
    }


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="P2-1 入口中间件：路由清单与状态")
    ap.add_argument("--snapshot", action="store_true", help="重新生成 webui/middleware_routes.json")
    ap.add_argument("--show", action="store_true", help="打印冻结清单与运行时开关")
    args = ap.parse_args(argv)

    if args.snapshot:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if here not in os.sys.path:
            os.sys.path.insert(0, here)
        os.chdir(here)
        import server  # noqa: F401  (只为拿 app.routes)
        data = snapshot_from_app(server.app)
        with open(ROUTES_JSON, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        print("已写 %s：%d 条路由" % (ROUTES_JSON, len(data)))
        return 0

    if args.show:
        data = load_route_manifest()
        counts: Dict[str, int] = {}
        for v in data.values():
            counts[v] = counts.get(v, 0) + 1
        print("冻结清单 %d 条：%s" % (len(data), sorted(counts.items())))
        print("运行时开关：", stats())
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
