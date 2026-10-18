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



# ---------------- 环境解析（读 memomics_home/cluster_envs.json，2026-10-18）----------------
def _envs_record() -> dict:
    """读取实测确认过的集群环境记录（RNA=R4.41 / ATAC=R4.3.3）。"""
    p = os.path.join(os.environ.get("MEMOMICS_HOME") or os.path.expanduser("~"), "cluster_envs.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def resolve_interpreter(lang: str = "python", purpose: str = "RNA") -> str:
    """按「语言 + 用途」从环境记录里取解释器绝对路径；取不到才退回默认。

    科研场景关键：集群上 `python3`/`Rscript` 不在默认 PATH，必须用 env 里的绝对路径，
    而且 RNA 与 ATAC 环境不同（R4.41 vs R4.3.3）——不能混用，否则包版本不对。
    """
    rec = _envs_record()
    envs = rec.get("envs") or {}
    key = str(purpose or "RNA").upper()
    ent = envs.get(key) or envs.get("RNA") or {}
    if str(lang).lower().startswith("r"):
        return ent.get("Rscript") or ""
    return ent.get("python") or ""


def env_summary() -> dict:
    """给模型/日志用的一句话环境摘要（含版本），避免用错环境。"""
    rec = _envs_record()
    out = {}
    for k, v in (rec.get("envs") or {}).items():
        out[k] = {"env": v.get("env_name"), "R": v.get("R"),
                  "Rscript": v.get("Rscript"), "python": v.get("python"),
                  "packages": (v.get("R_packages") or {}),
                  "use_for": v.get("use_for")}
    return out


class ClusterKernel:
    """一个跑在集群上（或本地模拟）的长驻 worker。"""

    def __init__(self, host: str = "", user: str = "", port: int = 22, workdir: str = "~",
                 key: str = "", python: str = "python3", timeout: float = 300.0,
                 extra_opts=None, local: bool = False, lang: str = "python",
                 purpose: str = "RNA"):
        self.lang = "R" if str(lang).lower().startswith("r") else "python"
        self.purpose = purpose or "RNA"
        # 解释器优先来自实测环境记录（R4.41/R4.3.3），避免用错环境或 PATH 里没有
        if self.lang == "R":
            python = resolve_interpreter("R", self.purpose) or python
        elif not python or python == "python3":
            python = resolve_interpreter("python", self.purpose) or python
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
        self.kernel_id = ""          # 由 get_kernel 赋值，用于跨对话定位

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

    def _worker_file(self) -> str:
        return "_kernel_worker.R" if self.lang == "R" else WORKER_NAME

    def _remote_worker(self) -> str:
        return f"$HOME/{REMOTE_DIR}/{self._worker_file()}"

    def upload_worker(self) -> bool:
        """把自包含 worker 传到集群（cat 覆盖写，不需要 scp）。"""
        if self.local:
            self._uploaded = True
            return True
        try:
            _wf = self._worker_file()
            if self.lang == "R":
                _wf = "_kernel_worker.R"
                _src_path = os.path.join(os.path.dirname(_worker_path()), _wf)
            else:
                _src_path = _worker_path()
            src = open(_src_path, "rb").read()
            remote = f'$HOME/{REMOTE_DIR}'
            cmd = self._ssh_prefix() + [
                f'mkdir -p {remote} && cat > {remote}/{_wf} && echo UPLOAD_OK']
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
                _exe = self.python
                remote_cmd = (f'cd {self.workdir} && exec {_exe} '
                              + (f'{self._remote_worker()}' if self.lang == "R"
                                 else f'-u {self._remote_worker()}'))
                cmd = self._ssh_prefix() + [remote_cmd]
                cwd = None
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=cwd, bufsize=0)
            self.last_use = time.time()
            try:
                _reg_touch(self)     # 落盘登记 → 下一次对话 action=list 能看到
            except Exception:
                pass
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
            kern.kernel_id = k
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
            "action": {"type": "string", "enum": ["start", "exec", "status", "stop", "list", "attach", "env"]},
            "lang": {"type": "string", "enum": ["python", "R"], "description": "语言（默认 python；RNA 分析建议 R）"},
            "purpose": {"type": "string", "enum": ["RNA", "ATAC"], "description": "用途（决定用 R4.41 还是 R4.3.3）"},
            "code": {"type": "string", "description": "要执行的 Python 代码（exec 时必填）"},
            "timeout": {"type": "number", "description": "执行超时秒数，默认 300"},
            "host": {"type": "string", "description": "可选：覆盖集群 host"},
            "kernel_id": {"type": "string", "description": "list 查到的内核 id（attach/stop 用）"},
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
                        host: str = "", workdir: str = "", kernel_id: str = "",
                        lang: str = "python", purpose: str = "RNA") -> str:
    sid = ""
    try:
        from memomics.bio_tools.debate_analysis import get_session_sid
        sid = get_session_sid() or ""
    except Exception:
        sid = ""
    cfg = _cluster_cfg()
    key = f"cluster:{sid or 'default'}"
    if action == "env":
        return json.dumps({"ok": True, "source": "memomics_home/cluster_envs.json",
                           "envs": env_summary()}, ensure_ascii=False, indent=1)
    if action == "list":
        return json.dumps({"ok": True, "kernels": list_kernels(),
                           "note": "alive/attachable 只在当前服务进程内有效；服务重启后 ssh 管道断，变量必然丢失"}, ensure_ascii=False, indent=1)
    if action == "attach":
        return json.dumps(attach_kernel(kernel_id or key, sid), ensure_ascii=False)
    if action == "stop":
        return json.dumps(stop_kernel_by_id(kernel_id) if kernel_id else stop_kernel(key),
                          ensure_ascii=False)
    if action == "status":
        return json.dumps(kernel_status(key), ensure_ascii=False)
    kern = get_kernel(
        f"cluster:{sid or 'default'}:{lang}:{purpose}",
        host=(host or cfg.get("host") or ""),
        user=cfg.get("user") or "",
        port=int(cfg.get("port") or 22),
        workdir=(workdir or cfg.get("workdir") or "~"),
        key_file=cfg.get("key") or "",
        python=(resolve_interpreter(lang, purpose) or cfg.get("python") or "python3"),
        local=bool(not (host or cfg.get("host"))),   # 没配集群 → 本地模拟（同一套协议）
        lang=lang, purpose=purpose,
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
                float(args.get("timeout") or 300), args.get("host", ""), args.get("workdir", ""),
                args.get("kernel_id", ""), args.get("lang", "python"), args.get("purpose", "RNA")),
        )
    except Exception:
        pass


_register()


# ---------------- 跨对话定位 / 结束（2026-10-18 用户要求）----------------
_REG_FILE = os.path.join(os.environ.get("MEMOMICS_HOME") or os.path.expanduser("~"),
                         "cluster_kernels.json")


def _reg_load() -> dict:
    try:
        with open(_REG_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {"kernels": {}}
    except Exception:
        return {"kernels": {}}


def _reg_save(d: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_REG_FILE), exist_ok=True)
        tmp = _REG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _REG_FILE)
    except Exception:
        pass


def _reg_touch(kernel) -> None:
    """把内核登记到磁盘（跨对话可见），并刷新 last_use。"""
    d = _reg_load()
    kid = getattr(kernel, "kernel_id", "") or ""
    if not kid:
        return
    st = kernel.status()
    d.setdefault("kernels", {})[kid] = {
        "kernel_id": kid, "host": st.get("host"), "pid": st.get("pid"),
        "local": st.get("local"), "uses": st.get("uses", 0),
        "created_at": getattr(kernel, "created_at", time.time()),
        "last_use": time.time(), "alive": bool(st.get("alive")),
        "workdir": getattr(kernel, "workdir", ""),
    }
    _reg_save(d)


def list_kernels(include_stale: bool = True) -> list:
    """列出所有登记过的集群内核；alive 只对**本服务进程内**的内核有效。"""
    d = _reg_load()
    out = []
    for kid, rec in (d.get("kernels") or {}).items():
        live = _session_kernels.get(kid)
        in_proc = live is not None and live.proc is not None and live.proc.poll() is None
        rec = dict(rec)
        rec["in_process"] = bool(live is not None)
        rec["alive"] = bool(in_proc)
        rec["attachable"] = bool(in_proc)
        if rec["alive"] or include_stale:
            out.append(rec)
    out.sort(key=lambda r: r.get("last_use", 0), reverse=True)
    return out


def attach_kernel(kernel_id: str, sid: str = "") -> dict:
    """把当前会话挂到已有内核（跨"下一次对话"复用，同一服务进程内有效）。"""
    kid = str(kernel_id or "").strip()
    if not kid:
        return {"ok": False, "error": "需要 kernel_id（先用 action=list 查）"}
    live = _session_kernels.get(kid)
    if live is None or live.proc is None or live.proc.poll() is not None:
        return {"ok": False,
                "error": ("该内核不在当前服务进程内（服务重启或内核已退出）→ 变量已丢失，"
                          "需要重新 start 并重新加载数据"),
                "kernel_id": kid, "hint": "tmux 托管版可跨重启，属下一步升级"}
    target = f"cluster:{sid or 'default'}"
    with _lock:
        _session_kernels[target] = live
    _reg_touch(live)
    return {"ok": True, "attached": kid, "bound_to": target,
            "host": live.status().get("host"), "uses": live.uses}


def stop_kernel_by_id(kernel_id: str) -> dict:
    kid = str(kernel_id or "").strip()
    live = _session_kernels.pop(kid, None)
    if live is not None:
        r = live.stop()
        d = _reg_load()
        if kid in (d.get("kernels") or {}):
            d["kernels"][kid]["alive"] = False
            d["kernels"][kid]["stopped_at"] = time.time()
            _reg_save(d)
        return {**r, "kernel_id": kid}
    return {"ok": False, "error": f"本进程没有这个内核: {kid}（可能已停止或服务重启过）"}
