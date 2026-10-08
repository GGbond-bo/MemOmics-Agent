#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
热图灰度 / 色觉可达性审计（只需 numpy + PIL）

回答「RdBu 这类 diverging 色标在灰度打印 / 色觉障碍读者眼中还分得清吗」——
尤其是行内 z-score 把低动态范围程序拉满色阶之后，反方/审稿人必然要问的那个问题。

原理
  按绘制几何反推每个单元格中心的像素坐标 → 5×5 中位数取样（避开白色格线）
  → ① 相对亮度（sRGB→linear 加权，模拟灰度打印的最优映射）
    ② Viénot 1999 近似矩阵模拟 deuteranopia（红绿色盲）/ protanopia（红色盲）
  → 逐行打印「同一行内各格之间的 Δ」，Δ 最小者 = 可辨性最弱的行。

几何口径必须与出图脚本一致，否则取样点会落到格线上：
  x_px = mai_l*dpi + (col-0.5)*cell_in*dpi
  y_px = H_px - mai_b*dpi - (row_y+0.5)*cell_in*dpi
  row_y 自 YMAX 向下递减（R 的 y 轴向上增长 → 行布局必须递减赋值）

用法
  python audit_heatmap_gray_cvd.py --png Fig.png \
    --rows "Metabolism:4,Nutrient:4,Contractile:3,Inflamm-aging:4,Decompensation:2" \
    --progs "OxPhos,Glycolysis,Fatty acid metab.,Adipogenesis,Insulin signaling,mTORC1,AMPK-PGC1a,Autophagy,Sarcomeric,RegMyon,Denervation,SenMayo,Inflammatory,TNFA-NFKB,ROS,Atrophy,Fibrosis" \
    --ncol 10 --cell-in 0.255 --mai-l 1.35 --mai-r 0.35 --mai-b 0.75 --gap-y 0.24 \
    --csv audit.csv

判读参考（RdBu_r，17 行 × 10 格实测）
  灰度 Δ  min 0.639 / 中位 0.869 ；红绿色盲 Δ min 1.183 ；红色盲 Δ min 1.169
  Δ 明显 > 0 即「同一行内深浅可辨」。若出现 gray_range < 0.15 的行，
  该行在灰度打印下几乎不可分，需要换色标或加冗余编码（纹理/符号/分组标注）。
"""
import argparse
import csv
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", required=True, help="热图 PNG（300dpi 原图，勿用缩略图）")
    ap.add_argument("--rows", required=True, help="轴:成员数,轴:成员数,... 自顶向下")
    ap.add_argument("--progs", required=True, help="按行序（自顶向下）逗号分隔的程序名/行名")
    ap.add_argument("--ncol", type=int, default=10, help="列数（默认 10）")
    ap.add_argument("--cell-in", type=float, default=0.255, help="单元格边长（英寸）")
    ap.add_argument("--mai-l", type=float, default=1.35)
    ap.add_argument("--mai-r", type=float, default=0.35)
    ap.add_argument("--mai-b", type=float, default=0.75)
    ap.add_argument("--gap-y", type=float, default=0.24, help="轴间纵向间隙（数据单位）")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--radius", type=int, default=3, help="取样半边长（5 => 11x11）")
    ap.add_argument("--csv", default="", help="可选：逐行结果落 CSV")
    a = ap.parse_args()

    import numpy as np
    from PIL import Image

    im = np.asarray(Image.open(a.png).convert("RGB")).astype(float) / 255.0
    hp, wp = im.shape[:2]

    axes = []
    for tok in a.rows.split(","):
        name, _, n = tok.rpartition(":")
        if not name or not n.isdigit():
            sys.exit("--rows 格式应为 轴名:成员数,轴名:成员数,...（收到 %r）" % tok)
        axes.append((name.strip(), int(n)))
    progs = [p.strip() for p in a.progs.split(",")]
    nrow = sum(n for _, n in axes)
    if len(progs) != nrow:
        sys.exit("--progs 给了 %d 个，但 --rows 合计 %d 行，数量必须一致" % (len(progs), nrow))

    exp_w = (a.ncol * a.cell_in + a.mai_l + a.mai_r) * a.dpi
    if abs(exp_w - wp) > max(6.0, 0.01 * wp):
        print("[warn] 几何与图像不符：按参数算宽度 %.0f px，实际 %d px —— 取样点可能落在格线上"
              % (exp_w, wp))

    # 行 y（数据单位），自顶向下递减
    ymax = nrow + a.gap_y * (len(axes) - 1)
    rowy, yc, idx = [], ymax, 0
    for k, (name, n) in enumerate(axes):
        for _ in range(n):
            yc -= 1
            rowy.append((name, progs[idx], yc))
            idx += 1
        if k < len(axes) - 1:
            yc -= a.gap_y

    px = a.cell_in * a.dpi

    def sample(xd, yd):
        x0 = int(round(a.mai_l * a.dpi + xd * px))
        y0 = int(round(hp - a.mai_b * a.dpi - yd * px))
        r = a.radius
        blk = im[max(0, y0 - r):y0 + r + 1, max(0, x0 - r):x0 + r + 1].reshape(-1, 3)
        return np.median(blk, axis=0)

    def to_lin(c):
        c = np.clip(c, 0.0, 1.0)
        return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

    def to_srgb(c):
        c = np.clip(c, 0.0, 1.0)
        return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)

    deut = np.array([[0.625, 0.375, 0.0], [0.70, 0.30, 0.0], [0.0, 0.30, 0.70]])
    prot = np.array([[0.567, 0.433, 0.0], [0.558, 0.442, 0.0], [0.0, 0.242, 0.758]])

    def simulate(rgb, m):
        return to_srgb(to_lin(rgb) @ m.T)

    def luma(rgb):
        lin = to_lin(rgb)
        return 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]

    recs = []
    for name, prog, y in rowy:
        cells = np.array([sample(ci - 0.5, y + 0.5) for ci in range(1, a.ncol + 1)])
        g = luma(cells)
        d = np.array([simulate(c, deut) for c in cells])
        p = np.array([simulate(c, prot) for c in cells])
        recs.append(dict(program=prog, axis=name,
                         gray_range=float(g.max() - g.min()),
                         deut_range=float(np.linalg.norm(d.max(0) - d.min(0))),
                         prot_range=float(np.linalg.norm(p.max(0) - p.min(0))),
                         raw_range=float(np.linalg.norm(cells.max(0) - cells.min(0)))))

    print("图像 %dx%d px | %d 行 x %d 列" % (wp, hp, nrow, a.ncol))
    print("\n=== 可辨性最弱的 6 行（灰度 Δ 升序）===")
    print("%-22s%-16s%9s%12s%11s%11s" % ("program", "axis", "灰度Δ", "红绿色盲Δ", "红色盲Δ", "原始RGBΔ"))
    for r in sorted(recs, key=lambda x: x["gray_range"])[:6]:
        print("%-22s%-16s%9.3f%12.3f%11.3f%11.3f"
              % (r["program"], r["axis"], r["gray_range"], r["deut_range"],
                 r["prot_range"], r["raw_range"]))

    gs = [r["gray_range"] for r in recs]
    ds = [r["deut_range"] for r in recs]
    ps = [r["prot_range"] for r in recs]
    print("\n=== 全部 %d 行汇总 ===" % nrow)
    print("灰度Δ     min=%.3f 中位=%.3f max=%.3f" % (min(gs), float(np.median(gs)), max(gs)))
    print("红绿色盲Δ min=%.3f 中位=%.3f max=%.3f" % (min(ds), float(np.median(ds)), max(ds)))
    print("红色盲Δ   min=%.3f 中位=%.3f max=%.3f" % (min(ps), float(np.median(ps)), max(ps)))
    weak = [r["program"] for r in recs if r["gray_range"] < 0.15]
    print("灰度不可辨行（gray_range < 0.15）：%s" % (", ".join(weak) if weak else "无"))

    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
            w.writeheader()
            w.writerows(recs)
        print("写出: %s" % a.csv)


if __name__ == "__main__":
    main()