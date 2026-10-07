# 导 ArchR project → per-sample × tiles 可及性矩阵 + 连续年龄（在集群跑）

## 用途
跨物种/连续年龄 ATAC 相关性分析的第一步：从 ArchR project 提取「每个样本(donor) × 每个 500bp tile」的
平均可及性（sparse 矩阵）+ 每样本连续年龄 → 下载回本地后对每 tile 算 `(年龄, 可及性)` 的 Pearson r。
解决「猴侧只有 Old/Young 二分类 DA、人侧是连续年龄 r」的量纲不一致问题（见 references/aging-response-surrogacy-stats.md 坑位 6）。

## ArchR API 签名（R 4.5.3 + ArchR 1.0.3 已实证，写对不用返工）
```r
getMatrixFromProject(ArchRProj=NULL, useMatrix="GeneScoreMatrix", useSeqnames=NULL,
    excludeChr=NULL, verbose=TRUE, binarize=FALSE, threads=getArchRThreads(), logFile=...)
getAvailableMatrices(ArchRProj=NULL)
addTileMatrix(input=NULL, chromSizes=NULL, blacklist=NULL, tileSize=500, binarize=TRUE,
    excludeChr=c("chrM","chrY"), threads=..., parallelParam=NULL, force=FALSE, logFile=...)
getCellColData(ArchRProj=NULL, select=NULL, drop=FALSE)
loadArchRProject(path="./", force=FALSE, showLogo=TRUE)
```
注意：`excludeChr` 默认 `chrM/chrY`，食蟹猴 T2T-MFA8v1.1 染色体名是 `NC_088375.1..NC_088395.1`，
但 TileMatrix 通常已用染色体 size 源 add 过（`getMarkerFeatures(useMatrix="TileMatrix")` 能跑即是证明），
直接 `getMatrixFromProject` 读即可，不必重跑 `addTileMatrix`（慢）。

## 脚本（改 3 处：project_path / sample_col / age_col）

```r
library(ArchR)
library(Matrix)

project_path <- "/hwfssz3/PS_JLU/<user>/<ArchR project 目录>"   # ← 改
out_dir      <- "/hwfssz3/PS_JLU/<user>/export_continuous"      # ← 改
dir.create(out_dir, showWarnings=FALSE, recursive=TRUE)
proj <- loadArchRProject(path=project_path)

avail <- getAvailableMatrices(proj)
cat("可用矩阵:", paste(avail, collapse=" | "), "\n")
if (!"TileMatrix" %in% avail) stop("TileMatrix 不存在，先 addTileMatrix(proj)")

ccd <- getCellColData(proj)
cat("\ncellColData 列:\n")            # 打印列名 + n_unique + 前12取值，据此定 sample/age 列
for (cn in colnames(ccd)) {
  u <- unique(as.character(ccd[[cn]]))
  cat(sprintf("  %-22s n_unique=%d", cn, length(u)))
  if (length(u) <= 25) cat("  ->", paste(head(u, 12), collapse=","))
  cat("\n")
}

sample_col <- "Sample"                 # ← 按打印改；21 猴 Sample 前缀 Y3-Y7/M1-M5/O1-O6/V1-V6
age_col    <- "Age"                    # ← 按打印改

se  <- getMatrixFromProject(proj, useMatrix="TileMatrix", binarize=FALSE)
mat <- assay(se)                       # tiles × cells sparse
tr  <- rowRanges(se)                   # tile GRanges

cells <- colnames(mat)
sam <- as.character(ccd[cells, sample_col])
sample_ids <- sort(unique(sam))

# 每 sample 每 tile 平均可及性：cells→samples one-hot 左乘
J <- sparseMatrix(i=seq_along(sam), j=match(sam, sample_ids),
                  x=1, dims=c(length(sam), length(sample_ids)))
mat_mean <- mat %*% J %*% Diagonal(x=1/as.numeric(colSums(J)))   # tiles × samples
mat_st <- t(mat_mean)                                            # samples × tiles
rownames(mat_st) <- sample_ids

age_by_sample <- sapply(sample_ids, function(s)
  mean(as.numeric(ccd[cells, age_col])[sam==s], na.rm=TRUE))

saveRDS(mat_st, file.path(out_dir, "monkey_tile_matrix_samples_x_tiles.rds"))
write.csv(data.frame(sample=sample_ids, age=age_by_sample),
          file.path(out_dir, "monkey_sample_age.csv"), row.names=FALSE)
write.csv(data.frame(tile=rownames(mat), seqnames=as.character(seqnames(tr)),
                     start=start(tr), end=end(tr)),
          file.path(out_dir, "monkey_tile_coords.csv"), row.names=FALSE)

cat("矩阵 samples x tiles =", nrow(mat_st), "x", ncol(mat_st), "\n")
cat("年龄:", paste(sprintf("%s=%.1f", sample_ids, age_by_sample), collapse=", "), "\n")
```

## 关键坑位
- **年龄列若是分组占位值而非真值**：`monkey_sample_age.csv` 让用户手动改成精确连续年龄再发回（张潇 atlas 精确个体年龄在 Supplementary Table S2A；但 cellColData 的 Age 列通常已是数值 5/10/11/12/22/23/28/29/31）。
- **聚合用 mean（log2 归一化值）**：ArchR TileMatrix 默认 binarize=TRUE 后 log2Norm，per-sample mean = 「该 tile 可及细胞比例」的 log2 代理，适合做连续年龄 Pearson r。
- 产物 sparse RDS 是高效保存（只存非零）；tile 坐标单独 CSV，别塞进 rownames（太大）。