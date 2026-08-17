# 集群 40 样本 ArchR 流程（GSE278576 人海马 · 正式版 M 流程）

来源：2026-08-11/12 会话。用户在自己集群（Linux）上跑人侧全量 40 样本，测试版（4 样本）已全部跑通。
**用户明确偏好：脚本直接写在交互框上、极简三步走（装包/读数据 → 操作 → 保存+验证），不要长篇脚本 + 解释堆砌。**

## 数据布局与核心坑

- `ArchR_Arrow_QC_Filtered/` 下 40 个样本目录，每目录含：
  - `GSMxxxx_hcXX.arrow`（QC 后 Arrow，自包含 HDF5，可跨机拷贝）
  - `GSMxxxx_hcXX_filtered_cells.csv`（doublet 过滤后存活名单）
- ⚠️ **`_filtered_cells.csv` 的 `DoubletFilter` 列全部是 "Keep"** —— 文件只含幸存者，被剔除的 doublet 根本不在名单里。取名单用 `keep$cellNames[keep$DoubletFilter=="Keep"]`。
- ⚠️ **`.arrow` 本身没有真正剔除 doublet**（`filterDoublets()` 不改写 Arrow），过滤结果只记录在 CSV。merge 前必须用 CSV 名单 subset，否则 ~18% doublet 混入（测试版踩过：4 样本 merge 出 35,787 而非预期 29,357）。
- ⚠️ 目录里可能有嵌套 `FilteredProjects/` / `ArrowFiles/` 副本（subsetArchRProject 中间产物），导致 `recursive=TRUE` 扫出 46 个而非 40 个。Linux 清理：
  ```bash
  cd <DIR>
  find . -depth -type d \( -name "FilteredProjects" -o -name "ArrowFiles" \) -exec rm -rf {} \;
  find . -name "*.arrow" | wc -l   # 验证 = 40
  ```

## 40 样本读取 + doublet 剔除 + 合并（一步到位）

```r
library(ArchR)
addArchRThreads(8)
addArchRGenome("hg38")
dir <- "/hwfssz3/.../ArchR_Arrow_QC_Filtered"

af <- list.files(dir, "\\.arrow$", full.names = TRUE, recursive = TRUE)
proj <- ArchRProject(ArrowFiles = af)   # 注意：大写 ArrowFiles！

cf <- list.files(dir, "_filtered_cells\\.csv$", full.names = TRUE, recursive = TRUE)
cells <- do.call(rbind, lapply(cf, read.csv))
cells <- cells$cellNames[cells$DoubletFilter == "Keep"]

proj <- subsetArchRProject(proj, cells = cells,
                           outputDirectory = "Human_ATAC/archr_out", force = TRUE)
saveRDS(proj, "human_proj_40_filtered.rds")
cat("细胞数:", length(cells), "\n")                 # 265,909
cat("样本数:", length(unique(proj$Sample)), "\n")   # 40
```

## ArchR 常见报错与坑（集群/本地通用）

1. **`ArchRProject(arrowFiles=...)` → "unused argument"**：参数名必须大写 `ArrowFiles=`。R 区分大小写。
2. **`list.files()` 不能用 glob `*.arrow`**（那是 shell 语法）：用 `pattern="\\.arrow$"` + `recursive=TRUE`。
3. **`plotEmbedding(name="samples")` 报错**：cellColData 里没有小写 `samples` 列，正确列名是 `Sample`（大写）。猴侧 `project_clustered.rds` 17 列无 CellType；人侧 `human_proj_annotated.rds` 18 列含 CellType。
4. **`addClusters(ArchRProj=...)` 在 ArchR 1.0.3 报错**：必须 `addClusters(input=proj, ...)`（1.0.3 签名 `input` 优先，内部 `rm(ArchRProj)` 导致 object not found）。
5. **聚类顺序**：官网先 `addClusters` 后 `addUMAP`（聚类用 LSI 空间，UMAP 只是可视化投影）。别反。
6. **`Save-ArchR-Project.rds`（几 MB）**：是项目元数据/索引卡，每次 subset 自动生成，正常。数据本体在 `.arrow`（几百 MB）。省空间可 `subsetArchRProject(..., copyArrows=FALSE)`。
7. **注释流程**：集群 Linux 走官网完整流程 `addGeneScoreMatrix` → `addImputeWeights`（MAGIC 平滑，可选，仅改善 UMAP 基因特征图，不改变 getMarkerFeatures 统计）→ `getMarkerFeatures`。Windows 上 addGeneScoreMatrix 会崩 → 用 TileMatrix 500bp TSS±2kb 覆盖度近似（见主 SKILL）。
8. **cellColData 查看**：`proj@cellColData` / `getCellColData(proj)` / `colnames(proj@cellColData)`。ArchR 没有 Seurat 的 `meta.data` 命名。

## 过滤前/后统计（每样本 before/after/removed）

```r
n_before <- table(proj$Sample)                  # Arrow 内细胞数（含 doublet）
n_after  <- sapply(cf, function(c) sum(read.csv(c)$DoubletFilter == "Keep"))
# removed = before - after；40 样本 after 合计 = 265,909
```

## 聚类后

- `table(proj$Clusters, proj$Sample)` 看批次/单样本霸群
- marker 注释 8 大类（Ex/Inh/Astro/Micro/OPC/ODC/VS/ChP），marker 基因表见主 SKILL / cross-species-atac-conservation
- `proj$CellType <- mapvalues(proj$Clusters, ...)`；保存 `human_proj_40_annotated.rds`
