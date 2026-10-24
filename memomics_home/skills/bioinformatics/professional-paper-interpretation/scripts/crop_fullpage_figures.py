#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""整页图版论文（Cell/Science 式）的主图批量裁取 —— footer-anchored。

为什么不用 caption 锚点：这类排版里主图**独占一页**（图版页），caption 往往在同一页图下方，
但图区本身靠 `get_drawings()` 拿不到（矢量内容常驻 XObject，只返回页眉碎片，矩形会退化成页眉条）。
最稳的做法：以「页脚文字块上沿」为裁切下界（页脚形如 'Cell 190, 1–27, ...' 或纯页码数字），
上界取页顶安全边距，左右留边距，按 dpi 渲染。

用法：
  # 裁主图（页号按 1-based 传，与 PDF 阅读器一致）
  python crop_fullpage_figures.py <pdf> <outdir> --pages 3,6,8,10,13,16,17 --dpi 200

  # 可选：自定义文件名（与 --pages 一一对应，逗号分隔）
  python crop_fullpage_figures.py <pdf> <outdir> --pages 1,3,6 --names FigGA,Fig1,Fig2

  # 只导出逐页文本（带 '===== PAGE n =====' 分隔，便于 grep 章节区间）
  python crop_fullpage_figures.py <pdf> <outdir> --text-dump pages_text.txt

输出：<outdir>/<name>_p<page>.png，并打印每张图的 像素尺寸 / KB / 非白像素%。
      ⚠️ 非白像素 <5% 通常说明裁到空白或正文页（页索引 off-by-one 的典型症状）——必须复核。
"""
from __future__ import annotations

import argparse
import os
import re
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("需要 PyMuPDF：pip install pymupdf")

FOOTER_RE = re.compile(r"Cell\s+\d+|\b\d{1,3}\b\s*$")


def footer_cut(page, margin: float = 58.0) -> float:
    """返回裁切下界 y：默认页面底部 −margin，若发现页脚文字块则取其上沿。"""
    rect = page.rect
    ycut = rect.y1 - margin
    for b in page.get_text("blocks"):
        txt = (b[4] or "").strip()
        if not txt:
            continue
        if "Cell " in txt or re.fullmatch(r"\d{1,3}", txt):
            ycut = min(ycut, b[1] - 4)
    return ycut


def crop(pdf: str, outdir: str, pages: list[int], names: list[str] | None,
         dpi: int = 200, top: float = 36.0, left: float = 28.0, right: float = 22.0) -> int:
    doc = fitz.open(pdf)
    os.makedirs(outdir, exist_ok=True)
    zoom = dpi / 72.0
    ok = 0
    for idx, pno in enumerate(pages):
        i = pno - 1                       # ← 1-based → 0-based（off-by-one 就出在这里）
        if not 0 <= i < doc.page_count:
            print(f"!! page {pno} 超出范围 (共 {doc.page_count} 页)，跳过")
            continue
        page = doc[i]
        r = page.rect
        clip = fitz.Rect(left, top, r.x1 - right, footer_cut(page))
        name = names[idx] if names and idx < len(names) else f"Fig{pno}"
        out = os.path.join(outdir, f"{name}_p{pno}.png")
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
        pix.save(out)
        kb = os.path.getsize(out) // 1024
        note = ""
        try:
            from PIL import Image
            import numpy as np
            a = np.asarray(Image.open(out).convert("L"))
            pct = float((a < 240).mean() * 100)
            note = f"  非白像素={pct:.1f}%"
            if pct < 5:
                note += "  ⚠️ 疑似空白/裁错页，请抽查"
        except Exception:
            pass
        print(f"{name}: page {pno} -> {out}  {pix.width}x{pix.height}  {kb} KB{note}")
        ok += 1
    return ok


def dump_text(pdf: str, dest: str) -> None:
    doc = fitz.open(pdf)
    os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        for i, pg in enumerate(doc):
            f.write(f"\n===== PAGE {i + 1} =====\n" + pg.get_text())
    print(f"pages={doc.page_count} -> {dest}")
    print("meta:", doc.metadata)


def main() -> None:
    ap = argparse.ArgumentParser(description="整页图版论文的主图批量裁取 / 逐页文本导出")
    ap.add_argument("pdf")
    ap.add_argument("outdir")
    ap.add_argument("--pages", help="要裁的页号，1-based，逗号分隔，如 3,6,8,10,13,16,17")
    ap.add_argument("--names", help="可选，与 --pages 一一对应的输出名前缀")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--text-dump", help="只导出逐页文本到该路径（可与 --pages 同时使用）")
    a = ap.parse_args()

    if a.text_dump:
        dump_text(a.pdf, a.text_dump)
    if a.pages:
        pages = [int(x) for x in a.pages.split(",") if x.strip()]
        names = [x.strip() for x in a.names.split(",")] if a.names else None
        n = crop(a.pdf, a.outdir, pages, names, dpi=a.dpi)
        print(f"done: {n} figure page(s) -> {a.outdir}")
    if not a.pages and not a.text_dump:
        ap.error("至少要给 --pages 或 --text-dump")


if __name__ == "__main__":
    main()