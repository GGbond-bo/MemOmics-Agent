"""权限档位（借鉴 DSH 的 permission-presets：一档 = sandbox 档 + 审批策略）。

MemOmics 现在没有 OS 级沙箱（本模块不改这一点），而是把「什么工具能做什么」收成三档，
在 enforcement 的统一 pre-tool 钩子上强制，行为对齐 DSH 的档位语义：

    read-only           只读：禁一切写文件 / 执行命令 / 有副作用的研究动作
    workspace-write     工作区写：只允许写会话工作区（cwd + results_dir），执行命令仍过门禁
    danger-full-access  不限（**默认**，与改动前行为一致，避免打断在跑的研究流程）

取值优先级：env MEMOMICS_SANDBOX_MODE > config.yaml 的 sandbox.mode > 默认 danger-full-access。
改档位：`python scripts/set_permission_mode.py workspace-write`（或在 config.yaml 手改）。
"""
from __future__ import annotations

import os
from typing import Iterable, Optional, Tuple

MODE_READ_ONLY = "read-only"
MODE_WORKSPACE_WRITE = "workspace-write"
MODE_DANGER_FULL = "danger-full-access"
MODES = (MODE_READ_ONLY, MODE_WORKSPACE_WRITE, MODE_DANGER_FULL)
DEFAULT_MODE = MODE_DANGER_FULL

# 写类工具（名字含这些关键字即视为会落盘）
_WRITE_HINTS = ("write", "edit", "patch", "save_", "create_", "mkdir", "rename",
                "delete", "remove_", "move_", "upload", "append")
# 执行类工具
_EXEC_TOOLS = {"terminal", "execute_python", "execute_r", "code_execution",
               "computer_use", "bash", "shell", "subprocess", "run_command"}
# 只读探测：这些即使名字里带 write/save 也放行（避免误拦自身状态写入）
_ALWAYS_ALLOW = {"read_file", "list_files", "glob", "grep", "search_files",
                 "session_search", "skill_view", "list_sessions", "recall"}

_PATH_KEYS = ("path", "file_path", "target", "target_file", "filename", "file",
              "dest", "destination", "output_path", "out", "cwd", "workdir", "dir")


def _cfg() -> dict:
    try:
        from hermes_cli.config import read_raw_config
        cfg = read_raw_config() or {}
        section = cfg.get("sandbox")
        return section if isinstance(section, dict) else {}
    except Exception:
        return {}


def get_mode() -> str:
    env = (os.environ.get("MEMOMICS_SANDBOX_MODE") or "").strip().lower()
    if env in MODES:
        return env
    cfg_mode = str(_cfg().get("mode") or "").strip().lower()
    if cfg_mode in MODES:
        return cfg_mode
    return DEFAULT_MODE


def set_mode(mode: str) -> bool:
    mode = str(mode or "").strip().lower()
    if mode not in MODES:
        return False
    try:
        from hermes_cli.config import read_raw_config, atomic_config_write, get_config_path
        cfg = read_raw_config() or {}
        section = cfg.get("sandbox")
        if not isinstance(section, dict):
            section = {}
        section["mode"] = mode
        cfg["sandbox"] = section
        atomic_config_write(get_config_path(), cfg)
        return True
    except Exception:
        return False


def allowed_roots(session: Optional[dict] = None) -> list:
    """workspace-write 档允许写入的根：会话工作区（results_dir）+ 进程 cwd。"""
    roots = []
    try:
        rd = (session or {}).get("results_dir") or ""
        if rd:
            roots.append(os.path.abspath(rd))
    except Exception:
        pass
    try:
        roots.append(os.path.abspath(os.getcwd()))
    except Exception:
        pass
    out = []
    for r in roots:
        try:
            rp = os.path.normcase(os.path.normpath(r))
            if rp and rp not in out:
                out.append(rp)
        except Exception:
            continue
    return out


def _under(path: str, roots: Iterable[str]) -> bool:
    try:
        p = os.path.normcase(os.path.abspath(path))
    except Exception:
        return False
    for r in roots:
        if p == r or p.startswith(r + os.sep):
            return True
    return False


def _args_dict(args) -> dict:
    if isinstance(args, dict):
        return args
    try:
        import json
        v = json.loads(args) if isinstance(args, (str, bytes)) else {}
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def classify_tool(tool_name: str, args=None) -> str:
    """把工具归成 read / write / exec 三类（未知工具按 read 处理，档位不额外收紧）。"""
    name = (tool_name or "").strip().lower()
    if name in _ALWAYS_ALLOW:
        return "read"
    if name in _EXEC_TOOLS or name.endswith("_exec") or name.startswith("terminal"):
        return "exec"
    if any(h in name for h in _WRITE_HINTS):
        return "write"
    return "read"


def check(tool_name: str, args=None, session: Optional[dict] = None) -> Tuple[bool, str]:
    """返回 (allowed, reason)。allowed=False 时 enforcement 应拦下该次工具调用。"""
    mode = get_mode()
    if mode == MODE_DANGER_FULL:
        return True, ""
    kind = classify_tool(tool_name, args)
    if kind == "read":
        return True, ""
    if mode == MODE_READ_ONLY:
        return False, (f"权限档位 read-only：禁止 {kind} 类工具（{tool_name}）。"
                       "需要落盘/执行时把 sandbox.mode 切到 workspace-write 或 danger-full-access。")
    # workspace-write：写必须有可判定的路径且落在允许根内；exec 允许（仍过其它门禁）
    if kind == "write":
        argsd = _args_dict(args)
        target = ""
        for k in _PATH_KEYS:
            v = argsd.get(k)
            if isinstance(v, str) and v.strip():
                target = v.strip()
                break
        roots = allowed_roots(session)
        if target and not _under(target, roots):
            return False, (f"权限档位 workspace-write：写入目标 {target} 不在会话工作区内"
                           f"（允许：{', '.join(roots[:2]) or '无'}）。"
                           "确需写到别处请把 sandbox.mode 切到 danger-full-access。")
        return True, ""
    return True, ""
