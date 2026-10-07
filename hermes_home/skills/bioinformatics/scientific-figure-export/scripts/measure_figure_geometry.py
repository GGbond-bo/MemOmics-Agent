#!/usr/bin/env python3
"""量已渲染图的几何与可读性 —— 面板纵横比 / 填充率 / 留白 / 配色灰度可分性.

为什么不用 gtable: ggplot 面板是 null 单位, 设备外 convertWidth 返回 0;
ggplot2 4.0.3 起 names(g$grobs) 为 NULL, 布局名是 panel-1-1 形式.
=> 几何量测的权威口径是渲染后的 PNG 像素.

用法
----
  # 面板几何 (默认 6 面板单排; 用 --panels / --spacing-px 校正边界)
  python measure_figure_geometry.py fig_preview.png --panels 6 --res 100

  # 非等分排布: 给出每块内容的 x 区间, 逗号分隔 (面板 + 图例混排时最准)
  python measure_figure_geometry.py fig.png --bounds 0,364,375,739,750,1114 --names Y_Pre,Y_Post,O_Pre

  # 配色灰度可分性
  python measure_figure_geometry.py --palette "NMJ=#D62728,zone1=#1F77B4,zone6=#E377C2"

判读
----
* 面板纵横比 (宽/高) 偏离 1.0 越多 => UMAP/t-SNE 拉伸越严重 (见 SKILL.md 几何自检 §1)
* 填充率 应随细胞数单调; 不同向 => 先查绘图层
* 上/下留白 > 0.8 in 且纵横比 << 1 => 画布高度过大, 收高度而不是砍点径
* 灰度相邻最小差 < 0.05 => 灰度打印下不可分
"""
from __future__ import annotations

import argparse
import sys

try:
    from PIL import Image
    import numpy as np
except ImportError:  # pragma: no cover
    sys.exit("需要 pillow + numpy:  pip install pillow numpy")

DARK_T = 0.3   # 面板内容判定: 行/列平均深度阈值 (0=白)
CONTENT_T = 10  # 填充率判定: 单像素深度阈值


def geometry(path: str, n_panels: int, res: float, bounds=None, names=None) -> None:
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(int)
    h, w, _ = a.shape
    dark = 255 - a.mean(axis=2)

    print(f"图像 {w}x{h} px @{res:g}dpi = {w/res:.2f} x {h/res:.2f} in")
    print(f"         ({w/res*25.4:.1f} x {h/res*25.4:.1f} mm)\n")

    nz = np.where(dark.mean(axis=1) > 0.5)[0]
    if len(nz):
        print(f"纵向内容占比 {(nz.max()-nz.min())/h*100:.0f}%  "
              f"(顶空 {nz.min()/res:.2f} in / 底空 {(h-nz.max())/res:.2f} in)")
    nzc = np.where(dark.mean(axis=0) > 0.5)[0]
    if len(nzc):
        print(f"横向内容占比 {(nzc.max()-nzc.min())/w*100:.0f}%\n")

    if bounds:
        pairs = [(int(bounds[i]), int(bounds[i + 1])) for i in range(0, len(bounds) - 1, 2)]
    else:
        step = w / n_panels
        pairs = [(int(i * step), int((i + 1) * step)) for i in range(n_panels)]

    print(f"{'panel':<10}{'内容 WxH (px)':>18}{'纵横比 W/H':>12}{'填充率':>10}{'高/宽':>9}{'留白(in)':>16}")
    ratios = []
    for i, (x0, x1) in enumerate(pairs):
        nm = (names[i] if names and i < len(names) else f"panel{i+1}")
        sub = dark[:, x0:x1]
        rows = np.where(sub.mean(axis=1) > DARK_T)[0]
        cols = np.where(sub.mean(axis=0) > DARK_T)[0]
        if len(rows) == 0:
            print(f"{nm:<10}{'— 空 —':>18}")
            continue
        cw, ch = cols.max() - cols.min(), rows.max() - rows.min()
        r = cw / ch if ch else float("nan")
        ratios.append(r)
        top_pad, bot_pad = rows.min() / res, (h - rows.max()) / res
        print(f"{nm:<10}{f'{cw}x{ch}':>18}{r:>12.2f}"
              f"{(sub > CONTENT_T).mean()*100:>9.1f}%{ch/cw if cw else float('nan'):>9.2f}"
              f"{f'{top_pad:.2f}/{bot_pad:.2f}':>16}")

    if ratios:
        import statistics as st
        m = st.median(ratios)
        print(f"\n面板纵横比中位数 {m:.2f} (宽/高)")
        if m < 0.8:
            print(f"  ⚠️ 面板明显竖长 => 横轴被压 / 纵轴被拉伸约 {1/m:.1f}x")
            print("     UMAP/t-SNE/PCA 需等比例: 加 coord_fixed(ratio=1) 或 theme(aspect.ratio=1)")
            print("     ⚠️ 加完后收【画布高度】而不是砍 pt.size (宽度不变则点径仍有效)")
        elif m > 1.3:
            print(f"  ⚠️ 面板明显横长 => 纵向被压缩约 {m:.1f}x, 同样需 coord_fixed")
        else:
            print("  ✅ 面板近方形, 等比例约束合理")


def palette(spec: str) -> None:
    items = []
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        name, _, hexv = tok.partition("=")
        hexv = hexv.strip() or name.strip()
        items.append((name.strip() or hexv, hexv))
    if not items:
        sys.exit("--palette 格式: 'name=#RRGGBB,name2=#RRGGBB,...'")

    def lum(hexv):
        hexv = hexv.lstrip("#")
        if len(hexv) != 6:
            sys.exit(f"非法色值: #{hexv}")
        r, g, b = (int(hexv[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    L = sorted(((lum(v), n, v) for n, v in items))
    print("灰度亮度 (0=黑 1=白):")
    for l, n, v in L:
        print(f"  {n:<14}{v}  L={l:.3f}")
    d = [L[i + 1][0] - L[i][0] for i in range(len(L) - 1)]
    print(f"\n亮度跨度 {L[-1][0]-L[0][0]:.3f} | 相邻最小差 {min(d):.3f}")
    k = d.index(min(d))
    print(f"最接近的一对: {L[k][1]} vs {L[k+1][1]}  (ΔL={d[k]:.3f})")
    if min(d) < 0.05:
        print("  ⚠️ ΔL<0.05 ⇒ 灰度打印下难以区分, 需换色或加形状/线型编码")
    else:
        print("  ✅ 灰度可分辨")
    print("\n⚠️ 只对本次传入的配色成立; 若为占位色, 不可替用户宣称其配色达标")


def main() -> None:
    ap = argparse.ArgumentParser(description="量已渲染图的几何与可读性")
    ap.add_argument("image", nargs="?", help="PNG 预览图 (矢量 PDF/SVG 不适用)")
    ap.add_argument("--panels", type=int, default=6, help="等分面板数 (默认 6)")
    ap.add_argument("--res", type=float, default=100, help="渲染 dpi, 用于换算 inch (默认 100)")
    ap.add_argument("--bounds", help="每块内容的 x 区间, 逗号分隔 (优先于 --panels)")
    ap.add_argument("--names", help="面板名, 逗号分隔")
    ap.add_argument("--palette", help="配色灰度检查: 'name=#RRGGBB,...'")
    args = ap.parse_args()

    if args.palette:
        palette(args.palette)
        return
    if not args.image:
        ap.error("需要 image 路径, 或用 --palette 做配色检查")
    bounds = [float(v) for v in args.bounds.split(",")] if args.bounds else None
    names = args.names.split(",") if args.names else None
    geometry(args.image, args.panels, args.res, bounds, names)


if __name__ == "__main__":
    main()