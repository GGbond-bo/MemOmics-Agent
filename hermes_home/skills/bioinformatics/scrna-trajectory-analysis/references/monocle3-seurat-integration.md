# Monocle3 + Seurat 集成深度原理

## 为什么绝不能用 Monocle3 的 `reduce_dimension()`

### 两条路径的数学差异

```
Seurat 路径 (正确):
  counts → SCTransform (正则化负二项回归) → Pearson residuals → PCA (50PCs) → Harmony (批次校正) → UMAP

Monocle3 路径 (错误):
  counts → estimateSizeFactors → log(sf_normalized + 1) → PCA → UMAP
```

### 三步走的问题

**1. 归一化差异**

`log(sf_normalized + 1)` 保留了测序深度信号。低测序深度的细胞在 PCA 空间聚在一起，UMAP 的第一主成分往往是测序深度而非生物学差异。

SCTransform 用正则化负二项回归建模 `expression ~ log(UMI) + ...`，取 Pearson residuals 作为"去除了测序深度后还剩多少信号"。

**2. PCA 输入不同**

SCTransform → residuals → PCA：每个 PC 捕获的都是生物学方差（基因表达模式差异）。

`log(norm+1)` → PCA：前几个 PC 捕获的是测序深度 + 低表达基因噪声。

**3. 批次校正缺失**

Monocle3 的 `align_cds()` 用的是简单 CCA（无正则化），无法处理大样本量的复杂批次效应。

Harmony 用 soft-clustering + maximum diversity clustering，在 PCA 空间迭代校正批次效应。

### 实验证据

在 26 样本骨骼肌衰老数据集上：
- Seurat Harmony UMAP：青年/老年样本充分混合，纤维类型分离清晰
- Monocle3 UMAP：样本按批次分离，青年/老年混在批次 cluster 里

### 结论

> 有 SCTransform + Harmony 的 Seurat UMAP 是数据最好的低维表示。
> Monocle3 轨迹图必须建立在这个 UMAP 上。

## `as.cell_data_set()` 内部行为（Monocle3 ≥ 1.3）

```r
# 等效内部逻辑
cds <- new_cell_data_set(
  expression_data = GetAssayData(seurat_obj, assay = "RNA", slot = "counts"),
  cell_metadata = seurat_obj@meta.data
)

# 遍历所有 reduction，逐个拷贝到 cds@int_colData$reducedDims
for (reduc in names(seurat_obj@reductions)) {
  cds@int_colData$reducedDims[[reduc]] <- Embeddings(seurat_obj, reduc)
}

# Idents → colData(cds)$cluster
colData(cds)$cluster <- Idents(seurat_obj)
```

### 不会带的

- Harmony 嵌入（`reductions$harmony`）— 但不需要，UMAP 已经是 Harmony 校正后的
- SCTransform 模型（`@commands$SCTransform`）
- Graphs（`@graphs`）

## UMAP 覆盖后的恢复

如果你不小心跑了 `reduce_dimension()`：

```r
# 1. 恢复 Seurat UMAP
cds@int_colData$reducedDims$UMAP <- Embeddings(seurat_obj, "umap")[colnames(cds), ]

# 2. 重建所有下游
cds <- cluster_cells(cds, resolution = 1e-4)
cds <- learn_graph(cds)
# 3. 重新 order_cells、graph_test 等
```

## 验证脚本

```r
# 确认 CDS UMAP = Seurat UMAP
umap_cds <- cds@int_colData$reducedDims$UMAP
umap_seurat <- Embeddings(seurat_obj, "umap")

stopifnot(all(rownames(umap_cds) %in% rownames(umap_seurat)))
stopifnot(all(abs(umap_cds - umap_seurat[rownames(umap_cds), ]) < 1e-10))

cat("✅ CDS UMAP = Seurat UMAP\n")
```
