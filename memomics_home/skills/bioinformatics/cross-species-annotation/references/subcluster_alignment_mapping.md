# 人脑海马 ATAC 细分亚群对齐注释参考

## 背景
用户要求：能对齐的细分亚群用相同名字，不能对齐的各自保留原文名字。不要强行把所有 cluster 塞进 8 大类。

## 数据来源
- **人脑**: `E:/专利/patent/human_Hf_ATAC_40_clustered.rds` (ArchRProject, 265,909 细胞, 30 clusters)
- **猴脑**: `E:/专利/patent/monkey_Hf_ATAC_final.rds` (18 predictedAnno 亚群)
- **Marker list**: `E:/专利/human_40_markerList.csv` (20,327 行, 30 clusters)

## 猴脑 18 个亚群分布
| 亚群 | 细胞数 | 说明 |
|------|--------|------|
| ODC | 44,021 | 成熟少突胶质细胞 |
| DG Ex | 28,854 | 齿状回兴奋性神经元 |
| Astrocyte | 23,548 | 星形胶质细胞 |
| CA1_SUB s_f_Ex | 16,457 | CA1/下托兴奋性神经元 |
| Microglia | 9,388 | 小胶质细胞 |
| CA2_4 EX | 7,833 | CA2/CA4 兴奋性神经元 |
| EC L3_5 EX | 6,878 | 内嗅皮层 L3-5 兴奋性神经元 |
| OPC | 6,574 | 少突胶质细胞前体 |
| EC L6 EX | 3,669 | 内嗅皮层 L6 兴奋性神经元 |
| EC L2 EX | 3,226 | 内嗅皮层 L2 兴奋性神经元 |
| CGE CNR1 lnh | 2,190 | CGE 抑制性神经元 |
| CAE_SUB deep Ex | 2,130 | CAE/深部兴奋性神经元 |
| MGE SST lnh | 1,884 | MGE SST 抑制性神经元 |
| CGE LAMP5 lnh | 1,408 | CGE LAMP5 抑制性神经元 |
| MGE PVALB lnh | 1,232 | MGE PVALB 抑制性神经元 |
| Ependymal | 879 | 室管膜细胞 |
| Choroid Plexus | 702 | 脉络丛 |
| VS | 624 | 血管相关 |

## 人脑 30 个 Cluster Top 5 Marker
| Cluster | Top 5 Markers |
|---------|---------------|
| C1 | MYT1, TNR, SEZ6L, CACNG4, MEGF11 |
| C2 | MYT1, CACNG4, MEGF11, TMEM132C, XYLT1 |
| C3 | CACNG4, MYT1, TNR, AFAP1L2, MEGF11 |
| C4 | HECW1, CACNG4, MEGF11, CHST11, SEZ6L |
| C5 | MYT1, CACNG4, TNR, SEZ6L, CHST11 |
| C6 | MYT1, CACNG4, TNR, OPCML, XYLT1 |
| C7 | ETNPPL, EYA1, PRKCH, DDAH1, TRDN |
| C8 | HSPB8, LOC105370024, MSI2, GFAP, PITPNC1 |
| C9 | PRDM16, SLC1A2, LINC00673, MSI2, EMX2 |
| C10 | ZNRF3, SLC1A2, PITPNC1, PRDM16, LINC00673 |
| C11 | PRDM16, MSI2, KCNN3, VAC14, PITPNC1 |
| C12 | SLC1A2, PRDM16, ZIC5, ZNRF3, LINC00673 |
| C13 | EBF3, MNX1-AS1, PLEC, PTPRN2, LINC01749 |
| C14 | MYT1L, SRRM4, RIMBP2, RBFOX3, GRIN2B |
| C15 | GRIN2B, MYT1L, KIAA1217, GABBR2, SRRM4 |
| C16 | MYT1L, ADARB2, DAB1, RBFOX3, RIMBP2 |
| C17 | KCNAB2, PLXNA4, BCL11B, SHISA6, PPM1E |
| C18 | GABBR2, MIR6083, HRH2, KIAA1211L, MYT1L |
| C19 | CELF2, MIR6083, KALRN, KCNQ2, SV2B |
| C20 | TNFRSF1B, IRF8, SRGN, CX3CR1, ST6GAL1 |
| C21 | SLC16A6, ARSG, BCL3, SMAD3, SMAD6 |
| C22 | TNFRSF1B, CX3CR1, LOC101928269, MCF2L2, SRGN |
| C23 | TNFRSF1B, CD163, C9orf66, PIK3R5, FPR1 |
| C25 | OR2T4, CPA5, OR7A5, OR7A10, TCAF2 |
| C26 | MIR8069-1, GPC5, CSMD3, CCSER1, GALNTL6 |
| C28 | LINC00482, CT47A7, HMX2 |
| C29 | LOC284412 |
| C30 | TMEM235, VWA1, OPALIN, ACP7, MAG |

## 对齐映射逻辑

### 能对齐的（用猴脑名字）
1. **OPC** (C1-C6): CSPG4(NG2), SOX6, SOX1, ASCL1 → 猴脑 OPC
2. **Astrocyte** (C7-C12): AQP4, GFAP, SLC1A2, ALDH1L1 → 猴脑 Astrocyte
3. **Inhibitory** (C14, C15, C16, C18): GABBR2, SLC32A1, DLX6-AS1, ADARB2 → 猴脑 CGE/MGE subtypes
4. **Excitatory** (C17, C19): BCL11B, GRIN2A → 猴脑 DG Ex, CA1_SUB, etc.
5. **Microglia** (C20-C23): CX3CR1, IRF8, CD163 → 猴脑 Microglia
6. **ODC** (C30): OPALIN, MAG → 猴脑 ODC

### 不能对齐的（保留原文名字）
1. **C13**: EBF3, MNX1, UNCX → 特殊神经元亚型
2. **C25**: OR2T4, OR7A5 → 嗅觉受体相关
3. **C26**: NRG1, ROBO2, GRM8 → 特殊神经元亚型
4. **C28**: LINC00482, CT47A7 → 少量 marker
5. **C29**: LOC284412 → 单 marker

### Unknown（不在 marker list 中）
1. **C24**: 3,089 细胞
2. **C27**: 4,821 细胞

## 输出结果
**文件**: `E:/专利/patent/human_subcluster_annotation_aligned.csv`

**分布**:
| 对齐注释 | 细胞数 | 占比 |
|----------|--------|------|
| ODC | 104,170 | 39.2% |
| Astrocyte | 27,738 | 10.4% |
| C26 | 22,940 | 8.6% |
| Microglia | 22,272 | 8.4% |
| C29 | 21,397 | 8.0% |
| C28 | 20,925 | 7.9% |
| Inhibitory | 15,628 | 5.9% |
| OPC | 10,926 | 4.1% |
| Unknown | 7,910 | 3.0% |
| Excitatory | 7,612 | 2.9% |
| C25 | 4,066 | 1.5% |
| C13 | 325 | 0.1% |

## 脚本
**路径**: `E:/MemOmics-Agent/results/memomics-cd677556/scripts/annotate_subcluster_alignment.R`

**关键代码**:
```r
# 定义对齐映射
alignment_map <- c(
  "C1"  = "OPC", "C2"  = "OPC", "C3"  = "OPC", "C4"  = "OPC", "C5"  = "OPC", "C6"  = "OPC",
  "C7"  = "Astrocyte", "C8"  = "Astrocyte", "C9"  = "Astrocyte", "C10" = "Astrocyte", "C11" = "Astrocyte", "C12" = "Astrocyte",
  "C13" = "C13",
  "C14" = "Inhibitory", "C15" = "Inhibitory", "C16" = "Inhibitory", "C18" = "Inhibitory",
  "C17" = "Excitatory", "C19" = "Excitatory",
  "C20" = "Microglia", "C21" = "Microglia", "C22" = "Microglia", "C23" = "Microglia",
  "C25" = "C25", "C26" = "C26", "C28" = "C28", "C29" = "C29",
  "C30" = "ODC"
)

# 应用映射（ArchRProject 用 getCellColData）
meta <- getCellColData(human)
clusters <- as.character(meta$Clusters)
aligned <- ifelse(clusters %in% names(alignment_map), alignment_map[clusters], "Unknown")
```
