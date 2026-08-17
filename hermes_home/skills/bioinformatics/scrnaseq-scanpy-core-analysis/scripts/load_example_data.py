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

"""
============================================================================
LOAD EXAMPLE DATA FOR TESTING
============================================================================

This script loads example single-cell RNA-seq data for testing workflows.

Functions:
  - load_example_data(): Load PBMC 3k example dataset

Usage:
  from load_example_data import load_example_data
  adata = load_example_data()
"""

from typing import Optional


def load_example_data(dataset: str = "pbmc3k") -> 'AnnData':
    """
    Load example single-cell RNA-seq dataset.

    This function loads the PBMC 3k dataset (2,700 PBMCs from a healthy donor)
    from the scanpy datasets collection. Perfect for testing and learning.

    Parameters
    ----------
    dataset : str, optional
        Dataset to load (default: "pbmc3k")
        Options: "pbmc3k", "pbmc68k_reduced"

    Returns
    -------
    AnnData
        Example dataset with raw counts

    Examples
    --------
    >>> adata = load_example_data()
    >>> print(f"Loaded {adata.n_obs} cells and {adata.n_vars} genes")
    """
    import scanpy as sc

    print(f"Loading {dataset} example dataset...")
    print("  Source: 10X Genomics")

    if dataset == "pbmc3k":
        print("  Description: 2,700 PBMCs from a healthy donor")
        print("  Platform: 10X Chromium v1")
        adata = sc.datasets.pbmc3k()
    elif dataset == "pbmc68k_reduced":
        print("  Description: Subsampled PBMC 68k dataset")
        print("  Platform: 10X Chromium")
        adata = sc.datasets.pbmc68k_reduced()
    else:
        raise ValueError(f"Unknown dataset: {dataset}. Options: 'pbmc3k', 'pbmc68k_reduced'")

    print(f"\n✓ Data loaded successfully!")
    print(f"  Cells: {adata.n_obs}")
    print(f"  Genes: {adata.n_vars}")

    return adata


if __name__ == "__main__":
    # Test the function
    adata = load_example_data("pbmc3k")
    print("\nExample data ready for analysis!")
