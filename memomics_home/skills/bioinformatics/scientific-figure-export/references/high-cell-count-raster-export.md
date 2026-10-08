# High-cell-count point cloud export (≥100K points: UMAP / scatter)

For Nature-family submission of large single-cell UMAPs (e.g. 50万 = 500K cells),
vector export is NOT viable — the file explodes to hundreds of MB and InDesign/AI
choke on it. Raster PNG/TIFF is the correct choice. The file-size optimization chain
below is the complete answer to users who say "the PNG export feels too big" or "why
does scattermore look blurry but geom_point looks sharp".

## Durable facts (session-verified, 2026-09)

1. **scattermore default raster resolution is 512×512** — points get binned into 512
   cells then upscaled → visibly blurry at 300+ dpi export. THIS is the root cause of
   "scattermore looks softer than geom_point". Fix: raise to match final output pixels:
   ```r
   geom_scattermore(pixels = c(2200, 2000), interpolate = TRUE)  # current API
   # older/alternative param: resolution = 3000
   ```
   Default 512 keeps it fast but cheap; professional use must set pixels explicitly.

2. **geom_point + jitter looks clearer but it's FAKE clarity.** jitter displaces real
   UMAP/t-SNE/PCA coordinates — an image-integrity risk at Nature (editors check
   coordinate fidelity). The real clarity levers are: smaller point size (0.1-0.2),
   alpha 0.5-0.7 (not 1 — 500K points at alpha=1 saturates into a black blob), and
   output resolution. Never jitter on a coordinate plot for publication.

3. **Nature-compliant dpi is 300 — 600 is overkill.** 89mm @ 600dpi = 2102px vs
   @ 300dpi = 1051px. 300 is the hard floor for bitmaps; 600 quadruples file size
   with zero editorial benefit. Users who then complain "file is too big" usually
   set 600 — drop to 300 first, before any compression trick.

4. **PNG palette compression (pngquant) is visually lossless for category-colored
   UMAPs** (10-20 distinct colors → 256-color indexed PNG).
   `pngquant --quality=70-95 -f in.png -o out.png` turns a 5-20 MB RGBA PNG into
   <1 MB. Also: white background (no alpha channel) is ~1/3 smaller than
   transparent. Transparent is for panel compositing only; Nature guidance defaults
   to white anyway (transparent can render black in some PDF pipelines).

5. **ragg device param is `background = "transparent"`, NOT ggsave's `bg`.**
   ```r
   ragg::agg_png("out.png", width = 120, height = 100, units = "mm",
                 res = 300, background = "transparent")  # ragg API uses background=
   print(p); dev.off()
   ```
   ggsave uses `bg=`; ragg device functions use `background=`. Mixing them up
   silently fails to produce transparency.

## Recommended recipe (500K-cell UMAP, direct category colors)

```r
ggsave("MF_umap_nolegend.png", p2,
       width = 89, height = 80, units = "mm",
       dpi = 300,            # Nature floor; NOT 600
       bg = "white",         # white = no alpha = smaller file
       limitsize = FALSE)
# then: pngquant --quality=70-95 -f MF_umap_nolegend.png -o MF_umap_final.png
```

## Nature figure file contract (recap)

| item | value |
|---|---|
| single-column width | 89 mm (3.5 in) |
| double-column width | 183 mm |
| bitmap dpi | ≥300 (hard floor; 300 is standard, 600 is super-requirement) |
| file size | <10 MB (recommend ≤5 MB) |
| formats | TIFF or PNG for bitmaps; PDF/SVG for vectors |

Sizing rule of thumb: a point cloud with N points needs ≥ N×2 pixels total before
points crowd out — e.g. 500K points → ~1M px (89×80mm @ 300dpi = 1051×945 ≈ 1M px
is exactly right). If the export is much smaller than that, the plot WILL look dense
and mushy; if much larger, the file is bloated without clarity gain.