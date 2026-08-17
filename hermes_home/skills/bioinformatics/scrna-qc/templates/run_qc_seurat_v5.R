# ============================================================================
# QC Analysis Template — Seurat v5 + anndata R (handles pre-normalized h5ad)
#
# PROVEN: 2026-07-02, human skeletal muscle aging, 29993 cells → 29988 cells
#         59/59 verification checks passed.
#
# This template handles 4 Seurat v5 / anndata-R compatibility issues:
#   1. dgRMatrix → dgCMatrix sparse conversion (avoid 12GB dense coercion)
#   2. [[<- assignment fails → use @meta.data directly
#   3. GetAssayData(slot=) defunct → use layer=
#   4. VlnPlot triggers dense coercion → use ggplot2 geom_violin on metadata
#
# USAGE:
#   Rscript run_qc_seurat_v5.R
#   Edit INPUT_PATH, OUTPUT_DIR, SPECIES, and thresholds below.
#
# REQUIRES: Seurat (v5), anndata (R), ggplot2, patchwork, dplyr
# ============================================================================

suppressPackageStartupMessages({
  library(Seurat)
  library(anndata)
  library(ggplot2)
  library(patchwork)
  library(dplyr)
})

# ── Configuration (edit these) ──────────────────────────────────────────
input_path  <- "MEMOMICS_HOME/results/subset_30k.h5ad"
output_dir  <- "MEMOMICS_HOME/results/02_basic/qc"
SPECIES     <- "human"
MIN_GENES   <- 200
MAX_GENES   <- 6000
MAX_PCT_MT  <- 15       # 15% for muscle; 20% default
GENE_MIN_CELLS <- 3

fig_dir <- file.path(output_dir, "figures")
res_dir <- file.path(output_dir, "results")
dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(res_dir, recursive = TRUE, showWarnings = FALSE)

# ── Helper: violin plot from metadata (avoids VlnPlot dense coercion) ──
plot_violin <- function(df, title_suffix) {
  plots <- list()
  metrics <- c("nFeature_RNA", "nCount_RNA", "percent.mt", "percent.ribo")
  labels  <- c("n_genes", "total_expr", "pct_mt", "pct_ribo")
  colors  <- if (title_suffix == "AFTER") rep("#27AE60", 4) else rep("#5DADE2", 4)
  for (i in seq_along(metrics)) {
    m <- metrics[i]; lab <- labels[i]
    plots[[i]] <- ggplot(df, aes(x = 1, y = .data[[m]])) +
      geom_violin(fill = colors[i], alpha = 0.7, color = NA) +
      geom_boxplot(width = 0.1, fill = "white", outlier.shape = NA, color = "grey30") +
      labs(x = "", y = lab, title = sprintf("%s\n(median=%.1f)", lab, median(df[[m]]))) +
      theme_classic() +
      theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())
  }
  wrap_plots(plots, ncol = 4)
}

plot_violin_grouped <- function(meta_df, group_col) {
  plots <- list()
  metrics <- c("nFeature_RNA", "nCount_RNA", "percent.mt")
  labels  <- c("n_genes", "total_expr", "pct_mt")
  for (i in seq_along(metrics)) {
    m <- metrics[i]; lab <- labels[i]
    plots[[i]] <- ggplot(meta_df, aes(x = .data[[group_col]], y = .data[[m]],
                                      fill = .data[[group_col]])) +
      geom_violin(alpha = 0.7, color = NA) +
      geom_boxplot(width = 0.1, fill = "white", outlier.shape = NA, color = "grey30") +
      labs(x = "", y = lab, title = lab, fill = group_col) +
      theme_classic() +
      theme(axis.text.x = element_text(angle = 45, hjust = 1, size = 8),
            legend.position = "none")
  }
  wrap_plots(plots, ncol = 3)
}

# ── Step 1: Load h5ad ──
cat("Step 1: Loading h5ad...\n")
adata <- read_h5ad(input_path)
cat(sprintf("  %d cells x %d genes\n", nrow(adata), ncol(adata)))

X <- adata$X
is_integer <- all(round(X@x) == X@x)
is_normalized <- !is_integer
cat(sprintf("  Class: %s | Integer: %s | Normalized: %s\n",
            class(X)[1], is_integer, is_normalized))

# ── Step 2: Convert to Seurat (SPARSE — no dense coercion) ──
cat("Step 2: Converting to Seurat (sparse path)...\n")
# dgRMatrix → dgCMatrix via TsparseMatrix (stays sparse)
if (inherits(X, "dgRMatrix") || inherits(X, "RsparseMatrix")) {
  X_csc <- as(as(X, "TsparseMatrix"), "dgCMatrix")
} else {
  X_csc <- as(X, "dgCMatrix")
}
expr_mat <- Matrix::t(X_csc)  # genes x cells
rownames(expr_mat) <- colnames(adata)
colnames(expr_mat) <- rownames(adata$obs)
gc()

# Pre-compute QC from sparse matrix
nCount_RNA_vals   <- Matrix::colSums(expr_mat)
nFeature_RNA_vals <- Matrix::colSums(expr_mat > 0)

seurat_obj <- CreateSeuratObject(counts = NULL, data = expr_mat,
                                  meta.data = as.data.frame(adata$obs))
seurat_obj$nCount_RNA   <- nCount_RNA_vals
seurat_obj$nFeature_RNA <- nFeature_RNA_vals

# ── Step 3: Source predefined QC scripts (if available) ──
# These provide get_species_mito_pattern() and filter_cells_by_qc()
qc_metrics_script <- "MEMOMICS_HOME/skills/scrna-seurat-core/scripts/qc_metrics.R"
filter_script     <- "MEMOMICS_HOME/skills/scrna-seurat-core/scripts/filter_cells.R"
if (file.exists(qc_metrics_script)) source(qc_metrics_script)
if (file.exists(filter_script))     source(filter_script)

# ── Step 4: Calculate QC metrics ──
cat("Step 4: QC metrics...\n")
# Determine patterns from sourced helpers or hardcode
if (exists("get_species_mito_pattern")) {
  mito_pattern <- get_species_mito_pattern(SPECIES)
  ribo_pattern <- get_species_ribo_pattern(SPECIES)
} else {
  mito_pattern <- if (SPECIES == "human") "^MT-" else "^mt-"
  ribo_pattern <- if (SPECIES == "human") "^RP[SL]" else "^Rp[sl]"
}

data_mat <- GetAssayData(seurat_obj, layer = "data")  # layer= not slot= (Seurat v5)
mt_genes   <- grepl(mito_pattern, rownames(seurat_obj))
ribo_genes <- grepl(ribo_pattern, rownames(seurat_obj))

# Assign to @meta.data directly ([[<- fails in Seurat v5 without counts layer)
seurat_obj@meta.data$percent.mt <-
  (Matrix::colSums(data_mat[mt_genes, , drop = FALSE]) / Matrix::colSums(data_mat)) * 100
seurat_obj@meta.data$percent.ribo <-
  (Matrix::colSums(data_mat[ribo_genes, , drop = FALSE]) / Matrix::colSums(data_mat)) * 100
seurat_obj@meta.data$log10GenesPerUMI <-
  log10(seurat_obj$nFeature_RNA / seurat_obj$nCount_RNA)

cat(sprintf("  MT genes: %d | Ribo genes: %d\n", sum(mt_genes), sum(ribo_genes)))
cat(sprintf("  nFeature: median=%.0f | pct.mt: median=%.2f%%, max=%.2f%%\n",
            median(seurat_obj$nFeature_RNA),
            median(seurat_obj$percent.mt), max(seurat_obj$percent.mt)))

# ── Step 5: Plot BEFORE ──
cat("Step 5: Plotting QC (before)...\n")
violin_data <- data.frame(
  nFeature_RNA = seurat_obj$nFeature_RNA, nCount_RNA = seurat_obj$nCount_RNA,
  percent.mt = seurat_obj$percent.mt, percent.ribo = seurat_obj$percent.ribo)
ggsave(file.path(fig_dir, "qc_violin_before.png"), plot_violin(violin_data, "BEFORE"),
       width = 20, height = 5, dpi = 150, bg = "white")

scatter_df <- data.frame(nFeature = seurat_obj$nFeature_RNA,
                          nCount = seurat_obj$nCount_RNA, pct_mt = seurat_obj$percent.mt)
p_scatter <- (ggplot(scatter_df, aes(x = nFeature, y = nCount)) +
  geom_point(size = 0.5, alpha = 0.3, color = "#5DADE2") +
  labs(x = "n_genes", y = "total_expr", title = "before") + theme_classic()) |
  (ggplot(scatter_df, aes(x = nFeature, y = pct_mt, color = pct_mt)) +
  geom_point(size = 0.5, alpha = 0.3) +
  scale_color_gradient2(low = "#313695", mid = "#FFFFBF", high = "#A50026", midpoint = 7.5) +
  geom_hline(yintercept = MAX_PCT_MT, color = "red", linetype = "dashed") +
  labs(x = "n_genes", y = "pct_mt (%)", title = "before") + theme_classic())
ggsave(file.path(fig_dir, "qc_scatter_before.png"), p_scatter,
       width = 14, height = 6, dpi = 150, bg = "white")

# ── Step 6: Filter cells ──
cat("Step 6: Filtering...\n")
n_before <- ncol(seurat_obj)
if (exists("filter_cells_by_qc")) {
  seurat_filtered <- filter_cells_by_qc(seurat_obj, min_features = MIN_GENES,
                                         max_features = MAX_GENES, max_mt_percent = MAX_PCT_MT)
} else {
  keep <- seurat_obj$nFeature_RNA >= MIN_GENES &
          seurat_obj$nFeature_RNA <= MAX_GENES &
          seurat_obj$percent.mt <= MAX_PCT_MT
  seurat_filtered <- subset(seurat_obj, cells = colnames(seurat_obj)[keep])
}
n_after <- ncol(seurat_filtered)

# ── Step 7: Gene filter ──
cat("Step 7: Gene filter...\n")
n_genes_before <- nrow(seurat_filtered)
data_mat <- GetAssayData(seurat_filtered, layer = "data")
genes_to_keep <- rownames(seurat_filtered)[Matrix::rowSums(data_mat > 0) >= GENE_MIN_CELLS]
seurat_filtered <- subset(seurat_filtered, features = genes_to_keep)
n_genes_after <- nrow(seurat_filtered)

# ── Step 8: Plot AFTER ──
cat("Step 8: Plotting QC (after)...\n")
violin_data_after <- data.frame(
  nFeature_RNA = seurat_filtered$nFeature_RNA, nCount_RNA = seurat_filtered$nCount_RNA,
  percent.mt = seurat_filtered$percent.mt, percent.ribo = seurat_filtered$percent.ribo)
ggsave(file.path(fig_dir, "qc_violin_after.png"), plot_violin(violin_data_after, "AFTER"),
       width = 20, height = 5, dpi = 150, bg = "white")

scatter_df_after <- data.frame(nFeature = seurat_filtered$nFeature_RNA,
                                nCount = seurat_filtered$nCount_RNA, pct_mt = seurat_filtered$percent.mt)
p_scatter_after <- (ggplot(scatter_df_after, aes(x = nFeature, y = nCount)) +
  geom_point(size = 0.5, alpha = 0.3, color = "#27AE60") +
  labs(x = "n_genes", y = "total_expr", title = "after") + theme_classic()) |
  (ggplot(scatter_df_after, aes(x = nFeature, y = pct_mt, color = pct_mt)) +
  geom_point(size = 0.5, alpha = 0.3) +
  scale_color_gradient2(low = "#313695", mid = "#FFFFBF", high = "#A50026", midpoint = 7.5) +
  geom_hline(yintercept = MAX_PCT_MT, color = "red", linetype = "dashed") +
  labs(x = "n_genes", y = "pct_mt (%)", title = "after") + theme_classic())
ggsave(file.path(fig_dir, "qc_scatter_after.png"), p_scatter_after,
       width = 14, height = 6, dpi = 150, bg = "white")

# ── Step 9: Group plots ──
meta_filtered <- seurat_filtered@meta.data
if ("age_group" %in% colnames(meta_filtered))
  ggsave(file.path(fig_dir, "qc_violin_by_age_group.png"),
         plot_violin_grouped(meta_filtered, "age_group"), width = 18, height = 5, dpi = 150, bg = "white")
if ("sample_id" %in% colnames(meta_filtered))
  ggsave(file.path(fig_dir, "qc_violin_by_sample.png"),
         plot_violin_grouped(meta_filtered, "sample_id"), width = 22, height = 5, dpi = 150, bg = "white")

# ── Step 10: Save ──
cat("Step 10: Saving...\n")
saveRDS(seurat_filtered, file.path(res_dir, "qc_filtered_seurat.rds"))
write.csv(meta_filtered, file.path(res_dir, "qc_metadata.csv"), row.names = FALSE)

qc_summary <- data.frame(
  metric = c("cells_before","cells_after","cells_removed","pct_removed",
             "genes_before","genes_after","n_genes_median","n_genes_min","n_genes_max",
             "pct_mt_median","pct_mt_max","n_count_median","pct_ribo_median"),
  value = c(n_before, n_after, n_before - n_after,
            round((n_before - n_after) / n_before * 100, 4),
            n_genes_before, n_genes_after,
            round(median(seurat_filtered$nFeature_RNA), 1),
            min(seurat_filtered$nFeature_RNA), max(seurat_filtered$nFeature_RNA),
            round(median(seurat_filtered$percent.mt), 2),
            round(max(seurat_filtered$percent.mt), 2),
            round(median(seurat_filtered$nCount_RNA), 1),
            round(median(seurat_filtered$percent.ribo), 2)))
write.csv(qc_summary, file.path(res_dir, "qc_summary.csv"), row.names = FALSE)

if ("sample_id" %in% colnames(meta_filtered)) {
  grp_cols <- if ("age_group" %in% colnames(meta_filtered)) c("sample_id","age_group") else "sample_id"
  per_sample <- meta_filtered %>% group_by(across(all_of(grp_cols))) %>%
    summarise(n_cells = n(), n_genes_median = round(median(nFeature_RNA), 0),
              n_genes_min = min(nFeature_RNA), n_genes_max = max(nFeature_RNA),
              pct_mt_median = round(median(percent.mt), 2),
              pct_mt_max = round(max(percent.mt), 2), .groups = "drop")
  write.csv(per_sample, file.path(res_dir, "qc_per_sample.csv"), row.names = FALSE)
}

params <- list(data_path = input_path, species = SPECIES, tissue = "skeletal_muscle",
               direction = "aging", data_state = ifelse(is_normalized, "NORMALIZED", "RAW"),
               is_normalized = is_normalized,
               filters = list(min_genes = MIN_GENES, max_genes = MAX_GENES,
                              max_pct_mt = MAX_PCT_MT, gene_min_cells = GENE_MIN_CELLS),
               skipped = c("n_counts_filter","doublet_detection","ambient_rna_removal"),
               skip_reason = "data is pre-normalized, raw counts unavailable",
               results = list(cells_before = n_before, cells_after = n_after,
                              cells_removed = n_before - n_after,
                              pct_removed = round((n_before - n_after)/n_before*100, 4),
                              genes_after = n_genes_after))
jsonlite::write_json(params, file.path(res_dir, "qc_params.json"), auto_unbox = TRUE, pretty = TRUE)

cat(sprintf("\nQC COMPLETE: %d -> %d cells, %d -> %d genes\n",
            n_before, n_after, n_genes_before, n_genes_after))
