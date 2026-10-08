# KEGG/GO 富集：四项门禁的可复用配方（含实测数字）

来源：2026-09-24 会话（人骨骼肌肌纤维 `MF_2000.rds`，2,132 cells / 48 样本 / 6 组，Y_Post vs O_Post）。
脚本：`results/memomics-d53bc866/scripts/12_kegg_YPost_vs_OPost.R` + `12b_kegg_validation.R`
+ `12c_kegg_collapse_plot.R` + `12d_sample_level_and_module.R`。

---

## 0. 本例事实（用来对照你的结果是否同形）

| 环节 | 数字 |
|------|------|
| 细胞级 DEG（Seurat Wilcoxon, min.pct=0.1, logfc.threshold=0, padj<0.05 & \|log2FC\|≥0.5） | 406（上调 314 / 下调 92） |
| 富集背景 universe（`logfc.threshold=0` 拿到的全部可检测基因） | 8,061 |
| enrichKEGG（pvalueCutoff=1/qvalueCutoff=1 后按列判定） | 399 条；名义 p<0.05 = 62；FDR<0.05 = 33 |
| 上调 top（细胞级） | Diabetic cardiomyopathy 30/173 p=5.4e-11；Chemical carcinogenesis-ROS 27/173；**Oxidative phosphorylation 22/173 p=2.0e-8**；Glycolysis/Gluconeogenesis 10/173；Thermogenesis 25/173；Alzheimer 30/173；Huntington 25/173；Prion 23/173 |
| 下调（细胞级） | **Cytoskeleton in muscle cells 10/49 p=5.1e-5 FDR=0.0078**；Axon guidance 6/49（FDR=0.077）；MAPK 7/49；TGF-beta 3/49 |
| 冗余 | 上调 top20 里 11 条与 OXPHOS 互相 Jaccard 0.68–0.92 |
| 合并模块（并集重算） | OXPHOS/ETC（11 条合并，并集 995 基因，hit 46）= **p 1.58e-6 / FDR 1.13e-5**（≠ 成员最小 FDR 1.34e-8） |
| 组成混杂 | RSS 2.00% vs 16.38%（p=0.0145）、Pure IIA 17.33% vs 4.88%（p=0.035）、Pure IIX 8.44% vs 4.18%（p=0.018） |
| 样本级 Wilcoxon（n=10 vs 7, 23,674 基因） | **FDR<0.05 = 0**（结构性假阴性：min p 1.03e-4 vs BH 阈值 2.1e-6；名义 p<0.05 = 2,066 ≈ 预期 1,184 的量级） |
| 样本级 limma-trend | **FDR<0.05 = 427**（min p 8.55e-31）；DESeq2 Wald = 383 |
| 加组成协变量（~group+RSS+IIA+IIX） | limma FDR<0.05 = **33** |
| 通路级样本级读数 | hsa00190 OXPHOS：检出 126 基因，FDR<0.05 = 2、名义 = 21，中位 log2FC **+0.32**（CYC1 +1.05、ATP5MC3 +0.95、CYCS +1.27、COX5A +0.71）；hsa04820 肌细胞骨架：222 基因，FDR<0.05 = 19（DAAM2 +2.63、ITGB6 +1.48、FHL3 +1.41、TLN2 +1.07） |

**结论措辞**：细胞级探索性 + 样本级参数模型方向可复现（组成校正后大幅衰减）。
⛔ 不可写「无差异」（秩检验是限制），也不可写「确证差异」（混杂未排除）。

---

## 1. 门禁 2：BH 可达性自检（先算再解释阴性）

```r
n_tested     <- nrow(res)                    # 参与多重校正的基因数
min_p_wilcox <- 2 / choose(n1 + n2, n1)      # 秩检验最小可能双侧 p（n1=10,n2=7 → 1.03e-4）
bh_floor     <- 0.05 / n_tested              # min p 必须 ≤ 该值才有基因能达 FDR<0.05
cat("min_p_wilcox:", min_p_wilcox, "| bh_floor:", bh_floor,
    "| 可达:", min_p_wilcox <= bh_floor, "\n")
```

## 2. 门禁 1：样本级 pseudobulk（秩检验 + 参数模型并列）

```r
cnt  <- LayerData(obj[["RNA"]], layer = "counts")      # 一定用 raw counts
pb   <- sapply(split(cells, samp), function(cs) Matrix::rowSums(cnt[, cs, drop = FALSE]))
cpm  <- t(t(pb) / colSums(pb) * 1e6)
keep <- rowSums(cpm > 1) >= 3                          # 至少 3 样本 CPM>1

# ① 秩检验（会因离散度不可达，仅作对照）
p_w <- apply(log2(cpm[keep, ] + 1), 1, function(v)
  tryCatch(wilcox.test(v[grpv == "Y_Post"], v[grpv == "O_Post"])$p.value, error = function(e) NA))

# ② limma-trend（首选）
yl  <- log2(cpm[keep, ] + 1)
des <- model.matrix(~ grpv)
fit <- eBayes(lmFit(yl, des), trend = TRUE, robust = TRUE)
res_limma <- topTable(fit, coef = grep("^grpv", colnames(des))[1], number = Inf, sort.by = "P")

# ③ DESeq2 Wald（并列报告）
dds <- DESeq(DESeqDataSetFromMatrix(pb[keep, ], data.frame(grpv = grpv), ~ grpv), quiet = TRUE)
res_deseq <- results(dds, contrast = c("grpv", "Y_Post", "O_Post"))

# ④ 组成协变量敏感性
ppx <- do.call(rbind, lapply(split(md_sel, samp), function(x) {
  t <- table(x$annotation_L3) / nrow(x) * 100
  data.frame(RSS = as.numeric(t["RSS"]), IIA = as.numeric(t["Pure Type IIA"]),
             IIX = as.numeric(t["Pure Type IIX"])) }))
ppx[is.na(ppx)] <- 0; ppx <- ppx[colnames(pb), ]
des_c <- model.matrix(~ grpv + RSS + IIA + IIX, data = ppx)
```
> ⚠️ 协变量与分组高度共线时（组成差异本身由分组造成）会吃掉大部分信号——**这正是要看的敏感性结果**，两个模型都报，别只报好看的那个。

## 3. 门禁 3：构成差自检

```r
tab  <- table(md_sel$type, md_sel$annotation_L3)
prop <- prop.table(tab, 1) * 100                       # 组水平占比
pp   <- do.call(rbind, lapply(split(md_sel, md_sel$samplename),
                function(x) table(x$annotation_L3) / nrow(x) * 100))
pp   <- as.data.frame(pp); pp$type <- sapply(split(md_sel, md_sel$samplename),
                                             function(x) as.character(x$type[1]))
# 每个亚群：样本级比例 Wilcoxon
pv <- sapply(colnames(tab), function(ct)
  tryCatch(wilcox.test(pp[[ct]][pp$type == "A"], pp[[ct]][pp$type == "B"])$p.value,
           error = function(e) NA))
```

## 4. 门禁 4：通路冗余 → 连通分量合并 → 并集重算

```r
gl <- strsplit(kegg$geneID, "/"); names(gl) <- kegg$Description      # ENTREZ 列表
J  <- outer(seq_along(gl), seq_along(gl), Vectorize(function(i, j)
  length(intersect(gl[[i]], gl[[j]])) / max(1, length(union(gl[[i]], gl[[j]])))))
adj <- J > 0.5; diag(adj) <- FALSE
cl <- integer(length(gl)); cid <- 0
for (i in seq_along(gl)) if (cl[i] == 0) { cid <- cid + 1; q <- i
  while (length(q)) { v <- q[1]; q <- q[-1]
    if (cl[v] == 0) { cl[v] <- cid; q <- c(q, which(adj[v, ])) } } }

# 代表名：含 Oxidative phosphorylation 就用它；否则取非疾病名中基因数最大者
DIS <- "disease|cardiomyopathy|carcinogenesis|cancer|Parkinson|Alzheimer|Huntington|Prion|sclerosis"
# 模块 FDR：并集基因集 + 同一 universe 超几何
kk  <- clusterProfiler::download_KEGG("hsa")
ids <- setNames(kegg$ID, kegg$Description)                  # Description → hsa 号
pids <- unique(na.omit(ids[members]))
eg  <- intersect(unique(kk$KEGGPATHID2EXTID$to[kk$KEGGPATHID2EXTID$from %in% pids]), universe_entrez)
hit <- length(intersect(up_entrez, eg))
p   <- phyper(hit - 1, length(eg), length(universe_entrez) - length(eg),
              length(up_entrez), lower.tail = FALSE)
p.adjust(p, "BH")                                           # 模块之间也要 BH
```

## 5. 定稿气泡图（合并版）

```r
d$lab <- sprintf("%s%s", d$Representative,
                 ifelse(d$n_pathways_merged > 1, sprintf("  [+%d 冗余通路]", d$n_pathways_merged - 1), ""))
d$lab <- make.unique(as.character(d$lab), sep = " [#")      # ← 上下调同名通路会导致 factor 重名报错
d$lab <- factor(d$lab, levels = rev(unique(d$lab[order(d$p.adjust, decreasing = TRUE)])))
ggplot(d, aes(GeneRatio_num, lab)) +
  geom_point(aes(size = Count, color = -log10(p.adjust))) +
  scale_color_gradientn(colours = c("#4A6E8A","#8FB8D6","#F0C9A8","#D95F3B")) +
  facet_wrap(~Dir, ncol = 2, scales = "free_y") + theme_bw(base_size = 9)
ggsave("figures/kegg_bubble_collapsed_<对比>.png", width = 10, height = 5.6, dpi = 300, bg = "white")
# 另存 pdf + svg；探索期再加一版 color = -log10(pvalue) 的 rawP 图
```

## 6. 交付清单

主图（合并版）+ 附图（原始榜单、Jaccard 矩阵）+ 表（富集全表 / 组成比例表 / 样本级 limma、DESeq2 表 / 模块重算表）
+ 结论措辞按 SKILL.md 的措辞表。**上报时把「我先前说错的统计口径」显式更正**——本轮踩过：先报了「样本级 0 基因显著」，
L2 辩论指出这是结构性假阴性，随后用参数模型推翻。凡涉及阴性结论，先过门禁 2。