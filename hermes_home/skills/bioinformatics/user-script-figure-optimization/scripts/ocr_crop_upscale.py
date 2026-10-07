#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ocr_crop_upscale.py —— 把小字号文字裁出来放大，供 vision_describe 二次 OCR。

为什么需要它：整图 OCR 会**静默漏读**小字号（5–6 pt）长文本（实测：两行脚注只读到第 2 行），
看起来像"文字没渲染出来"。在断言"没画出来"之前，必须先裁切 + 放大复核。
（反向也成立：读到了 ≠ 一定渲染正确，但"读不到"绝不足以判定失败。）

用法
----
  # 底部 140 px 条带，放大 2 倍（最常用：脚注 / x 轴名）
  python ocr_crop_upscale.py figure.png --strip bottom --px 140 --scale 2

  # 顶部条带（主标题）+ 自定义输出路径
  python ocr_crop_upscale.py figure.png --strip top --px 120 --scale 2 --out /tmp/_chk_title.png

  # 任意矩形（x0 y0 x1 y1，像素；原点左上）
  python ocr_crop_upscale.py figure.png --box 0 700 1896 832 --scale 3

  # 左侧竖带（旋转的 y 轴名，配合 --rotate 90 转正）
  python ocr_crop_upscale.py figure.png --strip left --px 160 --rotate 90

输出：默认写 `<原图目录>/_chk_<原文件名>`，并打印尺寸与路径（直接拿去调 vision_describe）。
依赖：Pillow（PIL）。无需 matplotlib。
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    from PIL import Image
except ImportError:                                    # pragma: no cover
    sys.exit("需要 Pillow：pip install Pillow")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="裁区域 + 放大，供二次 OCR（vision_describe）")
    ap.add_argument("image", help="输入图片路径（png/jpg/tiff）")
    ap.add_argument("--strip", choices=["bottom", "top", "left", "right"],
                    help="按边条带裁切")
    ap.add_argument("--px", type=int, default=140,
                    help="条带厚度（像素，默认 140）")
    ap.add_argument("--frac", type=float, default=None,
                    help="条带厚度按图高/宽的比例给（如 0.18）。与 --px 同时给时以 --frac 为准")
    ap.add_argument("--box", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"),
                    help="任意矩形（像素，原点左上）。给了 --box 就忽略 --strip")
    ap.add_argument("--scale", type=float, default=2.0, help="放大倍数（默认 2）")
    ap.add_argument("--rotate", type=float, default=0.0,
                    help="旋转角度（顺时针，仅 --strip left/right 需要，常用 90）")
    ap.add_argument("--out", default=None, help="输出路径（默认 <原图目录>/_chk_<名>）")
    return ap.parse_args(argv)


def region_from_args(im, a):
    W, H = im.size
    if a.box:
        x0, y0, x1, y1 = a.box
    else:
        if not a.strip:
            sys.exit("必须给 --strip 或 --box 之一")
        px = int(round(a.frac * (H if a.strip in ("top", "bottom") else W))) if a.frac else a.px
        px = max(1, min(px, (H if a.strip in ("top", "bottom") else W)))
        x0, y0, x1, y1 = {
            "bottom": (0, H - px, W, H),
            "top":    (0, 0, W, px),
            "left":   (0, 0, px, H),
            "right":  (W - px, 0, W, H),
        }[a.strip]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 <= x0 or y1 <= y0:
        sys.exit(f"非法矩形：({x0},{y0},{x1},{y1})，图尺寸 {W}x{H}")
    return (x0, y0, x1, y1)


def main(argv=None):
    a = parse_args(argv)
    if not os.path.isfile(a.image):
        sys.exit(f"文件不存在：{a.image}")
    im = Image.open(a.image)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")

    box = region_from_args(im, a)
    crop = im.crop(box)

    if a.rotate:
        crop = crop.rotate(-a.rotate, expand=True)     # PIL rotate 逆时针 → 取负得到顺时针

    if a.scale and a.scale != 1:
        nw, nh = int(round(crop.width * a.scale)), int(round(crop.height * a.scale))
        crop = crop.resize((nw, nh), Image.LANCZOS)

    out = a.out or os.path.join(
        os.path.dirname(os.path.abspath(a.image)), "_chk_" + os.path.basename(a.image))
    crop.save(out)

    print(f"[原图] {a.image}  {im.size[0]}x{im.size[1]}")
    print(f"[裁切] box={box}  → {box[2]-box[0]}x{box[3]-box[1]} px")
    if a.rotate:
        print(f"[旋转] {a.rotate}°")
    if a.scale and a.scale != 1:
        print(f"[放大] {a.scale}x")
    print(f"[输出] {out}  {crop.width}x{crop.height}")
    print("→ 下一步：vision_describe(image_path=上面这个路径)")
    print("⚠️ 验收完记得删除该临时图，别留在 log/ 里当产物。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())