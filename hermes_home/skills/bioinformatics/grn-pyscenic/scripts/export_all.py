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
Export all pySCENIC results to standard formats.

Saves analysis objects (pickle) for downstream skills and exports
results to CSV/markdown/PDF formats for human analysis.
"""

import os
import pickle
import pandas as pd
from datetime import datetime


def export_all(regulons, auc_matrix, auc_summary, adjacencies=None, output_dir="."):
    """
    Export all pySCENIC results to pickle and CSV formats.

    This function saves all analysis objects and results for downstream use
    and generates a comprehensive analysis report.

    Parameters:
    -----------
    regulons : list
        List of Regulon objects from pySCENIC
    auc_matrix : pd.DataFrame
        AUCell activity matrix (cells x regulons)
    auc_summary : pd.DataFrame
        Summary statistics per regulon
    adjacencies : pd.DataFrame, optional
        Raw TF-target adjacencies from GRNBoost2
    output_dir : str
        Directory to save outputs (default: current directory)

    Examples:
    ---------
    >>> export_all(regulons, auc_matrix, auc_summary, adjacencies, output_dir="scenic_results")

    Outputs:
    --------
    - regulons.pkl - Regulon objects for downstream analysis
    - auc_matrix.pkl - AUCell activity matrix
    - regulons.csv - Human-readable TF-target relationships
    - aucell_matrix.csv - Cell x regulon activity scores
    - aucell_summary.csv - Per-regulon statistics
    - scenic_regulon_summary.csv - Comprehensive regulon summary
    - scenic_report.md - Analysis summary report
    - scenic_analysis_report.pdf - Publication-quality PDF report (if reportlab installed)
    """
    os.makedirs(output_dir, exist_ok=True)

    print("\nExporting pySCENIC results...")

    # 1. Save analysis objects as pickle (CRITICAL for downstream skills)
    print("  Saving analysis objects...")
    regulons_pkl = os.path.join(output_dir, "regulons.pkl")
    with open(regulons_pkl, 'wb') as f:
        pickle.dump(regulons, f)
    print(f"   Saved: {regulons_pkl}")
    print(f"   (Load with: regulons = pickle.load(open('{regulons_pkl}', 'rb')))")

    auc_matrix_pkl = os.path.join(output_dir, "auc_matrix.pkl")
    with open(auc_matrix_pkl, 'wb') as f:
        pickle.dump(auc_matrix, f)
    print(f"   Saved: {auc_matrix_pkl}")
    print(f"   (Load with: auc_matrix = pickle.load(open('{auc_matrix_pkl}', 'rb')))")

    # 2. Export regulons to CSV (human-readable)
    print("  Exporting regulon relationships...")
    regulon_data = []
    for reg in regulons:
        tf = reg.transcription_factor
        for gene in reg.genes:
            regulon_data.append({
                'TF': tf,
                'Regulon': reg.name,
                'Target': gene,
                'N_targets': len(reg.genes)
            })

    regulons_csv = os.path.join(output_dir, "regulons.csv")
    regulon_df = pd.DataFrame(regulon_data)
    regulon_df.to_csv(regulons_csv, index=False)
    print(f"   Saved: {regulons_csv}")

    # 3. Export AUCell matrix
    print("  Exporting AUCell scores...")
    aucell_csv = os.path.join(output_dir, "aucell_matrix.csv")
    auc_matrix.to_csv(aucell_csv)
    print(f"   Saved: {aucell_csv}")

    # 4. Export AUCell summary
    aucell_summary_csv = os.path.join(output_dir, "aucell_summary.csv")
    auc_summary.to_csv(aucell_summary_csv)
    print(f"   Saved: {aucell_summary_csv}")

    # 5. Export adjacencies if provided
    if adjacencies is not None:
        adjacencies_csv = os.path.join(output_dir, "adjacencies.csv")
        adjacencies.to_csv(adjacencies_csv, index=False)
        print(f"   Saved: {adjacencies_csv}")

    # 6. Create regulon summary
    print("  Creating regulon summary...")
    regulon_summary = []
    for reg in regulons:
        regulon_summary.append({
            'Regulon': reg.name,
            'TF': reg.transcription_factor,
            'N_targets': len(reg.genes),
            'Mean_activity': auc_matrix[reg.name].mean() if reg.name in auc_matrix.columns else 0,
            'Std_activity': auc_matrix[reg.name].std() if reg.name in auc_matrix.columns else 0,
            'Max_activity': auc_matrix[reg.name].max() if reg.name in auc_matrix.columns else 0
        })

    summary_df = pd.DataFrame(regulon_summary)
    summary_df = summary_df.sort_values('N_targets', ascending=False)

    summary_csv = os.path.join(output_dir, "scenic_regulon_summary.csv")
    summary_df.to_csv(summary_csv, index=False)
    print(f"   Saved: {summary_csv}")

    # 7. Generate analysis report
    print("  Generating analysis report...")
    report_md = os.path.join(output_dir, "scenic_report.md")
    with open(report_md, 'w') as f:
        f.write("# pySCENIC Analysis Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## Summary Statistics\n\n")
        f.write(f"- **Total regulons identified:** {len(regulons)}\n")
        f.write(f"- **Total TF-target pairs:** {len(regulon_df)}\n")
        f.write(f"- **Cells analyzed:** {auc_matrix.shape[0]}\n")
        f.write(f"- **Mean targets per regulon:** {summary_df['N_targets'].mean():.1f}\n")
        f.write(f"- **Median targets per regulon:** {summary_df['N_targets'].median():.0f}\n\n")

        f.write("## Top 10 Regulons by Target Count\n\n")
        f.write("| Rank | Regulon | TF | Targets | Mean Activity | Std Activity |\n")
        f.write("|------|---------|----|---------|--------------|--------------|\n")
        for idx, row in summary_df.head(10).iterrows():
            f.write(f"| {idx+1} | {row['Regulon']} | {row['TF']} | {row['N_targets']} | "
                   f"{row['Mean_activity']:.3f} | {row['Std_activity']:.3f} |\n")

        f.write("\n## Top 10 Regulons by Activity Variance\n\n")
        summary_df['Var_activity'] = summary_df['Std_activity'] ** 2
        summary_df_sorted = summary_df.sort_values('Var_activity', ascending=False)

        f.write("| Rank | Regulon | TF | Targets | Mean Activity | Variance |\n")
        f.write("|------|---------|----|---------|--------------|---------|\n")
        for idx, (_, row) in enumerate(summary_df_sorted.head(10).iterrows(), 1):
            f.write(f"| {idx} | {row['Regulon']} | {row['TF']} | {row['N_targets']} | "
                   f"{row['Mean_activity']:.3f} | {row['Var_activity']:.4f} |\n")

        f.write("\n## Files Generated\n\n")
        f.write("**Analysis Objects (for downstream use):**\n")
        f.write("- `regulons.pkl` - Regulon objects\n")
        f.write("- `auc_matrix.pkl` - AUCell activity matrix\n\n")
        f.write("**Results (CSV):**\n")
        f.write("- `regulons.csv` - TF-target relationships\n")
        f.write("- `aucell_matrix.csv` - Cell × regulon activities\n")
        f.write("- `aucell_summary.csv` - Regulon statistics\n")
        f.write("- `scenic_regulon_summary.csv` - Comprehensive summary\n")
        if adjacencies is not None:
            f.write("- `adjacencies.csv` - Raw GRNBoost2 adjacencies\n")

    print(f"   Saved: {report_md}")

    # 8. Generate PDF analysis report
    print("  Generating PDF analysis report...")
    pdf_path = os.path.join(output_dir, "scenic_analysis_report.pdf")
    try:
        from scripts.generate_report import generate_report
        result = generate_report(
            regulons=regulons,
            auc_matrix=auc_matrix,
            auc_summary=auc_summary,
            adjacencies=adjacencies,
            output_dir=output_dir,
        )
        if not result:
            print("   (Install reportlab for PDF reports: pip install reportlab)")
    except Exception as e:
        print(f"   PDF generation skipped: {e}")
        print("   (Markdown report still available)")

    print("\n=== Export Complete ===")
    print(f"\nAll results saved to: {output_dir}")
    print("\nKey files:")
    print(f"  - {regulons_pkl} (for downstream analysis)")
    print(f"  - {auc_matrix_pkl} (cell-level activities)")
    print(f"  - {summary_csv} (regulon summary)")
    print(f"  - {report_md} (analysis report - markdown)")
    print(f"  - {pdf_path} (analysis report - PDF)")
