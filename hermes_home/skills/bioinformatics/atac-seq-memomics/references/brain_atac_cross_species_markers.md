# 脑ATAC-seq跨物种细胞类型Marker（文献支持版）

> 来源：2026-08-25 文献搜索整理，用于人海马+猴脑ATAC-seq跨物种细胞类型注释。
> 所有marker均附文献PMID/DOI，可直接用于ArchR Gene Activity Score scoring。

## 核心参考文献

| # | 文献 | 期刊/年份 | 价值 |
|---|------|----------|------|
| [1] | Zhang X et al. "Multimodal brain cell atlas across the adult macaque lifespan" | Cell, 2026 (PMID: 42612631) | 猴脑多模态图谱（scRNA+snATAC+snmC），有详细细胞类型注释 |
| [2] | Yuan J et al. "Single-nucleus multi-omics analyses reveal cellular and molecular innovations in the anterior cingulate cortex during primate evolution" | Cell Genomics, 2024 (PMID: 39631404) | 人+猴ACC多组学（snRNA+snATAC），跨物种细胞类型直接比较 |
| [3] | Zemke NR et al. "Epigenetic and 3D genome reprogramming during the aging of human hippocampus" | bioRxiv, 2024 (PMID: 39463924) | 40个人海马 snRNA+snATAC+snmC+HiC |
| [4] | Zhang J et al. "Single-cell spatiotemporal transcriptomic and chromatin accessibility profiling in developing postnatal human and macaque prefrontal cortex" | Nat Neurosci, 2026 (PMID: 41381947) | 人+猴PFC snRNA+snATAC发育图谱 |
| [5] | Liu Z et al. "Single-cell multiregion epigenomic rewiring in Alzheimer's disease progression and cognitive resilience" | Cell, 2025 (PMID: 40752494) | 人脑多区域scATAC（含海马） |
| [6] | Kabbe M et al. "Single-nucleus epigenomic profiling of the adult human central nervous system" | Nat Neurosci, 2026 (PMID: 41857393) | 人CNS表观基因组图谱 |

## 7大群 + 亚群Marker

### 1. 兴奋性神经元 (ExN)

| Marker | 文献 |
|--------|------|
| SLC17A7 (VGLUT1) | [2][3][6] |
| CAMK2A | [3][5] |
| NEUROD6 | [1][4] |

亚群：DG(PROX1,NEUROD1) / CA1(CAMK2A,SORL1) / CA3(CAMK2A,EGR1) / EC浅层(CUX2,RELN) / EC深层(TLE4,THEMIS)

### 2. 抑制性神经元 (InN)

| Marker | 文献 |
|--------|------|
| GAD1 | [2][3][6] |
| GAD2 | [2] |
| SLC32A1 (VGAT) | [5][6] |
| SST | [2][4] |
| PVALB | [2][1] |
| VIP | [2][6] |

### 3. 星形胶质细胞 (Ast)

| Marker | 文献 |
|--------|------|
| GFAP | [1][2][3] |
| S100B | [1][5] |
| AQP4 | [1][2] |
| ALDH1L1 | [3][6] |
| SLC1A3 (EAAT1) | [5][6] |

### 4. 少突胶质细胞 (OLG)

| Marker | 文献 |
|--------|------|
| MBP | [1][2][3] |
| PLP1 | [1][5] |
| MOBP | [2][6] |
| OLIG2 | [4][5] |

### 5. OPC

| Marker | 文献 |
|--------|------|
| PDGFRA | [2][5][6] |
| CSPG4 (NG2) | [2][4] |
| SOX10 | [2][6] |

### 6. 小胶质细胞 (MG)

| Marker | 文献 |
|--------|------|
| CX3CR1 | [1][2][5] |
| P2RY12 | [3][6] |
| TMEM119 | [2][5] |
| AIF1 (Iba1) | [1] |

### 7. 内皮+周细胞 (EC+PC)

| Marker | 细胞类型 | 文献 |
|--------|---------|------|
| FLT1 | EC | [2][6] |
| PECAM1 | EC | [1][5] |
| CLDN5 | EC | [2][3] |
| RGS5 | PC | [1][2] |
| PDGFRB | PC | [2][5] |

## 人猴共有核心Marker

| 大群 | 共有核心Marker |
|------|--------------|
| ExN | SLC17A7, CAMK2A |
| InN | GAD1, GAD2, SLC32A1 |
| Ast | GFAP, S100B, AQP4 |
| OLG | MBP, PLP1, MOBP |
| OPC | PDGFRA, CSPG4, SOX10 |
| MG | CX3CR1, P2RY12, TMEM119 |
| EC | FLT1, PECAM1, CLDN5 |

## ATAC注释方法

1. ArchR `addGeneScoreMatrix()` 计算gene activity score
2. `AddModuleScore()` 对上述marker打分
3. 每个cluster取高分marker判断细胞类型
4. 跨物种：用共有核心marker做初步注释，各物种特有marker做精细亚群鉴定

⚠️ ATAC gene activity score反映染色质可及性，与RNA不完全一致。某些RNA marker在ATAC中可及性较低（如P2RY12），需结合peak可及性判断。
