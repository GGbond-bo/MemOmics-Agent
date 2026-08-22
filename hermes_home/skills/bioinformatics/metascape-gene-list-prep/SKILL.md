---
name: metascape-gene-list-prep
version: 1.0
description: >
  从 DEG/FindMarkers 结果表构建 Metascape 输入基因列表。按亚群分列、按 avg_log2FC 降序取 top-N，
  输出一列一个亚群的 CSV（亚群名为列头，基因竖排）。支持多表行合并（如 MF+SMF 合并）。触发词：metascape / 基因列表 / top100 / DEG转Metascape / 按亚群取基因 / 合并Metascape表。
category: user-skill
source: user-requested
tags: [metascape, deg, gene-list, marker, csv-formatting]
---

# Metascape 基因列表构建

## 使用场景

用户有 FindMarkers / DEG 结果 CSV（含 `cluster`、`gene`、`avg_log2FC` 列），需要构建 Metascape 导入格式的基因列表：
- 每列 = 一个亚群
- 列头 = 亚群名
- 下方 = 该亚群按 `avg_log2FC` 降序排列的 top-N 基因（默认 100）
- 不足 top-N 的亚群全取

## 核心流程

1. 读取 DEG CSV → 清洗 gene 列（去制表符/空白）
2. 按 cluster 分组 → 每组按 avg_log2FC 降序排序 → 取 head(top_n)
3. 构建 CSV：每列 = [亚群名, gene1, gene2, ...geneN]
4. 验证：表头行 = 亚群名，第 2 行起 = 基因（无重复表头）

## ⚠️ 关键陷阱：pandas to_csv 表头重复

**根因**：`pd.Series(name=cl)` → `pd.concat(axis=1)` → `to_csv(header=False)` 时，Series 的 `name` 属性会**同时**写入列头和第一个数据行，导致 CSV 第 2 行重复亚群名。

**错误模式**（用户会看到"表头重复了"）：
```
cluster1,cluster2    ← 第1行: 表头 ✓
cluster1,cluster2    ← 第2行: 重复的表头 ✗（应为基因数据）
gene1,gene3          ← 第3行: 基因数据
```

**正确写法**（手动 CSV writer，绕过 pandas）：
```python
import csv

# columns = [ [cluster_name, gene1, gene2, ...], [...], ... ]
with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    for row_idx in range(len(columns[0])):  # 0=header, 1..N=genes
        w.writerow([col[row_idx] for col in columns])
```

**备选修复**（仍用 pandas，但确认 name=None）：
```python
metascape_df = pd.concat(records, axis=1)
# 强制列名 = 亚群名列表，不含 Series.name 残留
metascape_df.columns = clusters
metascape_df.to_csv(OUT, index=False, encoding="utf-8-sig")
# 验证: assert 第2行全是基因名，不含亚群名
```

## 验证清单

生成后必须检查：
1. [ ] 第 1 行 = 亚群名（列头）
2. [ ] 第 2 行起 = 基因名（不含亚群名）
3. [ ] 各列非空基因数 = min(top_n, 该亚群原始基因数)
4. [ ] 同亚群内无重复基因
5. [ ] 编码 utf-8-sig（Excel 直接打开不乱码）

## 合并多个 Metascape 表格

用户常有多张 Metascape CSV（如 MF + SMF 两套亚群），需要合并成一张大表再丢 Metascape。

### ⛔ 关键陷阱：cbind vs rbind（2026-08-22 用户纠正）

Metascape 表格合并 = **cbind（横向合并）**，不是 rbind（纵向拼接）！

- **cbind（正确）**：`pd.concat([df1, df2], axis=1)` — 列数相加，行数不变
- **rbind（错误）**：`pd.concat([df1, df2], axis=0)` — 行数相加，列数不变

用户原话纠正："用cbind不就行了吗？你现在SMF的基因都跑102行以下了" — 用 rbind 会导致后表的基因从第 N+1 行开始填入，前面全是空值。

**何时用什么**：
- 合并两张 Metascape 表（如 MF 10列 + SMF 7列）→ **cbind**（横向合并，17列）
- Metascape 只需要基因列表，不需要空行填充

### cbind 合并代码（正确做法）

```python
import pandas as pd

df_mf = pd.read_csv(mf_path, encoding="utf-8-sig")    # 100行 × 10列
df_smf = pd.read_csv(smf_path, encoding="utf-8-sig")  # 100行 × 7列

# cbind: 横向合并，列数相加，行数不变
merged = pd.concat([df_mf, df_smf], axis=1)  # 100行 × 17列
merged.to_csv(out_path, index=False, encoding="utf-8-sig")
```

### rbind 合并代码（仅限同结构表的纵向堆叠）

```python
# 仅当两个表列名完全相同、需要上下叠放时才用 rbind
merged = pd.concat([df1, df2], ignore_index=True)  # axis=0 纵向
```

**验证**（cbind 后）：
- 行数 = 各表行数之和（各表 top-N 相同的情况下）
- 列数 = 各表列数之和
- 每列非空基因数 = min(top_n, 该亚群原始基因数)（无空行）

## Metascape 格式要求

Metascape 导入格式：
- 第 1 行 = 列名（自定义，如亚群名）
- 第 2 行起 = 基因 symbol（每行一个基因）
- 不需要 p-value / log2FC 列（Metascape 只需基因列表）
- 列数不限，每列独立分析

## 脚本模板

- `scripts/metascape_top100.py` — 单表构建：输入校验 + 手动 CSV writer + 验证输出
- `scripts/merge_metascape_cbind.py` — 多表 cbind 合并：横向拼接 + 逐列验证非空基因数

## 参考

- Metascape 官网: https://metascape.org
- 用户偏好：脚本直接贴对话（不写文件），分步给出，关键行加验证注释
