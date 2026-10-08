
# =============================================================================
# CNS-level curated GO-term heatmap — pheatmap + Illustrator-handoff layout
# Verified 2026-09-15 (v11 final: YlOrRd, wide canvas, gtable padding margin,
#                         words-only rows, bottom-right horizontal legend)
#
# Runs as an INDEPENDENT Rscript process (NOT inside execute_r — the persistent
# kernel's device state leaks and yields a 100% white PNG when png+pdf+svg are
# opened in one call):
#   "C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe" this_script.R
#
# INPUT  : data/<x>.csv  — first column = row names (GO term), header row = clusters,
#                          cells = abs(-log10 q) clipped to 0-10, 0 = term absent.
#          Build it with references/term-selection-worksheet.md's recipe.
# OUTPUT : figures/<tag>.{png,pdf,svg}   (svg text is OUTLINED by R's svg() device —
#          switch to svglite::svglite() if the user needs editable text objects)
# =============================================================================

suppressMessages({library(pheatmap); library(grid); library(gtable)})
setwd("E:/MemOmics-Agent/results/<session_dir>")           # <-- edit

m <- as.matrix(read.csv("data/<matrix>.csv", row.names = 1, check.names = FALSE))
cat("dim:", dim(m), "\n")                                  # sanity: rows x cols

# ---- YlOrRd sequential palette (user-accepted 2026-09-08) -------------------
# -log10(q) is SEQUENTIAL data -> sequential colormap. NEVER a diverging one.
# Low end is warm off-white (#FFF7EC), never pure white.
pal_D <- c("#FFF7EC", "#FDD49E", "#FC8D59", "#D7301F", "#7F0000")
cols  <- colorRampPalette(pal_D)(100)

# ---- hand-rolled horizontal legend, bottom-right (pheatmap's own legend is off)
make_legend <- function(){
  pushViewport(viewport(x = unit(0.98, "npc"), y = unit(0.012, "npc"),
                        width = unit(5, "cm"), height = unit(1.5, "cm"),
                        just = c("right", "bottom")))
  grid.raster(matrix(cols, nrow = 1), x = 0.5, y = 0.62,
              width = unit(3.6, "cm"), height = unit(0.35, "cm"),
              interpolate = FALSE)
  grid.text("0",  x = unit(0.2, "cm"), y = unit(0.2, "cm"), gp = gpar(fontsize = 7), just = "center")
  grid.text("5",  x = unit(2.0, "cm"), y = unit(0.2, "cm"), gp = gpar(fontsize = 7), just = "center")
  grid.text("10", x = unit(3.6, "cm"), y = unit(0.2, "cm"), gp = gpar(fontsize = 7), just = "center")
  grid.text("-log10 Q", x = unit(1.9, "cm"), y = unit(1.35, "cm"),
            gp = gpar(fontsize = 8, fontface = "bold"), just = "center")
  popViewport()
}

# ---- draw: silent=TRUE -> grab gtable -> add padding for real margins --------
# gtable_add_padding order = c(top, right, bottom, left).
# LEFT gets the most: 45-degree long column labels (e.g. "Pure Type IIA") extend
# up-and-left past the heatmap body and were being clipped at the canvas edge.
draw <- function(){
  p  <- pheatmap(m, color = cols,
                 cluster_rows = FALSE, cluster_cols = FALSE,   # keep author's order
                 display_numbers = FALSE,
                 fontsize_row = 8, fontsize_col = 9, angle_col = 45,
                 border_color = NA,
                 legend = FALSE, main = "",
                 silent = TRUE)
  gt <- gtable_add_padding(p$gtable, unit(c(0.5, 0.9, 0.35, 1.8), "cm"))
  grid.newpage(); grid.draw(gt)
  make_legend()
}

# ---- 3-format export (canvas >= 10.5in wide: 45-deg labels need the room) ----
Wi <- 10.5; Hi <- 11.5
png("figures/<tag>.png", width = Wi, height = Hi, units = "in", res = 300); draw(); dev.off()
pdf("figures/<tag>.pdf", width = Wi, height = Hi);                          draw(); dev.off()
svg("figures/<tag>.svg", width = Wi, height = Hi);                          draw(); dev.off()
cat("done", Wi, "x", Hi, "in\n")

# ---- POST-RENDER CHECK (do exactly these 3, then stop) ----------------------
# 1) all three files non-zero size
# 2) non-background share > 30%  (a healthy render; <5% == broken/blank)
# 3) column-label zone (top 25%) has NO non-white pixel touching the left edge
#
#   import numpy as np; from PIL import Image
#   a  = np.array(Image.open(png).convert("RGB")); H, W, _ = a.shape
#   nb = (a < 245).any(axis=2)
#   print((nb != np.array(Image.open(png).convert("RGB"))[0,0]).mean())   # (2)
#   strip = nb[:, :15]                                                    # (3)
#   print("label-zone left hits:", strip[:int(H*0.25)].sum())             # want 0
# NOTE: stray non-white pixels at the very BOTTOM-left are the bottom-right
# legend's tick text, not clipped labels — do not misread them as truncation.
