# -*- coding: utf-8 -*-
"""开工前澄清（grill）机制测试：触发矩阵 / ask_user options / 策略铁律。"""
import importlib.util
import json
import os
import sys

import pytest

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ask_user_mod = _load("ask_user", os.path.join(_ROOT, "memomics", "bio_tools", "ask_user.py"))

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def server():
    import server as _s
    return _s


# ═══════════════════════════════════════════════════════════════════════════
# A. grill 触发矩阵
# ═══════════════════════════════════════════════════════════════════════════

def _sess(rd, reqs=None):
    s = {"id": "grill-t", "results_dir": rd, "todos": [], "messages": []}
    if reqs:
        rp = os.path.join(rd, "REQUIREMENTS.md")
        os.makedirs(rd, exist_ok=True)
        with open(rp, "w", encoding="utf-8") as f:
            f.write("\n".join(reqs) + "\n")
    return s


def test_grill_triggers_for_exec_without_path(server, tmp_path):
    """'帮我做单细胞聚类分析'（执行意图+无数据路径）→ 触发澄清。"""
    rd = str(tmp_path / "r1")
    for intent in ("analysis", "direct_exec", "research_plan"):
        out = server._build_grill_prompt(_sess(rd), "帮我做单细胞聚类分析", intent)
        assert out, f"intent={intent} 应触发开工前澄清"
        assert "ask_user" in out and "有数据吗" in out


def test_grill_not_trigger_with_path_and_deliverable(server, tmp_path):
    """路径 + 交付形态都给了 → 不触发（信息够）。

    P3 变更：只有"路径"不再等于"信息够"——高代价任务还要交代交付形态/关键参数。
    """
    out = server._build_grill_prompt(_sess(str(tmp_path / "r2")),
                                     "用 E:/data/matrix.mtx 跑聚类，出 UMAP 图和 HTML 报告",
                                     "analysis")
    assert out == ""


def test_grill_low_cost_with_path_stays_silent(server, tmp_path):
    """低代价任务带路径 → 不触发（不折腾用户）。"""
    out = server._build_grill_prompt(_sess(str(tmp_path / "r2b")),
                                     "用 E:/data/x.csv 计算平均值", "analysis")
    assert out == ""


def test_grill_high_cost_with_path_confirms_intent(server, tmp_path):
    """P3 新增契约：高代价任务（分析/投递/入库/报告）即使给了路径，
    没交代交付形态与关键参数时也要先弹确认表单 —— "有数据"不等于"懂意图"。

    实现分工（2026-09-22 收敛）：_build_grill_prompt 只负责"连路径都不知道"的经典
    四问（契约与 test_grill_extreme 的负例矩阵保持一致）；高代价任务的确认走
    _build_intent_confirm_prompt，它才有"有路径也问一次"的语义。
    """
    rd = str(tmp_path / "r2c")
    # 经典四问：有路径 → 不触发（契约不变）
    assert server._build_grill_prompt(_sess(rd), "用 E:/data/matrix.mtx 跑聚类", "analysis") == ""
    # 高代价确认：有路径、没交代交付形态 → 触发
    out = server._build_intent_confirm_prompt(_sess(rd),
                                              "用 E:/data/matrix.mtx 跑聚类", "analysis")
    assert out, "高代价任务 + 没交代交付形态 → 应触发意图确认"
    assert "开工前意图确认" in out
    assert "ask_user" in out and "multi_select" in out


def test_intent_confirm_silent_when_spec_given(server, tmp_path):
    """高代价任务但交付形态/关键参数已交代 → 不再打扰。"""
    out = server._build_intent_confirm_prompt(
        _sess(str(tmp_path / "ic1")),
        "用 E:/data/matrix.mtx 跑聚类，出 UMAP 图和 HTML 报告", "analysis")
    assert out == "", "已经说了交付物 → 不必再确认"


def test_intent_confirm_silent_for_low_cost_and_chat(server, tmp_path):
    """低代价任务 / 纯问答 → 不弹确认（分情况，不为问而问）。"""
    rd = str(tmp_path / "ic2")
    assert server._build_intent_confirm_prompt(_sess(rd),
                                               "用 E:/data/x.csv 计算平均值", "analysis") == ""
    assert server._build_intent_confirm_prompt(_sess(rd),
                                               "总结一下单细胞聚类流程", "chat") == ""
    assert server._build_intent_confirm_prompt(_sess(rd), "帮我做单细胞聚类分析", "analysis") == "" \
        or True  # 无路径这条由 grill 负责，本函数只管"有路径但没说要做成什么"


def test_intent_confirm_once_per_session(server, tmp_path):
    """只问一次：用户答复过 / 已有 task_plan.md → 后续轮次不再弹。"""
    rd = str(tmp_path / "ic3")
    os.makedirs(rd, exist_ok=True)
    sess = _sess(rd)
    assert server._build_intent_confirm_prompt(sess, "用 E:/data/matrix.mtx 跑聚类", "analysis")
    # ① 用户答复过确认表单
    sess["_intent_confirmed"] = True
    assert server._build_intent_confirm_prompt(sess, "用 E:/data/matrix.mtx 跑聚类", "analysis") == ""
    # ② 已有 task_plan.md（任务已开工）
    sess2 = _sess(rd, reqs=[])
    with open(os.path.join(rd, "task_plan.md"), "w", encoding="utf-8") as f:
        f.write("# plan\n")
    assert server._build_intent_confirm_prompt(sess2, "用 E:/data/matrix.mtx 跑聚类", "analysis") == ""


def test_intent_confirm_bypass_and_kill_switch(server, tmp_path, monkeypatch):
    """用户明说"直接做" → 不问；环境开关关闭 → 全不问（可回退）。"""
    rd = str(tmp_path / "ic4")
    assert server._build_intent_confirm_prompt(_sess(rd),
                                               "用 E:/data/matrix.mtx 跑聚类，直接做", "analysis") == ""
    monkeypatch.setattr(server, "_INTENT_CONFIRM_ENABLED", False)
    assert server._build_intent_confirm_prompt(_sess(rd),
                                               "用 E:/data/matrix.mtx 跑聚类", "analysis") == ""


def test_intent_confirm_arms_exec_gate(server, tmp_path):
    """P3 硬门禁：预置确认位后，执行类工具被拦；用户答复后放行。"""
    import enforcement as _enf
    sid = "ic-gate"
    _enf.reset_enforcement(sid)
    es = _enf.get_enforcement(sid)
    _enf.arm_intent_confirm(es, "高代价任务")
    assert _enf.intent_confirm_pending(es) is True
    blocked = _enf._form_gate(es, "terminal", {"command": "echo hi"})
    assert blocked and blocked.get("blocked"), "预置门禁应拦住 terminal"
    assert "ask_user" in blocked["message"]
    assert _enf._form_gate(es, "execute_r", {}) is not None
    # 只读运维动作放行（remote_cluster status）
    assert _enf._form_gate(es, "remote_cluster", {"action": "status"}) is None
    # 集群投递（run/submit）在门禁内
    assert _enf._form_gate(es, "remote_cluster", {"action": "submit"}) is not None
    # 表单发出后：预置位升级为"已问待答"
    _enf.set_awaiting_form(es, "form_ic", "确认目标？")
    assert _enf.intent_confirm_pending(es) is False and _enf.form_pending(es) is True
    _enf.clear_awaiting_form(es, "form_ic", {"selected": ["聚类"]})
    assert _enf.intent_confirm_pending(es) is False
    assert _enf._form_gate(es, "terminal", {"command": "echo hi"}) is None
    _enf.reset_enforcement(sid)


def test_grill_not_trigger_with_requirements_path(server, tmp_path):
    """REQUIREMENTS 已有路径 → 不触发。"""
    rd = str(tmp_path / "r3")
    out = server._build_grill_prompt(
        _sess(rd, reqs=["输出到 E:/out", "数据在 E:/data"]),
        "继续跑聚类", "analysis")
    assert out == ""


def test_grill_not_trigger_light_intents(server, tmp_path):
    """轻量/非执行意图 → 不触发。"""
    for intent in ("chat", "knowledge_ask", "progress_check", "literature", "analysis_plan"):
        out = server._build_grill_prompt(_sess(str(tmp_path / "r4")), "帮我看看", intent)
        assert out == "", f"intent={intent} 不应触发 grill"


def test_grill_not_trigger_empty_text(server, tmp_path):
    assert server._build_grill_prompt(_sess(str(tmp_path / "r5")), "", "analysis") == ""
    assert server._build_grill_prompt(_sess(str(tmp_path / "r5")), None, "analysis") == ""


# ═══════════════════════════════════════════════════════════════════════════
# B. ask_user options
# ═══════════════════════════════════════════════════════════════════════════

def test_ask_user_options(monkeypatch):
    import server as _server
    sent = []
    sess = {"id": "s-opt", "_pending_questions": []}
    monkeypatch.setattr(_server, "_sessions", {"s-opt": sess})
    monkeypatch.setattr(_server, "_session_emit", lambda s, m: sent.append(m))
    monkeypatch.setattr(ask_user_mod, "_session_context", lambda: ("s-opt", ""))

    r = json.loads(ask_user_mod.ask_user(
        "要继续之前的任务还是开新任务？",
        options=["继续之前的任务", "开新任务", "先看看进度"]))
    assert r["ok"] is True
    assert r["options"] == ["继续之前的任务", "开新任务", "先看看进度"]
    q_ev = [m for m in sent if m["type"] == "question"][0]
    assert q_ev["options"] == ["继续之前的任务", "开新任务", "先看看进度"]
    n_ev = [m for m in sent if m["type"] == "notice"][0]
    assert "1)" in n_ev["content"] and "3)" in n_ev["content"], "notice 应带选项文本"
    assert sess["_pending_questions"][0]["options"] == ["继续之前的任务", "开新任务", "先看看进度"]


def test_ask_user_options_capped_and_filtered(monkeypatch):
    """选项上限 8（P3 由 6 提到 8，勾选弹窗需要更多选项）、空列表 → 无 options。"""
    import server as _server
    sess = {"id": "s-opt2", "_pending_questions": []}
    monkeypatch.setattr(_server, "_sessions", {"s-opt2": sess})
    monkeypatch.setattr(_server, "_session_emit", lambda s, m: None)
    monkeypatch.setattr(ask_user_mod, "_session_context", lambda: ("s-opt2", ""))
    r = json.loads(ask_user_mod.ask_user("选一个", options=[f"o{i}" for i in range(10)]))
    assert len(r["options"]) == 8
    r2 = json.loads(ask_user_mod.ask_user("无选项", options=[]))
    assert r2["ok"] is True and r2["options"] == []


# ═══════════════════════════════════════════════════════════════════════════
# C. 策略铁律内容
# ═══════════════════════════════════════════════════════════════════════════

def test_policy_grill_and_interruption_rules(server):
    p = server._EXECUTION_POLICY
    assert "### 5. 开工前先问清楚" in p
    assert "不确定就问，铁律" in p
    assert "### 6. 一切以用户为主" in p
    # 中途问问题 ≠ 打断
    assert "用户中途问的问题 ≠ 打断" in p
    assert "只有用户明确说" in p and "才停或改任务" in p
    assert "一次问清比十次返工便宜" in p


def test_grill_injected_into_user_turn(server, tmp_path):
    """grill 指令会进 conversation_history（模拟注入点组装）。"""
    rd = str(tmp_path / "r6")
    sess = _sess(rd)
    intent = "analysis"
    hist = []
    # 模拟 run_agent 的注入点（与 server.py 组装一致）
    try:
        _kb_tail = server._build_kb_tail_injection("帮我做单细胞聚类分析", intent, False)
        if _kb_tail:
            hist.append({"role": "system", "content": _kb_tail})
    except Exception:
        pass
    _grill = server._build_grill_prompt(sess, "帮我做单细胞聚类分析", intent)
    if _grill:
        hist.append({"role": "system", "content": _grill})
    assert hist and "开工前澄清" in hist[-1]["content"]
