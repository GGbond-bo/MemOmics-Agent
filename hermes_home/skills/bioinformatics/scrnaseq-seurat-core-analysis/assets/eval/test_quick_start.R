#!/usr/bin/env Rscript

# Quick Start Functional Test
# This script tests the Quick Start workflow from SKILL.md

cat("=== Quick Start Functional Test ===\n\n")
cat("Testing scrnaseq-seurat-core-analysis skill\n")
cat("Started at:", as.character(Sys.time()), "\n\n")

# Load evaluation helpers for example data
cat("Step 1: Loading evaluation helpers...\n")
tryCatch({
  source("assets/eval/eval_helpers.R")
  cat("✓ Loaded assets/eval/eval_helpers.R\n\n")
}, error = function(e) {
  cat("✗ Error loading eval_helpers.R:", conditionMessage(e), "\n")
  quit(status = 1)
})

# Load required core scripts
cat("Step 2: Loading core scripts...\n")
scripts <- c(
  "scripts/setup_and_import.R",
  "scripts/qc_metrics.R",
  "scripts/filter_cells.R",
  "scripts/normalize_data.R",
  "scripts/scale_and_pca.R",
  "scripts/cluster_cells.R",
  "scripts/run_umap.R",
  "scripts/find_markers.R",
  "scripts/plot_dimreduction.R",
  "scripts/annotate_celltypes.R"
)

for (script in scripts) {
  tryCatch({
    source(script)
    cat("✓ Loaded", script, "\n")
  }, error = function(e) {
    cat("✗ Error loading", script, ":", conditionMessage(e), "\n")
    quit(status = 1)
  })
}

cat("\nStep 3: Setting up Seurat libraries...\n")
tryCatch({
  setup_seurat_libraries()
  cat("✓ Libraries loaded successfully\n\n")
}, error = function(e) {
  cat("✗ Error setting up libraries:", conditionMessage(e), "\n")
  cat("Note: This is expected if Seurat packages are not installed\n")
  quit(status = 1)
})

cat("Step 4: Loading PBMC 3k example data...\n")
tryCatch({
  seurat_obj <- load_seurat_data("pbmc3k")
  cat("✓ Loaded pbmc3k data\n")
  cat("  Dimensions:", nrow(seurat_obj), "genes x", ncol(seurat_obj), "cells\n\n")
}, error = function(e) {
  cat("✗ Error loading pbmc3k data:", conditionMessage(e), "\n")
  cat("Note: This requires SeuratData package and pbmc3k dataset\n")
  quit(status = 1)
})

cat("Step 5: QC and filtering...\n")
tryCatch({
  seurat_obj <- calculate_qc_metrics(seurat_obj, species = "human")
  cat("✓ Calculated QC metrics\n")

  seurat_obj <- filter_cells_by_qc(seurat_obj, min_features = 200, max_features = 2500, max_mt_percent = 5)
  cat("✓ Filtered cells\n")
  cat("  Retained:", ncol(seurat_obj), "cells\n\n")
}, error = function(e) {
  cat("✗ Error in QC/filtering:", conditionMessage(e), "\n")
  quit(status = 1)
})

cat("Step 6: Normalization and dimensionality reduction...\n")
cat("(This step takes 5-10 minutes - running abbreviated version)\n")
tryCatch({
  seurat_obj <- # SCT 依赖已在 run_sctransform() 内部处理: library(glmGamPoi) + library(future) + plan(multisession) + options(future.globals.maxSize=70*1024^3)
    run_sctransform(seurat_obj, vars_to_regress = "percent.mt")
  cat("✓ SCTransform normalization complete\n")

  seurat_obj <- run_pca_analysis(seurat_obj, n_pcs = 30)
  cat("✓ PCA analysis complete\n")

  seurat_obj <- run_umap_reduction(seurat_obj, dims = 1:30)
  cat("✓ UMAP reduction complete\n\n")
}, error = function(e) {
  cat("✗ Error in normalization/reduction:", conditionMessage(e), "\n")
  quit(status = 1)
})

cat("Step 7: Clustering...\n")
tryCatch({
  seurat_obj <- cluster_multiple_resolutions(seurat_obj, dims = 1:30, resolutions = c(0.6, 0.8))
  cat("✓ Clustering complete\n")
  cat("  Tested resolutions: 0.6, 0.8\n\n")
}, error = function(e) {
  cat("✗ Error in clustering:", conditionMessage(e), "\n")
  quit(status = 1)
})

cat("Step 8: Finding markers...\n")
tryCatch({
  all_markers <- find_all_cluster_markers(seurat_obj, resolution = 0.8)
  cat("✓ Found cluster markers\n")
  cat("  Total markers:", nrow(all_markers), "\n\n")
}, error = function(e) {
  cat("✗ Error finding markers:", conditionMessage(e), "\n")
  quit(status = 1)
})

cat("Step 9: Creating output directory for plots...\n")
dir.create("results", showWarnings = FALSE, recursive = TRUE)
dir.create("results/umap", showWarnings = FALSE, recursive = TRUE)
dir.create("results/markers", showWarnings = FALSE, recursive = TRUE)
cat("✓ Directories created\n\n")

cat("Step 10: Generating visualizations...\n")
tryCatch({
  plot_umap_clusters(seurat_obj, output_dir = "results/umap")
  cat("✓ UMAP cluster plot generated\n")

  plot_top_markers_heatmap(seurat_obj, all_markers, n_top = 10, output_dir = "results/markers")
  cat("✓ Marker heatmap generated\n\n")
}, error = function(e) {
  cat("✗ Error generating plots:", conditionMessage(e), "\n")
  quit(status = 1)
})

cat("=== TEST COMPLETED SUCCESSFULLY ===\n")
cat("Finished at:", as.character(Sys.time()), "\n\n")

cat("Results:\n")
cat("- Final cell count:", ncol(seurat_obj), "cells\n")
cat("- Clusters (res 0.8):", length(unique(seurat_obj$RNA_snn_res.0.8)), "clusters\n")
cat("- Output files saved to: results/\n\n")

cat("✓ All Quick Start steps executed successfully\n")
