# 人猴脑海马细胞类型 Marker 参考

> 来源：2026-08-25 会话，综合 Franjic 2022 Neuron, Zhang Xiao 2026 Cell, Zemke 2024 bioRxiv

## 1. 大群 Marker（ModuleScore 打分用）

```
sigs <- list(
  ExN    = c("SLC17A7","CAMK2A","NEUROD6"),
  InN    = c("GAD1","GAD2","SLC32A1"),
  Ast    = c("GFAP","S100B","AQP4","ALDH1L1"),
  OLG    = c("MBP","PLP1","MOBP"),
  OPC    = c("PDGFRA","CSPG4","SOX10"),
  MG     = c("CX3CR1","P2RY12","TMEM119"),
  EC     = c("FLT1","PECAM1","CLDN5","RGS5")
)
```

## 2. 海马亚群 Marker（亚区级别）

兴奋性神经元按解剖亚区分，非神经元按细胞谱系分。

```
sigs <- list(
  DG     = c("PROX1","NEUROD1","GABRA4"),
  CA1    = c("CAMK2A","SORL1"),
  CA23   = c("EGR1","NPY1R","NTS"),
  SUB    = c("PRSS8","GABRA1"),
  Oligo  = c("MBP","PLP1","MOBP"),
  OPC    = c("PDGFRA","CSPG4","SOX10"),
  Astro  = c("AQP4","S100B","GFAP"),
  Micro  = c("CX3CR1","P2RY12","TMEM119"),
  Endo   = c("FLT1","PECAM1","CLDN5")
)
```

## 3. ArchR 中 ModuleScore 的正确计算

AddModuleScore() 和 addScoreGeneset() 在 ArchR 中不存在。必须手动计算：

```
mat <- getMatrixFromProject(proj, useMatrix = "GeneScoreMatrix")
mat <- assays(mat)[[1]]
for (name in names(sigs)) {
  idx <- which(rownames(mat) %in% sigs[[name]])
  if (length(idx) > 0) {
    scores <- colMeans(mat[idx, ])
    proj <- addCellColData(ArchRProj = proj, data = scores, name = paste0("score_", name))
  }
}
```

## 4. 文章对照表

| 文章 | 数据类型 | 海马ATAC | 注释粒度 |
|------|---------|---------|---------|
| Zhang Xiao 2026 Cell | snRNA + snATAC + snmC | Yes | 15+ 亚群 |
| Zemke 2024 bioRxiv | snRNA + snATAC + snmC + HiC | Yes | 7 大类（无细分） |
| Wang 2022 Cell Research | snRNA only | No | 13 大类 |

## 5. Zhang Xiao 2026 猴脑注释命名规则

- ExN 按脑区亚层：DG Ex / CA1 / CA2-4 / EC L2 / EC L3-5 / EC L6
- InN 按发育起源+marker：MGE SST / MGE PVALB / CGE CNR1 / CGE LAMP5
- 非神经元直接写：ODC / OPC / Astrocyte / Microglia / VS
- 注释方法：canonical markers + 手动注释（不是 TransferData 预测）
