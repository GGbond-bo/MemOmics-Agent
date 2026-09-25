# -*- coding: utf-8 -*-
"""cua_bootstrap 的定位逻辑测试（全部 hermetic，不碰真实 PATH/安装目录）。"""
import os
import sys

import pytest

try:
    from webui.cua_bootstrap import (
        CUA_DRIVER_ENV,
        candidate_paths,
        ensure_cua_driver_env,
        locate,
    )
except ImportError:  # pragma: no cover - 直接以 webui/tests 为 rootdir 时
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from webui.cua_bootstrap import (  # type: ignore
        CUA_DRIVER_ENV,
        candidate_paths,
        ensure_cua_driver_env,
        locate,
    )


def _fake_exe(path):
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("stub")
    return path


def test_explicit_env_is_never_overridden():
    env = {CUA_DRIVER_ENV: "D:/custom/cua-driver.exe"}
    called = []

    def which(cmd):
        called.append(cmd)
        return "/usr/bin/cua-driver"

    got = ensure_cua_driver_env(env=env, platform="linux", which=which, log=None)
    assert got == "D:/custom/cua-driver.exe"
    assert env[CUA_DRIVER_ENV] == "D:/custom/cua-driver.exe"
    assert called == []          # 显式配置时连 which 都不该调用


def test_path_hit_is_promoted_to_env():
    env = {}
    got = ensure_cua_driver_env(env=env, platform="linux",
                                which=lambda cmd: "/usr/bin/cua-driver", log=None)
    assert got == os.path.normpath("/usr/bin/cua-driver")
    assert env[CUA_DRIVER_ENV] == os.path.normpath("/usr/bin/cua-driver")


def test_windows_well_known_location(tmp_path):
    local = tmp_path / "AppData" / "Local"
    exe = _fake_exe(local / "Programs" / "Cua" / "cua-driver" / "bin" / "cua-driver.exe")
    env = {"LOCALAPPDATA": str(local), "USERPROFILE": str(tmp_path)}
    got = ensure_cua_driver_env(env=env, platform="win32", which=lambda cmd: None, log=None)
    assert got == os.path.normpath(exe)
    assert env[CUA_DRIVER_ENV] == os.path.normpath(exe)


def test_windows_packages_current_junction_layout(tmp_path):
    exe = _fake_exe(tmp_path / ".cua-driver" / "packages" / "current" / "cua-driver.exe")
    env = {"USERPROFILE": str(tmp_path)}          # 没有 LOCALAPPDATA
    got = ensure_cua_driver_env(env=env, platform="win32", which=lambda cmd: None, log=None)
    assert got == os.path.normpath(exe)


def test_posix_home_local_bin(tmp_path):
    exe = _fake_exe(tmp_path / ".local" / "bin" / "cua-driver")
    env = {"HOME": str(tmp_path)}
    got = ensure_cua_driver_env(env=env, platform="darwin", which=lambda cmd: None, log=None)
    assert got == os.path.normpath(exe)


def test_missing_driver_is_graceful_and_hints_install(tmp_path):
    lines = []
    env = {"HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    got = ensure_cua_driver_env(env=env, platform="linux", which=lambda cmd: None,
                                log=lines.append)
    assert got == ""
    assert CUA_DRIVER_ENV not in env          # 不写垃圾值，工具优雅缺席
    assert len(lines) == 1 and "computer-use install" in lines[0]


def test_candidates_are_platform_specific(tmp_path):
    win = candidate_paths(env={"LOCALAPPDATA": str(tmp_path), "USERPROFILE": str(tmp_path)},
                          platform="win32")
    nix = candidate_paths(env={"HOME": str(tmp_path)}, platform="linux")
    assert win and all(p.endswith("cua-driver.exe") for p in win)
    assert nix and all(not p.endswith(".exe") for p in nix)
    assert not set(win) & set(nix)


def test_locate_prefers_path_over_well_known(tmp_path):
    _fake_exe(tmp_path / ".local" / "bin" / "cua-driver")
    env = {"HOME": str(tmp_path)}
    assert locate(env=env, platform="linux", which=lambda cmd: "/opt/x/cua-driver") == \
        os.path.normpath("/opt/x/cua-driver")
