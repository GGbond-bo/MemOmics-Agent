# WGCNA vs hdWGCNA 官方参数默认值（2026-08-14 全量核实）

核实方法（本机实测 + 官方一手来源）：
- CRAN WGCNA 1.74 官方手册 PDF（436 页，pymupdf 全文本提取）
- 本机已装包函数签名：`Rscript -e 'print(args(hdWGCNA::SetDatExpr))'` / `formals(WGCNA::blockwiseModules)`（比查网页权威）
- hdWGCNA 0.4.12 已装包 + GitHub **dev** 分支源码（R/SoftPowers.R、R/ConstructNetwork.R、R/ModuleEigengenes.R、R/metacells.R、R/SelectNetworkGenes.R）
- 官方 vignettes：basic_tutorial / consensus_wgcna / pseudobulk / differential_MEs（dev 分支源码）
- 论文：Morabito et al. 2023, Cell Reports Methods 3:100498（PMID 37426759）
- WGCNA 官方 FAQ（2017-12-24 更新版，经 archive.org 2021 快照核实）

## ⚠️ 关键纠正（与网上常见说法不同，以官方核实为准）

| 常见说法 | 实际情况 |
|---|---|
| mergeCutHeight 默认 0.25 | ❌ 0.25 是**经典教程推荐值**。WGCNA blockwiseModules v1.74 默认 **0.15**；mergeCloseModules 默认 0.2；hdWGCNA ConstructNetwork 默认 **0.2** |
| WGCNA minModuleSize 默认 30 | ❌ 函数默认 `min(20, ncol(datExpr)/2)`；30 是教程显式设置值。hdWGCNA 默认 **50** |
| 两方法都默认 unsigned | ❌ WGCNA blockwiseModules/adjacency 默认 **"unsigned"**；hdWGCNA TestSoftPowers/ConstructNetwork 默认 **"signed"**（论文推荐 signed adjacency + signed TOM） |
| WGCNA 有 pickSoftThresholdFromBootstrap | ❌ 官方 WGCNA（CRAN 1.74 + GitHub master 镜像源码清单）**无此函数**，仅 pickSoftThreshold（默认 RsquaredCut=0.85）。不要再引用该函数名 |
| 官方建议 metacell >500 | ⚠️ 无字面 ">500" 官方声明。函数默认 `target_metacells=1000`，basic tutorial 示例 500、consensus 教程 250。实践共识：数百至上千、越多越稳 |

## 参数对比表（官方核实）

### 软阈值选择
| 项 | WGCNA | hdWGCNA |
|---|---|---|
| 函数 | pickSoftThreshold | TestSoftPowers（内部调 WGCNA::pickSoftThreshold） |
| 默认阈值 | RsquaredCut=0.85 | 同（选 SFT R²≥0.8 的最低 power，教程惯例） |
| power 扫描 | c(seq(1,10,by=1), seq(12,20,by=2)) | c(seq(1,10,by=1), seq(12,30,by=2)) |
| 相关函数 | corOptions=list(use="p") | corFnc="bicor" |
| 多数据集 | 逐个手动 | TestSoftPowersConsensus |

### 网络构建（默认值）
| 参数 | WGCNA blockwiseModules | hdWGCNA ConstructNetwork |
|---|---|---|
| networkType | "unsigned" | "signed"（可选 unsigned/signed hybrid） |
| TOMType | "signed"（注意：底层 TOMsimilarity 默认 "unsigned"） | "signed" |
| TOMDenom | "min" | "min" |
| corType | "pearson" | "pearson" |
| power | 6（adjacency 默认） | 自动选择（soft_power=NULL 时） |
| maxBlockSize | 5000 | 30000 + useDiskCache=TRUE |
| consensusQuantile | — | 0.3 |

### 模块检测（默认值）
| 参数 | WGCNA | hdWGCNA |
|---|---|---|
| deepSplit | 2 | 4 |
| pamStage | TRUE | FALSE |
| detectCutHeight | 0.995 | 0.995 |
| minModuleSize | min(20, ncol/2) | 50 |
| mergeCutHeight | 0.15（教程 0.25） | 0.2 |
| reassignThreshold/minKMEtoStay | 1e-6 / 0.3 | 沿用 WGCNA 内部默认 |

### hdWGCNA 特有流程参数（0.4.12）
- `SetupForWGCNA(gene_select="fraction", fraction=0.05)`；也可 "variable"（HVG）。**勿用 3000 HVG 子集建网 → 假平坦网络**（实测 R²=0.72、单一 turquoise 模块）；用完整基因集（>5000）power=10 R²=0.98
- `MetacellsByGroups(group.by=c("cell_type","Sample"), k=25, max_shared=15(教程10-12), min_cells=100, target_metacells=1000(教程500), mode="average", reduction="harmony")`——group.by 必须含样本列，metacell 不跨样本
- `SetDatExpr(group_name=具体组值向量, group.by='cell_type', use_metacells=TRUE, layer='data', multi.group.by/multi_group_name)`——group_name 传值不传列名
- `ModuleEigengenes(group.by.vars='Sample')` → Harmony 校正得 hMEs；**必须先 ScaleData**；可配 vars.to.regress
- `ModuleConnectivity(group.by='cell_type', group_name=...)` 按群算 kME；`GetHubGenes(n_hubs=10)`；`ModuleTraitCorrelation(traits=meta.data 列名字符向量)`
- Consensus：`SetMultiExpr` + `ConstructNetwork(consensus=TRUE, soft_power=每数据集一个值的向量)`
- Pseudobulk：`AggregatePseudobulk(replicate_col='Sample', group_col='cell_type')` + VST 归一化；**需 ≥20 生物学重复**（官方引用 WGCNA FAQ）

## 适用场景速判
- bulk/微阵列（≥15-20 独立生物学重复）→ 经典 WGCNA；<15 官方不建议（FAQ 原话："do not recommend attempting WGCNA on fewer than 15 samples... at least 20"）
- 单细胞（无论细胞数）→ hdWGCNA metacell（原始稀疏矩阵直跑 WGCNA：R² 不达标/单模块）
- 单细胞 + ≥20 重复 → hdWGCNA pseudobulk
- 多条件/多队列 → hdWGCNA consensus；空间 → MetaspotsByGroups
- 均质终末亚群（如单一快肌纤维）拆不出模块（R²≈0.72）→ 先换完整基因集重跑，仍失败再改 NMF

## 技术坑（本次实测）
- hdWGCNA GitHub 默认分支是 **dev** 不是 main：`raw.githubusercontent.com/smorabit/hdWGCNA/dev/...`，main 一律 404
- smorabit.github.io / UCLA 站点 curl 常 SSL reset（exit 35）：兜底路径 GitHub API（api.github.com/repos/.../contents/）、raw.githubusercontent、cdn.jsdelivr.net、web.archive.org
- execute_r 调用的 R 4.5.3（Program Files）Matrix.dll 损坏无法加载包 → 用终端直接调 R 4.4.2 Rscript：`C:/Users/USERNAME/AppData/Local/R/R-4.4.2/bin/Rscript.exe`
- 验证已装包默认值：`Rscript -e 'loadNamespace("hdWGCNA"); print(args(asNamespace("hdWGCNA")$SetDatExpr))'`——签名即文档
- 软阈值 R² 不达标排查顺序：未聚合直接用稀疏矩阵 / 基因子集太少 / 亚群异质性不足

## 来源
- https://smorabit.github.io/hdWGCNA/（教程 + 函数参考）
- Morabito et al. 2023 Cell Rep Methods 3:100498
- https://cran.r-project.org/web/packages/WGCNA/WGCNA.pdf（v1.74）
- WGCNA FAQ：https://horvath.genetics.ucla.edu/html/CoexpressionNetwork/Rpackages/WGCNA/faq.html（archive.org 2021 快照）
- 完整中文调研报告：MEMOMICS_HOME\hdWGCNA_vs_WGCNA_调研报告.md
