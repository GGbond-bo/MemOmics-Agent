# 跨物种细胞类型注释方法详解

## Seurat TransferData 跨物种流程

```r
library(Seurat)

# 1. 跨物种基因同源映射（关键步骤）
# 人→猴：用基因同源表（HomoloGene或BioMart）
human_to_macaque <- read.csv("human_macaque_homologs.csv")
# 格式: human_gene, macaque_gene

# 2. 准备参考（人类，已注释）
# 确保参考数据集有 cell_type 列

# 3. 准备查询（猴脑，未注释）
# 确保查询数据集与参考使用相同基因名

# 4. 找锚点
anchors <- FindTransferAnchors(
  reference = human_seurat,
  query = macaque_seurat,
  dims = 1:30,
  reference.reduction = "pca"
)

# 5. 预测标签
predictions <- TransferData(
  anchorset = anchors,
  refdata = human_seurat$cell_type,
  dims = 1:30
)

# 6. 添加到元数据
macaque_seurat$predicted_anno <- predictions$predicted.id
macaque_seurat$prediction_score <- predictions$prediction.score.max
```

## 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 基因名不匹配 | 人和猴基因名不同 | 用同源映射表转换 |
| 预测置信度低 | 参考和查询差异大 | 增加参考数据量、调整dims |
| 细胞类型缺失 | 参考没有该类型 | 手动验证+marker基因确认 |
| 批次效应干扰 | 跨物种技术差异 | 先做Harmony整合再预测 |

## 参考文献

- Stuart et al., 2019, Cell (Seurat v3 TransferData)
- Hao et al., 2023, Cell (Seurat v5)
- Aran et al., 2019, Nat Biotechnol (SingleR)
- Guo et al., 2026, Nat Commun (CAMEX)
