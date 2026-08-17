---
name: scrna-eda
description: "分析前自动数据探索——细胞/基因数、稀疏度、批次分布、表达分布、高变基因预览。生成 EDA 诊断报告，推荐 QC 阈值。"
when_to_use: "[scrna-eda] 有 h5ad 数据但还没做 QC，或用户说'看看数据'/'数据长什么样'/'数据探索'/'概览'时触发"
version: 1.0.0
category: scRNA
hermes:
  tags: [eda, exploration, data-quality, metadata, 数据探索]
  trigger_level: RED
  keywords: "eda / 数据探索 / 看看数据 / 概览 / data exploration / 数据概览"
---

# 🔍 scRNA-seq 数据探索 (EDA)

> 在任何 scRNA 分析前，快速检查数据质量、分布特征、潜在问题。
> 输出诊断报告 + QC 阈值推荐。

---

## ⛔ MemOmics 强制规则

1. **先 EDA 再 QC**：有 h5ad → 必须先 EDA，不跳过
2. **不做修改**：EDA 只读数据，不做任何过滤/修改
3. **输出报告**：结果写入 `results/{session}/eda/eda_report.md`

---

## Step 1: 加载数据

```python
import anndata, scanpy as sc
adata = anndata.read_h5ad(data_path)
print(f"Cells: {adata.n_obs}, Genes: {adata.n_vars}")
```

## Step 2: 基本统计

| 指标 | 检查项 |
|------|--------|
| 细胞数 | < 500 可能不可靠，> 100K 注意内存 |
| 基因数 | < 2000 可能低质量数据 |
| 稀疏度 | > 95% 稀疏 → 考虑保留更多基因 |
| 线粒体% | > 20% → 死细胞多，需过滤 |
| 核糖体% | > 40% → 可能技术噪音 |

```python
# 检测已归一化的数据
from scipy.sparse import issparse
X = adata.X
if issparse(X):
    print(f"Sparsity: {X.nnz / (X.shape[0] * X.shape[1]) * 100:.1f}%")
```

## Step 3: 批次分布

```python
# 检查 batch/sample 分布
for col in ['sample', 'batch', 'Sample', 'Batch', 'samplename']:
    if col in adata.obs.columns:
        counts = adata.obs[col].value_counts()
        print(f"\n{col} distribution:")
        print(counts.to_string())
        # 如果某个 batch 细胞数 < 100 → 警告
        if counts.min() < 100:
            print(f"⚠️  Small batch detected: min={counts.min()}")
```

## Step 4: 表达分布

```python
# Count depth 分布
import numpy as np
counts_per_cell = np.array(adata.X.sum(axis=1)).flatten()
print(f"Median counts/cell: {np.median(counts_per_cell):.0f}")
print(f"Min counts/cell: {np.min(counts_per_cell):.0f}")
print(f"Cells with <500 counts: {(counts_per_cell < 500).sum()}")

# 基因检测分布
genes_per_cell = (adata.X > 0).sum(axis=1)
if issparse(adata.X):
    genes_per_cell = np.array(genes_per_cell).flatten()
print(f"Median genes/cell: {np.median(genes_per_cell):.0f}")
```

## Step 5: 高变基因预览

```python
# 如需先 normalise
try:
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, n_top_genes=2000)
    print(f"HVGs: {adata.var.highly_variable.sum()}")
except Exception as e:
    print(f"HVG detection failed: {e}")
```

## Step 6: QC 阈值推荐

基于分布给出推荐阈值：

| 指标 | 保守过滤 | 宽松过滤 |
|------|---------|---------|
| min_genes | 500 | 200 |
| max_genes | 6000 | 10000 |
| max_mito_pct | 10% | 20% |
| min_counts | 1000 | 500 |

推荐写入 `eda_report.md` 供后续 QC 步骤参考。

---

## 探索结论模板

```
## EDA 结论
- 数据规模: {n_cells} 细胞 × {n_genes} 基因
- 数据质量: {good/acceptable/poor}
- 潜在问题: [batch 效应 / 高稀疏度 / 死细胞多 / 低深度样本]
- 推荐 QC 阈值: min_genes={}, max_mito={}
- 下一步: scrna-qc → scrna-seurat-core-analysis


---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="EDA 数据质量评估 —— {样本}",
     context="数据: {细胞数} cells {基因数} genes | MT%={x} ribo%={y} | 稀疏度={z}",
     knowledge_base_info=<KB内容>,
   )
   辩论: 数据质量评估准确吗？QC阈值建议合理吗？有batch效应吗？
3. save_conclusions(module="01_decontamination", topic="EDA", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md → 推荐下一步
```

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| - | - | - | 2026-08-13 | check_xlsx.R | - | - |  |
| - | - | - | 2026-08-13 | check_xlsx.R | - | - |  |
| - | - | - | 2026-08-13 | check_xlsx2.R | - | - |  |
| - | - | - | 2026-08-13 | fix_xlsx_format.R | - | - |  |
| - | - | - | 2026-08-13 | check_xlsx3.R | - | - |  |


| - | - | - | 2026-08-13 | fix_xlsx_format.R | - | - |  |
| - | - | - | 2026-08-13 | fix_xlsx_to_newfile.R | - | - |  |
| - | - | - | 2026-08-13 | fix_xlsx_to_newfile.R | - | - |  |
## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| write.xlsx 写回 E:/骨骼肌锻炼/pathway_score.xlsx 时 Permis | 目标 xlsx 正被 Excel 程序占用（用户打开着文件），Windows 下 | 改为输出修复版到独立新文件，用户关闭 Excel 后自行替换 |

