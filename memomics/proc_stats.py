"""进程级 CPU/内存/IO 采样（Windows/Linux/macOS 统一，psutil 实现）。

用途（2026-08-16，用户要求）：科研任务（几十 GB readRDS / 大矩阵 / 长计算）
单工具调用可跑数十分钟，期间无任何流式事件。判定"真在干活"还是"真卡死"
只靠进程证据：
  - cpu_seconds 累计增长 → 进程在计算
  - io_read/io_write 字节增长 → 进程在推进 I/O（读大文件/写盘）
  两者都冻结 → 死锁/挂起（此时唤醒 AI 诊断解决，而不是直接暂停回合）。

Windows/Linux 统一走 psutil（.venv 已含 7.2.2）；psutil 缺失或进程无权限时
返回 None（调用方按"无证据"降级，不误判）。
"""
from __future__ import annotations

import time

_PSUTIL_OK = True
try:
    import psutil  # noqa: F401
except Exception:
    _PSUTIL_OK = False


def sample_process(pid) -> dict | None:
    """采样单个进程。

    返回 {'pid', 'alive', 'cpu_seconds', 'rss_bytes', 'io_read', 'io_write', 'at'}。
    进程不存在/无权限/psutil 不可用 → None 或 alive=False（调用方按"无证据"处理）。
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if not _PSUTIL_OK:
        return None
    try:
        p = psutil.Process(pid)
        if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
            return {"pid": pid, "alive": False, "at": time.time()}
        ct = p.cpu_times()
        mi = p.memory_info()
        _io = None
        try:
            _io = p.io_counters()
        except Exception:
            pass
        return {
            "pid": pid,
            "alive": True,
            "cpu_seconds": float(getattr(ct, "user", 0.0) + getattr(ct, "system", 0.0)),
            "rss_bytes": int(getattr(mi, "rss", 0) or 0),
            "io_read": int(_io.read_bytes) if _io else 0,
            "io_write": int(_io.write_bytes) if _io else 0,
            "at": time.time(),
        }
    except Exception:
        return None


def sample_processes(pids) -> list:
    """批量采样：过滤 None / 死进程，只留存活样本。"""
    return [s for s in (sample_process(p) for p in (pids or [])) if s and s.get("alive")]
