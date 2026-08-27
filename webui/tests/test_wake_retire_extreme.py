# -*- coding: utf-8 -*-
"""唤醒退役 / 重复输出 · 极端回归测试（2026-08-27 memomics-cd677556 实测修复）。

背景：task_plan 已标完成但 .task_state.json 被 ask_user 否定回答复活（pending+armed）
→ 唤醒链复活 → 模型被反复叫醒 → 同一回答重复输出 4 次。

覆盖矩阵：
A. task_plan 整体完成文本检测（_plan_is_complete_text）：完成变体 × 不误判变体
   （Phase 级"已完成"/"Status: complete"/in_progress 不得误判整体完成）
B. ask_user 否定/结束回答判定（_is_negation_end_answer）：否定命中 × 肯定不命中
C. RunGate 状态机矩阵（check_gate）：done/cancelled × 自动唤醒/用户消息/继续词/否定词/预算
D. 端到端场景组合（临时 results_dir）：完成→标记→否定回答不复活→继续词才恢复
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "webui"))

from webui.server import _plan_is_complete_text, _is_negation_end_answer  # noqa: E402
from webui.runtime import run_gate  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.memory]


# ═══════════════════════════════════════════════════════════════════════
# A. task_plan 整体完成文本检测矩阵
# ═══════════════════════════════════════════════════════════════════════

PLAN_COMPLETE_POS = [
    # 真实场景（memomics-cd677556）：Current Phase 段 + 任务状态段
    "## Current Phase\n全部完成（用户确认无长任务，08-27 标记完成）",
    "## 任务状态\n✅ **已完成** — 用户确认当前无长任务需要继续",
    "## 任务状态\n任务已完成，无待办",
    "全部完成，等待用户下一步指令",
    "已全部完成（用户确认无长任务）",
    "No active task, waiting for user",
    "No ACTIVE TASK",
    "All tasks complete",
    "## Current Phase\n任务结束",
    "确认无长任务，标记完成",
]


@pytest.mark.parametrize("text", PLAN_COMPLETE_POS)
def test_plan_complete_positive(text):
    assert _plan_is_complete_text(text), f"应判定整体完成: {text!r}"


PLAN_COMPLETE_NEG = [
    # Phase 级完成词不得误判整体完成（极端修复点）
    "## Phase 1\nPhase 1 已完成，Phase 2 pending",
    "Phase 1 已完成，等待 Phase 2",
    "## Phases\n### Phase 1: QC（已完成）\n### Phase 2: 聚类（进行中）",
    "### Phase 1 下载文章（已完成）\n### Phase 2: C25-29 亚群验证（in_progress）",
    "**Status:** complete\n**Status:** complete\n**Status:** in_progress",
    "## Current Phase\nPhase 2 进行中",
    "## 任务状态\nrunning",
    "in_progress: Phase 1 完成但 Phase 2 未开始",
    "已完成 1/3 阶段，剩余 2 个",
    "## Current Phase\n等待用户提供 RDS 后开始",
    "任务进行中：Cluster 1 已完成注释",
]


@pytest.mark.parametrize("text", PLAN_COMPLETE_NEG)
def test_plan_complete_negative(text):
    assert not _plan_is_complete_text(text), f"不应判定整体完成: {text!r}"


# ═══════════════════════════════════════════════════════════════════════
# B. ask_user 否定/结束回答判定矩阵
# ═══════════════════════════════════════════════════════════════════════

NEG_ANSWER_POS = [
    "不用了，先这样吧",
    "不需要继续了",
    "不用",
    "不做了",
    "算了，就到这",
    "先这样",
    "没有任务了",
    "没任务",
    "不用继续了",
    "暂停一下",
    "不要了",
    "先不做了",
    "嗯不用了谢谢",
]

NEG_ANSWER_NEG = [
    "好的，继续吧",
    "继续",
    "接着做",
    "下一步",
    "选A方案",
    "嗯，就按你说的做",
    "好的",
    "可以了，继续",
    "帮我跑一下",
    "新任务：分析这个数据",
]


@pytest.mark.parametrize("text", NEG_ANSWER_POS)
def test_negation_answer_positive(text):
    assert _is_negation_end_answer(text), f"应判定否定/结束: {text!r}"


@pytest.mark.parametrize("text", NEG_ANSWER_NEG)
def test_negation_answer_negative(text):
    assert not _is_negation_end_answer(text), f"不应判定否定: {text!r}"


# ═══════════════════════════════════════════════════════════════════════
# C. RunGate 状态机矩阵（check_gate 判定）
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture()
def rd(tmp_path):
    return str(tmp_path / "results-rg")


def _with_state(rd, state="pending", armed=True, rounds=0, maxr=256):
    run_gate.save_state(rd, state, "test", armed=armed, rounds_started=rounds, max_rounds=maxr)
    return rd


# C1: done 任务
def test_done_auto_wake_stopped(rd):
    _with_state(rd, "done")
    v, r = run_gate.check_gate(rd, is_auto_wake=True)
    assert v == "stop", f"done+自动唤醒必须 stop: {r}"


def test_done_user_continue_restarts(rd):
    _with_state(rd, "done")
    v, r = run_gate.check_gate(rd, is_auto_wake=False, user_message="继续做")
    assert v == "run", f"done+继续词应重置并放行: {r}"
    assert run_gate.load_state(rd)["state"] == "pending"


def test_done_user_negation_keeps_done(rd):
    _with_state(rd, "done")
    v, r = run_gate.check_gate(rd, is_auto_wake=False, user_message="不用了")
    assert v == "ask_user", f"done+否定词应返回 ask_user（由上层决定）: {r}"
    # 上层（server）逻辑：否定回答 → 不重置
    if _is_negation_end_answer("不用了"):
        assert run_gate.load_state(rd)["state"] == "done", "否定回答后状态必须保持 done"


def test_done_user_plain_keeps_done_until_decision(rd):
    _with_state(rd, "done")
    v, r = run_gate.check_gate(rd, is_auto_wake=False, user_message="帮我看看这个结果")
    assert v == "ask_user"
    # 上层：非否定非继续 → 旧逻辑重置 pending（新指令语义）；此处验证 check_gate 层不擅自重置
    assert run_gate.load_state(rd)["state"] == "done"


# C2: cancelled 同退役语义
def test_cancelled_auto_wake_stopped(rd):
    _with_state(rd, "cancelled")
    v, r = run_gate.check_gate(rd, is_auto_wake=True)
    assert v == "stop"


# C3: pending + 武装/预算
def test_pending_auto_wake_allowed_when_armed(rd):
    _with_state(rd, "pending", armed=True)
    v, r = run_gate.check_gate(rd, is_auto_wake=True)
    assert v == "run"


def test_pending_auto_wake_stopped_when_disarmed(rd):
    _with_state(rd, "pending", armed=False)
    v, r = run_gate.check_gate(rd, is_auto_wake=True)
    assert v == "stop", "未武装的自动唤醒必须 stop（重启后需用户消息授权）"


def test_round_budget_exhausted_stopped(rd):
    _with_state(rd, "pending", armed=True, rounds=256, maxr=256)
    v, r = run_gate.check_gate(rd, is_auto_wake=True)
    assert v == "stop", "预算耗尽自动唤醒必须 stop"


def test_round_budget_refreshed_by_user_message(rd):
    _with_state(rd, "pending", armed=True, rounds=256, maxr=256)
    v, r = run_gate.check_gate(rd, is_auto_wake=False, user_message="继续")
    assert v == "run"
    # 上层重置预算
    run_gate.reset_rounds(rd)
    assert run_gate.round_budget(rd)["rounds_started"] == 0


# C4: admit_round 对退役任务拒绝
def test_admit_round_rejects_done(rd):
    _with_state(rd, "done")
    assert run_gate.admit_round(rd) is False


def test_admit_round_rejects_cancelled(rd):
    _with_state(rd, "cancelled")
    assert run_gate.admit_round(rd) is False


def test_admit_round_counts_for_pending(rd):
    _with_state(rd, "pending", armed=True, rounds=0)
    assert run_gate.admit_round(rd) is True
    assert run_gate.round_budget(rd)["rounds_started"] == 1


# ═══════════════════════════════════════════════════════════════════════
# D. 端到端场景组合（模拟 memomics-cd677556 完整事件序列）
# ═══════════════════════════════════════════════════════════════════════

def _mk_plan(rd, complete=True, text=None):
    os.makedirs(rd, exist_ok=True)
    if text is None:
        text = ("# Task Plan: 验证\n## Current Phase\n"
                + ("全部完成（用户确认无长任务，08-27 标记完成）" if complete else "Phase 2 进行中")
                + "\n## 任务状态\n" + ("✅ 已完成" if complete else "in_progress"))
    with open(os.path.join(rd, "task_plan.md"), "w", encoding="utf-8") as f:
        f.write(text)
    return rd


def _wake_should_inject(rd):
    """模拟唤醒 else 分支守卫：task_plan 不存在或整体完成 → 不注入。"""
    plan = os.path.join(rd, "task_plan.md")
    if not os.path.isfile(plan):
        return False
    with open(plan, "r", encoding="utf-8") as f:
        return not _plan_is_complete_text(f.read())


def test_scene_complete_plan_no_inject(rd):
    _mk_plan(rd, complete=True)
    assert not _wake_should_inject(rd), "整体完成的 plan 不得注入唤醒（休息）"


def test_scene_incomplete_plan_injects(rd):
    _mk_plan(rd, complete=False)
    assert _wake_should_inject(rd), "进行中的 plan 应允许注入唤醒"


def test_scene_no_plan_no_inject(rd):
    assert not _wake_should_inject(rd), "无 task_plan 不得注入唤醒"


def test_scene_phase_completed_but_overall_running_injects(rd):
    # Phase 级完成词不得误判整体完成 → 仍可唤醒
    _mk_plan(rd, text="# Task Plan\n## Phases\n### Phase 1: QC（已完成）\n### Phase 2: 聚类（in_progress）")
    assert _wake_should_inject(rd)


def test_scene_full_lifecycle(rd):
    """完整生命周期：新任务 → 完成 → 否定回答保持退役 → 继续词才恢复。"""
    # 1. 新任务创建（用户消息）
    run_gate.save_state(rd, "pending", "new task", armed=True)
    assert run_gate.check_gate(rd, is_auto_wake=True)[0] == "run"
    # 2. 模型完成任务 → mark_done
    run_gate.mark_done(rd, "task completed")
    assert run_gate.is_retired(rd)
    # 3. 自动唤醒被拦
    assert run_gate.check_gate(rd, is_auto_wake=True)[0] == "stop"
    assert run_gate.admit_round(rd) is False
    # 4. 模型 ask_user → 用户否定回答 → 上层不复活
    v, _ = run_gate.check_gate(rd, is_auto_wake=False, user_message="不用了")
    assert v == "ask_user"
    if _is_negation_end_answer("不用了"):
        pass  # 上层跳过 save_state(pending)
    assert run_gate.is_retired(rd), "否定回答后必须保持退役"
    # 5. 用户明确继续 → 恢复
    v, _ = run_gate.check_gate(rd, is_auto_wake=False, user_message="继续做下一步")
    assert v == "run"
    assert run_gate.load_state(rd)["state"] == "pending"
