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
                 purpose: str = "RNA", seed: int = None, max_rss_mb: int = 24000):
        self.lang = "R" if str(lang).lower().startswith("r") else "python"
        self.purpose = purpose or "RNA"
        # 2026-10-18（科研可复现）：默认固定种子；启动时自动设进内核并记录
        self.seed = int(seed) if seed is not None else 20261018
        self.applied_seed = None
        # OOM 保护：远端 worker RSS 上限（MB）；连续 2 次超限才终止，避免误杀长任务
        self.max_rss_mb = int(max_rss_mb or 24000)
        self._rss_over = 0
        self.remote_pid = None
        self._rss_checked_at = 0.0
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
        # 决策3：登录节点禁止跑重分析（只允许轻量交互）
        _g = guard_heavy_on_login(self.host, self.purpose)
        if not _g.get("ok"):
            return _g
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
                _safe = (self.kernel_id or "kernel").replace(":", "_")
                self._pidfile = f"$HOME/{REMOTE_DIR}/{_safe}.pid"
                remote_cmd = (f'cd {self.workdir} && echo $$ > {self._pidfile} && exec {_exe} '
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
            if not self.local:
                try:
                    self.remote_pid = self._read_remote_pid()
                except Exception:
                    self.remote_pid = None
            try:
                self._apply_seed()   # 2026-10-18：启动即固定随机种子（科研可复现）
            except Exception:
                pass
            return {"ok": True, "pid": self.proc.pid, "local": self.local,
                    "host": self.host or "(local)"}
        except Exception as exc:
            return {"ok": False, "error": f"启动失败: {exc}"}

    def execute(self, code: str, timeout: float = None) -> dict:
        # 决策1：6 小时不动 → 自动结束（交互期长驻，不做永久占用）
        if self.proc is not None and (time.time() - self.last_use) > INTERACTIVE_IDLE_SEC:
            self._close()
            return {"status": "error",
                    "error": (f"内核已因 {INTERACTIVE_IDLE_SEC // 3600} 小时无交互自动结束"
                              "（内存变量已释放，需重新 start 并重新加载数据）"),
                    "output": ""}
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

    def _read_remote_pid(self):
        """读远端 worker 的真实 pid（启动命令把 $$ 写进了 pid 文件）。"""
        if self.local or not self.host:
            return None
        try:
            p = subprocess.run(_ssh_cmd(self.host, self.user, self.port, self.key, self.extra_opts)
                               + [f"cat {self._pidfile} 2>/dev/null"],
                               capture_output=True, text=True, timeout=60)
            v = (p.stdout or "").strip()
            return int(v) if v.isdigit() else None
        except Exception:
            return None

    def remote_rss_mb(self):
        """远端 worker 的 RSS（MB）；本地模式用 psutil。"""
        if self.local:
            try:
                import psutil
                p = psutil.Process(self.proc.pid)
                tot = p.memory_info().rss + sum(c.memory_info().rss for c in p.children(recursive=True))
                return round(tot / (1024.0 * 1024.0), 1)
            except Exception:
                return None
        if not self.remote_pid:
            return None
        try:
            p = subprocess.run(_ssh_cmd(self.host, self.user, self.port, self.key, self.extra_opts)
                               + [f"ps -o rss= -p {self.remote_pid} | awk '{{print int($1/1024)}}'"],
                               capture_output=True, text=True, timeout=60)
            v = (p.stdout or "").strip().splitlines()
            return float(v[-1]) if v and v[-1].strip().isdigit() else None
        except Exception:
            return None

    def check_memory(self, force: bool = False) -> dict:
        """OOM 保护：超限先警告，连续 2 次超限才终止（不误杀正常长任务）。"""
        now = time.time()
        if not force and (now - self._rss_checked_at) < 60:
            return {"checked": False, "reason": "60s 内刚查过"}
        self._rss_checked_at = now
        rss = self.remote_rss_mb()
        out = {"checked": True, "rss_mb": rss, "limit_mb": self.max_rss_mb}
        if rss is None:
            out["status"] = "unknown"
            return out
        if rss <= self.max_rss_mb:
            self._rss_over = 0
            out["status"] = "ok"
            return out
        self._rss_over += 1
        out["status"] = "over"
        out["consecutive"] = self._rss_over
        if self._rss_over >= 2:
            self._close()
            out["status"] = "killed"
            out["message"] = (f"内核 RSS {rss:.0f}MB 连续 2 次超过上限 {self.max_rss_mb}MB，"
                              "已终止以保护节点；请精简对象或改走 qsub 批处理")
        else:
            out["message"] = (f"警告：内核 RSS {rss:.0f}MB 已超过上限 {self.max_rss_mb}MB，"
                              "再超一次将自动终止")
        return out

    def _apply_seed(self):
        """把固定种子设进内核（R: set.seed；Python: random/numpy），并记录。"""
        if self.lang == "R":
            r = self.execute(f"set.seed({self.seed}); cat('seed=', {self.seed}, '\n')", timeout=60)
        else:
            code = ("import random\ntry:\n    import numpy as np\n    np.random.seed(%d)\n"
                    "except Exception:\n    pass\nrandom.seed(%d)\nprint('seed=', %d)" % (self.seed, self.seed, self.seed))
            r = self.execute(code, timeout=60)
        if r.get("status") == "ok":
            self.applied_seed = self.seed
        return self.applied_seed

    def reseed(self, seed: int) -> dict:
        self.seed = int(seed)
        self.applied_seed = None
        return {"ok": True, "seed": self.seed, "applied": self._apply_seed()}

    def status(self) -> dict:
        alive = self.proc is not None and self.proc.poll() is None
        return {"alive": alive, "pid": (self.proc.pid if self.proc else None),
                "remote_pid": self.remote_pid, "seed": self.applied_seed or self.seed,
                "rss_mb": self.remote_rss_mb(), "max_rss_mb": self.max_rss_mb,
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
            "action": {"type": "string", "enum": ["start", "exec", "status", "stop", "list", "attach", "env", "rss", "seed", "submit", "jobs", "logs", "cancel"]},
            "lang": {"type": "string", "enum": ["python", "R"], "description": "语言（默认 python；RNA 分析建议 R）"},
            "purpose": {"type": "string", "enum": ["RNA", "ATAC"], "description": "用途（决定用 R4.41 还是 R4.3.3）"},
            "code": {"type": "string", "description": "要执行的 Python 代码（exec 时必填）"},
            "timeout": {"type": "number", "description": "执行超时秒数，默认 300"},
            "host": {"type": "string", "description": "可选：覆盖集群 host"},
            "kernel_id": {"type": "string", "description": "list 查到的内核 id（attach/stop 用）"},
            "seed": {"type": "integer", "description": "随机种子（action=seed 时重设；start 默认 20261018）"},
            "job_id": {"type": "string", "description": "作业号（action=logs/cancel 用）"},
            "scope": {"type": "string", "enum": ["session", "all"], "description": "jobs 的范围（默认本会话）"},
            "mem_gb": {"type": "number", "description": "本作业预计需要的内存 GB（不填则自动估算）"},
            "disk_gb": {"type": "number", "description": "预计产出占用磁盘 GB（默认 20）"},
            "force": {"type": "boolean", "description": "true = 无视水位线强行提交（会提醒风险）"},
            "workdir": {"type": "string", "description": "可选：集群上的工作目录"},
        },
        "required": ["action"],
    },
}


def _resolve_target(host_override: str = "", workdir_override: str = ""):
    """解析真正的执行目标：优先 remote.nodes[default_node]（计算节点）+ proxy_jump。

    ⚠️ remote.host 是**跳板/登录节点**，不能用来跑分析或取指纹（2026-10-18 实测：
    登录节点 not a submit host，R 也不在那里）。
    """
    cfg = _cluster_cfg()
    node_name = str(cfg.get("default_node") or "")
    node = ((cfg.get("nodes") or {}).get(node_name) or {}) if isinstance(cfg.get("nodes"), dict) else {}
    host = host_override or node.get("host") or cfg.get("host") or ""
    pj = node.get("proxy_jump") or cfg.get("proxy_jump") or ""
    extra = ["-J", pj] if pj else []
    extra += list(cfg.get("extra_ssh_options") or [])
    return {"host": host, "user": cfg.get("user") or "", "port": int(cfg.get("port") or 22),
            "key": cfg.get("key") or "", "extra_opts": extra,
            "workdir": workdir_override or node.get("workdir") or cfg.get("workdir") or "~",
            "node": node_name, "proxy_jump": pj}


def _cluster_cfg() -> dict:
    try:
        from memomics.bio_tools.remote_cluster import _load_remote_config
        return _load_remote_config() or {}
    except Exception:
        return {}


def cluster_kernel_tool(action: str = "status", code: str = "", timeout: float = 300,
                        host: str = "", workdir: str = "", kernel_id: str = "",
                        lang: str = "python", purpose: str = "RNA", seed: int = None,
                        job_id: str = "", mem_gb: float = None, disk_gb: float = None,
                        force: bool = False) -> str:
    sid = ""
    try:
        from memomics.bio_tools.debate_analysis import get_session_sid
        sid = get_session_sid() or ""
    except Exception:
        sid = ""
    cfg = _cluster_cfg()
    key = f"cluster:{sid or 'default'}"
    if action in ("jobs", "logs", "cancel"):
        from memomics.bio_tools import node_state as _ns
        try:
            from memomics.bio_tools.debate_analysis import get_session_sid as _gss
            _sid_now = _gss() or ""
        except Exception:
            _sid_now = ""
        _t = _resolve_target(host, workdir)
        if action == "jobs":
            # 2026-10-18：每次查作业时顺带推进排队队列（资源松了就自动开跑）
            _promo = {}
            try:
                _promo = _ns.promote_queued()
            except Exception as _e:
                _promo = {"error": str(_e)}
            try:
                _ns.poll_jobs(_t["host"], _t["user"], _t["port"], _t["key"], _t["extra_opts"])
            except Exception:
                pass
            _scope = str(locals().get("_scope_arg") or "session").lower()
            _mine = _ns.list_jobs() if _scope == "all" else _ns.list_jobs(session_id=(_sid_now or None))
            _others = len(_ns.list_jobs()) - len(_mine)
            return json.dumps({"ok": True, "node": _t["node"], "promoted": _promo,
                               "session_id": _sid_now, "jobs": _mine,
                               "other_sessions": _others,
                               "hint": ("其它会话还有 %d 个作业；scope=all 可看全部" % _others) if _others else ""},
                              ensure_ascii=False, indent=1)
        if action == "logs":
            jid = job_id or kernel_id
            rec = next((j for j in _ns.list_jobs(limit=80) if j.get("job_id") == jid), None)
            if not rec:
                return json.dumps({"ok": False, "error": f"没有作业 {jid}"}, ensure_ascii=False)
            import subprocess as _sp
            lg = (rec.get("log") or "").replace("$HOME", "/home/%s" % _t["user"])
            try:
                _q = _sp.run(_ssh_cmd(_t["host"], _t["user"], _t["port"], _t["key"], _t["extra_opts"])
                             + [f"bash -lc {('tail -c 20000 ' + lg + ' 2>/dev/null')!r}"],
                             capture_output=True, text=True, timeout=90)
                return json.dumps({"ok": True, "job_id": jid, "status": rec.get("status"),
                                   "log_tail": (_q.stdout or "")[-20000:]}, ensure_ascii=False)
            except Exception as exc:
                return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
        # cancel
        jid = job_id or kernel_id
        rec = next((j for j in _ns.list_jobs(limit=80) if j.get("job_id") == jid), None)
        if not rec:
            return json.dumps({"ok": False, "error": f"没有作业 {jid}"}, ensure_ascii=False)
        import subprocess as _sp
        try:
            _sp.run(_ssh_cmd(_t["host"], _t["user"], _t["port"], _t["key"], _t["extra_opts"])
                    + [f"bash -lc 'kill -TERM {rec.get('pid')} 2>/dev/null; sleep 1; kill -9 {rec.get('pid')} 2>/dev/null; echo KILLED'"],
                    capture_output=True, text=True, timeout=60)
            _ns.update_job(jid, status="cancelled", finished_at=__import__("time").time())
            return json.dumps({"ok": True, "job_id": jid, "cancelled": True}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    if action == "submit":
        tgt3 = _resolve_target(host, workdir)
        return json.dumps(submit_job(
            code, lang, purpose, slots=4, job_name="mmjob",
            host=tgt3["host"], user=tgt3["user"], port=tgt3["port"],
            key=tgt3["key"], extra_opts=tgt3["extra_opts"],
            workdir=tgt3["workdir"], mem_gb=mem_gb, disk_gb=disk_gb, force=force),
            ensure_ascii=False, indent=1)
    if action == "env":
        tgt = _resolve_target(host)
        fp = verify_env_fingerprint(lang, purpose,
                                    host=tgt["host"], user=tgt["user"], port=tgt["port"],
                                    key=tgt["key"], extra_opts=tgt["extra_opts"])
        fp["target"] = {k: tgt[k] for k in ("host", "node", "proxy_jump")}
        return json.dumps({"ok": True, "source": "memomics_home/cluster_envs.json",
                           "envs": env_summary(), "fingerprint_check": fp},
                          ensure_ascii=False, indent=1)
    if action in ("rss", "seed"):
        kern = _session_kernels.get(key)
        if kern is None:
            return json.dumps({"ok": False, "error": "当前会话没有运行中的内核，先 start"},
                              ensure_ascii=False)
        if action == "rss":
            return json.dumps(kern.check_memory(force=True), ensure_ascii=False)
        return json.dumps(kern.reseed(seed if seed is not None else kern.seed), ensure_ascii=False)
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
    _tgt = _resolve_target(host, workdir)
    kern = get_kernel(
        f"cluster:{sid or 'default'}:{lang}:{purpose}",
        host=_tgt["host"], user=_tgt["user"], port=_tgt["port"],
        workdir=_tgt["workdir"], key_file=_tgt["key"],
        python=(resolve_interpreter(lang, purpose) or cfg.get("python") or "python3"),
        local=bool(not _tgt["host"]),   # 没配集群 → 本地模拟（同一套协议）
        lang=lang, purpose=purpose, extra_opts=_tgt["extra_opts"],
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
                args.get("kernel_id", ""), args.get("lang", "python"), args.get("purpose", "RNA"),
                args.get("job_id", ""), args.get("mem_gb"), args.get("disk_gb"), bool(args.get("force")),
                (int(args["seed"]) if args.get("seed") is not None else None)),
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

# ---------------- 用户决策（2026-10-18）----------------
INTERACTIVE_IDLE_SEC = 6 * 3600     # 决策1：6 小时不动自动结束
LOGIN_NODE_PATTERNS = ("login", "cngb-login")   # 决策3：登录节点禁止跑重分析


def is_login_node(host: str) -> bool:
    h = str(host or "").lower()
    return any(p in h for p in LOGIN_NODE_PATTERNS)


def guard_heavy_on_login(host: str, purpose: str = "RNA") -> dict:
    """决策3：登录节点只允许轻量交互；重分析必须 qsub。

    判定采用保守策略：只要目标是登录节点且调用方声明的是分析用途 → 直接拒绝并给 qsub 指引。
    """
    if not is_login_node(host):
        return {"ok": True}
    return {"ok": False,
            "error": (f"拒绝在登录节点（{host}）跑 {purpose} 重分析：会把登录节点拖垮、也容易被管理员杀。"
                      "正确做法：重分析用 qsub/SGE 提交到计算节点（remote_cluster 的 submit），"
                      "内核只用于轻量交互（看数据、画小图）。"),
            "hint": "cluster_kernel 仅做交互；重活走 qsub"}


def _ssh_cmd(host="", user="", port=22, key="", extra_opts=None) -> list:
    """构造 ssh 命令前缀（与 ClusterKernel 一致，便于指纹等一次性远端查询）。"""
    opts = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-p", str(port or 22)]
    if key:
        opts += ["-i", key]
    opts += list(extra_opts or [])
    target = f"{user}@{host}" if user else host
    return ["ssh", *opts, target]


def verify_env_fingerprint(lang: str = "R", purpose: str = "RNA", host: str = "",
                           user: str = "", port: int = 22, key: str = "",
                           extra_opts=None) -> dict:
    """决策4：环境指纹校验 —— 现取 R/python 版本与关键包，和记录比对。"""
    rec = _envs_record()
    ent = ((rec.get("envs") or {}).get(str(purpose).upper()) or {})
    exe = resolve_interpreter(lang, purpose)
    if not exe:
        return {"ok": False, "error": "环境记录里没有该用途的解释器"}
    import subprocess
    _remote = bool(host)
    try:
        if str(lang).lower().startswith("r"):
            code = ('cat(R.version.string, "|");'
                    'for (p in c("Seurat","ArchR")) cat(p,"=",as.character(tryCatch(packageVersion(p), error=function(e) "MISSING")),"|")')
            argv = [exe, "-e", code]
        else:
            _py = ("import sys,pandas;print(sys.version.split()[0],'|pandas=',pandas.__version__)")
            argv = [exe, "-c", _py]
        if _remote:
            # 集群环境：必须走 ssh 执行，本地 subprocess 取不到远端版本（原实现的缺陷）
            import shlex as _shlex
            _inner = " ".join(_shlex.quote(str(a)) for a in argv)   # 引号必须保留，否则 R 代码被 shell 拆解
            cmd = _ssh_cmd(host, user, port, key, extra_opts) + [
                f'cd "$HOME" && {_inner}']
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            out = (p.stdout or "").strip() or (p.stderr or "").strip()[-300:]
            where = f"{user}@{host}" if user else host
        else:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=120)
            out = (p.stdout or "").strip()
            where = "local"
    except Exception as exc:
        return {"ok": False, "error": f"取指纹失败: {exc}"}
    return {"ok": True, "where": where, "exe": exe, "fingerprint": out,
            "recorded": {"R": ent.get("R"), "packages": ent.get("R_packages") or
                         ent.get("python_packages")},
            "note": "指纹与记录不一致说明环境被升级/重装，需重新核对后再跑分析"}

# ---------------- 集群内核 → qsub 桥（2026-10-18 用户要求）----------------
SGE_DEFAULTS = {"pe": "smp", "slots": 4, "queue": "", "name": "mmjob"}


def submit_job(code: str, lang: str = "R", purpose: str = "RNA", slots: int = 4,
               queue: str = "", job_name: str = "mmjob", host: str = "", user: str = "",
               port: int = 22, key: str = "", extra_opts=None, workdir: str = "",
               script: str = "", mem_gb: float = None, disk_gb: float = None,
               force: bool = False, input_paths=None, job_key: str = "") -> dict:
    """把一段分析代码变成 SGE 作业提交（登录节点禁跑重分析的"正确出口"）。

    流程：写脚本到集群 ~/memomics_jobs/scripts/<name>.<ext> → qsub -cwd -j y -o <log>
          -N <name> -pe smp <slots> <script> → 返回作业号。
    """
    if not code.strip() and not script:
        return {"ok": False, "error": "需要 code（要跑的分析代码）"}
    if not host:
        return {"ok": False, "error": "需要集群 host（或在 config.yaml 配置 remote）"}
    exe = resolve_interpreter(lang, purpose)
    if not exe:
        return {"ok": False, "error": f"环境记录里没有 {purpose}/{lang} 的解释器"}
    # === 2026-10-18 用户口径：默认都放行，只有"实时观测到紧张"才排队并提醒 ===
    from memomics.bio_tools import node_state as _ns
    _req = _ns.estimate_mem_gb(paths=input_paths, declared=mem_gb)
    _disk_req = float(disk_gb if disk_gb is not None else 20.0)
    _state = _ns.node_state(host, user, port, key, extra_opts, workdir)
    _verdict = _ns.decide(_state, _req["mem_gb"], _disk_req)
    if _verdict["zone"] == "unknown" and not force:
        return {"ok": False, "need_confirm": True, "zone": "unknown",
                "message": _verdict.get("message") or "拿不到节点实时状态，要不要照样提交？",
                "req_mem_gb": _req["mem_gb"]}
    if _verdict["zone"] == "red" and not force:
        # 2026-10-18：红区自动**入队**（而不是单纯拒绝），等资源松了自动跑
        try:
            import datetime as _dt2
            _qstamp = _dt2.datetime.now().strftime("%Y%m%d_%H%M%S")
            _qname = "".join(c for c in (job_name or "mmjob") if c.isalnum() or c in "-_")[:24] or "mmjob"
            _qext = "R" if str(lang).lower().startswith("r") else "py"
            _qscript = f"$HOME/memomics_jobs/scripts/{_qname}_{_qstamp}.{_qext}"
            _qid = f"q{_qstamp}_{_qname}"
            _ns.queue_job(_qid, host=host, user=user, port=port, key=key, extra_opts=extra_opts,
                          workdir=workdir or "~", exe=exe, script=_qscript,
                          log=f"$HOME/memomics_jobs/logs/{_qname}_{_qstamp}.log",
                          exit_file=_qscript + ".exit", lang=lang, purpose=purpose,
                          mem_gb=_req["mem_gb"], disk_gb=_disk_req, zone="red",
                          code=code, need_upload=True,
                          message=_verdict.get("message"))
        except Exception as _exc:
            return {"ok": False, "queued": False, "zone": "red",
                    "message": (_verdict.get("message") or "") + f"（入队失败: {_exc}）",
                    "options": _verdict.get("options") or []}
        return {"ok": False, "queued": True, "job_id": _qid, "zone": "red",
                "message": (_verdict.get("message") or "") + " → 已自动排队，资源宽松时自动开跑",
                "options": _verdict.get("options") or [],
                "req_mem_gb": _req["mem_gb"], "state": {k: _verdict.get(k) for k in
                    ("node", "mem_avail_gb", "remain_gb", "load1", "procs_R")}}
    _advisory = _verdict.get("advisory") or ""
    if force and _verdict["zone"] in ("red", "unknown"):
        _advisory = "⚠️ 已按 force 绕过水位线限制：" + (_verdict.get("message") or "")[:120]

    import datetime as _dt
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c for c in (job_name or "mmjob") if c.isalnum() or c in "-_")[:24] or "mmjob"
    ext = "R" if str(lang).lower().startswith("r") else "py"
    remote_script = script or f"$HOME/memomics_jobs/scripts/{safe}_{stamp}.{ext}"
    remote_log = f"$HOME/memomics_jobs/logs/{safe}_{stamp}.log"
    body = code
    if str(lang).lower().startswith("r"):
        header = f"#!{exe}\n" if not code.startswith("#!") else ""
    else:
        header = f"#!{exe}\n" if not code.startswith("#!") else ""
    payload = (header + body).encode("utf-8")
    ssh = _ssh_cmd(host, user, port, key, extra_opts)
    try:
        # 1) 落脚本（cat 覆盖写，避免引号/编码问题）
        w = subprocess.run(ssh + [f"mkdir -p $HOME/memomics_jobs/{{scripts,logs}} && "
                                  f"cat > {remote_script} && chmod +x {remote_script} && echo WROTE"],
                           input=payload, capture_output=True, timeout=120)
        if b"WROTE" not in (w.stdout or b""):
            return {"ok": False, "error": "写脚本失败", "stderr": (w.stderr or b"").decode("utf-8", "replace")[-300:]}
        # 2) qsub
        qargs = ["qsub", "-cwd", "-j", "y", "-o", remote_log, "-N", safe]
        if queue:
            qargs += ["-q", queue]
        if slots and int(slots) > 1:
            qargs += ["-pe", SGE_DEFAULTS["pe"], str(int(slots))]
        qargs.append(remote_script)
        # 远端用 bash -lc 加载登录环境（SGE/PATH 依赖 profile），并加 timeout + </dev/null 防挂住
        _cmd = "bash -lc " + shlex.quote("timeout 90 " + " ".join(qargs) + " </dev/null 2>&1")
        r = subprocess.run(ssh + [_cmd], capture_output=True, text=True, timeout=180)
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        import re as _re
        # 失败识别（2026-10-18 实测踩坑：qmaster 不可达时输出里带 "port 6444"，
        # 旧正则把端口号当作业号 → 假成功）
        _fail = bool(_re.search(r"Unable to run job|not a submit host|send timeout|got send error", out))
        _m = _re.search(r"Your job(?:-array)?\s+(\d+)", out)
        job_id = "" if _fail else (_m.group(1) if _m else "")
        if not job_id:
            # 降级：该集群（ssh3/ssh0/ssh23）scheduler=none，正确模式是**直接 ssh 到计算节点 nohup 直跑**
            try:
                _exitf = remote_script + ".exit"
                _inner = (f"cd {workdir or '~'} && {exe} {remote_script} > {remote_log} 2>&1; "
                          f"echo EXIT:$? > {_exitf}")
                _cmd2 = (f"bash -lc {shlex.quote('nohup bash -c ' + shlex.quote(_inner) +
                                                 ' >/dev/null 2>&1 & echo PID:$! && sleep 1 && ps -o lstart= -p $!')}")
                _r2 = subprocess.run(ssh + [_cmd2], capture_output=True, text=True, timeout=120)
                _o2 = (_r2.stdout or "").strip()
                _mp = _re.search(r"PID:\s*(\d+)", _o2)
                if _mp:
                    _pid = _mp.group(1)
                    # 2026-10-20 修复：bash -lc 会带 profile 噪音行，必须正则精确取 lstart，
                    # 否则记录的 lstart 是噪音 → 轮询时"不一致" → 在跑的作业被误判 lost。
                    import re as _re4
                    _lm = _re4.search(r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\w+\s+\d+\s+[\d:]+\s+\d{4})", _o2)
                    _lstart = " ".join(_lm.group(1).split()) if _lm else ""
                    _jid = job_key or f"mm{stamp}_{_pid}"
                    try:
                        _ns.register_job(_jid, status="running", pid=_pid, lstart=_lstart,
                                         host=host, user=user, port=port, key=key,
                                         extra_opts=list(extra_opts or []),
                                         node=_verdict.get("node") or host,
                                         script=remote_script, log=remote_log, exit_file=_exitf,
                                         workdir=workdir or "~", lang=lang, purpose=purpose,
                                         mem_gb=_req["mem_gb"], mem_source=_req["source"],
                                         zone=_verdict["zone"], kernel_id=kernel_id if "kernel_id" in dir() else "")
                    except Exception:
                        pass
                    return {"ok": True, "mode": "nohup", "job_id": _jid, "pid": _pid,
                            "lstart": _lstart, "script": remote_script, "log": remote_log,
                            "exit_file": _exitf, "zone": _verdict["zone"],
                            "req_mem_gb": _req["mem_gb"], "mem_source": _req["source"],
                            "advisory": _advisory,
                            "message": ("SGE 不可用（" + ("not a submit host" if "not a submit host" in out
                                       else "qmaster 不可达") + "）→ 已在计算节点 nohup 直跑"),
                            "qsub_raw": out[:300]}
                return {"ok": False, "error": "qsub 与 nohup 都失败", "qsub_raw": out[:400],
                        "nohup_raw": _o2[:300]}
            except Exception as exc:
                return {"ok": False, "error": f"提交失败: {exc}", "qsub_raw": out[:300]}
        if job_id:
            try:
                _ns.register_job(job_id, status="running", host=host, user=user, port=port,
                                 key=key, extra_opts=list(extra_opts or []),
                                 node=_verdict.get("node") or host,
                                 script=remote_script, log=remote_log, exit_file="", mode="qsub",
                                 mem_gb=_req["mem_gb"], zone=_verdict["zone"])
            except Exception:
                pass
        return {"ok": bool(job_id), "job_id": job_id, "zone": _verdict["zone"],
                "advisory": _advisory, "script": remote_script,
                "log": remote_log, "argv": " ".join(qargs),
                "message": "已提交到计算节点（登录节点不跑重分析）" if job_id else "qsub 未返回作业号",
                "stderr": (r.stderr or "")[-300:]}
    except Exception as exc:
        return {"ok": False, "error": f"提交失败: {exc}"}

