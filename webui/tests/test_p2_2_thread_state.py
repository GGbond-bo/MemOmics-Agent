# -*- coding: utf-8 -*-
"""P2-2 显式 ThreadState 聚焦测试（2026-09-23）

覆盖四层：
  A. schema 冻结——server.py 里用到的会话键必须全部在册（AST 漂移门禁 + 运行时真会话校验）
  B. ThreadState 单元——回合记账、冲突检测、上限、有界、fail-open、等待
  C. 门面 + 真实 server——审计接口暴露 threads、真会话 sid 能记账
  D. 极端验收——两会话交错 500 轮零串扰（含 4 线程真并发，barrier 保证重叠）
  E. 边界——脏 sid、注册表淘汰、万级回合、重置
  F. 串行化门（P2-2 补丁）——MEMOMICS_THREAD_SERIALIZE=1 时同会话回合真串行：conflicts 归零，
     含原子性（TOCTOU）、超时 fail-open、僵尸租约自愈、/ws 入口真实调用顺序

纪律：所有测试都是 offline（本地 server + TestClient），不联网、不调用真实模型。
关键坑：测试绝对不能自己 import thread_state——那会拿到**另一个模块对象**，
注册表是另一份，什么都测不到。统一用 server._thread_state。
"""
import ast
import asyncio
import os
import sys
import threading
import time
import uuid

import pytest

from conftest import cleanup_session
import server

TS = server._thread_state           # 与 server 共享同一个模块对象
SRV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server.py")


# ------------------------------------------------------------------ 工具
_SESSION_BASE_NAMES = {"session", "s", "_session", "_s", "sess", "sess_dict", "state"}
_GETTERS = {"get", "pop", "setdefault"}


def _ast_session_keys():
    """扫 server.py：会话字典上被字面量访问过的键（体检同一口径，含 .get/.pop/.setdefault）。"""
    with open(SRV, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    keys = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id in _SESSION_BASE_NAMES
                and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)):
            keys.add(node.slice.value)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in _GETTERS and isinstance(node.func.value, ast.Name)
              and node.func.value.id in _SESSION_BASE_NAMES and node.args):
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                keys.add(a0.value)
    return keys


def _get_audit(client):
    r = client.get("/api/middleware/audit")
    assert r.status_code == 200
    return r.json()


# ============================================================ A. schema 冻结
def test_a1_module_installed_in_server():
    assert server._THREAD_STATE_INSTALLED is True, "server.py 里 ThreadState 没挂上"
    assert TS is not None and TS.VERSION.startswith("p2-2")
    assert callable(TS.mark_turn_start) and callable(TS.mark_turn_end)


def test_a2_schema_shape():
    st = TS.schema_stats()
    assert st["keys"] >= 90, st
    assert set(st["groups"].keys()) <= set(TS.GROUPS.keys())
    assert TS.SESSION_STATE_SCHEMA, "schema 空了就等于没定义"
    assert all(isinstance(k, str) and k for k in TS.SESSION_STATE_SCHEMA)
    assert all(v in TS.GROUPS for v in TS.SESSION_STATE_SCHEMA.values())
    # 决定性的那几组必须在册
    assert TS.SESSION_STATE_SCHEMA["messages"] == "persist"
    assert TS.SESSION_STATE_SCHEMA["_user_turn_active"] == "turn"
    assert TS.SESSION_STATE_SCHEMA["agent"] == "llm"
    assert TS.SESSION_STATE_SCHEMA["results_dir"] == "domain"


def test_a3_ast_drift_gate():
    """漂移门禁：源码里新加一个会话键却没登记 → 这里失败（和 P2-1 路由清单同一个套路）。"""
    used = _ast_session_keys()
    missing = sorted(k for k in used if k not in TS.SESSION_STATE_SCHEMA)
    assert not missing, "server.py 用到但未登记的会话键：%s" % missing
    assert len(used) >= 80, "扫描命中 %d 个键，口径疑似失效" % len(used)


def test_a4_runtime_sessions_are_registered(client, new_session):
    """运行时真值：真会话字典上的键必须全部在册（比 AST 更硬）。"""
    sid = new_session
    for path in ("/api/sessions/%s/messages" % sid, "/api/sessions/%s/outline" % sid,
                 "/api/sessions/%s/goal" % sid, "/api/sessions/%s/changes" % sid,
                 "/api/sessions/%s/progress" % sid, "/api/sessions/%s/citations" % sid,
                 "/api/todos/%s" % sid):
        client.get(path)
    sess = server._sessions[sid]
    chk = TS.check_schema(sess)
    assert chk["ok"], "未登记的会话键：%s" % chk["unknown"]
    assert chk["total"] >= 10, chk
    assert set(chk["by_group"]) <= set(TS.GROUPS.keys())


# ========================================================= B. ThreadState 单元
def test_b1_begin_end_accounting():
    st = TS.ThreadState("unit-b1")
    assert st.busy() is False and st.active_count() == 0
    rec = st.begin_turn("user")
    assert rec is not None and st.busy() is True and st.active_count() == 1
    el = st.end_turn(rec.turn_id)
    assert isinstance(el, float) and el >= 0.0
    assert st.busy() is False and st.total_turns == 1 and st.conflicts == 0


def test_b2_turn_ids_unique_and_ordered():
    st = TS.ThreadState("unit-b2")
    ids = []
    for _ in range(50):
        r = st.begin_turn()
        ids.append(r.turn_id)
        st.end_turn(r.turn_id)
    assert len(set(ids)) == 50
    assert [int(i.split("#")[1]) for i in ids] == list(range(1, 51))


def test_b3_end_edge_cases():
    st = TS.ThreadState("unit-b3")
    assert st.end_turn() is None                       # 没有活跃回合
    r1 = st.begin_turn()
    assert st.end_turn("不存在的-id") is not None       # 过期 id → 结束最早的
    assert st.active_count() == 0
    assert st.end_turn(r1.turn_id) is None             # 已经结束了，再结束返回 None


def test_b4_conflict_detection_same_sid_only():
    st = TS.ThreadState("unit-b4")
    a = st.begin_turn("user")
    b = st.begin_turn("wakeup")                        # 同一会话第二个回合 → 冲突
    assert st.conflicts == 1
    lc = st.snapshot()["last_conflict"]
    assert lc and lc["active_turn"] == a.turn_id and lc["new_turn"] == b.turn_id
    assert lc["active_source"] == "user" and lc["sids"] == "unit-b4"
    st.end_turn(a.turn_id)
    st.end_turn(b.turn_id)
    assert st.conflicts == 1                           # 不同会话互不干扰
    other = TS.ThreadState("unit-b4-other")
    other.begin_turn()
    assert other.conflicts == 0


def test_b5_overflow_is_bounded():
    limit = TS.MAX_ACTIVE_PER_SESSION
    st = TS.ThreadState("unit-b5")
    for _ in range(limit + 7):
        st.begin_turn()
    assert st.active_count() == limit
    assert st.overflows == 7
    assert st.total_turns == limit + 7


def test_b6_recent_ring_bounded():
    st = TS.ThreadState("unit-b6")
    for _ in range(TS.MAX_RECENT_TURNS * 3):
        r = st.begin_turn()
        st.end_turn(r.turn_id)
    assert len(st._recent) == TS.MAX_RECENT_TURNS


def test_b7_registry_get_is_idempotent():
    reg = TS.ThreadRegistry()
    s1 = reg.get("sid-x")
    s2 = reg.get("sid-x")
    assert s1 is s2
    assert reg.keys() == ["sid-x"]
    assert reg.drop("sid-x") is True
    assert reg.drop("sid-x") is False
    assert reg.get("sid-x") is not s1                  # 掉了就是新对象


def test_b8_registry_evicts_oldest():
    reg = TS.ThreadRegistry(max_sessions=3)
    for i in range(3):
        st = reg.get("sid-%d" % i)
        r = st.begin_turn()                            # 让 _last_turn_at 有值，淘汰按最近活跃
        st.end_turn(r.turn_id)
        time.sleep(0.002)
    reg.get("sid-9")
    assert reg.stats()["sessions"] == 3
    assert reg.evicted == 1


def test_b9_fail_open_on_dirty_sids():
    assert TS.mark_turn_start(None) is None
    assert TS.mark_turn_start("") is None
    assert TS.mark_turn_start(0) is None
    assert TS.mark_turn_end(None) is None
    assert TS.turn_active(None) is False

    class Boom(object):
        def __str__(self):
            raise RuntimeError("boom")

        def __bool__(self):
            return True

    assert TS.mark_turn_start(Boom()) is None          # 异常必须被吞掉
    assert TS.turn_active(Boom()) is False
    assert TS.check_schema(Boom())["ok"] is True        # 非字典 → 安全返回
    assert TS.check_schema(None)["unknown"] == []


def test_b10_long_and_unicode_sid_truncated():
    ts = TS
    long_sid = "x" * 5000
    tid = ts.mark_turn_start(long_sid)
    assert tid is not None
    assert len(tid.split("#")[0]) <= 256
    ts.mark_turn_end(long_sid)
    uni = "会话-\u4e2d\u6587-\u0000-\n"
    assert ts.mark_turn_start(uni) is not None
    assert ts.mark_turn_end(uni) is not None


def test_b11_wait_for_idle():
    st = TS.ThreadState("unit-b11")
    assert st.wait_for_idle(0.01) is True              # 空闲 → 立刻 True
    rec = st.begin_turn()
    assert st.wait_for_idle(0.05) is False             # 忙 → 超时 False

    def _release():
        time.sleep(0.05)
        st.end_turn(rec.turn_id)

    th = threading.Thread(target=_release)
    th.start()
    t0 = time.time()
    assert st.wait_for_idle(2.0) is True               # 被另一个线程放行
    th.join()
    assert time.time() - t0 >= 0.03


# ==================================================== C. 门面 + 真实 server
@pytest.fixture()
def _flag_guard():
    """跑完恢复门面开关与环境变量，别把状态漏给别的测试。"""
    saved = (TS.enabled(), os.environ.get("MEMOMICS_THREAD_STATE"),
             os.environ.get("MEMOMICS_THREAD_SERIALIZE"))
    yield
    TS.set_enabled(saved[0])
    for k, v in (("MEMOMICS_THREAD_STATE", saved[1]), ("MEMOMICS_THREAD_SERIALIZE", saved[2])):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_c1_enabled_switch(_flag_guard):
    assert TS.enabled() is True
    TS.set_enabled(False)
    assert TS.enabled() is False
    assert TS.mark_turn_start("unit-c1") is None       # 关掉就彻底不记账
    TS.set_enabled(True)
    os.environ["MEMOMICS_THREAD_STATE"] = "0"
    assert TS.enabled() is False
    os.environ.pop("MEMOMICS_THREAD_STATE")
    assert TS.enabled() is True


def test_c2_serialize_flag(_flag_guard):
    os.environ.pop("MEMOMICS_THREAD_SERIALIZE", None)
    assert TS.should_serialize() is False
    os.environ["MEMOMICS_THREAD_SERIALIZE"] = "1"
    assert TS.should_serialize() is True
    assert TS.serialize_timeout() > 0


def test_c3_audit_endpoint_exposes_threads(client):
    body = _get_audit(client)
    assert "threads" in body
    th = body["threads"]
    for key in ("enabled", "sessions", "busy_sessions", "active_turns", "total_turns",
                "conflicts", "overflows", "evicted", "serialize", "schema", "worst"):
        assert key in th, "threads 缺字段 %s" % key
    assert th["schema"]["keys"] == len(TS.SESSION_STATE_SCHEMA)
    assert isinstance(th["worst"], list)


def test_c4_real_sid_bookkeeping_visible_in_audit(client, new_session):
    sid = new_session
    TS.reset()
    try:
        tid = TS.mark_turn_start(sid, source="user")
        assert tid is not None and tid.startswith(sid)
        th = _get_audit(client)["threads"]
        assert th["active_turns"] >= 1 and th["busy_sessions"] >= 1
        assert TS.mark_turn_end(sid, tid) is not None
        th = _get_audit(client)["threads"]
        assert th["total_turns"] >= 1 and th["active_turns"] == 0
    finally:
        TS.reset()


# ================================================= D. 极端验收：交错零串扰
def _turn(sid, tag, sess):
    """一个"回合"：记账 + 往该会话写一条消息（复刻真实回合的状态写入面）。"""
    tid = TS.mark_turn_start(sid, source="user")
    sess["messages"].append({"role": "user", "content": tag,
                             "time": "00:00:00", "sid_tag": sid})
    sess["_turn_count"] = int(sess.get("_turn_count", 0)) + 1
    TS.mark_turn_end(sid, tid)
    return tid


def test_d1_two_sessions_500_interleaved_turns(client, new_session):
    """验收主项：两个真会话交错 500 轮，零串扰。"""
    a, b = new_session, None
    r = client.post("/api/sessions/new", params={"title": "pytest-串扰-B-%s" % uuid.uuid4().hex[:6]})
    assert r.status_code == 200
    b = r.json()["id"]
    try:
        sa, sb = server._sessions[a], server._sessions[b]
        assert sa is not sb
        sa["agent"], sb["agent"] = "agent-A", "agent-B"      # 身份哨兵
        rd_a, rd_b = sa.get("results_dir"), sb.get("results_dir")
        n = 250
        for i in range(n):
            _turn(a, "A-%03d" % i, sa)
            _turn(b, "B-%03d" % i, sb)
        # 1) 条数精确
        assert sa["_turn_count"] == n and sb["_turn_count"] == n
        # 2) 内容零串扰
        assert [m["content"] for m in sa["messages"]] == ["A-%03d" % i for i in range(n)]
        assert [m["content"] for m in sb["messages"]] == ["B-%03d" % i for i in range(n)]
        assert all(m["sid_tag"] == a for m in sa["messages"])
        assert all(m["sid_tag"] == b for m in sb["messages"])
        # 3) 身份/产物目录没被换
        assert sa["agent"] == "agent-A" and sb["agent"] == "agent-B"
        assert sa.get("results_dir") == rd_a and sb.get("results_dir") == rd_b
        assert sa["id"] == a and sb["id"] == b
        # 4) 记账正确且无冲突（交错 = 串行，不该有重叠）
        st = TS.stats()
        assert st["total_turns"] >= 2 * n
        assert st["conflicts"] == 0, "串行交错竟然记到冲突：%s" % st["worst"]
        sa["agent"] = sb["agent"] = None                     # 别把哨兵留给别的测试
    finally:
        cleanup_session(b)


def test_d2_same_session_true_concurrency_zero_crosstalk(client, new_session):
    """4 线程真并发（barrier 保证重叠）：跨会话零串扰 + 同会话重叠被记账暴露。"""
    a = new_session
    r = client.post("/api/sessions/new", params={"title": "pytest-并发-B-%s" % uuid.uuid4().hex[:6]})
    assert r.status_code == 200
    b = r.json()["id"]
    try:
        sa, sb = server._sessions[a], server._sessions[b]
        per_thread = 125
        n_threads = 4
        barrier = threading.Barrier(n_threads)
        # 每个会话一对线程，首回合用 pair barrier 卡住 → 保证两回合**真的重叠**
        # （首版没卡，单回合只有微秒级，靠概率撞重叠 → 冲突计数偶发为 0，测试不稳）
        pair = {a: threading.Barrier(2), b: threading.Barrier(2)}
        errors = []
        overlapped = []

        def worker(sid, sess, tag):
            try:
                barrier.wait(timeout=10)
                for i in range(per_thread):
                    tid = TS.mark_turn_start(sid, source="user")
                    if i == 0:
                        pair[sid].wait(timeout=10)     # 两个同会话回合同时在场
                        overlapped.append(len(TS.get_state(sid).snapshot()["active"]))
                    sess["messages"].append({"role": "user", "content": "%s-%03d" % (tag, i),
                                             "time": "00:00:00", "sid_tag": sid})
                    TS.mark_turn_end(sid, tid)
            except Exception as exc:      # pragma: no cover
                errors.append(repr(exc))

        ths = [threading.Thread(target=worker, args=(a, sa, "A")),
               threading.Thread(target=worker, args=(a, sa, "A2")),
               threading.Thread(target=worker, args=(b, sb, "B")),
               threading.Thread(target=worker, args=(b, sb, "B2"))]
        for t in ths:
            t.start()
        for t in ths:
            t.join(timeout=60)
        assert not errors, errors
        # 零串扰：每个会话只收到自己的条目，条数精确
        assert len(sa["messages"]) == 2 * per_thread
        assert len(sb["messages"]) == 2 * per_thread
        assert {m["sid_tag"] for m in sa["messages"]} == {a}
        assert {m["sid_tag"] for m in sb["messages"]} == {b}
        assert sorted(m["content"] for m in sa["messages"]) == sorted(
            ["A-%03d" % i for i in range(per_thread)] + ["A2-%03d" % i for i in range(per_thread)])
        # 同会话两线程必然重叠 → 记账必须看见（这就是 P2-2 要暴露的那个洞）
        # 重叠由 pair barrier 结构性保证（X 不进 barrier 就结束不了，Y 必须先 start 才进 barrier）；
        # 这里的采样只作旁证——先跑完的那条线程可能已经把回合结束了，所以看最大值而不是最小值。
        assert max(overlapped) >= 2, "重叠没造出来，测试失去意义：%s" % overlapped
        st_a = TS.get_state(a).snapshot()
        st_b = TS.get_state(b).snapshot()
        assert st_a["conflicts"] >= 1, "同会话并发没被发现？"
        assert st_b["conflicts"] >= 1
        assert st_a["total_turns"] == 2 * per_thread
        assert st_a["last_conflict"]["sids"] == a
    finally:
        cleanup_session(b)


# ============================================================== E. 边界
def test_e1_many_threads_many_sids():
    n_threads, per_thread = 20, 200
    TS.reset()
    errors = []

    def worker(idx):
        try:
            sid = "load-%02d" % idx
            for _ in range(per_thread):
                tid = TS.mark_turn_start(sid)
                TS.mark_turn_end(sid, tid)
        except Exception as exc:      # pragma: no cover
            errors.append(repr(exc))

    ths = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(timeout=60)
    assert not errors, errors
    st = TS.stats()
    assert st["sessions"] == n_threads
    assert st["total_turns"] == n_threads * per_thread
    assert st["conflicts"] == 0 and st["overflows"] == 0
    TS.reset()


def test_e2_ten_thousand_turns_no_growth():
    TS.reset()
    st = TS.ThreadState("unit-e2")
    ids = set()
    for _ in range(10000):
        r = st.begin_turn()
        ids.add(r.turn_id)
        st.end_turn(r.turn_id)
    assert len(ids) == 10000
    assert st.active_count() == 0
    assert len(st._recent) == TS.MAX_RECENT_TURNS       # 长跑不涨内存
    assert st.total_turns == 10000
    TS.reset()


def test_e3_stats_after_reset_is_clean():
    TS.reset()
    st = TS.stats()
    assert st["sessions"] == 0 and st["active_turns"] == 0
    assert st["conflicts"] == 0 and st["total_turns"] == 0
    assert st["schema"]["keys"] == len(TS.SESSION_STATE_SCHEMA)
    assert TS.get_state("never-touched") is not None    # get 是惰性创建
    TS.reset()
    assert TS.stats()["sessions"] == 0


def test_e4_check_schema_reports_unknown():
    chk = TS.check_schema({"messages": [], "完全不认识的键": 1, 42: "非字符串键不算"})
    assert chk["ok"] is False
    assert chk["unknown"] == ["完全不认识的键"]
    assert chk["total"] == 2                            # 非字符串键被忽略


# ==================================================== F. 串行化门（P2-2 补丁）
class _StubAgent:
    """最小 agent stub：让 /ws 回合能走到记账点，不联网、不调真实模型。"""
    _interrupt_requested = False
    _pending_steer_lock = None
    _steer_lock = None

    def __init__(self):
        self._pending_steer = []

    def clear_interrupt(self):
        self._interrupt_requested = False

    def run_conversation(self, *a, **k):
        return "stub-ok"

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


def test_f1_gate_is_free_when_off(_flag_guard):
    """串行化关着时：立刻放行、不碰注册表——默认路径零开销、零行为变更。"""
    os.environ.pop("MEMOMICS_THREAD_SERIALIZE", None)
    TS.reset()
    assert asyncio.run(TS.wait_turn_idle("f1-sid")) is True
    assert TS.stats()["sessions"] == 0, "关着的时候不该创建任何会话账目"
    # 关着的时候 begin_turn_serialized 就该等价于 mark_turn_start
    tid = asyncio.run(TS.begin_turn_serialized("f1-sid", source="user"))
    assert tid is not None and tid.startswith("f1-sid")
    assert TS.stats()["sessions"] == 1
    assert TS.stats()["serialized_waits"] == 0
    TS.mark_turn_end("f1-sid", tid)
    TS.reset()


def test_f2_gate_waits_for_previous_turn(_flag_guard):
    """开门后：上一个回合没结束，新回合就得等；等到才记账 → conflicts 为 0。"""
    os.environ["MEMOMICS_THREAD_SERIALIZE"] = "1"
    TS.reset()
    sid = "f2-sid"
    tid0 = TS.mark_turn_start(sid)
    releases = []

    def release_later():
        time.sleep(0.25)
        releases.append(TS.mark_turn_end(sid, tid0))

    th = threading.Thread(target=release_later)
    th.start()
    t0 = time.time()
    assert asyncio.run(TS.wait_turn_idle(sid, timeout=5.0)) is True
    elapsed = time.time() - t0
    th.join(timeout=5)
    assert elapsed >= 0.2, "没等就放行了：%.3fs" % elapsed
    assert not TS.turn_active(sid)
    st = TS.get_state(sid).snapshot()
    assert st["serialized_waits"] == 1
    assert st["wait_timeouts"] == 0
    assert st["conflicts"] == 0
    TS.reset()


def test_f3_concurrent_gated_entries_never_conflict(_flag_guard):
    """极端：8 个线程同时抢同一会话的回合入口（都走门）→ 真串行、conflicts 恒为 0。

    这是"门必须原子"的验收：如果空闲判定和记账之间有 TOCTOU 缝隙，这里会漏出 conflicts。
    """
    os.environ["MEMOMICS_THREAD_SERIALIZE"] = "1"
    TS.reset()
    sid = "f3-sid"
    n = 8
    errors = []
    barrier = threading.Barrier(n)

    def worker():
        try:
            barrier.wait(timeout=10)
            tid = asyncio.run(TS.begin_turn_serialized(sid, timeout=20.0, poll=0.01))
            assert tid, "门没给出回合 id"
            time.sleep(0.02)                    # 模拟"回合在干活"
            TS.mark_turn_end(sid, tid)
        except Exception as exc:                # pragma: no cover
            errors.append(repr(exc))

    ths = [threading.Thread(target=worker) for _ in range(n)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(timeout=60)
    assert not errors, errors
    st = TS.get_state(sid).snapshot()
    assert st["total_turns"] == n
    assert st["conflicts"] == 0, "门上方的并发仍然踩了：%s" % st["last_conflict"]
    assert st["active"] == []
    assert st["overflows"] == 0
    assert st["serialized_waits"] >= 1, "8 个并发至少该有一个真的等过"
    TS.reset()


def test_f4_timeout_is_fail_open_and_honest(_flag_guard):
    """等到超时 → 记 wait_timeouts、按原行为放行（fail-open），并把这次冲突如实记下来。"""
    os.environ["MEMOMICS_THREAD_SERIALIZE"] = "1"
    TS.reset()
    sid = "f4-sid"
    tid0 = TS.mark_turn_start(sid)
    tid1 = asyncio.run(TS.begin_turn_serialized(sid, timeout=0.15, poll=0.02))
    assert tid1 is not None, "超时必须放行，不能把用户消息卡死"
    st = TS.get_state(sid).snapshot()
    assert st["wait_timeouts"] == 1
    assert st["conflicts"] == 1, "fail-open 放行后的重叠必须如实记账"
    TS.mark_turn_end(sid, tid1)
    TS.mark_turn_end(sid, tid0)
    TS.reset()


def test_f5_stale_lease_self_heals(_flag_guard):
    """僵尸回合（线程被强杀/连接异常退出留下占位）超过阈值 → 清掉放行，不会永久卡死会话。"""
    os.environ["MEMOMICS_THREAD_SERIALIZE"] = "1"
    TS.reset()
    sid = "f5-sid"
    tid0 = TS.mark_turn_start(sid)
    st = TS.get_state(sid)
    rec = st._active[tid0]
    rec.started_at -= (TS.DEFAULT_STALE_TURN_S + 600)      # 伪造成两小时前的僵尸
    t0 = time.time()
    tid1 = asyncio.run(TS.begin_turn_serialized(sid, timeout=2.0, poll=0.02))
    assert tid1 is not None
    assert time.time() - t0 < 1.0, "僵尸租约没被清掉，会话被卡死了"
    snap = st.snapshot()
    assert snap["stale_dropped"] == 1
    assert snap["conflicts"] == 0
    TS.mark_turn_end(sid, tid1)
    TS.reset()


def test_f6_gate_disabled_module_is_free(_flag_guard):
    """整体关掉 MEMOMICS_THREAD_STATE=0 → 门也必须立刻放行（fail-open 到"没这个模块"）。"""
    os.environ["MEMOMICS_THREAD_SERIALIZE"] = "1"
    TS.set_enabled(False)
    os.environ["MEMOMICS_THREAD_STATE"] = "0"
    TS.reset()
    tid = asyncio.run(TS.begin_turn_serialized("f6-sid"))
    assert tid is None                       # 关掉就彻底不记账
    assert TS.stats()["sessions"] == 0
    TS.set_enabled(True)
    os.environ.pop("MEMOMICS_THREAD_STATE")
    TS.reset()


def test_f8_without_gate_the_hole_is_real(_flag_guard):
    """A/B 的 A 面：关掉串行化（= P2-2 之前的现有行为）→ 并发入口必然踩车。

    这条是 f3 的对照组，证明 f3 的 conflicts==0 是"门"挣来的，不是测试本身造不出重叠。
    """
    os.environ.pop("MEMOMICS_THREAD_SERIALIZE", None)
    TS.reset()
    sid = "f8-sid"
    n = 8
    barrier = threading.Barrier(n)
    errors = []

    def worker():                               # 完全走老路径：直接记账，没有门
        try:
            barrier.wait(timeout=10)
            tid = TS.mark_turn_start(sid)
            time.sleep(0.03)
            TS.mark_turn_end(sid, tid)
        except Exception as exc:                # pragma: no cover
            errors.append(repr(exc))

    ths = [threading.Thread(target=worker) for _ in range(n)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(timeout=60)
    assert not errors, errors
    st = TS.get_state(sid).snapshot()
    assert st["total_turns"] == n
    assert st["conflicts"] >= 1, "对照组没踩车，说明这个测试造不出重叠，f3 的结论不成立"
    assert st["serialized_waits"] == 0
    TS.reset()


def test_f7_ws_entry_calls_gate_before_accounting(client, new_session, monkeypatch, _flag_guard):
    """真 /ws 入口必须过门，且**先过门后记账**（顺序错了就等于没串行化）。"""
    sid = new_session
    os.environ["MEMOMICS_THREAD_SERIALIZE"] = "1"
    TS.reset()
    calls = []
    real_gate, real_start = TS.begin_turn_serialized, TS.mark_turn_start

    async def spy_gate(s, source="user", **kw):
        calls.append(("gate", s, source))
        return await real_gate(s, source, **kw)

    def spy_start(s, source="user"):
        calls.append(("start", s, source))
        return real_start(s, source)

    monkeypatch.setattr(TS, "begin_turn_serialized", spy_gate)
    monkeypatch.setattr(TS, "mark_turn_start", spy_start)
    monkeypatch.setattr(server, "_create_agent", lambda *a, **k: _StubAgent())
    try:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "switch_session", "session_id": sid})
            ws.send_json({"type": "chat", "message": "你好", "session_id": sid})
            deadline = time.time() + 20
            while time.time() < deadline and not calls:
                time.sleep(0.05)
        assert calls, "真 /ws 回合没有调用串行化门"
        assert calls[0][0] == "gate" and calls[0][1] == sid, calls
        snap = TS.get_state(sid).snapshot()
        assert snap["total_turns"] >= 1, "记账没落在真会话上"
        assert snap["conflicts"] == 0
    finally:
        cleanup_session(sid)
