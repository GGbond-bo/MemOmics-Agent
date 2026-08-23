"""任务完成闸门（P1-A）— 确定性 task_state 状态机，替代 task_plan.md 文本词判定。

背景：_schedule_self_check 自唤醒看门狗靠 task_plan.md 文本标记（"completed/完成"）
判定任务是否完成，文本不可靠且 session dict 是内存态（server 重启即丢），
导致"老任务被自动重启"。本模块把完成状态落盘为显式状态机：
  - 状态文件：<results_dir>/.task_state.json（磁盘持久化，server 重启不丢）
  - 状态迁移：pending → running → done | blocked →（用户新消息）→ pending
  - 闸门规则：task_state == done 时拒绝一切自动唤醒（self-check / watchdog）；
    只有用户主动发新消息才重置为 pending（用户主动 = 新指令，不算自动重启）。

设计原则：纯逻辑模块，不 import webui/server，可独立单测；所有失败返回安全默认
（默认放行 run，绝不因本模块故障阻断正常对话）。
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional, Tuple

logger = logging.getLogger("memomics.run_gate")

STATE_FILE = ".task_state.json"
VALID_STATES = ("pending", "running", "done", "blocked", "cancelled")
# 任务类型（2026-08-16）：normal=普通任务（画图/轻量分析，默认）；
# long_running=长任务管线（后台进程/心跳监督）。运行时证据自动升级，不降级。
VALID_TASK_CLASSES = ("normal", "long_running")

# 判"用户显式继续/新任务"的最小词表（命中才重置退役状态）
RESET_HINT_WORDS = ("继续", "接着", "下一步", "新任务", "换一个", "重跑", "重新",
                    "continue", "next", "new task", "restart", "重新开始", "开始做")


def _state_path(results_dir: str) -> str:
    return os.path.join(results_dir, STATE_FILE)


def load_state(results_dir: str) -> dict:
    """读取落盘状态；文件缺失/损坏返回 {'state': 'pending'}（安全默认：视为新任务）。"""
    default = {"state": "pending", "reason": "", "updated_at": 0.0, "task_class": "normal"}
    if not results_dir:
        return default
    try:
        with open(_state_path(results_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("state") not in VALID_STATES:
            return default
        if data.get("task_class") not in VALID_TASK_CLASSES:
            data["task_class"] = "normal"
        return data
    except FileNotFoundError:
        return default
    except Exception:
        logger.warning("[RunGate] 读取 task_state 失败，按 pending 处理", exc_info=True)
        return default


def save_state(results_dir: str, state: str, reason: str = "") -> bool:
    """写入落盘状态（原子写：先写临时文件再 rename）。失败返回 False（不抛异常）。"""
    if state not in VALID_STATES:
        return False
    if not results_dir:
        return False
    try:
        os.makedirs(results_dir, exist_ok=True)
        # 保留任务类型（save_state 不得清掉 long_running 标记）
        _existing = load_state(results_dir)
        payload = {"state": state, "reason": reason, "updated_at": time.time(),
                   "task_class": _existing.get("task_class", "normal")}
        tmp = _state_path(results_dir) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, _state_path(results_dir))
        logger.info("[RunGate] %s -> %s (%s)", os.path.basename(results_dir), state, reason)
        return True
    except Exception:
        logger.warning("[RunGate] 写入 task_state 失败", exc_info=True)
        return False


def mark_done(results_dir: str, reason: str = "task completed") -> bool:
    """显式置 done —— 由完成信号（文本判定/agent 汇报）触发，只写一次。"""
    return save_state(results_dir, "done", reason)


def mark_running(results_dir: str, reason: str = "task started") -> bool:
    return save_state(results_dir, "running", reason)


def mark_blocked(results_dir: str, reason: str = "task blocked") -> bool:
    return save_state(results_dir, "blocked", reason)


def mark_cancelled(results_dir: str, reason: str = "user cancelled") -> bool:
    """用户放弃任务 → 确定性标记 cancelled（退役：自动唤醒不再恢复）。"""
    return save_state(results_dir, "cancelled", reason)


def is_done(results_dir: str) -> bool:
    return load_state(results_dir).get("state") == "done"


def is_retired(results_dir: str) -> bool:
    """任务是否已退役（完成或放弃）—— 退役状态不得污染新任务。"""
    return load_state(results_dir).get("state") in ("done", "cancelled")


def get_task_class(results_dir: str) -> str:
    """当前任务类型：normal（默认，画图/轻量分析）| long_running（长任务管线）。"""
    return load_state(results_dir).get("task_class", "normal")


def set_task_class(results_dir: str, task_class: str) -> bool:
    """标记任务类型（运行时证据升级 long_running），不改变 state/reason。"""
    if task_class not in VALID_TASK_CLASSES or not results_dir:
        return False
    try:
        _st = load_state(results_dir)
        os.makedirs(results_dir, exist_ok=True)
        payload = {"state": _st.get("state", "pending"),
                   "reason": _st.get("reason", ""),
                   "updated_at": time.time(),
                   "task_class": task_class}
        tmp = _state_path(results_dir) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, _state_path(results_dir))
        logger.info("[RunGate] task_class -> %s (%s)", task_class, os.path.basename(results_dir))
        return True
    except Exception:
        logger.warning("[RunGate] 写入 task_class 失败", exc_info=True)
        return False


def user_restarts(results_dir: str, user_text: str) -> bool:
    """用户新消息是否算"显式继续/新任务"（命中才把 done 重置为 pending）。

    用户主动发消息本身即是新指令；此处仅做保守细化：命中词表立即重置，
    未命中时由 check_gate 返回 ask_user 而非直接放行。
    """
    if not user_text:
        return False
    t = user_text.lower().strip()
    return any(w in t for w in RESET_HINT_WORDS)


def check_gate(results_dir: str, *, interrupt_requested: bool = False,
               user_message: Optional[str] = None, is_auto_wake: bool = True) -> Tuple[str, str]:
    """每轮运行前的闸门判定。返回 (verdict, reason)。

    verdict:
      run       — 放行（新任务 / 用户显式继续 / 状态 running）
      stop      — 拒绝（task_state == done 的自动唤醒 / 中断置位）
      ask_user  — 状态 done 但用户发了消息且未命中词表：交由上层决定
                  （上层可发确认消息，或直接重置为新任务）

    is_auto_wake=True 表示本轮由 self-check/watchdog 触发（非用户消息）。
    """
    # 中断优先：任何路径都尊重中断
    if interrupt_requested:
        return "stop", "interrupt requested"

    st = load_state(results_dir)
    state = st.get("state", "pending")

    if state == "done" or state == "cancelled":
        if is_auto_wake:
            return "stop", f"task_state={state}: 自动唤醒被闸门拦截（任务已退役，防止重启）"
        # 用户消息路径
        if user_restarts(results_dir, user_message or ""):
            save_state(results_dir, "pending", "user explicitly restarted")
            return "run", "user explicitly restarted (task_state reset to pending)"
        return "ask_user", f"task_state={state}: 用户消息未命中继续词表，由上层决定是否开新任务"

    if state == "blocked":
        if is_auto_wake:
            # blocked 的自动唤醒：允许（看门狗可尝试恢复），但上限由上层控制
            return "run", "task_state=blocked: 允许自动唤醒尝试恢复"
        return "run", "user message on blocked task"

    # pending / running：自动唤醒与用户消息均放行
    return "run", f"task_state={state}: 放行"
