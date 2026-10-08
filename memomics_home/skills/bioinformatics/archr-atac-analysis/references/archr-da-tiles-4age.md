# ArchR 四年龄组 DA tiles（伪bulk 个体为统计单元）

场景：跨物种（人 40 / 猴 21−M4=20 个体）海马 ATAC，检验四年龄组
（Young / Middle / Old / Exceptionally old）差异可及 tiles，供 motif 富集 /
跨物种保守性打分（L3/CRECS 专利管线）。2026-09-01 本会话生成并现场纠正统计单元错误。

> ⚠️ **方法选型 v2（2026-09-01 用户拍板）**：对齐 Zemke Science 2026（GSE278576）官方方法 →
> **不用 DESeq2 LRT**（下方 DESeq2 版保留为"分组比较替代方案"），改用
> **连续年龄 Pearson + shuffle ×5000 + FDR<0.1**（含完整脚本见下文「✅ v2 终版：Pearson + shuffle」）。
> 用户原话语境：agent 提议 DESeq2 → 用户问"你确定人家文章使用的是这个吗?" → 查证文章官方代码
> `03_age_correlation/correlation_ATAC.ipynb` 用 Pearson → 用户选 1（Pearson + shuffle 版）。

## 核心模式（统计单元铁律，两版通用）

- 聚合单元 = individual（40/20 列），**不是** age_group（4 列）——千问生成代码的原错误
- 年龄组 = DESeq2 design 因子（`~age_group`，LRT `reduced=~1`）【仅 DESeq2 版】
- 方向判定（DESeq2 版） = 最老两组均值 vs 最幼两组均值 log2FC（伪计数 1e-9 放分子分母内部）
- `direction` 需 FDR<0.05 且 |log2FC|≥0.25；loose=FDR<0.05；strict=loose 且 |log2FC|≥0.5
- 剔除个体（M4）必须在 getGroupSE **之前**过滤 project 细胞
- colData 贴分组用 `match()` 按个体名对齐，不用行号
- 人侧坐标 hg38；猴侧 MFA8/T2T（输出原样，下游 agent 做 liftover 映射，不要本地转坐标）

## 人侧完整脚本（40 个体）

```r
# ===== 四年龄组 DA tiles（人侧 40 样本 · 个体级）=====
suppressMessages({library(ArchR); library(DESeq2)})
setArchRThreads(16)

proj1 <- loadArchRProject("/hwfssz3/PS_JLU/zhangbo/patent/Save-ArchR", force=FALSE)
cd <- as.data.frame(getCellColData(proj1))
stopifnot(all(c("individual","age_group") %in% colnames(cd)))
cat("unique individuals:", length(unique(cd$individual)), "\n")

se_h <- getGroupSE(proj1, useMatrix="TileMatrix", groupBy="individual")
cat("n individuals(columns):", ncol(se_h), "\n")

md <- unique(cd[, c("individual","age_group")])
age <- factor(md$age_group[match(colnames(se_h), md$individual)],
              levels=c("Young","Middle","Old","Exceptionally old"))
stopifnot(!anyNA(age))
colData(se_h) <- DataFrame(age_group=age)
print(table(age))

keep <- rowSums(assay(se_h) > 0) >= 0.2*ncol(se_h)
se_h <- se_h[keep, ]
cat("tiles kept:", nrow(se_h), "\n")

dds <- DESeqDataSet(se_h, design=~age_group)
dds <- DESeq(dds, test="LRT", reduced=~1)
res <- as.data.frame(results(dds))

nc <- counts(dds, normalized=TRUE)
gm <- do.call(rbind, lapply(seq_len(nrow(nc)), function(i)
  tapply(nc[i,], age, mean)))
fc <- log2( ((gm[,"Exceptionally old"]+gm[,"Old"])/2 + 1e-9) /
            ((gm[,"Young"]+gm[,"Middle"])/2 + 1e-9) )

out <- data.frame(chr=as.character(seqnames(rowRanges(se_h))),
                  start=start(rowRanges(se_h)), end=end(rowRanges(se_h)),
                  LRT_p=res$pvalue, LRT_q=res$padj,
                  mean_Young=gm[,"Young"], mean_Middle=gm[,"Middle"],
                  mean_Old=gm[,"Old"], mean_EO=gm[,"Exceptionally old"],
                  log2FC=fc, stringsAsFactors=FALSE)
out$direction <- ifelse(!is.na(out$LRT_q) & out$LRT_q<0.05 & abs(out$log2FC)>=0.25,
                        ifelse(out$log2FC>=0,"up_aging","down_aging"),"ns")

loose  <- out[!is.na(out$LRT_q) & out$LRT_q<0.05, ]
strict <- loose[abs(loose$log2FC)>=0.5, ]
cat("loose:", nrow(loose), " strict:", nrow(strict), "\n")

OUT <- "/hwfssz3/PS_JLU/zhangbo/patent"
saveRDS(list(strict=strict, loose=loose, all=out),
        file.path(OUT,"da_tiles_4age_ind.rds"))
for (th in c("strict","loose")) {
  d <- get(th)
  write.table(d[,c("chr","start","end")],
              file.path(OUT,sprintf("da_tiles_4age_ind_%s.bed",th)),
              sep="\t", row.names=FALSE, col.names=FALSE, quote=FALSE)
  write.csv(d, file.path(OUT,sprintf("da_tiles_4age_ind_%s.csv",th)), row.names=FALSE)
}
```

## 猴侧差异（M4 剔除 + 列名适配）

猴侧 vs 人侧 4 处不同：project 路径、M4 剔除（21→20）、列名（IND_COL/AGE_COL 先 print 确认）、输出前缀 monkey_。

```r
# ===== 四年龄组 DA tiles（猴侧 · M4 剔除）=====
suppressMessages(library(ArchR)); setArchRThreads(16)
proj <- loadArchRProject("/hwfssz3/PS_JLU/zhangbo/patent/Monkey-ArchR")  # 按实际改

cd <- as.data.frame(getCellColData(proj))
print(colnames(cd)); print(table(cd$Age_group))   # 先看列名再走

IND_COL <- "Individual"                            # 实际列名不同改这里
AGE_COL <- "Age_group"

# ⛔ M4 必须在 getGroupSE 之前剔除（与 L2 数据底一致：21 → 20）
keep <- !is.na(cd[[AGE_COL]]) & cd[[IND_COL]] != "M4"
proj <- proj[keep, ]
cat("cells after M4 removal:", nrow(getCellColData(proj)), "\n")

se_tile <- getGroupSE(proj, useMatrix="TileMatrix", groupBy=IND_COL)
cat("n individuals(columns):", ncol(se_tile), "\n")

meta <- read.csv("monkey_meta.csv")
se_tile$age_group <- factor(meta[[AGE_COL]][match(se_tile[[IND_COL]], meta[[IND_COL]])],
                            levels=c("Young","Middle","Old","Exceptionally old"))
print(table(se_tile$age_group))
stopifnot(!any(is.na(se_tile$age_group)))
saveRDS(se_tile, "/hwfssz3/PS_JLU/zhangbo/patent/monkey_da_tiles_byindividual.rds")

# ... 之后 DESeq2 LRT 段落与人侧完全一致（dds/out/strict/loose/保存），
#     输出前缀 monkey_da_tiles_4age_*
```

## 陷阱清单（本会话实测纠正）

1. `groupBy="age_group"` → n=4 伪重复（千问生成代码的原错误）——审稿人必抓的统计单元错误；用户会当场质疑"你要跑年龄四组的 DA 还是个体的？"
2. M4 不剔就聚合 → 被剔除个体成为 NA-age 列报错，或数据底与 L2（meta60=40人+20猴）不一致——必须在聚合前 `proj <- proj[keep, ]`
3. 复用 L2 的 PeakMatrix SE 做 DA tiles → 错矩阵；必须 TileMatrix 重新聚合（同一 project，分钟级）
4. match() 按个体名对齐 age_group，禁止按行号
5. Exceptionally old 组个体 <2 → DESeq2 组内方差不可估报错 → 并入 Old 重跑（Pearson 版无此问题，连续年龄天然处理）
6. `getGroupSE` 必须加 `divideN=FALSE`——默认 `divideN=TRUE` 把 counts 除以组内细胞数 → 小数计数全被 `rowSums >= 2*ncol` 过滤 → `All tiles filtered out!`（2026-09-02 猴侧实测，先查 divideN 别改阈值）
7. 坐标在 `rowData(se)` 不在 `rowRanges(se)`——1.0.3 的 getGroupSE 只填 rowData（源码 `SummarizedExperiment(..., rowData=featureDF)`），`rowRanges(se)` 返回 length=0，防御检查必炸
8. **rowData 坐标是 per-chr tile 伪坐标**——`.addTileMat` 源码 `featureDF$start <- (idx-1)*tileSize`，列顺序为 seqnames/idx/start；直接当 start/end 输出 CSV（如 `chr1,1587,793000`）liftover 全错。真实坐标 = `col3+1 ~ col3+500`（tileSize=500）。自检：正常 tile `end-start≈500` 且 start 间隔 500；`end/start≈500` 或 start 连续 +1 → 没换算。已生成 CSV 可后处理修坐标（统计列与坐标无关，不重跑）

---

## ✅ v2 终版（用户拍板，对齐 Science 文章官方方法）：连续年龄 Pearson + shuffle ×5000 + FDR<0.1

> 适用：跨物种 DA tiles 鉴定用于 motif 富集一致性（专利 L3）。**不跑 DESeq2**。
> meta 列名实测（2026-09-01）：人 `human_meta.csv` 有 `individual / Age(连续) / age_group`；猴 `monkey_meta.csv` 有 `Individual/individual 双列 / Age(连续) / Age_group`。

### 人侧 40 样本（统计单元=个体，Age=供体连续年龄）

```r
# ===== L3 v2: DA tiles — 连续年龄 Pearson + shuffle（对齐 Zemke Science 2026）=====
suppressMessages(library(ArchR)); setArchRThreads(16)
proj1 <- loadArchRProject("/hwfssz3/PS_JLU/zhangbo/patent/Save-ArchR", force=FALSE)
cd <- as.data.frame(getCellColData(proj1))
cat("cellColData columns:", paste(colnames(cd), collapse=", "), "\n")  # 确认有 individual + Age

se <- getGroupSE(proj1, useMatrix="TileMatrix", groupBy="individual",
                 scaleTo=NULL, divideN=FALSE)   # ★ divideN=FALSE 才返回原始总 counts（默认 TRUE 会除以细胞数 → 全被过滤）
cat("n individuals(columns):", ncol(se), "\n")

# 连续年龄：优先 cellColData 的 Age，取不到再读 meta（两文件都放集群工作目录）
if ("Age" %in% colnames(cd)) {
  md <- unique(cd[, c("individual","Age")]); md <- md[!duplicated(md$individual), ]
  age <- md$Age[match(colnames(se), md$individual)]
} else {
  m <- read.csv("human_meta.csv", stringsAsFactors=FALSE)
  age <- m$Age[match(colnames(se), m$individual)]
}
stopifnot(!anyNA(age)); print(age)          # 40 个连续年龄值
cnts <- assay(se)

# 特征过滤（文章官方：总 counts ≥ 2 × 剩余供体数）
keep <- rowSums(cnts) >= 2 * ncol(cnts); cnts <- cnts[keep, ]
cat("tiles kept:", nrow(cnts), "\n")

# log2CPM（每供体列标准化）
cpm <- t(t(cnts) / colSums(cnts) * 1e6); lcpm <- log2(cpm + 1)

# 全 tiles 向量化 Pearson（等价 cor.test，快 1000 倍；50 万 tiles 不能逐行 cor.test）
n <- ncol(lcpm)
rv <- apply(lcpm, 1, function(x) cor(x, age))
tv <- rv * sqrt((n-2) / (1-rv^2)); pv <- 2 * pt(-abs(tv), df=n-2); fdr <- p.adjust(pv, "fdr")
# ⛔ 坐标取 rowData(se)，不取 rowRanges(se)（1.0.3 的 SE 不填 rowRanges）
# ⛔ rowData 列 = seqnames, idx, start=(idx-1)*tileSize（per-chr tile 伪坐标，非真实坐标）→ 换算真实坐标
fr <- as.data.frame(rowData(se))[keep, , drop=FALSE]
resTbl <- data.frame(chr   = fr[[1]],
                     start = fr[[3]] + 1,        # (idx-1)*500 + 1
                     end   = fr[[3]] + 500,      # idx*500
                     r=rv, p=pv, FDR=fdr)
stopifnot(nrow(resTbl) == length(rv))            # 行数对齐自检
resTbl$dir <- ifelse(resTbl$FDR<0.1 & resTbl$r>0, "Up",
             ifelse(resTbl$FDR<0.1 & resTbl$r<0, "Down", "No"))
cat("Up:", sum(resTbl$dir=="Up"), " Down:", sum(resTbl$dir=="Down"), "\n")

# shuffle ×5000：置换供体年龄标签，统计 |r| ≥ 真实 r_cut 的次数 → 经验 p
r_cut <- min(abs(resTbl$r[resTbl$FDR<0.1])); B <- 5000; n_sig_perm <- numeric(B)
set.seed(42)
for (b in 1:B) { r_perm <- apply(lcpm, 1, function(x) cor(x, sample(age))); n_sig_perm[b] <- sum(abs(r_perm) >= r_cut) }
perm_p <- mean(n_sig_perm >= sum(resTbl$FDR<0.1))
cat("shuffle: median=", median(n_sig_perm), " 真实显著=", sum(resTbl$FDR<0.1), " 经验p=", perm_p, "\n")

OUT <- "/hwfssz3/PS_JLU/zhangbo/patent"
saveRDS(list(all=resTbl, age=age, perm_nsig=n_sig_perm, perm_p=perm_p),
        file.path(OUT, "da_tiles_pearson_human.rds"))
for (d in c("Up","Down")) {
  sub <- resTbl[resTbl$dir==d, ]
  write.table(sub[,c("chr","start","end")],
              file.path(OUT, sprintf("da_tiles_pearson_human_%s.bed", tolower(d))),
              sep="\t", row.names=FALSE, col.names=FALSE, quote=FALSE)
  write.csv(sub, file.path(OUT, sprintf("da_tiles_pearson_human_%s.csv", tolower(d))), row.names=FALSE)
}
```

### 猴侧差异（3 处）

1. project 路径 → 猴 project；2. 聚合前 M4 剔除 + 列名自适应：
```r
proj <- loadArchRProject("/hwfssz3/PS_JLU/zhangbo/patent/Monkey-ArchR")
cd <- as.data.frame(getCellColData(proj))
IND <- ifelse("Individual" %in% colnames(cd), "Individual", "individual")  # 猴列名双写自动适配
proj <- proj[!is.na(cd[[IND]]) & cd[[IND]] != "M4", ]                     # ⚠️ M4 剔除必须在此（21→20 个体）
```
3. 输出前缀 `human` → `monkey`（猴坐标 MFA8，原样保存，不本地 liftover）。

### 四年龄组如何使用（v2）

- **检验层**：连续年龄 Pearson（保留每位供体真实年龄 → 统计力 > 4 组离散比较）
- **展示层**：拿 Up/Down tiles 按 Young/Middle/Old/EO 画四组均值趋势（下游 R 步骤，不参与显著性判定）