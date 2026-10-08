# 人脑海马 ATAC 28 亚群最终注释（对齐猴脑 19 亚群命名，2026-08-28 定稿）

来源：`E:/专利/human_40_markerList.csv`（getMarkerFeatures 输出，**实际 28 个 cluster，C24/C27 不存在**）
参考：猴脑 `monkey_Hf_ATAC_final.rds` predictedAnno + 张潇原稿
产出：`task4/human_subcluster_annotation_final.csv` + `task4/scripts/annotate_subcluster_alignment.py`

## 最终注释表

| human_cluster | annotation | align_status | evidence_markers |
|---|---|---|---|
| C1 | OPC | ✅ 对齐 OPC1/2 | CSPG4, PDGFRA, MYT1, SOX6, SOX1, ASCL1, DLL3 |
| C2 | OPC | ✅ 对齐 OPC1/2 | CSPG4, PDGFRA, MYT1, SOX6, DLL3, CHAD |
| C3 | OPC | ✅ 对齐 OPC1/2 | CSPG4, MYT1, SOX1, ASCL1, PDGFRA |
| C4 | OPC | ✅ 对齐 OPC1/2 | CSPG4, MYT1, ASCL1, DLL3, GSX1, LCE1D |
| C5 | OPC | ✅ 对齐 OPC1/2 | CSPG4, MYT1, SOX6, ASCL1, DLL3 |
| C6 | OPC | ✅ 对齐 OPC1/2 | CSPG4, MYT1, SOX1, ASCL1, SOX6 |
| C7 | Astrocyte | ✅ 对齐 Ast1/2/3 | AQP4, SLC1A2, GJA1, EDNRB, FOXG1 |
| C8 | Astrocyte | ✅ 对齐 Ast1/2/3 | GFAP, AQP4, SLC1A2, ALDH1L1, EMX2, PAX6 |
| C9 | Astrocyte | ✅ 对齐 Ast1/2/3 | GFAP, AQP4, SLC1A2, ALDH1L1, EMX2, LHX2, ZIC5, CXCL14 |
| C10 | Astrocyte | ✅ 对齐 Ast1/2/3 | GFAP, AQP4, SLC1A2, ALDH1L1, EMX2, LHX2, CXCL14 |
| C11 | Astrocyte | ✅ 对齐 Ast1/2/3 | GFAP, AQP4, SLC1A2, ALDH1L1, EMX2 |
| C12 | Astrocyte | ✅ 对齐 Ast1/2/3 | GFAP, AQP4, SLC1A2, ALDH1L1, EMX2, ZIC5, FEZF2 |
| C13 | C13 (伪影?) | ❌ 保留原文 | HOXD11/MNX1/HOXB5(HOX cluster)+GRM6(视网膜ON bipolar)+KRTAP → 疑似双联体/伪影 |
| C14 | MGE SST Inh | ✅ 对齐 MGE SST | DLX1, DLX6, SLC32A1, GAD1, SST, SNCB, SRRM4 (SST 命中) |
| C15 | MGE PVALB Inh | ✅ 对齐 MGE PVALB | DLX1, DLX6, LHX6, SLC32A1, GAD1, PVALB, SNCB, CDK5R2 |
| C16 | CGE Inh | ✅ 对齐 CGE CNR1/LAMP5 | DLX1, DLX6, GAD1, SLC32A1, SNCB, GJD2, ADARB2 类 |
| C17 | CTX-deep Ex | 人脑独有 (marker命名) | SLC17A7(2.26), FEZF2(2.32), BCL11B(2.17), EGR4, CDK5R2, ICAM5 → FEZF2/BCL11B 双 marker 深皮层证据较强 |
| C18 | CA1/SUB-like Ex* | 人脑独有 (marker命名) | SSTR3(2.29), NEUROD6, GSG1L2, GABRA4(1.50), SATB2(1.46), INA → WFS1/SORL1 未命中→候选级 |
| C19 | CA1-like Ex* | 人脑独有 (marker命名) | NRGN, SSTR3(2.34), HRH2, CDK5R2, SLC17A7(1.83), CAMK2A(1.61), GABRA4(1.44) → WFS1/SORL1 未命中→候选级 |
| C20 | Microglia | ✅ 对齐 Mic1 | CX3CR1, P2RY12, P2RY13, C1QB, ABI3, IRF8 |
| C21 | Macrophage | ✅ 对齐 Macrophage | CCL18, CCL3, CCL23, CCL5, CCL11, ICAM2, FOXC2 (血管相关巨噬；由 VS 修正) |
| C22 | Microglia | ✅ 对齐 Mic2 | CX3CR1, P2RY12, P2RY13, TMEM119, TYROBP, ABI3, IRF8, CD83 类 |
| C23 | Microglia_activated | ✅ 对齐 Mic3 | CXCL10, CLEC5A, S100A8, CD163, CASP1, FPR2, CCL11 (活化) |
| C25 | C25 (噪声) | ❌ 保留原文 | 仅5个marker，全为 OR 嗅觉受体 (OR7A5/OR2T4/TCAF2) → 技术噪声 |
| C26 | C26 (噪声) | ❌ 保留原文 | TAS2R9(味觉)+IFNA10+OR基因+AMY2A(唾液) → 多组织污染/噪声 |
| C28 | C28 (低置信) | ❌ 保留原文 | 仅3个marker (HMX2, LINC00482, CT47A7) → 低置信 |
| C29 | C29 (低置信) | ❌ 保留原文 | 仅1个marker (LOC284412) → 低置信 |
| C30 | ODC | ✅ 对齐 ODC1/2 | OPALIN, MAG, KLK6, MCAM, TMEM31, VWA1 |

## 统计
- 对齐猴脑：**18 群**（OPC×6 + Astro×6 + ODC + MGE×2 + CGE + Micro×2 + Macrophage）
- 人脑独有 ExN（marker 命名）：**3 群**（C17/C18/C19）
- 低置信/噪声/伪影（保留原文）：**5 群**（C13/C25/C26/C28/C29）
- 缺失：C24/C27（marker list 中不存在，勿追）

## ExN 命名区域 marker 核查（辩论后补充验证）
- C17: WFS1/SORL1/GRIK1/NR4A2/CUX2/PROX1/NEUROD1 全部未命中 → 但 FEZF2(2.32)+BCL11B(2.17) 双 marker → CTX-deep Ex（不标 *）
- C18: 仅 SATB2(1.46) 命中，WFS1/SORL1 未命中 → CA1/SUB-like Ex*
- C19: 仅 SATB2(1.34, rank 119) 命中，WFS1/SORL1 未命中 → CA1-like Ex*
- L1 辩论裁决：need_more_info / low → 候选级命名（like + *），不硬下结论