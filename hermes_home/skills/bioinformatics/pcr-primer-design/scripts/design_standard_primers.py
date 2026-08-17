
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
Design standard PCR primers using Primer3.

This module provides functions for designing PCR primers for general amplification,
cloning, or genotyping applications using the primer3-py library.
"""

import primer3


def design_pcr_primers(
    sequence: str,
    target_region: tuple = None,
    primer_size_range: tuple = (18, 25),
    tm_range: tuple = (55, 65),
    gc_range: tuple = (40, 60),
    amplicon_size_range: tuple = (100, 1000),
    num_return: int = 5
) -> dict:
    """
    Design PCR primers for a target sequence.

    Parameters
    ----------
    sequence : str
        Target DNA sequence (must be uppercase ATCG)
    target_region : tuple, optional
        (start, end) positions for primer placement. If None, uses entire sequence.
    primer_size_range : tuple
        (min, max) primer length in nucleotides. Default: (18, 25)
    tm_range : tuple
        (min, max) melting temperature in °C. Default: (55, 65)
    gc_range : tuple
        (min, max) GC content in %. Default: (40, 60)
    amplicon_size_range : tuple
        (min, max) PCR product size in bp. Default: (100, 1000)
    num_return : int
        Number of primer pairs to return. Default: 5

    Returns
    -------
    dict
        Dictionary containing:
        - 'primers': list of primer pair dictionaries
        - 'parameters': design parameters used
        - 'sequence_length': length of input sequence

    Example
    -------
    >>> primers = design_pcr_primers(
    ...     sequence="ATGCGTACG..." * 50,
    ...     amplicon_size_range=(200, 500)
    ... )
    >>> print(f"Found {len(primers['primers'])} primer pairs")
    """

    # Validate input
    sequence = sequence.upper().strip()
    if not all(base in 'ATCGN' for base in sequence):
        raise ValueError("Sequence must contain only A, T, C, G, or N characters")

    if len(sequence) < amplicon_size_range[0]:
        raise ValueError(f"Sequence length ({len(sequence)}) is shorter than minimum amplicon size ({amplicon_size_range[0]})")

    # Set up Primer3 parameters
    primer3_params = {
        'PRIMER_OPT_SIZE': 20,
        'PRIMER_MIN_SIZE': primer_size_range[0],
        'PRIMER_MAX_SIZE': primer_size_range[1],
        'PRIMER_OPT_TM': (tm_range[0] + tm_range[1]) / 2,
        'PRIMER_MIN_TM': tm_range[0],
        'PRIMER_MAX_TM': tm_range[1],
        'PRIMER_MIN_GC': gc_range[0],
        'PRIMER_MAX_GC': gc_range[1],
        'PRIMER_PRODUCT_SIZE_RANGE': [amplicon_size_range],
        'PRIMER_NUM_RETURN': num_return,
        'PRIMER_MAX_POLY_X': 4,  # No more than 4 identical nucleotides in a row
        'PRIMER_GC_CLAMP': 1,  # At least 1 G or C in last 5 bases
        'PRIMER_MAX_NS_ACCEPTED': 0,  # No ambiguous bases
        'PRIMER_MAX_SELF_ANY': 8,  # Max self-complementarity
        'PRIMER_MAX_SELF_END': 3,  # Max 3' self-complementarity
        'PRIMER_PAIR_MAX_COMPL_ANY': 8,  # Max complementarity between primers
        'PRIMER_PAIR_MAX_COMPL_END': 3,  # Max 3' complementarity between primers
    }

    # Set up sequence input
    seq_args = {
        'SEQUENCE_TEMPLATE': sequence,
    }

    # Add target region if specified
    if target_region is not None:
        start, end = target_region
        if start < 0 or end > len(sequence) or start >= end:
            raise ValueError(f"Invalid target region ({start}, {end}) for sequence length {len(sequence)}")
        seq_args['SEQUENCE_TARGET'] = [start, end - start]

    # Run Primer3
    primer3_result = primer3.designPrimers(seq_args, primer3_params)

    # Parse results
    primers_list = []
    num_returned = primer3_result.get('PRIMER_PAIR_NUM_RETURNED', 0)

    for i in range(num_returned):
        # Extract primer sequences
        forward_seq = primer3_result[f'PRIMER_LEFT_{i}_SEQUENCE']
        reverse_seq = primer3_result[f'PRIMER_RIGHT_{i}_SEQUENCE']

        # Extract positions (0-indexed)
        forward_pos, forward_len = primer3_result[f'PRIMER_LEFT_{i}']
        reverse_pos, reverse_len = primer3_result[f'PRIMER_RIGHT_{i}']

        # Extract properties
        forward_tm = primer3_result[f'PRIMER_LEFT_{i}_TM']
        reverse_tm = primer3_result[f'PRIMER_RIGHT_{i}_TM']
        forward_gc = primer3_result[f'PRIMER_LEFT_{i}_GC_PERCENT']
        reverse_gc = primer3_result[f'PRIMER_RIGHT_{i}_GC_PERCENT']

        # Amplicon size
        amplicon_size = primer3_result[f'PRIMER_PAIR_{i}_PRODUCT_SIZE']

        # Penalty score (lower is better)
        penalty = primer3_result[f'PRIMER_PAIR_{i}_PENALTY']

        primer_pair = {
            'pair_id': i,
            'forward_seq': forward_seq,
            'reverse_seq': reverse_seq,
            'forward_tm': round(forward_tm, 2),
            'reverse_tm': round(reverse_tm, 2),
            'tm_diff': round(abs(forward_tm - reverse_tm), 2),
            'forward_gc': round(forward_gc, 2),
            'reverse_gc': round(reverse_gc, 2),
            'forward_length': forward_len,
            'reverse_length': reverse_len,
            'forward_pos': forward_pos,
            'reverse_pos': reverse_pos,
            'amplicon_size': amplicon_size,
            'penalty': round(penalty, 3),
        }

        primers_list.append(primer_pair)

    # Compile results
    results = {
        'primers': primers_list,
        'parameters': {
            'primer_size_range': primer_size_range,
            'tm_range': tm_range,
            'gc_range': gc_range,
            'amplicon_size_range': amplicon_size_range,
            'target_region': target_region,
        },
        'sequence_length': len(sequence),
        'num_primers_found': num_returned,
    }

    return results


def get_primer_properties(primer_seq: str) -> dict:
    """
    Calculate basic properties of a primer sequence.

    Parameters
    ----------
    primer_seq : str
        Primer sequence

    Returns
    -------
    dict
        Dictionary with length, GC%, Tm, and other properties
    """
    primer_seq = primer_seq.upper()

    # Calculate GC content
    gc_count = primer_seq.count('G') + primer_seq.count('C')
    gc_percent = (gc_count / len(primer_seq)) * 100

    # Calculate Tm using nearest-neighbor method
    tm = primer3.calcTm(primer_seq)

    # Check for runs of identical nucleotides
    max_run = max(len(s) for s in primer_seq.replace('A', ' A ').replace('T', ' T ').replace('C', ' C ').replace('G', ' G ').split())

    # Check for 3' GC clamp
    gc_clamp_3prime = sum(1 for base in primer_seq[-5:] if base in 'GC')

    return {
        'length': len(primer_seq),
        'gc_percent': round(gc_percent, 2),
        'tm': round(tm, 2),
        'max_nucleotide_run': max_run,
        'gc_clamp_3prime': gc_clamp_3prime,
    }
