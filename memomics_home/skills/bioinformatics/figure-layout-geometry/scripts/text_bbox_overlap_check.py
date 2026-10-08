#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
text_bbox_overlap_check.py — 图内「文字 ⨯ 文字」碰撞的硬指标互检

用途
----
改完一张多面板图的标注层后，**证明文字真的不再互相压住**，而不是"我看着好了"。
用户指着图说「这张图有文字重叠」时，修完必须用它复验并把数字贴出来。

原理
----
用 runpy 执行绘图脚本（拦截 plt.close 保住 figure），在**导出 dpi** 下取全部
Text 的 window_extent（ax.texts / 轴标题 / 刻度标签 / fig.texts），两两求交，
报告任何重叠面积 > eps 的文字对。OCR 只作第二证据：OCR 会把相邻文字顺序打乱、
且覆盖率有上限（实测 74 处文字 OCR 只报出 66 条），不能当唯一判据。

用法
----
  python text_bbox_overlap_check.py <figure_script.py> [--dpi 300] [--eps 4]
                                    [--csv out.csv] [--quiet]

  --eps   重叠面积阈值，单位 px^2（默认 4.0，≈0.0004 mm² @300dpi）。
          不要设 0：相邻行文本允许亚像素相切。
  --csv   明细导出路径（默认写到脚本同目录 _text_overlap_check.csv）

退出码
------
  0 = PASS（无文字重叠）  1 = FAIL（存在重叠对）  2 = 用法/执行错误

实测案例（2026-10-02, 44d_MEF2C_AS1_audit_map.py）
--------------------------------------------------
  修复前：Panel B 三段长坐标标签与加粗横幅同处 y≈1.02/1.095 层叠 + ①(15.9%)
          与 ②(33.3%) 横向贴住 → OCR 读成糊字 "the onlyhregborBuMBeoiusttingicansee"
  修复后：texts=74, OVERLAPPING PAIRS = 0 → PASS
"""
import argparse
import csv
import os
import runpy
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def collect_texts(figs, dpi):
    """返回 [(label, bbox), ...]，坐标为导出 dpi 下的像素窗口范围。"""
    items = []
    for fi, fig in enumerate(figs):
        fig.set_dpi(dpi)
        fig.canvas.draw()
        try:
            rend = fig.canvas.get_renderer()
        except Exception:
            rend = None

        def _ext(t):
            if rend is not None:
                return t.get_window_extent(renderer=rend)
            return t.get_window_extent()

        for ai, ax in enumerate(fig.axes):
            tag = f"fig{fi}.ax{ai}"
            for t in ax.texts:
                if t.get_text().strip() and t.get_visible():
                    items.append((f"{tag}|{t.get_text()[:46]}", _ext(t)))
            for nm, t in (("xlabel", ax.xaxis.label), ("ylabel", ax.yaxis.label),
                          ("title", ax.title)):
                if t.get_text().strip() and t.get_visible():
                    items.append((f"{tag}|{nm}:{t.get_text()[:30]}", _ext(t)))
            for t in list(ax.get_xticklabels()) + list(ax.get_yticklabels()):
                if t.get_text().strip() and t.get_visible():
                    items.append((f"{tag}|tick:{t.get_text()[:20]}", _ext(t)))
        for t in fig.texts:
            if t.get_text().strip() and t.get_visible():
                items.append((f"fig{fi}|{t.get_text()[:46]}", _ext(t)))
    return items


def find_overlaps(items, eps):
    def area(b):
        return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)

    bad = []
    for i in range(len(items)):
        n1, b1 = items[i]
        for j in range(i + 1, len(items)):
            n2, b2 = items[j]
            ix = max(0.0, min(b1.x1, b2.x1) - max(b1.x0, b2.x0))
            iy = max(0.0, min(b1.y1, b2.y1) - max(b1.y0, b2.y0))
            ov = ix * iy
            if ov > eps:
                sm = min(area(b1), area(b2))
                bad.append((n1, n2, round(ov, 1), round(sm, 1)))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script", help="绘图脚本路径（.py）")
    ap.add_argument("--dpi", type=int, default=300, help="导出 dpi（默认 300）")
    ap.add_argument("--eps", type=float, default=4.0, help="重叠面积阈值 px^2（默认 4.0）")
    ap.add_argument("--csv", default="", help="明细 CSV 输出路径")
    ap.add_argument("--quiet", action="store_true", help="不打印目标脚本自身的 stdout")
    a = ap.parse_args()

    if not os.path.exists(a.script):
        print(f"[ERR] script not found: {a.script}")
        return 2

    captured = []
    _orig_close = plt.close
    plt.close = lambda f=None: captured.append(f if f is not None else plt.gcf())

    if a.quiet:
        import contextlib
        import io
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                runpy.run_path(a.script, run_name="__main__")
        except SystemExit:
            pass
    else:
        try:
            runpy.run_path(a.script, run_name="__main__")
        except SystemExit:
            pass
    finally:
        plt.close = _orig_close

    figs = [f for f in captured if f is not None]
    if not figs:
        figs = [plt.gcf()]
    print(f"[info] figures captured: {len(figs)}  (target dpi = {a.dpi})")

    items = collect_texts(figs, a.dpi)
    print(f"[info] texts collected: {len(items)}")
    bad = find_overlaps(items, a.eps)

    csv_path = a.csv or os.path.join(os.path.dirname(os.path.abspath(a.script)),
                                     "_text_overlap_check.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["text_a", "text_b", "overlap_px2", "smaller_box_px2", "overlap_pct_of_smaller"])
        for n1, n2, ov, sm in bad:
            w.writerow([n1, n2, ov, sm, round(100 * ov / sm, 2) if sm else ""])

    print(f"OVERLAPPING PAIRS (> {a.eps} px^2 @{a.dpi}dpi): {len(bad)}")
    for n1, n2, ov, sm in sorted(bad, key=lambda x: -x[2])[:25]:
        print(f"  {ov:8.1f} px2  ({100 * ov / sm:5.1f}% of smaller)")
        print(f"      A: {n1}")
        print(f"      B: {n2}")
    print("CHECK:", "PASS - no text overlap" if not bad
          else f"FAIL - {len(bad)} overlapping pairs (fix, then re-run)")
    print("csv:", csv_path)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())