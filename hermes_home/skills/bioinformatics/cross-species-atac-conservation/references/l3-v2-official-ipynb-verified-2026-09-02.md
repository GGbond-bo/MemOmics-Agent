# L3 v2 Pearson+shuffle 官方语义核验（2026-09-02 用户提供官方 ipynb 后修正）

> 本文件承接 `l3-v2-pearson-shuffle-2026-09-02.md`；**以本文件为准**——早期泛化版 shuffle 描述（置换年龄标签 + 经验 p）已被用户提供的官方 ipynb 推翻。

## 官方源码一手来源（用户本地已存）

- 文章：Zemke, Lee, Mamde et al., *Epigenetic and 3D genome reprogramming during the aging of human hippocampus*, Science 2026（GSE278576）
- 官方仓库：`github.com/nrzemke/aging_human_hippocampus` → `03_age_correlation/`
- **用户本地副本：`D:/我的下载/correlation_ATAC.ipynb`**（20 个细胞类型同一模板，核一份即可）
- 已核：该 ipynb 不是"我自己写的替代实现"——它就是文章中做 ATAC 年龄相关统计的官方代码

## 官方真实统计流程（逐 cell 核验，shuffle 语义修正点）

```
输入: <celltype>_log2cpm_filtered.tsv（peak × donor，已过滤）
  → 每个 tile/peak: cor.test(cpm, age, method="pearson") → r, p
  → BH FDR < 0.1
  → r > 0 → "Up"（年龄↑可及性↑）；r < 0 → "Down"；否则 "No"
  → shuffle: randomizeMatrix(cpm, null.model="richness", iterations=5000)（picante 包）
     → 打乱表达矩阵（行内重排），再算 shuffled PCC → 只画密度图（真实 vs shuffled 对比）
     → 不参与 FDR 判定，不算经验 p
```

| 项 | 官方（ipynb 原句） | 早期错误写法（作废） |
|---|---|---|
| shuffle 对象 | **表达矩阵** `randomizeMatrix(cpm, null.model="richness")` | ❌ 置换年龄标签 `sample(age)` |
| shuffle 用途 | **只画密度图**（真实 r vs shuffled r 分布对比） | ❌ 额外算"经验 p 值" |
| 显著判定 | `FDR<0.1 & cor 符号` → Up/Down，**无 FC 门槛** | ⚠️ 曾加 FC 0.25/0.5 门槛 |
| 分层 | 文章按 20 细胞类型分别跑（看细胞类型特异衰老） | ⚠️ 专利 L3 要全海马保守性，**不要照搬分层**（猴侧某些类型样本极少，拆碎保守信号） |
| 输出 | `<ct>_ATAC_pcc_donor_counts_filt_donors.tsv` + `<ct>_pcc_fdr_0.1.tsv` + 密度图（真 #B0D229 / shuffled #999999）+ 热图 | ❌ 自定义 bed/csv 缺官方格式（下游转 bed 可以，但保留官方 tsv 格式做溯源） |

## 代码（人侧 40 个体，向量化等价版本——比官方 foreach 快千倍但统计等价）

```r
suppressMessages({library(ArchR); library(picante)}); setArchRThreads(16)
proj1 <- loadArchRProject("Save-ArchR", force=FALSE)

se <- getGroupSE(proj1, useMatrix="TileMatrix", groupBy="individual")   # 40 列，⚠️ 勿用 age_group
# metadata 优先从 project 取（用户确认 cellColData 可以且更好）：
md <- as.data.frame(proj1@cellColData)
um <- unique(md[, c("individual","Age")])                 # 细胞级→个体级，必须 unique()
age <- um$Age[match(colnames(se), um$individual)]
stopifnot(!anyNA(age))

cnt <- assay(se); keep <- rowSums(cnt) >= 2*ncol(cnt)     # 官方特征过滤
lcp <- log2(t(t(cnt[keep,])/colSums(cnt[keep,])*1e6)+1)   # log2CPM
n <- ncol(lcp); r <- apply(lcp,1,cor,age)
p <- 2*pt(-abs(r*sqrt((n-2)/(1-r^2))), n-2); q <- p.adjust(p,"fdr")
gr <- rowRanges(se)[keep]
out <- data.frame(chr=seqnames(gr), start=start(gr), end=end(gr), r, p, q)
up <- out[q<0.1 & r>0,]; dn <- out[q<0.1 & r<0,]
paste0("human tiles:", nrow(out), " Up:", nrow(up), " Down:", nrow(dn))
write.csv(up,"human_ageDA_up.csv",row.names=FALSE); write.csv(dn,"human_ageDA_down.csv",row.names=FALSE)

# shuffle 只用于密度图（可选；官方 5000 次打乱矩阵）
cpm_shuf <- randomizeMatrix(lcp, null.model="richness", iterations=5000)
r_shuf <- apply(cpm_shuf, 1, function(x) cor(x, age))
plot(density(r, adjust=1.8), col="#B0D229", lwd=2, xlim=c(-1,1), main="All Tiles - Pearson Correlation")
lines(density(r_shuf, adjust=1.8), col="#999999", lwd=2); legend("topright", c("real","shuffled"), col=c("#B0D229","#999999"), lwd=2)
```

## 猴侧差异（3 处）

1. project 路径改猴；2. **M4 剔除必须在 getGroupSE 前**（`proj <- proj[!is.na(cd$Age_group) & cd[[IND]] != "M4",]`，21→20 个体，与 L2 一致）；3. 列名 `Individual`/`Age` 大写（若 cellColData 有 `Individual`）+ 输出名 human→monkey，坐标为 MFA8 原样保存不 liftover（本地 `monkey_peaks_hg38_map.csv` 接 hg38）。

## L3 五步全貌（Pearson 只是 1–2 步）

1. 人侧 age-DA tiles（Pearson+FDR<0.1 连续年龄）
2. 猴侧 age-DA tiles（同法，M4 剔除→20 个体）
3. **跨物种保守比较（灵魂）**：猴 tile→hg38 → 人猴 Jaccard + 方向一致率 vs 随机背景 1000 次经验 p
4. motif 富集：保守 age-DA tiles 富集哪些 TF
5. CRECS 综合打分

**专业判断（用户问"这是我们 L3 需要的吗"的标准答案）**：需要，但 Pearson 版是 L3 的前 1-2 步——只跑完它 = 复刻 Science 文章的单物种图谱，不是专利。审稿人真正会问的是第 3 步"人猴重叠是否显著多于随机"——shuffle 移到第 3 步的随机背景统一检验更贴问题、更省时间（单物种 5000 次 shuffle 对专利价值低）。