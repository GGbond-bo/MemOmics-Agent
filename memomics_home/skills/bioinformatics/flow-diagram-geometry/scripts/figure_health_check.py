#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
figure_health_check.py — 出图后一键体检（桑基/流向图及其他带大量标签的图）

用法:
  python figure_health_check.py figures/xx.png
  python figure_health_check.py figures/xx.png --x0 2680 --x1 3352        # 只看右轴标签列
  python figure_health_check.py figures/xx.png --x0 2680 --x1 3352 --min-gap 25

输出:
  1) 尺寸 / 文件大小 / PNG dpi(pHYs) / 非白像素占比(ink) / 唯一色数
  2) 指定 x 范围内的「文字行带」区间（暗像素行剖面切分）
  3) 相邻行带间距 < --min-gap 时报警 —— 两行文字挨得太近就是重叠信号

判读经验（300dpi）:
  ＊ 9pt 文字高约 38px、10.5pt 约 44px —— 一条 48px 的行带装不下两行文字，必然是叠了
  ＊ 桑基图节点多的一侧 ink ≈ 0.25–0.30 / uniq ≈ 6000+；节点少的一侧 ink ≈ 0.14 /
    uniq ≈ 900 属正常（留白多），不判空白
  ＊ 全图 OCR 漏掉某个标签 = 强信号，多半被邻近文字压住；本脚本用来佐证「装不下」

x 范围怎么选: 挑一段**只有文字没有链路**的条带（如右轴标签列、左轴标签列）。
先跑一次不带 --x0/--x1（全图），看行带分布，再收窄。
永远 exit 0（结论走 stdout，不要用退出码表达业务判断）。
"""
import argparse
import os
import struct
import sys

import numpy as np
from PIL import Image


def png_dpi(path):
    """从 PNG pHYs chunk 读 dpi；读不到返回 None。"""
    try:
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return None
            while True:
                hdr = f.read(8)
                if len(hdr) < 8:
                    return None
                ln, typ = struct.unpack(">I4s", hdr)
                if typ == b"pHYs":
                    x, y, unit = struct.unpack(">IIB", f.read(9))
                    if unit == 1:                      # 米 → 英寸
                        return round(x * 0.0254), round(y * 0.0254)
                    return None
                f.seek(ln + 4, 1)
    except Exception:
        return None


def bands(profile, thresh, min_gap):
    """暗像素行剖面 → 连续行带区间 + 相邻间距报警。"""
    out, s = [], None
    for i, v in enumerate(profile):
        if v > thresh and s is None:
            s = i
        elif v <= thresh and s is not None:
            out.append((s, i)); s = None
    if s is not None:
        out.append((s, len(profile)))
    warns = []
    for (_, e), (s2, _) in zip(out, out[1:]):
        if s2 - e < min_gap:
            warns.append((e, s2, s2 - e))
    return out, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--x0", type=int, default=None)
    ap.add_argument("--x1", type=int, default=None)
    ap.add_argument("--thresh", type=int, default=3,
                    help="一行里暗像素数超过它才算有内容（默认 3）")
    ap.add_argument("--min-gap", type=int, default=25,
                    help="相邻行带间距小于它就报警（默认 25px ≈ 9pt 文字高度下限）")
    args = ap.parse_args()

    rc = 0
    for p in args.images:
        if not os.path.exists(p):
            print("[MISS] %s 不存在" % p); rc = 1; continue
        im = Image.open(p).convert("RGB")
        w, h = im.size
        a = np.array(im)
        ink = (a < 245).any(axis=2).mean()
        uniq = len(np.unique(a.reshape(-1, 3), axis=0))
        dpi = png_dpi(p) if p.lower().endswith(".png") else None
        print("=" * 74)
        print("%s" % os.path.basename(p))
        print("  尺寸 %dx%d  %.0f KB  dpi=%s" % (w, h, os.path.getsize(p) / 1024, dpi))
        print("  ink(非白占比)=%.3f  唯一色=%d" % (ink, uniq))

        x0 = 0 if args.x0 is None else max(0, args.x0)
        x1 = w if args.x1 is None else min(w, args.x1)
        g = np.array(im.crop((x0, 0, x1, h)).convert("L"))
        prof = (g < 180).sum(axis=1)
        bs, warns = bands(prof, args.thresh, args.min_gap)
        print("  文字行带 x[%d,%d)  共 %d 段:" % (x0, x1, len(bs)))
        for s, e in bs:
            print("      y=%4d–%-4d  高 %3d px" % (s, e, e - s))
        if warns:
            rc = 1
            for e, s2, gp in warns:
                print("  [WARN] 行带间距仅 %d px (< %d) @y=%d–%d —— 疑两行文字重叠"
                      % (gp, args.min_gap, e, s2))
        else:
            print("  [OK] 无过近行带")
    return 0 if rc == 0 else 0        # 永远 exit 0，结论看 stdout


if __name__ == "__main__":
    sys.exit(main())