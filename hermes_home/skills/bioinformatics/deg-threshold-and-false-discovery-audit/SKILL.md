---
name: deg-threshold-and-false-discovery-audit
description: "DEG 效应量阈值的溯源与假发现审计：任何 |logFC|/|coef| 阈值取多少、要不要筛、为什么显著基因数异常多时使用。含 Seurat FindMarkers 默认值的版本差异、MAST 官方无阈值参数的源码级实证、pseudobulk vs 细胞级方法的权威文献结论、正对照校准法。"
when_to_use: "用户问「阈值取 0.2 还是 0.25」「做 DEG 要不要筛阈值」「为什么我的显著基因这么多」「新方法比老方法多几十倍基因，是不是更好」「这个阈值有文献出处吗」；或写 DEG methods 需要给阈值找依据时。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [deg, threshold, logFC, MAST, Seurat, pseudobulk, false-discovery, provenance]
    difficulty: intermediate
    language: R+Python
    category: bioinformatics
---

# DEG 阈值与假发现审计

> 配套详证（源码 formals 原文、文献原句、PMID/DOI、Europe PMC 全文抽取配方）见
> `references/parameter-provenance-and-mast-thresholds.md`。

## 触发场景

- 「阈值取 0.2 还是 0.25？」
- 「别人做 DEG 的时候要筛选阈值吗？他们怎么做？」
- 「为什么我的显著基因有 5–6 万个？」「新方法比老方法多几十倍，是不是更好？」
- 写 DEG 的 methods 段，需要给阈值找依据。
- 任何 `fdr<0.05` 命中率异常高 / 上下调方向比失衡的情况。

---

## 🔴 铁律 1：阈值必须能追到具体出处，否则明说「无出处」

写 methods 或汇报时，`|logFC|` 阈值只能有三种写法：

| 写法 | 何时可用 | 例子 |
|---|---|---|
| ✅ 上游工具默认值 | **首选**，最可追溯 | 「沿用 Seurat v4 `FindMarkers` 默认 `logfc.threshold = 0.25`」 |
| ✅ 明标自定的最小生物学意义效应 | 无先例时 | 「自定最小效应标准 \|log2FC\| > 0.25（≈1.19 倍变化），非引用文献值」 |
| ⛔ 「参考某某文献」 | **禁止** —— 除非真的逐字查到那篇写了这个数 | — |

**实测教训**：曾把 `0.25` 挂到某篇猴脑图谱论文名下，逐段核对全文后确认**那是该文 ATAC sDARE 的判据（`P<0.05` 且 `log2FC>0.25`）**，而该文 RNA DEG 段用的是 MAST + 样本随机效应、**代码里没有任何效应量阈值** —— 属张冠李戴，审稿人一查即破。**参数溯源必须逐段核原文，不能凭印象或摘要。** 完整更正记录见 `references/parameter-provenance-and-mast-thresholds.md`。

---

## 🔴 铁律 2：Seurat `FindMarkers` 默认值随版本变 —— 必须显式写死

| Seurat 版本 | 默认 `logfc.threshold` | 默认 `min.pct` | 证据 |
|---|---|---|---|
| v3 / v4 | **0.25** | 0.1 | 论文 methods 实证（`Seurat (v4) … logfc.threshold = 0.25`） |
| v5 | **0.1** | 0.01 | 本机实测 5.5.0 `FindMarkers.default` 的 formals |

- ⚠️ 脚本里不显式写 → **v4 得 0.25、v5 得 0.1，同一份数据换版本结论就变**（隐蔽的可复现性坑）。
- ⚠️ 「用 MAST 的论文」绝大多数不是直接调 MAST，而是 `FindMarkers(test.use="MAST")` —— 阈值实际来自 **Seurat 默认值**，不是 MAST。
- 单细胞领域流传的 `0.25` 的真实血统 = **Seurat v3/v4 出厂默认值**，这是它站得住的正确理由。

## 🔴 铁律 3：MAST 官方对效应量阈值完全沉默（别去它身上找）

| 检查项 | 实测（MAST 1.32.0） | 含义 |
|---|---|---|
| `MAST::zlm()` formals | 无任何阈值参数 | 模型层不筛 |
| `MAST::filterLowExpressedGenes(threshold=0.1)` | 0.1 | **基因表达频率**过滤，**不是效应量** |
| `MAST::mast_filter()` | `sigmaContinuous=7, sigmaProportion=7, nOutlier=2, K=1.48` | **细胞级离群**过滤，与 DEG 阈值无关 |
| MAST 原文 Finak 2015 [PMID 26653891](https://pubmed.ncbi.nlm.nih.gov/26653891/) | 全文 43 处提 MAST/hurdle，仅 4 处与「阈值」同句且全在**比 FDR 性能** | **从未推荐过效应量阈值** |

## 🔴 铁律 4：论文写法是「事实惯例」不是「方法学共识」

Europe PMC 全文检索（`logfc.threshold` + `FindMarkers`）命中 1263 篇，抽样规律：

- `0` / `0.1` / `0.25` **三档并存**；
- **同一篇论文里经常两个并用**：marker 鉴定用 `0.25`（要漂亮），条件间 DEG 用 `0`（原文 "allowing all genes to be evaluated"，要全）；
- 也有 `0.1`（跟随 Seurat v5 默认）再叠 `p_val < 0.001` 的双阈值写法；
- **没有任何一篇写「参考某文献取 0.25」** —— 都是直接写参数值。

⇒ 汇报时如实说「这是事实惯例」，不要包装成「方法学标准」。

---

## 🔬 假发现审计流程（显著基因数异常多时走这套）

**症状判据（先量化，别先调阈值）**：

| 指标 | 警戒线 | 含义 |
|---|---|---|
| `fdr<0.05` 占全部检验行比例 | **> 50%** | 显著性由分母（SE）决定，不是由信号决定 |
| 上下调方向比 | **> 10 : 1** | 极端不对称本身是膨胀指纹，正常生物学不会这样 |
| 边界带（如 `0.20<\|coef\|≤0.25`）的 `fdr` 中位数 | 仍在 1e-16 ~ 1e-45 量级 | ⇒ **p 值区分不了阈值带与保留组**，卡在哪纯属人为划线 |
| θ 等价 z 值 | `θ / se中位` 达 **10–21** | 常规 p<0.05 只要 1.96 倍 SE ⇒ 阈值比统计门槛严 5–10 倍 |

**根因优先级（按顺序排查）**：

1. **没有建模 biological replicate** ← **最常见、最致命**
   细胞级测试（MAST hurdle / Wilcoxon / 各种单细胞专用方法）把每个细胞当独立观测 ⇒ SE 被严重低估、假阳性膨胀。
   **权威依据（该引这三篇，不是引阈值）**：
   - Squair et al. 2021 *Nat Commun* [PMID 34584091](https://pubmed.ncbi.nlm.nih.gov/34584091/) · DOI 10.1038/s41467-021-25960-2 —— 14 种方法对比，**pseudobulk 显著优于全部细胞级方法（含 MAST）**，细胞级方法偏向高表达基因；**把聚合步骤关掉、让 pseudobulk 方法跑单细胞 → 优势立即消失**（这就是机制证明）。
   - Crowell et al. 2020 *Nat Commun*（muscat）[PMID 33257685](https://pubmed.ncbi.nlm.nih.gov/33257685/) —— 原文直写 **"Since relying on thresholds alone is prone to bias"**。
   - Murphy & Skene 2022 *Nat Commun* [PMID 36550119](https://pubmed.ncbi.nlm.nih.gov/36550119/) —— pseudobulk 优于混合模型与伪重复做法。
   **处置**：加供体随机效应（`(1|individual)`）或改 pseudobulk；不是在阈值上加码。
2. **批次/混杂未校正** → 检查 design formula 是否含 batch。
3. **分组不平衡 >3:1** → 报告限制或配对设计。
4. 以上都排除后，才谈阈值。

**正对照校准法（决定阈值该切在哪）**：
取领域公认的真信号基因集（如骨骼肌衰老/运动：CDKN1A、GADD45G、FBXO32、MYOG、NR4A3、MYBPH、HSPB1、PPARGC1A、ULK1、TFEB、FOXO3 等），测每个候选 θ 下**已知真信号的召回率**。
实测教训：`θ=0.25` 在衰老组砍掉 **2/3 已知真信号** ⇒ 阈值定得越高不等于越严谨，可能是在砍真信号。
**推荐交付**：θ 敏感性曲线（x = 剩余基因数，y = 已知真信号召回率）比直接拍一个数可信得多。

---

## 📐 换算锚点（被问到就直给）

| log2FC | 倍数变化 | 备注 |
|---|---|---|
| 0.263 | **1.2×** | 「初步有变化」的换算锚点 |
| 0.25 | **1.19×** | ≈ Seurat v3/v4 默认 |
| 0.5 | 1.41× | 本项目 KB `deg.yaml` 记录的 pseudobulk 约定 |
| 1.0 | 2× | 常规 bulk 强效应门槛 |

## 产出规范

1. **同时给未过滤与过滤后两套计数**（reviewer 必问口径）。
2. 阈值表注明**计算口径**：过滤分母是「全部检验行」还是「FDR<0.05 集合」；是「基因 × 亚群」行数还是「去重基因数」——两者差异可达数倍。
3. 报告里写清：**阈值只减少假阳性、不消除假阳性**；若根因是 SE 低估，调阈值只是掩盖。
4. 判上下调**用 `coef` 符号派生新列**，不要用表里现成的常量说明列（那种列每张表只有一个值，逐行用会全错）。

## Pitfalls

| 坑 | 规避 |
|---|---|
| 把某论文的 ATAC 阈值当 RNA DEG 阈值引用 | 逐段核原文模态（RNA/ATAC/Bulk）与段落位置 |
| 以为「用 MAST 的论文」的阈值来自 MAST | 它们走 Seurat `FindMarkers`，阈值来自 **Seurat 默认值** |
| 脚本不写 `logfc.threshold` | 显式写死并注明版本来源 |
| 只报过滤后计数 | 必须给两套 |
| `direction` 类常量列用来判逐行上下调 | 用 `coef` 符号派生 `regulation` 列 |
| `fdr` 列出现 0 | 是 float64 下溢（<1e-308），不是缺失；根源常是 SE 低估 |

## 参考

- `references/parameter-provenance-and-mast-thresholds.md` —— 本 skill 的全部实证原始记录：Seurat/MAST 源码 formals、文献原句、PMID/DOI、Europe PMC `fullTextXML` 抽取 Methods 原句的可复用配方。
- `scripts/extract_methods_sentences.py` —— **参数溯源探针**：给 PMCID 列表或 Europe PMC 检索式 + 关键词正则，抓开放获取全文并按句打印命中原句。查「某个阈值/参数有没有文献出处」时直接跑它，一次拿全证据（不用手搓正则循环，也避开「批量同构调用触发循环检测」）。
- 关联 skill：`deg-analysis`（DEG 分析主流程）、`deg-mixed-design`（混合设计：组间独立 + 组内配对）、`platform-execution-pitfalls`（执行层坑）。