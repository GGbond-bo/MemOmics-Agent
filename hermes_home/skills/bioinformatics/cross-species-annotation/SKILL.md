---
name: cross-species-annotation
description: 跨物种单细胞RNA-seq细胞类型注释方法
version: 1.0.0
---

# 跨物种单细胞RNA-seq细胞类型注释

## 核心概念

跨物种注释 = 用已注释物种（参考）的标签迁移到未注释物种（查询）。

## 常用方法

1. Seurat TransferData - 找锚点预测标签
2. SingleR - 相关性打分
3. scType - marker列表自动打分
4. CAMEX (2026) - 多物种整合+注释

## 关键步骤

1. 基因同源映射（人→猴）
2. 找锚点 FindTransferAnchors
3. 预测标签 TransferData
4. 置信度过滤 prediction.score.max

## 海马注释常见坑（2026-08-25 新增）

### 坑1：双轴分类混淆
海马注释同时用**解剖亚区**（DG/CA1/CA2-3/SUB/EC，用于ExN）和**细胞谱系**（Oligo/OPC/Astro/Micro，用于非神经元）。用户常困惑"marker在好几个cluster都亮"——因为用了谱系级marker（如SLC17A7）去打所有ExN亚群。

**正确做法**：先用谱系marker分大群 → ExN内部做亚聚类 → 用亚群级marker（PROX1=DG, EGR1=CA3）区分。

### 坑2：ArchR没有AddModuleScore
`AddModuleScore`是Seurat函数，不适用于ArchRProject。`addScoreGeneset`也不存在。必须用GeneScoreMatrix手动算均值打分（见 `references/hippocampal_annotation_guide.md`）。

### 坑3：RNA vs ATAC数据类型确认
文献标题含"Transcriptome"=RNA-seq，含"chromatin accessibility/ATAC"=ATAC-seq。跨物种注释前必须先确认数据类型，否则选错方法。

### 坑4："predicted annotation"≠手动marker注释
文献中的"predicted annotation"通常是TransferData从人类参考迁移标签，不是手动打marker。需确认参考数据集来源。
