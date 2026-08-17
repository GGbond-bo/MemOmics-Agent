# getMarkerFeatures 全零结果诊断指南

> 触发：`getMarkerFeatures(useMatrix="TileMatrix", groupBy="AgeGroup", testMethod="wilcoxon")` → 所有 tile log2FC=0, FDR=1

## 真实案例 (2026-07-29)

**数据**：猴海马 scATAC-seq, 35,879 cells, 21 clusters, 3 Arrow (Old×1, Young×2)

**ArchR log 节选** (正常完成但全零):
```
2026-07-29 05:16:57 : Young_NC_088389.1_diffResult, Class = data.frame
Young_NC_088389.1_diffResult: nRows = 257218, nCols = 8
         log2Mean log2FC fdr pval mean1 mean2   n auc
f4646866        0      0   1    1     0     0 500 0.5
f4646867        0      0   1    1     0     0 500 0.5
...

2026-07-29 05:16:57 : Pairwise Test Young : Seqnames NC_088390.1
Young_NC_088390.1_scMaty: nRows = 179517, nCols = 1000
NonZeroEntries = 374307, EntryRange = [ 1 , 1 ]

2026-07-29 05:17:27 : Completed Pairwise Tests, 2.912 mins elapsed.
```

**关键观察**：
- `NonZeroEntries` ≠ 0（如 374,307），说明 TileMatrix 有信号
- 但 `mean1` 和 `mean2` 列全为 0 — **问题不在矩阵，在均值计算**
- 1926 行 log 全部生成，无报错 — 看起来"成功"但实际无发现
- `markers_age_tiles.rds` 107MB → 191MB（正常大小的对象，但全是零）

## 诊断决策树

```
getMarkerFeatures 返回全零
    │
    ├─ mean1/mean2 全为 0?
    │   ├─ YES → 问题在分组或矩阵索引（非矩阵本身）
    │   │   └─ 检查 groupBy 列的值分布: table(proj$AgeGroup)
    │   │       ├─ 每组只有 1 个样本 → 统计功效问题 (fix: 增样本或换方法)
    │   │       └─ 每组 ≥ 3 样本 → 检查 useMatrix= 是否正确
    │   │
    │   └─ NO (有 non-zero mean) → 是真阴性或阈值太严
    │       └─ 放宽 cutOff: FDR <= 0.1 & abs(Log2FC) >= 0.1
    │
    └─ NonZeroEntries = 0?
        ├─ YES → TileMatrix 真的是空的
        │   └─ 检查 addTileMatrix 是否成功、染色体命名是否匹配
        └─ NO (有 non-zero) → 路径 1
```

## 已知解决方案

| 方法 | 前提 | 效果 |
|------|------|------|
| groupBy="Sample" (3组) 代替 "AgeGroup" (2组) | 样本≥3 | 提高统计效力 |
| tileSize=100bp 代替 500bp | — | 更密集 tile，更多非零 |
| nTop=5000 代替默认 | — | 限制测试 tile 数 |
| pseudobulk per individual | ≥2/组 | 聚合后 DESeq2 |

## 快速验证脚本

```r
library(ArchR)
proj <- readRDS("project_tilemat.rds")

# 1. 检查 AgeGroup 分布
print(table(proj$AgeGroup, proj$Sample))

# 2. 检查 TileMatrix 是否有信号
tm <- getMatrixFromProject(proj, "TileMatrix")
cat("TileMatrix dims:", dim(tm), "\n")
cat("NonZeroEntries:", length(assay(tm)@x), "\n")
cat("NonZero rate:", length(assay(tm)@x) / prod(dim(tm)) * 100, "%\n")

# 3. 快速测试不同参数
markers_test <- getMarkerFeatures(proj, useMatrix="TileMatrix",
  groupBy="AgeGroup", bias=c("TSSEnrichment", "nFrags"),
  testMethod="wilcoxon", maxCells=10000)
cat("Markers dims:", nrow(markers_test), "x", ncol(markers_test), "\n")
```
