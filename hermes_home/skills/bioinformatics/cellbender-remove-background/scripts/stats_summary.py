#!/usr/bin/env python3
"""
CellBender 前后对比统计表

读取 h5ad (before) + cellbender_output_filtered.h5 (after)，生成 TSV 对比表。

Usage:
  python stats_summary.py --h5ad_dir PROJECT_DATA_DIR/h5ad --cb_dir PROJECT_DATA_DIR/cellbender_output --out_dir PROJECT_DATA_DIR/summary
"""

import os, sys, glob, csv, argparse, time
import h5py


def run(h5ad_dir, cb_dir, out_dir, sample_names=None):
    """
    对比 CellBender 前后细胞数/基因数/稀疏度。

    Args:
        h5ad_dir: Stage 1 输出的 h5ad 目录
        cb_dir: CellBender output 目录
        out_dir: 输出目录
        sample_names: 样本列表（None=自动检测）
    """
    os.makedirs(out_dir, exist_ok=True)

    # 检测样本
    if sample_names is None:
        h5ads = sorted(glob.glob(os.path.join(h5ad_dir, "*.h5ad")))
        sample_names = [os.path.basename(f).replace(".h5ad", "") for f in h5ads]

    rows = []

    for sname in sample_names:
        row = {"sample": sname}

        # Before (h5ad)
        h5ad_path = os.path.join(h5ad_dir, f"{sname}.h5ad")
        if os.path.exists(h5ad_path):
            try:
                import anndata
                ad = anndata.read(h5ad_path, backed="r")
                row["before_cells"] = ad.n_obs
                row["before_genes"] = ad.n_vars
                if hasattr(ad.X, "nnz"):
                    row["before_nnz"] = ad.X.nnz
                    total_entries = ad.n_obs * ad.n_vars
                    if total_entries > 0:
                        row["before_sparsity"] = f"{100 * (1 - ad.X.nnz / total_entries):.1f}%"
            except Exception as e:
                row["before_error"] = str(e)

        # After (CellBender filtered.h5)
        cb_file = os.path.join(cb_dir, sname, "cellbender_output_filtered.h5")
        if os.path.exists(cb_file):
            try:
                with h5py.File(cb_file, "r") as f:
                    if "matrix" in f:
                        grp = f["matrix"]
                        shape = grp["shape"][:]
                        row["after_cells"] = int(shape[0])
                        row["after_genes"] = int(shape[1])
                        nnz = len(grp["data"])
                        row["after_nnz"] = nnz
                        total_after = shape[0] * shape[1]
                        if total_after > 0:
                            row["after_sparsity"] = f"{100 * (1 - nnz / total_after):.1f}%"

                        # 移除比例
                        if "before_cells" in row:
                            delta = row["before_cells"] - int(shape[0])
                            row["cell_change"] = delta
                            if row["before_cells"] > 0:
                                row["cell_change_pct"] = f"{100 * delta / row['before_cells']:.1f}%"
            except Exception as e:
                row["after_error"] = str(e)

        # CB output size
        cb_full = os.path.join(cb_dir, sname, "cellbender_output.h5")
        if os.path.exists(cb_full):
            sz_mb = os.path.getsize(cb_full) / 1e6
            row["output_h5_mb"] = f"{sz_mb:.0f}"

        rows.append(row)

    # 写 TSV
    if rows:
        fieldnames = list(rows[0].keys())
        tsv_path = os.path.join(out_dir, "cellbender_stats.tsv")
        with open(tsv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        print(f"统计表 -> {tsv_path}")
    else:
        tsv_path = None
        print("无数据")

    # 控制台输出
    print(f"\n{'sample':30s} {'before_cells':>12s} {'after_cells':>12s} {'变化':>10s} {'sparsity_before':>16s} {'sparsity_after':>16s}")
    print("-" * 96)
    for r in rows:
        b = str(r.get("before_cells", "?"))
        a = str(r.get("after_cells", "?"))
        ch = r.get("cell_change_pct", "?")
        sb = r.get("before_sparsity", "?")
        sa = r.get("after_sparsity", "?")
        cb = r.get("output_h5_mb", "?")
        print(f"{r['sample']:30s} {b:>12s} {a:>12s} {ch:>10s} {sb:>16s} {sa:>16s}  ({cb} MB)")

    return tsv_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CellBender 前后对比统计")
    parser.add_argument("--h5ad_dir", required=True, help="h5ad 输入目录")
    parser.add_argument("--cb_dir", required=True, help="CellBender output 目录")
    parser.add_argument("--out_dir", required=True, help="统计表输出目录")
    parser.add_argument("--samples", nargs="*", default=None, help="样本列表")
    args = parser.parse_args()

    run(args.h5ad_dir, args.cb_dir, args.out_dir, args.samples)
