# -*- coding: utf-8 -*-
"""任务目标持久层回归测试（链路审计修复，2026-08-25）。

实证发现：执行类意图无数据路径时（"帮我做单细胞聚类分析"）task_plan 不自动
创建——`_is_exec` 引用了不存在的意图 "analysis_exec"（恒 False），任务目标没有
服务器兜底。修复后用真实意图列表，执行意图即使无路径也自动建 task_plan
（Goal = 用户原话前 80 字），目标持久化 + 每轮注入（_build_task_plan_context）。
"""
import os
import shutil

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def server():
    import server as _s
    return _s


def _mk_sess(tmp_path, intent, user_text):
    rd = str(tmp_path / "results")
    os.makedirs(rd, exist_ok=True)
    s = {"id": "goal-t", "results_dir": rd, "todos": [], "messages": [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好。"},
        {"role": "user", "content": user_text},
    ]}
    s["intent"] = intent
    return s, os.path.join(rd, "task_plan.md")


@pytest.fixture()
def tmp(tmp_path):
    yield tmp_path
    shutil.rmtree(str(tmp_path), ignore_errors=True)


def test_goal_only_exec_request_auto_creates_plan(server, tmp):
    """无数据路径的执行请求 → task_plan 自动创建（Goal 持久化）。"""
    for intent in ("analysis", "direct_exec", "research_plan"):
        sess, plan = _mk_sess(tmp, intent, "帮我做单细胞聚类分析，用 marker 基因注释")
        ctx = server._build_task_plan_context(sess)
        assert os.path.isfile(plan), f"intent={intent} 应自动创建 task_plan"
        assert ctx, "创建后应返回注入内容"
        with open(plan, encoding="utf-8") as f:
            content = f.read()
        assert "单细胞聚类" in content, f"Goal 应含用户目标: {content[:120]}"


def test_path_exec_request_auto_creates_plan(server, tmp):
    sess, plan = _mk_sess(tmp, "analysis", "用 E:/data/matrix.mtx 跑聚类")
    server._build_task_plan_context(sess)
    assert os.path.isfile(plan)


def test_light_intents_do_not_create_plan(server, tmp):
    """轻量意图（问路线/查进度/闲聊）不自动建 plan——不误伤。"""
    for intent, text in [
        ("analysis_plan", "这个数据怎么分析比较好"),
        ("knowledge_ask", "聚类分辨率参数怎么选"),
        ("chat", "今天天气不错"),
        ("progress_check", "跑到哪一步了"),
    ]:
        sess, plan = _mk_sess(tmp, intent, text)
        ctx = server._build_task_plan_context(sess)
        assert not os.path.isfile(plan), f"intent={intent} 不应自动创建 task_plan"
        assert ctx in (None, False, "")


def test_existing_plan_reused(server, tmp):
    """已有 task_plan → 复用不覆盖。"""
    sess, plan = _mk_sess(tmp, "analysis", "继续跑聚类")
    with open(plan, "w", encoding="utf-8") as f:
        f.write("# Goal\n用户自写目标\n\n## Phase 1\n- [x] 完成\n")
    ctx = server._build_task_plan_context(sess)
    with open(plan, encoding="utf-8") as f:
        content = f.read()
    assert "用户自写目标" in content, "已有 plan 不得被覆盖"
    assert ctx


def test_goal_survives_in_digest_path(server, tmp):
    """任务目标经 task_plan 持久后，折叠 checkpoint/唤醒上下文可见（链路闭环）。"""
    sess, plan = _mk_sess(tmp, "analysis", "帮我做跨物种 ATAC 保守性分析")
    server._build_task_plan_context(sess)
    # task_plan 摘要注入（_build_task_plan_context 返回）含目标
    ctx = server._build_task_plan_context(sess) or ""
    assert "ATAC" in ctx or "跨物种" in ctx
