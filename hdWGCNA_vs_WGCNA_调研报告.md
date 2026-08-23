# hdWGCNA vs 经典 WGCNA：适用场景与参数差异调研报告

> 调研日期：2026-08-14 ｜ 资料来源：hdWGCNA 官方文档/教程/论文（smorabit.github.io/hdWGCNA，Morabito et al. 2023 *Cell Reports Methods* 3:100498）、WGCNA 官方手册 v1.74（CRAN PDF）与官方 FAQ（horvath.genetics.ucla.edu，2017-12-24 更新版，经 archive.org 快照核实）、本机已安装 hdWGCNA 0.4.12 / WGCNA 1.74 函数签名逐一核对。

---

## 1. 适用场景对比：什么数据该用哪个方法

| 维度 | 经典 WGCNA | hdWGCNA |
|---|---|---|
| **数据形态** | bulk RNA-seq、微阵列（基因×样本稠密矩阵） | 单细胞/单核 RNA-seq（scRNA/snRNA-seq）、空间转录组、isoform 水平网络；可扩展至 ATAC（基因活性评分投影）、蛋白组学多组学 | 
| **观察单元** | 样本 = 独立生物学重复；**基因-基因相关在样本间计算** | 细胞 → 先聚合成 metacell（KNN 聚合），**在 metacell 间计算相关**，再投影回单细胞 | 
| **最小样本/单元数** | 官方 FAQ：**<15 个样本不建议做**，最好 ≥20（相关性太噪）[WGCNA FAQ] | metacell 数量需数百至上千：函数默认 `target_metacells=1000`，官方教程示例 500 [hdWGCNA 手册/教程]；越多越稳 | 
| **稀疏度问题** | 矩阵稠密，无 dropout 问题 | 原始单细胞矩阵高度稀疏，直接算相关会产生大量伪零相关；metacell 聚合可将稀疏度降低 10 倍以上 [论文 Fig.1C] | 
| **批次处理** | 无内置，需上游先做批次校正 | 内置：`RunHarmonyMetacells(group.by.vars='Sample')` + `ModuleEigengenes(group.by.vars=...)` 得 harmonized MEs (hMEs) [官方教程] | 
| **跨条件/跨组学** | 多数据集需手动 `blockwiseConsensusModules`，无组学扩展 | 内置 consensus（`SetMultiExpr`+`TestSoftPowersConsensus`+`ConstructNetwork(consensus=TRUE)`）、pseudobulk（`AggregatePseudobulk`，按样本+细胞类型聚合）、差异模块（DMEs/limma）、模块投影 `ProjectModules`（如 bulk→scRNA、RNA→ATAC 基因活性）[官方 vignettes：consensus_wgcna / pseudobulk / differential_MEs / projecting_modules] | 
| **建网粒度** | 全体基因一个网络 | 按细胞类型/亚群分别建网（`SetDatExpr(group_name=目标群, group.by=细胞类型列)`），模块可标到具体亚群 | 

**决策框（一句话选方法）**：
- **bulk RNA-seq / 微阵列（≥15–20 个独立生物学重复）→ 经典 WGCNA**。样本数不足 15 时官方明确不建议 [WGCNA FAQ]。
- **单细胞/单核数据（无论细胞数多少）→ hdWGCNA**：必须走 metacell 聚合，绝不要拿原始稀疏细胞矩阵直接跑 WGCNA。
- **单细胞 + 生物学重复 ≥20 且样本量大 → hdWGCNA pseudobulk**：按"样本×细胞类型"求和聚合后建网，等价于对每个细胞类型跑一次 bulk WGCNA，官方明确引用 WGCNA FAQ 要求最少 20 个重复 [pseudobulk vignette]。
- **多条件/多数据集（如疾病 vs 对照、不同队列）→ hdWGCNA consensus**：各数据集分别 SetMultiExpr 后做共识网络，找跨条件稳定模块 [consensus_wgcna vignette]。
- **空间转录组 → hdWGCNA**（`MetaspotsByGroups` 聚合成 metaspot 再建网）。

**实战例证（骨骼肌数据，2026-08 实测）**：
1. **失败例**：同一基因表达矩阵（约 2 万细胞、10 个肌纤维亚群）不聚合、直接喂给经典 WGCNA——软阈值 SFT R² 最高仅 0.72（不达 0.8 标准），3000 个高变基因全部落入单一 turquoise 模块。根因：原始稀疏矩阵中零膨胀把相关压平，且 3000 基因子集信息量不足。**这是"WGCNA 不能直接用于原始单细胞稀疏矩阵"的直接证据**。
2. **成功例**：同数据走 hdWGCNA 官方 workflow（6482 个 metacells）→ 软阈值 power=10、R²=0.98，拆出 11 个模块。
3. **边界案例**：在高度均质的单一快肌纤维亚群上，连 hdWGCNA 也拆不出模块（R²=0.72 不达标）——网络方法需要足够的转录异质性；均质终末分化群体的共表达主轴太单一，此类数据建议改用 NMF 分解基因程序。

---

## 2. 参数差异详细对比表（均已核对官方文档/源码）

### 2.1 软阈值 power 选择

| 参数/环节 | 经典 WGCNA | hdWGCNA |
|---|---|---|
| 选择函数 | `pickSoftThreshold`（默认 `RsquaredCut=0.85`，`powerVector=c(seq(1,10,by=1), seq(12,20,by=2))`，`corOptions=list(use="p")`）[WGCNA 1.74 手册] | `TestSoftPowers`（默认 `powers=c(seq(1,10,by=1), seq(12,30,by=2))`、`networkType="signed"`、`corFnc="bicor"`；内部实际调用 WGCNA::pickSoftThreshold）[hdWGCNA 0.4.12 源码] |
| 选择标准 | 取 SFT 拟合 R² ≥ 0.8（教程惯例）的最低 power [WGCNA 教程] | 与 WGCNA 相同："pick the lowest soft power threshold with SFT fit ≥ 0.8"；`ConstructNetwork` 未给 soft_power 时自动选择 [官方教程] |
| 多数据集 | 逐数据集手动跑 | `TestSoftPowersConsensus` 对每个 datExpr 矩阵分别测 [consensus vignette] |
| ⚠️ 更正 | **`pickSoftThresholdFromBootstrap` 在当前官方 WGCNA（CRAN 1.74 及 GitHub master 镜像）中不存在**（已核对源码文件清单，仅 `pickSoftThreshold`）——若任务/资料中出现该函数名，请以 `pickSoftThreshold` 为准 | 无对应函数 |

### 2.2 TOM 与网络构建

| 参数 | 经典 WGCNA（blockwiseModules 默认） | hdWGCNA（ConstructNetwork 默认） |
|---|---|---|
| 网络类型 networkType | **"unsigned"**（`adjacency()` 默认 type="unsigned"）[WGCNA 1.74 手册] | **"signed"**（`TestSoftPowers`/`ConstructNetwork` 均默认 signed，可选 unsigned / signed hybrid）；论文推荐 signed adjacency + signed TOM [hdWGCNA 源码/论文] |
| TOMType | blockwiseModules 默认 **"signed"**；底层 `TOMsimilarity()` 默认 "unsigned" [WGCNA 1.74 手册] | **"signed"** [hdWGCNA 源码] |
| TOMDenom | "min" | "min"（一致） |
| corType | "pearson" | "pearson"；软阈值测试用 bicor（对离群值稳健） |
| 默认 power | 6（adjacency 默认） | 由 TestSoftPowers 自动选（无默认值） |
| maxBlockSize | 5000 | 30000（+`useDiskCache=TRUE`，大矩阵磁盘缓存） |
| consensusQuantile | — | 0.3（consensus 模式） |

### 2.3 模块检测与合并

| 参数 | 经典 WGCNA（blockwiseModules 默认） | hdWGCNA（ConstructNetwork 默认） |
|---|---|---|
| deepSplit | **2** | **4**（切分更细，模块更多） |
| pamStage | **TRUE** | **FALSE** |
| detectCutHeight | 0.995 | 0.995（一致） |
| minModuleSize | **min(20, ncol(datExpr)/2)**（函数默认）；经典教程显式设 30 [WGCNA 1.74 手册/教程] | **50** [hdWGCNA 源码] |
| mergeCutHeight | **0.15**（v1.74 函数默认）；`mergeCloseModules()` 默认 0.2 | **0.2** [hdWGCNA 源码] |
| ⚠️ 更正 | **0.25 是经典教程/多数论文的推荐值，不是函数默认值**；官方手册当前默认 0.15 | 官方教程未显式传该参数（用默认 0.2） |
| reassignThreshold / minKMEtoStay | 1e-6 / 0.3 | 沿用 WGCNA 内部默认 |

### 2.4 hdWGCNA 特有：数据准备与表达矩阵（WGCNA 无对应项）

| 函数/参数 | 说明（来源） |
|---|---|
| `SetupForWGCNA(gene_select="fraction", fraction=0.05)` | 选入网基因：默认保留 ≥5% 细胞表达的基因；也可 `"variable"`（HVG）。**教训：只取 3000 个 HVG 子集会导致假平坦网络，须用完整基因集（>5000）**[官方教程/实测] |
| `MetacellsByGroups(group.by=c("cell_type","Sample"), k=25, max_shared=10~15, min_cells=100, target_metacells=1000, mode="average", reduction="harmony")` | 聚合参数：`group.by` 必须包含样本列（保证 metacell 不跨样本）；k=25 为最近邻数（官方教程 25，小数据可降低）；max_shared 控制 metacell 间共享细胞上限；target_metacells 控制目标 metacell 数（默认 1000，教程示例 500、共识教程 250）；聚合方式默认均值 [hdWGCNA 0.4.12 源码/教程] |
| `SetDatExpr(group_name, group.by='cell_type', use_metacells=TRUE, slot/layer='data', multi.group.by/multi_group_name, features)` | 取某细胞群的表达矩阵入网：默认用 metacell 矩阵（use_metacells=TRUE）；group.by 需与 MetacellsByGroups 一致；group_name 可传向量同时建多群网络；`multi.group.by` 用于按额外列（如性别/条件）拆分子集（consensus 场景）[hdWGCNA 0.4.12 帮助] |
| 批次校正 | 聚合前 `RunHarmonyMetacells(group.by.vars='Sample')`；ME 计算时 `ModuleEigengenes(group.by.vars='Sample')` 得 hMEs（需先 ScaleData；可同时 `vars.to.regress` 回归连续协变量）[官方教程/论文] |
| 下游 | `ModuleConnectivity(group.by='cell_type')` 按群算 kME；`GetHubGenes(n_hubs=10)` 取 hub 基因；`ModuleTraitCorrelation(traits=meta.data 列名)` 做模块-性状关联 [官方教程] |

---

## 3. 参数速查表：拿到单细胞数据怎么配（推荐值）

```r
# ① 基因选择（用完整基因集，勿用 3000 HVG 子集）
seurat_obj <- SetupForWGCNA(seurat_obj, gene_select="fraction",
                            fraction=0.05, wgcna_name="sc_wgcna")

# ② metacell 聚合（关键：group.by 必须含样本列 + 细胞类型列）
seurat_obj <- MetacellsByGroups(seurat_obj,
  group.by = c("cell_type", "Sample"),   # 细胞类型 + 生物学样本
  k = 25, max_shared = 10,               # 官方教程值；小数据 k 可降
  min_cells = 100, target_metacells = 1000,  # 默认 1000；>500 起步，越多越稳
  reduction = "harmony",                 # 先 RunHarmonyMetacells 去批次
  ident.group = "cell_type")
seurat_obj <- NormalizeMetacells(seurat_obj)

# ③ 取目标细胞群表达矩阵（按群建网）
seurat_obj <- SetDatExpr(seurat_obj, group_name = "快肌纤维",  # 具体组值向量
                         group.by = "cell_type", assay = "RNA", layer = "data")

# ④ 软阈值测试 → 取 SFT R² ≥ 0.8 的最低 power（默认 signed/bicor）
seurat_obj <- TestSoftPowers(seurat_obj, networkType = "signed")
# R² 最高也不到 0.8 → 排查：异质性不足？基因数太少？未聚合直接跑？

# ⑤ 建网（可显式传 soft_power，如 power=10）
seurat_obj <- ConstructNetwork(seurat_obj, soft_power = 10, tom_name = "fast",
                               networkType = "signed", TOMType = "signed",
                               minModuleSize = 50, mergeCutHeight = 0.2,
                               deepSplit = 4)   # 全部为官方默认，可按需调

# ⑥ 模块 eigengene + 批次校正（hMEs）+ hub 基因 + 模块-性状关联
seurat_obj <- ModuleEigengenes(seurat_obj, group.by.vars = "Sample")  # 需先 ScaleData
seurat_obj <- ModuleConnectivity(seurat_obj, group.by = "cell_type", group_name = "快肌纤维")
hub_df <- GetHubGenes(seurat_obj, n_hubs = 10)
seurat_obj <- ModuleTraitCorrelation(seurat_obj, traits = c("Aging"), features = "hMEs")
```

**实战验证参数**（骨骼肌 2 万细胞，已跑通）：6482 metacells、power=10（R²=0.98）、11 模块、minModuleSize 默认 50、networkType signed。

**常见坑速查**：
- 原始稀疏细胞矩阵直接跑 WGCNA → R² 不达标/单模块（必须先聚合）。
- 均质亚群（如单一终末分化肌纤维）→ 无模块可拆，属异质性边界，改用 NMF。
- `SetDatExpr` 报 "groups not found" → group_name 传具体组值，非列名。
- `ModuleEigengenes` 报 "Need to run ScaleData" → 先 ScaleData。
- 模块合并过头 → 调低 mergeCutHeight（0.15–0.2）；模块太碎 → 调低 deepSplit（2–4）。

---

## 资料来源
- hdWGCNA 官方站点（basic tutorial / consensus / pseudobulk / differential_MEs vignettes、函数参考页）：https://smorabit.github.io/hdWGCNA/
- hdWGCNA 0.4.12 已装包函数签名与帮助（本机 R 4.4.2 逐一核对）
- Morabito S, et al. hdWGCNA identifies co-expression networks in high-dimensional transcriptomics data. *Cell Reports Methods* 2023;3:100498. doi:10.1016/j.crmeth.2023.100498
- WGCNA 官方参考手册 v1.74（CRAN PDF）：https://cran.r-project.org/web/packages/WGCNA/WGCNA.pdf
- WGCNA 官方 FAQ（2017-12-24 更新；archive.org 快照）：https://horvath.genetics.ucla.edu/html/CoexpressionNetwork/Rpackages/WGCNA/faq.html
- WGCNA GitHub master 源码文件清单（核实 pickSoftThreshold 系列函数）：https://github.com/cran/WGCNA
