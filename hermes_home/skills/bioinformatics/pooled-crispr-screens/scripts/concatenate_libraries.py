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
Concatenate Multiple Libraries

Merge filtered libraries into a single AnnData object with batch labels.
"""

import scanpy as sc
import anndata as ad
from typing import List, Optional
import warnings


def concatenate_libraries(
    adata_list: List[ad.AnnData],
    batch_labels: Optional[List[str]] = None,
    batch_key: str = 'batch'
) -> ad.AnnData:
    """
    Concatenate multiple AnnData objects (libraries) into one.

    Parameters
    ----------
    adata_list : list of AnnData
        List of filtered AnnData objects to concatenate
    batch_labels : list of str, optional
        Labels for each batch (e.g., ["lib1", "lib2", "lib3"])
        If None, uses numeric labels (0, 1, 2, ...)
    batch_key : str, default='batch'
        Column name for batch labels in obs

    Returns
    -------
    adata_combined : AnnData
        Concatenated AnnData object with batch labels

    Example
    -------
    >>> adata_combined = concatenate_libraries(
    ...     [adata1_filtered, adata2_filtered, adata3_filtered, adata4_filtered],
    ...     batch_labels=["lib1", "lib2", "lib3", "lib4"]
    ... )
    """
    print(f"Concatenating {len(adata_list)} libraries...")

    # Print summary of each library
    for i, adata in enumerate(adata_list):
        label = batch_labels[i] if batch_labels else f"batch_{i}"
        print(f"  {label}: {adata.n_obs} cells x {adata.n_vars} genes")

        # Check for required columns
        if 'gene' in adata.obs.columns:
            n_genes = adata.obs['gene'].nunique()
            print(f"    Unique perturbations: {n_genes}")

    # Concatenate using modern anndata.concat (not deprecated concatenate method)
    if batch_labels:
        # Add batch labels to each AnnData
        for i, adata in enumerate(adata_list):
            adata.obs[batch_key] = batch_labels[i]

        adata_combined = ad.concat(
            adata_list,
            join='outer',
            label=None,  # We already added batch labels above
            keys=None,
            index_unique=None
        )
    else:
        # Simple concatenation without batch labels
        adata_combined = ad.concat(
            adata_list,
            join='outer'
        )

    print(f"\nCombined dataset:")
    print(f"  Total cells: {adata_combined.n_obs}")
    print(f"  Total genes: {adata_combined.n_vars}")

    if 'gene' in adata_combined.obs.columns:
        n_unique_genes = adata_combined.obs['gene'].nunique()
        print(f"  Unique perturbations: {n_unique_genes}")

        if 'sgRNA' in adata_combined.obs.columns:
            n_unique_sgrnas = adata_combined.obs['sgRNA'].nunique()
            print(f"  Unique sgRNAs: {n_unique_sgrnas}")

        # Summary per perturbation
        cells_per_gene = adata_combined.obs.groupby('gene').size()
        print(f"\nCells per perturbation:")
        print(f"  Mean: {cells_per_gene.mean():.1f}")
        print(f"  Median: {cells_per_gene.median():.1f}")
        print(f"  Min: {cells_per_gene.min()}")
        print(f"  Max: {cells_per_gene.max()}")

    print("\n✓ Libraries concatenated successfully!")
    return adata_combined


def check_batch_balance(
    adata: ad.AnnData,
    batch_key: str = 'batch',
    gene_key: str = 'gene'
) -> None:
    """
    Check balance of perturbations across batches.

    Parameters
    ----------
    adata : AnnData
        Combined AnnData with batch labels
    batch_key : str, default='batch'
        Column name for batch labels
    gene_key : str, default='gene'
        Column name for perturbation labels
    """
    import pandas as pd

    # Cross-tabulation
    crosstab = pd.crosstab(
        adata.obs[gene_key],
        adata.obs[batch_key]
    )

    print("\nBatch Balance Check:")
    print(f"  Total perturbations: {len(crosstab)}")
    print(f"  Perturbations in all batches: {(crosstab > 0).all(axis=1).sum()}")
    print(f"  Perturbations in only 1 batch: {(crosstab > 0).sum(axis=1).eq(1).sum()}")

    # Most imbalanced perturbations
    print("\nMost batch-imbalanced perturbations (coefficient of variation):")
    cv = crosstab.std(axis=1) / crosstab.mean(axis=1)
    print(cv.nlargest(10))
