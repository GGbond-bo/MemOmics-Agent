# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 此脚本由 MemOmics Agent 执行。原脚本永远不被修改。
#
# 执行前必须:
#   1. rail_review(action="pre")  — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs", script_name="本脚本名",
#      species="物种", tissue="组织", direction="方向")
#      → 查同类运行日志，有则参考已有参数和经验，无则按原脚本执行
#   3. debate_analysis(topic, context) — 参数不确定时多角色辩论
#
# 执行后必须:
#   1. rail_review(action="post") — 检查输出/质量/图表
#   2. 如果通过 → skill_evolution(action="record_run",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", params_used="参数JSON", result_summary="结果",
#      quality_score=8, notes="经验总结")
#      → 记录成功运行日志，供后续同类型分析参考
#   3. 如果失败 → skill_evolution(action="record_error",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", error_message="报错", root_cause="根因",
#      fix_applied="修复方案")
#      → 记录错误日志，修正后重跑
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

#!/usr/bin/env python3
"""
Load scRNA-seq data for disease drug discovery analysis.

Supports:
  - Pre-annotated AnnData (.h5ad) from scrnaseq-scanpy-core-analysis
  - Demo data: GSE195452 systemic sclerosis skin biopsies
  - Raw data with automatic preprocessing

Usage:
  from load_data import load_demo_ssc_data
  adata = load_demo_ssc_data()

  from load_data import load_annotated_h5ad
  adata = load_annotated_h5ad("path/to/adata.h5ad")
"""

import os
import sys

import numpy as np
import pandas as pd
import scanpy as sc
import anndata as ad


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_OBS_KEYS = {
    "celltype": ["cell_type", "celltype", "cell_type_annotation", "CellType",
                  "annotation", "cluster_annotation", "celltypist_label"],
    "condition": ["condition", "disease", "group", "status", "disease_status",
                  "diagnosis", "phenotype", "sample_type"],
    "sample": ["sample_id", "sample", "donor", "donor_id", "patient",
               "patient_id", "subject", "subject_id", "orig.ident"],
}


# ---------------------------------------------------------------------------
# Data loading functions
# ---------------------------------------------------------------------------

def load_annotated_h5ad(path, celltype_key=None, condition_key=None,
                        sample_key=None):
    """Load a pre-annotated AnnData object and validate required columns.

    Args:
        path: Path to .h5ad file
        celltype_key: Column name for cell type annotations
        condition_key: Column name for disease/condition labels
        sample_key: Column name for sample/donor IDs

    Returns:
        Validated AnnData object with standardized column names
    """
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading AnnData from {path}...")
    adata = sc.read_h5ad(path)

    # Resolve column names
    celltype_col = _resolve_column(adata, celltype_key, "celltype")
    condition_col = _resolve_column(adata, condition_key, "condition")
    sample_col = _resolve_column(adata, sample_key, "sample")

    # Standardize column names
    if celltype_col != "cell_type":
        adata.obs["cell_type"] = adata.obs[celltype_col].copy()
    if condition_col != "condition":
        adata.obs["condition"] = adata.obs[condition_col].copy()
    if sample_col != "sample_id":
        adata.obs["sample_id"] = adata.obs[sample_col].copy()

    # Validate
    _validate_adata(adata)

    n_cells = adata.n_obs
    n_genes = adata.n_vars
    n_types = adata.obs["cell_type"].nunique()
    n_conditions = adata.obs["condition"].nunique()
    print(f"\u2713 Data loaded successfully! {n_cells} cells, {n_genes} genes, "
          f"{n_types} cell types, {n_conditions} conditions")

    return adata


def load_demo_ssc_data():
    """Load GSE195452 systemic sclerosis demo dataset.

    Checks local cache first. If not found, downloads the cell metadata
    and per-sample count matrices from GEO and constructs an AnnData.

    NOTE: GSE195452 is a MARS-seq/Smart-seq2 dataset (plate-based).
    GEO provides per-sample count text files in a RAW.tar (~800 MB)
    plus a cell metadata annotation file. There is NO pre-built h5ad.
    Building the AnnData from raw files takes 10-20 minutes.

    The recommended approach for Biomni:
    1. Download GSE195452_Cell_metadata_v26_anno.txt.gz (3 MB, cell annotations)
    2. Download GSE195452_RAW.tar (800 MB, per-sample count matrices)
    3. Extract TAR, load each sample's count matrix, concatenate
    4. Merge cell metadata (annotations, patient IDs, conditions)
    5. Save as h5ad for reuse

    Returns:
        Annotated AnnData object ready for analysis
    """
    # Check local cache locations
    cache_paths = [
        "./data/GSE195452_adata.h5ad",
        "/mnt/datalake/scrna/GSE195452_adata.h5ad",
        "/mnt/results/GSE195452_adata.h5ad",
        os.path.expanduser("~/data/GSE195452_adata.h5ad"),
    ]

    for path in cache_paths:
        if os.path.exists(path):
            print(f"Loading cached GSE195452 data from {path}...")
            adata = sc.read_h5ad(path)
            _validate_adata(adata)
            n_cells = adata.n_obs
            n_genes = adata.n_vars
            n_types = adata.obs["cell_type"].nunique()
            n_conditions = adata.obs["condition"].nunique()
            print(f"\u2713 Data loaded successfully! {n_cells} cells, {n_genes} genes, "
                  f"{n_types} cell types, {n_conditions} conditions")
            return adata

    # Download from GEO
    print("GSE195452 data not found locally.")
    print("NOTE: This dataset requires building from GEO RAW files (~800 MB download).")
    print("Files needed from GEO FTP:")
    print("  1. GSE195452_Cell_metadata_v26_anno.txt.gz (cell annotations)")
    print("  2. GSE195452_RAW.tar (per-sample count matrices)")
    print("Download from: https://ftp.ncbi.nlm.nih.gov/geo/series/GSE195nnn/GSE195452/suppl/")
    print("")
    print("After download: extract TAR, load count matrices per sample,")
    print("merge with cell metadata, assign conditions from patient IDs")
    print("(Ctrl* = Healthy, others = SSc), and save as h5ad.")
    print("")
    adata = _download_gse195452()
    _validate_adata(adata)

    n_cells = adata.n_obs
    n_genes = adata.n_vars
    n_types = adata.obs["cell_type"].nunique()
    n_conditions = adata.obs["condition"].nunique()
    print(f"\u2713 Data loaded successfully! {n_cells} cells, {n_genes} genes, "
          f"{n_types} cell types, {n_conditions} conditions")

    return adata


def load_raw_data(path, species="human"):
    """Load raw count data for preprocessing.

    Supports: 10X CellRanger output directory, H5 files, CSV/TSV matrices.

    Args:
        path: Path to data file or directory
        species: "human" or "mouse"

    Returns:
        Raw AnnData object (requires preprocessing before analysis)
    """
    if os.path.isdir(path):
        # Try 10X CellRanger output
        mtx_dir = os.path.join(path, "filtered_feature_bc_matrix")
        if os.path.exists(mtx_dir):
            print(f"Loading 10X CellRanger output from {mtx_dir}...")
            adata = sc.read_10x_mtx(mtx_dir, var_names="gene_symbols")
        else:
            print(f"Loading 10X output from {path}...")
            adata = sc.read_10x_mtx(path, var_names="gene_symbols")
    elif path.endswith(".h5"):
        print(f"Loading H5 file from {path}...")
        adata = sc.read_10x_h5(path)
    elif path.endswith(".h5ad"):
        print(f"Loading H5AD file from {path}...")
        adata = sc.read_h5ad(path)
    elif path.endswith((".csv", ".tsv", ".txt")):
        print(f"Loading matrix from {path}...")
        sep = "\t" if path.endswith((".tsv", ".txt")) else ","
        adata = sc.read_csv(path, delimiter=sep).T
    else:
        print(f"ERROR: Unsupported file format: {path}", file=sys.stderr)
        sys.exit(1)

    adata.var_names_make_unique()
    print(f"\u2713 Raw data loaded! {adata.n_obs} cells, {adata.n_vars} genes")
    return adata


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_column(adata, user_key, column_type):
    """Find the best matching column in adata.obs."""
    if user_key and user_key in adata.obs.columns:
        return user_key

    candidates = REQUIRED_OBS_KEYS.get(column_type, [])
    for col in candidates:
        if col in adata.obs.columns:
            return col

    available = list(adata.obs.columns)
    print(f"WARNING: Could not find '{column_type}' column. "
          f"Available columns: {available}", file=sys.stderr)
    print(f"  Searched for: {candidates}", file=sys.stderr)
    if user_key:
        print(f"  User specified: '{user_key}' (not found)", file=sys.stderr)
    return candidates[0]  # Will fail at validation if not present


def _validate_adata(adata):
    """Validate AnnData has required columns and structure."""
    errors = []

    # Check required columns
    for col in ["cell_type", "condition", "sample_id"]:
        if col not in adata.obs.columns:
            errors.append(f"Missing required column: '{col}'")

    if errors:
        print("ERROR: Data validation failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(f"\nAvailable columns: {list(adata.obs.columns)}", file=sys.stderr)
        sys.exit(1)

    # Check conditions
    n_conditions = adata.obs["condition"].nunique()
    if n_conditions < 2:
        print(f"ERROR: Need >=2 conditions for disease vs control comparison. "
              f"Found {n_conditions}: {adata.obs['condition'].unique().tolist()}",
              file=sys.stderr)
        sys.exit(1)

    # Check cell types
    n_types = adata.obs["cell_type"].nunique()
    if n_types < 2:
        print(f"WARNING: Only {n_types} cell type(s) found. "
              f"L-R analysis requires >=3 cell types.", file=sys.stderr)

    # Check sample IDs for pseudobulk
    for condition in adata.obs["condition"].unique():
        n_samples = adata.obs.loc[
            adata.obs["condition"] == condition, "sample_id"
        ].nunique()
        if n_samples < 2:
            print(f"WARNING: Condition '{condition}' has only {n_samples} sample(s). "
                  f"Pseudobulk DE requires >=2 per condition. "
                  f"Will use cell-level DE as fallback.", file=sys.stderr)


def _download_gse195452():
    """Download and prepare GSE195452 dataset from GEO.

    This is a scRNA-seq dataset of skin biopsies from systemic sclerosis
    patients. The function downloads the supplementary files and constructs
    an AnnData object.
    """
    import urllib.request
    import gzip
    import tempfile

    # GEO supplementary file URL
    geo_url = ("https://ftp.ncbi.nlm.nih.gov/geo/series/GSE195nnn/"
               "GSE195452/suppl/")

    # Create data directory
    data_dir = "./data"
    os.makedirs(data_dir, exist_ok=True)

    print("Attempting to download GSE195452 from GEO...")
    print("Note: If download fails, please manually download the dataset "
          "and place the h5ad file at ./data/GSE195452_adata.h5ad")

    # Try to load via scanpy's GEO utilities or direct download
    # The exact file format depends on what the authors deposited
    try:
        # Try common GEO supplementary file patterns
        h5ad_url = geo_url + "GSE195452_adata.h5ad.gz"
        output_path = os.path.join(data_dir, "GSE195452_adata.h5ad")

        print(f"Downloading from {h5ad_url}...")
        tmp_path = os.path.join(data_dir, "GSE195452_adata.h5ad.gz")
        urllib.request.urlretrieve(h5ad_url, tmp_path)

        print("Decompressing...")
        with gzip.open(tmp_path, "rb") as f_in:
            with open(output_path, "wb") as f_out:
                f_out.write(f_in.read())
        os.remove(tmp_path)

        adata = sc.read_h5ad(output_path)
    except Exception as e:
        print(f"Direct h5ad download failed: {e}", file=sys.stderr)
        print("Trying alternative download method...", file=sys.stderr)

        try:
            # Try loading via GEOparse or alternative formats
            _download_geo_matrix(data_dir)
            adata = sc.read_h5ad(os.path.join(data_dir, "GSE195452_adata.h5ad"))
        except Exception as e2:
            print(f"ERROR: Could not download GSE195452: {e2}", file=sys.stderr)
            print("\nPlease download the dataset manually:", file=sys.stderr)
            print("  1. Visit https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE195452",
                  file=sys.stderr)
            print("  2. Download the supplementary files", file=sys.stderr)
            print("  3. Place the processed h5ad at ./data/GSE195452_adata.h5ad",
                  file=sys.stderr)
            sys.exit(1)

    # Standardize column names for SSc dataset
    _standardize_ssc_metadata(adata)

    # Cache for future runs
    cache_path = os.path.join(data_dir, "GSE195452_adata.h5ad")
    if not os.path.exists(cache_path):
        adata.write_h5ad(cache_path)
        print(f"Cached processed data at {cache_path}")

    return adata


def _download_geo_matrix(data_dir):
    """Alternative download method using count matrix + metadata."""
    import urllib.request

    base_url = ("https://ftp.ncbi.nlm.nih.gov/geo/series/GSE195nnn/"
                "GSE195452/suppl/")

    # Download count matrix and metadata files
    files_to_try = [
        "GSE195452_counts.h5",
        "GSE195452_raw_counts.h5",
        "GSE195452_filtered_counts.h5",
        "GSE195452_expression_matrix.csv.gz",
    ]

    for fname in files_to_try:
        try:
            url = base_url + fname
            local_path = os.path.join(data_dir, fname)
            print(f"  Trying {url}...")
            urllib.request.urlretrieve(url, local_path)
            print(f"  Downloaded {fname}")

            if fname.endswith(".h5"):
                adata = sc.read_10x_h5(local_path)
            elif fname.endswith(".csv.gz"):
                adata = sc.read_csv(local_path).T

            adata.write_h5ad(os.path.join(data_dir, "GSE195452_adata.h5ad"))
            return
        except Exception:
            continue

    raise RuntimeError("No compatible supplementary files found on GEO")


def _standardize_ssc_metadata(adata):
    """Standardize metadata columns for SSc dataset."""
    # Map common column names to standard names
    col_map = {}

    # Cell type
    for col in ["cell_type", "celltype", "CellType", "annotation",
                "cell_type_annotation", "cluster_annotation"]:
        if col in adata.obs.columns:
            col_map["cell_type"] = col
            break

    # Condition/disease status
    for col in ["condition", "disease", "group", "status", "disease_status",
                "diagnosis", "phenotype"]:
        if col in adata.obs.columns:
            col_map["condition"] = col
            break

    # Sample/donor ID
    for col in ["sample_id", "sample", "donor", "donor_id", "patient",
                "patient_id", "subject", "orig.ident"]:
        if col in adata.obs.columns:
            col_map["sample_id"] = col
            break

    # Apply mappings
    for standard_name, original_name in col_map.items():
        if standard_name not in adata.obs.columns:
            adata.obs[standard_name] = adata.obs[original_name].copy()

    # If condition column contains SSc subtypes, create a binary condition
    if "condition" in adata.obs.columns:
        conditions = adata.obs["condition"].unique().tolist()
        ssc_keywords = ["ssc", "sclerosis", "scleroderma", "diffuse", "limited",
                        "dcSSc", "lcSSc", "disease"]
        healthy_keywords = ["healthy", "control", "normal", "HC"]

        has_ssc = any(
            any(kw.lower() in str(c).lower() for kw in ssc_keywords)
            for c in conditions
        )
        has_healthy = any(
            any(kw.lower() in str(c).lower() for kw in healthy_keywords)
            for c in conditions
        )

        if has_ssc and has_healthy and len(conditions) > 2:
            # Create binary disease column preserving subtypes
            adata.obs["condition_detail"] = adata.obs["condition"].copy()
            adata.obs["condition"] = adata.obs["condition"].apply(
                lambda x: "Healthy" if any(
                    kw.lower() in str(x).lower() for kw in healthy_keywords
                ) else "SSc"
            )
            print(f"  Simplified conditions: {adata.obs['condition'].value_counts().to_dict()}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Load scRNA-seq data")
    parser.add_argument("--input", help="Path to h5ad file")
    parser.add_argument("--demo", action="store_true", help="Load demo SSc data")
    parser.add_argument("--celltype-key", help="Cell type column name")
    parser.add_argument("--condition-key", help="Condition column name")
    parser.add_argument("--sample-key", help="Sample ID column name")
    args = parser.parse_args()

    if args.demo:
        adata = load_demo_ssc_data()
    elif args.input:
        adata = load_annotated_h5ad(args.input, args.celltype_key,
                                     args.condition_key, args.sample_key)
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    print(f"\nDataset summary:")
    print(f"  Cells: {adata.n_obs}")
    print(f"  Genes: {adata.n_vars}")
    print(f"  Cell types: {adata.obs['cell_type'].value_counts().to_dict()}")
    print(f"  Conditions: {adata.obs['condition'].value_counts().to_dict()}")
    print(f"  Samples: {adata.obs['sample_id'].nunique()}")
