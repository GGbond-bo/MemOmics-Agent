#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Crop every journal figure by anchoring on its caption, and WARN where the anchor is missing.

Rule: the caption block ("Figure 3. ...", "Figure S1: ...", "Fig. 4 | ...") sits BELOW
the artwork. So the figure region = page top margin -> caption top, full text width.
Do NOT use embedded-image bboxes: vector figures shatter into dozens of fragment blocks.

Caption prefix varies by publisher -- match all of them, or you silently lose anchors:
    Cell/Elsevier : "Figure 1."   "Figure S1:"   (period OR colon)
    Nature        : "Fig. 1 |"    "Extended Data Fig. 3 |"
    generic       : "Table 1."    "Supplementary Figure 2:"

Pitfall this script exists to catch: supplemental captions often start on the page
AFTER the artwork (multi-panel captions overflow). With a too-narrow regex those pages
fall back to the H-bottom guess, and the crop can swallow caption prose or clip the
figure. The per-page report prints captionsplit=True/False -- ALWAYS re-crop the False
ones by looking up the caption on the next page.

Usage:
    python crop_figures_by_caption.py "E:/path/paper.pdf" "results/<sid>/figures/atlas_figures"
    python crop_figures_by_caption.py paper.pdf out/ --dpi 300 --top 55 --discover
"""
import os
import re
import sys
import argparse

import pymupdf

CAP = re.compile(r"^(?:Supplementary\s+)?(?:Extended\s+Data\s+)?(?:Figure|Fig\.?|Table)\s+S?\d+\s*[:.|]", re.I)


def find_caption(page):
    """Return (label, caption_top_y) for the page's own caption block, or (None, None)."""
    for b in page.get_text("blocks"):
        t = b[4].strip()
        if CAP.match(t):
            label = re.match(r"^.*?S?\d+", t).group(0)
            label = re.sub(r"[^A-Za-z0-9]", "", label)  # "Figure S1" -> "FigureS1"
            return label, b[1]
    return None, None


def crop_all(src, outdir, dpi=300, top=55.0, discover=False, pages=None):
    os.makedirs(outdir, exist_ok=True)
    doc = pymupdf.open(src)
    todo = pages or (range(1, doc.page_count + 1) if discover else [])
    written = []
    for pno in todo:
        page = doc[pno - 1]
        label, cap_y = find_caption(page)
        if label is None and not discover:
            print(f"p{pno:<3} SKIP  no caption on page")
            continue
        if label is None:                       # discover mode: art-only page (thin text, has image)
            if len(page.get_text().strip()) > 800 or not page.get_images(full=True):
                continue
            label = f"fig_p{pno}"
        W, H = page.rect.width, page.rect.height
        anchor = "caption" if cap_y else "FALLBACK"     # FALLBACK = verify by eye / look on next page
        bottom = (cap_y - 4) if cap_y else (H - 120)
        rect = pymupdf.Rect(40, top, W - 40, bottom)
        out = os.path.join(outdir, f"{label}_p{pno}.png")
        page.get_pixmap(clip=rect, dpi=dpi).save(out)
        written.append(out)
        print(f"{label:<12} p{pno:<3} h={bottom-top:>6.1f}pt anchor={anchor:<9} "
              f"bytes={os.path.getsize(out):>10,}")
    print(f"total={len(written)}  ->  {outdir}")
    print("NEXT: inspect any anchor=FALLBACK crop (vision_describe) - expect only in-figure "
          "labels/axis text, no sentence-like prose; reclip or fetch the caption from p+1 if wrong.")
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("outdir")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--top", type=float, default=55.0)
    ap.add_argument("--discover", action="store_true",
                    help="scan every page instead of a supplied page->label map")
    ap.add_argument("--pages", type=str, default="",
                    help="comma-separated 1-based page numbers, e.g. 3,6,8,10,13,16,17")
    a = ap.parse_args()
    pgs = [int(x) for x in a.pages.split(",") if x.strip()] if a.pages else None
    if not pgs and not a.discover:
        sys.exit("pass --pages 3,6,8 or --discover (see docstring for pitfalls)")
    crop_all(a.pdf, a.outdir, dpi=a.dpi, top=a.top, discover=a.discover, pages=pgs)