#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task_plan.md「注入区」卫生审计（read-side，零副作用）。

为什么需要它（2026-10-18 实测，见 SKILL §二 4-b-vii-b）
------------------------------------------------------
`task_plan.md` 的 **Goal / Current Phase / Phases 区**会被框架**每轮唤醒原样回灌**进 Agent 上下文。
实测逐词对照：Goal 里写着

    **Agent 侧待办 = 0**。…**唯一挂起（需用户决定，非 agent 可自动完成）**：① 是否扩卡 … ② 是否恢复 LoopX。

该轮回复随即写出

    **Agent 侧待办 = 0，只等你一句话：** 1. 扩卡 → 点篇名 … 2. 封版 … 3. LoopX → 维持 paused 或说「恢复」

—— 复述的**源头是注入文本**，不是记忆、也不是台账。
⇒ `scripts/replay_reply_lint.py` 管的是「**写**」（输出侧），本脚本管的是「**读进来的是什么**」（输入侧）。
两者是同一件事的两半：输入侧不清理，输出侧的门就得每轮硬扛。

判据（机械，零记忆量）
----------------------
注入区里出现**待决项词汇**或**序号计数**即违规 —— 因为它们会被回灌，进而复述进回复。
允许待在注入区的只有：交付物是什么、终态判据、该 Phase 的状态行（一行）。
待决项只写 `notes.md` 的 `[挂起]` 行；核销/唤醒记录只写独立的 `## 唤醒/核销台账` 小节。

用法
----
    python scripts/audit_taskplan_injection.py results/<sid>/task_plan.md
    python scripts/audit_taskplan_injection.py --text "$(cat task_plan.md)"   # 也可直接喂文本
    python scripts/audit_taskplan_injection.py < task_plan.md                 # 或 stdin

返回码
------
    0 = 注入区干净（可以放心让下一轮唤醒回灌）
    1 = 注入区含待决项 / 计数 ⇒ 按 Fix **就地清理那几行**，再跑一次
        ⛔ 不要顺手重写 Goal 的**主线目标句**（那是 SKILL §二 4-b-vii 主条明禁的）
"""
from __future__ import annotations

import argparse
import re
import sys

# ── 注入区的边界 ────────────────────────────────────────────────────────────────
# 起点：`# Task Plan: …` 或 `## Goal`；终点：第一个讲「唤醒 / 核销 / 维护 / 台账」的二级标题。
# 找不到起点 ⇒ 退回全文件扫描（宁可多报，不要漏报）。
_START = re.compile(r"^#{1,3}\s*(Task\s*Plan|Goal)\b", re.I)
_STOP = re.compile(r"^#{1,3}\s*(?!#)[^\n]*?(唤醒|核销|维护|台账|replay|回执)", re.I)

# ── 不该出现在注入区的两类内容 ─────────────────────────────────────────────────
CHECKS = [
    (
        "待决项进了注入区",
        re.compile(
            r"挂起|等用户|待用户|需用户|用户决定|用户定夺|用户拍板|"
            r"非\s*agent|非agent|唯一挂起|待决|待定|等你|等您|待你"
        ),
        "移到 notes.md 的 `[挂起] …（等用户，非阻塞）` 行，或独立的 `## 唤醒/核销台账` 小节。"
        "理由：该区每轮唤醒被原样回灌 ⇒ 下一轮回复会把这些项名逐词复述给用户"
        "（正撞 §二 4-b「正文不得出现待决项名字 / 邀约句」）。",
    ),
    (
        "序号计数进了注入区",
        re.compile(r"第\s*\d+\s*次|第\s*[一二三四五六七八九十]+\s*(批|次)|replay\s*#\s*\d+|(?<![\w])#\s*\d{1,3}(?![\d\w])"),
        "改成「维护轮台账见 notes.md」，⛔ 不要在注入区里写 `#N` / `第 N 次`。"
        "理由：Agent 会照抄注入区的写法 ⇒ 裸 `#<n>` 正是 replay_reply_lint 序号门要拦的形态。",
    ),
]


def injected_region(text: str) -> tuple[int, int, bool]:
    """返回 (起行, 止行, 是否命中起点)，行号 0-based、止行不含。"""
    lines = text.splitlines()
    start = 0
    found = False
    for i, ln in enumerate(lines):
        if _START.match(ln):
            start, found = i, True
            break
    if not found:
        return 0, len(lines), False          # 兜底：全文件
    for j in range(start + 1, len(lines)):
        if _STOP.match(lines[j]):
            return start, j, True
    return start, len(lines), True


def main() -> int:
    ap = argparse.ArgumentParser(description="task_plan.md 注入区卫生审计（见 SKILL §二 4-b-vii-b）")
    ap.add_argument("path", nargs="?", help="task_plan.md 路径；省略则读 --text 或 stdin")
    ap.add_argument("--text", help="直接给文本")
    args = ap.parse_args()

    if args.text is not None:
        text = args.text
    elif args.path:
        with open(args.path, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()

    lines = text.splitlines()
    lo, hi, found = injected_region(text)
    print("注入区 = 行 %d–%d（1-based，共 %d 行）%s"
          % (lo + 1, hi, hi - lo, "" if found else "  ⚠️ 未找到 `# Task Plan` / `## Goal` 起点 ⇒ 兜底扫全文件"))

    hits = []
    for i in range(lo, min(hi, len(lines))):
        ln = lines[i]
        for name, rx, fix in CHECKS:
            for m in rx.finditer(ln):
                hits.append((i + 1, name, m.group(0), ln.strip(), fix))

    if hits:
        print("\n❌ 注入区命中 %d 处 —— 清理后再让下一轮唤醒回灌\n" % len(hits))
        for line_no, name, lit, original, fix in hits:
            print("  L%-4d %s" % (line_no, name))
            print("        命中: %r" % lit)
            print("        原行: %s" % (original[:160] + ("…" if len(original) > 160 else "")))
            print("        修法: %s\n" % fix)
        print("提示：只清这几行 —— ⛔ 不要重写 Goal 的**主线目标句**（4-b-vii 主条明禁）。")
        print("     清理属「允许的 task_plan 写入」第四处（4-b-vii-b ③），不改变任何交付物。")
        return 1

    print("\n✅ 注入区干净：无待决项词汇、无序号计数。")
    print("   允许留在注入区的只有：交付物是什么 / 终态判据 / 该 Phase 的状态行（一行）。")
    print("   输出侧仍要跑：python scripts/replay_reply_lint.py --ledger results/<sid>/notes.md <草稿>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())