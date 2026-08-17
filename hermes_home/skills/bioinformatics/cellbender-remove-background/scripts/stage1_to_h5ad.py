#!/usr/bin/env python3
"""
Stage 1: Read raw matrix → h5ad (FULL — all droplets, for CellBender)
兼容:
  - 华大 BGI DNBC4tools: features.tsv.gz 仅 1 列 (gene_name)
  - 10x Cell Ranger ≥3.0: features.tsv.gz 3 列 (gene_id, gene_name, feature_type)
  - 10x Cell Ranger <3.0:  genes.tsv(.gz) 2 列 (gene_id, gene_name)

Input:  {BASE_DIR}/{sample}/output/raw_matrix/
Output: {OUTPUT_DIR}/{sample}.h5ad

Usage:
  python stage1_to_h5ad.py --base_dir F:/00.RawData --out_dir PROJECT_DATA_DIR/h5ad
  python stage1_to_h5ad.py --base_dir F:/00.RawData --out_dir PROJECT_DATA_DIR/h5ad --samples S1 S2 S3
"""

import os, sys, time, traceback, gzip, argparse
import numpy as np
import pandas as pd
import anndata
from scipy.io import mmread
from scipy.sparse import csr_matrix

anndata.settings.allow_write_nullable_strings = True


# ──────────────────────────────────────────────
# 工具函数：自动探测 features 文件并解析
# ──────────────────────────────────────────────
def find_features_file(mtx_dir):
    """按优先级查找 features 文件，兼容 BGI / 10x 新旧版本"""
    candidates = [
        "features.tsv.gz",
        "features.tsv",
        "genes.tsv.gz",
        "genes.tsv",
    ]
    for name in candidates:
        path = os.path.join(mtx_dir, name)
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        f"在 {mtx_dir} 中未找到 features/genes 文件，"
        f"已尝试: {candidates}"
    )


def parse_features(feat_path):
    """
    解析 features 文件，返回 (gene_symbols, var_df)
    兼容:
      1 列 -> BGI:  仅 gene_name
      2 列 -> 10x旧: gene_id, gene_name
      3 列 -> 10x新: gene_id, gene_name, feature_type
    """
    compression = 'gzip' if feat_path.endswith('.gz') else None
    feat_df = pd.read_csv(feat_path, sep='\t', header=None,
                          compression=compression)
    ncols = feat_df.shape[1]

    if ncols == 1:
        # 华大 BGI DNBC4tools：只有 gene_name 一列
        gene_symbols = feat_df[0].values.astype(str)
        var_df = pd.DataFrame(index=gene_symbols)
        # 没有 gene_id，用 gene_name 自身填充
        var_df['gene_ids'] = gene_symbols

    elif ncols == 2:
        # 10x 旧版 (genes.tsv): col0=gene_id, col1=gene_name
        gene_symbols = feat_df[1].values.astype(str)
        var_df = pd.DataFrame(index=gene_symbols)
        var_df['gene_ids'] = feat_df[0].values.astype(str)

    elif ncols >= 3:
        # 10x 新版 (features.tsv.gz): col0=gene_id, col1=gene_name, col2=feature_type
        gene_symbols = feat_df[1].values.astype(str)
        var_df = pd.DataFrame(index=gene_symbols)
        var_df['gene_ids'] = feat_df[0].values.astype(str)
        var_df['feature_types'] = feat_df[2].values.astype(str)

    else:
        raise ValueError(f"features 文件列数异常: {ncols} 列 ({feat_path})")

    return gene_symbols, var_df


def find_barcodes_file(mtx_dir):
    for name in ["barcodes.tsv.gz", "barcodes.tsv"]:
        path = os.path.join(mtx_dir, name)
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"在 {mtx_dir} 中未找到 barcodes 文件")


def find_matrix_file(mtx_dir):
    for name in ["matrix.mtx.gz", "matrix.mtx"]:
        path = os.path.join(mtx_dir, name)
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"在 {mtx_dir} 中未找到 matrix.mtx 文件")


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────
def run(base_dir, output_dir, sample_names=None, log_file=None):
    """
    将 raw matrix 三件套转换为 h5ad。

    Args:
        base_dir: 包含样本目录的根目录
        output_dir: 输出 h5ad 目录
        sample_names: 可选，指定样本列表；None=自动检测所有子目录
        log_file: 日志文件路径；None=自动生成

    Returns:
        dict: {sample_name: "ok"/"skip"/"missing_dir"/{"error": str}}
    """
    if sample_names is None:
        sample_names = sorted(d for d in os.listdir(base_dir)
                              if os.path.isdir(os.path.join(base_dir, d)))

    os.makedirs(output_dir, exist_ok=True)

    if log_file is None:
        log_dir = os.path.join(os.path.dirname(output_dir), "log")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "stage1.log")

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    results = {}
    total = len(sample_names)
    t0_all = time.time()

    with open(log_file, "w", encoding="utf-8") as log:
        log.write(f"Stage 1 — Read raw -> h5ad (FULL) | {total} samples | {time.ctime()}\n")
        log.write(f"{'='*70}\n")

        for i, sname in enumerate(sample_names, 1):
            mtx_dir  = os.path.join(base_dir, sname, "output", "raw_matrix")
            out_file = os.path.join(output_dir, f"{sname}.h5ad")

            # ---- 跳过已完成的 ----
            if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
                sz_mb = os.path.getsize(out_file) / 1e6
                msg = f"[{i}/{total}] {sname} — SKIP ({sz_mb:.1f} MB)"
                print(msg); log.write(msg + "\n"); log.flush()
                results[sname] = "skip"
                continue

            # ---- 检查目录是否存在 ----
            if not os.path.isdir(mtx_dir):
                msg = f"[{i}/{total}] {sname} — SKIP (目录不存在: {mtx_dir})"
                print(msg); log.write(msg + "\n"); log.flush()
                results[sname] = "missing_dir"
                continue

            t0 = time.time()
            try:
                # ---- 1. 读取 features ----
                feat_path = find_features_file(mtx_dir)
                gene_symbols, var_df = parse_features(feat_path)
                n_genes = len(gene_symbols)

                # ---- 2. 读取 barcodes ----
                bc_path = find_barcodes_file(mtx_dir)
                compression = 'gzip' if bc_path.endswith('.gz') else None
                all_barcodes = pd.read_csv(bc_path, sep='\t', header=None,
                                           compression=compression)[0].values
                n_cells = len(all_barcodes)

                # ---- 3. 读取矩阵 ----
                mtx_path = find_matrix_file(mtx_dir)
                mat = mmread(mtx_path)

                # ---- 4. 方向校验 ----
                if mat.shape == (n_genes, n_cells):
                    mat = mat.T.tocsr()
                elif mat.shape == (n_cells, n_genes):
                    mat = mat.tocsr()
                else:
                    raise ValueError(
                        f"矩阵 shape {mat.shape} 与预期不匹配 "
                        f"(genes={n_genes}, barcodes={n_cells})"
                    )

                # ---- 5. int32 转换（UMI counts 足够）----
                mat = mat.astype(np.int32)

                print(f"  [{sname}] {mat.shape[0]:,} droplets x {mat.shape[1]:,} genes "
                      f"— writing h5ad...", end="", flush=True)

                # ---- 6. 构建 AnnData ----
                adata = anndata.AnnData(
                    X=mat,
                    obs=pd.DataFrame(index=all_barcodes),
                    var=var_df
                )
                adata.obs_names = [f"{sname}_{x}" for x in adata.obs_names]
                adata.obs['sample'] = sname
                if not adata.var_names.is_unique:
                    adata.var_names_make_unique()

                adata.write(out_file)
                elapsed = time.time() - t0
                sz_mb = os.path.getsize(out_file) / 1e6
                msg = (f"[{i}/{total}] {sname} — {adata.n_obs:,} cells x {adata.n_vars:,} genes "
                       f"({sz_mb:.1f} MB, {elapsed:.0f}s)")
                print("\r" + msg); log.write(msg + "\n"); log.flush()
                results[sname] = {"status": "ok", "n_obs": adata.n_obs, "n_vars": adata.n_vars}

            except Exception as e:
                elapsed = time.time() - t0
                msg = f"[{i}/{total}] {sname} — ERROR ({elapsed:.0f}s): {e}"
                print("\r" + msg); log.write(msg + "\n")
                log.write(traceback.format_exc() + "\n"); log.flush()
                results[sname] = {"status": "error", "error": str(e)}

        # ---- 汇总 ----
        sys.stdout.flush()
        total_elapsed = time.time() - t0_all
        n_done = sum(1 for v in results.values()
                     if isinstance(v, dict) and v.get("status") == "ok")
        n_skip = sum(1 for v in results.values() if v == "skip")
        n_miss = sum(1 for v in results.values() if v == "missing_dir")
        n_err  = sum(1 for v in results.values()
                     if isinstance(v, dict) and v.get("status") == "error")
        summary = (f"\nDONE: {n_done} ok | {n_skip} skip | {n_miss} missing | "
                   f"{n_err} err | {total_elapsed/60:.1f} min")
        print(f"\n{'='*70}")
        print(summary)
        log.write(summary + "\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 1: Raw matrix -> h5ad")
    parser.add_argument("--base_dir", required=True,
                        help="根目录，内含样本子目录")
    parser.add_argument("--out_dir", required=True,
                        help="h5ad 输出目录")
    parser.add_argument("--samples", nargs="*", default=None,
                        help="指定样本列表（不传则自动检测所有子目录）")
    parser.add_argument("--log_file", default=None,
                        help="日志文件路径")
    args = parser.parse_args()

    run(
        base_dir=args.base_dir,
        output_dir=args.out_dir,
        sample_names=args.samples,
        log_file=args.log_file,
    )
