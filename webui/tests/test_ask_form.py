# -*- coding: utf-8 -*-
"""P3(2026-09-22) 意图确认弹窗：门禁 + 弹窗事件 + 答复回流 回归测试。

用户需求原话："我希望在执行任务之前，先理解用户的意图，然后 grill 用户，
把不清楚的问题问明白。做出弹窗，供用户勾选，理解用户的意图之后再执行。"

锁死的契约：
  1. ask_user 带 options → 发出结构化 ask_form 事件（前端弹窗渲染）+ 置位执行门禁
  2. 未答复前执行/产物类工具被硬拦（read 类照常放行，避免把澄清本身卡死）
  3. 用户答复（弹窗提交 / 直接回消息）→ 解除门禁
  4. 门禁 30 分钟无答复自动失效（用户走开不该永久锁死）
  5. 结构化答复 → 确定性上下文（只注入一次），模型不会再问一遍
  6. enforcement 被两个模块名加载时状态仍然共享（模块分裂防护）
"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import enforcement as enf  # noqa: E402
import server  # noqa: E402
from memomics.bio_tools import ask_user as au  # noqa: E402


# ==================== A. 门禁机制 ====================

def _mk(sid="p3_test"):
    enf.reset_enforcement(sid)
    es = enf.get_enforcement(sid)
    es.analysis_level = "analysis"
    return es


def test_pending_form_blocks_exec_tool():
    es = _mk()
    enf.set_awaiting_form(es, "form_1", "用哪个物种的参考基因组？")
    blk = enf._form_gate(es, "execute_r")
    assert blk and blk["blocked"] is True
    assert "意图还没确认" in blk["message"]
    assert "参考基因组" in blk["message"]
    assert es.form_block_hits == 1


def test_pending_form_blocks_high_impact_tools():
    es = _mk()
    enf.set_awaiting_form(es, "form_1", "q")
    for t in ("generate_report", "save_knowledge", "terminal", "execute_python"):
        assert enf._form_gate(es, t) is not None, t


def test_pending_form_gates_cluster_submit_only():
    """集群：run/submit 属高代价执行 → 拦；check/status/push/pull 只读运维 → 放行。"""
    es = _mk("p3_cluster")
    enf.set_awaiting_form(es, "form_1", "q")
    assert enf._form_gate(es, "remote_cluster", {"action": "submit"}) is not None
    assert enf._form_gate(es, "remote_cluster", {"action": "run"}) is not None
    assert enf._form_gate(es, "remote_cluster", {"action": "status"}) is None
    assert enf._form_gate(es, "remote_cluster", {"action": "pull"}) is None


def test_pending_form_allows_readonly_tools():
    """查询/读类工具不拦 —— 否则模型连"查清楚再问"都做不到。"""
    es = _mk()
    enf.set_awaiting_form(es, "form_1", "q")
    for t in ("skill_view", "search_knowledge", "read_file", "ask_user", "debate_analysis"):
        assert enf._form_gate(es, t) is None, t


def test_answer_clears_gate():
    es = _mk()
    enf.set_awaiting_form(es, "form_1", "q")
    assert enf.clear_awaiting_form(es, "form_1", {"selected": ["A"]}) is True
    assert enf.form_pending(es) is False
    assert enf._form_gate(es, "execute_r") is None
    assert es.form_answers and es.form_answers[-1]["selected"] == ["A"]


def test_wrong_form_id_does_not_clear():
    es = _mk()
    enf.set_awaiting_form(es, "form_1", "q")
    assert enf.clear_awaiting_form(es, "form_OTHER", {}) is False
    assert enf.form_pending(es) is True


def test_gate_expires_after_ttl():
    es = _mk()
    enf.set_awaiting_form(es, "form_1", "q")
    es.awaiting_form_ts = time.time() - (enf._FORM_PENDING_TTL + 60)
    assert enf.form_pending(es) is False
    assert enf._form_gate(es, "execute_r") is None


def test_no_form_no_gate():
    es = _mk()
    assert enf.form_pending(es) is False
    assert enf._form_gate(es, "execute_r") is None


def test_state_surface_exposes_form_fields():
    es = _mk()
    enf.set_awaiting_form(es, "form_9", "物种？")
    d = es.to_dict()
    assert d["awaiting_form_id"] == "form_9"
    assert d["awaiting_form_question"] == "物种？"
    assert "form_block_hits" in d and "form_answers" in d


def test_callback_blocks_exec_and_emits_blocked_event(tmp_path):
    """接线回归：tool_start_callback 真的会拦，并发出 blocked 事件给前端。"""
    emitted = []
    enf.reset_enforcement("cb_form")
    cbs = enf.create_enforcement_callbacks(
        {"id": "cb_form", "results_dir": str(tmp_path)},
        lambda s, m: emitted.append(m))
    es = enf.get_enforcement("cb_form")
    enf.set_awaiting_form(es, "form_x", "先确认意图")
    res = cbs["tool_start_callback"]("c1", "execute_r", {"code": "1+1"})
    assert isinstance(res, dict) and res.get("blocked") is True
    assert any(m.get("action") == "blocked" for m in emitted)
    # 答复后放行（不再返回 blocked）
    enf.clear_awaiting_form(es, "form_x", {"selected": ["继续"]})
    res2 = cbs["tool_start_callback"]("c2", "execute_r", {"code": "1+1"})
    assert not (isinstance(res2, dict) and res2.get("blocked"))


def test_state_shared_across_module_aliases():
    """模块分裂防护：webui.enforcement 与 enforcement 必须共用同一份状态。"""
    import importlib
    try:
        e2 = importlib.import_module("webui.enforcement")
    except Exception:
        pytest.skip("webui 包不可导入")
    if e2 is enf:
        pytest.skip("同一模块对象，无需共享")
    a = enf.get_enforcement("alias_sid")
    b = e2.get_enforcement("alias_sid")
    assert a is b
    e2.set_awaiting_form(b, "form_alias", "q")
    assert enf.form_pending(a) is True
    enf.reset_enforcement("alias_sid")


# ==================== B. ask_user 弹窗事件 ====================

class _FakeSess(dict):
    pass


@pytest.fixture
def ask_env(monkeypatch):
    """隔离：假会话 + 事件记录器（不碰真实 WS / 生产目录）。"""
    sid = "ask_form_sid"
    sess = _FakeSess({"id": sid, "messages": [], "results_dir": "/tmp/none"})
    events = []
    monkeypatch.setitem(server._sessions, sid, sess)
    monkeypatch.setattr(server, "_session_emit", lambda s, m: events.append(m))
    monkeypatch.setattr(au, "_session_context", lambda: (sid, "/tmp/none"))
    enf.reset_enforcement(sid)
    yield sid, sess, events
    enf.reset_enforcement(sid)


def test_ask_user_emits_structured_form(ask_env):
    sid, sess, events = ask_env
    out = json.loads(au.ask_user(
        "这次要跑哪套流程？",
        options=[{"label": "Seurat 标准流程", "desc": "省事、可复现", "recommended": True},
                 "自定义脚本"],
        multi_select=False, header="开工前确认", kind="intent"))
    assert out["ok"] is True and out["form_id"]
    forms = [e for e in events if e.get("type") == "ask_form"]
    assert len(forms) == 1
    f = forms[0]
    assert f["question"] == "这次要跑哪套流程？"
    assert f["options"] == ["Seurat 标准流程", "自定义脚本"]
    assert f["form_options"][0]["recommended"] is True
    assert f["form_options"][0]["desc"] == "省事、可复现"
    assert f["multi_select"] is False
    assert f["allow_other"] is True
    assert f["kind"] == "intent"
    assert f["header"] == "开工前确认"
    assert f["session_id"] == sid


def test_ask_user_sets_execution_gate(ask_env):
    sid, sess, events = ask_env
    out = json.loads(au.ask_user("确认一下？", options=["A", "B"]))
    es = enf.get_enforcement(sid)
    assert es.awaiting_form_id == out["form_id"]
    assert enf.form_pending(es) is True
    assert enf._form_gate(es, "execute_r") is not None
    # 待确认记录留档
    pend = sess.get("_pending_questions") or []
    assert pend and pend[-1]["form_id"] == out["form_id"] and pend[-1]["answered"] is False


def test_ask_user_plain_strings_and_no_options(ask_env):
    sid, sess, events = ask_env
    out = json.loads(au.ask_user("要不要继续？"))
    assert out["ok"] is True and out["options"] == []
    f = [e for e in events if e.get("type") == "ask_form"][0]
    assert f["options"] == [] and f["allow_other"] is True
    assert f["header"]  # 有默认标题


def test_ask_user_empty_question_rejected():
    out = json.loads(au.ask_user("   "))
    assert out["ok"] is False


def test_ask_user_without_session_reports_failure(monkeypatch):
    monkeypatch.setattr(au, "_session_context", lambda: ("", ""))
    out = json.loads(au.ask_user("q?"))
    assert out["ok"] is False and "无法联系用户" in out["error"]

def test_ask_user_finds_server_instance_named_main(ask_env, monkeypatch):
    """真机事故回归（2026-09-24 / memomics-c8aacf1e）：

    生产入口是 `python webui/server.py` → 模块名变成 __main__。老代码只查
    sys.modules["server"] / ["webui.server"]，查不到就 `import webui.server` →
    又造一个实例、_sessions 是空的 → ask_user 静默返回「无法联系用户（会话不可用）」，
    意图确认表单永远弹不到前端。这条测试把"server 实例挂在别的名字下"这一生产条件固化下来。
    """
    import sys
    import types
    sid, sess, events = ask_env
    fake_main = types.ModuleType("__main__")
    fake_main._sessions = server._sessions          # 同一个会话表
    fake_main._session_emit = server._session_emit  # 同一个发送口
    monkeypatch.delitem(sys.modules, "server", raising=False)
    monkeypatch.delitem(sys.modules, "webui.server", raising=False)
    monkeypatch.setitem(sys.modules, "__main__", fake_main)

    out = json.loads(au.ask_user("入口名是 __main__ 时还能弹表单吗？", options=["能", "不能"],
                                 kind="intent"))
    assert out["ok"] is True, "生产入口名（__main__）下弹不出表单：%s" % out
    assert [e for e in events if e.get("type") == "ask_form"], "没发出 ask_form 事件"


def test_ask_user_error_says_why(monkeypatch):
    """联系不上用户时要写清原因（没 sid / 没实例 / 实例里没这个会话），别再只说一句不可用。"""
    monkeypatch.setattr(au, "_session_context", lambda: ("", ""))
    out = json.loads(au.ask_user("q?"))
    assert out["ok"] is False
    assert "无法联系用户" in out["error"] and "会话上下文为空" in out["error"]



# ==================== C. 答复回流（HTTP + 上下文） ====================

def test_answer_endpoint_records_and_clears(client, new_session):
    sid = new_session
    sid = sid if isinstance(sid, str) else sid
    sess = server._sessions[sid]
    sess["_pending_questions"] = [{"form_id": "form_ep", "question": "用哪个阈值？",
                                   "options": ["0.5", "0.8"], "answered": False}]
    es = enf.get_enforcement(sid)
    enf.set_awaiting_form(es, "form_ep", "用哪个阈值？")
    r = client.post("/api/ask_form/answer", json={
        "session_id": sid, "form_id": "form_ep",
        "selected": ["0.8"], "other": "另外报告里保留原始值",
        "question": "用哪个阈值？"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["gate_cleared"] is True
    assert "0.8" in body["answer_text"] and "原始值" in body["answer_text"]
    assert enf.form_pending(enf.get_enforcement(sid)) is False
    assert enf._form_gate(enf.get_enforcement(sid), "execute_r") is None
    assert sess["_pending_questions"][0]["answered"] is True
    ans = sess.get("_ask_form_answers") or []
    assert ans and ans[-1]["selected"] == ["0.8"] and ans[-1]["injected"] is False
    assert ans[-1]["_ts"] > 0


def test_answer_endpoint_requires_selection(client, new_session):
    sid = new_session
    r = client.post("/api/ask_form/answer", json={"session_id": sid, "form_id": "x",
                                                 "selected": [], "other": "  "})
    assert r.status_code == 400


def test_answer_endpoint_unknown_session(client):
    r = client.post("/api/ask_form/answer", json={"session_id": "no-such-sid-xyz",
                                                 "selected": ["A"]})
    assert r.status_code == 404


def test_ask_form_context_injected_once():
    sid = "ctx_sid"
    sess = {"id": sid, "_ask_form_answers": [{
        "form_id": "form_c", "question": "要不要做批次校正？",
        "selected": ["要做", "保留原始矩阵"], "other": "",
        "_ts": time.time(), "injected": False}]}
    ctx = server._build_ask_form_context(sess, "【确认答复】选中：要做")
    assert "要不要做批次校正" in ctx
    assert "要做" in ctx and "保留原始矩阵" in ctx
    assert "不要再重复询问" in ctx
    # 只注入一次
    assert server._build_ask_form_context(sess, "随便") == ""


def test_ask_form_context_expires():
    sess = {"id": "ctx2", "_ask_form_answers": [{
        "form_id": "f", "question": "q", "selected": ["A"], "other": "",
        "_ts": time.time() - 3600, "injected": False}]}
    assert server._build_ask_form_context(sess, "x") == ""


def test_ask_form_context_empty_when_no_answers():
    assert server._build_ask_form_context({"id": "s"}, "x") == ""
