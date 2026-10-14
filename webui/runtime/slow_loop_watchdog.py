"""事件循环慢调用看门狗（2026-10-13）。

背景：用户反馈"会话卡住、暂停也不立即生效"。实测抓到 `/api/sessions`（纯内存遍历，
正常 0.03s）耗时 **33.4s** —— 说明事件循环被某个**同步重活**堵住，而不是接口本身慢。

本模块把这类"神秘卡顿"变成可定位日志：
  · 事件循环里跑一个 0.25s 心跳（调用 `heartbeat()`）；
  · 一条守护线程采样：心跳超过阈值没动 → 判定阻塞；
  · 阻塞瞬间抓**主线程 Python 调用栈**（`sys._current_frames`）→ 直接指出堵在哪一行；
  · 恢复时补一条"阻塞结束：约 N 秒"。

零依赖、只读、异常全部吞掉，绝不影响主流程。
日志默认 `<root>/log/slow_loop.log`（阈值可用 MEMOMICS_SLOW_LOOP_SEC 覆盖）。
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback

DEFAULT_THRESHOLD_SEC = float(os.environ.get("MEMOMICS_SLOW_LOOP_SEC", "2.0"))
SAMPLE_INTERVAL_SEC = 0.5


class SlowLoopWatchdog:
    """监控 asyncio 事件循环是否被同步调用堵住，并把调用栈写进日志。"""

    def __init__(self, log_path: str, *, threshold: float = DEFAULT_THRESHOLD_SEC) -> None:
        self.log_path = log_path
        self.threshold = max(0.2, float(threshold))
        self._hb = time.monotonic()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- 事件循环侧 ---
    def heartbeat(self) -> None:
        self._hb = time.monotonic()

    # --- 生命周期 ---
    def start(self) -> "SlowLoopWatchdog":
        try:
            d = os.path.dirname(self.log_path)
            if d:
                os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        self._thread = threading.Thread(target=self._loop, name="slow-loop-watchdog", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    # --- 内部 ---
    def _log(self, text: str) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
        except OSError:
            pass

    def _stacks(self) -> str:
        out: list[str] = []
        try:
            frames = sys._current_frames()
            names = {t.ident: t.name for t in threading.enumerate()}
            for tid, frame in frames.items():
                out.append("--- thread %s (%s) ---" % (tid, names.get(tid, "?")))
                out.extend("    " + ln.rstrip() for ln in traceback.format_stack(frame, limit=12))
        except Exception as exc:  # noqa: BLE001 - 诊断代码，绝不抛出
            out.append("(stack 抓取失败: %r)" % (exc,))
        return "\n".join(out)

    def _loop(self) -> None:
        in_stall = False
        stall_start = 0.0
        while not self._stop.is_set():
            time.sleep(SAMPLE_INTERVAL_SEC)
            now = time.monotonic()
            gap = now - self._hb
            if gap > self.threshold:
                if not in_stall:
                    in_stall = True
                    stall_start = now - gap
                    self._log("=== 事件循环阻塞开始（心跳停了 >%.1fs）===" % self.threshold)
                    self._log(self._stacks())
            elif in_stall:
                in_stall = False
                self._log("=== 阻塞结束：约 %.1f 秒 ===" % (now - stall_start))


def start_watchdog(root_dir: str) -> SlowLoopWatchdog:
    """按约定路径启动看门狗（<root>/log/slow_loop.log）。"""
    return SlowLoopWatchdog(os.path.join(root_dir, "log", "slow_loop.log")).start()