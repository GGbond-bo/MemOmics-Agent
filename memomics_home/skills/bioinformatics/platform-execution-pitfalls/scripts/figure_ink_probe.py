#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""figure_ink_probe.py — 面板图「墨迹级验收」探针（确定性，不用 OCR）

用途：改完一版图后，证明「元素真的画出来了 + 颜色没越界 + 箭头方向对」。
适用于任何按 fig 比例坐标布局、用颜色区分语义的 matplotlib 面板图。

用法（DEG 8 亚群柱图 Σ 计数行：蓝 Down 在左 / 红 Up 在右 / 箭头 ↓↑）：

    python figure_ink_probe.py fig_xxx.png \
        --centers 0.2068,0.3814,0.5560,0.7306,0.9052 \
        --band-y 0.789 --band-pad 34 \
        --left-color "#2166AC"  --left-dir  down \
        --right-color "#B2182B" --right-dir up \
        --min-run 28

判据（全部确定性）：
  1. 左色墨迹 x 极大值 < 面板中心；右色墨迹 x 极小值 > 面板中心（颜色不越界）
  2. 两色都有一列「竖向 run >= --min-run」→ 箭头确实渲染出来
     （矢量箭头 run≈33 px vs 同字号数字字高≈26 px @400dpi / 6.6pt）
  3. 该列落在中心线正确一侧
  4. 箭头朝向：逐行墨宽 profile 的最宽行（三角底边）在上半→up，下半→down

退出码：0 全通过 / 1 有面板未通过 / 2 参数或文件错误
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image


def color_mask(im, hexcol, tol):
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    R, G, B = (im[..., i].astype(int) for i in range(3))
    return (abs(R - r) < tol) & (abs(G - g) < tol) & (abs(B - b) < tol)


def probe_color(mask, band, lo, hi, c, min_run):
    """返回 (x0_off, x1_off, arrow_col_off, run, direction, span, has_arrow) 或 None"""
    m = mask[band, lo:hi]
    cols = np.where(m.any(axis=0))[0]
    if len(cols) == 0:
        return None
    runs = m.sum(axis=0)
    j = int(runs.argmax())
    run = int(runs[j])
    j0, j1 = max(j - 6, 0), min(j + 7, m.shape[1])
    prof = m[:, j0:j1].sum(axis=1)
    rr = np.where(prof > 0)[0]
    span = int(rr.max() - rr.min() + 1)
    widest = int(prof.argmax()) - int(rr.min())
    direction = "up" if widest < span / 2 else "down"
    return (int(cols.min()) + lo - c, int(cols.max()) + lo - c,
            j + lo - c, run, direction, span, run >= min_run)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("png")
    ap.add_argument("--centers", required=True,
                    help="面板中心 x（fig 比例，逗号分隔），如 0.2068,0.3814")
    ap.add_argument("--band-y", type=float, default=0.789,
                    help="目标行 y（fig 比例，从下往上）")
    ap.add_argument("--band-pad", type=int, default=34, help="行带上下各取多少 px")
    ap.add_argument("--window-l", type=int, default=150, help="中心线左侧搜索宽度 px")
    ap.add_argument("--window-r", type=int, default=280, help="中心线右侧搜索宽度 px")
    ap.add_argument("--left-color", default="#2166AC")
    ap.add_argument("--right-color", default="#B2182B")
    ap.add_argument("--left-dir", default="", choices=["", "up", "down"])
    ap.add_argument("--right-dir", default="", choices=["", "up", "down"])
    ap.add_argument("--min-run", type=int, default=28)
    ap.add_argument("--tol", type=int, default=55)
    a = ap.parse_args()

    if not os.path.exists(a.png):
        print("文件不存在:", a.png, file=sys.stderr)
        return 2
    im = np.asarray(Image.open(a.png).convert("RGB"))
    h, w = im.shape[:2]
    centers = [float(x) for x in a.centers.split(",") if x.strip()]
    yc = int(round((1.0 - a.band_y) * h))
    band = slice(max(yc - a.band_pad, 0), min(yc + a.band_pad + 1, h))

    ml = color_mask(im, a.left_color, a.tol)
    mr = color_mask(im, a.right_color, a.tol)
    print(f"# {os.path.basename(a.png)}  {w}x{h}  band rows {band.start}..{band.stop - 1}"
          f"  (y={a.band_y} -> py={yc})")

    ok_all = True
    for i, cf in enumerate(centers):
        c = int(round(cf * w))
        lo, hi = c - a.window_l, c + a.window_r
        parts, good = [], True
        for nm, m, side, wantdir in (("L", ml, "left", a.left_dir),
                                     ("R", mr, "right", a.right_dir)):
            r = probe_color(m, band, lo, hi, c, a.min_run)
            if r is None:
                parts.append(f"{nm}: EMPTY")
                good = False
                continue
            x0, x1, acol, run, d, span, has_arrow = r
            parts.append(f"{nm} x[{x0:+d},{x1:+d}] arr@{acol:+d} run={run} {d}")
            if side == "left" and not (x1 < 0):
                good = False
            if side == "right" and not (x0 > 0):
                good = False
            if not has_arrow:
                good = False
            if side == "left" and not (acol < 0):
                good = False
            if side == "right" and not (acol > 0):
                good = False
            if wantdir in ("up", "down") and d != wantdir:
                good = False
        print(f"  P{i + 1} cx={c:5d}  " + " | ".join(parts) + "   " + ("OK" if good else "FAIL"))
        ok_all &= good

    print("RESULT:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())