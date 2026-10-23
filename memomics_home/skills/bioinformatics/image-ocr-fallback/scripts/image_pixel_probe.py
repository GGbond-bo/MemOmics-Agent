# -*- coding: utf-8 -*-
"""L1 · 本地像素探针（PIL/numpy，零联网、零外部模型）。

vision_describe 的等价手写版，用于：
  - vision_describe 不可用 / 需要更细的事实（3x3 分区主色、纹理梯度、色相分布）时；
  - 与 L3 的语义描述**互相印证**（铁律 -2 多源验证）。

用法：python image_pixel_probe.py <图片绝对路径>
读法：
  - OCR 文本为空 + 唯一色数万级 + 梯度 2~8  → 纯图形/插画类图（不是文档截图）
  - 主色全落在同一色相带（如 27~33°）        → 近单色调（棕褐/米色）渲染图
  - 强饱和像素占比低（<15%）                 → 低饱和、写实风格，而非扁平插画
"""
import sys

import numpy as np
from PIL import Image

RAMP = " .:-=+*#%@"          # 亮度 → 字符密度（空格最暗，@ 最亮）


def ascii_map(im, gw=100, gh=46):
    small = im.resize((gw, gh), Image.LANCZOS).convert("L")
    lum = np.asarray(small).astype(float)
    idx = (lum / 255 * (len(RAMP) - 1)).round().astype(int)
    return "\n".join("".join(RAMP[i] for i in row) for row in idx)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    im = Image.open(path)
    print(f"=== 文件 ===\n  {path}\n  {im.format} {im.size} {im.mode} "
          f"{__import__('os').path.getsize(path)} B")

    im = im.convert("RGB")
    W, H = im.size
    a = np.asarray(im).astype(float)

    # 1) 调色板（量化到 12 色）+ 色相
    q = np.asarray(im.convert("P", palette=Image.ADAPTIVE, colors=12).convert("RGB")).reshape(-1, 3)
    cols, cnt = np.unique(q, axis=0, return_counts=True)
    print("\n=== 主色板 (Top12) ===")
    for i in np.argsort(-cnt):
        c = cols[i]
        hue = Image.new("RGB", (1, 1), tuple(int(v) for v in c)).convert("HSV")
        h, s, v = np.asarray(hue)[0]
        print(f"  #{c[0]:02X}{c[1]:02X}{c[2]:02X}  {cnt[i]/len(q)*100:5.2f}%  HSV=({h*360/255:5.1f}°,{s/255:.2f},{v/255:.2f})")

    # 2) 饱和度/明度/纹理
    hsv = np.asarray(im.convert("HSV")).astype(float)
    sat, val = hsv[:, :, 1] / 255, hsv[:, :, 2] / 255
    g = np.asarray(im.convert("L")).astype(float)
    print("\n=== 统计 ===")
    print(f"  平均亮度 {val.mean():.3f}  平均饱和度 {sat.mean():.3f}")
    print(f"  高饱和(sat>0.5) {(sat>0.5).mean()*100:.1f}%  暗(val<0.15) {(val<0.15).mean()*100:.1f}%"
          f"  亮(val>0.85) {(val>0.85).mean()*100:.1f}%")
    print(f"  纹理 水平梯度 {np.abs(np.diff(g,axis=1)).mean():.2f} / 垂直梯度 "
          f"{np.abs(np.diff(g,axis=0)).mean():.2f}  (>8 照片, 2-8 插画, <2 色块)")
    print(f"  唯一颜色数 {len(np.unique(np.asarray(im).reshape(-1,3), axis=0))}")

    # 3) 3x3 分区（看主体构图在哪一块）
    print("\n=== 3x3 分区 平均色(平均饱和度) ===")
    for i in range(3):
        row = []
        for j in range(3):
            blk = a[H*i//3:H*(i+1)//3, W*j//3:W*(j+1)//3].reshape(-1, 3).mean(0).astype(int)
            sb = sat[H*i//3:H*(i+1)//3, W*j//3:W*(j+1)//3].mean()
            row.append(f"#{blk[0]:02X}{blk[1]:02X}{blk[2]:02X}(s{sb:.2f})")
        print("  " + "  ".join(row))

    # 4) ASCII 亮度图（形状/构图）
    print("\n=== ASCII %dx%d (空格最暗 @ 最亮) ===" % (100, 46))
    print(ascii_map(im))
    print("\n[提示] 图像本身无文字时 OCR 为空属正常，不等于图有问题；"
          "语义需 L3（scripts/read_image_via_qwen_vl.py）并与之互证。")


if __name__ == "__main__":
    main()