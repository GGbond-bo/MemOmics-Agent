#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""verify_figure_no_clip.py — 出图后一次性验收探针（零裁切 + 非空白 + 尺寸）

用法:
    python verify_figure_no_clip.py <figure.png> [more.png ...]

判据（三项全过 => OK；任何一项 FAIL 就重跑，不要靠肉眼/反复 vision）:
    1. 非空白 : 非背景像素占比 > 30%      —— 全白图 extrema=(255,255) 直接判死
    2. 零裁切 : 内容 bbox 四边留白均 > 0 px —— 任一边贴边 = 内容被裁
    3. 尺寸   : 打印画布英寸尺寸，便于与期望值（如 11.92 x 8.33 in）对照

要点:
    * PNG 常为 mode P（调色板），必须 .convert("RGB") 后再阈值化，否则检测全错 /
      抛 "zero-size array to reduction operation minimum"。
    * 右下角自绘 legend 会伸到内容 bbox 的右下端，故"右侧留白"可能小于设定 padding，
      这是正常的；判据只看"是否贴边"（> 0 px）。
"""
import sys
import numpy as np
from PIL import Image

THRESH = 248          # < 248 视为非白（内容）
MIN_CONTENT_RATIO = 0.30
DPI = 300


def check(path):
    im = Image.open(path)
    gray_extrema = im.convert("L").getextrema()          # (255,255) => 全白坏图
    rgb = im.convert("RGB")                              # 必须 convert，PNG 常为 mode P
    a = np.array(rgb)
    h, w, _ = a.shape
    r, g, b = a[:, :, 0].astype(int), a[:, :, 1].astype(int), a[:, :, 2].astype(int)

    nw = (r < THRESH) | (g < THRESH) | (b < THRESH)
    ratio = nw.mean()

    if nw.sum() == 0:
        print(f"[FAIL] {path}: 全白/无内容 (extrema={gray_extrema}, size={im.size}, mode={im.mode})")
        return False

    cols = np.where(nw.sum(axis=0) > 0)[0]
    rows = np.where(nw.sum(axis=1) > 0)[0]
    left, right = int(cols.min()), int(w - 1 - cols.max())
    top, bottom = int(rows.min()), int(h - 1 - rows.max())
    zero_clip = left > 0 and right > 0 and top > 0 and bottom > 0

    ok_blank = ratio > MIN_CONTENT_RATIO
    print(f"file        : {path}")
    print(f"canvas      : {w} x {h} px  ({w/DPI:.2f} x {h/DPI:.2f} in @ {DPI}dpi)  mode={im.mode}")
    print(f"content bbox: x {cols.min()}-{cols.max()}  y {rows.min()}-{rows.max()}")
    print(f"margins px  : left {left} | right {right} | top {top} | bottom {bottom}")
    print(f"[{'OK  ' if ok_blank else 'FAIL'}] non-blank  : content ratio {ratio*100:.1f}%  (need > {MIN_CONTENT_RATIO*100:.0f}%)")
    print(f"[{'OK  ' if zero_clip else 'FAIL'}] zero-clip  : {'no content touches the edge' if zero_clip else 'CONTENT TOUCHES EDGE -> enlarge canvas / re-derive from gtable'}")
    print(f"=> {'PASS' if (ok_blank and zero_clip) else 'FAIL'}\n")
    return ok_blank and zero_clip


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    results = [check(p) for p in argv[1:]]
    print("ALL PASS" if all(results) else "SOME FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
