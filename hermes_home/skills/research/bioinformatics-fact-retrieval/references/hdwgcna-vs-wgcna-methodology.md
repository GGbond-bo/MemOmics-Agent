# hdWGCNA vs 经典 WGCNA 方法学要点（2026-08 已核实）

核实途径：论文全文 PDF（Morabito 2023）、官方 basic_tutorial（v0.4.12，smorabit.github.io）、dev 分支源码 `R/metacells.R`、WGCNA 2008 原文 PDF（Europe PMC）。输出报告：`work/hdwgcna_research/hdWGCNA_vs_WGCNA_调研报告.md`。

## 文献引用（重要更正，避免误引）

| 文献 | 正确引用 | 常见错误 |
|---|---|---|
| WGCNA 原始文献 | Langfelder & Horvath, **BMC Bioinformatics** 2008;9:559. PMID 19114008, DOI 10.1186/1471-2105-9-559 | — |
| hdWGCNA 方法论文 | Morabito S, Reese F, Rahimzadeh N, Miyoshi E, Swarup V. **Cell Reports Methods** 2023;3(6):100498. PMID 37426759, DOI 10.1016/j.crmeth.2023.100498 | ⚠️ **常被误引为 Nature Methods 2023**；标题 *"High-dimensional co-expression networks enable discovery of tumour- and immune-associated biology"* 经 PubMed/EuropePMC 检索查无此文。任务描述给的期刊/标题组合不可信时，用 PubMed 核实卷期并在报告标注更正 |
| Dynamic Tree Cut | Langfelder, Zhang & Horvath, Bioinformatics 2008;24(5):719-720 | — |
| 软阈值/无标度准则 | Zhang & Horvath 2005, Stat Appl Genet Mol Biol 4:Article17, DOI 10.2202/1544-6115.1128 | — |

## metacell 构建（论文 Algorithm 1 + 源码 metacells.R）

- **算法**：bootstrapped aggregation (bagging) + kNN。在降维表示（Harmony/PCA，`FNN::knn.index` 取 k−1 近邻+自身）上随机采样中心细胞 → 与 k 近邻聚合为 1 个 metacell；与已选 metacell 共享细胞数 > `max_shared` 则拒绝；循环至 `target_metacells`（默认 1000）/`max_iter`（默认 5000）收敛。论文伪代码 Algorithm 1（STAR Methods）。
- **聚合方式（源码硬校验）**：`mode` 仅支持 **"average"（默认，new_exprs = exprs %*% mask 后除以 k）或 "sum"**；**median/geometric-mean 官方未实现**——任务描述出现"三种聚合方式"时只认 average/sum，其余标注待核实，不要顺着任务说法写。
- **为什么解决稀疏性**：单细胞矩阵 sparsity（零元素占比，>0.5 定义为稀疏，Equation 1）极高；dropout 使基因-基因相关分布在 0 处尖峰（假相关）；metacell 矩阵相关性分布平坦化、sparsity 下降 10 倍以上（Figure 1B/1C）。教程原文 "correlation network approaches such as WGCNA are sensitive to data sparsity"。
- **"保守 metacell 策略"无此术语**：实质 = `MetacellsByGroups` 按 `group.by=c('cell_type','Sample')` 分组，metacell **仅在同一生物样本内聚合**（避免跨样本批次假共表达、保留 age/sex/disease 信息）+ `max_shared` 重叠限制 + `min_cells`（默认 100）剔除小群。
- **参数**：k 建议 20–75（教程例 40,039 细胞 k=25、max_shared=10）；空间版 metaspot ≤7 spot、≤2 重叠；极少数细胞类型（如血管周细胞/内皮）不适合 metacell 聚合。

## 标准流程与数学细节

- 流程：SetupForWGCNA → MetacellsByGroups → NormalizeMetacells → `SetDatExpr`（默认 metacell 矩阵 `use_metacells=TRUE`，`group_name` 选细胞群，可多群）→ `TestSoftPowers`（signed/unsigned/signed hybrid；选 SFT.R.sq≥0.8 的最低 power，教程例 power=9；`GetPowerTable` 看表）→ `ConstructNetwork`（**内部调 WGCNA `blockwiseConsensusModules`**，可传同名参数；TOM 写盘，`GetTOM` 读取）→ `ModuleEigengenes` → `ModuleConnectivity`（kME）→ `ModuleTraitCorrelation`（cor/pval/fdr，**按细胞群分组**，仅限数值/二分类/有序分类变量）→ DME。
- **网络数学**：signed adjacency `a_ij=(1+cor(xi,xj))/2`（Eq.2）→ 幂次 β 软阈值（Eq.3）→ signed TOM（Eq.4-6，负相关负向抑制连接）→ DissTOM = 1 − TOM → Dynamic Tree Cut。
- **Eigengene 差异（核心）**：WGCNA = 模块矩阵第一主成分（样本维度）；hdWGCNA = 在**全部单细胞**上计算（建网用 metacell、ME 用单细胞矩阵）：ScaleData（可回归技术协变量）→ SVD `X=UDVᵀ` → ME = 第一列右奇异向量 v1（Eq.7，等价 PCA 第一主成分）→ 可选 **Harmony 批次校正 → hMEs**（`group.by.vars="Sample"`）；IRLBA 加速。
- **DME**：组间 ME 差异检验 = Wilcoxon rank-sum + Bonferroni 校正 + 平均 log2 fold change（论文 Figure 5D 应用例）。
- 模块-性状变量约束：分类变量仅支持二分类或有序（如 disease stage），无序多分类需两两转二分类（module_trait_correlation vignette 原文）。
- 建网用**完整基因集**（SetupForWGCNA fraction 0.05 → 上万基因）；top3000 高变基因子集会得到假平坦网络（单一 turquoise 模块、R² 低）→ 误判"数据不适合 WGCNA"。

## 检索获取技巧（本次验证）

- smorabit.github.io 页面 curl 常 SSL error 35 → 改 **raw.githubusercontent.com/smorabit/hdWGCNA/dev/**（源码/vignette Rmd 可下；raw 不可用时换 jsdelivr CDN）。
- 开放获取论文 PDF：`europepmc.org/articles/PMC<id>?pdf=render` 直接 curl 下载（download_pdf 的 pmc_fulltext 策略失败时的手动兜底）。
- web_extract 后端为 search-only（ddgs）时无法提取 URL → curl 下载 HTML 后 python 正则提取正文（去 script/style → 去标签 → unescape → 关键词窗口打印）。
- pymupdf (fitz) 提取 PDF 全文 → 正则定位 Algorithm/Equation 段，避免整页输出。
- 大文件 write_file 可能流超时 → 报告拆 3 部分分别 write_file，再 `cat` 合并。
