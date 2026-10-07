# L2 ⑤ 保守基因（跨物种同向一致）分析 — 2026-09-01 实测完整配方

## 场景
用户拿到 16 个交互（分歧）候选基因后问："那有没有跟人保持一致的基因呢？"
→ 需要跑**同方向（conservation）**互补分析。方法学：先报分歧面 → 自动补一致面。

## 输入（复用既有产物，不重跑模型）
- `E:/专利/P3_L2_data/l2_gene_model_results.rds`：`$model`(14927×14)、`$Y`(60×14927 基因×个体)、`$meta60`(individual/species/age_group)
- meta60 组分布：猴 20（Young4/Middle4/Old6/EO6）、人 40（各 10）
- 组名必须统一：`levels=c("Young","Middle","Old","Exceptionally old")`（Young 基线）

## 完整分析脚本
文件：`results/memomics-cd677556/scripts/l2_5_conserved_stats.R`（统计）
+ `scripts/l2_5_conserved_scatter.R`（出图，source 加载）

```r
# 核心：物种内 OLS + 方向二项
run_within <- function(Ysub, ag) {
  D <- model.matrix(~ ag)
  qrD <- qr(D); beta <- qr.coef(qrD, Ysub); fit <- qr.fitted(qrD, Ysub)
  rss <- colSums((Ysub-fit)^2); df_res <- nrow(Ysub)-qrD$rank; sigma2 <- rss/df_res
  rss0 <- colSums((Ysub - qr.fitted(qr(D[,1,drop=FALSE]), Ysub))^2)
  F_age <- ((rss0-rss)/3)/sigma2; p_age <- pf(F_age,3,df_res,lower.tail=FALSE)
  idx_old <- which(grepl("^agOld$", colnames(D)))
  list(p_age=p_age, fdr_age=p.adjust(p_age,"BH"), logFC_Old=beta[idx_old,])
}
# 严格保守 = FDR_h<0.05 & FDR_m<0.1 & sign 同号
# 二项检验: binom.test(sum(same_dir), n, p=0.5) 拆上调/下调两组做
# 年龄效应 Spearman: cor(logFC_h, logFC_m, method="spearman") + bootstrap 500 CI
```

## 结果速查（14927 基因）
| 指标 | 值 | 含义 |
|---|---|---|
| 严格保守 | 0 | 猴 n=4-6/组功效不足 |
| 人上调(498) 猴同号 | 58.0% p=0.0004 | **上调保守★** |
| 人下调(1103) 猴同号 | 44.7% p=0.0005 | **下调分歧** |
| 年龄效应 ρ | 0.0047 CI 含0 | 无整体秩保守 |

## 答辩话术
- "保守的是衰老激活程序的方向（上调 58% 富集），具体基因名单跨物种不保守（严格 0 个）"
- 审稿人若问"你们说有跨物种保守性，但基因名单呢？" → 转方向级富集证据 + 候选 5 基因（CLEC7A/WAS/VSX1/CLEC2A/ARFGAP2）
- 防 A26.3：没有说没有，用集合方向富集支撑一致性主张

## 坑位
1. **read_file dedup**：同一文件多次 read_file 返回 "File unchanged since last read" → 用 `terminal cat` 强制读脚本全文再贴进 rail_review code_executed
2. **rail_review output_dir 必须含图**：指向无图目录（如数据目录）判未通过；指向 results/.../ 含图即过
3. **R 脚本用 source() 加载**：`source('path', encoding='utf-8')`，不要 `exec(open().read())`
4. **same_dir 判定**：`sign(x)==sign(y) & sign(x)!=0`（去掉 FC=0 的基因，否则 0 vs 0 误判同向）