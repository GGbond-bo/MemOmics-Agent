# TileMatrix 按样本聚合（多供体 → samples × tiles）+ ArchR API 陷阱

跨物种 / 年龄相关分析需要把多个 arrow 的 TileMatrix 聚合成「样本 × tiles」矩阵时的完整做法与坑。2026-09-14 实测（人 40 供体海马 ATAC）。

## 大小估算（先算清楚再动手，别拍脑袋）

- TileMatrix `binSize=500bp`，hg38 主染色体 ≈ **500–600 万 tiles**（= 矩阵列数）。
- **最终 samples × tiles 矩阵小**：N样本 行 × 600 万列，稀疏存储 ≈ **300 MB ~ 1 GB**（由 `nnzero` 决定，不是 cells 数）。
- **中间对象大**：`getMatrixFromProject` 对多个 arrow 一次性 cbind 是「几十万 cells × 600 万 tiles」全量稀疏矩阵，会顶到几十 GB / 触发 **2³¹−1 溢出**。**"逐个 arrow 挂载聚合"绕开的是这个中间对象，不是最终产物。**

⛔ 用户会当面质疑估算数字（"你确定只有几十M吗"）——报任何数字（cells / 文件大小 / 内存）前必须有类似上式子的估算依据，禁止无来源的"几十M / 几个G"。

## 聚合脚本（逐个 arrow 挂载，绕开溢出）

```r
.libPaths(c("E:/R-libs/R-4.5.3", .libPaths()))
suppressMessages(library(ArchR))
arrowDir <- "<arrow 目录>"
arrows <- list.files(arrowDir, pattern = "arrow$", recursive = TRUE, full.names = TRUE)
arrows <- arrows[!grepl("FilteredProjects", arrows)]   # 排嵌套副本
arrows <- arrows[!duplicated(basename(arrows))]        # 按 basename 去重
cat("唯一 arrow:", length(arrows), "\n")

agg_list <- vector("list", length(arrows))
for (i in seq_along(arrows)) {
  proj_i <- ArchRProject(ArrowFiles = arrows[i],
                         outputDirectory = file.path(outDir, sub("[.]arrow$", "", basename(arrows[i]))),
                         copyArrows = FALSE)
  se_i  <- getMatrixFromProject(proj_i, useMatrix = "TileMatrix", binarize = TRUE, threads = 1)
  mat_i <- assay(se_i)                       # cells × tiles（单 arrow 安全）
  agg_i <- t(Matrix::rowsum(t(mat_i), group = proj_i$Sample))  # samples × tiles
  agg_list[[i]] <- agg_i
  rm(proj_i, se_i, mat_i); gc()
}
# 同一样本跨 arrow 相加合并
agg <- Reduce(function(a, b) {
  common <- intersect(rownames(a), rownames(b))
  rbind(a[setdiff(rownames(a), rownames(b)), , drop = FALSE],
        b[setdiff(rownames(b), rownames(a)), , drop = FALSE],
        a[common, , drop = FALSE] + b[common, , drop = FALSE])
}, agg_list)
saveRDS(agg, "<out>.rds")
```

**验证两要点**：① 第一行 arrow 数 = 预期样本数；② 每个 `[i/N]` 的 `tiles` 数字**必须全部相同**（同批 hg38 500bp 平铺理应对齐），出现不同 = tile 坐标没对齐，需按 tile 名（rownames）重排后再合并。

## 陷阱

### ⛔ getCellNames 不接受 arrow 路径（character）
- 症状：`getCellNames(arrow_path)` → `Input value for 'ArchRProj' is not a archrproject, (ArchRProj = character)`。
- 根因：`getCellNames()` 参数名是 `ArchRProj`，只收 ArchRProject 对象，不给裸 arrow 路径回退。
- 修复：① 建单 arrow 项目再取，或 ② rhdf5 直读 arrow 内 cellNames dataset（ArchR arrow 本质是 h5），或 ③ `ArchRProject(ArrowFiles=...)` 建项目后 `getCellNames(proj)`。

### execute_r 反斜杠转义（交叉引用）
`list.files(pattern = "\\.arrow$")` → R 报 `'\/' is an unrecognized escape`（解析期整段不跑）。规避：`pattern = "arrow$"` 或 `fixed = TRUE`。详见 `platform-execution-pitfalls` 坑表同款行。

### 相关（交叉引用）
- ArchR Windows 多实例 tmp 目录竞争 → 必须串行 1 实例。
- filterDoublets 后 DoubletFilter 列消失 → 用过滤前后细胞数差算 doublet。
- 跨物种年龄设计「离散阶段 vs 连续轴」判定 → `cross-species-atac-conservation` 的 `references/staged-design-vs-continuous-age.md`。
