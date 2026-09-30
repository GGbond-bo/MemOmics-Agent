# -*- coding: utf-8 -*-
"""P1-1 回归：会话目标条（goal）+ 待办持久化。

覆盖两类真实缺陷 + 一组新接口契约：

A. 待办刷新丢失（真实 bug）：四个 `todos_update` 推送点只发 WS 事件、不回写
   session["todos"]，刷新/切回会话走 /api/todos 拿到的是初始化时的 []。
   现在回写收口在 _session_emit（server.py 的 emit 唯一出口），本文件既测收口
   函数本身，也走 HTTP 端点断言"刷新后能读到"。

B. get_todos() 死分支（真实 bug）：原代码调 _agent.get_todos()，该方法在
   hermes-agent 全仓 grep 0 命中 → 恒为 []。现在真源是 _todo_store.read()。

C. 新接口：GET/PUT/DELETE /api/sessions/{sid}/goal + /progress 携带 goal/todos。
   语义抄 deer-flow：None = 没动它（保留旧值），[] = 显式清空。
"""
import json
import os
import uuid

import pytest

import server
from conftest import cleanup_session


def _cleanup_kv(sid):
    """清掉本测试写进 state.db kv 表的两行，保持生产库干净。"""
    server._kv_set(server._kv_ns("todos", sid), "")
    server._kv_set(server._kv_ns("goal", sid), "")


# --- A. 待办回写收口 -------------------------------------------------------

def test_sync_none_keeps_old_value_and_empty_clears():
    """deer-flow 语义：None=没动它（保留），[]=显式清空。"""
    sess = {"id": "p1_1_unit_" + uuid.uuid4().hex[:6], "todos": []}
    try:
        first = server._sync_session_todos(sess, [{"id": "t1", "title": "跑 QC", "status": "pending"}])
        assert [t["title"] for t in first] == ["跑 QC"]
        assert sess["todos_revision"] == 1

        # None：不动它
        kept = server._sync_session_todos(sess, None)
        assert [t["title"] for t in kept] == ["跑 QC"]
        assert sess["todos_revision"] == 1

        # []：显式清空
        server._sync_session_todos(sess, [])
        assert sess["todos"] == []
        assert sess["todos_revision"] == 2

        # 内容没变时不涨 revision（前端乐观对账靠它）
        server._sync_session_todos(sess, [])
        assert sess["todos_revision"] == 2
    finally:
        _cleanup_kv(sess["id"])


def test_emit_todos_update_writes_back_to_session():
    """核心回归：emit 一次 todos_update，session["todos"] 必须同步。"""
    sid = "p1_1_emit_" + uuid.uuid4().hex[:6]
    sess = {"id": sid, "todos": [], "progress_log": []}
    try:
        server._session_emit(sess, {
            "type": "todos_update",
            "todos": [{"id": "1", "title": "去双细胞", "status": "running", "module": "scRNA"},
                      {"content": "质控", "status": "pending"}],
        })
        assert [t["title"] for t in sess["todos"]] == ["去双细胞", "质控"]
        assert sess["todos"][1]["status"] == "pending"
        # content 字段被归一成 title（前端只认 title）
        assert sess["todos"][1]["title"] == "质控"
        assert sess["progress_log"][-1]["type"] == "todos_update"
    finally:
        _cleanup_kv(sid)


def test_emit_todos_without_payload_keeps_old():
    """只发事件不带 todos（todos=None）时不能把已有待办抹掉。"""
    sid = "p1_1_none_" + uuid.uuid4().hex[:6]
    sess = {"id": sid, "todos": [{"id": "1", "title": "已有待办", "status": "pending"}],
            "progress_log": []}
    try:
        server._session_emit(sess, {"type": "todos", "todos": None})
        assert [t["title"] for t in sess["todos"]] == ["已有待办"]
    finally:
        _cleanup_kv(sid)


def test_all_four_emit_shapes_sync(client, new_session):
    """四个真实推送点的载荷形状（debate / heartbeat / 裁决 / 管线）都能回写。"""
    sid = new_session
    sess = server._sessions[sid]
    shapes = [
        {"id": "a", "title": "辩论：设计对照", "status": "pending"},                       # debate
        {"title": "生成报告", "status": "completed"},                                       # heartbeat
        {"id": "c", "title": "裁决：通过", "status": "running", "module": "review"},        # 裁决
        {"id": "d", "title": "管线步骤 1", "status": "pending", "module": "pipeline", "skill": "x"},
    ]
    server._session_emit(sess, {"type": "todos_update", "todos": shapes})
    r = client.get(f"/api/todos/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert [t["title"] for t in body["todos"]] == [s["title"] for s in shapes]
    assert body["revision"] >= 1
    assert all(set(t) == {"id", "title", "status", "module"} for t in body["todos"])


def test_todos_survive_session_switch(client, new_session):
    """刷新/切会话场景：把内存态删掉后仍能从 state.db 读回。"""
    sid = new_session
    sess = server._sessions[sid]
    server._session_emit(sess, {"type": "todos_update",
                                "todos": [{"id": "1", "title": "持久化待办", "status": "pending"}]})
    # 模拟进程重启：内存态清空（kv 保留）
    sess.pop("todos", None)
    sess.pop("_todos_blob", None)
    got = server._session_todos(sess)
    assert [t["title"] for t in got] == ["持久化待办"], "刷新后待办必须能从 state.db 恢复"


# --- B. get_todos 死分支 ---------------------------------------------------

def test_get_todos_dead_branch_replaced():
    """server.py 里不该再出现不存在的 _agent.get_todos() 调用。"""
    import inspect
    lines = inspect.getsource(server).splitlines()
    # 只看可执行代码行（注释里解释历史 bug 时仍会提到这个名字）
    code = [l for l in lines if not l.lstrip().startswith("#")]
    assert not any("todos = _agent.get_todos()" in l for l in code), "死分支调用必须已移除"
    assert not any("hasattr(_agent, \"get_todos\")" in l for l in code)
    assert any("_todo_store.read()" in l for l in code), "必须改走真源 _todo_store.read()"


# --- C. 目标接口 -----------------------------------------------------------

def test_goal_crud_and_progress_payload(client, new_session):
    sid = new_session
    try:
        # 初始：没有目标
        r = client.get(f"/api/sessions/{sid}/goal")
        assert r.status_code == 200
        assert r.json()["goal"] is None

        # 设置
        r = client.put(f"/api/sessions/{sid}/goal",
                       json={"objective": "把这份 scRNA 数据从原始 counts 做到细胞注释"})
        assert r.status_code == 200, r.text
        goal = r.json()["goal"]
        for k in ("objective", "status", "source", "created_at", "updated_at", "revision"):
            assert k in goal, k
        assert goal["status"] == "active"
        assert goal["source"] == "manual"
        assert goal["revision"] == 1

        # 改状态 = 新 revision，created_at 不变
        r = client.put(f"/api/sessions/{sid}/goal",
                       json={"objective": goal["objective"], "status": "done"})
        assert r.status_code == 200
        g2 = r.json()["goal"]
        assert g2["status"] == "done" and g2["revision"] == 2
        assert g2["created_at"] == goal["created_at"]

        # progress 端点零额外请求带回 goal + todos
        r = client.get(f"/api/sessions/{sid}/progress")
        assert r.status_code == 200
        p = r.json()
        assert p["goal"]["objective"] == goal["objective"]
        assert isinstance(p["todos"], list)
        assert "todos_revision" in p
        # 老的键没被动过
        for k in ("progress_log", "reasoning_log", "partial_text", "is_running",
                  "last_tool", "session_id"):
            assert k in p, k

        # 清空
        r = client.delete(f"/api/sessions/{sid}/goal")
        assert r.status_code == 200
        assert r.json()["goal"] is None
        assert client.get(f"/api/sessions/{sid}/goal").json()["goal"] is None
    finally:
        _cleanup_kv(sid)


def test_goal_survives_restart(client, new_session):
    """目标落 state.db：内存清掉后 GET 仍能拿回（= 服务重启不丢）。"""
    sid = new_session
    try:
        client.put(f"/api/sessions/{sid}/goal", json={"objective": "重启后还应在的目标"})
        sess = server._sessions[sid]
        sess.pop("goal", None)            # 模拟进程重启：只留 state.db
        r = client.get(f"/api/sessions/{sid}/goal")
        assert r.status_code == 200
        assert r.json()["goal"]["objective"] == "重启后还应在的目标"
        assert server._sessions[sid]["goal"]["objective"] == "重启后还应在的目标"
    finally:
        _cleanup_kv(sid)


@pytest.mark.parametrize("payload,why", [
    ({"objective": ""}, "空目标"),
    ({"objective": "   "}, "只有空白"),
    ({"objective": "x" * (server._GOAL_MAX_LEN + 1)}, "超长"),
    ({"objective": "合法", "status": "whatever"}, "非法状态"),
])
def test_goal_invalid_input_400(client, new_session, payload, why):
    sid = new_session
    try:
        r = client.put(f"/api/sessions/{sid}/goal", json=payload)
        assert r.status_code == 400, f"{why} 应被拒绝: {r.text}"
    finally:
        _cleanup_kv(sid)


def test_goal_unknown_session_404(client):
    r = client.get("/api/sessions/does-not-exist-p1-1/goal")
    assert r.status_code == 404
    r = client.put("/api/sessions/does-not-exist-p1-1/goal", json={"objective": "x"})
    assert r.status_code == 404
    r = client.delete("/api/sessions/does-not-exist-p1-1/goal")
    assert r.status_code == 404


def test_goal_persisted_blob_is_valid_json(client, new_session):
    """落库内容必须是可解析 JSON（重启后 _goal_get 靠它还原）。"""
    sid = new_session
    try:
        client.put(f"/api/sessions/{sid}/goal", json={"objective": "落库检查"})
        raw = server._kv_get(server._kv_ns("goal", sid))
        parsed = json.loads(raw)
        assert parsed["objective"] == "落库检查"
    finally:
        _cleanup_kv(sid)

# --- C2. 清空待办（2026-09-24：用户问"待办结束之后怎么关掉"） ----------------

def test_delete_todos_endpoint_clears_and_broadcasts(client, new_session):
    """清空待办：HTTP 后 /api/todos 空、session 内存空、WS 广播一条 todos_update([])。"""
    sid = new_session
    try:
        sess = server._sessions[sid]
        server._session_emit(sess, {"type": "todos_update",
                                    "todos": [{"id": "1", "title": "跑 QC", "status": "completed"}]})
        assert [t["title"] for t in client.get(f"/api/todos/{sid}").json()["todos"]] == ["跑 QC"]
        rev_before = client.get(f"/api/todos/{sid}").json()["revision"]

        r = client.delete(f"/api/sessions/{sid}/todos")
        assert r.status_code == 200, r.text
        assert r.json()["todos"] == []
        assert client.get(f"/api/todos/{sid}").json()["todos"] == []
        assert sess["todos"] == []
        assert sess["todos_revision"] > rev_before, "清空也要涨 revision（前端靠它对账）"
        # 广播：目标条上的待办段靠这条事件关掉（不吃本地状态）
        last = sess["progress_log"][-1]
        assert last["type"] == "todos_update"
        assert last.get("todos") == []
    finally:
        _cleanup_kv(sid)


def test_delete_todos_keeps_goal(client, new_session):
    """两个 ✕ 各管各的：清待办不能顺手把目标也清了。"""
    sid = new_session
    try:
        client.put(f"/api/sessions/{sid}/goal", json={"objective": "别被清掉"})
        sess = server._sessions[sid]
        server._session_emit(sess, {"type": "todos_update", "todos": [{"id": "1", "title": "X"}]})
        assert client.delete(f"/api/sessions/{sid}/todos").status_code == 200
        assert client.get(f"/api/sessions/{sid}/goal").json()["goal"]["objective"] == "别被清掉"
    finally:
        _cleanup_kv(sid)


def test_delete_todos_unknown_session_404(client):
    r = client.delete("/api/sessions/does-not-exist-p1-1-todos/todos")
    assert r.status_code == 404


# --- D. 前端接线（静态守卫） -------------------------------------------------
# 这些断言很"浅"，但守的正是「后端有接口、前端没接」这类真空洞：
# P1 之前的引用/待办就出现过"数据在、上不了屏"。

_INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")


def _index_html():
    with open(_INDEX, encoding="utf-8") as f:
        return f.read()


def test_frontend_goal_bar_wired():
    html = _index_html()
    assert 'id="goal-bar"' in html, "目标条容器缺失"
    assert "function renderGoalBar" in html
    assert "function applyGoalPayload" in html
    # 目标条的待办必须复用同一份数据（WS todos_update 的唯一落点）
    assert "_goalBar.todos = Array.isArray(todos)" in html, "renderTodos 未同步目标条"
    # 三条来源都要接上：WS goal_update / /progress 兜底 / 面板刷新
    assert "msg.type === 'goal_update'" in html, "WS goal_update 分支缺失"
    assert "applyGoalPayload(d);" in html, "progress 兜底未恢复目标"
    # 请求路径必须与后端一致
    assert "'/api/sessions/' + currentSid + '/goal'" in html
    # 2026-09-24：待办段的关闭入口 + 宽度对齐输入框
    assert 'id="gb-clear-todos"' in html, "清空待办按钮缺失"
    assert "function clearTodos" in html, "清空待办未接线"
    assert "'/api/sessions/' + currentSid + '/todos'" in html, "清空待办请求路径与后端不一致"
    assert "function _syncGoalBarWidth" in html, "目标条宽度未对齐输入框"
    assert "autoDoneSig" in html, "全部完成后自动收起未实现"


# --- D. TodoStore.add() 死调用（真实 bug，2026-09-30） -------------------------
# 症状：界面上的待办完成一步也划不掉，一直挂在输入框上方不动。
# 根因：server.py 两处调 _agent._todo_store.add(...)，而 TodoStore 只有
#   write(merge=True) / read() / has_items() —— 没有 add()。抛出的 AttributeError 被
#   except 吞掉（只在 errors.log 留一行 auto-todos failed），于是待办只写进
#   session["_pipeline_todos"]、进不了 store；前端读 store 为空就回落到那份原始清单
#   （状态全是 pending），完成状态再也不会更新。
# 与 B 同类：调用了一个在后端根本不存在的方法。


def _todo_store_class():
    """加载真实的 TodoStore（todo_tool.py 只依赖 json/typing，可以单独加载）。"""
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "hermes-agent", "tools", "todo_tool.py")
    spec = importlib.util.spec_from_file_location("_memomics_todo_tool", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TodoStore


def test_should_emit_todos_pushes_the_clear():
    """空清单不是「没什么可推」—— 它是一次状态变化，必须推（否则页面挂着旧清单不动）。"""
    # 非空：一律推
    assert server._should_emit_todos([{"id": "1"}], None) is True
    assert server._should_emit_todos([{"id": "1"}], [{"id": "1"}]) is True
    # 空但之前有：这是「清空」，必须推 —— 这条就是这次修的
    assert server._should_emit_todos([], [{"id": "1"}]) is True
    assert server._should_emit_todos(None, [{"id": "1"}]) is True
    # 空且之前就空：没变化，不推（别每次工具调用都刷一遍）
    assert server._should_emit_todos([], []) is False
    assert server._should_emit_todos([], None) is False


def test_todos_emit_site_uses_should_emit_helper():
    """接线检查：推送点必须真的用上判定函数（别再退回 len(todos) > 0）。"""
    src = open(os.path.join(os.path.dirname(server.__file__), "server.py"), encoding="utf-8").read()
    assert "_should_emit_todos(todos, session.get(\"todos\"))" in src
    assert "if todos and len(todos) > 0:" not in src, "旧的 len(todos) > 0 判定又回来了"


def test_server_never_calls_todo_store_add():
    """server.py 里不许再出现 _todo_store.add( —— TodoStore 没有这个方法。"""
    import ast
    src = open(os.path.join(os.path.dirname(server.__file__), "server.py"), encoding="utf-8").read()
    # 用 AST 找真正的调用点：<x>._todo_store.add(...)。
    # 不用文本匹配 —— 注释和文档字符串里提到这个词不算调用（第一版就是这么误伤的）。
    bad = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add":
            continue
        val = node.func.value
        if isinstance(val, ast.Attribute) and val.attr == "_todo_store":
            bad.append(node.lineno)
    assert not bad, "又调 TodoStore.add() 了（该方法不存在），行号: %s" % bad


def test_todo_store_really_has_no_add():
    """钉住前提：TodoStore 没有 add()。哪天上游补上了，这条会失败并提示重写。"""
    store = _todo_store_class()()
    assert not hasattr(store, "add"), "TodoStore 现在有 add() 了？上面的结论要重写"
    for m in ("write", "read", "has_items"):
        assert hasattr(store, m), "TodoStore 缺 %s" % m


class _FakeAgent:
    """只要有 _todo_store 就够 —— _seed_agent_todos 只碰这一个属性。"""



def test_enforcement_report_exposes_debate_todos():
    """诊断字段：不暴露它，「这条裁决待办为什么卡着」就只能靠猜。"""
    from webui import enforcement
    sid = "test-enf-report-" + uuid.uuid4().hex[:8]
    es = enforcement.get_enforcement(sid)
    es.debate_todos = [
        {"id": "d1", "title": "第一步", "status": "pending", "blocks": ["terminal"]},
        {"id": "d2", "title": "第二步", "status": "completed"},
    ]
    rep = enforcement.get_enforcement_report(sid)
    assert [t["id"] for t in rep["debate_todos"]] == ["d1", "d2"]
    assert rep["debate_todos"][0]["status"] == "pending"
    assert rep["debate_todos"][1]["status"] == "completed"
    assert rep["debate_blocks_pending"] == 1, "只有 d1 既没完成又带硬约束"


def test_seed_agent_todos_treats_pending_as_no_opinion():
    """单调规则：源里写 pending = 没意见，不许把 store 里已完成的打回未完成。

    write(merge=True) 见到 status 就覆盖，所以「顺手补一个默认 pending」等于
    每次推清单都抹一次完成进度。新建条目不受影响（_validate 自己落 pending）。
    """
    a = _FakeAgent()
    a._todo_store = _todo_store_class()()
    a._todo_store.write([{"id": "01", "content": "第一步", "status": "completed"}], merge=True)
    server._seed_agent_todos(a, [{"id": "01", "title": "第一步", "status": "pending"}], "x")
    assert a._todo_store.read()[0]["status"] == "completed"
    # 反向仍然成立：明确说完成就必须写进去
    a._todo_store.write([{"id": "02", "content": "第二步", "status": "pending"}], merge=True)
    server._seed_agent_todos(a, [{"id": "02", "title": "第二步", "status": "completed"}], "x")
    assert [x["status"] for x in a._todo_store.read()] == ["completed", "completed"]


def test_debate_reseed_never_un_completes_a_todo():
    """用户 2026-09-30 报的那份 3 条全 ⬜ 的待办：裁决待办做完了也不划掉。

    真实链路：debate_analysis 跑完 → 把 es.debate_todos 写进 store。原来那句是
        write([{..., "status": "pending"} for t in _dt], merge=True)
    —— merge 见到 status 就覆盖，于是画火山图那轮每跑一次辩论，agent 勾掉的
    完成状态就被抹一次，怎么勾都是 ⬜。
    """
    a = _FakeAgent()
    a._todo_store = _todo_store_class()()
    debate = [
        {"id": "d1", "title": "在当前workspace检索旧柱子图/火山图脚本、R历史…", "status": "pending"},
        {"id": "d2", "title": "按临时参数生成5张火山的PNG/PDF/SVG…", "status": "pending"},
        {"id": "d3", "title": "不等证据齐：先产出可复核的中间结论…", "status": "pending"},
    ]
    server._seed_agent_todos(a, debate, "debate")  # 裁决第一次生成
    assert [x["status"] for x in a._todo_store.read()] == ["pending"] * 3
    # agent 做完了前两步
    a._todo_store.write([{"id": "d1", "status": "completed"},
                         {"id": "d2", "status": "completed"}], merge=True)
    # 之后再跑裁决：_dt 同步过（completed）和没同步过（还是 pending）两种都要扛住
    synced = [dict(t, status="completed" if t["id"] != "d3" else "pending") for t in debate]
    for src in (synced, debate):
        server._seed_agent_todos(a, src, "debate")
        got = {x["id"]: x["status"] for x in a._todo_store.read()}
        assert got == {"d1": "completed", "d2": "completed", "d3": "pending"}, got


def test_debate_todo_site_uses_seed_helper():
    """接线检查：裁决推送点必须走 _seed_agent_todos（别再手写 status）。"""
    src = open(os.path.join(os.path.dirname(server.__file__), "server.py"), encoding="utf-8").read()
    assert '_seed_agent_todos(_agent, _dt, "debate")' in src, "裁决待办推送点没接上助手"
    assert '"status": "pending"} for t in' not in src, "又有批量写入在硬写 pending 了"


def test_every_method_called_on_todo_store_exists():
    """泛化防线：server.py 里对 _todo_store 调的每个方法都必须真的存在。

    这次的 add() 是第三例同类事故（前两例：get_todos()、todo_manage 幻影工具名）。
    与其每次等用户报，不如把「调用了不存在的方法」变成一条会失败的测试。
    """
    import ast
    # 按实例取，不按类取：_items 是 __init__ 里挂的实例属性，
    # dir(cls) 看不到它（第一版就是这么误报的）。
    methods = {n for n in dir(_todo_store_class()()) if not n.startswith("__")}
    src = open(os.path.join(os.path.dirname(server.__file__), "server.py"), encoding="utf-8").read()
    bad = []
    for node in ast.walk(ast.parse(src)):
        # 只看 <某物>._todo_store.<方法> 这种真实的属性访问
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Attribute):
            continue
        if node.value.attr != "_todo_store":
            continue
        if node.attr not in methods:
            bad.append((node.attr, node.lineno))
    assert not bad, "调用了 TodoStore 上不存在的方法（方法, 行号）: %s；实际可用: %s" % (
        bad[:5], sorted(methods))


def test_seed_agent_todos_writes_into_real_store():
    """修复本身：_seed_agent_todos 必须真的把待办写进 TodoStore。"""
    a = _FakeAgent()
    a._todo_store = _todo_store_class()()
    todos = [
        {"id": "01", "title": "数据质控", "module": "01", "skill": "s1"},
        {"id": "02", "title": "聚类注释", "status": "completed"},
    ]
    written = server._seed_agent_todos(a, todos, "pipe")
    assert len(written) == 2
    got = {x["id"]: x for x in a._todo_store.read()}
    assert set(got) == {"01", "02"}, "待办没进 store（就是这次修的 bug）"
    assert got["01"]["content"] == "数据质控", "title 没落到 content"
    assert got["01"]["status"] == "pending", "缺 status 应落 pending"
    assert got["02"]["status"] == "completed", "已有 status 必须原样保留"


def test_seed_agent_todos_edges():
    """边界：没 id 兜底生成、非字典跳过、空输入不写也不清空、无 store 不炸。"""
    a = _FakeAgent()
    a._todo_store = _todo_store_class()()
    # merge=True 时没 id 的条目会被静默跳过 —— 必须兜底生成 id
    written = server._seed_agent_todos(a, [{"title": "没有 id 的一条"}, "字符串不是字典"], "auto")
    assert len(written) == 1 and written[0]["id"] == "auto_0"
    assert [x["content"] for x in a._todo_store.read()] == ["没有 id 的一条"]
    assert server._seed_agent_todos(a, [], "auto") == []
    assert server._seed_agent_todos(a, None, "auto") == []
    assert [x["content"] for x in a._todo_store.read()] == ["没有 id 的一条"], "空输入不该清空已有待办"
    assert server._seed_agent_todos(_FakeAgent(), [{"title": "x"}]) == [], "没有 _todo_store 不该炸"


def test_seed_agent_todos_keeps_status_on_rewrite():
    """合并语义：同一 id 再灌一次不能把已完成的打回 pending。"""
    a = _FakeAgent()
    a._todo_store = _todo_store_class()()
    server._seed_agent_todos(a, [{"id": "01", "title": "第一步", "status": "completed"}], "x")
    assert a._todo_store.read()[0]["status"] == "completed"
    # 再灌一次同 id（模拟 pipeline 重复推送）：仍应保留 completed
    server._seed_agent_todos(a, [{"id": "01", "title": "第一步"}], "x")
    assert a._todo_store.read()[0]["status"] == "completed"

