"""Cooperative CPU, memory and GPU admission control for analysis sessions."""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ResourceCapacity:
    cpu_cores: int
    memory_gb: float
    gpu_slots: int = 0

    @classmethod
    def detect(cls) -> "ResourceCapacity":
        cpu = max(1, (os.cpu_count() or 2) - 1)
        memory = 8.0
        try:
            import psutil

            memory = max(
                1.0,
                round(psutil.virtual_memory().available / 1024**3 * 0.8, 1),
            )
        except Exception:
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


class ResourceScheduler:
    """FIFO admission controller shared by all analysis sessions."""

    def __init__(self, capacity: ResourceCapacity) -> None:
        self.capacity = capacity
        self._condition = asyncio.Condition()
        self._active: dict[str, ResourceLease] = {}
        self._waiting: list[tuple[str, str, ResourceRequest]] = []

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

    async def acquire(self, session_id: str, request: ResourceRequest) -> ResourceLease:
        if not session_id:
            raise ValueError("session_id is required")
        request.validate(self.capacity)
        ticket = uuid.uuid4().hex
        waiter = (ticket, session_id, request)
        async with self._condition:
            self._waiting.append(waiter)
            try:
                await self._condition.wait_for(
                    lambda: self._waiting[0][0] == ticket and self._fits(request)
                )
                self._waiting.pop(0)
                lease = ResourceLease(ticket, session_id, request)
                self._active[ticket] = lease
                self._condition.notify_all()
                return lease
            except BaseException:
                self._waiting[:] = [entry for entry in self._waiting if entry[0] != ticket]
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
            "active": [
                {
                    "lease_id": lease.lease_id,
                    "session_id": lease.session_id,
                    **asdict(lease.request),
                }
                for lease in self._active.values()
            ],
            "waiting": [
                {"session_id": session_id, **asdict(request)}
                for _, session_id, request in self._waiting
            ],
        }
