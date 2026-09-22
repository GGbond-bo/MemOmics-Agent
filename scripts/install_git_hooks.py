# -*- coding: utf-8 -*-
"""安装/卸载 git 钩子（P0-1 skill 门禁）。

用法：
  python scripts/install_git_hooks.py             # 安装（设置 core.hooksPath=.githooks）
  python scripts/install_git_hooks.py --status    # 查看当前状态
  python scripts/install_git_hooks.py --uninstall  # 卸载（恢复 git 默认钩子目录）

为什么用 core.hooksPath 而不是往 .git/hooks 里拷文件：钩子脚本进版本库（.githooks/），
任何人 clone 后一条命令就能启用，也不会被 git 自己清理；.git/hooks 是不进版本库的。
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = ".githooks"
HOOK_FILE = os.path.join(ROOT, HOOKS_DIR, "pre-commit")


def _git(*args):
    proc = subprocess.run(["git"] + list(args), cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout.decode("utf-8", "replace").strip()


def status():
    _, cur = _git("config", "--get", "core.hooksPath")
    exists = os.path.isfile(HOOK_FILE)
    print("core.hooksPath = %s" % (cur or "(未设置)"))
    print("%s 存在: %s" % (HOOK_FILE, "是" if exists else "否"))
    enabled = (cur or "").replace("\\\\", "/").strip("/") == HOOKS_DIR
    print("门禁状态: %s" % ("已启用" if (enabled and exists) else "未启用"))
    return 0 if (enabled and exists) else 1


def install():
    if not os.path.isfile(HOOK_FILE):
        print("[hooks] 缺少 %s" % HOOK_FILE)
        return 1
    code, out = _git("config", "core.hooksPath", HOOKS_DIR)
    if code != 0:
        print("[hooks] 设置 core.hooksPath 失败: %s" % out)
        return 1
    try:
        os.chmod(HOOK_FILE, 0o755)
    except OSError:
        pass
    print("[hooks] 已启用: core.hooksPath=%s" % HOOKS_DIR)
    print("[hooks] 提交涉及技能面文件时会自动跑 scripts/check_skills_gate.py")
    print("[hooks] 跳过一次: SKILLS_GATE=0 git commit ...  卸载: --uninstall")
    return 0


def uninstall():
    code, out = _git("config", "--unset", "core.hooksPath")
    if code != 0 and "not found" not in out.lower() and "没有" not in out:
        print("[hooks] 取消失败: %s" % out)
        return 1
    print("[hooks] 已卸载（core.hooksPath 恢复默认 .git/hooks）")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="安装/卸载 MemOmics git 钩子")
    ap.add_argument("--status", action="store_true", help="只看状态")
    ap.add_argument("--uninstall", action="store_true", help="卸载")
    args = ap.parse_args(argv)
    if args.status:
        return status()
    if args.uninstall:
        return uninstall()
    return install()


if __name__ == "__main__":
    sys.exit(main())
