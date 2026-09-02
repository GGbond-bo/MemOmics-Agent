# Seurat 与 Scanpy 多批次单细胞数据整合流程深度调研报告

> 调研时间：2026-08-11 ｜ 信息来源：satijalab.org/seurat 官方 vignette（含 GitHub 源 Rmd）、scanpy.readthedocs.io 官方 API 文档、scvi-tools 官方文档、PubMed/Europe PMC 文献核实

## 一、核心结论（一句话）

Seurat（R）与 Scanpy（Python）在批次整合上的核心差异不在"哪个更好"，而在方法架构与使用范式：**Seurat v5 以"锚定法（CCA/RPCA anchors）"为根基，通过统一入口 `IntegrateLayers()` 把 CCA/RPCA/Harmony/FastMNN/scVI 五种方法接入同一流程，原生支持跨模态（WNN、ATAC、bridge）与标签转移；Scanpy 则是"插拔式"API——Harmony 改 PCA 嵌入、BBKNN 只改 kNN 图、scVI/scANVI 给潜在表示、ComBat 回归表达，按需组合**；规模上 Harmony/scVI/BBKNN 天然适合 10 万级以上数据，Seurat CCA 更适合中小规模/强批次/跨物种场景，超大数据靠 RPCA+reference+sketch 方案。

## 二、Seurat vs Scanpy 生态总对比表

| 维度 | Seurat（R） | Scanpy（Python） |
|---|---|---|
| 整合入口 | v5：`IntegrateLayers()` 统一入口（5 种方法）；v4：`FindIntegrationAnchors()` + `IntegrateData()`；参考映射：`FindTransferAnchors()` + `TransferData()`/`MapQuery()` | 无统一入口，按需插拔：`scanpy.external.pp.harmony_integrate`、`scanpy.external.pp.bbknn`、`scanpy.external.pp.mnn_correct`、`scanpy.pp.combat`（新版核心 API，旧版 external）、scvi-tools 的 `scvi.model.SCVI/SCANVI` |
| 批次校正作用空间 | 锚定法在 CCA/RPCA 低维空间找 anchor → v4 写回校正表达矩阵 / v5 输出低维校正 reduction（不覆盖原始表达） | Harmony：PCA 嵌入（`X_pca_harmony`）；BBKNN：kNN 图（不产新嵌入）；scVI：VAE 潜在空间（`X_scVI`）；ComBat：表达矩阵回归 |
| 是否保留原始表达 | v5 保留（原始数据仍在 RNA assay，批次拆为 layers）；v4 生成新的 integrated assay | 各方法基本不覆盖 `adata.X`（ComBat 例外，写回校正表达） |
| 标签转移 | 一等公民：anchors + TransferData/MapQuery，支持跨模态（RNA→ATAC、蛋白）与参考映射 | `sc.tl.ingest()`（kNN 标签映射）、scANVI（半监督） |
| 多组学整合 | WNN（RNA+ADT/RNA+ATAC 同一细胞）、scATAC-seq 整合、bridge integration/字典学习（Hao 2024） | scvi-tools 生态：totalVI（CITE-seq）、MultiVI、PeakVI；scanpy 本体无 WNN 直接对等物 |
| 超大规模 | RPCA + reference-based + sketch（官方 1M 细胞 vignette）+ BPCells 降内存 | BBKNN（极快图法）、Harmony（官方摘要：约 10⁶ 细胞可在个人电脑完成）、scVI（GPU，官方教程含 Tahoe100M 细胞数据集） |
| 运行环境 | R 单机、future 并行、内存占用高 | Python、AnnData 生态、GPU 友好（scVI/scANVI） |

## 三、方法与算法原理详解

### 3.1 四类方法范式

1. **锚定法（Seurat CCA/RPCA anchors）**——"找跨批次对应细胞对 + SNN 图加权校正"
2. **图结构融合（BBKNN）**——"重连 kNN 图，让跨批次邻居进入同一图"
3. **低维嵌入迭代校正（Harmony）**——"软聚类 + 迭代线性去偏移"
4. **深度生成模型（scVI/scANVI）**——"VAE 学一个与批次无关的潜在空间"

另有：回归法（ComBat，表达级）、MNN 族（Haghverdi 2018；Seurat anchor 思想与其同源，v5 也内置 FastMNNIntegration）。

### 3.2 逐方法原理

**① Seurat 锚定法 CCA/RPCA（Stuart 2019）**：各数据集独立归一化→找高变基因→（RPCA 需各自先跑 PCA）。CCA 在两个数据集间找共享变异方向（CCA 空间）；RPCA 则是"将每个数据集投影到对方的 PCA 空间"（官方 RPCA vignette 原文），锚点用同样的 mutual neighborhood 约束。随后在低维空间找互为最近邻的 **anchor pairs**，用 shared nearest neighbor（SNN）图对 anchors 打分并去重保持一致性，最后用 anchor 对构建校正变换：v4 的 `IntegrateData()` 生成批次校正后的表达矩阵（integrated assay），v5 的 `IntegrateLayers()` 输出低维 reduction（co-embedding）。**CCA 适用**：细胞类型保守但表达差异巨大（疾病/刺激状态）、跨物种、跨模态；但非重叠细胞比例高时易过度校正。**RPCA 更快更保守**（官方原文："a faster and more conservative (less correction) method"），推荐用于：大量细胞无对应类型、同平台多批次（如多个 10x lane）、数据集/细胞数量大。`k.anchor` 控制校正强度（默认 5，调至 20 增强对齐）。

**② Harmony（Korsunsky 2019）**：在 PCA 嵌入上迭代两步——(1) 对细胞做 soft k-means 软聚类（每个细胞按概率属于多个 cluster）；(2) 计算各聚类内每批次的中心偏移，将每个细胞的嵌入按其聚类隶属概率加权地向批次混合中心"拉回"；反复迭代至收敛，输出批次校正后的 PCA 嵌入（harmony reduction / `X_pca_harmony`）。可同时整合多个协变量（batch+donor）。不修改表达矩阵，下游图构建在 harmony 嵌入上。官方摘要声明 **约 10⁶ 细胞可在个人电脑上完成整合**。

**③ BBKNN（Polański 2020）**：在 PCA 上为每个细胞**在每个批次内分别**找 k 个最近邻（`neighbors_within_batch=3` 表示初始邻居数 = 3 × 批次数），合并为跨批次均衡的 kNN 图（对称化处理，`trim` 修剪长尾边），**直接替换 scanpy 的邻居图**（替代 `sc.pp.neighbors`）。不产生任何新嵌入或校正表达——聚类与 UMAP 直接在图上进行。论文主打"extremely fast"，为大规模 atlas 设计。

**④ scVI（Lopez 2018）**：变分自编码器（VAE），观测模型为 **ZINB（零膨胀负二项）** 分布，刻画 drop-out 与文库大小；每个细胞学一个低维潜在变量 z，批次作为条件协变量输入编码器；训练后用编码器后验均值得到与批次无关的潜在表示（`X_scVI`）。随机优化 + GPU 可扩展到百万级，也可用生成过程输出校正/去噪表达（imputation）。**scANVI**（scvi-tools，Gayoso 2022）是 scVI 的半监督扩展：把部分细胞的已知标签（如参考注释）作为训练信号，同时学"标签+批次无关"表示，在 Luecken 2022 大基准中综合表现名列前茅。

**⑤ ComBat（Johnson 2007）**：对每个基因拟合"表达 = 生物学 + 批次"线性模型，批次效应项用经验贝叶斯向整体收缩，输出校正后的表达矩阵。快速简单，但假设批次效应基因层面线性可加，对强/非线性单细胞批次效应能力有限，通常作轻量预处理。

**⑥ MNN（Haghverdi 2018）**：在高维表达空间找互为最近邻的跨批次细胞对（MNN pairs），用 pair 差异向量估计并减去批次效应（cosine 归一化、向量修正、邻域平滑）。scanpy 侧由 mnnpy 封装为 `scanpy.external.pp.mnn_correct`。Seurat 的 anchor 概念与此同源，区别在于锚定法在 CCA/RPCA 空间配对并用 SNN 图加权。

### 3.3 关键维度对比表

| 方法 | 作用空间 | 是否输出/改写表达矩阵 | 跨平台(10x vs Smart-seq2) | 跨物种 | 标签转移 | 典型规模 |
|---|---|---|---|---|---|---|
| Seurat CCA 锚定 | CCA 低维空间 | v4 输出校正表达；v5 输出 reduction | 官方支持 | 官方支持（RPCA vignette 原文） | 支持（anchors/TransferData，跨模态） | 中小（大数需 RPCA/参考法/sketch） |
| Seurat RPCA 锚定 | 互投影 PCA 空间 | 同上 | 推荐同平台（多 10x lane） | 弱（同平台为主） | 支持 | 中–大（+reference 更省） |
| Harmony | PCA 嵌入 | 否（输出 harmony 嵌入） | 支持 | 需先 ortholog 化（原理推断） | 间接（共享嵌入上 kNN） | 大（~10⁶ 个人电脑） |
| BBKNN | kNN 图 | 否（仅改图） | 支持 | 需共享特征空间（原理推断） | 不支持 | 超大（极快） |
| scVI/scANVI | VAE 潜在空间 | 否（输出 `X_scVI`；可生成去噪表达） | 支持（论文跨多种技术） | 需共享基因/ortholog | scANVI 半监督、可配 ingest | 超大（GPU） |
| ComBat | 表达矩阵 | 是（写回校正表达） | 支持但线性假设强 | 需共享基因 | 不支持 | 任意（快） |
| MNN/mnnpy | 表达空间（PCA 后） | 是（返回校正表达） | 支持 | 需共享基因 | 不支持 | 中 |

## 四、代码示例

### 4.1 Seurat v5：IntegrateLayers（五种方法一行切换，Harmony 为例）

```r
library(Seurat)
# 依赖提示：HarmonyIntegration 需安装 harmony R 包；
# scVIIntegration 需 SeuratWrappers + scvi-tools（reticulate 调用）

# v5 关键一步：把 RNA assay 按批次拆成 layers
obj[["RNA"]] <- split(obj[["RNA"]], f = obj$batch)

# 每个批次独立归一化/高变基因/PCA
obj <- NormalizeData(obj)
obj <- FindVariableFeatures(obj, nfeatures = 2000)
obj <- ScaleData(obj)
obj <- RunPCA(obj, npcs = 30)

# 五种方法任选其一（官方 vignette 原文代码风格）
obj <- IntegrateLayers(object = obj, method = CCAIntegration,
                       orig.reduction = "pca", new.reduction = "integrated.cca", verbose = FALSE)
obj <- IntegrateLayers(object = obj, method = RPCAIntegration,
                       orig.reduction = "pca", new.reduction = "integrated.rpca", verbose = FALSE)
obj <- IntegrateLayers(object = obj, method = HarmonyIntegration,
                       orig.reduction = "pca", new.reduction = "harmony", verbose = FALSE)   # ← Harmony 示例
obj <- IntegrateLayers(object = obj, method = FastMNNIntegration,
                       new.reduction = "integrated.mnn", verbose = FALSE)
obj <- IntegrateLayers(object = obj, method = scVIIntegration,
                       new.reduction = "integrated.scvi", verbose = FALSE)

# 下游分析基于整合后的 reduction（原始表达保留在 RNA assay 中）
obj <- FindNeighbors(obj, reduction = "harmony", dims = 1:30)
obj <- RunUMAP(obj, reduction = "harmony", dims = 1:30)
obj <- FindClusters(obj, resolution = 0.5)
```

RPCA 完整流程（官方 RPCA vignette，含 k.anchor 调强度）：

```r
obj[["RNA"]] <- split(obj[["RNA"]], f = obj$batch)
obj <- NormalizeData(obj)
features <- VariableFeatures(FindVariableFeatures(obj, selection.method = "vst", nfeatures = 2000))
obj <- ScaleData(obj, features = features)
obj <- RunPCA(obj, features = features, npcs = 30)
obj <- IntegrateLayers(object = obj, method = RPCAIntegration,
                       features = features, k.anchor = 20, verbose = FALSE)  # k.anchor=20 增强对齐
obj <- FindNeighbors(obj, reduction = "integrated.dr", dims = 1:30)
obj <- RunUMAP(obj, reduction = "integrated.dr", dims = 1:30)
```

### 4.2 Seurat v4 经典锚定流程（旧 API，仍可用）

```r
obj.list <- SplitObject(obj, split.by = "batch")
obj.list <- lapply(obj.list, function(x) {
  x <- NormalizeData(x)
  x <- FindVariableFeatures(x, nfeatures = 2000)
  x
})
# reduction = "cca"（默认）或 "rpca"；大数时建议 rpca + reference 参数
anchors <- FindIntegrationAnchors(object.list = obj.list, dims = 1:30, reduction = "rpca")
integrated <- IntegrateData(anchorset = anchors, dims = 1:30)   # 生成校正表达矩阵（v4 方式）
```

### 4.3 Scanpy：Harmony（scanpy.external.pp.harmony_integrate）

```python
import scanpy as sc
import scanpy.external as sce

sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
sc.pp.highly_variable_genes(adata, batch_key="batch", n_top_genes=2000)
sc.pp.pca(adata, n_comps=30)

# 官方要求：PCA 之后、建邻居图之前调用；可传多个协变量列名
sce.pp.harmony_integrate(adata, key="batch",
                         basis="X_pca", adjusted_basis="X_pca_harmony")
sc.pp.neighbors(adata, use_rep="X_pca_harmony", n_neighbors=15)
sc.tl.umap(adata)
sc.tl.leiden(adata)
```

### 4.4 Scanpy：BBKNN（图融合，替代 sc.pp.neighbors）

```python
sc.pp.pca(adata, n_comps=50)
sce.pp.bbknn(adata, batch_key="batch",
             neighbors_within_batch=3)   # 每批次取 3 个近邻；直接改写邻居图
sc.tl.umap(adata)
sc.tl.leiden(adata)                       # 聚类直接在 BBKNN 图上进行
```

### 4.5 Scanpy：scVI / scANVI（scvi-tools）

```python
import scvi

# 用原始 count 矩阵（adata.X 为 counts，勿先 log 归一化）
scvi.model.SCVI.setup_anndata(adata, batch_key="batch")
model = scvi.model.SCVI(adata, n_latent=30, n_layers=2)
model.train(max_epochs=100)
adata.obsm["X_scVI"] = model.get_latent_representation()
sc.pp.neighbors(adata, use_rep="X_scVI")
sc.tl.umap(adata)

# scANVI：半监督，用参考细胞标签强化整合与注释
scvi.model.SCANVI.setup_anndata(adata, batch_key="batch",
                                labels_key="celltype", unlabeled_category="Unknown")
scanvi = scvi.model.SCANVI.from_scvi_model(model, unlabeled_category="Unknown")
scanvi.train()
adata.obsm["X_scANVI"] = scanvi.get_latent_representation()
```

### 4.6 Scanpy：ComBat 与 MNN

```python
sc.pp.combat(adata, key="batch")          # 写回批次校正后的表达；旧版为 scanpy.external.pp.combat
# 之后需重新 PCA/建图：
sc.pp.pca(adata, n_comps=30)
sc.pp.neighbors(adata)

# MNN（mnnpy 封装）：返回校正表达
sce.pp.mnn_correct(adata, batch_key="batch", k=20, do_concatenate=True)
```

### 4.7 标签转移对照

```r
# Seurat：anchors + TransferData（跨模态亦可，如 RNA 参考 → ATAC 查询）
anchors <- FindTransferAnchors(reference = ref, query = query, dims = 1:30)
query <- AddMetaData(query, TransferData(anchorset = anchors, refdata = ref$celltype))
```

```python
# Scanpy：tl.ingest（kNN 标签映射到参考）
sc.tl.ingest(adata, adata_ref, obs="celltype",
             embedding_method=("umap", "pca"), labeling_method="knn")
```

## 五、适用场景建议

| 场景 | 推荐方案 | 理由/依据 |
|---|---|---|
| 中小规模（<5 万）、经典流程 | Seurat CCA/RPCA；scanpy BBKNN 图法 | 官方主推流程，结果稳健 |
| 强批次效应/疾病状态大差异/跨物种 | Seurat CCA 锚定（官方推荐）或 scVI/Harmony | RPCA vignette 原文：CCA 适合"very substantial differences in gene expression"、跨模态、跨物种 |
| 10 万+ 超大规模 | Harmony（CPU 可行）、scVI（GPU）、BBKNN（图法最快）；Seurat 用 RPCA+reference+sketch 或直接 `HarmonyIntegration`/`scVIIntegration` | Harmony 官方摘要 ~10⁶ 细胞；Seurat 官方大数 vignette（280k 骨髓示例、1M sketch） |
| 同平台多批次（10x 多 lane） | RPCA、Harmony | RPCA vignette：同平台推荐；"多 10x lanes"原文 |
| 跨平台（10x vs Smart-seq2） | CCA、scVI、Harmony | Stuart 2019 跨技术整合；Lopez 2018 多种技术 |
| 多组学同一细胞（RNA+蛋白/ATAC） | Seurat WNN（FindMultiModalNeighbors）；CITE-seq 可用 scvi-tools totalVI | Hao 2021（WNN）；scvi-tools 文档 |
| 参考图谱映射/标签转移 | Seurat anchors/MapQuery（跨模态最强）；scanpy `tl.ingest`、scANVI（半监督） | Stuart 2019；scanpy/scvi-tools 官方文档 |
| 下游需要"校正后表达矩阵"做 DEG | ComBat/MNN、v4 `IntegrateData`、scVI 生成表达 | 嵌入/图法不提供校正表达 |
| 生态绑定 | R 生态（Seurat 全家桶）vs Python 生态（scvi-tools、GPU、后续 ML） | 团队技术栈决定 |

**实证提示（Luecken 2022 基准，68 种方法/预处理组合、85 批次、>120 万细胞、13 个 atlas 任务）**：高变基因（HVG）选择普遍提升整合效果；过度标准化/scale 会让方法偏向去批次而牺牲生物学变异保留；scANVI、Scanorama、scVI 综合表现领先。Tran 2020 基准（14 方法、5 场景）在运行时间、大数据处理、批次校正与细胞类型纯度保持四个维度上系统比较。

## 六、性能与可扩展性对比

| 方法 | 内存 | 时间 | 10 万+ | 百万级 |
|---|---|---|---|---|
| CCA 锚定 | 高（全对全 anchors：10 数据集 = 45 对比较） | 慢 | 吃力，需 RPCA/参考法 | 官方走 sketch（1M vignette） |
| RPCA 锚定 + reference | 中 | 快（官方原文"substantial reduction in compute time and memory"） | 可（官方 280k 骨髓示例） | 配合 sketch |
| Harmony | 低–中 | 快（官方摘要：~10⁶ 细胞可在个人电脑完成） | 可 | 可 |
| BBKNN | 低（只建图） | 极快（论文主打卖点） | 可 | 可（atlas 首选） |
| scVI/scANVI | 中（GPU） | 训练数十分钟–数小时 | 可 | 可（scvi-tools 官方教程含 Tahoe100M 细胞） |
| ComBat/MNN | 低 | 快 | 可 | 可 |

## 七、参考文献（全部经 PubMed/Europe PMC 核实，PMID/DOI 可靠）

1. Stuart T, et al. **Comprehensive Integration of Single-Cell Data**. *Cell*. 2019;177(7):1888-1902. PMID: 31178118. DOI: 10.1016/j.cell.2019.05.031（CCA 锚定整合、跨模态、标签转移）
2. Korsunsky I, et al. **Fast, sensitive and accurate integration of single-cell data with Harmony**. *Nat Methods*. 2019;16(12):1289-1296. PMID: 31740819. DOI: 10.1038/s41592-019-0619-0
3. Lopez R, et al. **Deep generative modeling for single-cell transcriptomics**. *Nat Methods*. 2018;15(12):1053-1058. PMID: 30504886. DOI: 10.1038/s41592-018-0229-2（scVI）
4. Polański K, et al. **BBKNN: fast batch alignment of single cell transcriptomes**. *Bioinformatics*. 2020;36(3):964-965. PMID: 31400197. DOI: 10.1093/bioinformatics/btz625
5. Hao Y, et al. **Integrated analysis of multimodal single-cell data**. *Cell*. 2021;184(13):3573-3587. PMID: 34062119. DOI: 10.1016/j.cell.2021.04.048（WNN）
6. Haghverdi L, et al. **Batch effects in single-cell RNA-sequencing data are corrected by matching mutual nearest neighbors**. *Nat Biotechnol*. 2018;36(5):421-427. PMID: 29608177. DOI: 10.1038/nbt.4091（MNN）
7. Gayoso A, et al. **A Python library for probabilistic analysis of single-cell omics data**. *Nat Biotechnol*. 2022;40(2):163-166. PMID: 35132262. DOI: 10.1038/s41587-021-01206-w（scvi-tools/scANVI）
8. Luecken MD, et al. **Benchmarking atlas-level data integration in single-cell genomics**. *Nat Methods*. 2022;19(1):41-50. PMID: 34949812. DOI: 10.1038/s41592-021-01336-8
9. Tran HTN, et al. **A benchmark of batch-effect correction methods for single-cell RNA sequencing data**. *Genome Biol*. 2020;21(1):12. PMID: 31948481. DOI: 10.1186/s13059-019-1850-9
10. Hao Y, et al. **Dictionary learning for integrative, multimodal and scalable single-cell analysis**. *Nat Biotechnol*. 2024;42(2):293-304. PMID: 37231261. DOI: 10.1038/s41587-023-01767-y（Seurat v5 bridge/字典学习）
11. Johnson WE, et al. **Adjusting batch effects in microarray expression data using empirical Bayes methods**. *Biostatistics*. 2007;8(1):118-127. PMID: 16632515. DOI: 10.1093/biostatistics/kxj037（ComBat）

**官方文档来源（均已在线核验）**：
- Seurat v5 整合 vignette：https://satijalab.org/seurat/articles/seurat5_integration.html（GitHub 源：satijalab/seurat@main vignettes/seurat5_integration.Rmd）
- RPCA 与大数整合 vignette 源文件：vignettes/seurat5_integration_rpca.Rmd、vignettes/seurat5_integration_large_datasets.Rmd
- Scanpy API 文档：scanpy.external.pp.harmony_integrate / scanpy.external.pp.bbknn / scanpy.external.pp.mnn_correct / scanpy.tl.ingest（stable 版官方生成页）；scanpy.pp.combat 见于新版核心 API 导航
- scvi-tools 文档：scvi.model.SCVI、scvi.model.SCANVI（API 参考页）

**注记（诚实性声明）**：①"跨物种"支持仅 CCA 有官方文档明确表述；Harmony/BBKNN/scVI 跨物种需先将基因映射到共享/ortholog 特征空间，此为基于算法原理的推断而非官方原文；②ComBat 的 DOI 为期刊标准 DOI（检索接口未回传 DOI 字段，以 Biostatistics 期刊记录为准）；③版本细节：Seurat v5 的整合 API 已改为 IntegrateLayers（integration.method 概念由 method 参数实现），v4 的 FindIntegrationAnchors+IntegrateData 仍可用；Scanpy 侧 Harmony 为 scanpy.external.pp.harmony_integrate，scVI 通过 scvi-tools 的 scvi.model.SCVI 使用。
