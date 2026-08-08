# -*- coding: utf-8 -*-
"""持久 Python kernel 池（P0-1）

借鉴 OpenAI4S 持久内核理念：跨 execute_code 调用复用子进程，保留变量/
模块状态，避免每次解释器启动 + 依赖 import 的开销（生信分析 load
pandas/scanpy 数秒级）。

- 状态隔离：task_id → 独立 worker（不同任务互不干扰）
- 超时：kill 卡死 worker，下次调用自动重建
- 空闲回收：30min 无请求自动终止（防内存泄漏）
- 逃生阀：MEMOMICS_KERNEL_FRESH=1 强制走旧路径（每次新进程）
"""
import json
import logging
import os
import subprocess
import sys
import threading
import time

logger = logging.getLogger(__name__)

_IDLE_TIMEOUT = float(os.environ.get("MEMOMICS_KERNEL_IDLE_TIMEOUT", "1800"))
_MAX_OUTPUT_BYTES = int(os.environ.get("MEMOMICS_KERNEL_MAX_OUTPUT", "200000"))
_WORKER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_kernel_worker.py")


def _truncate(text, max_bytes=_MAX_OUTPUT_BYTES):
    """对齐 execute_code 的 head+tail 截断语义"""
    data = text.encode("utf-8", errors="replace")
    if len(data) <= max_bytes:
        return text, {}
    head = data[: int(max_bytes * 0.4)].decode("utf-8", errors="replace")
    tail = data[-int(max_bytes * 0.6):].decode("utf-8", errors="replace")
    return head + f"\n... [输出截断，共 {len(data)} 字节] ...\n" + tail, {"truncated": True}


class _Worker:
    """单个持久 worker 进程（task_id 级隔离）"""

    def __init__(self, task_id, python_path, env, cwd):
        self.task_id = task_id
        self.python_path = python_path
        self.env = env
        self.cwd = cwd
        self.proc = None
        self.lock = threading.Lock()
        self.last_use = time.monotonic()
        self._pending = {}
        self._results = {}
        self._seq = 0
        self._reader_stop = threading.Event()
        self._stderr_buf = []
        self._spawn()

    def _spawn(self):
        self.proc = subprocess.Popen(
            [self.python_path, "-u", _WORKER_PATH],
            cwd=self.cwd,
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self._reader_stop.clear()
        threading.Thread(target=self._reader_loop, daemon=True).start()
        threading.Thread(target=self._stderr_loop, daemon=True).start()

    def _reader_loop(self):
        while not self._reader_stop.is_set():
            line = self.proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except Exception:
                continue
            rid = msg.get("id")
            if rid in self._pending:
                self._results[rid] = msg
                self._pending[rid].set()

    def _stderr_loop(self):
        while not self._reader_stop.is_set():
            line = self.proc.stderr.readline()
            if not line:
                break
            self._stderr_buf.append(line[:500])
            if len(self._stderr_buf) > 20:
                self._stderr_buf.pop(0)

    def execute(self, code, timeout):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._spawn()
            self.last_use = time.monotonic()
            self._seq += 1
            rid = str(self._seq)
            ev = threading.Event()
            self._pending[rid] = ev
            try:
                self.proc.stdin.write((json.dumps({"id": rid, "code": code}, ensure_ascii=False) + "\n").encode("utf-8"))
                self.proc.stdin.flush()
            except Exception:
                self._pending.pop(rid, None)
                self._kill()
                return {"status": "error", "error": "worker write failed", "output": "", "tool_calls_made": 0, "duration_seconds": 0}
            if not ev.wait(timeout):
                self._pending.pop(rid, None)
                self._kill()
                return {"status": "timeout",
                        "error": f"Kernel timed out after {timeout}s and was killed.",
                        "output": f"⏰ Kernel timed out after {timeout}s and was killed.",
                        "tool_calls_made": 0, "duration_seconds": timeout}
            self._pending.pop(rid, None)
            res = self._results.pop(rid, None)
            if res is None:
                return {"status": "error", "error": "worker protocol error", "output": "", "tool_calls_made": 0, "duration_seconds": 0}
            out = res.get("stdout", "")
            err = res.get("stderr", "")
            if res.get("error"):
                return {"status": "error", "error": res["error"],
                        "output": (out + "\n--- stderr ---\n" + err) if err else out,
                        "tool_calls_made": 0, "duration_seconds": 0}
            out, meta = _truncate(out)
            result = {"status": "ok", "result": out, "output": out, "error": None,
                      "tool_calls_made": 0, "duration_seconds": 0}
            result.update(meta)
            return result

    def _kill(self):
        self._reader_stop.set()
        try:
            if self.proc is not None:
                self.proc.kill()
        except Exception:
            pass
        self.proc = None

    def close(self):
        self._kill()


class KernelPool:
    def __init__(self):
        self._workers = {}
        self._lock = threading.Lock()

    @staticmethod
    def _python_path():
        try:
            from tools.code_execution_tool import _get_execution_mode, _resolve_child_python
            return _resolve_child_python(_get_execution_mode())
        except Exception:
            return sys.executable

    @staticmethod
    def _child_env():
        try:
            from tools.code_execution_tool import _scrub_child_env
            env = _scrub_child_env(os.environ)
        except Exception:
            env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # hermes-agent/
        _pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = _root if not _pp else _root + os.pathsep + _pp
        return env

    def execute(self, code, task_id, timeout=120):
        now = time.monotonic()
        with self._lock:
            for tid in [t for t, w in self._workers.items() if now - w.last_use > _IDLE_TIMEOUT]:
                self._workers[tid].close()
                del self._workers[tid]
            w = self._workers.get(task_id)
            if w is None:
                w = _Worker(task_id, self._python_path(), self._child_env(), cwd=os.getcwd())
                self._workers[task_id] = w
        try:
            return w.execute(code, timeout)
        except Exception as e:
            logger.exception("kernel execute error")
            return {"status": "error", "error": str(e), "output": "", "tool_calls_made": 0, "duration_seconds": 0}

    def close(self):
        with self._lock:
            for w in self._workers.values():
                w.close()
            self._workers.clear()


KERNEL_POOL = KernelPool()


def try_persistent_kernel(code, task_id, timeout):
    """持久 kernel 快速路径；不适用时返回 None（调用方走旧路径）"""
    if os.environ.get("MEMOMICS_KERNEL_FRESH") == "1":
        return None
    if not code or not code.strip():
        return None
    # 沙箱/进程相关代码走旧路径（有审批 guard + hermes_tools RPC）
    if any(tok in code for tok in ("hermes_tools", "subprocess", "Popen", "os.system", "__import__", "importlib")):
        return None
    try:
        res = KERNEL_POOL.execute(code, task_id or "default", timeout=timeout)
    except Exception:
        return None
    return json.dumps(res, ensure_ascii=False)
