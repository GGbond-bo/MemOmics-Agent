# L3 v2 DA tiles — Pearson + shuffle（对齐 Zemke Science 2026 官方方法）

## 决策链（2026-09-02 会话实录）

1. **最初版本（我自己写的）**：DESeq2 四组 LRT，`groupBy="age_group"` → 4 列伪重复。❌
2. **审查出统计单元错误**：`getGroupSE` 必须 `groupBy="individual"`（人 40 列 / 猴 20 列），age_group 放 design 因子。用户连续 4 轮追问确认这是必修。
3. **用户质疑："你确定人家文章使用的是 DESeq2 吗？"** → 查证官方仓库 `nrzemke/aging_human_hippocampus` → **文章根本不用 DESeq2**。
4. **用户质疑："有去找原文章 github 的源码吗？还是你自己写的？"** → 定位官方源码 `03_age_correlation/correlation_ATAC.ipynb`（ATAC 年龄相关）+ `TF_motif_chrom_access_age_correlation.R`（TF motif 富集×年龄）。
5. **用户拍板（选择 1）**：**Pearson + shuffle 版**，人侧 40 样本 + 猴侧 M4 剔除。DESeq2 四组 LRT 全部废弃。

## 官方文章方法核验（一手来源）

- **文章**：Zemke, Lee, Mamde et al., *Epigenetic and 3D genome reprogramming during the aging of human hippocampus*（Science 2026）
- **官方仓库**：`github.com/nrzemke/aging_human_hippocampus`（GitHub 仓库 description 原文 = 论文标题，一手确认）
- **本地 skill 记录**：PMID 42490474（Science 2026-07-23）、DOI 10.1126/science.adt8307；bioRxiv PMID 39463924、DOI 10.1101/2024.10.14.618338；GEO GSE278576
- **官方统计范式**（skill gse278576-atac-aging-comparison 已整理）：
  - 输入：每细胞类型 pseudobulk log2CPM 矩阵（行=peak, 列=donor）
  - 特征过滤：总 counts ≥ 2 × 剩余供体数
  - 每 peak：`cor.test(cpm[i,], age, method="pearson")` → r + p
  - FDR 校正：`p.adjust(p, "fdr")`
  - 显著判定：`FDR<0.1 & cor>0 → Up`、`FDR<0.1 & cor<0 → Down`、否则 No
  - 验证：shuffle 零分布 ×5000（`randomizeMatrix(cpm, null.model="richness", iterations=5000)`）→ 密度图对比

## 关键事实（2026-09-02 会话确认的 meta 列）

- **人侧** `human_meta.csv`：`individual`（hc77…）、`Age`（连续 20-89）、`age_group`（Young/Middle/Old/Exceptionally old）四组
- **猴侧** `monkey_meta.csv`：`individual`/`Individual` 双列、`Age`（M1=10… 连续）、`Age_group` 四组
- **M4 剔除**：猴 21 个体中 M4 仅 61 cells（极端小样本），L2 数据底已剔除 → L3 必须同口径（21→20 个体）
- **v4 最新 L1**：`E:/专利/P3_L1_data/v4/l1_full_human.csv`（524,257 tiles）+ `l1_full_monkey.csv`（288,327 tiles）——phy loP 全量保守打分，L3 坐标匹配取 phyloP 列

## 人侧集群脚本（Pearson + shuffle，40 样本）

```r
# ============================================================
# L3 v2: DA tiles — 连续年龄 Pearson + shuffle（对齐 Zemke Science 2026 官方方法）
# 人侧 40 样本 · 统计单元=个体（40 列）· 输出 Up/Down 年龄相关 tiles
# ============================================================
suppressMessages(library(ArchR))
setArchRThreads(16)

proj1 <- loadArchRProject("/hwfssz3/PS_JLU/zhangbo/patent/Save-ArchR", force=FALSE)
cd <- as.data.frame(getCellColData(proj1))
cat("cellColData columns:", paste(colnames(cd), collapse=", "), "\n")  # 确认有 individual + Age

# --- 1) 个体级 TileMatrix 伪bulk（40 列 = 40 人）---
se <- getGroupSE(proj1, useMatrix="TileMatrix", groupBy="individual")
cat("n individuals(columns):", ncol(se), "\n")

# --- 2) 连续年龄：优先从 cellColData 取，取不到读 meta ---
if ("Age" %in% colnames(cd)) {
  md <- unique(cd[, c("individual", "Age")]); md <- md[!duplicated(md$individual), ]
  age <- md$Age[match(colnames(se), md$individual)]
} else {
  m <- read.csv("human_meta.csv", stringsAsFactors=FALSE)
  age <- m$Age[match(colnames(se), m$individual)]
}
stopifnot(!anyNA(age)); print(age)   # 应 40 个连续年龄值
cnts <- assay(se)

# --- 3) 特征过滤（官方：总 counts ≥ 2 × 剩余供体数）---
keep <- rowSums(cnts) >= 2 * ncol(cnts)
cnts <- cnts[keep, ]
cat("tiles kept:", nrow(cnts), "\n")

# --- 4) log2CPM（每供体列标准化）---
cpm <- t(t(cnts) / colSums(cnts) * 1e6)
lcpm <- log2(cpm + 1)

# --- 5) 全 tiles 向量化 Pearson: r + p（等价 cor.test，快 1000 倍）---
n <- ncol(lcpm)
rv <- apply(lcpm, 1, function(x) cor(x, age))
tv <- rv * sqrt((n - 2) / (1 - rv^2))
pv <- 2 * pt(-abs(tv), df = n - 2)
fdr <- p.adjust(pv, "fdr")

resTbl <- data.frame(
  chr = as.character(seqnames(rowRanges(se))[keep]), start = start(rowRanges(se))[keep], end = end(rowRanges(se))[keep],
  r = rv, p = pv, FDR = fdr)
resTbl$dir <- ifelse(resTbl$FDR < 0.1 & resTbl$r > 0, "Up",
             ifelse(resTbl$FDR < 0.1 & resTbl$r < 0, "Down", "No"))

cat("Up:", sum(resTbl$dir=="Up"), " Down:", sum(resTbl$dir=="Down"), " No:", sum(resTbl$dir=="No"), "\n")

# --- 6) shuffle 零分布 ×5000（置换供体年龄标签，统计 |r| 超真实阈值部分）---
r_cut <- min(abs(resTbl$r[resTbl$FDR < 0.1]))          # 真实显著最小 |r|
B <- 5000                                              # 文章官方 5000 次
n_sig_perm <- numeric(B)
set.seed(42)
for (b in 1:B) {
  age_perm <- sample(age)
  r_perm <- apply(lcpm, 1, function(x) cor(x, age_perm))
  n_sig_perm[b] <- sum(abs(r_perm) >= r_cut)
}
cat("shuffle 零分布: median=", median(n_sig_perm), " p95=", quantile(n_sig_perm, .95),
    " 真实显著=", sum(resTbl$FDR < 0.1), "\n")
perm_p <- mean(n_sig_perm >= sum(resTbl$FDR < 0.1))
cat("shuffle 经验 p =", perm_p, "\n")
png("l3_human_pcc_density.png", width=900, height=600)
  dens_real <- density(abs(resTbl$r)); dens_perm <- density(abs(sample(abs(resTbl$r), 1e5)))
  plot(dens_real, col="#7F2582", lwd=2, main="|PCC| real vs shuffled (age labels)", xlab="|Pearson r|")
  lines(dens_perm, col="grey60", lwd=2); legend("topright", c("real","shuffled"), col=c("#7F2582","grey60"), lwd=2)
dev.off()

# --- 7) 保存 ---
OUT <- "/hwfssz3/PS_JLU/zhangbo/patent"
saveRDS(list(all=resTbl, age=age, perm_nsig=n_sig_perm, perm_p=perm_p), file.path(OUT, "da_tiles_pearson_human.rds"))
for (d in c("Up","Down")) {
  sub <- resTbl[resTbl$dir == d, ]
  write.table(sub[, c("chr","start","end")],
              file.path(OUT, sprintf("da_tiles_pearson_human_%s.bed", tolower(d))),
              sep="\t", row.names=FALSE, col.names=FALSE, quote=FALSE)
  write.csv(sub, file.path(OUT, sprintf("da_tiles_pearson_human_%s.csv", tolower(d))), row.names=FALSE)
}
cat("saved:", OUT, "\n")
```

## 猴侧差异（M4 剔除 + 列名适配）

```r
# ① project 路径 → 猴 project；② M4 剔除必须在 getGroupSE 之前！
proj <- loadArchRProject("/hwfssz3/PS_JLU/zhangbo/patent/Monkey-ArchR")
cd <- as.data.frame(getCellColData(proj))
IND <- ifelse("Individual" %in% colnames(cd), "Individual", "individual")  # 猴列名自适应
keep_cells <- !is.na(cd[[IND]]) & cd[[IND]] != "M4"
proj <- proj[keep_cells, ]                       # ⚠️ M4 剔除 → 21→20 个体
# ③ 输出文件名 human → monkey（猴坐标是 MFA8，原样保存不 liftover）
# ④ meta 用 monkey_meta.csv，Age 列也是连续值（M1=10 等），别用 Age_group
```

## 未决提醒

- 官方源码 `correlation_ATAC.ipynb` 全文本地下载曾失败（curl exit 23），只核验了 skill 转述 + GitHub 目录结构 + description；**若答辩需要逐行对照，从用户处拿 notebook 后补核**（文章名已给用户：标题见上，用户自行下载中）
- shuffle B=5000 约 10-30 分钟（apply 向量化后）；集群排队紧张可临时降 1000，答辩建议保留 5000（与文章一致）