# 富集结论的五类误读 + 无 clusterProfiler 时的离线 ORA 实现

适用于对**已算好的 DEG 表**做 GO/KEGG 富集后定稿结论的场景（不重跑 DE）。
实测参考：人示例组织 aging，10 个 annotation_L3 亚群 × 17,395 基因，单对比，
|logFC| ≥ 0.5 且 adj.P < 0.05（2026-10-23）。

---

## A. 五类必须拦下的误读

### A1. KEGG 疾病名通路 ≠ 该疾病（最高频、最严重）

msigdbr `C2/CP:KEGG_LEGACY` 里的 **`KEGG_PARKINSONS_DISEASE` 几乎完全由线粒体氧化磷酸化
（复合物 I 为主）基因组成**。它在衰老 / 肌肉 / 任何线粒体相关数据里必然显著，
**语义上等于「OXPHOS 下调」的同义反复**。

同类：`KEGG_ALZHEIMERS_DISEASE`、`KEGG_HUNTINGTONS_DISEASE`、`KEGG_AMYOTROPHIC_LATERAL_SCLEROSIS`
都是线粒体 / 蛋白酶体基因的集合。

**判据**：疾病名通路显著时，看 `OXIDATIVE PHOSPHORYLATION` / `RIBOSOME` 是否同时显著且 fold 接近
（实测：RP_high(II) 亚群 OXPHOS GO padj 2.7e−48 fold 7.4，KEGG PD padj 4.6e−48 fold 8.1 —— 同一件事）。
**处理**：按机制通路报告（呼吸链下调），疾病名只在表里保留原样，**正文不得写成疾病关联**。

### A2. 「显著条目数」不是效应强度
>1,000 个基因的查询列表几乎必然出上百条 padj<0.05（实测 Type IIA-Down 116 条）。
按条目数排名会挑出最差的可解释性。**读 fold 与 padj，不读条目数。**

### A3. 0 条显著 ≠ 无变化
实测 RSS-Up 带 **2,214 个基因却 0 条显著通路**；OTUD1+(I)-Down 593 个基因同样 0 条。
前者 = 上调是**分散、非协同**的（长尾低效应量堆积，没有开关被打开）；
后者 = **power 不足**。两者都必须写成「未检出协同通路」，不能写成「无变化」。

### A4. 三个「口径」不声明就无法复核
1. **推断单位**：细胞级 limma 表（伪重复）vs 供体级 pseudobulk —— 决定结论是候选级还是确证级；
2. **universe 定义**：必须 = **该分组自己检测到的基因**（实测各组 12,268–26,879，
   差 2 倍以上；取并集/全基因组会让「测得少的组」虚假富集）；
3. **BH 家族范围**：在「该组×该方向实际检验的全部集合池」内统一校正（实测 GO:BP 7,538 +
   KEGG 186 = 7,724 组一起校正，偏保守；按库分开校正时 KEGG 会多出显著条目）。
   写清范围，否则读者无法复算 padj。

### A5. 跨库「三口径一致」不是独立验证
HALLMARK / KEGG / GO:BP 的同名通路基因高度共享（Jaccard 常仅 0.25–0.48）。
报结论前先算 Jaccard / leading-edge 重叠；高度共享则**不得**按「多次独立复现」计分。

---

## B. 无 clusterProfiler 时的离线 ORA（msigdbr + Matrix + phyper）

本机 `clusterProfiler=FALSE / DOSE=FALSE`，但 `msigdbr + Matrix + ggplot2 + data.table` 齐 →
**不要装包、不要走网络 Enrichr**，直接用本地基因集手写超几何 ORA。20 组约 1–2 分钟（R 4.4.2）。

### B1. 基因集解析（msigdbr 26.1.0 实测可用 + 必须带 fallback 链）

```r
grab_first <- function(cands) {
  for (cd in cands) {
    r <- try(if (compareVersion(as.character(packageVersion("msigdbr")), "10.0.0") >= 0)
               msigdbr(collection = cd[1], subcollection = cd[2])
             else msigdbr(category = cd[1], subcategory = cd[2]), silent = TRUE)
    if (!inherits(r, "try-error") && nrow(r) > 0) return(as.data.table(r))
  }
  stop("no gene set collection resolved")
}
gobp <- grab_first(list(c("C5","GO:BP"), c("C5","GO"), c("C5","BP")))          # 7,538 组
kegg <- grab_first(list(c("C2","CP:KEGG_LEGACY"), c("C2","CP:KEGG_MEDICUS"),
                        c("C2","CP:KEGG"), c("C2","KEGG")))                     #   186 组
```

msigdbr ≥10.0.0 弃用 `category=`/`subcategory=`，改 `collection=`/`subcollection=`。
symbol 列名兜底：`gene_symbol` / `human_gene_symbol` / 含 "symbol" 的任一列。
统一 `toupper()` 匹配即可，**不需要 org.Hs.eg.db** 做 SYMBOL↔ENTREZ 映射。

### B2. 检验

```r
p <- phyper(k - 1, K, N - K, n, lower.tail = FALSE)
# k = 命中集合的查询基因数; K = 集合在 universe 内的基因数;
# N = universe 大小; n = 查询基因数(必须 ⊆ universe)
fold <- (k / n) / (K / N)     # 富集倍数 —— 比条目数更该看
```
过滤 `minSize = 15` / `maxSize = 500`（小集合防护见 functional-enrichment 的 Common Issues）。

### B3. 三个必踩的 R 报错（原文便于检索）

**① `选择了未定义的列` —— data.frame 退化**
```
错误于`[.data.frame`(sets_all, sets_all$symbol %in% universe): 选择了未定义的列
```
`rbind(df1, df2)` 出来还是 **data.frame**，此时 `x[logical]` 是**列选择**语义，
后续所有 `DT[i]` 语法失效。→ `as.data.table(rbind(...))` + `unique(by=c("db","gs_name","symbol"))`
（顺带防 `sparseMatrix` 对重复 (i,j) **求和**导致 K 虚高）。

**② `non-conformable arguments` —— sparseMatrix 维度被截断**
```
错误于 M %*% sel: non-conformable arguments
```
`sparseMatrix(i=, j=, x=)` 不传 `dims=` 时按 `max(i)/max(j)` 推维度；
基因集不覆盖 universe 中索引最大的基因 → `ncol(M) < N`。只在「有些基因不在任何集合里」时暴露。
```r
M <- sparseMatrix(i = match(sub$gs_name, gs_lv), j = match(sub$symbol, u_genes),
                  x = 1, dims = c(length(gs_lv), length(u_genes)))   # ← 必须显式
sel <- integer(length(u_genes)); sel[match(query, u_genes)] <- 1L
k   <- as.integer(M %*% sel)
```

**③ `找不到对象'xxx'` —— facet_wrap 里塞表达式**
```
Calls: dotplot_db ... check_vars -> is_mapping -> <Anonymous> -> interaction
```
`facet_wrap(interaction(a,b,sep="\n"), ...)` / `paste(...)` 在数据上下文之外求值。→ 先落实体列：
```r
d[, facet_grp := paste(as.character(celltype_f), as.character(dir_f), sep = "\n")]
ggplot(d, ...) + facet_wrap(~ facet_grp, scales = "free_y", ncol = 5)
```
热图底表用 `expand.grid`（不要用 `CJ` 传 factor）后，**levels 必须显式指定**：
```r
LVL <- as.vector(outer(CT_ORDER, c("Up","Down"), function(a,b) paste(a, b, sep="\n")))
m2[, lvl := factor(paste(celltype, direction, sep="\n"), levels = LVL)]
```

### B4. 交付物形状

| 类别 | 内容 |
|---|---|
| 全量表 | 每个 (group × direction) **所有被检验集合**及 K/k/fold/p/padj |
| top 表 | 每组 top10 显著条目（给人看） |
| 图 | 每库一张分面 lollipop：x = −log10 padj，size = k_hit，color = direction，facet 按 group×direction |
| 图 | 跨组共享条目热图：signed −log10(padj)，红 = Up 富集 / 蓝 = Down 富集 / 灰 = 不显著，**上限截 20** |
| 声明 | A4 的三项口径 + A1 的疾病名免责（缺一不可） |