# 参考文献与答辩话术（跨物种 CRE 保守性 · 2026-09-01 沉淀）

> 用户要求（2026-09-01）："需要沉淀 skill 的参考文献/答辩话术，方便以后直接引用"。
> 场景：写论文/专利背景技术、导师/评审/审查员追问方法学依据时直接引用本节。
> 所有 PMID 均已在线核实（search_papers 实证，非记忆）。

---

## 一、核心参考文献表（按引用场景分）

| # | 文献 | PMID | 引用场景 / 用途 |
|---|------|------|----------------|
| 1 | **Villar D, et al. *Cell* 2015. "Enhancer evolution across 20 mammalian species."** doi:10.1016/j.cell.2015.01.006 | **25635462**（687 引） | 🔴 **最直接的"教科书级同行先例"**：把 20 种哺乳动物增强子（H3K27ac）都映射到人类参考基因组，比较保守性与重编程速率。答辩"跨物种×人参考坐标系"时首引此篇——我们做法 = 同源锚定版 Villar 框架 |
| 2 | **Siepel A, et al. *Genome Res* 2005. "Evolutionarily conserved elements in vertebrate, insect, worm, and yeast genomes."** doi:10.1101/gr.3715005 | **16024819**（3429 引） | **phastCons 原始方法学**。答辩"conserved_pc / phastCons 元件判定怎么算的"时引用：多物种比对 → 系统发育隐马尔可夫模型（phylo-HMM）→ 保守元件 posterior 概率 |
| 3 | **Pollard KS, et al. *Genome Res* 2010. "Detection of nonneutral substitution rates on mammalian phylogenies."** doi:10.1101/gr.097857.109 | **19858363**（2079 引） | **phyloP 原始方法学**。答辩"phyloP 分数怎么算 / 正负分含义"时引用：以中性进化模型为 Null，判定非中性替代速率（保守=正分、加速=负分） |
| 4 | **Phan et al. *Nat Genet* 2025. "Conservation of regulatory elements with highly diverged sequences."**（IPP 算法 / TFBS shuffling / IC 元件） | **40425826**（已下载全文 29 页核实） | ⚠️ **审查员标准现有技术**（B 类 CRE 的最近邻）：答辩"B 类 = 序列保守版 IC，原理已知"时承认 + 主动引用 + 转增量（见 skill B 类章节战略调整） |
| 5 | **Zemke NR, et al. *Nature* 2023.** "Conserved and divergent gene regulatory programs of the mammalian neocortex." doi:10.1038/s41586-023-06819-6 | **38092918**（PMC10719095，CCBY 开放全文 141K 字已核实） | 🔴 **L2 活性保守比较的最直接方法学先例**：4 物种（人/猴/绒猴/小鼠）neocortex snATAC；定义 **epi-conservation level 0/1/2/3**（L0=有直系同源序列 → L1=跨物种有 peak → L2=至少一种相同细胞类型可及 → L3=全部细胞类型可及模式显著匹配）；用 **GLS 回归 T-statistic 定义 conservation/divergence index**。⚠️ 关键差异：**它按 cell type 合并 pseudobulk（非个体聚合）、不用 ArchR getGroupSE、无年龄维度**（详见 Q6/Q7） |
| 5b | **GSE278576 人海马 aging Multiome（40 donors）** Zemke 组 bioRxiv 2024.10.14.618338 | — | 人侧**数据源**引用（与 #5 Nature 2023 是同一组的不同数据集：Nature 2023 是 4 物种 neocortex，GSE278576 是 人海马 aging；数据卡片另详） |
| 6 | **张潇 NHPABC（拟投 Cell 2026）** | — | 猴侧数据源引用（NHPABC 63 海马文库，CNP0004459 / Zenodo 20482872） |

---

## 二、答辩话术（直接可讲，按问题分类）

### Q1：为什么猴子不自看自己的保守，而是要映射到人的坐标？

**一句话（给导师/评审）**：
> "保守性评分需要一把'统一的尺子'。phyloP100way/phastCons100way 轨道是按人类参考基因组 hg38 构建的——它们是 100 个哺乳动物的全基因组多序列比对结果，而食蟹猴（M. fascicularis）本来就包含在这 100 个物种之内。因此将猴 CRE 经同源基因锚定映射到 hg38 坐标后直接查询 hg38 轨道，所得分数天然已编码'猴 vs 人 vs 其他 98 个哺乳动物'的保守程度；并不存在、也不需要单独的'猴版 phyloP 轨道'（该方法学依据：Siepel 2005；Pollard 2010）。"

**大白话（给非生信老师）**：
> "就像用同一台词典给全班同学打分——词典是按人编的，但猴子也是这本词典的'参考生'之一（100 个物种比对里有它）。把猴子的开关位置翻译到人这边，就能用同一台尺子量它保守不保守。如果猴子自己造一把尺子量自己，两把尺子的刻度不一样，人和猴的数字就比不了。"

**技术补充（方法学注明，防审查员挑刺）**：
- 我们不用 UCSC liftover chain 的直接原因：猴基因组是 **T2T-MFA8v1.1**（新组装），UCSC 只提供旧组装 MacFas5 的 chain——版本错配会把 peak 系统性放到错误坐标（结构差异 indel/SV），正确性不可接受（2026-08-30 用户拍板：gene ortholog 映射 = 主通道）。
- 基因锚定的语义 = **"orthologous locus conservation"（同源基因座保守性）**，不是全基因组保守性；只覆盖近基因 CRE（TSS±2kb 窗口），写论文/专利时方法学必须注明此边界。

### Q2：映射到人类参考坐标系，这方法有人做过吗？有文献背书吗？

**答辩主句**：
> "有，而且是领域标准范式。最直接的同行先例是 **Villar et al. (Cell, 2015, PMID 25635462)**：该研究把 20 个哺乳动物物种的增强子全部映射到人类参考基因组上，系统比较增强子保守性与进化速率——这是跨物种调控元件保守性研究广为接受的'人类参考坐标系'范式。我们的实现与其同源，仅在坐标映射通道上做了适配：因猴侧使用最新的 T2T-MFA8 组装（无现成 chain），采用基因锚定的 ortholog 同源映射替代 UCSC liftover（Villar 框架不变，仅替代链技术路径）。保守性打分工具本身亦有完整方法学文献背书：phastCons（Siepel 2005, PMID 16024819）与 phyloP（Pollard 2010, PMID 19858363）均为 UCSC 官方轨道、被数万篇论文引用。"

**补充一句（防止"你这只是把别人的方法拿来"）**：
> "跨物种映射到人类参考坐标系是**公共领域工具**（Villar 2015 已确立），我们的专利创新不在'映射'本身，而在映射之后的 **species×age 可代替性评估系统**：pseudobulk 个体聚合 + 混合效应模型 + SDI/IRS 评分 + A/B/C/D 分类路由 + 产业转化决策——这部分在现有技术中无对应（Phan 2025 无年龄维度；Villar 2015 无 ATAC 可及性/无年龄动态）。"

### Q3：为什么猴子侧看起来整体更保守？（数字：人 pct 中位 34.2% vs 猴 56.5%）

**答辩主句**：
> "两侧峰集的构成不同，直接比较整体分布存在系统性偏差：猴侧仅包含经基因锚定成功映射的 CRE（约占全部猴峰的 63.8%，均位于基因 TSS±2kb 邻近区域），而近基因调控元件在进化上天然更保守；人侧是全基因组 501bp 原始峰（含大量基因间/远端区域）。因此'猴侧整体保守'主要是采样偏差，不是真实的物种差异——跨物种比较必须限定在可比子集（如仅比较两侧近基因 CRE），或在 L2 按同源区域对齐后再比。"

**专利/论文写法**：方法学注明"orthologous locus conservation, gene-proximal CRE subset（63.8% of monkey peaks）"；结论只谈可比子集，禁止把全量分布差异当成生物学发现。

### Q4：L1 全量 FDR 校正后 0 个显著保守 peak？（人侧 q 全 ≥0.63，猴侧 ≥0.75）

**答辩主句（三条都真，按听众选）**：
> ① "这是多重检验惩罚的必然结果，不是数据没信号：52.5 万次全峰 BH-FDR 校正下，即使有 7.4% 原始 p<0.05（略高于随机期望 5%），也没有单峰能扛住 52.5 万次检验——任何全基因组范围的逐元素显著性宣告都会遇到同一问题（Villar 2015 同样不做逐增强子 FDR 宣告，而是做分布级/功能级比较）。"
> ② "因此我们把'保守性'作为**排序/筛选层**而非'显著宣告层'：原始 pval 与背景百分位（p100_bg_pct）已输出用于排序，显著性判定移交到 L2 差异可及性层——先在数百~数千个 DA 差异区域内做 FDR，检验规模下降 3 个数量级，显著保守元件即可浮现。"
> ③ "分布层面的秩和检验（人 vs 猴、DA vs 非 DA 区域的 p100_mean/pct 比较）如实呈现'提示但不显著'的趋势，与领域共识一致：CRE 保守性本身是连续谱，单峰显著宣告不是必要条件。"

**给导师的结论句式**：
> "L1 表明：海马 ATAC peaks 整体保守性不高于随机基因组背景（人 7.4% / 猴 4.0% 原始 p<0.05，均贴近 5% 期望），说明'进化保守'不是 ATAC peak 的普遍属性——这恰恰说明必须在 L2 把衰老差异区域筛出来后再评估其保守性（保守 + 衰老差异 = 双条件叠加才是专利要找的靶点），而不是在全部 peaks 上期待显著保守。"

### Q5：你们怎么保证打分窗口合理？（防 BNIP3 稀释错误）

**答辩主句**：
> "评估窗口锚定在 CRE 相对位置（DA tile 在基因内相对位置 frac → hg38 同相对位置 ±5kb，或 TSS±2kb），禁止用基因全长均值——基因全长会被长内含子非保守区域稀释（实测 BNIP3 全长 phyloP -0.126 误判不保守，TSS±1kb = +0.185 保守）。该窗口策略与 Villar 2015 以增强子/启动子自身坐标为中心的做法一致。"

---

### Q6：L2 用 `getGroupSE(proj, groupBy="Individual")` 有文献先例吗？你看过原代码吗？

**先答"看过原代码吗"：看过，两层都实证过。**
1. **ArchR 1.0.3 本地源码**（execute_r 打印完整源码核实）：`getGroupSE` 内部按 `groupBy` 指定的 colData 列把 cells 分组，每组 counts 求和，再按 `divideN`（默认 TRUE，除以每组细胞数）得到均值信号，输出 SummarizedExperiment。**groupBy 接受任意 colData 列名，官方不限定只能是 Sample**。
2. **官方 pkgdown 参考页**（archrproject.com/reference/getGroupSE.html，1.0.3 在线核实）：签名 `getGroupSE(ArchRProj=NULL, useMatrix=NULL, groupBy="Sample", divideN=TRUE, scaleTo=NULL, threads=getArchRThreads(), verbose=TRUE, logFile=createLogFile("getGroupSE"))`；`groupBy` 文档 = "A column name in colData"；官方 Example 用 `getTestProject`。**默认值是 "Sample"，但那是默认，不是限制。**

**再答"有先例吗"——诚实版（重要，禁止吹牛）**：
> 逐字使用 `getGroupSE(groupBy="Individual")` 做跨物种 DA 的公开论文，**我们没有检索到**。最近的同行方法是 Zemke 2023 Nature（#5）：它也做跨物种 ATAC 活性保守比较（epi-conservation L0-L3 + GLS index），但**它不用 ArchR getGroupSE、按 cell type 而非 individual 聚合、且没有年龄维度**。因此答辩措辞必须精确：
> - ✅ 可以说："我们使用的聚合工具是 ArchR 官方函数（官方 API 明确支持任意 colData 分组列，ArchR 1.0.3 源码与 pkgdown 文档已核实）；聚合单位选个体，遵循单细胞差异分析伪重复统计标准（Squair 2022；Heumos 2023；Murphy 2023）。"
> - ⚠️ 不能说："Zemke 也是这么做的"——它不是（cell type 聚合、自定义 GLS）。
> - 💡 专利含金量恰恰在此：**跨物种 × 年龄动态的染色质可及性比较（species×age 交互），现有文献无直接先例**（Zemke 只有跨物种×细胞类型，无年龄）——这是我们的空白点/独权依据。

### Q7：L2 的伪重复问题——为什么聚合单位必须是"个体/样本"，不是"细胞"或"文库"？

**答辩主句**：
> 单细胞测序中，同一生物学个体（或同一文库）内的数万细胞高度相关，把它们当作独立样本做差异检验 = 伪重复，会把 p 值系统性压低、假阳性爆炸。因此差异分析必须先聚合到**独立生物学重复**（个体/样本）水平再检验——这是 scRNA/scATAC 差异分析的统计标准（**Squair et al. 2022 *eLife*"Confronting false discoveries in single-cell differential expression"**；**Heumos et al. 2023 *Nat Rev Genet*"Best practices for single-cell analysis across modalities"**；**Murphy et al. 2023 *eLife*"Avoiding false discoveries…AD dataset"** 是同领域的伪重复教训）。我们的规则：**聚合单位 = 生物学重复**——人侧 40 样本 1:1 个体（"Sample"≈"Individual"）；**猴侧 63 文库 → 21 个体，必须按 Individual 聚合**，否则同一只猴的 2-3 个文库被当成独立样本，统计功效虚高。

**速查**：审查员问"为什么不用 Sample" → 猴侧 Sample = 同一猴多文库 = 伪重复 → 专利共识早已定（pseudobulk 个体聚合防伪重复）。审查员问"细胞级矩阵不是更精确？" → 细胞非独立样本，差异检验必须在个体级（Squair 2022）。

| 对方质疑 | 甩哪篇 | 一句要点 |
|---------|--------|---------|
| "为什么猴不映射先例？" | Villar 2015 Cell (25635462) | 20 物种增强子全映射到人参考，领域标准 |
| "getGroupSE(groupBy=Individual) 有先例吗？" | ArchR 官方 pkgdown + 源码；Zemke 2023 Nature (38092918) | 官方 API 支持任意分组列；Zemke 用 cell type 聚合非个体（诚实边界见 Q6） |
| "为什么按个体聚合不按细胞/文库？" | Squair 2022 eLife (伪重复经典) | 细胞非独立样本，个体才是生物学重复（见 Q7） |
| "Zemke 2023 不是已经做了吗？" | Zemke 2023 Nature (38092918) | 它做跨物种×细胞类型、无年龄；我们做 species×age 交互——空白点 |
| "phyloP 是什么？可靠吗？" | Pollard 2010 GR (19858363) | 非中性替代率检测，UCSC 官方轨道 |
| "phastCons 元件判定依据？" | Siepel 2005 GR (16024819) | 系统发育 HMM 保守元件模型 |
| "猴自己看自己不就行了？" | （无文献，方法学） | 尺子统一性 + 食蟹猴在 100 物种比对内，见 Q1 |
| "为什么不 liftover？" | （无文献，技术事实） | T2T-MFA8 无现成 chain，旧组装 chain 版本错配不可信 |
| "B 类不是抄 IC 元件？" | Phan 2025 NG (40425826) | 承认原理邻近 + 我们的增量 = 检出+评分+分类+年龄维度 |
| "全基因组 FDR 全 0 是不是失败？" | （方法学事实） | 多重检验必然，转分布/缩小检验规模，见 Q4 |

---

## 四、来源说明

- PMID 实证：search_papers 在线核对（Villar 25635462 / Siepel 16024819 / Pollard 19858363 / Phan 40425826）
- Phan 2025 全文 29 页已下载核实（prior-art-2025-plan-evaluation.md 内有完整评估）
- Villar 2015 为 Europe PMC 开放获取（PMC4313353）
- 数据源引用（Zemke 2026 / NHPABC 2026）见 nhpabc-dataset-card.md / gse278576-data-spec.md