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
============================================================================
PREPROCESSING PIPELINE FOR RAW scRNA-seq DATA
============================================================================

This script runs a full preprocessing pipeline on raw (unannotated) scRNA-seq
data: QC metrics, MAD-based filtering, doublet removal, normalization, HVG
selection, dimensionality reduction, clustering, and automated cell type
annotation via CellTypist.

Only call this when data is NOT already annotated.  For pre-annotated data
use load_data.load_annotated_h5ad() directly.

Functions:
  - check_annotation_status(): Check whether an AnnData is already annotated
  - run_preprocessing_pipeline(): Full end-to-end preprocessing pipeline

Usage:
  from preprocess import check_annotation_status, run_preprocessing_pipeline
  if not check_annotation_status(adata):
      adata = run_preprocessing_pipeline(adata, species="human")

  # CLI
  python preprocess.py --input raw_counts.h5ad --output preprocessed.h5ad
"""

import argparse
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd
import scanpy as sc


# ---------------------------------------------------------------------------
# Annotation status check
# ---------------------------------------------------------------------------

def check_annotation_status(adata):
    """Return True if data already has cell_type, condition, and sample_id.

    Parameters
    ----------
    adata : AnnData
        AnnData object to inspect.

    Returns
    -------
    bool
        True when all three annotation columns are present and populated.
    """
    required = ["cell_type", "condition", "sample_id"]
    for col in required:
        if col not in adata.obs.columns:
            return False
        if adata.obs[col].isna().all():
            return False
    return True


# ---------------------------------------------------------------------------
# Preprocessing pipeline
# ---------------------------------------------------------------------------

def run_preprocessing_pipeline(
    adata,
    species="human",
    min_genes=200,
    min_cells=3,
    n_mads=5,
    target_sum=1e4,
    n_top_genes=2000,
    n_pcs=50,
    n_neighbors=15,
    leiden_resolution=1.0,
    celltypist_model=None,
    random_state=0,
):
    """Run the full preprocessing pipeline on raw scRNA-seq counts.

    Steps:
      1. QC metrics (gene counts, total counts, mitochondrial %)
      2. MAD-based outlier filtering
      3. Doublet detection with Scrublet
      4. Normalization (target_sum + log1p)
      5. Highly variable gene selection
      6. PCA
      7. Neighbor graph
      8. Leiden clustering
      9. UMAP
     10. CellTypist automated annotation

    Parameters
    ----------
    adata : AnnData
        Raw count matrix (cells x genes).
    species : str, optional
        Species for mitochondrial gene prefix ("human" or "mouse").
    min_genes : int, optional
        Minimum genes per cell (default: 200).
    min_cells : int, optional
        Minimum cells per gene (default: 3).
    n_mads : int, optional
        Number of MADs for outlier detection (default: 5).
    target_sum : float, optional
        Target sum for normalization (default: 1e4).
    n_top_genes : int, optional
        Number of highly variable genes to select (default: 2000).
    n_pcs : int, optional
        Number of principal components (default: 50).
    n_neighbors : int, optional
        Number of neighbors for the kNN graph (default: 15).
    leiden_resolution : float, optional
        Resolution parameter for Leiden clustering (default: 1.0).
    celltypist_model : str or None, optional
        CellTypist model name. If None, uses the default Immune_All_Low model.
    random_state : int, optional
        Random seed for reproducibility (default: 0).

    Returns
    -------
    AnnData
        Fully preprocessed and annotated AnnData object with standardized
        ``cell_type`` column in ``.obs``.
    """
    n_cells_start = adata.n_obs
    n_genes_start = adata.n_vars
    print(f"Starting preprocessing pipeline: {n_cells_start} cells, "
          f"{n_genes_start} genes")

    # Ensure var_names are unique
    adata.var_names_make_unique()

    # ------------------------------------------------------------------
    # Step 1: QC metrics
    # ------------------------------------------------------------------
    print("\n[Step 1/10] Computing QC metrics...")
    mt_prefix = "MT-" if species == "human" else "mt-"
    adata.var["mt"] = adata.var_names.str.startswith(mt_prefix)
    sc.pp.calculate_qc_metrics(
        adata, qc_vars=["mt"], percent_top=None, log1p=False, inplace=True
    )
    print(f"  Median genes/cell: {adata.obs['n_genes_by_counts'].median():.0f}")
    print(f"  Median counts/cell: {adata.obs['total_counts'].median():.0f}")
    print(f"  Median MT%: {adata.obs['pct_counts_mt'].median():.1f}%")

    # ------------------------------------------------------------------
    # Step 2: MAD-based outlier filtering
    # ------------------------------------------------------------------
    print(f"\n[Step 2/10] Filtering outliers (MAD method, n_mads={n_mads})...")
    adata = _filter_by_mad(adata, n_mads=n_mads, min_genes=min_genes)
    print(f"  Cells after MAD filtering: {adata.n_obs}")

    # Basic gene filter
    sc.pp.filter_genes(adata, min_cells=min_cells)
    print(f"  Genes after min_cells={min_cells} filter: {adata.n_vars}")

    # ------------------------------------------------------------------
    # Step 3: Doublet detection
    # ------------------------------------------------------------------
    print("\n[Step 3/10] Running doublet detection (Scrublet)...")
    adata = _run_scrublet(adata, random_state=random_state)
    n_doublets = adata.obs["predicted_doublet"].sum()
    print(f"  Predicted doublets: {n_doublets}")
    adata = adata[~adata.obs["predicted_doublet"]].copy()
    print(f"  Cells after doublet removal: {adata.n_obs}")

    # ------------------------------------------------------------------
    # Step 4: Normalization
    # ------------------------------------------------------------------
    print("\n[Step 4/10] Normalizing (target_sum={:.0f} + log1p)...".format(
        target_sum))
    # Store raw counts before normalization
    adata.layers["counts"] = adata.X.copy()
    sc.pp.normalize_total(adata, target_sum=target_sum)
    sc.pp.log1p(adata)

    # ------------------------------------------------------------------
    # Step 5: HVG selection
    # ------------------------------------------------------------------
    print(f"\n[Step 5/10] Selecting {n_top_genes} highly variable genes...")
    sc.pp.highly_variable_genes(
        adata, n_top_genes=n_top_genes, flavor="seurat_v3",
        layer="counts", subset=False
    )
    n_hvg = adata.var["highly_variable"].sum()
    print(f"  HVGs selected: {n_hvg}")

    # ------------------------------------------------------------------
    # Step 6: PCA
    # ------------------------------------------------------------------
    print(f"\n[Step 6/10] Running PCA (n_pcs={n_pcs})...")
    sc.tl.pca(adata, n_comps=n_pcs, use_highly_variable=True,
              random_state=random_state)
    print(f"  Variance explained by PC1: "
          f"{adata.uns['pca']['variance_ratio'][0]:.2%}")

    # ------------------------------------------------------------------
    # Step 7: Neighbor graph
    # ------------------------------------------------------------------
    print(f"\n[Step 7/10] Building neighbor graph (n_neighbors={n_neighbors})...")
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs,
                    random_state=random_state)

    # ------------------------------------------------------------------
    # Step 8: Leiden clustering
    # ------------------------------------------------------------------
    print(f"\n[Step 8/10] Leiden clustering (resolution={leiden_resolution})...")
    sc.tl.leiden(adata, resolution=leiden_resolution, random_state=random_state)
    n_clusters = adata.obs["leiden"].nunique()
    print(f"  Clusters found: {n_clusters}")

    # ------------------------------------------------------------------
    # Step 9: UMAP
    # ------------------------------------------------------------------
    print("\n[Step 9/10] Computing UMAP embedding...")
    sc.tl.umap(adata, random_state=random_state)

    # ------------------------------------------------------------------
    # Step 10: CellTypist annotation
    # ------------------------------------------------------------------
    print("\n[Step 10/10] Annotating cell types with CellTypist...")
    adata = _annotate_celltypist(adata, model_name=celltypist_model)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    n_cells_final = adata.n_obs
    n_types = adata.obs["cell_type"].nunique()
    print(f"\nPreprocessing complete! {n_cells_final} cells retained, "
          f"{n_types} cell types annotated")
    print(f"  Cells removed: {n_cells_start - n_cells_final} "
          f"({100 * (n_cells_start - n_cells_final) / n_cells_start:.1f}%)")
    print(f"  Cell type distribution:")
    for ct, count in adata.obs["cell_type"].value_counts().items():
        print(f"    {ct}: {count}")

    return adata


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_outlier(series, n_mads=5):
    """Flag values more than *n_mads* MADs from the median.

    Parameters
    ----------
    series : pd.Series
        Numeric values to evaluate.
    n_mads : int
        Number of median absolute deviations.

    Returns
    -------
    pd.Series of bool
    """
    median = series.median()
    mad = np.median(np.abs(series - median))
    # Avoid zero MAD (constant column)
    if mad == 0:
        return pd.Series(False, index=series.index)
    lower = median - n_mads * mad
    upper = median + n_mads * mad
    return (series < lower) | (series > upper)


def _filter_by_mad(adata, n_mads=5, min_genes=200):
    """Filter cells using MAD-based outlier detection on QC metrics.

    Parameters
    ----------
    adata : AnnData
        AnnData with QC metrics already computed.
    n_mads : int
        Number of MADs for outlier detection.
    min_genes : int
        Hard minimum gene count.

    Returns
    -------
    AnnData
        Filtered AnnData (copy).
    """
    outlier = (
        _is_outlier(adata.obs["n_genes_by_counts"], n_mads)
        | _is_outlier(adata.obs["total_counts"], n_mads)
        | _is_outlier(adata.obs["pct_counts_mt"], n_mads)
        | (adata.obs["n_genes_by_counts"] < min_genes)
    )
    n_removed = outlier.sum()
    print(f"  MAD outliers flagged: {n_removed}")
    return adata[~outlier].copy()


def _run_scrublet(adata, random_state=0):
    """Detect doublets with Scrublet.

    Parameters
    ----------
    adata : AnnData
        AnnData with raw or normalised counts.
    random_state : int
        Random seed.

    Returns
    -------
    AnnData
        Same object with ``doublet_score`` and ``predicted_doublet`` in .obs.
    """
    try:
        import scrublet as scr
    except ImportError:
        print("  WARNING: scrublet not installed. Skipping doublet detection.",
              file=sys.stderr)
        print("  Install with: pip install scrublet", file=sys.stderr)
        adata.obs["doublet_score"] = 0.0
        adata.obs["predicted_doublet"] = False
        return adata

    # Estimate expected doublet rate (~0.8% per 1000 cells on 10X)
    n_cells = adata.n_obs
    expected_rate = max(0.01, min(0.008 * (n_cells / 1000), 0.15))

    scrub = scr.Scrublet(adata.X, expected_doublet_rate=expected_rate,
                         random_state=random_state)
    scores, predictions = scrub.scrub_doublets(
        min_counts=2, min_cells=3, min_gene_variability_pctl=85,
        n_prin_comps=30, verbose=False,
    )

    adata.obs["doublet_score"] = scores
    adata.obs["predicted_doublet"] = predictions
    return adata


def _annotate_celltypist(adata, model_name=None):
    """Annotate cell types using CellTypist.

    Parameters
    ----------
    adata : AnnData
        Normalised, log-transformed AnnData.
    model_name : str or None
        CellTypist model. Defaults to ``Immune_All_Low.pkl``.

    Returns
    -------
    AnnData
        Same object with ``cell_type`` added to .obs.
    """
    try:
        import celltypist
        from celltypist import models
    except ImportError:
        print("  WARNING: celltypist not installed. Falling back to Leiden "
              "cluster labels.", file=sys.stderr)
        print("  Install with: pip install celltypist", file=sys.stderr)
        adata.obs["cell_type"] = adata.obs["leiden"].copy()
        return adata

    if model_name is None:
        model_name = "Immune_All_Low.pkl"

    print(f"  Downloading/loading model: {model_name}")
    try:
        models.download_models(model=model_name)
        model = models.Model.load(model=model_name)
    except Exception as e:
        print(f"  WARNING: Could not load CellTypist model '{model_name}': {e}",
              file=sys.stderr)
        print("  Falling back to Leiden cluster labels.", file=sys.stderr)
        adata.obs["cell_type"] = adata.obs["leiden"].copy()
        return adata

    predictions = celltypist.annotate(
        adata, model=model, majority_voting=True
    )
    adata.obs["cell_type"] = predictions.predicted_labels[
        "majority_voting"
    ].values
    adata.obs["celltypist_conf_score"] = predictions.predicted_labels[
        "conf_score"
    ].values

    return adata


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Preprocess raw scRNA-seq data for disease drug discovery"
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to raw AnnData (.h5ad) or 10X directory"
    )
    parser.add_argument(
        "--output", default=None,
        help="Output path for preprocessed .h5ad (default: <input>_preprocessed.h5ad)"
    )
    parser.add_argument(
        "--species", default="human", choices=["human", "mouse"],
        help="Species (default: human)"
    )
    parser.add_argument(
        "--n-top-genes", type=int, default=2000,
        help="Number of highly variable genes (default: 2000)"
    )
    parser.add_argument(
        "--n-pcs", type=int, default=50,
        help="Number of principal components (default: 50)"
    )
    parser.add_argument(
        "--leiden-resolution", type=float, default=1.0,
        help="Leiden clustering resolution (default: 1.0)"
    )
    parser.add_argument(
        "--celltypist-model", default=None,
        help="CellTypist model name (default: Immune_All_Low.pkl)"
    )
    parser.add_argument(
        "--random-state", type=int, default=0,
        help="Random seed (default: 0)"
    )
    args = parser.parse_args()

    # Load raw data
    input_path = args.input
    if os.path.isdir(input_path):
        print(f"Loading 10X directory: {input_path}")
        adata = sc.read_10x_mtx(input_path, var_names="gene_symbols")
    elif input_path.endswith(".h5"):
        print(f"Loading 10X H5: {input_path}")
        adata = sc.read_10x_h5(input_path)
    elif input_path.endswith(".h5ad"):
        print(f"Loading H5AD: {input_path}")
        adata = sc.read_h5ad(input_path)
    else:
        print(f"ERROR: Unsupported input format: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Check if already annotated
    if check_annotation_status(adata):
        print("Data is already annotated (cell_type, condition, sample_id present).")
        print("Skipping preprocessing. Use load_data.py instead.")
        sys.exit(0)

    # Run pipeline
    adata = run_preprocessing_pipeline(
        adata,
        species=args.species,
        n_top_genes=args.n_top_genes,
        n_pcs=args.n_pcs,
        leiden_resolution=args.leiden_resolution,
        celltypist_model=args.celltypist_model,
        random_state=args.random_state,
    )

    # Save
    output_path = args.output
    if output_path is None:
        base = os.path.splitext(input_path)[0]
        output_path = f"{base}_preprocessed.h5ad"

    print(f"\nSaving preprocessed data to {output_path}...")
    adata.write_h5ad(output_path)
    print("Done.")
