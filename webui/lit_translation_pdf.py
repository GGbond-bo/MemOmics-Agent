# -*- coding: utf-8 -*-
"""把对照译文写回 PDF：按原 block 矩形遮罩英文并写入中文（2026-11-16）。

只写派生文件，不改原 PDF：
  papers/.translations/<stem>.p<N>.pdf   单页（供右栏双 PDF 对照）
  papers/.translations/<stem>.zh.pdf    整篇（导出/下载）

关键约束：
- 坐标以 lit_layout 的归一化 rect 为准，不信任前端传来的坐标；
- 无译文 / 译文等于原文的块保持原样；
- 图、表、公式不动，只遮罩文本块；
- 中文使用 PyMuPDF 内置 china-s，按矩形自动缩字号，极端溢出时截断并记录。
"""
from __future__ import annotations

import os

import pymupdf as fitz

from webui import lit_marks

CJK_FONT = "china-s"
FONT_PATH = r"C:\Windows\Fonts\simhei.ttf"
MIN_FONT = 4.5
MAX_TEXT = 12000


def _font_kwargs() -> dict:
    """优先系统黑体：内置 china-s 会把拉丁字母/数字拉成全角间距。"""
    if os.path.isfile(FONT_PATH):
        return {"fontname": "litzh", "fontfile": FONT_PATH}
    return {"fontname": CJK_FONT}


def _out_path(src: str, page: int | None = None) -> str:
    stem = os.path.splitext(os.path.basename(src))[0]
    suffix = ".p%d.pdf" % page if page else ".zh.pdf"
    root = os.path.join(lit_marks.papers_root(), ".translations")
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, stem + suffix)


def _rect_of(block: dict, page_rect) -> fitz.Rect:
    r = block.get("rect") or {}
    x = float(r.get("x") or 0) * page_rect.width + page_rect.x0
    y = float(r.get("y") or 0) * page_rect.height + page_rect.y0
    w = float(r.get("w") or 0) * page_rect.width
    h = float(r.get("h") or 0) * page_rect.height
    # 轻微外扩，避免英文抗锯齿边缘从中文下面漏出来
    pad = 0.6
    return fitz.Rect(x - pad, y - pad, x + w + pad, y + h + pad) & page_rect


def _trial_spare(rect: fitz.Rect, text: str, size: float) -> float:
    """在临时文档试写，返回剩余高度；负数表示装不下。"""
    doc = fitz.open()
    try:
        page = doc.new_page(width=max(1.0, rect.width), height=max(1.0, rect.height))
        box = fitz.Rect(0, 0, rect.width, rect.height)
        return float(page.insert_textbox(
            box, text, fontsize=size, color=(0, 0, 0), align=0, **_font_kwargs()
        ))
    finally:
        doc.close()


def _fit_text(rect: fitz.Rect, text: str, base: float):
    """返回 (字号, 实际文本, 是否截断)。保证有内容可写。"""
    size = max(MIN_FONT, min(28.0, float(base or 10.0)))
    while size > MIN_FONT:
        if _trial_spare(rect, text, size) >= 0:
            return size, text, False
        size = round(size - 0.5, 2)
    # 最小字号仍装不下：二分截断，保留可读前缀
    lo, hi = 0, len(text)
    best = ""
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid].rstrip() + "…"
        if _trial_spare(rect, candidate, MIN_FONT) >= 0:
            best = candidate
            lo = mid
        else:
            hi = mid - 1
    return MIN_FONT, best or text[:1], True


def build(src_rel: str, layout: dict, translations: dict, page: int | None = None) -> dict:
    """生成译文 PDF。translations 的 key 是 lit_layout 的 block id。"""
    src = lit_marks.pdf_path(src_rel)
    out = _out_path(src, page)
    pages = layout.get("pages") or []
    if not pages:
        raise ValueError("没有可用版面")
    wanted = None
    if page is not None:
        wanted = int(page)
        if wanted < 1 or wanted > len(pages):
            raise ValueError("页码超出范围")

    doc = fitz.open(src)
    written, skipped, truncated = [], [], []
    try:
        for pg in pages:
            n = int(pg.get("page") or 0)
            if wanted is not None and n != wanted:
                continue
            if n < 1 or n > doc.page_count:
                continue
            p = doc[n - 1]
            for block in pg.get("blocks") or []:
                bid = str(block.get("id") or "")
                source = str(block.get("text") or "").strip()
                zh = str(translations.get(bid) or "").strip()
                if not zh or zh == source:
                    skipped.append(bid)
                    continue
                rect = _rect_of(block, p.rect)
                if rect.is_empty or rect.width < 2 or rect.height < 2:
                    skipped.append(bid)
                    continue
                base = float(block.get("font_size") or 10.0)
                if block.get("kind") == "heading":
                    base = max(base, 12.0)
                size, text, cut = _fit_text(rect, zh[:MAX_TEXT], base)
                # 白底只盖住原文本块；图片/公式不受影响
                p.draw_rect(rect, color=None, fill=(1, 1, 1), overlay=True)
                p.insert_textbox(rect, text, fontsize=size, color=(0, 0, 0),
                                 align=0, overlay=True, **_font_kwargs())
                written.append(bid)
                if cut:
                    truncated.append(bid)
        if wanted is not None:
            # 单页文件供右栏按页取图；不改变原 PDF
            doc.select([wanted - 1])
        tmp = out + ".tmp-%d.pdf" % os.getpid()
        doc.save(tmp, garbage=4, deflate=True)
    finally:
        doc.close()
    os.replace(tmp, out)
    return {
        "file": os.path.basename(out),
        "rel": ".translations/" + os.path.basename(out),
        "page": wanted,
        "written": len(written),
        "skipped": len(skipped),
        "truncated": truncated,
        "bytes": os.path.getsize(out),
    }
