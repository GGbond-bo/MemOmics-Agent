# L2 置换检验 1000 次升级 + 通路富集验证（2026-09-01 完整配方）

会话：memomics-cd677556 ｜ 输入：`E:/专利/P3_L2_data/l2_gene_individual_matrix.rds`（mat_m_gene/mat_h_gene/meta60）
脚本：`results/memomics-cd677556/scripts/l2_4e_permutation_1000.R`、`l2_4f_enrichment_16genes.R`、`l2_4g_direction_enrichment.R`

## 1. 置换检验 200 → 1000 次（正式版）

### 结果
- 观测 FDR<0.05 交互显著基因 = **16**（必须与主模型 `l2_gene_model_results.csv` 一致，不一致 = 参数化错）
- 置换分布：median=0，绝大多数置换 0 个；**个别肥尾置换达 8834**（极端偏斜，答辩主动说明）
- 置换 p = (1 + sum(n_perm >= n_obs)) / (1 + 1000) = **0.01698 < 0.05**（200 次版 0.00995；样本更大更保守）

### ⛔ 去截距列事故（必须避免）
- 为"优化"去掉设计矩阵截距列 `D <- D[, -1]` → 无截距参数化改变 F 统计量 reduced-model 基准
- 症状：观测从正确 16 变成 **14039（94%）**，置换分布 median 12379（整体畸形）
- 修复：`D <- model.matrix(~ spM + ag + spM:ag)` 保留全部 8 列，`D0 <- D[, -c(6:8)]`；`df_res = 60 - qr(D)$rank = 52`
- **核查门禁：重跑后先验证 `n_obs == 16`（与主模型 CSV 比对）再读置换 p**

### 高效实现（1000 次仅 62 秒）
```r
qrD  <- qr(D)             # 固定设计 QR 只分解一次
qrD0 <- qr(D0)
batchF_int <- function(Yx) {
  fit  <- qr.fitted(qrD, Yx);  rss  <- colSums((Yx - fit)^2)
  fit0 <- qr.fitted(qrD0, Yx); rss0 <- colSums((Yx - fit0)^2)
  sigma2 <- rss / df_res
  F_int <- ((rss0 - rss) / 3) / sigma2
  pf(F_int, 3, df_res, lower.tail=FALSE)
}
set.seed(123)
N <- 1000L; n_perm <- integer(N)
for (b in 1:N) {                       # 打乱 Y 行(观测) = 等价于打乱物种×年龄标签
  Yp <- Y[sample(nrow(Y)), , drop=FALSE]
  n_perm[b] <- sum(p.adjust(batchF_int(Yp), "BH") < 0.05)
}
perm_p <- (1 + sum(n_perm >= n_obs)) / (1 + N)
```

## 2. 通路富集验证（msigdbr 本地超几何，零新依赖）

### 环境探测
```r
# clusterProfiler / org.Hs.eg.db / GO.db / DOSE 全 FALSE
requireNamespace("msigdbr", quietly=TRUE)   # TRUE —— 唯一可用，内置数据离线可跑
```

### 超几何核心
```r
gs_go <- msigdbr(species="Homo sapiens", category="C5", subcategory="GO:BP")
gs_h  <- msigdbr(species="Homo sapiens", category="H")
gs <- rbind(data.table(gs_id=gs_go$gs_name, gene=gs_go$gene_symbol),
            data.table(gs_id=gs_h$gs_name,  gene=gs_h$gene_symbol))
universe <- unique(gs$gene[gs$gene %in% bg_genes])      # 背景 = 基因集∩建模基因 (13195)
N <- length(universe)
stat <- gs[, .(m=sum(gene %in% universe), x=sum(gene %in% query)), by=gs_id][m>0]
stat[, N:=N][, k:=length(unique(query[query %in% universe]))]
stat[, p := phyper(x-1, m, N-m, k, lower.tail=FALSE)]
stat[, FDR := p.adjust(p, "BH")][, fold := (x/k)/(m/N)]
setorder(stat, p)
```

### 结果（如实报告）
| 查询集 | top GO:BP（raw p） | FDR | 结论 |
|---|---|---|---|
| 16 交互基因 | 溶酶体靶向 / 细胞呼吸（p≈4.5e-4） | 全=1 | 小基因集无法过 7581 项 BH |
| 16 交互基因 Hallmark | E2F_TARGETS / HYPOXIA（p≈0.016） | 1 | 同上 |
| 289 上调同向 | 线粒体定位 / 轴突线粒体转运 / BCAA 代谢（p=1.2e-4） | 0.46 | 主题清晰未过校正 |
| 493 下调同向 | 糖复合物合成 / 血压调节（p=5e-4） | 1 | 同上 |

结论话术：**"跨物种保守信号是分散的基因集合（方向级显著、秩级不显著、通路级不聚团），而非整条通路程序的保守"**——与辩论裁决"候选标志物"定位一致。

### ⛔ 1:0 空集 bug + 0B 图
```r
# ❌ sum=0 时 1:0 = c(1,0) → NA 行 → barplot "need finite 'xlim' values" + 0B png
tp <- stat[cond][1:min(15, sum(cond))]
# ✅ 修复
idx <- which(cond)
if (length(idx) > 0) tp <- stat[idx][1:min(15, length(idx))]
```
rail_review(post) 会抓 0B/损坏图（"图片太小 (0B)"），必须重新生成后再交审；png 尺寸按 `nrow*55+300` 动态控制防超高。

### 其他坑
- EFCAB13 无 msigdbr 注释（16→k=15）→ 方法学写明 k=15，不补
- 小基因集 FDR 全 1 是统计常态（BH 阈值 p<6.6e-6），**不是 bug，禁止重跑**

## 3. 章节素材组装（L2_section_draft.md 模式）

专利长项目每层完成后可组装 6 节 Markdown 素材（可直接贴说明书/毕业论文）：
2.1 目的（数据/样本量）→ 2.2 方法（步骤表+脚本索引，可复现）→ 2.3 结果（三块结论+明细表）→ 2.4 主张表述铁律（辩论裁决 callout）→ 2.5 图表清单（图路径+用途表）→ 2.6 数据文件索引。
产出示例：`E:/专利/P3_L2_data/L2_section_draft.md`（8.5KB）。