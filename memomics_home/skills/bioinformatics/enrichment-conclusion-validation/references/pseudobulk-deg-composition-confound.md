# Pseudobulk DEG 的组成混杂控制与交付口径（2026-09-24 实测配方）

> 场景：在**混合细胞群体**的单细胞对象上做「条件 A vs 条件 B」差异表达（如 MF 整体、未细分亚群的全组织），
> 主结果用样本级 pseudobulk DESeq2。**核心风险：所谓"下调基因"其实是组间亚群比例变化**——耗竭亚群的标志基因在样本聚合后被整体拉低。
> 本文件是 `enrichment-conclusion-validation` 门禁 3 强化的配套完整配方；`deg-analysis` 由人工维护、不允许 agent 自动改，故实现坑也一并记在这里。

## 0. 判断要不要走这套流程
- 数据含多个 celltype / subcluster 层（`annotation_L3` 之类）且两组**组成明显不同** → 必须走。
- 只关心已纯化的单一细胞类型 → 组成风险小，做常规稳健性即可。

## 1. 主分析骨架（两层，缺一不可）
| 层级 | 方法 | 参数 | 定位 |
|---|---|---|---|
| 主结果 | pseudobulk：按 `samplename` 稀疏求和 → DESeq2 `~type` | BH；`padj<0.05` 且 `|log2FC|>=0.5` | 结论唯一依据 |
| 探索 | 细胞级 `FindMarkers(test.use="wilcox", logfc.threshold=0, min.pct=0.10)` | BH | 仅方向佐证 |

细胞级 Wilcoxon 在嵌套设计下把细胞当独立重复（伪重复），**不得作为最终结论**
（方法学证据：[PMID:40794957] Hafner et al. 2025 *Brief Bioinform*，DOI 10.1093/bib/bbaf397）。

## 2. Pseudobulk 实现四坑（写脚本前先读，全部实测）
```r
# ① 不要用 AggregateExpression（layer 参数签名冲突，且 tryCatch 兜底会把错误吞掉）
cnt <- GetAssayData(sub, assay = "RNA", layer = "counts")   # 老版 Seurat 用 slot = "counts"
grp <- as.character(sub$samplename); su <- unique(grp)
pb  <- vapply(su, function(s) as.numeric(Matrix::rowSums(cnt[, grp == s, drop = FALSE])), numeric(nrow(cnt)))
pb  <- round(as.matrix(pb)); colnames(pb) <- su
rownames(pb) <- rownames(cnt)          # ② 必须补！vapply 丢 names → 基因名变行号 → 与细胞级交集=0（静默灾难）
# ③ 样本名→组别 用唯一映射表 + 硬校验（否则 match 出 NA → design formula cannot contain NA: type）
smap <- unique(data.frame(samplename = as.character(sub$samplename), type = as.character(sub$type)))
col_tab <- data.frame(sample = colnames(pb)); col_tab$type <- smap$type[match(col_tab$sample, smap$samplename)]
ok <- !is.na(col_tab$type); pb <- pb[, ok, drop = FALSE]; col_tab <- col_tab[ok, , drop = FALSE]
stopifnot(!any(is.na(col_tab$type)), ncol(pb) >= 4, sum(res_pb$gene %in% mk$gene) > 0)
# ④ Cook 距离写全名（精简会话没 attach SummarizedExperiment）
cm <- SummarizedExperiment::assays(dds)[["cooks"]]
```
读数为 0 的教训：**这些坑没有一个会报错**，只有对着 `gene` 列名和交集数才看得出来。

## 3. 组成混杂四件套（缺一件结论就降级）
1. **组成表** `table(annotation_L3, type)` + 各组占比
   实测：RSS 16.4%→2.0%、Specialized MF 12.2%→3.3%、Pure Type IIA 4.9%→17.3%、Pure Type I 8.4%→15.3%。
2. **marker Fisher 富集**：每亚群 `FindAllMarkers(only.pos=TRUE, min.pct=0.25, logfc.threshold=0.25)` 取 top50，vs 下调基因集做 Fisher（`alternative="greater"`），BH 校正。
   实测：RSS 21/50（13.8×，BH 1.6e-18）、Specialized MF 15/50（9.9×）、OTUD1+(I) 15/50（9.9×）、OTUD1+(II) 7/50（4.6×，BH 1.8e-3）；Pure I/IIA/IIX、RP_high 全部 0–3 个、ns。
3. **秩检验（不依赖 top50 阈值）**：全基因按亚群特异性 `avg_log2FC` 排序（`FindAllMarkers(only.pos=FALSE, min.pct=0.05, logfc.threshold=0)`），比较下调基因的秩 vs 其余基因（Wilcoxon 秩和，`alternative="less"`）。
   实测：仅 OTUD1+(II)（p=0.0082，BH 0.082）与 RSS（p=0.0179，BH 0.090）名义显著 ⇒ **第 2 步的强富集对阈值敏感，措辞降为"趋势"**。
4. **组成协变量 + 共线性诊断**：样本组成比例 → CLR 化 → `prcomp` 第一主成分 `compPC1` → DESeq2 `~type + compPC1`；报 Pearson/Spearman/R²/**VIF**。
   实测：Pearson 0.40、Spearman 0.34、R² 0.16、VIF 1.19 → **可估**，且下调 209/209 完全保留、方向冲突 0
   ⇒ 说明下调**不能被组成主成分单独解释**（但仍不等于排除混杂；VIF>5 或 |r|>0.7 时禁止说"组成校正后的独立效应"）。

**within-L3 / 亚群内 pseudobulk 可估判据**：每样本每亚群 **≥10 细胞 且 每组 ≥3 个可估样本**。
实测（2,132 cells / 每样本 45 cells / 10 个 L3）：**10 个 L3 全部不可估**（每样本每 L3 仅 4–5 细胞）。
按大类合并（RSS+Specialized / Pure I+IIA+IIX / Mixed 5 亚群）后仅 **Mixed（396 cells）可估** → 下调 83，其中 69 与全局重叠、0 冲突，作方向性佐证。
⇒ 不可估就写"数据不允许更细的校正"，**不要降门槛硬跑**。

## 4. 稳健性四件套（一个脚本跑完，别分轮）
| 项 | 做法 | 实测 |
|---|---|---|
| 剔除小样本 | 去掉细胞数 <30 的样本（如 17 cells 的样本）重跑 | 下调 209→225，与全量重叠 187/209 |
| leave-one-sample-out ×N | 逐样本剔除重跑，统计每个下调基因「符号一致 / 仍显著」 | 符号 100% 一致；93/209 每次显著；145/209 ≥80% 显著 |
| 阈值扫描 | `padj{0.01,0.05,0.1} × \|log2FC\|{0,0.25,0.5,0.75}` | 下调 104/209/311（lfc=0）；92/180/236（lfc=0.75） |
| Cook 距离 | `cm > 3*qf(0.99, 3, n-3)` 逐样本计数 | 17 个样本全部 0（无单样本主导） |

## 5. 三级交付表 + 一句话口径
- `tier`：`1_conservative_core`（主候选 且（双方法交集 或 LOO 全显著））／`2_main`（`padj<0.05` 且 `|log2FC|>=0.5`）／`3_candidate`（仅 `padj<0.05`）。
  实测：保守核心 120（双方法交集 76 / LOO 全显著 92）+ 主候选 86。**tier 定义必须写进随附 md**，否则"高置信"含义会漂移。
- 交付措辞（不得写"驱动/因果/细胞内在下调"）：
  > "在 X 整体样本层面检出 N 个 A vs B 下调候选（pseudobulk DESeq2，padj<0.05，方向 LOO 100% 一致）。由于两组 annotation_L3 组成严重失衡、within-L3 检验因细胞数不足不可估，该列表应视为**组成 + 表达混合**的候选，不可解读为亚群内细胞内在下调。"

## 6. 出图（≥3 张，都有实质信息）
1. **火山图**：x = `log2FC`(pseudobulk)、y = `-log10(padj)`，蓝=下调 / 橙=上调 / 灰=NS，`geom_text_repel` 标注下调 top12；`theme_classic(base_size=7)`，90×95 mm，PNG + PDF + TIFF（`compression="lzw"` 只给 tiff，png/pdf 传了会报 unused argument）。
2. **诊断四联**：size factor 条形 / p 值直方图 / MA 图 / 细胞级 vs pseudobulk `log2FC` 散点（`patchwork` 的 `(d1|d2)/(d3|d4)`）。
3. **混杂图**：A 下调基因 × 各亚群 marker 富集倍数条形（标 BH<0.05）、B 各亚群组间占比条形。
4. 敏感性汇总：LOO 显著性比例直方图 + 阈值扫描柱状。
- `ggrepel` 缺失时用 `requireNamespace()` 守卫降级为 `geom_text`；`rail_review(post)` 的 `output_dir` 传**会话根目录**（`figures/` 与 `results/` 是平级子目录，传 `results/` 会被判"未生成任何图片"）。

## 7. 交付前自检
- [ ] pseudobulk 的 `gene` 列是**基因名**不是行号
- [ ] 双方法交集**不为 0**（为 0 先查基因名，再谈生物学）
- [ ] 组成表 + marker Fisher + 秩检验 + 共线性四件套齐
- [ ] within-L3 可估性有明确结论（可估给结果 / 不可估写限制）
- [ ] 三级表 + tier 定义 md + 口径段落（无因果措辞）
- [ ] 火山图 / 诊断图 / 混杂图三张齐全且非空白