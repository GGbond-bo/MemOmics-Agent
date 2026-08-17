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
PSEUDOBULK DIFFERENTIAL EXPRESSION ANALYSIS
============================================================================

Per-cell-type differential expression using pseudobulk aggregation + PyDESeq2.
Automatically falls back to cell-level Wilcoxon DE when fewer than 2 biological
replicates are available per condition.

Functions:
  - run_pseudobulk_de(): Pseudobulk aggregation + PyDESeq2 per cell type
  - run_cell_level_de(): Fallback Wilcoxon rank-sum DE per cell type
  - get_disease_signature_genes(): Extract significant DEGs across cell types

Usage:
  from pseudobulk_de import run_pseudobulk_de, get_disease_signature_genes
  de_results = run_pseudobulk_de(adata, reference="Healthy")
  sig_genes = get_disease_signature_genes(de_results)

  # CLI
  python pseudobulk_de.py --input annotated.h5ad --reference Healthy
"""

import argparse
import os
import sys
import warnings
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import scanpy as sc


def _save_de_incremental(df, celltype, output_dir):
    """Save DE results immediately after computation (OOM resilience).

    NEVER rely on end-of-pipeline export — if the pipeline crashes,
    partial results are lost and agents may reconstruct from memory.
    """
    safe_name = str(celltype).replace(" ", "_").replace("/", "-")
    path = os.path.join(output_dir, f"de_results_{safe_name}.csv")
    try:
        df.to_csv(path, index=False)
        print(f"    Saved: {path}")
    except Exception as e:
        print(f"    WARNING: Failed to save {path}: {e}")


# ---------------------------------------------------------------------------
# Main pseudobulk DE
# ---------------------------------------------------------------------------

def run_pseudobulk_de(
    adata,
    condition_key="condition",
    sample_key="sample_id",
    celltype_key="cell_type",
    reference="Healthy",
    min_cells=5,
    min_counts_per_gene=10,
    min_samples_per_gene=3,
    layer=None,
):
    """Pseudobulk DE analysis per cell type using PyDESeq2.

    For each cell type the function aggregates single-cell counts to sample-
    level pseudobulk (sum), then runs PyDESeq2 to compare disease vs the
    reference condition.  When fewer than 2 biological replicates are available
    in either group, the function automatically falls back to cell-level
    Wilcoxon rank-sum DE and prints a warning.

    Parameters
    ----------
    adata : AnnData
        Annotated AnnData.  Must contain raw integer counts in ``.X`` (or in
        the layer specified by *layer*).
    condition_key : str, optional
        Column in ``adata.obs`` with condition labels (default: ``"condition"``).
    sample_key : str, optional
        Column in ``adata.obs`` with biological sample IDs
        (default: ``"sample_id"``).
    celltype_key : str, optional
        Column in ``adata.obs`` with cell type labels
        (default: ``"cell_type"``).
    reference : str, optional
        Reference condition label (default: ``"Healthy"``).
    min_cells : int, optional
        Minimum cells per sample-celltype combination (default: 10).
    min_counts_per_gene : int, optional
        Minimum total counts across samples to retain a gene (default: 10).
    min_samples_per_gene : int, optional
        Minimum samples with counts >= 1 to retain a gene (default: 3).
    layer : str or None, optional
        Layer containing raw counts.  ``None`` uses ``.X``.

    Returns
    -------
    dict of {str: DataFrame}
        Mapping of cell type name to a DataFrame with columns:
        ``gene``, ``log2FoldChange``, ``padj``, ``baseMean``.
    """
    # ------------------------------------------------------------------
    # Validate inputs
    # ------------------------------------------------------------------
    for col, name in [(condition_key, "condition_key"),
                      (sample_key, "sample_key"),
                      (celltype_key, "celltype_key")]:
        if col not in adata.obs.columns:
            print(f"ERROR: '{col}' ({name}) not found in adata.obs. "
                  f"Available: {list(adata.obs.columns)}", file=sys.stderr)
            sys.exit(1)

    conditions = adata.obs[condition_key].unique().tolist()
    if reference not in conditions:
        print(f"ERROR: Reference '{reference}' not found in conditions: "
              f"{conditions}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Auto-detect raw counts layer (CRITICAL for DESeq2 correctness)
    # ------------------------------------------------------------------
    if layer is None:
        if "counts" in adata.layers:
            layer = "counts"
            print("  Auto-detected raw counts in adata.layers['counts']")
        elif "raw_counts" in adata.layers:
            layer = "raw_counts"
            print("  Auto-detected raw counts in adata.layers['raw_counts']")
        else:
            # Check if .X looks like counts (integers) or normalized (floats)
            import scipy.sparse as sp
            sample = adata.X[:100] if not sp.issparse(adata.X) else adata.X[:100].toarray()
            frac_integer = np.mean(np.equal(np.mod(sample, 1), 0))
            max_val = np.max(sample)
            if frac_integer < 0.5 or (max_val < 20 and frac_integer < 0.9):
                print("  WARNING: adata.X appears to contain log-normalized data "
                      "(not raw counts). DESeq2 requires raw integer counts.",
                      file=sys.stderr)
                print("  WARNING: If adata.layers['counts'] exists, pass "
                      "layer='counts'. Results may be unreliable.", file=sys.stderr)
            else:
                print("  Using raw counts from adata.X")

    # Determine disease condition(s)
    disease_conditions = [c for c in conditions if c != reference]
    print(f"Conditions: {conditions}")
    print(f"Reference: {reference}")
    print(f"Disease: {disease_conditions}")

    # ------------------------------------------------------------------
    # Check replicate availability
    # ------------------------------------------------------------------
    can_pseudobulk = _check_replicates(adata, condition_key, sample_key)

    if not can_pseudobulk:
        print("\nWARNING: Fewer than 2 biological replicates per condition.",
              file=sys.stderr)
        print("Falling back to cell-level Wilcoxon DE (exploratory only).",
              file=sys.stderr)
        return run_cell_level_de(
            adata,
            condition_key=condition_key,
            celltype_key=celltype_key,
        )

    # ------------------------------------------------------------------
    # Run pseudobulk DE per cell type
    # ------------------------------------------------------------------
    celltypes = adata.obs[celltype_key].unique()
    print(f"\nRunning pseudobulk DE for {len(celltypes)} cell types...")

    # Set up incremental save directory for data integrity (OOM resilience)
    output_dir = os.environ.get("SCRNA_RESULTS_DIR", "results")
    os.makedirs(output_dir, exist_ok=True)
    print(f"  Saving DE results incrementally to {output_dir}/ (OOM-resilient)")

    de_results = {}
    total_degs = 0

    for ct in sorted(celltypes):
        print(f"\n  --- {ct} ---")
        ct_adata = adata[adata.obs[celltype_key] == ct].copy()

        # Aggregate to pseudobulk
        pb = _aggregate_pseudobulk(
            ct_adata,
            sample_key=sample_key,
            condition_key=condition_key,
            min_cells=min_cells,
            layer=layer,
        )
        if pb is None:
            print(f"  Skipped (insufficient cells per sample).")
            continue

        counts_df, sample_meta = pb

        # Check per-cell-type replicates
        ref_n = (sample_meta[condition_key] == reference).sum()
        dis_n = (sample_meta[condition_key] != reference).sum()
        print(f"  Samples: {ref_n} reference, {dis_n} disease")

        if ref_n < 2 or dis_n < 2:
            print(f"  Skipped (need >=2 samples per group).")
            continue

        # Filter lowly expressed genes
        keep_genes = (
            (counts_df.sum(axis=1) >= min_counts_per_gene)
            & ((counts_df > 0).sum(axis=1) >= min_samples_per_gene)
        )
        counts_df = counts_df.loc[keep_genes]
        print(f"  Genes tested: {counts_df.shape[0]}")

        if counts_df.shape[0] == 0:
            print(f"  Skipped (no genes pass filters).")
            continue

        # Run PyDESeq2
        result_df = _run_pydeseq2(
            counts_df, sample_meta, condition_key, reference
        )
        if result_df is not None and len(result_df) > 0:
            n_sig = (result_df["padj"] < 0.05).sum()
            padj_range = result_df["padj"].max() - result_df["padj"].min()
            n_sig_loose = (result_df["padj"] < 0.1).sum()

            # Detect degenerate results (dispersion estimation failure)
            if n_sig_loose == 0 and padj_range < 0.01:
                print(f"  WARNING: DESeq2 produced degenerate results "
                      f"(0 sig genes, padj range {padj_range:.4f}). "
                      f"Falling back to Wilcoxon for {ct}.",
                      file=sys.stderr)
                # Fall back to cell-level Wilcoxon for this cell type
                ct_adata_wilcox = adata[adata.obs[celltype_key] == ct].copy()
                try:
                    import scanpy as sc
                    sc.tl.rank_genes_groups(
                        ct_adata_wilcox, groupby=condition_key,
                        reference=reference, method="wilcoxon",
                        use_raw=False,
                    )
                    wilcox_df = sc.get.rank_genes_groups_df(
                        ct_adata_wilcox, group=None
                    )
                    wilcox_df = wilcox_df.rename(columns={
                        "names": "gene",
                        "logfoldchanges": "log2FoldChange",
                        "pvals_adj": "padj",
                    })
                    wilcox_df = wilcox_df[["gene", "log2FoldChange", "padj"]].copy()
                    wilcox_df["baseMean"] = 0.0
                    wilcox_df["de_method"] = "wilcoxon_fallback"
                    de_results[ct] = wilcox_df
                    n_sig = (wilcox_df["padj"] < 0.05).sum()
                    total_degs += n_sig
                    print(f"  Wilcoxon fallback DEGs (padj < 0.05): {n_sig}")
                    # Incremental save for OOM resilience
                    _save_de_incremental(wilcox_df, ct, output_dir)
                except Exception as e:
                    print(f"  Wilcoxon fallback failed for {ct}: {e}",
                          file=sys.stderr)
            else:
                de_results[ct] = result_df
                total_degs += n_sig
                print(f"  Significant DEGs (padj < 0.05): {n_sig}")
                # Incremental save for OOM resilience
                _save_de_incremental(result_df, ct, output_dir)

    n_tested = len(de_results)
    print(f"\nDE analysis complete! {n_tested} cell types tested, "
          f"{total_degs} total DEGs")

    return de_results


# ---------------------------------------------------------------------------
# Cell-level DE fallback
# ---------------------------------------------------------------------------

def run_cell_level_de(
    adata,
    condition_key="condition",
    celltype_key="cell_type",
    method="wilcoxon",
    n_genes=None,
):
    """Wilcoxon rank-sum cell-level DE as fallback for N=1 designs.

    This is an exploratory method only -- it treats individual cells as
    independent observations, inflating statistical power (pseudoreplication).
    Use results with appropriate caveats.

    Parameters
    ----------
    adata : AnnData
        Annotated AnnData (normalised + log-transformed).
    condition_key : str, optional
        Column in ``adata.obs`` with condition labels.
    celltype_key : str, optional
        Column in ``adata.obs`` with cell type labels.
    method : str, optional
        Method for ``scanpy.tl.rank_genes_groups`` (default: ``"wilcoxon"``).
    n_genes : int or None, optional
        Number of top genes to return per group.  ``None`` returns all.

    Returns
    -------
    dict of {str: DataFrame}
        Same format as ``run_pseudobulk_de``: mapping of cell type to a
        DataFrame with ``gene``, ``log2FoldChange``, ``padj``, ``baseMean``.
    """
    print("\nRunning cell-level DE (Wilcoxon rank-sum)...")
    print("  NOTE: This is exploratory only -- pseudoreplication caveat applies.")

    celltypes = adata.obs[celltype_key].unique()
    de_results = {}
    total_degs = 0

    for ct in sorted(celltypes):
        ct_adata = adata[adata.obs[celltype_key] == ct].copy()

        # Need at least two conditions represented
        ct_conditions = ct_adata.obs[condition_key].unique()
        if len(ct_conditions) < 2:
            print(f"  {ct}: skipped (only one condition present)")
            continue

        print(f"  {ct}: {ct_adata.n_obs} cells, "
              f"{len(ct_conditions)} conditions")

        try:
            sc.tl.rank_genes_groups(
                ct_adata,
                groupby=condition_key,
                method=method,
                n_genes=n_genes if n_genes else ct_adata.n_vars,
            )
        except Exception as e:
            print(f"  {ct}: rank_genes_groups failed: {e}", file=sys.stderr)
            continue

        # Extract results for each non-reference group
        result = sc.get.rank_genes_groups_df(ct_adata, group=None)
        if result is None or len(result) == 0:
            continue

        # Standardize columns to match pseudobulk output
        result_df = result.rename(columns={
            "names": "gene",
            "logfoldchanges": "log2FoldChange",
            "pvals_adj": "padj",
        })

        # Add baseMean as mean expression across all cells of this type
        if hasattr(ct_adata.X, "toarray"):
            mean_expr = np.array(ct_adata.X.toarray().mean(axis=0)).flatten()
        else:
            mean_expr = np.array(ct_adata.X.mean(axis=0)).flatten()
        gene_means = pd.Series(mean_expr, index=ct_adata.var_names)
        result_df["baseMean"] = result_df["gene"].map(gene_means).values

        # Keep standard columns
        result_df = result_df[["gene", "log2FoldChange", "padj", "baseMean"]]
        result_df = result_df.dropna(subset=["padj"])

        de_results[ct] = result_df
        n_sig = (result_df["padj"] < 0.05).sum()
        total_degs += n_sig
        print(f"    DEGs (padj < 0.05): {n_sig}")

    n_tested = len(de_results)
    print(f"\nDE analysis complete! {n_tested} cell types tested, "
          f"{total_degs} total DEGs")

    return de_results


# ---------------------------------------------------------------------------
# Signature gene extraction
# ---------------------------------------------------------------------------

def get_disease_signature_genes(
    de_results,
    padj_threshold=0.05,
    log2fc_threshold=0.5,
):
    """Extract significant DEGs from all cell types.

    Parameters
    ----------
    de_results : dict of {str: DataFrame}
        Output from ``run_pseudobulk_de`` or ``run_cell_level_de``.
    padj_threshold : float, optional
        Maximum adjusted p-value (default: 0.05).
    log2fc_threshold : float, optional
        Minimum absolute log2 fold change (default: 0.5).

    Returns
    -------
    dict of {str: list of str}
        Mapping of cell type to a list of significant gene names.
    """
    sig_genes = {}

    for ct, df in de_results.items():
        mask = (
            (df["padj"] < padj_threshold)
            & (df["log2FoldChange"].abs() > log2fc_threshold)
        )
        genes = df.loc[mask, "gene"].tolist()
        if genes:
            sig_genes[ct] = genes

    total = sum(len(g) for g in sig_genes.values())
    print(f"Disease signature genes: {total} genes across "
          f"{len(sig_genes)} cell types "
          f"(padj < {padj_threshold}, |log2FC| > {log2fc_threshold})")
    for ct, genes in sig_genes.items():
        print(f"  {ct}: {len(genes)} genes")

    return sig_genes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_replicates(adata, condition_key, sample_key):
    """Return True if every condition has >= 2 biological replicates."""
    for cond in adata.obs[condition_key].unique():
        n_samples = adata.obs.loc[
            adata.obs[condition_key] == cond, sample_key
        ].nunique()
        if n_samples < 2:
            print(f"  Condition '{cond}': {n_samples} sample(s) "
                  f"(need >= 2 for pseudobulk)")
            return False
    return True


def _aggregate_pseudobulk(adata, sample_key, condition_key, min_cells=10,
                          layer=None):
    """Sum counts per sample to create pseudobulk profiles.

    Parameters
    ----------
    adata : AnnData
        Subset for one cell type.
    sample_key : str
        Sample column.
    condition_key : str
        Condition column.
    min_cells : int
        Minimum cells per sample.
    layer : str or None
        Layer with raw counts.

    Returns
    -------
    tuple of (DataFrame, DataFrame) or None
        (counts_df [genes x samples], sample_metadata) or None if all
        samples are below the cell threshold.
    """
    # Get count matrix (keep sparse to save memory; aggregate in chunks)
    if layer is not None:
        X = adata.layers[layer]
    else:
        X = adata.X

    import scipy.sparse as sp
    is_sparse = sp.issparse(X)

    samples = adata.obs[sample_key].unique()
    n_vars = adata.n_vars
    sample_list = list(samples)
    sample_idx = {s: i for i, s in enumerate(sample_list)}

    # Chunked aggregation: stream 5000 cells at a time to avoid OOM on large datasets
    CHUNK_SIZE = 5000
    pseudobulk_mat = np.zeros((len(sample_list), n_vars), dtype=np.float64)
    cell_counts = np.zeros(len(sample_list), dtype=np.int64)
    sample_values = adata.obs[sample_key].values

    for start in range(0, adata.n_obs, CHUNK_SIZE):
        end = min(start + CHUNK_SIZE, adata.n_obs)
        chunk = X[start:end]
        if is_sparse:
            chunk = chunk.toarray()
        chunk_samples = sample_values[start:end]
        for i, s in enumerate(chunk_samples):
            si = sample_idx[s]
            pseudobulk_mat[si] += chunk[i]
            cell_counts[si] += 1

    # Filter to samples with >= min_cells
    pseudobulk = {}
    meta_rows = []
    for i, sample in enumerate(sample_list):
        n_cells = int(cell_counts[i])
        if n_cells < min_cells:
            print(f"    Sample '{sample}': {n_cells} cells (< {min_cells}), "
                  f"skipping")
            continue
        pseudobulk[sample] = pseudobulk_mat[i]
        mask = adata.obs[sample_key] == sample
        cond = adata.obs.loc[mask, condition_key].iloc[0]
        meta_rows.append({"sample": sample, condition_key: cond,
                          "n_cells": n_cells})

    if len(pseudobulk) == 0:
        return None

    counts_df = pd.DataFrame(pseudobulk, index=adata.var_names)
    meta_df = pd.DataFrame(meta_rows).set_index("sample")

    # Ensure integer counts
    counts_df = counts_df.round().astype(int)

    return counts_df, meta_df


def _run_pydeseq2(counts_df, sample_meta, condition_key, reference):
    """Run PyDESeq2 on a pseudobulk count matrix.

    Parameters
    ----------
    counts_df : DataFrame
        Genes (rows) x samples (columns) integer counts.
    sample_meta : DataFrame
        Sample metadata with *condition_key* column.  Index = sample IDs.
    condition_key : str
        Column name for the condition factor.
    reference : str
        Reference level for the contrast.

    Returns
    -------
    DataFrame or None
        Columns: ``gene``, ``log2FoldChange``, ``padj``, ``baseMean``.
    """
    try:
        from pydeseq2.dds import DeseqDataSet
        from pydeseq2.ds import DeseqStats
    except ImportError:
        print("ERROR: pydeseq2 is required for pseudobulk DE. "
              "Install with: pip install pydeseq2", file=sys.stderr)
        sys.exit(1)

    # PyDESeq2 expects samples x genes
    counts_t = counts_df.T

    # Align metadata to counts
    common = counts_t.index.intersection(sample_meta.index)
    counts_t = counts_t.loc[common]
    sample_meta = sample_meta.loc[common]

    if len(common) < 4:
        print(f"    Too few samples ({len(common)}) after alignment.")
        return None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            dds = DeseqDataSet(
                counts=counts_t,
                metadata=sample_meta,
                design_factors=condition_key,
                refit_cooks=True,
            )
            dds.deseq2()

            # Determine contrast: disease vs reference
            disease_level = [
                lvl for lvl in sample_meta[condition_key].unique()
                if lvl != reference
            ][0]

            stat_res = DeseqStats(
                dds,
                contrast=[condition_key, disease_level, reference],
            )
            stat_res.summary()

            result = stat_res.results_df.copy()

    except Exception as e:
        print(f"    PyDESeq2 failed: {e}", file=sys.stderr)
        return None

    # Standardize output
    result.index.name = "gene"
    result = result.reset_index()

    # Keep standard columns (PyDESeq2 uses the same names as R DESeq2)
    keep_cols = []
    for col in ["gene", "log2FoldChange", "padj", "baseMean"]:
        if col in result.columns:
            keep_cols.append(col)
    result = result[keep_cols]
    result = result.dropna(subset=["padj"])

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pseudobulk differential expression analysis per cell type"
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to annotated AnnData (.h5ad)"
    )
    parser.add_argument(
        "--output-dir", default="results/pseudobulk_de",
        help="Output directory for DE results (default: results/pseudobulk_de)"
    )
    parser.add_argument(
        "--condition-key", default="condition",
        help="Condition column in adata.obs (default: condition)"
    )
    parser.add_argument(
        "--sample-key", default="sample_id",
        help="Sample ID column in adata.obs (default: sample_id)"
    )
    parser.add_argument(
        "--celltype-key", default="cell_type",
        help="Cell type column in adata.obs (default: cell_type)"
    )
    parser.add_argument(
        "--reference", default="Healthy",
        help="Reference condition label (default: Healthy)"
    )
    parser.add_argument(
        "--layer", default=None,
        help="Layer with raw counts (default: use .X)"
    )
    parser.add_argument(
        "--padj-threshold", type=float, default=0.05,
        help="Adjusted p-value threshold for significance (default: 0.05)"
    )
    parser.add_argument(
        "--log2fc-threshold", type=float, default=0.5,
        help="Absolute log2FC threshold for signature genes (default: 0.5)"
    )
    args = parser.parse_args()

    # Load data
    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading data from {args.input}...")
    adata = sc.read_h5ad(args.input)
    print(f"  {adata.n_obs} cells, {adata.n_vars} genes")

    # Run DE
    de_results = run_pseudobulk_de(
        adata,
        condition_key=args.condition_key,
        sample_key=args.sample_key,
        celltype_key=args.celltype_key,
        reference=args.reference,
        layer=args.layer,
    )

    # Extract signature genes
    sig_genes = get_disease_signature_genes(
        de_results,
        padj_threshold=args.padj_threshold,
        log2fc_threshold=args.log2fc_threshold,
    )

    # Export results
    os.makedirs(args.output_dir, exist_ok=True)

    for ct, df in de_results.items():
        safe_name = ct.replace("/", "_").replace(" ", "_")
        out_path = os.path.join(args.output_dir, f"{safe_name}_de_results.csv")
        df.to_csv(out_path, index=False)
        print(f"  Saved: {out_path}")

    # Save signature gene summary
    sig_rows = []
    for ct, genes in sig_genes.items():
        for g in genes:
            sig_rows.append({"cell_type": ct, "gene": g})
    if sig_rows:
        sig_df = pd.DataFrame(sig_rows)
        sig_path = os.path.join(args.output_dir, "disease_signature_genes.csv")
        sig_df.to_csv(sig_path, index=False)
        print(f"  Saved signature genes: {sig_path}")

    print("\nDone.")
