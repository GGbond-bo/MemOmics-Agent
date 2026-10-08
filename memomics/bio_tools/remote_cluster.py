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
      scheduler: auto               # auto | slurm | pbs | gridengine | none
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
    "default_node": "MEMOMICS_REMOTE_NODE",
    "node_policy": "MEMOMICS_REMOTE_NODE_POLICY",
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
    # --- 多节点（MobaXterm 式命名节点）---
    "nodes": {},                 # {名字: {} | "主机名" | {host/user/port/key/...}}
    "default_node": "",          # 配了多个节点时可指定默认；留空则多节点必须显式指定
    "node_policy": "ask",        # ask（没说就问）| 预留 auto（自动挑最闲）
    "allow_unlisted_nodes": True,  # True: 传了未登记的名字时按裸主机连（并在返回里标注）
    # --- Grid Engine（SGE/UGE）微调：按集群 qconf 实际情况改 ---
    "ge_pe": "smp",              # 并行环境名（qconf -spl 可查；多核作业用 #$ -pe <名> N）
    "ge_mem_res": "vf",          # 内存资源名（华大系 GE 是 vf=virtual_free；别的 GE 常见 h_vmem/mem_free）
    "ge_gpu_res": "num_gpu",     # GPU 资源名
    "auto_record_env": True,     # check 成功后把节点环境自动沉淀到 🧩 环境管理（environment.json）
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
    cfg["nodes"] = _normalize_nodes(raw.get("nodes"))
    cfg["default_node"] = str(cfg.get("default_node") or "").strip()
    cfg["node_policy"] = str(cfg.get("node_policy") or "ask").strip().lower() or "ask"
    cfg["allow_unlisted_nodes"] = _truthy(cfg.get("allow_unlisted_nodes", True))

    _CFG_CACHE["mtime"] = mtime
    _CFG_CACHE["cfg"] = cfg
    return cfg


def remote_cluster_enabled() -> bool:
    """check_fn：没配置 remote: 段（或 nodes 段）时工具对模型不可见。"""
    cfg = _load_remote_config()
    if not cfg["enabled"]:
        return False
    table = _node_table(cfg)
    if not table:
        return False
    # user 可以是全局共享，也可以在某个节点上单独给
    return bool(cfg["user"]) or any(str(t.get("user") or "").strip() for t in table.values())


# ---------------------------------------------------------------------------
# 多节点（命名节点）—— MobaXterm 式的命名连接，按名字选机器
# ---------------------------------------------------------------------------

_NODE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")

# 节点条目里允许覆盖的字段；其余一律跟共享配置走（同一个集群路径一样，没必要重复配）
_NODE_OVERRIDE_KEYS = (
    "host", "user", "port", "key", "workdir", "job_dir", "scheduler",
    "partition", "queue", "timeout", "proxy_jump", "extra_ssh_options",
    "note", "role",
)

_LITERAL_HOST_RE = re.compile(r"^(?:([^@\s]+)@)?([A-Za-z0-9._-]+)(?::(\d+))?$")


def _normalize_nodes(raw) -> dict:
    """把 config 的 nodes: 段规范化成 {名字: {显式覆盖字段}}。

    支持三种写法（都合法，按需混用）::

        remote:
          nodes:
            ssh3: {}                    # 名字本身就是 ssh 主机名 / ~/.ssh/config 里的别名
            ssh5: ssh5.example.org      # 字符串 = 显式主机名
            gpu1:                       # 完整写法：只写要覆盖的字段
              host: 10.0.0.5
              user: zhang
              port: 2222
              key: C:/Users/me/.ssh/id_gpu
              proxy_jump: bastion.example.org
              workdir: /data/zhang
              note: 带 A100 的节点

    名字只允许 [A-Za-z0-9._-]，因为节点名会进入远端作业名/日志名/pid 文件名。
    中文等名字请写在 note 里。
    """
    if raw is None:
        return {}
    if isinstance(raw, (list, tuple)):
        raw = {str(x).strip(): {} for x in raw if str(x).strip()}
    if not isinstance(raw, dict):
        logger.warning("remote.nodes 必须是字典或列表，已忽略（当前类型 %s）", type(raw).__name__)
        return {}
    out: dict = {}
    for name, spec in raw.items():
        key = str(name).strip()
        if not key or key.startswith("_"):
            continue
        if not _NODE_NAME_RE.match(key):
            logger.warning("remote.nodes 忽略非法节点名 %r（只允许字母数字和 . _ -，不超过 48 字符）", key)
            continue
        entry: dict = {}
        if spec is None:
            entry = {}
        elif isinstance(spec, str):
            entry = {"host": spec.strip() or key}
        elif isinstance(spec, dict):
            for k in _NODE_OVERRIDE_KEYS:
                val = spec.get(k)
                if val is None or (isinstance(val, str) and not val.strip()):
                    continue
                entry[k] = _as_list(val) if k == "extra_ssh_options" else val
        else:
            logger.warning("remote.nodes.%s 的值类型不支持（%s），按空配置处理",
                           key, type(spec).__name__)
        entry.setdefault("host", key)   # 名字默认就当主机名/ssh 别名用
        out[key] = entry
    return out


def _node_table(cfg: dict) -> dict:
    """名字 → 展开后的连接配置（共享字段 + 节点覆盖 + 跳板机）。

    没有 nodes 段时退化成单个节点（名字 = host），旧配置行为完全不变。
    """
    table: dict = {}
    nodes = cfg.get("nodes") or {}
    if not nodes:
        host = str(cfg.get("host") or "").strip()
        if host:
            node = dict(cfg)
            node["_name"] = host
            node["_note"] = "（单节点配置，未命名）"
            node["_role"] = ""
            node["_shared"] = True
            table[host] = node
        return table

    for name, entry in nodes.items():
        node = dict(cfg)
        node.update({k: v for k, v in entry.items() if k not in ("note", "role")})
        node["_name"] = name
        node["_note"] = str(entry.get("note") or "")
        node["_role"] = str(entry.get("role") or "")
        node["_shared"] = False
        node["host"] = str(node.get("host") or name).strip()
        # 节点覆盖了 workdir 但没覆盖 job_dir 时，作业目录要跟着走
        if "workdir" in entry and "job_dir" not in entry:
            node["job_dir"] = posixpath.join(str(node.get("workdir") or "~").rstrip("/"),
                                             "memomics_jobs")
        try:
            node["port"] = int(str(node.get("port") or 22).strip() or 22)
        except Exception:
            node["port"] = 22
        node["workdir"] = str(node.get("workdir") or "~").strip() or "~"
        if not str(node.get("job_dir") or "").strip():
            node["job_dir"] = posixpath.join(node["workdir"], "memomics_jobs")
        # 连接层要的额外选项：节点自己的 + 跳板机（-o ProxyJump 对 ssh/scp 都有效）
        extra = _as_list(node.get("extra_ssh_options"))
        jump = str(entry.get("proxy_jump") or "").strip()
        if jump and not any("proxyjump" in str(x).lower() or str(x) == "-J" for x in extra):
            extra = extra + ["-o", "ProxyJump=%s" % jump]
        node["extra_ssh_options"] = extra
        table[name] = node
    return table


def _nodes_brief(table: dict) -> list:
    return [{"name": n, "host": t.get("host"), "user": t.get("user"),
             "note": t.get("_note") or "", "role": t.get("_role") or ""}
            for n, t in table.items()]


def _select_node(cfg: dict, requested: str = ""):
    """按名字选节点 → (node_cfg, name, 错误JSON)。

    选点策略（用户 2026-09 定的 ②）：
      • 只配了 1 个节点 → 静默用它（用户说「用集群」就直接跑，不打断）
      • 配了多个节点、调用没指定、也没配 default_node → **硬拦**，返回 status=needs_node
        并列出候选，要求先问清用户；绝不自己挑一台
      • 指定了名字 → 必须命中已配置节点（大小写不敏感）；未登记但形如主机名/别名时，
        按裸主机连并在返回值里标注（allow_unlisted_nodes=false 可关掉这个兜底）
    """
    table = _node_table(cfg)
    if not table:
        return None, "", _err(
            "没有可用的远端节点：请在 hermes_home/config.yaml 的 remote: 段配置 "
            "host: <登录节点> 或 nodes: {名字: {host: ...}}"
        )
    req = str(requested or "").strip()

    if req:
        for name, node in table.items():
            if name.lower() == req.lower():
                return node, name, None
        m = _LITERAL_HOST_RE.match(req)
        if m and cfg.get("allow_unlisted_nodes", True):
            user, host, port = m.group(1), m.group(2), m.group(3)
            node = dict(cfg)
            node["host"] = host
            if user:
                node["user"] = user
            if port:
                node["port"] = int(port)
            node["_name"] = req
            node["_note"] = "⚠️ 未登记在 nodes 里，按裸主机连接"
            node["_role"] = ""
            node["_shared"] = False
            node["_unlisted"] = True
            return node, req, None
        return None, "", _err(
            "节点名 %r 不在配置里，也不是合法主机名。已配置的节点：%s"
            % (req, "、".join(table)),
            nodes=_nodes_brief(table),
            hint="要用哪个节点请先确认；名字写错了就改 node 参数，或先在 config.yaml 的 remote.nodes 里登记",
        )

    default_node = str(cfg.get("default_node") or "").strip()
    if default_node:
        for name, node in table.items():
            if name.lower() == default_node.lower():
                return node, name, None
        return None, "", _err(
            "remote.default_node=%r 不在 nodes 里，已配置：%s"
            % (default_node, "、".join(table)),
            nodes=_nodes_brief(table),
        )

    if len(table) == 1:
        name = next(iter(table))
        return table[name], name, None

    # 多个节点 + 没指定 → 硬拦（这就是「没说就问清楚」）
    return None, "", json.dumps({
        "status": "needs_node",
        "error": ("配置了多个远端节点，但这次调用没指定用哪个。"
                  "**先问用户要在哪个节点上跑**，拿到答复后再用 node=\"<名字>\" 重新调用；"
                  "不要自己挑一个，也不要用最近一次用过的。"),
        "nodes": _nodes_brief(table),
        "usage": "remote_cluster(action='submit', node='ssh3', command='...')",
        "policy": cfg.get("node_policy") or "ask",
        "tip": ("想挑最闲的节点：先 action='nodes' 看 load_per_cpu/idle_now，再把选中的名字传进来"
                "（node_policy=auto 的自动择优还没实现，目前仍按 ask 处理）。"),
    }, ensure_ascii=False, indent=2)


def _node_slug(name: str) -> str:
    """节点名 → 文件名安全的后缀（中文名会带短哈希，保证两个名字不会撞成同一个）。"""
    raw = str(name or "").strip()
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", raw)
    if not slug:
        return "node"
    if slug != raw:
        slug = "%s-%s" % (slug, hashlib.md5(raw.encode("utf-8")).hexdigest()[:4])
    return slug[:48]


def _rec_matches_node(rec: dict, cfg: dict) -> bool:
    """作业记录是否属于当前节点。

    记录里**有** node 字段就必须按节点名严格比：多个节点可能是同一个集群的不同入口，
    host 完全可能一样（例如 ssh3/ssh5 都指向同一台登录机），再退回比 host 会把
    A 节点的作业当成 B 节点的。只有升级前的旧记录（没有 node 字段）才退化成比 host。
    """
    name = str(cfg.get("_name") or "")
    rec_node = str(rec.get("node") or "")
    if rec_node:
        return bool(name) and rec_node == name
    return bool(cfg.get("host")) and rec.get("host") == cfg.get("host")


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
    # 键里带上密钥路径：同一个 host 用不同密钥/不同用户时不能复用同一条连接
    return "%s@%s:%s|%s" % (cfg["user"], cfg["host"], cfg["port"], cfg.get("key") or "")


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
        # job_dir 开头的 ~ 展开成远端家目录：scp 的目标路径不经 shell 解释，
        # 字面 '~/...' 会被当成相对路径直接打不开（2026-10-08 dry_run 实踩）
        jd = str(cfg.get("job_dir") or "")
        if jd.startswith("~"):
            home = str(getattr(conn, "_remote_home", "") or "").rstrip("/")
            if home:
                cfg["job_dir"] = home + jd[1:]
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
        if str(rec.get("job_id")) == str(job_id) and _rec_matches_node(rec, cfg):
            return rec
    return None


def _job_owner_node(job_id: str) -> str:
    """这个 job_id 在记录里属于哪个节点（没有记录返回空串）。"""
    for rec in reversed(_iter_jobs()):
        if str(rec.get("job_id")) == str(job_id):
            return str(rec.get("node") or "")
    return ""


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
    'p=$(command -v "$c" 2>/dev/null); echo "$c=${p:--}"; done; '
    # qsub 的版本行用来区分 Grid Engine（SGE 8.1.9 / Univa Grid Engine）和 PBS/Torque
    # （usage: qsub ...）——两者二进制同名但指令语法完全不同（#$ vs #PBS）
    'v=$(qsub -help 2>&1 | head -1); echo "qsub_ver=${v:--}"'
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


def _sched_from_probe(bins: dict) -> str:
    """探测结果 → 调度器名。slurm 看 sbatch；qsub/qstat 同名二义性用 qsub 版本行区分 GE/PBS。"""
    if bins.get("sbatch") and bins.get("squeue"):
        return "slurm"
    if bins.get("qsub") and bins.get("qstat"):
        ver = str(bins.get("qsub_ver") or "")
        if re.search(r"(?i)\b(SGE|UGE|Grid ?Engine|Univa)\b", ver):
            return "gridengine"
        return "pbs"
    return "none"


def _detect_scheduler(conn, cfg: dict):
    want = (cfg["scheduler"] or "auto").lower()
    if want in ("slurm", "pbs", "gridengine", "none"):
        return want, {}
    res = conn.execute(_PROBE_SCHED, timeout=60)
    bins = _parse_probe(res.get("output", ""))
    return _sched_from_probe(bins), bins


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
    elif sched == "gridengine":
        # SGE/UGE：#$ 指令。日志走 GE 默认命名 <jobname>.o<jobid>/.e<jobid>（落在 #$ -cwd
        # 指定的提交目录）——不要给 GE 传 -o 带 %j 的路径：GE 不认识 %j，会生成一个字面量
        # 名叫 %j 的文件。记录里的 %j 模板只给我们自己用，事后由 _expand_job_pattern 展开。
        wd = workdir or cfg["workdir"]
        out_log = posixpath.join(wd, "%s.o%%j" % name)
        err_log = posixpath.join(wd, "%s.e%%j" % name)
        lines.append("#$ -N %s" % name)
        lines.append("#$ -cwd")
        lines.append("#$ -S /bin/bash")
        if queue:
            lines.append("#$ -q %s" % queue)
        if cpus:
            lines.append("#$ -pe %s %s" % (cfg.get("ge_pe") or "smp", int(cpus)))
        if mem_gb:
            lines.append("#$ -l %s=%sG" % (cfg.get("ge_mem_res") or "vf", int(mem_gb)))
        lines.append("#$ -l h_rt=%s" % _walltime_or_default(walltime))
        if gpu:
            lines.append("#$ -l %s=%s" % (cfg.get("ge_gpu_res") or "num_gpu", gpu))
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
    if sched == "gridengine":
        # GE：'Your job 123456 ("name") has been submitted' → 抓第一个数字
        m = re.search(r"\b(\d+)\b", text)
        if m:
            return m.group(1)
        return ""
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
    res = _exec_env(conn, cmd, timeout=max(cfg["timeout"], 120))
    output = res.get("output", "") or ""
    if _is_conn_error(output):
        _drop_conn(cfg)
    sched_bins = _parse_probe(output)
    scheduler = cfg["scheduler"] if cfg["scheduler"] in ("slurm", "pbs", "gridengine", "none") else "auto"
    if scheduler == "auto":
        scheduler = _sched_from_probe(sched_bins)
    remote_home = getattr(conn, "_remote_home", "")
    # 自检成功 → 自动把节点环境沉淀到 🧩 环境管理（environment.json cluster.nodes.<名>.probed；
    # 用户手填的声明字段永不覆盖）。失败只记 warning，绝不影响自检本身。
    env_sync = ""
    if cfg.get("auto_record_env", True):
        try:
            from memomics.bio_tools import env_inventory as _ei
            rec = _ei.record_cluster_node(cfg.get("_name") or cfg["host"], {
                "status": "ok", "host": cfg["host"], "user": cfg["user"],
                "scheduler": scheduler, "workdir": workdir,
                "workdir_missing": ("WORKDIR_MISSING" in output),
                "remote_home": remote_home,
                "bins": {k: v for k, v in sched_bins.items() if v and not str(k).endswith("_ver")},
                "output": output,
            })
            if rec.get("ok"):
                env_sync = ("已同步到 🧩 环境管理（environment.json → cluster.nodes.%s.probed）"
                            % (cfg.get("_name") or cfg["host"]))
                output += "\n== env_sync ==\n" + env_sync
        except Exception as exc:  # noqa: BLE001
            logger.warning("节点环境同步失败（不影响自检）: %s", exc)
    return _ok({
        "status": "ok" if res.get("returncode") == 0 else "partial",
        "node": cfg.get("_name") or cfg["host"],
        "node_note": cfg.get("_note") or "",
        "host": cfg["host"], "user": cfg["user"], "port": cfg["port"],
        "nodes_configured": len(_node_table(cfg)),
        "remote_home": remote_home,
        "workdir": workdir,
        "workdir_missing": ("WORKDIR_MISSING" in output),
        "scheduler": scheduler,
        "bins": {k: v for k, v in sched_bins.items() if v},
        "env_sync": env_sync,
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
    res = _exec_env(conn, command, timeout=timeout)
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


# ---------------------------------------------------------------------------
# 产物分工：什么该拉回本机、什么该留在集群
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PULL_FALLBACK_DIR = os.path.join(str(_REPO_ROOT), "results", "_cluster_pulls")

# pull 的默认体积上限（MB）：超过就**拒绝执行**，让 agent 先去问用户。
# 依据：WebUI 只能浏览 work/ 和 results/，能直接看的产物（表格/图/PDF/日志）
# 都在 KB~几十 MB；一旦到上百 MB/GB，基本就是 BAM/FASTQ/矩阵/权重——那些本该留集群。
_PULL_MAX_MB_DEFAULT = 512

# Windows 上写的脚本是 CRLF，直接推给 Linux 跑会报 "\r: command not found" / python 语法错。
_PUSH_TEXT_EXT = {".sh", ".bash", ".sbatch", ".pbs", ".py", ".r", ".pl", ".smk", ".nf",
                  ".yaml", ".yml", ".json", ".csv", ".tsv", ".txt", ".cfg", ".conf",
                  ".ini", ".md"}
_PUSH_EXEC_EXT = {".sh", ".bash", ".sbatch", ".pbs", ".py", ".pl", ".r"}
_PUSH_CRLF_SCAN_MAX = 64 * 1024 * 1024


def _human_bytes(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return "%d%s" % (n, unit)
            return "%.1f%s" % (n, unit)
        n /= 1024.0
    return "?"


def _remote_stat(conn, remote_path: str) -> dict:
    """远端路径的 kind/bytes；支持通配符。返回 {'items': [...], 'errors': [...]}。"""
    items, errors = [], []
    if _has_glob(remote_path):
        got = _locate_remote_glob(conn, [remote_path], {"hits": [], "checked": [], "errors": []})
        items, errors = got["hits"], got["errors"]
    else:
        res = _exec_env(conn, "LC_ALL=C ls -ld -- %s 2>&1 | head -1" % _sh_path(remote_path),
                        timeout=60)
        raw = (res.get("output") or "").strip()
        parsed = _parse_ls_line(raw)
        if parsed:
            items = [{"path": remote_path, "kind": parsed[0], "bytes": parsed[1]}]
        elif raw:
            errors.append(raw.splitlines()[0][:200])
    return {"items": items, "errors": errors}


def _remote_bytes(conn, remote_path: str, kind: str):
    """目录要算递归体积才知道该不该拉；文件用 ls 的 size 就够。"""
    if kind != "dir":
        return None
    for cmd, mul in (("du -sb -- %s", 1), ("du -sk -- %s", 1024)):
        res = _exec_env(conn, (cmd % _sh_path(remote_path)) + " 2>/dev/null | cut -f1",
                        timeout=180)
        txt = (res.get("output") or "").strip().splitlines()
        if txt and txt[0].strip().isdigit():
            return int(txt[0].strip()) * mul
    return None


def _crlf_prepare(local_abs: str, mode: str):
    """把 Windows CRLF 文本转成 LF 副本再上传（本机原文件不动）。

    mode: auto（默认，按后缀判断）| lf（强制转换）| keep（原样上传）
    返回 (要上传的路径, 说明 dict 或 None)
    """
    ext = os.path.splitext(local_abs)[1].lower()
    if mode == "keep":
        return local_abs, None
    if mode != "lf" and ext not in _PUSH_TEXT_EXT:
        return local_abs, None
    try:
        if os.path.getsize(local_abs) > _PUSH_CRLF_SCAN_MAX:
            return local_abs, None
        with open(local_abs, "rb") as fh:
            data = fh.read()
    except OSError:
        return local_abs, None
    if b"\r\n" not in data:
        return local_abs, None
    fixed = data.replace(b"\r\n", b"\n")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext or ".tmp")
    tmp.write(fixed)
    tmp.close()
    return tmp.name, {"crlf_fixed": True, "crlf_lines": data.count(b"\r\n"),
                      "orig_bytes": len(data), "sent_bytes": len(fixed)}


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
    crlf_mode = str(args.get("crlf") or "auto").strip().lower()
    send_path, crlf_info = _crlf_prepare(local_abs, crlf_mode)
    conn = _get_conn(cfg)
    result, verify = {}, {}
    try:
        parent = posixpath.dirname(remote_path.rstrip("/")) or "."
        mkdir = conn.execute("mkdir -p %s" % shlex.quote(parent), timeout=60)
        if mkdir.get("returncode") != 0:
            return _err("远端目录创建失败: %s" % (mkdir.get("output") or "").strip())
        result = _scp_transfer(conn, send_path, remote_path, upload=True)
        if not result.get("ok"):
            return _err("上传失败: %s" % result.get("error"))
        # Windows 侧 scp 复制过来的权限位常常带 group/other 写（0707 之类），
        # 集群是共享机器，统一收紧成"仅属主可读写"（0700/0600）。
        conn.execute("chmod -R u+rwX,go-rwx %s" % shlex.quote(remote_path), timeout=60)
        if os.path.splitext(local_abs)[1].lower() in _PUSH_EXEC_EXT:
            conn.execute("chmod u+x %s" % shlex.quote(remote_path), timeout=60)
        verify = conn.execute("du -sh %s 2>/dev/null; ls -ld %s" % (shlex.quote(remote_path),
                                                                    shlex.quote(remote_path)),
                              timeout=60)
    finally:
        if crlf_info:
            try:
                os.unlink(send_path)
            except OSError:
                pass
    payload = {
        "local_path": local_abs,
        "remote_path": remote_path,
        "transport": result.get("cmd_mode"),
        "remote_check": (verify.get("output") or "").strip(),
    }
    if crlf_info:
        payload["crlf"] = dict(crlf_info, action="已转成 LF 再上传，本机原文件没动")
    return _ok(payload)


def _action_pull(cfg: dict, args: dict) -> str:
    remote_path = (args.get("remote_path") or "").strip()
    local_path = (args.get("local_path") or "").strip()
    if not remote_path:
        return _err("pull 需要 remote_path")
    conn = _get_conn(cfg)
    stat = _remote_stat(conn, remote_path)
    items = stat["items"]
    if not items:
        why = ("；远端回了：" + "；".join(stat["errors"])) if stat["errors"] else ""
        return _err("远端没找到（路径写错 / 没权限 / 通配符没匹配上）: %s%s" % (remote_path, why))
    for it in items:
        if it.get("kind") == "dir":
            got = _remote_bytes(conn, it["path"], "dir")
            if got is not None:
                it["bytes"] = got
    total = sum(int(it.get("bytes") or 0) for it in items)
    # ★体积闸门：默认不给"手滑把 200GB 的 BAM 拖回本机"
    max_mb = args.get("max_mb")
    if max_mb is None:
        max_mb = 0 if args.get("allow_large") else _PULL_MAX_MB_DEFAULT
    else:
        try:
            max_mb = float(max_mb)
        except (TypeError, ValueError):
            max_mb = _PULL_MAX_MB_DEFAULT
    if max_mb and total > max_mb * 1024 * 1024:
        return _ok({
            "status": "too_large",
            "remote_path": remote_path,
            "total_bytes": total, "total_human": _human_bytes(total),
            "max_mb": max_mb,
            "items": items[:20],
            "hint": ("这份东西 %s，超过 pull 默认上限 %s MB。**先问用户要不要拉**；"
                     "用户确认要拉，就带 max_mb=<更大的数字>（或 allow_large=true）再调一次。"
                     "经验：表格/图/PDF/脚本/日志汇总（.csv .tsv .xlsx .png .pdf .svg .R .py .log）"
                     "拉回本机 results/<会话目录>/，WebUI 才能直接看；"
                     "BAM/FASTQ/大矩阵/模型权重留在集群。"
                     % (_human_bytes(total), int(max_mb))),
        })
    # 目标路径：多命中/通配符 → 都放进一个目录；单个 → 尊重 local_path
    if len(items) > 1:
        base_dir = local_path or os.path.join(_PULL_FALLBACK_DIR,
                                              os.path.basename(remote_path.rstrip("/")) or "pull")
        targets = [(it, os.path.join(base_dir, os.path.basename(it["path"].rstrip("/"))))
                   for it in items]
    else:
        it = items[0]
        lp = local_path or _map_remote_to_local(cfg, it["path"]) or os.path.join(
            _PULL_FALLBACK_DIR, os.path.basename(it["path"].rstrip("/")))
        if it["kind"] != "dir" and os.path.isdir(lp):
            lp = os.path.join(lp, os.path.basename(it["path"].rstrip("/")))
        elif it["kind"] == "dir" and os.path.isdir(lp):
            lp = os.path.join(lp, os.path.basename(it["path"].rstrip("/")))
        targets = [(it, lp)]
    # 不静默覆盖用户本机已有文件
    if not args.get("overwrite"):
        clash = [lp for _it, lp in targets if os.path.exists(lp)]
        if clash:
            return _ok({"status": "exists", "local_paths": clash[:10],
                        "hint": ("本机已经有同名文件，没有覆盖。确认要覆盖就带 overwrite=true 再调一次；"
                                 "或者换一个 local_path（建议 results/<会话目录>/）。")})
    done, failed = [], []
    for it, lp in targets:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(lp)) or ".", exist_ok=True)
        except OSError as exc:
            failed.append({"remote_path": it["path"], "error": "本地目录创建失败: %s" % exc})
            continue
        res = _scp_transfer(conn, lp, it["path"], upload=False)
        if res.get("ok"):
            size = it.get("bytes")
            if it["kind"] == "file" and os.path.exists(lp):
                try:
                    size = os.path.getsize(lp)
                except OSError:
                    pass
            done.append({"remote_path": it["path"], "local_path": lp, "bytes": size,
                         "kind": it["kind"]})
        else:
            failed.append({"remote_path": it["path"], "error": res.get("error")})
    if not done:
        return _err("下载失败: %s" % (failed[0].get("error") if failed else "未知原因"),
                    failed=failed)
    local_out = done[0]["local_path"] if len(done) == 1 else os.path.dirname(done[0]["local_path"])
    payload = {
        "status": "ok" if not failed else "partial",
        "remote_path": remote_path,
        "local_path": local_out,
        "local_paths": [d["local_path"] for d in done],
        "count": len(done),
        "total_bytes": total,
        "total_human": _human_bytes(total),
        "transport": "scp",
        "failed": failed,
        "hint": "这只是拉回本机；要放进 WebUI 能看的目录，请确保落在 results/<会话目录>/ 或 work/ 下。",
    }
    return _ok(payload)






def _action_submit(cfg: dict, args: dict) -> str:
    command = (args.get("command") or "").strip()
    if not command:
        return _err("submit 需要 command（要跑的作业命令）")
    conn = _get_conn(cfg)
    sched, _bins = _detect_scheduler(conn, cfg)
    base_name = (args.get("job_name") or "memomics").strip().replace(" ", "_")
    # 多个节点共用同一个文件系统时，同名作业的日志/pid 文件会互相覆盖
    # （logs/<作业名>.log、logs/<作业名>.pid）→ 多节点时自动加节点后缀
    node_tag = ""
    if len(_node_table(cfg)) > 1:
        node_tag = "_" + _node_slug(cfg.get("_name") or cfg["host"])
    name = "%s%s" % (base_name, node_tag)
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
    elif sched in ("pbs", "gridengine"):
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
        "ts": _now(), "node": cfg.get("_name") or "", "host": cfg["host"], "user": cfg["user"],
        "scheduler": sched, "job_id": job_id, "name": name,
        "script": script_remote, "stdout": out_log, "stderr": err_log,
        "workdir": workdir, "command": command[:4000], "pid_file": pid_file,
    }
    _record_job(record)
    return _ok({
        "status": "submitted", "scheduler": sched, "job_id": job_id,
        "node": cfg.get("_name") or "", "host": cfg["host"],
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
    if sched == "gridengine":
        qsec = _probe_section(text, "qstat")
        ms = re.search(r"state=(\S+)", qsec)
        if ms:
            st = ms.group(1)
            if st in ("r", "t", "Rr", "Rt"):
                return "RUNNING"
            if "E" in st:
                return "ERROR(Eqw 错误态——用 action='logs' 或直接问 qstat -j <id>)"
            return "PENDING(%s)" % st
        asec = _probe_section(text, "qacct")
        me = re.search(r"exit_status\s+(\d+)", asec)
        if me:
            return "COMPLETED" if me.group(1) == "0" else "FAILED(exit=%s)" % me.group(1)
        if "do not exist" in (qsec + asec).lower():
            return "UNKNOWN(队列和记账里都查不到——可能刚提交还没入账，或 job_id 不对)"
        return "UNKNOWN"
    m = re.search(r"job_state\s*=\s*(\w+)", text)
    return m.group(1).upper() if m else "UNKNOWN"


def _action_status(cfg: dict, args: dict) -> str:
    job_id = str(args.get("job_id") or "").strip()
    rec = _find_job(cfg, job_id) if job_id else None
    cross_note = ""
    if job_id and rec is None:
        owner = _job_owner_node(job_id)
        if owner and owner != (cfg.get("_name") or ""):
            cross_note = ("job_id %s 的提交记录在节点 %r 上（现在选的是 %r）。"
                          "同一个集群共享调度器时这样查没问题；"
                          "如果那个节点用的是无调度器(setid)模式，作业号是那边的本机 PID，"
                          "查不到就要换 node=%r 再查。" % (job_id, owner, cfg.get("_name") or cfg["host"], owner))
    assumed = False
    if not job_id:
        recent = [r for r in _iter_jobs(50) if _rec_matches_node(r, cfg)]
        if not recent:
            return _err("status 需要 job_id（本机还没有提交记录，先用 action='submit'）")
        rec = recent[-1]
        job_id = str(rec.get("job_id"))
        assumed = True
    conn = _get_conn(cfg)
    sched = ((rec or {}).get("scheduler")
             or (cfg["scheduler"] if cfg["scheduler"] in ("slurm", "pbs", "gridengine", "none") else "auto"))
    if sched == "auto":
        sched, _ = _detect_scheduler(conn, cfg)
    if sched == "slurm":
        qid = shlex.quote(job_id)
        cmd = ("echo '== squeue =='; squeue -j %s -h -o '%%T %%M %%R' 2>&1; "
               "echo '== scontrol =='; (scontrol show job %s 2>&1 "
               "| grep -E 'JobState|RunTime|ExitCode' | head -5); "
               "echo '== sacct =='; (sacct -j %s --format=JobID,State,Elapsed,ExitCode -P -n 2>&1 | head -5)"
               % (qid, qid, qid))
    elif sched == "gridengine":
        qid = shlex.quote(job_id)
        # GE 两段式：在队列里（qstat 列表抓 state 列）；已离队（qacct 记账拿 exit_status）
        cmd = ("echo '== qstat =='; "
               "(qstat -u \"$USER\" 2>&1 | awk -v id=%s '$1==id {print \"state=\"$5\" queue=\"$8}'); "
               "qstat -j %s 2>&1 | head -2; "
               "echo '== qacct =='; (qacct -j %s 2>&1 | grep -E '^(exit_status|failed|end_time)' | head -5)"
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
        "node": cfg.get("_name") or "", "host": cfg["host"],
        "state": state,
        **({"note": "未指定 job_id，用的是最近一次提交"} if assumed else {}),
        **({"cross_node_note": cross_note} if cross_note else {}),
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
            recent = [r for r in _iter_jobs(20) if _rec_matches_node(r, cfg)]
            if len(recent) == 1:
                rec = recent[0]
        if rec is not None:
            job_id = job_id or str(rec.get("job_id") or "")
            path = str(rec.get("stdout") or "")
    if not path:
        owner = _job_owner_node(job_id) if job_id else ""
        if owner and owner != (cfg.get("_name") or ""):
            return _err("job_id %s 的提交记录在节点 %r 上（现在选的是 %r），"
                        "日志路径只有那边的记录里才有 → 请用 node=%r 再读，"
                        "或直接给 path=远端日志文件"
                        % (job_id, owner, cfg.get("_name") or cfg["host"], owner),
                        job_id=job_id, owner_node=owner)
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
    elif sched in ("pbs", "gridengine"):
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
    sched = cfg["scheduler"] if cfg["scheduler"] in ("slurm", "pbs", "gridengine", "none") else "auto"
    if sched == "auto":
        sched, _ = _detect_scheduler(conn, cfg)
    if sched == "slurm":
        cmd = ("echo '== squeue =='; squeue -u \"$USER\" -o '%.12i %.9P %.30j %.8T %.10M %.6D %R' 2>&1 | head -30; "
               "echo '== sacct (today) =='; (sacct -u \"$USER\" --starttime today --format=JobID,JobName,State,Elapsed -P -n 2>&1 | tail -20)")
    elif sched in ("pbs", "gridengine"):
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
        "local_records": [{k: r.get(k) for k in ("ts", "node", "job_id", "name", "scheduler", "workdir")}
                          for r in _iter_jobs(10) if _rec_matches_node(r, cfg)][-5:],
    })


# ---------------------------------------------------------------------------
# 节点体检（action='nodes'）—— 列配置里的节点 + 连通性 + 负载
# ---------------------------------------------------------------------------

_NODE_PROBE = "\n".join([
    "echo \"== host ==\"",
    "hostname; whoami",
    "echo \"== cpu ==\"",
    "nproc 2>/dev/null || echo 0",
    "echo \"== load ==\"",
    "cat /proc/loadavg 2>/dev/null | cut -d' ' -f1-3 || uptime",
    "echo \"== users ==\"",
    "who 2>/dev/null | wc -l",
    "echo \"== home ==\"",
    "echo \"$HOME\"",
    "echo \"== workdir ==\"",
    "cd %s 2>/dev/null && { pwd; df -h . | tail -1; } || echo WORKDIR_MISSING",
    "echo \"== sched ==\"",
    _PROBE_SCHED,
])


def _probe_section(text: str, name: str) -> str:
    m = re.search(r"== %s ==\n(.*?)(?=\n== |\Z)" % re.escape(name), text or "", re.S)
    return (m.group(1) if m else "").strip()


def _parse_node_probe(text: str) -> dict:
    info: dict = {}
    host_sec = _probe_section(text, "host").splitlines()
    if host_sec:
        info["remote_hostname"] = host_sec[0].strip()
    if len(host_sec) > 1:
        info["remote_user"] = host_sec[1].strip()
    try:
        info["nproc"] = int(_probe_section(text, "cpu").split()[0])
    except Exception:
        info["nproc"] = 0
    load = _probe_section(text, "load").split()
    for idx, key in enumerate(("load1", "load5", "load15")):
        if len(load) > idx:
            try:
                info[key] = float(load[idx])
            except Exception:
                pass
    try:
        info["users"] = int(_probe_section(text, "users").split()[0])
    except Exception:
        info["users"] = None
    home_sec = _probe_section(text, "home").splitlines()
    if home_sec:
        info["remote_home"] = home_sec[0].strip()
    wd = _probe_section(text, "workdir")
    if not wd or "WORKDIR_MISSING" in wd:
        info["workdir_ok"] = False
    else:
        wd_lines = wd.splitlines()
        info["workdir_ok"] = True
        info["workdir"] = wd_lines[0].strip()
        if len(wd_lines) > 1:
            info["workdir_df"] = wd_lines[1].strip()
    sched_sec = _probe_section(text, "sched")
    if sched_sec:
        bins = _parse_probe(sched_sec)
        info["bins"] = {k: v for k, v in bins.items() if v}
        info["scheduler"] = _sched_from_probe(bins)
    return info


def _action_nodes(cfg: dict, args: dict) -> str:
    """列配置里的所有节点，逐个探连通性 + 负载（用于「哪个节点现在空着」和排查连不上）。

    不选定节点也能调用；给了 node= 就只探那一个。
    """
    table = _node_table(cfg)
    if not table:
        return _err("没有配置任何远端节点：请在 config.yaml 的 remote: 段配 host 或 nodes")
    only = str(args.get("node") or "").strip()
    names = list(table)
    if only:
        names = [n for n in table if n.lower() == only.lower()]
        if not names:
            return _err("节点名 %r 不在配置里。已配置：%s" % (only, "、".join(table)),
                        nodes=_nodes_brief(table))

    items = []
    for name in names:
        node = table[name]
        item: dict = {
            "name": name, "note": node.get("_note") or "", "role": node.get("_role") or "",
            "host": node.get("host"), "user": node.get("user"), "port": node.get("port"),
            "workdir": node.get("workdir"), "reachable": False,
        }
        if not str(node.get("user") or "").strip():
            item["error"] = "这个节点没有 user（全局 remote.user 和节点条目里都没给）"
            items.append(item)
            continue
        try:
            conn = _get_conn(node)
            res = _exec_env(conn, _NODE_PROBE % shlex.quote(str(node.get("workdir") or "~")),
                            timeout=min(int(node.get("timeout") or 60), 60))
            out = res.get("output") or ""
            item.update(_parse_node_probe(out))
            bad = _is_conn_error(out) or res.get("returncode") != 0
            item["reachable"] = not bad
            if bad:
                item["error"] = _truncate(out.strip(), 400)
                if _is_conn_error(out):
                    _drop_conn(node)
        except Exception as exc:
            item["error"] = str(exc)[:400]
        nproc = int(item.get("nproc") or 0)
        if nproc and item.get("load1") is not None:
            item["load_per_cpu"] = round(float(item["load1"]) / nproc, 3)
            item["idle_guess"] = item["load_per_cpu"] < 0.6
        items.append(item)

    reachable = [i for i in items if i.get("reachable")]
    idle = [i["name"] for i in reachable if i.get("idle_guess")]
    return _ok({
        "status": "ok" if len(reachable) == len(items) else "partial",
        "nodes": items,
        "configured": len(table),
        "reachable": len(reachable),
        "idle_now": idle,
        "policy": cfg.get("node_policy") or "ask",
        "default_node": cfg.get("default_node") or "",
        "summary": ("%d/%d 个节点可连；负载较低：%s"
                    % (len(reachable), len(items), "、".join(idle) if idle else "无")),
    })


_BOUNDED_CAPTURE_OK = None


def _exec_env(conn, command: str, timeout: int = None, cwd: str = None,
              stdin_data: str = None) -> dict:
    """调 environment.execute()：老版本 hermes 的 BaseEnvironment 不认 bounded_capture，自动降级。

    这里刻意用签名探测而不是 try/except 包住 execute——否则命令内部的 TypeError 会被
    误判成"版本不支持"，导致同一条命令被跑第二次（有副作用的命令会出事）。
    """
    global _BOUNDED_CAPTURE_OK
    if _BOUNDED_CAPTURE_OK is None:
        try:
            import inspect
            _BOUNDED_CAPTURE_OK = "bounded_capture" in inspect.signature(conn.execute).parameters
        except Exception:
            _BOUNDED_CAPTURE_OK = False
    kw = {}
    if timeout is not None:
        kw["timeout"] = timeout
    if cwd:
        kw["cwd"] = cwd
    if stdin_data is not None:
        kw["stdin_data"] = stdin_data
    if _BOUNDED_CAPTURE_OK:
        kw["bounded_capture"] = True
    return conn.execute(command, **kw)


def _memomics_root() -> Path:
    """仓库根目录（memomics/bio_tools/remote_cluster.py → 上三级）。"""
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path(os.getcwd())


_WIN_ABS = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|//)")
_GLOB_CHARS = "*?["


def _path_flavor(raw: str) -> str:
    """用户给的是哪种路径：win(Windows 盘符/UNC) / posix(远端绝对或 ~) / bare(相对或纯文件名)。"""
    s = (raw or "").strip()
    if _WIN_ABS.match(s):
        return "win"
    if s.startswith("/") or s.startswith("~"):
        return "posix"
    return "bare"


def _sh_path(cand: str) -> str:
    """候选路径在 shell 里的安全写法。注意 ~ 不能被整体加引号，否则 shell 不展开。"""
    if cand == "~":
        return '"$HOME"'
    if cand.startswith("~/"):
        return '"$HOME"' + shlex.quote(cand[1:])
    return shlex.quote(cand)


def _has_glob(raw: str) -> bool:
    return any(ch in (raw or "") for ch in _GLOB_CHARS)


_LS_MODE = re.compile(r"^[-dlbcsp][-rwxsStT]{9}[.+@]?$")


def _parse_ls_line(line: str):
    """解析 'LC_ALL=C ls -ld' 的首行 → (kind, bytes)；不是列表行（报错/空）返回 None。

    必须严格认模式串：ls 的报错行 "ls: cannot access ...: No such file or directory"
    首字符也是 'l'，宽松判断会把「不存在」当成「符号链接」，
    结果是**任何路径都被判成存在**（差点发布出去的真 bug）。
    """
    line = (line or "").strip()
    if not line or line.startswith("ls:"):
        return None
    if "No such file" in line or "Permission denied" in line or "not a directory" in line:
        return None
    parts = line.split()
    if len(parts) < 5 or not _LS_MODE.match(parts[0]):
        return None
    try:
        size = int(parts[4])
    except ValueError:
        size = None
    kind = {"d": "dir", "l": "link"}.get(parts[0][0], "file")
    return (kind, size)


def _glob_local(raw: str, root: Path) -> list:
    """本地通配符查找（*.tsv 这类）。只在会话常见目录里展开，避免全盘扫。"""
    import glob as _glob
    if os.path.isabs(raw):
        pats = [raw]
    else:
        pats = [raw,
                os.path.join(str(root), raw),
                os.path.join(str(root), "work", raw),
                os.path.join(str(root), "results", "*", raw),
                os.path.join(str(root), "webui", "uploads", raw)]
    out, seen = [], set()
    for pat in pats:
        try:
            found = sorted(_glob.glob(pat))[:50]
        except Exception:
            continue
        for p in found:
            try:
                ap = os.path.abspath(p)
            except Exception:
                continue
            if ap in seen:
                continue
            seen.add(ap)
            try:
                isdir = os.path.isdir(ap)
                out.append({"found_as": "glob:" + pat, "path": ap,
                            "kind": "dir" if isdir else "file",
                            "bytes": None if isdir else os.path.getsize(ap)})
            except OSError:
                continue
    return out


_REMOTE_GLOB_PY = ('import glob,sys,os;ps=[];'
                   '[ps.extend(glob.glob(p)) for p in sys.argv[1:]];'
                   'ps=sorted(set(ps))[:50];'
                   '[print(("D" if os.path.isdir(p) else "F")+":"+'
                   'str(os.path.getsize(p) if os.path.isfile(p) else 0)+":"+p) for p in ps]')


def _locate_remote_glob(conn, cands: list, out: dict) -> dict:
    """远端通配符：借节点上的 python3 展开（shell 里带引号的 glob 不会自己展开）。"""
    pats = " ".join(shlex.quote(c) for c in cands if c)
    cmd = ("for PY in python3 python; do command -v $PY >/dev/null 2>&1 || continue; "
           "$PY -c '%s' %s && break; done" % (_REMOTE_GLOB_PY, pats))
    res = _exec_env(conn, cmd, timeout=60)
    for line in (res.get("output") or "").strip().splitlines():
        line = line.strip()
        if line.count(":") < 2 or line[0] not in "DF":
            if line:
                out["errors"].append(line[:160])
            continue
        kind, size, path = line.split(":", 2)
        try:
            size = int(size)
        except ValueError:
            size = None
        out["hits"].append({"path": path, "kind": "dir" if kind == "D" else "file", "bytes": size})
    return out


def _locate_local(raw: str, flavor: str = "bare") -> dict:
    """在本机常见位置找这个路径：原样 / 仓库根 / work/ / results/（含各会话子目录）/ webui/uploads/。

    flavor='win'（Windows 绝对路径）只按原样查：绝不把盘符路径拼到仓库子目录里，
    更不会因为集群上碰巧有同名文件就把用户的本地文件判成集群数据。
    """
    root = _memomics_root()
    unix = raw.replace("\\", "/")
    base = unix.rstrip("/").rsplit("/", 1)[-1] if unix else ""
    if _has_glob(raw):
        return {"hits": _glob_local(raw, root), "checked": ["glob:" + raw], "root": str(root)}
    cands = [("原样", raw)]
    if flavor == "bare":
        for sub in ("", "work", "results", "webui/uploads"):
            cands.append((sub or "仓库根", os.path.join(str(root), sub, raw)))
    if base and flavor == "bare" and not os.path.isabs(raw):
        # 用户常只说文件名 → 去 results/<各个会话>/ 里找（最近的会话排前面）
        try:
            rdir = str(root / "results")
            sess = [d for d in os.listdir(rdir) if os.path.isdir(os.path.join(rdir, d))]
            sess.sort(key=lambda d: os.path.getmtime(os.path.join(rdir, d)), reverse=True)
            for s in sess[:40]:
                cands.append(("results/" + s, os.path.join(rdir, s, raw)))
        except Exception:
            pass
    hits, seen, checked = [], set(), []
    for tag, p in cands:
        try:
            ap = os.path.abspath(p)
        except Exception:
            continue
        if ap in seen:
            continue
        seen.add(ap)
        if len(checked) < 12:
            checked.append(ap)
        try:
            if os.path.exists(ap):
                isdir = os.path.isdir(ap)
                hits.append({"found_as": tag, "path": ap, "kind": "dir" if isdir else "file",
                             "bytes": None if isdir else os.path.getsize(ap)})
        except Exception:
            continue
    return {"hits": hits, "checked": checked, "root": str(root)}


def _locate_remote(node_cfg: dict, raw: str, flavor: str = "bare") -> dict:
    """在某个节点上找这个路径：原样 / 工作目录下同名 / 工作目录 data/ 下同名。"""
    workdir = str(node_cfg.get("workdir") or "~").rstrip("/")
    unix = raw.replace("\\", "/")
    base = os.path.basename(unix.rstrip("/")) if unix.strip() else ""
    out = {"hits": [], "checked": [], "errors": []}
    cands = [unix]
    if base and flavor != "posix" and not unix.startswith("/"):
        cands.append(workdir + "/" + base)
        cands.append(workdir + "/data/" + base)
    conn = _get_conn(node_cfg)
    if _has_glob(unix):
        out["checked"] = [c for c in cands if c]
        return _locate_remote_glob(conn, out["checked"], out)
    seen = set()
    for cand in cands:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        out["checked"].append(cand)
        # ls -ld 一次问清「在不在/是文件还是目录/多大/有没有权限」：
        # 不读文件内容（几 GB 的 BAM 也是瞬间），而且能区分"没有"和"没权限"。
        res = _exec_env(conn, "LC_ALL=C ls -ld -- %s 2>&1 | head -1" % _sh_path(cand),
                        timeout=min(int(node_cfg.get("timeout") or 60), 45))
        lines = (res.get("output") or "").strip().splitlines()
        line = lines[0].strip() if lines else ""
        parsed = _parse_ls_line(line)
        if parsed is None:
            if line and ("Permission denied" in line or "not a directory" in line
                         or "No such file" in line):
                if "Permission denied" in line:
                    out["errors"].append("无权限（%s 可能确实存在，但当前账号读不到）" % cand)
            elif line:
                out["errors"].append("%s: %s" % (cand, line[:120]))
            continue
        kind, size = parsed
        if not any(h["path"] == cand for h in out["hits"]):
            out["hits"].append({"path": cand, "kind": kind, "bytes": size})
    return out


def _fmt_bytes(n) -> str:
    if n is None:
        return "?"
    try:
        n = float(n)
    except Exception:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return ("%.1f%s" % (n, unit)) if unit != "B" else ("%dB" % int(n))
        n /= 1024.0
    return "?"


def _action_locate(cfg: dict, args: dict) -> str:
    """判定一个路径到底在本地还是集群上。

    用户明说了按用户说的走；没说就查出来（本地常见目录 + 各节点），查不出来就问，
    不许猜、不许编路径。远端没配置时也能用（只报本地那一半）。
    """
    raw = str(args.get("path") or args.get("local_path") or args.get("remote_path") or "").strip()
    if not raw:
        return _err("locate 需要给出要判定的路径：path='...'（直接用用户消息里的原话路径，不要自己拼）")
    flavor = _path_flavor(raw)
    local = _locate_local(raw, flavor)
    table = _node_table(cfg)
    only = str(args.get("node") or "").strip()
    # Windows 盘符 / UNC 路径 = 本机文件，绝不拿到集群上去找：
    # 集群上碰巧有同名文件会把本地数据判成集群数据，最坏情况是拿错数据去算。
    skip_remote = (flavor == "win")
    names = [] if skip_remote else list(table)
    if only and not skip_remote:
        names = [n for n in table if n.lower() == only.lower()]
        if not names:
            return _err("节点名 %r 不在配置里。已配置：%s" % (only, "、".join(table) or "无"),
                        nodes=_nodes_brief(table))
    remote, errs = {}, {}
    for name in names[:6]:
        try:
            remote[name] = _locate_remote(table[name], raw, flavor)
            if remote[name].get("errors"):
                errs[name] = "；".join(remote[name]["errors"])[:300]
        except Exception as exc:
            errs[name] = str(exc)[:200]
            _drop_conn(table[name])
    rh = {n: v["hits"] for n, v in remote.items() if v.get("hits")}
    lh = local["hits"]
    if lh and rh:
        verdict = "ambiguous"
        advice = ("两边都找到了 → **不要自己挑**：把两边的大小报给用户问清楚用哪一份"
                  "（本机 %s；远端 %s）。如果只是刚 push/pull 过的同一份，按用户最后提到的位置走。"
                  % ("、".join(_fmt_bytes(h.get("bytes")) + " " + h["path"] for h in lh[:2]),
                     "、".join("%s %s" % (n, _fmt_bytes(h.get("bytes"))) for n, hs in rh.items() for h in hs[:1])))
    elif lh:
        verdict = "local"
        advice = ("本机找到了（%s）→ 按本地跑（execute_python / execute_r），"
                  "输出照旧放 results/<会话目录>/，不要为了它去连集群。"
                  % "、".join(h["path"] for h in lh[:2]))
        if skip_remote:
            advice += "（Windows 盘符路径，没拿去集群上找；集群同名文件不算数。）"
    elif rh:
        verdict = "cluster"
        advice = ("本机没有、集群上有（%s）→ 这是集群数据：**原始大文件不要往本机拉**，"
                  "用 remote_cluster 的 run/submit 在集群上算；表格/图片/脚本/日志这类小产物算完 "
                  "pull 回 results/<会话目录>/，否则 WebUI 里看不到。"
                  % "、".join("%s:%s" % (n, hs[0]["path"]) for n, hs in rh.items()))
    else:
        verdict = "missing"
        if skip_remote:
            advice = ("你给的这个本机路径（Windows 盘符）没找到，查过：%s。"
                      "**先跟用户确认路径**（是不是盘符/目录写错了、或文件还没生成）；"
                      "Windows 路径不会被拿去集群上找，如果数据其实在集群上，请用户给远端路径或说明哪个节点。"
                      % ("、".join(local["checked"][:6]) or "无"))
        elif not table:
            advice = ("本机没找到，而且远端集群还没配置 → 请用户给准确路径，"
                      "(或先在 WebUI「🖧 远端集群」里配好节点再查集群那一边)。")
        else:
            advice = ("本机和集群都没找到 → **不要编路径、也不要假设**："
                      "把查过的位置报给用户（本机：%s；集群：%s），请他给准确路径，"
                      "或确认是不是要先 push 上传。"
                      % ("、".join(local["checked"][:5]) or "无",
                         "；".join("%s: %s" % (n, "、".join(v["checked"][:3])) for n, v in remote.items()) or "无"))
    return _ok({
        "status": "ok",
        "path": raw,
        "verdict": verdict,
        "local": local,
        "remote": remote,
        "remote_errors": errs,
        "scope": "local-only（Windows 盘符路径，不去集群上找）" if skip_remote else "local+cluster",
        "globs_expanded": _has_glob(raw),
        "nodes_checked": names[:6],
        "advice": advice,
        "summary": ("路径 %r → %s" % (raw, {"local": "只在本地", "cluster": "只在集群",
                                            "ambiguous": "两边都有", "missing": "两边都没找到"}[verdict])),
    })


# ---------------------------------------------------------------------------
# 一键装公钥（WebUI「🔑 安装公钥」专用，2026-10-08）
# ---------------------------------------------------------------------------
# 为什么需要它：本工具走 BatchMode 密钥免密，但"第一次把公钥放上集群"这一步
# 必须过一次密码认证；Windows 自带 ssh.exe 不支持脚本化密码输入，用户在
# WebUI 里输密码 → 后端用 paramiko 完成这一次安装，之后全部免密。
# 硬约束：密码只在内存里用这一次 —— 不落盘、不进日志、不缓存、不暴露给模型。


def _paramiko():
    try:
        import paramiko
        return paramiko
    except ImportError:
        return None


def _p_connect(paramiko, host, port, user, password, key_path, sock_factory=None):
    """按顺序尝试 密钥→密码（哪个给了试哪个）；返回 (client, 认证方式)。全失败抛最后异常。

    sock_factory：走跳板时传一个"开新通道"的 callable —— 每次认证尝试都必须用
    一条全新的 direct-tcpip 通道（上一次认证失败会把通道 EOF 掉，复用必炸 EOFError）。
    """
    attempts = []
    key_path = os.path.expanduser(str(key_path or "").strip())
    if key_path and os.path.exists(key_path):
        attempts.append(("key", key_path))
    if password:
        attempts.append(("password", password))
    last_exc = None
    for mode, secret in attempts:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = {"hostname": host, "port": int(port or 22), "username": user,
                  "look_for_keys": False, "allow_agent": False,
                  "timeout": 15, "banner_timeout": 30, "auth_timeout": 20}
        if sock_factory is not None:
            kwargs["sock"] = sock_factory()
        if mode == "key":
            kwargs["key_filename"] = secret
        else:
            kwargs["password"] = secret
        try:
            client.connect(**kwargs)
            return client, mode
        except Exception as exc:  # noqa: BLE001 — 认证失败换下一方式；网络错误也只会让下一方式再撞一次
            last_exc = exc
            try:
                client.close()
            except Exception:
                pass
    raise last_exc or RuntimeError("没有可用的认证方式（既没找到密钥文件也没给密码）")


def _p_exec(client, cmd, timeout=30):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err_out = stderr.read().decode("utf-8", "replace")
    return out, err_out


def _install_cmd(pub_line: str) -> str:
    """幂等安装命令：已有该行就报 ALREADY，否则追加并报 INSTALLED。"""
    return ("umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; "
            "chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; "
            "grep -qF '%s' ~/.ssh/authorized_keys 2>/dev/null && echo __MEMOMICS_KEY_ALREADY__ "
            "|| { echo '%s' >> ~/.ssh/authorized_keys && echo __MEMOMICS_KEY_INSTALLED__; }"
            ) % (pub_line, pub_line)


def _exec_install(client, pub_line: str) -> str:
    """在一台已连上的机器上执行安装；返回 installed / already，拿不到标记抛异常。"""
    out, err_out = _p_exec(client, _install_cmd(pub_line), timeout=30)
    if "__MEMOMICS_KEY_ALREADY__" in out:
        return "already"
    if "__MEMOMICS_KEY_INSTALLED__" in out:
        return "installed"
    raise RuntimeError("远端执行安装命令后没看到完成标记。stdout=%r stderr=%r"
                       % (out[-500:], err_out[-500:]))


def install_pubkey(cfg: dict, node_name: str, password: str) -> str:
    """用密码登录一次，把本机公钥追加进远端 ~/.ssh/authorized_keys（幂等）。

    流程：解析节点（含 default_node/单节点兜底）→ 能密钥免密就直接报 already_ok
    → 否则密码登录（带 proxy_jump 的先连跳板再开 direct-tcpip 通道，跳板优先用
    共享密钥、密钥不行用同一密码）→ 幂等追加公钥 → 立刻用纯密钥重连验证整条链路。
    """
    paramiko = _paramiko()
    if paramiko is None:
        return _err("缺少 paramiko 库（WebUI 密码装公钥靠它做密码认证，Windows 自带 ssh.exe "
                    "不支持脚本化密码）。装法：.venv\\Scripts\\python.exe -m pip install paramiko")
    node_cfg, name, err = _select_node(cfg, node_name)
    if err:
        return err
    host = str(node_cfg.get("host") or "").strip()
    user = str(node_cfg.get("user") or "").strip()
    if not host or not user:
        return _err("节点 %r 缺 host/user，连不了" % (name or node_name), node=name)
    port = int(node_cfg.get("port") or 22)
    key_path = str(node_cfg.get("key") or "").strip()
    pub_path = (os.path.expanduser(key_path) + ".pub") if key_path else ""
    if not pub_path or not os.path.exists(pub_path):
        return _err("找不到公钥文件：%s（先在「⚙️ 配置」里填对私钥路径；本机还没有密钥对就先生成："
                    "ssh-keygen -t ed25519）" % (pub_path or "<未配置 remote.key>"), node=name)
    with open(pub_path, "r", encoding="utf-8") as fh:
        pub_line = fh.read().strip()
    if not pub_line:
        return _err("公钥文件是空的：%s" % pub_path, node=name)
    if "'" in pub_line:
        return _err("公钥内容含单引号，拒绝拼进 shell（异常文件）：%s" % pub_path, node=name)

    # 跳板解析：proxy_jump 形如 [user@]host[:port]，缺省 user/port 继承共享配置
    raw_entry = (cfg.get("nodes") or {}).get(name) or {}
    jump_spec = str(raw_entry.get("proxy_jump") or "").strip()
    jump_client = None
    client = None
    via = ""
    try:
        sock_factory = None
        jump_note = ""
        if jump_spec:
            m = _LITERAL_HOST_RE.match(jump_spec)
            if not m:
                return _err("节点 %r 的 proxy_jump=%r 解析不了（应为 [user@]host[:port]）" % (name, jump_spec),
                            node=name)
            j_user = m.group(1) or str(cfg.get("user") or user)
            j_host = m.group(2)
            j_port = int(m.group(3) or 22)
            jump_client, j_mode = _p_connect(paramiko, j_host, j_port, j_user,
                                             password, str(cfg.get("key") or ""))
            via = "经跳板 %s@%s:%s(%s) → " % (j_user, j_host, j_port,
                                            "密钥" if j_mode == "key" else "密码")
            # 跳板是用密码登进来的 = 跳板上还没有我们的公钥 → 顺手装上。
            # 不装的话以后所有 key-only 的 ProxyJump（check/run/submit）都会死在跳板这一跳。
            if j_mode == "password":
                try:
                    j_res = _exec_install(jump_client, pub_line)
                    jump_note = "；跳板公钥%s" % ("也已写入" if j_res == "installed" else "本就在")
                except Exception as exc:
                    jump_note = "；⚠️ 跳板公钥写入失败（%s），目标装完跳板仍要补装" % exc

            def sock_factory():
                return jump_client.get_transport().open_channel(
                    "direct-tcpip", (host, port), ("127.0.0.1", 0))

        # 目标节点：先试纯密钥（已装过 = already_ok，不再动 authorized_keys）。
        # 每次尝试都走 sock_factory() 开新通道——认证失败会 EOF 掉旧通道，复用必炸。
        try:
            client, mode = _p_connect(paramiko, host, port, user, "", key_path, sock_factory=sock_factory)
        except Exception:
            client, mode = _p_connect(paramiko, host, port, user, password, "", sock_factory=sock_factory)

        if mode == "key":
            return _ok({
                "status": "already_ok", "node": name, "host": host, "user": user,
                "via_jump": bool(jump_spec),
                "summary": ("%s%s@%s:%s 已经能用密钥免密登录，公钥无需重复安装%s"
                            % (via, user, host, port, jump_note)),
            })

        try:
            installed = _exec_install(client, pub_line)
        except RuntimeError as exc:
            return _err(str(exc), node=name,
                        hint="目标节点的 shell 可能不是 POSIX sh（极简容器/csh），需要手工装公钥")
        try:
            client.close()
        except Exception:
            pass
        client = None

        # 立刻用纯密钥重连验证整条链路（跳板开着的话走新通道）
        verify_note = ""
        try:
            v_client, _ = _p_connect(paramiko, host, port, user, "", key_path, sock_factory=sock_factory)
            v_out, _ = _p_exec(v_client, "hostname && whoami", timeout=15)
            v_client.close()
            verify_note = "；密钥重连验证通过（%s）" % " / ".join(v_out.strip().splitlines()[:2])
        except Exception as exc:
            verify_note = ("；⚠️ 但密钥重连验证失败（%s）——公钥已写入，可能 sshd 禁了 pubkey "
                           "或该节点 home 不共享，点「🔌 自检」进一步看" % exc)

        return _ok({
            "status": installed, "node": name, "host": host, "user": user,
            "via_jump": bool(jump_spec),
            "summary": ("公钥%s到 %s%s@%s:%s 的 ~/.ssh/authorized_keys%s%s"
                        % ("已写入" if installed == "installed" else "本就在",
                           via, user, host, port, jump_note, verify_note)),
        })
    except paramiko.ssh_exception.AuthenticationException:
        return _err("密码认证失败：密码不对，或该节点不允许密码登录。%s" %
                    ("（跳板 %s 已通，死在目标节点）" % via if via else ""),
                    node=name, host=host)
    except EOFError:
        return _err("对端在 SSH 握手阶段断开了连接（EOF）：%s%s@%s:%s 的 SSH 会话没建立起来。"
                    "通常是目标节点 sshd 没起 / 端口不对 / 跳板到目标之间被拦。"
                    % (via, user, host, port),
                    node=name, host=host,
                    hint="对照实验：在 MobaXterm 登录口手敲 ssh %s 能通的话，把现象发我" % host)
    except Exception as exc:
        return _err("安装失败：%s: %s" % (type(exc).__name__, exc), node=name, host=host,
                    hint="网络/端口/跳板问题先点「🔌 自检」或「🖥 节点体检」看具体哪一跳不通")
    finally:
        for c in (client, jump_client):
            try:
                if c is not None:
                    c.close()
            except Exception:
                pass


_ACTIONS = {
    "locate": _action_locate,
    "nodes": _action_nodes,
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


def _conn_hint(exc, node_cfg) -> str:
    """把 OpenSSH 的英文报错翻译成「下一步该点哪里」（WebUI 与 agent 共用这个诊断）。"""
    text = str(exc).lower()
    # 从节点实际生效的 extra_ssh_options 里认出跳板地址，提示里指名道姓
    jump = ""
    extra = [str(o) for o in (node_cfg.get("extra_ssh_options") or [])]
    for i, opt in enumerate(extra):
        low = opt.lower()
        if "proxyjump=" in low:
            jump = opt.split("=", 1)[1]
        elif opt == "-J" and i + 1 < len(extra):
            jump = extra[i + 1]
    if "could not resolve hostname" in text:
        return ("本机解析不了这个主机名——它是集群内网名字，必须给这个节点配「跳板机」"
                "（⚙️ 配置 → 节点行的跳板机框，填 用户名@登录口IP，如 zhangbo11@192.168.61.11），"
                "让登录口去解析它。")
    if "banner" in text or "unknown port 65535" in text:
        return ("走跳板的连接在跳板那一跳就断了（banner 超时 / UNKNOWN port 65535 的典型表现）——"
                "九成是跳板（登录口%s）上还没有我们的公钥，密钥认证被拒，管道随之中断。"
                "先去 ⚙️ 配置 → 输密码 → 点「🔑 安装公钥」（会自动把跳板一并装上），装完再自检。"
                % (" " + jump if jump else ""))
    if "permission denied" in text:
        return ("对方拒绝了密钥认证——公钥还没装到%s，或私钥路径指错。"
                "先在 ⚙️ 配置里输密码点一次「🔑 安装公钥」。"
                % ("跳板或目标节点" if jump else "目标节点"))
    if "connection refused" in text:
        return "对方端口拒接：检查节点的 host / port 是否填对（sshd 是否在这个端口上）。"
    if "timed out" in text or "timeout" in text:
        return "连接超时：检查 IP / 端口 / 网络（要不要连 VPN），或跳板地址是否填对。"
    return "连接类错误先用 action='nodes' 体检全部节点（或 action='check' 单节点）：密钥/端口/跳板机/known_hosts"


def remote_cluster_handler(args=None, **kwargs) -> str:
    args = args or {}
    cfg = _load_remote_config()
    action = str(args.get("action") or "").strip().lower()
    if action == "locate":
        # 路径判定：用户没说文件在哪时先用它查（远端没配也能用，只报本地那一半）
        try:
            return _action_locate(cfg, args)
        except Exception as exc:
            logger.exception("remote_cluster action=locate 失败")
            return _err("locate 执行失败: %s" % exc)
    if not remote_cluster_enabled():
        return _err(
            "远端集群未配置或未启用。请在 hermes_home/config.yaml 的 remote: 段配置，两种写法任选：\n"
            "① 单节点：\n  enabled: true\n  host: <登录节点>\n  user: <用户名>\n"
            "  key: <私钥路径>\n  workdir: <远端工作目录>\n"
            "② 多节点（命名节点，用 node= 选机器）：\n  enabled: true\n  user: <用户名>\n"
            "  key: <私钥路径>\n  workdir: <共享工作目录>\n  nodes:\n    ssh3: {}\n    ssh5: {}\n"
            "（或用环境变量 MEMOMICS_REMOTE_ENABLED/HOST/USER/KEY/WORKDIR 临时覆盖）"
        )
    if action not in _ACTIONS:
        return _err("未知 action: %r（可选：%s）" % (action, ", ".join(sorted(_ACTIONS))))
    if action == "nodes":
        # 体检所有节点，不需要先选定一个
        try:
            return _action_nodes(cfg, args)
        except Exception as exc:
            logger.exception("remote_cluster action=nodes 失败")
            return _err("nodes 执行失败: %s" % exc)

    requested = str(args.get("node") or args.get("host") or "").strip()
    node_cfg, node_name, err = _select_node(cfg, requested)
    if err:
        return err
    try:
        return _ACTIONS[action](node_cfg, args)
    except Exception as exc:
        logger.exception("remote_cluster action=%s node=%s 失败", action, node_name)
        _drop_conn(node_cfg)
        return _err("%s 执行失败: %s" % (action, exc),
                    node=node_name, host=node_cfg.get("host"),
                    hint=_conn_hint(exc, node_cfg))


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
        "  • submit —— 生成作业脚本并提交（Slurm=sbatch；PBS / Grid Engine（SGE/UGE，#$ 指令）=qsub，"
        "qstat 看队列、qdel 取消、qacct 查已结束作业；无调度器则 setsid 脱离会话后台跑），"
        "返回 job_id；随后 status 看状态、logs 读日志、cancel 取消。\n"
        "  • push / pull —— 本地 ↔ 远端传文件（大文件先 push 再 submit，产物 pull 回本地）。"
        "push 会自动处理 Windows 换行：.sh/.py/.R 等脚本带 CRLF 时转成 LF 再上传（本机文件不动，"
        "用 crlf='keep' 可关掉）；pull 有体积闸门，超过 max_mb（默认 512MB）直接拒绝，"
        "避免手滑把几百 GB 的 BAM 拖回本机。\n"
        "  • jobs   —— 列队列与最近提交记录。\n"
        "  • locate —— **判定一个路径在本地还是在集群上**（用户没说数据在哪时先跑这个，再决定在哪儿算）；"
        "远端没配置时也能用，只报本地那一半。\n"
        "  • nodes  —— 列配置里的所有节点，逐个探连通性 + 负载（谁空着、谁连不上）；"
        "不指定节点也能调用。\n"
        "【用哪个节点】config 的 remote.nodes 里配了多个命名节点（如 ssh3/ssh5）时，"
        "用 node=\"<名字>\" 指定；**只配了一个节点时不用传，工具静默用它**。"
        "配了多个但没传 node：**若设了 default_node 就静默用默认节点**（用户说「用集群」即默认节点）；"
        "只有既没传 node 又没配 default_node 才返回 status=needs_node + 候选列表，"
        "此时必须**先问用户要用哪个节点**再重新调用，不许自己挑一个、也不许沿用上次那个。\n"
        "【路径判定：先查清数据在哪，再决定在哪算——不要凭感觉】\n"
        "  ① 用户说了位置 → 以用户为准：本地路径（E:/...、results/...、'我上传的文件'）就在本地跑"
        "（execute_python/execute_r）；远端绝对路径（/home/you/...、/data/...）或明说'数据在集群上' → 用本工具。\n"
        "  ② 用户没说 → **先用 action='locate' 查**，别猜也别默认："
        "path 直接给用户消息里的原话路径，它会同时查本机（原样 / work/ / results/ 各会话目录 / webui/uploads/）"
        "和各节点（原样 / 工作目录 / 工作目录/data/），返回 verdict=local|cluster|ambiguous|missing + 命中位置和大小。\n"
        "  ③ verdict=ambiguous（两边都有）或 missing（两边都没有）→ **不要自己挑、不要编路径**："
        "把候选位置和大小报给用户问清楚；missing 时把查过的地方一起报出来，请他给准确路径。\n"
        "【产物分工】集群上只留大文件（原始数据/中间产物/BAM/FASTQ/大矩阵/模型权重），不要往本机拉；"
        "表格/图/脚本/日志这类小产物必须 pull 回本地 results/<会话>/，否则 WebUI 里看不到"
        "（WebUI 只浏览 work/ 和 results/）。判断标准："
        ".csv/.tsv/.xlsx/.png/.pdf/.svg/.R/.py/.log 这类（KB~几十 MB）→ 拉回来；"
        "超过 max_mb（默认 512MB）工具会返回 status=too_large 并拒绝，"
        "**这时先问用户要不要拉**，确认了再带 max_mb 或 allow_large=true。"
        "pull 支持通配符（远端 *.tsv 会展开成多个文件，放进 local_path 目录）和目录（递归）；"
        "默认不覆盖本机已有同名文件（返回 status=exists，给 overwrite=true 才覆盖）。\n"
        "连接配置在 hermes_home/config.yaml 的 remote: 段（host 或 nodes /user/port/key/workdir/"
        "scheduler/local_root/remote_root），需密钥登录（BatchMode，不会弹密码输入）；未配置时本工具不可见。\n"
        "⚠️ 两点别搞混：① 本工具只把**命令/作业**送到远端，execute_python / execute_r 的持久内核仍在本地跑——"
        "要在集群上算就把代码写成脚本交给 run/submit；② 远端路径（/home/you/...）与本地路径（E:/...）是两套，"
        "push/pull 可用 local_root/remote_root 自动换算。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["locate", "nodes", "check", "run", "push", "pull", "submit", "status",
                         "logs", "cancel", "jobs"],
                "description": "要执行的动作",
            },
            "node": {
                "type": "string",
                "description": ("用哪个远端节点（remote.nodes 里配置的名字，如 ssh3/ssh5）。"
                                "只配了一个节点时可省略；配了多个又没给这个参数，工具会拒绝执行"
                                "并列出候选——这时必须先问用户要用哪个节点。"
                                "也可以用 action='nodes' 先看各节点负载再决定。"),
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
            "path": {"type": "string",
                     "description": ("locate：要判定的路径（用用户消息里的原话，本地/远端都行）；"
                                     "logs：直接指定远端日志文件路径")},
            "lines": {"type": "integer", "description": "logs：看末尾多少行（默认 100）"},
            "max_mb": {"type": "number",
                       "description": ("pull：允许拉回的最大体积（MB，默认 %d）。超过会返回 "
                                       "status=too_large 并拒绝下载——先问用户；确认要拉再显式给更大的值。"
                                       % _PULL_MAX_MB_DEFAULT)},
            "allow_large": {"type": "boolean",
                            "description": "pull：true = 不设体积上限（默认 false；超上限时一律先问用户）"},
            "overwrite": {"type": "boolean",
                          "description": ("pull：true = 允许覆盖本机同名文件"
                                          "（默认 false，遇到同名返回 status=exists 等确认）")},
            "crlf": {"type": "string", "enum": ["auto", "lf", "keep"],
                     "description": ("push：Windows 换行处理。auto（默认）= .sh/.py/.R/.sbatch 等脚本"
                                     "检测到 CRLF 自动转 LF 再上传（本机原文件不动）；"
                                     "keep = 原样上传；lf = 强制转 LF。")},
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
