# -*- coding: utf-8 -*-
"""
cbind 合并多张 Metascape 基因列表表格。
用法: python merge_metascape_cbind.py out.csv table1.csv table2.csv [table3.csv ...]
陷阱: 必须用 axis=1 (cbind), 不是 axis=0 (rbind)。Metascape 表格列数不同但行数应一致。
"""
import pandas as pd
import sys

if len(sys.argv) < 4:
    print("用法: python merge_metascape_cbind.py <out.csv> <table1.csv> <table2.csv> [...]")
    sys.exit(1)

out_path = sys.argv[1]
input_paths = sys.argv[2:]

dfs = []
for p in input_paths:
    df = pd.read_csv(p, encoding="utf-8-sig")
    print(f"  读取 {p}: {df.shape[0]} 行 × {df.shape[1]} 列 — {list(df.columns)}")
    dfs.append(df)

# cbind: 横向合并
merged = pd.concat(dfs, axis=1)
merged.to_csv(out_path, index=False, encoding="utf-8-sig")

print(f"\n✅ 合并完成: {out_path}")
print(f"   结果: {merged.shape[0]} 行 × {merged.shape[1]} 列")

# 验证每列非空基因数
for col in merged.columns:
    non_null = merged[col].notna().sum()
    print(f"   {col}: {non_null} 个基因")
