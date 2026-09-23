# -*- coding: utf-8 -*-
"""P2-1 回归：入口侧中间件链（纯 ASGI，默认只观察不拦截）。

覆盖五层：
A 纯函数（路由归类、会话号提取、request_id 清洗、限流、审计环、裁剪）
B 链行为（小应用：请求头、会话守卫 404、限流 429、异常信封、流式、WebSocket、lifespan）
C 与真实 server 对拍（逐字节 A/B 等价、守卫 404 与处理函数 404 同字节、冻结路由清单）
D 接口（GET /api/middleware/audit 只读状态 + 漂移报告）
E 极端输入（超长路径、脏请求头、非法配置、穿样式会话号、并发）

为什么要有 A/B：接链的第一原则是「默认行为一个字都不变」，所以同一条请求
关链 / 开链两次的 status + body 字节 + 头（去掉 x-request-id）必须完全相同。
"""
import contextlib
import os
import threading

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

import server

# server.py 用 from webui import entry_middleware 挂的链；必须拿同一个模块对象，
# 换个名字 import 会得到第二份全局状态，开关就拨不动了。
mw = server._entry_mw
assert mw is not None, "server 没挂上入口中间件"


@contextlib.contextmanager
def chain(enabled=True, **env):
    """临时开关链与相关环境变量，退出时一律复原（含限流桶）。"""
    old_enabled = mw.enabled()
    old_env = {k: os.environ.get(k) for k in env}
    mw.set_enabled(enabled)
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = str(v)
    try:
        yield
    finally:
        mw.set_enabled(old_enabled)
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        mw.reset_rate_limit()


def _scope(path, method="GET", headers=None, query="", client=("127.0.0.1", 5000)):
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": (query or "").encode(),
        "headers": headers or [],
        "client": client,
    }


def _snapshot(resp):
    """状态码 + body 字节 + 头（去掉每次不同的 request id）。"""
    headers = sorted((k.lower(), v) for k, v in resp.headers.items() if k.lower() != "x-request-id")
    return resp.status_code, resp.content, headers


# --- A. 纯函数 --------------------------------------------------------------

@pytest.mark.parametrize("path,policy", [
    ("/", mw.POLICY_STATIC),
    ("/assets/app.js", mw.POLICY_STATIC),
    ("/uploads/x.png", mw.POLICY_STATIC),
    ("/openapi.json", mw.POLICY_STATIC),
    ("/docs", mw.POLICY_STATIC),
    ("/ws", mw.POLICY_WS),
    ("/api/version", mw.POLICY_PUBLIC),
    ("/api/health", mw.POLICY_PUBLIC),
    ("/api/kb/search", mw.POLICY_PUBLIC),
    ("/api/skills/catalog", mw.POLICY_PUBLIC),
    ("/api/file/open", mw.POLICY_LOCAL),
    ("/api/update/apply", mw.POLICY_LOCAL),
    ("/api/env/check", mw.POLICY_LOCAL),
    ("/api/sessions/abc/messages", mw.POLICY_SESSION),
    ("/api/results/abc/tree", mw.POLICY_SESSION),
    ("/api/todos/abc", mw.POLICY_SESSION),
    ("/api/enforcement/abc", mw.POLICY_SESSION),
])
def test_classify_matches_route_shapes(path, policy):
    assert mw.classify(path)[0] == policy


def test_classify_unknown_path_is_observe_not_deny():
    assert mw.classify("/nope")[0] == mw.POLICY_OBSERVE
    assert mw.classify("/api2/x")[0] == mw.POLICY_OBSERVE


def test_template_keeps_tail_and_hides_real_sid():
    policy, rule = mw.classify("/api/sessions/abc/messages")
    assert policy == mw.POLICY_SESSION
    tpl = mw._template_of(rule, "/api/sessions/abc/messages")
    assert tpl == "/api/sessions/{sid}/messages"
    assert "abc" not in tpl
    assert mw.extract_sid("/api/sessions/abc/messages", rule) == "abc"
    assert mw.extract_sid("/api/kb/search", "") is None


def test_new_context_generates_id_and_reads_header():
    ctx = mw.new_context(_scope("/api/version"))
    assert len(ctx.request_id) == 16 and ctx.request_id.isalnum()
    ctx2 = mw.new_context(_scope("/api/version", method="post",
                                 headers=[(b"x-request-id", b"trace-abc-123")]))
    assert ctx2.request_id == "trace-abc-123"
    assert ctx2.method == "POST"
    assert ctx2.client == "127.0.0.1"
    assert ctx2.policy == mw.POLICY_PUBLIC


def test_request_id_is_cleaned_and_capped():
    assert mw._clean_request_id("a b/c<d>") == "abcd"
    assert len(mw._clean_request_id("z" * 500)) == mw.MAX_REQUEST_ID


def test_rate_limit_hit_then_blocks_then_resets():
    mw.reset_rate_limit()
    ctx = mw.new_context(_scope("/api/ping"))
    assert [mw.rate_limit_hit(ctx, limit=3) for _ in range(3)] == [False, False, False]
    assert mw.rate_limit_hit(ctx, limit=3) is True
    mw.reset_rate_limit()
    assert mw.rate_limit_hit(ctx, limit=3) is False


def test_rate_limit_off_by_default_and_on_bad_config():
    with chain(True, MEMOMICS_MW_RATE_LIMIT=None):
        assert mw.rate_limit_per_minute() == 0
        assert mw.rate_limit_hit(mw.new_context(_scope("/api/ping"))) is False
    with chain(True, MEMOMICS_MW_RATE_LIMIT="abc"):
        assert mw.rate_limit_per_minute() == 0


def test_audit_ring_records_once_and_is_bounded():
    mw.reset_audit()
    ctx = mw.new_context(_scope("/api/version"))
    ctx.status = 200
    mw.record(ctx)
    mw.record(ctx)                      # 幂等：同一次请求只记一条
    assert mw.stats()["total"] == 1
    assert mw.recent(5)[0]["t"] == "/api/version"
    assert mw.recent(5)[0]["pol"] == mw.POLICY_PUBLIC
    for i in range(mw.MAX_AUDIT + 50):
        c = mw.new_context(_scope("/api/version"))
        c.status = 200
        mw.record(c)
    assert len(mw.recent(mw.MAX_AUDIT)) <= mw.MAX_AUDIT


def test_long_path_is_clipped_in_audit_record():
    ctx = mw.new_context(_scope("/api/" + "x" * 4000))
    ctx.status = 404
    rec = ctx.as_record()
    assert len(rec["t"]) <= mw.MAX_TEMPLATE_CHARS + 3


def test_policy_constants_all_have_rules_and_manifest_policies_are_known():
    used = {policy for _rule, policy, _mode in mw.ROUTE_RULES}
    for name in (mw.POLICY_STATIC, mw.POLICY_PUBLIC, mw.POLICY_SESSION, mw.POLICY_LOCAL, mw.POLICY_WS):
        assert name in used
    valid = used | {mw.POLICY_OBSERVE}
    assert set(mw.load_route_manifest().values()) <= valid


def test_session_enforce_list_is_session_scoped():
    for tpl in mw.SESSION_ENFORCE_PATHS:
        assert mw.classify(tpl)[0] == mw.POLICY_SESSION


# --- B. 链行为（独立小应用，不碰真实 server）-------------------------------

@pytest.fixture()
def tiny_app():
    app = FastAPI()

    @app.get("/api/ping")
    async def _ping():
        return {"ok": True}

    @app.get("/api/sessions/{sid}/messages")
    async def _msgs(sid: str):
        return {"sid": sid, "items": []}

    @app.post("/api/sessions/{sid}/messages")
    async def _post_msgs(sid: str):
        return {"posted": sid}

    @app.get("/api/results/{sid}")
    async def _res(sid: str):
        return {"sid": sid, "rows": []}

    @app.get("/api/big")
    async def _big():
        async def gen():
            for _ in range(64):
                yield b"x" * 4096
        return StreamingResponse(gen(), media_type="application/octet-stream")

    @app.post("/api/boom")
    async def _boom():
        raise RuntimeError("kaboom")

    @app.websocket("/ws")
    async def _ws(ws: WebSocket):
        await ws.accept()
        await ws.send_text("hi")
        await ws.close()

    prev = mw.session_exists_hook()
    mw.install(app, session_exists=lambda sid: sid == "known")
    try:
        yield app
    finally:
        mw.configure(session_exists=prev or (lambda sid: bool(sid) and sid in server._sessions))


def test_passes_through_and_stamps_request_id(tiny_app):
    with chain(True):
        c = TestClient(tiny_app)
        r = c.get("/api/ping")
        assert r.status_code == 200 and r.json() == {"ok": True}
        rid = r.headers.get("x-request-id")
        assert rid and len(rid) == 16
        r2 = c.get("/api/ping", headers={"X-Request-ID": "abc-def"})
        assert r2.headers.get("x-request-id") == "abc-def"


def test_disabled_chain_adds_nothing(tiny_app):
    with chain(False):
        r = TestClient(tiny_app).get("/api/ping")
        assert r.status_code == 200
        assert "x-request-id" not in r.headers


def test_session_guard_denies_unknown_only_when_enforced(tiny_app):
    c = TestClient(tiny_app)
    with chain(True, MEMOMICS_MW_SESSION_ENFORCE=None):
        r = c.get("/api/sessions/nope/messages")
        assert r.status_code == 200 and r.json()["sid"] == "nope"      # 默认只观察
    with chain(True, MEMOMICS_MW_SESSION_ENFORCE="1"):
        r = c.get("/api/sessions/nope/messages")
        assert r.status_code == 404
        assert r.json() == {"error": "Session not found"}
        assert r.content == mw._json_bytes(mw.SESSION_NOT_FOUND_BODY)  # 与处理函数同字节
        ok = c.get("/api/sessions/known/messages")
        assert ok.status_code == 200 and ok.json()["sid"] == "known"
        # 白名单之外的模板 / 非 GET：一律不拦
        assert c.get("/api/results/nope").status_code == 200
        assert c.post("/api/sessions/nope/messages").status_code == 200


def test_rate_limit_stage_returns_429(tiny_app):
    with chain(True, MEMOMICS_MW_RATE_LIMIT="2"):
        c = TestClient(tiny_app)
        assert c.get("/api/ping").status_code == 200
        assert c.get("/api/ping").status_code == 200
        r = c.get("/api/ping")
        assert r.status_code == 429
        assert r.json()["request_id"]
        assert r.headers.get("x-request-id")


def test_error_envelope_on_returns_json_500(tiny_app):
    with chain(True, MEMOMICS_MW_ERROR_ENVELOPE="1"):
        c = TestClient(tiny_app, raise_server_exceptions=False)
        r = c.post("/api/boom")
        assert r.status_code == 500
        body = r.json()
        assert body["error"] == "Internal Server Error" and body["request_id"]


def test_error_envelope_off_keeps_original_exception(tiny_app):
    with chain(True, MEMOMICS_MW_ERROR_ENVELOPE=None):
        c = TestClient(tiny_app)
        with pytest.raises(RuntimeError):
            c.post("/api/boom")


def test_streaming_body_is_not_buffered_or_truncated(tiny_app):
    with chain(True):
        c = TestClient(tiny_app)
        r = c.get("/api/big")
        assert r.status_code == 200
        assert len(r.content) == 64 * 4096
        recs = [it for it in mw.recent(50) if it["t"] == "/api/big"]
        assert recs and recs[0]["st"] == 200


def test_websocket_scope_passes_through(tiny_app):
    with chain(True):
        with TestClient(tiny_app).websocket_connect("/ws") as ws:
            assert ws.receive_text() == "hi"


def test_lifespan_events_pass_through():
    hits = []

    @contextlib.asynccontextmanager
    async def lifespan(app):
        hits.append("start")
        yield
        hits.append("stop")

    app = FastAPI(lifespan=lifespan)
    mw.install(app)
    with TestClient(app):
        assert hits == ["start"]
    assert hits == ["start", "stop"]


def test_audit_uses_template_not_real_sid(tiny_app):
    mw.reset_audit()
    with chain(True):
        TestClient(tiny_app).get("/api/sessions/known/messages")
    rec = mw.recent(10)[0]
    assert rec["t"] == "/api/sessions/{sid}/messages"
    assert "known" not in rec["t"]
    assert rec["sid"] == "known"


# --- C. 与真实 server 对拍 --------------------------------------------------

def test_chain_is_installed_exactly_once_on_real_app():
    assert server._MW_INSTALLED is True
    assert len(server.app.user_middleware) == 1
    assert server.app.user_middleware[0].cls is mw.EntryMiddleware
    assert server._entry_mw is mw


def test_frozen_route_manifest_matches_real_app():
    ra = mw.route_audit(server.app)
    assert ra["added"] == [], "新增路由没同步 webui/middleware_routes.json（跑 --snapshot）：%s" % ra["added"]
    assert ra["removed"] == [], "清单里有已删除的路由：%s" % ra["removed"]
    assert ra["reclassified"] == [], "归类变了：%s" % ra["reclassified"]
    assert ra["unclassified"] == [], "有路由没归类：%s" % ra["unclassified"]
    assert len(ra["actual"]) == len(ra["frozen"]) >= 120


def test_session_enforce_list_matches_handler_behaviour(client):
    """白名单里的每条路由，处理函数自己也要返回同样的 404（否则守卫会改变行为）。"""
    bad = []
    with chain(False):
        for tpl in mw.SESSION_ENFORCE_PATHS:
            path = tpl.replace("{sid}", "__no_such_session__")
            r = client.get(path)
            if r.status_code != 404 or r.json() != mw.SESSION_NOT_FOUND_BODY:
                bad.append((path, r.status_code, r.text[:60]))
    assert bad == [], "这些模板的处理函数并不是统一的会话 404，必须从白名单里去掉：%s" % bad


def test_guard_404_is_byte_identical_to_handler_404(client):
    path = "/api/sessions/__no_such_session__/messages"
    with chain(False):
        off = client.get(path)
    assert off.status_code == 404
    with chain(True, MEMOMICS_MW_SESSION_ENFORCE="1"):
        on = client.get(path)
    assert on.status_code == 404
    assert on.content == off.content
    assert on.headers.get("x-request-id")


def test_session_hook_covers_real_sessions(client):
    """注入的 hook 必须认得真实会话，否则开强制会误伤。"""
    r = client.get("/api/sessions")
    assert r.status_code == 200
    items = r.json()
    if isinstance(items, dict):
        items = items.get("sessions") or items.get("items") or []
    sids = [it.get("id") for it in items if isinstance(it, dict) and it.get("id")]
    hook = mw.session_exists_hook()
    assert hook is not None
    unknown = [s for s in sids[:8] if not hook(s)]
    assert unknown == [], "这些真实会话 hook 认不出来（开强制会误伤）：%s" % unknown


AB_PATHS = (
    "/api/version",
    "/api/health",
    "/api/sessions",
    "/api/results",
    "/api/memory",
    "/api/providers",
    "/api/ui/lang",
    "/api/skills/enabled/list",
    "/api/todos/__no_such_session__",
    "/api/sessions/__no_such_session__/messages",
    "/api/enforcement/__no_such_session__",
    "/api/nope",
    "/openapi.json",
    "/",
)


def test_ab_equivalence_chain_off_vs_on(client):
    """关链 / 开链的响应必须完全一致；不确定的接口只比状态码，且要有覆盖下限。"""
    compared, unstable = [], []
    for path in AB_PATHS:
        with chain(False):
            off = _snapshot(client.get(path))
        with chain(True):
            on1 = _snapshot(client.get(path))
            on2 = _snapshot(client.get(path))
        if on1 != on2:
            unstable.append(path)
            assert off[0] == on1[0], "%s 状态码在开链前后不一致" % path
            continue
        assert off == on1, "%s 开链前后响应不一致" % path
        compared.append(path)
    assert len(compared) >= 12, "逐字节对拍覆盖太少：%s（不稳定：%s）" % (compared, unstable)


def test_ab_equivalence_on_session_endpoints(client, new_session):
    sid = new_session
    for path in ("/api/sessions/%s/messages?limit=0" % sid,
                 "/api/sessions/%s/outline" % sid,
                 "/api/sessions/%s/goal" % sid,
                 "/api/todos/%s" % sid):
        with chain(False):
            off = client.get(path)
        with chain(True):
            on = client.get(path)
        assert off.status_code == on.status_code, path
        if off.status_code == 200:
            assert off.content == on.content, path


# --- D. 只读审计接口 --------------------------------------------------------

def test_audit_endpoint_reports_state_and_recent(client):
    with chain(True):
        client.get("/api/version")
        r = client.get("/api/middleware/audit", params={"limit": 50})
        assert r.status_code == 200
        data = r.json()
        assert data["installed"] is True and data["enabled"] is True
        assert data["stats"]["session_exists_hook"] is True
        assert any(it["t"] == "/api/version" and it["st"] == 200 for it in data["items"])
        assert all(len(it["t"]) <= mw.MAX_TEMPLATE_CHARS + 3 for it in data["items"])


def test_audit_endpoint_route_report_is_clean(client):
    r = client.get("/api/middleware/audit", params={"routes": 1})
    assert r.status_code == 200
    rep = r.json()["routes"]
    assert rep["added"] == [] and rep["removed"] == [] and rep["reclassified"] == []
    assert rep["unclassified"] == []
    assert rep["total"] == len(mw.load_route_manifest())


def test_audit_endpoint_limit_is_clamped(client):
    for limit in (0, -5, 1, 99999):
        r = client.get("/api/middleware/audit", params={"limit": limit})
        assert r.status_code == 200
        assert 1 <= len(r.json()["items"]) <= mw.MAX_AUDIT


# --- E. 极端输入 ------------------------------------------------------------

def test_extremely_long_path_does_not_crash(client):
    with chain(True):
        r = client.get("/api/" + "x" * 5000)
        assert r.status_code in (404, 414)
        assert r.headers.get("x-request-id")


def test_dirty_request_id_header_is_sanitized(client):
    dirty = "<script>alert(1)</script> " + "a" * 200
    with chain(True):
        r = client.get("/api/version", headers={"X-Request-ID": dirty})
        rid = r.headers.get("x-request-id")
        assert rid and len(rid) <= mw.MAX_REQUEST_ID
        assert all(c.isalnum() or c in "-_" for c in rid)


def test_non_utf8_header_bytes_never_break_context():
    ctx = mw.new_context(_scope("/api/version", headers=[(b"x-request-id", b"\xff\xfe\x00abc")]))
    assert ctx.request_id and all(c.isalnum() or c in "-_" for c in ctx.request_id)


def test_traversal_like_sid_is_only_a_string():
    with chain(True, MEMOMICS_MW_SESSION_ENFORCE="1"):
        ctx = mw.new_context(_scope("/api/sessions/../messages"))
        assert ctx.policy == mw.POLICY_SESSION
        assert ctx.sid == ".."
        assert ctx.template == "/api/sessions/{sid}/messages"
        assert mw.session_guard(ctx) is not None      # 未知会话，拦


def test_query_with_chinese_and_huge_value(client):
    with chain(True):
        r = client.get("/api/nope", params={"q": "中文查询" * 200})
        assert r.status_code == 404
        assert r.headers.get("x-request-id")


def test_concurrent_requests_stay_consistent(client):
    errs, ids = [], []
    lock = threading.Lock()

    def worker():
        try:
            r = client.get("/api/version")
            with lock:
                ids.append(r.headers.get("x-request-id"))
            if r.status_code != 200:
                raise AssertionError(r.status_code)
        except Exception as exc:  # pragma: no cover - 只在真出问题时走到
            with lock:
                errs.append(repr(exc))

    with chain(True):
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert errs == []
    assert len(ids) == 10 and all(ids) and len(set(ids)) == 10


def test_counters_stay_sane_after_all_of_this(client):
    st = mw.stats()
    assert st["total"] >= 1
    assert st["enforced"] >= 0 and st["errors"] >= 0
    assert st["audit_size"] <= st["max_audit"]
    assert sum(n for _k, n in st["policies"]) == st["total"]
    assert sum(n for _k, n in st["statuses"]) == st["total"]
