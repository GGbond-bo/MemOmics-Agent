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
Load and preprocess single-cell expression data for pySCENIC analysis.
"""

import pandas as pd
import scanpy as sc


def load_expression_data(file_path):
    """
    Load single-cell expression data from various formats.

    Parameters:
    -----------
    file_path : str
        Path to expression data file (.h5ad, .loom, .csv, or .tsv)

    Returns:
    --------
    adata : AnnData
        AnnData object with filtered data
    ex_matrix : pd.DataFrame
        Expression matrix (cells x genes) as DataFrame

    Examples:
    ---------
    >>> adata, ex_matrix = load_expression_data("scrnaseq_data.h5ad")
    >>> print(f"Loaded {adata.n_obs} cells x {adata.n_vars} genes")
    """
    if file_path.endswith('.h5ad'):
        adata = sc.read_h5ad(file_path)
    elif file_path.endswith('.loom'):
        adata = sc.read_loom(file_path)
    else:
        # Assume CSV/TSV
        df = pd.read_csv(file_path, index_col=0)
        # Transpose if genes are rows
        if df.shape[0] > df.shape[1]:
            df = df.T
        adata = sc.AnnData(df)

    print(f"Loaded data: {adata.n_obs} cells x {adata.n_vars} genes")

    # Basic filtering
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_genes(adata, min_cells=3)

    print(f"After filtering: {adata.n_obs} cells x {adata.n_vars} genes")
    print(f"✓ Data loaded successfully: {adata.n_obs} cells, {adata.n_vars} genes")

    # Get expression matrix as DataFrame (cells x genes)
    if hasattr(adata.X, 'toarray'):
        ex_matrix = pd.DataFrame(adata.X.toarray(),
                                  index=adata.obs_names,
                                  columns=adata.var_names)
    else:
        ex_matrix = pd.DataFrame(adata.X,
                                  index=adata.obs_names,
                                  columns=adata.var_names)

    return adata, ex_matrix
