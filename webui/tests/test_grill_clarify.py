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


def test_grill_not_trigger_with_path(server, tmp_path):
    """当前消息带数据路径 → 不触发（信息够）。"""
    out = server._build_grill_prompt(_sess(str(tmp_path / "r2")),
                                     "用 E:/data/matrix.mtx 跑聚类", "analysis")
    assert out == ""


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
    """选项上限 6、非法选项过滤、空列表 → 无 options。"""
    import server as _server
    sess = {"id": "s-opt2", "_pending_questions": []}
    monkeypatch.setattr(_server, "_sessions", {"s-opt2": sess})
    monkeypatch.setattr(_server, "_session_emit", lambda s, m: None)
    monkeypatch.setattr(ask_user_mod, "_session_context", lambda: ("s-opt2", ""))
    r = json.loads(ask_user_mod.ask_user("选一个", options=[f"o{i}" for i in range(10)]))
    assert len(r["options"]) == 6
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
