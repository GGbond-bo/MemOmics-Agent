# Legibility Audit of an Already-Rendered Figure

**When to use.** The figure exists only as pixels — a figure lifted from a
published paper, or your own export whose on-page size you need to verify.

- Source code available → `academic-figure-skill/scripts/check_fontsize.py`
  (greps declared sizes; exact).
- Only pixels available → `scripts/measure_figure_fontsize.py` (this doc).

Run the script; this file explains the arithmetic so you can sanity-check its
output and report the uncertainty honestly instead of quoting a false precision.

---

## Why the file's own dpi tag is not evidence

A PNG has no reliable physical size. "300 dpi" in an image header — or a
converter that assumed 300 dpi — tells you nothing about how the publisher
actually placed the figure on the page. Two rasters of the same figure exported
at different resolutions both "are 300 dpi" under that convention.

**The only ground truth is the displayed rectangle in the publisher's own PDF.**
Recover it, don't assume it:

```python
import fitz                       # PyMuPDF; rect units are PDF POINTS
doc = fitz.open("publisher.pdf")
for pno, page in enumerate(doc):
    for im in page.get_images(full=True):
        w, h = im[2], im[3]
        if w < 800:
            continue
        if abs(w / h - our_px_w / our_px_h) > 0.02:   # match OUR raster's aspect
            continue
        for rect in page.get_image_rects(im[0]):
            print(pno, w, h, rect.width, rect.width / 72 * 25.4, "mm")
```

Do **not** use embedded-px ÷ displayed-px for anything except *recognising* the
figure — the publisher may re-export at a different resolution than the file you
hold. What you need is the display width applied to *your* raster:

```
dpi       = img_w_px / (display_mm / 25.4)
pt_per_px = 72 / dpi          ==  display_pt / img_w_px
```

### Getting that PDF

PMC's own PDF endpoint sits behind a reCAPTCHA (returns an HTML challenge page
with `HTTP 200` — size is your tell, ~20 KB of HTML, not a PDF) and Europe PMC's
`?pdf=render` returns 403 for this route. For **open-access** articles the
publisher's own PDF is the reliable source:

```
https://www.nature.com/articles/<doi-suffix>.pdf     # e.g. s43018-025-01072-4
```

Send a browser User-Agent + a matching `Referer`. For non-OA articles there is no
free PDF — say so rather than burning calls on other mirrors.

## Ink height → font size

What you measure is ink, not em. For Arial/Helvetica (what these journals
require):

| Metric | Fraction of em | Notes |
|---|---|---|
| Cap height | **0.716** | capitals AND digits — the cleanest target |
| x-height | **0.519** | lowercase body |
| Ascender + descender | ~1.117 | full ink of a mixed-case line with descenders |

```
font_pt = ink_px * pt_per_px / ratio
```

All-caps labels (`CD3D`, `UMAP 1`) and axis tick digits give cap height directly
— prefer these. Lowercase words mix x-height and cap-height blobs, which is why
the histogram has several peaks: a real figure contains two or three distinct
sizes and they appear as separate modes.

**Cross-check with two independent methods** (connected components, and tiled
row-projection of text lines). If their modal values disagree by more than a
pixel the segmentation is being dominated by antialiasing — widen the ink
threshold or read a lower percentile.

## Worked example (verified in session, 2026-09)

Nature Cancer 2026, MM bone-marrow single-cell atlas, Figure 2.

| Step | Value |
|---|---|
| Raster | 2163 × 2698 px PNG (publisher `MediaObjects/..._Fig2_HTML.png`) |
| Displayed in publisher PDF | 181.8 mm wide |
| Scale | 302 dpi → 1 px = 0.238 pt |
| Modal glyph ink | 14 px (n=456); secondary mode 11 px |
| Text-line ink | mode 14 px, median 11 px |
| Largest common glyph | 17–20 px |

Interpretations:

- 14 px as **cap height** → 14 × 0.238 / 0.716 = **4.7 pt**
- 11 px as **x-height** → 11 × 0.238 / 0.519 = **5.1 pt**
- 20 px as **cap height** → 20 × 0.238 / 0.716 = **6.6 pt**

Two independent readings converge on the same picture: **main labels ≈ 6–7 pt,
smallest tick text ≈ 5 pt** — i.e. sitting right on Nature's floor. Report it as
a range (±1 px jitter = ±0.33 pt on the cap reading), never as a single decimal.

Note the 2163 px ≈ 183 mm @ 300 dpi coincidence: a figure exported at exactly
300 dpi for double-column width is common, which is why the naive "assume 300
dpi" guess often lands near the right answer — near, not exact. Measure anyway.

## Reporting it

Give the number, the chain that produced it, and the error bar. Shape that works:
scale source → measured ink → both readings → range → verdict vs floor. Keep it
tight; a measurement question deserves the number and its provenance, not a long
report.

Also state the consequence the user is usually actually asking about: **a raster
figure carries no font objects**, so "I can't change the font in Illustrator" is
not a broken-file problem. Publisher `MediaObjects` figures are raster; when only
PNG is served (the `.jpg` variant commonly 404s) there is no vector master to
obtain, and at ~14–20 px of ink height the text is not practically retouchable
either. Editable text means rebuilding the figure from the source data.

## Related files

- `scripts/measure_figure_fontsize.py` — the measurement tool
- `references/matplotlib-canvas-and-font-pitfalls.md` — the other half of
  export QA: canvas overflow, missing glyphs, post-render verification
- `academic-figure-skill` — `scripts/check_fontsize.py` (source-code audit),
  `references/journal-specs.md` (column widths, 5 pt minimum)
