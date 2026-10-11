"""Cooperative CPU, memory and GPU admission control for analysis sessions."""

from __future__ import annotations

import asyncio
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    """时间戳一律 UTC ISO —— 和任务契约同一个写法（面板按同一套解析）"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ResourceCapacity:
    cpu_cores: int
    memory_gb: float
    gpu_slots: int = 0

    @classmethod
    def detect(cls) -> "ResourceCapacity":
        cpu = max(1, (os.cpu_count() or 2) - 1)
        # 显式覆盖：压小容量好复现排队（运维也能主动限流），不给就按机器来
        configured_cpu = os.environ.get("MEMOMICS_CPU_CORES")
        if configured_cpu:
            try:
                cpu = max(1, int(configured_cpu))
            except ValueError:
                pass
        memory = 8.0
        try:
            import psutil

            memory = max(
                1.0,
                round(psutil.virtual_memory().available / 1024**3 * 0.8, 1),
            )
        except Exception:
            pass
        configured_memory = os.environ.get("MEMOMICS_MEMORY_GB")
        if configured_memory:
            try:
                memory = max(0.5, float(configured_memory))
            except ValueError:
                pass
        configured_gpu_slots = os.environ.get("MEMOMICS_GPU_SLOTS")
        if configured_gpu_slots is not None:
            try:
                gpu_slots = max(0, int(configured_gpu_slots))
            except ValueError:
                gpu_slots = 0
        else:
            gpu_slots = 1 if shutil.which("nvidia-smi") else 0
        return cls(cpu_cores=cpu, memory_gb=memory, gpu_slots=gpu_slots)


@dataclass(frozen=True)
class ResourceRequest:
    cpu_cores: int = 1
    memory_gb: float = 2.0
    gpu_slots: int = 0

    def validate(self, capacity: ResourceCapacity) -> None:
        if self.cpu_cores < 1 or self.memory_gb <= 0 or self.gpu_slots < 0:
            raise ValueError("Resource values must be positive")
        if self.cpu_cores > capacity.cpu_cores:
            raise ValueError("Requested CPU exceeds scheduler capacity")
        if self.memory_gb > capacity.memory_gb:
            raise ValueError("Requested memory exceeds scheduler capacity")
        if self.gpu_slots > capacity.gpu_slots:
            raise ValueError("Requested GPU slots exceed scheduler capacity")


@dataclass(frozen=True)
class ResourceLease:
    lease_id: str
    session_id: str
    request: ResourceRequest
    label: str = ""
    acquired_at: str = ""
    acquired_monotonic: float = 0.0


@dataclass(frozen=True)
class QueuedWaiter:
    """排队记录：面板要能说清"谁在排、排第几、等了多久"。"""

    ticket: str
    session_id: str
    request: ResourceRequest
    label: str = ""
    enqueued_at: str = ""
    enqueued_monotonic: float = 0.0


class ResourceScheduler:
    """FIFO admission controller shared by all analysis sessions.

    严格 FIFO：队首不满足就**整队等着**，后到的小请求不插队 —— 所以面板上的
    "排第几"就是真实位次（这也意味着一个超大请求会挡住后面的人，是刻意保留的行为）。
    """

    def __init__(self, capacity: ResourceCapacity) -> None:
        self.capacity = capacity
        self._condition = asyncio.Condition()
        self._active: dict[str, ResourceLease] = {}
        self._waiting: list[QueuedWaiter] = []

    def _used(self) -> ResourceRequest:
        leases = self._active.values()
        return ResourceRequest(
            cpu_cores=sum(item.request.cpu_cores for item in leases),
            memory_gb=sum(item.request.memory_gb for item in leases),
            gpu_slots=sum(item.request.gpu_slots for item in leases),
        )

    def _fits(self, request: ResourceRequest) -> bool:
        used = self._used()
        return (
            used.cpu_cores + request.cpu_cores <= self.capacity.cpu_cores
            and used.memory_gb + request.memory_gb <= self.capacity.memory_gb
            and used.gpu_slots + request.gpu_slots <= self.capacity.gpu_slots
        )

    async def acquire(self, session_id: str, request: ResourceRequest, label: str = "") -> ResourceLease:
        if not session_id:
            raise ValueError("session_id is required")
        request.validate(self.capacity)
        ticket = uuid.uuid4().hex
        waiter = QueuedWaiter(
            ticket=ticket,
            session_id=session_id,
            request=request,
            label=str(label or "")[:80],
            enqueued_at=_utc_now(),
            enqueued_monotonic=time.monotonic(),
        )
        async with self._condition:
            self._waiting.append(waiter)
            try:
                await self._condition.wait_for(
                    lambda: self._waiting[0].ticket == ticket and self._fits(request)
                )
                self._waiting.pop(0)
                lease = ResourceLease(
                    ticket,
                    session_id,
                    request,
                    waiter.label,
                    _utc_now(),
                    time.monotonic(),
                )
                self._active[ticket] = lease
                self._condition.notify_all()
                return lease
            except BaseException:
                # 排队中途被取消（超时/断线）也要摘干净：队列里不留幽灵
                self._waiting[:] = [entry for entry in self._waiting if entry.ticket != ticket]
                self._condition.notify_all()
                raise

    async def release(self, lease: ResourceLease | None) -> None:
        if lease is None:
            return
        async with self._condition:
            self._active.pop(lease.lease_id, None)
            self._condition.notify_all()

    def snapshot(self) -> dict[str, Any]:
        used = self._used()
        now = time.monotonic()
        waiting = [
            {
                "session_id": entry.session_id,
                "position": idx + 1,
                "label": entry.label,
                "enqueued_at": entry.enqueued_at,
                "waited_sec": round(max(0.0, now - entry.enqueued_monotonic), 1),
                **asdict(entry.request),
            }
            for idx, entry in enumerate(self._waiting)
        ]
        active = [
            {
                "lease_id": lease.lease_id,
                "session_id": lease.session_id,
                "label": lease.label,
                "acquired_at": lease.acquired_at,
                "held_sec": round(max(0.0, now - lease.acquired_monotonic), 1),
                **asdict(lease.request),
            }
            for lease in self._active.values()
        ]
        return {
            "enforcement": {
                "admission": "cooperative_fifo",
                "local_process_limits": (
                    "windows_job_object" if os.name == "nt" else "unavailable"
                ),
            },
            "capacity": asdict(self.capacity),
            "used": asdict(used),
            "available": {
                "cpu_cores": self.capacity.cpu_cores - used.cpu_cores,
                "memory_gb": round(self.capacity.memory_gb - used.memory_gb, 2),
                "gpu_slots": self.capacity.gpu_slots - used.gpu_slots,
            },
            "queue": {
                "admission": "cooperative_fifo",
                "active": len(active),
                "waiting": len(waiting),
                "head_wait_sec": waiting[0]["waited_sec"] if waiting else 0.0,
                "max_wait_sec": max([w["waited_sec"] for w in waiting], default=0.0),
            },
            "active": active,
            "waiting": waiting,
        }
