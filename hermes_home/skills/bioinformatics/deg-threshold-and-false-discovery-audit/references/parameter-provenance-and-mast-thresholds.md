# 参数溯源与 MAST 阈值 —— 实证原始记录

来源会话：`memomics-afd2d418`（人骨骼肌衰老/运动/糖尿病，5 个对比组，2026-09-29）。
本文只记**逐字实证**，推断部分显式标注。

---

## 1. 源码级实证（本机实测，非文档转述）

R 库：`C:/Users/<user>/AppData/Local/R/R-4.4.2/library` · Seurat 5.5.0 · MAST 1.32.0

### 1.1 Seurat `FindMarkers` 是 S3 泛型 —— 默认值要到方法级拿

```r
formals(Seurat::FindMarkers)
# object = , ... =            ← 泛型本身没有默认值，直接取会得 NULL（易误判）
```

方法级实测：

| 方法 | `logfc.threshold` | `min.pct` | `test.use` |
|---|---|---|---|
| `FindMarkers.default` | **0.1** | **0.01** | `"wilcox"` |
| `FindMarkers.Assay` | — | — | `"wilcox"` |
| `FindMarkers.StdAssay` | — | — | `"wilcox"` |

⇒ **Seurat 5 把默认从 v3/v4 的 0.25 改成了 0.1**。脚本不显式写阈值 = 结果随 Seurat 版本漂移。

取方法级 formals 的写法（避开 getFromNamespace 取不到泛型方法的情况）：
```r
f <- getFromNamespace("FindMarkers.default", "Seurat")
formals(f)[c("logfc.threshold","min.pct","test.use")]
```

### 1.2 MAST 官方函数：一个都不是效应量阈值

| 函数 | formals 实测 | 真实用途 |
|---|---|---|
| `zlm()` | `formula, sca, method, silent, ebayes, ebayesControl, force, hook, parallel, LMlike, onlyCoef, exprs_values` | **无任何阈值参数** |
| `filterLowExpressedGenes()` | `assay, threshold = 0.1` | **基因表达频率过滤**（`freq() > threshold`），非效应量 |
| `mast_filter()` | `sc, groups, filt_control, apply_filter`；默认 `list(filter=TRUE, nOutlier=2, sigmaContinuous=7, sigmaProportion=7, sigmaSum=NULL, K=1.48)` | **细胞级离群过滤**（QC 性质），与 DEG 阈值无关 |
| `thresholdSCRNACountMatrix()` | `data_all, conditions, cutbins, nbins=10, bin_by="median", qt=0.975, min_per_bin=50, absolute_min=0, data_log=TRUE, adj=1` | 表达矩阵阈值化（预处理） |

`mast_filter` 源码头部（实测 deparse）：
```r
default_filt <- list(filter = TRUE, nOutlier = 2, sigmaContinuous = 7,
                     sigmaProportion = 7, sigmaSum = NULL, K = 1.48)
```

### 1.3 MAST 原文（Finak et al. 2015）

- PMID 26653891 · PMC4676162 · *Genome Biology*
- 全文可解析句 261 条，含 MAST/hurdle 43 条，**与「阈值」同句仅 4 条**，全部是 FDR 性能比较，例如：
  > "As expected, MAST did not detect any significant differences … whereas DEseq and edgeR, designed for bulk RNA-seq, detected a large number of differentially expressed genes even at a stringent nominal false discovery rate (FDR)."
  > "SCDE, a single-cell RNA-seq specific method, also had higher FDRs than MAST."
- ⇒ **原文从未推荐过效应量阈值。**

---

## 2. 文献实证：论文实际怎么写

Europe PMC 检索 `"logfc.threshold" OR "log2FC threshold" OR "log2 fold change threshold"` + `FindMarkers` + `OPEN_ACCESS:Y` ⇒ **hitCount = 1263**。抽样 5 篇：

| PMID / PMC | 系统 | 写法原文（摘） |
|---|---|---|
| PMC13388743（CTC 结直肠癌） | Seurat Wilcoxon | 同篇两用：marker 用 log2FC 0.25；正式 DEG 用 `logfc.threshold` 设为 `0`，原文 "allowing all genes to be evaluated" |
| PMC13452298（胰岛 CVB3 方案） | FindAllMarkers | marker `logfc.threshold = 0.25`；`FindMarkers` DEG 用 `logfc.threshold = 0` + `min.pct = 0.25` |
| PMC13073673（SASP 衰老） | **Seurat v4** | `logfc.threshold = 0.25` + `test.use = "wilcox"` + 细胞数 ≥50 |
| PMC7619458（犬感觉神经元） | FindMarkers | `logfc.threshold = 0.25, min.pct = 0.10, test.use = "wilcox"`，**再叠** `p_val < 0.001` |
| PMC13115725（嗜酸-嗜碱-肥大细胞） | FindMarkers | `min.pct = 0.25`、`logfc.threshold = 0.1`（= Seurat v5 默认） |

**规律**：0 / 0.1 / 0.25 三档并存；同篇常两用（marker 严、比较宽）；**无一篇写「参考某文献」**。

---

## 3. 权威方法学文献（引立场，不引阈值）

| 文献 | 逐字结论 |
|---|---|
| **Squair et al. 2021**, *Nat Commun* · [PMID 34584091](https://pubmed.ncbi.nlm.nih.gov/34584091/) · DOI 10.1038/s41467-021-25960-2 · PMC8479118 | "We find that differences in the performance of these methods reflect **the failure of certain methods to account for intrinsic variation between biological replicates**." / "**Pseudobulk methods outperform generic and specialized single-cell DE methods**" / "**Single-cell DE methods are biased towards highly expressed genes**" / "To test this possibility, we **disabled the aggregation procedure** and applied the pseudobulk methods to individual cells … **Strikingly, this procedure abolished the superiority of the pseudobulk methods**." —— 该文把 MAST 列为 7 种细胞级方法之一（"the two-part hurdle model implemented by MAST"），14 种方法共评 + 18 个 ground-truth 数据集。 |
| **Crowell et al. 2020**（muscat）, *Nat Commun* · [PMID 33257685](https://pubmed.ncbi.nlm.nih.gov/33257685/) · PMC7705760 | "**Since relying on thresholds alone is prone to bias**, we next clustered the (per-subpopulation) fold-changes across the union of all differentially expressed genes." |
| **Murphy & Skene 2022**, *Nat Commun* · [PMID 36550119](https://pubmed.ncbi.nlm.nih.gov/36550119/) · PMC9780232 | pseudobulk 优于混合模型 / 伪重复做法（独立第三方印证）。 |
| 本项目 KB `deg.yaml` | pseudobulk `logfc_threshold = 0.5`（source: domain_convention, confidence: medium）—— **惯例值，非文献值** |

---

## 4. 可复用配方：从文献 Methods 抽原句

`scripts/extract_methods_sentences.py`（本 skill 附带）—— 给 PMCID 列表 + 关键词正则，抓 Europe PMC `fullTextXML`、剥标签、按句切分、打印命中的原句。

核心三行：
```python
xml = urllib.request.urlopen(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML").read()
txt = re.sub(r"<(ref-list|back|table-wrap|fig)[^>]*>.*?</\1>", " ", xml, flags=re.S)
sentences = re.split(r"(?<=[.;])\s+(?=[A-Z(])", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt)))
```
句子切分要点：`(?<=[.;])` 后接 `(?=[A-Z(])` —— 既按句号切，又不会在 `0.05`、`et al.` 之类小数/缩写处断开太少（宁可粗一点，人工复核成本低于漏句）。

**用法判据**：查「某个数值参数有没有文献出处」时，**必须抓到写该参数的那句话本身**；只看到摘要/标题不算证据。

---

## 5. 更正记录：0.25 曾被我误标为「猴脑 RNA DEG 阈值」

- 原文：NHPABC 猴脑图谱（*Cell* 2026, PMID 42612631, DOI 10.1016/j.cell.2026.07.045），官方代码仓库 `3DC-STAR-Anthony/NHPABC`。
- 逐段核对后的事实：
  - **`log2FC > 0.25` 出现在 ATAC 的 sDAREs 判据里**（`P < 0.05` 且 `log2FC > 0.25`，且用的是**未校正 P**）；
  - 该文 **RNA DEG（pDEG/sDEG）** 段用 MAST v1.12.0 + 蛋白编码基因过滤，**官方脚本 `RUV_MAST_pDEG_MBA.R` 全文没有 `|coef|` 过滤**，只有：
    ```r
    fulldf$fdr = p.adjust(fulldf$p, 'fdr')
    fulldf = fulldf[!is.na(fulldf$coef),]
    ```
  - 该文 methods 有一处**确实值得抄**："sample was modeled as a random effect" ⇒ 支持加 `(1|individual)` 供体随机效应。
- **教训**：参数溯源要逐段核原文并确认**模态（RNA/ATAC/Bulk）与段落归属**；同一篇论文里 ATAC 与 RNA 的阈值常常不同。

---

## 6. 本会话实测计数（口径示例）

`fdr < 0.05` 再叠效应量阈值；**分母 = 该对比组全部检验行（10 亚群合并）**。

| 对比组 | 检验行 | FDR<0.05 | + \|coef\|>0.20 | + \|coef\|>0.25 |
|---|---:|---:|---:|---:|
| 衰老 Y_Pre vs O_Pre | 70,113 | 59,681 (85.1%) | 34,289 | **23,178** |
| 老年运动 O_Pre vs O_Post | 64,476 | 51,241 (79.5%) | 6,056 | **1,846** |
| 糖尿病 O_Pre vs OD_Pre | 63,516 | 36,473 (57.4%) | 678 | **311** |
| 糖病运动 OD_Pre vs OD_Post | 66,806 | 23,640 (35.4%) | 557 | **246** |
| 年轻运动 Y_Pre vs Y_Post | 76,060 | 24,624 (32.4%) | 287 | **115** |

关键诊断：**四组运动对比的 `|coef|` 中位数只有 0.029–0.107** ⇒ 0.20/0.25 远在分布尾部，0.20→0.25 之差在运动组意味着再砍 55–70% 基因。
正对照（21 个公认骨骼肌衰老/运动 DEG）：θ=0.25 下衰老组仅保留 **33.2%**（θ=0.20 为 47.7%）⇒ **θ=0.25 砍掉 2/3 已知真信号**。