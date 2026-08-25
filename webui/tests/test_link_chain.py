# -*- coding: utf-8 -*-
"""上下系统链路回归测试（2026-08-25 链路审计修复）。

审计发现：grill 触发（执行请求+无数据路径）时 task_plan 仍被自动创建 →
用户还没确认数据就产生"幽灵任务"；且 plan_ctx+resume 重复注入。
修复：grill 场景抑制自动建 plan → 注入链只剩 grill 一条（先问清楚），
用户确认数据后下一轮才建 plan、注入任务状态。
"""
import os
import re
import shutil

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def server():
    import server as _s
    return _s


def _mk_sess(tmp_path, user_text, intent="analysis"):
    rd = str(tmp_path / "results")
    os.makedirs(rd, exist_ok=True)
    s = {"id": "link-t", "results_dir": rd, "todos": [], "messages": [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好。"},
        {"role": "user", "content": user_text},
    ]}
    s["intent"] = intent
    return s, os.path.join(rd, "task_plan.md")


def _assemble(server, sess, user_text):
    """模拟 run_agent 注入组装（真实顺序）。"""
    hist = []
    try:
        kb = server._build_kb_tail_injection(user_text, sess.get("intent", ""), False)
        if kb:
            hist.append(("kb", kb))
    except Exception:
        pass
    try:
        grill = server._build_grill_prompt(sess, user_text, sess.get("intent", ""))
        if grill:
            hist.append(("grill", grill))
    except Exception:
        pass
    try:
        plan_ctx = server._build_task_plan_context(sess)
        if plan_ctx:
            hist.append(("plan_ctx", plan_ctx))
    except Exception:
        pass
    try:
        resume = server._build_task_resume_prompt(sess)
        if resume:
            hist.append(("resume", resume))
    except Exception:
        pass
    return hist


def test_grill_scene_clean_injection(server, tmp_path):
    """grill 场景：只注入 grill 一条——不建幽灵 plan、不重复任务状态。"""
    sess, plan = _mk_sess(tmp_path, "帮我做单细胞聚类分析")
    hist = _assemble(server, sess, "帮我做单细胞聚类分析")
    kinds = [k for k, _ in hist]
    assert "grill" in kinds
    assert not os.path.isfile(plan), "grill 场景不得自动创建 task_plan（幽灵任务）"
    assert "plan_ctx" not in kinds, "无 plan 时不得注入 plan_ctx"
    assert "resume" not in kinds, "无 plan/todos 时 resume 应为空"


def test_with_path_scene_creates_plan(server, tmp_path):
    """有数据路径 → grill 不触发 → 正常建 plan + 任务状态注入。"""
    sess, plan = _mk_sess(tmp_path, "用 E:/data/matrix.mtx 跑聚类")
    hist = _assemble(server, sess, "用 E:/data/matrix.mtx 跑聚类")
    kinds = [k for k, _ in hist]
    assert "grill" not in kinds
    assert os.path.isfile(plan), "有路径应自动建 task_plan"
    assert "plan_ctx" in kinds, "有 plan 应注入任务状态"


def test_requirements_path_scene(server, tmp_path):
    """REQUIREMENTS 已有路径 → 不 grill、正常建 plan。"""
    rd = str(tmp_path / "results")
    os.makedirs(rd, exist_ok=True)
    with open(os.path.join(rd, "REQUIREMENTS.md"), "w", encoding="utf-8") as f:
        f.write("数据在 E:/known\n")
    sess = {"id": "link-r", "results_dir": rd, "todos": [], "messages": [
        {"role": "user", "content": "继续"},
        {"role": "assistant", "content": "好"},
        {"role": "user", "content": "帮我做单细胞聚类分析"},
    ]}
    sess["intent"] = "analysis"
    hist = _assemble(server, sess, "帮我做单细胞聚类分析")
    kinds = [k for k, _ in hist]
    assert "grill" not in kinds, "REQUIREMENTS 有路径不触发 grill"
    assert "plan_ctx" in kinds


def test_after_grill_answer_creates_plan(server, tmp_path):
    """grill 问出路径 → 用户回答 → 下一轮建 plan（闭环，不残留幽灵）。"""
    rd = str(tmp_path / "results")
    os.makedirs(rd, exist_ok=True)
    # 第一轮：无路径 → grill，不建 plan
    sess = {"id": "link-c", "results_dir": rd, "todos": [], "messages": [
        {"role": "user", "content": "帮我做单细胞聚类分析"},
    ]}
    sess["intent"] = "analysis"
    server._extract_and_store_requirements(sess, "数据在 E:/scRNA/matrix.mtx")
    # 第二轮：REQUIREMENTS 有路径 → 建 plan
    sess["messages"].append({"role": "user", "content": "开始分析"})
    sess["intent"] = "analysis"
    plan = os.path.join(rd, "task_plan.md")
    ctx = server._build_task_plan_context(sess)
    assert os.path.isfile(plan), "用户确认数据后应建 task_plan"
    assert ctx


def test_grill_suppression_does_not_break_light(server, tmp_path):
    """轻量意图不受抑制逻辑影响（不建 plan 是原行为）。"""
    sess, plan = _mk_sess(tmp_path, "这个参数怎么设", intent="knowledge_ask")
    hist = _assemble(server, sess, "这个参数怎么设")
    kinds = [k for k, _ in hist]
    assert "grill" not in kinds and "plan_ctx" not in kinds
    assert not os.path.isfile(plan)
