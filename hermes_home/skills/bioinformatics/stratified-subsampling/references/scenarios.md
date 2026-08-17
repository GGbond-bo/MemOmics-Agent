# 分层抽样 — 3种场景详解

## 场景1: 分层降采样

**目的**: 每个sample取相同数量细胞，避免大样本主导下游分析。

**适用**: 多样本聚类、DEG、细胞组成分析前。

**算法**:
```
for each sample:
  if n_cells > N:
    randomly pick N cells
  else:
    keep all cells (or drop sample if too few)
merge all picked cells
```

**注意事项**:
- N应≤最小样本的细胞数，保证所有样本都有代表
- 降采样后不要重新聚类，聚类结果可能不稳定
- 可用Seurat的`subset`或Python的`anndata[].copy()`

## 场景2: 分层训练/测试拆分

**目的**: 按sample分层拆分，确保每个样本细胞同时出现在训练集和测试集。

**适用**: 机器学习分类器训练、标记转移评估。

**算法**:
```
for each sample:
  shuffle cells
  split into train (ratio) and test (1-ratio)
merge all train cells → train set
merge all test cells → test set
```

**注意事项**:
- train_ratio一般0.7-0.8
- 确保每个样本在训练集和测试集中都有足够的细胞
- 小样本（<20 cells）考虑全放训练集

## 场景3: 分层可视化抽样

**目的**: 每个sample随机抽N个细胞画UMAP，避免overplotting。

**适用**: 大样本多时UMAP看不清小样本分布。

**算法**:
```
for each sample:
  n_pick = min(N, n_cells_in_sample)
  randomly pick n_pick cells
merge all picked cells → subsampled Seurat
plot UMAP with existing coordinates
```

**注意事项**:
- UMAP必须在抽样前已计算好，不能抽样后重新算
- N建议200-500，平衡覆盖度和可读性
- 最小样本全取，不做drop
- 抽样后对象仅用于可视化，不用于下游分析

## 已验证案例

| 日期 | 物种 | 组织 | 场景 | 原始细胞 | 抽样后 | N | 样本数 |
|------|------|------|------|----------|--------|---|--------|
| 2026-07-03 | human | skeletal_muscle | 场景3 | 29,988 | 4,437 | 200 | 24 |