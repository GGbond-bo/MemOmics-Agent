# L2 ④ species:age_group 交互模型（2026-09-01 执行定稿）

专利核心空白点：**跨物种衰老动态一致性（species×age 交互）**——现有文献（Villar 2015 / Zemke 2023 / Andrews 2023）只做跨物种活性比较、无年龄维度。
本文件记录完整执行配方，含可直接复用的 base R 代码骨架（零新依赖）+ 置换检验 + 全部实证数字。

## 输入数据链路（都已核验）

| 文件 | 内容 |
|---|---|
| `E:/专利/P3_L1_data/file/human_GroupSE_byindividual.rds` | 525,137 peaks × 40 个体（hg38 坐标） |
| `E:/专利/P3_L1_data/file/monkey_GroupSE_byIndividual.rds` | 538,420 peaks × 21 个体（T2T-MFA8 坐标） |
| `E:/专利/P3_L1_data/monkey_peaks_hg38_map.csv` | 289,523 行逐峰猴→hg38 坐标映射（含 macaque_gene/human_gene 锚定） |
| `human_meta.csv` / `monkey_meta.csv` | Age_group 4 组标签（Young/Middle/Old/Exceptionally old） |
| `P3_L2_data/l2_alignment_prep.rds` | RBH 峰对 136,654（mi/hi/w 列）+ 两 SE |
| `P3_L2_data/l2_activity_normalized.rds` | log_m(136654×20) / log_h(136654×40) CPM+log1p 个体级矩阵 + colData |

## 第 1 步：峰对齐（l2_1_peak_alignment.R）

- ⛔ 跨物种峰坐标**禁止字符串精确匹配**（人 `chr1:...` vs 映射表 `1:...` → 统一前缀后仍 0，因为人猴 peak 边界不逐碱基相等）
- 正解：`findOverlaps(gr_monkey_hg38, gr_human, minoverlap=200)` → 777,279 重叠对
- ⛔ 严格 1:1 只剩 12,600（信息自杀）；**RBH（reciprocal best hit）**：`setorder(dt, mi, -w); best_m <- dt[!duplicated(mi)]; setorder(best_m, hi, -w); rbh <- best_m[!duplicated(hi)]` → **136,654 对**, 中位重叠 501bp
- chr 前缀统一：`if (!startsWith(chr,"chr")) chr <- paste0("chr", chr)`

## 第 2 步：归一化（l2_2_activity_normalize.R）

- `getGroupSE(divideN=TRUE)` 只做每细胞平均，**未做文库深度校正**（人 log10 nFrags 4.16 vs 猴 3.91，~1.8 倍差）
- 必加 CPM：`sweep(mat, 2, colSums(mat), "/")*1e6` + `log1p`
- 结果：`l2_activity_normalized.rds`（log_m/log_h = 峰对×个体矩阵，行序 = RBH 行序）

## 第 3 步：基因×个体矩阵（l2_4_gene_significance.R）

```r
gene_map <- data.table(rbh_row = 1:nrow(rbh), human_gene = map$human_gene[rbh$mi])  # rbh$mi 即 map 行号（已验证范围=289523）
log_m <- d$log_m; log_h <- d$log_h
# 按基因聚合（rowsum 求和 / 计数 = 均值），14927 唯一 human_gene × 60 个体
mat_m_gene <- rowsum(log_m[gidx, ], group=glab) / as.numeric(table(glab)[...])
# meta 组装：colData 无 age_group 列 → 从 monkey_meta/human_meta 的 Individual/individual 列 merge
```

⚠️ 14927（RBH 全锚定基因）> 早先 l2_gene_level 的 7456（可能只留双侧对称对）——建模用 14927，口径一致即可；报告时说明。

## 第 4 步：固定效应批量 OLS（l2_4c_gene_model_selfcontained.R，base R 零依赖）

```r
# Y: 60个体 x G基因（行序 = meta60: 猴20 + 人40）
spM <- ifelse(meta60$species=="monkey", 1, 0)
ag  <- factor(meta60$age_group, levels=c("Young","Middle","Old","Exceptionally old"))
D <- model.matrix(~ spM + ag + spM:ag)
colnames(D) <- c("(Int)","spM","agMid","agOld","agEO","spM:Mid","spM:Old","spM:EO")  # 8列 rank 8
qrD <- qr(D); beta <- qr.coef(qrD, Y); fit <- qr.fitted(qrD, Y)
df_res <- 60 - 8  # 52
rss <- colSums((Y-fit)^2); sigma2 <- rss/df_res
D0 <- D[, -c(6:8)]; rss0 <- colSums((Y - qr.fitted(qr(D0), Y))^2)
F_int <- ((rss0-rss)/3)/sigma2; p_int <- pf(F_int, 3, df_res, lower.tail=FALSE)
fdr_int <- p.adjust(p_int, "BH")
# 主效应同法：D[, -2] 去 species；D[, -c(3:5)] 去 age
# 落盘: l2_gene_model_results.rds/csv（gene, beta_int_mid/old/EO, F/p/FDR_interaction, p_species, p_age, sigma2）
```

## 第 5 步：置换检验（l2 置换，**验证显著基因数是否超出偶然的决定性工具**）

```r
set.seed(20260901)
nperm <- 200; perm_n <- integer(nperm)
for (b in 1:nperm) {
  idx <- sample(60); sp_p <- sp_obs[idx]; ag_p <- ag_obs[idx]   # 一起打乱保持物种-年龄组合结构
  Dp <- model.matrix(~ sp_p + ag_p + sp_p:ag_p)
  fitp <- qr.fitted(qr(Dp), Y); rssp <- colSums((Y-fitp)^2)
  rss0p <- colSums((Y - qr.fitted(qr(Dp[,-c(6:8)]), Y))^2)
  Fp <- ((rss0p-rssp)/3)/(rssp/df_res); pp <- pf(Fp, 3, df_res, lower.tail=FALSE)
  perm_n[b] <- sum(p.adjust(pp, "BH") < 0.05)
}
perm_pval <- (sum(perm_n >= obs_n) + 1)/(nperm + 1)   # +1 保守校正
```

实测：obs=16；perm median=0 / mean=7.32 / max=1460；**perm p = 0.00995** → 交互信号真实存在。
⚠️ 分布极端偏斜（median 0 / max 1460）——答辩主动说明"多数置换无显著、个别极端排列大数"。

## 实证数字总表（2026-09-01 权威）

| 指标 | 值 | 含义 |
|---|---|---|
| 基因级 ρ (Spearman) | 0.0128 [−0.0035, 0.0283] | 秩保守弱（含 0），背景陈述 |
| 交互 nominal p<0.05 | 1452 (9.73%) | 略高于 5% 期望 |
| 交互 FDR<0.05 | **16** | 候选标志物 |
| 交互 FDR<0.10 | 21 | 探索阈值 |
| 主效应 species | 10486 (70%) | 物种差异主导 |
| 主效应 age | 1948 (13%) | 池内年龄效应 |
| 置换 p | 0.00995 | 16 非偶然 |

16 显著基因 + β_int_EO（猴 EO 组偏离方向）：POP7(−1.01) IDS(+0.48) SNX16(−0.58) TBC1D25(−0.82) METTL17(−0.91) RBBP7(−0.53) GMNC(−0.45) COX7A1(−0.80) EFCAB13(+1.11) FBXO30(−0.61) IK(−1.06) ROBO4(+0.53) NDP(−0.25) PDK3(−0.46) S1PR4(−0.42) SCML2(−0.57)

## 专利主张措辞（辩论裁决 modify 定稿）

- ✅ 可写："16 个 FDR<0.05 交互基因作为跨物种衰老动态分歧的**候选标志物**"
- ❌ 禁止："全基因组/一般性衰老动态跨物种分歧"——ρ≈0 + 显著率 0.1% + 猴 n小 → A26.3 攻击面
- 独权骨架保持"评估方法 + 交互项检验 + 候选集优先级排序"，候选集是实施例证据
- 答辩补强：≥1000 次置换 / 独立队列验证 16 基因方向 / 效应量 95%CI

## 产物路径

```
E:/专利/P3_L2_data/l2_alignment_prep.rds           # RBH 峰对 + 两 SE
E:/专利/P3_L2_data/l2_activity_normalized.rds      # CPM+log1p 个体级峰对矩阵
E:/专利/P3_L2_data/l2_gene_individual_matrix.rds   # 14927 基因 × 60 个体
E:/专利/P3_L2_data/l2_gene_level.rds               # 早先 7456 基因全个体均值（口径旧）
E:/专利/P3_L2_data/l2_gene_model_results.{rds,csv} # 模型全结果
E:/专利/P3_L2_data/l2_interaction_significant_genes.csv  # 16 显著基因
E:/专利/P3_L2_data/l2_permutation_test.rds         # 置换分布 + p
figures/l2_gene_rho_bootstrap.png / l2_interaction_manhattan.png / l2_interaction_pval_dist.png / l2_permutation_dist.png
```

## 坑清单（本会话实测）

1. limma 两侧 R（4.5.3/4.4.2）都没有 → 用 base R 批量 OLS，不装包
2. Windows 同文件 readRDS 3 次 → `cannot open the connection` → 读一次复用
3. rail_review(post) `code_executed` 传摘要→"代码过短 + 未生成图"误报 3 次 → 必须传完整脚本正文 + 图路径
4. rbh 行序 vs SE 行索引混用 → NA 污染（`row_id := seq_len(.N)` 修复）
5. R 内核加载脚本用 `source()` 不是 `exec(open().read())`