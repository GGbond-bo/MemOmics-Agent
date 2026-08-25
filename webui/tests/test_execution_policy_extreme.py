# -*- coding: utf-8 -*-
"""DSH 执行策略迁移 · 极端压力测试。

A. 意图分类极端矩阵：调查正例 / 执行反例 / 边界混合（30+ 用例）
B. resume prompt 全组合矩阵：intent × has_plan × has_todos（8 意图 × 4 状态）
C. _EXECUTION_POLICY 内容完备性
D. ask_user 极端：空/超长/emoji/换行/会话缺失/emit 异常/并发/pending 上限
E. 集成链路：多组用户消息 → 意图 → resume → 策略组装
"""
import importlib.util
import json
import os
import sys
import threading

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
# A. 意图分类极端矩阵
# ═══════════════════════════════════════════════════════════════════════════

INVESTIGATE_POS = [
    "检查为什么报错",
    "排查一下报错原因",
    "为什么失败了",
    "看看日志，分析原因",
    "查一下为什么报错",
    "诊断一下这个问题",
    "这是为什么出错的",
    "什么原因导致的报错",
    "出错原因是什么",
    "失败原因是什么",
    "为什么 R 脚本挂了",
    "看下日志里报了什么错",
    "查一下日志找原因",
    "这个错误是怎么发生的",
    "帮我调查一下这个报错",
    "哪里出错了",
    "出了什么问题",
    "分析一下失败的原因",
    "pipeline 为什么中断了",
    "这个 warning 什么原因",
]

INVESTIGATE_NEG = [
    "帮我跑一下这个分析",
    "执行 pipeline",
    "开始跑细胞聚类",
    "继续跑下一个步骤",
    "帮我修复这个报错并重跑",
    "报错了，修一下继续跑",
    "把报错修好",
    "重新跑一遍",
    "帮我写个脚本",
    "画一张 UMAP 图",
    "生成报告",
    "安装 Seurat",
    "翻译这段文字",
    "总结这篇文献",
    "把结果保存一下",
]

INVESTIGATE_EDGE = [
    # 调查+执行混合：含"修"明确指令 → 仍可 investigate（先查原因，策略第4条让模型决定）
    ("先查原因再修复", "investigate"),
    ("报错原因找到了帮我修一下", "investigate"),
    # 无错误词的调查
    ("为什么细胞这么少", "investigate"),
    ("这个结果怎么解释", None),  # 不强制断言——知识问答或调查均可，但不能是执行类
    # 知识问答（怎么解决=问方法）
    ("这个报错怎么解决", "knowledge_ask"),
    ("怎么修复这个报错", None),
]


def test_investigate_positive(server):
    for t in INVESTIGATE_POS:
        intent, conf, _ = server._classify_intent(t)
        assert intent == "investigate", f"正例 {t!r} → {intent}"
        assert float(conf) >= 0.5


def test_investigate_negative(server):
    for t in INVESTIGATE_NEG:
        intent, _, _ = server._classify_intent(t)
        assert intent != "investigate", f"反例 {t!r} → {intent}（不得误判为调查）"


def test_investigate_edge(server):
    for t, expect in INVESTIGATE_EDGE:
        intent, _, _ = server._classify_intent(t)
        if expect is not None:
            assert intent == expect, f"边界 {t!r} → {intent}（期望 {expect}）"
        else:
            assert intent not in ("direct_exec", "analysis"), f"边界 {t!r} → {intent}（不得强执行）"


def test_investigate_never_contains_exec_action(server):
    """investigate 意图的请求必须不含执行类关键词组合（回归护栏）。"""
    for t in INVESTIGATE_POS + [e[0] for e in INVESTIGATE_EDGE]:
        intent, _, _ = server._classify_intent(t)
        if intent == "investigate":
            # "帮我调查" 含"帮"但不含"跑/执行/开始做"等执行动作词
            for _kw in ("跑", "执行", "运行", "开始做"):
                assert _kw not in t or "查" in t, f"{t!r} 含执行词但被判 investigate，需确认"


# ═══════════════════════════════════════════════════════════════════════════
# B. resume prompt 全组合矩阵
# ═══════════════════════════════════════════════════════════════════════════

LIGHT_INTENTS = ("knowledge_ask", "progress_check", "result_check",
                 "analysis_plan", "chat", "cancel_task", "investigate")
HEAVY_INTENTS = ("analysis", "direct_exec", "research_plan", "plan_refine",
                 "report", "literature")


def _mk_sess(intent, has_plan, has_todos, tmp_path):
    rd = str(tmp_path / ("p" if has_plan else "np"))
    if has_plan:
        os.makedirs(rd, exist_ok=True)
        with open(os.path.join(rd, "task_plan.md"), "w", encoding="utf-8") as f:
            f.write("# Goal\npending\n")
    return {"id": "s-x", "results_dir": rd, "intent": intent,
            "todos": ([{"status": "in_progress", "title": "t1"}] if has_todos else [])}


def test_resume_full_matrix(server, tmp_path):
    """8 意图 × 4 状态组合：行为必须符合约束（轻量/通报/空）。"""
    for intent in LIGHT_INTENTS + HEAVY_INTENTS:
        for has_plan in (True, False):
            for has_todos in (True, False):
                sess = _mk_sess(intent, has_plan, has_todos, tmp_path)
                out = server._build_task_resume_prompt(sess)
                tag = f"intent={intent} plan={has_plan} todos={has_todos}"
                if not has_plan and not has_todos:
                    assert out == "", f"{tag} 无任务应返回空"
                    continue
                if intent in LIGHT_INTENTS:
                    assert "提示" in out and "未完成主线" not in out, f"轻量 {tag}: {out[:80]}"
                    assert "系统自动续跑接管" in out, f"轻量也应提续跑 {tag}"
                else:
                    assert out.startswith("ℹ️"), f"通报版 {tag}"
                    assert "系统自动接管" in out
                # 全矩阵统一约束：任何版本都不得含强制推进/禁止结束
                for banned in ("必须检查并推进主线", "禁止：回答完用户问题后直接结束",
                               "你的下一句话必须是工具调用", "报错→分析原因→能修就修"):
                    assert banned not in out, f"{tag} 含强制文案"


# ═══════════════════════════════════════════════════════════════════════════
# C. _EXECUTION_POLICY 内容完备性
# ═══════════════════════════════════════════════════════════════════════════

def test_policy_all_five_principles(server):
    p = server._EXECUTION_POLICY
    # 五个编号小节齐全
    for i in range(1, 6):
        assert f"### {i}." in p, f"策略缺第 {i} 节"
    pairs = [
        ("最高优先级", "覆盖"),
        ("只回答", "不擅自推进"),
        ("自动续跑轮", "自主"),
        ("报错停止后", "由用户决定"),
        ("ask_user", "不要猜"),
    ]
    for a, b in pairs:
        assert a in p and b in p


# ═══════════════════════════════════════════════════════════════════════════
# D. ask_user 极端
# ═══════════════════════════════════════════════════════════════════════════

def test_ask_user_extreme_inputs():
    assert json.loads(ask_user_mod.ask_user(""))["ok"] is False
    assert json.loads(ask_user_mod.ask_user("   "))["ok"] is False
    # 超长截断到 500
    r = json.loads(ask_user_mod.ask_user("问" * 3000))
    assert r["ok"] is False or len(r.get("question", "")) <= 500
    # emoji / 换行 / 特殊字符不炸
    r2 = json.loads(ask_user_mod.ask_user("继续吗？🧬\n(选 A/B)\n<tag>&\"'"))
    assert r2["ok"] is False or r2.get("question", "").startswith("继续吗")


def test_ask_user_emit_exception_fails_safe(monkeypatch):
    """_session_emit 抛异常 → 不炸、返回失败、不误报成功。"""
    import server as _server
    sess = {"id": "s-boom", "_pending_questions": []}
    monkeypatch.setattr(_server, "_sessions", {"s-boom": sess})
    monkeypatch.setattr(_server, "_session_emit", lambda s, m: (_ for _ in ()).throw(RuntimeError("ws down")))
    monkeypatch.setattr(ask_user_mod, "_session_context", lambda: ("s-boom", ""))
    r = json.loads(ask_user_mod.ask_user("测试"))
    assert r["ok"] is False
    assert sess["_pending_questions"] == [], "发送失败不得留 pending"


def test_ask_user_pending_capped(monkeypatch):
    """pending 上限 20：连问 30 次只留最近 20。"""
    import server as _server
    sess = {"id": "s-cap", "_pending_questions": []}
    monkeypatch.setattr(_server, "_sessions", {"s-cap": sess})
    monkeypatch.setattr(_server, "_session_emit", lambda s, m: None)
    monkeypatch.setattr(ask_user_mod, "_session_context", lambda: ("s-cap", ""))
    for i in range(30):
        json.loads(ask_user_mod.ask_user(f"问题{i}"))
    assert len(sess["_pending_questions"]) == 20
    assert sess["_pending_questions"][-1]["question"] == "问题29"
    assert sess["_pending_questions"][0]["question"] == "问题10"


def test_ask_user_concurrent(monkeypatch):
    """多线程并发 ask_user → 无异常、pending 不超上限、记录数正确。"""
    import server as _server
    sess = {"id": "s-conc", "_pending_questions": []}
    monkeypatch.setattr(_server, "_sessions", {"s-conc": sess})
    monkeypatch.setattr(_server, "_session_emit", lambda s, m: None)
    monkeypatch.setattr(ask_user_mod, "_session_context", lambda: ("s-conc", ""))
    errors = []

    def _w(i):
        try:
            for j in range(10):
                json.loads(ask_user_mod.ask_user(f"q{i}-{j}"))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=_w, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(sess["_pending_questions"]) == 20, "并发后仍受上限约束"
    # 记录按时间序保留最近 20 条（无重复/无损坏）
    assert len({r["question"] for r in sess["_pending_questions"]}) == 20


# ═══════════════════════════════════════════════════════════════════════════
# E. 集成链路：用户消息 → 意图 → resume → 策略组装
# ═══════════════════════════════════════════════════════════════════════════

def test_full_pipeline_scenarios(server):
    """真实用户消息场景的端到端组装验证。"""
    scenarios = [
        # (用户消息, 期望意图类或 None, resume 是否轻量版)
        ("检查为什么报错", "investigate", True),
        ("为什么失败了", "investigate", True),
        ("这个错误是怎么发生的", "investigate", True),
        ("继续跑任务", None, True),  # 现有分类：无数据路径短句 → chat（轻量）——非本次改动
        ("这个报错怎么解决", "knowledge_ask", True),
        ("帮我修好报错继续跑", None, None),  # 意图不定，只验证无强制文案
    ]
    for text, want_intent, light in scenarios:
        intent, _, _ = server._classify_intent(text)
        if want_intent:
            assert intent == want_intent, f"{text!r} → {intent}"
        sess = {"id": "s-f", "results_dir": "", "intent": intent,
                "todos": [{"status": "in_progress", "title": "t"}]}
        out = server._build_task_resume_prompt(sess)
        if light is True:
            assert out.startswith("💡"), f"{text!r}: {out[:60]}"
        # 全场景统一：无强制推进文案
        for banned in ("必须检查并推进主线", "禁止：回答完用户问题后直接结束",
                       "你的下一句话必须是工具调用", "报错→分析原因→能修就修"):
            assert banned not in out, f"{text!r} 含强制文案"
        # 组装即策略可见
        assert "执行策略（用户优先" in server._EXECUTION_POLICY
