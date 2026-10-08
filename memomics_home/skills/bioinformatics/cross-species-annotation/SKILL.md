---
name: cross-species-annotation
description: 跨物种单细胞细胞类型注释方法（RNA-seq + ATAC-seq）。RNA 用 TransferData/SingleR/scType/CAMEX；ATAC 用 marker 基因全量搜索对照（注意非编码 RNA 污染 + ExN 亚区域不可分）。触发：跨物种注释 / 人猴 marker 对比 / ATAC 跨物种 / cell type transfer / 标签迁移
version: 1.1.0
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
`AddModuleScore`是Seurat函数，不适用于ArchRProject。`addScoreGeneset`也不存在。必须用GeneScoreMatrix手动算均值打分（见 `references/hippocampal_annotation_guide.md` 和 `references/brain_cell_type_markers.md`）。

### 坑3：RNA vs ATAC数据类型确认
文献标题含"Transcriptome"=RNA-seq，含"chromatin accessibility/ATAC"=ATAC-seq。跨物种注释前必须先确认数据类型，否则选错方法。

### 坑4："predicted annotation"≠手动marker注释
文献中的"predicted annotation"通常是TransferData从人类参考迁移标签，不是手动打marker。需确认参考数据集来源。

### 坑5：getMarkerFeatures testMethod 参数
ArchR 官方教程写法：`testMethod = "wilcoxon"`（不是 "U"）。`testMethod = "G"` 是 Gaussian 近似，快 3-5 倍。30 cluster × 16万细胞 TileMatrix Wilcoxon 可能 OOM。

### 坑6：filterDoublets(filterRatio) 默认值
ArchR 默认 `filterRatio = 1`（保留 50%）。Zhang Xiao 2026 用 `filterRatio = 2`（保留 33%，更严格）。保留比例 = 1/(1+filterRatio)。

### 坑7：marker 签名参考
完整 marker 列表见 `references/brain_cell_type_markers.md`（大群 + 海马亚群 + ArchR 打分代码 + 文章对照表）。

### 坑8：ATAC-seq 跨物种 marker 比较的两大陷阱（2026-08-26 实测）

**陷阱 A：ATAC top marker 被非编码 RNA 污染**

ATAC peak-to-gene 注释的 top marker 列表中，前 30 位几乎全是 miRNA（MIR517A/MIR519D）、snRNA（SNORD114 系列）、嗅觉受体基因（OR7A5/OR5B2）和角蛋白相关基因（KRTAP 系列）。真正的蛋白编码 marker（GAD2/GFAP/CSF1R 等）被挤到 30 名开外。

**后果**：如果只查 top30，会误判为"marker 未出现"（False Negative）。

**正确做法**：搜**全量**基因列表（不限 top N），逐基因在所有 cluster 中查 Log2FC + FDR。脚本示例：
```python
hits = m[m['name']==gene]  # 不过滤排名，搜全部
for _, row in hits.sort_values('Log2FC', ascending=False).iterrows():
    print(f"  {gene} → {row['group_name']} Log2FC={row['Log2FC']:.2f} FDR={row['FDR']:.2e}")
```

**陷阱 B：兴奋性神经元亚区域 marker 在 ATAC 分辨率下不可分**

张潇猴脑的 ExN 亚区域 marker（DG: NEUROD1/PROX1; CA1: CAMK2A/SORL1; CA2-4: EGR1/NPY1R; EC: CUX2/TLE4）在人类 40 样本 ATAC 数据中散在 C1-C19 多个 cluster 里，无法唯一对应。

**根本原因**：ATAC-seq 检测的是染色质可及性，不是基因表达。兴奋性神经元亚区域的差异主要在 **基因表达层面**（RNA marker），不在 **染色质开放层面**。张潇原文也承认 ATAC 分辨率下 ExN 亚区域分不开。

**正确做法**：
- 非神经元（Ast/ODC/Mic/Endo）和抑制性神经元（Inh）：ATAC marker 跨物种可对齐（GAD2/DLX1/LHX6/GFAP/CSF1R 等）
- 兴奋性神经元（ExN）：ATAC 只能标 "Ex"（大群），不能分 DG/CA1/CA2-4/EC 亚区域
- 如需细分 ExN → 必须用 RNA-seq 数据的 marker（PROX1=DG, EGR1=CA3, CALB2=CA2 等）

**实测案例**：人类 40 海马 ATAC 28 cluster × 张潇猴脑亚群对照结果：
- ✅ 高置信：C8/C11=Ast(GFAP+), C9=Ast(WIF1+), C6=OPC, C14/C15=MGE-Inh, C16=CGE-Inh, C20/C22/C23=Mic, C21=Endo, C30=ODC
- ⚠️ 中置信：C1-C5=DG Ex（OPCML/ADRA1A 高但与 OPC marker 重叠）
- ❌ 无法对齐：DG/CA1/CA2-4/EC 各亚区域（NEUROD1/PROX1/CAMK2A/CUX2/TLE4 在 top marker 中均未出现，全量搜索后散在多个 cluster）

### 坑9：⚠️ 不要凭 marker 数量/OR 基因就把大细胞量 cluster 判为噪声（2026-08-27 推翻坑8 旧结论）

**此前坑8 曾把 C25/C26/C28/C29 判为"噪声（OR 基因/peak 数 <5）"——该结论被后续实测推翻，务必更正。**

**推翻证据（2026-08-27 全量重分析）**：
- C26 有 1146 个 marker，其中 **825 个（72%）是 C26 特异**（只在 C26 出现，非共享背景）
- C26 特异 marker 含**真实神经元基因**：GAD2、SLC17A6、FOXP2、CALB1、EOMES + GPC5/CSMD3/NRG1/ROBO2/DCC/EPHA6/RIMS1/CNTN4
- 用户跑 TSS violin（plotGroups TSSEnrichment）→ **TSS 很高**，与"低质量垃圾群"矛盾

**正确判据（判定 cluster 是否噪声/低质量，必须三查之后才下结论）**：
1. **QC 三指标**：TSSEnrichment + log10(nFrags) + DoubletScore（plotGroups violin）。**TSS 高 = 不是低质量**，先别定性
2. **marker 特异性**：算每个 marker 出现在几个 cluster（特异 vs 共享背景）。特异 marker 占比高（如 C26 72%）→ 有真实身份信号；全是共享背景基因 → 混合残余
3. **特异 marker 的生物学构成**：看特异基因是不是真实细胞类型基因（神经元 GAD2/SLC17A6/NRGN 等），不是只看 OR/非编码 RNA

**正确处理（不盲目删除）**：
- 大细胞量 + 高 TSS + 高特异 marker 占比 → **亚分离的真实 cluster**（under-separated），不是垃圾
- 处理选项：① 单独 subset 出来提高分辨率重聚类（addIterativeLSI iterations=2, resolution=1.5）看能否拆出真实群；② 专利最稳做法 = cellColData 标 "Ambig" + 下游 DA/保守性分析排除（不冤枉也不带病）；③ 仅当 QC 明确差（低 TSS + 低 Frags + 高 DoubletScore）才剔除

**教训**：OR/味觉基因 + marker 数量少 ≠ 噪声。OR 基因是 mappability 假 peak 的背景信号，但特异 marker 占比和 QC 才是决定性证据。

详见 `references/atac_cross_species_marker_pitfalls.md` 和 `references/subcluster_alignment_mapping.md`。

## 细分亚群对齐注释策略（2026-08-27 新增）

### 核心原则
**能对齐的细分亚群用相同名字，不能对齐的各自保留原文名字**。不要强行把所有 cluster 塞进 8 大类。

### 对齐逻辑（人脑海马 ATAC vs 猴脑）
| 人脑 Cluster | Top Markers | 对齐注释 | 猴脑对应 | 置信度 |
|---|---|---|---|---|
| C1-C6 | CSPG4, SOX6, ASCL1, MYT1 | **OPC** | OPC (6,574) | ✅ 高 |
| C7-C12 | AQP4, GFAP, SLC1A2, ALDH1L1 | **Astrocyte** | Astrocyte (23,548) | ✅ 高 |
| C14, C15, C16, C18 | GABBR2, SLC32A1, DLX6-AS1, ADARB2 | **Inhibitory** | CGE/MGE subtypes | ✅ 高 |
| C17, C19 | BCL11B, GRIN2A | **Excitatory** | DG Ex, CA1_SUB, etc. | ⚠️ 中 |
| C20-C23 | CX3CR1, IRF8, CD163 | **Microglia** | Microglia (9,388) | ✅ 高 |
| C30 | OPALIN, MAG | **ODC** | ODC (44,021) | ✅ 高 |
| C13 | EBF3, MNX1, UNCX | C13 (保留) | ❌ 无对应 | - |
| C25 | OR2T4, OR7A5 | C25 (保留) | ❌ 无对应 | - |
| C26 | NRG1, ROBO2, GRM8 | C26 (保留) | ❌ 无对应 | - |
| C28 | LINC00482, CT47A7 | C28 (保留) | ❌ 无对应 | - |
| C29 | LOC284412 | C29 (保留) | ❌ 无对应 | - |
| C24, C27 | 不在 marker list | **Unknown** | ❌ 待补充 | - |

### 关键 Marker 判据
- **OPC**: CSPG4(NG2), SOX6, SOX1, ASCL1
- **Astrocyte**: AQP4, GFAP, SLC1A2, ALDH1L1, ETNPPL, ZIC5
- **Microglia**: CX3CR1, IRF8, CD163, TNFRSF1B, SRGN
- **ODC**: OPALIN, MAG, TMEM235, VWA1
- **Inhibitory**: GABBR2, SLC32A1(VGAT), DLX6-AS1, ADARB2
- **Excitatory**: BCL11B(CTIP2), GRIN2A, KCNAB2

### 坑10：ArchRProject metadata 访问（2026-08-27 实测）

ArchRProject 对象没有 `@meta.data` 槽位，必须用 `getCellColData()` 函数。

```r
# ❌ 错误：ArchRProject 没有 meta.data 槽位
meta <- human@meta.data  # Error: no slot of name "meta.data"

# ✅ 正确：用 ArchR 函数
library(ArchR)
meta <- getCellColData(human)
```

### 坑11：marker list 与数据 cluster 不完全匹配（2026-08-27 实测）

marker list 可能缺少部分 cluster（如 C24、C27 不在 marker list 中）。处理方式：
- 在数据中存在但 marker list 中缺失的 cluster → 标记为 "Unknown"
- 后续补充 marker 分析后再更新注释

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | hippocampus | aging | 2026-08-27 | annotate_subcluster_alignment.R | - | - |  |
