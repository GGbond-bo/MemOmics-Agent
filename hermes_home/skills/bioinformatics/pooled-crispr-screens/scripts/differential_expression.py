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
Differential Expression Analysis per Perturbation

For each perturbation, perform differential expression analysis comparing
perturbed cells to non-targeting controls.
"""

import os
import pandas as pd
import anndata as ad
import diffxpy.api as de
from typing import Dict, Optional, Literal


def run_de_analysis(
    adata: ad.AnnData,
    control_group: str = 'non-targeting',
    gene_col: str = 'gene',
    test_method: Literal['t-test', 'wilcoxon', 'negative_binomial'] = 't-test',
    use_outliers_only: bool = True,
    outlier_cells: Optional[list] = None,
    top_n_genes: int = 50,
    output_dir: str = 'DEG/rank_test/',
    is_logged: bool = True
) -> Dict[str, pd.DataFrame]:
    """
    Run differential expression analysis for each perturbation vs control.

    Parameters
    ----------
    adata : AnnData
        Log-normalized AnnData (use adata.raw or normalized data)
    control_group : str, default='non-targeting'
        Label for control group
    gene_col : str, default='gene'
        Column in obs with perturbation labels
    test_method : str, default='t-test'
        Statistical test: 't-test', 'wilcoxon', 'negative_binomial'
    use_outliers_only : bool, default=True
        If True and outlier_cells provided, use only outlier cells for DE
    outlier_cells : list, optional
        List of cell barcodes identified as outliers (from detect_perturbed_cells)
    top_n_genes : int, default=50
        Number of top genes to highlight in output
    output_dir : str, default='DEG/rank_test/'
        Directory to save per-perturbation DE results
    is_logged : bool, default=True
        Whether data is log-transformed

    Returns
    -------
    de_results : dict
        Dictionary mapping gene -> DE results DataFrame

    Example
    -------
    >>> de_results = run_de_analysis(
    ...     adata,
    ...     control_group='non-targeting',
    ...     test_method='t-test',
    ...     use_outliers_only=True,
    ...     outlier_cells=results['outlier_cells'],
    ...     top_n_genes=50
    ... )
    """
    os.makedirs(output_dir, exist_ok=True)

    # Subset to outliers + controls if requested
    if use_outliers_only and outlier_cells is not None:
        print(f"Subsetting to outlier cells + controls...")
        control_cell_barcodes = adata[adata.obs[gene_col] == control_group].obs_names.tolist()
        kept_cells = list(set(outlier_cells + control_cell_barcodes))
        adata_selected = adata[adata.obs_names.isin(kept_cells)].copy()
        print(f"  Using {len(outlier_cells)} outlier cells + {len(control_cell_barcodes)} control cells")
    else:
        adata_selected = adata.copy()
        print("Using all cells for DE analysis")

    # Get unique perturbations
    genes = adata_selected.obs[gene_col].unique().tolist()
    genes = [g for g in genes if g != control_group]

    print(f"\nRunning DE analysis for {len(genes)} perturbations...")
    print(f"  Test method: {test_method}")
    print(f"  Top N genes to export: {top_n_genes}\n")

    de_results = {}

    for i, gene in enumerate(genes):
        if (i + 1) % 10 == 0:
            print(f"Processing {i+1}/{len(genes)}: {gene}")

        # Subset to this perturbation vs control
        adata_temp = adata_selected[
            adata_selected.obs[gene_col].isin([control_group, gene])
        ].copy()

        # Run DE test
        if test_method == 't-test':
            test = de.test.t_test(
                data=adata_temp,
                grouping=gene_col,
                is_logged=is_logged
            )
        elif test_method == 'wilcoxon':
            test = de.test.wilcoxon(
                data=adata_temp,
                grouping=gene_col
            )
        elif test_method == 'negative_binomial':
            test = de.test.wald(
                data=adata_temp,
                formula_loc=f"~ 1 + {gene_col}"
            )
        else:
            raise ValueError(f"Unknown test method: {test_method}")

        # Get summary
        de_summary = test.summary()

        # Sort by p-value
        de_summary_sorted = de_summary.sort_values('pval')

        # Save full results
        output_path = os.path.join(output_dir, f"{gene}_{test_method}.csv")
        de_summary_sorted.to_csv(output_path)

        # Store in dict
        de_results[gene] = de_summary_sorted

    print(f"\n=== DE Analysis Complete ===")
    print(f"Results saved to: {output_dir}")
    print(f"Files: {len(de_results)} perturbations")

    return de_results


def summarize_de_results(
    de_results: Dict[str, pd.DataFrame],
    pval_threshold: float = 0.05,
    log2fc_threshold: float = 0.5
) -> pd.DataFrame:
    """
    Summarize DE results across all perturbations.

    Parameters
    ----------
    de_results : dict
        Dictionary of DE results from run_de_analysis
    pval_threshold : float, default=0.05
        P-value threshold for calling DE genes
    log2fc_threshold : float, default=0.5
        Log2 fold-change threshold

    Returns
    -------
    summary : DataFrame
        Summary with columns: gene, n_de_genes, n_up, n_down, top_de_gene

    Example
    -------
    >>> summary = summarize_de_results(de_results)
    >>> print(summary.sort_values('n_de_genes', ascending=False))
    """
    summary_list = []

    for gene, de_df in de_results.items():
        # Count DE genes
        de_genes = de_df[de_df['pval'] < pval_threshold]

        n_de_genes = len(de_genes)

        # Count up/down (if log2fc column exists)
        if 'log2fc' in de_df.columns:
            sig_with_fc = de_genes[abs(de_genes['log2fc']) > log2fc_threshold]
            n_up = (sig_with_fc['log2fc'] > 0).sum()
            n_down = (sig_with_fc['log2fc'] < 0).sum()
        else:
            n_up = 0
            n_down = 0

        # Top DE gene
        if n_de_genes > 0:
            top_gene = de_genes.iloc[0]['gene']
            top_pval = de_genes.iloc[0]['pval']
        else:
            top_gene = 'none'
            top_pval = 1.0

        summary_list.append({
            'perturbation': gene,
            'n_de_genes': n_de_genes,
            'n_up': n_up,
            'n_down': n_down,
            'top_de_gene': top_gene,
            'top_pval': top_pval
        })

    summary = pd.DataFrame(summary_list)
    summary = summary.sort_values('n_de_genes', ascending=False)

    return summary
