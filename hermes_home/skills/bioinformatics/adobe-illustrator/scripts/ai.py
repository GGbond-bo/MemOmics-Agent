#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ai.py — adobe-illustrator 技能统一入口：转发到 cli-anything-illustrator harness。

解析顺序（可用 --which 查看实际选用）：
  1) 环境变量 CLI_ANYTHING_ILLUSTRATOR（显式指定 exe / 脚本）
  2) 本仓库 .venv 的 cli-anything-illustrator(.exe)（相对本文件定位仓库根）
  3) PATH 上的 cli-anything-illustrator
  4) 自带快照 scripts/harness_bundle（python -m cli_anything.illustrator，零安装回退）

用法：
  python ai.py --which
  python ai.py --json doctor
  python ai.py --json rect --x 10 --y 20 --w 100 --h 50 --color "#e04040"
注意：--json 是 harness 的 group 级选项，必须写在子命令之前。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.join(HERE, "harness_bundle")


def _repo_root() -> str:
    # scripts -> adobe-illustrator -> bioinformatics -> skills -> hermes_home -> 仓库根
    return os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))


def _candidates():
    env = os.environ.get("CLI_ANYTHING_ILLUSTRATOR")
    if env:
        yield ("env", env)
    root = _repo_root()
    for rel in ((".venv", "Scripts", "cli-anything-illustrator.exe"),
                (".venv", "Scripts", "cli-anything-illustrator"),
                (".venv", "bin", "cli-anything-illustrator")):
        p = os.path.join(root, *rel)
        if os.path.isfile(p):
            yield ("venv", p)
    found = shutil.which("cli-anything-illustrator")
    if found:
        yield ("path", found)


def pick(force_bundled: bool = False):
    """返回 (kind, target)：kind ∈ {env, venv, path, bundle}。"""
    if not force_bundled:
        for kind, target in _candidates():
            return kind, target
    return "bundle", BUNDLE


def build_cmd(args, force_bundled: bool = False):
    kind, target = pick(force_bundled)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if kind == "bundle":
        if not os.path.isdir(os.path.join(BUNDLE, "cli_anything")):
            raise SystemExit("找不到已装 harness，且自带快照缺失：%s" % BUNDLE)
        env["PYTHONPATH"] = BUNDLE + os.pathsep + env.get("PYTHONPATH", "")
        return [sys.executable, "-m", "cli_anything.illustrator"] + args, env, kind
    return [target] + args, env, kind


def run(args, force_bundled: bool = False):
    """执行并透传输出；返回退出码。"""
    cmd, env, _kind = build_cmd(args, force_bundled)
    return subprocess.run(cmd, env=env).returncode


def run_capture(args, force_bundled: bool = False):
    """执行并捕获输出；返回 (rc, stdout_text, stderr_text)。"""
    cmd, env, _kind = build_cmd(args, force_bundled)
    proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout, proc.stderr


def main(argv):
    args = list(argv)
    force_bundled = "--bundled" in args
    which_only = "--which" in args
    args = [a for a in args if a not in ("--bundled", "--which")]
    if which_only:
        kind, target = pick(force_bundled)
        print("%s: %s" % (kind, target))
        return 0
    return run(args, force_bundled)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))