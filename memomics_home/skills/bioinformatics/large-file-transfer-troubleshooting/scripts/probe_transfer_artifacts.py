#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""传输失败一键探测：目标端残件 + 剩余空间 + 体积比对。

用途
    大文件上传/下载失败（提交即失败 / 0 B / 卡在 0%）时，一条命令拿到全部判据：
      - 目标文件是否为 0 字节空壳（平台预校验会因此判 failed item）
      - 同目录有无 <名>.crswap 残件（Chromium File System Access API 未收尾的物证）及体积
      - 目标盘剩余空间是否够（阈值 = 期望大小 ×1.2）
      - 同名 .part / .tmp / .download / ~$ 等常见残件
      - 已传/期望 比值，判断"是否真的传过"

用法
    python probe_transfer_artifacts.py <目标文件路径> [--expect-bytes N] [--expect-pretty 9.4GB]

例
    python probe_transfer_artifacts.py "E:/zhangxiao/20261008_PFC_substates_mapped.rds" --expect-pretty 9.4GB

退出码
    0 = 未发现残留、空间充足（可以直接重投）
    1 = 发现残留（需先清理）
    2 = 空间不足
    3 = 参数/路径错误
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

# 常见残件后缀（.crswap 必须单独列出：它是浏览器写入的交换文件，不是目标文件的别名）
RESIDUE_SUFFIXES = [".crswap", ".part", ".partial", ".tmp", ".temp",
                    ".download", ".crdownload", ".filepart", ".aria2"]

_SAFETY = 1.2  # 剩余空间安全系数


def parse_pretty(s: str) -> int:
    """'9.4GB' / '200 MB' / '1073741824' -> bytes"""
    s = s.strip().upper().replace(" ", "")
    m = re.fullmatch(r"([0-9.]+)\s*(B|KB|MB|GB|TB)?", s)
    if not m:
        raise ValueError(f"无法解析体积：{s!r}")
    val = float(m.group(1))
    unit = m.group(2) or "B"
    mult = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}[unit]
    return int(val * mult)


def human(n: int) -> str:
    f = float(n)
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if abs(f) < 1024 or u == "TB":
            return f"{f:.2f} {u}" if u != "B" else f"{int(f)} B"
        f /= 1024
    return f"{f:.2f} TB"


def main() -> int:
    ap = argparse.ArgumentParser(description="传输失败目标端探测")
    ap.add_argument("target", help="目标文件或目标目录路径")
    ap.add_argument("--expect-bytes", type=int, default=0, help="期望的文件总字节数")
    ap.add_argument("--expect-pretty", default="", help="期望体积，如 9.4GB（与 --expect-bytes 二选一）")
    args = ap.parse_args()

    try:
        expect = args.expect_bytes or (parse_pretty(args.expect_pretty) if args.expect_pretty else 0)
    except ValueError as e:
        print(f"[ERR] {e}")
        return 3

    target = Path(args.target)
    if not target.is_absolute():
        target = Path.cwd() / target
    if not target.parent.exists():
        print(f"[ERR] 父目录不存在：{target.parent}")
        return 3

    problems: list[str] = []
    notes: list[str] = []

    print("=" * 66)
    print(f"目标：{target}")
    print("=" * 66)

    # --- 1. 目标文件本体 ---
    if target.exists():
        size = target.stat().st_size
        print(f"[目标文件] 存在 · {human(size)} ({size} B)")
        if size == 0:
            problems.append("目标文件是 0 字节空壳 —— 平台预校验会判 failed item，必须先删除")
        elif expect and size < expect:
            pct = 100.0 * size / expect
            notes.append(f"目标文件小于期望（已传 {pct:.1f}%）—— 前次传输中途中断")
        else:
            print("          体积正常，可能已完整")
    else:
        print("[目标文件] 不存在（正常；若前次失败一般会留下残件）")

    # --- 2. 同名残件扫描 ---
    print("\n[残件扫描] 同目录同名/近名残件：")
    found_residue = []
    stem_names = {target.name, target.stem}
    try:
        entries = list(target.parent.iterdir())
    except OSError as e:
        print(f"  ! 无法列出目录：{e}")
        entries = []

    for p in entries:
        if not p.is_file():
            continue
        hit = None
        if p.name.endswith(".crswap"):
            hit = "Chromium File System Access API 交换文件（浏览器端流式写入未收尾）"
        else:
            for suf in RESIDUE_SUFFIXES:
                if p.name.endswith(suf):
                    hit = f"残件后缀 {suf}"
                    break
        if hit and (p.name.startswith(target.name) or p.stem.startswith(target.stem)
                    or p.name.startswith(f".{target.name}")):
            sz = p.stat().st_size
            found_residue.append(p)
            print(f"  ✗ {p.name}  {human(sz)} ({sz} B)")
            print(f"      └ {hit}")

    if found_residue:
        problems.append(f"发现 {len(found_residue)} 个残件 —— 重投前必须清理（平台会预校验目标条目）")
        total_res = sum(p.stat().st_size for p in found_residue)
        if expect:
            print(f"  合计残件体积 {human(total_res)}，占期望 {100.0*total_res/expect:.1f}%"
                  "  → 说明写入确实发生过，但未收尾")
    else:
        print("  ✓ 未发现残件")

    # --- 3. 目标盘剩余空间 ---
    print("\n[空间核查] 目标盘：")
    try:
        usage = shutil.disk_usage(str(target.parent))
        print(f"  总 {human(usage.total)} / 已用 {human(usage.used)} / 剩余 {human(usage.free)}")
        if expect:
            need = int(expect * _SAFETY)
            print(f"  期望文件 {human(expect)}，建议预留 {human(need)}（×{_SAFETY}）")
            if usage.free < need:
                problems.append(f"剩余空间不足：{human(usage.free)} < 建议 {human(need)}")
            else:
                print("  ✓ 空间充足")
    except OSError as e:
        print(f"  ! 无法读取磁盘用量：{e}")

    # --- 4. 结论 ---
    print("\n" + "=" * 66)
    if problems:
        print("结论：需要处理")
        for i, p in enumerate(problems, 1):
            print(f"  {i}. {p}")
        if any("空间不足" in p for p in problems):
            print("\n→ 修复顺序：清残件 → 腾空间 → 换 oss/raysync 通道 → 重投（后台）")
            return 2
        print("\n→ 修复顺序：清残件 → 核空间 → 换 oss/raysync 通道重投（>200MB 单文件不要用 web）")
        return 1
    print("结论：未发现目标端残留，空间充足")
    for n in notes:
        print(f"  注意：{n}")
    print("→ 若仍提交失败，问题在通道/体积侧（>200MB 单文件必须走 oss/raysync）")
    return 0


if __name__ == "__main__":
    sys.exit(main())