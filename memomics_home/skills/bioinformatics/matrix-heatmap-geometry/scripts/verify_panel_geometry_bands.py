#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""多面板图几何一致性核验 —— 量导出 PNG 底部的墨迹带（Pillow + numpy）。

为什么需要：同一脚本出的多面板图（面板行数不同），若注记/脚注用 transAxes / axes fraction
相对定位，偏移量会随**轴高**缩放 ⇒ 各面板的「旋转标签带 / 脚注带 / 两带间隙」互不相同
（典型症状：脚注带与标签带合并成一条，或脚注跑到轴名上方）。对象级自检会报假 PASS，
必须对**导出 PNG** 做像素测量（见 SKILL.md「核验三件套」的三层假 PASS）。

用法:
    python verify_panel_geometry_bands.py <figures_dir> [a.png b.png ...]
    # 不给文件名 → 目录下全部 .png（多面板的几张一起传才有跨面板比较）

输出每图的：末带高（脚注）/ 次末带高（旋转标签）/ 两带间隙 / 底边墨迹量
判据（脚本自动打印 PASS/FAIL）:
    1. 底边墨迹 == 0                          → 未被裁切
    2. 末带高跨面板相同 且 <= 60 px             → 脚注带一致（7.5 pt 一行 ≈ 31 px @300 dpi）
    3. 次末带高跨面板相同                       → 旋转标签带一致
    4. 两带间隙跨面板相同 且 >= 10 px            → 注记未压住标签（间隙 0 = 合并成一条 = FAIL）
"""
import os
import sys

import numpy as np
from PIL import Image

INK_LT = 240         # 灰度 < 此值视为墨迹（背景为白）
MIN_INK = 2          # 单行墨迹像素数下限，滤掉抗锯齿噪点
SEARCH_FROM = 0.5    # 只在画布下半部找带
GAP_TO_SPLIT = 3     # 连续空行 >= 此值才判定两条带断开
FOOTNOTE_MAX_H = 60  # 一"行"文字带的合理高度上限


def _bands(rows, height, from_frac=SEARCH_FROM):
    """把下半部连续有墨迹的行归成带，返回 [(y0, y1), ...] 自上而下。"""
    bands, cur, blank = [], None, 0
    for y in range(int(height * from_frac), height):
        if rows[y] > MIN_INK:
            cur = [y, y] if cur is None else [cur[0], y]
            blank = 0
        elif cur is not None:
            blank += 1
            if blank >= GAP_TO_SPLIT:
                bands.append((cur[0], cur[1]))
                cur, blank = None, 0
    if cur is not None:
        bands.append((cur[0], cur[1]))
    return bands


def measure(path):
    im = Image.open(path)
    gray = np.asarray(im.convert("L")).astype(np.int32)
    rows = (gray < INK_LT).sum(axis=1)
    bands = _bands(rows, gray.shape[0])
    heights = [b[1] - b[0] + 1 for b in bands]
    gap = (bands[-1][0] - bands[-2][1] - 1) if len(bands) >= 2 else None
    return {
        "file": os.path.basename(path),
        "size": "%dx%d" % im.size,
        "n_bands": len(bands),
        "footnote_h": heights[-1] if heights else None,
        "label_h": heights[-2] if len(heights) >= 2 else None,
        "gap": gap,
        "bottom_ink": int(rows[-1]),
        "bands": bands,
    }


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    root = argv[0]
    names = argv[1:] or sorted(f for f in os.listdir(root) if f.lower().endswith(".png"))
    if not names:
        print("没有找到 .png")
        return 2

    out = []
    for n in names:
        p = n if os.path.isabs(n) else os.path.join(root, n)
        try:
            out.append(measure(p))
        except Exception as exc:                      # 坏图/空图不该炸掉整批
            print("SKIP %s: %s" % (n, exc))

    print("%-40s %-12s %5s %11s %8s %6s %10s" %
          ("file", "size", "bands", "footnote_h", "label_h", "gap", "bottom_ink"))
    for r in out:
        print("%-40s %-12s %5d %11s %8s %6s %10d" %
              (r["file"], r["size"], r["n_bands"],
               r["footnote_h"], r["label_h"], r["gap"], r["bottom_ink"]))
    print()

    if len(out) < 2:
        print("只有 1 张图 —— 跨面板比较需要 >= 2 张（同一套多面板的 PNG 一起传）")
        return 0

    fails = []
    if any(r["bottom_ink"] > MIN_INK for r in out):
        fails.append("底边有墨迹 = 图被裁切")
    fh = {r["footnote_h"] for r in out}
    if len(fh) != 1:
        fails.append("脚注带高不一致: %s" % sorted(x for x in fh if x is not None))
    elif (out[0]["footnote_h"] or 0) > FOOTNOTE_MAX_H:
        fails.append("末带高 %s px > %d —— 脚注带很可能已与标签带合并成一条"
                     % (out[0]["footnote_h"], FOOTNOTE_MAX_H))
    lh = {r["label_h"] for r in out}
    if len(lh) != 1:
        fails.append("旋转标签带高不一致: %s" % sorted(x for x in lh if x is not None))
    gp = {r["gap"] for r in out}
    if None in gp or len(gp) != 1:
        fails.append("两带间隙不一致/缺失: %s"
                     % sorted(gp, key=lambda x: -1 if x is None else x))
    elif out[0]["gap"] < 10:
        fails.append("间隙 %s px 过小 —— 脚注压住标签" % out[0]["gap"])

    if fails:
        print("FAIL:")
        for f in fails:
            print("  - " + f)
        return 1

    r0 = out[0]
    print("PASS  底边无裁切 | 脚注带 %s px | 标签带 %s px | 间隙 %s px —— 跨 %d 张一致"
          % (r0["footnote_h"], r0["label_h"], r0["gap"], len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))