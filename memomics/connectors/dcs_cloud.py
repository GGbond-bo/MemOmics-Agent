"""MemOmics × 华大 DCS Cloud / GenPilot 连接器（PAT 版，官方 CLI 底板）。

调研依据（2026-10-07）
---------------------
DCS Cloud（www.dcs.cloud，华大基因）为外部客户端准备了官方自动化通道：
**PAT（个人访问令牌）** + 官方 `dcs` CLI（Windows 为 dcs.exe，官方 CDN 发行，v1.2.0，
SHA256SUMS 可校验）。平台帮助中心原文：PAT「是替代账号密码的访问凭证，用于命令行工具、
自动化脚本及 **AI Agent 调用 DCS Cloud** 时验证身份」，最长有效期 1 年，可随时删除立即失效。

因此本连接器**不保存用户密码**：平台支持双因子验证，中国站点"用密码登录时还需要验证手机号"，
密码自动登录在第一步就会被打断；而且很多用户是微信扫码/短信验证码注册（根本没有密码）。
PAT 是唯一正确的凭据形态。

能力边界（本模块 = 官方 CLI 的薄包装，不逆向任何网页接口）
----------------------------------------------------------
    * 项目：列表 / 切换 / 当前
    * 数据：浏览 Files、搜索、元数据、上传（本机→云）、下载（云→本机）
    * 容器：在线容器 open / exec / close（同一套 OpenSandbox 体系，即 GenPilot 智能分析的工作区）
    * 任务：离线任务列表 / 日志（分析类）；WDL 流程投递走 raw 白名单

设计取舍
--------
1. **只走官方 CLI**：稳定、有版本、有 `--schema`/`--describe` 自省；所有命令强制
   `--output json --no-history`（JSON 好解析；不把 MemOmics 触发的调用写进 CLI 历史）。
2. **PAT 双份存法**：CLI 自己在 `~/.dcs/config.yaml` 维护会话（`encrypt: true`）；
   本连接器另存一份到 ``hermes_home/dcs_cloud.json``，用于（a）会话失效后自动重登、
   （b）状态展示（掩码）、（c）用户解绑时能彻底清理。
3. **写操作先问用户**：上传/投递会改动云端数据并产生计费，工具描述里要求模型先确认；
   `allow_write: false` 可一键封掉所有写动作（只读模式）。
4. 不做 token 轮换/共享：一人一 PAT（平台 API Key 使用声明明确"仅供账号本人使用"）。

配置（hermes_home/config.yaml）
------------------------------
    dcs_cloud:
      enabled: true                     # 总开关；false/缺省时工具对模型不可见
      cli_path: ""                      # 留空则自动探测（PATH → LOCALAPPDATA → 仓库 tools/dcs）
      base_url: https://www.dcs.cloud   # 站点；其它片区换成对应域名
      region: ""                        # 片区代码；留空用站点默认
      default_project: ""               # 留空 = 用 CLI 当前项目
      timeout: 120                      # 单条命令超时（秒）
      max_output_chars: 20000           # 返回给模型的输出上限
      allow_write: true                 # false = 只读模式（上传/投递全拒）

环境变量覆盖：
    MEMOMICS_DCS_ENABLED / _CLI / _BASE_URL / _REGION / _PROJECT / _TIMEOUT / _ALLOW_WRITE

用户侧操作（WebUI「☁️ DCS 云」面板或对话里说"绑定 DCS 账号"）：
    个人中心 → 访问令牌 → 创建（设有效期）→ 复制 → 粘贴进 MemOmics。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

_ENV_MAP = {
    "enabled": "MEMOMICS_DCS_ENABLED",
    "cli_path": "MEMOMICS_DCS_CLI",
    "base_url": "MEMOMICS_DCS_BASE_URL",
    "region": "MEMOMICS_DCS_REGION",
    "default_project": "MEMOMICS_DCS_PROJECT",
    "timeout": "MEMOMICS_DCS_TIMEOUT",
    "max_output_chars": "MEMOMICS_DCS_MAX_OUTPUT",
    "allow_write": "MEMOMICS_DCS_ALLOW_WRITE",
}

_DEFAULT_CFG = {
    "enabled": False,
    "cli_path": "",
    "base_url": "https://www.dcs.cloud",
    "region": "",
    "default_project": "",
    "timeout": 120,
    "max_output_chars": 20000,
    "allow_write": True,
    "download_dir": "",
}

_CFG_CACHE = {"mtime": None, "cfg": None}

VAULT_FILENAME = "dcs_cloud.json"   # 相对 hermes_home；PAT 落盘处


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME", str(Path.cwd() / "hermes_home")))


def _config_path() -> Path:
    """定位 hermes_home/config.yaml（与 remote_cluster / debate_analysis 同源）。"""
    return _hermes_home() / "config.yaml"


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value, default: int) -> int:
    try:
        return int(str(value).strip() or default)
    except Exception:
        return default


def load_config(force: bool = False) -> dict:
    """读 config.yaml 的 dcs_cloud: 段 + 环境变量覆盖，带 mtime 缓存。"""
    path = _config_path()
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
            section = data.get("dcs_cloud") if isinstance(data, dict) else None
            if isinstance(section, dict):
                raw = dict(section)
        except Exception as exc:
            logger.warning("读取 dcs_cloud 配置失败(%s): %s", path, exc)

    cfg = dict(_DEFAULT_CFG)
    for key in _DEFAULT_CFG:
        if key in raw and raw[key] is not None:
            cfg[key] = raw[key]
    for key, env_name in _ENV_MAP.items():
        env_val = os.environ.get(env_name)
        if env_val is not None and str(env_val).strip() != "":
            cfg[key] = env_val

    cfg["enabled"] = _truthy(cfg["enabled"])
    cfg["allow_write"] = _truthy(cfg.get("allow_write", True))
    cfg["cli_path"] = str(cfg.get("cli_path") or "").strip()
    cfg["base_url"] = str(cfg.get("base_url") or "").strip() or _DEFAULT_CFG["base_url"]
    cfg["region"] = str(cfg.get("region") or "").strip()
    cfg["default_project"] = str(cfg.get("default_project") or "").strip()
    cfg["timeout"] = max(5, _as_int(cfg.get("timeout"), 120))
    cfg["max_output_chars"] = max(1000, _as_int(cfg.get("max_output_chars"), 20000))

    _CFG_CACHE["mtime"] = mtime
    _CFG_CACHE["cfg"] = cfg
    return cfg


def dcs_cloud_enabled() -> bool:
    """check_fn：配置里 enabled=true 时工具才对模型可见。

    注意：**故意不要求已绑定 PAT**——工具要先能被模型看见，模型才能在用户说
    "绑定 DCS 账号 / 查我云上的项目"时给出正确指引（与 remote_cluster 的取舍一致：
    宁可让它报"未绑定"，也不能让工具凭空消失）。
    """
    try:
        return bool(load_config().get("enabled"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 凭据库（PAT）
# ---------------------------------------------------------------------------

def vault_path() -> Path:
    return _hermes_home() / VAULT_FILENAME


def mask_pat(pat: str) -> str:
    """dcs_pat_9f2a7c1e... → dcs_pat_9f2a…（只留前缀 + 4 位尾号）。"""
    pat = (pat or "").strip()
    if len(pat) <= 12:
        return "…" if pat else ""
    return "%s…%s" % (pat[:12], pat[-4:])


def read_credential() -> dict:
    """读本地 PAT 记录；文件不存在/坏掉时返回 {}（绝不抛）。"""
    path = vault_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("读取 DCS 凭据失败(%s): %s", path, exc)
        return {}


def save_credential(pat: str, *, user: str = "", user_id: str = "",
                    expires_at=None, base_url: str = "") -> dict:
    """把 PAT 写进本机凭据库（文件权限尽力收窄到 0600）。"""
    pat = (pat or "").strip()
    record = {
        "pat": pat,
        "masked": mask_pat(pat),
        "user": user or "",
        "user_id": user_id or "",
        "base_url": base_url or "",
        "expires_at": expires_at,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = vault_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)
    try:
        os.chmod(tmp, 0o600)   # Windows 上是尽力而为；POSIX 上真生效
    except Exception:
        pass
    os.replace(tmp, path)
    return record


def clear_credential() -> bool:
    path = vault_path()
    try:
        if path.exists():
            path.unlink()
            return True
    except Exception as exc:
        logger.warning("删除 DCS 凭据失败(%s): %s", path, exc)
    return False


# ---------------------------------------------------------------------------
# CLI 定位与执行
# ---------------------------------------------------------------------------

def _candidate_cli_paths() -> list:
    out = []
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        out.append(Path(local) / "MemOmics" / "tools" / "dcs" / "dcs.exe")
    try:
        repo_root = Path(__file__).resolve().parents[2]   # <repo>/memomics/connectors/x.py
        out.append(repo_root / "tools" / "dcs" / "dcs.exe")
    except Exception:
        pass
    out.append(Path.home() / ".memomics" / "tools" / "dcs" / "dcs.exe")
    return out


def resolve_cli(cfg: dict | None = None) -> str:
    """按 配置 → PATH → 常见安装位置 的顺序找 dcs 可执行文件；找不到返回 ""。"""
    cfg = cfg or load_config()
    configured = str(cfg.get("cli_path") or "").strip()
    if configured and Path(configured).is_file():
        return configured
    for name in ("dcs.exe", "dcs"):
        found = shutil.which(name)
        if found:
            return found
    for cand in _candidate_cli_paths():
        try:
            if cand.is_file():
                return str(cand)
        except Exception:
            continue
    return ""


def _cli_env() -> dict:
    env = dict(os.environ)
    env.pop("DCS_PAT", None)   # 会话走 CLI 自己的登录态，不靠临时环境变量
    env.setdefault("NO_COLOR", "1")
    return env


def _run_cli(args: list, *, cfg: dict | None = None, timeout: int | None = None,
             with_json_output: bool = True) -> dict:
    """跑一条 dcs 命令，返回结构化结果（永不抛）。

    返回：{"ok": bool, "exit_code": int|None, "data": Any, "error": dict|None,
           "message": str, "hint": str, "cmd": [..], "stdout_tail": str}
    """
    cfg = cfg or load_config()
    cli = resolve_cli(cfg)
    if not cli:
        return {
            "ok": False, "exit_code": None, "data": None, "error": {"type": "cli_missing"},
            "message": "没找到 dcs 命令行工具",
            "hint": ("先安装官方 CLI：`scripts/install_dcs_cli.ps1`（从官方 CDN 下载并校验 SHA256），"
                     "或在 config.yaml 的 dcs_cloud.cli_path 里写 dcs.exe 全路径"),
            "cmd": [],
        }
    argv = [cli] + [str(a) for a in args]
    if with_json_output:
        argv += ["--output", "json", "--no-history"]
    t = int(timeout or cfg.get("timeout") or 120)
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=t, env=_cli_env(), creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit_code": None, "data": None,
                "error": {"type": "timeout"},
                "message": "命令超时（%ds）：%s" % (t, " ".join(argv[1:4])),
                "hint": "任务太重或网络慢：改用离线任务（analysis/workflow），或调大 dcs_cloud.timeout",
                "cmd": argv[1:], "stdout_tail": ""}
    except Exception as exc:
        return {"ok": False, "exit_code": None, "data": None,
                "error": {"type": "spawn_failed", "detail": str(exc)},
                "message": "拉起 dcs CLI 失败: %s" % exc,
                "hint": "检查 cli_path 是否指向可执行文件、是否有杀软拦截",
                "cmd": argv[1:], "stdout_tail": ""}

    stdout = proc.stdout or ""
    parsed = None
    try:
        parsed = json.loads(stdout)
    except Exception:
        parsed = None

    if isinstance(parsed, dict):
        error = parsed.get("error") or None
        exit_code = parsed.get("exit_code", proc.returncode)
        ok = (exit_code == 0) and not error
        message = parsed.get("message") or ""
        if not message and isinstance(error, dict):
            message = str(error.get("detail", {}).get("message") or error.get("hint") or "")
        hint = str((error or {}).get("hint") or "") if isinstance(error, dict) else ""
        out = {
            "ok": ok,
            "exit_code": exit_code,
            "data": parsed.get("data"),
            "error": error,
            "message": message,
            "hint": hint,
            "request_id": parsed.get("request_id"),
            "cmd": argv[1:],
            "stdout_tail": stdout[-2000:] if not ok else "",
        }
        if not ok:
            out = _attach_friendly_hint(out)
        return out

    # 非 JSON 输出（老版本 CLI / 崩溃）：按退出码判断
    ok = proc.returncode == 0
    out = {
        "ok": ok, "exit_code": proc.returncode, "data": None, "error": None,
        "message": "" if ok else (proc.stderr or stdout)[-500:],
        "hint": "" if ok else "CLI 未返回 JSON：确认版本 ≥ v1.2.0（dcs --version），或用 --describe 自查参数",
        "cmd": argv[1:], "stdout_tail": stdout[-2000:],
    }
    return out


_AUTH_CODES = {41201, 83002, 70102, 41104, 60003}


def _attach_friendly_hint(out: dict) -> dict:
    """把平台的业务码翻译成下一步动作（模型和用户都看得懂）。"""
    err = out.get("error") or {}
    detail = err.get("detail") if isinstance(err, dict) else None
    code = None
    for src in (detail, err):
        if isinstance(src, dict):
            for key in ("business_code", "api_code", "code"):
                try:
                    if src.get(key) is not None:
                        code = int(src.get(key))
                        break
                except Exception:
                    continue
        if code is not None:
            break
    if out.get("exit_code") == 3 and not out.get("hint"):
        out["hint"] = "认证失败：请重新绑定 DCS 访问令牌（个人中心 → 访问令牌）"
    if code in _AUTH_CODES:
        out["hint"] = ("未登录或 PAT 已失效：让用户在 MemOmics「☁️ DCS 云」面板重新绑定 PAT"
                       "（个人中心 → 访问令牌 → 创建）")
    elif code == 83003:
        out["hint"] = "还没选项目：先 action='projects' 看列表，再 action='use_project' 切换"
    elif code == 83006:
        out["hint"] = "在线容器没开：先 action='container_open'（打开后等 3–5 秒再 exec）"
    elif code == 83007:
        out["hint"] = "容器刚打开，稍等 3–5 秒再执行"
    return out


def _ensure_login(cfg: dict | None = None) -> dict:
    """确保 CLI 侧有登录态：没有就用手里的 PAT 自动登一次。"""
    cfg = cfg or load_config()
    cred = read_credential()
    pat = str(cred.get("pat") or "").strip()
    if not pat:
        return {"ok": False, "message": "本机还没有绑定 DCS 访问令牌（PAT）",
                "hint": "让用户在「☁️ DCS 云」面板粘贴 PAT，或说'绑定 DCS 账号'"}
    args = ["auth", "login", "--token", pat]
    base_url = str(cfg.get("base_url") or "").strip()
    res = _run_cli(args, cfg=cfg)
    if not res.get("ok") and base_url and base_url != _DEFAULT_CFG["base_url"]:
        # 站点不对时给 CLI 换 base_url 再试一次
        _run_cli(["config", "set", "base_url", base_url], cfg=cfg, with_json_output=False)
        res = _run_cli(args, cfg=cfg)
    return res


def _default_project_guard(cfg: dict) -> list:
    """配置里写了 default_project 就顺手确保当前项目是它（不覆盖用户手动切的）。"""
    proj = str(cfg.get("default_project") or "").strip()
    if not proj:
        return []
    cur = _run_cli(["project", "current"], cfg=cfg)
    data = cur.get("data") if isinstance(cur.get("data"), dict) else {}
    text = json.dumps(data, ensure_ascii=False)
    if proj not in text:
        _run_cli(["project", "switch", "--id", proj], cfg=cfg)
    return []


# ---------------------------------------------------------------------------
# 动作实现（每个都返回 dict，由 handler 统一序列化）
# ---------------------------------------------------------------------------

def _ok(payload: dict) -> dict:
    payload.setdefault("status", "ok")
    return payload


def _err(message: str, **extra) -> dict:
    payload = {"status": "error", "error": message}
    payload.update(extra)
    return payload


def _clip(cfg: dict, payload: dict) -> dict:
    """截断过长输出，保护模型上下文。"""
    limit = int(cfg.get("max_output_chars") or 20000)
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= limit:
        return payload
    payload = dict(payload)
    payload["truncated"] = True
    payload["note"] = "输出超过 %d 字符已截断；要细看请缩小范围（加 path / 减少 page-size）" % limit
    # 逐段砍：优先丢 data 里的明细
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("items", "list", "records", "rows"):
            if isinstance(data.get(key), list):
                data = dict(data)
                data[key] = data[key][:20]
                payload["data"] = data
                break
    return payload


def action_status(args: dict) -> dict:
    cfg = load_config()
    cli = resolve_cli(cfg)
    cred = read_credential()
    version = ""
    if cli:
        v = _run_cli(["--version"], cfg=cfg, with_json_output=False)
        version = "".join(v.get("stdout_tail") or "").strip() or ""
    info = _ok({
        "bound": bool(cred.get("pat")),
        "pat_masked": cred.get("masked") or "",
        "user": cred.get("user") or "",
        "user_id": cred.get("user_id") or "",
        "expires_at": cred.get("expires_at"),
        "saved_at": cred.get("saved_at"),
        "cli_path": cli or "(未找到)",
        "cli_version": version,
        "base_url": cfg.get("base_url"),
        "region": cfg.get("region") or "(站点默认)",
        "default_project": cfg.get("default_project") or "(用 CLI 当前项目)",
        "allow_write": cfg.get("allow_write"),
    })
    hints = []
    if not cred.get("pat"):
        hints.append("还没绑定 PAT：DCS 个人中心 → 访问令牌 → 创建 → 复制后粘贴到「☁️ DCS 云」面板")
    if not cli:
        hints.append("先装官方 CLI：scripts/install_dcs_cli.ps1（官方 CDN + SHA256 校验），"
                     "或在 config.yaml 写 dcs_cloud.cli_path")
    if cli and cred.get("pat"):
        cur = _run_cli(["project", "current"], cfg=cfg)
        info["cli_session_ok"] = bool(cur.get("ok"))
        if cur.get("ok"):
            info["current"] = cur.get("data")
        else:
            info["cli_session_error"] = cur.get("message")
            hints.append(cur.get("hint") or "会话失效：重新绑定或手动执行一次登录")
    if hints:
        info["hint"] = "；".join(hints)
    return info


def action_bind(args: dict) -> dict:
    cfg = load_config()
    pat = str(args.get("pat") or args.get("token") or "").strip()
    if not pat:
        return _err("missing_pat", hint="需要参数 pat（在 DCS 个人中心 → 访问令牌 里创建并复制）")
    if not pat.startswith("dcs_pat_"):
        return _err("PAT 格式不对：应以 dcs_pat_ 开头", hint="确认复制完整（令牌只显示一次）")
    res = _run_cli(["auth", "login", "--token", pat], cfg=cfg)
    if not res.get("ok"):
        return _err("绑定失败：%s" % (res.get("message") or "未知错误"),
                    detail=res.get("error"), hint=res.get("hint"))
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    user = str(data.get("username") or data.get("user_name") or data.get("user") or "")
    user_id = str(data.get("user_id") or "")
    expires = data.get("token_expires_at") or data.get("expires_at")
    save_credential(pat, user=user, user_id=user_id, expires_at=expires,
                    base_url=str(cfg.get("base_url") or ""))
    _default_project_guard(cfg)
    cur = _run_cli(["project", "current"], cfg=cfg)
    return _ok({
        "bound": True,
        "pat_masked": mask_pat(pat),
        "user": user,
        "user_id": user_id,
        "expires_at": expires,
        "current": cur.get("data") if cur.get("ok") else None,
        "message": "DCS 账号已绑定（PAT 保存在本机 %s，不进日志、不随安装包分发）" % VAULT_FILENAME,
    })


def action_unbind(args: dict) -> dict:
    cfg = load_config()
    _run_cli(["auth", "logout"], cfg=cfg)
    removed = clear_credential()
    return _ok({"bound": False, "vault_removed": removed,
                "message": "已解绑：CLI 会话已登出，本机 PAT 已删除"})


def action_projects(args: dict) -> dict:
    cfg = load_config()
    argv = ["project", "ls"]
    if args.get("page"):
        argv += ["--page", str(int(args["page"]))]
    if args.get("page_size"):
        argv += ["--page-size", str(int(args["page_size"]))]
    if str(args.get("name") or "").strip():
        argv += ["-n", str(args["name"]).strip()]
    res = _run_cli(argv, cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "查询项目失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"projects": res.get("data"), "count": len(res.get("data") or []) if isinstance(res.get("data"), list) else None})


def action_use_project(args: dict) -> dict:
    cfg = load_config()
    pid = str(args.get("project") or args.get("id") or "").strip()
    name = str(args.get("name") or "").strip()
    if not pid and not name:
        return _err("需要参数 project（项目 ID，P 开头）或 name")
    argv = ["project", "switch"]
    if pid:
        argv += ["--id", pid]
    else:
        argv += ["--name", name]
    res = _run_cli(argv, cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "切换项目失败", detail=res.get("error"), hint=res.get("hint"))
    cur = _run_cli(["project", "current"], cfg=cfg)
    return _ok({"switched": True, "current": cur.get("data"), "detail": res.get("data")})


def action_current(args: dict) -> dict:
    cfg = load_config()
    cur = _run_cli(["project", "current"], cfg=cfg)
    if not cur.get("ok"):
        if not read_credential().get("pat"):
            return _err("还没绑定 DCS 账号", hint=action_status({}).get("hint"))
        auto = _ensure_login(cfg)
        if not auto.get("ok"):
            return _err(auto.get("message") or "登录态不可用", hint=auto.get("hint"))
        cur = _run_cli(["project", "current"], cfg=cfg)
    return _ok({"current": cur.get("data")})


def action_ls(args: dict) -> dict:
    cfg = load_config()
    path = str(args.get("path") or "").strip()
    argv = ["data", "ls"]
    if path:
        argv.append(path)
    if _truthy(args.get("long")):
        argv.append("-l")
    if args.get("page"):
        argv += ["--page", str(int(args["page"]))]
    res = _run_cli(argv, cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "列目录失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"path": path or "(当前目录)", "entries": res.get("data")})


def action_find(args: dict) -> dict:
    cfg = load_config()
    argv = ["data", "find"]
    mapping = (("name", "-n"), ("type", "-t"), ("path", "-p"), ("size", "-s"),
               ("sn", "-N"), ("sample", "-a"), ("entity", "-e"), ("user", "-u"),
               ("task", "-k"), ("workflow", "-w"), ("time", "-T"))
    for key, flag in mapping:
        val = args.get(key)
        if val not in (None, ""):
            argv += [flag, str(val)]
    if len(argv) == 2:
        return _err("至少给一个查询条件（name / type / path / size / sn / sample …）")
    if args.get("page_size"):
        argv += ["--page-size", str(args["page_size"])]
    if args.get("page"):
        argv += ["--page", str(int(args["page"]))]
    res = _run_cli(argv, cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "搜索失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"matches": res.get("data")})


def action_info(args: dict) -> dict:
    cfg = load_config()
    path = str(args.get("path") or "").strip()
    if not path:
        return _err("需要参数 path（云上路径，/Files/... 开头）")
    res = _run_cli(["data", "info", path], cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "查询元数据失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"path": path, "info": res.get("data")})


def _write_guard(cfg: dict, action: str) -> dict | None:
    if not cfg.get("allow_write"):
        return _err("只读模式：%s 已禁用" % action,
                    hint="管理員可在 config.yaml 的 dcs_cloud.allow_write 打开写权限")
    return None


def action_download(args: dict) -> dict:
    cfg = load_config()
    path = str(args.get("path") or "").strip()
    target = str(args.get("target") or "").strip()
    if not path:
        return _err("需要参数 path（云上路径）")
    if not target:
        return _err("需要参数 target（本机目标目录）")
    dtype = str(args.get("type") or "web").strip().lower()
    res = _run_cli(["data", "download", "--type", dtype, "--path", path, "--target", target], cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "下载失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"downloaded": path, "target": target, "type": dtype, "detail": res.get("data")})


# =====================================================================
# 下载队列（2026-10-07）
# 用户要求：下载要有进度、要有「完成」显示、下多个文件要能看到队列。
# 实现取舍：
#   * 官方 CLI 不吐百分比 → 进度靠**盯本机落盘字节**（对照云上 size 算百分比；
#     目录/未知大小则给"不确定"进度条 + 已落盘字节数）。
#   * 队列 = 单线程串行 worker（云盘吞吐有限，并发只会互相拖慢）；
#     任务登记在**进程内存**里 → 刷新页面不丢队列，重启服务才清空。
#   * 支持取消（杀进程）、重试（重新入队）、打开所在文件夹。
# =====================================================================
_DL_LOCK = threading.Lock()
_DL_JOBS: dict = {}      # job_id -> job dict
_DL_ORDER: list = []     # 入队顺序（ID 列表）
_DL_THREAD = None        # 串行 worker 线程
_DL_SEQ = 0
_DL_KEEP = 80            # 队列最多保留多少条（含已结束的）


def _dl_now() -> float:
    return time.time()


def _dl_spawn(argv: list):
    """拉起 dcs 下载进程（测试可替换此函数）。"""
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        env=_cli_env(), creationflags=creationflags,
    )


def _dl_locate(target: str, name: str, since: float = 0.0) -> str:
    """找出真正落盘的文件/目录（CLI 可能用临时名或改名，例如 name.part）。"""
    if not target or not name:
        return ""
    exact = os.path.join(target, name)
    if os.path.exists(exact):
        return exact
    best, best_t = "", 0.0
    try:
        for fn in os.listdir(target):
            if not (fn.startswith(name) or fn.startswith("." + name)):
                continue
            p = os.path.join(target, fn)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if since and st.st_mtime < since - 5:
                continue
            if st.st_mtime >= best_t:
                best, best_t = p, st.st_mtime
    except OSError:
        pass
    return best


def _dl_measure(target: str, name: str, since: float = 0.0) -> int:
    """估算已落盘字节数（进度条的分子）。"""
    path = _dl_locate(target, name, since)
    if not path:
        return 0
    try:
        if os.path.isfile(path):
            return os.path.getsize(path)
        total = 0
        for root, _dirs, files in os.walk(path):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
            if total > 50 * 1024 ** 3:      # 别为进度条把盘拖死
                break
        return total
    except OSError:
        return 0


def _dl_parse_output(text: str) -> dict | None:
    """CLI 的 JSON 信封（可能混着进度行）：整段先试，再倒数逐行试。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    for line in reversed([l.strip() for l in text.splitlines() if l.strip()][-40:]):
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _dl_job_public(job: dict) -> dict:
    """给前端的只读快照。"""
    out = {
        "id": job.get("id"), "path": job.get("path"), "name": job.get("name"),
        "target": job.get("target"), "state": job.get("state"),
        "size": int(job.get("size") or 0), "got": int(job.get("got") or 0),
        "local": job.get("local") or "", "message": job.get("message") or "",
        "hint": job.get("hint") or "", "type": job.get("type") or "web",
        "created": job.get("created"), "started": job.get("started"), "ended": job.get("ended"),
        "elapsed": job.get("elapsed") or 0,
    }
    size, got = out["size"], out["got"]
    out["pct"] = int(min(100, round(got * 100.0 / size))) if size > 0 else None
    return out


def _dl_run_one(job: dict) -> None:
    """跑完一个下载任务（阻塞在这个 worker 线程里）。"""
    cfg = load_config()
    cli = resolve_cli(cfg)
    if not cli:
        job["state"] = "failed"
        job["message"] = "没找到 dcs 命令行工具"
        job["hint"] = "运行 scripts/install_dcs_cli.ps1 安装官方 CLI，或在 config.yaml 的 dcs_cloud.cli_path 里写全路径"
        job["ended"] = _dl_now()
        return
    argv = [cli, "data", "download", "--type", str(job.get("type") or "web"),
            "--path", str(job.get("path")), "--target", str(job.get("target")),
            "--output", "json", "--no-history"]
    job["cmd"] = argv[1:]
    t0 = _dl_now()
    try:
        proc = _dl_spawn(argv)
    except Exception as exc:
        job["state"] = "failed"
        job["message"] = "拉起 dcs CLI 失败: %s" % exc
        job["hint"] = "检查 cli_path 是否指向可执行文件、是否有杀软拦截"
        job["ended"] = _dl_now()
        return

    chunks: list = []

    def _reader():
        try:
            fh = proc.stdout
            if fh is None:
                return
            for line in fh:
                chunks.append(line)
        except Exception:
            pass

    th = threading.Thread(target=_reader, name="dcs-dl-read", daemon=True)
    th.start()
    killed = False
    while proc.poll() is None:
        if job.get("cancel") and not killed:
            killed = True
            try:
                proc.kill()
            except Exception:
                pass
        job["got"] = _dl_measure(str(job.get("target")), str(job.get("name")), t0)
        job["elapsed"] = round(_dl_now() - t0, 1)
        time.sleep(0.5)
    try:
        th.join(timeout=5)
    except Exception:
        pass

    text = "".join(chunks)
    parsed = _dl_parse_output(text)
    exit_code = proc.returncode
    error = (parsed or {}).get("error") or None
    ok = (exit_code == 0) and not error and not killed
    job["exit_code"] = exit_code
    job["request_id"] = (parsed or {}).get("request_id")
    job["stdout_tail"] = text[-2000:]
    job["got"] = _dl_measure(str(job.get("target")), str(job.get("name")), t0)
    job["local"] = _dl_locate(str(job.get("target")), str(job.get("name")), t0)
    if killed or job.get("cancel"):
        job["state"] = "cancelled"
        job["message"] = "已取消（可点「重试」重新入队）"
    elif ok:
        job["state"] = "done"
        job["message"] = "已下载到 %s" % (job.get("local") or job.get("target"))
    else:
        job["state"] = "failed"
        msg = (parsed or {}).get("message") or ""
        if not msg and isinstance(error, dict):
            msg = str((error.get("detail") or {}).get("message") or error.get("hint") or "")
        job["message"] = msg or (text[-400:].strip() or ("下载失败（退出码 %s）" % exit_code))
        hint = (error or {}).get("hint") if isinstance(error, dict) else ""
        if not hint:
            try:
                friendly = _attach_friendly_hint({
                    "ok": False, "error": error, "message": msg, "hint": "",
                    "exit_code": exit_code,
                })
                hint = str((friendly or {}).get("hint") or "")
            except Exception:
                hint = ""
        job["hint"] = hint
    job["ended"] = _dl_now()
    job["elapsed"] = round(float(job["ended"]) - t0, 1)


def _dl_worker() -> None:
    """串行消费队列；没活了就退出（下次入队再拉起）。"""
    while True:
        nxt = None
        with _DL_LOCK:
            for jid in list(_DL_ORDER):
                j = _DL_JOBS.get(jid)
                if j and j.get("state") == "queued":
                    j["state"] = "running"
                    j["started"] = _dl_now()
                    nxt = j
                    break
            if nxt is None:
                still = any((x or {}).get("state") == "queued" for x in _DL_JOBS.values())
                if not still:
                    globals()["_DL_THREAD"] = None
                    return
        if nxt is None:
            time.sleep(0.3)
            continue
        try:
            _dl_run_one(nxt)
        except Exception as exc:
            nxt["state"] = "failed"
            nxt["message"] = "%s: %s" % (type(exc).__name__, exc)
        if not nxt.get("ended"):
            nxt["ended"] = _dl_now()


def _dl_trim() -> None:
    """队列太长时丢最老的**已结束**任务（调用方须持锁）。"""
    while len(_DL_ORDER) > _DL_KEEP:
        for i, jid in enumerate(_DL_ORDER):
            j = _DL_JOBS.get(jid) or {}
            if j.get("state") in ("done", "failed", "cancelled"):
                _DL_ORDER.pop(i)
                _DL_JOBS.pop(jid, None)
                break
        else:
            break       # 全是活动任务，先留着


def _dl_default_target(cfg: dict) -> str:
    target = str(cfg.get("download_dir") or "").strip()
    if not target:
        target = os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "results", "dcs"))
    return os.path.abspath(os.path.expanduser(target))


def _dl_enqueue_one(raw: dict, cfg: dict) -> tuple:
    """把一条下载需求变成 job；返回 (job_id, error_message)。"""
    global _DL_SEQ, _DL_THREAD
    path = str((raw or {}).get("path") or "").strip()
    if not path:
        return "", "需要参数 path（云上路径）"
    target = str((raw or {}).get("target") or "").strip()
    target = os.path.abspath(os.path.expanduser(target)) if target else _dl_default_target(cfg)
    try:
        os.makedirs(target, exist_ok=True)
    except OSError as exc:
        return "", "本机目标目录建不出来（%s）：%s" % (target, exc)
    name = str((raw or {}).get("name") or "").strip() or path.rstrip("/").rsplit("/", 1)[-1]
    try:
        size = int((raw or {}).get("size") or 0)
    except Exception:
        size = 0
    with _DL_LOCK:
        _DL_SEQ += 1
        jid = "dl-%s-%03d" % (datetime.now().strftime("%H%M%S"), _DL_SEQ)
        job = {
            "id": jid, "path": path, "name": name, "target": target,
            "size": max(0, size), "got": 0, "state": "queued",
            "type": str((raw or {}).get("type") or "web").strip() or "web",
            "created": _dl_now(), "started": None, "ended": None, "elapsed": 0,
            "local": "", "message": "", "hint": "", "cancel": False,
        }
        _DL_JOBS[jid] = job
        _DL_ORDER.append(jid)
        _dl_trim()
        if _DL_THREAD is None or not _DL_THREAD.is_alive():
            _DL_THREAD = threading.Thread(target=_dl_worker, name="dcs-dl-queue", daemon=True)
            _DL_THREAD.start()
    return jid, ""


def dl_start(args: dict | None = None, **kwargs) -> dict:
    """入队下载（立即返回，不等下载完）。支持单条或 items 批量。"""
    args = dict(args or {})
    args.update(kwargs)
    cfg = load_config()
    items = args.get("items")
    if isinstance(items, list) and items:
        if len(items) > 200:
            return _err("一次最多入队 200 个文件（收到 %d 个）" % len(items))
        ids, errs = [], []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            jid, err = _dl_enqueue_one(raw, cfg)
            if jid:
                ids.append(jid)
            else:
                errs.append("%s: %s" % (str((raw or {}).get("path") or "?")[:80], err))
        if not ids:
            return _err(errs[0] if errs else "没有可入队的条目")
        with _DL_LOCK:
            snap = {"ids": ids, "queued": len(ids), "errors": errs[:8]}
        return _ok(snap)
    jid, err = _dl_enqueue_one(args, cfg)
    if not jid:
        return _err(err, hint="检查云上路径是否正确、默认下载目录是否可写")
    with _DL_LOCK:
        job = _dl_job_public(_DL_JOBS[jid])
    return _ok({"id": jid, "job": job, "queued": 1})


def dl_list(args: dict | None = None, **kwargs) -> dict:
    """队列全量快照（最新在前）+ 计数；前端轮询这个接口。"""
    with _DL_LOCK:
        jobs = [_dl_job_public(_DL_JOBS[j]) for j in _DL_ORDER if j in _DL_JOBS]
    jobs.reverse()
    counts = {"queued": 0, "running": 0, "done": 0, "failed": 0, "cancelled": 0}
    for j in jobs:
        counts[j["state"]] = counts.get(j["state"], 0) + 1
    counts["active"] = counts["queued"] + counts["running"]
    counts["total"] = len(jobs)
    return _ok({"jobs": jobs, "counts": counts})


def dl_cancel(args: dict | None = None, **kwargs) -> dict:
    """取消一个任务：排队中的直接标取消；正在跑的杀进程（worker 会收尾）。"""
    args = dict(args or {})
    args.update(kwargs)
    jid = str(args.get("id") or "").strip()
    with _DL_LOCK:
        job = _DL_JOBS.get(jid)
        if not job:
            return _err("没有这个下载任务：%s" % (jid or "（空 id）"))
        if job.get("state") in ("done", "failed", "cancelled"):
            return _ok({"id": jid, "state": job.get("state"), "note": "任务已结束，无需取消"})
        job["cancel"] = True
        if job.get("state") == "queued":
            job["state"] = "cancelled"
            job["message"] = "已取消（还没开始）"
            job["ended"] = _dl_now()
        snap = _dl_job_public(job)
    return _ok({"id": jid, "state": snap["state"], "job": snap})


def dl_retry(args: dict | None = None, **kwargs) -> dict:
    """重试：按原参数重新入队一条（失败/取消的都能重试）。"""
    args = dict(args or {})
    args.update(kwargs)
    jid = str(args.get("id") or "").strip()
    with _DL_LOCK:
        old = _DL_JOBS.get(jid)
    if not old:
        return _err("没有这个下载任务：%s" % (jid or "（空 id）"))
    return dl_start({"path": old.get("path"), "name": old.get("name"),
                     "target": old.get("target"), "size": old.get("size"),
                     "type": old.get("type")})


def dl_clear(args: dict | None = None, **kwargs) -> dict:
    """清掉已结束的任务（默认全清，也可给 ids 列表）。"""
    args = dict(args or {})
    args.update(kwargs)
    ids = args.get("ids")
    with _DL_LOCK:
        drop = []
        for jid in list(_DL_ORDER):
            job = _DL_JOBS.get(jid) or {}
            if job.get("state") not in ("done", "failed", "cancelled"):
                continue
            if isinstance(ids, list) and ids and jid not in ids:
                continue
            drop.append(jid)
        for jid in drop:
            _DL_ORDER.remove(jid)
            _DL_JOBS.pop(jid, None)
        left = len(_DL_ORDER)
    return _ok({"removed": len(drop), "left": left})


def dl_reveal(args: dict | None = None, **kwargs) -> dict:
    """在资源管理器里定位下载好的文件（失败则打开目标目录）。"""
    args = dict(args or {})
    args.update(kwargs)
    jid = str(args.get("id") or "").strip()
    job = _DL_JOBS.get(jid)
    if not job:
        return _err("没有这个下载任务：%s" % (jid or "（空 id）"))
    local = str(job.get("local") or "").strip()
    if not local or not os.path.exists(local):
        cand = _dl_locate(str(job.get("target") or ""), str(job.get("name") or ""))
        local = cand or str(job.get("target") or "")
    if not local or not os.path.exists(local):
        return _err("还没落盘，打不开（目标目录：%s）" % (job.get("target") or "-"))
    try:
        if os.name == "nt":
            if os.path.isdir(local):
                os.startfile(local)                       # noqa: S606
            else:
                subprocess.Popen(["explorer", "/select,", local])
        else:
            subprocess.Popen(["xdg-open", local if os.path.isdir(local) else os.path.dirname(local)])
        return _ok({"revealed": local})
    except Exception as exc:
        return _err("打开文件夹失败: %s" % exc, local=local)


def dl_reset() -> None:
    """测试用：清空队列状态。"""
    with _DL_LOCK:
        _DL_JOBS.clear()
        _DL_ORDER.clear()
        globals()["_DL_THREAD"] = None


def action_upload(args: dict) -> dict:
    cfg = load_config()
    guard = _write_guard(cfg, "upload")
    if guard:
        return guard
    path = str(args.get("path") or "").strip()
    target = str(args.get("target") or "").strip()
    if not path or not target:
        return _err("需要参数 path（本机文件）和 target（云上目标路径，/Files/...）")
    dtype = str(args.get("type") or "web").strip().lower()
    res = _run_cli(["data", "upload", "--type", dtype, "--path", path, "--target", target], cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "上传失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"uploaded": path, "target": target, "type": dtype, "detail": res.get("data"),
                "note": "云端存储与后续计算会计费（计费组见 dcs billing）"})


def action_container_open(args: dict) -> dict:
    cfg = load_config()
    guard = _write_guard(cfg, "container_open")
    if guard:
        return guard
    argv = ["terminal", "open"]
    if args.get("resource_id"):
        argv += ["--resource_id", str(args["resource_id"])]
    res = _run_cli(argv, cfg=cfg, timeout=max(cfg["timeout"], 180))
    if not res.get("ok"):
        return _err(res.get("message") or "打开容器失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"container": res.get("data"),
                "note": "容器已打开；等 3–5 秒再 exec（否则 83007）。不用时记得 container_close 释放资源"})


def action_container_exec(args: dict) -> dict:
    cfg = load_config()
    cmd = str(args.get("command") or args.get("cmd") or "").strip()
    if not cmd:
        return _err("需要参数 command")
    argv = ["terminal", "exec", "-c", cmd]
    if args.get("cwd"):
        argv += ["--cwd", str(args["cwd"])]
    if args.get("timeout"):
        argv += ["--timeout", str(int(args["timeout"]))]
    res = _run_cli(argv, cfg=cfg, timeout=max(cfg["timeout"], int(args.get("timeout") or 0) + 30))
    if not res.get("ok"):
        return _err(res.get("message") or "容器内执行失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"output": res.get("data")})


def action_container_close(args: dict) -> dict:
    cfg = load_config()
    argv = ["terminal", "close"]
    if _truthy(args.get("force")):
        argv.append("--force")
    res = _run_cli(argv, cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "关闭容器失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"closed": True, "detail": res.get("data")})


def action_tasks(args: dict) -> dict:
    cfg = load_config()
    argv = ["analysis", "ls"]
    if args.get("all"):
        argv.append("-a")
    if args.get("id"):
        argv += ["-i", str(args["id"])]
    if args.get("name"):
        argv += ["-n", str(args["name"])]
    if args.get("page_size"):
        argv += ["--page-size", str(args["page_size"])]
    res = _run_cli(argv, cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "查询任务失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"tasks": res.get("data")})


def action_task_logs(args: dict) -> dict:
    cfg = load_config()
    tid = str(args.get("task_id") or args.get("id") or "").strip()
    if not tid:
        return _err("需要参数 task_id（先用 action='tasks' 查）")
    res = _run_cli(["analysis", "log", "-i", tid], cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "取日志失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"task_id": tid, "log": res.get("data")})


# ---------------------------------------------------------------------------
# 🚀 投递：WDL 流程 / 离线分析任务（2026-10-07，用户："怎么用云平台跑分析、投递任务"）
#    只读三件套（flows / flow_form / images）一次把表单数据拿齐；
#    投递（flow_run / analysis_run）与取消（task_cancel）是写操作，先过 _write_guard。
# ---------------------------------------------------------------------------

def _short(text, n: int = 300) -> str:
    return str(text or "").replace("\r", "").strip()[:n]


def _argv_display(argv: list) -> str:
    """给人看的命令：含空格的参数加引号，方便核对（预检用）。"""
    return " ".join(('"%s"' % a) if (" " in str(a)) else str(a) for a in argv)


def _page_args(args: dict, default_size: int = 50) -> list:
    return ["--page", str(max(1, int(args.get("page") or 1))),
            "--page-size", str(min(200, max(1, int(args.get("page_size") or default_size))))]


def action_flows(args: dict) -> dict:
    """列出可投递的 WDL 流程（默认项目内；public=true 查公共库）。"""
    cfg = load_config()
    argv = ["workflow", "ls"]
    if _truthy(args.get("public")):
        argv.append("--public")
    if args.get("name"):
        argv += ["-n", str(args["name"])]
    argv += _page_args(args)
    res = _run_cli(argv, cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "查流程列表失败", detail=res.get("error"), hint=res.get("hint"))
    d = res.get("data") or {}
    recs = ((d.get("records") if isinstance(d, dict) else d) or [])
    flows = [{
        "name": str(r.get("name") or ""),
        "version": str(r.get("version") or r.get("latest_version") or ""),
        "tag": str(r.get("official_tag") or r.get("tags") or ""),
        "price": str(r.get("price") or ""),
        "origin": str(r.get("origin") or ""),
        "creator": str(r.get("creator") or ""),
    } for r in recs if str(r.get("name") or "").strip()]
    return _ok({"flows": flows,
                "total": (d.get("total") if isinstance(d, dict) else len(flows)) or len(flows),
                "page": args.get("page") or 1,
                "source": "public" if _truthy(args.get("public")) else "project"})


def action_flow_form(args: dict) -> dict:
    """WDL 投递表单：`workflow info`（inputs/版本/计费）+ `workflow check_parameter`（默认值）。"""
    cfg = load_config()
    name = str(args.get("flow") or args.get("name") or args.get("workflow") or "").strip()
    if not name:
        return _err("需要参数 flow（流程名，先用 action='flows' 查）")
    argv = ["workflow", "info", "-n", name]
    if args.get("version"):
        argv += ["-v", str(args["version"])]
    res = _run_cli(argv, cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "取流程详情失败（名字对不对？先 action='flows'）",
                    detail=res.get("error"), hint=res.get("hint"))
    info = res.get("data") or {}
    if not isinstance(info, dict):
        return _err("流程详情格式异常", detail=res.get("data"))
    spec = {}
    r2 = _run_cli(["workflow", "check_parameter", "-n", name], cfg=cfg)
    if r2.get("ok") and isinstance(r2.get("data"), dict):
        for p in (r2["data"].get("wdl_parameter") or []):
            nm = str(p.get("参数名") or p.get("name") or "").strip()
            if nm:
                spec[nm] = p
    inputs = []
    for it in (info.get("inputs") or []):
        if not isinstance(it, dict):
            continue
        nm = str(it.get("name") or "").strip()
        if not nm:
            continue
        sp = spec.get(nm) or {}
        inputs.append({
            "name": nm,
            "type": str(it.get("type") or sp.get("类型") or ""),
            "required": bool(it.get("required")) or str(sp.get("必填/选填") or "") == "必填",
            "default": str(sp.get("默认值") or it.get("default") or ""),
            "description": _short(it.get("description") or sp.get("说明"), 400),
        })
    return _ok({"flow": name,
                "version": str(info.get("version") or ""),
                "official_tag": str(info.get("official_tag") or ""),
                "pricing": info.get("pricing") or {},
                "inputs": inputs,
                "outputs": info.get("outputs") or [],
                "description": _short(info.get("description"), 800)})


def _flow_input_pairs(args: dict) -> list:
    raw = args.get("inputs") or {}
    pairs = []
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, list):
        for it in raw:
            if isinstance(it, dict):
                pairs.append((it.get("name") or it.get("key"), it.get("value")))
    return pairs


def action_flow_run(args: dict) -> dict:
    """投递 WDL 流程任务（写操作）。inputs 传 {参数名: 值}；output_path 传云上输出目录。"""
    cfg = load_config()
    name = str(args.get("flow") or args.get("name") or "").strip()
    if not name:
        return _err("需要参数 flow（流程名）")
    pairs = _flow_input_pairs(args)
    argv = ["workflow", "run", "-n", name]
    if args.get("version"):
        argv += ["-v", str(args["version"])]
    if args.get("entity"):
        argv += ["-e", str(args["entity"])]
    for k, v in pairs:
        if k is None or v is None or str(v).strip() == "":
            continue
        argv += ["-i", "%s=%s" % (k, v)]
    if args.get("output_path"):
        argv += ["-o", str(args["output_path"])]
    if args.get("table"):
        argv += ["--table", str(args["table"])]
    if not any(str(v).strip() for _, v in pairs) and not args.get("table"):
        return _err("至少要填一个输入参数（-i 名=值），或用 --table 参数表文件")
    if _truthy(args.get("dry_run")):
        return _ok({"dry_run": True, "flow": name, "argv": ["dcs"] + argv,
                    "command": _argv_display(["dcs"] + argv),
                    "note": "预检（dry_run）：没有提交、不计费；核对无误后去掉 dry_run 再提交"})
    guard = _write_guard(cfg, "flow_run")
    if guard:
        return guard
    res = _run_cli(argv, cfg=cfg, timeout=max(int(cfg.get("timeout") or 120), 240))
    if not res.get("ok"):
        return _err(res.get("message") or "投递失败", detail=res.get("error"), hint=res.get("hint"))
    d = res.get("data")
    tid = ""
    if isinstance(d, dict):
        tid = str(d.get("task_id") or d.get("batch_id") or d.get("id") or "")
    elif isinstance(d, str):
        tid = d.strip()
    return _ok({"task_id": tid, "flow": name, "argv": res.get("cmd") or [],
                "note": "已投递 → 用 action='flow_tasks' 看进度、'flow_task_info' 看详情与日志"})


def action_analysis_run(args: dict) -> dict:
    """投递离线分析任务（shell，写操作）。command 可多条（每条 = 一个 -i）。"""
    cfg = load_config()
    cmd = args.get("command") or args.get("cmd") or args.get("input") or []
    if isinstance(cmd, str):
        cmd = [cmd]
    cmds = [str(x).strip() for x in cmd if str(x).strip()]
    if not cmds and not args.get("path"):
        return _err("需要参数 command（要跑的 shell 命令，例：sh /work/<user>/run.sh）")
    argv = ["analysis", "run"]
    if args.get("name"):
        argv += ["-n", str(args["name"])]
    for x in cmds:
        argv += ["-i", x]
    if args.get("resource"):
        argv += ["-l", str(args["resource"])]
    if args.get("image"):
        argv += ["--image", str(args["image"])]
    if args.get("mount"):
        argv += ["-m", str(args["mount"])]
    if args.get("output_path"):
        argv += ["-o", str(args["output_path"])]
    if args.get("path"):
        argv += ["-p", str(args["path"])]
    if _truthy(args.get("dry_run")):
        return _ok({"dry_run": True, "argv": ["dcs"] + argv,
                    "command": _argv_display(["dcs"] + argv),
                    "note": "预检（dry_run）：没有提交、不计费；核对无误后去掉 dry_run 再提交"})
    guard = _write_guard(cfg, "analysis_run")
    if guard:
        return guard
    res = _run_cli(argv, cfg=cfg, timeout=max(int(cfg.get("timeout") or 120), 240))
    if not res.get("ok"):
        return _err(res.get("message") or "投递失败", detail=res.get("error"), hint=res.get("hint"))
    d = res.get("data")
    tid = ""
    if isinstance(d, dict):
        tid = str(d.get("task_id") or d.get("batch_id") or d.get("id") or "")
    elif isinstance(d, str):
        tid = d.strip()
    return _ok({"task_id": tid, "argv": res.get("cmd") or [],
                "note": "已投递 → 用 action='tasks' / 'task_logs' 看进度与日志"})


def action_images(args: dict) -> dict:
    """本机可用的容器镜像列表（离线任务 --image 用）。"""
    cfg = load_config()
    argv = ["image", "ls"] + _page_args(args)
    res = _run_cli(argv, cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "查镜像失败", detail=res.get("error"), hint=res.get("hint"))
    d = res.get("data") or {}
    recs = ((d.get("records") if isinstance(d, dict) else d) or [])
    images = []
    for r in recs:
        nm = str(r.get("name") or "").strip()
        tag = str(r.get("tags") or "").strip().strip(":") or "latest"
        if nm:
            images.append({"name": nm, "ref": "%s:%s" % (nm, tag),
                           "prog_env": str(r.get("prog_env") or ""),
                           "build_type": str(r.get("build_type") or "")})
    return _ok({"images": images, "total": (d.get("total") if isinstance(d, dict) else len(images)) or len(images)})


def action_flow_tasks(args: dict) -> dict:
    """WDL 任务列表（投递后看进度）。"""
    cfg = load_config()
    argv = ["workflow", "tasks"] + _page_args(args)
    if args.get("status"):
        argv += ["-s", str(args["status"])]
    if args.get("user"):
        argv += ["-u", str(args["user"])]
    if args.get("flow"):
        argv += ["-n", str(args["flow"])]
    if args.get("task_id"):
        argv += ["-i", str(args["task_id"])]
    if _truthy(args.get("all")):
        argv.append("-a")
    res = _run_cli(argv, cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "查 WDL 任务失败", detail=res.get("error"), hint=res.get("hint"))
    d = res.get("data") or {}
    recs = ((d.get("records") if isinstance(d, dict) else d) or [])
    return _ok({"tasks": recs,
                "total": (d.get("total") if isinstance(d, dict) else len(recs)) or len(recs),
                "page": args.get("page") or 1})


def action_flow_task_info(args: dict) -> dict:
    """WDL 任务详情（含提交信息 / 输入输出 / 运行日志）。"""
    cfg = load_config()
    tid = str(args.get("task_id") or args.get("id") or "").strip()
    if not tid:
        return _err("需要参数 task_id（先用 action='flow_tasks' 查）")
    res = _run_cli(["workflow", "task_info", tid], cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "取任务详情失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"task_id": tid, "info": res.get("data")})


def action_task_cancel(args: dict) -> dict:
    """取消任务（kind='workflow' 走 workflow cancel -n；否则 analysis cancel <id>）。写操作。"""
    cfg = load_config()
    guard = _write_guard(cfg, "task_cancel")
    if guard:
        return guard
    tid = str(args.get("task_id") or args.get("id") or "").strip()
    if not tid:
        return _err("需要参数 task_id")
    kind = str(args.get("kind") or "analysis").strip().lower()
    if kind in ("workflow", "wdl", "w"):
        argv = ["workflow", "cancel", "-n", tid]
    else:
        argv = ["analysis", "cancel", tid]
    res = _run_cli(argv, cfg=cfg)
    if not res.get("ok"):
        return _err(res.get("message") or "取消失败", detail=res.get("error"), hint=res.get("hint"))
    return _ok({"task_id": tid, "kind": "workflow" if kind in ("workflow", "wdl", "w") else "analysis",
                "detail": res.get("data")})


# ---------------------------------------------------------------------------
# ⚡ 读缓存 + 先给旧值（stale-while-revalidate）
#   背景（2026-10-08 实测）：CLI 进程启动只 0.08s，真正慢的是云 API 往返 1.6–2.8s；
#   面板每开一次至少一次 `project ls`。策略：只读结果缓存；过期先回旧值、后台刷新；
#   写动作清空整表（宁旧勿错）；fresh=true 强制真跑；失败结果不入缓存。
# ---------------------------------------------------------------------------
_CACHE_TTL = {
    "projects": 45, "current": 30, "context": 30, "ls": 10, "find": 10, "info": 60,
    "tasks": 20, "task_logs": 15, "flows": 90, "flow_form": 180, "images": 600,
    "flow_tasks": 20, "flow_task_info": 15,
}
# 这些动作会改动云端或本地状态 → 清空缓存
_CACHE_CLEAR_ON = {
    "bind", "unbind", "use_project", "download", "upload", "container_open",
    "container_exec", "container_close", "flow_run", "analysis_run", "task_cancel", "raw",
}
_CACHE: dict = {}
_CACHE_LOCK = threading.RLock()
_CACHE_EPOCH = [0]
_CACHE_MAX = 128          # 条目上限，超了丢最旧的（防呆）


def _cache_key_for(action: str, args: dict):
    """缓存键：动作 + 与结果有关的参数（fresh / no_cache 不参与）。"""
    payload = {k: v for k, v in (args or {}).items() if k not in ("action", "fresh", "no_cache")}
    try:
        sig = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        sig = repr(sorted(payload.items()))
    return action + "|" + sig


def _cache_get(key):
    with _CACHE_LOCK:
        return _CACHE.get(key)


def _cache_put(key, value, epoch=None):
    """写缓存；若期间发生过清空（epoch 变了），丢掉这次的在途结果。"""
    with _CACHE_LOCK:
        if epoch is not None and epoch != _CACHE_EPOCH[0]:
            return False
        if len(_CACHE) >= _CACHE_MAX and key not in _CACHE:
            oldest = min(_CACHE.items(), key=lambda kv: kv[1].get("t", 0))[0]
            _CACHE.pop(oldest, None)
        _CACHE[key] = {"t": time.time(), "value": value, "refreshing": False, "hits": 0}
        return True


def _cache_touch(key):
    with _CACHE_LOCK:
        ent = _CACHE.get(key)
        if ent:
            ent["hits"] = ent.get("hits", 0) + 1
        return ent


def _cache_clear() -> int:
    with _CACHE_LOCK:
        n = len(_CACHE)
        _CACHE.clear()
        _CACHE_EPOCH[0] += 1
        return n


def _cache_mark(key, refreshing: bool):
    with _CACHE_LOCK:
        ent = _CACHE.get(key)
        if ent:
            ent["refreshing"] = refreshing


def _cache_refresh(key, action, args, epoch):
    """后台线程：真跑一次并回填（epoch 变了就丢弃）。"""
    try:
        clean = {k: v for k, v in (args or {}).items() if k not in ("fresh", "no_cache")}
        if action not in _ACTIONS:
            return
        res = _ACTIONS[action](clean)
        if isinstance(res, dict) and res.get("status") == "ok":
            _cache_put(key, res, epoch)
        else:
            _cache_mark(key, False)
    except Exception:
        logger.debug("缓存后台刷新失败 action=%s", action, exc_info=True)
        _cache_mark(key, False)


def _cache_wrap(action: str, args: dict, cfg: dict):
    """缓存命中判断。返回 (直接可用的响应, 或 None 表示要真跑)。"""
    ttl = _CACHE_TTL.get(action)
    if not ttl or _truthy((args or {}).get("fresh")) or _truthy((args or {}).get("no_cache")):
        return None
    key = _cache_key_for(action, args)
    ent = _cache_get(key)
    if not ent:
        return None
    ent = _cache_touch(key) or ent
    age = max(0.0, time.time() - float(ent.get("t") or 0))
    out = dict(ent.get("value") or {})
    out["cached"] = True
    out["age"] = round(age, 1)
    if age <= ttl:
        out["refreshing"] = False
        return {"key": key, "value": out, "hit": True, "stale": False}
    # 过期：先回旧值，后台刷新（同一键只起一个刷新线程）
    if not ent.get("refreshing"):
        _cache_mark(key, True)
        threading.Thread(target=_cache_refresh, args=(key, action, args, _CACHE_EPOCH[0]),
                         name="dcs-cache-%s" % action, daemon=True).start()
    out["refreshing"] = True
    return {"key": key, "value": out, "hit": True, "stale": True}


# 单飞：同一个键的并发请求只跑一次 CLI，其余等结果（悬停预热 + 紧接着点开就是这种情形）
_INFLIGHT: dict = {}


def _flight_begin(key):
    """返回 (flight, is_leader)。leader 负责真跑并 end；跟随者等 event。"""
    with _CACHE_LOCK:
        fl = _INFLIGHT.get(key)
        if fl:
            return fl, False
        fl = {"ev": threading.Event(), "t0": time.time()}
        _INFLIGHT[key] = fl
        return fl, True


def _flight_end(key):
    with _CACHE_LOCK:
        fl = _INFLIGHT.pop(key, None)
    if fl:
        fl["ev"].set()


def _flight_wait(flight, timeout: float) -> bool:
    """等 leader 跑完；真等到返回 True（结果在缓存里）。"""
    try:
        return bool(flight["ev"].wait(timeout=max(1.0, timeout)))
    except Exception:
        return False


def _split_raw_cmd(text) -> list:
    """把用户输入切成 argv。三种口径，按优先级：

    * **JSON 数组** —— ``["analysis","run","-i","sh /work/x.sh"]``：唯一能 100% 表达的方式，
      工具/模型推荐用这种；
    * **含引号的字符串** —— 按 shell 规则切，让 ``-i "sh /work/x.sh"`` 这种带空格的参数活下来；
    * **其余** —— 按空白切（老行为；Windows 反斜杠路径不受影响）。

    背景（2026-10-07）：以前一律空白切，投递命令 ``analysis run -i "sh /x.sh"`` 会被拆成
    ``"sh`` + ``/x.sh"`` 两个参数，命令根本发不出去。
    """
    s = str(text or "").strip()
    if not s:
        return []
    if s[0] in "[{":
        try:
            v = json.loads(s)
        except Exception:
            v = None
        if isinstance(v, list):
            return [str(x) for x in v if str(x).strip()]
    if '"' in s or "'" in s:
        try:
            parts = shlex.split(s)
        except Exception:
            parts = []
        if parts:
            return [str(x) for x in parts if str(x).strip()]
    return s.split()


_RAW_ALLOWED = {"project", "data", "table", "terminal", "analysis", "workflow",
                "image", "billing", "region", "history"}
_RAW_FORBIDDEN = {"auth", "login", "logout", "config"}


def action_raw(args: dict) -> dict:
    """白名单逃生舱：跑任意 dcs 子命令（凭据类子命令除外）。"""
    cfg = load_config()
    raw = args.get("command") or args.get("args") or []
    if isinstance(raw, str):
        raw = _split_raw_cmd(raw)
    raw = [str(x) for x in raw if str(x).strip()]
    if not raw:
        return _err("需要参数 command（字符串或数组，例如 \"project detail --code P123\"）")
    head = raw[0].lower()
    if head in _RAW_FORBIDDEN:
        return _err("凭据类子命令不允许走 raw：绑定用 bind、解绑用 unbind")
    if head not in _RAW_ALLOWED:
        return _err("raw 只放行这些子命令：%s" % ", ".join(sorted(_RAW_ALLOWED)))
    res = _run_cli(raw, cfg=cfg)
    payload = {"cmd": res.get("cmd"), "data": res.get("data")}
    if not res.get("ok"):
        return _err(res.get("message") or "命令失败", detail=res.get("error"),
                    hint=res.get("hint"), **_clip(cfg, payload))
    return _ok(_clip(cfg, payload))


def action_context(args: dict) -> dict:
    """一次拿齐「开工前确认」需要的上下文（只读：不切项目、不动数据）。

    用户说「在云平台/GenPilot 上跑分析」「投递任务」时，模型先调这个，再用 ask_user 把
    项目、数据位置、参数、输出、费用问清楚 —— 用户有很多项目，**不能替他默认**。
    """
    cfg = load_config()
    out: dict = {"read_only": True}
    r = _run_cli(["config", "show"], cfg=cfg)
    if r.get("ok"):
        d = r.get("data") or {}
        out["session"] = {k: d.get(k) for k in (
            "current_user", "current_project", "current_region", "data_cwd",
            "login_time", "base_url", "copilot_base_url", "lang")}
        out["available_regions"] = (d.get("available_regions") or [])[:12]
    else:
        out["session_error"] = r.get("message")
    r2 = _run_cli(["project", "ls"], cfg=cfg)
    if r2.get("ok"):
        d2 = r2.get("data") or {}
        plist = d2.get("projects") or []
        out["projects"] = [{
            "project_id": p.get("project_id"),
            "project_name": p.get("project_name"),
            "region": p.get("region"),
            "current": bool(p.get("current")),
            "is_arrears": bool(p.get("is_arrears")),
        } for p in plist]
        out["projects_total"] = d2.get("total")
        out["projects_page"] = d2.get("page")
    else:
        out["projects_error"] = r2.get("message")
    if _truthy(args.get("with_files", True)):
        path = str(args.get("path") or "/Files")
        r3 = _run_cli(["data", "ls", path], cfg=cfg)
        if r3.get("ok"):
            d3 = r3.get("data") or {}
            items = (d3.get("items") or []) if isinstance(d3, dict) else []
            out["data_root"] = {
                "path": (d3.get("path") if isinstance(d3, dict) else None) or path,
                "total": (d3.get("total") if isinstance(d3, dict) else None),
                "dirs": [i.get("name") for i in items if i.get("is_directory")][:20],
                "files": [i.get("name") for i in items if not i.get("is_directory")][:10],
            }
        else:
            out["data_root_error"] = r3.get("message")
    out["download_dir"] = cfg.get("download_dir") or ""
    out["allow_write"] = bool(cfg.get("allow_write"))
    out["questions"] = [
        "① 用哪个项目？（当前项目只是候选，用户有多个项目时必须让他确认，尤其投递/计费前）",
        "② 数据在哪？本机路径 / 云上 /Files 路径 / 云容器内 /work 路径 —— 三套文件系统不互通，先 ls 确认",
        "③ 跑什么？分析类型或流程名；投递必须写清流程 + 参数 + 输出目录",
        "④ 结果回哪里？云上输出目录，或下载到本机哪个目录（download_dir 是默认值）",
        "⑤ 费用与资源：项目是否欠费？开容器/投递会产生费用，是否确认继续",
    ]
    out["rules"] = [
        "不问清不动手：项目/数据/参数/输出/费用确认完再执行（铁律 27/28/35）",
        "不替用户默认项目：只有用户明说「就用当前项目」或 config 配了 default_project 才直接用",
        "投递任务 / 上传 / 开容器属高代价写操作：先弹意图确认（ask_user kind='intent'）再执行",
        "欠费项目先充值再投递（平台会拦；context 的 projects[].is_arrears 可直接判断）",
        "MemOmics 只是中介：真正干活的是云平台（GenPilot / 离线任务），本地只负责取数与后处理",
    ]
    return _ok(out)


_ACTIONS = {
    "flows": action_flows,
    "flow_form": action_flow_form,
    "flow_run": action_flow_run,
    "analysis_run": action_analysis_run,
    "images": action_images,
    "flow_tasks": action_flow_tasks,
    "flow_task_info": action_flow_task_info,
    "task_cancel": action_task_cancel,
    "status": action_status,
    "bind": action_bind,
    "unbind": action_unbind,
    "projects": action_projects,
    "use_project": action_use_project,
    "current": action_current,
    "context": action_context,
    "ls": action_ls,
    "find": action_find,
    "info": action_info,
    "download": action_download,
    "upload": action_upload,
    "container_open": action_container_open,
    "container_exec": action_container_exec,
    "container_close": action_container_close,
    "tasks": action_tasks,
    "task_logs": action_task_logs,
    "raw": action_raw,
}


def dcs_cloud_handler(args: dict | None = None, **kwargs):
    """工具/HTTP 共用的统一入口：返回 JSON 字符串（与 remote_cluster 同款约定）。"""
    args = dict(args or {})
    cfg = load_config()
    action = str(args.get("action") or "").strip().lower()
    if not action:
        action = "status"
    if action not in _ACTIONS:
        return json.dumps(_err("未知 action: %r（可选：%s）" % (action, ", ".join(sorted(_ACTIONS)))),
                          ensure_ascii=False, indent=2)
    if not cfg.get("enabled") and action not in ("status", "bind", "unbind"):
        return json.dumps(_err("DCS 连接器未启用（config.yaml 的 dcs_cloud.enabled=false）",
                               hint="在 WebUI「☁️ DCS 云」面板或 config.yaml 打开开关"),
                          ensure_ascii=False, indent=2)
    if action not in ("status", "bind", "unbind"):
        cred = read_credential()
        if not cred.get("pat"):
            return json.dumps(_err("未绑定 DCS 账号",
                                   hint="让用户在「☁️ DCS 云」面板粘贴 PAT（个人中心 → 访问令牌 → 创建）后重试"),
                              ensure_ascii=False, indent=2)
    cached_hit = _cache_wrap(action, args, cfg)
    if cached_hit:
        return json.dumps(_clip(cfg, cached_hit["value"]), ensure_ascii=False, indent=2)
    flight_key = None
    if action in _CACHE_TTL and not _truthy(args.get("fresh")):
        flight_key = _cache_key_for(action, args)
        flight, leader = _flight_begin(flight_key)
        if not leader:
            waited = _flight_wait(flight, min(90, int(cfg.get("timeout") or 120)))
            ent = _cache_get(flight_key)
            if waited and ent and ent.get("value"):
                shared = dict(ent["value"])
                shared["cached"] = True
                shared["age"] = 0.0
                shared["shared"] = True
                return json.dumps(_clip(cfg, shared), ensure_ascii=False, indent=2)
            flight_key = None      # 等超时/leader 失败：自己跑，别去 end 别人的飞行
    try:
        result = _ACTIONS[action](args)
    except Exception as exc:      # 任何未预期异常都变成结构化错误，别让工具链崩
        logger.exception("dcs_cloud action=%s 失败", action)
        result = _err("%s 执行失败: %s" % (action, exc),
                      hint="先用 action='status' 看绑定与 CLI 状态")
        if flight_key:
            _flight_end(flight_key)
            flight_key = None
    if not isinstance(result, dict):
        result = _ok({"result": result})
    if action in _CACHE_CLEAR_ON:
        _cache_clear()
    elif action in _CACHE_TTL and result.get("status") == "ok":
        _cache_put(_cache_key_for(action, args), result)
    if flight_key:
        _flight_end(flight_key)
    try:
        return json.dumps(_clip(cfg, result), ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps(_err("结果序列化失败: %s" % exc), ensure_ascii=False)


__all__ = [
    "load_config", "dcs_cloud_enabled", "dcs_cloud_handler",
    "resolve_cli", "read_credential", "save_credential", "clear_credential",
    "mask_pat", "vault_path", "VAULT_FILENAME",
]