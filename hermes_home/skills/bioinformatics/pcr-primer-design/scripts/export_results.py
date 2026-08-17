
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
Export primers in multiple formats.

This module provides functions to export primer designs in various formats
for ordering, documentation, and analysis.
"""

import json
import csv
import os
from typing import Dict, List
from datetime import datetime


# Minimum byte size a real .xlsx must exceed. A valid openpyxl workbook (zipped
# XML) is several KB even when nearly empty; anything below this indicates a
# truncated/0-byte write that would open as a corrupt file.
_MIN_XLSX_BYTES = 1000


def _verify_nonempty(path: str, min_bytes: int = _MIN_XLSX_BYTES) -> bool:
    """
    Return True iff ``path`` exists and is larger than ``min_bytes``.

    Used after writing Excel files to catch silent 0-byte / truncated writes
    (e.g. when an engine error left an empty file handle behind).
    """
    try:
        return os.path.exists(path) and os.path.getsize(path) > min_bytes
    except OSError:
        return False


def _excel_fallback_to_csv(sheets: Dict[str, "object"], output_file: str) -> str:
    """
    Fall back to CSV when an Excel write fails or produces an empty file.

    ``sheets`` maps sheet-name -> pandas DataFrame. The first (primary) sheet is
    written to ``<output_file minus .xlsx>.csv``; any additional sheets are written
    to ``<base>__<sheet>.csv``. Returns the path of the primary CSV.
    """
    base, _ = os.path.splitext(output_file)
    primary_csv = base + ".csv"
    items = list(sheets.items())
    for i, (sheet_name, df) in enumerate(items):
        target = primary_csv if i == 0 else f"{base}__{sheet_name}.csv"
        try:
            df.to_csv(target, index=False)
        except Exception as csv_err:  # last-resort: do not crash the pipeline
            print(f"⚠ CSV fallback for sheet '{sheet_name}' also failed: {csv_err}")
    return primary_csv


# Human-readable phrasing for each specificity_status value (mirrors the
# controlled vocabulary in validate_specificity.SPECIFICITY_STATUS). Kept local
# so export_results has no hard dependency on validate_specificity at import.
_SPECIFICITY_STATUS_LABELS = {
    'in_silico_on_target_only':
        "Performed (IN-SILICO, ON-TARGET TRANSCRIPT ONLY — genome-wide / "
        "pseudogene & paralog off-targets NOT checked)",
    'flagged_high_risk_unverified':
        "FLAGGED HIGH-RISK, UNVERIFIED (pseudogene/paralog-prone target; only "
        "in-silico on-target performed — genome-wide check still required)",
    'local_blast_passed':
        "Performed (local BLAST, genome-wide — passed)",
    'local_blast_failed':
        "Performed (local BLAST, genome-wide — OFF-TARGETS DETECTED)",
    'primer_blast_passed':
        "Performed (NCBI Primer-BLAST, genome-wide — passed)",
    'not_run':
        "NOT PERFORMED (no specificity check was run)",
}


def _specificity_status_from_validation(validation_results: Dict) -> str:
    """
    Pull the specificity_status out of a validation_results dict.

    Looks under validation_results['specificity']['specificity_status'] first
    (the normal location), then a top-level 'specificity_status'. Returns
    'not_run' when nothing usable is found so reports never silently imply a
    check happened.
    """
    if not validation_results:
        return 'not_run'
    spec = validation_results.get('specificity')
    if isinstance(spec, dict) and spec.get('specificity_status'):
        return spec['specificity_status']
    if validation_results.get('specificity_status'):
        return validation_results['specificity_status']
    return 'not_run'


def export_primers(
    primers: Dict,
    format: str = "csv",
    output_file: str = None,
    include_validation: bool = True,
    validation_results: Dict = None
) -> str:
    """
    Export primers to various formats.

    Parameters
    ----------
    primers : dict
        Primer design results
    format : str
        Export format: "csv", "excel", "json", "idt_order", "miqe_checklist"
    output_file : str, optional
        Output file path. If None, returns string.
    include_validation : bool
        Include validation results if available. Default: True
    validation_results : dict, optional
        Validation results to include

    Returns
    -------
    str
        Exported data (if output_file is None) or file path

    Example
    -------
    >>> export_primers(
    ...     primers=primer_results,
    ...     format="csv",
    ...     output_file="primers.csv"
    ... )
    """

    if format == "csv":
        return _export_csv(primers, output_file, include_validation, validation_results)
    elif format == "excel":
        return _export_excel(primers, output_file, include_validation, validation_results)
    elif format == "json":
        return _export_json(primers, output_file, include_validation, validation_results)
    elif format == "idt_order":
        return _export_idt_order(primers, output_file)
    elif format == "miqe_checklist":
        return _export_miqe_checklist(primers, output_file, validation_results)
    else:
        raise ValueError(f"Unknown export format: {format}")


def _export_csv(
    primers: Dict,
    output_file: str = None,
    include_validation: bool = True,
    validation_results: Dict = None
) -> str:
    """Export to CSV format."""

    rows = []

    # Header
    header = [
        'Pair_ID', 'Forward_Sequence', 'Reverse_Sequence',
        'Amplicon_Size_bp', 'Forward_Tm_C', 'Reverse_Tm_C', 'Tm_Diff_C',
        'Forward_GC_%', 'Reverse_GC_%',
        'Forward_Length', 'Reverse_Length',
        'Forward_Position', 'Reverse_Position',
        'Design_Quality_Score'
    ]

    # Add validation columns if available
    if include_validation and validation_results:
        header.extend(['Specificity', 'Specificity_Status',
                       'Pseudogene_Risk', 'Has_Dimers', 'Has_Secondary_Structures'])

    rows.append(header)

    # Specificity status is per-design (not per-pair), computed once.
    spec_status = _specificity_status_from_validation(validation_results) \
        if (include_validation and validation_results) else None
    pseudo_risk = (validation_results or {}).get('specificity', {}).get('pseudogene_risk') \
        if (include_validation and validation_results) else None

    # Data rows
    for pair in primers.get('primers', []):
        row = [
            pair.get('pair_id', ''),
            pair['forward_seq'],
            pair['reverse_seq'],
            pair['amplicon_size'],
            pair['forward_tm'],
            pair['reverse_tm'],
            pair['tm_diff'],
            pair['forward_gc'],
            pair['reverse_gc'],
            pair['forward_length'],
            pair['reverse_length'],
            pair['forward_pos'],
            pair['reverse_pos'],
            pair['penalty'],
        ]

        # Add validation data
        if include_validation and validation_results:
            row.extend([
                validation_results.get('specificity', {}).get('is_specific', 'N/A'),
                spec_status if spec_status is not None else 'N/A',
                pseudo_risk if pseudo_risk is not None else 'N/A',
                validation_results.get('dimers', {}).get('has_issues', 'N/A'),
                validation_results.get('secondary_structures', {}).get('has_issues', 'N/A'),
            ])

        rows.append(row)

    # Write to file or return string
    if output_file:
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        return output_file
    else:
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        return output.getvalue()


def _export_excel(
    primers: Dict,
    output_file: str,
    include_validation: bool = True,
    validation_results: Dict = None
) -> str:
    """Export to Excel format with multiple sheets."""

    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas required for Excel export. Install with: pip install pandas openpyxl")

    # Prepare primers dataframe
    primer_data = []
    for pair in primers.get('primers', []):
        primer_data.append({
            'Pair_ID': pair.get('pair_id', ''),
            'Forward_Sequence': pair['forward_seq'],
            'Reverse_Sequence': pair['reverse_seq'],
            'Amplicon_Size_bp': pair['amplicon_size'],
            'Forward_Tm_C': pair['forward_tm'],
            'Reverse_Tm_C': pair['reverse_tm'],
            'Tm_Diff_C': pair['tm_diff'],
            'Forward_GC_%': pair['forward_gc'],
            'Reverse_GC_%': pair['reverse_gc'],
            'Forward_Length': pair['forward_length'],
            'Reverse_Length': pair['reverse_length'],
            'Design_Quality': pair['penalty'],
        })

    df_primers = pd.DataFrame(primer_data)

    # Assemble the sheets up front so the same data can be reused for a CSV
    # fallback if the Excel write fails.
    sheets = {'Primers': df_primers}

    params = primers.get('parameters', {})
    sheets['Parameters'] = pd.DataFrame([params])

    if include_validation and validation_results:
        val_data = []
        for key, value in validation_results.items():
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    val_data.append({
                        'Category': key,
                        'Check': subkey,
                        'Result': str(subvalue)
                    })
        if val_data:
            sheets['Validation'] = pd.DataFrame(val_data)

    # Write to Excel with verification + CSV fallback. We never leave a silent
    # 0-byte / truncated .xlsx behind.
    try:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            for sheet_name, df in sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    except Exception as e:
        print(f"⚠ Excel export failed ({e}); falling back to CSV.")
        return _excel_fallback_to_csv(sheets, output_file)

    if not _verify_nonempty(output_file):
        print(f"⚠ Excel file '{output_file}' is missing or suspiciously small "
              f"(<{_MIN_XLSX_BYTES} bytes); falling back to CSV.")
        return _excel_fallback_to_csv(sheets, output_file)

    return output_file


def _export_json(
    primers: Dict,
    output_file: str = None,
    include_validation: bool = True,
    validation_results: Dict = None
) -> str:
    """Export to JSON format."""

    export_data = {
        'metadata': {
            'generated': datetime.now().isoformat(),
            'sequence_length': primers.get('sequence_length'),
            'num_primers': primers.get('num_primers_found'),
            # Surface the specificity status prominently in metadata so consumers
            # don't have to dig into the validation block to learn what was checked.
            'specificity_status': _specificity_status_from_validation(
                validation_results if (include_validation and validation_results) else None
            ),
        },
        'parameters': primers.get('parameters', {}),
        'primers': primers.get('primers', []),
    }

    if include_validation and validation_results:
        export_data['validation'] = validation_results

    # Write to file or return string
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)
        return output_file
    else:
        return json.dumps(export_data, indent=2)


def _export_idt_order(primers: Dict, output_file: str = None) -> str:
    """
    Export in IDT (Integrated DNA Technologies) order format.

    Format: Name, Sequence, Scale, Purification
    """

    lines = []
    lines.append("Name\tSequence\tScale\tPurification")

    for i, pair in enumerate(primers.get('primers', []), 1):
        # Forward primer
        fwd_name = f"Primer_Pair{i}_Forward"
        lines.append(f"{fwd_name}\t{pair['forward_seq']}\t25nm\tSTD")

        # Reverse primer
        rev_name = f"Primer_Pair{i}_Reverse"
        lines.append(f"{rev_name}\t{pair['reverse_seq']}\t25nm\tSTD")

        # Probe if present
        if 'probe_seq' in pair:
            probe_name = f"Primer_Pair{i}_Probe"
            lines.append(f"{probe_name}\t{pair['probe_seq']}\t25nm\tHPLC")

    content = "\n".join(lines)

    if output_file:
        with open(output_file, 'w') as f:
            f.write(content)
        return output_file
    else:
        return content


def _export_miqe_checklist(
    primers: Dict,
    output_file: str,
    validation_results: Dict = None
) -> str:
    """
    Export MIQE compliance checklist.

    Creates an Excel file with MIQE checklist pre-filled where possible. The
    in-silico specificity row is qualified with the actual ``specificity_status``
    (from ``validation_results``) so an on-target-only check is never presented
    as a genome-wide pass. Falls back to CSV if the Excel write fails or yields a
    suspiciously small file.

    Parameters
    ----------
    primers : dict
        Primer design results.
    output_file : str
        Output .xlsx path (CSV fallback uses the same base name).
    validation_results : dict, optional
        Validation results carrying a ``specificity`` sub-dict with
        ``specificity_status`` (and optional pseudogene_risk fields). Backward-
        compatible: if omitted, the specificity row reports 'NOT PERFORMED'.
    """

    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas required for MIQE checklist. Install with: pip install pandas openpyxl")

    # Determine the honest specificity wording from what was actually run.
    spec_status = _specificity_status_from_validation(validation_results)
    spec_label = _SPECIFICITY_STATUS_LABELS.get(spec_status, f"Unknown ({spec_status})")

    spec_dict = (validation_results or {}).get('specificity', {})
    pseudo_risk = spec_dict.get('pseudogene_risk')
    pseudo_reason = spec_dict.get('pseudogene_risk_reason', '')
    if pseudo_risk is True:
        pseudo_value = f"HIGH RISK — {pseudo_reason}"
    elif pseudo_risk is False:
        pseudo_value = "Not flagged"
    else:
        pseudo_value = "Not assessed (no gene symbol provided)"

    # MIQE essential information
    miqe_items = [
        # Experimental Design
        ('Experimental Design', 'qPCR purpose', '', 'Essential'),
        ('Experimental Design', 'Experimental design', '', 'Essential'),
        ('Experimental Design', 'Sample nature', '', 'Essential'),

        # Sample
        ('Sample', 'Description', '', 'Essential'),
        ('Sample', 'Volume/mass', '', 'Essential'),
        ('Sample', 'Storage conditions', '', 'Essential'),
        ('Sample', 'RNA/DNA quality', '', 'Essential'),

        # Primers
        ('Primers', 'Primer sequences', 'See Primers sheet', 'Essential'),
        ('Primers', 'Location on target', f"{primers.get('primers', [{}])[0].get('forward_pos', 'N/A')} - {primers.get('primers', [{}])[0].get('reverse_pos', 'N/A')}", 'Essential'),
        ('Primers', 'Amplicon length', f"{primers.get('primers', [{}])[0].get('amplicon_size', 'N/A')} bp", 'Essential'),
        ('Primers', 'In silico specificity check', spec_label, 'Essential'),
        ('Primers', 'Specificity status (machine)', spec_status, 'Essential'),
        ('Primers', 'Pseudogene/paralog risk', pseudo_value, 'Essential'),
        ('Primers', 'Empirical specificity check', '', 'Essential'),

        # Protocol
        ('Protocol', 'Complete reaction conditions', '', 'Essential'),
        ('Protocol', 'Reaction volume', '', 'Essential'),
        ('Protocol', 'Primer concentration', '', 'Essential'),
        ('Protocol', 'Cycling conditions', '', 'Essential'),

        # Validation
        ('Validation', 'Evidence of optimization', '', 'Essential'),
        ('Validation', 'Specificity (melt curve)', '', 'Essential'),
        ('Validation', 'Standard curve slope', '', 'Essential'),
        ('Validation', 'PCR efficiency', '', 'Essential'),
        ('Validation', 'R²', '', 'Essential'),
        ('Validation', 'Linear dynamic range', '', 'Essential'),
        ('Validation', 'Cq variation at LOD', '', 'Essential'),

        # Data Analysis
        ('Data Analysis', 'Cq method', '', 'Essential'),
        ('Data Analysis', 'Outlier identification', '', 'Essential'),
        ('Data Analysis', 'Results of NTCs', '', 'Essential'),
        ('Data Analysis', 'Normalization method', '', 'Essential'),
        ('Data Analysis', 'Number and description of reference genes', '', 'Essential'),
        ('Data Analysis', 'Statistical methods', '', 'Essential'),
    ]

    df_miqe = pd.DataFrame(miqe_items, columns=['Category', 'Item', 'Value', 'MIQE Level'])

    # Also include primer details
    primer_data = []
    for i, pair in enumerate(primers.get('primers', []), 1):
        primer_data.append({
            'Pair': i,
            'Forward': pair['forward_seq'],
            'Reverse': pair['reverse_seq'],
            'Amplicon_bp': pair['amplicon_size'],
            'Tm_F': pair['forward_tm'],
            'Tm_R': pair['reverse_tm'],
        })

    df_primers = pd.DataFrame(primer_data)

    sheets = {'MIQE_Checklist': df_miqe, 'Primers': df_primers}

    # Write to Excel with verification + CSV fallback (no silent 0-byte .xlsx).
    try:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            for sheet_name, df in sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    except Exception as e:
        print(f"⚠ MIQE Excel export failed ({e}); falling back to CSV.")
        return _excel_fallback_to_csv(sheets, output_file)

    if not _verify_nonempty(output_file):
        print(f"⚠ MIQE Excel file '{output_file}' is missing or suspiciously "
              f"small (<{_MIN_XLSX_BYTES} bytes); falling back to CSV.")
        return _excel_fallback_to_csv(sheets, output_file)

    return output_file


def export_for_benchling(primers: Dict, output_file: str = None) -> str:
    """
    Export in Benchling-compatible format.

    Parameters
    ----------
    primers : dict
        Primer design results
    output_file : str, optional
        Output CSV file path

    Returns
    -------
    str
        File path or CSV content
    """

    rows = []
    rows.append(['Name', 'Bases', 'Description'])

    for i, pair in enumerate(primers.get('primers', []), 1):
        rows.append([
            f"Pair{i}_Forward",
            pair['forward_seq'],
            f"Forward primer, Tm={pair['forward_tm']}°C, GC={pair['forward_gc']}%"
        ])

        rows.append([
            f"Pair{i}_Reverse",
            pair['reverse_seq'],
            f"Reverse primer, Tm={pair['reverse_tm']}°C, GC={pair['reverse_gc']}%"
        ])

    if output_file:
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        return output_file
    else:
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        return output.getvalue()
