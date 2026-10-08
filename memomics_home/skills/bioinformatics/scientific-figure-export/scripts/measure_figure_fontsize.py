#!/usr/bin/env python3
"""
Measure the EFFECTIVE font size (pt) of text in an already-rendered figure.

    check_fontsize.py (academic-figure-skill)  audits sizes DECLARED IN SOURCE.
    measure_figure_fontsize.py                 audits PIXELS.

Use this one when there is no source to grep:
  * a figure lifted from a published paper (you only have the PNG/TIFF)
  * verifying YOUR OWN export actually landed at the intended size
    (a figure authored at 7pt then scaled to 89mm column width is NOT 7pt)

Everything hinges on the scale factor (pt per pixel), which comes from the
figure's TRUE PRINTED WIDTH - never from the file's nominal dpi tag:

  --from-pdf PUBLISHER.pdf   auto-recover width from the publisher PDF (exact)
  --width-mm 183             you know the print width (89 / 183 mm for Nature)
  --dpi 300                  you know the raster dpi

Examples
  python measure_figure_fontsize.py fig2.png --from-pdf article.pdf
  python measure_figure_fontsize.py fig2.png --width-mm 183
  python measure_figure_fontsize.py fig1.tiff --dpi 600

Reading the output
  Ink heights are not font sizes. Arial/Helvetica: cap/digit height = 0.716 em,
  lowercase x-height = 0.519 em, so font_pt = ink_px * pt_per_px / ratio.
  The script prints BOTH readings. Pick the one matching the text you care
  about: all-caps labels & tick digits -> cap reading; lowercase body -> x reading.
  A single figure legitimately contains two or three distinct sizes.

Deps: numpy, Pillow, scipy (ndimage). PyMuPDF (fitz) only for --from-pdf.
"""
import argparse
import sys

import numpy as np

# Arial / Helvetica vertical metrics, as a fraction of the em (= font size)
CAP_RATIO = 0.716     # capital letters and digits
X_RATIO = 0.519       # lowercase x-height
MIN_PT = 5.0          # Nature / Cell / Science floor at final print size

INK_LEVEL = 200       # gray value below which a pixel counts as ink


# --------------------------------------------------------------------------
# scale
# --------------------------------------------------------------------------
def scale_from_pdf(pdf_path, img_w_px, img_h_px):
    """Find the embedded image in the PDF whose aspect ratio matches our raster
    and whose displayed rect is largest; return (pt_per_px, display_mm, dpi, page).

    The displayed rect is the ground truth for print size - the embedded pixel
    count is NOT (publishers re-export figures at arbitrary resolutions)."""
    import fitz

    target = img_w_px / img_h_px
    doc = fitz.open(pdf_path)
    best = None
    for pno, page in enumerate(doc):
        for im in page.get_images(full=True):
            w, h = im[2], im[3]
            if w < 800:                       # skip logos, rules, inline glyphs
                continue
            if abs((w / h) - target) > 0.02:  # not the same figure
                continue
            for rect in page.get_image_rects(im[0]):
                if rect.width < 200:
                    continue
                cand = (rect.width / img_w_px, rect.width, pno, w)
                if best is None or w > best[3]:
                    best = cand
    doc.close()
    if best is None:
        return None
    ppp, disp_pt, pno, _ = best
    return ppp, disp_pt / 72 * 25.4, 72 / ppp, pno


# --------------------------------------------------------------------------
# ink measurement
# --------------------------------------------------------------------------
def glyph_heights(gray):
    """One height per connected ink blob that looks like a text glyph."""
    from scipy import ndimage

    ink = gray < INK_LEVEL
    labeled, _ = ndimage.label(ink)
    out = []
    for sl in ndimage.find_objects(labeled):
        if sl is None:
            continue
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        if not (2 <= h <= 60 and 2 <= w <= 80):
            continue
        area = int(ink[sl].sum())
        if area < 8 or not (0.1 <= w / h <= 5.0):
            continue
        out.append(h)
    return np.asarray(out)


def line_ink_heights(gray, tile=256, min_frac=0.06):
    """Ink height of each text LINE, via row projection inside tiles.

    Independent of the connected-component method above - the two agreeing is
    the sanity check that neither is dominated by antialiasing artefacts."""
    ink = gray < INK_LEVEL
    h_img, w_img = ink.shape
    runs = []
    for y0 in range(0, max(h_img - tile, 1), tile):
        for x0 in range(0, max(w_img - tile, 1), tile):
            rows = ink[y0:y0 + tile, x0:x0 + tile].sum(1)
            on = rows > min_frac * tile
            i = 0
            while i < len(on):
                if on[i]:
                    j = i
                    while j < len(on) and on[j]:
                        j += 1
                    if 4 <= (j - i) <= 30:
                        runs.append(j - i)
                    i = j
                else:
                    i += 1
    return np.asarray(runs)


def _mode(arr):
    vals, counts = np.unique(arr, return_counts=True)
    return float(vals[counts.argmax()])


def _summary(label, arr):
    if arr.size == 0:
        return f"  {label:<14s} (none found)"
    return (f"  {label:<14s} n={arr.size:<5d} p10={np.percentile(arr,10):4.0f}  "
            f"mode={_mode(arr):4.0f}  p50={np.percentile(arr,50):4.0f}  "
            f"p90={np.percentile(arr,90):4.0f}  p98={np.percentile(arr,98):4.0f}  px")


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="rendered figure (PNG / TIFF / JPEG)")
    ap.add_argument("--from-pdf", help="publisher PDF, to recover true print width")
    ap.add_argument("--width-mm", type=float, help="known print width in mm")
    ap.add_argument("--dpi", type=float, help="known raster dpi")
    args = ap.parse_args()

    from PIL import Image

    img = Image.open(args.image)
    img_w, img_h = img.size
    gray = np.asarray(img.convert("L"), dtype=np.int16)

    if args.from_pdf:
        got = scale_from_pdf(args.from_pdf, img_w, img_h)
        if got is None:
            print("!! no aspect-matching image found in that PDF "
                  "- pass --width-mm or --dpi instead")
            return 2
        ppp, disp_mm, dpi, pno = got
        src = f"publisher PDF (page {pno + 1})"
    elif args.width_mm:
        disp_mm = args.width_mm
        dpi = img_w / (args.width_mm / 25.4)
        ppp = 72.0 / dpi
        src = "supplied print width"
    elif args.dpi:
        dpi = args.dpi
        ppp = 72.0 / dpi
        disp_mm = img_w / args.dpi * 25.4
        src = "supplied dpi"
    else:
        print("!! need one of --from-pdf / --width-mm / --dpi")
        return 2

    print("\n" + "=" * 68)
    print(f"  raster        : {img_w} x {img_h} px   ({args.image})")
    print(f"  scale from    : {src}")
    print(f"  PRINT WIDTH   : {disp_mm:.1f} mm  ->  {dpi:.0f} dpi  "
          f"->  1 px = {ppp:.4f} pt")
    print("=" * 68)

    hs = glyph_heights(gray)
    runs = line_ink_heights(gray)
    print("\nobserved INK heights (not font sizes):")
    print(_summary("glyph blobs", hs))
    print(_summary("text lines", runs))

    if hs.size == 0:
        print("\n!! no text-like ink found - is this figure blank or vector-only?")
        return 1

    tiers = sorted({round(float(np.percentile(hs, q))) for q in (15, 50, 90, 98)})
    print("\nimplied FONT SIZE (pt) at final print size:")
    print(f"  {'ink px':>7} {'cap-height reading':>20} {'x-height reading':>19}")
    print(f"  {'':>7} {'(caps/digits)':>20} {'(lowercase)':>19}")
    for h in tiers:
        print(f"  {h:7.0f} {h * ppp / CAP_RATIO:20.1f} {h * ppp / X_RATIO:19.1f}")

    lo_cap = tiers[0] * ppp / CAP_RATIO
    hi_cap = tiers[-1] * ppp / CAP_RATIO
    lo_x = tiers[0] * ppp / X_RATIO
    hi_x = tiers[-1] * ppp / X_RATIO
    print(f"\n  smallest text ~ {lo_cap:.1f}-{lo_x:.1f} pt"
          f"   |   largest common text ~ {hi_cap:.1f}-{hi_x:.1f} pt")
    print(f"  (+/-1 px antialiasing jitter = +/-{ppp / CAP_RATIO:.2f} pt)")

    print(f"\nfloor check: journal minimum is {MIN_PT:g} pt at final size")
    if lo_cap < MIN_PT:
        print(f"  -> smallest tier may sit AT or BELOW the floor "
              f"({lo_cap:.1f} pt cap reading)")
    else:
        print("  -> all tiers clear the floor")
    print("\nNote: a raster figure carries NO font objects. These are measured ink\n"
          "heights. 'Editable text' is impossible in a bitmap no matter the size -\n"
          "below ~8 px of ink height it is also not economically retouchable.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
