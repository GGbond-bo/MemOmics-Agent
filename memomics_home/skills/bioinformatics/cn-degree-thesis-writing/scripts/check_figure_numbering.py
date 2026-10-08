#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图件 ↔ 图号一致性探针（只诊断，不改稿）。

用法:
    python check_figure_numbering.py <论文目录>
    python check_figure_numbering.py <论文目录> --docx 论文.docx
    python check_figure_numbering.py <论文目录> --order part1_front.md,part2a_ch1.md,part2b_ch2.md

检查:
    1. 同一图件文件被 >=2 个图号引用（一图两号）        -> FAIL
    2. 图号不按正文出现顺序（图序倒置）                -> FAIL
    3. 同一章内图号不连续（删图后未重编）              -> WARN
    4. 图片 alt 未写成完整图题（不含「图 X.Y」）        -> WARN
    5. (可选, --docx) DOCX 内嵌图片数 vs 正文图号数     -> WARN

设计要点:
    * 只扫 part 文件（part*.md），**不扫合并稿** —— 否则同一张图会被统计两次。
      没有 part* 文件时才退回扫全部 *.md。
    * 文件名前缀即阅读顺序（part1 -> part4）；换成别的命名请用 --order 显式给定。
    * 图号只从**图片 alt 文本**里取 —— 这也是「alt 必须写完整图题」的原因之一。

退出码: 0 = 无 FAIL / 1 = 存在 FAIL
"""
from __future__ import print_function

import glob
import os
import re
import sys
import zipfile

FIG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
NUM_RE = re.compile(r"图\s*(\d+)\s*[.\-－]\s*(\d+)")


def out(msg=""):
    print(msg)


def pick_files(root, order_arg):
    if order_arg:
        names = [n.strip() for n in order_arg.split(",") if n.strip()]
        files = [os.path.join(root, n) for n in names]
    else:
        parts = sorted(glob.glob(os.path.join(root, "part*.md")))
        files = parts if parts else sorted(glob.glob(os.path.join(root, "*.md")))
    return [f for f in files
            if os.path.isfile(f) and not os.path.basename(f).startswith("_")]


def collect(files):
    recs = []
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                m = FIG_RE.search(line)
                if not m:
                    continue
                alt = m.group(1).strip()
                path = m.group(2).strip()
                n = NUM_RE.search(alt)
                recs.append({
                    "src": os.path.basename(f),
                    "line": i,
                    "alt": alt,
                    "file": os.path.basename(path) or path,
                    "num": (int(n.group(1)), int(n.group(2))) if n else None,
                })
    return recs


def check_duplicates(recs):
    by_file = {}
    for r in recs:
        by_file.setdefault(r["file"], []).append(r)
    fails = []
    for fname, rs in sorted(by_file.items()):
        nums = sorted({r["num"] for r in rs if r["num"]})
        if len(nums) >= 2:
            fails.append((fname, sorted(rs, key=lambda r: (r["src"], r["line"]))))
    return fails


def check_order(recs):
    seq = [(r["num"], r) for r in recs if r["num"]]
    bad = []
    for a, b in zip(seq, seq[1:]):
        if a[0] != b[0] and a[0] > b[0]:
            bad.append((a, b))
    return bad


def check_gaps(recs):
    chapters = {}
    for r in recs:
        if r["num"]:
            chapters.setdefault(r["num"][0], set()).add(r["num"][1])
    gaps = []
    for ch, minors in sorted(chapters.items()):
        lo, hi = min(minors), max(minors)
        missing = [m for m in range(lo, hi + 1) if m not in minors]
        if missing:
            gaps.append((ch, sorted(minors), missing))
    return gaps


def check_alt(recs):
    return [r for r in recs if not r["num"]]


def count_docx_media(docx_path):
    with zipfile.ZipFile(docx_path) as z:
        return [n for n in z.namelist()
                if n.startswith("word/media/") and not n.endswith("/")]


def main(argv):
    if len(argv) < 2:
        out(__doc__)
        return 2
    root = argv[1]
    order_arg = ""
    docx_path = ""
    if "--order" in argv:
        order_arg = argv[argv.index("--order") + 1]
    if "--docx" in argv:
        docx_path = argv[argv.index("--docx") + 1]

    files = pick_files(root, order_arg)
    if not files:
        out("[FAIL] 目录下找不到可分析的 Markdown 母本: %s" % root)
        return 1
    recs = collect(files)

    out("=" * 60)
    out("图件 ↔ 图号一致性探针")
    out("目录: %s" % root)
    out("母本: %s" % ", ".join(os.path.basename(f) for f in files))
    out("图片引用总数: %d" % len(recs))
    out("=" * 60)

    fails = 0

    dup = check_duplicates(recs)
    if dup:
        fails += 1
        out("")
        out("[FAIL] 同一图件被多个图号引用（一图两号）: %d 处" % len(dup))
        for fname, rs in dup:
            out("   图件: %s" % fname)
            for r in rs:
                num = "图 %d.%d" % r["num"] if r["num"] else "(无图号)"
                out("      - %-22s line %-5d %s | alt=%s"
                    % (r["src"], r["line"], num, r["alt"][:46]))
        out("   -> 修法只有两条: 删冗余图号(正文改引已有图号) 或 重绘独立图件;")
        out("      改图题/调位置/图注写「同图 X.Y」都不算修复 (见铁律 9)")
    else:
        out("")
        out("[PASS] 图件↔图号一一对应（无重复图件）")

    bad = check_order(recs)
    if bad:
        fails += 1
        out("")
        out("[FAIL] 图序倒置（图号与正文出现顺序不一致）: %d 处" % len(bad))
        for a, b in bad:
            ra, rb = a[1], b[1]
            out("   图 %d.%d (%s:%d) 出现在 图 %d.%d (%s:%d) 之前"
                % (a[0][0], a[0][1], ra["src"], ra["line"],
                   b[0][0], b[0][1], rb["src"], rb["line"]))
        out("   -> 重排图号后，插图清单/目录页码/正文引用/图注/alt 五处都要同步")
    else:
        out("")
        out("[PASS] 图号顺序与正文出现顺序一致")

    gaps = check_gaps(recs)
    if gaps:
        out("")
        out("[WARN] 同章内图号不连续（疑似删图未重编）: %d 章" % len(gaps))
        for ch, minors, missing in gaps:
            out("   第 %d 章: 现有小号 %s，缺 %s"
                % (ch, minors, ", ".join("图 %d.%d" % (ch, m) for m in missing)))
    else:
        out("")
        out("[PASS] 图号无空洞")

    noalt = check_alt(recs)
    if noalt:
        out("")
        out("[WARN] 图片 alt 未写成完整图题（不含「图 X.Y」）: %d 处" % len(noalt))
        for r in noalt[:20]:
            out("   - %s:%d  alt=%s" % (r["src"], r["line"], r["alt"][:46] or "(空)"))
        out("   -> alt 写完整图题，正文引用另用「如图 X.Y 所示」(见铁律 8)")

    if docx_path and os.path.isfile(docx_path):
        media = count_docx_media(docx_path)
        distinct_files = {r["file"] for r in recs}
        out("")
        out("[INFO] DOCX 内嵌图片: %d 个 | 母本引用去重后图件: %d 个 | 图号: %d 个"
            % (len(media), len(distinct_files), len({r["num"] for r in recs if r["num"]})))
        if len(distinct_files) < len({r["num"] for r in recs if r["num"]}):
            out("   -> 图件数 < 图号数，必然存在复用（一图两号）")

    out("")
    out("=" * 60)
    out("结论: %s" % ("存在 FAIL，需修复后再出稿" if fails else "无 FAIL"))
    out("=" * 60)
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main(sys.argv))
