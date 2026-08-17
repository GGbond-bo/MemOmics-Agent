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
Load 10X Feature-Barcode Matrices for Pooled CRISPR Screens

This module loads raw 10X h5 feature-barcode matrices containing both gene
expression and sgRNA capture data.
"""

import scanpy as sc
from typing import List
import anndata as ad


def load_single_library(h5_path: str) -> ad.AnnData:
    """
    Load a single 10X h5 feature-barcode matrix.

    Parameters
    ----------
    h5_path : str
        Path to raw_feature_bc_matrix.h5 file

    Returns
    -------
    adata : AnnData
        AnnData object with unique gene names
    """
    print(f"Loading {h5_path}...")
    adata = sc.read_10x_h5(h5_path)

    # Make gene names unique (handles duplicate gene symbols)
    adata.var_names_make_unique()

    print(f"  Loaded {adata.n_obs} cells x {adata.n_vars} features")

    return adata


def load_multiple_libraries(h5_paths: List[str]) -> List[ad.AnnData]:
    """
    Load multiple 10X h5 files for replicate libraries.

    Parameters
    ----------
    h5_paths : list of str
        Paths to h5 files

    Returns
    -------
    adata_list : list of AnnData
        List of AnnData objects, one per library

    Example
    -------
    >>> adata_list = load_multiple_libraries([
    ...     "raw_feature_bc_matrix_lib1.h5",
    ...     "raw_feature_bc_matrix_lib2.h5",
    ...     "raw_feature_bc_matrix_lib3.h5",
    ...     "raw_feature_bc_matrix_lib4.h5"
    ... ])
    """
    adata_list = []

    for h5_path in h5_paths:
        adata = load_single_library(h5_path)
        adata_list.append(adata)

    print(f"\nLoaded {len(adata_list)} libraries total")

    return adata_list
