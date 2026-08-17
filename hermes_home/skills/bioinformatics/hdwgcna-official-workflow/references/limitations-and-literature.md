# WGCNA/hdWGCNA 局限性与替代方案（文献核实版, 2026-08-14 调研产出）

> 全部 PMID/DOI 已经 PubMed 关键词检索核实；关键论断逐字核验自 hdWGCNA 原文全文 PDF（PMC10326379）。
> 适用：hdWGCNA/WGCNA 拆模块失败排查、"为什么 WGCNA 不适合我的单细胞数据"类问题、方法选型报告。

## ⚠️ 排查顺序（重要）：先排除基因子集伪影，再谈"数据不适合"

本机骨骼肌 MF 实测（见 SKILL.md「关键教训：基因子集 ≠ 网络平坦」）：
- top3000 HVG 子集 → 假平坦网络（R²=0.72@power1、单一 turquoise 模块）→ 曾误判"均质亚群不适合 WGCNA"
- **改用全部 WGCNA 基因（SetupForWGCNA fraction=0.05 → 10176 基因）→ power=10, R²=0.982, 拆出 11 模块**

结论：**拆模块失败时先换完整基因集（≥5000 基因）重跑，再下"低异质性/均质"结论**。NMF 仍可作互补验证（MF 上拆出 6 程序含衰老程序 P3/BMPR1B），但"R²<0.8 → 直接判数据不适合 WGCNA"是错误的解读路径。

## 1. 经典 WGCNA 用于单细胞的核心问题（含证据）

| 问题 | 后果 | 证据（已核实） |
|---|---|---|
| dropout/零膨胀 | spurious gene-gene correlations（伪共表达） | hdWGCNA 原文："The sparsity and noise inherent in single-cell data can lead to spurious gene-gene correlations"（PMID 37426759）；MAGIC（PMID 29961576）；scCoBench 基准（bioRxiv 10.1101/2025.05.26.656221） |
| 技术噪声/批次 | 模块反映技术因素 | PMID 37426759（"Technical noise may arise from dropout events or from various steps in the experimental protocols"）；hdWGCNA 对 ME 用 Harmony 批次校正（原文 Algorithm 2） |
| 样本概念错位（伪重复） | 把细胞当样本→有效自由度=个体数而非细胞数→假阳性膨胀、模块不可复现 | Zimmerman 2021 Nat Commun（PMID 33531494）；Squair 2021 Nat Commun（PMID 34584091）；WGCNA 官方 FAQ：建网至少 ~15-30 个独立样本（https://edo98811.github.io/WGCNA_official_documentation/faq.html） |
| 共表达≠因果/调控 | hub 基因被误读为调控者 | BEELINE 基准：相关性方法在调控推断中表现差（PMID 31907445）；合成 GRN：TF-靶基因间甚至不必然共表达（Yin 2021 PLoS One, 10.1371/journal.pone.0247671） |

## 2. hdWGCNA 自身局限（原文全文核验）

- **metacell 聚合丢分辨率 + 聚合方式敏感**：metacell=bagging+KNN 相似细胞均值；原文比较了 Metacell2 与 SEACells（PMID 36973557）三种策略结果有差异；mcRigor 指出划分统计严谨性问题（PMID 41022768）；库大小稳定化 metacell 可增强网络分析（PMID 41231963, PLoS Comput Biol 10.1371/journal.pcbi.1013697）。
- **需要足够细胞数与异质性**：细胞太少/亚群太均质时软阈值不收敛、模块合并报错 `mergeCloseModules: less than two proper modules`（报错源头=WGCNA 底层 moduleColor 包源码, https://rdrr.io/cran/moduleColor/src/R/Functions.R）——但先按上面排查顺序排除基因子集伪影。
- **hub/模块定义主观**：kME 截断阈值、`cutHeight`/`deepSplit`/`minModuleSize` 启发式参数，微调即变模块划分→必须做参数敏感性分析。
- **计算成本**：基因×基因相关矩阵 + TOM = O(G²) 内存；原文实测 1K~50K 细胞子集 runtime/内存上界（GB 级, Figure 2）。

## 3. hdWGCNA vs NMF 适用边界（判据）

**优先 NMF（cNMF/CoGAPS/RcppML）当且仅当**（先排除基因子集伪影后仍成立）：
1. 完整基因集下软阈值 R² 仍 < 0.8，或所有基因落入单一模块（低异质性/均质亚群信号）；
2. 目标是可解释基因程序（衰老/代谢程序）而非网络拓扑/hub 结构；
3. 细胞数有限、异质性以连续状态（分化/代谢梯度）为主——WGCNA 分层聚类要离散模块轴，NMF 加性分解不依赖负相关分开的模块结构。

**NMF 证据**：cNMF（PMID 31282856, k 用稳定性准则选）、Enter the Matrix 综述（PMID 30143323）、CoGAPS 协议（PMID 37989764）。NMF 程序同样≠调控网络，仍需富集+实验验证。

## 4. 假阳性控制（原文核验）

| 方法 | 做法/阈值 | 证据 |
|---|---|---|
| 置换检验 | hdWGCNA 跨数据集模块保存检验用 **100 permutations** | PMID 37426759（ModulePreservation） |
| Zsummary | Z<5 未保存；5≤Z<10 中等；≥10 高度保存 | 提出者 PMID 21283776；hdWGCNA Figure 1H 同阈值 |
| 稳定性 | bootstrap 重建网比模块成员一致性（Jaccard）；metacell K 参数扫描 | PMID 21283776；PMID 41231963 |
| 生物验证 | GO/KEGG、标志基因比对、独立数据集复现 | PMID 37426759；scCoBench promoter-reporter 内部对照（bioRxiv 10.1101/2025.05.26.656221） |

## 5. 关键文献速查（全部已核实）

- WGCNA 原文：Langfelder & Horvath 2008, BMC Bioinformatics, PMID 19114008, 10.1186/1471-2105-9-559
- hdWGCNA 原文：Morabito 2023, Cell Reports Methods, PMID 37426759, 10.1016/j.crmeth.2023.100498（PMC10326379, PDF 可 curl europepmc `?pdf=render`）
- Module preservation：Langfelder 2011, PLoS Comput Biol, PMID 21283776, 10.1371/journal.pcbi.1001057
- MetaCell：Baran 2019, Genome Biol, PMID 31604482；SEACells：Persad 2023, Nat Biotechnol, PMID 36973557
- 伪重复：Zimmerman 2021 PMID 33531494；Squair 2021 PMID 34584091
- BEELINE：Pratapa 2020, Nat Methods, PMID 31907445
- cNMF：Kotliar 2019, eLife, PMID 31282856, 10.7554/eLife.43803
- 待核实项：用户提及 "Hurlock 等" 对 WGCNA 单细胞应用的批评文献未检索到（关键词 'Hurlock WGCNA single-cell' 无结果），疑作者名记忆偏差；de la Fuente 2010（Trends Genet）"共表达描述性"批评未核验 PMID。
