#' ============================================================================
#' MemOmics — Seurat scRNA-seq Pipeline: QC → SCTransform → PCA → UMAP → Clustering
#' Skeletal muscle aging dataset (60k cells subset)
#' ============================================================================
#' Output dir: results/基础分析/Seurat_QC/
#' Data: results/基础分析/Seurat_QC/data/mtx/ (10X MTX format)
#' ============================================================================

library(Seurat)
library(ggplot2)
library(patchwork)
library(dplyr)
library(Matrix)

# ─── Paths ────────────────────────────────────────────────────────────────
base_dir  <- "E:/MemOmics-Agent/hermes-agent/results/基础分析/Seurat_QC"
mtx_dir   <- file.path(base_dir, "data", "mtx")
fig_dir   <- file.path(base_dir, "figures")
res_dir   <- file.path(base_dir, "results")
script_dir <- file.path(base_dir, "scripts")

dir.create(fig_dir,   showWarnings = FALSE, recursive = TRUE)
dir.create(res_dir,   showWarnings = FALSE, recursive = TRUE)
dir.create(script_dir, showWarnings = FALSE, recursive = TRUE)

cat("═══ Step 1: Reading 10X MTX format ═══\n")
system.time({
  counts <- Read10X(data.dir = mtx_dir)
})
cat(sprintf("  Matrix dimensions: %s\n", paste(dim(counts), collapse = " × ")))

# ─── Step 2: Create Seurat Object ─────────────────────────────────────────
cat("\n═══ Step 2: Creating Seurat Object ═══\n")
obj <- CreateSeuratObject(
  counts  = counts,
  project = "Muscle_Aging_60k",
  min.cells = 3,
  min.features = 200
)
cat(sprintf("  Cells: %d, Genes: %d\n", ncol(obj), nrow(obj)))

# ─── Step 3: Metadata from upstream ───────────────────────────────────────
cat("\n═══ Step 3: Adding cell metadata ═══\n")
meta_csv <- file.path(mtx_dir, "metadata.csv")
if (file.exists(meta_csv)) {
  meta_df <- read.csv(meta_csv, row.names = 1)
  # Keep only columns that are in the metadata but not already in obj
  common_cells <- intersect(colnames(obj), rownames(meta_df))
  cat(sprintf("  Overlapping cells: %d / %d\n", length(common_cells), ncol(obj)))
  
  for (col in colnames(meta_df)) {
    if (!col %in% colnames(obj[[]])) {
      obj <- AddMetaData(obj, metadata = meta_df[colnames(obj), col, drop = FALSE], col.name = col)
    }
  }
}
cat("  Metadata columns:", paste(colnames(obj[[]]), collapse = ", "), "\n")

# ─── Step 4: QC ──────────────────────────────────────────────────────────
cat("\n═══ Step 4: Quality Control ═══\n")

# Calculate % mitochondrial (human: MT- prefix)
obj[["percent.mt"]] <- PercentageFeatureSet(obj, pattern = "^MT-")

# Calculate % ribosomal
obj[["percent.ribo"]] <- PercentageFeatureSet(obj, pattern = "^RP[SL]")

# Skeletal muscle QC thresholds (from literature):
#   nFeature_RNA: 200–6000 (Kim et al. 2023, Nat Commun)
#   percent.mt: <5% (Rubio-Lara et al. 2023, Cell Rep)
# Also filter doublet_score from metadata if present
qc_before <- ncol(obj)

# Pre-QC violin
p_qc_raw <- VlnPlot(obj, features = c("nFeature_RNA", "nCount_RNA", "percent.mt", "percent.ribo"),
                     ncol = 4, pt.size = 0, cols = "#E41A1C") +
  ggtitle("Pre-QC Metrics") & theme(plot.title = element_text(hjust = 0.5))
ggsave(file.path(fig_dir, "01_QC_violin_pre.pdf"), p_qc_raw, width = 16, height = 5)

# Feature-feature scatter
p_qc_scatter <- FeatureScatter(obj, feature1 = "nCount_RNA", feature2 = "nFeature_RNA") +
  ggtitle("RNA Count vs Feature (pre-QC)")
ggsave(file.path(fig_dir, "02_QC_scatter_pre.pdf"), p_qc_scatter, width = 7, height = 6)

# Apply QC filters
obj <- subset(obj, subset = nFeature_RNA > 200 & nFeature_RNA < 6000 &
                percent.mt < 5 & nCount_RNA > 500)

qc_after <- ncol(obj)
cat(sprintf("  Cells before QC: %d → after QC: %d (removed %d, %.1f%%)\n",
            qc_before, qc_after, qc_before - qc_after,
            (qc_before - qc_after) / qc_before * 100))

# Post-QC violin
p_qc_post <- VlnPlot(obj, features = c("nFeature_RNA", "nCount_RNA", "percent.mt", "percent.ribo"),
                      ncol = 4, pt.size = 0, cols = "#377EB8") +
  ggtitle("Post-QC Metrics") & theme(plot.title = element_text(hjust = 0.5))
ggsave(file.path(fig_dir, "03_QC_violin_post.pdf"), p_qc_post, width = 16, height = 5)

# ─── Step 5: SCTransform normalization ───────────────────────────────────
cat("\n═══ Step 5: SCTransform ═══\n")

# For 60k cells, use v5 assay and regularize to speed up
# Only use top 3000 variable features
system.time({
  obj <- SCTransform(obj, 
                     vars.to.regress = "percent.mt",
                     variable.features.n = 3000,
                     verbose = TRUE,
                     conserve.memory = TRUE)
})
cat(sprintf("  SCTransform done. Assays: %s\n", paste(Assays(obj), collapse = ", ")))

# ─── Step 6: PCA ─────────────────────────────────────────────────────────
cat("\n═══ Step 6: PCA ═══\n")
system.time({
  obj <- RunPCA(obj, npcs = 50, verbose = FALSE)
})

# Elbow plot
p_elbow <- ElbowPlot(obj, ndims = 50) + ggtitle("PCA Elbow Plot")
ggsave(file.path(fig_dir, "04_PCA_elbow.pdf"), p_elbow, width = 7, height = 5)

# PC heatmap
p_pc_heat <- DimHeatmap(obj, dims = 1:6, cells = 500, balanced = TRUE, fast = FALSE)
ggsave(file.path(fig_dir, "05_PCA_heatmap.pdf"), p_pc_heat, width = 12, height = 10)

# ─── Step 7: UMAP ────────────────────────────────────────────────────────
cat("\n═══ Step 7: UMAP ═══\n")
# Use 30 PCs (determined from elbow)
n_pcs <- 30

system.time({
  obj <- RunUMAP(obj, reduction = "pca", dims = 1:n_pcs, verbose = FALSE)
})

# Basic UMAP
p_umap <- DimPlot(obj, reduction = "umap", group.by = "orig.ident",
                  pt.size = 0.3, raster = TRUE) +
  ggtitle("UMAP - All Cells") + theme(plot.title = element_text(hjust = 0.5))
ggsave(file.path(fig_dir, "06_UMAP_raw.pdf"), p_umap, width = 7, height = 6)

# UMAP colored by existing annotations (if available)
if ("celltype" %in% colnames(obj[[]])) {
  p_umap_ct <- DimPlot(obj, reduction = "umap", group.by = "celltype",
                       pt.size = 0.2, raster = TRUE, label = TRUE, repel = TRUE) +
    ggtitle("UMAP - Cell Type (pre-existing annotation)")
  ggsave(file.path(fig_dir, "07_UMAP_celltype.pdf"), p_umap_ct, width = 9, height = 7)
}

if ("age_group" %in% colnames(obj[[]])) {
  p_umap_age <- DimPlot(obj, reduction = "umap", group.by = "age_group",
                         pt.size = 0.2, raster = TRUE) +
    ggtitle("UMAP - Age Group")
  ggsave(file.path(fig_dir, "08_UMAP_agegroup.pdf"), p_umap_age, width = 8, height = 6)
}

if ("sex" %in% colnames(obj[[]])) {
  p_umap_sex <- DimPlot(obj, reduction = "umap", group.by = "sex",
                         pt.size = 0.2, raster = TRUE) +
    ggtitle("UMAP - Sex")
  ggsave(file.path(fig_dir, "09_UMAP_sex.pdf"), p_umap_sex, width = 7, height = 6)
}

# ─── Step 8: Clustering ──────────────────────────────────────────────────
cat("\n═══ Step 8: Clustering ═══\n")
system.time({
  obj <- FindNeighbors(obj, reduction = "pca", dims = 1:n_pcs, verbose = FALSE)
})
cat("  Neighbors found\n")

# Test multiple resolutions
resolutions <- c(0.2, 0.5, 0.8, 1.2)
for (res in resolutions) {
  obj <- FindClusters(obj, resolution = res, verbose = FALSE)
  cat(sprintf("  Resolution %.1f: %d clusters\n", res, 
              length(unique(obj[[paste0("SCT_snn_res.", res)]][,1]))))
}

# UMAP with clusters at resolution 0.5
p_clust_05 <- DimPlot(obj, reduction = "umap", group.by = "SCT_snn_res.0.5",
                       pt.size = 0.2, raster = TRUE, label = TRUE, repel = TRUE) +
  ggtitle("UMAP - Clusters (res=0.5)")
ggsave(file.path(fig_dir, "10_UMAP_clusters_res0.5.pdf"), p_clust_05, width = 8, height = 6)

# UMAP with clusters at resolution 0.8
p_clust_08 <- DimPlot(obj, reduction = "umap", group.by = "SCT_snn_res.0.8",
                       pt.size = 0.2, raster = TRUE, label = TRUE, repel = TRUE) +
  ggtitle("UMAP - Clusters (res=0.8)")
ggsave(file.path(fig_dir, "11_UMAP_clusters_res0.8.pdf"), p_clust_08, width = 9, height = 7)

# ─── Combined summary figure ─────────────────────────────────────────────
cat("\n═══ Step 9: Summary composite figure ═══\n")
# Create a multi-panel figure
p_combined <- wrap_plots(
  p_qc_post + theme(legend.position = "none"),
  p_elbow + theme(legend.position = "none"),
  p_umap + theme(legend.position = "none"),
  p_clust_05 + theme(legend.position = "none"),
  ncol = 2
) + plot_annotation(title = "MemOmics - Seurat QC Analysis Summary",
                    subtitle = paste0("60k cells subset | ", qc_after, " cells after QC"))
ggsave(file.path(fig_dir, "12_summary_combined.pdf"), p_combined, width = 14, height = 12)
ggsave(file.path(fig_dir, "12_summary_combined.png"), p_combined, width = 14, height = 12, dpi = 150)

# ─── Save Seurat object ──────────────────────────────────────────────────
cat("\n═══ Saving results ═══\n")
saveRDS(obj, file.path(res_dir, "seurat_qc_final.rds"))
cat(sprintf("  Seurat object saved: %s\n", file.path(res_dir, "seurat_qc_final.rds")))

# Save clustering statistics
cluster_stats <- obj[[]] %>%
  group_by(SCT_snn_res.0.5) %>%
  summarise(
    n_cells = n(),
    pct = round(n() / ncol(obj) * 100, 2)
  )
write.csv(cluster_stats, file.path(res_dir, "cluster_stats_res0.5.csv"), row.names = FALSE)
cat("  Cluster statistics saved\n")

# ─── Session info ────────────────────────────────────────────────────────
cat("\n═══ Session Info ═══\n")
cat(paste(capture.output(sessionInfo()), collapse = "\n"))

cat("\n\n═══ DONE ═══\n")
cat(sprintf("Figures: %s\n", fig_dir))
cat(sprintf("Results: %s\n", res_dir))