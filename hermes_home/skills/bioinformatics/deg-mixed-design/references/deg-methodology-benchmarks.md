# DEG 方法学基准文献与选型依据（实测检索 + 核实 PMID）

> 2026-09-26 检自 PubMed / Europe PMC / Semantic Scholar，全部带可核 PMID。
> 用途：回答「哪个 DEG 方法更适合我的设计」「细胞级到底能不能用」这类选型问题时，
> **直接引本页，不要凭记忆下绝对化判断**（曾因断言「细胞级不能当主分析」被用户以
> Cell 2026 反例驳回）。

## 一句话结论

**没有单一方法在所有情形最优，结论高度依赖数据特征**（Gilis 2025 原文结论）。
选型不是「细胞级 vs pseudobulk」的对错题，而是**样本层变异有没有进模型**。

## A. 细胞级方法

| 方法 | 原文 | 机制要点 | PMID / DOI |
|---|---|---|---|
| **MAST** | Finak 2015 *Genome Biol* | 两阶段 hurdle：logistic 建模检出力 + 高斯建模表达量；`zlm` 的 `method` 支持 `glm`/`glmer`/`bayesglm`（默认 bayesglm = 纯固定效应） | **26653891** / `10.1186/s13059-015-0844-5` |
| **NEBULA** | He 2021 *Commun Biol* | 负二项 GLMM，**显式放供体随机效应**，细胞级、百万细胞可跑 | **34040149** / `10.1038/s42003-021-02146-6` |
| FLASH-MM | Xu 2026 *Nat Commun* | 线性混合模型，快且可扩展 | 41644528 |
| cytoKernel | Ghosh 2025 *Bioinformatics* | 核嵌入非参数法 | 40658464 |

> ⚠️ **Squair 2021 批评的是「不带任何样本层校正的朴素细胞级检验」这个设定，不是 MAST 本身。**
> 别把它读成「细胞级方法不能用」。

## B. pseudobulk 阵营

| 方法 | 原文 | 对本类设计的关键点 | PMID |
|---|---|---|---|
| muscat | Crowell 2020 *Nat Commun* | 多样本多条件标准框架；**明确区分 DS（亚群内状态变化）与 DA（组成变化）** | 33257685 |
| dreamlet / dream | Hoffman 2023 | `variancePartition` 家族，lme4 内核，支持小样本 + 随机效应 | 37205331 |
| limma-voom | Ritchie 2015 *NAR* | `duplicateCorrelation` 专治**重复测量** | 25605792 |
| edgeR v4 | Chen 2025 *NAR* | 2025 更新版 | 39844453 |
| DESeq2 | Love 2014 *Genome Biol* | n 小时吃紧（每加固定效应损 df） | 25516281 |

## C. 决定「选哪个」的实证基准（争议核心）

| 文献 | 年份 | 结论要点 | PMID / DOI |
|---|---|---|---|
| Squair *Nat Commun* | 2021 | 多供体数据下细胞级朴素检验 FDR 膨胀（被引 900+） | **34584091** |
| Junttila *Brief Bioinform* | 2022 | 多受试者条件下方法的基准比较 | 35880426 |
| **Lee & Han *Bioinformatics*** | 2024 | **pseudobulk 用对 offset 后与 GLMM 统计性质相同** | 39115884 |
| Gilis *BMC Genomics* | 2025 | 多样本 DEG 完整工作流基准；「没有单一方法在所有情形最优」 | 41053561 |
| Germain/Robinson *bioRxiv* | 2025 | 用 bulk 假设加权提升 scRNA 功效 | `10.1101/2025.04.15.648932` |
| Hafner *Brief Bioinform* | 2025 | 嵌套设定下的条件间比较 | 40794957 |
| Prieto León *NAR Genom* | 2025 | pseudobulk 中去除 unwanted variation | 41368194 |
| Dos Santos *PLoS Comput Biol* | 2026 | 尺度建模决定 FDR | 42709908 |

## D. 组成层（常被漏掉、必须单独做）

- **propeller** — Phipson 2022 *Bioinformatics*（PMID **36005887**）：专测细胞比例差异，
  logit 变换 + 供体级建模。
- 与 muscat 的 **DA**（组成变化）呼应：按亚群做 pseudobulk DEG 对**亚群内部**表达变化敏感，
  对**亚群之间比例变化结构性失明** —— 组成变化必须单独检验。

## E. 本类项目的应用先例（骨骼肌 + 运动 + 糖尿病 / 衰老）

| 文献 | 年份 | 为什么有用 |
|---|---|---|
| Hansen *J Physiol*（PMID **40413649**） | 2025 | **单核 RNA-seq + 训练干预 + 2 型糖尿病**；结论「T2D 个体肌核转录响应被削弱」—— 与「老年糖尿病组运动」设计镜像对应 |
| Lixandrao *J Appl Physiol*（PMID 40839394） | 2025 | 老年男女抗阻训练高/低响应者，within-subject 设计 |
| Koopmans *Adv Sci*（PMID 41704039） | 2026 | 年龄依赖的肌核多组学对肥大刺激的响应 |
| Zhang X *Cell*（PMID **42612631**） | 2026 | 猴脑衰老图谱，**细胞级 MAST + RUV 因子**做主 DEG 的官方先例（源码 `github.com/3DC-STAR-Anthony/NHPABC`） |
| Dilbaz *bioRxiv* | 2025 | 肌纤维类型特异的训练适应（小鼠），`10.1101/2025.11.04.686534` |

## 选型速查（判据 → 方法）

| 你的情况 | 建议 |
|---|---|
| 每组 ≥5 样本、要最稳的主分析 | pseudobulk + dream/muscat（或 limma-voom + duplicateCorrelation） |
| 样本数少（n=7–10/组）但细胞多 | 细胞级 + 供体随机效应（NEBULA / MAST glmer）——**合法**，能合规多借一点信息 |
| 已有细胞级结果、想加样本层校正而不改检验单位 | RUV/SVA 因子当协变量（Cell 2026 先例） |
| 关心的是「哪些细胞变了」而非「谁的表达变了」 | **组成层**（propeller）——DEG 结构性失明 |
| 单基因变化小、怀疑是协调变化 | **程序/通路层**（camera 竞争性基因集检验，PMID 22638577）——不要求单基因过 1e-6 |

> 功效上限提醒：**细胞级不突破「供体数决定精度上限」这条线**。它提升的是「每个供体均值的估计精度」，
> 不是「独立观测数」。宣称细胞级「大幅提升功效」是错的；它提升的是**灵敏度**，代价是 p 偏乐观。