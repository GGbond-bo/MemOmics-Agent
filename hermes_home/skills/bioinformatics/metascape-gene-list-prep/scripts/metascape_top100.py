# -*- coding: utf-8 -*-
"""
从 DEG/FindMarkers CSV 构建 Metascape 输入表。
规则: 按 cluster 分组 → avg_log2FC 降序 → top-N（默认100，不足全取）→ 一列一个亚群的 CSV
陷阱: 绝不用 pandas to_csv 写入 Series name 列——会把亚群名写进数据行！手动 csv.writer 安全。

输入: DEG CSV（需含 cluster, gene, avg_log2FC 列）
输出: Metascape 格式 CSV（第1行=亚群名，第2行起=基因）
"""
import pandas as pd
import csv
import sys
import os

# === 参数 ===
SRC = sys.argv[1] if len(sys.argv) > 1 else r"<数据目录>\MF_annotation_L3_protein_DEG.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"Metascape_gene_list.csv"
TOP_N = int(sys.argv[3]) if len(sys.argv) > 3 else 100
CLUSTER_COL = "cluster"
GENE_COL = "gene"
FC_COL = "avg_log2FC"

# === 读取 & 清洗 ===
df = pd.read_csv(SRC)
df[GENE_COL] = df[GENE_COL].astype(str).str.strip().str.replace(r"\t", "", regex=True)

# 校验
assert not df[FC_COL].isna().any(), f"{FC_COL} 有缺失值"
dup = df.duplicated(subset=[CLUSTER_COL, GENE_COL]).sum()
assert dup == 0, f"同亚群内存在重复基因 {dup} 行"

# === 分组取 top-N ===
clusters = sorted(df[CLUSTER_COL].unique())
columns = []
for cl in clusters:
    sub = df[df[CLUSTER_COL] == cl].sort_values(FC_COL, ascending=False).head(TOP_N)
    genes = sub[GENE_COL].tolist()
    col = [cl] + genes
    columns.append(col)

# 统一长度
max_len = max(len(c) for c in columns)
for c in columns:
    while len(c) < max_len:
        c.append("")

# === 手动写 CSV（避免 pandas 表头重复陷阱）===
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    for row_idx in range(max_len):
        w.writerow([col[row_idx] for col in columns])

# === 验证 ===
verify = pd.read_csv(OUT, nrows=3)
print(f"✅ 已导出: {OUT}")
print(f"表尺寸: {max_len - 1} 行基因 x {len(columns)} 列亚群")
header = list(verify.columns)
row1 = verify.iloc[0].tolist()
dups = [h for h, r in zip(header, row1) if h == r]
if dups:
    print(f"⚠️ 表头重复! 以下列的第2行=列名: {dups}")
else:
    print(f"✅ 无表头重复")
