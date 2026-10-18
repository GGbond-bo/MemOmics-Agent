# -*- coding: utf-8 -*-
"""集群长驻内核（真·集群 Jupyter，2026-10-18）。

用户需求：7G 数据在 HPC 上，希望像 Jupyter 一样读一次、后续多张图接着用，不要每轮重传。

做法（最省事且真长驻）：把本地那套 58 行自包含 worker 上传到集群，用 **ssh 的 stdin/stdout**
当作 JSON 行协议管道（与本地 persistent_kernel 完全同一协议）：
    ssh user@host "cd <workdir> && python3 ~/memomics_kernel/_kernel_worker.py"
于是变量/DataFrame/h5ad 对象都活在**集群进程内存**里，数据不出集群，第二张图 0 重读。

边界：
  · ssh 进程活着 = 内核活着；ssh 断了变量就没了（会明确提示"需重新加载"）
  · 需要密钥登录（BatchMode），密码交互不支持
  · 未配置集群时可用 local=True 走本地进程（用于自测/离线验证协议）

工具：cluster_kernel(action=start|exec|status|stop, code=..., timeout=...)
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
import time

WORKER_NAME = "_kernel_worker.py"
REMOTE_DIR = "memomics_kernel"
_session_kernels = {}          # (key) -> ClusterKernel
_lock = threading.Lock()


def _worker_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "..", "..", "hermes-agent", "tools", WORKER_NAME),
                 os.path.join(here, "_kernel_worker.py")):
        p = os.path.abspath(cand)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(WORKER_NAME)


class ClusterKernel:
    """一个跑在集群上（或本地模拟）的长驻 worker。"""

    def __init__(self, host: str = "", user: str = "", port: int = 22, workdir: str = "~",
                 key: str = "", python: str = "python3", timeout: float = 300.0,
                 extra_opts=None, local: bool = False):
        self.host = host or ""
        self.user = user or ""
        self.port = int(port or 22)
        self.workdir = workdir or "~"
        self.key = key or ""
        self.python = python or "python3"
        self.timeout = float(timeout or 300)
        self.extra_opts = list(extra_opts or [])
        self.local = bool(local) or not self.host
        self.proc = None
        self._seq = 0
        self._uploaded = False
        self.created_at = time.time()
        self.last_use = time.time()
        self.uses = 0

    # ---------- 连接构造 ----------
    def _ssh_prefix(self):
        opts = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6",
                "-p", str(self.port)]
        if self.key:
            opts += ["-i", self.key]
        opts += self.extra_opts
        target = f"{self.user}@{self.host}" if self.user else self.host
        return ["ssh", *opts, target]

    def _remote_worker(self) -> str:
        return f"$HOME/{REMOTE_DIR}/{WORKER_NAME}"

    def upload_worker(self) -> bool:
        """把自包含 worker 传到集群（cat 覆盖写，不需要 scp）。"""
        if self.local:
            self._uploaded = True
            return True
        try:
            src = open(_worker_path(), "rb").read()
            remote = f'$HOME/{REMOTE_DIR}'
            cmd = self._ssh_prefix() + [
                f'mkdir -p {remote} && cat > {remote}/{WORKER_NAME} && '
                f'echo UPLOAD_OK && python3 -c "print(1)" 2>/dev/null || true']
            p = subprocess.run(cmd, input=src, capture_output=True, timeout=120)
            ok = b"UPLOAD_OK" in (p.stdout or b"")
            self._uploaded = ok
            return ok
        except Exception:
            self._uploaded = False
            return False

    # ---------- 生命周期 ----------
    def start(self) -> dict:
        if self.proc is not None and self.proc.poll() is None:
            return {"ok": True, "already": True, "pid": self.proc.pid, "local": self.local}
        if not self.local and not self._uploaded:
            if not self.upload_worker():
                return {"ok": False, "error": "worker 上传失败（检查 host/user/密钥/网络）"}
        try:
            if self.local:
                cmd = [sys.executable, "-u", _worker_path()]
                cwd = os.path.expanduser("~")
            else:
                remote_cmd = (f'cd {self.workdir} && '
                              f'exec {self.python} -u {self._remote_worker()}')
                cmd = self._ssh_prefix() + [remote_cmd]
                cwd = None
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=cwd, bufsize=0)
            self.last_use = time.time()
            return {"ok": True, "pid": self.proc.pid, "local": self.local,
                    "host": self.host or "(local)"}
        except Exception as exc:
            return {"ok": False, "error": f"启动失败: {exc}"}

    def execute(self, code: str, timeout: float = None) -> dict:
        st = self.start()
        if not st.get("ok"):
            return {"status": "error", "error": st.get("error", "kernel 未能启动"), "output": ""}
        to = float(timeout or self.timeout)
        self._seq += 1
        rid = str(self._seq)
        self.last_use = time.time()
        self.uses += 1
        try:
            self.proc.stdin.write((json.dumps({"id": rid, "code": code}, ensure_ascii=False) + "\n")
                                  .encode("utf-8"))
            self.proc.stdin.flush()
        except Exception as exc:
            self._close()
            return {"status": "error", "error": f"写入失败（连接可能已断）: {exc}", "output": ""}
        deadline = time.monotonic() + to
        buf = b""
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                # ssh/worker 退出：把 stderr 带回去，便于判断是认证还是环境问题
                try:
                    err = (self.proc.stderr.read() or b"").decode("utf-8", "replace")[-600:]
                except Exception:
                    err = ""
                self._close()
                return {"status": "error",
                        "error": f"集群内核已退出（变量丢失，需重新加载数据）。stderr: {err}".strip(),
                        "output": ""}
            line = self.proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue
            buf += line
            try:
                resp = json.loads(buf.decode("utf-8", "replace"))
            except Exception:
                continue
            buf = b""
            if str(resp.get("id")) != rid:
                continue
            out = (resp.get("stdout") or "")
            err = resp.get("error")
            return {"status": "error" if err else "ok", "output": out,
                    "result": out, "error": err, "local": self.local}
        return {"status": "error", "output": "", "error": f"执行超时（{to}s）"}

    def status(self) -> dict:
        alive = self.proc is not None and self.proc.poll() is None
        return {"alive": alive, "pid": (self.proc.pid if self.proc else None),
                "host": self.host or "(local)", "local": self.local,
                "uses": self.uses, "idle_seconds": round(time.time() - self.last_use, 1),
                "worker": self._remote_worker() if not self.local else _worker_path()}

    def _close(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
        except Exception:
            pass
        self.proc = None

    def stop(self) -> dict:
        self._close()
        return {"ok": True, "stopped": True}


# ---------------- 会话级内核注册表 ----------------
def get_kernel(key: str = "", host: str = "", user: str = "", port: int = 22,
               workdir: str = "~", key_file: str = "", python: str = "python3",
               local: bool = False) -> ClusterKernel:
    k = key or "default"
    with _lock:
        kern = _session_kernels.get(k)
        if kern is None:
            kern = ClusterKernel(host=host, user=user, port=port, workdir=workdir,
                                 key=key_file, python=python, local=local)
            _session_kernels[k] = kern
        return kern


def kernel_status(key: str = "") -> dict:
    kern = _session_kernels.get(key or "default")
    return kern.status() if kern else {"alive": False, "host": "(none)", "note": "尚未启动"}


def stop_kernel(key: str = "") -> dict:
    kern = _session_kernels.pop(key or "default", None)
    return kern.stop() if kern else {"ok": True, "note": "没有正在运行的内核"}


# ---------------- 模型工具 ----------------
SCHEMA = {
    "name": "cluster_kernel",
    "description": (
        "在集群上开一个**长驻** Python 内核（真·集群 Jupyter）：数据读一次就留在集群内存里，"
        "后续多个任务/cell 直接复用变量，不用重新传输 7G 数据。"
        "action: start(启动) / exec(执行代码, 用 code 传) / status / stop。"
        "适合：数据在 HPC 上、需要多轮分析同一批数据。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["start", "exec", "status", "stop"]},
            "code": {"type": "string", "description": "要执行的 Python 代码（exec 时必填）"},
            "timeout": {"type": "number", "description": "执行超时秒数，默认 300"},
            "host": {"type": "string", "description": "可选：覆盖集群 host"},
            "workdir": {"type": "string", "description": "可选：集群上的工作目录"},
        },
        "required": ["action"],
    },
}


def _cluster_cfg() -> dict:
    try:
        from memomics.bio_tools.remote_cluster import _load_remote_config
        return _load_remote_config() or {}
    except Exception:
        return {}


def cluster_kernel_tool(action: str = "status", code: str = "", timeout: float = 300,
                        host: str = "", workdir: str = "") -> str:
    sid = ""
    try:
        from memomics.bio_tools.debate_analysis import get_session_sid
        sid = get_session_sid() or ""
    except Exception:
        sid = ""
    cfg = _cluster_cfg()
    key = f"cluster:{sid or 'default'}"
    if action == "stop":
        return json.dumps(stop_kernel(key), ensure_ascii=False)
    if action == "status":
        return json.dumps(kernel_status(key), ensure_ascii=False)
    kern = get_kernel(
        key,
        host=(host or cfg.get("host") or ""),
        user=cfg.get("user") or "",
        port=int(cfg.get("port") or 22),
        workdir=(workdir or cfg.get("workdir") or "~"),
        key_file=cfg.get("key") or "",
        python=cfg.get("python") or "python3",
        local=bool(not (host or cfg.get("host"))),   # 没配集群 → 本地模拟（同一套协议）
    )
    if action == "start":
        return json.dumps(kern.start(), ensure_ascii=False)
    if action == "exec":
        if not code.strip():
            return json.dumps({"status": "error", "error": "exec 需要 code"}, ensure_ascii=False)
        return json.dumps(kern.execute(code, timeout=timeout), ensure_ascii=False)
    return json.dumps({"status": "error", "error": f"未知 action: {action}"}, ensure_ascii=False)


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="cluster_kernel",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: cluster_kernel_tool(
                args.get("action", "status"), args.get("code", ""),
                float(args.get("timeout") or 300), args.get("host", ""), args.get("workdir", "")),
        )
    except Exception:
        pass


_register()
