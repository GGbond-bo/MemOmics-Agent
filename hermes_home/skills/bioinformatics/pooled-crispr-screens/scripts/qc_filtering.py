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

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================
"""
Quality Control Filtering for Pooled CRISPR Screens

Applies standard single-cell QC filters including gene count, UMI count,
and mitochondrial percentage thresholds.
"""

from typing import Optional
import numpy as np
import scanpy as sc
import anndata as ad


def calculate_qc_metrics(
    adata: ad.AnnData,
    mito_prefix: str = "MT-"
) -> ad.AnnData:
    """
    Calculate QC metrics for each cell.

    Parameters
    ----------
    adata : AnnData
        Input AnnData object
    mito_prefix : str, default="MT-"
        Prefix for mitochondrial genes (human: "MT-", mouse: "mt-")

    Returns
    -------
    adata : AnnData
        AnnData with QC metrics added to obs:
        - n_genes: number of detected genes
        - n_counts: total UMI counts
        - percent_mito: fraction of mitochondrial reads
    """
    # Identify mitochondrial genes
    mito_genes = adata.var_names.str.startswith(mito_prefix)
    n_mito_genes = mito_genes.sum()

    print(f"Identified {n_mito_genes} mitochondrial genes")

    # Calculate percent mitochondrial
    # Handle both sparse and dense matrices
    if len(mito_genes) > 0 and mito_genes.sum() > 0:
        mito_counts = np.asarray(adata[:, mito_genes].X.sum(axis=1)).flatten()
        total_counts = np.asarray(adata.X.sum(axis=1)).flatten()
        adata.obs['percent_mito'] = mito_counts / total_counts
    else:
        adata.obs['percent_mito'] = 0.0

    # Add total counts per cell
    adata.obs['n_counts'] = np.asarray(adata.X.sum(axis=1)).flatten()

    print("\nQC Metrics Summary:")
    print(f"  n_genes - Mean: {adata.obs['n_genes'].mean():.0f}, "
          f"Median: {adata.obs['n_genes'].median():.0f}")
    print(f"  n_counts - Mean: {adata.obs['n_counts'].mean():.0f}, "
          f"Median: {adata.obs['n_counts'].median():.0f}")
    print(f"  percent_mito - Mean: {adata.obs['percent_mito'].mean():.3f}, "
          f"Median: {adata.obs['percent_mito'].median():.3f}")

    return adata


def apply_qc_filters(
    adata: ad.AnnData,
    min_genes: int = 2000,
    min_counts: int = 8000,
    max_mito_pct: float = 0.15,
    calculate_metrics: bool = True,
    mito_prefix: str = "MT-"
) -> ad.AnnData:
    """
    Apply QC filters to remove low-quality cells.

    Parameters
    ----------
    adata : AnnData
        Input AnnData object
    min_genes : int, default=2000
        Minimum number of genes detected per cell
    min_counts : int, default=8000
        Minimum total UMI counts per cell
    max_mito_pct : float, default=0.15
        Maximum mitochondrial fraction (0-1 scale)
    calculate_metrics : bool, default=True
        Whether to calculate QC metrics first
    mito_prefix : str, default="MT-"
        Prefix for mitochondrial genes

    Returns
    -------
    adata : AnnData
        Filtered AnnData object

    Example
    -------
    >>> adata_filtered = apply_qc_filters(
    ...     adata,
    ...     min_genes=2000,
    ...     min_counts=8000,
    ...     max_mito_pct=0.15
    ... )
    """
    original_n_cells = adata.n_obs

    if calculate_metrics:
        adata = calculate_qc_metrics(adata, mito_prefix=mito_prefix)

    print("\nApplying QC filters:")
    print(f"  min_genes: {min_genes}")
    print(f"  min_counts: {min_counts}")
    print(f"  max_mito_pct: {max_mito_pct}")

    # Filter cells by minimum genes
    n_before = adata.n_obs
    sc.pp.filter_cells(adata, min_genes=min_genes)
    n_after = adata.n_obs
    print(f"  Filtered {n_before - n_after} cells with <{min_genes} genes")

    # Filter cells by minimum counts
    n_before = adata.n_obs
    sc.pp.filter_cells(adata, min_counts=min_counts)
    n_after = adata.n_obs
    print(f"  Filtered {n_before - n_after} cells with <{min_counts} counts")

    # Filter cells by mitochondrial percentage
    n_before = adata.n_obs
    adata = adata[adata.obs['percent_mito'] < max_mito_pct, :].copy()
    n_after = adata.n_obs
    print(f"  Filtered {n_before - n_after} cells with >{max_mito_pct*100}% mito")

    total_filtered = original_n_cells - adata.n_obs
    retention_rate = adata.n_obs / original_n_cells * 100

    print(f"\nQC Filtering Summary:")
    print(f"  Original cells: {original_n_cells}")
    print(f"  Retained cells: {adata.n_obs} ({retention_rate:.1f}%)")
    print(f"  Filtered cells: {total_filtered}")
    print("✓ QC filtering complete")

    return adata


def plot_qc_metrics(
    adata: ad.AnnData,
    save: Optional[str] = None
) -> None:
    """
    Generate QC metric visualizations.

    Parameters
    ----------
    adata : AnnData
        AnnData with QC metrics in obs
    save : str, optional
        If provided, save figures with this prefix

    Example
    -------
    >>> plot_qc_metrics(adata, save="qc_violin")
    """
    # Violin plots
    sc.pl.violin(
        adata,
        ['n_genes', 'n_counts', 'percent_mito'],
        jitter=0.4,
        multi_panel=True,
        save=f"_{save}_violin.pdf" if save else None
    )

    # Scatter plots
    sc.pl.scatter(
        adata,
        x='n_counts',
        y='percent_mito',
        save=f"_{save}_counts_mito.pdf" if save else None
    )

    sc.pl.scatter(
        adata,
        x='n_counts',
        y='n_genes',
        save=f"_{save}_counts_genes.pdf" if save else None
    )
