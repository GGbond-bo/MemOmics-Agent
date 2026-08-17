
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
Variant Prioritization Module

This module provides functions for prioritizing variants based on pathogenicity and
clinical relevance using ACMG/AMP criteria.
"""

import sys

try:
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip install pandas numpy")
    sys.exit(1)


def prioritize_variants(
    df,
    criteria=None,
    weights=None,
    output_column='Priority_Score'
):
    """
    Prioritize variants using multiple weighted criteria.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with variant annotations
    criteria : list of tuples
        List of (column_name, criterion_type) tuples
        Types: 'clinical_significance', 'consequence_severity',
               'pathogenicity_score', 'allele_frequency', 'loss_of_function'
    weights : list of float
        Weight for each criterion (must sum to 1.0)
    output_column : str
        Name for priority score column (default: 'Priority_Score')

    Returns
    -------
    pd.DataFrame
        DataFrame with priority scores
    """
    if criteria is None:
        criteria = [
            ('CLIN_SIG', 'clinical_significance'),
            ('IMPACT', 'consequence_severity'),
            ('CADD_PHRED', 'pathogenicity_score'),
            ('gnomAD_AF', 'allele_frequency')
        ]

    if weights is None:
        # Equal weights if not specified
        weights = [1.0 / len(criteria)] * len(criteria)

    if len(criteria) != len(weights):
        raise ValueError("Number of criteria must match number of weights")

    if not np.isclose(sum(weights), 1.0):
        print(f"Warning: Weights sum to {sum(weights)}, not 1.0. Normalizing...")
        weights = [w / sum(weights) for w in weights]

    # Calculate score for each criterion
    scores = []

    for (column, criterion_type), weight in zip(criteria, weights):
        if column not in df.columns:
            print(f"Warning: Column {column} not found, skipping")
            continue

        if criterion_type == 'clinical_significance':
            score = _score_clinical_significance(df[column])
        elif criterion_type == 'consequence_severity':
            score = _score_consequence_severity(df[column])
        elif criterion_type == 'pathogenicity_score':
            score = _score_pathogenicity(df[column])
        elif criterion_type == 'allele_frequency':
            score = _score_allele_frequency(df[column])
        elif criterion_type == 'loss_of_function':
            score = _score_lof(df[column])
        else:
            print(f"Warning: Unknown criterion type {criterion_type}")
            continue

        scores.append(score * weight)

    # Combine weighted scores
    if scores:
        priority_score = sum(scores)
        df[output_column] = priority_score
    else:
        df[output_column] = 0.0

    return df


def _score_clinical_significance(series):
    """Score based on ClinVar clinical significance."""
    score_map = {
        'Pathogenic': 1.0,
        'Likely_pathogenic': 0.8,
        'Pathogenic/Likely_pathogenic': 1.0,
        'Uncertain_significance': 0.3,
        'Likely_benign': 0.1,
        'Benign': 0.0,
        'Benign/Likely_benign': 0.0
    }

    def map_score(value):
        if pd.isna(value):
            return 0.5  # Neutral for missing
        value_str = str(value)
        for key, score in score_map.items():
            if key.lower() in value_str.lower():
                return score
        return 0.5

    return series.apply(map_score)


def _score_consequence_severity(series):
    """Score based on variant consequence severity."""
    impact_scores = {
        'HIGH': 1.0,
        'MODERATE': 0.7,
        'LOW': 0.3,
        'MODIFIER': 0.1
    }

    return series.map(impact_scores).fillna(0.5)


def _score_pathogenicity(series):
    """Score based on pathogenicity prediction (e.g., CADD, REVEL)."""
    # Normalize scores to 0-1 range
    numeric = pd.to_numeric(series, errors='coerce')

    # Assume CADD-like scale (0-40+)
    # Threshold: 20 = moderate, 30 = high confidence
    normalized = (numeric - 10) / 30  # Maps 10->0, 40->1
    normalized = normalized.clip(0, 1)

    return normalized.fillna(0.5)


def _score_allele_frequency(series):
    """Score based on allele frequency (rarer = higher score)."""
    numeric = pd.to_numeric(series, errors='coerce')

    # Inverse relationship: rare variants score higher
    # AF < 0.001 = 1.0, AF > 0.01 = 0.0
    score = 1.0 - (numeric / 0.01)
    score = score.clip(0, 1)

    return score.fillna(1.0)  # Treat missing as rare


def _score_lof(series):
    """Score based on loss-of-function prediction."""
    # LOF = 1.0, not LOF = 0.0
    return series.apply(lambda x: 1.0 if pd.notna(x) and x else 0.0)


def acmg_classify(df, classify_column='ACMG_Class', output_criteria=False):
    """
    Classify variants using simplified ACMG/AMP guidelines.

    This is a simplified implementation. For clinical use, manual review
    and full ACMG criteria application is required.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with variant annotations
    classify_column : str
        Name for classification column
    output_criteria : bool
        Include which ACMG criteria were met

    Returns
    -------
    pd.DataFrame
        DataFrame with ACMG classifications
    """
    classifications = []
    criteria_met = []

    for _, row in df.iterrows():
        criteria = []
        pathogenic_score = 0
        benign_score = 0

        # PVS1: Null variant (LOF) in gene where LOF is disease mechanism
        if row.get('IMPACT') == 'HIGH':
            if any(cons in str(row.get('Consequence', '')) for cons in
                   ['stop_gained', 'frameshift', 'splice_acceptor', 'splice_donor']):
                pathogenic_score += 8  # Very strong
                criteria.append('PVS1')

        # PS1: Same amino acid change as known pathogenic variant
        if 'Pathogenic' in str(row.get('CLIN_SIG', '')):
            pathogenic_score += 4  # Strong
            criteria.append('PS1')

        # PM1: Located in mutational hot spot or critical functional domain
        if row.get('IMPACT') in ['HIGH', 'MODERATE']:
            pathogenic_score += 2  # Moderate
            criteria.append('PM1')

        # PM2: Absent from controls (or very low frequency)
        gnomad_af = pd.to_numeric(row.get('gnomAD_AF'), errors='coerce')
        if pd.isna(gnomad_af) or gnomad_af < 0.0001:
            pathogenic_score += 2  # Moderate
            criteria.append('PM2')

        # PP3: Multiple lines of computational evidence support pathogenicity
        cadd = pd.to_numeric(row.get('CADD_PHRED'), errors='coerce')
        revel = pd.to_numeric(row.get('REVEL'), errors='coerce')
        if (pd.notna(cadd) and cadd > 20) or (pd.notna(revel) and revel > 0.5):
            pathogenic_score += 1  # Supporting
            criteria.append('PP3')

        # BA1: Allele frequency > 5% in population databases
        if pd.notna(gnomad_af) and gnomad_af > 0.05:
            benign_score += 8  # Stand-alone
            criteria.append('BA1')

        # BS1: Allele frequency > expected for disorder
        if pd.notna(gnomad_af) and gnomad_af > 0.01:
            benign_score += 4  # Strong
            criteria.append('BS1')

        # BP4: Multiple lines of computational evidence suggest no impact
        if row.get('IMPACT') == 'MODIFIER' or row.get('Consequence') == 'synonymous_variant':
            benign_score += 1  # Supporting
            criteria.append('BP4')

        # Classify based on evidence
        if pathogenic_score >= 10 or ('PVS1' in criteria and pathogenic_score >= 6):
            classification = 'Pathogenic'
        elif pathogenic_score >= 6:
            classification = 'Likely_pathogenic'
        elif benign_score >= 8 or benign_score >= 4:
            classification = 'Benign' if benign_score >= 8 else 'Likely_benign'
        else:
            classification = 'Uncertain_significance'

        classifications.append(classification)
        criteria_met.append(','.join(criteria) if criteria else '')

    df[classify_column] = classifications

    if output_criteria:
        df[f'{classify_column}_Criteria'] = criteria_met

    return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Prioritize variants')
    parser.add_argument('input_csv', help='Input CSV file with variant annotations')
    parser.add_argument('output_csv', help='Output CSV file with prioritized variants')
    parser.add_argument('--acmg', action='store_true', help='Add ACMG classification')

    args = parser.parse_args()

    # Load data
    df = pd.read_csv(args.input_csv)
    print(f"Loaded {len(df)} variants")

    # Prioritize
    df = prioritize_variants(df)

    # ACMG classification
    if args.acmg:
        df = acmg_classify(df, output_criteria=True)

    # Sort by priority
    df = df.sort_values('Priority_Score', ascending=False)

    # Save
    df.to_csv(args.output_csv, index=False)
    print(f"\nWrote {len(df)} prioritized variants to {args.output_csv}")
