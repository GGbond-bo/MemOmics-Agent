#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Two-column journal PDF -> correct reading-order text, one file per page.

Why this exists: ``page.get_text()`` / a naive y-bucket sort SILENTLY interleaves
the two columns of a Nature/Cell/Elsevier two-column layout. The result "runs fine"
and produces paragraph pairs that are simply in the wrong order.

Method (no hard-coded page geometry, works on 595pt / 603pt / A4 widths):
  1. classify each text block as left / right / wide,
     - wide   = block width > 0.72 * page width (titles, full-width figure captions)
     - left   = block x-center < page midline
     - right  = otherwise
  2. sort each class by y0
  3. merge by vertical position: emit a wide block when it starts above both column
     heads, otherwise drain the column that starts higher (left first) up to the next
     wide block's top, then the other column.

Usage:
    python pdf_2col_extract.py "E:/path/paper.pdf" "results/<sid>/data/pdf_text2"

Then VERIFY before trusting the output (mandatory):
    open a mid-document page, e.g. head page_004.txt
    the block seam must read continuously ("...teomics on four muscles. Because leg
    muscles exhibited the strongest ..." -> resumes mid-sentence from the previous
    page = correct). Sentences that jump between unrelated topics = column mixed.
"""
import os
import sys
import json

import pymupdf  # `import fitz` is deprecated


def order_page(page):
    """Return the page's block texts in natural two-column reading order."""
    W = page.rect.width
    mid = W / 2.0
    blocks = [b for b in page.get_text("blocks") if b[4].strip()]
    left, right, wide = [], [], []
    for b in blocks:
        x0, y0, x1 = b[0], b[1], b[2]
        if (x1 - x0) > 0.72 * W:
            wide.append(b)
        elif (x0 + x1) / 2.0 < mid:
            left.append(b)
        else:
            right.append(b)
    left.sort(key=lambda b: b[1])
    right.sort(key=lambda b: b[1])
    wide.sort(key=lambda b: b[1])

    seq, li, ri, wi = [], 0, 0, 0
    while li < len(left) or ri < len(right) or wi < len(wide):
        yw = wide[wi][1] if wi < len(wide) else 1e9
        yl = left[li][1] if li < len(left) else 1e9
        yr = right[ri][1] if ri < len(right) else 1e9
        if yw <= min(yl, yr):
            seq.append(wide[wi]); wi += 1
        elif yl <= yr:
            seq.append(left[li]); li += 1
            while li < len(left) and left[li][1] < yw:
                seq.append(left[li]); li += 1
            while ri < len(right) and right[ri][1] < yw:
                seq.append(right[ri]); ri += 1
        else:
            seq.append(right[ri]); ri += 1
            while ri < len(right) and right[ri][1] < yw:
                seq.append(right[ri]); ri += 1
            while li < len(left) and left[li][1] < yw:
                seq.append(left[li]); li += 1
    return [b[4].rstrip() for b in seq]


def main(src, outdir):
    os.makedirs(outdir, exist_ok=True)
    doc = pymupdf.open(src)
    print("pages:", doc.page_count, "| title:", doc.metadata.get("title"))
    rows = []
    for i, page in enumerate(doc):
        texts = order_page(page)
        with open(os.path.join(outdir, f"page_{i+1:03d}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(texts))
        rows.append({
            "page": i + 1,
            "chars": len("\n".join(texts)),
            "images": len(page.get_images(full=True)),
            "head": texts[0][:110].replace("\n", " ") if texts else "",
        })
    with open(os.path.join(outdir, "_structure.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    # page-type split: body pages are char-dense, figure pages are thin + image-heavy
    for r in rows:
        print(f"p{r['page']:>3} chars={r['chars']:>6} img={r['images']:>2} | {r['head']}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])