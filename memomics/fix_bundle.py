# -*- coding: utf-8 -*-
"""修复包迁移器（Fix Bundle）——让已安装的旧版本在启动时自动应用"文件级修复"。

背景（2026-08-16）：修复分两类——
  代码级修复（server.py/enforcement.py/execute_r 等）只能靠换新包文件生效；
  文件级修复（config.yaml 限额等）可以在旧代码上直接迁移生效。
本模块负责后者：幂等、只动旧默认值（用户自定义过的值不碰）、
写 memomics_home/.fix_bundle 标记当前修复级别，供 /api/version 报告新旧。

调用方：
  scripts/apply_fix_bundle.py（start.bat 启动时）
  webui/server.py 启动事件（Linux/macOS/Cluster 直接跑 server 的场景）
"""
from __future__ import annotations

import os
import re

BUNDLE = "2026-10-10"  # 本次修复包级别（新增迁移时递增）

_CONFIG_MIGRATIONS = (
    # (字段, 旧默认值, 新值)
    ("memory_char_limit", "10000", "30000"),
    ("user_char_limit", "10000", "30000"),
)


def _migrate_config(memomics_home: str) -> str:
    """config.yaml 记忆限额 10000→30000（仅当恰为旧默认值时迁移）。"""
    p = os.path.join(memomics_home, "config.yaml")
    if not os.path.isfile(p):
        return "config.yaml 不存在，跳过"
    try:
        with open(p, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception as e:
        return f"config 读取失败: {e}"
    lines = txt.splitlines(keepends=True)
    out, changed = [], 0
    for line in lines:
        m = re.match(r"^(\s*)(memory_char_limit|user_char_limit):\s*10000\s*(\r?\n)$", line)
        if m:
            out.append(f"{m.group(1)}{m.group(2)}: 30000{m.group(3)}")
            changed += 1
        else:
            out.append(line)
    if changed:
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write("".join(out))
        except Exception as e:
            return f"config 写回失败: {e}"
    return f"限额迁移 {changed} 项"


# 2026-10-10：依赖自愈 —— 老安装更新 update 包后，新功能可能需要新依赖；
# 随包 .venv 不会被覆盖，所以这里用"当前解释器"补装 requirements.txt。
# 触发条件（幂等）：requirements.txt 哈希变了，或关键包 import 失败。
# 失败不阻塞启动（下次启动重试）；MEMOMICS_SKIP_DEPS_SYNC=1 可跳过。
_CRIT_CAND = (
    ("fastapi", "fastapi"), ("starlette", "starlette"), ("uvicorn", "uvicorn"),
    ("websockets", "websockets"), ("httpx", "httpx"), ("pydantic", "pydantic"),
    ("yaml", "pyyaml"), ("openai", "openai"), ("multipart", "python-multipart"),
    ("openpyxl", "openpyxl"), ("PIL", "pillow"), ("docx", "python-docx"),
    ("pptx", "python-pptx"), ("pandas", "pandas"), ("aiofiles", "aiofiles"),
)


def _critical_modules(requirements_txt: str):
    """只检查 requirements.txt 里确实声明的关键包。"""
    try:
        with open(requirements_txt, "r", encoding="utf-8", errors="replace") as f:
            req = f.read().lower()
    except Exception:
        req = ""
    out = []
    for mod, pkg in _CRIT_CAND:
        if pkg in req:
            out.append(mod)
    return out


def _missing_modules(requirements_txt: str):
    import importlib
    miss = []
    for mod in _critical_modules(requirements_txt):
        try:
            importlib.import_module(mod)
        except Exception:
            miss.append(mod)
    return miss


def _deps_sync(memomics_home: str) -> str:
    """requirements.txt 变化或关键包缺失 → 用当前解释器补装（幂等，失败不阻塞）。"""
    import hashlib
    import json
    import subprocess
    import sys
    import time

    if os.environ.get("MEMOMICS_SKIP_DEPS_SYNC") == "1":
        return "已跳过（MEMOMICS_SKIP_DEPS_SYNC=1）"
    root = os.path.dirname(os.path.abspath(memomics_home.rstrip("/\\"))) or os.getcwd()
    req = os.path.join(root, "requirements.txt")
    if not os.path.isfile(req):
        return "无 requirements.txt，跳过"
    try:
        h = hashlib.sha256(open(req, "rb").read()).hexdigest()[:16]
    except Exception as e:
        return f"requirements 读取失败: {e}"
    state_p = os.path.join(memomics_home, ".deps_state.json")
    old = {}
    try:
        old = json.load(open(state_p, "r", encoding="utf-8")) or {}
    except Exception:
        old = {}
    miss = _missing_modules(req)
    same = (old.get("req_hash") == h)
    if same and not miss:
        return "依赖一致（%s）" % h
    why = []
    if not same:
        why.append("requirements 已更新")
    if miss:
        why.append("缺包: " + ", ".join(miss))
    print("[DepsSync] %s → pip install -r requirements.txt（首次可能几分钟）" % "；".join(why), flush=True)
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-user",
             "--disable-pip-version-check", "-q", "-r", req],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800,
        )
        ok = (r.returncode == 0)
        tail = (r.stdout or "")[-400:] + (r.stderr or "")[-800:]
    except Exception as e:
        ok = False
        tail = f"{type(e).__name__}: {e}"
    if not ok:
        print("[DepsSync] 补装未成功（不影响启动，下次启动重试）: %s" % tail.strip()[-300:], flush=True)
        return "补装失败: %s" % tail.strip()[-120:]
    miss2 = _missing_modules(req)
    try:
        json.dump({"req_hash": h, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "missing": miss2},
                  open(state_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass
    if miss2:
        return "补装完成但仍有缺失: %s" % ", ".join(miss2)
    print("[DepsSync] 依赖已就绪", flush=True)
    return "依赖已就绪（%s）" % h


def _tidy_from_hermes_dupes(memomics_home: str) -> tuple:
    """清掉迁移留下的、与本体逐字节相同的 .from_hermes_* 备份（零信息损失）。

    2026-10-10：用户实测一次更新产生 2290 个重复备份；这里只删"内容完全相同"的，
    有差异的一律保留（真正的用户改动不会被删）；>8MB 的不比较，直接保留。
    """
    import hashlib
    removed = kept = 0
    if not memomics_home or not os.path.isdir(memomics_home):
        return 0, 0
    for root, dirs, files in os.walk(memomics_home):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if ".from_hermes_" not in name:
                continue
            path = os.path.join(root, name)
            base = os.path.join(root, name.split(".from_hermes_")[0])
            try:
                if not os.path.isfile(base):
                    kept += 1
                    continue
                sa, sb = os.path.getsize(base), os.path.getsize(path)
                if sa != sb or sa > 8 * 1024 * 1024:
                    kept += 1
                    continue
                with open(base, "rb") as f:
                    ha = hashlib.sha256(f.read()).hexdigest()
                with open(path, "rb") as f:
                    hb = hashlib.sha256(f.read()).hexdigest()
                if ha == hb:
                    os.remove(path)
                    removed += 1
                else:
                    kept += 1
            except OSError:
                kept += 1
    return removed, kept


def apply_fix_bundle(memomics_home: str, dry_run: bool = False) -> dict:
    """应用文件级迁移并推进 .fix_bundle 标记。幂等。"""
    os.makedirs(memomics_home, exist_ok=True)
    marker = os.path.join(memomics_home, ".fix_bundle")
    try:
        with open(marker, "r", encoding="utf-8") as f:
            cur = f.read().strip()
    except Exception:
        cur = ""
    if cur >= BUNDLE:
        return {"ok": True, "up_to_date": True, "bundle": cur}
    result = {"config": _migrate_config(memomics_home)}
    # 2026-10-10: 依赖自愈（老安装更新后功能要齐，必须把 requirements 补上）
    try:
        result["deps"] = _deps_sync(memomics_home)
    except Exception as _e:
        result["deps"] = f"跳过（{type(_e).__name__}: {_e}）"
    if not dry_run:
        try:
            with open(marker, "w", encoding="utf-8") as f:
                f.write(BUNDLE)
        except Exception as e:
            result["marker_error"] = str(e)
    try:
        _rm, _kp = _tidy_from_hermes_dupes(memomics_home)
        result["tidy"] = "清理重复迁移备份 %d 个（保留有差异的 %d 个）" % (_rm, _kp)
    except Exception as exc:
        result["tidy"] = "跳过：%s" % exc

    return {"ok": True, "up_to_date": False, "from": cur or "none",
            "to": BUNDLE, "migrations": result}


def fix_bundle_level(memomics_home: str) -> str:
    """当前安装的修复级别（无标记 → 空串 = 旧安装）。"""
    try:
        p = os.path.join(memomics_home, ".fix_bundle")
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""
