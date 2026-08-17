# ============================================================================
# COMPLETE SEURAT ANALYSIS EXAMPLE - PBMC 3K DATASET
# ============================================================================
#
# This script demonstrates a complete end-to-end scRNA-seq analysis
# using the PBMC 3k dataset from 10X Genomics.
#
# For dataset info, see: assets/eval/datasets/pbmc3k_info.md
#
# Expected runtime: ~15-20 minutes on standard laptop

# Load evaluation helpers (for example data)
source("assets/eval/eval_helpers.R")

# Load all required scripts
source("scripts/setup_and_import.R")
source("scripts/qc_metrics.R")
source("scripts/plot_qc.R")
source("scripts/filter_cells.R")
source("scripts/normalize_data.R")
source("scripts/scale_and_pca.R")
source("scripts/cluster_cells.R")
source("scripts/run_umap.R")
source("scripts/plot_dimreduction.R")
source("scripts/find_markers.R")
source("scripts/annotate_celltypes.R")
source("scripts/export_results.R")

# Setup
setup_seurat_libraries()

# ============================================================================
# STEP 1: Load data
# ============================================================================

# Option A: From SeuratData package (easiest)
seurat_obj <- load_seurat_data("pbmc3k")

# Option B: From downloaded 10X data
# seurat_obj <- import_10x_data("path/to/filtered_gene_bc_matrices/hg19/")

# Option C: From H5 file
# seurat_obj <- import_h5_data("path/to/filtered_feature_bc_matrix.h5")

# ============================================================================
# STEP 2: Quality Control
# ============================================================================

# Calculate QC metrics
seurat_obj <- calculate_qc_metrics(seurat_obj, species = "human")

# Visualize QC metrics
plot_qc_violin(seurat_obj, output_dir = "results/qc")
plot_qc_scatter(seurat_obj, output_dir = "results/qc")
plot_qc_histogram(seurat_obj, output_dir = "results/qc")

# Check metrics before filtering
summary(seurat_obj$nFeature_RNA)
summary(seurat_obj$nCount_RNA)
summary(seurat_obj$percent.mt)

# ============================================================================
# STEP 3: Filter cells
# ============================================================================

# Apply tissue-specific filtering (PBMC)
seurat_obj <- filter_cells_by_qc(
  seurat_obj,
  min_features = 200,
  max_features = 2500,
  max_mt_percent = 5
)

# Expected: ~2,600-2,700 cells retained (>95%)

# ============================================================================
# STEP 4: Normalize data
# ============================================================================

# Use SCTransform (recommended for 10X data)
seurat_obj <- # SCT 依赖已在 run_sctransform() 内部处理: library(glmGamPoi) + library(future) + plan(multisession) + options(future.globals.maxSize=70*1024^3)
    run_sctransform(seurat_obj, vars_to_regress = c("percent.mt"))

# Alternative: LogNormalize workflow
# seurat_obj <- run_lognormalize(seurat_obj)
# source("scripts/find_variable_features.R")
# seurat_obj <- find_hvgs(seurat_obj, n_features = 2000)
# seurat_obj <- scale_data(seurat_obj, vars_to_regress = c("percent.mt"))

# ============================================================================
# STEP 5: Dimensionality Reduction - PCA
# ============================================================================

# Run PCA
seurat_obj <- run_pca_analysis(seurat_obj, n_pcs = 50)

# Visualize PCA results
plot_elbow(seurat_obj, output_dir = "results/pca")
plot_pca_heatmaps(seurat_obj, dims = 1:15, output_dir = "results/pca")
plot_pca_loadings(seurat_obj, dims = 1:4, output_dir = "results/pca")

# Decision: Use 30 PCs for clustering (conservative)

# ============================================================================
# STEP 6: Clustering
# ============================================================================

# Test multiple resolutions
seurat_obj <- cluster_multiple_resolutions(
  seurat_obj,
  dims = 1:30,
  resolutions = c(0.4, 0.6, 0.8, 1.0)
)

# Expected clusters:
# - Resolution 0.4: ~7 clusters
# - Resolution 0.8: ~9 clusters
# - Resolution 1.0: ~11 clusters

# Set resolution 0.8 as default (good balance)
Idents(seurat_obj) <- "RNA_snn_res.0.8"

# ============================================================================
# STEP 7: UMAP
# ============================================================================

# Run UMAP for visualization
seurat_obj <- run_umap_reduction(seurat_obj, dims = 1:30)

# Visualize clusters
plot_umap_clusters(seurat_obj, output_dir = "results/umap")

# Compare different resolutions
plot_clustering_comparison(
  seurat_obj,
  resolutions = c(0.4, 0.6, 0.8, 1.0),
  output_dir = "results/umap"
)

# Plot QC metrics on UMAP (check for technical artifacts)
plot_feature_umap(
  seurat_obj,
  features = c("nFeature_RNA", "nCount_RNA", "percent.mt"),
  output_dir = "results/umap"
)

# ============================================================================
# STEP 8: Find marker genes
# ============================================================================

# Find markers for all clusters
all_markers <- find_all_cluster_markers(
  seurat_obj,
  resolution = 0.8,
  min_pct = 0.25,
  logfc_threshold = 0.25
)

# Expected: ~100-200 markers per cluster

# Export marker tables
export_marker_tables(all_markers, output_dir = "results/markers")

# Visualize top markers
plot_top_markers_heatmap(seurat_obj, all_markers, n_top = 10, output_dir = "results/markers")
plot_markers_dotplot(seurat_obj, all_markers, n_top = 5, output_dir = "results/markers")
plot_markers_violin(seurat_obj, all_markers, n_top = 3, output_dir = "results/markers")

# Examine specific cluster markers
head(all_markers[all_markers$cluster == 0, ], 10)

# ============================================================================
# STEP 9: Cell type annotation
# ============================================================================

# Based on marker genes, assign cell type labels
# See references/marker_gene_database.md for marker lists

annotations <- c(
  "0" = "CD4 T cells",           # CD3D+, IL7R+, CD4+
  "1" = "CD14+ Monocytes",       # CD14+, LYZ+, S100A8+
  "2" = "CD8 T cells",           # CD3D+, CD8A+, CD8B+
  "3" = "B cells",               # MS4A1+, CD79A+, CD79B+
  "4" = "NK cells",              # GNLY+, NKG7+, GZMB+
  "5" = "FCGR3A+ Monocytes",     # FCGR3A+, MS4A7+
  "6" = "Dendritic cells",       # FCER1A+, CST3+
  "7" = "Megakaryocytes"         # PPBP+ (if present)
)

seurat_obj <- annotate_clusters_manual(seurat_obj, annotations, resolution = 0.8)

# Visualize annotations
plot_annotated_umap(seurat_obj, output_dir = "results/annotation")
plot_celltype_proportions(seurat_obj, output_dir = "results/annotation")

# Alternative: Automated annotation with SingleR
# seurat_obj <- annotate_with_singler(seurat_obj, reference = "HPCA")

# ============================================================================
# STEP 10: Visualize specific genes
# ============================================================================

# Key immune markers
immune_markers <- c("CD3D", "CD4", "CD8A", "CD14", "MS4A1", "GNLY")
plot_feature_umap(seurat_obj, features = immune_markers, output_dir = "results/umap")

# T cell markers
tcell_markers <- c("CD3D", "CD4", "CD8A", "IL7R", "CCR7", "CD69")
plot_feature_umap(seurat_obj, features = tcell_markers, output_dir = "results/umap")

# ============================================================================
# STEP 11: Export results
# ============================================================================

# Export everything
export_seurat_results(
  seurat_obj,
  output_dir = "pbmc3k_results",
  resolution = 0.8,
  export_counts = TRUE,
  export_metadata = TRUE,
  export_dimreductions = TRUE
)

# Export summary statistics
export_summary_stats(seurat_obj, output_dir = "pbmc3k_results")

# ============================================================================
# ANALYSIS COMPLETE
# ============================================================================

message("\n========================================")
message("PBMC 3k Analysis Complete!")
message("========================================")
message("Results saved in: pbmc3k_results/")
message("\nKey files:")
message("  - seurat_processed.rds (complete Seurat object)")
message("  - cell_metadata.csv (cell annotations)")
message("  - cluster_markers_all.csv (all marker genes)")
message("  - umap_celltypes.svg/png (annotated UMAP)")
message("\nCell types identified:")
print(table(seurat_obj$celltype))

# Save session info for reproducibility
sink("pbmc3k_results/session_info.txt")
sessionInfo()
sink()

message("\nSession info saved to: pbmc3k_results/session_info.txt")
