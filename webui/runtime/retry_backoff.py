"""工具失败指数退避（P1-B）— 治"报错没人管、死循环重试"。

设计（照搬 LoopX scheduler 退避思想，适配 MemOmics 交互式）：
  - 连续失败按 2s/5s/15s/45s 指数退避，之后停止硬重试
  - wait_interruptible 分段 sleep，每段检查中断回调 —— 点"停止"不会卡死
  - 连续 3 次失败后把结构化错误喂给 LLM 换方案（build_structured_error）
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

logger = logging.getLogger("memomics.retry_backoff")

DEFAULT_DELAYS = (2, 5, 15, 45)  # 秒
MAX_FAILURES = 3  # 连续失败 3 次后不再硬重试（换方案）


class RetryBackoff:
    def __init__(self, base_delays: tuple = DEFAULT_DELAYS, max_failures: int = MAX_FAILURES):
        self.base_delays = tuple(base_delays)
        self.max_failures = max_failures

    def next_delay(self, failure_count: int) -> float:
        """第 failure_count 次失败后的等待秒数（1-based）。超界取最大值。"""
        idx = max(0, failure_count - 1)
        if idx >= len(self.base_delays):
            return float(self.base_delays[-1])
        return float(self.base_delays[idx])

    def exhausted(self, failure_count: int) -> bool:
        """连续失败次数是否已到上限（应停止硬重试，换方案）。"""
        return failure_count >= self.max_failures

    def wait_interruptible(self, delay: float,
                           interrupt_check: Optional[Callable[[], bool]] = None) -> bool:
        """分段 sleep（每段 ≤0.2s）并检查中断回调；被中断返回 False。

        用途：点"停止"后最多 0.2s 内响应，不会卡在长 sleep 里。
        """
        end = time.time() + delay
        while time.time() < end:
            if interrupt_check and interrupt_check():
                return False
            time.sleep(min(0.2, end - time.time()))
        return True


def build_structured_error(command: str, exit_code: Optional[int],
                           traceback_tail: str, stderr_tail: str = "") -> dict:
    """把工具失败组织成结构化错误（供 LLM 换方案，而非只看一行日志）。

    字段：command / exit_code / traceback_tail（后 30 行）/ stderr_tail（后 20 行）
          / suggested_actions（由上层补充，如'检查路径/换参数/分步执行'）
    """
    return {
        "kind": "tool_failure",
        "command": command or "",
        "exit_code": exit_code,
        "traceback_tail": (traceback_tail or "").strip()[-4000:],
        "stderr_tail": (stderr_tail or "").strip()[-2000:],
    }
