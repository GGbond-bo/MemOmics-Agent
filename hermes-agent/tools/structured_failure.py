"""工具失败结构化注入（P1-B 接入点）— terminal 失败时给 LLM 结构化纠错信号。

设计：
  - 每个 task_id 维护连续失败计数（线程安全，全局 dict）。
  - 连续失败 < 3 次：在输出前附加简短结构化错误块（command/exit_code/建议）。
  - 连续失败 ≥ 3 次：明示"连续失败，建议更换方案/分步执行"，防止死循环硬重试。
  - 成功（exit_code==0）时清零计数。
  - 本模块不抛异常、不阻塞：任何内部错误静默降级为原输出。

与 runtime/retry_backoff.py 的关系：retry_backoff 提供退避原语与结构化错误构建，
本模块是 hermes-agent 工具层的接入适配（按 task_id 计数 + 注入文本）。
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger("memomics.structured_failure")

MAX_CONSECUTIVE = 3  # 连续失败上限（与 runtime.retry_backoff.MAX_FAILURES 一致）

_fail_counts: Dict[str, int] = {}
_lock = threading.Lock()


def note_failure(task_id: str) -> int:
    """记录一次失败，返回当前连续失败次数。"""
    with _lock:
        _fail_counts[task_id] = _fail_counts.get(task_id, 0) + 1
        return _fail_counts[task_id]


def reset_failures(task_id: str) -> None:
    """成功时清零连续失败计数。"""
    with _lock:
        _fail_counts.pop(task_id, None)


def current_count(task_id: str) -> int:
    with _lock:
        return _fail_counts.get(task_id, 0)


def build_failure_note(command: str, exit_code: int, output_tail: str,
                       count: int, meaning: Optional[str] = None) -> str:
    """构建注入输出前的结构化错误块（LLM 可直接据此换方案）。"""
    lines = [
        "⚠️ [结构化错误]",
        f"命令: {command[:300]}",
        f"退出码: {exit_code}",
    ]
    if meaning:
        lines.append(f"语义: {meaning}")
    if count >= MAX_CONSECUTIVE:
        lines.append(
            f"连续失败 {count} 次（上限 {MAX_CONSECUTIVE}）。"
            "请停止重复同一命令，改换方案：检查路径/参数、分步执行、"
            "或用 write_file 先写脚本再运行。"
        )
    else:
        lines.append(f"连续失败 {count}/{MAX_CONSECUTIVE}。检查后重试或调整参数。")
    tail = (output_tail or "").strip().splitlines()
    if tail:
        lines.append("错误尾部:")
        lines.extend("  " + ln[:200] for ln in tail[-8:])
    return "\n".join(lines)


def inject_failure_note(result_dict: dict, command: str, exit_code: int,
                        task_id: str, meaning: Optional[str] = None) -> dict:
    """在 terminal 结果 dict 上附加结构化错误块。

    原地修改 output 字段（前缀注入），保留其余字段不变（返回 schema 兼容）。
    """
    try:
        if exit_code in (0, None):
            reset_failures(task_id)
            return result_dict
        count = note_failure(task_id)
        note = build_failure_note(command, exit_code,
                                  str(result_dict.get("output") or ""),
                                  count, meaning)
        old_output = str(result_dict.get("output") or "")
        result_dict["output"] = (note + "\n\n--- 原始输出 ---\n" + old_output)[:8000]
        result_dict["consecutive_failures"] = count
        return result_dict
    except Exception:
        # 注入失败绝不影响原结果
        return result_dict
