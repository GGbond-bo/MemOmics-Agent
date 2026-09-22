# -*- coding: utf-8 -*-
"""P4(2026-09-22) 代码修改模式（只改不跑 + 数据验证弹窗）契约测试。

用户原话："如果我给一些脚本和代码，让 MemOmics 自己帮我改一下、完善一下，它会不会自己
跑去执行呢？什么时候执行脚本，什么时候只是改代码呢？如果只是修改代码，能不能直接给修改后的
代码呢？如果记忆里有用户的数据可以拿来验证，是不是可以弹窗问用户需不需要用数据验证一下呢？"

四组契约（全部走真实实现）：
  A. _code_edit_mode        改代码→edit(只改不跑) / 用户说要跑→verify / 其它→不进入本模式
  B. _find_memory_data      只认用户自己的数据（数据后缀或 data/raw/数据 目录）
  C. enforcement 门禁       execute_r/脚本/集群投递被拦；cat 脚本、write 代码放行；只读命令放行
  D. 确定性弹窗 + 答复语义 服务器自己弹窗（不靠模型自觉）；"只给代码"保持锁，"验证"解锁
"""
import json
import os
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import enforcement as enf  # noqa: E402
import server  # noqa: E402
from memomics.bio_tools import ask_user as au  # noqa: E402


# ==================== A. 模式判定 ====================

EDIT_CASES = [
    "帮我改一下这个脚本，把阈值改成 0.05",
    "这段代码帮我改改，适配 h5ad 输入",
    "优化一下这个函数，太慢了",
    "帮我把这个 R 脚本改一下，加上分组参数",
    "我这个 Python 脚本报错了，帮我修一下",
    "帮我完善一下这个脚本的注释和参数校验",
    "重构一下这个 notebook 里的代码",
    "把脚本里的 seurat 版本换成 v5 写法",
    "please fix this python script, it crashes on h5ad",
    "refactor this function so it takes a path argument",
    "帮我把 E:/work/analysis.R 改成支持 h5ad 输入",
]

VERIFY_CASES = [
    "帮我改一下这个脚本，然后跑一遍看看",
    "修改这段代码并测试",
    "优化脚本后用 E:/data/x.h5ad 验证一下",
    "帮我改下脚本，重新出图",
    "fix the script and run it on E:/data/test.csv",
]
NONE_CASES = [
    "帮我分析一下这段 Python 代码为什么报错",
    "这段代码是什么意思",
    "帮我写一段 Python 代码统计测序深度",
    "用 E:/data/matrix.mtx 跑聚类",
    "帮我做单细胞聚类分析",
    "帮我看看这个脚本",
    "帮我改一下这个报告的标题",
    "今天心情不错",
    "帮我改一下这个图的颜色",
    "帮我把 E:/data/x.h5ad 质控一下",
    "",
]


@pytest.mark.parametrize("text", EDIT_CASES)
def test_mode_edit(text):
    assert server._code_edit_mode(text) == "edit", text


@pytest.mark.parametrize("text", VERIFY_CASES)
def test_mode_verify(text):
    assert server._code_edit_mode(text) == "verify", text


@pytest.mark.parametrize("text", NONE_CASES)
def test_mode_none(text):
    assert server._code_edit_mode(text) == "", text


def test_mode_kill_switch(monkeypatch):
    monkeypatch.setattr(server, "_CODE_EDIT_ENABLED", False)
    assert server._code_edit_mode("帮我改一下这个脚本") == ""


def test_mode_superlong_text_ignored():
    assert server._code_edit_mode("帮我改一下这个脚本 " + "补" * 5000) == ""


# ==================== B. 记忆里的用户数据 ====================

def _mk_session(requirements=None):
    rd = tempfile.mkdtemp(prefix="codeedit_")
    sess = {"id": "sess-code-edit-test", "results_dir": rd}
    if requirements:
        with open(os.path.join(rd, "REQUIREMENTS.md"), "w", encoding="utf-8") as f:
            f.write(chr(10).join(requirements) + chr(10))
    return sess



def test_find_data_from_requirements():
    s = _mk_session(["数据在 E:/data/x.h5ad (特别指定)", "物种：人", "矩阵 E:/raw/GSE1/matrix.mtx"])
    got = server._find_memory_data(s, "帮我改一下这个脚本")
    assert "E:/data/x.h5ad" in got and "E:/raw/GSE1/matrix.mtx" in got


def test_find_data_from_current_message():
    s = _mk_session()
    got = server._find_memory_data(s, "帮我改一下脚本，用 E:/data/expr.csv 试试")
    assert got == ["E:/data/expr.csv"]


def test_find_data_skips_scripts_and_outputs():
    s = _mk_session(["脚本在 E:/work/analysis.R", "结果在 E:/results/out/report.html"])
    assert server._find_memory_data(s, "帮我改一下这个脚本") == []


def test_find_data_dedup_and_limit():
    s = _mk_session(["E:/data/a.h5ad", "E:/data/b.h5ad", "E:/data/c.h5ad", "E:/data/d.h5ad"])
    got = server._find_memory_data(s, "E:/data/a.h5ad 帮我改一下脚本")
    assert len(got) == 3 and got[0] == "E:/data/a.h5ad"


# ==================== C. enforcement 代码修改门禁 ====================

@pytest.fixture()
def es():
    return enf.EnforcementState("sess-code-edit-es",
                                results_dir=tempfile.mkdtemp(prefix="codeedit_es_"))


def test_gate_blocks_exec_tools(es):
    enf.arm_code_edit(es, "用户要求改代码", data=["E:/data/x.h5ad"])
    for t in ("execute_r", "execute_python", "execute_code", "run_script"):
        r = enf.code_edit_gate(es, t, {})
        assert r and r["blocked"] is True, t
        assert "改代码" in r["message"]


def test_gate_blocks_terminal_python_but_allows_readonly(es):
    enf.arm_code_edit(es)
    assert enf.code_edit_gate(es, "terminal", {"command": "python run.py"}) is not None
    assert enf.code_edit_gate(es, "terminal", {"command": "Rscript analysis.R"}) is not None
    assert enf.code_edit_gate(es, "terminal", {"command": "cat E:/work/a.R"}) is None
    assert enf.code_edit_gate(es, "terminal", {"command": "Get-Content E:/work/a.py"}) is None


def test_gate_allows_write_and_read_tools(es):
    enf.arm_code_edit(es)
    for t in ("write", "read", "edit", "read_file", "search_knowledge"):
        assert enf.code_edit_gate(es, t, {}) is None, t



def test_gate_cluster_run_blocked_status_allowed(es):
    enf.arm_code_edit(es)
    assert enf.code_edit_gate(es, "remote_cluster", {"action": "submit"}) is not None
    assert enf.code_edit_gate(es, "remote_cluster", {"action": "status"}) is None


def test_gate_release_and_non_sticky(es):
    enf.arm_code_edit(es)
    assert enf.code_edit_pending(es) is True
    assert enf.clear_code_edit(es, grant_exec=True) is True
    assert enf.code_edit_pending(es) is False
    assert enf.code_edit_gate(es, "execute_r", {}) is None
    enf.arm_code_edit(es)
    assert enf.code_edit_pending(es) is True
    assert enf.code_edit_gate(es, "execute_r", {}) is not None


def test_gate_ttl_expiry(es):
    enf.arm_code_edit(es)
    es.code_edit_ts = time.time() - (enf._CODE_EDIT_TTL + 5)
    assert enf.code_edit_pending(es) is False
    assert enf.code_edit_gate(es, "execute_r", {}) is None


def test_gate_block_message_has_release_paths(es):
    enf.arm_code_edit(es, data=["E:/data/x.h5ad"])
    m = enf.code_edit_gate(es, "execute_r", {})["message"]
    assert "ask_user" in m and "30 分钟" in m and "E:/data/x.h5ad" in m
    assert es.code_edit_block_hits >= 1


def test_state_dict_reports_code_edit(es):
    enf.arm_code_edit(es, data=["E:/data/x.h5ad"])
    d = es.to_dict()
    assert d["code_edit"] is True and d["code_edit_data"] == 1



# ==================== D. 确定性弹窗 + 答复语义 ====================

def test_emit_form_for_session_writes_real_events(monkeypatch):
    sid = "sess-code-emit"
    sess = {"id": sid}
    monkeypatch.setitem(server._sessions, sid, sess)
    events = []
    monkeypatch.setattr(server, "_session_emit", lambda s, e: events.append(e))
    fid, delivered = au.emit_form_for_session(
        sess, "要不要用你的数据验证？", options=["只给我改好的代码，先别跑", "用这些数据跑一遍验证"],
        kind="intent", arm_gate=False)
    assert delivered is True and fid.startswith("form_")
    assert any(e.get("type") == "ask_form" for e in events)
    assert sess["_pending_questions"][-1]["form_id"] == fid



def test_emit_code_edit_form_arms_no_p3_gate(monkeypatch):
    sid = "sess-code-form"
    sess = {"id": sid}
    monkeypatch.setitem(server._sessions, sid, sess)
    events = []
    monkeypatch.setattr(server, "_session_emit", lambda s, e: events.append(e))
    fid, ok = server._emit_code_edit_form(sess, ["E:/data/x.h5ad"])
    assert ok is True
    form = [e for e in events if e.get("type") == "ask_form"][0]
    assert len(form["form_options"]) == 3
    assert form["form_options"][0]["recommended"] is True
    assert "x.h5ad" in form["question"]
    assert enf.get_enforcement(sid).awaiting_form_id == ""



def test_answer_edit_only_keeps_lock(client, new_session):
    sid = new_session
    e = enf.get_enforcement(sid)
    enf.arm_code_edit(e, "用户要求改代码", data=["E:/data/x.h5ad"])
    r = client.post("/api/ask_form/answer", json={
        "session_id": sid, "selected": ["只给我改好的代码，先别跑"], "other": ""})
    assert r.status_code == 200
    assert r.json()["code_edit"] == "edit_only"
    assert enf.code_edit_pending(e) is True
    assert enf.code_edit_gate(e, "execute_r", {}) is not None


def test_answer_verify_releases_lock(client, new_session):
    sid = new_session
    e = enf.get_enforcement(sid)
    enf.arm_code_edit(e, "用户要求改代码", data=["E:/data/x.h5ad"])
    r = client.post("/api/ask_form/answer", json={
        "session_id": sid, "selected": ["用这些数据跑一遍验证"], "other": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["code_edit"] == "verify_ok" and body["gate_cleared"] is True
    assert enf.code_edit_pending(e) is False
    assert enf.code_edit_gate(e, "execute_r", {}) is None


def test_answer_plan_first_keeps_lock(client, new_session):
    sid = new_session
    e = enf.get_enforcement(sid)
    enf.arm_code_edit(e, "用户要求改代码")
    r = client.post("/api/ask_form/answer", json={
        "session_id": sid, "selected": ["先给我改动计划"], "other": ""})
    assert r.json()["code_edit"] == "edit_only"
    assert enf.code_edit_pending(e) is True


def test_prompt_asks_for_full_code_and_style_respect():
    sess = _mk_session(["数据在 E:/data/x.h5ad"])
    p = server._build_code_edit_prompt(sess, "帮我改一下这个脚本", "edit", ["E:/data/x.h5ad"])
    assert "只改不跑" in p
    assert "完整代码" in p and "SOUL 铁律" in p
    assert "E:/data/x.h5ad" in p and "ask_user" in p
    assert "scripts" in p


def test_prompt_verify_mode_allows_running():
    p = server._build_code_edit_prompt(_mk_session(), "改一下脚本然后跑一遍", "verify", [])
    assert "改完再跑" in p and "可以直接跑" in p
    assert "别自己找数据跑" in p


def test_prompt_without_data_tells_model_to_ask():
    p = server._build_code_edit_prompt(_mk_session(), "帮我改一下这个脚本", "edit", [])
    assert "记忆里没有他数据的路径" in p


def test_normalize_options_caps_at_8():
    labels, rich = au._normalize_options([{"label": "x%d" % i} for i in range(20)])
    assert len(labels) == 8 and len(rich) == 8

# ==================== E. "弹窗答复"识别（前端措辞 vs 后端措辞）P4 修复回归 ====================

FE_ANSWER = "【确认答复】针对「你只让我改代码（没说要跑）。记忆里有你的数据：expr.csv —— 要不要用这些数据跑一遍验证？」：选中：只给我改好的代码，先别跑"
BE_ANSWER = "【用户对「要不要用这些数据跑一遍验证？」的确认答复】选中：用这些数据跑一遍验证"


def test_form_ans_frontend_wording_recognized():
    assert server._is_form_answer_text(FE_ANSWER) is True


def test_form_ans_backend_wording_recognized():
    assert server._is_form_answer_text(BE_ANSWER) is True


def test_form_ans_normal_message_not_recognized():
    for t in ("帮我改一下这个脚本，用 E:/data/x.h5ad 验证", "帮我做单细胞聚类分析", ""):
        assert server._is_form_answer_text(t) is False, t


def test_form_ans_marker_is_one_shot():
    s = {"_form_ans_marker": time.time()}
    assert server._is_form_answer_text("选中：只给我改好的代码，先别跑", s) is True
    assert "_form_ans_marker" not in s
    assert server._is_form_answer_text("帮我做单细胞聚类分析", s) is False


def test_form_ans_marker_expires():
    s = {"_form_ans_marker": time.time() - 600}
    assert server._is_form_answer_text("选中：用这些数据跑一遍验证", s) is False


def test_frontend_answer_does_not_release_lock(client, new_session):
    """真实前端措辞走一遍完整链路：POST 上报 → 答复消息必须被认成"弹窗答复"。

    不然选"只给代码"的那条消息会被当成新需求，把代码修改锁放掉（用户最怕的"自己跑去跑"）。
    """
    sid = new_session
    e = enf.get_enforcement(sid)
    enf.arm_code_edit(e, "用户要求改代码", data=["E:/release/_ce_demo/expr.csv"])
    r = client.post("/api/ask_form/answer", json={
        "session_id": sid, "selected": ["只给我改好的代码，先别跑"], "other": "",
        "question": "要不要用你的数据跑一遍验证？"})
    assert r.json()["code_edit"] == "edit_only"
    assert server._is_form_answer_text(FE_ANSWER, server._sessions[sid]) is True
    assert enf.code_edit_pending(e) is True
    assert enf.code_edit_gate(e, "terminal", {"command": "python x.py"}) is not None


def test_form_ans_marker_set_by_real_endpoint(client, new_session):
    sid = new_session
    client.post("/api/ask_form/answer", json={
        "session_id": sid, "selected": ["用这些数据跑一遍验证"], "other": "",
        "question": "要不要用你的数据跑一遍验证？"})
    assert "_form_ans_marker" in server._sessions[sid]
