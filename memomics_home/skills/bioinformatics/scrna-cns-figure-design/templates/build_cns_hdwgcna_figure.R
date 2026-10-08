#!/usr/bin/env Rscript
# ============================================================================
# CNS-level hdWGCNA figure builder (v2) — reusable template
# 8-panel publication figure for an hdWGCNA module-trait analysis.
# Panels: a softpower | b dendrogram | c module×effect HERO heatmap
#         d GO | e KEGG | f hub lollipop | g module-gene DotPlot (+color strip)
#         + conclusion strip
# Export: SVG (editable) + PDF (TrueType) + TIFF (600dpi) + PNG (300dpi)
#         + source-data CSVs (投稿必需)
# Run:    "/c/Program Files/R/R-4.5.3/bin/x64/Rscript" --vanilla <this file>
#
# ⚠️ Windows Seurat figure scripts MUST bootstrap the library path first
#    (PATH Rscript may be a fresh install with no Seurat; --vanilla does not
#     read user libraries). Verified working combo 2026-08-04:
#     R-4.5.3 binary + E:/R-libs/R-4.5.3 → Seurat v5.5.1 + ComplexHeatmap +
#     circlize + gridExtra + ggplot2 + png all load.
# ⚠️ Write this script into an ASCII working dir (NOT /tmp — MSYS path
#    segfaults Rscript exit 139). Edit with patch tool, never sed.
# ============================================================================

# ------------------------- 0.5 LIB PATHS (Windows 必需) -------------------------
.libPaths(c("E:/R-libs/R-4.5.3", .libPaths()))   # 与用户环境匹配的 Seurat 库

# ------------------------- 0. CONFIG (按需修改) -------------------------
BASE   <- "E:/MemOmics-Agent/results/memomics-2f229850/hdwgcna"          # hdWGCNA 输出目录
SEURAT <- "E:/骨骼肌锻炼/MF_subset_2000.rds"                              # 原始 Seurat 对象 (含 type/samplename/annotation_L3)
FIG    <- file.path(BASE, "figures", "CNS_v2")
dir.create(FIG, showWarnings = FALSE, recursive = TRUE)

FONT <- "sans"            # Windows 下映射 Arial; 别写裸 "Arial" 会报字体类别出错
mods_show <- c("red", "magenta", "brown", "turquoise", "blue", "purple")  # 主图展示的模块
top_genes_per_module <- 6 # DotPlot 每个模块取 top-k hub 基因

# ------------------------- 1. PACKAGES -------------------------
suppressPackageStartupMessages({
  library(ComplexHeatmap)
  library(circlize)
  library(grid)
  library(gridExtra)
  library(ggplot2)
  library(png)
  library(Seurat)
})

# ------------------------- 2. UNIFIED THEME -------------------------
theme_cns <- theme_classic(base_size = 7) +
  theme(axis.text = element_text(color = "black", family = FONT),
        axis.ticks = element_line(color = "black", linewidth = 0.4),
        axis.line = element_line(color = "black", linewidth = 0.4),
        plot.title = element_text(size = 7, face = "bold", hjust = 0, family = FONT),
        legend.text = element_text(size = 6, family = FONT),
        legend.title = element_text(size = 6.5, family = FONT),
        plot.margin = margin(4, 4, 2, 2))

mod_cols <- c(blue="#1F77B4", red="#D62728", brown="#8C564B", turquoise="#2CA02C",
              pink="#FF69B4", black="#333333", yellow="#D4B106", green="#228B22",
              magenta="#CC00CC", purple="#7B2FBE")

# ------------------------- 3. LOAD DATA -------------------------
tc <- read.csv(file.path(BASE, "data/official_module_trait_cor.csv"), check.names = FALSE, row.names = 1)
tp <- read.csv(file.path(BASE, "data/official_module_trait_p.csv"),  check.names = FALSE, row.names = 1)
st <- read.csv(file.path(BASE, "data/official_softpower_table.csv"))
hub <- read.csv(file.path(BASE, "data/official_hub_genes.csv"))
gokegg <- readRDS(file.path(BASE, "data/official_module_go_kegg.rds"))

effects <- c("Aging", "T2D", "ExYoung", "ExOld", "ExT2D")
mods <- c("blue","red","brown","turquoise","pink","black","yellow","green","magenta","purple")

# ============================================================================
# Panel a: soft power (自动取最优 power 标注)
# ============================================================================
best <- st[which.max(st$SFT.R.sq), ]
pa <- ggplot(st, aes(x = Power, y = SFT.R.sq)) +
  geom_hline(yintercept = 0.8, linetype = "dashed", color = "grey50", linewidth = 0.3) +
  geom_line(color = "#B2182B", linewidth = 0.6) +
  geom_point(shape = 21, size = 2, stroke = 0.3,
             fill = ifelse(st$SFT.R.sq >= 0.8, "#B2182B", "white")) +
  annotate("text", x = best$Power + 1.5, y = best$SFT.R.sq,
           label = sprintf("R² = %.2f (power=%d)", best$SFT.R.sq, best$Power),
           size = 2.2, family = FONT) +
  coord_cartesian(xlim = c(1, 20), ylim = c(0, 1.02)) +
  labs(x = "Soft power", y = "Scale-free fit (R²)", title = "a") + theme_cns

# ============================================================================
# Panel b: dendrogram (官方图嵌入; 若要纯矢量可换 PlotDendrogram 重绘)
# ============================================================================
den_png <- file.path(BASE, "figures", "official_02_dendrogram.png")
if (file.exists(den_png)) {
  pb <- rasterGrob(readPNG(den_png), interpolate = TRUE)
} else {
  pb <- textGrob("dendrogram (missing PNG)", gp = gpar(fontsize = 7, fontfamily = FONT))
}

# ============================================================================
# Panel c: module × effect 热图 (HERO, 全宽)
# ============================================================================
mcor <- as.matrix(tc[, paste0("all_cells.", mods)])
mp   <- as.matrix(tp[, paste0("all_cells.", mods)])
ord <- order(mcor["Aging", ])              # 模块按 Aging 效应排序
mcor <- mcor[, ord]; mp <- mp[, ord]
lab <- ifelse(mp < 0.001, "***", ifelse(mp < 0.01, "**", ifelse(mp < 0.05, "*", "")))
col_fun <- colorRamp2(c(-0.35, 0, 0.35), c("#2166AC", "white", "#B2182B"))

ht <- Heatmap(t(mcor), name = "cor",
  col = col_fun,
  cluster_rows = FALSE, cluster_columns = FALSE,
  rect_gp = gpar(col = "white", lwd = 0.8),
  cell_fun = function(j, i, x, y, w, h, fill) {
    grid.rect(x, y, w, h, gp = gpar(fill = fill, col = "white", lwd = 0.8))
    grid.text(lab[j, i], x, y,
              gp = gpar(fontsize = 5, fontface = "bold",
                        col = ifelse(abs(mcor[j,i]) > 0.25, "white", "black")))
  },
  row_names_gp = gpar(fontsize = 6, fontfamily = FONT),
  column_names_gp = gpar(fontsize = 6, fontfamily = FONT),
  column_names_rot = 45,
  heatmap_legend_param = list(title = "cor",
                              title_gp = gpar(fontsize = 6, fontfamily = FONT),
                              labels_gp = gpar(fontsize = 6, fontfamily = FONT),
                              grid_width = unit(3, "mm"), grid_height = unit(3, "mm")),
  show_column_names = TRUE, show_row_names = TRUE)
pc <- grid.grabExpr(draw(ht, heatmap_legend_side = "right",
                         column_title = "c  Module × five effects (all cells)",
                         column_title_gp = gpar(fontsize = 8, fontfamily = FONT, fontface = "bold"),
                         column_title_side = "top"))

# ============================================================================
# Panel d/e: GO & KEGG bubble (red module — 最强机制证据)
# ============================================================================
get_terms <- function(er, n = 8) {
  if (is.null(er) || nrow(as.data.frame(er)) == 0) return(NULL)
  df <- as.data.frame(er)
  df$Description <- sub(" -.*$", "", df$Description)
  df$logp <- -log10(df$p.adjust)
  df <- df[order(df$p.adjust), ]
  if (nrow(df) > n) df <- df[1:n, ]
  df$Description <- factor(df$Description, levels = rev(df$Description))
  df
}
plot_bubble <- function(df, title) {
  if (is.null(df)) return(ggplot() + theme_void() + ggtitle(title))
  df$GeneRatio_n <- sapply(strsplit(as.character(df$GeneRatio), "/"),
                           function(v) as.numeric(v[1]) / as.numeric(v[2]))
  ggplot(df, aes(x = GeneRatio_n, y = Description)) +
    geom_point(aes(size = Count, color = logp)) +
    scale_color_gradient(low = "#2166AC", high = "#B2182B", name = "-log10(q)") +
    scale_size_continuous(range = c(1.2, 3.2), name = "Count") +
    labs(x = "Gene ratio", y = NULL, title = title) + theme_cns +
    theme(axis.text.y = element_text(size = 5.2, family = FONT),
          legend.key.size = unit(3, "mm"))
}
pd <- plot_bubble(get_terms(gokegg[["red"]]$go),   "d  GO (red)")
pe <- plot_bubble(get_terms(gokegg[["red"]]$kegg), "e  KEGG (red)")

# ============================================================================
# Panel f: hub 基因 (red 模块, lollipop 按 kME)
# ============================================================================
hub_red <- hub[hub$module == "red", ]
hub_top <- head(hub_red[order(hub_red$kME, decreasing = TRUE), ], 10)
hub_top <- hub_top[order(hub_top$kME), ]
pf <- ggplot(hub_top, aes(x = kME, y = reorder(gene_name, kME))) +
  geom_segment(aes(xend = min(kME) * 0.96, yend = reorder(gene_name, kME)),
               color = "grey75", linewidth = 0.4) +
  geom_point(aes(size = kME), color = "#B2182B", alpha = 0.85) +
  scale_size_continuous(range = c(1.5, 4), guide = "none") +
  labs(x = "kME", y = NULL, title = "f  hub genes (red)") + theme_cns +
  theme(axis.text.y = element_text(size = 5.2, family = FONT))

# ============================================================================
# Panel g: 模块基因 DotPlot (★ 用户指定面板)
#   基础: DotPlot(seurat_obj, features=mods, group.by='type') + RotatedAxis() +
#         scale_color_gradient2(high='red', mid='grey95', low='blue')
#   CNS 升级: ① 基因按模块分组排序  ② 左侧加模块色条  ③ 统一配色到 figure 主题
# ============================================================================
seurat_obj <- readRDS(SEURAT)
genes_per_mod <- lapply(mods_show, function(m) {
  g <- hub[hub$module == m, ]
  g <- g[order(g$kME, decreasing = TRUE), "gene_name"]
  head(g, top_genes_per_module)
})
names(genes_per_mod) <- mods_show
mods_feat <- unlist(genes_per_mod)          # 按模块分组的有序基因向量
mods_lab  <- rep(mods_show, sapply(genes_per_mod, length))

gdot <- DotPlot(seurat_obj, features = mods_feat, group.by = "type") +
  RotatedAxis() +
  scale_color_gradient2(high = "#D7263D", mid = "#F5F5F5", low = "#1B3A6B",
                        midpoint = 0, name = "Avg exp\n(scaled)") +   # ← CNS 配色; 想用原配色改回 high='red', mid='grey95', low='blue'
  theme_cns +
  theme(axis.text.x = element_text(angle = 45, hjust = 1, size = 5.2, family = FONT),
        axis.text.y = element_text(size = 4.5, family = FONT),
        legend.key.size = unit(3, "mm"))

# 左侧模块色条 (标注基因归属)
strip_df <- data.frame(gene = factor(mods_feat, levels = mods_feat),
                       mod = factor(mods_lab, levels = mods_show))
gstrip <- ggplot(strip_df, aes(x = 1, y = gene, fill = mod)) +
  geom_tile(width = 0.8, height = 0.9) +
  scale_fill_manual(values = mod_cols, guide = "none") +
  theme_void() +
  theme(plot.margin = margin(0, 0, 0, 0))

pg2 <- grid.grabExpr(grid.arrange(
  grobs = list(ggplotGrob(gstrip), ggplotGrob(gdot)),
  ncol = 2, widths = c(0.035, 1),
  top = textGrob("g  Module hub genes by condition (type)",
                 gp = gpar(fontsize = 8, fontfamily = FONT, fontface = "bold"), hjust = 0)))

# ============================================================================
# 结论条 (3-5 句: 生物学结论 + 统计提醒)
# ============================================================================
concl <- c(
  "red module: aging & T2D suppress (r=-0.26/-0.25), young exercise restores (+0.27), old exercise fails (-0.23)",
  "KEGG: insulin signalling / AMPK — exercise-reversible metabolic programme",
  "purple & magenta: T2D-specific modules (r=+0.25/+0.20), refractory to exercise in T2D",
  "n = 6,524 metacells (10 subtypes x 6 groups); p-values are metacell-level, individual-level validation required"
)
concl_grob <- textGrob(paste(concl, collapse = "\n"),
                       x = unit(0.02, "npc"), y = unit(0.5, "npc"), just = "left",
                       gp = gpar(fontsize = 6.5, fontfamily = FONT, lineheight = 1.3))

# ============================================================================
# ASSEMBLE (不对称布局: hero 热图全宽)
# ============================================================================
gl <- list(
  ggplotGrob(pa), pb, pc, ggplotGrob(pd), ggplotGrob(pe), ggplotGrob(pf), pg2, concl_grob
)
lay <- rbind(c(1, 2),          # a softpower | b dendrogram
             c(3, 3),          # c HERO 热图 (全宽)
             c(4, 5),          # d GO | e KEGG
             c(6, 6),          # f hub
             c(7, 7),          # g DotPlot (全宽)
             c(8, 8))          # 结论条
hts <- c(0.55, 1.0, 0.8, 0.45, 1.2, 0.45)

cat("Assembling figure...\n")
g <- grid.grabExpr(grid.arrange(grobs = gl, layout_matrix = lay,
                                widths = c(1, 1), heights = hts))

# ============================================================================
# EXPORT: SVG + PDF + TIFF + PNG + source data
# ============================================================================
cat("Exporting...\n")
W <- 183; H <- 250   # mm (Nature 单栏宽)

# SVG (可编辑)
svg(file.path(FIG, "Fig_hdwgcna_CNS_v2.svg"), width = W/25.4, height = H/25.4)
grid.draw(g); dev.off()

# PDF (TrueType)
pdf(file.path(FIG, "Fig_hdwgcna_CNS_v2.pdf"), width = W/25.4, height = H/25.4,
    family = "sans", useDingbats = FALSE)
grid.draw(g); dev.off()

# TIFF 600dpi (投稿)
tiff(file.path(FIG, "Fig_hdwgcna_CNS_v2.tiff"), width = W, height = H, units = "mm",
     res = 600, compression = "lzw", bg = "white")
grid.draw(g); dev.off()

# PNG 300dpi (预览)
png(file.path(FIG, "Fig_hdwgcna_CNS_v2.png"), width = W, height = H, units = "mm", res = 300)
grid.draw(g); dev.off()

# source data (投稿必需)
write.csv(as.data.frame(mcor), file.path(FIG, "source_module_trait_cor.csv"))
write.csv(as.data.frame(mp),   file.path(FIG, "source_module_trait_p.csv"))
write.csv(hub_top,             file.path(FIG, "source_hub_red.csv"))
write.csv(data.frame(gene = mods_feat, module = mods_lab), file.path(FIG, "source_dotplot_genes.csv"))

cat("DONE →", FIG, "\n")
cat(list.files(FIG), sep = "\n")
