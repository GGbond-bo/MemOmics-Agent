# -*- coding: utf-8 -*-
"""沙箱能力探测（P1-4）：fail-closed 原则

探测本机可用的代码执行沙箱（Docker / WSL2 / bubblewrap / Seatbelt）。
无沙箱（degraded）时：
  - 写白名单外路径的代码直接拒绝（静态检查）
  - 探测失败一律按未沙箱处理（fail-closed，绝不误报已沙箱）

可写路径白名单：MEMOMICS_ALLOWED_WRITE_ROOTS（分号分隔绝对路径）；
未配置时默认 = 当前工作目录 + 系统临时目录。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

_ALLOWED_WRITE_ROOTS_ENV = "MEMOMICS_ALLOWED_WRITE_ROOTS"

# 明确写文件的 API（分析脚本常见），避免误伤 open('r') 读取
_WRITE_API_RE = re.compile(
    r"""(?:to_csv|to_excel|to_json|savefig|write_text|write_bytes|writelines|save)\s*\(\s*["']([^"']+)["']"""
)
_OPEN_WRITE_RE = re.compile(
    r"""open\s*\(\s*["']([^"']+)["']\s*,\s*["'][wa]""", re.IGNORECASE
)


def probe_sandbox_capability() -> dict:
    """探测沙箱能力。返回 {sandboxed, backends, degraded, detail}"""
    backends = []
    # Docker
    _docker = shutil.which("docker")
    if _docker:
        try:
            r = subprocess.run([_docker, "info"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
            if r.returncode == 0:
                backends.append("docker")
        except Exception:
            pass
    # WSL2（Windows）
    if os.name == "nt":
        for cand in (shutil.which("wsl"), r"C:\Windows\System32\wsl.exe"):
            if cand:
                try:
                    r = subprocess.run([cand, "--status"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
                    if r.returncode == 0 or "Default" in r.stdout or "默认" in r.stdout:
                        backends.append("wsl2")
                except Exception:
                    pass
                break
    # bubblewrap（Linux）
    if shutil.which("bwrap"):
        backends.append("bwrap")
    # Seatbelt（macOS）
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        backends.append("seatbelt")

    sandboxed = bool(backends)
    return {
        "sandboxed": sandboxed,
        "backends": backends,
        "degraded": not sandboxed,
        "detail": "沙箱后端: " + (", ".join(backends) if backends else "无（degraded 模式：写白名单外路径将被拒绝）"),
    }


def get_allowed_write_roots() -> list:
    """白名单根目录（MEMOMICS_ALLOWED_WRITE_ROOTS，分号分隔）；空则 cwd + temp"""
    raw = os.environ.get(_ALLOWED_WRITE_ROOTS_ENV, "")
    roots = []
    for p in raw.split(";"):
        p = p.strip()
        if p:
            roots.append(os.path.abspath(os.path.expanduser(p)))
    if not roots:
        roots = [os.getcwd(), tempfile.gettempdir()]
    return roots


def is_write_path_allowed(target: str) -> bool:
    """写入目标是否在白名单内（相对路径基于 cwd 解析；cwd 始终允许）"""
    if not target or target.startswith(("http://", "https://", "ftp://", "~")):
        return False
    try:
        t = os.path.abspath(os.path.expanduser(target))
    except Exception:
        return False
    # cwd 始终允许（分析脚本写工作目录是基本权利）
    cwd = os.getcwd().rstrip(os.sep)
    if t == cwd or t.startswith(cwd + os.sep):
        return True
    for r in get_allowed_write_roots():
        base = r.rstrip(os.sep)
        if t == base or t.startswith(base + os.sep):
            return True
    return False


def check_script_write_roots(code: str) -> list:
    """静态检查脚本写文件目标；返回白名单外路径列表（空 = 通过）"""
    violations = []
    seen = set()
    for m in _WRITE_API_RE.finditer(code):
        p = m.group(1).strip()
        if p and p not in seen and not is_write_path_allowed(p):
            seen.add(p)
            violations.append(p)
    for m in _OPEN_WRITE_RE.finditer(code):
        p = m.group(1).strip()
        if p and p not in seen and not is_write_path_allowed(p):
            seen.add(p)
            violations.append(p)
    return violations
