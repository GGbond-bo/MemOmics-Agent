
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
VCF Validation and Quality Control Module

This module provides functions for validating VCF files and generating quality metrics.
"""

import os
import sys
from collections import defaultdict
from pathlib import Path

try:
    import pysam
    import cyvcf2
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip install pysam cyvcf2 pandas numpy")
    sys.exit(1)


def validate_vcf(vcf_path, reference_genome=None):
    """
    Validate VCF file format and check for common issues.

    Parameters
    ----------
    vcf_path : str
        Path to VCF file (can be gzipped)
    reference_genome : str, optional
        Path to reference genome FASTA (for reference allele validation)

    Returns
    -------
    dict
        Validation results with 'is_valid', 'errors', and 'warnings' keys
    """
    results = {
        'is_valid': True,
        'errors': [],
        'warnings': []
    }

    vcf_path = Path(vcf_path)

    # Check file exists
    if not vcf_path.exists():
        results['is_valid'] = False
        results['errors'].append(f"File not found: {vcf_path}")
        return results

    # Check file is not empty
    if vcf_path.stat().st_size == 0:
        results['is_valid'] = False
        results['errors'].append("File is empty")
        return results

    try:
        vcf = cyvcf2.VCF(str(vcf_path))
    except Exception as e:
        results['is_valid'] = False
        results['errors'].append(f"Cannot parse VCF file: {e}")
        return results

    # Validate header
    header_validation = _validate_header(vcf)
    results['warnings'].extend(header_validation['warnings'])
    if not header_validation['is_valid']:
        results['is_valid'] = False
        results['errors'].extend(header_validation['errors'])

    # Validate variants (sample first 10,000)
    variant_validation = _validate_variants(vcf, max_variants=10000, reference_genome=reference_genome)
    results['warnings'].extend(variant_validation['warnings'])
    if not variant_validation['is_valid']:
        results['is_valid'] = False
        results['errors'].extend(variant_validation['errors'])

    vcf.close()

    return results


def _validate_header(vcf):
    """Validate VCF header completeness."""
    results = {'is_valid': True, 'errors': [], 'warnings': []}

    # Check for contigs
    if not vcf.seqnames:
        results['warnings'].append("No contig definitions in header (##contig lines)")

    # Check for required FORMAT fields if samples present
    if vcf.samples and 'GT' not in vcf:
        results['warnings'].append("GT (genotype) FORMAT field not defined in header")

    # Check for common INFO fields
    common_info = ['AC', 'AF', 'AN', 'DP']
    missing_info = [field for field in common_info if field not in vcf]
    if missing_info:
        results['warnings'].append(f"Common INFO fields missing: {', '.join(missing_info)}")

    return results


def _validate_variants(vcf, max_variants=10000, reference_genome=None):
    """Validate variant records for common issues."""
    results = {'is_valid': True, 'errors': [], 'warnings': []}

    seen_positions = set()
    n_checked = 0
    n_duplicates = 0
    n_invalid_coords = 0

    for variant in vcf:
        if n_checked >= max_variants:
            break

        n_checked += 1

        # Check for duplicate positions
        var_id = (variant.CHROM, variant.POS, variant.REF, str(variant.ALT))
        if var_id in seen_positions:
            n_duplicates += 1
        seen_positions.add(var_id)

        # Check valid coordinates
        if variant.POS < 1:
            n_invalid_coords += 1
            if n_invalid_coords <= 5:  # Report first 5
                results['errors'].append(
                    f"Invalid position {variant.CHROM}:{variant.POS} (positions must be >= 1)"
                )

        # Check REF and ALT are not empty
        if not variant.REF or not variant.ALT:
            results['errors'].append(
                f"Missing REF or ALT at {variant.CHROM}:{variant.POS}"
            )
            results['is_valid'] = False

        # Check ALT alleles
        if variant.ALT and variant.ALT[0] is None:
            results['warnings'].append(
                f"No ALT allele at {variant.CHROM}:{variant.POS}"
            )

    # Report duplicate summary
    if n_duplicates > 0:
        results['warnings'].append(
            f"Found {n_duplicates} duplicate variants in first {n_checked} records"
        )

    # Report invalid coordinates summary
    if n_invalid_coords > 0:
        results['is_valid'] = False
        results['errors'].append(
            f"Found {n_invalid_coords} variants with invalid coordinates"
        )

    return results


def vcf_summary_stats(vcf_path):
    """
    Generate summary statistics for a VCF file.

    Parameters
    ----------
    vcf_path : str
        Path to VCF file

    Returns
    -------
    dict
        Summary statistics including variant counts, Ti/Tv ratio, etc.
    """
    vcf = cyvcf2.VCF(str(vcf_path))

    stats = {
        'total_variants': 0,
        'snvs': 0,
        'insertions': 0,
        'deletions': 0,
        'mnvs': 0,
        'complex': 0,
        'multiallelic': 0,
        'transitions': 0,
        'transversions': 0,
        'ti_tv_ratio': 0.0,
        'n_samples': len(vcf.samples),
        'samples': vcf.samples,
        'chromosomes': [],
        'variants_per_chromosome': {}
    }

    chrom_counts = defaultdict(int)
    transitions = {'A>G', 'G>A', 'C>T', 'T>C'}

    for variant in vcf:
        stats['total_variants'] += 1
        chrom_counts[variant.CHROM] += 1

        # Count variant types
        ref_len = len(variant.REF)
        alt_len = len(variant.ALT[0]) if variant.ALT and variant.ALT[0] else 0

        if len(variant.ALT) > 1:
            stats['multiallelic'] += 1

        if ref_len == 1 and alt_len == 1:
            stats['snvs'] += 1

            # Count transitions vs transversions
            change = f"{variant.REF}>{variant.ALT[0]}"
            if change in transitions:
                stats['transitions'] += 1
            else:
                stats['transversions'] += 1

        elif ref_len < alt_len:
            stats['insertions'] += 1
        elif ref_len > alt_len:
            stats['deletions'] += 1
        elif ref_len > 1 and ref_len == alt_len:
            stats['mnvs'] += 1
        else:
            stats['complex'] += 1

    vcf.close()

    # Calculate Ti/Tv ratio
    if stats['transversions'] > 0:
        stats['ti_tv_ratio'] = stats['transitions'] / stats['transversions']

    # Chromosome summary
    stats['chromosomes'] = sorted(chrom_counts.keys())
    stats['variants_per_chromosome'] = dict(chrom_counts)

    return stats


def print_validation_report(validation_results, stats=None):
    """
    Print a formatted validation report.

    Parameters
    ----------
    validation_results : dict
        Results from validate_vcf()
    stats : dict, optional
        Results from vcf_summary_stats()
    """
    print("\n" + "="*60)
    print("VCF VALIDATION REPORT")
    print("="*60)

    # Validation status
    if validation_results['is_valid']:
        print("\n✓ VCF file is VALID")
    else:
        print("\n✗ VCF file has ERRORS")

    # Errors
    if validation_results['errors']:
        print(f"\nERRORS ({len(validation_results['errors'])}):")
        for error in validation_results['errors']:
            print(f"  ✗ {error}")

    # Warnings
    if validation_results['warnings']:
        print(f"\nWARNINGS ({len(validation_results['warnings'])}):")
        for warning in validation_results['warnings']:
            print(f"  ! {warning}")

    # Statistics
    if stats:
        print("\n" + "-"*60)
        print("SUMMARY STATISTICS")
        print("-"*60)
        print(f"Total variants:      {stats['total_variants']:,}")
        print(f"SNVs:                {stats['snvs']:,}")
        print(f"Insertions:          {stats['insertions']:,}")
        print(f"Deletions:           {stats['deletions']:,}")
        print(f"MNVs:                {stats['mnvs']:,}")
        print(f"Complex:             {stats['complex']:,}")
        print(f"Multiallelic sites:  {stats['multiallelic']:,}")
        print(f"\nTransitions:         {stats['transitions']:,}")
        print(f"Transversions:       {stats['transversions']:,}")
        print(f"Ti/Tv ratio:         {stats['ti_tv_ratio']:.2f}")
        print(f"\nSamples:             {stats['n_samples']}")

        if len(stats['samples']) <= 10:
            print(f"  {', '.join(stats['samples'])}")

        print(f"\nChromosomes:         {len(stats['chromosomes'])}")

    print("\n" + "="*60 + "\n")


def test_dependencies():
    """Test that all required dependencies are installed."""
    required = {
        'pysam': pysam,
        'cyvcf2': cyvcf2,
        'pandas': pd,
        'numpy': np
    }

    print("Testing dependencies...")
    all_present = True

    for name, module in required.items():
        try:
            version = getattr(module, '__version__', 'unknown')
            print(f"  ✓ {name} {version}")
        except Exception as e:
            print(f"  ✗ {name} - {e}")
            all_present = False

    if all_present:
        print("\n✓ All dependencies installed")
    else:
        print("\n✗ Some dependencies missing")
        print("Install with: pip install pysam cyvcf2 pandas numpy")

    return all_present


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Validate VCF file')
    parser.add_argument('vcf', help='Path to VCF file')
    parser.add_argument('--stats', action='store_true', help='Generate summary statistics')

    args = parser.parse_args()

    # Run validation
    validation_results = validate_vcf(args.vcf)

    # Optionally generate stats
    stats = None
    if args.stats:
        stats = vcf_summary_stats(args.vcf)

    # Print report
    print_validation_report(validation_results, stats)

    # Exit with error code if validation failed
    sys.exit(0 if validation_results['is_valid'] else 1)
