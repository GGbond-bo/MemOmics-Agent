"""Supervision and observable state for per-session asyncio jobs."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any, Callable

logger = logging.getLogger("memomics.tasks")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobState(str, Enum):
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class SupervisedTask:
    job_id: str
    session_id: str
    task: asyncio.Task[Any]
    label: str = "agent"
    state: JobState = JobState.RUNNING
    created_at: str = field(default_factory=_utc_now)
    finished_at: str | None = None
    error: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "session_id": self.session_id,
            "label": self.label,
            "state": self.state.value,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


class TaskSupervisor:
    """监督会话级 asyncio 任务：注册/完成记账 + 完成事件监听（M1 事件驱动唤醒底座）。

    add_done_listener 注册的回调在任务进入终态后调用（带 record 快照），
    供上层做事件驱动唤醒（后台任务完成 → 立即调度 agent 自检），
    替代"定时轮询任务状态"。
    """

    def __init__(self, store=None) -> None:
        self._active: dict[str, SupervisedTask] = {}
        self._history: list[dict[str, Any]] = []
        self._done_listeners: list[Callable[[dict[str, Any]], Any]] = []
        self._lock = RLock()
        self._store = store

    def add_done_listener(self, fn: Callable[[dict[str, Any]], Any]) -> None:
        """注册任务完成监听器。fn(record: dict) 在任务终态确定后调用（锁外）。"""
        with self._lock:
            self._done_listeners.append(fn)

    def _notify_done(self, record: dict[str, Any]) -> None:
        """锁外通知所有完成监听器（单个异常不阻断其余监听器）。"""
        for fn in list(self._done_listeners):
            try:
                fn(dict(record))
            except Exception:
                logger.warning("tasks: done listener threw for job %s", record.get("job_id"), exc_info=True)

    def register(
        self, session_id: str, task: asyncio.Task[Any], label: str = "agent"
    ) -> SupervisedTask:
        with self._lock:
            existing = self._active.get(session_id)
            if existing and not existing.task.done():
                raise RuntimeError(f"Session {session_id} already has an active task")
            persisted = self._store.start(session_id, label) if self._store else None
            record = SupervisedTask(
                job_id=(persisted or {}).get("job_id", f"runtime-{id(task)}"),
                session_id=session_id,
                task=task,
                label=label,
            )
            self._active[session_id] = record
        task.add_done_callback(lambda completed: self._on_done(session_id, completed))
        return record

    def _on_done(self, session_id: str, task: asyncio.Task[Any]) -> None:
        with self._lock:
            record = self._active.get(session_id)
            if record is None or record.task is not task:
                return
            record.finished_at = _utc_now()
            if task.cancelled():
                record.state = JobState.CANCELLED
            else:
                try:
                    error = task.exception()
                except asyncio.CancelledError:
                    error = None
                    record.state = JobState.CANCELLED
                if error is not None:
                    record.state = JobState.FAILED
                    record.error = f"{type(error).__name__}: {error}"
                elif record.state != JobState.CANCELLED:
                    record.state = JobState.SUCCEEDED
            self._history.append(record.public())
            self._history[:] = self._history[-200:]
            self._active.pop(session_id, None)
            done_snapshot = record.public()
        # 锁外落盘 + 事件通知（监听器可能回调 supervisor，不能持锁）
        if self._store:
            self._store.finish(
                record.job_id,
                record.state.value,
                error=record.error,
                termination_source=(
                    "user_cancel" if record.state == JobState.CANCELLED else None
                ),
            )
        self._notify_done(done_snapshot)

    def cancel(self, session_id: str) -> bool:
        with self._lock:
            record = self._active.get(session_id)
            if record is None or record.task.done():
                return False
            record.state = JobState.CANCELLING
            record.task.cancel()
            return True

    def is_running(self, session_id: str) -> bool:
        with self._lock:
            record = self._active.get(session_id)
            return bool(record and not record.task.done())

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._active.get(session_id)
            return record.public() if record else None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            snapshot = {
                "active": {sid: record.public() for sid, record in self._active.items()},
                "history": list(self._history),
            }
            if self._store:
                snapshot["durable_history"] = self._store.list(limit=200)
            return snapshot
