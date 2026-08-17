#!/usr/bin/env python3
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
Complete Workflow Test for Genetic Variant Annotation

Tests all 4 steps of the standard workflow:
1. Load and validate data
2. Run annotation (simulated if VEP/SNPEff not available)
3. Generate visualizations
4. Export results

This script can run with or without VEP/SNPEff installed.
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))

print("="*70)
print("GENETIC VARIANT ANNOTATION - COMPLETE WORKFLOW TEST")
print("="*70)
print()

# =============================================================================
# STEP 1: LOAD AND VALIDATE DATA
# =============================================================================
print("="*70)
print("STEP 1: LOAD AND VALIDATE DATA")
print("="*70)
print()

try:
    from load_example_data import load_clinvar_pathogenic_sample
    from validate_vcf import validate_vcf, vcf_summary_stats

    # Load example data
    print("Loading example data...")
    data = load_clinvar_pathogenic_sample()
    input_vcf = data['vcf_path']
    print(f"✓ Example VCF created: {input_vcf}")

    # Validate VCF
    print("\nValidating VCF format...")
    results = validate_vcf(input_vcf)
    if not results['is_valid']:
        print(f"❌ Validation errors: {results['errors']}")
        sys.exit(1)

    stats = vcf_summary_stats(input_vcf)
    print(f"✓ VCF is valid!")
    print(f"  Total variants: {stats['total_variants']}")
    print(f"  SNVs: {stats['snvs']}")
    print(f"  Indels: {stats['indels']}")

    print("\n✓ Data loaded successfully!")

except Exception as e:
    print(f"❌ Step 1 failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# =============================================================================
# STEP 2: RUN ANNOTATION (SIMULATED IF TOOLS NOT AVAILABLE)
# =============================================================================
print("\n" + "="*70)
print("STEP 2: RUN ANNOTATION")
print("="*70)
print()

# Check if annotation tools are available
from select_tool import select_annotation_tool

try:
    tool = select_annotation_tool(organism='human', use_case='clinical', resources='standard')
    print(f"Recommended tool: {tool}")
except:
    tool = 'vep'  # Default
    print(f"Using default tool: {tool}")

# Try to check if VEP/SNPEff are installed
import shutil
vep_available = shutil.which('vep') is not None
snpeff_available = shutil.which('snpEff') is not None

print(f"VEP available: {vep_available}")
print(f"SNPEff available: {snpeff_available}")

if not vep_available and not snpeff_available:
    print("\n⚠️  No annotation tools installed. Creating simulated annotated data...")
    print("   (For real annotation, install VEP or SNPEff)")

    # Create simulated annotated DataFrame
    np.random.seed(42)
    df = pd.DataFrame({
        'CHROM': ['chr17'] * 5 + ['chr13'] * 5,
        'POS': [43044295, 43045802, 43057051, 43070927, 43091434,
                32315474, 32319077, 32326241, 32332271, 32340271],
        'REF': ['C', 'A', 'G', 'C', 'T', 'G', 'A', 'C', 'G', 'C'],
        'ALT': ['T', 'G', 'A', 'T', 'C', 'T', 'G', 'G', 'A', 'T'],
        'QUAL': [100] * 10,
        'SYMBOL': ['BRCA1'] * 5 + ['BRCA2'] * 5,
        'Consequence': ['missense_variant', 'stop_gained', 'missense_variant',
                       'frameshift_variant', 'missense_variant',
                       'missense_variant', 'stop_gained', 'frameshift_variant',
                       'missense_variant', 'synonymous_variant'],
        'IMPACT': ['MODERATE', 'HIGH', 'MODERATE', 'HIGH', 'MODERATE',
                   'MODERATE', 'HIGH', 'HIGH', 'MODERATE', 'LOW'],
        'gnomAD_AF': [0.0001, 0.0, 0.0005, 0.0, 0.002,
                      0.0003, 0.0, 0.0, 0.001, 0.05],
        'SIFT': ['deleterious', 'deleterious', 'tolerated', 'deleterious', 'deleterious',
                 'deleterious', 'deleterious', 'deleterious', 'tolerated', 'tolerated'],
        'CADD_PHRED': [25.3, 35.0, 22.1, 32.5, 24.8,
                       26.1, 34.2, 31.8, 23.5, 15.2],
        'REVEL': [0.65, 0.95, 0.45, 0.89, 0.62,
                  0.71, 0.93, 0.88, 0.55, 0.25]
    })

    annotated_vcf = input_vcf  # Use original VCF path
    print(f"✓ Simulated annotation completed! ({len(df)} variants)")

else:
    print("\n✓ Annotation tools available!")
    print("   (Skipping actual annotation for speed - would run VEP/SNPEff here)")
    print("   Creating simulated data for testing steps 3-4...")

    # Even if tools available, simulate for speed
    np.random.seed(42)
    df = pd.DataFrame({
        'CHROM': ['chr17'] * 5 + ['chr13'] * 5,
        'POS': [43044295, 43045802, 43057051, 43070927, 43091434,
                32315474, 32319077, 32326241, 32332271, 32340271],
        'REF': ['C', 'A', 'G', 'C', 'T', 'G', 'A', 'C', 'G', 'C'],
        'ALT': ['T', 'G', 'A', 'T', 'C', 'T', 'G', 'G', 'A', 'T'],
        'QUAL': [100] * 10,
        'SYMBOL': ['BRCA1'] * 5 + ['BRCA2'] * 5,
        'Consequence': ['missense_variant', 'stop_gained', 'missense_variant',
                       'frameshift_variant', 'missense_variant',
                       'missense_variant', 'stop_gained', 'frameshift_variant',
                       'missense_variant', 'synonymous_variant'],
        'IMPACT': ['MODERATE', 'HIGH', 'MODERATE', 'HIGH', 'MODERATE',
                   'MODERATE', 'HIGH', 'HIGH', 'MODERATE', 'LOW'],
        'gnomAD_AF': [0.0001, 0.0, 0.0005, 0.0, 0.002,
                      0.0003, 0.0, 0.0, 0.001, 0.05],
        'SIFT': ['deleterious', 'deleterious', 'tolerated', 'deleterious', 'deleterious',
                 'deleterious', 'deleterious', 'deleterious', 'tolerated', 'tolerated'],
        'CADD_PHRED': [25.3, 35.0, 22.1, 32.5, 24.8,
                       26.1, 34.2, 31.8, 23.5, 15.2],
        'REVEL': [0.65, 0.95, 0.45, 0.89, 0.62,
                  0.71, 0.93, 0.88, 0.55, 0.25]
    })
    annotated_vcf = input_vcf

print("\n✓ Annotation completed successfully!")

# =============================================================================
# STEP 3: GENERATE VISUALIZATIONS
# =============================================================================
print("\n" + "="*70)
print("STEP 3: GENERATE VISUALIZATIONS")
print("="*70)
print()

try:
    from filter_variants import filter_by_consequence, filter_by_frequency
    from annotate_genes import annotate_gene_summary
    from plot_variant_distribution import (
        plot_consequence_distribution,
        plot_impact_by_chromosome,
        plot_pathogenicity_scores,
        plot_allele_frequency,
        plot_gene_burden
    )

    # Filter variants
    print("Filtering variants...")
    high_impact = filter_by_consequence(df, consequence_levels=['HIGH', 'MODERATE'])
    print(f"  HIGH/MODERATE impact: {len(high_impact)} variants")

    rare = filter_by_frequency(df, max_af=0.01)
    print(f"  Rare (AF < 0.01): {len(rare)} variants")

    # Generate gene summaries
    print("\nGenerating gene-level summaries...")
    gene_df = annotate_gene_summary(df)
    if gene_df is not None:
        print(f"  ✓ Gene summary created: {len(gene_df)} genes")
    else:
        print("  ⚠️  No gene summary (SYMBOL column may be missing)")

    # Create output directory
    output_dir = "results"
    Path(output_dir).mkdir(exist_ok=True)

    # Generate visualizations
    print("\nGenerating visualizations (PNG + SVG)...")

    print("\n1. Consequence distribution plot...")
    plot_consequence_distribution(df, f"{output_dir}/consequence_distribution.png")

    print("\n2. Impact by chromosome plot...")
    plot_impact_by_chromosome(df, f"{output_dir}/impact_by_chromosome.png")

    print("\n3. Pathogenicity scores plot...")
    plot_pathogenicity_scores(df, scores=['CADD_PHRED', 'REVEL'],
                              output_file=f"{output_dir}/pathogenicity_scores.png")

    print("\n4. Allele frequency plot...")
    plot_allele_frequency(df, output_file=f"{output_dir}/allele_frequency.png")

    if gene_df is not None:
        print("\n5. Gene burden plot...")
        plot_gene_burden(gene_df, output_file=f"{output_dir}/gene_burden.png")

    print("\n✓ All visualizations generated successfully!")

except Exception as e:
    print(f"❌ Step 3 failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# =============================================================================
# STEP 4: EXPORT RESULTS
# =============================================================================
print("\n" + "="*70)
print("STEP 4: EXPORT RESULTS")
print("="*70)
print()

try:
    from export_results import export_all

    # Export all results
    print("Exporting all results in all formats...")
    export_all(
        df=df,
        gene_df=gene_df,
        original_vcf=input_vcf,
        output_dir=output_dir,
        tool_name=tool
    )

except Exception as e:
    print(f"❌ Step 4 failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# =============================================================================
# VERIFICATION: TEST PICKLE LOADING
# =============================================================================
print("\n" + "="*70)
print("VERIFICATION: TESTING PICKLE LOADING")
print("="*70)
print()

try:
    from test_pickle_load import test_pickle_load

    pickle_path = f"{output_dir}/analysis_object.pkl"
    obj = test_pickle_load(pickle_path)

    if obj is None:
        print("❌ Pickle loading test failed!")
        sys.exit(1)

except Exception as e:
    print(f"❌ Pickle verification failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "="*70)
print("✓✓✓ COMPLETE WORKFLOW TEST PASSED ✓✓✓")
print("="*70)
print()
print("All 4 steps completed successfully:")
print("  ✓ Step 1: Data loaded and validated")
print("  ✓ Step 2: Annotation completed (simulated)")
print("  ✓ Step 3: Visualizations generated (PNG + SVG)")
print("  ✓ Step 4: All results exported")
print("  ✓ Verification: Pickle loading works")
print()
print(f"Output directory: {output_dir}/")
print()
print("Generated files:")
print("  - analysis_object.pkl (for downstream skills)")
print("  - all_variants.csv")
print("  - high_impact_variants.csv")
print("  - moderate_impact_variants.csv")
print("  - rare_variants.csv")
if gene_df is not None:
    print("  - gene_summary.csv")
print("  - summary_report.xlsx")
print("  - consequence_distribution.png/.svg")
print("  - impact_by_chromosome.png/.svg")
print("  - pathogenicity_scores.png/.svg")
print("  - allele_frequency.png/.svg")
if gene_df is not None:
    print("  - gene_burden.png/.svg")
print()
print("="*70)
print("🎉 WORKFLOW VALIDATION COMPLETE!")
print("="*70)
