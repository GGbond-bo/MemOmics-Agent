# CellBender 后处理 Excel 汇总表

## 何时使用

6+ 样本 CellBender 跑完 → 用户想看前后对比数据 → 用 Excel（不是 markdown）。

## 数据源

每个样本的 `*_raw_output_metrics.csv` 包含精确的 found_cells 和 UMI 前后数据。

## Excel 结构

### Sheet 1: 细胞保留统计

| 列 | 来源 | 说明 |
|----|------|------|
| 样本 | 文件名 | 原始 h5ad 样本名 |
| 原始液滴 | h5ad `.shape[0]` 或日志 `Features in dataset` | 全量 barcode 数 |
| 检出细胞 | `_metrics.csv` 的 `found_cells` 列 | CellBender 判定为细胞的 barcode |
| 细胞占比 | 检出细胞 / `total-droplets-included` | 在包含集中的占比 |
| 判定 | 条件格式 | ≥80% 绿色，<50% 黄色 |

### Sheet 2: UMI 统计

| 列 | 来源 |
|----|------|
| 原始 UMI | `_metrics.csv` |
| 去除 UMI | 原始 - 保留 |
| 保留 UMI | `_metrics.csv` |
| 去除率 | 去除 / 原始 × 100% |

### Sheet 3: 运行参数

| 列 | 来源 |
|----|------|
| 完整 14 项参数 | `cellbender_output.log` 第一行的 `Command:` |

## 生成方式

```python
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, numbers

# 颜色
GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
YELLOW_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
```

## Pitfall

- 不要直接用 pipeline 日志的 `done=N/26`，数字不可靠
- 不要重建 Excel 时漏掉"剩余细胞"列 — 用户要看到的就是"从多少细胞跑完还剩多少"
- `_metrics.csv` 里的 cell count 可能和 `_cell_barcodes.csv` 行数差几个（精确用前者）
