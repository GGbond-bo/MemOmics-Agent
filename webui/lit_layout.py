# -*- coding: utf-8 -*-
"""对照视图的 PDF 版面文本块（保留原位置、行数和字号）。

只读 PDF，不调用 LLM，不写知识库。每个文本块带归一化 rect、行数和原始字号，
前端据此把中文覆盖到原 PDF 页面相同位置，图表/公式/其它对象不动。
"""
from __future__ import annotations

import os
import re
import threading

from webui import lit_marks

_CACHE = {}
_LOCK = threading.Lock()
_HEADING_RE = re.compile(
    r"^(?:summary|abstract|graphical abstract|introduction|results?|discussion|methods?|"
    r"materials and methods|conclusions?|references|acknowledg(?:e)?ments|"
    r"author contributions|declaration of interests|supplementary information)$", re.I)


def _text_of_block(block: dict) -> str:
    parts = []
    for line in block.get("lines") or []:
        text = "".join(str(s.get("text") or "") for s in (line.get("spans") or []))
        # 手稿行号只是版面对象，不送入翻译。
        text = re.sub(r"^\s*\d{1,3}\s+", "", text).strip()
        if text:
            parts.append(text)
    out = " ".join(parts)
    # 保留 activity-induced 这类复合词连字符，只去掉断行空白。
    out = re.sub(r"([A-Za-z])-\s+([a-z])", r"\1-\2", out)
    return re.sub(r"\s+", " ", out).strip()


def load(rel: str) -> dict:
    path = lit_marks.pdf_path(rel)
    mtime = os.path.getmtime(path)
    with _LOCK:
        hit = _CACHE.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
    import pymupdf as fitz

    doc = fitz.open(path)
    pages = []
    try:
        for idx in range(doc.page_count):
            page = doc[idx]
            width = float(page.rect.width or 1)
            height = float(page.rect.height or 1)
            blocks = []
            data = page.get_text("dict", sort=True)
            for b in data.get("blocks") or []:
                if int(b.get("type") or 0) != 0:
                    continue
                # 旋转/竖排页边不参与覆盖，避免竖向块跨正文。
                dirs = [ln.get("dir") or (1, 0) for ln in (b.get("lines") or [])]
                if any(abs(float(d[1])) > 0.2 for d in dirs):
                    continue
                text = _text_of_block(b)
                if len(text) < 2:
                    continue
                bb = b.get("bbox") or (0, 0, 0, 0)
                sizes = [float(s.get("size") or 0) for ln in (b.get("lines") or [])
                         for s in (ln.get("spans") or []) if float(s.get("size") or 0) > 0]
                sizes.sort()
                font_size = sizes[len(sizes) // 2] if sizes else 10.0
                line_count = max(1, len(b.get("lines") or []))
                no = int(b.get("number") if b.get("number") is not None else len(blocks) + 1)
                kind = "heading" if (_HEADING_RE.match(text) or font_size >= 14 or
                                     (len(text) <= 100 and text.isupper())) else "p"
                blocks.append({
                    "id": "p%d-b%d" % (idx + 1, no),
                    "page": idx + 1,
                    "kind": kind,
                    "text": text,
                    "lines": line_count,
                    "font_size": round(font_size, 2),
                    "rect": {
                        "x": round(max(0.0, min(1.0, float(bb[0]) / width)), 5),
                        "y": round(max(0.0, min(1.0, float(bb[1]) / height)), 5),
                        "w": round(max(0.0, min(1.0, float(bb[2] - bb[0]) / width)), 5),
                        "h": round(max(0.0, min(1.0, float(bb[3] - bb[1]) / height)), 5),
                    },
                })
            pages.append({"page": idx + 1, "width": width, "height": height, "blocks": blocks})
    finally:
        doc.close()
    data = {"pdf": os.path.basename(path), "pages": pages,
            "total_blocks": sum(len(p["blocks"]) for p in pages), "source": "pymupdf-layout"}
    with _LOCK:
        _CACHE[path] = (mtime, data)
        while len(_CACHE) > 12:
            _CACHE.pop(next(iter(_CACHE)))
    return data