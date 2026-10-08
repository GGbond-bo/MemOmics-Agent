# pheatmap sizing & 3-format export (verified 2026-09-15)

Companion to the "Narrow-body / wide-label handoff mode" section of SKILL.md.
Use when the user wants the **heatmap body narrow, row labels (GO terms) wide**, and will
hand-finish in Adobe Illustrator.

## 1. Size units — the one that breaks everything

`pheatmap(cellwidth, cellheight)` are in **points (磅)**, NOT cm.

| 目标 | 传入 |
|---|---|
| 列宽 0.39 cm | `cellwidth = 11` |
| 行高 0.46 cm | `cellheight = 13` |
| 换算 | cm × 28.35 = pt |

Symptom of getting it wrong: R exits 0, the PDF/SVG exist, but the heatmap body is a
tiny dot — PNG measures **1.4% non-background pixels / 98.6% white**.

## 2. Verified script (48 terms × 15 subclusters, labels get 53% of canvas)

```r
suppressMessages({library(pheatmap); library(grid)})
setwd("<project>/results/<sid>")

m <- as.matrix(read.csv("data/go_matrix.csv", row.names = 1, check.names = FALSE))

pal_D <- c("#FFF7EC", "#FDD49E", "#FC8D59", "#D7301F", "#7F0000")   # YlOrRd 5档 (用户定稿)
cols  <- colorRampPalette(pal_D)(100)

CW <- 11   # 列宽 pt (0.388 cm)  ← 单位是磅！
CH <- 13   # 行高 pt (0.459 cm)

# 行名区真实文字宽度 (strwidth 不支持 units="cm"，用 inches 再换算)
lab_w_cm <- (max(strwidth(rownames(m), units = "inches", cex = 8/12)) + 0.12) * 2.54
body_w   <- ncol(m) * CW / 28.35
body_h   <- nrow(m) * CH / 28.35
W_cm     <- lab_w_cm + body_w + 1.5     # 余量给 45° 列名 + 图例
H_cm     <- body_h + 3.4
cat(sprintf("label %.1fcm | body %.1fx%.1fcm | canvas %.1fx%.1fcm | lab:body=%.2f\n",
            lab_w_cm, body_w, body_h, W_cm, H_cm, lab_w_cm / body_w))

# 图例：右下角横放短条 (pheatmap 内置 legend 无法横放，关掉后手动 grid 画)
make_legend <- function() {
  pushViewport(viewport(x = unit(0.98, "npc"), y = unit(0.012, "npc"),
                        width = unit(5, "cm"), height = unit(1.5, "cm"),
                        just = c("right", "bottom")))
  grid.raster(matrix(cols, nrow = 1), x = 0.5, y = 0.62,
              width = unit(3.6, "cm"), height = unit(0.35, "cm"), interpolate = FALSE)
  grid.text("0",  x = unit(0.2, "cm"), y = unit(0.2, "cm"), gp = gpar(fontsize = 7), just = "center")
  grid.text("5",  x = unit(2.0, "cm"), y = unit(0.2, "cm"), gp = gpar(fontsize = 7), just = "center")
  grid.text("10", x = unit(3.6, "cm"), y = unit(0.2, "cm"), gp = gpar(fontsize = 7), just = "center")
  grid.text("-log10 Q", x = unit(1.9, "cm"), y = unit(1.35, "cm"),
            gp = gpar(fontsize = 8, fontface = "bold"), just = "center")
  popViewport()
}

draw <- function() pheatmap(m, color = cols,
  cluster_rows = FALSE, cluster_cols = FALSE,   # 保持作者/Excel 顺序
  display_numbers = FALSE, fontsize_row = 8, fontsize_col = 9,
  angle_col = 45, border_color = NA, legend = FALSE, main = "",
  cellwidth = CW, cellheight = CH)

Wi <- W_cm / 2.54; Hi <- H_cm / 2.54
png("figures/x.png", width = Wi, height = Hi, units = "in", res = 300); draw(); make_legend(); dev.off()
pdf("figures/x.pdf", width = Wi, height = Hi);                        draw(); make_legend(); dev.off()
svg("figures/x.svg", width = Wi, height = Hi);                        draw(); make_legend(); dev.off()  # 活文字 → Illustrator 可编辑
```

## 3. Export it from a standalone process, not the persistent kernel

Opening `png()`+`pdf()`+`svg()` inside one `execute_r` call left a **100% white PNG**
(device state carried over in the persistent kernel). Run the script as its own process:

```bash
"C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe" <script>.R
```
or from `execute_python`: `subprocess.run([rscript, script_path], capture_output=True, text=True, timeout=900)`.

## 4. Verification probe — measure, never trust exit_code

```python
from PIL import Image
import numpy as np
a = np.array(Image.open(png).convert("RGB")); H, W, _ = a.shape
flat = a.reshape(-1, 3); vals, cnt = np.unique(flat, axis=0, return_counts=True)
bg = vals[np.argmax(cnt)]
ink = (np.abs(a.astype(int) - bg.astype(int)).sum(axis=2) > 20)
print("content share %.1f%%" % (100 * ink.mean()))          # <5% = 坏图, >30% = 健康

# 热图本体宽度（奶油色零值格 vs 纯白背景）
cream = ((np.abs(a[:,:,0].astype(int)-255) < 10) &
         (np.abs(a[:,:,2].astype(int)-236) < 16) & (a[:,:,1].astype(int) > 228))
proj = cream.sum(axis=0); nz = np.where(proj > H * 0.05)[0]
bw = (nz.max() - nz.min()) / 300 * 2.54
print("body %.1f cm | cell %.2f cm" % (bw, bw / 15))
```
Measured reference values: broken v7 = 1.4% share; blank v8 = 0.0% (single colour);
healthy v9 = 47.8% share, body 7.9 cm, cell 0.53 cm, 48/48 row labels OCR'd at conf 0.96–1.0.

## 5. Why OCR alone is not enough

`vision_describe` OCR of a healthy render returned **62 text items**, all 48 GO term labels
at confidence ≥0.96 — that is the check that the row labels actually rendered. But OCR
cannot tell you the *body is a dot* (v7 had 4 OCR hits and still looked "fine"), so always
pair OCR with the numeric content-share/body-width probe above.
