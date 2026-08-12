# -*- coding: utf-8 -*-
"""持久 kernel 池（P0-1）：Python + R

借鉴 OpenAI4S 持久内核理念：跨 execute_code/execute_r 调用复用子进程，
保留变量/模块状态，避免每次解释器启动 + 依赖 import 的开销。

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

# 0 = 不启用时间回收；>0 则空闲超过该秒数的 worker 被回收（与 LRU 容量回收并存）。
# 默认 1800s = 30 分钟（2026-08-13 用户定：最多 2 个 R + 空闲 30 分钟关闭）
_IDLE_TIMEOUT = float(os.environ.get("MEMOMICS_KERNEL_IDLE_TIMEOUT", "1800"))
# 每种语言最多保留的 worker 数（LRU：超出时回收最久未用的）。
# 默认 2：单任务分析隔多久回来都不重读数据，多任务切换也不爆内存。
_MAX_WORKERS_PER_LANG = int(os.environ.get("MEMOMICS_KERNEL_MAX_WORKERS", "2"))
_MAX_OUTPUT_BYTES = int(os.environ.get("MEMOMICS_KERNEL_MAX_OUTPUT", "200000"))
_PY_WORKER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_kernel_worker.py")
_R_WORKER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_kernel_worker.R")


def _truncate(text, max_bytes=_MAX_OUTPUT_BYTES):
    """对齐 execute_code 的 head+tail 截断语义"""
    data = text.encode("utf-8", errors="replace")
    if len(data) <= max_bytes:
        return text, {}
    head = data[: int(max_bytes * 0.4)].decode("utf-8", errors="replace")
    tail = data[-int(max_bytes * 0.6):].decode("utf-8", errors="replace")
    return head + f"\n... [输出截断，共 {len(data)} 字节] ...\n" + tail, {"truncated": True}


class _ProtoWorker:
    """协议通用部分：reader / stderr / 超时语义（子类实现 _spawn）"""

    def __init__(self, task_id, env, cwd):
        self.task_id = task_id
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

    def _spawn(self):  # pragma: no cover - 子类实现
        raise NotImplementedError

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
                self._kill(grace=0.5)
                return {"status": "error", "error": "worker write failed", "output": "", "tool_calls_made": 0, "duration_seconds": 0}
            # 轮询等待响应，同时监控 worker 存活：worker 若中途死亡（如 R 缺
            # jsonlite 启动即退），空等 ev.wait(timeout) 会白烧整个超时窗口
            # （2026-08-13 实测 R-4.5.3 无 jsonlite 时每个 R 执行卡满 600s）。
            deadline = time.monotonic() + timeout
            while not ev.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if self.proc is not None and self.proc.poll() is not None:
                    break  # worker 死了：立即失败，让上层回退
                ev.wait(min(remaining, 0.5))
            if not ev.is_set():
                self._pending.pop(rid, None)
                if self.proc is not None and self.proc.poll() is not None:
                    # 明确报告 worker 死亡（区别于超时），上层据此回退旧路径
                    self.proc = None
                    return {"status": "error",
                            "error": "kernel worker died unexpectedly (missing runtime dep, e.g. jsonlite?)",
                            "output": "".join(self._stderr_buf[-5:]) if getattr(self, "_stderr_buf", None) else "",
                            "tool_calls_made": 0, "duration_seconds": round(time.monotonic() - (deadline - timeout), 1)}
                self._kill(grace=0.5)
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

    def _kill(self, grace=3.0):
        """阶梯关闭：shutdown 帧 → 等待自行退出 → 进程树强杀兜底。

        防孤儿（对齐 OpenAI4S 三层防线）：
        1) 发 {"type":"shutdown"} 帧，worker 收到后 break 退出（正常路径）；
        2) 卡死时（不读帧）等待 grace 秒后强杀整个进程树——
           Windows 用 taskkill /T /F，POSIX 用进程组 SIGKILL，不留子进程；
        3) 树杀失败再退回 proc.kill()。
        """
        self._reader_stop.set()
        proc = self.proc
        self.proc = None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.stdin.write(b'{"type": "shutdown"}\n')
            proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=grace)
            return
        except Exception:
            pass
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass

    def close(self):
        self._kill()


class _PyWorker(_ProtoWorker):
    def __init__(self, task_id, python_path, env, cwd):
        self.python_path = python_path
        super().__init__(task_id, env, cwd)

    def _spawn(self):
        self.proc = subprocess.Popen(
            [self.python_path, "-u", _PY_WORKER_PATH],
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


class _RWorker(_ProtoWorker):
    def __init__(self, task_id, rscript_path, env, cwd):
        self.rscript_path = rscript_path
        super().__init__(task_id, env, cwd)

    def _spawn(self):
        self.proc = subprocess.Popen(
            [self.rscript_path, "--vanilla", _R_WORKER_PATH],
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


class KernelPool:
    def __init__(self):
        self._workers = {}
        self._lock = threading.Lock()
        self._sweeper_started = False
        self._sweeper_lock = threading.Lock()

    def _ensure_sweeper(self):
        """启动后台空闲清扫线程（幂等）。

        仅当 _IDLE_TIMEOUT > 0 时启动（时间回收模式）；默认 LRU 容量回收
        在 execute() 创建新 worker 时即时触发，不需要后台线程。"""
        if _IDLE_TIMEOUT <= 0:
            return
        with self._sweeper_lock:
            if self._sweeper_started:
                return
            self._sweeper_started = True

        def _sweep():
            while True:
                try:
                    time.sleep(60)
                    self._reap_idle()
                except Exception:
                    pass  # 清扫失败不影响主流程

        threading.Thread(target=_sweep, daemon=True, name="kernel-pool-sweeper").start()

    def _evict_lru(self, lang):
        """LRU 容量回收：该语言 worker 数超过上限时，回收最久未用的。

        语义（2026-08-13 用户定）：不限时间，最多保留 N 个最近使用的
        worker——单任务分析隔多久回来都不重读数据，多任务切换不爆内存。
        仅在创建新 worker 时触发。"""
        with self._lock:
            same_lang = {k: w for k, w in self._workers.items() if k.startswith(lang + ":")}
            if len(same_lang) <= _MAX_WORKERS_PER_LANG:
                return
            overflow = len(same_lang) - _MAX_WORKERS_PER_LANG
            for k in sorted(same_lang, key=lambda k: same_lang[k].last_use)[:overflow]:
                try:
                    same_lang[k].close()
                except Exception:
                    pass
                del self._workers[k]
            logger.info("kernel pool: LRU evicted %d %s worker(s), %d remaining",
                        overflow, lang, len(self._workers))

    def _reap_idle(self):
        now = time.monotonic()
        with self._lock:
            stale = [k for k, w in self._workers.items()
                     if now - w.last_use > _IDLE_TIMEOUT]
            for k in stale:
                try:
                    self._workers[k].close()
                except Exception:
                    pass
                del self._workers[k]
        if stale:
            logger.info("kernel pool: reaped %d idle worker(s), %d remaining",
                        len(stale), len(self._workers))

    @staticmethod
    def _python_path():
        try:
            from tools.code_execution_tool import _get_execution_mode, _resolve_child_python
            return _resolve_child_python(_get_execution_mode())
        except Exception:
            return sys.executable

    @staticmethod
    def _rscript_path():
        for cand in (os.environ.get("RSCRIPT_PATH"), "Rscript"):
            if not cand:
                continue
            import shutil
            found = shutil.which(cand)
            if found:
                return found
        return "Rscript"

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
        # R 用户库：environment.json 里 default R 的 lib_user/lib_site 不在 scrub
        # 白名单（scrub 会删 R_LIBS_USER），但主力分析 R 的 251 个包（含
        # jsonlite）都在自定义 lib_user 里。R 启动时读取 R_LIBS_USER 环境变量
        # 并自动加入 .libPaths()——不设的话 worker 找不到 jsonlite 立即死亡
        # （2026-08-13 实测 R-4.5.3 无此变量时 execute_r 卡满 600s）。
        try:
            import json as _json
            _app_root = os.path.dirname(_root)  # E:\MemOmics-Agent
            _env_json = _json.load(open(os.path.join(_app_root, "environment.json"), encoding="utf-8"))
            _r_section = _env_json.get("paths", {}).get("r", {})
            _def_rscript = _r_section.get("default", "")
            _r_ver = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(_def_rscript))))
            _r_info = _r_section.get(_r_ver, {})
            if _r_info.get("lib_user") and not env.get("R_LIBS_USER"):
                env["R_LIBS_USER"] = _r_info["lib_user"]
            if _r_info.get("lib_site") and not env.get("R_LIBS_SITE"):
                env["R_LIBS_SITE"] = _r_info["lib_site"]
        except Exception:
            pass  # 环境文件缺失/格式异常不阻塞执行，worker 用 R 默认库
        return env

    def execute(self, code, task_id, timeout=120, language="python"):
        lang = language or "python"
        key = f"{lang}:{task_id or 'default'}"
        now = time.monotonic()
        self._ensure_sweeper()  # 幂等：仅 _IDLE_TIMEOUT>0 时启动时间回收
        with self._lock:
            if _IDLE_TIMEOUT > 0:
                for k in [k for k, w in self._workers.items() if now - w.last_use > _IDLE_TIMEOUT]:
                    self._workers[k].close()
                    del self._workers[k]
            w = self._workers.get(key)
            if w is None:
                if lang == "r":
                    w = _RWorker(task_id or "default", self._rscript_path(), self._child_env(), cwd=os.getcwd())
                else:
                    w = _PyWorker(task_id or "default", self._python_path(), self._child_env(), cwd=os.getcwd())
                self._workers[key] = w
        self._evict_lru(lang)  # LRU 容量回收：超出上限时回收最久未用的 worker
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


def try_persistent_kernel(code, task_id, timeout, language="python"):
    """持久 kernel 快速路径；不适用时返回 None（调用方走旧路径）"""
    if os.environ.get("MEMOMICS_KERNEL_FRESH") == "1":
        return None
    if not code or not code.strip():
        return None
    # 沙箱/进程相关代码走旧路径（有审批 guard + hermes_tools RPC）
    if any(tok in code for tok in ("hermes_tools", "subprocess", "Popen", "os.system", "__import__", "importlib")):
        return None
    try:
        res = KERNEL_POOL.execute(code, task_id or "default", timeout=timeout, language=language)
    except Exception:
        return None
    return json.dumps(res, ensure_ascii=False)
