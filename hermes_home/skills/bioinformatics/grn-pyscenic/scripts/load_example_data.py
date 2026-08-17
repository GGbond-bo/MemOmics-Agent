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
Load PBMC 3k example dataset for testing pySCENIC workflow.

This script provides a convenient way to load the PBMC 3k dataset from
Scanpy's built-in datasets for testing and demonstration purposes.
"""

import scanpy as sc
import pandas as pd


def load_pbmc3k_example(preprocess=True, subsample=None):
    """
    Load PBMC 3k example dataset for pySCENIC testing.

    This function downloads and loads the PBMC 3k dataset (2,700 PBMCs from
    a healthy donor, 10x Genomics). The dataset is automatically downloaded
    from the Scanpy repository on first use (~20MB).

    Parameters:
    -----------
    preprocess : bool
        Whether to apply basic preprocessing (filtering, normalization).
        Default: True. Set to False if you want raw counts only.
    subsample : int, optional
        Number of cells to subsample for faster testing. If None (default),
        uses all cells (~2,700). Recommended: 500-1000 for quick tests.

    Returns:
    --------
    adata : AnnData
        AnnData object with PBMC 3k data
    ex_matrix : pd.DataFrame
        Expression matrix (cells x genes) as DataFrame

    Examples:
    ---------
    >>> # Quick start with preprocessing
    >>> adata, ex_matrix = load_pbmc3k_example()
    >>> print(f"Loaded {adata.n_obs} cells x {adata.n_vars} genes")

    >>> # Fast testing with subsampled data (~10-15 min)
    >>> adata, ex_matrix = load_pbmc3k_example(subsample=500)

    >>> # Load raw data without preprocessing
    >>> adata, ex_matrix = load_pbmc3k_example(preprocess=False)

    Dataset Information:
    -------------------
    - Source: 10x Genomics, healthy human PBMCs
    - Cells: ~2,700 (after QC) or subsampled
    - Genes: ~13,700 (raw) or ~1,800 (after filtering)
    - Expected cell types: CD4+ T, CD8+ T, B cells, NK, monocytes, dendritic
    - Reference: Zheng et al. (2017) Nature Communications
    """
    print("Loading PBMC 3k example dataset...")
    print("  (First run: downloading ~20MB from Scanpy repository)")

    # Load PBMC 3k dataset
    adata = sc.datasets.pbmc3k()

    if preprocess:
        print("  Applying basic preprocessing...")

        # Basic QC filtering
        sc.pp.filter_cells(adata, min_genes=200)
        sc.pp.filter_genes(adata, min_cells=3)

        # Identify highly variable genes for SCENIC
        # (SCENIC works best with 2,000-5,000 genes)
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.highly_variable_genes(adata, n_top_genes=2000)

        # Keep only highly variable genes for SCENIC
        adata = adata[:, adata.var.highly_variable].copy()

        # Get counts for SCENIC (needs counts, not log-normalized)
        # Re-load and filter to same genes
        adata_raw = sc.datasets.pbmc3k()
        sc.pp.filter_cells(adata_raw, min_genes=200)
        sc.pp.filter_genes(adata_raw, min_cells=3)
        adata_raw = adata_raw[:, adata.var_names].copy()
        adata = adata_raw

        print(f"  Filtered to {adata.n_vars} highly variable genes")

    # Subsample cells if requested (for faster testing)
    if subsample is not None and adata.n_obs > subsample:
        print(f"  Subsampling {subsample} cells from {adata.n_obs}...")
        sc.pp.subsample(adata, n_obs=subsample)
        print(f"  Subsampled to {adata.n_obs} cells")

    # Estimate runtime based on dataset size
    if adata.n_obs < 1000:
        runtime_estimate = "~10-15 minutes"
    elif adata.n_obs < 2000:
        runtime_estimate = "~20-30 minutes"
    else:
        runtime_estimate = "~30-45 minutes"

    print(f"✓ Example data loaded successfully: {adata.n_obs} cells, {adata.n_vars} genes")
    print(f"  Expected runtime for GRN inference: {runtime_estimate}")

    # Get expression matrix as DataFrame (cells x genes)
    if hasattr(adata.X, 'toarray'):
        ex_matrix = pd.DataFrame(
            adata.X.toarray(),
            index=adata.obs_names,
            columns=adata.var_names
        )
    else:
        ex_matrix = pd.DataFrame(
            adata.X,
            index=adata.obs_names,
            columns=adata.var_names
        )

    return adata, ex_matrix


def load_pbmc68k_example():
    """
    Load PBMC 68k example dataset for larger-scale testing.

    WARNING: This dataset is much larger (~68,000 cells) and will require:
    - More memory (32GB+ RAM recommended)
    - Longer runtime (2-4 hours for GRN inference)
    - More disk space for databases and results

    Returns:
    --------
    adata : AnnData
        AnnData object with PBMC 68k data
    ex_matrix : pd.DataFrame
        Expression matrix (cells x genes) as DataFrame

    Examples:
    ---------
    >>> # For testing scalability (requires significant resources)
    >>> adata, ex_matrix = load_pbmc68k_example()
    """
    print("Loading PBMC 68k example dataset...")
    print("  WARNING: Large dataset - requires 32GB+ RAM and 2-4 hours")
    print("  (First run: downloading ~200MB)")

    adata = sc.datasets.pbmc68k_reduced()

    # Basic filtering
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_genes(adata, min_cells=3)

    # For very large datasets, subsample or filter to top variable genes
    print("  Filtering to top 2,000 highly variable genes...")
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, n_top_genes=2000)
    adata = adata[:, adata.var.highly_variable].copy()

    # Re-load raw counts
    adata_raw = sc.datasets.pbmc68k_reduced()
    sc.pp.filter_cells(adata_raw, min_genes=200)
    sc.pp.filter_genes(adata_raw, min_cells=3)
    adata_raw = adata_raw[:, adata.var_names].copy()
    adata = adata_raw

    print(f"✓ Example data loaded: {adata.n_obs} cells, {adata.n_vars} genes")

    if hasattr(adata.X, 'toarray'):
        ex_matrix = pd.DataFrame(
            adata.X.toarray(),
            index=adata.obs_names,
            columns=adata.var_names
        )
    else:
        ex_matrix = pd.DataFrame(
            adata.X,
            index=adata.obs_names,
            columns=adata.var_names
        )

    return adata, ex_matrix


if __name__ == "__main__":
    """Quick test of example data loading."""
    print("Testing PBMC 3k example data loader...")
    adata, ex_matrix = load_pbmc3k_example()

    print("\nDataset summary:")
    print(f"  Cells: {adata.n_obs}")
    print(f"  Genes: {adata.n_vars}")
    print(f"  Matrix shape: {ex_matrix.shape}")
    print(f"  Matrix type: {type(ex_matrix)}")
    print(f"  Memory usage: {ex_matrix.memory_usage(deep=True).sum() / 1e6:.1f} MB")

    print("\nExample data ready for pySCENIC workflow!")
    print("Next steps:")
    print("  1. Download cisTarget databases (see references/database_downloads.md)")
    print("  2. Run: python scripts/run_grn_workflow.py")
