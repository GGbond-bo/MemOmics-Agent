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
Gene Name Corrections

Fix gene name mismatches between sgRNA target names and gene expression matrix.
This commonly occurs with gene symbol updates.
"""

import anndata as ad
from typing import Dict, List, Optional
import pandas as pd


def detect_mismatches(
    adata: ad.AnnData,
    gene_col: str = 'gene'
) -> List[str]:
    """
    Detect gene names in obs that are not present in var_names.

    Parameters
    ----------
    adata : AnnData
        AnnData with 'gene' column in obs
    gene_col : str, default='gene'
        Column name for target gene in obs

    Returns
    -------
    mismatched_genes : list of str
        List of gene names in obs but not in var_names
    """
    if gene_col not in adata.obs.columns:
        print(f"Warning: Column '{gene_col}' not found in adata.obs")
        return []

    genes_in_obs = adata.obs[gene_col].unique().tolist()
    genes_in_var = adata.var_names.tolist()

    mismatched_genes = [g for g in genes_in_obs if g not in genes_in_var]

    if mismatched_genes:
        print(f"Found {len(mismatched_genes)} gene name mismatches:")
        for gene in mismatched_genes:
            print(f"  {gene}")
    else:
        print("No gene name mismatches detected")

    return mismatched_genes


def correct_gene_names(
    adata: ad.AnnData,
    corrections: Dict[str, str],
    gene_col: str = 'gene'
) -> ad.AnnData:
    """
    Apply gene name corrections to obs column.

    Parameters
    ----------
    adata : AnnData
        AnnData with gene column in obs
    corrections : dict
        Dictionary mapping old names to new names
        Example: {'TMEM55A': 'PIP4P2', 'ATP5C1': 'ATP5F1C'}
    gene_col : str, default='gene'
        Column name for target gene in obs

    Returns
    -------
    adata : AnnData
        AnnData with corrected gene names

    Example
    -------
    >>> corrections = {
    ...     'TMEM55A': 'PIP4P2',
    ...     'ATP5C1': 'ATP5F1C',
    ...     'ATP5H': 'ATP5PD'
    ... }
    >>> adata = correct_gene_names(adata, corrections)
    """
    # Check if gene column exists
    if gene_col not in adata.obs.columns:
        print(f"Warning: Column '{gene_col}' not found in adata.obs")
        print("  No corrections applied. Ensure sgRNA mapping is done first.")
        return adata

    if len(corrections) == 0:
        print("No gene name corrections to apply")
        return adata

    print(f"Applying {len(corrections)} gene name corrections:")

    target_genes = adata.obs[gene_col].copy()

    for old_name, new_name in corrections.items():
        n_cells = (target_genes == old_name).sum()
        if n_cells > 0:
            target_genes = target_genes.replace(old_name, new_name)
            print(f"  {old_name} -> {new_name} ({n_cells} cells)")
        else:
            print(f"  {old_name} -> {new_name} (not found)")

    adata.obs[gene_col] = target_genes

    # Verify corrections
    remaining_mismatches = detect_mismatches(adata, gene_col=gene_col)

    if remaining_mismatches:
        print(f"\nWarning: {len(remaining_mismatches)} mismatches remain")
    else:
        print("\nAll gene names corrected successfully")

    return adata


def suggest_corrections(
    adata: ad.AnnData,
    gene_col: str = 'gene',
    use_synonyms: bool = False
) -> Dict[str, str]:
    """
    Suggest gene name corrections based on common aliases.

    Parameters
    ----------
    adata : AnnData
        AnnData with gene column
    gene_col : str, default='gene'
        Column name for target gene
    use_synonyms : bool, default=False
        Use external gene synonym database (requires mygene package)

    Returns
    -------
    suggestions : dict
        Suggested corrections dictionary

    Note
    ----
    For comprehensive synonym lookup, install mygene:
    pip install mygene
    """
    mismatched = detect_mismatches(adata, gene_col=gene_col)

    if not mismatched:
        return {}

    # Common known aliases (human genes)
    known_aliases = {
        'TMEM55A': 'PIP4P2',
        'ATP5C1': 'ATP5F1C',
        'ATP5H': 'ATP5PD',
        'ATP5A1': 'ATP5F1A',
        'ATP5B': 'ATP5F1B',
        'C9orf72': 'C9ORF72',  # Case differences
    }

    suggestions = {}

    for gene in mismatched:
        if gene in known_aliases:
            new_name = known_aliases[gene]
            if new_name in adata.var_names:
                suggestions[gene] = new_name
                print(f"Suggested correction: {gene} -> {new_name}")

    if use_synonyms and len(suggestions) < len(mismatched):
        try:
            import mygene
            mg = mygene.MyGeneInfo()

            remaining = [g for g in mismatched if g not in suggestions]
            results = mg.querymany(remaining, scopes='symbol,alias', fields='symbol', species='human')

            for result in results:
                if 'symbol' in result:
                    old_name = result['query']
                    new_name = result['symbol']
                    if new_name in adata.var_names:
                        suggestions[old_name] = new_name
                        print(f"Suggested correction (from synonym DB): {old_name} -> {new_name}")
        except ImportError:
            print("\nNote: Install mygene for automated synonym lookup:")
            print("  pip install mygene")

    return suggestions
