
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
Calculate melting temperatures using multiple methods.

This module provides functions for calculating primer Tm using various
algorithms and salt correction methods.
"""

import primer3
from Bio.SeqUtils import MeltingTemp as mt
from Bio.Seq import Seq
from typing import Dict


def calculate_tm_comprehensive(
    primer_sequence: str,
    method: str = "nearest_neighbor",
    salt_conc: float = 50.0,
    dna_conc: float = 200.0,
    mg_conc: float = 0.0,
    dntp_conc: float = 0.0
) -> Dict:
    """
    Calculate melting temperature using multiple methods.

    Parameters
    ----------
    primer_sequence : str
        Primer sequence
    method : str
        Tm calculation method:
        - "nearest_neighbor" (most accurate, default)
        - "salt_adjusted" (salt-adjusted formula)
        - "gc_content" (simple GC% method)
        - "all" (calculate using all methods)
    salt_conc : float
        Monovalent cation (Na+, K+) concentration in mM. Default: 50.0
    dna_conc : float
        DNA/primer concentration in nM. Default: 200.0
    mg_conc : float
        Mg2+ concentration in mM. Default: 0.0
    dntp_conc : float
        dNTP concentration in mM. Default: 0.0

    Returns
    -------
    dict
        Dictionary with Tm values from different methods

    Example
    -------
    >>> tm_results = calculate_tm_comprehensive(
    ...     "ATGCGTACGATCGATCG",
    ...     method="all",
    ...     salt_conc=50.0
    ... )
    >>> print(f"Nearest-Neighbor Tm: {tm_results['tm_nn']:.1f}°C")
    """

    # Validate input
    primer_sequence = primer_sequence.upper().strip()

    if not all(base in 'ATCGN' for base in primer_sequence):
        raise ValueError("Primer must contain only A, T, C, G, or N")

    if len(primer_sequence) < 10:
        raise ValueError("Primer too short for accurate Tm calculation (minimum 10 bp)")

    results = {
        'primer_sequence': primer_sequence,
        'primer_length': len(primer_sequence),
    }

    # Method 1: Nearest-Neighbor (most accurate)
    if method in ["nearest_neighbor", "all"]:
        # Using primer3
        tm_nn_primer3 = primer3.calcTm(
            primer_sequence,
            mv_conc=salt_conc,
            dv_conc=mg_conc,
            dntp_conc=dntp_conc,
            dna_conc=dna_conc
        )
        results['tm_nn'] = round(tm_nn_primer3, 2)
        results['method_nn'] = "Primer3 (SantaLucia 1998)"

        # Also calculate using Biopython for comparison
        try:
            tm_nn_biopython = mt.Tm_NN(
                Seq(primer_sequence),
                Na=salt_conc,
                Mg=mg_conc,
                dNTPs=dntp_conc,
                saltcorr=7  # Owczarzy et al. 2008
            )
            results['tm_nn_biopython'] = round(tm_nn_biopython, 2)
        except:
            pass

    # Method 2: Salt-adjusted formula
    if method in ["salt_adjusted", "all"]:
        # Wallace rule with salt adjustment
        # Tm = 2(A+T) + 4(G+C) - 16.6*log10[Na+] + 0.41(%GC)
        gc_count = primer_sequence.count('G') + primer_sequence.count('C')
        at_count = primer_sequence.count('A') + primer_sequence.count('T')
        gc_percent = (gc_count / len(primer_sequence)) * 100

        import math
        tm_basic = 2 * at_count + 4 * gc_count
        salt_correction = 16.6 * math.log10(salt_conc / 1000.0)  # Convert mM to M
        gc_correction = 0.41 * gc_percent

        tm_salt_adjusted = tm_basic - salt_correction + gc_correction
        results['tm_salt_adjusted'] = round(tm_salt_adjusted, 2)
        results['method_salt'] = "Wallace with salt correction"

    # Method 3: Simple GC content
    if method in ["gc_content", "all"]:
        gc_count = primer_sequence.count('G') + primer_sequence.count('C')
        at_count = primer_sequence.count('A') + primer_sequence.count('T')

        # Basic Wallace rule: Tm = 2(A+T) + 4(G+C)
        tm_gc = 2 * at_count + 4 * gc_count
        results['tm_gc'] = round(tm_gc, 2)
        results['method_gc'] = "Wallace rule (GC content)"

    # Method 4: %GC-based formula (for primers >13 bp)
    if method in ["all"] and len(primer_sequence) > 13:
        gc_count = primer_sequence.count('G') + primer_sequence.count('C')
        gc_percent = (gc_count / len(primer_sequence)) * 100

        # Tm = 64.9 + 41*(G+C-16.4)/(A+T+G+C)
        tm_percent = 64.9 + 41 * (gc_percent - 16.4) / 100
        results['tm_percent'] = round(tm_percent, 2)
        results['method_percent'] = "%GC formula"

    # Add parameters used
    results['parameters'] = {
        'salt_conc_mM': salt_conc,
        'dna_conc_nM': dna_conc,
        'mg_conc_mM': mg_conc,
        'dntp_conc_mM': dntp_conc,
    }

    # Add recommendation
    if method == "all":
        results['recommended_tm'] = results.get('tm_nn', results.get('tm_salt_adjusted'))
        results['recommendation'] = "Use nearest-neighbor (tm_nn) for most accurate results"

    return results


def calculate_tm_range(
    primer_list: list,
    method: str = "nearest_neighbor",
    **kwargs
) -> Dict:
    """
    Calculate Tm for multiple primers and return range.

    Parameters
    ----------
    primer_list : list of str
        List of primer sequences
    method : str
        Tm calculation method
    **kwargs
        Additional parameters for calculate_tm_comprehensive

    Returns
    -------
    dict
        Dictionary with Tm values and statistics

    Example
    -------
    >>> primers = ["ATGCGTACG...", "CGTAGCTA...", "GCTATCGA..."]
    >>> tm_range = calculate_tm_range(primers)
    >>> print(f"Tm range: {tm_range['tm_min']}°C - {tm_range['tm_max']}°C")
    """

    tm_values = []
    primer_tms = []

    for primer in primer_list:
        tm_result = calculate_tm_comprehensive(primer, method=method, **kwargs)
        tm_key = 'tm_nn' if method == "nearest_neighbor" else f'tm_{method}'
        tm = tm_result.get(tm_key)

        if tm is not None:
            tm_values.append(tm)
            primer_tms.append({
                'sequence': primer,
                'tm': tm,
            })

    if not tm_values:
        raise ValueError("Could not calculate Tm for any primers")

    tm_min = min(tm_values)
    tm_max = max(tm_values)
    tm_mean = sum(tm_values) / len(tm_values)
    tm_range = tm_max - tm_min

    return {
        'num_primers': len(primer_list),
        'primer_tms': primer_tms,
        'tm_min': round(tm_min, 2),
        'tm_max': round(tm_max, 2),
        'tm_mean': round(tm_mean, 2),
        'tm_range': round(tm_range, 2),
        'tm_compatible': tm_range <= 5.0,  # All primers within 5°C
        'method': method,
    }


def optimize_tm(
    primer_sequence: str,
    target_tm: float,
    tolerance: float = 2.0,
    max_length_change: int = 3
) -> Dict:
    """
    Suggest primer modifications to achieve target Tm.

    Parameters
    ----------
    primer_sequence : str
        Original primer sequence
    target_tm : float
        Desired melting temperature
    tolerance : float
        Acceptable Tm deviation from target. Default: 2.0°C
    max_length_change : int
        Maximum bases to add/remove. Default: 3

    Returns
    -------
    dict
        Suggestions for achieving target Tm

    Example
    -------
    >>> suggestions = optimize_tm("ATGCGTACGATCG", target_tm=60.0)
    >>> for s in suggestions['modifications']:
    ...     print(f"{s['action']}: New Tm = {s['new_tm']}°C")
    """

    # Calculate current Tm
    current_result = calculate_tm_comprehensive(primer_sequence)
    current_tm = current_result['tm_nn']

    modifications = []

    # If already within tolerance, no changes needed
    if abs(current_tm - target_tm) <= tolerance:
        return {
            'current_tm': current_tm,
            'target_tm': target_tm,
            'needs_optimization': False,
            'message': f"Primer Tm ({current_tm:.1f}°C) is within tolerance of target ({target_tm:.1f}°C)",
        }

    # Try shortening (if Tm too high)
    if current_tm > target_tm:
        for i in range(1, max_length_change + 1):
            # Try removing from 5' end
            shortened_5 = primer_sequence[i:]
            if len(shortened_5) >= 15:  # Keep minimum length
                tm_5 = calculate_tm_comprehensive(shortened_5)['tm_nn']
                modifications.append({
                    'action': f"Remove {i} bp from 5' end",
                    'new_sequence': shortened_5,
                    'new_tm': tm_5,
                    'tm_difference': abs(tm_5 - target_tm),
                })

            # Try removing from 3' end
            shortened_3 = primer_sequence[:-i]
            if len(shortened_3) >= 15:
                tm_3 = calculate_tm_comprehensive(shortened_3)['tm_nn']
                modifications.append({
                    'action': f"Remove {i} bp from 3' end",
                    'new_sequence': shortened_3,
                    'new_tm': tm_3,
                    'tm_difference': abs(tm_3 - target_tm),
                })

    # Try lengthening (if Tm too low)
    else:
        modifications.append({
            'action': f"Increase primer length by {max_length_change} bp",
            'new_sequence': None,
            'recommendation': "Extend primer into flanking sequence to increase Tm",
        })

    # Sort by closest to target Tm
    modifications.sort(key=lambda x: x.get('tm_difference', float('inf')))

    return {
        'current_tm': current_tm,
        'target_tm': target_tm,
        'needs_optimization': True,
        'tm_difference': abs(current_tm - target_tm),
        'modifications': modifications[:5],  # Top 5 suggestions
        'recommendation': "Try the suggested modifications to achieve target Tm",
    }
