# Tile 矩阵 vs 细胞矩阵 误读诊断 + 人/猴 seqname 前缀区分（2026-09-14 定性）

跨物种 ATAC 专利项目里，人侧「样本 × tile」矩阵曾被误读成「样本 × 细胞」矩阵，导致矩阵只有 2.8MB、
列名是细胞 barcode、跨样本列数不齐，完全无法与猴侧 206MB 的 tile 矩阵对齐。下面是定性判据，
下次遇到任何声称是「tile 矩阵」的产物，先过这三关。

## 一、tile 矩阵三个硬特征（一票否决维度错）

| 检查项 | 正确（tile 矩阵） | 错误（细胞矩阵） |
|--------|------------------|------------------|
| 文件大小 | 百 MB 级（猴侧基准 206MB） | 只有几 MB（误读版 2.8MB） |
| 列名 | tile 坐标（chr:start-end） | 细胞 barcode（如 `GSM8549615_hc77#ACGCACGGTATTCGCT-1`） |
| 列数跨样本 | 统一（608 万 tile 网格） | 不齐（每样本几百~几千细胞） |

三个都对不上 = 维度错了，值落在「每个细胞」而非「每个 tile 的覆盖比例」。

## 二、正确抽取路径

从每样本 ArchR Project 里抽 tile 矩阵：

```r
library(ArchR)
proj <- readRDS("每样本的 Save-ArchR-Project.rds")  # 201MB 就是对量级
gs <- getMatrixFromProject(proj, useMatrix = "TileMatrix")  # 数百 MB 稀疏矩阵
```

再聚合到统一 608 万 tile 网格，与猴侧对齐。不要读那个「样本×细胞」散件。

## 三、人侧 vs 猴侧 ArchR 产物：seqname 前缀一锤定音

**不要靠样本名（`O1_Hip/Y3_Hip`）或目录时间戳判断物种**——会被带偏（7/29 的 `E:/专利/ArchR_Output/`
曾被误当人侧，实为猴侧）。

最硬判据 = seqname 前缀：

- 猴（Macaca fascicularis）**T2T-MFA8** 参考基因组 → 染色体名 **`NC_088xxx.1`**（RefSeq 编号），如 `NC_088391.1`、`NC_088380.1`
- 人 hg38 → **`chr1`–`chr22`/`chrX`**

```r
unique(as.character(seqnames(gs)))   # 看前缀 NC_0 还是 chr，立即定物种
```

**坑**：`getMatrixFromProject` 需要 arrow 文件仍在原位——ArchR 存保守相对路径，搬目录会报
`Cannot open file '... .arrow does not exist'`。此时 `proj$cellNames` / `proj$Sample` 仍可读，
可先靠样本名 + `da_tiles.rds`（若存在）的 seqnames 侧写判断物种。`da_tiles.rds` 是 ArchR
markerTest 差异可及性结果（list: loose/strict × Old/Young），其 `seqnames` Rle 直接暴露参考基因组。

## 四、本机人侧数据位置（截至 2026-09-14）

- 正确数据：`E:/专利/Human_Hippocampus_ATAC/ArchR_Arrow_QC_Filtered/`，40 样本齐全，
  但目录里当前只有 `.arrow` + `_filtered_cells.csv`（完整 Project 未必已同步回本机）。
- 每样本完整 ArchR Project（含 201MB `Save-ArchR-Project.rds` + ArrowFiles/GroupCoverages/
  IterativeLSI/PeakCalls/Plots）曾在用户 Linux 集群生成——用前先问用户这批完整 Project 的绝对路径。
- 猴侧旧结果：`E:/专利/ArchR_Output/`（3 样本 O1_Hip/Y3_Hip，35879 cells，T2T-MFA8，7/29 生成）。