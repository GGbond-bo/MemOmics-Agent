# NHPABC 数据集卡片 + 人·猴海马 8 大类对齐映射（2026-08-26）

> 来源：张潇原稿 `D:/学习文献/Revised text-final.docx`（全文 550 行 Methods+Figure Legends 提取）+ 本会话人侧 40 样本 getMarkerFeatures 对照实测。
> 本文件是专利猴侧数据源的**最新权威卡片**——与此前"猴侧仅 3 Arrow"的所有旧描述冲突时，以本文件为准。

## 1. NHPABC 数据集官方档案

| 项目 | 内容 |
|------|------|
| 数据集名 | NHPABC（Non-Human Primate Aging Brain Cell Atlas） |
| 文章 | Multimodal brain cell atlas across the adult macaque lifespan（Zhang X 等，拟投 Cell，2026） |
| 物种 | 食蟹猴 *Macaca fascicularis*（柬埔寨来源，雌性 23 只） |
| 平台 | DNBelab C4 液滴平台（snRNA-seq + snATAC-seq 双模态） |
| 参考基因组 | **T2T-MFA8 v1.1**（2025 版；唯一官方参考，非 rheMac10） |
| 原始数据 | CNGB 序列归档 **CNP0004459** |
| 处理数据 | NHPABC 网站 https://db.cngb.org/stomics/nhpabc |
| 补充材料 | Zenodo 20482872 |
| 分析代码 | GitHub 3DC-STAR-Anthony/NHPABC |

## 2. 样本设计（23 只 × 8 脑区）

| 年龄组 | 年龄 | 只数 |
|--------|------|:----:|
| Young | 5–6 岁 | 6 |
| Middle | 10–12 岁 | 5 |
| Old | 22–23 岁 | 6 |
| Exceptionally old | 28–31 岁 | 6 |

**8 脑区**：PFC、海马区（hippocampal formation）、纹状体、丘脑、下丘脑、中脑、脑桥+延髓、小脑。
⚠️ 原文注明 *"Not all regions were successfully processed for all individuals"* → **海马区 63 文库 ≠ 23 只**（海马按个体+文库多次上机；做 species×age 混合效应模型前必须按文库归属核实每个年龄组的**个体数**，文库数≠个体数）。

## 3. snATAC-seq 官方处理参数（复现必须一致）

| 步骤 | 参数 |
|------|------|
| 比对 | PISA → fragment 文件 |
| 质控 | **TSS ≥ 4，fragments ≥ 3,000** |
| 双联体 | `addDoubletScores` + `filterDoublets(filterRatio = 2)` |
| 矩阵 | 500-bp tiles（TileMatrix） |
| 降维 | `addIterativeLSI` |
| 聚类 | **Seurat 聚类，resolution = 0.8** |
| 注释 | **直接用 snRNA-seq 的 same markers 注释 ATAC clusters** |
| QC 后规模 | snRNA 1,461,941 核；**snATAC 1,493,932 核**（中位 6,980 fragments/核，TSS 11.57，FRiP 70.36%） |

## 4. 亚群注释体系

- **非神经元**（snRNA 高分辨率）：Ast1/2/3、Mic1/2/3、ODC1/2、OPC1/2/3、COPs、7 种血管/基质亚型
- **神经元**：59 种亚型（snRNA）；splatter 神经元 18 亚群；海马中 DG Ex、CA1/SUB s.f. Ex、CA2-4 Ex 等
- **ATAC 中 splatter 亚群和细微胶质/血管亚型无法可靠分辨（原文承认）** → 与用户 40 人数据行为一致，这是支持"8 大类对齐"的重要证据

## 5. 人·猴海马 8 大类对齐映射（专利实施例素材，用户 2026-08-26 接受）

### 人侧 40 样本 cluster → 8 大类（全部高置信度，无 "?"）

| 大类 | 人 cluster | 人的关键 marker（Log2FC） | 猴对标 | 置信度 |
|------|:---------:|--------------------------|--------|:------:|
| Ex 兴奋性神经元 | C1-C5, C7, C12, C13, C17-19 | CAMK2A, FEZF2, CUX2, NRGN, OPCML（ATAC 分不开 DG/CA1/CA2-4/EC → 统一标 Ex） | DG/CA1/CA2-4/EC 统一 | 高 |
| Inh 抑制性 | C14, C15, C16 | GAD2, DLX1/6, LHX6, SLC32A1, PVALB, SST | MGE-SST / MGE-PVALB / CGE | 高 |
| Astro 星形胶质 | C8, C9, C11 | GFAP, HSPB8, EMX2, SLC1A2, WIF1 | Ast1/2/3 | 高 |
| Micro 小胶质 | C20, C22, C23 | CSF1R, CX3CR1, TMEM119, CD83, CXCL10 | Mic1/2/3 | 高 |
| OPC | C6 | CSPG4, SOX1, OPCML | OPC1/2 | 高 |
| ODC | C30 | OPALIN | ODC1/2 | 高 |
| VS 血管/基质 | C21 | CLDN5, PECAM1, DCN, ACTA2 | Endo/Peri/SMC/Fib | 高 |
| ChP 脉络丛 | —（人侧无对应） | — | Ependymal/ChP | 猴有、人无 → 跳过即可 |

### 已知噪声 cluster（建议过滤，不进实施例）
C25（5 peak OR 基因）、C26（OR/TAS2R 嗅觉/味觉基因）、C28（3 peak）、C29（1 peak）。

### 用法（专利说明书实施例模板）
> 实施例：对人和食蟹猴海马 snATAC-seq 数据进行细胞类型注释，统一为八大主要细胞类型（兴奋性/抑制性神经元、星形胶质、小胶质、少突胶质前体、少突胶质、血管细胞、脉络丛），鉴定各细胞类型随衰老的染色质可及性变化区域（DA regions）……

## 6. 关键结论（供 patent 文档引用）
1. 猴侧数据已补齐（63 文库），**species×age 混合效应模型可行性从"不足"升级为"可核实"**——下一步只需按文库归属核对每组个体数（≥6 个体 × ≥3 年龄组）
2. 人猴兴奋性神经元亚区（DG/CA1/CA2-4/EC）在 ATAC 分辨率分不开——两侧皆然，不是注释质量问题；统一标 Ex 是标准做法
3. 8 大类对齐全部高置信度 → 专利实施例无需再深入 30×59 细粒度对照（少对齐 = 权项宽 + 审查攻击面小）