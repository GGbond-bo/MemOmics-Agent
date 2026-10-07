# TileMatrix 样本级聚合（跨物种 L2 可及性比对的输入矩阵制备）

> 适用：给「人/猴跨物种染色质可及性 L2 比对」制备 `samples × tiles` 覆盖比例矩阵时。
> 上游：ArchR 项目按样本 subset 后 `getMatrixFromProject(useMatrix="TileMatrix", binarize=TRUE)`。
> 核心结论：跨物种 L2 比对用的 tile 矩阵必须是**样本级覆盖比例**（`Matrix::colMeans` 得 0~1），不是 cell 级矩阵、不是覆盖细胞计数。两物种还要用**同一套 500bp tile 网格**才能逐列对齐。

## 口径铁律：样本级 = colMeans 覆盖比例（0~1），不是计数

实测猴侧矩阵 `monkey_tile_matrix_samples_x_tiles.rds`（20 样本 × 6,085,841 tile，dgCMatrix）：

| 观察 | 数值 | 含义 |
|---|---|---|
| 值域 | 6.19e-05 ~ 0.9988 | **0~1 覆盖比例**，不是整数计数 |
| 最小非零值 | 6.19e-05 ≈ 1/16161 | = 1 个细胞覆盖 / 该样本细胞总数 → colMeans |
| 每样本非零 tile 数 | 368万 ~ 556万 | 稀疏 |

→ 判据：值域落在 [0,1] 且 max ≤ 1 = `Matrix::colMeans` 聚合结果（每个 tile 被该样本多少比例的细胞覆盖）。若值是整数 = `rowSums/colSums` 覆盖细胞计数，**口径错误**，不能和猴侧直接比。

## 坑：`saveRDS(assay(se_sample))` 存的是 cell 级矩阵 → 爆内存

用户给的原始人脑提取代码每个样本存 `assay(se_sample)`（cells × tiles），单样本就 200M，40 样本 8GB，最后 cbind 成几十万细胞 × 600万 tile 必撞内存/2^31 上限。

**根因**：`getMatrixFromProject` 返回的 `SummarizedExperiment` 的 `assay()` 是**细胞 × tile** 的原始稀疏矩阵。样本级矩阵要靠自己聚合，不是直接存 assay。

## 修正代码（colMeans 压成 1 行/样本 + rbind 合并）

```r
all_samples <- unique(proj1$Sample)
agg_list <- vector("list", length(all_samples))
names(agg_list) <- all_samples

for (i in seq_along(all_samples)) {
  s <- all_samples[i]
  proj_sub <- ArchR::subsetArchRProject(proj1,
    cells = proj1$cellNames[proj1$Sample == s],
    outputDirectory = paste0("Human_file/sub_", s),
    dropCells = TRUE, force = TRUE)

  se <- getMatrixFromProject(proj_sub, useMatrix = "TileMatrix", binarize = TRUE)

  # 关键：colMeans 聚合成 1 行 × tiles 的覆盖比例（0~1），和猴侧同口径
  agg_list[[i]] <- Matrix::colMeans(assay(se))

  rm(se, proj_sub); gc()
}

agg <- do.call(rbind, agg_list)
saveRDS(agg, "Human_file/human_tile_matrix_samples_x_tiles.rds")
cat("完成:", dim(agg), "\n")   # 预期 40 × ~607万
```

## 产物体积经验值（稀疏 dgCMatrix，tile 网格 500bp）

| 物种 | 样本数 | tile 列 | 体积 |
|---|---|---|---|
| 猴（已落盘） | 20 | ~608万 | ~206 MB |
| 人（此代码） | 40 | ~607万 | ~400 MB（样本翻倍 → nnz 约线性 → 体积约 2 倍） |

→ 样本级稀疏矩阵量级 MB~GB，不会爆；cell 级才爆。

## 跨物种列对齐（下一步必查）

两物种矩阵要能逐列比对，前提是 tile 网格一致：
- 猴侧 6,085,841 列 vs 人侧列数需核对是否同一套 500bp tile 定义。
- 若网格不同（不同参考基因组/不同 bin 起点），需统一到同源网格（本项目已建「统一同源网格 + 逐单元归一化」门控，见主 SKILL.md）。
- 跑完先 `dim(agg)` 核对列数，再进 L2 比对。
