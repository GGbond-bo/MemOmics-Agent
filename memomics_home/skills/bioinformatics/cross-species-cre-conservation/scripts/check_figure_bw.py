# -*- coding: utf-8 -*-
"""
专利附图形式体检 —— 纯黑白判据 + 空白/过淡判据 + 尺寸清单。

用途：出完黑白版附图（或改造完彩色图）后复验，**不要凭"我改了配色"就宣布黑白**。
依据：《专利审查指南》第一部分第一章 2.4 —— 说明书附图应当使用制图工具和黑色墨水绘制，
      线条应当均匀清晰、足够深，不得着色和涂改。

判据：
  · 彩色像素占比 —— 必须 0.000%（判定阈值：max(|R-G|,|G-B|,|R-B|) > 12 视为彩色像素）
  · 墨迹占比    —— sum(RGB) < 600 的像素比例，正常 4%~20%；< 1% 疑似空白/过淡
  · 尺寸        —— 打印 px 与 @300dpi 对应的 cm，供与代理人确认版面

用法：
  python check_figure_bw.py <目录或图片路径> [更多路径...]
  python check_figure_bw.py E:/专利/patent/figures_bw
  python check_figure_bw.py E:/专利/patent/figures E:/专利/patent/figures_bw   # 彩色/黑白对照

退出码：0 = 全部通过；1 = 存在不合格（彩色像素 > 0 或疑似空白）。
"""
import os
import sys
import glob

from PIL import Image
import numpy as np

CHROMA_TOL = 12       # 通道差 > 12 视为彩色
INK_SUM = 600         # RGB 和 < 600 视为墨迹
MIN_INK_PCT = 1.0     # 墨迹占比下限（低于此判疑似空白/过淡）
MAX_INK_PCT = 30.0    # 墨迹占比上限（高于此判过黑、可能糊）
DPI = 300


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for ext in ("png", "PNG"):
                out.extend(glob.glob(os.path.join(p, "*." + ext)))
        elif os.path.isfile(p):
            out.append(p)
        else:
            print("  [跳过] 路径不存在: %s" % p)
    return sorted(set(out))


def inspect(p):
    im = Image.open(p).convert("RGB")
    a = np.asarray(im).astype(int)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    chroma = (np.abs(r - g) > CHROMA_TOL) | (np.abs(g - b) > CHROMA_TOL) | (np.abs(r - b) > CHROMA_TOL)
    ink = (a.sum(2) < INK_SUM).mean() * 100.0
    chroma_pct = chroma.mean() * 100.0
    cm = (im.width / DPI * 2.54, im.height / DPI * 2.54)
    return {
        "name": os.path.basename(p),
        "path": p,
        "bytes": os.path.getsize(p),
        "wxh": (im.width, im.height),
        "cm": cm,
        "chroma_pct": chroma_pct,
        "ink_pct": ink,
        "ok_bw": chroma_pct < 0.001,
        "ok_ink": MIN_INK_PCT <= ink <= MAX_INK_PCT,
    }


def main(argv):
    targets = argv[1:] or ["."]
    files = collect(targets)
    if not files:
        print("未找到 PNG 文件")
        return 1

    print("%-46s %10s %13s %9s %8s %8s  %s" %
          ("文件", "大小", "像素", "cm@300dpi", "彩色%", "墨迹%", "判定"))
    print("-" * 116)
    bad = []
    for p in files:
        try:
            d = inspect(p)
        except Exception as e:
            print("%-46s  读取失败: %s" % (os.path.basename(p), e))
            bad.append(p)
            continue
        verdict = "OK 黑白" if (d["ok_bw"] and d["ok_ink"]) else (
            "!! 含彩色像素" if not d["ok_bw"] else "!! 疑似空白/过淡" if d["ink_pct"] < MIN_INK_PCT else "!! 墨迹过重")
        if not (d["ok_bw"] and d["ok_ink"]):
            bad.append(d["path"])
        print("%-46s %9.1fKB %6dx%-6d %4.1fx%-4.1f %8.3f %8.1f  %s" %
              (d["name"], d["bytes"] / 1024.0, d["wxh"][0], d["wxh"][1],
               d["cm"][0], d["cm"][1], d["chroma_pct"], d["ink_pct"], verdict))

    print("-" * 116)
    print("共 %d 张；不合格 %d 张" % (len(files), len(bad)))
    for p in bad:
        print("  ✗ %s" % p)
    if bad:
        print("\n提示：彩色像素 > 0 ⇒ 回源脚本改配色（hatch / 线型 / 空心实心标记 / 黑底白字），")
        print("      改完重跑本脚本直到彩色占比 0.000%；墨迹 < 1% ⇒ 检查是否画到了空数据或画布裁切。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
