#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""render_pixel_audit.py — 从交付的 PNG 里量「节点条 ↔ 标签」几何对齐（不看绘图脚本任何变量）。

为什么必须用这个：脚本自检常是恒等式（标签就是用同一个 (y0+y1)/2 画的 → 偏差恒 0），
或只验中心不验高度（9 px 节点 vs 38 px 标签，中心对齐但视觉"挂着"）。
本脚本只认像素。

用法
----
  python render_pixel_audit.py FIG.png \
      --bars "#7A7A7A,#B08A5A,#5A8AA5" \      # 左列节点条颜色（可多个）
      --bars2 "#A50026" \                      # 右列节点条颜色（可空）
      [--text "#222222"] [--label-pt 9.2] [--tol 12]

输出：每条带的 y 区间/像素高、每个标签的 ink band、中心偏差、高度比、重叠对数。
判据：|中心偏差| <= 3 px ；节点高 >= 1.5 x 标签 ink 高 ；相邻条带 0 重叠。
"""
import argparse
import sys

import numpy as np
from PIL import Image


def hex_rgb(hx):
    hx = hx.strip()
    if not hx.startswith("#"):
        hx = "#" + hx
    return np.array([int(hx[i:i + 2], 16) for i in (1, 3, 5)])


def segs(mask1d, minlen=5, bridge=3):
    """连续 True 段；bridge 用于桥接白色描边造成的小空隙。"""
    raw, s = [], None
    for i, v in enumerate(mask1d):
        if v and s is None:
            s = i
        elif not v and s is not None:
            raw.append([s, i - 1])
            s = None
    if s is not None:
        raw.append([s, len(mask1d) - 1])
    out = []
    for a, b in raw:
        if out and a - out[-1][1] - 1 <= bridge:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(a, b) for a, b in out if b - a + 1 >= minlen]


def maxrun(mask1d):
    """单列最长连续 True 长度。"""
    best = cur = 0
    for v in mask1d:
        cur = cur + 1 if v else 0
        if cur > best:
            best = cur
    return best


def color_mask(im, hexes, tol):
    m = np.zeros(im.shape[:2], bool)
    for hx in hexes:
        c = hex_rgb(hx)
        m |= (np.abs(im - c).max(axis=2) <= tol)
    return m


def audit_column(im, mask, side, W, H):
    """找条带列（左/右半各取最长竖向连续），返回 [(y0,y1)]。"""
    rng = range(W // 2) if side == "L" else range(W // 2, W)
    runs = [(maxrun(mask[:, x]), x) for x in rng]
    if not runs:
        return None, []
    best, xcol = max(runs)
    if best < 5:
        return None, []
    return xcol, segs(mask[:, xcol])


def report(tag, segs_, labs, lab_px):
    print("-- %s --" % tag)
    if len(segs_) != len(labs):
        print("   !! 数量不等：条带 %d / 标签 %d —— 打印原始区间排查" % (len(segs_), len(labs)))
        for a, b in segs_:
            print("      node y[%4d,%4d] h%4d" % (a, b, b - a + 1))
        for a, b in labs:
            print("      label y[%4d,%4d] h%4d" % (a, b, b - a + 1))
        return
    dev_max, ratio_min, worst = 0.0, 9e9, ""
    for (c, d), (a, b) in zip(segs_, labs):
        nh, lh = d - c + 1, b - a + 1
        dev = (a + b) / 2 - (c + d) / 2
        ratio = nh / lh
        dev_max = max(dev_max, abs(dev))
        if ratio < ratio_min:
            ratio_min, worst = ratio, "y[%d,%d]" % (c, d)
        print("   node h=%4d | label h=%3d | 中心偏差 %+6.1f px | 高比 %.2f"
              % (nh, lh, dev, ratio))
    ov = sum(1 for i in range(1, len(segs_)) if segs_[i][0] < segs_[i - 1][1])
    print("   => 最差中心偏差 %.1f px | 最小高比 %.2f (%s) | 相邻重叠 %d 对 | 标签字高 %.0f px"
          % (dev_max, ratio_min, worst, ov, lab_px))
    ok = dev_max <= 3.0 and ratio_min >= 1.5 and ov == 0
    print("   => %s" % ("PASS" if ok else "REVIEW"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("png")
    ap.add_argument("--bars", default="#7A7A7A", help="左列节点条颜色，逗号分隔")
    ap.add_argument("--bars2", default="", help="右列节点条颜色，逗号分隔（可空）")
    ap.add_argument("--text", default="#222222", help="标签墨迹色")
    ap.add_argument("--label-pt", type=float, default=9.2, help="标签字号 pt")
    ap.add_argument("--tol", type=int, default=12, help="颜色容差")
    a = ap.parse_args()

    im = np.asarray(Image.open(a.png).convert("RGB")).astype(int)
    H, W, _ = im.shape
    print("%s  (%d x %d px)" % (a.png, W, H))

    dark = (np.abs(im - hex_rgb(a.text)).max(axis=2) <= 90)
    sides = [("L", [c for c in a.bars.split(",") if c.strip()])]
    if a.bars2.strip():
        sides.append(("R", [c for c in a.bars2.split(",") if c.strip()]))

    any_found = False
    for side, hexes in sides:
        mask = color_mask(im, hexes, a.tol)
        xcol, seg = audit_column(im, mask, side, W, H)
        if not seg:
            print("[%s] 未找到条带（检查 --bars/--bars2 颜色与 --tol）" % side)
            continue
        any_found = True
        print("[%s] 条带列 x=%d，检出 %d 条" % (side, xcol, len(seg)))
        m = dark.copy()
        if side == "L":
            m[:, xcol - 3:] = False          # 标签在条带左侧
        else:
            m[:, :xcol + 4] = False          # 标签在条带右侧
        m[:seg[0][0] - 28] = False           # 排除列标题
        m[seg[-1][1] + 28:] = False          # 排除图例/脚注
        labs = segs(m.any(axis=1), 4, 1)
        report("标签 band", seg, labs, a.lab_pt / 72 * 300)

    # 理论字高参考（ink 高通常略小于此值）
    print("\n参考：%g pt @300dpi = %.1f px（理论字高；PNG 量到的 ink 高会略小，比较时用同一张图的实测值）"
          % (a.label_pt, a.label_pt / 72 * 300))
    if not any_found:
        sys.exit(2)


if __name__ == "__main__":
    main()