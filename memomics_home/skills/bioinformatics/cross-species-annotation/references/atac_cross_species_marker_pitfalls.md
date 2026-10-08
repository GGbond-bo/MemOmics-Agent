# ATAC-seq 跨物种 Marker 比较陷阱与实测数据

## 陷阱 A：非编码 RNA 污染 top marker

ATAC peak-to-gene 注释的 marker 列表中，top30 几乎全是：
- miRNA: MIR517A, MIR519D, MIR188, MIR532, MIR521-2...
- snRNA: SNORD114-27/26/25/24/23/28, SNORD116-26/25...
- 嗅觉受体: OR7A5, OR7A10, OR2T4, OR5B2, OR8J1...
- 角蛋白: KRTAP3-3, KRTAP2-4, KRTAP9-4...

真正的蛋白编码 marker（GAD2/GFAP/CSF1R/LHX6 等）排在 30 名开外。

**必须搜全量基因列表，不限 top N。**

## 陷阱 B：兴奋性神经元亚区域 marker 在 ATAC 下不可分

### 张潇猴脑 Marker → 人类 40 海马 ATAC 全量搜索结果

#### 完全未出现的 marker（在所有 28 个 cluster 中均无）
NEUROD1, PROX1, EGR1, WFS1, SORL1, RELN, THEMIS, CRYM (仅在 C17/18/19 出现), FOXP1, MEIS2, OTX2, WIF1 (仅在 C7/9/10/12/13 出现), TSHZ2, ACTG1, MBP, PLP1, MOG, RGS5, MYH11, TAGLN, LUM

#### 散在多个 cluster 的 marker（无法唯一对应）
- CAMK2A: C14/C15/C16/C17/C18/C19（抑制性+兴奋性混合）
- OPCML: C1/C2/C3/C4/C5/C6（兴奋性+OPC 重叠）
- ADRA1A: C1-C12 全部（非特异）
- FEZF2: C7-C13 多个（非特异）
- FOXG1: C1-C19 几乎所有（非特异）
- GFAP: C1-C12 多个（Ast 标记但非排他性）

#### 高置信对齐的 marker
| Marker | 最强 Cluster | Log2FC | FDR |
|--------|-------------|--------|-----|
| GAD2 | C14 | 1.70 | 5.17e-67 |
| DLX6 | C15 | 2.89 | - |
| DLX1 | C14 | 2.33 | - |
| LHX6 | C15 | 2.15 | 3.36e-47 |
| SST | C15 | 1.52 | 7.02e-17 |
| ADARB2 | C16 | 1.60 | 9.14e-101 |
| GFAP | C8 | 3.50 | 7.17e-112 |
| HSPB8 | C8 | 3.56 | 1.89e-118 |
| SLC1A2 | C9 | 2.36 | 5.52e-113 |
| CSF1R | C22 | 3.18 | 1.25e-88 |
| CX3CR1 | C22 | 3.68 | 5.21e-99 |
| TMEM119 | C22 | 2.07 | 4.77e-41 |
| CXCL10 | C23 | 4.90 | 7.23e-06 |
| OPALIN | C30 | 1.70 | 3.78e-34 |
| CSPG4 | C6 | 2.77 | 1.21e-64 |
| SOX1 | C6 | 2.76 | 1.64e-66 |

## 注释对照表（人类 40 海马 ATAC 28 cluster × 张潇猴脑）

| Human | 注释 | 类型 | 关键 Marker | 猴对标 | 置信度 |
|-------|------|------|------------|--------|--------|
| C1 | DG Ex | 兴奋性 | OPCML/ADRA1A/CSPG4/SOX1 | DG Ex | 中 |
| C2 | DG Ex | 兴奋性 | OPCML/ADRA1A/CSPG4/SOX1 | DG Ex | 中 |
| C3 | OPC/Ex 混合 | OPC | CSPG4/SOX1/OPCML/COL1A1 | OPC | 中 |
| C4 | DG Ex | 兴奋性 | OPCML/ADRA1A/CSPG4/SOX1 | DG Ex | 低 |
| C5 | DG Ex | 兴奋性 | OPCML/ADRA1A/FOXG1 | DG Ex | 中 |
| C6 | OPC | OPC | CSPG4(2.77)/SOX1(2.76) | OPC TSHZ2 | 高 |
| C7 | Ast/Ex 混合 | 混合 | SLC1A2/WIF1/HSPB8/FOXG1 | 混合 | 中 |
| C8 | Ast(GFAP+) | 星形胶质 | GFAP(3.50)/HSPB8(3.56)/EMX2(2.99) | Ast GFAP | 高 |
| C9 | Ast(WIF1+) | 星形胶质 | SLC1A2(2.36)/WIF1(1.89)/GFAP(1.97) | Ast WIF1 | 高 |
| C10 | Ast/OPC 混合 | 混合 | GFAP/SLC1A2/EMX2/WIF1 | Ast | 中 |
| C11 | Ast(GFAP+) | 星形胶质 | GFAP(2.94)/HSPB8(2.75)/SLC1A2(2.04) | Ast GFAP | 高 |
| C12 | Ast/Ex 混合 | 混合 | GFAP/SLC1A2/FEZF2 | 混合 | 中 |
| C13 | Inh/Ex 混合 | 混合 | LHX6(2.23)/PVALB(2.22)/FEZF2(2.72) | MGE Inh/Ex | 中 |
| C14 | MGE-Inh(SST) | 抑制性 | GAD2(1.70)/DLX1(2.33)/DLX6(2.27)/LHX6(1.64) | MGE-SST Inh | 高 |
| C15 | MGE-Inh(PVALB) | 抑制性 | GAD2(1.45)/DLX6(2.89)/DLX1(2.38)/LHX6(2.15)/SST(1.52) | MGE-PVALB Inh | 高 |
| C16 | CGE-Inh | 抑制性 | GAD2(1.41)/DLX6(2.68)/DLX1(2.58)/ADARB2(1.60)/CALB2(1.78) | CGE-CNR1 Inh | 高 |
| C17 | Ex/Inh 混合 | 混合 | CAMK2A(1.60)/NPY1R(1.26)/FEZF2(2.32) | CA2-4 Ex/Inh | 低 |
| C18 | Inh(CGE) | 抑制性 | GABRA4(1.50)/SSTR3(2.29)/CRYM(1.27) | Inh | 中 |
| C19 | Ex/Inh 混合 | 混合 | CAMK2A(1.61)/GABRA4(1.44)/NRGN(2.51) | Ex/Inh | 中 |
| C20 | Microglia(稳态) | 小胶质 | CSF1R(1.43)/CX3CR1(1.60)/CCL3(2.32) | Mic1 | 高 |
| C21 | Endo/Pericyte | 内皮 | CLDN5(2.39)/PECAM1(1.68)/DCN(1.35)/ACTA2(1.57) | Endo/SMC | 高 |
| C22 | Microglia(激活) | 小胶质 | CSF1R(3.18)/CX3CR1(3.68)/TMEM119(2.07)/CD83(2.44) | Mic2 | 高 |
| C23 | Microglia(炎症) | 小胶质 | CSF1R(2.93)/CXCL10(4.90)/CD163(3.79) | Mic3 | 高 |
| C25 | 待定（OR 富集） | 待定 | OR7A5/OR7A10 - 5 peaks | - | 需 QC+特异marker 复核 |
| C26 | ⚠️ 神经元富集（非噪声） | ExN 倾向 | 825/1146 特异 marker（72%），含 GAD2/SLC17A6/FOXP2/CALB1/EOMES + GPC5/CSMD3/NRG1/ROBO2/DCC/EPHA6/RIMS1/CNTN4 | 待定 | 需重聚类/Ambig |
| C28 | 待定（低 marker 数） | 待定 | HMX2 - 3 peaks | - | 需 QC 复核 |
| C29 | 待定（低 marker 数） | 待定 | LOC284412 - 1 peak | - | 需 QC 复核 |
| C30 | ODC(OPALIN+) | 少突 | OPALIN(1.70) | ODC1/2 | 高 |

## 核心结论

1. **ATAC 跨物种可对齐**：非神经元 (Ast/ODC/Mic/Endo) + 抑制性神经元 (Inh) → marker 跨物种有效
2. **ATAC 跨物种不可对齐**：兴奋性神经元亚区域 (DG/CA1/CA2-4/EC) → 需要 RNA 数据
3. **搜索必须全量**：top30 被非编码 RNA 污染，蛋白编码 marker 排不上名
4. **marker 重叠需警惕**：OPCML/ADRA1A/CSPG4/SOX1 同时标记 ExN 和 OPC，需多 marker 组合判断
5. **⚠️ 噪声判定必须三查（2026-08-27）**：① QC（TSS/nFrags/DoubletScore，TSS 高=不是垃圾）② marker 特异性（特异 vs 共享背景占比）③ 特异 marker 生物学构成（C26 的 72% 特异 marker 含真实神经元基因）。**大细胞量+高 TSS+高特异占比 = 亚分离真实 cluster，不是噪声**；正确处理 = 提高分辨率重聚类 或 标 "Ambig" + 下游排除，仅 QC 明确差才剔除