# annotate_human_tilematrix.R — ArchR 细胞类型注释（TileMatrix 替代 addGeneScoreMatrix）
# 用途：addGeneScoreMatrix 在 Windows 连续崩溃 2 次 → 改用 TileMatrix 500bp bins
#       计算 marker 基因 TSS±2kb 覆盖度（等价 gene score 简化版），threads=1
# 验证：2026-08-08 P0 人侧 4 样本 merge 后（35,787 cells / 17 clusters）跑通，秒级出结果
# 适用：猴-人跨物种注释对齐时必须两侧用同一套 marker 列表保证可比
.libPaths(c("USER_R_LIBS/R-4.5.3", .libPaths()))
suppressPackageStartupMessages(library(ArchR))

addArchRThreads(threads = 1)
addArchRGenome("hg38")

out_dir <- "MEMOMICS_HOME/results/memomics-1c1890da/patent_test"   # ← 改成本项目输出目录
setwd(out_dir)

cat("Loading human_proj_clustered.rds ...\n")
proj <- readRDS(file.path(out_dir, "human_proj_clustered.rds"))
cat("Cells:", nCells(proj), "| Clusters:", length(unique(proj$Clusters)), "\n")

# === 1. TileMatrix（已存在于 Arrow，安全，零额外计算）===
cat("\n=== getMatrixFromProject TileMatrix ===\n")
tile <- getMatrixFromProject(proj, "TileMatrix", binarize = TRUE)
tile_mat <- assay(tile)          # tiles x cells
tile_gr <- rowRanges(tile)       # 500bp bins
cat("TileMatrix dims:", nrow(tile_mat), "x", ncol(tile_mat), "\n")

# === 2. hg38 基因坐标（ArchR GeneAnnotation）===
geneAnno <- getGeneAnnotation(proj)$genes
gn <- mcols(geneAnno)$name
cat("GeneAnnotation genes:", length(gn), "\n")

# === 3. 8 大类 marker（猴-人两侧共用）===
markers <- list(
  Ex    = c("SLC17A7", "CAMK2A", "SATB2", "NRGN", "NEUROD6"),
  Inh   = c("GAD1", "GAD2", "SLC32A1", "PVALB", "SST"),
  Astro = c("GFAP", "AQP4", "SLC1A2", "GJA1"),
  Micro = c("PTPRC", "CX3CR1", "P2RY12", "CSF1R", "TREM2"),
  OPC   = c("PDGFRA", "OLIG1", "OLIG2", "CSPG4"),
  ODC   = c("MBP", "MOG", "PLP1", "MOBP"),
  VS    = c("CLDN5", "FLT1", "PECAM1", "VWF"),
  ChP   = c("TTR", "CLIC6", "FOLR1", "SLC13A3")
)

# 每个 marker 基因 → TSS±2kb 内 tile 索引
gene_tile_idx <- function(gene_symbols, geneAnno, tile_gr) {
  gn <- mcols(geneAnno)$name
  hits <- which(gn %in% gene_symbols)
  if (length(hits) == 0) return(integer(0))
  tss_gr <- resize(geneAnno[hits], width = 1, fix = "start")
  win <- resize(tss_gr, width = 4001, fix = "center")   # TSS±2kb
  ov <- findOverlaps(win, tile_gr)
  unique(subjectHits(ov))
}

clusters <- proj$Clusters
cl_levels <- unique(clusters)
score_df <- data.frame(cluster = cl_levels)

cat("\n=== Cluster marker TSS coverage matrix ===\n")
for (ct in names(markers)) {
  idx <- gene_tile_idx(markers[[ct]], geneAnno, tile_gr)
  if (length(idx) == 0) { cat("WARN: no tiles for", ct, "\n"); score_df[[ct]] <- NA; next }
  cat("  ", ct, ": marker genes ->", length(idx), "tiles\n")
  score_df[[ct]] <- sapply(cl_levels, function(cl) {
    cells_cl <- which(clusters == cl)
    if (length(cells_cl) == 0) return(NA)
    mean(tile_mat[idx, cells_cl, drop = FALSE])
  })
}
print(round(score_df, 4))

# === 4. 注释 = 最大类别 ===
score_mat <- as.matrix(score_df[, names(markers)])
annot <- apply(score_mat, 1, function(x) names(markers)[which.max(x)])
score_df$CellType <- annot
cat("\n=== Cluster -> CellType mapping ===\n")
print(score_df[, c("cluster", "CellType")])

# === 5. 写回 + 保存 ===
ct_map <- setNames(score_df$CellType, score_df$cluster)
proj$CellType <- ct_map[as.character(proj$Clusters)]
cat("\nCellType distribution:\n")
print(table(proj$CellType))
cat("\nCluster x CellType cross-tab:\n")
print(table(proj$Clusters, proj$CellType))

saveRDS(proj, file.path(out_dir, "human_proj_annotated.rds"))
write.csv(score_df, file.path(out_dir, "human_cluster_annotation.csv"), row.names = FALSE)
cat("Saved: human_proj_annotated.rds + human_cluster_annotation.csv\n")

# === 6. UMAP 注释图 ===
png(file.path(out_dir, "human_umap_celltype.png"), width = 1400, height = 1200, res = 150)
p <- plotEmbedding(proj, colorBy = "cellColData", name = "CellType", embedding = "UMAP",
                   pal = c("#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F",
                           "#8491B4", "#91D1C2", "#DC0000"))
print(p)
dev.off()

png(file.path(out_dir, "human_umap_cluster.png"), width = 1400, height = 1200, res = 150)
p2 <- plotEmbedding(proj, colorBy = "cellColData", name = "Clusters", embedding = "UMAP")
print(p2)
dev.off()

cat("\n=== P0 DONE — human_proj_annotated.rds + annotation CSV + UMAP saved ===\n")
cat("Cells:", nCells(proj), "| Clusters:", length(unique(proj$Clusters)),
    "| CellTypes:", length(unique(proj$CellType)), "\n")
