# -*- coding: utf-8 -*-
"""computer_use 的 cua-driver 定位引导（2026-09-25）。

为什么需要这个模块
------------------
Hermes 的 `computer_use` 工具集（截屏 / 鼠标 / 键盘 / 窗口）由外部二进制
cua-driver 驱动，而 `hermes-agent/tools/computer_use/cua_backend.py` 在 **import 时**
只读一次 `HERMES_CUA_DRIVER_CMD`（缺省 "cua-driver"），之后用 `shutil.which()`
判断可用性。找不到二进制时工具不是报错，而是**整个从模型的工具表里消失**。

官方安装器把二进制放进用户目录，并把该目录**追加到 User PATH**：

  Windows      %LOCALAPPDATA%/Programs/Cua/cua-driver/bin/cua-driver.exe
  macOS/Linux  ~/.local/bin/cua-driver（或 /usr/local/bin、/opt/homebrew/bin）

PATH 是进程启动时冻结的快照：装完不重开终端（更别说已经在跑的 8899 服务），
`shutil.which("cua-driver")` 就是 None。用户看到的现象是"MemOmics 不能操控电脑"，
真实原因只是没找到二进制。

本模块在 Hermes 工具被 import 之前跑一次：

1. `HERMES_CUA_DRIVER_CMD` 已被显式设置 → 完全尊重，不动；
2. 否则 PATH → 各平台已知安装位置 依次定位；
3. 命中 → 写回 `HERMES_CUA_DRIVER_CMD`（绝对路径，不依赖 PATH）；
4. 都没命中 → 不报错（工具优雅缺席），只留一行安装提示。

定位逻辑与平台无关地可测：`env` / `platform` / `which` 都可注入。
"""
from __future__ import annotations

import os
import shutil
import sys

CUA_DRIVER_ENV = "HERMES_CUA_DRIVER_CMD"
DEFAULT_CMD = "cua-driver"

# 官方安装器的落点（用正斜杠书写，Windows 也接受，最终 normpath 归一）。
_WIN_CANDIDATES = (
    "%LOCALAPPDATA%/Programs/Cua/cua-driver/bin/cua-driver.exe",
    "%USERPROFILE%/.cua-driver/packages/current/cua-driver.exe",
    "%LOCALAPPDATA%/Programs/cua-driver/cua-driver.exe",
)
_POSIX_CANDIDATES = (
    "~/.local/bin/cua-driver",
    "/usr/local/bin/cua-driver",
    "/opt/homebrew/bin/cua-driver",
    "~/.cua-driver/packages/current/cua-driver",
)

INSTALL_HINT = (
    "cua-driver 未找到：computer_use（截屏/鼠标/键盘）将不可用。"
    "启用方式：hermes computer-use install（macOS/Windows/Linux 均支持）"
)


def _expand(item, env):
    """只从**注入的 env** 展开 ~ 与 %VAR%（不用 os.path.expandvars —— 它会读真实
    进程环境，导致注入 env 的测试在装了 cua-driver 的机器上假绿/假红）。
    变量缺失返回 ""，调用方跳过该候选。"""
    if item.startswith("~"):
        home = env.get("USERPROFILE") or env.get("HOME") or ""
        if not home:
            return ""
        item = home.rstrip("/\\") + item[1:]
    for var in ("LOCALAPPDATA", "USERPROFILE"):
        token = "%" + var + "%"
        if token in item:
            val = env.get(var)
            if not val:
                return ""
            item = item.replace(token, val)
    return "" if "%" in item else item


def candidate_paths(env=None, platform=None):
    """返回该平台的已知安装位置（已展开变量，不判断是否存在）。"""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    raw = _WIN_CANDIDATES if platform.startswith("win") else _POSIX_CANDIDATES
    out = []
    for item in raw:
        p = _expand(item, env)
        if p:
            out.append(os.path.normpath(p))
    return out


def locate(env=None, platform=None, which=None):
    """PATH → 已知安装位置。返回绝对路径；找不到返回 ""。"""
    env = os.environ if env is None else env
    which = shutil.which if which is None else which
    hit = which(DEFAULT_CMD)
    if hit:
        return os.path.normpath(hit)
    for p in candidate_paths(env=env, platform=platform):
        if os.path.isfile(p):
            return p
    return ""


def ensure_cua_driver_env(env=None, platform=None, which=None, log=None):
    """把 cua-driver 的绝对路径写进 HERMES_CUA_DRIVER_CMD。返回最终生效的命令。

    - 已显式配置 → 原样返回（绝不覆盖用户/运维的显式选择）；
    - 定位到 → 写入并返回绝对路径；
    - 定位不到 → 返回 ""，仅当传入 log 时留一行提示。
    """
    env = os.environ if env is None else env
    explicit = (env.get(CUA_DRIVER_ENV) or "").strip()
    if explicit:
        return explicit
    found = locate(env=env, platform=platform, which=which)
    if found:
        env[CUA_DRIVER_ENV] = found
        if log:
            log("[computer_use] cua-driver -> " + found)
        return found
    if log:
        log("[computer_use] " + INSTALL_HINT)
    return ""
