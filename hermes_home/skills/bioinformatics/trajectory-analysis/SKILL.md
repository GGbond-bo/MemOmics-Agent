---
name: trajectory-analysis
description: "单细胞轨迹推断/拟时序分析：Monocle3 (R)、Slingshot (R)、scVelo RNA velocity (Python)、CellRank 命运映射 (Python)。从 Seurat/Scanpy 对象链接。"
when_to_use: "[trajectory-analysis] scRNA-seq 轨迹推断/拟时序分析/RNA velocity/发育分化。使用场景：已聚类的 scRNA-seq 数据，需重建发育/衰老/分化轨迹，伪时间排序，RNA velocity 分析。"
version: 1.0.0
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
| **用 `new_cell_data_set()` 手动构建 → 跑 `preprocess_cds()` 拿 Size_Factor/PCA → 跳过 `align_cds()` 和 `reduce_dimension()` → 注入 Seurat UMAP** | Monocle3 v1.4.x 没有 `as.cell_data_set()`，只能用 `new_cell_data_set()` |
| **跑 `preprocess_cds()` 但不跑 `align_cds()`** | `preprocess_cds()` 提供 Size_Factor + PCA（后续 `graph_test()` 需要）；`align_cds()` 的 CCA 弱于 Harmony，再跑会洗掉 Seurat 的 Harmony 校正 |
| **不跑 `reduce_dimension()`** | Monocle3 的 UMAP 只有简单 PCA→UMAP，没有 SCTransform/Harmony；用 Seurat 的 UMAP 替代 |
| **>100K 细胞先 subset** | `learn_graph()` 复杂度 O(n²)，>60K 细胞会卡死 |
| **有大分支才做分支分析** | 衰老数据通常线性（Young→Old），不一定有分叉；发育数据（干细胞→多种终末细胞）才有明显分叉 |

---

## 路径 A: Monocle3（R，推荐 — Seurat 对象直接使用）

### 适用场景
- 已有注释好的 Seurat 对象
- 需要伪时间排序 + 轨迹图
- 数据量 < 100K 细胞（建议 subset 到 30-60K）

### 标准流程

> ⚠️ **Monocle3 v1.4.x 没有 `as.cell_data_set()`**，用 `new_cell_data_set()` 手动构建 + `preprocess_cds()` 拿 PCA + 跳过 `align_cds()` 和 `reduce_dimension()` + 注入 Seurat Harmony-UMAP。

```r
library(monocle3)
library(Seurat)
library(dplyr)

# ==== Step 1: 加载 Seurat + subset ====
seurat_obj <- readRDS("你的seurat对象.rds")
set.seed(42)
seurat_sub <- subset(seurat_obj, cells = sample(Cells(seurat_obj), 60000))

# ==== Step 2: 手动构建 CDS（v1.4.x 唯一方式）====
cds <- new_cell_data_set(
    expression_data = GetAssayData(seurat_sub, assay = "RNA", layer = "counts"),
    cell_metadata   = seurat_sub@meta.data,
    gene_metadata   = data.frame(
        gene_short_name = rownames(seurat_sub),
        row.names       = rownames(seurat_sub)
    )
)

# ==== Step 3: 跑 PCA（拿 Size_Factor + 降维基座），跳过 align_cds ====
cds <- preprocess_cds(cds, num_dim = 50)
# ⚠️ 不跑 align_cds() — Harmony 已做校正，CCA 会洗掉
# ⚠️ 不跑 reduce_dimension() — Monocle3 UMAP 没有 SCTransform/Harmony

# ==== Step 4: ⭐ 注入 Seurat 的 Harmony-UMAP ====
cds@int_colData$reducedDims$UMAP <- Embeddings(seurat_sub, "umap")[colnames(cds), ]

# ==== Step 5: 聚类 + 学习轨迹图 ====
cds <- cluster_cells(cds, resolution = 1e-4)
cds <- learn_graph(cds)

# ==== Step 6: 可视化 ====
plot_cells(cds, color_cells_by = "cell_type",    # 你的 Seurat 注释列名
           label_groups_by_cluster = FALSE,
           label_leaves = TRUE,
           label_branch_points = TRUE,
           graph_label_size = 1.5)

# ==== Step 7: 伪时间排序 ====
# 以某个分组（如 Young）细胞最多的节点为根
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

# 伪时间着色
plot_cells(cds, color_cells_by = "pseudotime",
           label_cell_groups = FALSE, label_leaves = TRUE,
           label_branch_points = TRUE, graph_label_size = 1.5)

# ==== Step 8: 轨迹差异表达（随时间变化的基因）====
pr_test_res <- graph_test(cds, neighbor_graph = "principal_graph", cores = 8)
pr_deg_ids <- row.names(subset(pr_test_res, q_value < 0.05))

# 找共表达模块 + 热图
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
           show_trajectory_graph = FALSE,
           label_cell_groups = FALSE)

# ==== Step 9: 分叉分析（如果有多分叉）====
# cds_sub <- choose_graph_segments(cds)  # 交互式选分叉
# pr_deg_branch <- graph_test(cds_sub, neighbor_graph = "principal_graph")
```

### Monocle3 常见坑

| 坑 | 解法 |
|---|---|
| `as.cell_data_set()` 不存在 | Monocle3 v1.4.x 已移除，必须用 `new_cell_data_set()` 手动构建 CDS |
| `preprocess_cds()` 和 `reduce_dimension()` 覆盖了 Seurat UMAP | 跑 `preprocess_cds()`（拿 Size_Factor + PCA）但**不跑** `reduce_dimension()`；跑完后用 `cds@int_colData$reducedDims$UMAP <- Embeddings(seurat_sub, "umap")[colnames(cds), ]` 盖回 Seurat Harmony-UMAP |
| `align_cds()` 洗掉 Harmony 校正 | **不要跑** `align_cds()`；Monocle3 的 CCA 校正弱于 Harmony，在 Harmony UMAP 上直接建轨迹即可 |
| `learn_graph()` 卡死 | 细胞太多（>60K）→ subset |
| `order_cells()` 报错 "no root node" | 用 `get_earliest_principal_node()` 编程式指定根 |
| partition 太碎（多个独立轨迹）| `cluster_cells(resolution=1e-4)` 调小 |
| `new_cell_data_set()` 构建后 `graph_test()` 报错缺 Size_Factor | 必须跑 `preprocess_cds()` — 它生成 `Size_Factor` 列，Monocle3 内部很多函数依赖它 |

### 步骤对照表（Monocle3 v1.4.x）

| 步骤 | 函数 | 跑不跑 | 理由 |
|------|------|:---:|------|
| 构建 CDS | `new_cell_data_set()` | ✅ | v1.4.x 唯一方式，传入 counts + metadata + gene_metadata |
| PCA + Size_Factor | `preprocess_cds()` | ✅ | 生成内部状态（`graph_test()` 等依赖），不跑会报错 |
| 批次校正 | `align_cds()` | ❌ | CCA 弱于 Harmony，会洗掉 Seurat 的校正结果 |
| UMAP 降维 | `reduce_dimension()` | ❌ | 没有 SCTransform/Harmony，质量低于 Seurat UMAP |
| 注入 UMAP | `cds@int_colData$reducedDims$UMAP <- ...` | ✅ | 一行代码注入 Seurat Harmony-UMAP |

---

## 路径 B: Slingshot (R，适合复杂分叉轨迹)

### 适用场景
- 已有 Seurat 对象的 UMAP 降维
- 预期有多个分叉/分支点
- 需要 tradeSeq 做分叉差异表达

### 标准流程

```r
library(slingshot)
library(tradeSeq)
library(SingleCellExperiment)
library(Seurat)

# ==== 1. Seurat → SingleCellExperiment ====
sce <- as.SingleCellExperiment(seurat_sub)

# ==== 2. Slingshot 轨迹推断 ====
# 用 UMAP 降维，指定起始 cluster
sce <- slingshot(sce, 
                 clusterLabels = "cell_type",     # 你的注释列
                 reducedDim = "UMAP",             # 用 Seurat UMAP
                 start.clus = "Satellite_Cell")   # 干细胞为起始

# 提取伪时间
pseudotime_values <- slingPseudotime(sce)

# ==== 3. 可视化 ====
colors <- rainbow(length(unique(sce$cell_type)))
plot(reducedDims(sce)$UMAP, col = colors[sce$cell_type], pch = 16, cex = 0.5)
lines(SlingshotDataSet(sce), lwd = 2, col = "black")

# ==== 4. tradeSeq 分叉差异表达 ====
# 找分叉点的差异基因
counts <- counts(sce)
counts <- as.matrix(counts[rowSums(counts) > 10, ])  # 过滤低表达

# fit GAM
sce <- fitGAM(sce, nknots = 6)

# 全局检验：哪些基因沿轨迹变化
asso_res <- associationTest(sce)
asso_sig <- rownames(asso_res)[asso_res$pvalue < 0.05]

# 分叉点检验
start_res <- startVsEndTest(sce)
# 热图
plotSmoothers(sce, assays(sce)$counts, gene = asso_sig[1:20])
```

---

## 路径 C: scVelo RNA velocity (Python)

### 适用场景
- 有 spliced/unspliced 计数
- 需要推断细胞方向性（RNA velocity 有方向，伪时间没有）
- 数据格式为 AnnData / h5ad

### 标准流程

```python
import scvelo as scv
import scanpy as sc

# ==== 1. 加载数据 ====
adata = sc.read_h5ad("your_data.h5ad")

# ==== 2. 预处理 ====
scv.pp.filter_and_normalize(adata, min_shared_counts=20, n_top_genes=2000)
scv.pp.moments(adata, n_pcs=30, n_neighbors=30)

# ==== 3. RNA velocity 计算 ====
scv.tl.recover_dynamics(adata)
scv.tl.velocity(adata, mode="dynamical")
scv.tl.velocity_graph(adata)

# ==== 4. 可视化 ====
scv.pl.velocity_embedding_stream(adata, basis="umap", color="cell_type")
scv.pl.velocity_embedding(adata, basis="umap", arrow_length=2, arrow_size=1.5)

# ==== 5. 伪时间（velocity pseudotime）====
scv.tl.velocity_pseudotime(adata)
scv.pl.scatter(adata, color="velocity_pseudotime", basis="umap")
```

---

## 路径 D: CellRank 命运映射 (Python)

### 适用场景
- 已有 RNA velocity（scVelo 输出）
- 需要推断终末状态概率
- 发育/分化数据

### 标准流程

```python
import cellrank as cr
import scvelo as scv

# ==== 1. 先跑 scVelo velocity ====
# （参考路径 C）

# ==== 2. CellRank 初始化 ====
vk = cr.kernels.VelocityKernel(adata)
ck = cr.kernels.ConnectivityKernel(adata)
combined_kernel = 0.8 * vk + 0.2 * ck

# ==== 3. 估算终末状态 ====
g = cr.estimators.GPCCA(combined_kernel)
g.fit(cluster_key="cell_type")
g.compute_schur(n_components=20)
g.compute_macrostates(n_states=5, cluster_key="cell_type")

# 可视化
g.plot_macrostates(which="all", basis="umap", title="Macrostates")

# ==== 4. 命运概率 ====
g.compute_fate_probabilities()
g.plot_fate_probabilities(same_plot=False, basis="umap")

# ==== 5. 基因沿命运轨迹的趋势 ====
driver_genes = g.compute_lineage_drivers(lineages="0")
g.plot_lineage_drivers(lineage="0", n_genes=5)
```

---

## 输出目录结构

```
results/trajectory_monocle3_{date}/
├── figures/
│   ├── trajectory_celltype.png
│   ├── trajectory_pseudotime.png
│   ├── module_heatmap.png
│   └── gene_expression_facets.png
├── results/
│   ├── graph_test_results.csv
│   └── pseudotime.csv
├── scripts/
│   └── monocle3_analysis.R
└── data/
    └── cds.rds
```

---

## 常见问题排查

| 问题 | 原因 | 解法 |
|------|------|------|
| Monocle3 没有 `as.cell_data_set()` | v1.4.x 已移除该函数 | 用 `new_cell_data_set()` 手动构建 CDS，然后 `preprocess_cds()` + 注入 Seurat UMAP |
| `learn_graph()` 后轨迹图是一团乱线 | resolution 太大 → partition 太碎 | `cluster_cells(resolution=1e-5)` |
| 伪时间值和生物学方向相反 | 根节点选错了 | 把 `group_val` 参数改成预期的起点组 |
| `graph_test()` 结果全部不显著 | 轨迹太短或细胞太少 | 每个分支至少 200 个细胞 |
| scVelo `recover_dynamics` 耗时过长 | 基因数太多 | `n_top_genes=2000` |


---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="轨迹推断结果 —— {样本}",
     context="方法: {Monocle3/Slingshot/scVelo} | 参数: 根节点={root} | 结果: {n}个分支",
     knowledge_base_info=<KB内容>,
   )
   辩论: 轨迹方向跟生物学一致吗？根节点选对了吗？分支点有意义吗？
3. save_conclusions(module="03_advanced", topic="Trajectory", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
