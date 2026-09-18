"""MemOmics 远端集群（SSH）工具 — 把 hermes 的 SSH 后端接进 MemOmics。

背景
----
hermes 框架本身带 SSH 执行后端（hermes-agent/tools/environments/ssh.py 的
SSHEnvironment：ControlMaster 连接复用 + 持久会话快照 + cwd 标记），但 MemOmics
的算力链是**本地**的（execute_r/execute_python 直接 subprocess 调本机 Rscript/
python）。因此本工具把那条 SSH 链路单独接出来，给 MemOmics 增加"连集群"的能力：

  * 只连一台远端登录节点（host/user/port/key 来自 config.yaml 的 remote: 段）
  * run        — 登录节点上跑轻量命令（探查/环境自检）
  * submit     — 生成作业脚本并提交到 Slurm / PBS / 无调度器（nohup 后台）
  * status/logs/cancel/jobs — 看作业状态、读日志、取消、列队列
  * push/pull  — 本地 ↔ 远端文件同步（重活产物回传本地，继续用 execute_r 分析）

与 hermes SSHEnvironment 的关系（重要）
-------------------------------------
ClusterSSH 直接继承 SSHEnvironment，复用它的 _build_ssh_command /
_establish_connection / _detect_remote_home / _run_bash / execute / cleanup
（即整条 SSH 传输与执行引擎），只覆盖两处：

  1. 不调用父类 __init__ 里那两步"把本地 ~/.hermes 同步到远端"的逻辑
     （file_sync.iter_sync_files 会把 credentials/skills/cache 上传到远端）。
     集群登录节点是共享机器，把本机凭据/技能推上去既不必要也不安全，
     实测本机该清单含 10 个 skills/_debates/*.json；配置了凭据时还会带凭据文件。
  2. _before_execute() 置空 —— 父类每次执行前都会触发一次文件同步，
     集群场景不需要。

除这两点外，SSH 命令构造（ControlMaster/ControlPersist/BatchMode/
StrictHostKeyChecking=accept-new/ConnectTimeout/-p/-i）与执行语义和 hermes
完全一致，因此行为可预期、出问题可按 hermes 文档排查。

配置（hermes_home/config.yaml）
-------------------------------
    remote:
      enabled: true                 # 总开关；false 或缺省时本工具不出现在工具列表
      host: login.example.edu.cn    # 登录节点
      user: zhangsan
      port: 22
      key: C:/Users/me/.ssh/id_ed25519   # 私钥路径；留空则用 ssh-agent/默认密钥
      workdir: /home/zhangsan/proj       # 远端工作目录（默认执行目录）
      scheduler: auto               # auto | slurm | pbs | none
      partition: cpu                # Slurm 默认分区
      queue: ""                     # PBS 默认队列
      local_root: E:/MemOmics-Agent # 与 remote_root 配对，用于路径映射（可选）
      remote_root: /home/zhangsan/proj
      job_dir: ""                   # 作业脚本/日志目录，默认 <workdir>/memomics_jobs
      timeout: 300                  # run 默认超时（秒）
      max_output_chars: 20000       # 返回给模型的输出上限
      extra_ssh_options: []         # 追加 ssh 参数，例如 ["-o","ProxyJump=bastion"]

环境变量覆盖（便于临时测试，不必改配置）：
    MEMOMICS_REMOTE_ENABLED / _HOST / _USER / _PORT / _KEY / _WORKDIR /
    _SCHEDULER / _LOCAL_ROOT / _REMOTE_ROOT

网关限制：ssh 使用 BatchMode=yes，**只支持密钥登录**，不支持密码交互。
本机没有 ssh/scp 时工具自检报错并说明装法。

平台差异：hermes 的 SSH 后端默认用 ControlMaster 复用连接，但 Windows 自带的
Win32-OpenSSH 没有 mux 支持（报 "getsockname failed: Not a socket"）。本工具会自动
探测并降级为"每次新建连接"（Linux/macOS 上仍走 ControlMaster），不需要手工配置。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

_ENV_MAP = {
    "enabled": "MEMOMICS_REMOTE_ENABLED",
    "host": "MEMOMICS_REMOTE_HOST",
    "user": "MEMOMICS_REMOTE_USER",
    "port": "MEMOMICS_REMOTE_PORT",
    "key": "MEMOMICS_REMOTE_KEY",
    "workdir": "MEMOMICS_REMOTE_WORKDIR",
    "scheduler": "MEMOMICS_REMOTE_SCHEDULER",
    "local_root": "MEMOMICS_REMOTE_LOCAL_ROOT",
    "remote_root": "MEMOMICS_REMOTE_REMOTE_ROOT",
    "timeout": "MEMOMICS_REMOTE_TIMEOUT",
}

_DEFAULT_CFG = {
    "enabled": False,
    "host": "",
    "user": "",
    "port": 22,
    "key": "",
    "workdir": "",
    "scheduler": "auto",
    "partition": "",
    "queue": "",
    "local_root": "",
    "remote_root": "",
    "job_dir": "",
    "timeout": 300,
    "max_output_chars": 20000,
    "extra_ssh_options": [],
}

_CFG_CACHE = {"mtime": None, "cfg": None}


def _get_config_path() -> Path:
    """定位 hermes_home/config.yaml（与 debate_analysis._get_config_path 同源）。"""
    try:
        from hermes_constants import get_hermes_home
        base = Path(get_hermes_home())
    except Exception:
        base = Path(os.environ.get("HERMES_HOME", "E:/MemOmics-Agent/hermes_home"))
    return base / "config.yaml"


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except Exception:
            pass
    return [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]


def _load_remote_config(force: bool = False) -> dict:
    """读取 config.yaml 的 remote: 段 + 环境变量覆盖，带 mtime 缓存。"""
    path = _get_config_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    if not force and _CFG_CACHE["cfg"] is not None and _CFG_CACHE["mtime"] == mtime:
        return _CFG_CACHE["cfg"]

    raw: dict = {}
    if mtime is not None:
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            section = data.get("remote") if isinstance(data, dict) else None
            if isinstance(section, dict):
                raw = dict(section)
        except Exception as exc:  # 配置坏掉时不要让工具消失，只是拿默认值
            logger.warning("读取 remote 配置失败(%s): %s", path, exc)

    cfg = dict(_DEFAULT_CFG)
    for key in _DEFAULT_CFG:
        if key in raw and raw[key] is not None:
            cfg[key] = raw[key]
    for key, env_name in _ENV_MAP.items():
        env_val = os.environ.get(env_name)
        if env_val is not None and str(env_val).strip() != "":
            cfg[key] = env_val
    for alias in ("ssh_key", "identity_file", "key_path"):
        if not cfg["key"] and raw.get(alias):
            cfg["key"] = raw[alias]
    if not cfg["workdir"] and raw.get("cwd"):
        cfg["workdir"] = raw["cwd"]

    try:
        cfg["port"] = int(str(cfg["port"]).strip() or 22)
    except Exception:
        cfg["port"] = 22
    try:
        cfg["timeout"] = int(str(cfg["timeout"]).strip() or 300)
    except Exception:
        cfg["timeout"] = 300
    try:
        cfg["max_output_chars"] = int(str(cfg["max_output_chars"]).strip() or 20000)
    except Exception:
        cfg["max_output_chars"] = 20000

    cfg["enabled"] = _truthy(cfg["enabled"])
    cfg["host"] = str(cfg["host"] or "").strip()
    cfg["user"] = str(cfg["user"] or "").strip()
    cfg["key"] = str(cfg["key"] or "").strip()
    cfg["workdir"] = str(cfg["workdir"] or "").strip() or "~"
    cfg["scheduler"] = str(cfg["scheduler"] or "auto").strip().lower()
    cfg["job_dir"] = str(cfg["job_dir"] or "").strip()
    if not cfg["job_dir"]:
        cfg["job_dir"] = posixpath.join(cfg["workdir"], "memomics_jobs")
    cfg["extra_ssh_options"] = _as_list(cfg.get("extra_ssh_options"))
    cfg["local_root"] = str(cfg["local_root"] or "").strip()
    cfg["remote_root"] = str(cfg["remote_root"] or "").strip()

    _CFG_CACHE["mtime"] = mtime
    _CFG_CACHE["cfg"] = cfg
    return cfg


def remote_cluster_enabled() -> bool:
    """check_fn：没配置 remote: 段时工具对模型不可见。"""
    cfg = _load_remote_config()
    return bool(cfg["enabled"] and cfg["host"] and cfg["user"])


# ---------------------------------------------------------------------------
# SSH 连接层（继承 hermes SSHEnvironment，跳过 ~/.hermes 同步）
# ---------------------------------------------------------------------------

def _ensure_ssh_available() -> None:
    if not shutil.which("ssh"):
        raise RuntimeError(
            "本机没有 ssh 客户端（不在 PATH）。Windows 可在 设置→可选功能 里安装 "
            "'OpenSSH 客户端'，或 PowerShell 执行: Add-WindowsCapability -Online "
            "-Name OpenSSH.Client~~~~0.0.1.0"
        )
    if not shutil.which("scp"):
        raise RuntimeError("本机没有 scp 客户端（不在 PATH）。随 OpenSSH 客户端一起安装。")


def _cluster_env_class():
    """延迟导入 hermes 的 SSHEnvironment（失败时给出清晰原因）。"""
    try:
        from tools.environments.base import BaseEnvironment
        from tools.environments.ssh import SSHEnvironment
    except Exception as exc:
        raise RuntimeError(
            "无法导入 hermes 的 SSH 后端（tools.environments.ssh）：%s。"
            "确认 hermes-agent 目录在本进程 sys.path 上。" % exc
        )
    return BaseEnvironment, SSHEnvironment


_CONN_LOCK = threading.RLock()
_CONNS: dict = {}
_CLUSTER_SSH_CLS = None

# Windows 版 OpenSSH（Win32-OpenSSH）没有编译 mux 支持，带
# ControlMaster/ControlPath 会直接失败：getsockname failed: Not a socket。
# 这里做能力探测：先用 mux 试连，命中该错误就永久降级为"每次新建连接"
# （仍然复用 hermes 的 SSH 命令构造与执行引擎，只是没有连接复用）。
_MUX_KNOWN_UNSUPPORTED = False

_MUX_ERROR_MARKERS = (
    "getsockname", "not a socket", "controlmaster", "control master",
    "control socket", "mux_client", "multiplexing", "unix_listener",
)


def _looks_like_mux_error(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _MUX_ERROR_MARKERS)


def _make_conn_class():
    global _CLUSTER_SSH_CLS
    if _CLUSTER_SSH_CLS is not None:
        return _CLUSTER_SSH_CLS
    BaseEnvironment, SSHEnvironment = _cluster_env_class()

    class ClusterSSH(SSHEnvironment):
        """hermes SSHEnvironment 的集群变体：同样走 ssh/scp，但不做 ~/.hermes 同步。

        父类 __init__ 会调用 FileSyncManager.sync(force=True)，把本地
        credentials/skills/cache 上传到远端 ~/.hermes —— 对共享登录节点不合适，
        这里刻意跳过；SSH 命令构造与执行引擎仍完全复用父类。
        """

        def __init__(self, host: str, user: str, cwd: str = "~", timeout: int = 60,
                     port: int = 22, key_path: str = "", extra_options=None):
            global _MUX_KNOWN_UNSUPPORTED
            BaseEnvironment.__init__(self, cwd=cwd, timeout=timeout)
            self.host = host
            self.user = user
            self.port = int(port or 22)
            self.key_path = key_path or ""
            self.extra_options = [str(o) for o in (extra_options or [])]

            # Windows 没有 unix socket / Win32-OpenSSH 无 mux：默认关掉连接复用
            self.use_mux = (not _MUX_KNOWN_UNSUPPORTED) and os.name != "nt"
            self.control_dir = Path(tempfile.gettempdir()) / "hermes-ssh"
            self.control_dir.mkdir(parents=True, exist_ok=True)
            _socket_id = hashlib.sha256(
                ("%s@%s:%s" % (user, host, self.port)).encode()
            ).hexdigest()[:16]
            self.control_socket = self.control_dir / ("%s.sock" % _socket_id)

            self._sync_manager = None
            _ensure_ssh_available()
            try:
                self._establish_connection()
            except RuntimeError as exc:
                if self.use_mux and _looks_like_mux_error(str(exc)):
                    # 本机 ssh 不支持多路复用（典型：Windows OpenSSH）→ 永久降级
                    _MUX_KNOWN_UNSUPPORTED = True
                    self.use_mux = False
                    self._establish_connection()
                else:
                    raise
            self._remote_home = self._detect_remote_home()
            self.init_session()

        def _build_ssh_command(self, extra_args=None):
            if self.use_mux:
                cmd = super()._build_ssh_command(extra_args)
            else:
                # 复刻父类命令构造，只是不带 ControlMaster/ControlPath
                cmd = ["ssh",
                       "-o", "BatchMode=yes",
                       "-o", "StrictHostKeyChecking=accept-new",
                       "-o", "ConnectTimeout=10"]
                if self.port != 22:
                    cmd.extend(["-p", str(self.port)])
                if self.key_path:
                    cmd.extend(["-i", self.key_path])
                if extra_args:
                    cmd.extend(extra_args)
                cmd.append("%s@%s" % (self.user, self.host))
            if self.extra_options and cmd:
                # ssh 选项必须排在 host 之前
                cmd[-1:] = list(self.extra_options) + [cmd[-1]]
            return cmd

        def _before_execute(self) -> None:
            # 集群场景不做本地→远端文件同步（父类默认行为）
            return None

    _CLUSTER_SSH_CLS = ClusterSSH
    return ClusterSSH


def _conn_key(cfg: dict) -> str:
    return "%s@%s:%s" % (cfg["user"], cfg["host"], cfg["port"])


def _get_conn(cfg: dict, force_reconnect: bool = False):
    key = _conn_key(cfg)
    with _CONN_LOCK:
        if force_reconnect:
            old = _CONNS.pop(key, None)
            if old is not None:
                try:
                    old.cleanup()
                except Exception:
                    pass
        conn = _CONNS.get(key)
        if conn is None:
            ClusterSSH = _make_conn_class()
            conn = ClusterSSH(
                host=cfg["host"],
                user=cfg["user"],
                cwd=cfg["workdir"] or "~",
                timeout=cfg["timeout"],
                port=cfg["port"],
                key_path=cfg["key"],
                extra_options=cfg["extra_ssh_options"],
            )
            _CONNS[key] = conn
        return conn


def _drop_conn(cfg: dict) -> None:
    with _CONN_LOCK:
        old = _CONNS.pop(_conn_key(cfg), None)
    if old is not None:
        try:
            old.cleanup()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------

def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    head = int(limit * 0.6)
    tail = max(limit - head, 0)
    return ("%s\n…[输出过长已截断：共 %d 字符，仅保留头尾]\n…\n%s"
            % (text[:head], len(text), text[-tail:] if tail else ""))


def _ok(payload: dict) -> str:
    payload.setdefault("status", "ok")
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _err(message: str, **extra) -> str:
    payload = {"status": "error", "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _is_conn_error(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in (
        "connection closed", "connection reset", "connection refused",
        "broken pipe", "no route to host", "operation timed out",
        "control socket", "ssh_exchange_identification", "kex_exchange_identification",
        "permission denied", "host key verification failed",
    ))


def _records_path() -> Path:
    base = _get_config_path().parent / "remote"
    base.mkdir(parents=True, exist_ok=True)
    return base / "jobs.jsonl"


def _record_job(record: dict) -> None:
    try:
        with open(_records_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("记录远端作业失败: %s", exc)


def _iter_jobs(limit: int = 200) -> list:
    path = _records_path()
    if not path.exists():
        return []
    out = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except OSError as exc:
        logger.warning("读取远端作业记录失败: %s", exc)
    return out[-limit:]


def _find_job(cfg: dict, job_id: str):
    for rec in reversed(_iter_jobs()):
        if str(rec.get("job_id")) == str(job_id) and rec.get("host") == cfg["host"]:
            return rec
    return None


def _map_local_to_remote(cfg: dict, local_path: str) -> str:
    if not cfg["local_root"] or not cfg["remote_root"]:
        return ""
    try:
        rel = os.path.relpath(os.path.abspath(local_path), os.path.abspath(cfg["local_root"]))
    except ValueError:
        return ""
    if rel.startswith(".."):
        return ""
    return posixpath.join(cfg["remote_root"], rel.replace("\\", "/"))


def _map_remote_to_local(cfg: dict, remote_path: str) -> str:
    if not cfg["local_root"] or not cfg["remote_root"]:
        return ""
    root = cfg["remote_root"].rstrip("/")
    if not remote_path.startswith(root):
        return ""
    rel = remote_path[len(root):].lstrip("/")
    return os.path.join(cfg["local_root"], rel.replace("/", os.sep))


# ---------------------------------------------------------------------------
# scp 收发（复用 ControlMaster socket，不重复认证）
# ---------------------------------------------------------------------------

def _scp_base(conn) -> list:
    cmd = ["scp", "-r", "-q"]
    if getattr(conn, "use_mux", False):
        cmd.extend(["-o", "ControlPath=%s" % conn.control_socket])
    cmd.extend([
           "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=accept-new",
           "-o", "ConnectTimeout=10"])
    if conn.port and conn.port != 22:
        cmd.extend(["-P", str(conn.port)])
    if conn.key_path:
        cmd.extend(["-i", conn.key_path])
    if conn.extra_options:
        cmd.extend(conn.extra_options)
    return cmd


def _scp_transfer(conn, local_path: str, remote_path: str, upload: bool) -> dict:
    """scp 传输；新版 scp 走 SFTP，若对端禁用 sftp-server 则退回传统 scp（-O）。"""
    target = "%s@%s:%s" % (conn.user, conn.host, shlex.quote(remote_path))
    last_err = ""
    for extra in ([], ["-O"]):
        cmd = _scp_base(conn) + extra
        if upload:
            cmd.extend([local_path, target])
        else:
            cmd.extend([target, local_path])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=max(conn.timeout, 120),
                                  stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            last_err = "scp 超时（%ss）" % max(conn.timeout, 120)
            continue
        if proc.returncode == 0:
            return {"ok": True, "cmd_mode": "legacy" if extra else "sftp"}
        last_err = (proc.stderr or proc.stdout or "").strip()
        if extra or "sftp" not in last_err.lower():
            break
    return {"ok": False, "error": last_err or "scp 失败"}


# ---------------------------------------------------------------------------
# 调度器探测与作业脚本
# ---------------------------------------------------------------------------

_SCHED_BINS = ("sbatch", "squeue", "scancel", "sacct", "scontrol",
               "qsub", "qstat", "qdel", "bsub")

_PROBE_SCHED = (
    'for c in ' + " ".join(_SCHED_BINS) + '; do '
    'p=$(command -v "$c" 2>/dev/null); echo "$c=${p:--}"; done'
)

_PROBE_TOOLS = (
    'for c in python3 python Rscript R conda mamba micromamba nextflow snakemake '
    'singularity apptainer docker module git; do '
    'p=$(command -v "$c" 2>/dev/null); echo "$c=${p:--}"; done'
)


def _parse_probe(text: str) -> dict:
    found = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip()
        if name:
            found[name] = "" if value == "-" else value
    return found


def _detect_scheduler(conn, cfg: dict):
    want = (cfg["scheduler"] or "auto").lower()
    if want in ("slurm", "pbs", "none"):
        return want, {}
    res = conn.execute(_PROBE_SCHED, timeout=60)
    bins = _parse_probe(res.get("output", ""))
    if bins.get("sbatch") and bins.get("squeue"):
        return "slurm", bins
    if bins.get("qsub") and bins.get("qstat"):
        return "pbs", bins
    return "none", bins


def _walltime_or_default(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "04:00:00"
    if ":" in text:
        return text
    try:
        hours = int(float(text))
    except Exception:
        return text
    return "%02d:00:00" % hours


def _build_job_script(cfg: dict, sched: str, command: str, name: str,
                      cpus, mem_gb, walltime, partition, gpu, queue,
                      modules, envs, workdir: str):
    """返回 (脚本内容, stdout 日志路径, stderr 日志路径, pid 文件路径)。"""
    job_dir = cfg["job_dir"].rstrip("/")
    logs = posixpath.join(job_dir, "logs")
    out_log = posixpath.join(logs, "%s-%%j.out" % name)
    err_log = posixpath.join(logs, "%s-%%j.err" % name)
    lines = ["#!/bin/bash"]
    if sched == "slurm":
        lines.append("#SBATCH --job-name=%s" % name)
        lines.append("#SBATCH --output=%s" % out_log)
        lines.append("#SBATCH --error=%s" % err_log)
        if cpus:
            lines.append("#SBATCH --cpus-per-task=%s" % int(cpus))
        if mem_gb:
            lines.append("#SBATCH --mem=%sG" % int(mem_gb))
        lines.append("#SBATCH --time=%s" % _walltime_or_default(walltime))
        if partition:
            lines.append("#SBATCH --partition=%s" % partition)
        if gpu:
            lines.append("#SBATCH --gres=gpu:%s" % gpu)
    elif sched == "pbs":
        out_log = posixpath.join(logs, "%s.out" % name)
        err_log = posixpath.join(logs, "%s.err" % name)
        lines.append("#PBS -N %s" % name)
        lines.append("#PBS -o %s" % out_log)
        lines.append("#PBS -e %s" % err_log)
        if cpus:
            lines.append("#PBS -l nodes=1:ppn=%s" % int(cpus))
        if mem_gb:
            lines.append("#PBS -l mem=%sgb" % int(mem_gb))
        lines.append("#PBS -l walltime=%s" % _walltime_or_default(walltime))
        if queue:
            lines.append("#PBS -q %s" % queue)
    else:
        out_log = posixpath.join(logs, "%s.log" % name)
        err_log = out_log

    pid_file = None
    lines.append("")
    lines.append('echo "[memomics] start $(date) on $(hostname)"')
    if sched == "none":
        # 无调度器：脚本自己记 PID，取消/查状态时按该 PID（会话组长）整组 kill
        pid_file = posixpath.join(logs, "%s.pid" % name)
        lines.append('echo $$ > %s' % shlex.quote(pid_file))
    if modules:
        for mod in modules:
            lines.append("module load %s || true" % mod)
    for key, value in (envs or {}).items():
        lines.append("export %s=%s" % (key, shlex.quote(str(value))))
    lines.append("cd %s" % shlex.quote(workdir or cfg["workdir"]))
    lines.append(command)
    lines.append("_memomics_rc=$?")
    lines.append('echo "[memomics] exit=$_memomics_rc $(date)"')
    lines.append("exit $_memomics_rc")
    return "\n".join(lines) + "\n", out_log, err_log, pid_file


def _upload_script(conn, cfg: dict, script_text: str, name: str) -> str:
    job_dir = cfg["job_dir"].rstrip("/")
    scripts_dir = posixpath.join(job_dir, "scripts")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    remote_path = posixpath.join(scripts_dir, "%s_%s.sh" % (name, stamp))
    mk = conn.execute("mkdir -p %s %s" % (shlex.quote(scripts_dir),
                                          shlex.quote(posixpath.join(job_dir, "logs"))),
                      timeout=60)
    if mk.get("returncode") != 0:
        raise RuntimeError("远端目录创建失败: %s" % (mk.get("output") or "").strip())
    with tempfile.TemporaryDirectory(prefix="memomics-job-") as tmp:
        local_script = os.path.join(tmp, "%s.sh" % name)
        # 远端是 Linux：强制 LF 换行
        with open(local_script, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(script_text)
        result = _scp_transfer(conn, local_script, remote_path, upload=True)
    if not result.get("ok"):
        raise RuntimeError("作业脚本上传失败: %s" % result.get("error"))
    chmod = conn.execute("chmod +x %s" % shlex.quote(remote_path), timeout=60)
    if chmod.get("returncode") != 0:
        raise RuntimeError("远端 chmod 失败: %s" % (chmod.get("output") or "").strip())
    return remote_path


def _parse_job_id(sched: str, output: str) -> str:
    text = (output or "").strip()
    if sched == "slurm":
        for token in text.replace("\n", " ").split():
            if token.isdigit():
                return token
    if sched == "pbs":
        first = text.splitlines()[0].strip() if text else ""
        if first:
            return first.split(".")[0]
    if text:
        return text.splitlines()[-1].strip()
    return ""


# ---------------------------------------------------------------------------
# 动作实现
# ---------------------------------------------------------------------------

def _action_check(cfg: dict, args: dict) -> str:
    conn = _get_conn(cfg)
    workdir = args.get("cwd") or cfg["workdir"]
    cmd = "\n".join([
        'echo "== host =="',
        'hostname; whoami; uname -srm',
        'echo "== cpu_mem =="',
        'nproc; (free -g 2>/dev/null | head -2 || true)',
        'echo "== workdir =="',
        'cd %s 2>/dev/null && { pwd; df -h . | tail -1; ls -1 | head -15; } '
        '|| echo "WORKDIR_MISSING: %s"' % (shlex.quote(workdir), workdir),
        'echo "== scheduler =="',
        _PROBE_SCHED,
        'echo "== tools =="',
        _PROBE_TOOLS,
        'echo "== versions =="',
        '(python3 -V 2>&1 || true); (Rscript -e \'cat(R.version.string)\' 2>&1 | head -1 || true)',
    ])
    res = conn.execute(cmd, timeout=max(cfg["timeout"], 120), bounded_capture=True)
    output = res.get("output", "") or ""
    if _is_conn_error(output):
        _drop_conn(cfg)
    sched_bins = _parse_probe(output)
    scheduler = cfg["scheduler"] if cfg["scheduler"] in ("slurm", "pbs", "none") else "auto"
    if scheduler == "auto":
        if sched_bins.get("sbatch") and sched_bins.get("squeue"):
            scheduler = "slurm"
        elif sched_bins.get("qsub") and sched_bins.get("qstat"):
            scheduler = "pbs"
        else:
            scheduler = "none"
    remote_home = getattr(conn, "_remote_home", "")
    return _ok({
        "status": "ok" if res.get("returncode") == 0 else "partial",
        "host": cfg["host"], "user": cfg["user"], "port": cfg["port"],
        "remote_home": remote_home,
        "workdir": workdir,
        "workdir_missing": ("WORKDIR_MISSING" in output),
        "scheduler": scheduler,
        "bins": {k: v for k, v in sched_bins.items() if v},
        "exit_code": res.get("returncode"),
        "output": _truncate(output, cfg["max_output_chars"]),
    })


def _action_run(cfg: dict, args: dict) -> str:
    command = (args.get("command") or "").strip()
    if not command:
        return _err("run 需要 command 参数")
    conn = _get_conn(cfg)
    cwd = args.get("cwd") or cfg["workdir"]
    timeout = int(args.get("timeout") or cfg["timeout"])
    if cwd:
        command = "cd %s && {\n%s\n}" % (shlex.quote(cwd), command)
    res = conn.execute(command, timeout=timeout, bounded_capture=True)
    output = res.get("output", "") or ""
    rc = res.get("returncode")
    if _is_conn_error(output):
        _drop_conn(cfg)
    return _ok({
        "status": "ok" if rc == 0 else ("timeout" if rc is None else "error"),
        "host": cfg["host"], "cwd": cwd,
        "exit_code": rc,
        "output": _truncate(output, cfg["max_output_chars"]),
    })


def _action_push(cfg: dict, args: dict) -> str:
    local_path = (args.get("local_path") or "").strip()
    remote_path = (args.get("remote_path") or "").strip()
    if not local_path:
        return _err("push 需要 local_path")
    local_abs = os.path.abspath(local_path)
    if not os.path.exists(local_abs):
        return _err("本地路径不存在: %s" % local_abs)
    if not remote_path:
        remote_path = _map_local_to_remote(cfg, local_abs)
        if not remote_path:
            return _err("未给 remote_path，且 remote.local_root/remote.remote_root 未配置，无法映射远端路径")
    conn = _get_conn(cfg)
    parent = posixpath.dirname(remote_path.rstrip("/")) or "."
    mkdir = conn.execute("mkdir -p %s" % shlex.quote(parent), timeout=60)
    if mkdir.get("returncode") != 0:
        return _err("远端目录创建失败: %s" % (mkdir.get("output") or "").strip())
    result = _scp_transfer(conn, local_abs, remote_path, upload=True)
    if not result.get("ok"):
        return _err("上传失败: %s" % result.get("error"))
    # Windows 侧 scp 复制过来的权限位常常带 group/other 写（0707 之类），
    # 集群是共享机器，统一收紧成"仅属主可读写"（0700/0600）。
    conn.execute("chmod -R u+rwX,go-rwx %s" % shlex.quote(remote_path), timeout=60)
    verify = conn.execute("du -sh %s 2>/dev/null; ls -ld %s" % (shlex.quote(remote_path),
                                                                shlex.quote(remote_path)),
                          timeout=60)
    return _ok({
        "local_path": local_abs,
        "remote_path": remote_path,
        "transport": result.get("cmd_mode"),
        "remote_check": (verify.get("output") or "").strip(),
    })


def _action_pull(cfg: dict, args: dict) -> str:
    remote_path = (args.get("remote_path") or "").strip()
    local_path = (args.get("local_path") or "").strip()
    if not remote_path:
        return _err("pull 需要 remote_path")
    if not local_path:
        local_path = _map_remote_to_local(cfg, remote_path)
        if not local_path:
            return _err("未给 local_path，且 remote.local_root/remote.remote_root 未配置，无法映射本地路径")
    local_abs = os.path.abspath(local_path)
    conn = _get_conn(cfg)
    exists = conn.execute("ls -ld %s" % shlex.quote(remote_path), timeout=60)
    if exists.get("returncode") != 0:
        return _err("远端路径不存在或无权限: %s" % (exists.get("output") or "").strip())
    os.makedirs(os.path.dirname(local_abs) or ".", exist_ok=True)
    result = _scp_transfer(conn, local_abs, remote_path, upload=False)
    if not result.get("ok"):
        return _err("下载失败: %s" % result.get("error"))
    size = 0
    if os.path.isdir(local_abs):
        for root, _dirs, files in os.walk(local_abs):
            for fname in files:
                try:
                    size += os.path.getsize(os.path.join(root, fname))
                except OSError:
                    pass
    elif os.path.exists(local_abs):
        size = os.path.getsize(local_abs)
    return _ok({
        "remote_path": remote_path,
        "local_path": local_abs,
        "transport": result.get("cmd_mode"),
        "local_bytes": size,
    })


def _action_submit(cfg: dict, args: dict) -> str:
    command = (args.get("command") or "").strip()
    if not command:
        return _err("submit 需要 command（要跑的作业命令）")
    conn = _get_conn(cfg)
    sched, _bins = _detect_scheduler(conn, cfg)
    name = (args.get("job_name") or "memomics").strip().replace(" ", "_")
    workdir = args.get("cwd") or cfg["workdir"]
    script_text, out_log, err_log, pid_file = _build_job_script(
        cfg, sched, command, name,
        args.get("cpus"), args.get("mem_gb"), args.get("walltime"),
        args.get("partition") or cfg["partition"], args.get("gpu"),
        args.get("queue") or cfg["queue"], args.get("modules") or [],
        args.get("envs") or {}, workdir,
    )
    script_remote = _upload_script(conn, cfg, script_text, name)
    if args.get("dry_run"):
        return _ok({
            "status": "dry_run", "scheduler": sched,
            "script_remote": script_remote, "script": script_text,
            "stdout": out_log, "stderr": err_log, "pid_file": pid_file,
        })

    if sched == "slurm":
        res = conn.execute("sbatch %s" % shlex.quote(script_remote),
                           timeout=max(cfg["timeout"], 120))
    elif sched == "pbs":
        res = conn.execute("cd %s && qsub %s" % (shlex.quote(workdir), shlex.quote(script_remote)),
                           timeout=max(cfg["timeout"], 120))
    else:
        # 无调度器：直接后台跑。必须用 setsid -f（fork 到新会话再脱离）：
        # 实测只写 "&"、或者 setsid 不带 -f、哪怕三个 fd 全部重定向，后台进程
        # 仍留在 sshd 的会话里，ssh 通道不关闭，客户端会一直挂到超时。
        # 作业 PID 由脚本自己写进 pid 文件（setsid -f 之后 $! 拿不到真 PID）。
        # rewrite_compound_background=False：hermes 的 execute() 默认会把 "A && B &"
        # 改写成 "{ A && B & }"，会把后台提交命令改坏（bash: syntax error near 'echo'）。
        probe = conn.execute("setsid -f true >/dev/null 2>&1 && echo yes || echo no", timeout=60)
        detached = "yes" in (probe.get("output") or "")
        if detached:
            submit_cmd = ("cd %s && setsid -f bash %s > %s 2>&1 < /dev/null; sleep 1; "
                          "cat %s 2>/dev/null || echo '(pid 文件还没写出来)'"
                          % (shlex.quote(workdir), shlex.quote(script_remote),
                             shlex.quote(out_log), shlex.quote(pid_file or "")))
        else:
            # 兜底：没有 setsid -f 的老系统（部分 BusyBox）。作业能起，但这条
            # 连接会被占住，所以给个短超时，PID 从 pid 文件读。
            submit_cmd = ("cd %s && nohup bash %s > %s 2>&1 < /dev/null & sleep 1; "
                          "cat %s 2>/dev/null || echo '(pid 文件还没写出来)'"
                          % (shlex.quote(workdir), shlex.quote(script_remote),
                             shlex.quote(out_log), shlex.quote(pid_file or "")))
        res = conn.execute(submit_cmd, timeout=(120 if detached else 20),
                           rewrite_compound_background=False)
    output = (res.get("output") or "").strip()
    rc = res.get("returncode")
    if rc != 0:
        return _err("提交失败（exit=%s）: %s" % (rc, _truncate(output, 2000)),
                    scheduler=sched, script_remote=script_remote)
    job_id = _parse_job_id(sched, output)
    if sched == "none":
        pid_match = re.search(r"(?m)^\s*(\d+)\s*$", output)
        if pid_match:
            job_id = pid_match.group(1)
    record = {
        "ts": _now(), "host": cfg["host"], "user": cfg["user"],
        "scheduler": sched, "job_id": job_id, "name": name,
        "script": script_remote, "stdout": out_log, "stderr": err_log,
        "workdir": workdir, "command": command[:4000], "pid_file": pid_file,
    }
    _record_job(record)
    return _ok({
        "status": "submitted", "scheduler": sched, "job_id": job_id,
        "name": name, "script_remote": script_remote,
        "stdout": out_log, "stderr": err_log,
        "submit_output": _truncate(output, 1000),
        "next": "用 action='status' 查状态，完成后用 action='logs' 读日志、action='pull' 取产物",
    })


def _expand_job_pattern(path: str, job_id: str, name: str = "", user: str = "") -> str:
    """展开 Slurm --output/--error 路径里的占位符（%j/%A/%x/%u...）。

    sbatch 提交时作业文件名带 %j，由 Slurm 在落盘时展开成真实文件名；我们事后再
    按记录里的模板去找日志，就必须自己展开——否则永远读到 "No such file or
    directory"（实测 job 1/4/6/7 全部踩到，state 也因此只能给 UNKNOWN）。
    """
    if not path or "%" not in path or not job_id:
        return path
    out = path.replace("%%", "\x00")           # %% 是字面量百分号，先保护起来
    for k, v in (("%j", job_id), ("%J", job_id), ("%A", job_id), ("%a", "0"),
                 ("%x", name or "memomics"), ("%u", user or "")):
        out = out.replace(k, str(v))
    return out.replace("\x00", "%")


def _derive_state(sched: str, output: str) -> str:
    """从 status 命令输出里判断作业状态。

    注意不能对整段输出做关键字扫描：日志尾部里的 "not running" 含 "RUNNING"，
    会把已经结束的作业误判成 RUNNING。所以按调度器分段解析。
    """
    text = output or ""
    if sched == "none":
        if "STATE=RUNNING" in text:
            return "RUNNING"
        exit_marker = re.search(r"\[memomics\] exit=(\d+)", text)
        if exit_marker:
            return "COMPLETED" if exit_marker.group(1) == "0" else "FAILED"
        if "STATE=NOT_RUNNING" in text:
            return "UNKNOWN(进程已结束，日志里没有结束标记，可能被 kill 或还在写)"
        return "UNKNOWN"
    if sched == "slurm":
        m = re.search(r"== squeue ==\n(.*?)(?=\n== |\Z)", text, re.S)
        section = (m.group(1) if m else "").upper()
        for st in ("PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "SUSPENDED"):
            if st in section:
                return st
        # 作业一离开队列 squeue 就查不到；scontrol 还能看到刚结束的作业（Slurm 默认
        # MinJobAge=300s 内保留），最后才退到 sacct（需要 accounting 数据库——很多
        # 单机/test 集群是关的，实测 "Slurm accounting storage is disabled"）。
        m = re.search(r"== scontrol ==\n(.*?)(?=\n== |\Z)", text, re.S)
        section = (m.group(1) if m else "").upper()
        for st in ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY",
                   "NODE_FAIL", "PREEMPTED"):
            if st in section:
                return st
        m = re.search(r"== sacct ==\n(.*?)(?=\n== |\Z)", text, re.S)
        section = (m.group(1) if m else "").upper()
        for st in ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY",
                   "NODE_FAIL", "PREEMPTED"):
            if st in section:
                return st
        if "ACCOUNTING STORAGE IS DISABLED" in text.upper():
            return ("UNKNOWN(队列与 scontrol 都没记录，sacct 未启用 accounting；"
                    "作业大概率已结束——直接 action='logs' 看输出)")
        return "UNKNOWN"
    m = re.search(r"job_state\s*=\s*(\w+)", text)
    return m.group(1).upper() if m else "UNKNOWN"


def _action_status(cfg: dict, args: dict) -> str:
    job_id = str(args.get("job_id") or "").strip()
    rec = _find_job(cfg, job_id) if job_id else None
    assumed = False
    if not job_id:
        recent = [r for r in _iter_jobs(50) if r.get("host") == cfg["host"]]
        if not recent:
            return _err("status 需要 job_id（本机还没有提交记录，先用 action='submit'）")
        rec = recent[-1]
        job_id = str(rec.get("job_id"))
        assumed = True
    conn = _get_conn(cfg)
    sched = ((rec or {}).get("scheduler")
             or (cfg["scheduler"] if cfg["scheduler"] in ("slurm", "pbs", "none") else "auto"))
    if sched == "auto":
        sched, _ = _detect_scheduler(conn, cfg)
    if sched == "slurm":
        qid = shlex.quote(job_id)
        cmd = ("echo '== squeue =='; squeue -j %s -h -o '%%T %%M %%R' 2>&1; "
               "echo '== scontrol =='; (scontrol show job %s 2>&1 "
               "| grep -E 'JobState|RunTime|ExitCode' | head -5); "
               "echo '== sacct =='; (sacct -j %s --format=JobID,State,Elapsed,ExitCode -P -n 2>&1 | head -5)"
               % (qid, qid, qid))
    elif sched == "pbs":
        cmd = ("echo '== qstat =='; (qstat -f %s 2>&1 | grep -E 'job_state|exec_host|resources_used' "
               "|| qstat -x %s 2>&1 | grep -E 'job_state' || echo 'not in queue')"
               % (shlex.quote(job_id), shlex.quote(job_id)))
    else:
        pid_file = str((rec or {}).get("pid_file") or "")
        if pid_file:
            cmd = ("pidf=%s; if [ -f \"$pidf\" ]; then p=$(cat \"$pidf\"); "
                   "if kill -0 \"$p\" 2>/dev/null; then echo \"STATE=RUNNING pid=$p\"; "
                   "else echo \"STATE=NOT_RUNNING pid=$p\"; fi; "
                   "else echo 'STATE=UNKNOWN 没有 pid 文件'; fi; "
                   "ps -p %s -o pid=,etime=,stat=,cmd= 2>/dev/null || true"
                   % (shlex.quote(pid_file), shlex.quote(job_id)))
        else:
            cmd = ("ps -p %s -o pid=,etime=,stat=,cmd= 2>/dev/null || echo 'not running'"
                   % shlex.quote(job_id))
    out_path = err_path = ""
    if rec and rec.get("stdout"):
        out_path = _expand_job_pattern(str(rec["stdout"]), job_id,
                                       str(rec.get("name") or ""), cfg["user"])
        err_path = _expand_job_pattern(str(rec.get("stderr") or ""), job_id,
                                       str(rec.get("name") or ""), cfg["user"])
        cmd += "\necho '== log tail =='; tail -n 15 %s 2>/dev/null || echo '(no log yet)'" % shlex.quote(out_path)
    res = conn.execute(cmd, timeout=max(cfg["timeout"], 120))
    output = (res.get("output") or "").strip()
    state = _derive_state(sched, output)
    return _ok({
        "job_id": job_id, "scheduler": sched, "name": (rec or {}).get("name"),
        "state": state,
        **({"note": "未指定 job_id，用的是最近一次提交"} if assumed else {}),
        "stdout": out_path or (rec or {}).get("stdout"),
        "stderr": err_path or (rec or {}).get("stderr"),
        "output": _truncate(output, cfg["max_output_chars"]),
    })


def _action_logs(cfg: dict, args: dict) -> str:
    lines = int(args.get("lines") or 100)
    job_id = str(args.get("job_id") or "").strip()
    path = (args.get("path") or "").strip()
    rec = _find_job(cfg, job_id) if job_id else None
    if not path:
        if rec is None:
            recent = [r for r in _iter_jobs(20) if r.get("host") == cfg["host"]]
            if len(recent) == 1:
                rec = recent[0]
        if rec is not None:
            job_id = job_id or str(rec.get("job_id") or "")
            path = str(rec.get("stdout") or "")
    if not path:
        return _err("logs 需要 job_id（最近一次提交）或 path（远端日志文件）")
    conn = _get_conn(cfg)
    # 记录里存的是作业文件名模板（slurm 是 %j 形式），读之前必须展开成真实文件名
    name = str((rec or {}).get("name") or "")
    path = _expand_job_pattern(path, job_id, name, cfg["user"])
    err_path = (_expand_job_pattern(str((rec or {}).get("stderr") or ""), job_id, name, cfg["user"])
                or (path[:-4] + ".err" if path.endswith(".out") else path))
    same_file = posixpath.normpath(err_path) == posixpath.normpath(path)
    if same_file:
        # 无调度器分支的作业脚本把 stdout/stderr 合并写同一个日志，别再重复打印一遍
        cmd = "echo '== %s =='; tail -n %d %s 2>&1" % (path, lines, shlex.quote(path))
    else:
        cmd = ("echo '== %s =='; tail -n %d %s 2>&1; echo '== stderr =='; "
               "if [ -f %s ]; then tail -n %d %s; else echo '(no stderr file)'; fi"
               % (path, lines, shlex.quote(path), shlex.quote(err_path),
                  max(lines // 4, 20), shlex.quote(err_path)))
    res = conn.execute(cmd, timeout=max(cfg["timeout"], 120))
    return _ok({
        "path": path, "lines": lines, "exit_code": res.get("returncode"),
        "output": _truncate((res.get("output") or "").strip(), cfg["max_output_chars"]),
    })


def _action_cancel(cfg: dict, args: dict) -> str:
    job_id = str(args.get("job_id") or "").strip()
    if not job_id:
        return _err("cancel 需要 job_id")
    rec = _find_job(cfg, job_id)
    conn = _get_conn(cfg)
    sched = (rec or {}).get("scheduler") or cfg["scheduler"]
    if sched == "auto":
        sched, _ = _detect_scheduler(conn, cfg)
    if sched == "slurm":
        cmd = "scancel %s" % shlex.quote(job_id)
    elif sched == "pbs":
        cmd = "qdel %s" % shlex.quote(job_id)
    else:
        pid_file = str((rec or {}).get("pid_file") or "")
        if pid_file:
            pid_expr = "$(cat %s 2>/dev/null || echo %s)" % (shlex.quote(pid_file),
                                                             shlex.quote(job_id))
        else:
            pid_expr = shlex.quote(job_id)
        # setsid 启动的作业是会话组长：先整组 TERM，再兜底杀进程本身和直接子进程
        cmd = ("p=%s; kill -TERM -- -\"$p\" 2>/dev/null; kill -TERM \"$p\" 2>/dev/null; "
               "pkill -TERM -P \"$p\" 2>/dev/null; sleep 1; "
               "if kill -0 \"$p\" 2>/dev/null; then echo \"still running pid=$p\"; "
               "else echo \"stopped pid=$p\"; fi" % pid_expr)
    res = conn.execute(cmd, timeout=120)
    return _ok({
        "job_id": job_id, "scheduler": sched, "exit_code": res.get("returncode"),
        "output": (res.get("output") or "").strip() or "已发送取消请求",
    })


def _action_jobs(cfg: dict, args: dict) -> str:
    conn = _get_conn(cfg)
    sched = cfg["scheduler"] if cfg["scheduler"] in ("slurm", "pbs", "none") else "auto"
    if sched == "auto":
        sched, _ = _detect_scheduler(conn, cfg)
    if sched == "slurm":
        cmd = ("echo '== squeue =='; squeue -u \"$USER\" -o '%.12i %.9P %.30j %.8T %.10M %.6D %R' 2>&1 | head -30; "
               "echo '== sacct (today) =='; (sacct -u \"$USER\" --starttime today --format=JobID,JobName,State,Elapsed -P -n 2>&1 | tail -20)")
    elif sched == "pbs":
        cmd = "qstat -u \"$USER\" 2>&1 | head -30"
    else:
        # 无调度器时只列本工具提交的作业（按作业目录过滤），避免把登录节点进程全倒出来
        cmd = ("out=$(ps -u \"$USER\" -o pid=,etime=,cmd= 2>/dev/null | grep -F %s | grep -v grep "
               "| cut -c1-160 | head -30); if [ -n \"$out\" ]; then echo \"$out\"; "
               "else echo '(没有本工具提交的作业在跑)'; fi" % shlex.quote(cfg["job_dir"]))
    res = conn.execute(cmd, timeout=max(cfg["timeout"], 120))
    return _ok({
        "scheduler": sched,
        "output": _truncate((res.get("output") or "").strip(), cfg["max_output_chars"]),
        "local_records": [{k: r.get(k) for k in ("ts", "job_id", "name", "scheduler", "workdir")}
                          for r in _iter_jobs(10) if r.get("host") == cfg["host"]][-5:],
    })


_ACTIONS = {
    "check": _action_check,
    "run": _action_run,
    "push": _action_push,
    "pull": _action_pull,
    "submit": _action_submit,
    "status": _action_status,
    "logs": _action_logs,
    "cancel": _action_cancel,
    "jobs": _action_jobs,
}


def remote_cluster_handler(args=None, **kwargs) -> str:
    args = args or {}
    cfg = _load_remote_config()
    if not remote_cluster_enabled():
        return _err(
            "远端集群未配置或未启用。请在 hermes_home/config.yaml 增加：\n"
            "remote:\n  enabled: true\n  host: <登录节点>\n  user: <用户名>\n"
            "  key: <私钥路径>\n  workdir: <远端工作目录>\n"
            "（或用环境变量 MEMOMICS_REMOTE_ENABLED/HOST/USER/KEY/WORKDIR 临时覆盖）"
        )
    action = str(args.get("action") or "").strip().lower()
    if action not in _ACTIONS:
        return _err("未知 action: %r（可选：%s）" % (action, ", ".join(sorted(_ACTIONS))))
    try:
        return _ACTIONS[action](cfg, args)
    except Exception as exc:
        logger.exception("remote_cluster action=%s 失败", action)
        _drop_conn(cfg)
        return _err("%s 执行失败: %s" % (action, exc),
                    hint="连接类错误请先用 action='check' 排查（密钥/端口/跳板机/known_hosts）")


SCHEMA = {
    "name": "remote_cluster",
    "description": (
        "远端集群（SSH）执行与作业调度 —— 把重活送到集群，产物拉回本地继续分析。\n"
        "适用：本地算力/内存不够、要跑需要排队的大作业（CellRanger、比对、大矩阵、长训练）、"
        "数据本来就放在集群上。\n"
        "不适用：本地几秒能跑完的小脚本（直接用 execute_python / execute_r）。\n"
        "用法：先 action='check' 自检（连通性/调度器/资源/工作目录），再决定 run 还是 submit。\n"
        "  • run    —— 在登录节点跑**轻量**命令（ls/du/head/which/环境自检）。"
        "禁止在登录节点跑重计算，会被管理员封号。\n"
        "  • submit —— 生成作业脚本并提交（Slurm 用 sbatch，PBS 用 qsub，无调度器则 setsid 脱离会话后台跑），"
        "返回 job_id；随后 status 看状态、logs 读日志、cancel 取消。\n"
        "  • push / pull —— 本地 ↔ 远端传文件（大文件先 push 再 submit，产物 pull 回本地）。\n"
        "  • jobs   —— 列队列与最近提交记录。\n"
        "连接配置在 hermes_home/config.yaml 的 remote: 段（host/user/port/key/workdir/scheduler/"
        "local_root/remote_root），需密钥登录（BatchMode，不会弹密码输入）；未配置时本工具不可见。\n"
        "⚠️ 两点别搞混：① 本工具只把**命令/作业**送到远端，execute_python / execute_r 的持久内核仍在本地跑——"
        "要在集群上算就把代码写成脚本交给 run/submit；② 远端路径（/home/you/...）与本地路径（E:/...）是两套，"
        "push/pull 可用 local_root/remote_root 自动换算。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["check", "run", "push", "pull", "submit", "status", "logs", "cancel", "jobs"],
                "description": "要执行的动作",
            },
            "command": {
                "type": "string",
                "description": "run/submit 要执行的命令（submit 时就是作业正文，可多行）",
            },
            "cwd": {"type": "string", "description": "远端工作目录（默认用配置的 workdir）"},
            "timeout": {"type": "integer", "description": "run 的超时秒数（默认配置值 300）"},
            "local_path": {"type": "string", "description": "push：本地源路径；pull：本地目标路径（可省，按路径映射推导）"},
            "remote_path": {"type": "string", "description": "push：远端目标路径（可省，按路径映射推导）；pull：远端源路径（必填）"},
            "job_id": {"type": "string", "description": "status/logs/cancel 的作业号（可省，默认最近一次提交）"},
            "job_name": {"type": "string", "description": "submit 作业名（默认 memomics）"},
            "cpus": {"type": "integer", "description": "submit：CPU 核数"},
            "mem_gb": {"type": "integer", "description": "submit：内存 GB"},
            "walltime": {"type": "string", "description": "submit：时限，如 '04:00:00' 或 '12'（小时）"},
            "partition": {"type": "string", "description": "submit：Slurm 分区（默认配置的 partition）"},
            "queue": {"type": "string", "description": "submit：PBS 队列（默认配置的 queue）"},
            "gpu": {"type": "string", "description": "submit：GPU 数量，如 '1'（Slurm --gres=gpu:<n>）"},
            "modules": {"type": "array", "items": {"type": "string"}, "description": "submit：作业开头 module load 的模块名列表"},
            "envs": {"type": "object", "description": "submit：作业环境变量 {名: 值}"},
            "dry_run": {"type": "boolean", "description": "submit 时 true = 只生成脚本不提交"},
            "path": {"type": "string", "description": "logs：直接指定远端日志文件路径"},
            "lines": {"type": "integer", "description": "logs：看末尾多少行（默认 100）"},
        },
        "required": ["action"],
    },
}


def _register():
    from tools.registry import registry
    registry.register(
        name="remote_cluster",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: remote_cluster_handler(args),
        check_fn=remote_cluster_enabled,
        emoji="🖧",
        max_result_size_chars=40_000,
    )


_register()
