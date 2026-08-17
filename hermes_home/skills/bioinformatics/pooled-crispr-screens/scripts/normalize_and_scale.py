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
Normalization and Scaling

Normalize counts, log-transform, regress out technical covariates, and scale data.
"""

import scanpy as sc
import anndata as ad
from typing import List, Optional


def normalize_and_scale_data(
    adata: ad.AnnData,
    target_sum: float = 1e6,
    exclude_highly_expressed: bool = True,
    regress_out: Optional[List[str]] = None,
    max_value: float = 10,
    save_raw: bool = True,
    n_jobs: int = 4
) -> ad.AnnData:
    """
    Complete normalization and scaling pipeline.

    Parameters
    ----------
    adata : AnnData
        Input AnnData (filtered, raw counts)
    target_sum : float, default=1e6
        Target sum for normalization (CPM: 1e6, TPM-like: 1e4)
    exclude_highly_expressed : bool, default=True
        Exclude highly expressed genes from normalization factor computation
        (e.g., MALAT1 which can dominate total counts)
    regress_out : list of str, optional
        Variables to regress out (e.g., ['n_counts', 'percent_mito'])
        Set to None to skip regression
    max_value : float, default=10
        Maximum value after scaling (clips outliers)
    save_raw : bool, default=True
        Save log-normalized counts in adata.raw before scaling
    n_jobs : int, default=4
        Number of parallel jobs for regression

    Returns
    -------
    adata : AnnData
        Normalized and scaled AnnData
        - adata.raw: log-normalized counts (if save_raw=True)
        - adata.X: scaled, regressed data

    Example
    -------
    >>> adata = normalize_and_scale_data(
    ...     adata,
    ...     target_sum=1e6,
    ...     exclude_highly_expressed=True,
    ...     regress_out=['n_counts'],
    ...     max_value=10
    ... )
    """
    print("Normalizing and scaling data...")

    # Normalize counts
    print(f"\n1. Normalizing to {target_sum} total counts per cell...")
    sc.pp.normalize_total(
        adata,
        target_sum=target_sum,
        exclude_highly_expressed=exclude_highly_expressed
    )

    # Log-transform
    print("2. Log-transforming (log1p)...")
    sc.pp.log1p(adata)

    # Save raw
    if save_raw:
        print("3. Saving log-normalized counts in adata.raw...")
        adata.raw = adata

    # Regress out technical variables
    if regress_out is not None:
        print(f"4. Regressing out: {regress_out}...")
        sc.pp.regress_out(adata, regress_out, n_jobs=n_jobs)
    else:
        print("4. Skipping regression (regress_out=None)")

    # Scale
    print(f"5. Scaling (max_value={max_value})...")
    sc.pp.scale(adata, max_value=max_value)

    print("\nNormalization complete!")
    print("  adata.X: scaled, regressed data (for PCA, UMAP)")
    print("  adata.raw: log-normalized counts (for DE, visualization)")

    return adata


def normalize_only(
    adata: ad.AnnData,
    target_sum: float = 1e6,
    exclude_highly_expressed: bool = True,
    save_raw: bool = False
) -> ad.AnnData:
    """
    Normalization and log-transformation only (no regression or scaling).

    Parameters
    ----------
    adata : AnnData
        Input AnnData (filtered, raw counts)
    target_sum : float, default=1e6
        Target sum for normalization
    exclude_highly_expressed : bool, default=True
        Exclude highly expressed genes from normalization
    save_raw : bool, default=False
        Save raw counts before normalization

    Returns
    -------
    adata : AnnData
        Log-normalized AnnData

    Example
    -------
    >>> adata_norm = normalize_only(adata, target_sum=1e6)
    """
    if save_raw:
        adata.raw = adata.copy()

    # Normalize
    sc.pp.normalize_total(
        adata,
        target_sum=target_sum,
        exclude_highly_expressed=exclude_highly_expressed
    )

    # Log-transform
    sc.pp.log1p(adata)

    print("✓ Normalization complete")
    return adata
