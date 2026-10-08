#!/usr/bin/env Rscript
# monocle3_cross_version_bridge.R — 跨 R 小版本跑 Monocle3 的可复用模板
#
# 背景：monocle3 常只装在某个 R 小版本的库里，而那个 R 没有 Seurat；平台的 execute_r 内核
#       固定另一个 R。不要去重装包，用纯 RDS 桥接 + 用另一版本的 Rscript 绝对路径跑。
#
# 用法（两步，分别用两个 R 的 Rscript 调用）：
#   # ① 在 Seurat 所在的 R（通常是平台内核那版，如 R-4.5.3）
#   "C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe" monocle3_cross_version_bridge.R export
#   # ② 在装了 monocle3 的 R（如 R-4.4.2）——bash 里直调绝对路径，不要用 cmd //c 包装
#   "C:/Users/<user>/AppData/Local/R/R-4.4.2/bin/x64/Rscript.exe" monocle3_cross_version_bridge.R monocle
#
# 产出：data/traj_counts.rds|traj_meta.rds|traj_umap.rds、data/cds_full.rds、
#       results/pseudotime_full.csv、results/pseudotime_root_<name>.csv、figures/traj_*.png

BASE        <- "E:/MemOmics-Agent/results/<sid>"     # ← 改成会话目录
SEURAT_RDS  <- "E:/release/_memtest/data/MF_2000.rds"  # ← 改成输入 Seurat 对象
ASSAY       <- "RNA"; UMAP_NAME <- "umap"
N_DIM       <- 50; RES       <- 1e-4
ROOT_COL    <- "celltype";  ROOT_VAL <- "RSS"          # 根端细胞类型（人为指定，须在结论里声明）

MODE <- if (length(commandArgs(TRUE))) commandArgs(TRUE)[1] else "monocle"
setwd(BASE); set.seed(42)
dir.create("data", showWarnings = FALSE); dir.create("results", showWarnings = FALSE)
dir.create("figures", showWarnings = FALSE)

# ============================ ① export（跑在 Seurat 那侧）============================
if (MODE == "export") {
  suppressPackageStartupMessages(library(Seurat))
  obj <- readRDS(SEURAT_RDS); DefaultAssay(obj) <- ASSAY
  cnt <- GetAssayData(obj, assay = ASSAY, layer = "counts")
  saveRDS(cnt, "data/traj_counts.rds")
  saveRDS(obj@meta.data, "data/traj_meta.rds")
  saveRDS(Embeddings(obj, UMAP_NAME), "data/traj_umap.rds")
  cat("exported counts:", dim(cnt), " umap:", dim(Embeddings(obj, UMAP_NAME)), "\n")
  print(table(obj@meta.data[[ROOT_COL]]))
  quit(status = 0)
}

# ============================ ② monocle（跑在 monocle3 那侧）============================
suppressPackageStartupMessages({library(monocle3); library(ggplot2)})
# ⚠️ 不要 library(igraph)：igraph::clusters() 会遮蔽 monocle3::clusters()，
#    导致 partitions()/clusters() 报 "Must provide a graph object"。需要时用 igraph:: 前缀。

cnt <- readRDS("data/traj_counts.rds")
md  <- readRDS("data/traj_meta.rds")
um  <- readRDS("data/traj_umap.rds")
cat("loaded:", dim(cnt), "| R:", R.version.string, "\n")

build_cds <- function(cells) {
  cds <- new_cell_data_set(cnt[, cells, drop = FALSE], cell_metadata = md[cells, , drop = FALSE],
          gene_metadata = data.frame(gene_short_name = rownames(cnt), row.names = rownames(cnt)))
  cds <- preprocess_cds(cds, num_dim = N_DIM)              # 只取 Size_Factor + PCA
  cds@int_colData$reducedDims$UMAP <- um[cells, , drop = FALSE]   # 注入 Seurat UMAP
  cds
}
node_of_cell <- function(cds) {
  nodes <- igraph::V(principal_graph(cds)[["UMAP"]])$name
  cv <- as.matrix(cds@principal_graph_aux[["UMAP"]]$pr_graph_cell_proj_closest_vertex[colnames(cds), ])
  list(nodes = nodes, noc = nodes[as.numeric(cv[, 1])])
}
pick_max <- function(cds, col, val) { n <- node_of_cell(cds); names(which.max(table(n$noc[as.character(colData(cds)[[col]]) == val]))) }

cds <- build_cds(colnames(cnt))
for (r in c(1e-5, RES, 1e-3)) { t <- cluster_cells(cds, resolution = r)
  cat(sprintf("res=%.0e partitions=%d clusters=%d\n", r, length(unique(partitions(t))), length(unique(clusters(t))))) }
cds <- cluster_cells(cds, resolution = RES)
cds <- learn_graph(cds, use_partition = TRUE)
root <- pick_max(cds, ROOT_COL, ROOT_VAL); cat("root (", ROOT_COL, "=", ROOT_VAL, "max):", root, "\n")
cds <- order_cells(cds, root_pr_nodes = root)
saveRDS(cds, "data/cds_full.rds")   # annoy/hnsw warning 可忽略：order_cells/plot_cells 都能回读

pt <- pseudotime(cds)
write.csv(data.frame(cell = names(pt), pseudotime = as.numeric(pt),
                     celltype = md[names(pt), ROOT_COL], group = md[names(pt), "type"],
                     sample = md[names(pt), "samplename"]), "results/pseudotime_full.csv", row.names = FALSE)
for (col in intersect(c(ROOT_COL, "type", "annotation"), colnames(md))) {
  ggsave(file.path("figures", paste0("traj_full_", col, ".png")),
         plot_cells(cds, color_cells_by = col, label_groups_by_cluster = FALSE, label_leaves = FALSE,
                    label_branch_points = TRUE, graph_label_size = 2), width = 7, height = 6, dpi = 300)
}
ggsave("figures/traj_full_pseudotime.png",
       plot_cells(cds, color_cells_by = "pseudotime", label_cell_groups = FALSE, label_leaves = FALSE,
                  label_branch_points = TRUE, graph_label_size = 2), width = 7, height = 6, dpi = 300)

# ---- 闸① 多根枚举（在已保存的 cds 上做，不重跑 learn_graph）----
n <- node_of_cell(cds); cols <- as.data.frame(colData(cds))
pk <- function(mask) names(which.max(table(n$noc[mask])))
roots <- list(root_by_type = root,
              high_degree = n$nodes[which.max(igraph::degree(principal_graph(cds)[["UMAP"]]))],
              random_node = sample(n$nodes, 1))
for (v in unique(as.character(cols[[ROOT_COL]]))) roots[[paste0("max_", v)]] <- pk(cols[[ROOT_COL]] == v)
for (nm in names(roots)) {
  p <- pseudotime(order_cells(cds, root_pr_nodes = roots[[nm]]))
  write.csv(data.frame(cell = names(p), pseudotime = as.numeric(p)),
            file.path("results", paste0("pseudotime_root_", nm, ".csv")), row.names = FALSE)
  cat(sprintf("root %-16s -> %s\n", nm, roots[[nm]]))
}
cat("=== DONE ===\n")

# ---- 闸② 独立降维对照（不注入 Seurat UMAP，另跑一次本脚本的降维分支即可）----
# cds_i <- new_cell_data_set(cnt, cell_metadata = md,
#          gene_metadata = data.frame(gene_short_name = rownames(cnt), row.names = rownames(cnt)))
# cds_i <- preprocess_cds(cds_i, num_dim = N_DIM)
# cds_i <- reduce_dimension(cds_i, umap.metric = "cosine")
# cds_i <- cluster_cells(cds_i, resolution = RES); cds_i <- learn_graph(cds_i)
# cds_i <- order_cells(cds_i, root_pr_nodes = pick_max(cds_i, ROOT_COL, ROOT_VAL))
# write.csv(data.frame(cell = names(pseudotime(cds_i)), pseudotime_indep = as.numeric(pseudotime(cds_i))),
#           "results/pseudotime_indepUMAP.csv", row.names = FALSE)