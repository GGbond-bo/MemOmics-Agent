#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""check_canvas_margins.py — 画布越界 / 贴边检查（可重跑）

为什么需要它：matplotlib 对"元素/文字跑出画布"**不报任何错**，OCR 也读不出被裁或旋转的文字。
唯一可靠的判据是像素：非白像素的包围盒 = 内容边界。

用法：
    python check_canvas_margins.py figures/*.png
    python check_canvas_margins.py fig1.png --min-margin 20 --bands

判据：
    四边边距（顶/底/左/右，px）全部 ≥ --min-margin（默认 12）→ PASS，否则 FAIL 并指出是哪一边。
    --bands：打印底部 20% / 顶部 6% 区域的行级墨迹带（确认小字注释/脚注真的渲染了）。

实测（2026-10-23，三张 183 mm 宽图）：
    fig1 PASS（T13 B69 L53 R21） · fig2 修复前 bottom/right = 0 → 定位到 colorbar label 与
    轴外两行 caveat 溢出；fig3 修复前 right = 0 → 定位到 "2%" 标签写在 xlim 之外。
"""
import argparse
import numpy as np
from PIL import Image

NONWHITE_SUM = 720          # RGB 三通道和 < 720 视为墨迹（白底图）


def ink(rgb):
    return rgb.sum(axis=2) < NONWHITE_SUM


def bands(rowsum, thresh=3):
    """把逐行墨迹计数压成连续带 [(start, end), ...]"""
    out, start = [], None
    for i, v in enumerate(rowsum):
        if v > thresh and start is None:
            start = i
        elif v <= thresh and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(rowsum) - 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--min-margin", type=int, default=12)
    ap.add_argument("--bands", action="store_true")
    a = ap.parse_args()

    n_fail = 0
    for p in a.images:
        rgb = np.array(Image.open(p).convert("RGB"))
        H, W = rgb.shape[:2]
        m = ink(rgb)
        rs = np.where(m.any(axis=1))[0]
        cs = np.where(m.any(axis=0))[0]
        if len(rs) == 0:
            print(f"[FAIL] {p}  {W}x{H}  全白（疑似空白图）")
            n_fail += 1
            continue
        top, bot = int(rs.min()), int(H - 1 - rs.max())
        left, right = int(cs.min()), int(W - 1 - cs.max())
        bad = [name for name, v in zip("TBRL", [top, bot, right, left]) if v < a.min_margin]
        n_fail += bool(bad)
        line = f"[{'FAIL' if bad else 'PASS'}] {p}  {W}x{H}  margins T{top} B{bot} L{left} R{right}px"
        if bad:
            line += f"  ← 越界风险边: {''.join(bad)}（< {a.min_margin}px）"
        print(line)
        if a.bands:
            for name, sl in [("bottom", slice(int(H * 0.80), H)), ("top", slice(0, int(H * 0.06)))]:
                bl = bands(m[sl, :].sum(axis=1))
                off = int(H * 0.80) if name == "bottom" else 0
                print(f"      {name} ink bands (rows): "
                      + ", ".join(f"{s + off}-{e + off}" for s, e in bl[:12]))
    raise SystemExit(1 if n_fail else 0)


if __name__ == "__main__":
    main()