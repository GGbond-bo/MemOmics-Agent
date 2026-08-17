# addGroupCoverages 命名不匹配诊断

**验证日期**: 2026-07-29
**验证数据**: 猴海马 scATAC-seq, 35K cells, 21 clusters, 3 samples

## 问题

`project_clustered.rds` 在 `addGroupCoverages` 之前保存，导致重载后 ArchR 不认识已生成的 coverage .h5 文件。即使磁盘上有 57 个 .h5 文件，`addGroupCoverages(force=FALSE)` 仍尝试全部重建。

## 诊断脚本

```r
.libPaths(c("USER_R_LIBS/R-4.5.3", .libPaths()))
library(ArchR)
addArchRGenome("hg38")
addArchRThreads(threads = 1)

proj <- readRDS("E:/专利/ArchR_Output/project_clustered.rds")

# ArchR 期望的文件名
groups <- getCellColData(proj, select = "Clusters")[,1]
samples <- getCellColData(proj, select = "Sample")[,1]
expected <- unique(paste(groups, samples, sep = "."))
cat("Expected groups:", length(expected), "\n")

# 磁盘上实际存在的 .h5 文件
coverage_dir <- "E:/专利/ArchR_Output/GroupCoverages/Clusters"
existing <- list.files(coverage_dir, pattern = "\\.insertions\\.coverage\\.h5$")
cat("Existing files:", length(existing), "\n")

# 命名对比
expected_files <- paste0(expected, ".insertions.coverage.h5")
missing <- setdiff(expected_files, existing)
cat("Missing:", length(missing), "\n")
```

## 根因

`project_clustered.rds` 仅含聚类信息（LSI + UMAP + Clusters），不含 `addGroupCoverages` 写入的 coverage 元数据。重载后 ArchRProject 没有 coverage 文件路径记录，`force=FALSE` 的跳过逻辑无法工作。

## 修复策略

### 策略 1：分步保存（预防）

每步操作后立即 `saveRDS`：

```r
proj <- readRDS("project_clustered.rds")

# Step 后立即保存
proj <- addGroupCoverages(proj, groupBy="Clusters")
saveRDS(proj, "project_cov.rds")  # ← 含 coverage 元数据

proj <- addTileMatrix(proj, tileSize=500)
saveRDS(proj, "project_tilemat.rds")

# 后续步骤从 project_cov.rds 加载，不会丢失之前的结果
```

### 策略 2：force=TRUE 重建（事后补救）

若已丢失 coverage 元数据且 `force=FALSE` 不工作：

```r
proj <- addGroupCoverages(proj, groupBy="Clusters", force=TRUE)
saveRDS(proj, "project_cov.rds")
```

耗时估算：35K cells × 21 clusters ≈ 15-20 分钟（单线程）。

### 策略 3：先诊断再决定

运行诊断脚本 → 若 `missing` 为空但 `force=FALSE` 仍重建 → 说明是 ArchRProject 元数据丢失 → 用 `force=TRUE`。

## 命名格式说明

ArchR `addGroupCoverages(groupBy="Clusters")` 生成的文件名格式为：
`{Cluster}._{Sample}.insertions.coverage.h5`

例如：
- `C1._.Rep1.insertions.coverage.h5`
- `C2._.O1_Hip_1.insertions.coverage.h5`

其中 `._.` 是 ArchR 内部分隔符，`Sample` 列来自 Arrow 文件的 `Sample` metadata。
