"""会话级单飞锁（P1-C）— 治"两会话长任务互踩"。

背景：results_dir 按会话隔离，但共享 analysis_dir/共享目录时心跳标记文件会串、
      _current_model 全局共享（A 切模型影响 B）。
方案：
  - per-sid 单飞锁：同会话并发运行互斥（try_lock 快速失败，不阻塞），
    异会话互不干扰（各拿各的锁）。
  - 全部锁带持有者 sid 标签；可查询任意会话是否在跑。
  - 线程安全（threading.Lock 保护注册表）。
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger("memomics.session_locks")


class SessionLocks:
    def __init__(self):
        self._registry: Dict[str, threading.Lock] = {}
        self._holders: Dict[str, str] = {}  # sid -> holder（默认 sid 自身）
        self._guard = threading.Lock()

    def _lock_for(self, sid: str) -> threading.Lock:
        with self._guard:
            if sid not in self._registry:
                self._registry[sid] = threading.Lock()
            return self._registry[sid]

    def lock(self, sid: str) -> threading.Lock:
        """阻塞式获取（同会话串行等待）。返回锁对象，调用方 with 使用。"""
        lock = self._lock_for(sid)
        lock.acquire()
        with self._guard:
            self._holders[sid] = sid
        return lock

    def try_lock(self, sid: str) -> Optional[threading.Lock]:
        """非阻塞获取：同会话正在跑 → 返回 None（快速失败，不排队）。
        这是单飞锁的核心语义：已有一个长任务在跑，第二个请求直接拒绝。"""
        lock = self._lock_for(sid)
        if not lock.acquire(blocking=False):
            return None
        with self._guard:
            self._holders[sid] = sid
        return lock

    def release(self, sid: str) -> None:
        """释放锁（仅当确实持有）。"""
        lock = self._registry.get(sid)
        if lock and lock.locked():
            try:
                lock.release()
            except RuntimeError:
                pass
        with self._guard:
            self._holders.pop(sid, None)

    def is_busy(self, sid: str) -> bool:
        lock = self._registry.get(sid)
        return bool(lock and lock.locked())
