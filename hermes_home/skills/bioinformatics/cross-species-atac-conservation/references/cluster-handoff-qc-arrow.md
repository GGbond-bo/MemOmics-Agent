# 集群交接：QC 过滤后 Arrow 上传（2026-08-09 实测）

用户场景：本机已完成 GSE278576 40 样本 QC（`E:/专利/Human_Hippocampus_ATAC/ArchR_Arrow_QC_Filtered/`），
要把处理好的 Arrow 传上集群继续跑 merge→LSI→聚类→跨物种对比。核心问题：传什么？能不能直接跑？

## 答案

**可以，但必须同时传 `.arrow` + `_filtered_cells.csv`，merge 前用 CSV 名单 subset。**

## 关键发现：filterDoublets 不修改 Arrow

- `ArchR_Arrow_QC_Filtered/GSM8549615_hc77/GSM8549615_hc77.arrow` = 1,147,119,327 字节
- 与 QC 原始目录 Arrow **字节数完全一致**（如 hc6021 2,503,186,259 也相同）
- 结论：`filterDoublets()` 只把 Keep 细胞名单写进 `_filtered_cells.csv`，Arrow 文件本身未剔除 doublet
- 因此 merge 时必须 subset：测试版 4 样本直接 merge 得到 35,787 cells，而按 CSV 预期应 29,357（多 ~18% doublet）

## 每个样本目录内容（实测）

```
GSM8549615_hc77/
├── GSM8549615_hc77.arrow              ← 1.1 GB（HDF5 自包含）
└── GSM8549615_hc77_filtered_cells.csv ← 275 KB（Keep 名单）
```

40 个子目录，每个 2 文件。

## 上传/核对命令

```bash
# 1. 数子目录（40/40）
ls -d /cluster/ArchR_Arrow_QC_Filtered/*/ | wc -l

# 2. 抽查子目录双文件
ls /cluster/ArchR_Arrow_QC_Filtered/GSM8549615_hc77/
# 期望：GSM8549615_hc77.arrow + GSM8549615_hc77_filtered_cells.csv

# 3. 总数核对（80 = 40 arrow + 40 csv）
find /cluster/ArchR_Arrow_QC_Filtered/ -maxdepth 2 -type f | wc -l
```

## 集群 merge 脚本骨架（含 doublet subset）

```r
library(ArchR)
# 1. 加载 40 个 Arrow
arrow_files <- list.files(".../ArchR_Arrow_QC_Filtered", pattern=".arrow$", full.names=TRUE)
proj <- ArchRProj(arrowFiles = arrow_files, outputDirectory = ".../proj_merge")

# 2. 关键：按 CSV 名单剔除 doublet（必须做，否则 doublet 混入）
for (f in arrow_files) {
  csv <- sub("\\.arrow$", "_filtered_cells.csv", f)
  keep <- read.csv(csv)  # 列名 cellNames 或 barcode
  proj <- subsetArchRProject(proj, cells = keep$cellNames, outputDirectory = paste0(subdir, sample, "_sub"))
}

# 3. 然后按测试版 P0 流程继续：merge → addTileMatrix → IterativeLSI → addUMAP → addClusters
# 注意：ArchR 1.0.3 addClusters 必须用 input=proj（不是 ArchRProj=proj，见 atac-seq-memomics）
```

## 不要传

- ❌ 原始 `fragments.tsv.gz`（Arrow 已含全部片段/坐标信息）
- ❌ `QC_summary_all40.csv`（只是 40 样本汇总表，非分析输入）
- ❌ 旧版 `ArchR_Arrow_QC/` 目录（未过滤）

## 环境一致性要求

- R 4.5.3 + ArchR 1.0.3（与测试版同版本，Arrow 格式兼容）
- hg38 BSgenome + JASPAR2020（merge 后 motif/phyloP 需要）
- 正式版后续步骤见 `CLUSTER_STEP_BY_STEP_GUIDE.md` M2 之后
