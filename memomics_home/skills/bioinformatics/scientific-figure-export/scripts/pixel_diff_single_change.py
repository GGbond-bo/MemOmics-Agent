#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""pixel_diff_single_change.py — 证明"只改了一处"的确定性探针

配套 SKILL.md「单元素改版：像素差分核验协议」+ references/single-element-revision-pixel-diff.md

用法
----
  # ① 差分前先确认两版是同一个渲染器（跨解释器渲染会让差分失真）
  python pixel_diff_single_change.py --probe

  # ② 差分旧版/新版，静区按 y-frac 成对给
  python pixel_diff_single_change.py OLD.png NEW.png --quiet 0.25 0.80 0.85 1.0

输出
----
  尺寸一致性 / 差异像素数与占画布比 / 包围盒(行+y-frac、列+x-frac) /
  x 方向簇数与各簇宽度 / 各静区差异 / 新版健康检查(非白占比、唯一色数)

判据
----
  静区差异 = 0  且  x 方向簇数 = 本次改动的独立元素个数  ⇒ 只改了那一处

例（2026-09-29 实测）
--------------------
  v3 -> v4 删 5 个面板字母 : 2,229 px(0.057%) 行 169-203  x 恰好 5 簇各 23-24 px  柱区 0  底部 0
  v4 -> v5 Σ 顺序对调      : 13,320 px        行 274-306 x 1 簇(Σ 行)            柱区 0  底部 0
"""
import sys
import argparse


def probe():
    """打印当前解释器的 matplotlib 版本与字体解析结果。"""
    import matplotlib as mpl
    import matplotlib.font_manager as fm
    fam = "DejaVu Sans"
    for f in ("Arial", "Helvetica"):
        try:
            fm.findfont(fm.FontProperties(family=f), fallback_to_default=False)
            fam = f
            break
        except Exception:
            pass
    print(f"interpreter = {sys.executable}")
    print(f"matplotlib  = {mpl.__version__}")
    print(f"font chain  = {fam}")
    print("⚠️ 两个版本做像素差分之前，各自跑一次 --probe：matplotlib 版本不一致 ⇒ 差分结果不可用于"
          "『只改了一处』的结论（跨版本字形差异会散布全画布）。")


def main():
    ap = argparse.ArgumentParser(description="证明『只改了一处』的像素差分探针")
    ap.add_argument("old", nargs="?", help="旧版 PNG")
    ap.add_argument("new", nargs="?", help="新版 PNG")
    ap.add_argument("--tol", type=int, default=10, help="三通道差和阈值（默认 10）")
    ap.add_argument("--gap", type=int, default=25, help="x 方向并簇间隔像素（默认 25）")
    ap.add_argument("--quiet", nargs="*", type=float, default=[],
                    help="静区 y-frac 区间，成对给：--quiet 0.25 0.80 0.85 1.0（这些区应 0 差异）")
    ap.add_argument("--probe", action="store_true", help="只打印渲染器信息")
    a = ap.parse_args()

    if a.probe or not (a.old and a.new):
        probe()
        if not a.probe:
            print("\n用法: python pixel_diff_single_change.py OLD.png NEW.png --quiet 0.25 0.80 0.85 1.0")
        return 0

    import numpy as np
    from PIL import Image

    probe()
    print("-" * 72)

    A = np.asarray(Image.open(a.old).convert("RGB")).astype(int)
    B = np.asarray(Image.open(a.new).convert("RGB")).astype(int)
    if A.shape != B.shape:
        print(f"❌ 尺寸不一致 {A.shape} vs {B.shape} —— 不可比（先确认画布/渲染器一致）")
        return 1
    H, W = B.shape[:2]
    print(f"尺寸 {W}x{H}")

    d = (np.abs(A - B).sum(axis=2) > a.tol)
    n = int(d.sum())
    print(f"差异像素 {n:,}  ({n / (H * W) * 100:.3f}% 画布)")

    if n == 0:
        print("✅ 两版逐像素完全一致")
    else:
        rows = np.where(d.any(axis=1))[0]
        cols = np.where(d.any(axis=0))[0]
        print(f"包围盒 行 {rows.min()}-{rows.max()} (y-frac {rows.min()/H:.3f}-{rows.max()/H:.3f})"
              f" | 列 {cols.min()}-{cols.max()} (x-frac {cols.min()/W:.3f}-{cols.max()/W:.3f})")
        cl = np.split(cols, np.where(np.diff(cols) > a.gap)[0] + 1)
        print(f"x 方向簇数 {len(cl)} | 各簇宽度 {[int(c[-1] - c[0] + 1) for c in cl]}")
        print("   ↑ 簇数应等于本次改动的独立元素个数（例：删 5 个面板字母 ⇒ 恰好 5 簇）")

    q = a.quiet
    for i in range(0, len(q) - 1, 2):
        y0, y1 = int(q[i] * H), int(q[i + 1] * H)
        s = int(d[y0:y1].sum())
        tag = "✅" if s == 0 else "⚠️ 该区本应不动，去查"
        print(f"{tag} 静区 y-frac {q[i]}-{q[i+1]} (行 {y0}-{y1}) 差异 {s:,} px")

    arr = B.reshape(-1, 3)
    nonwhite = float((arr.sum(axis=1) < 720).mean())
    uniq = len(np.unique(arr, axis=0))
    bad = nonwhite < 0.01 or float((arr.sum(axis=1) < 60).mean()) > 0.5
    print(f"新版健康 非白占比 {nonwhite:.4f} | 唯一色 {uniq:,} | {'⚠️ 疑似空白/全黑' if bad else 'OK'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())