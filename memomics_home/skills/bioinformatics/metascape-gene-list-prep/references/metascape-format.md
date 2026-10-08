# Metascape Input Format Reference

## 官方要求 (metascape.org)

Metascape 支持两种输入：
1. **Gene List** — 每列一个列表，第1行=列名，下方=基因 symbol
2. **Gene List + 丰度** — gene + expression value 两列

对于 marker/DEG 筛选场景，通常用 **Gene List** 格式。

## 标准格式示例

```csv
cluster1,cluster2,cluster3
GENE_A,GENE_D,GENE_G
GENE_B,GENE_E,GENE_H
GENE_C,GENE_F,GENE_I
```

- 第 1 行 = 列名（自定义，如亚群名、处理组名）
- 第 2 行起 = 基因 symbol（每行一个）
- 列数不限，每列独立富集分析
- 不需要 p-value / log2FC / FDR 列

## 基因 ID 要求

- 默认: **Gene Symbol**（如 TP53, BRCA1）
- 也支持: Ensembl ID, UniProt ID, RefSeq（需在 Metascape 设置中指定）
- 推荐用 Gene Symbol（最广泛支持）

## 常见来源数据格式

| 来源 | 典型列 | 注意事项 |
|------|--------|----------|
| Seurat FindMarkers | gene, avg_log2FC, p_val_adj, cluster | 需先按 cluster 分组 |
| scanpy rank_genes_groups | names, scores, logfoldchanges | 需 transpose |
| DESeq2 results | gene, log2FoldChange, padj | 需 filter padj < 0.05 |
| 手动列表 | gene | 直接导入 |

## 注意事项

- 基因 symbol 必须是官方 symbol（非别名）
- 物种必须一致（人/鼠不能混在同一列）
- 建议每列 ≥10 个基因（太少富集无意义）
- Metascape 免费版每次最多 10 个列表
