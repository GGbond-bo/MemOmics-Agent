# 人+猴海马细胞类型注释参考

## 文献来源
- Zhang Xiao 2026 Cell: 猴脑多模态图谱（snRNA+snATAC），海马注释用 canonical markers 手动注释
- Zemke 2024 bioRxiv (PMID: 39463924): 40人海马 snRNA+snATAC+snmC+HiC，ATAC 未做细胞注释
- Wang 2022 Cell Research (PMID: 35750757): 猴+人海马 snRNA-seq（无 ATAC）
- Franjic 2022 Neuron: 人海马 snRNA-seq 详细亚群注释

## ⚠️ 关键发现

### ATAC marker "在好几个亚群高表达"是正常的
- **谱系级 marker**（SLC17A7/GAD1/GFAP）在所有同大类亚群都高 → 这是正确的大群 marker
- **亚区级 marker**（PROX1/EGR1/CAMK2A）只在特定亚区高 → 这是亚群 marker
- **ATAC GeneScore 比 RNA 更宽泛**：染色质开放 ≠ 基因表达，启动子/增强子可能在相关细胞类型都开放
- **解决**：先用谱系级 marker 分大群（ModuleScore），再在大群内用亚区级 marker 细分

### Zhang Xiao 2026 的注释方法是"手动 canonical marker + 人工审核"
**不是** TransferData 预测。原文 Methods：
> "Cell clusters were identified and annotated based on canonical cell markers and reviewed manually."
> "The resulting cell clusters were annotated using the same markers of the snRNA-seq dataset."

### 命名规则：两条分类轴混搭
| 分类轴 | 用于 | 命名 | 例子 |
|--------|------|------|------|
| 脑区亚层 | 兴奋性神经元 | DG / CA1 / CA2-3 / EC L2 / EC L3-5 / EC L6 / SUB | 功能+连接完全不同 |
| 发育起源 | 抑制性神经元 | MGE SST / MGE PVALB / CGE CNR1 / CGE LAMP5 | MGE/CGE 来源 |
| 细胞谱系 | 非神经元 | ODC / OPC / Astrocyte / Microglia | 没有"亚区"概念 |

---

## 谱系级 Marker（分 7-9 大群）

```r
sigs <- list(
  ExN    = c("SLC17A7","CAMK2A","NEUROD6"),
  InN    = c("GAD1","GAD2","SLC32A1"),
  Astro  = c("GFAP","S100B","AQP4","ALDH1L1"),
  Oligo  = c("MBP","PLP1","MOBP"),
  OPC    = c("PDGFRA","CSPG4","SOX10"),
  Micro  = c("CX3CR1","P2RY12","TMEM119"),
  Endo   = c("FLT1","PECAM1","CLDN5","RGS5")
)
```

## 亚区级 Marker（细分兴奋性/抑制性神经元）

### 兴奋性神经元亚区
| 亚群 | 组合签名 | 特征 |
|------|---------|------|
| **DG 颗粒细胞** | PROX1+, NEUROD1+, GABRA4+, CAMK2A低 | 独立于 CA 区 |
| **CA1 锥体** | CAMK2A高, SORL1+, EGR1低 | 海马最大亚群 |
| **CA2-3 锥体** | CAMK2A高, EGR1+, NPY1R+, NTS+, OPCML+ | CA2 和 CA3 常合并 |
| **EC 浅层 (L2)** | CUX2+, RELN+ | 内嗅皮层 |
| **EC 深层 (L3-5)** | TLE4+, THEMIS+, ADRA1A+ | |
| **EC L6** | TLE4+, 其他层 marker | |
| **Subiculum (SUB)** | SORL1低, GABRA1+, PRSS8+ | 海马输出区 |

### 抑制性神经元亚型
| 亚群 | 组合签名 | 发育起源 |
|------|---------|---------|
| **SST+ InN** | SST+, LHX6+, NPY+ | MGE |
| **PVALB+ InN** | PVALB+, SST共表达+ | MGE |
| **VIP+ InN** | VIP+, LHX6+ | CGE |
| **LAMP5+ InN** | LAMP5+, CNR1+ | CGE (灵长类扩增) |

### 非神经元（直接用谱系名）
| 细胞类型 | RNA marker | ATAC GeneScore 备选 marker（RNA marker 缺失时用） |
|---------|-----------|-----------------------------------------------|
| Astrocyte | AQP4, S100B, GFAP | ALDH1L1, GFAP（ATAC 中通常可用） |
| Oligodendrocyte (ODC) | MBP, PLP1, MOBP | **GPC5, CSMD3, CCSER1, NRG1, ROBO2**（MBP/PLP1 可能在 ATAC 不出现，不代表 oligo 缺失） |
| OPC | PDGFRA, CSPG4, SOX10 | CSPG4（ATAC 中可用），PDGFRA/SOX10 可能弱 |
| Microglia | CX3CR1, P2RY12, TMEM119 | **CX3CR1, TNFRSF1B, SRGN, INPP5D**（见下方亚型） |
| Endothelial | FLT1, PECAM1, CLDN5 | FLT1, PECAM1 |
| Pericyte | RGS5, PDGFRB | RGS5 |
| Choroid Plexus | TTR, FOLR1 | TTR |
| Ependymal | FOXJ1, CFAP126 | FOXJ1 |

> ⚠️ **ATAC marker ≠ RNA marker**：GeneScoreMatrix 反映染色质可及性，不等于基因表达。PLP1/MBP 在 RNA 中是 oligo 强 marker，但在 ATAC GeneScore 中可能不出现——此时用 GPC5/CSMD3 等替代 marker 判断。**不要因 RNA marker 缺失就判定该细胞类型不存在。**

### Microglia 亚型（ATAC 可区分）

| 亚型 | ATAC marker | 特征 | 生物学意义 |
|------|------------|------|-----------|
| **Homeostatic** | CX3CR1, SRGN, INPP5D, TAL1 | 稳态小胶质 | 正常脑功能维持 |
| **DAM-like（活化态）** | CD163, FPR1, FPR3, IRF8, PIK3R5 | 清道夫受体+甲酰肽受体高 | 疾病相关/炎症状态 |

- 两个 microglia 群同时存在说明组织中有部分细胞处于活化状态
- CD163 通常被认为是外周巨噬细胞 marker，但在脑内 DAM（disease-associated microglia）中也上调
- **判断依据**：两个群共享 TNFRSF1B（microglia 共 marker），但活化态额外表达 CD163/FPR1/3

---

## 人猴对齐表

| Zhang Xiao 2026 猴 | 对应 | Zemke 2024 人 |
|-------------------|------|--------------|
| DG Ex / CA1 / CA2-4 / EC L2-6 / SUB | → | Excitatory neurons（未细分） |
| MGE SST / MGE PVALB / CGE CNR1 / CGE LAMP5 | → | Inhibitory interneurons（未细分） |
| Astrocyte | ✅ | Astrocytes |
| ODC | ✅ | Oligodendrocytes |
| OPC | ✅ | OPCs |
| Microglia | ✅ | Microglia |
| Choroid Plexus | ❌ 人缺失 | — |
| Ependymal | ❌ 人缺失 | — |
| VS | ❌ 人缺失 | — |

**注**：40人文章 ATAC 未做细胞注释，需用 snRNA (GSE278576) + TransferData 细分到和猴一样的亚群粒度。
