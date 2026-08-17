
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
Visualize primer binding sites and properties.

This module creates publication-quality visualizations using plotnine
with Prism theme following the repository standards.
"""

from plotnine import (ggplot, aes, geom_segment, geom_text, geom_point,
                      geom_bar, geom_hline, labs, theme,
                      element_text, scale_fill_manual, coord_flip, ylim)
from plotnine_prism import theme_prism

import pandas as pd
from typing import Dict, List


def plot_primer_alignment(
    sequence: str,
    primers: Dict,
    output_file: str,
    show_sequence: bool = False
):
    """
    Visualize primer positions on target sequence.

    Creates a publication-quality plot showing primer binding sites
    using plotnine with Prism theme.

    Parameters
    ----------
    sequence : str
        Target DNA sequence
    primers : dict
        Primer pair dictionary with positions
    output_file : str
        Output file path (SVG recommended)
    show_sequence : bool
        Show sequence at primer positions. Default: False

    Example
    -------
    >>> plot_primer_alignment(
    ...     sequence="ATGC..." * 100,
    ...     primers=primer_pair,
    ...     output_file="primer_alignment.svg"
    ... )
    """

    # Prepare data
    seq_length = len(sequence)

    plot_data = []

    # Forward primer
    plot_data.append({
        'type': 'Forward Primer',
        'start': primers['forward_pos'],
        'end': primers['forward_pos'] + primers['forward_length'],
        'y': 1,
        'label': f"F: {primers['forward_tm']:.1f}°C",
        'sequence': primers['forward_seq'],
    })

    # Reverse primer
    plot_data.append({
        'type': 'Reverse Primer',
        'start': primers['reverse_pos'] - primers['reverse_length'],
        'end': primers['reverse_pos'],
        'y': 1,
        'label': f"R: {primers['reverse_tm']:.1f}°C",
        'sequence': primers['reverse_seq'],
    })

    # Amplicon
    plot_data.append({
        'type': 'Amplicon',
        'start': primers['forward_pos'],
        'end': primers['reverse_pos'],
        'y': 0.5,
        'label': f"{primers['amplicon_size']} bp",
        'sequence': '',
    })

    df = pd.DataFrame(plot_data)

    # Create plot
    p = (ggplot(df, aes(x='start', y='y', xend='end', yend='y', color='type'))
         + geom_segment(size=4, arrow=None)
         + geom_text(aes(x='(start+end)/2', label='label'),
                     va='bottom', size=9, nudge_y=0.1)
         + labs(
             title='Primer Binding Sites',
             x='Position (bp)',
             y='',
             color='Element'
         )
         + scale_fill_manual(values=['#E74C3C', '#3498DB', '#95A5A6'])
         + ylim(-0.5, 2)
         + theme_prism()
         + theme(
             axis_text_y=element_text(size=0),  # Hide y-axis labels
             axis_ticks_major_y=element_text(size=0),
             legend_position='top'
         )
    )

    # Save plot
    p.save(output_file, dpi=300, width=10, height=4)
    print(f"Primer alignment plot saved: {output_file}")


def plot_tm_distribution(
    primer_set: List[Dict],
    output_file: str
):
    """
    Plot melting temperature distribution for primer set.

    Parameters
    ----------
    primer_set : list of dict
        List of primer pairs
    output_file : str
        Output file path (SVG recommended)

    Example
    -------
    >>> plot_tm_distribution(
    ...     primer_set=primers['primers'],
    ...     output_file="tm_distribution.svg"
    ... )
    """

    # Prepare data
    tm_data = []
    for i, pair in enumerate(primer_set, 1):
        tm_data.append({
            'Pair': f"Pair {i}",
            'Primer': 'Forward',
            'Tm': pair['forward_tm'],
        })
        tm_data.append({
            'Pair': f"Pair {i}",
            'Primer': 'Reverse',
            'Tm': pair['reverse_tm'],
        })

    df = pd.DataFrame(tm_data)

    # Create plot
    p = (ggplot(df, aes(x='Pair', y='Tm', fill='Primer'))
         + geom_bar(stat='identity', position='dodge')
         + geom_hline(yintercept=60, linetype='dashed', color='gray', alpha=0.5)
         + labs(
             title='Melting Temperature Distribution',
             x='Primer Pair',
             y='Melting Temperature (°C)',
             fill='Primer Type'
         )
         + scale_fill_manual(values=['#E74C3C', '#3498DB'])
         + theme_prism()
         + theme(
             axis_text_x=element_text(rotation=45, hjust=1),
             legend_position='top'
         )
    )

    # Save plot
    p.save(output_file, dpi=300, width=8, height=6)
    print(f"Tm distribution plot saved: {output_file}")


def plot_primer_properties(
    primer_set: List[Dict],
    output_file: str
):
    """
    Plot primer properties (Tm, GC%, length) for comparison.

    Parameters
    ----------
    primer_set : list of dict
        List of primer pairs
    output_file : str
        Output file path

    Example
    -------
    >>> plot_primer_properties(
    ...     primer_set=primers['primers'][:5],
    ...     output_file="primer_properties.svg"
    ... )
    """

    # Prepare data
    prop_data = []
    for i, pair in enumerate(primer_set, 1):
        for primer_type, prefix in [('Forward', 'forward'), ('Reverse', 'reverse')]:
            prop_data.append({
                'Pair': f"Pair {i}",
                'Type': primer_type,
                'Tm (°C)': pair[f'{prefix}_tm'],
                'GC (%)': pair[f'{prefix}_gc'],
                'Length (bp)': pair[f'{prefix}_length'],
            })

    df = pd.DataFrame(prop_data)

    # Create Tm plot
    p_tm = (ggplot(df, aes(x='Pair', y='Tm (°C)', color='Type', group='Type'))
            + geom_point(size=3)
            + geom_hline(yintercept=[58, 62], linetype='dashed', alpha=0.3)
            + labs(title='Primer Melting Temperatures', x='', y='Tm (°C)')
            + theme_prism()
    )

    p_tm.save(output_file.replace('.svg', '_tm.svg'), dpi=300, width=8, height=4)

    # Create GC% plot
    p_gc = (ggplot(df, aes(x='Pair', y='GC (%)', color='Type', group='Type'))
            + geom_point(size=3)
            + geom_hline(yintercept=[40, 60], linetype='dashed', alpha=0.3)
            + labs(title='Primer GC Content', x='', y='GC (%)')
            + theme_prism()
    )

    p_gc.save(output_file.replace('.svg', '_gc.svg'), dpi=300, width=8, height=4)

    print(f"Primer property plots saved: {output_file.replace('.svg', '_*.svg')}")


def plot_amplicon_sizes(
    primer_set: List[Dict],
    output_file: str,
    target_range: tuple = None
):
    """
    Plot amplicon size distribution.

    Parameters
    ----------
    primer_set : list of dict
        List of primer pairs
    output_file : str
        Output file path
    target_range : tuple, optional
        (min, max) target amplicon size for reference lines

    Example
    -------
    >>> plot_amplicon_sizes(
    ...     primer_set=primers['primers'],
    ...     output_file="amplicon_sizes.svg",
    ...     target_range=(70, 140)
    ... )
    """

    # Prepare data
    amp_data = []
    for i, pair in enumerate(primer_set, 1):
        amp_data.append({
            'Pair': f"Pair {i}",
            'Amplicon Size (bp)': pair['amplicon_size'],
            'In Range': target_range is None or (
                target_range[0] <= pair['amplicon_size'] <= target_range[1]
            )
        })

    df = pd.DataFrame(amp_data)

    # Create plot
    p = (ggplot(df, aes(x='Pair', y='Amplicon Size (bp)', fill='In Range'))
         + geom_bar(stat='identity')
         + labs(
             title='Amplicon Sizes',
             x='Primer Pair',
             y='Amplicon Size (bp)',
             fill='Within Target'
         )
         + scale_fill_manual(values=['#E74C3C', '#27AE60'])
         + theme_prism()
         + theme(axis_text_x=element_text(rotation=45, hjust=1))
    )

    if target_range:
        p = p + geom_hline(yintercept=target_range[0], linetype='dashed', alpha=0.3)
        p = p + geom_hline(yintercept=target_range[1], linetype='dashed', alpha=0.3)

    # Save plot
    p.save(output_file, dpi=300, width=8, height=6)
    print(f"Amplicon size plot saved: {output_file}")


def plot_qc_summary(
    primer_set: List[Dict],
    validation_results: List[Dict],
    output_file: str
):
    """
    Create a QC summary visualization.

    Parameters
    ----------
    primer_set : list of dict
        List of primer pairs
    validation_results : list of dict
        Validation results for each pair
    output_file : str
        Output file path

    Example
    -------
    >>> plot_qc_summary(
    ...     primer_set=primers['primers'],
    ...     validation_results=[val1, val2, val3],
    ...     output_file="qc_summary.svg"
    ... )
    """

    # Prepare data
    qc_data = []
    for i, (pair, validation) in enumerate(zip(primer_set, validation_results), 1):
        qc_checks = {
            'Tm Match': pair.get('tm_diff', 0) <= 2.0,
            'GC Content': (40 <= pair.get('forward_gc', 0) <= 60 and
                          40 <= pair.get('reverse_gc', 0) <= 60),
            'No Dimers': not validation.get('dimers', {}).get('has_issues', True),
            'Specific': validation.get('specificity', {}).get('is_specific', False),
        }

        for check_name, passes in qc_checks.items():
            qc_data.append({
                'Pair': f"Pair {i}",
                'QC Check': check_name,
                'Status': 'Pass' if passes else 'Fail',
            })

    df = pd.DataFrame(qc_data)

    # Create plot
    p = (ggplot(df, aes(x='QC Check', y='Pair', fill='Status'))
         + geom_point(aes(color='Status'), size=8, shape='s')
         + labs(
             title='QC Summary',
             x='Quality Check',
             y='Primer Pair',
             color='Status'
         )
         + scale_fill_manual(values=['#E74C3C', '#27AE60'])
         + coord_flip()
         + theme_prism()
    )

    # Save plot
    p.save(output_file, dpi=300, width=8, height=6)
    print(f"QC summary plot saved: {output_file}")
