#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pixel_diff_verify.py —— 证明「只改了指定区域，其余一个像素没动」

用途
    用户说「不需要 a,b 这些符号，其他的不变」「只把标题去掉」之后，
    不要用 OCR 去验（OCR 验不了孤立小字母 / 旋转文字），用两版 PNG 像素差分：
    这是确定性证据，能把「我没动柱子」从口头承诺变成实测数字。

用法
    python pixel_diff_verify.py A.png B.png
    python pixel_diff_verify.py v3.png v4.png --data-zone 0.25,0.80 --tol 8
    python pixel_diff_verify.py a.png b.png --expect-clusters 5

输出（四项，缺一不可）
    1) diff 像素数 + 占画布比例
    2) diff bbox（y-frac / x-frac）—— 应对上被删元素所在的纵向带
    3) x 方向簇数 + 每簇位置/宽度 —— 5 簇各 ~23px = 5 个孤字母
    4) 数据区 diff 是否为 0 —— 最重要的一行：数据面没被碰

退出码
    0 = 通过（数据区 0 差异，且簇数符合预期）
    1 = 存在额外改动（数据区有差异，或簇数不符）
    2 = 用法/格式错误（尺寸不一致、文件读不到）
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image


def load(path):
    if not os.path.exists(path):
        print(f"[ERR] 文件不存在: {path}")
        sys.exit(2)
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)


def cluster_1d(idx, gap=30):
    """把一维非零索引按间隔切簇（默认 >30px 视为新簇）。"""
    if len(idx) == 0:
        return []
    gaps = np.where(np.diff(idx) > gap)[0]
    return np.split(idx, gaps + 1)


def main():
    ap = argparse.ArgumentParser(description="两版同尺寸 PNG 的像素差分验证")
    ap.add_argument("prev", help="上一版 PNG（改动前）")
    ap.add_argument("new", help="这一版 PNG（改动后）")
    ap.add_argument("--tol", type=int, default=8,
                    help="单通道差值容忍阈值，默认 8（抗 PNG 压缩噪声）")
    ap.add_argument("--data-zone", default="0.25,0.80",
                    help="数据区（柱/点/热图）的 y-frac 上下界，默认 0.25,0.80")
    ap.add_argument("--expect-clusters", type=int, default=None,
                    help="预期 x 方向差异簇数（如删除 5 个面板字母 → 5）")
    ap.add_argument("--fmt", default="{:.1f}", help="尺寸换算格式（默认按 @400dpi 报 mm）")
    args = ap.parse_args()

    A, B = load(args.prev), load(args.new)
    print(f"prev: {os.path.basename(args.prev)}  {A.shape}")
    print(f"new : {os.path.basename(args.new)}  {B.shape}")
    if A.shape != B.shape:
        print("[ERR] 两版尺寸不一致 —— 无法逐像素比对。"
              "同 figsize + 同 dpi 才会同 px；画布被改过请先对齐。")
        sys.exit(2)

    d = (np.abs(A - B).max(axis=2) > args.tol)
    H, W = d.shape

    print(f"\n[1] diff pixels = {d.sum():,}  ({d.mean() * 100:.4f}% of canvas)")
    if d.sum() == 0:
        print("    → 两版完全相同（若预期有改动，说明新图没写出去/跑的是旧脚本）")

    rows = np.where(d.any(axis=1))[0]
    cols = np.where(d.any(axis=0))[0]
    if len(rows):
        print(f"[2] diff bbox   = rows {rows.min()}–{rows.max()} "
              f"(y-frac {rows.min()/H:.3f}–{rows.max()/H:.3f}) | "
              f"cols {cols.min()}–{cols.max()} (x-frac {cols.min()/W:.3f}–{cols.max()/W:.3f})")

    clusters = cluster_1d(cols)
    print(f"[3] x-clusters  = {len(clusters)}  positions/widths: "
          f"{[[int(c[0]), int(c[-1])] for c in clusters]}")

    y0, y1 = (float(v) for v in args.data_zone.split(","))
    data_zone = d[int(H * y0):int(H * y1), :]
    print(f"[4] DATA-ZONE diff (y-frac {y0}–{y1}) = {data_zone.sum():,} px "
          f"→ {'数据面未被触碰 ✓' if data_zone.sum() == 0 else '数据面被改动了 ✗'}")

    print(f"\nsize: {W}x{H}px"
          + ("" if args.fmt is None else f"  ({W/400*25.4:.1f} x {H/400*25.4:.1f} mm @400dpi)"))

    ok = data_zone.sum() == 0
    if args.expect_clusters is not None and len(clusters) != args.expect_clusters:
        print(f"[WARN] 簇数 {len(clusters)} != 预期 {args.expect_clusters}")
        ok = False
    print("VERDICT:", "只有目标区域发生变化 ✓" if ok else "存在额外改动 ✗")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()