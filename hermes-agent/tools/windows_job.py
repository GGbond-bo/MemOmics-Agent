"""Windows Job Object enforcement for MemOmics local analysis processes.

The web layer places private, task-scoped limit values in the environment
passed to Hermes.  This module consumes those values at the final Popen
boundary, so neither the global Python environment nor unrelated sessions are
affected.  All functions are safe no-ops outside Windows.
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
from dataclasses import dataclass
from ctypes import wintypes


logger = logging.getLogger(__name__)

MEMORY_ENV = "MEMOMICS_INTERNAL_JOB_MEMORY_BYTES"
CPU_RATE_ENV = "MEMOMICS_INTERNAL_JOB_CPU_RATE"
SESSION_ENV = "MEMOMICS_INTERNAL_JOB_SESSION_ID"

_JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_CPU_RATE_CONTROL_ENABLE = 0x1
_JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x4
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_CPU_RATE_CONTROL_INFORMATION = 15


@dataclass(frozen=True)
class JobLimits:
    memory_bytes: int | None = None
    cpu_rate: int | None = None
    session_id: str = ""

    @classmethod
    def from_environment(cls, env: dict | None) -> "JobLimits | None":
        values = env or {}
        memory = _positive_int(values.get(MEMORY_ENV))
        cpu_rate = _positive_int(values.get(CPU_RATE_ENV))
        if cpu_rate is not None:
            cpu_rate = min(cpu_rate, 10_000)
        if memory is None and cpu_rate is None:
            return None
        return cls(
            memory_bytes=memory,
            cpu_rate=cpu_rate,
            session_id=str(values.get(SESSION_ENV) or ""),
        )


def _positive_int(value) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _CPU_RATE_CONTROL_INFORMATION(ctypes.Structure):
    _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]


class WindowsJobLease:
    """Own a Job handle for the lifetime of one Popen process tree."""

    def __init__(self, handle, kernel32, limits: JobLimits):
        self._handle = handle
        self._kernel32 = kernel32
        self.limits = limits

    def terminate(self, exit_code: int = 1) -> bool:
        if not self._handle:
            return False
        return bool(self._kernel32.TerminateJobObject(self._handle, exit_code))

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def attach_windows_job(proc, env: dict | None) -> WindowsJobLease | None:
    """Attach *proc* and its future descendants to a constrained Job Object.

    Assignment can be rejected when a parent application placed MemOmics in a
    non-nestable Job.  That condition is deliberately non-fatal: the caller
    continues under the cooperative scheduler and receives an error marker on
    the Popen object for diagnostics.
    """
    limits = JobLimits.from_environment(env)
    if limits is None or platform.system() != "Windows":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _configure_api(kernel32)
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            _configure_limits(kernel32, job, limits)
            process_handle = getattr(proc, "_handle", None)
            if not process_handle:
                raise RuntimeError("Popen did not expose a Windows process handle")
            if not kernel32.AssignProcessToJobObject(job, process_handle):
                raise ctypes.WinError(ctypes.get_last_error())
        except Exception:
            kernel32.CloseHandle(job)
            raise
        lease = WindowsJobLease(job, kernel32, limits)
        proc._memomics_job_lease = lease
        proc._memomics_job_error = ""
        return lease
    except Exception as exc:
        proc._memomics_job_error = str(exc)
        logger.warning(
            "Could not enforce Windows Job limits for MemOmics session %s: %s",
            limits.session_id or "unknown",
            exc,
        )
        return None


def terminate_attached_job(proc) -> bool:
    lease = getattr(proc, "_memomics_job_lease", None)
    if lease is None:
        return False
    try:
        return lease.terminate()
    except Exception as exc:
        logger.warning("Could not terminate Windows Job Object: %s", exc)
        return False


def _configure_api(kernel32) -> None:
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL


def _configure_limits(kernel32, job, limits: JobLimits) -> None:
    extended = _EXTENDED_LIMIT_INFORMATION()
    extended.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if limits.memory_bytes is not None:
        extended.BasicLimitInformation.LimitFlags |= _JOB_OBJECT_LIMIT_JOB_MEMORY
        extended.JobMemoryLimit = limits.memory_bytes
    if not kernel32.SetInformationJobObject(
        job,
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(extended),
        ctypes.sizeof(extended),
    ):
        raise ctypes.WinError(ctypes.get_last_error())

    if limits.cpu_rate is not None:
        cpu = _CPU_RATE_CONTROL_INFORMATION(
            _JOB_OBJECT_CPU_RATE_CONTROL_ENABLE | _JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP,
            limits.cpu_rate,
        )
        if not kernel32.SetInformationJobObject(
            job,
            _JOB_OBJECT_CPU_RATE_CONTROL_INFORMATION,
            ctypes.byref(cpu),
            ctypes.sizeof(cpu),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
