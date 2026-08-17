#!/usr/bin/env python3
"""
Stage 4: 每个样本去污染前后统计对比表
输入: CellBender output (metrics.csv + cell_barcodes.csv + filtered.h5) + 原始 h5ad
输出: 终端表格 + CSV 文件

用法: python stage4_per_sample_stats.py
"""
import os, csv, h5py
from pathlib import Path

# ======== 配置 ========
H5AD_DIR = Path("PROJECT_DATA_DIR/h5ad")
CELLBENDER_DIR = Path("PROJECT_DATA_DIR/cellbender_output")
OUTPUT_CSV = Path("PROJECT_DATA_DIR/stats/stage4_per_sample.csv")
# =====================

OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

samples = sorted([d for d in os.listdir(CELLBENDER_DIR) if os.path.isdir(CELLBENDER_DIR / d)])

results = []
for sample in samples:
    sample_dir = CELLBENDER_DIR / sample
    metrics_file = sample_dir / "cellbender_output_metrics.csv"
    barcodes_file = sample_dir / "cellbender_output_cell_barcodes.csv"
    filtered_h5 = sample_dir / "cellbender_output_filtered.h5"
    h5ad_file = H5AD_DIR / f"{sample}.h5ad"

    metrics = {}
    if metrics_file.exists():
        with open(metrics_file) as f:
            for row in csv.reader(f):
                if len(row) == 2:
                    metrics[row[0].strip()] = row[1].strip()

    # Before: total droplets from original h5ad
    before = "N/A"
    if h5ad_file.exists():
        try:
            with h5py.File(h5ad_file, 'r') as f:
                before = int(f['X'].attrs['shape'][0])
        except:
            pass

    # After: retained cells from barcodes CSV (minus header)
    after = "N/A"
    if barcodes_file.exists():
        with open(barcodes_file) as f:
            after = sum(1 for _ in f) - 1

    # Genes from filtered.h5
    genes = "N/A"
    if filtered_h5.exists():
        try:
            with h5py.File(filtered_h5, 'r') as f:
                genes = int(f['matrix/shape'][1])
        except:
            pass

    removed_frac = metrics.get("fraction_counts_removed", "N/A")
    converged = metrics.get("convergence_indicator", "N/A")
    found_cells = metrics.get("found_cells", "N/A")

    results.append({
        "sample": sample.replace("_scRNA", ""),
        "before": before,
        "after": after,
        "genes": genes,
        "removed_frac": removed_frac,
        "converged": converged,
        "found_cells": found_cells,
    })

# Print terminal table
print(f"{'Sample':<26} {'去前液滴':>12} {'保留细胞':>10} {'基因数':>8} {'去UMI%':>8} {'收敛':>8}")
print("-" * 88)
for r in results:
    b = f"{r['before']:,}" if isinstance(r['before'], int) else r['before']
    rf = f"{float(r['removed_frac'])*100:.1f}%" if r['removed_frac'].replace('.', '', 1).isdigit() else r['removed_frac']
    cv = f"{float(r['converged']):.2f}" if r['converged'].replace('.', '', 1).isdigit() else r['converged']
    print(f"{r['sample']:<26} {b:>12} {str(r['after']):>10} {str(r['genes']):>8} {rf:>8} {cv:>8}")

total_before = sum(r['before'] for r in results if isinstance(r['before'], int))
total_after = sum(r['after'] for r in results if isinstance(r['after'], int))
print("-" * 88)
print(f"{'总计':<26} {total_before:>12,} {total_after:>10,}")

# Save CSV
with open(OUTPUT_CSV, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["sample", "total_droplets_before", "cells_retained", "genes", "umi_removed_pct", "convergence_indicator"])
    writer.writeheader()
    for r in results:
        writer.writerow({
            "sample": r["sample"],
            "total_droplets_before": r["before"],
            "cells_retained": r["after"],
            "genes": r["genes"],
            "umi_removed_pct": f"{float(r['removed_frac'])*100:.1f}" if r['removed_frac'].replace('.', '', 1).isdigit() else "",
            "convergence_indicator": r["converged"],
        })

print(f"\nCSV saved: {OUTPUT_CSV}")
