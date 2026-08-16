# -*- coding: utf-8 -*-
"""修复包迁移器（Fix Bundle）——让已安装的旧版本在启动时自动应用"文件级修复"。

背景（2026-08-16）：修复分两类——
  代码级修复（server.py/enforcement.py/execute_r 等）只能靠换新包文件生效；
  文件级修复（config.yaml 限额等）可以在旧代码上直接迁移生效。
本模块负责后者：幂等、只动旧默认值（用户自定义过的值不碰）、
写 hermes_home/.fix_bundle 标记当前修复级别，供 /api/version 报告新旧。

调用方：
  scripts/apply_fix_bundle.py（start.bat 启动时）
  webui/server.py 启动事件（Linux/macOS/Cluster 直接跑 server 的场景）
"""
from __future__ import annotations

import os
import re

BUNDLE = "2026-08-16"  # 本次修复包级别（新增迁移时递增）

_CONFIG_MIGRATIONS = (
    # (字段, 旧默认值, 新值)
    ("memory_char_limit", "10000", "30000"),
    ("user_char_limit", "10000", "30000"),
)


def _migrate_config(hermes_home: str) -> str:
    """config.yaml 记忆限额 10000→30000（仅当恰为旧默认值时迁移）。"""
    p = os.path.join(hermes_home, "config.yaml")
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


def apply_fix_bundle(hermes_home: str, dry_run: bool = False) -> dict:
    """应用文件级迁移并推进 .fix_bundle 标记。幂等。"""
    os.makedirs(hermes_home, exist_ok=True)
    marker = os.path.join(hermes_home, ".fix_bundle")
    try:
        with open(marker, "r", encoding="utf-8") as f:
            cur = f.read().strip()
    except Exception:
        cur = ""
    if cur >= BUNDLE:
        return {"ok": True, "up_to_date": True, "bundle": cur}
    result = {"config": _migrate_config(hermes_home)}
    if not dry_run:
        try:
            with open(marker, "w", encoding="utf-8") as f:
                f.write(BUNDLE)
        except Exception as e:
            result["marker_error"] = str(e)
    return {"ok": True, "up_to_date": False, "from": cur or "none",
            "to": BUNDLE, "migrations": result}


def fix_bundle_level(hermes_home: str) -> str:
    """当前安装的修复级别（无标记 → 空串 = 旧安装）。"""
    try:
        p = os.path.join(hermes_home, ".fix_bundle")
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""
