# -*- coding: utf-8 -*-
"""grill 开工前澄清机制 · 极端测试（多意图多场景）。

A. grill 触发矩阵 30+ 用例：正例（执行无路径）/ 反例（有路径/REQUIREMENTS/轻量）/
   边界（路径混淆/中英/问句/继续旧任务/混合意图）
B. 链路组装：意图 → grill → resume → 策略 端到端（真实 server 模块）
C. ask_user options 极端：超多/空/重复/超长/emoji/并发
D. 策略 6 条完备性
E. 跨机制：grill 与 investigate/路径记忆 共存不冲突
"""
import importlib.util
import json
import os
import re
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


def _sess(rd, reqs=None):
    s = {"id": "gx", "results_dir": rd, "todos": [], "messages": []}
    if reqs:
        os.makedirs(rd, exist_ok=True)
        with open(os.path.join(rd, "REQUIREMENTS.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(reqs) + "\n")
    return s


# ═══════════════════════════════════════════════════════════════════════════
# A. grill 触发矩阵
# ═══════════════════════════════════════════════════════════════════════════

GRILL_POS = [
    "帮我做单细胞聚类分析",
    "做个差异表达分析",
    "跑一下 WGCNA",
    "帮我分析一下我的数据",
    "做个注释",
    "执行细胞通讯分析",
    "帮我做个富集分析",
    "分析一下这个表达矩阵",
    "跑个降维聚类流程",
    "帮我做跨物种 ATAC 保守性分析",
    "帮我做一下拟时序分析",
]

GRILL_NEG = [
    "用 E:/data/matrix.mtx 跑聚类",
    "分析 E:/scRNA/obj.rds 的数据",
    "帮我分析一下，数据在 E:/data",
    "继续跑之前的分析",
    "帮我查一下这个基因的功能",        # 文献/知识 → 非执行意图
    "总结这篇文献",
    "这个参数怎么设",
    "帮我写个报告",
    "今天天气怎么样",
]

GRILL_EDGE = [
    # (文本, 期望触发?)
    ("数据在 E:/data 帮我分析", False),      # 路径在句中 → 不触发（信息够）
    ("帮我分析（数据在 E:/data）", False),   # 括号里路径 → 应识别到
    ("数据在桌面上，帮我分析", True),        # 无盘符路径 → 触发澄清
    ("帮我分析 E:/data 为什么报错", False),  # investigate 优先 → 不 grill
    ("检查一下报错原因", False),             # investigate → 不 grill
    ("帮我做分析，顺便查下文献", True),      # 执行为主 → 触发
    ("分析一下", True),                     # 极短执行请求 → 触发
    ("output to E:/x 帮我跑", False),        # 有路径 → 不触发
    ("帮我分析，数据我自己有", True),        # 有数据陈述但无路径 → 触发问在哪
    ("继续", False),                        # 无明确执行 → 不触发
    ("继续跑之前的分析", False),            # 继续旧任务 → 交 resume，不触发
    ("跑个降维聚类流程", True),             # 执行信号词（即使意图词表误判）→ 触发
]


def test_grill_positive_matrix(server, tmp_path):
    rd = str(tmp_path / "gp")
    for t in GRILL_POS:
        intent, _, _ = server._classify_intent(t)
        out = server._build_grill_prompt(_sess(rd), t, intent)
        assert out, f"正例 {t!r}（intent={intent}）应触发澄清"
        assert "ask_user" in out and "有数据吗" in out


def test_grill_negative_matrix(server, tmp_path):
    rd = str(tmp_path / "gn")
    for t in GRILL_NEG:
        intent, _, _ = server._classify_intent(t)
        out = server._build_grill_prompt(_sess(rd), t, intent)
        assert out == "", f"反例 {t!r}（intent={intent}）不应触发: {out[:60]}"


def test_grill_edge_matrix(server, tmp_path):
    rd = str(tmp_path / "ge")
    for t, expect_trigger in GRILL_EDGE:
        intent, _, _ = server._classify_intent(t)
        out = server._build_grill_prompt(_sess(rd), t, intent)
        assert bool(out) == expect_trigger, \
            f"边界 {t!r}（intent={intent}）期望触发={expect_trigger}，实际={bool(out)}"


def test_grill_all_exec_intents_consistent(server, tmp_path):
    """三种执行意图无路径都触发；且触发内容一致（含 4 问清单）。"""
    rd = str(tmp_path / "gc")
    outs = {i: server._build_grill_prompt(_sess(rd), "帮我做个分析", i)
            for i in ("analysis", "direct_exec", "research_plan")}
    for i, o in outs.items():
        assert o, f"{i} 应触发"
        for kw in ("有数据吗", "物种", "期望得到什么结果", "继续之前的任务"):
            assert kw in o, f"{i} 缺清单项 {kw}"


# ═══════════════════════════════════════════════════════════════════════════
# B. 链路组装端到端
# ═══════════════════════════════════════════════════════════════════════════

def test_full_assembly_injection(server, tmp_path):
    """完整用户回合组装：grill 注入顺序与策略可见。"""
    rd = str(tmp_path / "fa")
    sess = _sess(rd)
    intent, _, _ = server._classify_intent("帮我做单细胞聚类分析")
    hist = []
    try:
        _kb = server._build_kb_tail_injection("帮我做单细胞聚类分析", intent, False)
        if _kb:
            hist.append(("kb", _kb))
    except Exception:
        pass
    _grill = server._build_grill_prompt(sess, "帮我做单细胞聚类分析", intent)
    if _grill:
        hist.append(("grill", _grill))
    _resume = server._build_task_resume_prompt(sess)
    if _resume:
        hist.append(("resume", _resume))
    kinds = [k for k, _ in hist]
    assert "grill" in kinds, "必须注入 grill"
    assert kinds.index("grill") <= kinds.index("resume") if "resume" in kinds else True, \
        "grill 应在 resume 之前（先澄清再通报）"
    assert "执行策略（用户优先" in server._EXECUTION_POLICY


def test_grill_plus_requirements_path_suppression(server, tmp_path):
    """REQUIREMENTS 有路径 → 即使当前消息无路径也不触发（记忆兜底）。"""
    rd = str(tmp_path / "gs")
    sess = _sess(rd, reqs=["数据在 E:/known_data"])
    intent, _, _ = server._classify_intent("继续跑聚类")
    out = server._build_grill_prompt(sess, "继续跑聚类", intent)
    assert out == "", "REQUIREMENTS 有路径时不应触发 grill"


# ═══════════════════════════════════════════════════════════════════════════
# C. ask_user options 极端
# ═══════════════════════════════════════════════════════════════════════════

def test_ask_user_options_extreme(monkeypatch):
    import server as _server
    sess = {"id": "sx", "_pending_questions": []}
    monkeypatch.setattr(_server, "_sessions", {"sx": sess})
    monkeypatch.setattr(_server, "_session_emit", lambda s, m: None)
    monkeypatch.setattr(ask_user_mod, "_session_context", lambda: ("sx", ""))

    # 超多选项 → 截断 6
    r = json.loads(ask_user_mod.ask_user("q", options=[f"o{i}" for i in range(20)]))
    assert len(r["options"]) == 6
    # 重复选项 → 保留（截断即可，不强制去重）
    r2 = json.loads(ask_user_mod.ask_user("q", options=["same", "same", "same"]))
    assert len(r2["options"]) == 3
    # 超长选项 → 截 80 字
    r3 = json.loads(ask_user_mod.ask_user("q", options=["长" * 200]))
    assert len(r3["options"][0]) <= 80
    # emoji/特殊字符选项不炸
    r4 = json.loads(ask_user_mod.ask_user("q", options=["🧬 继续", "<tag>", "a'b\"c"]))
    assert r4["ok"] is True and len(r4["options"]) == 3
    # 非列表 options → 忽略
    r5 = json.loads(ask_user_mod.ask_user("q", options="not-a-list"))
    assert r5["options"] == []
    # None options → 无
    r6 = json.loads(ask_user_mod.ask_user("q"))
    assert r6["options"] == []


def test_ask_user_options_concurrent(monkeypatch):
    """并发 ask_user 带 options：pending 上限保持、无损坏。"""
    import server as _server
    sess = {"id": "sx2", "_pending_questions": []}
    monkeypatch.setattr(_server, "_sessions", {"sx2": sess})
    monkeypatch.setattr(_server, "_session_emit", lambda s, m: None)
    monkeypatch.setattr(ask_user_mod, "_session_context", lambda: ("sx2", ""))
    errors = []

    def _w(i):
        try:
            for j in range(8):
                json.loads(ask_user_mod.ask_user(f"q{i}-{j}", options=["A", "B", "C"]))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=_w, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(sess["_pending_questions"]) == 20
    assert all(len(r["options"]) == 3 for r in sess["_pending_questions"])


# ═══════════════════════════════════════════════════════════════════════════
# D. 策略完备
# ═══════════════════════════════════════════════════════════════════════════

def test_policy_six_sections(server):
    p = server._EXECUTION_POLICY
    for i in range(1, 7):
        assert f"### {i}." in p
    pairs = [
        ("中途问的问题 ≠ 打断", "任务本身继续"),
        ("开工前先问清楚", "一次问清比十次返工便宜"),
        ("一切以用户为主", "用户回答后继续"),
        ("报错停止后", "由用户决定"),
        ("自动续跑轮", "允许的自主行为"),
    ]
    for a, b in pairs:
        assert a in p and b in p


# ═══════════════════════════════════════════════════════════════════════════
# E. 跨机制共存
# ═══════════════════════════════════════════════════════════════════════════

def test_grill_vs_investigate_no_conflict(server, tmp_path):
    """调查请求（investigate）→ 不触发 grill；执行请求才触发。"""
    rd = str(tmp_path / "mx")
    for t in ("检查为什么报错", "排查一下原因", "看下日志分析原因"):
        intent, _, _ = server._classify_intent(t)
        assert intent == "investigate"
        assert server._build_grill_prompt(_sess(rd), t, intent) == "", \
            f"调查请求 {t!r} 不得触发开工澄清"
    for t in ("帮我做分析", "跑个聚类"):
        intent, _, _ = server._classify_intent(t)
        if intent in ("analysis", "direct_exec", "research_plan"):
            assert server._build_grill_prompt(_sess(rd), t, intent), \
                f"执行请求 {t!r} 应触发澄清"


def test_grill_then_path_remembered(server, tmp_path):
    """grill 问出路径 → 用户回答 → 路径默认全录 → 后续不再 grill（闭环）。"""
    rd = str(tmp_path / "m2")
    # 第一轮：无路径 → 触发
    intent, _, _ = server._classify_intent("帮我做单细胞聚类分析")
    assert server._build_grill_prompt(_sess(rd), "帮我做单细胞聚类分析", intent)
    # 用户回答提供路径 → 写入 REQUIREMENTS
    server._extract_and_store_requirements(_sess(rd), "数据在 E:/scRNA/matrix.mtx")
    sess = _sess(rd, reqs=["数据在 E:/scRNA/matrix.mtx"])
    # 第二轮：REQUIREMENTS 有路径 → 不触发
    assert server._build_grill_prompt(sess, "开始分析", intent) == "", \
        "问出路径并入库后不应再触发 grill"
