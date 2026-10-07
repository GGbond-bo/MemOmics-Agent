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
import subprocess
import sys
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
    res = _run_cli(["project", "ls"], cfg=cfg)
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


_RAW_ALLOWED = {"project", "data", "table", "terminal", "analysis", "workflow",
                "image", "billing", "region", "history"}
_RAW_FORBIDDEN = {"auth", "login", "logout", "config"}


def action_raw(args: dict) -> dict:
    """白名单逃生舱：跑任意 dcs 子命令（凭据类子命令除外）。"""
    cfg = load_config()
    raw = args.get("command") or args.get("args") or []
    if isinstance(raw, str):
        raw = raw.split()
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


_ACTIONS = {
    "status": action_status,
    "bind": action_bind,
    "unbind": action_unbind,
    "projects": action_projects,
    "use_project": action_use_project,
    "current": action_current,
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
    try:
        result = _ACTIONS[action](args)
    except Exception as exc:      # 任何未预期异常都变成结构化错误，别让工具链崩
        logger.exception("dcs_cloud action=%s 失败", action)
        result = _err("%s 执行失败: %s" % (action, exc),
                      hint="先用 action='status' 看绑定与 CLI 状态")
    if not isinstance(result, dict):
        result = _ok({"result": result})
    try:
        return json.dumps(_clip(cfg, result), ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps(_err("结果序列化失败: %s" % exc), ensure_ascii=False)


__all__ = [
    "load_config", "dcs_cloud_enabled", "dcs_cloud_handler",
    "resolve_cli", "read_credential", "save_credential", "clear_credential",
    "mask_pat", "vault_path", "VAULT_FILENAME",
]