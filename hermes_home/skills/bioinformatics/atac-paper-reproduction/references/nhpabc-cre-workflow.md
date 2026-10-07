# 张潇 NHPABC cCRE 流程参数（2026-08-29 用户贴 GitHub 脚本实测）

> 来源：NHPABC (Non-Human Primate Aging Brain cCRE) GitHub README 用户转发 + 对话确认。
> 用途：专利复现张潇猴脑 cCRE 分析时的**参数基线**；人脑对照已按此参数完成 peak calling。

## 1. Peak calling（张潇 README 原文参数）

```
Peak calling: cell-subtype basis, per individual, MACS2 v2.2.7.1
  addGroupCoverages:      minCells = 40, maxCells = 5,000, minReplicates = 2, maxReplicates = 10
  addReproduciblePeakSet: maxPeaks = 500,000, cutOff = 0.01
  输出: 501-bp fixed-width peaks
```

⚠️ **ArchR 默认 vs 张潇参数**（用户曾因传默认参数产出 `Number of Cells = 500` 而 peak 覆盖不足）：

| 参数 | 张潇显式 | ArchR 默认 | 影响 |
|------|---------|-----------|------|
| maxCells | 5,000 | 500 | 每组 pseudo-bulk 深度差 10× |
| maxReplicates | 10 | 5 | 每组最多个体数 |
| maxPeaks | 500,000 | 150,000 | peak 数量上限 |
| cutOff | 0.01 | 0.05 | MACS2 q 值更严 |

**必须显式传参**，不能依赖默认值。

## 2. Input 格式（张潇 README）

- 输入：ArchR PeakMatrix 对象 `.rds`（如 `Ast1_PFC_PeakMatrix.rds`），用 `getMatrixFromProject` 导出
- 对象必须含：
  - `peakmatrix`（peaks × Individuals）
  - Metadata 列：`Annotation`（如 Subtype）、`Individuals`（如 Y1,Y2,..,V6）

## 3. Step 1: PeakMatrix → Seurat（CPM 归一化）

```r
pm <- readRDS("Ast1_PFC_PeakMatrix.rds")
rds <- CreateSeuratObject(counts = pm, assay = "peaks", meta = meta)
rds <- NormalizeData(object = rds, normalization.method = "RC", scale.factor = 1e6)  # CPM
saveRDS(rds, "Ast1_PFC_peakmatrix_seurat.rds")
```

## 4. Step 2: cCRE 筛选标准（calculate_cCRE.R）

**Mean CPM > 4 在至少 4 个猴样本；Mean CPM > 0 在至少 12 个猴样本。**

```r
source("~/calculate_cCRE.R")
cCRE <- calculate_cCRE(
  rds_path = "./Ast1_PFC_peakmatrix_seurat.rds",
  output_dir = "./cCRE_result/"
)
```

> `calculate_cCRE.R` 未在本会话获取原文，筛选逻辑以 README 文字为准；如用户后续提供脚本则本文件补全。

## 5. Peak-to-gene links

```
addCoAccessibility (ArchR): aggregation k = 10, window size = 500 kb, distance constraint = 250 kb
```

## 6. 细胞类型入选门槛（README）

> Cell types containing **>10 nuclei per individual** and **>100 nuclei per age group** were selected for analysis.

## 7. 复现注意（本会话实测）

- 猴脑 21 个体 4 年龄组：Young(5y)×4 / Middle(10-12y)×5 / Old(22-23y)×6 / Exceptionally old(28-31y)×6 —— 对比时的 age group 定义用这套
- 人脑对照：40 个体 4 组×10（20-40/40-60/60-80/80-100）
- 猴 M4 个体仅 61 细胞（异常少）→ 趋势检验 n 从 21 掉到 20 的疑点，需敏感性分析
- 猴脑 GroupCoverages 报 `H5Fcreate Unable to open file` = 写权限/输出目录问题，不是参数问题（详见 atac-seq-memomics 对应条目）