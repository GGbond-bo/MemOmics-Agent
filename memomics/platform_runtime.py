# -*- coding: utf-8 -*-
"""platform_runtime — MemOmics 单入口进程薄层（P1-14/P1-15，2026-08-13）。

设计照抄 LoopX extensions/process_runtime.py（201 行薄层模式）：
  · 平台差异只允许出现在本模块；
  · 启动：posix → start_new_session；nt → CREATE_NEW_PROCESS_GROUP；
  · 终止：posix → killpg(SIGTERM) 优雅 1s → SIGKILL；nt → taskkill /T → /T /F；
  · 输出限流 + 超时（run_capped_process）；
  · MemOmics 增补：_ensure_win_env（SystemRoot/ComSpec，LoopX 不 spawn Windows
    shell 所以没有——MemOmics 必须有，否则子进程 0xC0000142）；
  · spawn_detached（后台守护启动，供 server/task_guardian 使用）。

其他模块（server.py、task_guardian.py、bio_tools）spawn 进程时一律走这里，
禁止散点 Popen + os.name 判断。
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_TERMINATE_GRACE_SECONDS = 1.0
_IO_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class CappedProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    failure_kind: str | None = None  # "timeout" | "output_limit" | None


def is_windows() -> bool:
    return os.name == "nt"


def _ensure_win_env(env: dict) -> dict:
    """Windows 子进程环境补全（STATUS_DLL_INIT_FAILED / 0xC0000142 根因修复）。

    从 bash/Git Bash 启动的进程缺 SystemRoot/ComSpec 时，Windows 加载器找不到
    核心 DLL，子进程（Rscript/python）间歇性启动即崩。
    """
    if not is_windows():
        return env
    env = dict(env)
    if not env.get("SystemRoot"):
        for c in (r"C:\WINDOWS", r"C:\Windows"):
            if os.path.isdir(c):
                env["SystemRoot"] = c
                break
    if not env.get("ComSpec"):
        for c in (r"C:\WINDOWS\system32\cmd.exe", r"C:\Windows\System32\cmd.exe"):
            if os.path.isfile(c):
                env["ComSpec"] = c
                break
    return env


def detach_options() -> dict:
    """脱离式启动参数（后台/长任务进程的唯一入口）。

    posix → start_new_session=True（setsid，脱离会话回收）；
    nt → CREATE_NEW_PROCESS_GROUP（脱离控制台 Ctrl+C / 会话级杀）。
    """
    if is_windows():
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _wait_for_process(process: subprocess.Popen, timeout: float) -> bool:
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return True


def _terminate_posix_process_group(process: subprocess.Popen) -> None:
    pgid = process.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return
    _wait_for_process(process, _TERMINATE_GRACE_SECONDS)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        process.kill()
        process.wait()


def _terminate_windows_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T"],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if _wait_for_process(process, _TERMINATE_GRACE_SECONDS):
        return
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    process.wait()


def terminate_process_tree(process: subprocess.Popen) -> None:
    """按平台杀整个进程树（优雅降级→强制）。安全：已退出进程为 no-op。"""
    if is_windows():
        _terminate_windows_process_tree(process)
        return
    if os.name == "posix":
        _terminate_posix_process_group(process)
        return
    if process.poll() is not None:
        return
    process.terminate()
    if not _wait_for_process(process, _TERMINATE_GRACE_SECONDS):
        process.kill()
        process.wait()


def run_capped_process(
    argv: Sequence[str],
    *,
    stdin: bytes = b"",
    timeout_seconds: int = 600,
    output_limit_bytes: int = 1_000_000,
    env: Mapping[str, str] | None = None,
    cwd: str | None = None,
) -> CappedProcessResult:
    """前台跑进程：双流限幅 + 超时 + 平台 detach 选项（对齐 LoopX 契约）。"""
    process = subprocess.Popen(
        list(argv),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        env=_ensure_win_env(dict(env)) if env is not None else None,
        cwd=cwd,
        **detach_options(),
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None

    stdout_buf = bytearray()
    stderr_buf = bytearray()
    limit_lock = threading.Lock()
    limit_event = threading.Event()
    limit_kind: list[str | None] = [None]

    def record_limit(kind: str) -> None:
        with limit_lock:
            if limit_kind[0] is None:
                limit_kind[0] = kind
                limit_event.set()

    def _pump(stream, target: bytearray, kind: str) -> None:
        # 限幅即停读并置事件 → 主循环检测到后主动杀进程
        # （子进程阻塞在管道写时不杀会永久挂起）
        try:
            while True:
                chunk = stream.read(_IO_CHUNK_BYTES)
                if not chunk:
                    return
                remaining = output_limit_bytes + 1 - len(target)
                if remaining > 0:
                    target.extend(chunk[:remaining])
                if len(target) > output_limit_bytes:
                    record_limit(kind)
                    return
        except (OSError, ValueError):
            return

    def _write_stdin() -> None:
        try:
            process.stdin.write(stdin)
        except (OSError, ValueError, BrokenPipeError):
            pass
        finally:
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass

    threads = [
        threading.Thread(target=_pump, args=(process.stdout, stdout_buf, "output_limit"), daemon=True),
        threading.Thread(target=_pump, args=(process.stderr, stderr_buf, "stderr_limit"), daemon=True),
        threading.Thread(target=_write_stdin, daemon=True),
    ]
    for t in threads:
        t.start()

    # 主循环：poll + 限幅事件检测（照抄 LoopX 原版——限幅/超时都主动杀进程树）
    deadline = time.monotonic() + float(timeout_seconds)
    timed_out = False
    while process.poll() is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            terminate_process_tree(process)
            break
        if limit_event.wait(timeout=min(0.05, remaining)):
            terminate_process_tree(process)
            break

    process.wait()
    for t in threads:
        t.join(timeout=_TERMINATE_GRACE_SECONDS)
    for stream in (process.stdout, process.stderr):
        try:
            stream.close()
        except (OSError, ValueError):
            pass
    return CappedProcessResult(
        returncode=process.returncode if process.returncode is not None else -1,
        stdout=bytes(stdout_buf),
        stderr=bytes(stderr_buf),
        failure_kind="timeout" if timed_out else limit_kind[0],
    )


def spawn_detached(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.Popen:
    """后台脱离启动（守护/长任务）：stdout/stderr 归 DEVNULL 或调用方自行传参。

    返回 Popen；杀它用 terminate_process_tree。
    """
    return subprocess.Popen(
        list(argv),
        env=_ensure_win_env(dict(env)) if env is not None else None,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **detach_options(),
    )
