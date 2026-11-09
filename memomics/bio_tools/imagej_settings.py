# -*- coding: utf-8 -*-
"""ImageJ 端点配置 + 会话级开关 + 每回合注入块（2026-11-09）

三件事：
1. **端点配置**（`memomics_home/imagej.json`）：本机 ImageJ 路径 / 集群集群名+节点+安装目录。
2. **会话开关**：某个会话是否"启用 ImageJ"。前端输入框下方那个按钮就是改这个。
3. **注入块**：server 每个用户回合重新读一次配置与开关（不缓存整段），生成给模型的
   system 片段——上下文再长也不会"忘记"ImageJ 怎么调；关掉就不注入。

设计约束（都是用户明确的）：
- 没配路径 → 前端提示先设置，不静默失败；
- 集群必须先连上（remote_cluster 可达）才算 ready；
- 本地电脑也要能跑（ImageJ.exe / ij.jar + java 两种启动方式都认）。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("memomics.imagej_settings")

_THIS = Path(__file__).resolve()
_REPO = _THIS.parents[2]


def _home() -> Path:
    env = os.environ.get("HERMES_HOME") or os.environ.get("MEMOMICS_HOME")
    if env and Path(env).is_dir():
        return Path(env)
    return _REPO / "memomics_home"


CONFIG_PATH = _home() / "imagej.json"

DEFAULTS: dict = {
    "local": {
        "root": "",          # 例如 E:\ImageJ 或 C:\Fiji.app
        "launcher": "",      # 留空自动找 ImageJ.exe / Fiji.exe / ij.jar
        "java": "",          # 留空用 <root>/jre/bin/java.exe 或 PATH 里的 java
        "upload_dir": "",    # 本机图片上传目录；空 = webui/uploads/imagej
        "save_dir": "",      # 本地结果根目录；空 = results/<会话>/imagej
    },
    "cluster": {
        "name": "",          # remote.clusters 里的集群名（空=默认集群）
        "node": "",          # 节点名（空=该集群 default_node）
        "root": "",          # 远端 ImageJ 目录；空=让工具按配置/默认值探测
        "save_dir": "",      # 集群作业/产物根目录；空 = <workdir>/ij_runs（运行时自动创建）
    },
    "sessions": {},          # {session_id: {"enabled": true, "ts": "..."}}
    "probes": {"local": {}, "cluster": {}},  # 用户点「检测」后缓存的插件/版本信息（不含凭据）
    "updated_at": "",
}

_EXE_CANDIDATES = ("ImageJ.exe", "ImageJ-win64.exe", "Fiji.exe", "fiji-windows-x64.exe", "ImageJ-win32.exe")


# ---------------------------------------------------------------------------
# 读写
# ---------------------------------------------------------------------------
def ensure_home_env() -> None:
    """没有 HERMES_HOME 时兜底指向仓库 memomics_home（remote_cluster 要它来找集群配置）。"""
    try:
        if not os.environ.get("HERMES_HOME"):
            h = _home()
            if h.is_dir():
                os.environ["HERMES_HOME"] = str(h)
    except Exception:
        pass


def load() -> dict:
    ensure_home_env()
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        if CONFIG_PATH.is_file():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in ("local", "cluster"):
                    if isinstance(data.get(key), dict):
                        cfg[key].update(data[key])
                if isinstance(data.get("sessions"), dict):
                    cfg["sessions"] = data["sessions"]
                if isinstance(data.get("probes"), dict):
                    for backend in ("local", "cluster"):
                        if isinstance(data["probes"].get(backend), dict):
                            cfg["probes"][backend] = data["probes"][backend]
                cfg["updated_at"] = data.get("updated_at", "")
    except Exception as exc:
        logger.warning("读取 imagej.json 失败：%s", exc)
    return cfg


def save(patch: dict | None = None) -> dict:
    cfg = load()
    patch = patch or {}
    for key in ("local", "cluster"):
        if isinstance(patch.get(key), dict):
            for k, v in patch[key].items():
                if v is None:
                    continue
                cfg[key][k] = str(v).strip()
    if isinstance(patch.get("sessions"), dict):
        cfg["sessions"].update(patch["sessions"])
    if isinstance(patch.get("probes"), dict):
        for backend in ("local", "cluster"):
            if isinstance(patch["probes"].get(backend), dict):
                cfg["probes"][backend] = patch["probes"][backend]
    # 用户明确设置的目录在保存时就创建；空目录沿用应用默认值
    for key in ("upload_dir", "save_dir"):
        raw_dir = str((cfg.get("local") or {}).get(key) or "").strip()
        if raw_dir:
            Path(raw_dir).expanduser().mkdir(parents=True, exist_ok=True)
    cfg["updated_at"] = datetime.now().isoformat(timespec="seconds")
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)
    return cfg


# ---------------------------------------------------------------------------
# 会话开关
# ---------------------------------------------------------------------------
def set_session(session_id: str, enabled: bool) -> dict:
    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("缺少 session_id")
    cfg = load()
    sessions = cfg.get("sessions") or {}
    sessions[sid] = {"enabled": bool(enabled), "ts": datetime.now().isoformat(timespec="seconds")}
    # 只保留最近 200 个会话，避免文件无限长
    if len(sessions) > 200:
        keep = sorted(sessions.items(), key=lambda kv: kv[1].get("ts", ""))[-200:]
        sessions = dict(keep)
    cfg["sessions"] = sessions
    save({"sessions": sessions})
    return {"session_id": sid, "enabled": bool(enabled)}


def session_enabled(session_id: str) -> bool:
    sid = str(session_id or "").strip()
    if not sid:
        return False
    return bool(((load().get("sessions") or {}).get(sid) or {}).get("enabled"))


def _record_probe(backend: str, info: dict) -> None:
    """保存最近一次真实探测结果，供提示词读取；不在每回合发起 SSH。"""
    try:
        cfg = load()
        probes = cfg.get("probes") or {}
        allowed = ("ok", "root", "kind", "launcher", "java", "plugins", "bioformats",
                   "plugin_jars", "node", "cluster", "runner")
        probes[backend] = {k: info.get(k) for k in allowed if k in info}
        probes[backend]["probed_at"] = datetime.now().isoformat(timespec="seconds")
        save({"probes": probes})
    except Exception as exc:
        logger.warning("缓存 ImageJ 探测结果失败：%s", exc)


# ---------------------------------------------------------------------------
# 探测
# ---------------------------------------------------------------------------
def probe_local(root: str = "", launcher: str = "", java: str = "") -> dict:
    """看本机 ImageJ 是否可用：ImageJ.exe / Fiji.exe / ij.jar + java。"""
    cfg = load()["local"]
    root = str(root or cfg.get("root") or "").strip()
    launcher = str(launcher or cfg.get("launcher") or "").strip()
    java = str(java or cfg.get("java") or "").strip()
    out: dict = {"ok": False, "root": root, "kind": "", "launcher": "", "java": "", "error": "",
                 "plugins": [], "bioformats": False, "version": ""}
    if not root:
        out["error"] = "未设置本机 ImageJ 路径"
        return out
    rp = Path(root)
    if not rp.is_dir():
        out["error"] = f"路径不存在：{root}"
        return out

    exe = ""
    cands = [launcher] if launcher else list(_EXE_CANDIDATES)
    for name in cands:
        if not name:
            continue
        p = rp / name
        if p.is_file():
            exe = str(p)
            break
    jar = rp / "ij.jar"

    if exe:
        out.update(kind="exe", launcher=exe, ok=True)
        jre = rp / "jre" / "bin" / "java.exe"
        if jre.is_file():
            out["java"] = str(jre)
    elif jar.is_file():
        j = java or str(rp / "jre" / "bin" / "java.exe")
        if not Path(j).is_file():
            j = shutil.which("java") or ""
        if not j:
            out["error"] = "找到 ij.jar，但没找到 java（可在设置里指定 java.exe）"
            return out
        out.update(kind="jar", launcher=str(jar), java=str(j), ok=True)
    else:
        out["error"] = "目录里没有 ImageJ.exe / Fiji.exe / ij.jar"
        return out

    plugins = []
    pdir = rp / "plugins"
    if pdir.is_dir():
        try:
            plugins = sorted([p.name for p in pdir.iterdir() if p.is_file()])[:40]
        except Exception:
            plugins = []
    out["plugins"] = plugins
    out["bioformats"] = any("bioformats" in n.lower() for n in plugins)
    _record_probe("local", out)
    return out


def probe_cluster(name: str = "", node: str = "", root: str = "") -> dict:
    """集群侧是否可用：先看 remote_cluster 通不通，再看 ImageJ 目录/启动器。"""
    cfg = load()["cluster"]
    name = str(name or cfg.get("name") or "")
    node = str(node or cfg.get("node") or "")
    root = str(root or cfg.get("root") or "")
    out: dict = {"ok": False, "cluster": name, "node": node, "root": root, "error": "",
                 "java": "", "launcher": False, "runner": False, "bioformats": False,
                 "plugin_jars": []}
    ensure_home_env()
    try:
        from . import remote_cluster as rc
    except Exception as exc:
        out["error"] = f"remote_cluster 不可用：{exc}"
        return out

    enabled = False
    try:
        enabled = bool(rc.remote_cluster_enabled())
    except Exception:
        enabled = False
    if not enabled:
        out["error"] = "还没配置/连上集群（先到「集群」里连接）"
        return out

    # 用 nodes 动作探活（一次 ssh，顺带拿 ImageJ 状态）
    try:
        raw = rc.remote_cluster_handler({"action": "nodes"})
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        if data.get("status") != "ok":
            out["error"] = str(data.get("error") or "集群连接失败")[:200]
            return out
        nodes = data.get("nodes") or []
        pick = None
        if node:
            pick = next((n for n in nodes if n.get("name") == node), None)
        if pick is None:
            pick = next((n for n in nodes if n.get("reachable")), None)
        if pick is None:
            out["error"] = "集群里没有可达节点"
            return out
        out["node"] = pick.get("name") or node
        if not root:
            probe = rc.remote_cluster_handler  # noqa: F841  (仅占位，root 由 imagej 工具兜底)
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"集群探活失败：{exc}"
        return out

    # 用 imagej 工具自己的 probe（它知道 root/runner/xvfb/插件）
    try:
        from . import imagej_analysis as ij
        info = ij.probe(out["node"] or "", refresh=False, root=root)
        out.update(root=info.get("root") or root, java=info.get("java") or "",
                   launcher=bool(info.get("launcher")), runner=bool(info.get("runner")),
                   bioformats=bool(info.get("bioformats")),
                   plugin_jars=list(info.get("plugin_jars") or []))
        out["ok"] = bool(info.get("imagej_ready"))
        if not out["ok"]:
            out["error"] = "集群侧 ImageJ 未就绪（缺 ij.jar/launcher/Xvfb）"
    except Exception as exc:
        out["error"] = f"集群 ImageJ 探测失败：{exc}"
    _record_probe("cluster", out)
    return out


def status(session_id: str = "") -> dict:
    cfg = load()
    local_cfg = cfg.get("local") or {}
    cluster_cfg = cfg.get("cluster") or {}
    configured = bool(local_cfg.get("root")) or bool(cluster_cfg.get("root")) or bool(cluster_cfg.get("name"))
    return {
        "configured": configured,
        "session_id": str(session_id or ""),
        "enabled": session_enabled(session_id),
        "local": {"root": local_cfg.get("root", ""), "configured": bool(local_cfg.get("root"))},
        "cluster": {"name": cluster_cfg.get("name", ""), "node": cluster_cfg.get("node", ""),
                    "root": cluster_cfg.get("root", ""), "configured": bool(cluster_cfg.get("name") or cluster_cfg.get("root"))},
        "updated_at": cfg.get("updated_at", ""),
    }


# ---------------------------------------------------------------------------
# 每回合注入块
# ---------------------------------------------------------------------------
def _method_catalog() -> list[tuple[str, str]]:
    """实时读取 op 目录；新增/删除方法后下一回合立即反映。"""
    out: list[tuple[str, str]] = []
    base = _REPO / "scripts" / "ij" / "ops"
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        p = d / "op.json"
        if not p.is_file():
            continue
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
            if meta.get("status") == "ready":
                out.append((str(meta.get("id") or d.name), str(meta.get("name") or "")))
        except Exception:
            continue
    return out


def prompt_block(session_id: str = "") -> str:
    """开关只控制当前会话；每回合重新读取路径、插件快照和方法目录。"""
    sid = str(session_id or "").strip()
    if not sid or not session_enabled(sid):
        return ""
    cfg = load()
    local = cfg.get("local") or {}
    cluster = cfg.get("cluster") or {}
    if not (local.get("root") or cluster.get("root") or cluster.get("name")):
        return ("## ImageJ（本会话已启用，但还没配置路径）\n"
                "请提示用户到左侧「设置 → ImageJ 图像分析」填本机 ImageJ 路径或选择集群节点；"
                "不要猜路径，也不要跳过 ImageJ 改用别的工具。")

    probes = cfg.get("probes") or {}
    lines = ["## ImageJ（本会话已开启：提示词 + 路径 + 插件 + 方法，每回合刷新）", ""]
    if local.get("root"):
        lines.append(f'''- 本机路径：`{local['root']}`；调用 `imagej(backend="local", ...)`''')
        lp = probes.get("local") or {}
        if lp.get("root") == local.get("root") and lp.get("plugins"):
            lines.append("  本机插件：" + ", ".join(str(x) for x in lp["plugins"][:12]))
    if cluster.get("root") or cluster.get("name"):
        lines.append(f'''- 集群：cluster={cluster.get('name') or '默认'}，node={cluster.get('node') or '默认'}，'''
                     f'''路径=`{cluster.get('root') or '按配置'}`；调用 `imagej(backend="cluster", ...)`''')
        cp = probes.get("cluster") or {}
        if cp.get("plugin_jars"):
            lines.append("  集群插件：" + ", ".join(str(x) for x in cp["plugin_jars"][:12]))
        if cp.get("bioformats"):
            lines.append("  集群 Bio-Formats：已装（厂商原生格式可用 bf_convert 转 TIFF）")

    if (local.get("upload_dir") or local.get("save_dir")):
        lines.append(f"- 本机上传目录：`{local.get('upload_dir') or 'webui/uploads/imagej'}`；"
                     f"结果目录：`{local.get('save_dir') or 'results/<会话>/imagej'}`")
    if cluster.get("save_dir"):
        lines.append(f"- 集群作业/保存目录：`{cluster['save_dir']}`（不存在时自动创建）")

    methods = _method_catalog()
    lines += ["", '可用方法（用 `imagej(action="ops")` 看参数）：']
    if methods:
        lines += [f"- `{op}`：{name}" for op, name in methods]
    else:
        lines.append("- 当前未发现 op，先检查 scripts/ij/ops 是否完整")
    lines += [
        "",
        "执行规则：",
        "1. 图像定量/宏执行走 `imagej` 工具，不用 Python/PIL 复刻阈值、分水岭、颗粒分析。",
        "2. 先 `probe`，再 `ops`；数据在本机用 backend=local，在集群用 backend=cluster。",
        "   本机/已上传图片可直接作为 input；选 cluster 时工具自动 SFTP 上传，用户无需先手动传集群。",
        "3. 参数先单图 `run` 验收 outlines.png / 指标，再 `batch`；报告给 manifest.json 路径。",
        "4. 未配置/未连接时直接给出可执行提示，不猜路径；关闭右下角 ImageJ 后本块不再注入。",
    ]
    return "\n".join(lines)
