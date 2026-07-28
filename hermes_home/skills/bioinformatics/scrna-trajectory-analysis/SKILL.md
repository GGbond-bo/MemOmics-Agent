---
name: scrna-trajectory-analysis
description: "单细胞轨迹推断/拟时序分析：Monocle3 (R)、Slingshot (R)、scVelo RNA velocity (Python)、CellRank 命运映射 (Python)。从 Seurat/Scanpy 对象链接。"
when_to_use: "[trajectory-analysis] scRNA-seq 轨迹推断/拟时序分析/RNA velocity/发育分化。使用场景：已聚类的 scRNA-seq 数据，需重建发育/衰老/分化轨迹，伪时间排序，RNA velocity 分析。"
version: 1.1.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [trajectory, pseudotime, monocle3, slingshot, scvelo, rna-velocity, cellrank, cell-fate, 03_高级分析]
    difficulty: advanced
    languages: [R, Python]
    category: scRNA
prerequisites:
  r_packages:
    - monocle3
    - Seurat
    - slingshot
    - tradeSeq
    - SingleCellExperiment
    - SummarizedExperiment
  python_packages:
    - scvelo
    - scanpy
    - cellrank
    - anndata
    - numpy
    - pandas
    - matplotlib
---

# Trajectory Analysis — 轨迹推断全流程

本 skill 覆盖 4 种轨迹推断方法，按用户数据格式和需求选择对应路径。

## 方法选择决策树

```
用户数据格式？
  ├─ Seurat 对象 (R) ──→ 路径 A: Monocle3  或  路径 B: Slingshot + tradeSeq
  └─ AnnData 对象 (Python) ──→ 路径 C: scVelo  RNA velocity  或  路径 D: CellRank 命运映射

已有注释好的 Seurat 对象？
  └─ 是 → 跳过重新降维，用 Seurat 的 UMAP + 注释 → 路径 A 或 B
```

---

## 📌 通用铁律（所有路径适用）

| 规则 | 说明 |
|------|------|
| **已有 Seurat 注释 → 不跑 Monocle3 的 preprocess_cds/reduce_dimension** | `as.cell_data_set()` 自带 Seurat 的 PCA/UMAP/注释 |
| **先用 Seurat UMAP 建轨迹** | Monocle3 的 `reduce_dimension()` 只有简单 PCA→UMAP，没有 SCTransform/Harmony |
| **>100K 细胞先 subset** | `learn_graph()` 复杂度 O(n²)，>60K 细胞会卡死 |
| **有大分支才做分支分析** | 衰老数据通常线性（Young→Old），不一定有分叉；发育数据（干细胞→多种终末细胞）才有明显分叉 |

### 🔬 为什么绝不能用 Monocle3 UMAP？

| 维度 | Seurat UMAP | Monocle3 UMAP |
|------|------------|---------------|
| 归一化 | SCTransform residuals（正则化负二项） | `log(size_factor_norm + 1)` |
| 批次校正 | Harmony 已校正 | 无 / 简单 CCA（无正则化） |
| 技术噪声 | 已去除 | 保留（低深度细胞聚在一起） |
| 与注释一致性 | 一致 | 不一致（重新聚类，注释无处可放） |

**核心原理**：SCTransform 用正则化负二项回归将测序深度信号与生物学方差分离，提取 Pearson residuals 进 PCA→Harmony→UMAP。Monocle3 的 `log(norm+1) → PCA → UMAP` 保留了测序深度作为主信号，UMAP 空间被技术变量主导。在这个空间上建的轨迹图反映的是测序深度梯度，不是生物学轨迹。

---

## 路径 A: Monocle3（R，推荐 — Seurat 对象直接使用）

### 适用场景
- 已有注释好的 Seurat 对象
- 需要伪时间排序 + 轨迹图
- 数据量 < 100K 细胞（建议 subset 到 30-60K）

### `as.cell_data_set()` 自动带过来什么

| Seurat 内容 | CDS 中的位置 | 自动？ |
|------------|-------------|:---:|
| `counts` (RNA assay) | `counts(cds)` | ✅ |
| `reductions$pca` | `cds@int_colData$reducedDims$PCA` | ✅ |
| `reductions$umap` | `cds@int_colData$reducedDims$UMAP` | ✅ |
| `meta.data` | `colData(cds)` | ✅ |
| `Idents()` | `colData(cds)$cluster` | ✅ |

### 标准流程

```r
library(monocle3)
library(Seurat)
library(dplyr)

# ==== Step 1: 加载 Seurat + subset ====
seurat_obj <- readRDS("你的seurat对象.rds")
set.seed(42)
seurat_sub <- subset(seurat_obj, cells = sample(Cells(seurat_obj), 60000))

# ==== Step 2: Seurat → CDS (PCA+UMAP+注释 自动带入) ====
cds <- as.cell_data_set(seurat_sub)

# 验证 UMAP 来自 Seurat
"UMAP" %in% names(cds@int_colData$reducedDims)  # 应返回 TRUE

# ==== Step 3: 聚类 + 学习轨迹图 ⚠️ 跳过 preprocess_cds/reduce_dimension ====
# cluster_cells 内部调用 monocle3:::cluster_cells_umap_coords()，只依赖 UMAP
cds <- cluster_cells(cds, resolution = 1e-4)
cds <- learn_graph(cds)

# ==== Step 4: 可视化 ====
plot_cells(cds, color_cells_by = "cell_type",    # 你的 Seurat 注释列名
           label_groups_by_cluster = FALSE,
           label_leaves = TRUE,
           label_branch_points = TRUE,
           graph_label_size = 1.5)

# ==== Step 5: 伪时间排序（编程式指定根节点）====
get_earliest_principal_node <- function(cds, group_col, group_val) {
  cell_ids <- which(colData(cds)[, group_col] == group_val)
  closest_vertex <- as.matrix(
    cds@principal_graph_aux[["UMAP"]]$pr_graph_cell_proj_closest_vertex[colnames(cds), ]
  )
  root_node <- igraph::V(principal_graph(cds)[["UMAP"]])$name[
    as.numeric(names(which.max(table(closest_vertex[cell_ids, ]))))
  ]
  root_node
}

cds <- order_cells(cds, root_pr_nodes = get_earliest_principal_node(cds, "condition", "Young"))

plot_cells(cds, color_cells_by = "pseudotime",
           label_cell_groups = FALSE, label_leaves = TRUE,
           label_branch_points = TRUE, graph_label_size = 1.5)

# ==== Step 6: 轨迹差异表达 ====
pr_test_res <- graph_test(cds, neighbor_graph = "principal_graph", cores = 8)
pr_deg_ids <- row.names(subset(pr_test_res, q_value < 0.05))

# 共表达模块 + 热图
gene_module_df <- find_gene_modules(cds[pr_deg_ids, ], resolution = 1e-3)
cell_group_df <- tibble::tibble(
  cell = row.names(colData(cds)),
  cell_group = colData(cds)$cell_type
)
agg_mat <- aggregate_gene_expression(cds, gene_module_df, cell_group_df)
row.names(agg_mat) <- stringr::str_c("Module ", row.names(agg_mat))
pheatmap::pheatmap(agg_mat, scale = "column", clustering_method = "ward.D2")

# 单个基因沿伪时间表达
plot_cells(cds, genes = c("MYH7", "MYH1", "TNNT1"),
           show_trajectory_graph = FALSE, label_cell_groups = FALSE)
```

### Monocle3 常见坑

| 坑 | 解法 |
|---|---|
| Seurat UMAP 被 `reduce_dimension()` 覆盖 | 坚决不跑 `reduce_dimension()`；已覆盖时：`cds@int_colData$reducedDims$UMAP <- Embeddings(seurat_sub, "umap")[colnames(cds), ]` |
| `learn_graph()` 卡死 | 细胞 >60K → subset |
| `order_cells()` "no root node" | 用 `get_earliest_principal_node()` |
| partition 太碎 | `cluster_cells(resolution=1e-4)` |
| `as.cell_data_set()` deprecated 警告 | 正常，忽略 |
| PCA 缺失但 UMAP 存在 | `preprocess_cds(num_dim=50)` 再覆盖 UMAP |
| 知乎代码的手动替换 UMAP | 仅 Monocle3 < 1.3 需要；v1.3+ 自动带 UMAP |

---

## 路径 B: Slingshot (R，复杂分叉轨迹)

```r
library(slingshot); library(tradeSeq); library(SingleCellExperiment); library(Seurat)

sce <- as.SingleCellExperiment(seurat_sub)
sce <- slingshot(sce, clusterLabels = "cell_type", reducedDim = "UMAP", start.clus = "Satellite_Cell")

# 可视化
colors <- rainbow(length(unique(sce$cell_type)))
plot(reducedDims(sce)$UMAP, col = colors[sce$cell_type], pch = 16, cex = 0.5)
lines(SlingshotDataSet(sce), lwd = 2, col = "black")

# tradeSeq 分叉差异表达
sce <- fitGAM(sce, nknots = 6)
asso_res <- associationTest(sce)
```

---

## 路径 C: scVelo RNA velocity (Python)

```python
import scvelo as scv; import scanpy as sc

adata = sc.read_h5ad("your_data.h5ad")
scv.pp.filter_and_normalize(adata, min_shared_counts=20, n_top_genes=2000)
scv.pp.moments(adata, n_pcs=30, n_neighbors=30)
scv.tl.recover_dynamics(adata)
scv.tl.velocity(adata, mode="dynamical")
scv.tl.velocity_graph(adata)
scv.pl.velocity_embedding_stream(adata, basis="umap", color="cell_type")
scv.tl.velocity_pseudotime(adata)
```

---

## 路径 D: CellRank 命运映射 (Python)

```python
import cellrank as cr; import scvelo as scv

vk = cr.kernels.VelocityKernel(adata)
ck = cr.kernels.ConnectivityKernel(adata)
combined_kernel = 0.8 * vk + 0.2 * ck

g = cr.estimators.GPCCA(combined_kernel)
g.fit(cluster_key="cell_type")
g.compute_schur(n_components=20)
g.compute_macrostates(n_states=5, cluster_key="cell_type")
g.compute_fate_probabilities()
g.plot_fate_probabilities(same_plot=False, basis="umap")
```

---

## 常见问题排查

| 问题 | 原因 | 解法 |
|------|------|------|
| `as.cell_data_set()` "not a Seurat object" | Seurat v5 格式 | 升级 monocle3 |
| `learn_graph()` 轨迹乱线 | resolution 太大 | `cluster_cells(1e-5)` |
| 伪时间方向反向 | 根节点选错 | 改 `group_val` |
| `graph_test()` 全不显著 | 细胞太少 | 每分支 ≥200 cells |
| scVelo `recover_dynamics` 慢 | 基因太多 | `n_top_genes=2000` |

## 输出目录结构

```
results/trajectory_monocle3_{date}/
├── figures/
│   ├── trajectory_celltype.png
│   ├── trajectory_pseudotime.png
│   └── module_heatmap.png
├── results/
│   ├── graph_test_results.csv
│   └── pseudotime.csv
├── scripts/
│   └── monocle3_analysis.R
└── data/
    └── cds.rds
```
