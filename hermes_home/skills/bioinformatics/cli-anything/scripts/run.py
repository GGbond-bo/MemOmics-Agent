#!/usr/bin/env python
# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 此脚本由 MemOmics Agent 执行。原脚本永远不被修改。
#
# 执行前必须:
#   1. rail_review(action="pre")  — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs", skill_name="cli-anything")
#      → 查同类运行日志，有则参考已有命令与坑，无则按本脚本执行
#   3. debate_analysis(topic, context) — 自建 harness / 批量改写用户文件时
#
# 执行后必须:
#   1. rail_review(action="post") — 检查输出/质量/图表
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. 产物是否存在且 > 0 字节？格式头是否正确（SVG/PNG/PDF）？
#        b. 用户已打开的文档是否被改动？默认必须 NOT saved
#        c. --json 输出能否 json.loads？
#        d. harness 退出码是否为 0？
#   2. 通过 → skill_evolution(action="record_run", skill_name="cli-anything",
#      script_name="...", params_used="...", result_summary="...", quality_score=8)
#   3. 失败 → skill_evolution(action="record_error", ... root_cause / fix_applied)
#
# ★ 参数和结论辩论铁律:
#   - 批量改写用户文件 / 自建 harness 的参数选择 → 必须 debate_analysis
# ============================================================
"""CLI-Anything workflow driver (Hub path A).

用法:
    python run.py search <keyword>
    python run.py install <name>
    python run.py help <name>
    python run.py probe-json <name> <subcommand...>
    python run.py trigger-test <skill-name>

设计要点（2026-10-04 实测）:
  * --json 是 group 级选项，必须放在子命令之前
  * session 状态不跨进程：每条命令都要 --json + 必要的 --project
  * 一切以 <子命令> --help 的实际输出为准，禁止凭记忆编参数
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", r"E:/MemOmics-Agent/hermes_home"))
SOUL = HERMES_HOME / "SOUL.md"


def _hub() -> str:
    env = Path(sys.prefix) / ("Scripts/cli-hub.exe" if os.name == "nt" else "bin/cli-hub")
    if env.exists():
        return str(env)
    found = shutil.which("cli-hub")
    if not found:
        raise SystemExit("cli-hub 未安装: python -m pip install cli-anything-hub")
    return found


def _cli(name: str) -> str:
    exe = Path(sys.prefix) / f"Scripts/cli-anything-{name}.exe"
    if exe.exists():
        return str(exe)
    found = shutil.which(f"cli-anything-{name}")
    if not found:
        raise SystemExit(f"cli-anything-{name} 未安装: cli-hub install {name}")
    return found


def run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def cmd_search(kw: str) -> int:
    rc, out = run([_hub(), "search", kw])
    print(out)
    return rc


def cmd_install(name: str) -> int:
    rc, out = run([_hub(), "install", name], timeout=900)
    print(out)
    if rc:
        return rc
    rc2, out2 = run([_cli(name), "--help"])
    print("--- installed CLI help ---")
    print(out2)
    return rc2


def cmd_help(name: str) -> int:
    rc, out = run([_cli(name), "--help"])
    print(out)
    return rc


def cmd_probe_json(name: str, args: list[str]) -> int:
    """Run with --json placed BEFORE the subcommand (verified convention)."""
    cmd = [_cli(name), "--json"] + args
    print("$ " + " ".join(cmd))
    rc, out = run(cmd)
    print(out)
    # agent-native 底线：JSON 必须可解析
    try:
        json.loads(out.strip())
        print("[json] parse OK")
    except Exception as exc:  # noqa: BLE001
        print(f"[json] parse FAILED: {exc}")
        return 2 if rc == 0 else rc
    return rc


def cmd_trigger_test(skill: str) -> int:
    """Reproduce server._match_red_skill_triggers() semantics over SOUL.md."""
    row = re.compile(
        r'^\|\s*((?:"[^"]+"\s*/\s*)*"[^"]+")\s*\|\s*`skill_view\("([^"]+)"\)`\s*\|', re.M
    )
    rows = [
        (m.group(2), re.findall(r'"([^"]+)"', m.group(1)))
        for m in row.finditer(SOUL.read_text(encoding="utf-8", errors="replace"))
    ]
    target = [kws for name, kws in rows if name == skill]
    if not target:
        print(f"❌ {skill} 未注册到 SOUL.md")
        return 1
    kws = target[0]
    print(f"{skill}: {len(kws)} 个关键词")
    samples = [
        "帮我把Illustrator里所有文字统一字号",
        "用inkscape批量转矢量图",
        "给Blender做个CLI",
        "CLI-Anything是干什么的",
        "装一下cli-hub",
        "批量控制桌面软件导出svg",
        "给这个软件做个命令行",
    ]
    hit = sum(1 for s in samples if any(k in s for k in kws))
    for s in samples:
        print(f"  {'✅' if any(k in s for k in kws) else '❌'} {s}")
    print(f"命中 {hit}/{len(samples)}")
    return 0 if hit == len(samples) else 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    op = argv[1]
    if op == "search":
        return cmd_search(argv[2])
    if op == "install":
        return cmd_install(argv[2])
    if op == "help":
        return cmd_help(argv[2])
    if op == "probe-json":
        return cmd_probe_json(argv[2], argv[3:])
    if op == "trigger-test":
        return cmd_trigger_test(argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))