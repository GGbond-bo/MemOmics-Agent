# Seurat vs Scanpy 批次整合方法对比（含核验文献）

> 用途：整合方法选型 / 回答"Seurat 与 Scanpy 整合流程差异"类调研时查此文件。
> 所有 PMID/DOI 均经 PubMed/EuropePMC 实查核实（2026-08）；官方 API 事实来自 satijalab.org vignette（含 GitHub 源 Rmd）、scanpy.readthedocs.io 生成页、scvi-tools 文档。

## 一句话结论
Seurat v5 以锚定法（CCA/RPCA anchors）为根基，用 `IntegrateLayers()` 统一入口接入 5 种方法（CCA/RPCA/Harmony/FastMNN/scVI），原生支持跨模态（WNN/ATAC/bridge）与标签转移；Scanpy 是插拔式 API——Harmony 改 PCA 嵌入、BBKNN 只改 kNN 图、scVI/scANVI 给潜在表示、ComBat 回归表达。规模上 Harmony/scVI/BBKNN 天然适合 10 万+；Seurat CCA 适合中小规模/强批次效应/跨物种场景，超大数据靠 RPCA+reference+sketch。

## 快速选型表（场景 → 推荐）

| 场景 | 推荐 | 依据 |
|---|---|---|
| 中小规模（<5 万）经典流程 | Seurat CCA/RPCA；scanpy BBKNN 图法 | 官方主推 |
| 强批次效应/疾病状态大差异/跨物种 | Seurat CCA（官方明确推荐）、scVI、Harmony | RPCA vignette 原文：CCA 适合强表达差异、跨模态、跨物种 |
| 10 万+ 超大规模 | Harmony（CPU）、scVI（GPU）、BBKNN（图法最快）；Seurat 走 RPCA+reference+sketch | Harmony 摘要 ~10⁶ 细胞个人电脑可跑；Seurat 官方 280k 骨髓 + 1M sketch vignette |
| 同平台多批次（10x 多 lane） | RPCA、Harmony | RPCA vignette 原文 |
| 跨平台（10x vs Smart-seq2） | CCA、scVI、Harmony | Stuart 2019；Lopez 2018 |
| 多组学同一细胞（RNA+蛋白/ATAC） | Seurat WNN（FindMultiModalNeighbors）；CITE-seq 用 scvi-tools totalVI | Hao 2021；scvi-tools |
| 参考图谱/标签转移 | Seurat anchors/MapQuery（跨模态最强）；scanpy `tl.ingest`、scANVI | 官方文档 |
| 下游需"校正后表达矩阵"做 DEG | ComBat/MNN、v4 `IntegrateData`、scVI 生成表达 | 嵌入/图法不提供校正表达 |

## 方法原理速查表（关键维度）

| 方法 | 作用空间 | 输出/改写表达 | 跨平台 | 跨物种 | 标签转移 | 规模 |
|---|---|---|---|---|---|---|
| Seurat CCA 锚定 | CCA 低维空间 | v4 校正表达 / v5 reduction | 官方支持 | 官方支持 | 支持（跨模态） | 中小 |
| Seurat RPCA 锚定 | 互投影 PCA 空间 | 同上 | 同平台推荐 | 弱 | 支持 | 中–大 |
| Harmony | PCA 嵌入 | 否（X_pca_harmony） | 支持 | 需 ortholog（推断） | 间接 | 大 |
| BBKNN | kNN 图 | 否（仅改图） | 支持 | 需共享特征（推断） | 不支持 | 超大 |
| scVI/scANVI | VAE 潜在空间 | 否（可生成表达） | 支持 | 需共享基因 | scANVI 半监督 | 超大（GPU） |
| ComBat | 表达矩阵 | 是 | 线性假设强 | 需共享基因 | 不支持 | 任意 |
| MNN/mnnpy | 表达空间 | 是 | 支持 | 需共享基因 | 不支持 | 中 |

## Seurat v5 API 要点（官方 vignette 核实）
- v5 统一入口 `IntegrateLayers(object, method=..., orig.reduction="pca", new.reduction=...)`，5 种 method：`CCAIntegration` / `RPCAIntegration` / `HarmonyIntegration` / `FastMNNIntegration` / `scVIIntegration`；全部在低维空间整合、返回 reduction（co-embedding），不覆盖原始表达。
- 前置：`obj[["RNA"]] <- split(obj[["RNA"]], f = obj$batch)` 按批次拆 layers；依赖：HarmonyIntegration 需 harmony R 包，scVIIntegration 需 SeuratWrappers + scvi-tools（reticulate）。
- RPCA 比 CCA 快且更保守（官方原文 "faster and more conservative (less correction)"）；`k.anchor` 控制强度（默认 5，调 20 增强对齐）。
- 大数：reference-based 整合（`reference=c(1,2)`；10 数据集从 45 次配对降到 9 次）+ sketch（1M 细胞 vignette）+ BPCells。官方 280k 骨髓示例用 RPCA+reference。
- v4 旧 API 仍可用：`FindIntegrationAnchors(object.list, reduction="cca"/"rpca")` + `IntegrateData()`（返回校正表达矩阵）。
- 多组学：WNN（Hao 2021，RNA+ADT/ATAC 同一细胞）；bridge integration/字典学习（Hao 2024，跨模态参考映射，可配 sketch）。

## Scanpy API 要点（官方生成页核实）
- Harmony：`sce.pp.harmony_integrate(adata, key="batch", basis="X_pca", adjusted_basis="X_pca_harmony")` —— 必须在 PCA 之后、建邻居图之前；可传多个协变量列名列表。
- BBKNN：`sce.pp.bbknn(adata, batch_key="batch", neighbors_within_batch=3)` —— 每批次各取 3 近邻（初始邻居数=3×批次数），对称化建图，`trim` 修剪；**替代 `sc.pp.neighbors`**，不产新嵌入，聚类/UMAP 直接在图上。
- scVI/scANVI：`scvi.model.SCVI.setup_anndata(adata, batch_key="batch")`（adata.X 用原始 counts）→ `model.train()` → `adata.obsm["X_scVI"] = model.get_latent_representation()` → `sc.pp.neighbors(use_rep="X_scVI")`。SCANVI 半监督：`setup_anndata(labels_key="celltype", unlabeled_category="Unknown")`，`SCANVI.from_scvi_model(model, unlabeled_category="Unknown")` → `X_scANVI`。
- ComBat：新版核心 API 导航为 `sc.pp.combat`（旧版 `scanpy.external.pp.combat`），写回校正表达。
- MNN：`sce.pp.mnn_correct(adata, batch_key="batch", k=20)`（mnnpy 封装，返回校正表达）。
- 标签转移：`sc.tl.ingest(adata, adata_ref, obs="celltype", embedding_method=("umap","pca"), labeling_method="knn")`。

## 核验文献表（PMID/DOI 均实查）
| 文献 | PMID | DOI | 关键点 |
|---|---|---|---|
| Stuart 2019 Cell（CCA 锚定） | 31178118 | 10.1016/j.cell.2019.05.031 | 跨技术+跨模态锚定、标签转移 |
| Korsunsky 2019 Nat Methods（Harmony） | 31740819 | 10.1038/s41592-019-0619-0 | 摘要原文："~10⁶ cells on a personal computer" |
| Lopez 2018 Nat Methods（scVI） | 30504886 | 10.1038/s41592-018-0229-2 | VAE+ZINB，处理批次与 drop-out |
| Polański 2020 Bioinformatics（BBKNN） | 31400197 | 10.1093/bioinformatics/btz625 | "extremely fast"图法，atlas 数据 |
| Hao 2021 Cell（WNN） | 34062119 | 10.1016/j.cell.2021.04.048 | RNA+ADT/ATAC 多模态加权近邻 |
| Haghverdi 2018 Nat Biotechnol（MNN） | 29608177 | 10.1038/nbt.4091 | 不要求批次组成相同，仅需共享亚群 |
| Gayoso 2022 Nat Biotechnol（scvi-tools/scANVI） | 35132262 | 10.1038/s41587-021-01206-w | scANVI 半监督 |
| Luecken 2022 Nat Methods（atlas 基准） | 34949812 | 10.1038/s41592-021-01336-8 | 68 组合/85 批次/>1.2M 细胞/13 任务；scANVI、Scanorama、scVI 领先；HVG 提升效果；过度 scaling 牺牲生物变异 |
| Tran 2020 Genome Biol（14 方法基准） | 31948481 | 10.1186/s13059-019-1850-9 | 5 场景：runtime/大数据/校正/纯度 |
| Hao 2024 Nat Biotechnol（Seurat v5 字典学习） | 37231261 | 10.1038/s41587-023-01767-y | bridge integration + sketch |
| Johnson 2007 Biostatistics（ComBat） | 16632515 | 10.1093/biostatistics/kxj037 | 经验贝叶斯批次回归 |

## 官方文档获取技巧（本次实测有效）
- satijalab.org 部分 vignette 页面 404（如 integrate_rpca.html、harmony 教程）→ 用 GitHub API 列目录确认源文件存在：`https://api.github.com/repos/satijalab/seurat/contents/vignettes?ref=main`（已确认文件名：seurat5_integration.Rmd、seurat5_integration_rpca.Rmd、seurat5_integration_large_datasets.Rmd、seurat5_integration_bridge.Rmd、seurat5_weighted_nearest_neighbor_analysis.Rmd 等）→ 用 jsdelivr CDN 拉源文件：`https://cdn.jsdelivr.net/gh/satijalab/seurat@main/vignettes/<file>.Rmd`（raw.githubusercontent.com 可能被网络屏蔽时）。
- scanpy readthedocs 个别生成页 404（如 scanpy.pp.combat、harmony tutorial）→ 用已抓取页面的导航/API 索引确认函数存在；或试版本化 URL（en/1.9.1/...）。
- HTML→文本提取：python 正则去 `<script>/<style>` + `html.unescape` + `\s+` 折叠成单行，再按关键词窗口打印上下文。
- 摘要核实：Europe PMC REST `https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:<PMID>&resultType=core&format=json` 取 abstractText。
- 检索兜底：search_papers 混合源会漏检（BBKNN 论文首轮未命中）→ `query_ncbi(db='pubmed', query='<精确标题>')` 直查成功。

## 诚实性注记
- "跨物种"支持仅 CCA 有官方文档明确表述；Harmony/BBKNN/scVI 跨物种需先 ortholog 化，属原理推断。
- ComBat DOI 为期刊标准 DOI（PubMed 检索接口未回传 DOI 字段），引用时建议加注。
- 版本以 2026-08 官方文档为准：Seurat v5 整合 API 为 IntegrateLayers；Scanpy Harmony 在 scanpy.external.pp。
