#' MemOmics — Seurat QC Pipeline (Fixed: bypass Read10X)
library(Seurat)
library(ggplot2)
library(patchwork)
library(dplyr)
library(Matrix)

base_dir <- "E:/MemOmics-Agent/hermes-agent/results/基础分析/Seurat_QC"
mtx_dir  <- file.path(base_dir, "data", "mtx")
fig_dir  <- file.path(base_dir, "figures")
res_dir  <- file.path(base_dir, "results")

dir.create(fig_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(res_dir, showWarnings = FALSE, recursive = TRUE)

cat("═══ Step 1: Reading MTX (manual) ═══\n")
mat <- readMM(file.path(mtx_dir, "matrix.mtx"))
genes <- readLines(file.path(mtx_dir, "features.tsv"))
barcodes <- readLines(file.path(mtx_dir, "barcodes.tsv"))
# Extract gene symbols (2nd column)
gene_sym <- sapply(strsplit(genes, "\t"), function(x) x[2])
rownames(mat) <- gene_sym
colnames(mat) <- barcodes
mat <- as(mat, "CsparseMatrix")
cat(sprintf("  Matrix: %d genes x %d cells\n", nrow(mat), ncol(mat)))

cat("\n═══ Step 2: Create Seurat Object ═══\n")
obj <- CreateSeuratObject(counts = mat, project = "Muscle_Aging_60k", min.cells = 3, min.features = 200)
cat(sprintf("  Cells: %d, Genes: %d\n", ncol(obj), nrow(obj)))

cat("\n═══ Step 3: Add Metadata ═══\n")
meta <- read.csv(file.path(mtx_dir, "metadata.csv"), row.names = 1, check.names = FALSE)
common <- intersect(colnames(obj), rownames(meta))
cat(sprintf("  Overlapping cells: %d / %d\n", length(common), ncol(obj)))
for (col in colnames(meta)) {
  if (!col %in% colnames(obj[[]])) {
    obj <- AddMetaData(obj, metadata = meta[colnames(obj), col, drop = FALSE], col.name = col)
  }
}

cat("\n═══ Step 4: QC ═══\n")
obj[["percent.mt"]] <- PercentageFeatureSet(obj, pattern = "^MT-")
obj[["percent.ribo"]] <- PercentageFeatureSet(obj, pattern = "^RP[SL]")
cat(sprintf("  Before QC: %d cells\n", ncol(obj)))

# QC violin (pre-filter)
p_qc <- VlnPlot(obj, features = c("nFeature_RNA", "nCount_RNA", "percent.mt", "percent.ribo"),
                ncol = 4, pt.size = 0.1) & theme(axis.text.x = element_text(angle = 45, hjust = 1))
ggsave(file.path(fig_dir, "01_qc_violin_pre.png"), p_qc, width = 12, height = 4, dpi = 150)

# Filter
obj <- subset(obj, subset = nFeature_RNA > 200 & nFeature_RNA < 6000 & percent.mt < 15)
cat(sprintf("  After QC: %d cells\n", ncol(obj)))

cat("\n═══ Step 5: SCTransform ═══\n")
options(future.globals.maxSize = 4000 * 1024^2)
library(future)
plan(sequential)
options(future.globals.maxSize = 4000 * 1024^2)
library(future)
plan(sequential)
obj <- SCTransform(obj, vst.flavor = "v2", ncells = 2000, vars.to.regress = "percent.mt", conserve.memory = TRUE, verbose = FALSE)
cat("  SCTransform done\n")

cat("\n═══ Step 6: PCA + UMAP ═══\n")
obj <- RunPCA(obj, npcs = 50, verbose = FALSE)
obj <- RunUMAP(obj, dims = 1:30, verbose = FALSE)
cat("  PCA + UMAP done\n")

# Elbow plot
p_elbow <- ElbowPlot(obj, ndims = 50)
ggsave(file.path(fig_dir, "02_elbow_plot.png"), p_elbow, width = 6, height = 4, dpi = 150)

cat("\n═══ Step 7: Clustering ═══\n")
obj <- FindNeighbors(obj, dims = 1:30, verbose = FALSE)
obj <- FindClusters(obj, resolution = 0.5, verbose = FALSE)
cat(sprintf("  Clusters: %d\n", length(unique(obj$seurat_clusters))))

# UMAP plots
p_umap_cluster <- DimPlot(obj, reduction = "umap", group.by = "seurat_clusters", label = TRUE) + ggtitle("UMAP - Clusters")
p_umap_age <- DimPlot(obj, reduction = "umap", group.by = "age") + ggtitle("UMAP - Age")
p_umap_celltype <- if ("celltype" %in% colnames(obj[[]])) {
  DimPlot(obj, reduction = "umap", group.by = "celltype", label = TRUE, repel = TRUE) + ggtitle("UMAP - Cell Type")
} else { NULL }

ggsave(file.path(fig_dir, "03_umap_clusters.png"), p_umap_cluster, width = 8, height = 6, dpi = 150)
ggsave(file.path(fig_dir, "04_umap_age.png"), p_umap_age, width = 8, height = 6, dpi = 150)
if (!is.null(p_umap_celltype)) {
  ggsave(file.path(fig_dir, "05_umap_celltype.png"), p_umap_celltype, width = 10, height = 8, dpi = 150)
}

cat("\n═══ Step 8: Save Results ═══\n")
saveRDS(obj, file.path(res_dir, "seurat_obj_qc.rds"))
# Cluster summary
cluster_summary <- obj@meta.data %>%
  group_by(seurat_clusters) %>%
  summarise(n_cells = n(), .groups = "drop")
write.csv(cluster_summary, file.path(res_dir, "cluster_summary.csv"), row.names = FALSE)
# Cell type x age table
if ("celltype" %in% colnames(obj[[]]) && "age" %in% colnames(obj[[]])) {
  ct_age <- table(obj$celltype, obj$age)
  write.csv(ct_age, file.path(res_dir, "celltype_age_table.csv"))
}

cat("\n═══ DONE! ═══\n")
cat(sprintf("Figures saved to: %s\n", fig_dir))
cat(sprintf("Results saved to: %s\n", res_dir))
cat(sprintf("Total figures: %d\n", length(list.files(fig_dir, pattern="\.png$"))))
