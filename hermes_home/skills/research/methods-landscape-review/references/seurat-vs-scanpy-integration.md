# Seurat vs Scanpy 单细胞整合流程对比 — 知识库（2026-08 调研产出，所有 PMID/DOI 经 PubMed 核实）

## 一句话结论

Seurat 与 Scanpy 整合的核心差异在"结果表达形式"：Seurat 经典 anchor 工作流产出**修正表达矩阵**（integrated assay，可回写表达值）；Scanpy 生态（Harmony/scVI/BBKNN/ingest）**只产出低维 embedding 或修正邻域图，不动原始表达矩阵**（scanpy 官方教程原文："ingest() leaves the data matrix itself invariant"）。两生态差异分析殊途同归走向 **pseudobulk**（Squair 2021, PMID 34584091, DOI 10.1038/s41467-021-25960-2）。

## 方法谱系

| 方法 | 生态 | 原理 | 产物 | 文献 |
|---|---|---|---|---|
| CCA anchors | Seurat v3/v4 | CCA 找共享变异结构 + MNN 锚点对 + 加权修正 | 修正表达矩阵 integrated assay | Butler 2018 PMID 29608179 (10.1038/nbt.4096)；Stuart 2019 PMID 31178118 (10.1016/j.cell.2019.05.031) |
| RPCA | Seurat v4/v5 | 互惠 PCA + MNN 锚点，更快、修正更保守 | reduction / integrated assay | 官方文档 seurat5_integration（"faster and more conservative (less correction)" 原文） |
| Harmony | 双生态 | 迭代软聚类 + 线性批次修正（PCA 空间） | 低维坐标（X_harmony / harmony reduction） | Korsunsky 2019 PMID 31740819 (10.1038/s41592-019-0619-0)；~10^6 细胞可在个人电脑整合 |
| scVI/scANVI | Scanpy(scvi-tools) | 变分自编码器生成模型，显式建模批次 | latent embedding（X_scvi） | Lopez 2018 PMID 30504886 (10.1038/s41592-018-0229-2)；Xu 2021 PMID 33491336 (10.15252/msb.20209620) |
| BBKNN | Scanpy | batch-aware kNN 图（每批次取 k/批次数 近邻再合并） | 仅修正邻居图 | Barkas 2019 PMID 31308548 (10.1038/s41592-019-0466-z) |
| ingest | Scanpy | 参考映射（PCA+近邻树），非对称整合 | 查询数据的投影坐标+标签 | scanpy 官方教程 |
| Seurat v5 IntegrateLayers | Seurat v5 | 一行代码 5 方法：CCA/RPCA/Harmony/FastMNN/scVI | dimensional reduction（默认不生成修正矩阵） | Hao 2024 PMID 37231261 (10.1038/s41587-023-01767-y) |

## Seurat v5 关键机制（官方文档 seurat5_integration 原文验证）

- layers 机制：`split(obj[["RNA"]], f=obj$batch)` → 每批次独立归一化+HVG，自动共识 HVG；整合后 `JoinLayers()` 再做强差异分析
- `IntegrateLayers(normalization.method="SCT")` 支持 SCTransform 数据（SCTransform: Hafemeister 2019 PMID 31870423, 10.1186/s13059-019-1874-1）
- FastMNN 额外生成 mnn.reconstructed 修正矩阵；DE 官方建议用原始 counts + pseudobulk（integration_introduction 原文警告细胞级 FindMarkers p 值需谨慎）

## Scanpy 生态接入点（官方 API 函数名）

`sc.external.pp.bbknn` / `sc.external.pp.harmony_integrate` / `sc.external.pp.scanorama_integrate` / `sc.external.pp.mnn_correct` / `sc.tl.ingest`；深度学习走 `scvi.model.SCVI`/`SCANVI`（输入 raw counts layer）。

## Benchmark 结论（必须引用原文，勿转述走样）

- **Tran 2020**（PMID 31948481, 10.1186/s13059-019-1850-9）：14 方法 × 5 场景（不同技术/非相同细胞类型/多批次/大数据/模拟）× 4 指标（kBET/LISI/ASW/ARI）。结论原文：**"Harmony, LIGER, and Seurat 3 are the recommended methods... Harmony is recommended as the first method to try"**（运行时最短）。
- **Luecken 2022**（PMID 34949812, 10.1038/s41592-021-01336-8）：68 方法+预处理组合 × 85 批次 × >1.2M 细胞 × 13 个 atlas 任务 × 14 指标（scIB 框架）。结论原文：**"scANVI, Scanorama, scVI and scGen perform well, particularly on complex integration tasks"**；**"highly variable gene selection improves performance... whereas scaling pushes methods to prioritize batch removal over conservation of biological variation"**（整合前慎用 scale/regress！）。

## 平台对接（MemOmics 4 项铁轨评估）

LISI（iLISI 混合度↑ / cLISI 分离度↓，出处 PMID 31740819）+ ASW（batch<0.1）+ kBET（rejection<0.05）+ PC 方差（PC1<50%）；与 scIB（Python）兼容。Seurat 侧无内置评估，需自行算；Scanpy 侧 scIB 原生对接 AnnData。

## 已验证文献清单（13 篇，PMID/DOI 全核实）

Butler 2018 (29608179) · Wolf 2018 Scanpy (29409532, 10.1186/s13059-017-1382-0) · Lopez 2018 scVI (30504886) · Stuart 2019 (31178118) · Barkas 2019 BBKNN (31308548) · Hafemeister 2019 SCTransform (31870423) · Korsunsky 2019 Harmony (31740819) · Tran 2020 (31948481) · Xu 2021 scANVI (33491336) · Luecken 2022 (34949812) · Squair 2021 pseudobulk (34584091, 10.1038/s41467-021-25960-2) · Hao 2024 Seurat v5 (37231261, 10.1038/s41587-023-01767-y)

## 官方文档 URL（2026-08 验证可用）

- https://satijalab.org/seurat/articles/seurat5_integration.html（IntegrateLayers 五方法）
- https://satijalab.org/seurat/articles/integration_introduction.html（ifnb 双条件整合、pseudobulk 警告）
- https://scanpy.readthedocs.io/en/stable/tutorials/basics/integrating-data-using-ingest.html（ingest+BBKNN 教程）
- https://scanpy.readthedocs.io/en/stable/generated/scanpy.external.pp.harmony_integrate.html
- https://docs.scvi-tools.org/en/stable/index.html
- ⚠️ 旧 URL 已 404：scanpy .../tutorials/integrating-data-using-harmony.html、satijalab .../integration_multi_tools.html（改版移动，用索引页 href 定位）
