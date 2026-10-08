# 细胞级方法的推断单位与样本层结构（2026-09-26 更正）

> 起因：本 skill 原标题写着「为什么**不要** cell-level MAST 当主分析 / 禁止 cell-level MAST 当主分析」。
> 用户拿已发表实例反证后，该绝对化表述**已被判定为错误并修正**。
> 本文档是修正后的完整依据与配方。

## 一句话结论

细胞级方法（MAST / NEBULA / 任何 `zlm`）**可以作为主分析**。真正的红线只有一条：
**样本/供体层的变异必须出现在模型里。** 用哪种机制是自由选择。

## ⛔ 禁止的表述（会踩的坑）

不要把"推荐做法"说成"硬规定"。以下说法是**错的**，会被已发表论文直接反证：

- ❌「细胞级 n = 细胞数，不能当主分析」
- ❌「必须用 pseudobulk」
- ❌「必须放 `(1|donor)` 随机效应」

正确表述：「**不加任何样本层校正**的朴素细胞级检验会因伪重复抬高假阳性（Squair 2021 的批评对象正是
这个设定）；只要样本层结构进了模型，细胞级是合法的。」

报结论前先自问：我这是在说"推荐"，还是在说"不允许"？**后者必须有原文或代码支撑。**

## 四条合法途径（同一目的，机制不同）

| 途径 | 检验单位 | 样本层结构怎么进模型 |
|---|---|---|
| 样本级 pseudobulk | 样本 | 单位本身就是样本 |
| 混合模型 | 细胞 | `(1\|sample)` / MAST `method="glmer"` |
| RUV / SVA 因子当协变量 | 细胞 | 从样本级数据估出的因子作固定效应 |
| pseudobulk PC / 残差当协变量 | 细胞 | 同上 |

## 官方先例：猕猴脑衰老图谱怎么用 MAST 的（Cell 2026）

**Zhang X et al. "Multimodal brain cell atlas across the adult macaque lifespan", *Cell* 2026**
PMID **42612631** / DOI `10.1016/j.cell.2026.07.045`（预印本 bioRxiv `10.1101/2025.03.11.641786`）
规模化：2,955,873 核 / 8 个脑区 / 23 只雌性食蟹猴 / 4 个年龄组（6·5·6·6）。

**代码（比正文更权威）**：`github.com/3DC-STAR-Anthony/NHPABC` →
`snRNA/04.Identification_of_differentially_expressed_genes(DEGs)/RUV_MAST_pDEG_MBA.R`、`RUV-seq_sDEGs.R`

**两阶段：细胞级检验 + 样本级校正**

1. `mat %*% make.tform(pathdf$Sample)` → 样本级 pseudobulk
2. edgeR：`DGEList` → `calcNormFactors("TMM")` → `estimateGLMCommonDisp` /
   `estimateGLMTagwiseDisp` → `glmFit` → `residuals(type="deviance")`
3. `RUVr(round(d_e$counts), rownames(d_e$counts), k=10, res1)` → `W_1..W_10`
4. 取**前 5 个**（`uruv = 5`），`merge(..., by="Sample")` 回并到**细胞级** metadata
5. 细胞级 `zlm(nb.form, sca)`，其中
   `nb.form = ~ Age + subtype_new + W_1 + ... + W_5`（**无随机效应项**，`zlm` 走默认 bayesglm），
   `summary(zlm.obj, doLRT="Age")`
6. `p.adjust(p, "fdr")`

**关键参数 / 阈值**

| 项 | 值 |
|---|---|
| 基因过滤 | `pctcut = 0.1` —— 只在 >10% 细胞中表达的基因入检 |
| 个体门槛 | 该亚型 **≥10 个细胞**才保留该个体；阶段比较要求 **≥10 个个体**，否则 `next` 跳过 |
| 判据 | **`Q < 0.05` 且 `|log2FC| > 0.25`**（≈1.19 倍） |
| pDEG | **年龄作连续变量**（LRT on Age） |
| sDEG | 0/1 `stim` 做相邻年龄组两两比较（early / late / very late） |
| chunk | `zlm` 按 500 基因分块并行 |

**组成分析用的是混合模型**：细胞类型比例随年龄变化 →
`n ~ age + modality + (1|sample) + offset(log(total cell))` 的 Poisson GLMM，`sample` 作随机截距，
判据用 LTSR（`LTSR > 0.99`）。

⇒ 即：**组成分析用样本级随机效应，表达分析用细胞级 + RUV 校正**。两者不是对错关系，
是对不同问题选不同机制 —— 该用随机效应的地方它确实用了。

## ⭐ 阈值教训（本类问题最有价值的一条）

`|log2FC| > 0.25` 是**可发表**的判据（Cell 2026）。当效应量本身很小时，
拿习惯性的 1.0 去讨论"这个设计能检出多大变化"，会得出"几乎检不出、方法有问题"的**错误结论**。

- **先查目标领域的已发表判据再定阈值**，不要默认 1.0
- 基因过滤（表达比例 pct、每样本最少细胞数）会改变 BH 家族大小，直接决定能过 FDR 的基因数
  —— 小 logFC 阈值与基因过滤必须**一起调**
- 报告"检出 N 个 DEG"时必须写清判据组合（FDR + logFC + 基因集范围），否则数字没有可比性

## MAST 的事实（别搞混）

- `zlm()` 官方 `method` 参数支持 `"glm"` / `"glmer"` / `"bayesglm"`（**默认 bayesglm**）
- 默认 bayesglm = **纯固定效应**，模型里没有随机效应项 ⇒ 用默认就必须自己加协变量（RUV/PC）
- `glmer` 路径需 `ebayes = FALSE`
- `coef` / `vcov` 是 S4 泛型，不能用 `MAST::` 前缀（裸调用）
- `MAST::CoefficientHypothesis` 未导出 → 改用 `coef()` + `vcov()` 手算 Wald
- `vcov` 维度序为 (系数, 系数, 基因)，写自适应判定，别硬编码

## 怎么核实"某篇论文实际怎么做的"

正文付费 / 预印本被 WAF 拦截时的兜底链（按顺序）：

1. **先查本地历史抽取的方法学文本** —— `results/*/data/*methods*.txt`、`*doc*.txt`
   （之前读过该论文 PDF 时，正文+methods 往往已抽成文本落盘；注意这类文本常**按行截断**，
   要按行号逐行取全文，别满足于 `grep` 的片段）
2. 论文的 **Data and code availability** 段 → GitHub 仓库 → **直接读 `.R` / `.py` 脚本**
   （列目录 `api.github.com/repos/<org>/<repo>/contents/<dir>`；取文件 `raw.githubusercontent.com/...`；
   ⛔ 别只看 README —— 本例 DEG 目录的 README 只有 1 字节）
3. 补充材料仓库（Zenodo / 期刊图库）：`https://zenodo.org/api/records/<id>`
4. OA 副本兜底：`https://api.openalex.org/works/doi:<DOI>` 看 `locations`

⛔ 不要凭"方法学常识"猜一篇论文怎么做的；也不要因为它发在顶刊就假定它做法更严格 —— **去读代码**。
交付时说明证据层级：正文本体没读到就如实说，同时给出「本地 methods 抽取文本 + 作者公开脚本」两条独立来源。