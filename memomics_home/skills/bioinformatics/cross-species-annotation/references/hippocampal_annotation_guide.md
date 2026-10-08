# 海马细胞类型注释指南

## 双轴分类体系

海马注释同时使用两条分类轴，混在一起命名：

| 分类轴 | 用于 | 命名示例 |
|--------|------|---------|
| 解剖亚区 (subfield) | 兴奋性神经元 | DG / CA1 / CA2-3 / SUB / EC |
| 细胞谱系 (lineage) | 非神经元 | Oligo / OPC / Astro / Micro / Endo |

## 注释流程

### Step 1: 大群注释 (7-9 大群)

用谱系级 marker 的 ModuleScore / GeneScoreMatrix 打分：

- ExN: SLC17A7, CAMK2A, NEUROD6
- InN: GAD1, GAD2, SLC32A1
- Astro: GFAP, S100B, AQP4, ALDH1L1
- OLG: MBP, PLP1, MOBP
- OPC: PDGFRA, CSPG4, SOX10
- MG: CX3CR1, P2RY12, TMEM119
- EC: FLT1, PECAM1, CLDN5, RGS5

### Step 2: ExN 亚区分注释

| 亚群 | 组合签名 (≥3 个同时高) | 文献来源 |
|------|----------------------|---------|
| DG 颗粒 | PROX1+ NEUROD1+ GABRA4+, CAMK2A 低 | Zemke 2024; Liu 2025 |
| CA1 锥体 | CAMK2A 高+ SORL1+, EGR1 低 | Zemke 2024 |
| CA2-3 锥体 | CAMK2A 高+ EGR1+ NPY1R+ | Zemke 2024 |
| SUB | PRSS8+ GABRA1+, SORL1 低 | Zemke 2024 |
| EC 浅层 | CUX2+ RELN+ | Zemke 2024 |
| EC 深层 | TLE4+ THEMIS+ ADRA1A+ | Zemke 2024 |

### Step 3: InN 亚聚类

- MGE: SST+ / PVALB+ (SST+ LHX6+ NPY+)
- CGE: VIP+ / LAMP5+

## ArchR GeneScoreMatrix 打分

```r
mat <- getMatrixFromProject(proj, useMatrix = "GeneScoreMatrix")
mat <- assays(mat)[[1]]
sigs <- list(
  DG=c("PROX1","NEUROD1","GABRA4"), CA1=c("CAMK2A","SORL1"),
  CA23=c("EGR1","NPY1R","NTS"), Oligo=c("MBP","PLP1","MOBP"),
  OPC=c("PDGFRA","CSPG4","SOX10"), Astro=c("AQP4","S100B","GFAP"),
  Micro=c("CX3CR1","P2RY12","TMEM119"), EC=c("FLT1","PECAM1","CLDN5"))
for (name in names(sigs)) {
  idx <- which(rownames(mat) %in% sigs[[name]])
  if (length(idx) > 0) {
    scores <- colMeans(mat[idx, ])
    proj <- addCellColData(ArchRProj=proj, data=scores, name=paste0("score_",name))
  }
}
```

## 跨物种 predicted annotation

文献中的 predicted annotation = Seurat TransferData 从人类参考迁移标签到猴脑。

## 文献参考

| 文献 | 数据类型 | 物种 | 价值 |
|------|---------|------|------|
| Wang W 2022 Cell Research (PMID:35750757) | snRNA-seq | 猴+人海马 | 13 major cell types |
| Zhang X 2026 Cell | snRNA+snATAC+snmC | 猴脑多区域 | TransferData 预测注释 |
| Yuan J 2024 Cell Genomics (PMID:39631404) | snRNA+snATAC | 人+猴 ACC | 跨物种直接比较 |
| Zemke 2024 bioRxiv (PMID:39463924) | snRNA+snATAC+snmC+HiC | 人海马 40 例 | ATAC 未做独立注释 |
| Liu Z 2025 Cell (PMID:40752494) | scATAC | 人脑多区域 | ATAC 细胞类型注释 |
