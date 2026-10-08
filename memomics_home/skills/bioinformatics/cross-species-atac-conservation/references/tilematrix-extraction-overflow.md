# ArchR TileMatrix 大矩阵提取：2^31-1 溢出 + 逐 arrow 建 project 方案

## 症状
对挂多 arrow 的 ArchRProj 调 `getMatrixFromProject(proj, useMatrix="TileMatrix", binarize=TRUE)` 一次性提取时报：

```
Error in cbind.Matrix(x, y, deparse.level = 0L): p[length(p)] cannot exceed 2^31-1
```

traceback 里凶手是 `Reduce("cbind", .)`（`getMatrixFromProject` 内部把 proj 挂的**全部 arrow** 的细胞拼成一个稀疏矩阵）。

## 根因（数字核算）
`getMatrixFromProject` 会 cbind proj 里**所有** arrow，非零元素数 nnz = 细胞数 × 每细胞覆盖 tile 数（scATAC 单细胞约 0.8–1.2 万 500bp tile）：

| 口径 | 细胞数 | nnz 量级 | 结果 |
|---|---|---|---|
| 单 arrow（~6600 细胞） | 6.6k | ~6600 万 | ✅ 安全 |
| 人 40 样本（265,909 细胞） | 26.6 万 | ~26.6 亿 | ❌ > 2^31−1（21.4 亿）爆 |
| 猴 61 库 | 十几万~几十万 | 可超 21 亿 | ❌ 视库数爆 |

最终要的产物是 `samples × tiles`（40 样本 / 20 样本），**从来不需要 cell 级巨矩阵**。

## 正解：逐 arrow 建 ArchRProject → 立刻按 Sample 聚合 → 合并

核心：每次只挂 1 个 arrow（单 arrow nnz ~6600 万，安全），读完立刻 `Matrix::rowsum` 压成 samples×tiles 小矩阵，最后按样本行名对齐合并。

```r
library(ArchR)
library(Matrix)

arrowFiles <- getArrowFiles(proj)   # 先确认数量（人侧应 40，猴侧 61 库）
cat("arrow 数:", length(arrowFiles), "\n")
outDir <- "<集群/本地输出目录>/agg_tmp"
dir.create(outDir, recursive = TRUE, showWarnings = FALSE)

parts <- vector("list", length(arrowFiles))
for (i in seq_along(arrowFiles)) {
  cat(sprintf("[%d/%d] %s\n", i, length(arrowFiles), basename(arrowFiles[i])))
  # 每次只挂 1 个 arrow，绕开 getMatrixFromProject 内部全量 cbind 溢出
  proj_i <- ArchRProject(ArrowFiles = arrowFiles[i],
                         outputDirectory = file.path(outDir, paste0("p", i)),
                         copyArrows = FALSE)
  se_i <- getMatrixFromProject(proj_i, useMatrix = "TileMatrix", binarize = TRUE, threads = 1)
  # 稀疏矩阵聚合必须用 Matrix::rowsum（base::rowsum 不支持稀疏/会慢）
  parts[[i]] <- t(Matrix::rowsum(t(assay(se_i)), group = as.character(proj_i$Sample)))
  rm(proj_i, se_i); gc()
}

# 合并 samples×tiles 小矩阵（同一样本跨 arrow 累加）
agg <- Reduce(function(a, b) {
  common <- intersect(rownames(a), rownames(b))
  rbind(a[setdiff(rownames(a), rownames(b)), , drop = FALSE],
        b[setdiff(rownames(b), rownames(a)), , drop = FALSE],
        a[common, , drop = FALSE] + b[common, , drop = FALSE])
}, parts)

saveRDS(agg, "<输出>/<物种>_tile_matrix_samples_x_tiles.rds")
```

## 三个必查 API/口径事实（ArchR 1.0.3 源码坐实）

1. **`getMatrixFromProject` 没有 `cellNames` 参数**。formals 仅 8 个：
   `ArchRProj / useMatrix / useSeqnames / excludeChr / verbose / binarize / threads / logFile`。
   想按细胞子集读 → 不能传 `cellNames=` 过滤（会报 `unused argument`），唯一办法是「每次只挂 1 个 arrow 建 project」。
2. **稀疏矩阵按组聚合用 `Matrix::rowsum`**，不是 base `rowsum`。ArchR 返回的是 dgCMatrix。
3. **tile 坐标在 `rowData(se)`**，`rowRanges(se)` 返回空 GRanges 是预期行为（见 getGroupSE 诊断）。

## 工作流铁律：先查已有产物，别重提

提取任何矩阵前，先 `search_files` 找 `*_tile_matrix_samples_x_tiles.rds`。实测坑：猴侧矩阵 2026-09-04 已落盘
`E:/专利/file/monkey_tile_matrix_samples_x_tiles.rds`（198MB，配套 `monkey_tile_coords.csv` 608 万 tile、
`monkey_sample_age.csv`），用户一度要在集群重提、浪费一天——**先确认成品在不在本地，在就直接复用，绝不重提**。
人侧 `human_tile_matrix` 若本地搜不到才是真缺口，才需要在集群逐 arrow 提。

## 用户偏好（本类任务的交付方式，必守）
- 提取方案**一次给到位**，不要来回换（"之前的方案你定的，现在换方案又是你"）。先查已有产物，再定要不要提。
- 路径**必须用集群真实路径**（如 `/hwfssz3/PS_JLU/zhangbo/...`），不要默认本地 `E:/`——先看 `getArrowFiles(proj)` 打印出来的路径再写。
- 别挤牙膏，别在用户问"有没有更好的办法"时给一长串解释，先给结论 + 能直接跑的代码。
