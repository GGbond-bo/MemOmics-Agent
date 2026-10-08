# -*- coding: utf-8 -*-
"""font_compare.py — 字号对照验收 / 交付预览（panel_to_a4 的核对搭档）。

背景（2026-10-05 实测教训）：
  * AI `exportFile` 的 PNG 默认 72dpi —— A4 页面上 5~7pt 文字只有 5~7 像素高，
    缩略图/低分图上看不清，用户容易误判「字号没变」；
  * 因此「用户可见预览」一律用成品 PDF 渲染 300dpi；
  * 「字号到底变没变」用 PDF 文本层直读字号直方图 + 原/成品同比例对照图（本脚本）。

做法：
  1) 读两份 PDF 的文本层 → 字号直方图、字体名分布（对照打印 + 写 JSON）；
  2) 内容区自动取联合边界（文字 bbox ∪ 矢量 drawings）→ 原图/成品各渲一张同比例整图；
  3) 按关键字（默认自动：最大字号词 / O_Pre / FDR）各给一组放大对照；
  4) 成品全页渲 300dpi 预览。

用法：
  python font_compare.py --orig <原图.pdf> --final <成品.pdf> --out <目录>
  python font_compare.py --orig ... --final ... --out ... --keys "Aged,O_Pre,FDR" --zoom 12

输出（--out 目录）：
  * 字号对照_原图vs成品.png     —— 上下两整图 + 按关键字的放大对
  * <成品名>_preview_300dpi.png —— 成品全页 300dpi 预览（替代 72dpi 小图）
  * font_compare_report.json    —— 两份 PDF 的字号/字体/放大对证据

依赖：pymupdf + Pillow（本机 venv `E:\\MemOmics-Agent\\.venv` 已装）。
约定：只读 PDF，不碰任何源文件；页码固定取第 1 页。
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter

import pymupdf
from PIL import Image, ImageDraw, ImageFont

MONTAGE_NAME = "字号对照_原图vs成品.png"
REPORT_NAME = "font_compare_report.json"


def all_spans(doc: "pymupdf.Document"):
    """θ=0 页面上的全部文字 span（跳过纯空白）。"""
    spans = []
    for b in doc[0].get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            for s in line.get("spans", []):
                if s.get("text", "").strip():
                    spans.append(s)
    return spans


def size_hist(spans) -> dict:
    return {k: v for k, v in sorted(Counter(round(float(s["size"]), 1) for s in spans).items())}


def font_hist(spans) -> dict:
    return dict(Counter(s.get("font", "?") for s in spans))


def hist_text(h: dict) -> str:
    return " · ".join("%g×%d" % (k, v) for k, v in h.items())


def content_rect(page) -> "pymupdf.Rect":
    """内容联合边界：文字 bbox ∪ 矢量 drawings（含 2pt 余量）。"""
    r = pymupdf.Rect()
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            for s in line.get("spans", []):
                if s.get("text", "").strip():
                    r |= pymupdf.Rect(s["bbox"])
    try:
        for d in page.get_drawings():
            if d.get("rect"):
                r |= pymupdf.Rect(d["rect"])
    except Exception:
        pass
    if r.is_empty:
        r = pymupdf.Rect(page.rect)
    return r + (-2, -2, 2, 2)


def render(doc, rect, zoom) -> Image.Image:
    pm = doc[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=rect)
    return Image.frombytes("RGB", (pm.width, pm.height), pm.samples)


def load_font(size):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
              r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def find_span(spans, key):
    if not key:
        return None
    k = key.lower()
    for s in spans:
        if k in s["text"].lower():
            return s
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", required=True, help="原图 PDF")
    ap.add_argument("--final", required=True, help="成品 PDF")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--keys", default="", help="放大对照关键字（逗号分隔；默认自动：最大字号词/O_Pre/FDR）")
    ap.add_argument("--zoom", type=float, default=12.0, help="放大对渲染倍率（默认 12 ≈ 864dpi）")
    ap.add_argument("--width", type=int, default=1900, help="对照图宽度（默认 1900）")
    a = ap.parse_args()

    for p in (a.orig, a.final):
        if not os.path.isfile(p):
            print("找不到文件:", p)
            return 2
    os.makedirs(a.out, exist_ok=True)

    odoc, fdoc = pymupdf.open(a.orig), pymupdf.open(a.final)
    osp, fsp = all_spans(odoc), all_spans(fdoc)
    oh, fh = size_hist(osp), size_hist(fsp)
    log = {
        "orig": {"path": a.orig, "span_count": len(osp), "size_hist": oh, "fonts": font_hist(osp)},
        "final": {"path": a.final, "span_count": len(fsp), "size_hist": fh, "fonts": font_hist(fsp)},
        "zoom_pairs": [], "outputs": {},
    }
    print("原图 : %d spans  %s  %s" % (len(osp), hist_text(oh), log["orig"]["fonts"]))
    print("成品 : %d spans  %s  %s" % (len(fsp), hist_text(fh), log["final"]["fonts"]))

    # 放大关键字：默认自动
    if a.keys.strip():
        keys = [k.strip() for k in a.keys.split(",") if k.strip()]
    else:
        keys = []
        if osp:
            top = max(osp, key=lambda s: float(s["size"]))
            keys.append(top["text"].split()[0])
        if any("O_Pre" in s["text"] for s in osp):
            keys.append("O_Pre")
        if any("FDR" in s["text"] for s in osp):
            keys.append("FDR")
    log["keys"] = keys

    W = a.width
    ZOOM = 300 / 72.0
    rows = []  # (kind, payload, label)
    rows.append(("label", None, "① 原图（%s）" % hist_text(oh)))
    rows.append(("img", render(odoc, content_rect(odoc[0]), ZOOM), None))
    rows.append(("label", None, "② 成品（%s）" % hist_text(fh)))
    rows.append(("img", render(fdoc, content_rect(fdoc[0]), ZOOM), None))
    for i, key in enumerate(keys, start=1):
        so, sf = find_span(osp, key), find_span(fsp, key)
        if so is None or sf is None:
            print("跳过放大对（任一侧缺「%s」）" % key)
            continue
        co = render(odoc, pymupdf.Rect(so["bbox"]) + (-7, -7, 7, 7), a.zoom)
        cf = render(fdoc, pymupdf.Rect(sf["bbox"]) + (-7, -7, 7, 7), a.zoom)
        label = "放大对照「%s」：原图 %gpt → 成品 %gpt" % (key, round(float(so["size"]), 1), round(float(sf["size"]), 1))
        rows.append(("label", None, label))
        rows.append(("pair", (co, cf), None))
        log["zoom_pairs"].append({"key": key, "orig_size": round(float(so["size"]), 2),
                                  "final_size": round(float(sf["size"]), 2)})
        print("放大对 [%s]: %gpt -> %gpt" % (key, so["size"], sf["size"]))

    # 组图
    F_BIG, F_SM = load_font(34), load_font(26)
    H = 60
    for kind, payload, _ in rows:
        if kind == "label":
            H += 58
        elif kind == "img":
            H += int(payload.height * (W - 40) / payload.width) + 20
        elif kind == "pair":
            H += max(payload[0].height, payload[1].height) + 20
    canvas = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(canvas)
    y = 30
    for kind, payload, label in rows:
        if kind == "label":
            dr.text((20, y), label, fill=(20, 20, 20), font=F_BIG if label.startswith("①②") else F_SM)
            y += 58
        elif kind == "img":
            img = payload
            if img.width != W - 40:
                img = img.resize((W - 40, max(1, int(img.height * (W - 40) / img.width))), Image.LANCZOS)
            canvas.paste(img, (20, y))
            y += img.height + 20
        elif kind == "pair":
            ia, ib = payload
            gap = 90
            tot = ia.width + ib.width + gap
            x0 = max(20, (W - tot) // 2)
            hmax = max(ia.height, ib.height)
            canvas.paste(ia, (x0, y + (hmax - ia.height) // 2))
            canvas.paste(ib, (x0 + ia.width + gap, y + (hmax - ib.height) // 2))
            dr.line([(x0 + ia.width + gap // 2, y), (x0 + ia.width + gap // 2, y + hmax)],
                    fill=(160, 160, 160), width=2)
            y += hmax + 20

    montage = os.path.join(a.out, MONTAGE_NAME)
    canvas.save(montage)
    log["outputs"]["montage"] = montage

    stem = os.path.splitext(os.path.basename(a.final))[0]
    preview = os.path.join(a.out, stem + "_preview_300dpi.png")
    pm = fdoc[0].get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM))
    Image.frombytes("RGB", (pm.width, pm.height), pm.samples).save(preview)
    log["outputs"]["preview_300dpi"] = preview

    rep = os.path.join(a.out, REPORT_NAME)
    with open(rep, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    log["outputs"]["report"] = rep
    print("对照图:", montage)
    print("预览  :", preview)
    print("报告  :", rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())