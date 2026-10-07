# 细胞级 vs pseudobulk：单细胞 DEG 方法学landscape（已核实 PMID/DOI）

> 用途：回答「单细胞 DEG 用哪个方法 / 细胞级能不能当主分析 / 方法 A vs B」时的**已验证证据底座**。
> 全部 PMID/DOI 均经 PubMed 检索核实（2026-09）。**引用前仍须按本 skill workflow 复核一次。**

## 0. 一句话结论

**两大阵营不是对错关系。** 2024–2026 的证据（Lee & Han 2024、Gilis 2025、Germain 2025、
Santacatterina 2026）显示：没有单一方法在所有情形最优，**结论高度依赖数据特征**。
选型看的是「样本层变异有没有进模型」，不是「细胞级 vs pseudobulk」的教条对立。

## 1. 红线（唯一一条）

> **样本/供体层的变异必须出现在模型里 —— 用哪种机制是自由选择。**

⛔ **不要**说"必须 pseudobulk"，⛔ **不要**说"细胞级不能作主分析"——两者都是过度绝对化的错误表述。

## 2. 四条合法途径对照表

| 途径 | 检验单位 | 代表工具 / 实例 |
|---|---|---|
| 样本级 pseudobulk | 样本/供体 | muscat、dreamlet、limma-voom `duplicateCorrelation` |
| 混合模型 `(1\|sample)` | 细胞（带随机效应） | NEBULA（负二项 GLMM）；MAST `zlm(method="glmer")` |
| **RUV/SVA 估计因子当固定协变量** | 细胞 | 猴脑图谱 Cell 2026（PMID 42612631）官方代码 |
| pseudobulk 残差/PC 当协变量 | 细胞 | 同上（该文引用 30,32） |

### 猴脑图谱的实证做法（PMID 42612631，DOI 10.1016/j.cell.2026.07.045）

2,955,873 核 / 23 只食蟹猴 / 8 脑区。**表达分析走细胞级，且没有随机效应项**：

```
样本级 pseudobulk（mat %*% make.tform(Sample)）
  → edgeR：TMM + estimateGLMCommonDisp + estimateGLMTagwiseDisp
  → glmFit → residuals(type="deviance")
  → RUVr(k=10) 取前 5 个因子 W_1..W_5
  → 因子回并细胞级 metadata
  → 细胞级 MAST::zlm(~ Age + subtype_new + W_1+...+W_5)   # 无 (1|donor)
  → p.adjust(p,'fdr')；判据 Q<0.05 且 |log2FC|>0.25
```

官方代码：`github.com/3DC-STAR-Anthony/NHPABC` →
`snRNA/04.Identification_of_differentially_expressed_genes(DEGs)/RUV_MAST_pDEG_MBA.R`、`RUV-seq_sDEGs.R`

**⚠️ 它的判据不能直接搬**：`|log2FC|>0.25` 是在**细胞级 coef** 上设的
（细胞级 n 大 → 过 FDR 的 coef 可以很小）。搬到 pseudobulk 表上几乎恒真
（pseudobulk 过 FDR 的基因 logFC 本就 >0.25），实测该阈值在 5 个对比上几乎不起过滤作用。

**成分分析它反而用随机效应**：`n ~ age + modality + (1|sample) + offset(log(total cell))` Poisson GLMM。
→ 即「表达用细胞级+RUV，组成用样本级随机效应」，**各按问题选机制**。

## 3. 细胞级方法的实测（原始文献）

| 方法 | 原文 | 机制 | PMID / DOI |
|---|---|---|---|
| **MAST** | Finak 2015 *Genome Biol* | 两阶段 hurdle：logistic 建模检出力 + 高斯建模表达量 | **26653891** / `10.1186/s13059-015-0844-5` |
| **NEBULA** | He 2021 *Commun Biol* | 负二项 GLMM，**显式含供体随机效应**，细胞级、百万细胞可跑 | **34040149** / `10.1038/s42003-021-02146-6` |
| FLASH-MM | Xu 2026 *Nat Commun* | 线性混合模型，快且可扩展 | 41644528 / `10.1038/s41467-026-69063-2` |
| cytoKernel | Ghosh 2025 *Bioinformatics* | 核嵌入非参数法，稳健 | 40658464 / `10.1093/bioinformatics/btaf399` |

> **MAST 不是"不能用"** —— 它是细胞级 hurdle 框架的原始出处。Squair 2021 批评的是
> 「**不带随机效应**的朴素细胞级检验」这个设定，不是 MAST 本身。
> MAST `zlm` 的 `method` 参数官方 Rd 原文：`character vector, either 'glm', 'glmer' or 'bayesglm'`
> → **支持 `glmer` 随机效应**。

## 4. pseudobulk 分支

| 方法 | 原文 | 关键点 |
|---|---|---|
| muscat | Crowell 2020 *Nat Commun* | **33257685** | 多样本多条件标准框架；明确区分 DS（亚群内状态变化）与 DA（组成变化） |
| dreamlet | Hoffman 2023 | **37205331** | 逐亚群 `dream`/`variancePartition`，支持 `(1\|individual)` |
| limma-voom | Ritchie 2015 *NAR* | **25605792** | `duplicateCorrelation` 专治重复测量/配对设计 |
| edgeR v4 | Chen 2025 *NAR* | **39844453** | 2025 更新版 |
| DESeq2 | Love 2014 *Genome Biol* | **25516281** | n 小时吃紧（每加固定效应损 df） |
| propeller | Phipson 2022 *Bioinformatics* | **36005887** | 专测**细胞比例**差异，logit 变换 + 供体级建模 |
| camera | Wu & Smyth 2012 *NAR* | **22638577** | 竞争性基因集检验，**校正基因间相关**（GSVA/平均分做不到） |

## 5. 方法学基准（决定"选哪个"的实证依据 —— 争议核心）

| 文献 | 年 | 结论要点 | PMID |
|---|---|---|---|
| Squair *Nat Commun* | 2021 | 多供体 scRNA 中**细胞级朴素检验 FDR 膨胀**（被引 900+） | **34584091** |
| Junttila *Brief Bioinform* | 2022 | 多受试者条件下方法基准比较 | 35880426 |
| Lee & Han *Bioinformatics* | 2024 | **pseudobulk 用对 offset ≡ GLMM 统计性质** | 39115884 |
| Gilis *BMC Genomics* | 2025 | 多样本 DEG 完整工作流基准；**"没有单一方法在所有情形最优"** | 41053561 |
| Germain/Robinson *bioRxiv* | 2025 | 用 bulk 假设加权提升 scRNA 功效 | `10.1101/2025.04.15.648932` |
| Hafner *Brief Bioinform* | 2025 | 嵌套设定下的条件间比较 | 40794957 |
| Prieto León *NAR Genom* | 2025 | pseudobulk 中去除 unwanted variation | 41368194 |
| Santacatterina *Nat Commun* | 2026 | 多患者百万细胞可扩展新法 | 42321172 |
| Dos Santos *PLoS Comput Biol* | 2026 | **尺度建模决定 FDR** | 42709908 |

## 6. 组织/方向应用锚点（人骨骼肌运动 × 衰老 × T2D）

| 文献 | 年 | 为什么有用 | PMID |
|---|---|---|---|
| **Hansen *J Physiol*** | 2025 | **单核 RNA-seq + 训练干预 + 2型糖尿病**；"T2D 个体肌核转录响应被削弱" | 40413649 |
| Lixandrao *J Appl Physiol* | 2025 | 老年男女抗阻训练高/低响应者，within-subject 设计 | 40839394 |
| Yang *Genes* | 2026 | 老年骨骼肌不同运动模式的转录特征 | 42510843 |
| Koopmans *Adv Sci* | 2026 | 年龄依赖的肌核多组学对肥大刺激的响应 | 41704039 |
| Dilbaz *bioRxiv* | 2025 | 肌纤维类型特异的训练适应（小鼠） | `10.1101/2025.11.04.686534` |

## 7. 选型后的必做验证（否则结果不可用）

细胞级新方法跑出"显著基因暴多"时，**先假定假阳性膨胀**，按六问自证
（p 分布 / FDR 口径 / **SE 对比** / **效应量脱钩** / 方向指纹 / 阴性对照）——
完整协议见 `analysis-output-validity-gates/references/statistical-inflation-diagnostics.md`。

该文件含实测参照值：细胞级 glmer+RUV 在 24 供体数据上报出 **99.7% 显著**、
p 中位 2.4e-288、**SE 比 pseudobulk 小 26.4 倍**、up:down=46:1、阴性对照被翻成 36,473 显著
→ 判为膨胀。**"方法跑通了" ≠ "结果在统计上成立"。**