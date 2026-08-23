# hdWGCNA 与经典 WGCNA 的局限性与注意事项调研报告

> 面向场景：scRNA-seq 共表达网络分析（骨骼肌快肌纤维亚群 hdWGCNA 拆模块失败案例）
> 日期：2026-08-14 ｜ 方法：PubMed/Europe PMC/Semantic Scholar 检索 + 原文 PDF 全文核验

## 0. 核心结论

WGCNA 是为 bulk 转录组（几十~几百个**独立样本**）设计的加权相关网络方法（PMID: 19114008），直接搬到单细胞数据会同时踩中两个坑：**概念错位**（把细胞当"样本"导致伪重复）与**统计失真**（dropout/零膨胀导致伪共表达）。hdWGCNA（PMID: 37426759）通过 metacell 聚合缓解了稀疏性问题，但**保留了相关性网络框架**，因此在均质、低异质性亚群上依然会失效（本案例 MF 亚群软阈值 R² 最高仅 0.72）。此时 **NMF（非负矩阵分解）是更合适的替代**——它在"分解出可解释的基因程序"这一任务上对异质性要求更低、对零膨胀更稳健。

---

## 1. 经典 WGCNA 用于单细胞数据的主要问题

| 局限 | 后果 | 应对 | 证据 |
|---|---|---|---|
| **dropout 事件/零膨胀**：scRNA-seq 矩阵通常 >90% 为零，技术性 dropout 使基因-基因相关性失真 | 产生 spurious correlations（伪共表达），模块反映"零的模式"而非生物学 | metacell 聚合（hdWGCNA 的做法）、先做可信基因过滤、与 imputation 结果交叉验证 | hdWGCNA 原文："The sparsity and noise inherent in single-cell data can lead to spurious gene-gene correlations"（PMID: 37426759）；MAGIC 指出 dropout 掩盖真实基因互作（PMID: 29961576）；scCoBench 基准证实稀疏性/dropout 损害基因-基因关系推断（bioRxiv 10.1101/2025.05.26.656221） |
| **技术噪声**：文库大小、扩增偏差、测序深度、批次效应 | 模块可能反映技术因素而非生物程序 | 校正批次（hdWGCNA 对模块特征基因 ME 应用 Harmony 校正，见原文 Algorithm 2）、多重复验证 | PMID: 37426759（"Technical noise may arise from dropout events or from various steps in the experimental protocols"） |
| **稀疏性**：高维稀疏矩阵下 Pearson 相关估计不稳定 | 相关矩阵噪声大，软阈值曲线不收敛（如本案例 R² 最高 0.72 不达标） | metacell 聚合（稀疏度可降 >10 倍，原文 Figure 1C）；改用对零膨胀稳健的模型 | PMID: 37426759；PMID: 31604482（MetaCell 聚合思想） |
| **"样本"概念错位**：bulk 中样本=独立个体；单细胞中若把每个细胞当样本，有效自由度=个体数/批次数而非细胞数 | 伪重复（pseudoreplication）→ 假阳性膨胀、模块"显著"但跨个体不可复现 | 每个生物学重复分别构建 metacell（hdWGCNA 默认做法）；模块-性状关联用个体级统计；混合效应模型 | PMID: 33531494（"A practical solution to pseudoreplication bias in single-cell studies"）；PMID: 34584091；WGCNA 官方 FAQ 建议构建网络至少 ~15-30 个独立样本（URL 见参考文献） |
| **共表达 ≠ 因果关系**：模块是描述性聚类，无方向、无因果 | hub 基因常被误读为"调控者"，实为丰度/管家基因 | 网络结论必须经扰动实验/调控推断工具（如 SCENIC）验证 | BEELINE 基准显示基于相关性的方法在调控网络推断中表现差（PMID: 31907445）；合成 GRN 模型显示 TF 与靶基因间甚至不必然共表达（DOI: 10.1371/journal.pone.0247671） |
| **模块稳定性依赖样本量与异质性**：动态树切分对样本组成敏感 | 小样本/低方差下模块不可复现 | 模块保存检验（Zsummary）、bootstrap 稳定性评估（见第 4 节） | PMID: 21283776（module preservation） |

---

## 2. hdWGCNA 自身的局限性

1. **metacell 聚合丢失单细胞分辨率**：metacell 是转录组相似细胞的均值（原文采用 bagging + KNN 构建），聚合本身平滑掉单细胞水平的异质性和稀有细胞状态；且**聚合方式选择影响结果**——原文比较了 Metacell2（PMID: 31604482 同源方法）与 SEACells（PMID: 36973557）三种 metacell 策略，结果存在差异；mcRigor 进一步指出 metacell 划分的统计严谨性问题（PMID: 41022768）；专门的基准研究显示库大小稳定化的 metacell 构建可增强共表达网络分析（PMID: 41231963）。

2. **需要足够细胞数与异质性**：细胞太少或亚群过于均质时拆不出模块。本案例 MF（快肌纤维）为终末分化亚群，转录程序高度协调、共享单一表达主轴，3000 个 HVG 全部落入一个模块，`mergeCloseModules` 直接报错 `'less than two proper modules'`（该报错来自 WGCNA 底层 moduleColor 包的模块数检查，见 URL）。hdWGCNA 原文也承认"correlation structure varies greatly for different subsets (cell types, cell states)"——即网络可构建性依赖亚群自身的结构。

3. **hub 基因与模块定义的主观性**：hub 基因按 kME（eigengene-based connectivity）排名截取，阈值无标准；模块合并依赖 `cutHeight`、`deepSplit`、`minModuleSize` 等参数，参数微调可显著改变模块划分——这些都属于启发式而非统计推断，需要敏感性分析支撑。

4. **计算成本/内存**：需构建基因×基因相关矩阵与 TOM（O(G²) 内存），原文实测 1,000~50,000 细胞子集的 runtime 与内存上界（GB 级）随细胞数近线性/超线性增长（PMID: 37426759, Figure 2）；高变基因多或细胞多时需降采样或分批。

5. **输入基因选择敏感**：只对 HVG 建网，HVG 数量与选择方式（`variable`/`fraction` 等模式）直接决定模块内容；结果对预处理（归一化、scale）同样敏感。

---

## 3. hdWGCNA vs NMF：适用边界

| 维度 | hdWGCNA | NMF（cNMF / CoGAPS / RcppML 等） |
|---|---|---|
| 数学框架 | 基因-基因相关网络 + 软阈值 + TOM + 层级聚类 | 非负矩阵分解 X≈W·H：每个因子=基因程序（W），每个细胞/样本获得程序负荷（H） |
| 输出 | 嵌套模块（网络结构、hub 基因、模块-性状关联） | 离散的基因程序集合 + 负荷分数 |
| 对异质性要求 | 高：需要可分异质性才有"模块轴" | 低：加性分解不依赖负相关分开的模块结构，均质/连续状态也可拆 |
| 对零膨胀/稀疏稳健性 | 中：靠 metacell 缓解 | 较高：非负约束 + 可显式建模误差分布（如 ZINB 类） |
| 代表性文献 | PMID: 37426759 | PMID: 31282856（cNMF）；PMID: 30143323（NMF 综述）；PMID: 37989764（CoGAPS 协议） |

**什么时候优先用 NMF 而不是 hdWGCNA**：
- 软阈值 R² 达不到 0.8、或所有基因落入单一模块（低异质性/均质亚群信号）；
- 目标是**可解释的基因程序**（如衰老程序、代谢程序）而非网络拓扑/hub 结构；
- 细胞数有限、异质性以连续状态（如分化梯度、代谢梯度）为主——WGCNA 的分层聚类适合离散模块，NMF 适合连续程序。

**本案例实证**：MF 亚群 hdWGCNA 失败后改用 RcppML NMF，成功拆出 **6 个生物学可解释的基因程序**，其中衰老相关程序 P3 命中 BMPR1B，直接验证了"低异质性下 NMF 更合适"。注意 NMF 也有自身主观性（程序数 k 的选择，cNMF 用稳定性准则选 k；PMID: 31282856），且 NMF 程序同样≠调控网络，仍需功能富集与实验验证。

---

## 4. 假阳性控制方法

| 方法 | 做法 | 阈值/判据 | 证据 |
|---|---|---|---|
| **置换检验（permutation/randomized test）** | 打乱基因标签重算模块统计量，评估模块显著性；hdWGCNA 跨数据集模块保存检验采用 **100 次置换** | P 值/FDR | PMID: 37426759（ModulePreservation with 100 permutations） |
| **Zsummary（Z-summary preservation）** | 组合密度/连通性等多项统计量的模块保存分数（跨数据集、跨细胞类型） | Z<5 未保存；5≤Z<10 中等；Z≥10 高度保存 | PMID: 21283776（提出者）；PMID: 37426759（采用同阈值，Figure 1H） |
| **模块稳定性评估** | bootstrap/resampling 重复建网，比较模块成员一致性；metacell 参数（K）敏感性扫描 | 成员重叠率（如 Jaccard） | PMID: 21283776；PMID: 41231963（metacell 构建方式影响网络） |
| **生物学验证** | GO/KEGG 富集、与已知标志基因/程序比对、独立数据集复现 | 富集显著性 + 复现性 | PMID: 37426759；scCoBench 用 promoter-reporter 基因对作内部对照（bioRxiv 10.1101/2025.05.26.656221） |

---

## 5. 实战案例：骨骼肌 MF（快肌纤维）亚群

- **现象**：软阈值 R² 最高 0.72（power=1，未达 0.8 标准）；3000 个 HVG 全部落入单一模块；`mergeCloseModules` 报错 `'less than two proper modules'`。
- **解读**：MF 是终末分化、转录程序高度协调的均质亚群——肌球蛋白、代谢、收缩相关基因共享同一表达主轴，相关性结构里没有可分模块的"轴"。WGCNA 的分层聚类前提（存在相对独立的模块化协变结构）在此不成立；软阈值曲线不收敛正是"网络无尺度结构弱"的信号，而非参数调得不够。
- **应对**：改用 NMF（RcppML），拆出 6 个生物学可解释程序（含衰老程序 P3，命中 BMPR1B）。
- **经验沉淀**：① 均质/终末分化亚群、软阈值不达标、单模块崩溃 → 直接转 NMF 类基因程序分解；② 异质性高（多细胞类型混合或疾病/发育状态差异大）→ hdWGCNA 仍为首选并可做模块-性状关联；③ 两种方法互为验证，结论需功能富集 + 外部数据集保存检验兜底。

---

## 6. 待核实项

- 用户提及的 "Hurlock 等对 WGCNA 单细胞应用的批评文献"：以 'Hurlock WGCNA single-cell' 等关键词未检索到，疑为作者名记忆偏差，**待核实**（未纳入正文引用）。
- "共表达网络是描述性而非机制性"的经典批评另有 de la Fuente（Trends Genet, 2010）等综述，本次未逐篇核验 PMID，**待核实**。
- 单细胞网络推断方法学的系统综述（Briefings in Bioinformatics 类）本次检索命中率低，如需可补充深度检索。

---

## 参考文献（已核实）

1. Langfelder P, Horvath S. WGCNA: an R package for weighted correlation network analysis. *BMC Bioinformatics* 2008. PMID: 19114008. DOI: 10.1186/1471-2105-9-559
2. Morabito S, et al. hdWGCNA identifies co-expression networks in high-dimensional transcriptomics data. *Cell Reports Methods* 2023. PMID: 37426759. DOI: 10.1016/j.crmeth.2023.100498. PMC10326379
3. Langfelder P, et al. Is my network module preserved and reproducible? *PLoS Comput Biol* 2011. PMID: 21283776. DOI: 10.1371/journal.pcbi.1001057
4. van Dijk D, et al. Recovering Gene Interactions from Single-Cell Data Using Data Diffusion (MAGIC). *Cell* 2018. PMID: 29961576. DOI: 10.1016/j.cell.2018.05.061
5. Baran Y, et al. MetaCell: analysis of single-cell RNA-seq data using K-nn graph partitions. *Genome Biol* 2019. PMID: 31604482. DOI: 10.1186/s13059-019-1812-2
6. Persad S, et al. SEACells infers transcriptional and epigenomic cellular states from single-cell genomics data. *Nat Biotechnol* 2023. PMID: 36973557. DOI: 10.1038/s41587-023-01716-9
7. Liu P, Li JJ. mcRigor: a statistical method to enhance the rigor of metacell partitioning. *Nat Commun* 2025. PMID: 41022768. DOI: 10.1038/s41467-025-63626-5
8. Zhang T, Zhu H. Library size-stabilized metacells construction enhances co-expression network analysis in single-cell data. *PLoS Comput Biol* 2025. PMID: 41231963. DOI: 10.1371/journal.pcbi.1013697
9. Zimmerman KD, et al. A practical solution to pseudoreplication bias in single-cell studies. *Nat Commun* 2021. PMID: 33531494. DOI: 10.1038/s41467-021-21038-1
10. Squair JW, et al. Confronting false discoveries in single-cell differential expression. *Nat Commun* 2021. PMID: 34584091. DOI: 10.1038/s41467-021-25960-2
11. Pratapa A, et al. Benchmarking algorithms for gene regulatory network inference from single-cell transcriptomic data (BEELINE). *Nat Methods* 2020. PMID: 31907445. DOI: 10.1038/s41592-019-0690-6
12. Yin W, et al. Emergence of co-expression in gene regulatory networks. *PLoS One* 2021. DOI: 10.1371/journal.pone.0247671
13. Kotliar D, et al. Identifying gene expression programs of cell-type identity and cellular activity with single-cell RNA-Seq (cNMF). *eLife* 2019. PMID: 31282856. DOI: 10.7554/eLife.43803
14. Stein-O'Brien GL, et al. Enter the Matrix: Factorization Uncovers Knowledge from Omics. *Trends Genet* 2018. PMID: 30143323. DOI: 10.1016/j.tig.2018.07.003
15. Johnson JAI, et al. Inferring cellular and molecular processes in single-cell data with NMF (CoGAPS). *Nat Protoc* 2023. PMID: 37989764. DOI: 10.1038/s41596-023-00892-x
16. Chau TN, et al. scCoBench: Benchmarking single cell RNA-seq co-expression using promoter-reporter lines. *bioRxiv* 2025. DOI: 10.1101/2025.05.26.656221（预印本）
17. WGCNA 官方 FAQ（样本量建议 ~15-30）：https://edo98811.github.io/WGCNA_official_documentation/faq.html
18. moduleColor 包源码（'less than two proper modules' 报错来源）：https://rdrr.io/cran/moduleColor/src/R/Functions.R
19. hdWGCNA 官方教程：https://smorabit.github.io/hdWGCNA/articles/basic_tutorial.html
