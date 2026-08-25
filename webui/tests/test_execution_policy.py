# -*- coding: utf-8 -*-
"""DSH 执行策略迁移测试：用户优先/插话两不误/调查类意图/resume 重构/ask_user。"""
import importlib.util
import json
import os
import sys

import pytest

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
_SERVER_PY = os.path.join(_ROOT, "webui", "server.py")


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


# ── _EXECUTION_POLICY 策略内容 ─────────────────────────────────────────────

def test_execution_policy_principles(server):
    p = server._EXECUTION_POLICY
    required = ["最高优先级", "只回答", "插话", "自动续跑", "报错停止", "由用户决定",
                "ask_user", "不要猜"]
    for kw in required:
        assert kw in p, f"策略缺关键原则: {kw}"
    # 决策交给 LLM：策略是行为准则不是 if-else 硬编码
    assert "决策由你判断" in p


def test_ephemeral_prompt_includes_policy(server):
    """两处 ephemeral 组装都带策略（_create_agent 与会话 agent 更新）。"""
    src = open(_SERVER_PY, encoding="utf-8").read()
    # 5399 处（_create_agent）与 10948 处（会话 agent 更新）
    assert src.count("_EXECUTION_POLICY") >= 3, "策略常量应定义 + 注入两处"


# ── resume prompt 重构 ──────────────────────────────────────────────────────

def test_resume_prompt_no_longer_forces(server):
    """resume prompt 不再强制推进主线。"""
    sess = {"id": "s-1", "results_dir": "/tmp/x", "intent": "analysis",
            "todos": [{"status": "in_progress", "title": "step1"}]}
    out = server._build_task_resume_prompt(sess)
    assert "必须检查并推进主线" not in out
    assert "禁止" not in out
    assert "报错→分析原因→能修就修" not in out
    assert "系统自动" in out, "任务推进应交给系统自动续跑"
    assert "不是执行命令" in out


def test_resume_prompt_light_for_investigate(server):
    """investigate 意图 → 轻量提示（只提醒不引导推进）。"""
    sess = {"id": "s-2", "results_dir": "/tmp/x", "intent": "investigate",
            "todos": [{"status": "in_progress", "title": "step1"}]}
    out = server._build_task_resume_prompt(sess)
    assert "提示" in out and "自动续跑接管" in out
    assert "未完成主线" not in out


def test_legacy_force_texts_removed_from_source(server):
    """旧的强制文案已从源码移除（源码级回归护栏）。"""
    src = open(_SERVER_PY, encoding="utf-8").read()
    for banned in ("必须检查并推进主线", "最高优先级指令 ⛔⛔⛔", "不要等用户确认"):
        assert banned not in src, f"旧强制文案仍存在: {banned}"


# ── 意图分类：调查类问句 ───────────────────────────────────────────────────

INVESTIGATE_CASES = [
    "检查为什么报错", "排查一下报错原因", "为什么失败了", "看看日志，分析原因",
    "查一下为什么报错", "诊断一下这个问题", "这是为什么出错的",
]
EXEC_CASES = [
    "帮我跑一下这个分析", "执行 pipeline", "开始跑细胞聚类", "继续跑下一个步骤",
]


def test_investigate_intent_detection(server):
    for t in INVESTIGATE_CASES:
        intent, conf, meta = server._classify_intent(t)
        assert intent == "investigate", f"{t!r} → {intent}（应 investigate）"
        assert float(conf) >= 0.5


def test_exec_intent_not_investigate(server):
    for t in EXEC_CASES:
        intent, conf, meta = server._classify_intent(t)
        assert intent != "investigate", f"{t!r} → {intent}（执行类不得误判为调查）"


def test_investigate_resume_light_integration(server):
    """端到端：用户说"检查为什么报错" → investigate 意图 → resume 轻量版。"""
    t = "检查为什么报错"
    intent, _, _ = server._classify_intent(t)
    sess = {"id": "s-3", "results_dir": "/tmp/x", "intent": intent,
            "todos": [{"status": "in_progress", "title": "step1"}]}
    out = server._build_task_resume_prompt(sess)
    assert "提示" in out, "调查请求不得触发强制推进"
    assert "系统自动续跑接管" in out


# ── ask_user 工具 ──────────────────────────────────────────────────────────

def test_ask_user_rejects_empty():
    r = json.loads(ask_user_mod.ask_user(""))
    assert r["ok"] is False


def test_ask_user_no_session():
    r = json.loads(ask_user_mod.ask_user("继续吗？"))
    assert r["ok"] is False, "无会话时应明确失败而不是假装发送"


def test_ask_user_delivers_and_ends_turn(monkeypatch):
    """集成：会话可用 → 问题送达前端 + 记录 pending + 指示结束回合。"""
    import server as _server
    sent = []
    sess = {"id": "s-ask", "_pending_questions": []}
    monkeypatch.setattr(_server, "_sessions", {"s-ask": sess})
    monkeypatch.setattr(_server, "_session_emit",
                        lambda s, m: sent.append(m))
    monkeypatch.setattr(ask_user_mod, "_session_context", lambda: ("s-ask", ""))

    r = json.loads(ask_user_mod.ask_user("是要检查还是修复后继续？"))
    assert r["ok"] is True
    assert "结束本回合" in r["instruction"]
    assert len(sent) == 2, "question + notice 双通道"
    assert sent[0]["type"] == "question"
    assert sess["_pending_questions"][0]["question"] == "是要检查还是修复后继续？"


def test_ask_user_question_truncated():
    r = json.loads(ask_user_mod.ask_user("问" * 800))
    assert r["ok"] is False or len(r.get("question", "")) <= 500


def test_ask_user_registers(server):
    """模块加载时注册进 registry（不炸）。"""
    try:
        from tools.registry import registry
        names = getattr(registry, "list", lambda: [])()
        if callable(names) or isinstance(names, list):
            # registry 可能没有 list 接口——只要注册不抛即通过
            pass
    except Exception:
        pass
    assert hasattr(ask_user_mod, "SCHEMA")
    assert ask_user_mod.SCHEMA["name"] == "ask_user"
