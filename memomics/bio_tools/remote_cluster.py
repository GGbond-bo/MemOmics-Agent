"""MemOmics 远端集群（SSH）工具 — 把 memomics 的 SSH 后端接进 MemOmics。

背景
----
memomics 框架本身带 SSH 执行后端（hermes-agent/tools/environments/ssh.py 的
SSHEnvironment：ControlMaster 连接复用 + 持久会话快照 + cwd 标记），但 MemOmics
的算力链是**本地**的（execute_r/execute_python 直接 subprocess 调本机 Rscript/
python）。因此本工具把那条 SSH 链路单独接出来，给 MemOmics 增加"连集群"的能力：

  * 只连一台远端登录节点（host/user/port/key 来自 config.yaml 的 remote: 段）
  * run        — 登录节点上跑轻量命令（探查/环境自检）
  * submit     — 生成作业脚本并提交到 Slurm / PBS / 无调度器（nohup 后台）
  * status/logs/cancel/jobs — 看作业状态、读日志、取消、列队列
  * push/pull  — 本地 ↔ 远端文件同步（重活产物回传本地，继续用 execute_r 分析）

与 memomics SSHEnvironment 的关系（重要）
-------------------------------------
ClusterSSH 直接继承 SSHEnvironment，复用它的 _build_ssh_command /
_establish_connection / _detect_remote_home / _run_bash / execute / cleanup
（即整条 SSH 传输与执行引擎），只覆盖两处：

  1. 不调用父类 __init__ 里那两步"把本地 ~/.memomics 同步到远端"的逻辑
     （file_sync.iter_sync_files 会把 credentials/skills/cache 上传到远端）。
     集群登录节点是共享机器，把本机凭据/技能推上去既不必要也不安全，
     实测本机该清单含 10 个 skills/_debates/*.json；配置了凭据时还会带凭据文件。
  2. _before_execute() 置空 —— 父类每次执行前都会触发一次文件同步，
     集群场景不需要。

旧版手工连接的 SSH 命令构造（ControlMaster/ControlPersist/BatchMode/
StrictHostKeyChecking=accept-new/ConnectTimeout/-p/-i）与 memomics 保持一致。
目录管理的 V5 密码连接则使用固定 System32 OpenSSH、受控 ``-F`` 路由和 ASKPASS，
不使用 ``-i``、ssh-agent 或 ControlMaster，因此可按其独立的密码连接提示排查。

配置（memomics_home/config.yaml）
-------------------------------
    remote:
      enabled: true                 # 总开关；false 或缺省时本工具不出现在工具列表
      host: login.example.edu.cn    # 登录节点
      user: zhangsan
      port: 22
      key: <用户目录>/.ssh/id_ed25519   # 私钥路径；留空则用 ssh-agent/默认密钥
      workdir: /home/zhangsan/proj       # 远端工作目录（默认执行目录）
      scheduler: auto               # auto | slurm | pbs | gridengine | none
      partition: cpu                # Slurm 默认分区
      queue: ""                     # PBS 默认队列
      local_root: <安装目录> # 与 remote_root 配对，用于路径映射（可选）
      remote_root: /home/zhangsan/proj
      job_dir: ""                   # 作业脚本/日志目录，默认 <workdir>/memomics_jobs
      timeout: 300                  # run 默认超时（秒）
      max_output_chars: 20000       # 返回给模型的输出上限
      extra_ssh_options: []         # 追加 ssh 参数，例如 ["-o","ProxyJump=bastion"]

环境变量覆盖（便于临时测试，不必改配置）：
    MEMOMICS_REMOTE_ENABLED / _HOST / _USER / _PORT / _KEY / _WORKDIR /
    _SCHEDULER / _LOCAL_ROOT / _REMOTE_ROOT

认证方式：目录管理的连接使用本机加密保存的账号密码和受控 ASKPASS；旧版手工配置仍可使用
BatchMode 密钥登录。浏览器不会显示或接收 SSH 密码交互。
本机没有 ssh/scp 时工具自检报错并说明装法。

平台差异：旧版手工连接默认用 ControlMaster 复用连接，但 Windows 自带的
Win32-OpenSSH 没有 mux 支持（报 "getsockname failed: Not a socket"），会自动
降级为"每次新建连接"。目录管理的 V5 密码连接始终每次新建连接，不需要手工配置。
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import posixpath
import re
import shlex
import shutil
import socket
import stat
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from memomics.bio_tools import ssh_policy as _ssh_policy
from memomics.bio_tools import password_ssh as _password_ssh
from memomics.bio_tools import askpass_security as _askpass_security

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
    "persist_gate": True,        # 铁规 10 硬闸：run/submit 要读 ≥100MB 未标记大输入 → 拒绝执行
    "persist_min_mb": 100,       # 硬闸阈值（MB）
    # --- 常驻 R 会话（kernel 式持久化，2026-10-09）---
    # remote.session: {env, rscript, roots, dir, load_timeout, wait, save_wait, max_sessions}
    # 节点级可覆盖：remote.nodes.<名字>.session: {...}（比如某台机器上 R 在别的路径）
    "session": {},
}

_CFG_CACHE = {"mtime": None, "cfg": None}


def _get_config_path() -> Path:
    """定位 memomics_home/config.yaml（与 debate_analysis._get_config_path 同源）。"""
    try:
        from hermes_constants import get_hermes_home
        base = Path(get_hermes_home())
    except Exception:
        base = Path(os.environ.get("MEMOMICS_HOME", "<安装目录>/memomics_home"))
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
    if not cfg["key"]:
        try:                                    # 2026-10-11：留空即自动探测本机默认密钥
            _det = detect_private_keys()
            if _det:
                cfg["key"] = _det[0]
        except Exception:
            pass
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
    # Both host and user may be per-profile.  A managed account profile with a
    # missing host is intentionally incomplete rather than an implicit alias
    # for its random stable id.
    return any(str(t.get("host") or "").strip() and str(t.get("user") or "").strip()
               for t in table.values())


# ---------------------------------------------------------------------------
# 多节点（命名节点）—— MobaXterm 式的命名连接，按名字选机器
# ---------------------------------------------------------------------------

_NODE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")

# 节点条目里允许覆盖的字段；其余一律跟共享配置走（同一个集群路径一样，没必要重复配）
_NODE_OVERRIDE_KEYS = (
    "host", "user", "port", "key", "workdir", "job_dir", "scheduler",
    "partition", "queue", "local_root", "remote_root", "timeout", "proxy_jump", "extra_ssh_options",
    "note", "role", "display_name", "connection_profile", "catalog_v4_ssh_route",
    # V5 password profiles have no key material.  These are opaque
    # non-secret provenance fields used to obtain the account password from
    # Windows Credential Manager at execution time.
    "auth_mode", "catalog_account_id", "gateway_account_id", "catalog_v5_ssh_route",
    "catalog_v5_target_alias", "catalog_v5_gateway_alias", "catalog_v5_gateway_host",
    "catalog_v5_gateway_user", "catalog_v5_gateway_port",
)

# Legacy hand-written nodes historically treat an omitted/empty field as an
# inherited top-level value.  Account-only catalog PATCHes can instead make a
# deliberate clear authoritative for just the edited profile.  The marker is
# internal YAML metadata, never an API response field or SSH argument.
_EXPLICIT_EMPTY_OVERRIDE_MARKER = "_memomics_explicit_empty_overrides"
_EXPLICIT_EMPTY_OVERRIDE_FIELDS = frozenset({
    "key", "workdir", "job_dir", "local_root", "remote_root", "proxy_jump", "extra_ssh_options",
})

# Durable remote resources must not be retargeted when an operator later edits
# or removes their named profile.  Keep this deliberately to connection and
# scheduler fields: it contains only a private-key *path*, never credential
# material.  New job/session records write every field (including empty
# values), so re-entry can distinguish an intentionally empty override from an
# older record that simply predates a field.
_CONNECTION_SNAPSHOT_FIELDS = (
    "host", "user", "port", "key", "workdir", "job_dir", "scheduler",
    "partition", "queue", "local_root", "remote_root", "timeout", "extra_ssh_options", "proxy_jump", "session",
    "catalog_v4_ssh_route", "auth_mode", "catalog_account_id", "gateway_account_id",
    "catalog_v5_ssh_route", "catalog_v5_target_alias", "catalog_v5_gateway_alias",
    "catalog_v5_gateway_host", "catalog_v5_gateway_user", "catalog_v5_gateway_port",
)

_LITERAL_HOST_RE = re.compile(r"^(?:([^@\s]+)@)?([A-Za-z0-9._-]+)(?::(\d+))?$")


def _normalize_nodes(raw) -> dict:
    """把 config 的 nodes: 段规范化成 {名字: {显式覆盖字段}}。

    支持三种写法（都合法，按需混用）::

        remote:
          nodes:
            node1: {}                    # 名字本身就是 ssh 主机名 / ~/.ssh/config 里的别名
            node2: node2.example.org      # 字符串 = 显式主机名
            gpu1:                       # 完整写法：只写要覆盖的字段
              host: 10.0.0.5
              user: zhang
              port: 2222
              key: <用户目录>/.ssh/id_gpu
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
            raw_empty_overrides = spec.get(_EXPLICIT_EMPTY_OVERRIDE_MARKER) or []
            explicit_empty = {
                str(field) for field in raw_empty_overrides
                if str(field) in _EXPLICIT_EMPTY_OVERRIDE_FIELDS
            } if isinstance(raw_empty_overrides, (list, tuple, set)) else set()
            for k in _NODE_OVERRIDE_KEYS:
                val = spec.get(k)
                if val is None:
                    continue
                if isinstance(val, str) and not val.strip() and k not in explicit_empty:
                    continue
                entry[k] = _as_list(val) if k == "extra_ssh_options" else val
        else:
            logger.warning("remote.nodes.%s 的值类型不支持（%s），按空配置处理",
                           key, type(spec).__name__)
        # Hand-written legacy nodes may use their mapping key as an SSH alias.
        # API-managed connection profiles are different: an omitted host must
        # remain incomplete rather than turning a generated stable id into a
        # remote hostname (and accidentally using a wrong account).
        if not entry.get("connection_profile"):
            entry.setdefault("host", key)
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
        if entry.get("connection_profile") is True:
            # API-created profiles represent a concrete server/account pair.
            # Do not let an omitted account field borrow credentials or a
            # path mapping / working directory from an old top-level
            # single-server setup.
            # Legacy hand-written nodes without this marker keep their shared
            # inheritance behaviour for backwards compatibility.
            node.update({
                "host": "", "user": "", "port": 22, "key": "",
                "workdir": "~", "job_dir": "", "extra_ssh_options": [],
                "local_root": "", "remote_root": "", "proxy_jump": "",
                "scheduler": "auto", "partition": "", "queue": "", "timeout": 300,
            })
        node.update({k: v for k, v in entry.items() if k not in ("note", "role")})
        node["_name"] = name
        # The mapping key is the stable server id.  A friendly display name is
        # intentionally separate so renaming it never breaks a chat session
        # that is bound to this server.
        node["_display_name"] = str(entry.get("display_name") or name)
        node["_note"] = str(entry.get("note") or "")
        node["_role"] = str(entry.get("role") or "")
        node["_shared"] = False
        if entry.get("connection_profile") is True:
            node["host"] = str(node.get("host") or "").strip()
        else:
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


def _connection_snapshot(cfg: dict) -> dict:
    """Return a detached, complete connection snapshot for a durable resource.

    Do not filter false-y values here.  ``key=''`` and
    ``extra_ssh_options=[]`` are meaningful: falling back to a subsequently
    edited server profile could send a historical job through the wrong key or
    bastion.  Older records omit fields entirely and are handled compatibly by
    the replay code below.
    """
    snapshot = {}
    for field in _CONNECTION_SNAPSHOT_FIELDS:
        # Do not add an empty new-only field to historical V1 snapshots.  Its
        # presence is itself a version signal during replay, and a stale/unknown
        # non-empty value must never be silently reclassified as legacy.
        if field == "catalog_v4_ssh_route":
            if catalog_v4_ssh_route_required(cfg.get(field)):
                snapshot[field] = CATALOG_V4_SSH_ROUTE_MARKER
            continue
        if field == "catalog_v5_ssh_route":
            if catalog_v5_ssh_route_required(cfg.get(field)):
                snapshot[field] = CATALOG_V5_SSH_ROUTE_MARKER
            continue
        value = cfg.get(field)
        if isinstance(value, dict):
            value = dict(value)
        elif isinstance(value, (list, tuple)):
            value = list(value)
        snapshot[field] = value
    return snapshot


def _apply_connection_snapshot(base: dict, record: dict) -> dict:
    """Overlay a persisted connection snapshot without losing deliberate empties.

    A field's *presence* is the version boundary: new records include all
    snapshot fields, whereas old records fall back to the current profile only
    for fields they never stored.
    """
    node = dict(base or {})
    record = record if isinstance(record, dict) else {}
    for field in _CONNECTION_SNAPSHOT_FIELDS:
        if field not in record:
            continue
        if field == "catalog_v4_ssh_route":
            # Interim builds wrote ``null`` for legacy records.  Treat that as
            # absent so it cannot erase a current V4 profile marker; exact V4
            # provenance survives durable R-session/job re-entry, while any
            # other non-empty marker is an integrity failure.
            if catalog_v4_ssh_route_required(record.get(field)):
                node[field] = CATALOG_V4_SSH_ROUTE_MARKER
            continue
        if field == "catalog_v5_ssh_route":
            if catalog_v5_ssh_route_required(record.get(field)):
                node[field] = CATALOG_V5_SSH_ROUTE_MARKER
            continue
        value = record.get(field)
        if isinstance(value, dict):
            value = dict(value)
        elif isinstance(value, (list, tuple)):
            value = list(value)
        node[field] = value
    # ``cluster_kernel``/node_state records historically use ``extra_opts``.
    # Accept it only when the canonical field is absent, preserving an explicit
    # empty ``extra_ssh_options`` in a new remote-cluster record.
    if "extra_ssh_options" not in record and "extra_opts" in record:
        node["extra_ssh_options"] = list(record.get("extra_opts") or [])
    try:
        node["port"] = int(node.get("port") or 22)
    except Exception:
        node["port"] = 22
    return node


def _nodes_brief(table: dict) -> list:
    return [{"name": n, "display_name": t.get("_display_name") or n,
             "host": t.get("host"), "user": t.get("user"),
             "note": t.get("_note") or "", "role": t.get("_role") or ""}
            for n, t in table.items()]


def bound_server_for_session(session_id: str = "") -> str:
    """Compatibility shim for retired chat-to-profile target bindings.

    Older callers (including the kernel helper) still import this function.
    Session metadata is deliberately not read: ``chat_session_id`` now records
    ownership only, so a stale binding or a metadata outage cannot choose or
    block a remote target.  Kept as a stable no-op until old clients stop
    calling the legacy binding endpoints.
    """
    _ = session_id
    return ""


def select_node_for_session(cfg: dict, requested: str = "", session_id: str = "",
                            recorded_target: bool = False):
    """Resolve a current node without using deprecated chat/profile bindings.

    ``chat_session_id`` remains valuable for user-message and durable job
    attribution, but it is not a target-selection authority.  New work may
    explicitly select any configured profile from any chat; without an
    explicit node the long-standing single-node/default/``needs_node`` policy
    applies.  Historical job and R-session re-entry remains the sole special
    case: it must reconnect to its recorded target (or reject a missing target
    rather than treating the retired profile id as a host name).
    """
    requested = str(requested or "").strip()
    # A persisted job/daemon owns a historical connection snapshot.  Do not
    # read current session metadata for that re-entry path.  It may still rely
    # on a current named profile when an older record predates full snapshots;
    # in that case never let the convenience literal-host fallback turn a
    # deleted stable id into an SSH destination.
    if recorded_target:
        table = _node_table(cfg)
        if requested.lower() == "legacy-default" and len(table) == 1 and not (cfg.get("nodes") or {}):
            name = next(iter(table))
            return table[name], name, None
        for name, node in table.items():
            if name.lower() == requested.lower():
                return node, name, None
        return None, "", _err(
            "历史资源登记的服务器 %r 已不存在，且记录没有可用的连接快照；已拒绝把它当作裸主机连接。"
            % requested,
            status="historical_target_missing", recorded_server_id=requested,
            nodes=_nodes_brief(table),
        )
    # ``session_id`` deliberately has no selection effect.  Keep it in the
    # signature for tool/API compatibility and for callers that use it only as
    # durable resource attribution.
    _ = session_id
    return _select_node(cfg, requested)


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
            "没有可用的远端节点：请在 memomics_home/config.yaml 的 remote: 段配置 "
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
        # 2026-10-10（用户报「装公钥失败：remote.default_node='https://…' 不在 nodes 里」）：
        # 只配了一个节点时，default_node 写错了不该把用户挡在门外 —— 一个节点谈不上歧义，直接用。
        if len(table) == 1:
            name = next(iter(table))
            node = dict(table[name])
            node["_note"] = ("⚠️ remote.default_node=%r 不是已配置的节点名，已自动改用唯一的节点 %r"
                             "（建议在「⚙️ 配置」里把默认节点清空或改成它）" % (default_node, name))
            return node, name, None
        return None, "", _err(
            "remote.default_node=%r 不在 nodes 里，已配置：%s（把默认节点改成其中之一，或清空它、每次点名）"
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
        "usage": "remote_cluster(action='submit', node='node1', command='...')",
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
    host 完全可能一样（例如 node1/node2 都指向同一台登录机），再退回比 host 会把
    A 节点的作业当成 B 节点的。只有升级前的旧记录（没有 node 字段）才退化成比 host。
    """
    name = str(cfg.get("_name") or "")
    rec_node = str(rec.get("node") or "")
    if rec_node:
        return bool(name) and rec_node == name
    return bool(cfg.get("host")) and rec.get("host") == cfg.get("host")


# ---------------------------------------------------------------------------
# SSH 连接层（继承 memomics SSHEnvironment，跳过 ~/.memomics 同步）
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
    """延迟导入 memomics 的 SSHEnvironment（失败时给出清晰原因）。"""
    try:
        from tools.environments.base import BaseEnvironment
        from tools.environments.ssh import SSHEnvironment
    except Exception as exc:
        raise RuntimeError(
            "无法导入 memomics 的 SSH 后端（tools.environments.ssh）：%s。"
            "确认 hermes-agent 目录在本进程 sys.path 上。" % exc
        )
    return BaseEnvironment, SSHEnvironment


_CONN_LOCK = threading.RLock()
_CONNS: dict = {}
_CLUSTER_SSH_CLS = None

# Windows 版 OpenSSH（Win32-OpenSSH）没有编译 mux 支持，带
# ControlMaster/ControlPath 会直接失败：getsockname failed: Not a socket。
# 这里做能力探测：先用 mux 试连，命中该错误就永久降级为"每次新建连接"
# （仍然复用 memomics 的 SSH 命令构造与执行引擎，只是没有连接复用）。
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
        """memomics SSHEnvironment 的集群变体：同样走 ssh/scp，但不做 ~/.memomics 同步。

        父类 __init__ 会调用 FileSyncManager.sync(force=True)，把本地
        credentials/skills/cache 上传到远端 ~/.memomics —— 对共享登录节点不合适，
        这里刻意跳过；SSH 命令构造与执行引擎仍完全复用父类。
        """

        def __init__(self, host: str, user: str, cwd: str = "~", timeout: int = 60,
                     port: int = 22, key_path: str = "", extra_options=None,
                     catalog_v4_ssh_route: str = "", catalog_v5_ssh_route: str = "",
                     auth_mode: str = "", catalog_account_id: str = "", gateway_account_id: str = "",
                     catalog_v5_target_alias: str = "", catalog_v5_gateway_alias: str = "",
                     catalog_v5_gateway_host: str = "", catalog_v5_gateway_user: str = "",
                     catalog_v5_gateway_port: int | str = ""):
            global _MUX_KNOWN_UNSUPPORTED
            BaseEnvironment.__init__(self, cwd=cwd, timeout=timeout)
            self.host = host
            self.user = user
            self.port = int(port or 22)
            self.key_path = key_path or ""
            self.catalog_v4_ssh_route = catalog_v4_ssh_route_required(catalog_v4_ssh_route)
            self.catalog_v5_ssh_route = catalog_v5_ssh_route_required(catalog_v5_ssh_route)
            if self.catalog_v4_ssh_route and self.catalog_v5_ssh_route:
                raise RuntimeError("a catalog profile cannot use both V4 and V5 authentication")
            self._v5_profile = {
                "host": self.host, "user": self.user, "port": self.port,
                "workdir": cwd or "~", "timeout": int(timeout or 60),
                "auth_mode": auth_mode, "catalog_account_id": catalog_account_id,
                "gateway_account_id": gateway_account_id,
                "catalog_v5_ssh_route": catalog_v5_ssh_route,
                "catalog_v5_target_alias": catalog_v5_target_alias,
                "catalog_v5_gateway_alias": catalog_v5_gateway_alias,
                "catalog_v5_gateway_host": catalog_v5_gateway_host,
                "catalog_v5_gateway_user": catalog_v5_gateway_user,
                "catalog_v5_gateway_port": catalog_v5_gateway_port,
                "extra_ssh_options": list(extra_options or []),
            }
            if self.catalog_v5_ssh_route:
                # A V5 profile must never carry an identity-file fallback.
                if self.key_path:
                    raise RuntimeError("catalog V5 password profile cannot carry a key path")
                _candidate, self.catalog_ssh_config_args, _runtime = catalog_v5_process_runtime(self._v5_profile)
                self.extra_options = []
                self.catalog_strict_host_keys = True
            else:
                self.catalog_ssh_config_args, self.extra_options = _split_catalog_ssh_options(
                    extra_options, host=self.host, user=self.user, port=self.port, key=self.key_path,
                    require_managed=self.catalog_v4_ssh_route,
                )
                self.catalog_strict_host_keys = bool(self.catalog_ssh_config_args)

            # Windows 没有 unix socket / Win32-OpenSSH 无 mux：默认关掉连接复用
            self.use_mux = (not self.catalog_v5_ssh_route) and (not _MUX_KNOWN_UNSUPPORTED) and os.name != "nt"
            self.control_dir = Path(tempfile.gettempdir()) / "memomics-ssh"
            self.control_dir.mkdir(parents=True, exist_ok=True)
            _socket_id = hashlib.sha256(json.dumps({
                "host": host, "user": user, "port": self.port,
                "key": self.key_path, "extra_options": self.extra_options,
                "catalog_ssh_config": self.catalog_ssh_config_args,
            }, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
            self.control_socket = self.control_dir / ("%s.sock" % _socket_id)

            self._sync_manager = None
            if self.catalog_v5_ssh_route:
                # V5 never trusts PATH: the runtime later launches only the
                # OS-owned System32 OpenSSH binaries.
                _password_ssh.system_openssh_executable("ssh.exe")
                _password_ssh.system_openssh_executable("scp.exe")
            else:
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

        def _v5_command(self, extra_args=None):
            """Return one non-multiplexed OpenSSH argv/env pair for V5."""
            _candidate, config_args, runtime = catalog_v5_process_runtime(self._v5_profile)
            cmd = [str(_password_ssh.system_openssh_executable("ssh.exe"))] + list(config_args) + [
                "-o", "BatchMode=no", "-o", "ConnectTimeout=10",
            ]
            if extra_args:
                cmd.extend(extra_args)
            cmd.append("%s@%s" % (self.user, runtime.target_alias))
            return cmd, runtime

        def _v5_scp_base(self):
            """Return one V5 SCP argv prefix/env/alias with no key fallback."""
            _candidate, config_args, runtime = catalog_v5_process_runtime(self._v5_profile)
            cmd = [str(_password_ssh.system_openssh_executable("scp.exe")), "-r", "-q"] + list(config_args) + [
                "-o", "BatchMode=no", "-o", "ConnectTimeout=10",
            ]
            return cmd, runtime

        def _establish_connection(self):
            if not self.catalog_v5_ssh_route:
                return super()._establish_connection()
            cmd, runtime = self._v5_command()
            cmd.append("echo 'SSH connection established'")
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                        stdin=subprocess.DEVNULL, env=runtime.env)
                if result.returncode != 0:
                    raise RuntimeError("SSH connection failed: %s" % (result.stderr.strip() or result.stdout.strip()))
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("SSH connection to %s@%s timed out" % (self.user, self.host)) from exc

        def _detect_remote_home(self):
            if not self.catalog_v5_ssh_route:
                return super()._detect_remote_home()
            try:
                cmd, runtime = self._v5_command()
                cmd.append("echo $HOME")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                                        stdin=subprocess.DEVNULL, env=runtime.env)
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except Exception:
                pass
            return "/root" if self.user == "root" else "/home/%s" % self.user

        def _build_ssh_command(self, extra_args=None):
            if self.catalog_v5_ssh_route:
                cmd, _runtime = self._v5_command(extra_args)
                return cmd
            # A long-lived connection may execute after an external file
            # change.  Revalidate the immutable -F proof on every command,
            # not merely when this ClusterSSH object was constructed.
            self.catalog_ssh_config_args, self.extra_options = _split_catalog_ssh_options(
                list(self.catalog_ssh_config_args) + list(self.extra_options),
                host=self.host, user=self.user, port=self.port, key=self.key_path,
                require_managed=self.catalog_v4_ssh_route,
            )
            self.catalog_strict_host_keys = bool(self.catalog_ssh_config_args)
            if self.use_mux:
                cmd = super()._build_ssh_command(extra_args)
            else:
                # 复刻父类命令构造，只是不带 ControlMaster/ControlPath。
                # V4 puts its verified -F first because ProxyJump children
                # inherit -F but not arbitrary outer -o options.
                cmd = ["ssh"] + list(self.catalog_ssh_config_args) + [
                       "-o", "BatchMode=yes",
                       "-o", "StrictHostKeyChecking=%s" % ("yes" if self.catalog_strict_host_keys else "accept-new"),
                       "-o", "ConnectTimeout=10"]
                if self.port != 22:
                    cmd.extend(["-p", str(self.port)])
                if self.key_path:
                    cmd.extend(["-i", self.key_path])
                if extra_args:
                    cmd.extend(extra_args)
                cmd.append("%s@%s" % (self.user, self.host))
            if self.catalog_strict_host_keys and self.use_mux:
                # The inherited builder has a legacy accept-new flag.  Remove
                # it rather than relying on later config precedence, then put
                # the content-addressed -F at argv start with an explicit yes.
                filtered = [cmd[0]]
                index = 1
                while index < len(cmd):
                    if (cmd[index] == "-o" and index + 1 < len(cmd)
                            and str(cmd[index + 1]).lower().startswith("stricthostkeychecking=")):
                        index += 2
                        continue
                    filtered.append(cmd[index])
                    index += 1
                cmd = [filtered[0]] + list(self.catalog_ssh_config_args) + [
                    "-o", "StrictHostKeyChecking=yes",
                ] + filtered[1:]
            if self.extra_options and cmd:
                # ssh 选项必须排在 host 之前
                cmd[-1:] = list(self.extra_options) + [cmd[-1]]
            return cmd

        def _run_bash(self, cmd_string: str, *, login: bool = False, timeout: int = 120,
                      stdin_data: str | None = None):
            if not self.catalog_v5_ssh_route:
                return super()._run_bash(cmd_string, login=login, timeout=timeout, stdin_data=stdin_data)
            from tools.environments.base import _popen_bash
            cmd, runtime = self._v5_command()
            if login:
                cmd.extend(["bash", "-l", "-c", shlex.quote(cmd_string)])
            else:
                cmd.extend(["bash", "-c", shlex.quote(cmd_string)])
            return _popen_bash(cmd, stdin_data, env=runtime.env)

        def cleanup(self):
            # V5 deliberately disables ControlMaster: every native process
            # receives a fresh bounded ASKPASS environment and cannot reuse a
            # key-authenticated master connection from a historical profile.
            if self.catalog_v5_ssh_route:
                return None
            return super().cleanup()

        def _before_execute(self) -> None:
            # 集群场景不做本地→远端文件同步（父类默认行为）
            return None

    _CLUSTER_SSH_CLS = ClusterSSH
    return ClusterSSH


def _conn_key(cfg: dict) -> str:
    # A profile is a complete connection identity.  Same-host accounts can
    # differ by user, identity path, jump route or working directory; reusing
    # the first ClusterSSH object would retain its cwd/SSH options.
    v4_route = catalog_v4_ssh_route_required(cfg.get("catalog_v4_ssh_route"))
    v5_route = catalog_v5_password_profile(cfg)
    identity = {
        "host": str(cfg.get("host") or ""),
        "user": str(cfg.get("user") or ""),
        "port": int(cfg.get("port") or 22),
        "key": str(cfg.get("key") or ""),
        "workdir": str(cfg.get("workdir") or "~"),
        "timeout": int(cfg.get("timeout") or 300),
        "extra_ssh_options": list(cfg.get("extra_ssh_options") or []),
    }
    if v4_route:
        # Preserve V1's historical cache identity byte-for-byte.  V4-only
        # provenance and the content-addressed route digest participate only
        # for profiles that actually carry the exact persistent marker.
        identity["catalog_v4_ssh_route"] = CATALOG_V4_SSH_ROUTE_MARKER
        identity["catalog_ssh_config"] = _catalog_ssh_config_fingerprint(
            cfg.get("extra_ssh_options") or [], cfg,
        )
    if v5_route:
        identity.update({
            "catalog_v5_ssh_route": CATALOG_V5_SSH_ROUTE_MARKER,
            "auth_mode": CATALOG_V5_PASSWORD_AUTH_MODE,
            "catalog_account_id": str(cfg.get("catalog_account_id") or ""),
            "gateway_account_id": str(cfg.get("gateway_account_id") or ""),
            "catalog_v5_target_alias": str(cfg.get("catalog_v5_target_alias") or ""),
            "catalog_v5_gateway_alias": str(cfg.get("catalog_v5_gateway_alias") or ""),
            "catalog_ssh_config": _catalog_ssh_config_fingerprint(
                cfg.get("extra_ssh_options") or [], cfg,
            ),
        })
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _get_conn(cfg: dict, force_reconnect: bool = False):
    # Fail closed before returning an existing cached client too.
    _catalog_ssh_config_fingerprint(cfg.get("extra_ssh_options") or [], cfg)
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
            kwargs = {
                "host": cfg["host"],
                "user": cfg["user"],
                "cwd": cfg["workdir"] or "~",
                "timeout": cfg["timeout"],
                "port": cfg["port"],
                "key_path": cfg["key"],
                "extra_options": cfg["extra_ssh_options"],
            }
            if catalog_v4_ssh_route_required(cfg.get("catalog_v4_ssh_route")):
                kwargs["catalog_v4_ssh_route"] = CATALOG_V4_SSH_ROUTE_MARKER
            if catalog_v5_password_profile(cfg):
                kwargs.update({
                    "catalog_v5_ssh_route": CATALOG_V5_SSH_ROUTE_MARKER,
                    "auth_mode": CATALOG_V5_PASSWORD_AUTH_MODE,
                    "catalog_account_id": cfg.get("catalog_account_id") or "",
                    "gateway_account_id": cfg.get("gateway_account_id") or "",
                    "catalog_v5_target_alias": cfg.get("catalog_v5_target_alias") or "",
                    "catalog_v5_gateway_alias": cfg.get("catalog_v5_gateway_alias") or "",
                    "catalog_v5_gateway_host": cfg.get("catalog_v5_gateway_host") or "",
                    "catalog_v5_gateway_user": cfg.get("catalog_v5_gateway_user") or "",
                    "catalog_v5_gateway_port": cfg.get("catalog_v5_gateway_port") or "",
                })
            conn = ClusterSSH(**kwargs)
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


def _iter_jobs(limit: int | None = 200) -> list:
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
    return out if limit is None else out[-limit:]


def _find_job(cfg: dict, job_id: str):
    # An explicit job id is an identity lookup, not a "recent jobs" view.
    # Keep scanning the append-only local ledger so an old record can retain
    # its scheduler/log/pid metadata after later submissions.
    for rec in reversed(_iter_jobs(limit=None)):
        if str(rec.get("job_id")) == str(job_id) and _rec_matches_node(rec, cfg):
            return rec
    return None


_INTERNAL_SELECTED_JOB_RECORD = "_memomics_selected_job_record"


def _selected_job_record(args: dict, cfg: dict, job_id: str):
    """Return the handler-selected historical record when it matches this call.

    The public handler strips this private key from inbound args before making
    its own full-ledger selection.  Actions therefore use it only as an
    internal hand-off, never as a REST/model supplied target override.
    """
    record = args.get(_INTERNAL_SELECTED_JOB_RECORD)
    if not isinstance(record, dict) or not job_id:
        return None
    if str(record.get("job_id") or "") != str(job_id):
        return None
    if not _rec_matches_node(record, cfg):
        return None
    return dict(record)


def _job_owner_node(job_id: str) -> str:
    """这个 job_id 在记录里属于哪个节点（没有记录返回空串）。"""
    for rec in reversed(_iter_jobs(limit=None)):
        if str(rec.get("job_id")) == str(job_id):
            return str(rec.get("node") or "")
    return ""


def _recorded_job_summary(record: dict) -> dict:
    """Return a non-secret diagnostic summary for an ambiguous job id."""
    return {
        "server_id": str(record.get("server_id") or ""),
        "node": str(record.get("node") or ""),
        "host": str(record.get("host") or ""),
        "session_id": str(record.get("session_id") or ""),
        "ts": str(record.get("ts") or record.get("created") or ""),
        "name": str(record.get("name") or ""),
    }


def _select_recorded_job_snapshot(job_id: str, *, requested: str = "", chat_session_id: str = ""):
    """Resolve one historical job without guessing across colliding scheduler IDs.

    Schedulers commonly issue the same numeric id on separate servers.  A
    status/log/cancel request must therefore use an explicit target first,
    then its owning chat, and only finally a globally unique record.  Returning
    an error rather than the most recent JSONL entry keeps cancel/log actions
    from being sent to another cluster.
    """
    wanted = str(job_id or "").strip()
    if not wanted:
        return None, None
    candidates = [dict(item) for item in _iter_jobs(limit=None)
                  if str(item.get("job_id") or "") == wanted]
    if not candidates:
        return None, None
    target = str(requested or "").strip().lower()
    if target:
        matches = [item for item in candidates if target in {
            str(item.get("server_id") or "").strip().lower(),
            str(item.get("node") or "").strip().lower(),
            str(item.get("host") or "").strip().lower(),
        }]
        if not matches:
            return None, _err(
                "job_id %s 的登记目标与请求的 node/host %r 不匹配，已拒绝操作。" % (wanted, requested),
                status="job_target_mismatch", job_id=wanted,
                candidates=[_recorded_job_summary(item) for item in candidates[:12]],
            )
        candidates = matches
    if chat_session_id:
        owned = [item for item in candidates
                 if str(item.get("session_id") or "") == str(chat_session_id)]
        if owned:
            candidates = owned
    if len(candidates) == 1:
        return candidates[0], None
    return None, _err(
        "job_id %s 在多个服务器或聊天会话中出现，无法安全判断目标；请指定 node/host 或从所属聊天操作。" % wanted,
        status="ambiguous_job", job_id=wanted,
        candidates=[_recorded_job_summary(item) for item in candidates[:12]],
    )


# ---------------------------------------------------------------------------
# 集群作业监督（P0 本机证据 + P1 轮询回写；2026-10-09）
#
# 背景：server 的自检唤醒链判断「还有没有活在跑」时只看 process_registry 与
# results_dir——集群作业提交后本机没有任何痕迹，于是有两种坏情况：
#   · 集群在跑但本机 15 分钟没写盘 → _session_no_live_work=True → 被当「已完成」
#   · 会话没有 task_plan/todos 时根本不调度自检 → 没人回来查作业
# 这组函数把「集群侧还有活在跑」变成**纯本地可判定**的证据（绝不 ssh），并给
# 轮询提供状态回写：
#   · session_touches.json  哪个 agent 会话最近碰过集群（归属用）
#   · job_states.json       每次轮询/status 落下的作业状态（queued/running/done/failed…）
# 不变量：读不到/解析失败 → 一律「无证据」，不抛异常（失败开放给本机逻辑）。
# ---------------------------------------------------------------------------
_JOB_STATES_FILE = "job_states.json"
_TOUCHES_FILE = "session_touches.json"
_TERMINAL_JOB_STATES = ("done", "failed", "cancelled")
_LIVE_JOB_STATES = ("submitted", "queued", "running", "unknown")
_EVIDENCE_MAX_AGE_H = 24.0    # 账本多久没刷新 / 多新的提交仍算「可能在跑」
_EVIDENCE_ABS_MAX_H = 168.0   # 兜底：7 天前的提交不再当活跃工作（轮询也不再重探）
_TOUCH_FRESH_H = 12.0         # 会话碰过集群多久之内算「在这个集群上干活」
_SESSION_LIVE_H = 72.0        # 常驻会话 status=active 且 updated 多久之内算活着
                              # （注册表的 updated 是「上次查询时间」不是心跳时间：
                              #   查得少 ≠ 死了，所以给足 3 天，宁可多保护也别误判死亡）
_POLL_MAX_AGE_H = 168.0       # 超过一周的未终态记录不再自动重探（省 ssh）
_POLL_MAX_NODES = 8
_MAX_TOUCHES = 50


def _supervision_dir() -> Path:
    base = _get_config_path().parent / "remote"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return base


def _read_json_file(path: Path, default):
    try:
        if not path.exists():
            return default
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning("监督台账 %s 读取失败（按无数据处理）: %s", path.name, exc)
        return default


def _write_json_atomic(path: Path, payload) -> bool:
    try:
        tmp = path.parent / (path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.warning("监督台账 %s 写入失败: %s", path.name, exc)
        return False


def _hours_since(stamp, now: float | None = None) -> float:
    """时间戳（epoch / '%Y-%m-%d %H:%M:%S' / ISO）距现在多少小时；解析不了 → 大数。"""
    if isinstance(stamp, (int, float)):
        return max(0.0, ((now or time.time()) - float(stamp)) / 3600.0)
    s = str(stamp or "").strip()
    if not s:
        return 1e9
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            t = time.mktime(time.strptime(s[:19], fmt))
            return max(0.0, ((now or time.time()) - t) / 3600.0)
        except Exception:
            continue
    return 1e9


def _current_agent_session() -> str:
    """当前 agent 会话 id（回合内调用才有；WebUI 直调可能拿不到 → 空串）。"""
    sid = ""
    try:
        from gateway.session_context import get_session_env
        sid = str(get_session_env("HERMES_SESSION_ID", "") or "")
    except Exception:
        sid = ""
    if not sid:
        sid = os.environ.get("HERMES_SESSION_ID") or os.environ.get("HERMES_SESSION_KEY") or ""
    return str(sid).strip()[:120]


def _normalize_job_state(raw: str) -> str:
    """_derive_state 的词表 → 监督用状态：queued|running|done|failed|cancelled|unknown。"""
    t = str(raw or "").strip().upper()
    if not t:
        return "unknown"
    if t.startswith("COMPLETED"):
        return "done"
    if t.startswith("CANCELLED") or t.startswith("CANCELED"):
        return "cancelled"
    for kw in ("FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "PREEMPTED", "ERROR"):
        if kw in t:
            return "failed"
    if t.startswith("PENDING") or t.startswith("CONFIGURING") or t.startswith("SUSPENDED"):
        return "queued"
    if t.startswith("RUNNING") or t.startswith("COMPLETING"):
        return "running"
    return "unknown"


def _job_key(node: str, job_id: str) -> str:
    return "%s|%s" % (str(node or "?"), str(job_id or "?"))


def touch_session(node: str = "", action: str = "", session_id: str = "") -> None:
    """记「某 agent 会话最近碰过集群」——归属证据；失败静默，绝不影响工具调用。"""
    try:
        sid = str(session_id or "").strip() or _current_agent_session()
        if not sid:
            return
        path = _supervision_dir() / _TOUCHES_FILE
        data = _read_json_file(path, {})
        touches = data.get("touches") if isinstance(data, dict) and isinstance(data.get("touches"), dict) else {}
        touches[sid] = {"at": _now(), "ts": time.time(),
                        "node": str(node or ""), "action": str(action or "")[:40]}
        if len(touches) > _MAX_TOUCHES:
            keep = sorted(touches, key=lambda k: (touches[k] or {}).get("ts") or 0)[-_MAX_TOUCHES:]
            touches = {k: touches[k] for k in keep}
        _write_json_atomic(path, {"version": 1, "touches": touches})
    except Exception as exc:
        logger.debug("记录集群触点失败（忽略）: %s", exc)


def _load_touches() -> dict:
    data = _read_json_file(_supervision_dir() / _TOUCHES_FILE, {})
    touches = data.get("touches") if isinstance(data, dict) and isinstance(data.get("touches"), dict) else {}
    return {str(k): v for k, v in touches.items() if isinstance(v, dict)}


def load_job_states() -> dict:
    """{'<node>|<job_id>': {...}} —— 轮询/status 落下的作业状态账本。"""
    data = _read_json_file(_supervision_dir() / _JOB_STATES_FILE, {})
    jobs = data.get("jobs") if isinstance(data, dict) and isinstance(data.get("jobs"), dict) else {}
    return {str(k): v for k, v in jobs.items() if isinstance(v, dict)}


def save_job_states(jobs: dict, last_poll: dict | None = None) -> bool:
    path = _supervision_dir() / _JOB_STATES_FILE
    old = _read_json_file(path, {})
    payload = {"version": 1, "jobs": jobs,
               "last_poll": last_poll if last_poll is not None
               else (old.get("last_poll") if isinstance(old, dict) else None)}
    return _write_json_atomic(path, payload)


def update_job_state(node: str, job_id: str, **fields) -> dict:
    """单条作业状态合并写（提交时先落一条 submitted；status 手查也会刷新它）。"""
    jobs = load_job_states()
    key = _job_key(node, job_id)
    entry = dict(jobs.get(key) or {})
    entry.update({"node": str(node or ""), "job_id": str(job_id or ""),
                  "updated": _now(), "ts": time.time()})
    entry.update(fields)
    jobs[key] = entry
    save_job_states(jobs)
    return entry


def _submitted_records(limit: int = 200) -> dict:
    """最新提交记录，按 '<node>|<job_id>' 去重（新记录覆盖旧记录）。"""
    out: dict = {}
    for rec in _iter_jobs(limit):
        jid = str(rec.get("job_id") or "").strip()
        if not jid:
            continue
        node = str(rec.get("node") or rec.get("host") or "")
        out[_job_key(node, jid)] = rec
    return out


def cluster_work_evidence(session_id: str = "", now: float | None = None) -> dict:
    """「这个会话在集群上还有活在跑吗」——纯本地读，绝不 ssh、绝不抛。

    两类证据：
      · 作业：有提交记录 且（账本状态 queued/running/unknown，或没轮询过但是 24h 内提交）
      · 常驻会话：sessions.json 里 status=active 且 updated 在 12h 内
    归属：记录带 session_id 就精确比；老记录没有 → 只有「本会话 12h 内碰过该节点」才算。
    返回 {live, reasons[], items[]}；方向性：宁枉勿纵（假 live 只多花唤醒预算，
    假 dead 会把还在跑的会话当已完成归档）。
    """
    now = float(now if now is not None else time.time())
    sid = str(session_id or "").strip()
    states = load_job_states()
    touches = _load_touches()
    touch = touches.get(sid) if sid else None
    my_nodes = set()
    if isinstance(touch, dict) and _hours_since(touch.get("ts") or touch.get("at"), now) <= _TOUCH_FRESH_H:
        node = str(touch.get("node") or "")
        if node:
            my_nodes.add(node)
    items: list = []
    for key, rec in _submitted_records().items():
        node = str(rec.get("node") or rec.get("host") or "")
        jid = str(rec.get("job_id") or "")
        st = states.get(key) or {}
        state = str(st.get("state") or "")
        age_h = _hours_since(rec.get("ts"), now)
        if state in _TERMINAL_JOB_STATES:
            continue
        checked_age_h = _hours_since(st.get("checked_at") or st.get("updated"), now)
        if state not in _LIVE_JOB_STATES and age_h > _EVIDENCE_MAX_AGE_H:
            continue
        if age_h > _EVIDENCE_ABS_MAX_H and checked_age_h > _EVIDENCE_MAX_AGE_H:
            continue
        rec_sid = str(rec.get("session_id") or st.get("session_id") or "")
        if rec_sid:
            if rec_sid != sid:
                continue
        elif not (node and node in my_nodes):
            continue
        items.append({"kind": "job", "key": key, "node": node, "job_id": jid,
                      "name": rec.get("name") or "", "state": state or "未轮询",
                      "session_id": rec_sid, "age_h": round(age_h, 1),
                      "checked_at": st.get("checked_at")})
    try:
        from memomics.bio_tools import cluster_session as _cs
        reg = _cs._load_registry()
    except Exception:
        reg = {}
    if isinstance(reg, dict):
        for rid, srec in reg.items():
            if not isinstance(srec, dict) or str(srec.get("status") or "") != "active":
                continue
            age_h = _hours_since(srec.get("updated") or srec.get("last_active"), now)
            if age_h > _SESSION_LIVE_H:
                continue
            node = str(srec.get("node") or "")
            rec_sid = str(srec.get("agent_session_id") or "")
            if rec_sid:
                if rec_sid != sid:
                    continue
            elif not (node and node in my_nodes):
                continue
            items.append({"kind": "session", "key": str(rid), "node": node, "job_id": "",
                          "name": srec.get("title") or "", "state": "active",
                          "session_id": rec_sid, "age_h": round(age_h, 1),
                          "checked_at": srec.get("updated")})
    reasons = []
    for it in items[:6]:
        if it["kind"] == "job":
            reasons.append("集群作业 %s@%s 状态=%s（%.1fh 前提交）"
                           % (it["job_id"], it["node"] or "?", it["state"], it["age_h"]))
        else:
            reasons.append("常驻 R 会话 %s@%s status=active（%.1fh 前有活动）"
                           % (it["key"], it["node"] or "?", it["age_h"]))
    return {"live": bool(items), "reasons": reasons, "items": items[:8]}


def _poll_backoff_sec(probe_count: int) -> float:
    """同一状态的重复探测退避：60 → 120 → 240 → 480 → 600s 封顶。

    状态一变就重置（下一次 60s），所以「快变期勤查、长期稳态省 ssh」两者兼得——
    与 skills 里「核对一次之后就不要再每轮重复同一条监控命令」同一条纪律。
    """
    try:
        n = max(0, int(probe_count))
    except Exception:
        n = 0
    if n <= 0:
        return 60.0
    return min(600.0, 60.0 * (2 ** min(n, 4)))


def poll_jobs(cfg: dict | None = None, limit: int = 20, force: bool = False) -> dict:
    """把未终态作业的远端状态查回来写进 job_states.json，返回本次状态转移。

    一次最多查 limit 个作业、最多 _POLL_MAX_NODES 个节点；某个节点连不上只记 errors
    继续下一台，绝不因为一台炸掉整轮。transitions 只含**状态发生变化**的作业——
    上层按它决定要不要唤醒会话（幂等：状态已落盘，下一轮不会重复报）。
    """
    cfg = cfg or _load_remote_config()
    if not remote_cluster_enabled():
        return {"ok": True, "checked": 0, "nodes": [], "transitions": [], "errors": [],
                "skipped": [], "note": "远端未启用（remote.enabled=false）"}
    states = load_job_states()
    groups: dict = {}
    skipped: list = []
    for key, rec in _submitted_records().items():
        st = states.get(key) or {}
        if str(st.get("state") or "") in _TERMINAL_JOB_STATES and not force:
            continue
        age_h = _hours_since(rec.get("ts"))
        if age_h > _POLL_MAX_AGE_H and not force:
            skipped.append(key)
            continue
        if not force:
            _last_ts = st.get("checked_ts") or 0
            try:
                _due = (time.time() - float(_last_ts)) >= _poll_backoff_sec(st.get("probe_count") or 0)
            except Exception:
                _due = True
            if _last_ts and not _due:
                skipped.append(key)
                continue
        node = str(rec.get("node") or rec.get("host") or "")
        groups.setdefault(node, []).append((key, rec))
    checked = 0
    transitions: list = []
    errors: list = []
    nodes_polled: list = []
    for node_name in sorted(groups, key=lambda n: -len(groups[n]))[:_POLL_MAX_NODES]:
        if checked >= limit:
            break
        recs = sorted(groups[node_name], key=lambda kv: str(kv[1].get("ts") or ""), reverse=True)
        node_cfg, found_name, err = _select_node(cfg, node_name)
        if err or not node_cfg:
            errors.append({"node": node_name, "error": "节点不可用（配置里找不到这个节点，或用 node= 指定）"})
            continue
        try:
            conn = _get_conn(node_cfg)
        except Exception as exc:
            errors.append({"node": node_name, "error": "%s: %s" % (type(exc).__name__, exc)})
            continue
        nodes_polled.append(found_name or node_name)
        for key, rec in recs:
            if checked >= limit:
                break
            jid = str(rec.get("job_id") or "")
            try:
                probe = _status_probe(conn, node_cfg, rec, jid, want_log_tail=False)
            except Exception as exc:
                errors.append({"node": found_name or node_name, "job_id": jid,
                               "error": "%s: %s" % (type(exc).__name__, exc)})
                continue
            checked += 1
            raw = str(probe.get("state") or "")
            new_state = _normalize_job_state(raw)
            old = states.get(key) or {}
            old_state = str(old.get("state") or "")
            entry = {
                "node": found_name or node_name, "job_id": jid, "name": rec.get("name"),
                "state": new_state, "state_raw": raw[:160], "scheduler": probe.get("scheduler"),
                "session_id": rec.get("session_id") or old.get("session_id") or "",
                "checked_at": _now(), "updated": _now(), "ts": time.time(),
                "stdout": probe.get("stdout") or rec.get("stdout") or "",
            }
            # 退避记账：状态一变就重置探测计数（下一轮 60s 后再查），稳态逐步放慢
            entry["checked_ts"] = time.time()
            try:
                entry["probe_count"] = 1 if old_state != new_state else (int(old.get("probe_count") or 0) + 1)
            except Exception:
                entry["probe_count"] = 1
            if new_state in _TERMINAL_JOB_STATES:
                entry["finished_at"] = entry["checked_at"]
            if old_state != new_state:
                transitions.append(dict(entry, **{"from": old_state or "submitted"}))
            states[key] = entry
    save_job_states(states, last_poll={"at": _now(), "ts": time.time(), "checked": checked,
                                       "nodes": nodes_polled, "transitions": len(transitions)})
    return {"ok": True, "checked": checked, "nodes": nodes_polled,
            "transitions": transitions, "errors": errors, "skipped": skipped[:10]}


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
    config_args = list(getattr(conn, "catalog_ssh_config_args", []) or [])
    extra_options = list(getattr(conn, "extra_options", []) or [])
    config_args, extra_options = _split_catalog_ssh_options(
        config_args + extra_options, host=getattr(conn, "host", ""), user=getattr(conn, "user", ""),
        port=getattr(conn, "port", 22), key=getattr(conn, "key_path", ""),
        require_managed=bool(getattr(conn, "catalog_v4_ssh_route", False)),
    )
    strict_host_keys = bool(config_args)
    cmd = ["scp", "-r", "-q"] + config_args
    if getattr(conn, "use_mux", False):
        cmd.extend(["-o", "ControlPath=%s" % conn.control_socket])
    cmd.extend([
           "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=%s" % ("yes" if strict_host_keys else "accept-new"),
           "-o", "ConnectTimeout=10"])
    if conn.port and conn.port != 22:
        cmd.extend(["-P", str(conn.port)])
    if conn.key_path:
        cmd.extend(["-i", conn.key_path])
    if extra_options:
        cmd.extend(extra_options)
    return cmd


def _scp_transfer(conn, local_path: str, remote_path: str, upload: bool) -> dict:
    """scp 传输；新版 scp 走 SFTP，若对端禁用 sftp-server 则退回传统 scp（-O）。"""
    v5 = bool(getattr(conn, "catalog_v5_ssh_route", False))
    if not v5:
        base = _scp_base(conn)
        scp_host = str(conn.host or "")
    last_err = ""
    for extra in ([], ["-O"]):
        # Each V5 native process must receive a fresh bounded-lifetime
        # ASKPASS mapping.  In particular, an SFTP fallback cannot reuse the
        # password map (or its credential revision) created for the failed
        # SFTP process.
        runtime = None
        if v5:
            base, runtime = conn._v5_scp_base()
            scp_host = str(runtime.target_alias)
        # scp remote-spec syntax uses ':' as the host/path separator, so a V4
        # literal IPv6 endpoint must be bracketed even though ssh itself
        # accepts the unbracketed HostName from our generated -F config.
        if ":" in scp_host and not (scp_host.startswith("[") and scp_host.endswith("]")):
            scp_host = "[%s]" % scp_host
        target = "%s@%s:%s" % (conn.user, scp_host, shlex.quote(remote_path))
        cmd = list(base) + extra
        if upload:
            cmd.extend([local_path, target])
        else:
            cmd.extend([target, local_path])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=max(conn.timeout, 120),
                                  stdin=subprocess.DEVNULL,
                                  env=runtime.env if runtime is not None else None)
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


# ---------------------------------------------------------------------------
# 铁规 10 硬闸（2026-10-08）：要读 ≥100MB 未标记大输入的 run/submit，先拦下
# ---------------------------------------------------------------------------
# 背景：铁规 10 写进 skill 后仍被同一 agent 当面跳过（662MB MuSC rds 无 scan/弹窗/标记
# 直接 submit）——规矩没接在执行路径上 = 没有规矩。本闸就是「违反了哪一步会拦住我」的答案：
# 命令文本里出现数据扩展名的远端绝对路径 → 批量 stat → ≥阈值且账本（large_cache
# cache_markers）里没有它的 active 远端标记 → 返回 status=needs_persist，拒绝执行。
# 纯巡检行（ls/stat/du/head... 开头）不触发——那是铁规 10 自己的查体积动作；
# large_cache.scan_remote 走 scan_only=True 内部通道，同理不触发。

_PERSIST_PATH_RE = re.compile(
    r"(/[A-Za-z0-9._~+@%/-]+\.(?:rds|rda|rdata|qs|h5ad|h5|hdf5|loom|zarr|mtx|"
    r"bam|cram|fastq|fq|parquet|feather|csv|tsv))", re.I)
_PERSIST_INSPECT_RE = re.compile(
    r"^\s*(ls|ll|stat|du|df|file|head|tail|which|echo|pwd|wc|qstat|squeue|qconf|"
    r"qhost|realpath|readlink|basename|dirname|test|\[)\b")


def _persist_gate_paths(command: str):
    """从命令文本抠「会被读的大输入候选」：数据扩展名的绝对路径。纯巡检行跳过。"""
    out = []
    for line in (command or "").splitlines():
        if _PERSIST_INSPECT_RE.match(line):
            continue
        for m in _PERSIST_PATH_RE.finditer(line):
            p = m.group(1)
            if p not in out:
                out.append(p)
    return out[:12]


def _persist_gate_decide(big, marked, node_name: str, min_mb: float):
    """纯判定（可离线单测）：大件 ∩ 账本 → None 放行 / needs_persist 载荷。"""
    unmarked = [b for b in big if b["path"] not in marked]
    if not unmarked:
        return None
    return {
        "status": "needs_persist",
        "node": node_name,
        "error": ("命令要读 %d 个 ≥%gMB 的远端大输入，但它们还没落任务标记（铁规 10）——"
                  "本次 run/submit 已被拦下，没有执行。" % (len(unmarked), min_mb)),
        "big_inputs": [{"path": b["path"], "size_h": "%.0fMB" % (b["size"] / 1048576.0)}
                       for b in unmarked],
        "flow": [
            "① 查体积：python -m memomics.bio_tools.large_cache scan --remote --node %s <路径...> --json"
            % (node_name or "<节点>"),
            "② 弹窗问用户：ask_user(kind=\"intent\") 要不要持久化（≥100MB 必须问，不许替用户答）",
            "③ 落标记：python -m memomics.bio_tools.large_cache mark --task-id <任务id> --title <标题> "
            "--input <路径> --remote（用户拒绝持久化也照落，加 --note 用户选择不持久化）",
            "④ 原样重发本次调用——账本里有标记就不再拦",
            "（另一条路）若用户想要的是「读一次、后面一直用」：直接 action='session_start', input=<路径> "
            "开常驻 R 会话——会话会自己落标记；之后 FindMarkers/CellChat/参数扫描都复用内存对象，不再回读文件。",
        ],
        "note": ("纯巡检命令（ls/stat/du/head 开头的行）不触发本闸；"
                 "config 里 persist_gate: false 可整闸关闭（不推荐）。"),
    }


def _persist_gate(cfg: dict, args: dict, command: str):
    """铁规 10 硬闸本体。返回 None=放行；否则返回 needs_persist 的 JSON 字符串。"""
    if not cfg.get("persist_gate", True):
        return None
    if _truthy(args.get("scan_only")):
        return None
    paths = _persist_gate_paths(command)
    if not paths:
        return None
    try:
        min_mb = float(cfg.get("persist_min_mb") or 100)
    except Exception:
        min_mb = 100.0
    conn = _get_conn(cfg)
    cmd = ("for p in " + " ".join(shlex.quote(p) for p in paths) + "; do "
           "[ -f \"$p\" ] && echo \"$(stat -c '%s' \"$p\" 2>/dev/null) $p\"; done")
    res = conn.execute(cmd, timeout=60)
    big = []
    for line in (res.get("output") or "").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) >= min_mb * 1048576:
            big.append({"path": parts[1].strip(), "size": int(parts[0])})
    if not big:
        return None
    try:
        from memomics.bio_tools import large_cache as _lc
        marked = _lc.marked_remote_paths()
    except Exception:
        marked = set()
    payload = _persist_gate_decide(big, marked, cfg.get("_name") or cfg.get("host") or "", min_mb)
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _action_run(cfg: dict, args: dict) -> str:
    command = (args.get("command") or "").strip()
    if not command:
        return _err("run 需要 command 参数")
    gate = _persist_gate(cfg, args, command)
    if gate:
        return gate
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
    gate = _persist_gate(cfg, args, command)
    if gate:
        return gate
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
        # rewrite_compound_background=False：memomics 的 execute() 默认会把 "A && B &"
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
        "ts": _now(), "node": cfg.get("_name") or "", "server_id": cfg.get("_name") or "",
        # Write a complete target snapshot.  Later server edits/removal must
        # not change where status/logs/cancel reconnect, including the port,
        # identity path and ProxyJump options.
        **_connection_snapshot(cfg),
        "connection_snapshot_version": 1,
        "scheduler": sched, "job_id": job_id, "name": name,
        "script": script_remote, "stdout": out_log, "stderr": err_log,
        "workdir": workdir, "command": command[:4000], "pid_file": pid_file,
        # WebUI console requests carry the durable chat id explicitly; agent
        # calls use the propagated ContextVar.  Preserve either so later
        # same-scheduler-id lookups can disambiguate by owning chat.
        "session_id": str(args.get("chat_session_id") or _current_agent_session() or ""),
    }
    _record_job(record)
    # 立刻落一条 submitted 到监督账本：即使本机还没轮询过，证据也能精确归属到会话
    try:
        update_job_state(record["node"], job_id, state="submitted", source="submit",
                         name=name, scheduler=sched, session_id=record["session_id"],
                         stdout=out_log, checked_at=_now())
    except Exception:
        pass
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


def _status_command(sched: str, job_id: str, rec, cfg: dict) -> str:
    """拼 status 探测命令（status / poll_jobs 共用；不在这里执行）。"""
    if sched == "slurm":
        qid = shlex.quote(job_id)
        return ("echo '== squeue =='; squeue -j %s -h -o '%%T %%M %%R' 2>&1; "
                "echo '== scontrol =='; (scontrol show job %s 2>&1 "
                "| grep -E 'JobState|RunTime|ExitCode' | head -5); "
                "echo '== sacct =='; (sacct -j %s --format=JobID,State,Elapsed,ExitCode -P -n 2>&1 | head -5)"
                % (qid, qid, qid))
    if sched == "gridengine":
        qid = shlex.quote(job_id)
        # GE 两段式：在队列里（qstat 列表抓 state 列）；已离队（qacct 记账拿 exit_status）
        return ("echo '== qstat =='; "
                "(qstat -u \"$USER\" 2>&1 | awk -v id=%s '$1==id {print \"state=\"$5\" queue=\"$8}'); "
                "qstat -j %s 2>&1 | head -2; "
                "echo '== qacct =='; (qacct -j %s 2>&1 | grep -E '^(exit_status|failed|end_time)' | head -5)"
                % (qid, qid, qid))
    if sched == "pbs":
        return ("echo '== qstat =='; (qstat -f %s 2>&1 | grep -E 'job_state|exec_host|resources_used' "
                "|| qstat -x %s 2>&1 | grep -E 'job_state' || echo 'not in queue')"
                % (shlex.quote(job_id), shlex.quote(job_id)))
    pid_file = str((rec or {}).get("pid_file") or "")
    if pid_file:
        return ("pidf=%s; if [ -f \"$pidf\" ]; then p=$(cat \"$pidf\"); "
                "if kill -0 \"$p\" 2>/dev/null; then echo \"STATE=RUNNING pid=$p\"; "
                "else echo \"STATE=NOT_RUNNING pid=$p\"; fi; "
                "else echo 'STATE=UNKNOWN 没有 pid 文件'; fi; "
                "ps -p %s -o pid=,etime=,stat=,cmd= 2>/dev/null || true"
                % (shlex.quote(pid_file), shlex.quote(job_id)))
    return ("ps -p %s -o pid=,etime=,stat=,cmd= 2>/dev/null || echo 'not running'"
            % shlex.quote(job_id))


def _status_probe(conn, cfg: dict, rec, job_id: str, want_log_tail: bool = True) -> dict:
    """跑一次作业状态探测（status / poll_jobs 共用）。

    返回 {scheduler,state,output,stdout,stderr}；scheduler=auto 时按节点探测一次。
    want_log_tail=False 时不带日志尾巴（轮询只关心状态，省流量）。
    """
    sched = ((rec or {}).get("scheduler")
             or (cfg["scheduler"] if cfg["scheduler"] in ("slurm", "pbs", "gridengine", "none") else "auto"))
    if sched == "auto":
        sched, _ = _detect_scheduler(conn, cfg)
    cmd = _status_command(sched, job_id, rec, cfg)
    out_path = err_path = ""
    if rec and rec.get("stdout"):
        out_path = _expand_job_pattern(str(rec["stdout"]), job_id,
                                       str(rec.get("name") or ""), cfg["user"])
        err_path = _expand_job_pattern(str(rec.get("stderr") or ""), job_id,
                                       str(rec.get("name") or ""), cfg["user"])
        if want_log_tail:
            cmd += "\necho '== log tail =='; tail -n 15 %s 2>/dev/null || echo '(no log yet)'" % shlex.quote(out_path)
    res = conn.execute(cmd, timeout=max(cfg["timeout"], 120))
    output = (res.get("output") or "").strip()
    return {"scheduler": sched, "state": _derive_state(sched, output), "output": output,
            "stdout": out_path or (rec or {}).get("stdout") or "",
            "stderr": err_path or (rec or {}).get("stderr") or ""}


def _action_status(cfg: dict, args: dict) -> str:
    job_id = str(args.get("job_id") or "").strip()
    rec = _selected_job_record(args, cfg, job_id) or (_find_job(cfg, job_id) if job_id else None)
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
    probe = _status_probe(conn, cfg, rec, job_id)
    # 手查也顺手刷新监督账本（P1 轮询看的就是它，越查越准）
    try:
        update_job_state(cfg.get("_name") or "", job_id,
                         state=_normalize_job_state(probe["state"]),
                         state_raw=str(probe["state"])[:160],
                         scheduler=probe["scheduler"], checked_at=_now(),
                         name=(rec or {}).get("name"),
                         session_id=(rec or {}).get("session_id") or "")
    except Exception:
        pass
    return _ok({
        "job_id": job_id, "scheduler": probe["scheduler"], "name": (rec or {}).get("name"),
        "node": cfg.get("_name") or "", "host": cfg["host"],
        "state": probe["state"],
        **({"note": "未指定 job_id，用的是最近一次提交"} if assumed else {}),
        **({"cross_node_note": cross_note} if cross_note else {}),
        "stdout": probe["stdout"] or (rec or {}).get("stdout"),
        "stderr": probe["stderr"] or (rec or {}).get("stderr"),
        "output": _truncate(probe["output"], cfg["max_output_chars"]),
    })


def _action_logs(cfg: dict, args: dict) -> str:
    lines = int(args.get("lines") or 100)
    job_id = str(args.get("job_id") or "").strip()
    path = (args.get("path") or "").strip()
    rec = _selected_job_record(args, cfg, job_id) or (_find_job(cfg, job_id) if job_id else None)
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
    rec = _selected_job_record(args, cfg, job_id) or _find_job(cfg, job_id)
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
    """调 environment.execute()：老版本 memomics 的 BaseEnvironment 不认 bounded_capture，自动降级。

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


# 远端展开通配符用的 python 一句话：**必须 py2/py3 双兼容**。
# 实测踩坑（2026-10-09，node4）：节点上只有 /usr/bin/python = Python 2.7.5，没有 python3；
# 原来的 `[print(...) for p in ps]` 在 py2 里是语法错误（print 是语句），整条 pull/locate 通配符
# 直接报 SyntaxError「远端没找到」。所以：不用 print()、不用 f-string，只留两边都合法的写法。
_REMOTE_GLOB_PY = ('import glob,sys,os;ps=[];'
                   '[ps.extend(glob.glob(p)) for p in sys.argv[1:]];'
                   'ps=sorted(set(ps))[:50];'
                   'sys.stdout.write("\\n".join([("D" if os.path.isdir(p) else "F")+":"+'
                   'str(os.path.getsize(p) if os.path.isfile(p) else 0)+":"+p for p in ps]))')


def _locate_remote_glob(conn, cands: list, out: dict) -> dict:
    """远端通配符：借节点上的 python 展开（shell 里带引号的 glob 不会自己展开）。

    先试 python3 再退 python —— 有些节点（node4）只有 Python 2.7.5，所以脚本本身要 py2 也能跑。
    """
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
    seen = []
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


_CATALOG_KNOWN_HOSTS_LOCK = threading.RLock()
_CATALOG_APPLICATION_KEY_LOCK = threading.RLock()
_CATALOG_SSH_CONFIG_LOCK = threading.RLock()
_CATALOG_MANAGED_STORE_LOCK = threading.RLock()

# Persisted with V4 catalog profiles and every durable connection snapshot.
# It is intentionally distinct from ``connection_profile``: older API-managed
# profiles can still carry user-owned legacy ``-F`` options, whereas this
# exact value means their route must prove the app-owned V4 policy at every
# SSH argv boundary.
CATALOG_V4_SSH_ROUTE_MARKER = "v4-managed-route-1"
CATALOG_V5_SSH_ROUTE_MARKER = _password_ssh.PASSWORD_ROUTE_MARKER
CATALOG_V5_PASSWORD_AUTH_MODE = _password_ssh.PASSWORD_AUTH_MODE


def catalog_v4_ssh_route_required(value) -> bool:
    """Return whether a profile/snapshot must carry a verified V4 ``-F``.

    An omitted marker is the sole legacy compatibility case.  A non-empty
    value that is not the exact marker is persistent provenance corruption,
    not a reason to weaken the route to a user-owned legacy ``-F`` config.
    """
    if value is None or value == "":
        return False
    if value == CATALOG_V4_SSH_ROUTE_MARKER:
        return True
    raise RuntimeError("catalog V4 SSH route provenance is invalid")


def catalog_v4_route_required(value) -> bool:
    """Validate the normalized boolean marker stored by local job ledgers.

    ``catalog_v4_route`` is internal data written as a real boolean after the
    public ``catalog_v4_ssh_route`` marker has been checked.  Accept only that
    exact shape so a tampered string cannot be coerced through ``bool(value)``
    into an unrelated execution policy.
    """
    if value is True:
        return True
    if value is False or value is None or value == "":
        return False
    raise RuntimeError("catalog V4 SSH route provenance is invalid")


def catalog_v5_ssh_route_required(value) -> bool:
    """Return whether a profile must use the V5 Credential-Manager route."""
    if value is None or value == "":
        return False
    if value == CATALOG_V5_SSH_ROUTE_MARKER:
        return True
    raise RuntimeError("catalog V5 SSH route provenance is invalid")


def catalog_v5_route_required(value) -> bool:
    """Validate the normalized V5 boolean used by durable job snapshots."""
    if value is True:
        return True
    if value is False or value is None or value == "":
        return False
    raise RuntimeError("catalog V5 SSH route provenance is invalid")


def catalog_v5_password_profile(cfg: dict) -> bool:
    """Recognize only a complete, explicitly marked V5 password profile.

    A partial/new-looking record is corruption, never a reason to fall back
    to an old ``key`` field.  Profiles without the V5 marker remain historical
    key-route compatibility records until they are deliberately rematched.
    """
    if not isinstance(cfg, dict):
        return False
    marked = catalog_v5_ssh_route_required(cfg.get("catalog_v5_ssh_route"))
    mode = cfg.get("auth_mode")
    if not marked and mode in (None, "", "legacy_key"):
        return False
    if not marked or mode != CATALOG_V5_PASSWORD_AUTH_MODE:
        raise RuntimeError("catalog V5 password profile provenance is invalid")
    # Validate the opaque identifiers now; runtime mapping is allowed only
    # after this exact profile shape is proved.
    if not _password_ssh.is_password_profile(cfg):
        raise RuntimeError("catalog V5 password profile provenance is invalid")
    if not str(cfg.get("catalog_account_id") or ""):
        raise RuntimeError("catalog V5 password account is unavailable")
    return True


class _CatalogHostKeyChangedError(RuntimeError):
    """A catalog TOFU entry exists but disagrees with a newly observed key."""


class _CatalogHostKeyStoreError(RuntimeError):
    """The app-owned catalog host-key store cannot be used safely."""


class _CatalogManagedStorePermissionError(RuntimeError):
    """The V4-managed SSH artifact store cannot be permission-hardened."""


def _catalog_known_hosts_path() -> Path:
    """Dedicated TOFU store for V4 catalog matching (never a credential)."""
    # Keep this a flat, app-owned file beside config.yaml.  It must outlive an
    # individual profile: historical job/R snapshots may still need its
    # verified host identity after that profile is deleted.
    return _catalog_managed_store_dir() / "known_hosts"


def _catalog_application_key_path() -> Path:
    """Return the one V4-managed identity path without consulting user ~/.ssh.

    This is deliberately a flat file in the existing application home.  The
    catalog must never scan or silently adopt arbitrary operator identities:
    an explicit key path remains supported, while password bootstrap may
    create this single app-owned ed25519 identity.
    """
    return _catalog_managed_store_dir() / "id_ed25519"


def _catalog_route_config_dir() -> Path:
    """App-owned, durable flat home for content-addressed V4 OpenSSH configs."""
    return _catalog_managed_store_dir()


def _catalog_managed_store_dir() -> Path:
    """Return the one V4-controlled directory beneath the existing app home."""
    return _get_config_path().parent / ".memomics-catalog-v4"


def _catalog_is_reparse_or_symlink(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.stat(), "st_file_attributes", 0)
        return bool(attributes & 0x0400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except OSError:
        return True


def _catalog_windows_current_sid() -> str:
    """Look up the current Windows SID using argv-only system tooling."""
    try:
        proc = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True,
            text=True, timeout=10, stdin=subprocess.DEVNULL,
        )
    except Exception as exc:
        raise _CatalogManagedStorePermissionError("catalog security identity unavailable") from exc
    match = re.search(r"S-\d+(?:-\d+)+", (proc.stdout or "")) if proc.returncode == 0 else None
    if not match:
        raise _CatalogManagedStorePermissionError("catalog security identity unavailable")
    return match.group(0)


def _catalog_set_windows_dacl(path: Path, sddl: str) -> None:
    """Set an exact protected DACL through Win32, without a shell command."""
    try:
        import ctypes
        from ctypes import wintypes
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD),
        ]
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
        advapi32.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
        advapi32.SetFileSecurityW.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        descriptor = ctypes.c_void_p()
        if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                str(sddl), 1, ctypes.byref(descriptor), None):
            raise OSError(ctypes.get_last_error(), "ConvertStringSecurityDescriptorToSecurityDescriptorW")
        try:
            # DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION.
            # Ownership is deliberately left untouched; the current user only
            # needs an exact non-inherited ACL on this app-owned object.
            if not advapi32.SetFileSecurityW(str(path), wintypes.DWORD(0x80000004), descriptor):
                raise OSError(ctypes.get_last_error(), "SetFileSecurityW")
        finally:
            kernel32.LocalFree(descriptor)
    except _CatalogManagedStorePermissionError:
        raise
    except Exception as exc:
        raise _CatalogManagedStorePermissionError("catalog security permissions unavailable") from exc


def _catalog_windows_sddl(path: Path) -> str:
    """Read the DACL SDDL for exact post-write verification."""
    try:
        import ctypes
        from ctypes import wintypes
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi32.GetNamedSecurityInfoW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
        advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(wintypes.DWORD),
        ]
        advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        descriptor = ctypes.c_void_p()
        # GetNamedSecurityInfoW returns Win32 ERROR_* instead of BOOL.
        status = advapi32.GetNamedSecurityInfoW(
            str(path), wintypes.DWORD(1), wintypes.DWORD(0x00000004),
            None, None, None, None, ctypes.byref(descriptor),
        )
        if status != 0:
            raise OSError(int(status), "GetNamedSecurityInfoW")
        try:
            rendered = ctypes.c_wchar_p()
            size = wintypes.DWORD()
            if not advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                    descriptor, 1, wintypes.DWORD(0x00000004), ctypes.byref(rendered), ctypes.byref(size)):
                raise OSError(ctypes.get_last_error(), "ConvertSecurityDescriptorToStringSecurityDescriptorW")
            try:
                return str(rendered.value or "")
            finally:
                kernel32.LocalFree(ctypes.cast(rendered, ctypes.c_void_p))
        finally:
            kernel32.LocalFree(descriptor)
    except _CatalogManagedStorePermissionError:
        raise
    except Exception as exc:
        raise _CatalogManagedStorePermissionError("catalog security permissions unavailable") from exc


def _catalog_windows_canonical_sid(value: str) -> str:
    """Resolve an SDDL trustee token to its concrete numeric Windows SID.

    ``GetNamedSecurityInfoW`` may render the current local Administrator as
    ``LA`` rather than the numeric SID returned by ``whoami /user``.  Compare
    resolved SIDs, not textual aliases: accepting ``LA`` by name would grant a
    different local Administrator account access when its SID is not the
    current process identity.
    """
    token = str(value or "").strip()
    if not token:
        raise _CatalogManagedStorePermissionError("catalog security permissions unavailable")
    try:
        import ctypes
        from ctypes import wintypes
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi32.ConvertStringSidToSidW.argtypes = [
            wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
        advapi32.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p),
        ]
        advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        binary_sid = ctypes.c_void_p()
        if not advapi32.ConvertStringSidToSidW(token, ctypes.byref(binary_sid)):
            raise OSError(ctypes.get_last_error(), "ConvertStringSidToSidW")
        try:
            rendered = ctypes.c_wchar_p()
            if not advapi32.ConvertSidToStringSidW(binary_sid, ctypes.byref(rendered)):
                raise OSError(ctypes.get_last_error(), "ConvertSidToStringSidW")
            try:
                canonical = str(rendered.value or "").strip()
            finally:
                kernel32.LocalFree(ctypes.cast(rendered, ctypes.c_void_p))
        finally:
            kernel32.LocalFree(binary_sid)
        if not re.fullmatch(r"S-\d+(?:-\d+)+", canonical, flags=re.IGNORECASE):
            raise _CatalogManagedStorePermissionError("catalog security permissions unavailable")
        return canonical.upper()
    except _CatalogManagedStorePermissionError:
        raise
    except Exception as exc:
        raise _CatalogManagedStorePermissionError("catalog security permissions unavailable") from exc


def _catalog_assert_windows_acl(actual: str, sid: str, *, directory: bool) -> None:
    """Reject any DACL that differs from the protected managed-file whitelist."""
    # SDDL may omit owner/group when we requested only DACL, so avoid relying
    # on their presentation.  Everything after D: is the requested DACL.
    dacl = actual.split("D:", 1)[1] if "D:" in actual else ""
    if not dacl.startswith("P"):
        raise _CatalogManagedStorePermissionError("catalog security permissions unavailable")
    aces = re.findall(r"\(([^()]*)\)", dacl)
    expected_trustees = [
        _catalog_windows_canonical_sid(sid),
        _catalog_windows_canonical_sid("SY"),
        _catalog_windows_canonical_sid("BA"),
    ]
    if len(aces) != 3:
        raise _CatalogManagedStorePermissionError("catalog security permissions unavailable")
    seen = []
    for ace in aces:
        fields = ace.split(";")
        if len(fields) != 6 or fields[0] != "A" or fields[2] != "FA":
            raise _CatalogManagedStorePermissionError("catalog security permissions unavailable")
        if directory:
            if fields[1] != "OICI":
                raise _CatalogManagedStorePermissionError("catalog security permissions unavailable")
        elif fields[1] != "":
            raise _CatalogManagedStorePermissionError("catalog security permissions unavailable")
        trustee = _catalog_windows_canonical_sid(fields[5])
        if trustee not in expected_trustees:
            raise _CatalogManagedStorePermissionError("catalog security permissions unavailable")
        seen.append(trustee)
    if sorted(seen) != sorted(expected_trustees):
        raise _CatalogManagedStorePermissionError("catalog security permissions unavailable")


def _catalog_verify_windows_acl(path: Path, *, directory: bool) -> None:
    """Read and verify, but never repair, a managed object's DACL."""
    sid = _catalog_windows_current_sid()
    _catalog_assert_windows_acl(_catalog_windows_sddl(path), sid, directory=directory)


def _catalog_harden_windows_acl(path: Path, *, directory: bool) -> None:
    """Replace—not merge—the managed object's DACL, then verify its whitelist."""
    sid = _catalog_windows_current_sid()
    inherit = "OICI" if directory else ""
    sddl = "D:P(A;%s;FA;;;%s)(A;%s;FA;;;SY)(A;%s;FA;;;BA)" % (
        inherit, sid, inherit, inherit,
    )
    _catalog_set_windows_dacl(path, sddl)
    _catalog_verify_windows_acl(path, directory=directory)


def _catalog_harden_managed_path(path: Path, *, directory: bool) -> None:
    """Harden only the V4-owned store and its artifacts, never user key files."""
    if _catalog_is_reparse_or_symlink(path):
        raise _CatalogManagedStorePermissionError("catalog security path is invalid")
    try:
        if os.name == "nt":
            _catalog_harden_windows_acl(path, directory=directory)
        else:
            os.chmod(path, 0o700 if directory else 0o600)
    except _CatalogManagedStorePermissionError:
        raise
    except OSError as exc:
        raise _CatalogManagedStorePermissionError("catalog security permissions unavailable") from exc


def _catalog_verify_managed_path(path: Path, *, directory: bool) -> None:
    """Fail closed when an existing managed artifact's current ACL/mode drifts.

    This is deliberately verification-only.  Re-applying a safe DACL at an
    execution boundary would make a previously replaceable known-host pin or
    app-owned key appear trustworthy after the fact.  Creation and atomic
    replacement use ``_catalog_harden_managed_path`` instead.
    """
    if _catalog_is_reparse_or_symlink(path):
        raise _CatalogManagedStorePermissionError("catalog security path is invalid")
    try:
        if directory:
            if not path.is_dir():
                raise _CatalogManagedStorePermissionError("catalog security path is invalid")
        elif not path.is_file():
            raise _CatalogManagedStorePermissionError("catalog security path is invalid")
        if os.name == "nt":
            _catalog_verify_windows_acl(path, directory=directory)
        else:
            expected_mode = 0o700 if directory else 0o600
            if stat.S_IMODE(path.stat().st_mode) != expected_mode:
                raise _CatalogManagedStorePermissionError("catalog security permissions unavailable")
    except _CatalogManagedStorePermissionError:
        raise
    except OSError as exc:
        raise _CatalogManagedStorePermissionError("catalog security permissions unavailable") from exc


def _catalog_ensure_managed_store() -> Path:
    """Create a new managed store or strictly verify an existing one.

    Repairing an existing root at this point would erase evidence that another
    identity could have replaced a child pin/key before normal execution.
    """
    root = _catalog_managed_store_dir()
    home = root.parent
    with _CATALOG_MANAGED_STORE_LOCK:
        if not home.is_dir() or _catalog_is_reparse_or_symlink(home):
            raise _CatalogManagedStorePermissionError("catalog security home is unavailable")
        if root.exists() and not root.is_dir():
            raise _CatalogManagedStorePermissionError("catalog security store is invalid")
        created = not root.exists()
        try:
            if created:
                root.mkdir(mode=0o700, parents=False, exist_ok=False)
        except OSError as exc:
            raise _CatalogManagedStorePermissionError("catalog security store is unavailable") from exc
        if created:
            _catalog_harden_managed_path(root, directory=True)
        else:
            _catalog_verify_managed_path(root, directory=True)
    return root


def _catalog_v5_staged_askpass_helper() -> Path:
    """Return the only helper a V5 password route may execute.

    The release-tree helper is merely an immutable byte source.  At the
    execution boundary, stage its reviewed bytes into the already protected
    catalog store and verify the staged file's exact DACL and hash before
    returning it for ``SSH_ASKPASS``.  This deliberately happens only during
    a V5 runtime request, never during code deployment or startup.
    """
    with _CATALOG_MANAGED_STORE_LOCK:
        root = _catalog_ensure_managed_store()
        return _askpass_security.stage_verified_askpass_helper(
            root,
            harden_managed_path=_catalog_harden_managed_path,
            verify_managed_path=_catalog_verify_managed_path,
            expected_sha256=_password_ssh.ASKPASS_HELPER_SHA256,
        )


def _known_host_lookup_names(host, port) -> list[str]:
    host = str(host or "").strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        port = int(port or 22)
    except Exception:
        port = 22
    # OpenSSH/Paramiko host-key stores scope non-default SSH ports as
    # ``[host]:port``.  Falling back to a bare host here would make a pin for
    # port 22 incorrectly block first-use bootstrap on (say) port 2222.
    if port != 22:
        return ["[%s]:%d" % (host, port)]
    return [host]


def _configure_catalog_host_key_policy(client, paramiko, host, port, known_hosts_path):
    """Load an endpoint-scoped TOFU record before auth; save first sightings.

    A known endpoint uses RejectPolicy, so a changed host key is rejected
    before a password can be sent.  An unseen endpoint uses the normal TOFU
    AutoAddPolicy and is persisted immediately, including an auth failure
    after its SSH handshake, to prevent an identity swap between a key attempt
    and the subsequent one-time password attempt.
    """
    if not known_hosts_path:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return None
    path = Path(known_hosts_path)
    # config.yaml's parent is the existing MemOmics home.  Do not create a
    # user ~/.ssh directory or a new task/work folder as a side effect.
    try:
        managed_root = _catalog_managed_store_dir()
        _catalog_verify_managed_path(managed_root, directory=True)
        if path.parent.resolve() != managed_root.resolve():
            raise _CatalogHostKeyStoreError("catalog host-key store is unavailable")
        # Existing pins are trust material.  Verify their current exact ACL
        # before loading; never repair an unexpected ACL and then trust bytes
        # that could have been replaced while it was writable.
        if path.exists() or path.is_symlink():
            _catalog_verify_managed_path(path, directory=False)
    except _CatalogManagedStorePermissionError:
        raise
    except _CatalogHostKeyStoreError:
        raise
    except Exception as exc:
        raise _CatalogHostKeyStoreError("catalog host-key store is unavailable") from exc
    try:
        if path.exists() and path.stat().st_size:
            client.load_host_keys(str(path))
    except Exception as exc:
        raise _CatalogHostKeyStoreError("catalog host-key store is unavailable") from exc
    known = False
    try:
        keys = client.get_host_keys()
        known = any(bool(keys.lookup(name)) for name in _known_host_lookup_names(host, port))
    except Exception:
        known = False
    client.set_missing_host_key_policy(paramiko.RejectPolicy() if known else paramiko.AutoAddPolicy())
    return path


def _save_catalog_host_keys(client, paramiko, path) -> None:
    if path is None:
        return
    try:
        path = Path(path)
        managed_root = _catalog_managed_store_dir()
        _catalog_verify_managed_path(managed_root, directory=True)
        if path.parent.resolve() != managed_root.resolve():
            raise _CatalogHostKeyStoreError("catalog host-key store is unavailable")
        if path.exists() or path.is_symlink():
            _catalog_verify_managed_path(path, directory=False)
        # Merge the just-observed key into the latest on-disk set while the
        # global lock is held.  A direct ``save_host_keys`` would overwrite a
        # concurrently learned different endpoint and could turn a same-host
        # first-seen race into last-writer-wins trust.
        HostKeys = getattr(paramiko, "HostKeys", None)
        if HostKeys is None or not hasattr(client, "get_host_keys"):
            # Falling back to ``save_host_keys`` is unsafe: it can overwrite a
            # different endpoint learned by another request between load and
            # save.  Real Paramiko exposes HostKeys; reject unsupported stubs
            # rather than weakening the V4 trust guarantee.
            raise _CatalogHostKeyStoreError("catalog host-key store is unavailable")
        merged = HostKeys()
        if path.exists() and path.stat().st_size:
            merged.load(str(path))
        observed = client.get_host_keys()
        for hostname, key_types in observed.items():
            existing = merged.lookup(hostname)
            for key_type, key in key_types.items():
                if existing and key_type in existing and existing[key_type] != key:
                    raise _CatalogHostKeyChangedError("catalog host key changed")
                merged.add(hostname, key_type, key)
        fd, tmp_name = tempfile.mkstemp(prefix=".%s." % path.name, suffix=".tmp", dir=str(path.parent))
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            merged.save(str(tmp))
            # ``HostKeys.save`` owns its own file handle.  Re-open and sync
            # its completed bytes before the atomic replacement so a sudden
            # process/host failure cannot acknowledge a first-seen key that
            # was only resident in the filesystem cache.  If the sync fails,
            # keep the previous non-empty store intact and abort this
            # connection attempt rather than allowing the password fallback
            # to TOFU a second identity.
            # Win32 FlushFileBuffers (used by ``os.fsync``) requires a handle
            # opened with write access; ``rb`` works on POSIX but rejects the
            # same temporary file on Windows.
            with open(tmp, "r+b") as sync_fh:
                os.fsync(sync_fh.fileno())
            os.replace(tmp, path)
            _catalog_harden_managed_path(path, directory=False)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
    except _CatalogHostKeyChangedError:
        raise
    except _CatalogManagedStorePermissionError:
        raise
    except _CatalogHostKeyStoreError:
        raise
    except Exception as exc:
        raise _CatalogHostKeyStoreError("catalog host-key store is unavailable") from exc


def _p_connect(paramiko, host, port, user, password, key_path, sock_factory=None, *, known_hosts_path=None):
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
        # The trust decision, SSH handshake, and first durable save must be a
        # single critical section.  This intentionally serializes catalogue
        # bootstrap attempts (not normal remote execution) so two requests
        # cannot accept different first keys for one endpoint or lose a key
        # for another endpoint during a read/modify/write save.
        lock = _CATALOG_KNOWN_HOSTS_LOCK if known_hosts_path else None
        if lock is not None:
            lock.acquire()
        try:
            client = paramiko.SSHClient()
            catalog_host_store = _configure_catalog_host_key_policy(
                client, paramiko, host, port, known_hosts_path,
            )
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
            except Exception as exc:  # noqa: BLE001 — 认证失败换下一方式; see caller's safe mapping
                last_exc = exc
                # For a first-seen V4 endpoint, AutoAddPolicy has already
                # observed the SSH host key before authentication can fail.
                # Persist it before considering a password retry.  A storage
                # failure is terminal: otherwise a second attempt would be a
                # fresh TOFU decision and could accept a different key.
                try:
                    _save_catalog_host_keys(client, paramiko, catalog_host_store)
                except Exception as store_exc:
                    try:
                        client.close()
                    except Exception:
                        pass
                    raise store_exc from exc
                try:
                    client.close()
                except Exception:
                    pass
                continue
            try:
                _save_catalog_host_keys(client, paramiko, catalog_host_store)
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass
                raise
            return client, mode
        finally:
            if lock is not None:
                lock.release()
    raise last_exc or RuntimeError("没有可用的认证方式（既没找到密钥文件也没给密码）")


def _p_exec(client, cmd, timeout=30):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err_out = stderr.read().decode("utf-8", "replace")
    return out, err_out


# ---------------------------------------------------------------------------
# V4 catalog matching probe
# ---------------------------------------------------------------------------
#
# A catalog connection is deliberately tested before it is written into
# ``remote.nodes``.  The catalog owns the server/node/account records; this
# module receives only a fully composed, short-lived candidate configuration.
# Do not make this a second SSH implementation: the last validation step below
# calls the existing ``_action_nodes`` / ClusterSSH BatchMode engine that all
# normal cluster work uses.

_CATALOG_PROBE_NODE = "catalog-probe"
_CATALOG_SAFE_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_CATALOG_SAFE_USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _catalog_probe_result(ok: bool, stage: str, code: str, message: str, **extra) -> dict:
    """Return the small, UI-safe V4 matching result shape.

    In particular, this intentionally never carries an exception object, a
    password, a private-key path, a public-key line, raw SSH output, or a
    Paramiko/openssl diagnostic.  Those values can leak credentials or local
    infrastructure details and are not useful instructions for the UI.
    """
    result = {"ok": bool(ok), "stage": str(stage), "code": str(code), "message": str(message)}
    result.update({key: value for key, value in extra.items() if value is not None})
    return result


def _catalog_safe_text(value, field: str, *, required: bool = False, maximum: int = 1024) -> str:
    text = "" if value is None else str(value).strip()
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise ValueError("%s contains control characters" % field)
    if required and not text:
        raise ValueError("%s is required" % field)
    if len(text) > maximum:
        raise ValueError("%s is too long" % field)
    return text


def _catalog_network_host(value, field: str = "host") -> str:
    """Validate catalog host syntax and return an unbracketed network host.

    The V4 catalog accepts DNS names, IPv4, IPv6, and bracketed IPv6.  Socket
    and Paramiko calls need the literal IPv6 address without brackets; the
    ProxyJump/config serializers add brackets back only where SSH syntax needs
    them.
    """
    host = _catalog_safe_text(value, field, required=True, maximum=253)
    if any(ch.isspace() for ch in host) or any(ch in host for ch in "@/\\"):
        raise ValueError("%s is invalid" % field)
    if host.startswith("[") != host.endswith("]"):
        raise ValueError("%s is invalid" % field)
    literal = host[1:-1] if host.startswith("[") else host
    try:
        return str(ipaddress.ip_address(literal))
    except ValueError:
        if not _CATALOG_SAFE_HOST_RE.fullmatch(host) or ".." in host:
            raise ValueError("%s is invalid" % field)
        return host


def _catalog_safe_port(value, field: str = "port") -> int:
    try:
        port = int(str(value).strip())
    except Exception as exc:
        raise ValueError("%s must be a number" % field) from exc
    if not 1 <= port <= 65535:
        raise ValueError("%s must be between 1 and 65535" % field)
    return port


def _catalog_safe_timeout(value) -> int:
    try:
        timeout = int(str(value if value is not None else 30).strip())
    except Exception as exc:
        raise ValueError("timeout must be a number") from exc
    if not 1 <= timeout <= 7200:
        raise ValueError("timeout must be between 1 and 7200")
    return timeout


def _catalog_key_path(value, *, required: bool = True) -> str:
    """Validate a supplied V4 identity path without falling back to user SSH.

    The catalog may use an explicit key, or its one app-owned key.  It never
    scans ``~/.ssh`` or asks OpenSSH to pick an arbitrary user identity.
    """
    raw = _catalog_safe_text(value, "key_path", required=required, maximum=2048)
    if not raw:
        return ""
    path = os.path.expanduser(raw)
    if not os.path.isfile(path):
        raise FileNotFoundError("application key file is unavailable")
    try:
        if os.path.getsize(path) <= 0:
            raise OSError("empty key")
    except OSError as exc:
        raise FileNotFoundError("application key file is unavailable") from exc
    return path


def _catalog_existing_application_key() -> str:
    """Return the trusted app-managed key when the complete pair exists."""
    key_path = _catalog_application_key_path()
    pub_path = Path(str(key_path) + ".pub")
    managed_root = _catalog_managed_store_dir()
    if not managed_root.exists():
        return ""
    _catalog_verify_managed_path(managed_root, directory=True)
    if _catalog_is_reparse_or_symlink(key_path) or _catalog_is_reparse_or_symlink(pub_path):
        # For a missing path the helper also returns true, so only treat it as
        # suspicious when either artifact is actually present/reparse-like.
        if key_path.exists() or pub_path.exists() or key_path.is_symlink() or pub_path.is_symlink():
            raise FileNotFoundError("application key pair is invalid")
    if not key_path.exists() and not pub_path.exists():
        return ""
    # A partial pair can be a previous interrupted generation.  Never replace
    # it blindly: return an explicit safe validation failure to the caller.
    if not key_path.is_file() or not pub_path.is_file():
        raise FileNotFoundError("application key pair is incomplete")
    _catalog_verify_managed_path(key_path, directory=False)
    _catalog_verify_managed_path(pub_path, directory=False)
    return _catalog_key_path(str(key_path))


def _catalog_create_application_key() -> str:
    """Create the one app-owned ed25519 pair after password bootstrap begins.

    This intentionally never calls the legacy ``ensure_keypair`` helper: that
    helper may inspect or create user ``~/.ssh`` material, which V4 must not
    silently adopt.  The parent application home must already exist.
    """
    key_path = _catalog_application_key_path()
    pub_path = Path(str(key_path) + ".pub")
    with _CATALOG_APPLICATION_KEY_LOCK:
        _catalog_ensure_managed_store()
        existing = _catalog_existing_application_key()
        if existing:
            return existing
        if key_path.exists() or pub_path.exists():
            raise FileNotFoundError("application key pair is incomplete")
        try:
            from cryptography.hazmat.primitives import serialization as _serialization
            from cryptography.hazmat.primitives.asymmetric import ed25519 as _ed25519
            private_key = _ed25519.Ed25519PrivateKey.generate()
            private_bytes = private_key.private_bytes(
                _serialization.Encoding.PEM,
                _serialization.PrivateFormat.OpenSSH,
                _serialization.NoEncryption(),
            )
            public_bytes = private_key.public_key().public_bytes(
                _serialization.Encoding.OpenSSH,
                _serialization.PublicFormat.OpenSSH,
            ) + b" memomics-catalog@local\n"
        except Exception as exc:
            raise RuntimeError("application key generation failed") from exc
        tmp_key = None
        tmp_pub = None
        installed_key = False
        installed_pub = False
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".%s." % key_path.name, suffix=".tmp", dir=str(key_path.parent))
            tmp_key = Path(tmp_name)
            with os.fdopen(fd, "wb") as fh:
                fh.write(private_bytes)
                fh.flush()
                os.fsync(fh.fileno())
            fd, tmp_name = tempfile.mkstemp(prefix=".%s." % pub_path.name, suffix=".tmp", dir=str(pub_path.parent))
            tmp_pub = Path(tmp_name)
            with os.fdopen(fd, "wb") as fh:
                fh.write(public_bytes)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_key, key_path)
            tmp_key = None
            installed_key = True
            os.replace(tmp_pub, pub_path)
            tmp_pub = None
            installed_pub = True
            _catalog_harden_managed_path(key_path, directory=False)
            _catalog_harden_managed_path(pub_path, directory=False)
        except _CatalogManagedStorePermissionError:
            # We own these just-created paths and must not leave a private key
            # behind with a broad inherited DACL after a failed hardening step.
            for path, installed in ((key_path, installed_key), (pub_path, installed_pub)):
                try:
                    if installed and path.exists():
                        path.unlink()
                except OSError:
                    pass
            raise
        except Exception as exc:
            for path, installed in ((key_path, installed_key), (pub_path, installed_pub)):
                try:
                    if installed and path.exists():
                        path.unlink()
                except OSError:
                    pass
            raise RuntimeError("application key generation failed") from exc
        finally:
            for path in (tmp_key, tmp_pub):
                try:
                    if path is not None and path.exists():
                        path.unlink()
                except OSError:
                    pass
    return _catalog_key_path(str(key_path))


def _catalog_public_key_line(key_path: str) -> str:
    """Read only the paired public-key *line* required for installation.

    The private-key body is never opened by this helper.  Requiring a paired
    ``.pub`` file avoids invoking a shell helper which could otherwise expose
    an untrusted path in diagnostics.
    """
    pub_path = key_path + ".pub"
    try:
        with open(pub_path, "r", encoding="utf-8") as fh:
            line = fh.read().strip()
    except Exception as exc:
        raise FileNotFoundError("paired public key file is unavailable") from exc
    if not line or "\n" in line or "\r" in line or "'" in line or len(line) > 16_384:
        raise ValueError("paired public key file is invalid")
    return line


def _catalog_same_key_path(left: str, right: str) -> bool:
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(left))) == os.path.normcase(
            os.path.normpath(os.path.abspath(right))
        )
    except Exception:
        return str(left) == str(right)


def _catalog_host_key_fingerprint(client):
    """Opaque host-key identity used only to detect a mid-flow identity swap."""
    try:
        transport = client.get_transport()
        key = transport.get_remote_server_key() if transport is not None else None
        fingerprint = key.get_fingerprint() if key is not None else None
        return bytes(fingerprint) if fingerprint else b""
    except Exception:
        return b""


def _catalog_validate_candidate(config: dict, *, require_public_key: bool) -> tuple[dict | None, dict | None]:
    """Normalize the private transient candidate and reject injection shapes."""
    if not isinstance(config, dict):
        return None, _catalog_probe_result(False, "validate", "invalid_connection", "连接配置格式无效。")
    try:
        # ``extra_ssh_options``/command/proxy command injection is never an
        # input surface for V4.  ProxyJump is generated structurally below.
        forbidden = {"command", "proxy_command", "extra_ssh_options", "password", "target_password", "gateway_password"}
        if forbidden.intersection(config):
            raise ValueError("unsupported connection field")
        host = _catalog_network_host(config.get("host"), "host")
        user = _catalog_safe_text(config.get("user"), "user", required=True, maximum=64)
        if not _CATALOG_SAFE_USER_RE.fullmatch(user):
            raise ValueError("user is invalid")
        port = _catalog_safe_port(config.get("port", 22))
        timeout = _catalog_safe_timeout(config.get("timeout", 30))
        key_path = _catalog_key_path(config.get("key_path", config.get("key")), required=False)
        normalized = {
            "host": host,
            "user": user,
            "port": port,
            "key": key_path,
            "workdir": _catalog_safe_text(config.get("workdir") or "~", "workdir", maximum=1024) or "~",
            "job_dir": _catalog_safe_text(config.get("job_dir") or "", "job_dir", maximum=1024),
            "local_root": _catalog_safe_text(config.get("local_root") or "", "local_root", maximum=2048),
            "remote_root": _catalog_safe_text(config.get("remote_root") or "", "remote_root", maximum=2048),
            "timeout": timeout,
            "scheduler": _catalog_safe_text(config.get("scheduler") or "auto", "scheduler", maximum=32).lower() or "auto",
            "partition": _catalog_safe_text(config.get("partition") or "", "partition", maximum=128),
            "queue": _catalog_safe_text(config.get("queue") or "", "queue", maximum=128),
            "node_name": _CATALOG_PROBE_NODE,
            # This path is produced locally, never accepted from the browser.
            # It is also passed to the final OpenSSH nodes probe so Paramiko
            # TOFU and the actual execution engine reject a changed host key
            # consistently.
            "known_hosts_path": str(_catalog_known_hosts_path()),
        }
        gateway = config.get("gateway")
        if gateway is not None:
            if not isinstance(gateway, dict):
                raise ValueError("gateway is invalid")
            g_forbidden = {"command", "proxy_command", "extra_ssh_options", "password"}
            if g_forbidden.intersection(gateway):
                raise ValueError("gateway contains unsupported fields")
            g_host = _catalog_network_host(gateway.get("host"), "gateway host")
            g_user = _catalog_safe_text(gateway.get("user"), "gateway user", required=True, maximum=64)
            if not _CATALOG_SAFE_USER_RE.fullmatch(g_user):
                raise ValueError("gateway endpoint is invalid")
            g_port = _catalog_safe_port(gateway.get("port", 22), "gateway port")
            requested_gateway_key = gateway.get("key_path", gateway.get("key")) or key_path
            g_key = _catalog_key_path(requested_gateway_key, required=bool(requested_gateway_key))
            if not g_key:
                raise FileNotFoundError("gateway application key is unavailable")
            normalized["gateway"] = {"host": g_host, "user": g_user, "port": g_port, "key": g_key}
        return normalized, None
    except _CatalogManagedStorePermissionError:
        return None, _catalog_probe_result(
            False, "validate", "key_permissions",
            "应用管理的 SSH 安全文件权限检查失败；连接未保存。",
        )
    except FileNotFoundError:
        return None, _catalog_probe_result(
            False, "validate", "key_path_unavailable",
            "指定的本地应用密钥或配套公钥文件不可用；请确认 key_path 和 .pub 文件。",
        )
    except Exception:
        return None, _catalog_probe_result(
            False, "validate", "invalid_connection",
            "连接配置无效；请检查主机、端口、用户名和路径。",
        )


def prepare_catalog_connection(config: dict, *, target_password: str | None = None,
                               require_public_key: bool = False) -> tuple[dict | None, dict | None]:
    """Resolve the V4-managed identity for a trusted, transient candidate.

    This is shared by the server adapter and the probe so a password-only
    first setup cannot persist a different identity than the one it tested.
    Omitted ``key_path`` never falls back to user SSH keys: we reuse only the
    existing app-owned catalog key, reuse the saved gateway key for a via-login
    route, or generate the app key *after* the caller supplied a target
    password for one-time authorization.
    """
    candidate, failure = _catalog_validate_candidate(config, require_public_key=False)
    if failure:
        return None, failure
    try:
        # Setup is the only phase allowed to create/harden the application
        # store.  Normal SSH/Paramiko re-entry uses verification-only helpers.
        _catalog_ensure_managed_store()
        key_path = str(candidate.get("key") or "")
        gateway = candidate.get("gateway")
        if not key_path and gateway:
            key_path = str(gateway.get("key") or "")
        if not key_path:
            key_path = _catalog_existing_application_key()
        if not key_path and str(target_password or ""):
            key_path = _catalog_create_application_key()
        if not key_path:
            return None, _catalog_password_required("target")
        candidate["key"] = _catalog_key_path(key_path)
        if gateway:
            gateway_key = _catalog_key_path(gateway.get("key"))
            if not _catalog_same_key_path(candidate["key"], gateway_key):
                return None, _catalog_probe_result(
                    False, "validate", "gateway_key_mismatch",
                    "跳板与目标必须使用同一把本地应用密钥；请为两端安装同一公钥后重试。",
                )
            gateway["key"] = gateway_key
        if require_public_key:
            candidate["public_key"] = _catalog_public_key_line(candidate["key"])
        return candidate, None
    except FileNotFoundError:
        return None, _catalog_probe_result(
            False, "validate", "key_path_unavailable",
            "指定的本地应用密钥或配套公钥文件不可用；请确认 key_path 和 .pub 文件。",
        )
    except Exception:
        return None, _catalog_probe_result(
            False, "validate", "invalid_connection",
            "连接配置无效；请检查主机、端口、用户名和路径。",
        )


def _catalog_tcp_handshake(host: str, port: int, timeout: int) -> None:
    """Cheap preflight with no credential material and no SSH command string."""
    sock = socket.create_connection((host, int(port)), timeout=min(max(int(timeout), 1), 15))
    try:
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _catalog_proxy_jump(gateway: dict) -> str:
    # Values have already passed strict literal validators; no shell fragment
    # or user-provided ProxyCommand ever reaches OpenSSH.
    host = str(gateway["host"])
    if ":" in host:
        host = "[%s]" % host
    return "%s@%s:%d" % (gateway["user"], host, int(gateway["port"]))


_CATALOG_ROUTE_CONFIG_RE = re.compile(r"^[0-9a-f]{64}\.conf$")


def _catalog_ssh_config_value(value) -> str:
    """Quote a generated OpenSSH config value without accepting fragments."""
    text = str(value or "")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text) or "%" in text:
        # OpenSSH expands tokens such as %h even inside quoted IdentityFile
        # and UserKnownHostsFile values.  Reject rather than serializing a
        # path different from the one V4 validated and pinned.
        raise ValueError("unsafe SSH config value")
    # Use slash paths on Windows so a backslash cannot accidentally become an
    # OpenSSH escape.  Quotes are still escaped for the few legal POSIX paths
    # containing a quote character.
    text = text.replace("\\", "/").replace('"', '\\"')
    return '"%s"' % text


def _catalog_ssh_config_endpoint(host: str, user: str, port: int, key_path: str,
                                 known_hosts_path: str, *, alias: str,
                                 proxy_jump: str = "") -> list[str]:
    """Render one fixed OpenSSH Host section from validated catalog fields."""
    lines = [
        "Host %s" % alias,
        "    HostName %s" % _catalog_ssh_config_value(host),
        "    User %s" % _catalog_ssh_config_value(user),
        "    Port %d" % int(port),
        "    BatchMode yes",
        "    StrictHostKeyChecking yes",
        "    UserKnownHostsFile %s" % _catalog_ssh_config_value(known_hosts_path),
        "    IdentitiesOnly yes",
        "    IdentityFile %s" % _catalog_ssh_config_value(key_path),
    ]
    if proxy_jump:
        lines.append("    ProxyJump %s" % proxy_jump)
    return lines


def _catalog_ssh_route_config_bytes(candidate: dict) -> tuple[str, bytes]:
    """Build a content-addressed config with no Include/ProxyCommand surface."""
    key_path = os.path.abspath(str(candidate["key"]))
    known_hosts_path = os.path.abspath(str(candidate["known_hosts_path"]))
    gateway = candidate.get("gateway")
    payload = {
        "version": 1,
        "target": {
            "host": str(candidate["host"]), "user": str(candidate["user"]),
            "port": int(candidate["port"]), "key": key_path,
        },
        "known_hosts": known_hosts_path,
        "gateway": ({
            "host": str(gateway["host"]), "user": str(gateway["user"]),
            "port": int(gateway["port"]), "key": os.path.abspath(str(gateway["key"])),
        } if gateway else None),
    }
    route_seed = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    gateway_alias = "memomics-v4-gateway-%s" % route_seed[:32]
    lines = _catalog_ssh_config_endpoint(
        payload["target"]["host"], payload["target"]["user"], payload["target"]["port"],
        payload["target"]["key"], known_hosts_path, alias=payload["target"]["host"],
        proxy_jump=gateway_alias if gateway else "",
    )
    if gateway:
        lines.append("")
        lines.extend(_catalog_ssh_config_endpoint(
            payload["gateway"]["host"], payload["gateway"]["user"], payload["gateway"]["port"],
            payload["gateway"]["key"], known_hosts_path, alias=gateway_alias,
        ))
    rendered = ("\n".join(lines) + "\n").encode("utf-8")
    return hashlib.sha256(rendered).hexdigest(), rendered


def _catalog_write_ssh_route_config(candidate: dict) -> Path:
    """Atomically materialize an immutable, generated V4 route config.

    The config is intentionally retained after profile deletion because job
    and R-session snapshots reference the exact historical ``-F`` path.
    """
    try:
        digest, rendered = _catalog_ssh_route_config_bytes(candidate)
    except ValueError as exc:
        raise RuntimeError("catalog SSH route config is invalid") from exc
    root = _catalog_ensure_managed_store()
    path = root / (digest + ".conf")
    with _CATALOG_SSH_CONFIG_LOCK:
        if path.exists() or path.is_symlink():
            try:
                _catalog_verify_managed_path(path, directory=False)
                if path.read_bytes() != rendered:
                    raise RuntimeError("catalog SSH route config digest conflict")
            except OSError as exc:
                raise RuntimeError("catalog SSH route config is unavailable") from exc
            return path
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".%s." % path.name, suffix=".tmp", dir=str(root))
            tmp = Path(tmp_name)
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(rendered)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
                _catalog_harden_managed_path(path, directory=False)
            finally:
                try:
                    if tmp.exists():
                        tmp.unlink()
                except OSError:
                    pass
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError("catalog SSH route config is unavailable") from exc
    return path


def validate_catalog_ssh_policy(options, *, host: str, user: str, port: int,
                                key: str, gateway=None,
                                require_managed: bool = False) -> tuple[list[str], list[str], str]:
    """Validate/pin a V4 route config for every SSH execution entry point.

    ``require_managed`` is durable profile/job-snapshot provenance.  It is
    deliberately independent of the mutable ``-F`` path so a V4 snapshot
    cannot become a legacy option list when its route file is moved or renamed.
    """
    def _permission_checker(path, directory):
        _catalog_verify_managed_path(Path(path), directory=bool(directory))

    try:
        return _ssh_policy.split_and_validate_managed_options(
            options, managed_root=_catalog_route_config_dir(), expected_host=str(host),
            expected_user=str(user), expected_port=int(port or 22), expected_key=str(key),
            expected_gateway=gateway, permission_checker=_permission_checker,
            require_managed=bool(require_managed),
        )
    except _CatalogManagedStorePermissionError:
        raise
    except _ssh_policy.ManagedSSHPolicyError as exc:
        raise RuntimeError("catalog SSH route config failed integrity validation") from exc


def _split_catalog_ssh_options(options, *, host: str, user: str, port: int,
                               key: str, gateway=None,
                               require_managed: bool = False) -> tuple[list[str], list[str]]:
    prefix, remaining, _digest = validate_catalog_ssh_policy(
        options, host=host, user=user, port=port, key=key, gateway=gateway,
        require_managed=require_managed,
    )
    return prefix, remaining


def _catalog_ssh_config_fingerprint(options, cfg: dict) -> str:
    """Return a validated content digest for the SSH connection cache."""
    if catalog_v5_password_profile(cfg):
        candidate = catalog_v5_candidate_from_profile(cfg)
        prefix, _target_alias, _gateway_alias = validate_catalog_v5_ssh_policy(options, candidate)
        try:
            return hashlib.sha256(Path(prefix[1]).read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeError("catalog V5 SSH route proof is invalid") from exc
    _prefix, _remaining, digest = validate_catalog_ssh_policy(
        options, host=str(cfg.get("host") or ""), user=str(cfg.get("user") or ""),
        port=int(cfg.get("port") or 22), key=str(cfg.get("key") or ""),
        require_managed=catalog_v4_ssh_route_required(cfg.get("catalog_v4_ssh_route")),
    )
    return digest


def catalog_ssh_policy_options(candidate: dict) -> list[str]:
    """Return the sole server-owned V4 SSH option surface for a profile."""
    path = _catalog_write_ssh_route_config(candidate)
    options = ["-F", str(path).replace("\\", "/")]
    validate_catalog_ssh_policy(
        options, host=candidate["host"], user=candidate["user"], port=candidate["port"],
        key=candidate["key"], gateway=candidate.get("gateway"), require_managed=True,
    )
    return options


# ---------------------------------------------------------------------------
# V5 password-only catalog route
# ---------------------------------------------------------------------------
#
# New catalog profiles do not generate/install a public key.  Their route
# config is still content-addressed and protected under the same app-owned
# directory as V4 because strict host-key pins and immutable -F configs remain
# necessary when the authentication factor is a locally stored password.

_CATALOG_V5_ACCOUNT_RE = re.compile(r"^account-[0-9a-f]{12}$")
_CATALOG_V5_ALIAS_RE = re.compile(r"^memomics-v5-(?:target|gateway)-[0-9a-f]{32}$")


def _catalog_v5_account_id(value, field: str) -> str:
    account_id = str(value or "")
    if not _CATALOG_V5_ACCOUNT_RE.fullmatch(account_id):
        raise ValueError("%s is invalid" % field)
    return account_id


def _catalog_v5_candidate(config: dict) -> dict:
    """Normalize a trusted V5 candidate without accepting a key/command path."""
    if not isinstance(config, dict):
        raise ValueError("candidate is invalid")
    forbidden = {
        "key", "key_path", "password", "target_password", "gateway_password",
        "extra_ssh_options", "command", "proxy_command", "proxy_jump",
    }
    if forbidden.intersection(config):
        raise ValueError("candidate contains retired authentication fields")
    host = _catalog_network_host(config.get("host"), "host")
    user = _catalog_safe_text(config.get("user"), "user", required=True, maximum=64)
    if not _CATALOG_SAFE_USER_RE.fullmatch(user):
        raise ValueError("user is invalid")
    candidate = {
        "host": host,
        "user": user,
        "port": _catalog_safe_port(config.get("port", 22)),
        "account_id": _catalog_v5_account_id(config.get("account_id"), "account id"),
        "workdir": _catalog_safe_text(config.get("workdir") or "~", "workdir", maximum=1024) or "~",
        "job_dir": _catalog_safe_text(config.get("job_dir") or "", "job_dir", maximum=1024),
        "local_root": _catalog_safe_text(config.get("local_root") or "", "local_root", maximum=2048),
        "remote_root": _catalog_safe_text(config.get("remote_root") or "", "remote_root", maximum=2048),
        "timeout": _catalog_safe_timeout(config.get("timeout", 30)),
        "scheduler": _catalog_safe_text(config.get("scheduler") or "auto", "scheduler", maximum=32).lower() or "auto",
        "partition": _catalog_safe_text(config.get("partition") or "", "partition", maximum=128),
        "queue": _catalog_safe_text(config.get("queue") or "", "queue", maximum=128),
        "node_name": _CATALOG_PROBE_NODE,
        "known_hosts_path": str(_catalog_known_hosts_path()),
    }
    gateway = config.get("gateway")
    if gateway is None:
        return candidate
    if not isinstance(gateway, dict) or {"key", "key_path", "password", "command", "proxy_command"}.intersection(gateway):
        raise ValueError("gateway is invalid")
    g_host = _catalog_network_host(gateway.get("host"), "gateway host")
    g_user = _catalog_safe_text(gateway.get("user"), "gateway user", required=True, maximum=64)
    if not _CATALOG_SAFE_USER_RE.fullmatch(g_user):
        raise ValueError("gateway user is invalid")
    candidate["gateway"] = {
        "host": g_host,
        "user": g_user,
        "port": _catalog_safe_port(gateway.get("port", 22), "gateway port"),
        "account_id": _catalog_v5_account_id(gateway.get("account_id"), "gateway account id"),
    }
    return candidate


def catalog_v5_candidate_from_profile(cfg: dict) -> dict:
    """Rebuild the non-secret route snapshot stored in a durable profile."""
    if not catalog_v5_password_profile(cfg):
        raise RuntimeError("catalog V5 password profile provenance is invalid")
    candidate = {
        "host": cfg.get("host"), "user": cfg.get("user"), "port": cfg.get("port"),
        "account_id": cfg.get("catalog_account_id"), "workdir": cfg.get("workdir"),
        "job_dir": cfg.get("job_dir"), "local_root": cfg.get("local_root"),
        "remote_root": cfg.get("remote_root"), "timeout": cfg.get("timeout"),
        "scheduler": cfg.get("scheduler"), "partition": cfg.get("partition"), "queue": cfg.get("queue"),
    }
    gateway_account = str(cfg.get("gateway_account_id") or "")
    if gateway_account:
        candidate["gateway"] = {
            "host": cfg.get("catalog_v5_gateway_host"),
            "user": cfg.get("catalog_v5_gateway_user"),
            "port": cfg.get("catalog_v5_gateway_port"),
            "account_id": gateway_account,
        }
    return _catalog_v5_candidate(candidate)


def _catalog_v5_route_seed(candidate: dict) -> tuple[str, dict]:
    """Return a deterministic seed plus a serialization-safe endpoint view."""
    known_hosts = os.path.abspath(str(candidate["known_hosts_path"]))
    gateway = candidate.get("gateway")
    payload = {
        "version": 5,
        "target": {
            "host": str(candidate["host"]), "user": str(candidate["user"]),
            "port": int(candidate["port"]), "account_id": str(candidate["account_id"]),
        },
        "known_hosts": known_hosts,
        "gateway": ({
            "host": str(gateway["host"]), "user": str(gateway["user"]),
            "port": int(gateway["port"]), "account_id": str(gateway["account_id"]),
        } if gateway else None),
    }
    seed = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()
    return seed, payload


def _catalog_v5_aliases(candidate: dict) -> tuple[str, str]:
    seed, payload = _catalog_v5_route_seed(candidate)
    target = "memomics-v5-target-%s" % seed[:32]
    gateway = "memomics-v5-gateway-%s" % seed[:32] if payload["gateway"] else ""
    return target, gateway


def _catalog_v5_ssh_config_endpoint(endpoint: dict, known_hosts_path: str, *, alias: str,
                                    proxy_jump: str = "", trust_only: bool = False) -> list[str]:
    """Render one fixed password-only section; no caller controls directives."""
    if not _CATALOG_V5_ALIAS_RE.fullmatch(alias):
        raise ValueError("route alias is invalid")
    lines = [
        "Host %s" % alias,
        "    HostName %s" % _catalog_ssh_config_value(endpoint["host"]),
        "    User %s" % _catalog_ssh_config_value(endpoint["user"]),
        "    Port %d" % int(endpoint["port"]),
        "    BatchMode %s" % ("yes" if trust_only else "no"),
        "    PubkeyAuthentication no",
        "    PasswordAuthentication no" if trust_only else "    PasswordAuthentication yes",
        "    KbdInteractiveAuthentication no",
        "    PreferredAuthentications %s" % ("none" if trust_only else "password"),
        "    NumberOfPasswordPrompts %d" % (0 if trust_only else 1),
        "    StrictHostKeyChecking %s" % ("accept-new" if trust_only else "yes"),
        "    UserKnownHostsFile %s" % _catalog_ssh_config_value(known_hosts_path),
        "    GlobalKnownHostsFile none",
        "    HashKnownHosts no",
        "    HostKeyAlias %s" % alias,
        "    IdentityAgent none",
        "    IdentitiesOnly yes",
    ]
    if proxy_jump:
        if not _CATALOG_V5_ALIAS_RE.fullmatch(proxy_jump):
            raise ValueError("gateway route alias is invalid")
        lines.append("    ProxyJump %s" % proxy_jump)
    return lines


def _catalog_v5_ssh_route_config_bytes(candidate: dict, *, trust_endpoint: str = "") -> tuple[str, bytes]:
    """Build a strict V5 route or its narrowly scoped unauthenticated TOFU probe."""
    candidate = _catalog_v5_candidate(candidate)
    if trust_endpoint not in {"", "target", "gateway"}:
        raise ValueError("trust endpoint is invalid")
    gateway = candidate.get("gateway")
    if trust_endpoint == "gateway" and not gateway:
        raise ValueError("gateway trust endpoint is unavailable")
    target_alias, gateway_alias = _catalog_v5_aliases(candidate)
    known_hosts = os.path.abspath(str(candidate["known_hosts_path"]))
    lines = _catalog_v5_ssh_config_endpoint(
        candidate, known_hosts, alias=target_alias,
        proxy_jump=gateway_alias if gateway else "", trust_only=trust_endpoint == "target",
    )
    if gateway:
        lines.append("")
        lines.extend(_catalog_v5_ssh_config_endpoint(
            gateway, known_hosts, alias=gateway_alias, trust_only=trust_endpoint == "gateway",
        ))
    rendered = ("\n".join(lines) + "\n").encode("utf-8")
    return hashlib.sha256(rendered).hexdigest(), rendered


def _catalog_v5_write_route_config(candidate: dict) -> tuple[Path, str, str]:
    digest, rendered = _catalog_v5_ssh_route_config_bytes(candidate)
    root = _catalog_ensure_managed_store()
    path = root / (digest + ".conf")
    with _CATALOG_SSH_CONFIG_LOCK:
        if path.exists() or path.is_symlink():
            _catalog_verify_managed_path(path, directory=False)
            if path.read_bytes() != rendered:
                raise RuntimeError("catalog password SSH route digest conflict")
        else:
            fd, tmp_name = tempfile.mkstemp(prefix=".%s." % path.name, suffix=".tmp", dir=str(root))
            tmp = Path(tmp_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(rendered)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
                _catalog_harden_managed_path(path, directory=False)
            finally:
                try:
                    if tmp.exists():
                        tmp.unlink()
                except OSError:
                    pass
    target_alias, gateway_alias = _catalog_v5_aliases(_catalog_v5_candidate(candidate))
    return path, target_alias, gateway_alias


def validate_catalog_v5_ssh_policy(options, candidate: dict) -> tuple[list[str], str, str]:
    """Prove a stored V5 ``-F`` matches this exact account/endpoint route."""
    values = [str(value) for value in (options or [])]
    if len(values) != 2 or values[0] != "-F":
        raise RuntimeError("catalog V5 SSH route proof is invalid")
    normalized = _catalog_v5_candidate(candidate)
    expected_digest, expected = _catalog_v5_ssh_route_config_bytes(normalized)
    root = _catalog_ensure_managed_store()
    raw = Path(values[1])
    canonical = Path(os.path.abspath(str(raw)))
    try:
        if (not canonical.is_absolute() or canonical.parent.resolve() != root.resolve()
                or _catalog_is_reparse_or_symlink(canonical) or canonical.resolve() != canonical
                or canonical.name != expected_digest + ".conf"):
            raise RuntimeError("catalog V5 SSH route proof is invalid")
        _catalog_verify_managed_path(canonical, directory=False)
        if canonical.read_bytes() != expected:
            raise RuntimeError("catalog V5 SSH route proof is invalid")
        known_hosts = _catalog_known_hosts_path()
        if known_hosts.exists() or known_hosts.is_symlink():
            _catalog_verify_managed_path(known_hosts, directory=False)
    except _CatalogManagedStorePermissionError:
        raise
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("catalog V5 SSH route proof is invalid") from exc
    target_alias, gateway_alias = _catalog_v5_aliases(normalized)
    return ["-F", str(canonical).replace("\\", "/")], target_alias, gateway_alias


def catalog_v5_ssh_policy_options(candidate: dict) -> list[str]:
    path, _target_alias, _gateway_alias = _catalog_v5_write_route_config(candidate)
    options, _target_alias, _gateway_alias = validate_catalog_v5_ssh_policy(["-F", str(path)], candidate)
    return options


def _catalog_v5_credential_store():
    from memomics.cluster_credentials import CredentialManagerStore
    return CredentialManagerStore(_get_config_path().parent)


def catalog_v5_password_runtime(candidate: dict, *, credential_store=None,
                                include_target: bool = True, include_gateway: bool = True):
    """Return a fresh ASKPASS environment for one V5 native SSH process."""
    normalized = _catalog_v5_candidate(candidate)
    options = catalog_v5_ssh_policy_options(normalized)
    _prefix, target_alias, gateway_alias = validate_catalog_v5_ssh_policy(options, normalized)
    gateway = normalized.get("gateway") or {}
    return _password_ssh.build_password_runtime(
        credential_store or _catalog_v5_credential_store(),
        target_account_id=normalized["account_id"], target_user=normalized["user"], target_alias=target_alias,
        gateway_account_id=gateway.get("account_id", ""), gateway_user=gateway.get("user", ""),
        gateway_alias=gateway_alias, include_target=include_target, include_gateway=include_gateway,
        helper_path=_catalog_v5_staged_askpass_helper(),
        helper_sha256=_password_ssh.ASKPASS_HELPER_SHA256,
    )


def catalog_v5_process_runtime(cfg: dict, *, credential_store=None):
    """Verify one durable V5 profile and create its next process environment."""
    candidate = catalog_v5_candidate_from_profile(cfg)
    options, target_alias, gateway_alias = validate_catalog_v5_ssh_policy(
        cfg.get("extra_ssh_options") or [], candidate,
    )
    # These copies are retained in the YAML/job snapshot for transparent
    # diagnostics, but are not trusted on their own.  They must agree with
    # the content-addressed policy generated from endpoint/account metadata.
    if (str(cfg.get("catalog_v5_target_alias") or "") != target_alias
            or str(cfg.get("catalog_v5_gateway_alias") or "") != gateway_alias):
        raise RuntimeError("catalog V5 SSH alias provenance is invalid")
    gateway = candidate.get("gateway") or {}
    runtime = _password_ssh.build_password_runtime(
        credential_store or _catalog_v5_credential_store(),
        target_account_id=candidate["account_id"], target_user=candidate["user"], target_alias=target_alias,
        gateway_account_id=gateway.get("account_id", ""), gateway_user=gateway.get("user", ""),
        gateway_alias=gateway_alias,
        helper_path=_catalog_v5_staged_askpass_helper(),
        helper_sha256=_password_ssh.ASKPASS_HELPER_SHA256,
    )
    return candidate, options, runtime


def _catalog_v5_known_alias_exists(alias: str) -> bool:
    """Inspect only the controlled, unhashed V5 HostKeyAlias entries."""
    if not _CATALOG_V5_ALIAS_RE.fullmatch(str(alias or "")):
        return False
    path = _catalog_known_hosts_path()
    if not path.exists():
        return False
    _catalog_verify_managed_path(path, directory=False)
    try:
        for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) >= 3 and alias in fields[0].split(","):
                return True
    except Exception as exc:
        raise RuntimeError("catalog V5 host-key store is unavailable") from exc
    return False


def _catalog_v5_trust_probe(candidate: dict, endpoint: str, *, credential_store=None) -> None:
    """TOFU exactly one absent alias without exposing that endpoint's password."""
    normalized = _catalog_v5_candidate(candidate)
    if endpoint not in {"target", "gateway"}:
        raise RuntimeError("catalog V5 trust probe is invalid")
    _strict_options = catalog_v5_ssh_policy_options(normalized)
    _prefix, target_alias, gateway_alias = validate_catalog_v5_ssh_policy(_strict_options, normalized)
    alias = target_alias if endpoint == "target" else gateway_alias
    if not alias:
        raise RuntimeError("catalog V5 trust probe is invalid")
    if _catalog_v5_known_alias_exists(alias):
        return
    # Target trust requires only the already-pinned gateway password.  The
    # target section has every authentication method disabled, so its map is
    # deliberately absent and a host-key write failure cannot release it.
    runtime = catalog_v5_password_runtime(
        normalized, credential_store=credential_store,
        include_target=False, include_gateway=(endpoint == "target"),
    )
    _digest, rendered = _catalog_v5_ssh_route_config_bytes(normalized, trust_endpoint=endpoint)
    root = _catalog_ensure_managed_store()
    with _CATALOG_KNOWN_HOSTS_LOCK:
        # Another request can pin the exact same alias while this one was
        # composing its local config.  Once present we never issue accept-new.
        if _catalog_v5_known_alias_exists(alias):
            return
        fd, tmp_name = tempfile.mkstemp(prefix=".v5-trust-", suffix=".conf", dir=str(root))
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            _catalog_harden_managed_path(tmp, directory=False)
            ssh = _password_ssh.system_openssh_executable("ssh.exe")
            # Authentication failure is expected (the trusted endpoint has
            # PreferredAuthentications=none); only an on-disk V5 HostKeyAlias
            # pin proves that the SSH handshake completed safely.
            subprocess.run(
                [str(ssh), "-F", str(tmp).replace("\\", "/"), alias, "exit"],
                capture_output=True, text=True, timeout=min(max(normalized["timeout"], 1), 45),
                stdin=subprocess.DEVNULL, env=runtime.env,
            )
            path = _catalog_known_hosts_path()
            if not path.exists() or path.is_symlink():
                raise RuntimeError("catalog V5 host-key pin was not written")
            _catalog_harden_managed_path(path, directory=False)
            _catalog_verify_managed_path(path, directory=False)
            if not _catalog_v5_known_alias_exists(alias):
                raise RuntimeError("catalog V5 host-key pin was not written")
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass


def catalog_v5_trust_host_keys(candidate: dict, *, credential_store=None) -> None:
    """Pin all missing V5 endpoint aliases before a strict password launch."""
    normalized = _catalog_v5_candidate(candidate)
    # A target behind a gateway cannot be reached before the gateway itself
    # has a strict pin.  Each branch is rechecked under the global pin lock.
    if normalized.get("gateway"):
        _catalog_v5_trust_probe(normalized, "gateway", credential_store=credential_store)
    _catalog_v5_trust_probe(normalized, "target", credential_store=credential_store)


def _catalog_v5_transient_nodes_config(candidate: dict) -> dict:
    normalized = _catalog_v5_candidate(candidate)
    _options, target_alias, gateway_alias = validate_catalog_v5_ssh_policy(
        catalog_v5_ssh_policy_options(normalized), normalized,
    )
    entry = {
        "connection_profile": True,
        "catalog_v5_ssh_route": CATALOG_V5_SSH_ROUTE_MARKER,
        "auth_mode": CATALOG_V5_PASSWORD_AUTH_MODE,
        "catalog_account_id": normalized["account_id"],
        "catalog_v5_target_alias": target_alias,
        "catalog_v5_gateway_alias": gateway_alias,
        "host": normalized["host"], "user": normalized["user"], "port": normalized["port"], "key": "",
        "workdir": normalized["workdir"], "job_dir": normalized["job_dir"],
        "local_root": normalized["local_root"], "remote_root": normalized["remote_root"],
        "timeout": normalized["timeout"], "scheduler": normalized["scheduler"],
        "partition": normalized["partition"], "queue": normalized["queue"],
        "extra_ssh_options": catalog_v5_ssh_policy_options(normalized),
    }
    if normalized.get("gateway"):
        gateway = dict(normalized["gateway"])
        entry.update({
            "gateway_account_id": gateway["account_id"],
            # Durable V5 execution rebuilds its route solely from these
            # non-secret fields.  The transient probe uses the same profile
            # shape so a direct test cannot pass while the persisted route
            # would later lose its gateway metadata.
            "catalog_v5_gateway_host": gateway["host"],
            "catalog_v5_gateway_user": gateway["user"],
            "catalog_v5_gateway_port": gateway["port"],
        })
    cfg = dict(_DEFAULT_CFG)
    cfg.update({"enabled": True, "nodes": {_CATALOG_PROBE_NODE: entry}, "default_node": _CATALOG_PROBE_NODE,
                "allow_unlisted_nodes": False, "auto_record_env": False})
    return cfg


def probe_catalog_v5_password_connection(candidate: dict, *, credential_store=None) -> dict:
    """Controlled V5 match: pin keys first, then run the normal nodes engine."""
    try:
        normalized = _catalog_v5_candidate(candidate)
        catalog_v5_trust_host_keys(normalized, credential_store=credential_store)
        # Building the final runtime after every pin is verified ensures the
        # target password is never mapped during a failed TOFU phase.
        catalog_v5_password_runtime(normalized, credential_store=credential_store)
        raw = _action_nodes(_catalog_v5_transient_nodes_config(normalized), {"node": _CATALOG_PROBE_NODE})
        payload = json.loads(raw)
        items = payload.get("nodes") if isinstance(payload, dict) else None
        item = items[0] if isinstance(items, list) and items else {}
        if isinstance(payload, dict) and bool(item.get("reachable")):
            return _catalog_probe_result(True, "nodes_probe", "ok", "密码连接和原始节点探测均已通过。",
                                         node=str(item.get("name") or _CATALOG_PROBE_NODE))
        return _catalog_probe_result(False, "nodes_probe", "nodes_probe_failed", "原始 SSH 节点探测未通过；连接尚未保存。")
    except _password_ssh.PasswordSSHError as exc:
        code = exc.code
        if code == "credential_missing":
            return _catalog_probe_result(False, "credential", code, "该集群账号尚未保存登录密码。")
        return _catalog_probe_result(False, "credential", code, "本机密码登录组件不可用；连接尚未保存。")
    except _CatalogManagedStorePermissionError:
        return _catalog_managed_store_permission_failure()
    except Exception:
        return _catalog_probe_result(False, "host_key", "host_key_probe_failed", "主机密钥验证或密码连接未通过；连接尚未保存。")


def _catalog_transient_nodes_config(candidate: dict) -> dict:
    """Create an in-memory remote config for the unmodified nodes engine."""
    entry = {
        "connection_profile": True,
        "catalog_v4_ssh_route": CATALOG_V4_SSH_ROUTE_MARKER,
        "host": candidate["host"],
        "user": candidate["user"],
        "port": candidate["port"],
        "key": candidate["key"],
        "workdir": candidate["workdir"],
        "job_dir": candidate["job_dir"],
        "local_root": candidate["local_root"],
        "remote_root": candidate["remote_root"],
        "timeout": candidate["timeout"],
        "scheduler": candidate["scheduler"],
        "partition": candidate["partition"],
        "queue": candidate["queue"],
        # This one app-owned ``-F`` file is intentionally inherited by the
        # standard OpenSSH ProxyJump child.  Outer ``-o`` values are not, so
        # BatchMode/strict host-key/IdentityFile rules live in the generated
        # config rather than user-controlled arguments.
        "extra_ssh_options": catalog_ssh_policy_options(candidate),
    }
    cfg = dict(_DEFAULT_CFG)
    cfg.update({"enabled": True, "nodes": {_CATALOG_PROBE_NODE: entry}, "default_node": _CATALOG_PROBE_NODE,
                "allow_unlisted_nodes": False, "auto_record_env": False})
    return cfg


def _catalog_original_nodes_probe(candidate: dict) -> dict:
    """Run the exact existing BatchMode nodes action against the transient cfg."""
    try:
        raw = _action_nodes(_catalog_transient_nodes_config(candidate), {"node": _CATALOG_PROBE_NODE})
        payload = json.loads(raw)
        items = payload.get("nodes") if isinstance(payload, dict) else None
        item = items[0] if isinstance(items, list) and items else {}
        if isinstance(payload, dict) and bool(item.get("reachable")):
            return _catalog_probe_result(
                True, "nodes_probe", "ok", "密钥连接和原始节点探测均已通过。",
                node=str(item.get("name") or _CATALOG_PROBE_NODE),
            )
    except _CatalogManagedStorePermissionError:
        return _catalog_managed_store_permission_failure()
    except Exception:
        pass
    return _catalog_probe_result(
        False, "nodes_probe", "nodes_probe_failed",
        "密钥已验证，但原始 SSH 节点探测未通过；连接尚未保存。",
    )


def _catalog_is_auth_error(paramiko, exc: Exception) -> bool:
    try:
        auth_error = paramiko.ssh_exception.AuthenticationException
        return isinstance(exc, auth_error)
    except Exception:
        return False


def _catalog_is_host_key_error(paramiko, exc: Exception) -> bool:
    if isinstance(exc, _CatalogHostKeyChangedError):
        return True
    try:
        host_key_error = paramiko.ssh_exception.BadHostKeyException
        return isinstance(exc, host_key_error)
    except Exception:
        return False


def _catalog_is_managed_store_permission_error(exc: Exception) -> bool:
    return isinstance(exc, _CatalogManagedStorePermissionError)


def _catalog_managed_store_permission_failure() -> dict:
    return _catalog_probe_result(
        False, "key_auth", "key_permissions",
        "应用管理的 SSH 安全文件权限检查失败；连接未保存。",
    )


def _catalog_host_key_changed(hop: str) -> dict:
    label = "跳板" if hop == "gateway" else "目标节点"
    return _catalog_probe_result(
        False, "%s_key_auth" % hop, "host_key_changed",
        "%s的 SSH 主机密钥与首次记录不一致；为安全起见未发送密码且未保存连接。" % label,
    )


def _catalog_password_required(hop: str) -> dict:
    label = "跳板" if hop == "gateway" else "目标节点"
    return _catalog_probe_result(
        False, "%s_password" % hop, "%s_password_required" % hop,
        "需要%s密码来一次性安装本地应用公钥；密码不会保存。" % label,
        password_required=hop,
    )


def _catalog_auth_failure(paramiko, exc: Exception, hop: str) -> dict:
    label = "跳板" if hop == "gateway" else "目标节点"
    if _catalog_is_managed_store_permission_error(exc):
        return _catalog_managed_store_permission_failure()
    if _catalog_is_auth_error(paramiko, exc):
        code = "%s_auth_failed" % hop
        message = "%s认证失败；请检查该账号密码或其 SSH 策略。" % label
    else:
        code = "%s_ssh_failed" % hop
        message = "%s SSH 握手或连接失败；请检查网络、端口和访问策略。" % label
    return _catalog_probe_result(False, "%s_auth" % hop, code, message)


def probe_connection(config: dict, *, target_password: str | None = None,
                     gateway_password: str | None = None) -> dict:
    """Test a V4 candidate without saving it, optionally installing its key.

    Stages are deliberately explicit so the WebUI can request each account's
    password independently.  Passwords are consumed only by Paramiko calls in
    this function and are never returned, logged, stored in YAML/SQLite, or
    inserted into the original BatchMode probe configuration.
    """
    candidate, failure = prepare_catalog_connection(
        config, target_password=target_password, require_public_key=True,
    )
    if failure:
        return failure
    paramiko = _paramiko()
    if paramiko is None:
        return _catalog_probe_result(
            False, "key_auth", "missing_dependency",
            "缺少 paramiko，无法进行一次性密码认证和公钥安装；请安装应用依赖后重试。",
        )

    target_client = None
    gateway_client = None
    target_host_key = b""
    try:
        gateway = candidate.get("gateway")
        if gateway:
            try:
                _catalog_tcp_handshake(gateway["host"], gateway["port"], candidate["timeout"])
            except Exception:
                return _catalog_probe_result(
                    False, "tcp", "gateway_tcp_failed",
                    "无法建立到跳板的 TCP 连接；请检查跳板主机、端口和网络。",
                )
            try:
                gateway_client, gateway_mode = _p_connect(
                    paramiko, gateway["host"], gateway["port"], gateway["user"], "", gateway["key"],
                    known_hosts_path=candidate["known_hosts_path"],
                )
            except Exception as key_exc:
                if _catalog_is_host_key_error(paramiko, key_exc):
                    return _catalog_host_key_changed("gateway")
                if _catalog_is_managed_store_permission_error(key_exc):
                    return _catalog_managed_store_permission_failure()
                if not str(gateway_password or ""):
                    return _catalog_password_required("gateway")
                try:
                    gateway_client, gateway_mode = _p_connect(
                        paramiko, gateway["host"], gateway["port"], gateway["user"], str(gateway_password), "",
                        known_hosts_path=candidate["known_hosts_path"],
                    )
                except Exception as password_exc:
                    if _catalog_is_host_key_error(paramiko, password_exc):
                        return _catalog_host_key_changed("gateway")
                    if _catalog_is_managed_store_permission_error(password_exc):
                        return _catalog_managed_store_permission_failure()
                    return _catalog_auth_failure(paramiko, password_exc, "gateway")
            if gateway_mode == "password":
                try:
                    _exec_install(gateway_client, candidate["public_key"])
                except Exception:
                    return _catalog_probe_result(
                        False, "install_key", "gateway_key_install_failed",
                        "跳板已认证，但应用公钥安装失败；连接尚未保存。",
                    )

            def sock_factory():
                transport = gateway_client.get_transport()
                if transport is None:
                    raise RuntimeError("gateway transport unavailable")
                return transport.open_channel("direct-tcpip", (candidate["host"], candidate["port"]), ("127.0.0.1", 0))
        else:
            try:
                _catalog_tcp_handshake(candidate["host"], candidate["port"], candidate["timeout"])
            except Exception:
                return _catalog_probe_result(
                    False, "tcp", "target_tcp_failed",
                    "无法建立到目标节点的 TCP 连接；请检查主机、端口和网络。",
                )
            sock_factory = None

        try:
            target_client, target_mode = _p_connect(
                paramiko, candidate["host"], candidate["port"], candidate["user"], "", candidate["key"],
                sock_factory=sock_factory, known_hosts_path=candidate["known_hosts_path"],
            )
        except Exception as key_exc:
            if _catalog_is_host_key_error(paramiko, key_exc):
                return _catalog_host_key_changed("target")
            if _catalog_is_managed_store_permission_error(key_exc):
                return _catalog_managed_store_permission_failure()
            if not str(target_password or ""):
                return _catalog_password_required("target")
            try:
                target_client, target_mode = _p_connect(
                    paramiko, candidate["host"], candidate["port"], candidate["user"], str(target_password), "",
                    sock_factory=sock_factory, known_hosts_path=candidate["known_hosts_path"],
                )
            except Exception as password_exc:
                if _catalog_is_host_key_error(paramiko, password_exc):
                    return _catalog_host_key_changed("target")
                if _catalog_is_managed_store_permission_error(password_exc):
                    return _catalog_managed_store_permission_failure()
                return _catalog_auth_failure(paramiko, password_exc, "target")
        target_host_key = _catalog_host_key_fingerprint(target_client)
        if target_mode == "password":
            try:
                _exec_install(target_client, candidate["public_key"])
            except Exception:
                return _catalog_probe_result(
                    False, "install_key", "target_key_install_failed",
                    "目标节点已认证，但应用公钥安装失败；连接尚未保存。",
                )
            try:
                target_client.close()
            except Exception:
                pass
            target_client = None
            try:
                verified_client, _mode = _p_connect(
                    paramiko, candidate["host"], candidate["port"], candidate["user"], "", candidate["key"],
                    sock_factory=sock_factory, known_hosts_path=candidate["known_hosts_path"],
                )
            except Exception as verify_exc:
                if _catalog_is_host_key_error(paramiko, verify_exc):
                    return _catalog_host_key_changed("target")
                if _catalog_is_managed_store_permission_error(verify_exc):
                    return _catalog_managed_store_permission_failure()
                return _catalog_auth_failure(paramiko, verify_exc, "target")
            verified_host_key = _catalog_host_key_fingerprint(verified_client)
            if target_host_key and verified_host_key and target_host_key != verified_host_key:
                try:
                    verified_client.close()
                except Exception:
                    pass
                return _catalog_probe_result(
                    False, "key_auth", "host_key_changed",
                    "目标节点的主机密钥在认证期间发生变化；为安全起见未保存连接。",
                )
            target_client = verified_client

        # Do not let a Paramiko success stand in for application usability.
        # The actual existing OpenSSH/BatchMode nodes engine must pass before
        # the catalog persists or enables this connection.
        return _catalog_original_nodes_probe(candidate)
    finally:
        # Do not persist credentials in objects retained by this scope.  The
        # local application key path is intentionally only used as an argv
        # value by the existing SSH engine and never placed in a response.
        target_password = None
        gateway_password = None
        for client in (target_client, gateway_client):
            try:
                if client is not None:
                    client.close()
            except Exception:
                pass


def probe_saved_connection(config: dict) -> dict:
    """Retest a saved V4 profile through the original nodes engine only.

    Unlike ``probe_connection``, this endpoint never prompts for or accepts a
    password.  A saved connection is usable only if its configured key passes
    the same BatchMode nodes probe users invoke elsewhere in MemOmics.
    """
    candidate, failure = prepare_catalog_connection(config, require_public_key=False)
    if failure:
        return failure
    return _catalog_original_nodes_probe(candidate)


def _install_cmd(pub_line: str) -> str:
    """幂等安装命令：已有该行就报 ALREADY，否则安全追加并报 INSTALLED。"""
    return ("umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; "
            "chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; "
            "grep -qF '%s' ~/.ssh/authorized_keys 2>/dev/null && echo __MEMOMICS_KEY_ALREADY__ "
            # Always write a leading newline.  This preserves existing bytes
            # while preventing a no-final-LF authorized_keys file from joining
            # its final key to the new public-key line; an extra blank line is
            # valid OpenSSH syntax.
            "|| { printf '\\n%%s\\n' '%s' >> ~/.ssh/authorized_keys && echo __MEMOMICS_KEY_INSTALLED__; }"
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


def detect_private_keys() -> list:
    """探测本机默认位置的 SSH 私钥（存在且非空），返回绝对路径列表（正斜杠）。

    2026-10-11 用户反馈"输入完 host 根本不知道怎么检测"：私钥路径不再要求手填，
    所有需要 key 的入口先用这里探测，探测不到再由 ensure_keypair 自动生成。
    """
    home = os.path.expanduser("~")
    out = []
    for nm in ("id_ed25519", "id_ecdsa", "id_rsa", "id_dsa"):
        p = os.path.join(home, ".ssh", nm)
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                out.append(p.replace("\\", "/"))
        except OSError:
            continue
    return out


def ensure_keypair(preferred: str = "") -> dict:
    """保证本机有一对可用密钥：优先用用户填的 → 其次自动探测 → 都没有就现场生成。

    返回 {"ok":bool, "key":<私钥>, "pub":<公钥>, "created":bool, "error":<str>}。
    生成的是 ed25519、无口令，落在 ~/.ssh/id_ed25519（权限 600），等价于
    ssh-keygen -t ed25519 -N ""；有 cryptography 就直接算，没有才退到 ssh-keygen 命令。
    """
    p = str(preferred or "").strip()
    if p:
        p = os.path.expanduser(p)
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                return {"ok": True, "key": p.replace("\\", "/"), "pub": (p + ".pub").replace("\\", "/"), "created": False}
        except OSError:
            pass
    det = detect_private_keys()
    if det:
        return {"ok": True, "key": det[0], "pub": det[0] + ".pub", "created": False}
    home = os.path.expanduser("~")
    d = os.path.join(home, ".ssh")
    key_path = os.path.join(d, "id_ed25519")
    try:
        os.makedirs(d, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
        made = False
        try:
            from cryptography.hazmat.primitives import serialization as _ser
            from cryptography.hazmat.primitives.asymmetric import ed25519 as _ed
            _k = _ed.Ed25519PrivateKey.generate()
            priv = _k.private_bytes(_ser.Encoding.PEM, _ser.PrivateFormat.OpenSSH, _ser.NoEncryption())
            pub = _k.public_key().public_bytes(_ser.Encoding.OpenSSH, _ser.PublicFormat.OpenSSH)
            with open(key_path, "wb") as fh:
                fh.write(priv)
            with open(key_path + ".pub", "wb") as fh:
                fh.write(pub + b" memomics@local\n")
            made = True
        except Exception:
            made = False
        if not made:
            import subprocess
            _r = subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", key_path, "-C", "memomics@local"],
                                capture_output=True, text=True)
            if _r.returncode != 0:
                return {"ok": False, "error": "生成密钥失败：%s" % ((_r.stderr or _r.stdout or "").strip() or "ssh-keygen 非 0 退出")}
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
    except Exception as exc:
        return {"ok": False, "error": "生成密钥失败：%s: %s" % (type(exc).__name__, exc)}
    return {"ok": True, "key": key_path.replace("\\", "/"), "pub": (key_path + ".pub").replace("\\", "/"), "created": True}


def install_pubkey(cfg: dict, node_name: str, password: str | None = None, *,
                   target_password: str | None = None,
                   gateway_password: str | None = None) -> str:
    """用密码登录一次，把本机公钥追加进远端 ~/.ssh/authorized_keys（幂等）。

    流程：解析节点（含 default_node/单节点兜底）→ 能密钥免密就直接报 already_ok
    → 否则密码登录（带 proxy_jump 的先连跳板再开 direct-tcpip 通道）→ 幂等追加
    公钥 → 立刻用纯密钥重连验证整条链路。

    ``password`` is the legacy single-password argument.  New callers must
    pass ``target_password`` and ``gateway_password`` independently: a target
    credential is never silently reused for a distinct gateway (nor vice
    versa).  Keeping the legacy positional fallback preserves the existing
    one-password WebUI endpoint until it can be retired safely.
    """
    # Deliberately resolve the old compatibility argument once, before any
    # connection attempt.  With either new keyword present, there is *no*
    # cross-hop fallback: two accounts may legitimately have different
    # passwords.
    _legacy_password = str(password or "")
    if target_password is None and gateway_password is None:
        target_password = _legacy_password
        gateway_password = _legacy_password
    else:
        target_password = str(target_password or "")
        gateway_password = str(gateway_password or "")

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
    _kp = ensure_keypair(str(node_cfg.get("key") or ""))
    if not _kp.get("ok"):
        return _err(str(_kp.get("error") or "无法准备本机 SSH 密钥"), node=name)
    key_path = _kp["key"]
    pub_path = _kp["pub"]
    created_note = ""
    if _kp.get("created"):
        created_note = "（本机原本没有密钥，已自动生成 %s）" % key_path
    if not os.path.exists(pub_path):
        return _err("私钥有了但公钥文件不在：%s（正常应是 %s.pub 同目录；删掉私钥重跑本操作可自动重建）"
                    % (pub_path, key_path), node=name)
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
                                             gateway_password, str(cfg.get("key") or ""))
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
            client, mode = _p_connect(paramiko, host, port, user, target_password, "", sock_factory=sock_factory)

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


# ---------------------------------------------------------------------------
# 常驻 R 会话（kernel 式持久化）—— 转发到 cluster_session 模块  2026-10-09
#
# 为什么挂在 remote_cluster 的动作位上、而不是再造一个工具：会话要和 push/pull/submit
# 共用同一套节点选择、SSH 引擎、体积闸门与账本；挂进来后 WebUI 控制台与 agent 自然走
# 同一条代码路径。重活仍归 run/submit，会话负责「读一次、一直用」的交互式分析。
# ---------------------------------------------------------------------------


def _action_session_start(cfg: dict, args: dict) -> str:
    from memomics.bio_tools import cluster_session as cs
    return cs.action_start(cfg, args)


def _action_session_exec(cfg: dict, args: dict) -> str:
    from memomics.bio_tools import cluster_session as cs
    return cs.action_exec(cfg, args)


def _action_session_save(cfg: dict, args: dict) -> str:
    from memomics.bio_tools import cluster_session as cs
    return cs.action_save(cfg, args)


def _action_session_restore(cfg: dict, args: dict) -> str:
    from memomics.bio_tools import cluster_session as cs
    return cs.action_restore(cfg, args)


def _action_session_status(cfg: dict, args: dict) -> str:
    from memomics.bio_tools import cluster_session as cs
    return cs.action_status(cfg, args)


def _action_session_stop(cfg: dict, args: dict) -> str:
    from memomics.bio_tools import cluster_session as cs
    return cs.action_stop(cfg, args)


def _action_session_list(cfg: dict, args: dict) -> str:
    from memomics.bio_tools import cluster_session as cs
    return cs.action_list(cfg, args)


def _action_session_cells(cfg: dict, args: dict) -> str:
    from memomics.bio_tools import cluster_session as cs
    return cs.action_cells(cfg, args)


def _action_session_plot(cfg: dict, args: dict) -> str:
    from memomics.bio_tools import cluster_session as cs
    return cs.action_plot(cfg, args)


# ---------------------------------------------------------------------------
# R 包清单（按节点 + env）—— 「按执行位置审查」的集群半边（2026-10-09）
#
# 用户实测事故：rail_review(pre) 只查**本机** R 包清单，本地缺 RUVSeq 就把**集群投递**硬拦了
# （"Missing packages: RUVSeq"），而 node4 的 R4.41 里其实装着。于是：
#   本地的任务查本地包、集群的任务查集群包、云平台单独标"没法在本地核实"。
# 这里负责集群侧的事实来源：一次 ssh 读全量包清单 → 本地缓存（默认 12h）→
# env_check(scope="cluster") 与 rail_review(location="cluster") 都吃它。
# 纯读：不装包、不改远端任何东西。
# ---------------------------------------------------------------------------

_PKGS_MARK = "#MM-PKGS v1"
_PKGS_TTL = 43200  # 12 小时（R 包变动不频繁；refresh=true 强制重读）
_PKGS_R_EXPR = ('ip <- rownames(installed.packages()); cat("%s\\n"); '
                'cat(paste(ip, collapse="\\n"), "\\n")') % _PKGS_MARK


def _pkgs_cache_dir() -> str:
    """缓存目录：跟 config.yaml 同一份 home（get_hermes_home 解析），别自己另起炉灶。"""
    try:
        return str(_get_config_path().parent / "remote" / "env_pkgs")
    except Exception:
        home = os.environ.get("HERMES_HOME") or os.environ.get("MEMOMICS_HOME")
        home = home or os.path.join(str(_memomics_root()), "memomics_home")
        return os.path.join(home, "remote", "env_pkgs")


def _pkgs_cache_file(node: str, env: str, rscript: str) -> str:
    def _safe(s) -> str:
        return (re.sub(r"[^A-Za-z0-9_.-]+", "_", str(s or "?")).strip("_") or "?")[:60]

    tag = _safe(env)
    if rscript:
        tag += "__" + _safe(os.path.basename(rscript))
    return os.path.join(_pkgs_cache_dir(), "%s__%s.json" % (_safe(node), tag))


def _pkgs_cache_read(path: str, ttl: int):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("packages"):
        return None
    if ttl and ttl > 0:
        try:
            age = time.time() - float(data.get("ts") or 0)
        except Exception:
            age = ttl + 1
        if age > ttl:
            return None
    return data


def _pkgs_cache_write(path: str, payload: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        logger.warning("R 包清单缓存写入失败：%s", path, exc_info=True)


def r_inventory(node: str = "", env: str = "", rscript: str = "", ttl: int = _PKGS_TTL,
                force: bool = False, cfg: dict = None) -> dict:
    """读某节点某 R 环境的**全量包清单**（一次 ssh；默认缓存 12 小时）。纯读动作。

    返回 {ok, node, env, rscript, r_version, count, packages[], checked_at, cached}；
    连不上/找不到 Rscript → ok=False + error + hint（调用方按"没法核实"处理，不要当成缺包）。
    """
    cfg = cfg or _load_remote_config()
    node_cfg, node_name, err = _select_node(cfg, node or "")
    if err:
        return {"ok": False, "node": node or "", "env": env,
                "error": "没有可用的节点（远端未配置或需要指定 node）", "hint": err}
    try:
        from memomics.bio_tools import cluster_session as cs
        sess = cs._session_cfg(cfg, node_cfg)
    except Exception:
        sess = dict(cfg.get("session") or {})
        cs = None
    env = str(env or sess.get("env") or "R4.41").strip()
    rscript = str(rscript or "").strip()
    node_label = node_name or str(node_cfg.get("host") or "")
    cache_path = _pkgs_cache_file(node_label, env, rscript)
    if not force:
        hit = _pkgs_cache_read(cache_path, ttl)
        if hit:
            out = dict(hit)
            out.update({"ok": True, "cached": True, "node": node_label, "env": env})
            return out
    try:
        conn = _get_conn(node_cfg)
        probe = cs._probe_rscript(conn, sess, env, rscript) if cs else {"ok": False}
    except Exception as exc:
        return {"ok": False, "node": node_label, "env": env,
                "error": "连不上节点或探测 Rscript 失败：%s" % exc,
                "hint": "先用 action='nodes' 看节点连通性；或 action='check' 看环境"}
    if not probe.get("ok"):
        return {"ok": False, "node": node_label, "env": env, "rscript": "",
                "error": "节点 %s 上没找到可用的 Rscript（env=%s）" % (node_label, env),
                "hint": ("用 action='check' 看节点上有什么；或显式给 rscript=<绝对路径>"
                         "（conda 环境一般长这样 <root>/envs/<env>/bin/Rscript）")}
    found = str(probe.get("rscript") or "")
    cmd = "%s -e '%s'" % (shlex.quote(found), _PKGS_R_EXPR)
    res = cs._exec_full(conn, cmd, timeout=240)
    out = str(res.get("output") or "")
    pkgs, seen_mark = [], False
    for line in out.splitlines():
        line = line.strip()
        if not seen_mark:
            if line == _PKGS_MARK:
                seen_mark = True
            continue
        if line and not line.startswith(">"):
            pkgs.append(line)
    if not seen_mark or not pkgs:
        return {"ok": False, "node": node_label, "env": env, "rscript": found,
                "error": "R 包清单读取失败（Rscript 没吐出预期输出）", "raw": _truncate(out, 400),
                "hint": "跑 action='run' + command='%s -e \"rownames(installed.packages())\"' 手查" % found}
    payload = {"node": node_label, "env": env, "rscript": found,
               "r_version": str(probe.get("version") or ""),
               "count": len(set(pkgs)), "packages": sorted(set(pkgs)),
               "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "ts": time.time()}
    _pkgs_cache_write(cache_path, payload)
    out = dict(payload)
    out.update({"ok": True, "cached": False})
    return out


def r_inventory_for_check(node: str = "", env: str = "", rscript: str = "",
                          ttl: int = _PKGS_TTL, force: bool = False):
    """给 env_check / rail_review 用的薄封装（同一份缓存与解析）。"""
    return r_inventory(node=node, env=env, rscript=rscript, ttl=ttl, force=force)


def r_packages_check(node: str = "", env: str = "", rscript: str = "", packages=None,
                     refresh: bool = False, full: bool = False, ttl: int = _PKGS_TTL,
                     cfg: dict = None) -> dict:
    """判定一批包在**集群**上有没有（供工具与门禁共用，返回 dict 不是 JSON 串）。

    语言歧义保护：不在 R 清单里的名字，如果看着像 Python 包（env_check 的 Python 名单里），
    归到 unverified 而不是 missing —— 集群 Python 环境这一层还没接，不能拿 R 清单判它。
    """
    inv = r_inventory(node=node, env=env, rscript=rscript, ttl=ttl, force=refresh, cfg=cfg)
    if not inv.get("ok"):
        out = {"status": "error", "node": inv.get("node") or node, "env": inv.get("env") or env,
               "error": inv.get("error") or "R 包清单读取失败",
               "hint": inv.get("hint") or "", "packages": [], "count": None,
               "missing": [], "installed": [], "unverified": []}
        return out
    pkgs = set(inv.get("packages") or [])
    try:
        from memomics.bio_tools import env_check as _ec
        py_names = {str(n).lower() for n in _ec.PYTHON_PACKAGES_BIO}
    except Exception:
        py_names = set()
    installed, missing, unverified = [], [], []
    for p in (packages or []):
        name = str(p).strip()
        if not name:
            continue
        if name in pkgs:
            installed.append(name)
        elif name.lower() in py_names:
            unverified.append(name)
        else:
            missing.append(name)
    out = {"status": "ok", "node": inv.get("node"), "env": inv.get("env"),
           "rscript": inv.get("rscript"), "r_version": inv.get("r_version"),
           "count": inv.get("count"), "checked_at": inv.get("checked_at"),
           "cached": inv.get("cached"), "installed": sorted(installed),
           "missing": sorted(missing), "unverified": sorted(unverified)}
    if full:
        out["packages"] = inv.get("packages")
    else:
        out["note"] = "只回判定结果；要看全量清单加 full=true（共 %s 个包）" % (inv.get("count") or 0)
    return out


def _action_r_packages(cfg: dict, args: dict) -> str:
    res = r_packages_check(
        node=str(args.get("node") or ""), env=str(args.get("env") or ""),
        rscript=str(args.get("rscript") or ""), packages=args.get("packages") or [],
        refresh=bool(args.get("refresh")), full=bool(args.get("full")), cfg=cfg)
    if res.get("status") != "ok":
        return _err(res.get("error") or "R 包清单读取失败", node=res.get("node") or "",
                    env=res.get("env") or "", hint=res.get("hint") or "")
    return _ok(res)


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
    # 常驻 R 会话（kernel 式持久化）—— 转发到 cluster_session 模块，见下方转发函数
    "session_start": _action_session_start,
    "session_exec": _action_session_exec,
    "session_save": _action_session_save,
    "session_restore": _action_session_restore,
    "session_status": _action_session_status,
    "session_stop": _action_session_stop,
    "session_list": _action_session_list,
    "session_cells": _action_session_cells,
    "session_plot": _action_session_plot,
    # 集群侧 R 包清单（rail_review 按位置审查用；也用来回答「集群上有没有这个包」）
    "r_packages": _action_r_packages,
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
                "（⚙️ 配置 → 节点行的跳板机框，填 用户名@登录口IP，如 user@login-host），"
                "让登录口去解析它。")
    if "banner" in text or "unknown port 65535" in text:
        return ("走跳板的连接在跳板那一跳就断了（banner 超时 / UNKNOWN port 65535 的典型表现）——"
                "九成是跳板（登录口%s）上还没有我们的公钥，密钥认证被拒，管道随之中断。"
                "先去 ⚙️ 配置 → 输密码 → 点「🔑 安装公钥」（会自动把跳板一并装上），装完再自检。"
                % (" " + jump if jump else ""))
    if "permission denied" in text:
        return ("对方拒绝了密钥认证——公钥还没装到%s，或私钥路径指错。"
                "先在 ⚙️ 配置里输密码点一次「🔑 安装公钥」——本机没有密钥也不用管，会自动生成（ed25519）并装好。"
                % ("跳板或目标节点" if jump else "目标节点"))
    if "connection refused" in text:
        return "对方端口拒接：检查节点的 host / port 是否填对（sshd 是否在这个端口上）。"
    if "timed out" in text or "timeout" in text:
        return "连接超时：检查 IP / 端口 / 网络（要不要连 VPN），或跳板地址是否填对。"
    return "连接类错误先用 action='nodes' 体检全部节点（或 action='check' 单节点）：密钥/端口/跳板机/known_hosts"


def remote_cluster_handler(args=None, **kwargs) -> str:
    args = dict(args or {})
    # This key is an internal exact-record hand-off from the selector below.
    # Never let a REST/browser/model payload forge it to steer logs/status or a
    # cancellation toward a different historical job.
    args.pop(_INTERNAL_SELECTED_JOB_RECORD, None)
    cfg = _load_remote_config()
    action = str(args.get("action") or "").strip().lower()
    # REST callers supply chat_session_id; agent tool calls use the propagated
    # ContextVar.  Neither path uses a process-global active server.
    chat_session_id = str(args.get("chat_session_id") or "").strip()
    if not chat_session_id:
        chat_session_id = _current_agent_session()
    if action == "locate":
        # 路径判定：用户没说文件在哪时先用它查（远端没配也能用，只报本地那一半）
        try:
            return _action_locate(cfg, args)
        except Exception as exc:
            logger.exception("remote_cluster action=locate 失败")
            return _err("locate 执行失败: %s" % exc)
    if action not in _ACTIONS:
        return _err("未知 action: %r（可选：%s）" % (action, ", ".join(sorted(_ACTIONS))))

    if action == "session_list":
        # 只看本机账本（列有哪些会话），不需要连节点
        try:
            from memomics.bio_tools import cluster_session as _cs
            return _cs.action_list(cfg, args)
        except Exception as exc:
            logger.exception("remote_cluster action=session_list 失败")
            return _err("session_list 执行失败: %s" % exc)

    recorded_target = False
    recorded_snapshot = None
    if action.startswith("session_") and action != "session_start":
        # 会话动作默认跟随会话记录里的节点（否则会落到 default_node 上连错机器）
        args = dict(args)
        try:
            from memomics.bio_tools import cluster_session as _cs
            sid = str(args.get("session_id") or "").strip()
            rec = _cs.find_session(sid) if sid else _cs.latest_session()
            if rec:
                # A persisted daemon is a durable remote resource.  Its own
                # snapshot is authoritative even if a caller supplied a
                # different node after the chat was rebound.
                args["node"] = str(rec.get("node") or rec.get("server_id") or "")
                recorded_target = True
                recorded_snapshot = dict(rec)
            elif not sid:
                return _err(
                    "本机账本里还没有任何常驻会话，没法定位到节点。",
                    hint=("用 action='session_list' 看全部会话；要新建用 "
                          "action='session_start'（可带 input=<大 rds 路径>，读一次一直用）。"))
        except Exception:
            pass

    # A submitted job is also a durable remote resource.  Its status, logs and
    # cancellation must go back to its recorded node even after a user changes
    # the chat session's default binding.
    recorded_job_snapshot = None
    if action in ("status", "logs", "cancel"):
        job_id = str(args.get("job_id") or "").strip()
        if job_id:
            requested_target = str(args.get("node") or args.get("host") or "").strip()
            recorded_job_snapshot, selection_error = _select_recorded_job_snapshot(
                job_id, requested=requested_target, chat_session_id=chat_session_id,
            )
            if selection_error:
                return selection_error
            if recorded_job_snapshot:
                owner = str(recorded_job_snapshot.get("node") or
                            recorded_job_snapshot.get("server_id") or "")
                if owner:
                    args["node"] = owner
                # The action must consume this exact full-ledger selection,
                # not independently re-resolve a shorter recent-job window.
                args[_INTERNAL_SELECTED_JOB_RECORD] = dict(recorded_job_snapshot)
                recorded_target = True

    resource_snapshot = recorded_snapshot or recorded_job_snapshot
    has_reconnectable_snapshot = bool(
        resource_snapshot and str(resource_snapshot.get("host") or "").strip()
    )
    # Historical jobs and R daemons remain operable from their complete local
    # snapshot after their profile is deleted.  New work still requires an
    # enabled, currently configured server.
    if not remote_cluster_enabled() and not has_reconnectable_snapshot:
        return _err(
            "远端集群未配置或未启用。请在 memomics_home/config.yaml 的 remote: 段配置，两种写法任选：\n"
            "① 单节点：\n  enabled: true\n  host: <登录节点>\n  user: <用户名>\n"
            "  key: <私钥路径>\n  workdir: <远端工作目录>\n"
            "② 多节点（命名节点，用 node= 选机器）：\n  enabled: true\n  user: <用户名>\n"
            "  key: <私钥路径>\n  workdir: <共享工作目录>\n  nodes:\n    node1: {}\n    node2: {}\n"
            "（或用环境变量 MEMOMICS_REMOTE_ENABLED/HOST/USER/KEY/WORKDIR 临时覆盖）"
        )
    if action == "nodes":
        # 体检所有节点，不需要先选定一个
        try:
            return _action_nodes(cfg, args)
        except Exception as exc:
            logger.exception("remote_cluster action=nodes 失败")
            return _err("nodes 执行失败: %s" % exc)

    requested = str(args.get("node") or args.get("host") or "").strip()
    if has_reconnectable_snapshot:
        # A persisted R daemon owns a complete connection snapshot.  It must
        # remain reachable even after its profile was renamed, edited, or
        # removed from remote.nodes.
        node_cfg = _apply_connection_snapshot(cfg, resource_snapshot)
        node_name = str(resource_snapshot.get("server_id") or resource_snapshot.get("node") or
                        requested or node_cfg.get("host") or "")
        node_cfg["_name"] = node_name
        err = None
    else:
        node_cfg, node_name, err = select_node_for_session(
            cfg, requested, chat_session_id, recorded_target=recorded_target
        )
    if err:
        return err
    # Cluster touch evidence is written only after final target resolution;
    # chat_session_id is attribution only and never constrains the selected
    # profile.
    touch_session(node_name, action, session_id=chat_session_id)
    args["node"] = node_name
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
        "  • session_start / session_exec / session_save / session_restore / session_status / "
        "session_stop / session_list / session_cells / session_plot —— **常驻 R 会话（kernel 式持久化）**，"
        "专治「大输入读一次一直用」：\n"
        "      session_start 在节点上起一个常驻 R 进程（setsid 常驻，ps/MobaXterm 里看得见，不开公网端口）；"
        "带 input=<大 rds 路径> 就先**同步读一次**进内存（读了几秒、对象名、readRDS 审计都会回报）。\n"
        "      随后 session_exec 投 R 代码（同一个进程、同一个 globalenv）：FindMarkers / CellChat / "
        "参数扫描都复用内存对象，**不再回读原文件**（结果头部的 readrds_calls 可以验证）。\n"
        "      session_save 落检查点（ckpt/<名>.rds）、session_restore 拉回来（daemon 死掉/换节点后用 "
        "session_start + restore='latest' 恢复，不必重读原文件）；session_status 看 pid/内存/对象/队列；"
        "session_stop 退出（save=true 先存检查点）；session_list 列本机账本（live=true 逐台核实）。\n"
        "      要点：① 长命令（FindMarkers 几分钟）用 async=true 投递，再用 session_status 查，别让 ssh 干挂；"
        "② 会话内可调 mm_info() / mm_reads() / mm_save() / mm_restore() / mm_quit()；"
        "③ 铁规 10 的大输入流程：用户要求开常驻会话本身就是在回答「要不要持久化」（工具会自动落标记），"
        "但**别在用户拒绝持久化时偷偷开会话**；④ 会话占内存，用完记得 session_stop。\n"
        "      session_cells / session_plot 是 **Notebook 总端**用的读侧：session_cells 一次拉回最近 N 个 cell"
        "（代码 + 输出尾 + 状态 + 图清单），session_plot 把 plots/ 里的一张图按 base64 取回来内联显示。"
        "会话里画的图会自动抓成 plots/<请求号>_NN.png（默认设备改写，一个顶层表达式一张）。\n"
        "  • locate —— **判定一个路径在本地还是在集群上**（用户没说数据在哪时先跑这个，再决定在哪儿算）；"
        "远端没配置时也能用，只报本地那一半。\n"
        "  • r_packages —— **查集群上的 R 包**（不是本机！）：一次 ssh 读目标节点/env 的全量包清单"
        "（缓存 12 小时，refresh=true 强制重读），给了 packages=[...] 就报 installed/missing。"
        "用途：决定「这个包集群上有没有」、以及 rail_review(location='cluster') 的包审查依据。"
        "**别拿本机包清单去判集群任务**（本地缺 ≠ 集群缺——实测本地缺 RUVSeq 曾把投递硬拦，"
        "而 node4 的 R4.41 里是有的）。\n"
        "  • nodes  —— 列配置里的所有节点，逐个探连通性 + 负载（谁空着、谁连不上）；"
        "不指定节点也能调用。\n"
        "【用哪个节点】config 的 remote.nodes 里配了多个命名节点（如 node1/node2）时，"
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
        "【大输入硬闸（铁规 10）】run/submit 的命令文本里若出现 ≥100MB 的远端数据文件"
        "（.rds/.h5ad/.bam/大表格等扩展名的绝对路径）且账本里没有它的任务标记 → 返回 "
        "status=needs_persist 拒绝执行（命令不会跑）。过闸三步："
        "① large_cache scan --remote --node <节点> <路径>（查体积）→ ② ask_user 弹窗问要不要持久化"
        "（必须问，不许替用户答）→ ③ large_cache mark --remote 落标记（用户拒绝也落，note 注明）→ 重发。"
        "纯巡检命令（ls/stat/du/head 开头的行）不触发；config 的 persist_gate: false 可关（不推荐）。\n"
        "【产物分工】集群上只留大文件（原始数据/中间产物/BAM/FASTQ/大矩阵/模型权重），不要往本机拉；"
        "表格/图/脚本/日志这类小产物必须 pull 回本地 results/<会话>/，否则 WebUI 里看不到"
        "（WebUI 只浏览 work/ 和 results/）。判断标准："
        ".csv/.tsv/.xlsx/.png/.pdf/.svg/.R/.py/.log 这类（KB~几十 MB）→ 拉回来；"
        "超过 max_mb（默认 512MB）工具会返回 status=too_large 并拒绝，"
        "**这时先问用户要不要拉**，确认了再带 max_mb 或 allow_large=true。"
        "pull 支持通配符（远端 *.tsv 会展开成多个文件，放进 local_path 目录）和目录（递归）；"
        "默认不覆盖本机已有同名文件（返回 status=exists，给 overwrite=true 才覆盖）。\n"
        "连接配置在 memomics_home/config.yaml 的 remote: 段（host 或 nodes /user/port/key/workdir/"
        "scheduler/local_root/remote_root）。目录管理连接使用本机加密保存的密码；旧版手工配置仍使用 "
        "BatchMode 密钥登录，均不会弹出浏览器密码输入；未配置时本工具不可见。\n"
        "⚠️ 两点别搞混：① 本工具只把**命令/作业/会话请求**送到远端；execute_python / execute_r 的持久内核仍在本地跑——"
        "要在集群上做**交互式分析**（读一次大 rds 后反复 FindMarkers / CellChat / 调参）用 session_*，"
        "一次性重活写成脚本交给 run/submit；② 远端路径（/home/you/...）与本地路径（E:/...）是两套，"
        "push/pull 可用 local_root/remote_root 自动换算。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["locate", "nodes", "check", "run", "push", "pull", "submit", "status",
                         "logs", "cancel", "jobs",
                         "session_start", "session_exec", "session_save", "session_restore",
                         "session_status", "session_stop", "session_list",
                         "session_cells", "session_plot", "r_packages"],
                "description": "要执行的动作",
            },
            "node": {
                "type": "string",
                "description": ("用哪个远端节点（remote.nodes 里配置的名字，如 node1/node2）。"
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
                                     "logs：直接指定远端日志文件路径；"
                                     "session_plot：要取的图（相对会话目录，如 plots/<请求号>_01.png，"
                                     "只能是会话目录内的 png/jpg/svg/pdf）")},
            "lines": {"type": "integer", "description": "logs：看末尾多少行（默认 100）"},
            "limit": {"type": "integer",
                      "description": "session_cells：拉回最近多少个 cell（默认 12，上限 60）"},
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
            "session_id": {"type": "string",
                           "description": ("session_exec/save/restore/status/stop：会话号（可省 = 该节点最近一个会话）。"
                                           "session_start 时传它 = 复用同一会话目录（配 restore 可把旧对象拉回来）。")},
            "code": {"type": "string",
                     "description": "session_exec：要执行的 R 代码（可多行；在会话的同一个进程里跑）"},
            "input": {"type": "string",
                      "description": ("session_start：要读一次的大文件（rds 等）。给了它就先同步读入内存，"
                                      "之后所有分析复用（这就是「读一次一直用」）；省略 = 起一个空会话。")},
            "object": {"type": "string",
                       "description": "session_start：读入后的对象名（默认按文件名推导，如 musc）"},
            "env": {"type": "string",
                    "description": ("session_start：conda 环境名（默认 remote.session.env；本集群 RNA 用 R4.41，"
                                    "ATAC 用 R4.3.3）——按 <roots>/envs/<env>/bin/Rscript 去找 Rscript。")},
            "rscript": {"type": "string",
                        "description": "session_start：Rscript 绝对路径（覆盖自动探测；自己 env 里的 R 用这个）"},
            "restore": {"type": "string",
                        "description": ("session_start：从检查点恢复（'latest' = 最新一个，也可给 ckpt 里的名字）。"
                                        "daemon 死后/换节点时把对象拉回来，不用重读原文件。")},
            "name": {"type": "string",
                     "description": ("session_save：检查点名（默认时间戳）；"
                                     "session_restore：检查点路径或名字（默认最新）")},
            "objects": {"type": "array", "items": {"type": "string"},
                        "description": "session_save：要保存的对象名列表（默认全部会话对象）"},
            "wait": {"type": "integer",
                     "description": ("session_exec/save/restore：等待秒数（默认 session.wait=1200；"
                                     "save 用 save_wait=3600）。async=true 时忽略（投递即返回）。")},
            "async": {"type": "boolean",
                      "description": ("session_exec/save：true = 投递后立即返回（长任务推荐），"
                                      "之后用 session_status 查进度；结果文件在 done/<req>.res.txt。")},
            "title": {"type": "string", "description": "session_start：会话标题（默认 input 文件名）"},
            "save": {"type": "boolean",
                     "description": "session_stop：true = 退出前先落检查点（大对象会慢；保住工作成果用）"},
            "live": {"type": "boolean",
                     "description": "session_list：true = 逐台连上去核实进程真的活着（慢，但最准）"},
            "packages": {"type": "array", "items": {"type": "string"},
                         "description": ("r_packages：要看哪几个包在不在集群（如 [\"RUVSeq\",\"CellChat\"]）；"
                                         "不传 = 只回报全量包数量。R 清单判不了的名字（像 Python 包）"
                                         "会进 unverified，不会误报 missing。")},
            "refresh": {"type": "boolean",
                        "description": "r_packages：true = 忽略 12 小时缓存，重新 ssh 读一遍包清单"},
            "full": {"type": "boolean",
                     "description": "r_packages：true = 连全量包名一起返回（默认只回数量与判定结果）"},
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
