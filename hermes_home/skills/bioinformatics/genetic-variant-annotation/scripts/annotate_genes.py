
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
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. 图片是否生成？无图 → 重新执行
#        b. 图片是否空白（全白/全黑/全单一色）？空白 → 强制重新出图
#        c. 图片是否有 NA/缺失值（>10%像素是NA）？有NA → 强制重新出图
#        d. 图片大小是否过小（<5KB）？过小 → 强制重新出图
#        e. 图片数量是否足够？（每步至少1张图，关键步骤至少2-3张）
#        f. 代码行数是否合理？是否分段执行（禁止&&连接）？
#        g. 数值范围是否合理？跟知识库对应吗？
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
# ★ 参数和结论辩论铁律:
#   - 有参数选择 → 必须调 debate_analysis 辩论
#   - 有结论输出 → 必须调 debate_analysis 辩论
#   - 辩论格式：正方(支持) vs 反方(质疑+替代) → 裁判决断
#   - 最多3轮，3轮后选最优结果
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
#   ★ 强制: 图片空白/NA/过小 → 重新出图 | 图片不够 → 补图 | 代码未分段 → 重写
#   ★ 强制: 有参数有结论 → debate_analysis 辩论
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================


"""
Gene-Level Annotation Module

This module provides functions for generating gene-level summaries from variant data.
"""

import sys
from collections import defaultdict

try:
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip install pandas numpy")
    sys.exit(1)


def create_gene_summary(
    df,
    group_by='SYMBOL',
    count_variants=True,
    count_by_consequence=True,
    count_by_impact=True,
    include_most_severe=True,
    aggregate_scores=None,
    aggregation='max'
):
    """
    Create gene-level summary from variant data.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with variant annotations
    group_by : str
        Column to group by (default: 'SYMBOL' for gene symbol)
    count_variants : bool
        Count total variants per gene
    count_by_consequence : bool
        Count variants by consequence type
    count_by_impact : bool
        Count variants by impact level
    include_most_severe : bool
        Include most severe variant per gene
    aggregate_scores : list, optional
        List of score columns to aggregate (e.g., ['CADD_PHRED', 'REVEL'])
    aggregation : str
        Aggregation method: 'max', 'mean', 'median' (default: 'max')

    Returns
    -------
    pd.DataFrame
        Gene-level summary DataFrame
    """
    if group_by not in df.columns:
        raise ValueError(f"Column '{group_by}' not found in DataFrame")

    # Remove missing gene names
    df_genes = df[df[group_by].notna()].copy()

    # Initialize summary dict
    summary_data = defaultdict(dict)

    # Group by gene
    for gene, gene_df in df_genes.groupby(group_by):
        gene_summary = {}

        # Total variant count
        if count_variants:
            gene_summary['N_Variants'] = len(gene_df)

        # Count by impact
        if count_by_impact and 'IMPACT' in gene_df.columns:
            for impact in ['HIGH', 'MODERATE', 'LOW', 'MODIFIER']:
                count = len(gene_df[gene_df['IMPACT'] == impact])
                gene_summary[f'N_{impact}_Impact'] = count

        # Count by consequence
        if count_by_consequence and 'Consequence' in gene_df.columns:
            # Count most common consequences
            cons_counts = gene_df['Consequence'].value_counts()
            for cons, count in cons_counts.items():
                if pd.notna(cons):
                    cons_clean = str(cons).split('&')[0]  # Take first if multi
                    gene_summary[f'N_{cons_clean}'] = count

        # Most severe variant
        if include_most_severe:
            if 'IMPACT_SCORE' in gene_df.columns:
                most_severe_idx = gene_df['IMPACT_SCORE'].idxmax()
            else:
                most_severe_idx = gene_df.index[0]

            most_severe = gene_df.loc[most_severe_idx]

            if 'Consequence' in most_severe:
                gene_summary['Most_Severe_Consequence'] = most_severe['Consequence']
            if 'IMPACT' in most_severe:
                gene_summary['Most_Severe_Impact'] = most_severe['IMPACT']
            if 'HGVSp' in most_severe:
                gene_summary['Most_Severe_HGVSp'] = most_severe['HGVSp']

        # Aggregate scores
        if aggregate_scores:
            for score_col in aggregate_scores:
                if score_col in gene_df.columns:
                    scores = pd.to_numeric(gene_df[score_col], errors='coerce').dropna()

                    if len(scores) > 0:
                        if aggregation == 'max':
                            gene_summary[f'Max_{score_col}'] = scores.max()
                        elif aggregation == 'mean':
                            gene_summary[f'Mean_{score_col}'] = scores.mean()
                        elif aggregation == 'median':
                            gene_summary[f'Median_{score_col}'] = scores.median()

        # Variant list (positions)
        variant_ids = []
        for _, row in gene_df.iterrows():
            var_id = f"{row['CHROM']}:{row['POS']}:{row['REF']}>{row['ALT']}"
            variant_ids.append(var_id)
        gene_summary['Variant_List'] = ';'.join(variant_ids[:10])  # Limit to first 10

        summary_data[gene] = gene_summary

    # Convert to DataFrame
    summary_df = pd.DataFrame.from_dict(summary_data, orient='index')
    summary_df.index.name = group_by
    summary_df = summary_df.reset_index()

    # Sort by number of variants
    if 'N_Variants' in summary_df.columns:
        summary_df = summary_df.sort_values('N_Variants', ascending=False)

    return summary_df


def annotate_gene_sets(df, gene_sets):
    """
    Annotate genes with gene set membership.

    Parameters
    ----------
    df : pd.DataFrame
        Gene summary DataFrame with gene symbols
    gene_sets : dict
        Dictionary mapping gene set names to file paths or lists
        Example: {'cancer_genes': 'path/to/cancer_genes.txt'}

    Returns
    -------
    pd.DataFrame
        DataFrame with gene set annotations
    """
    annotated = df.copy()

    for set_name, gene_list_source in gene_sets.items():
        # Load gene list
        if isinstance(gene_list_source, str):
            # Load from file
            with open(gene_list_source, 'r') as f:
                genes_in_set = set(line.strip() for line in f if line.strip())
        elif isinstance(gene_list_source, (list, set)):
            genes_in_set = set(gene_list_source)
        else:
            print(f"Warning: Invalid gene set format for {set_name}")
            continue

        # Check membership
        if 'SYMBOL' in annotated.columns:
            annotated[f'In_{set_name}'] = annotated['SYMBOL'].isin(genes_in_set)
        elif 'Gene' in annotated.columns:
            annotated[f'In_{set_name}'] = annotated['Gene'].isin(genes_in_set)

    return annotated


def calculate_gene_burden(df, normalize_by_length=False, gene_lengths=None):
    """
    Calculate variant burden per gene.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with variant annotations
    normalize_by_length : bool
        Normalize burden by gene length (default: False)
    gene_lengths : dict or str, optional
        Dictionary of gene lengths or path to file with gene lengths

    Returns
    -------
    pd.DataFrame
        Gene burden DataFrame
    """
    # Count variants per gene
    if 'SYMBOL' in df.columns:
        burden = df.groupby('SYMBOL').size().reset_index(name='Variant_Count')
        gene_col = 'SYMBOL'
    elif 'Gene' in df.columns:
        burden = df.groupby('Gene').size().reset_index(name='Variant_Count')
        gene_col = 'Gene'
    else:
        raise ValueError("No gene column found (SYMBOL or Gene)")

    # Normalize by gene length if requested
    if normalize_by_length and gene_lengths:
        if isinstance(gene_lengths, str):
            # Load from file (format: gene\tlength)
            length_df = pd.read_csv(gene_lengths, sep='\t', names=['gene', 'length'])
            gene_lengths = dict(zip(length_df['gene'], length_df['length']))

        burden['Gene_Length'] = burden[gene_col].map(gene_lengths)
        burden['Normalized_Burden'] = burden['Variant_Count'] / burden['Gene_Length'] * 1000

    return burden.sort_values('Variant_Count', ascending=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Create gene-level summary')
    parser.add_argument('input_csv', help='Input CSV file with variant annotations')
    parser.add_argument('output_csv', help='Output CSV file with gene summary')
    parser.add_argument('--aggregate-scores', nargs='+',
                        help='Score columns to aggregate (e.g., CADD_PHRED REVEL)')

    args = parser.parse_args()

    # Load data
    df = pd.read_csv(args.input_csv)
    print(f"Loaded {len(df)} variants")

    # Create gene summary
    gene_summary = create_gene_summary(
        df,
        aggregate_scores=args.aggregate_scores
    )

    # Save summary
    gene_summary.to_csv(args.output_csv, index=False)
    print(f"\nWrote summary for {len(gene_summary)} genes to {args.output_csv}")
