
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
Export selected sgRNAs to a unified CSV + a short markdown summary.

Produces the two deliverables the skill returns for a gene:
  <GENE>_selected_sgRNAs.csv   - unified table across whichever tier(s) were used
  <GENE>_sgRNA_summary.md      - which tier was used, why, the picks, and caveats

The unified schema lets validated (Addgene), CRISPick, and de-novo guides sit in one table.
"""

from __future__ import annotations

import os
import pandas as pd

UNIFIED_COLUMNS = [
    "gene", "sgRNA_sequence", "source", "application", "enzyme",
    "rank_or_score", "exon_or_position", "pam", "citation_or_dataset", "notes",
]

# source values: "validated_addgene" | "crispick" | "de_novo"


def from_addgene(df: pd.DataFrame, application: str = "", enzyme: str = "") -> pd.DataFrame:
    """Map a search_addgene() result into the unified schema."""
    rows = []
    for _, r in df.iterrows():
        cite = f"PMID {r['pubmed_id']}" if r.get("pubmed_id") else ""
        if r.get("plasmid_id"):
            cite += f"; Addgene #{r['plasmid_id']}"
        rows.append({
            "gene": r.get("Target Gene", ""),
            "sgRNA_sequence": r.get("Target Sequence", ""),
            "source": "validated_addgene",
            "application": application or r.get("Application", ""),
            "enzyme": enzyme or r.get("Cas9 Species", ""),
            "rank_or_score": "validated",
            "exon_or_position": "",
            "pam": "",
            "citation_or_dataset": cite,
            "notes": f"Depositor: {r.get('Depositor','')}; species: {r.get('Target Species','')}",
        })
    return pd.DataFrame(rows, columns=UNIFIED_COLUMNS)


def from_crispick(df: pd.DataFrame, gene: str, dataset_url: str = "",
                  application: str = "", enzyme: str = "") -> pd.DataFrame:
    """Map a select_crispick_sgrnas() result into the unified schema."""
    def col(*names):
        for n in names:
            if n in df.columns:
                return n
        return None

    seq_c = col("sgRNA Sequence", "sgRNA_sequence")
    exon_c = col("Exon Number", "Exon_ID")
    pos_c = col("sgRNA Cut Position (1-based)", "sgRNA 'Cut' Position")
    pam_c = col("PAM Sequence", "PAM")
    ds = dataset_url.rsplit("/", 1)[-1] if dataset_url else "CRISPick"

    rows = []
    for _, r in df.iterrows():
        exon_pos = ""
        if exon_c and pd.notna(r.get(exon_c)):
            exon_pos = f"exon {r[exon_c]}"
        if pos_c and pd.notna(r.get(pos_c)):
            exon_pos = (exon_pos + f" @ {int(r[pos_c])}").strip()
        rows.append({
            "gene": gene,
            "sgRNA_sequence": r.get(seq_c, "") if seq_c else "",
            "source": "crispick",
            "application": application,
            "enzyme": enzyme,
            "rank_or_score": r.get("rank_value", ""),
            "exon_or_position": exon_pos,
            "pam": r.get(pam_c, "") if pam_c else "",
            "citation_or_dataset": ds,
            "notes": "CRISPick precomputed; rank lower=better (or score higher=better)",
        })
    return pd.DataFrame(rows, columns=UNIFIED_COLUMNS)


def from_de_novo(records: list[dict]) -> pd.DataFrame:
    """records: list of dicts with at least gene, sgRNA_sequence, enzyme, pam, notes."""
    rows = []
    for r in records:
        rows.append({
            "gene": r.get("gene", ""),
            "sgRNA_sequence": r.get("sgRNA_sequence", ""),
            "source": "de_novo",
            "application": r.get("application", ""),
            "enzyme": r.get("enzyme", ""),
            "rank_or_score": r.get("rank_or_score", "de novo"),
            "exon_or_position": r.get("exon_or_position", ""),
            "pam": r.get("pam", ""),
            "citation_or_dataset": r.get("citation_or_dataset", "de novo design (this work)"),
            "notes": r.get("notes", ""),
        })
    return pd.DataFrame(rows, columns=UNIFIED_COLUMNS)


def export(selected: pd.DataFrame, gene: str, tier: str, outdir: str,
           rationale: str = "", caveats: list[str] | None = None) -> dict:
    """
    Write the unified CSV + markdown summary.

    Parameters
    ----------
    selected : DataFrame already in UNIFIED_COLUMNS (use the from_* mappers first).
    gene : str
    tier : str   e.g. "Option 1 (validated Addgene)", "Option 2 (CRISPick)", "Option 3 (de novo)".
    outdir : str  directory to write into (created if needed).
    rationale : str  why this tier was used.
    caveats : list[str]  extra caveats to append to the default list.

    Returns
    -------
    dict with 'csv' and 'summary' file paths.
    """
    os.makedirs(outdir, exist_ok=True)
    # Reorder/validate columns.
    for c in UNIFIED_COLUMNS:
        if c not in selected.columns:
            selected[c] = ""
    selected = selected[UNIFIED_COLUMNS].fillna("")

    csv_path = os.path.join(outdir, f"{gene}_selected_sgRNAs.csv")
    selected.to_csv(csv_path, index=False)

    default_caveats = [
        "Test 3-4 sgRNAs per gene experimentally regardless of predicted scores.",
        "Confirm the Cas enzyme/PAM matches your construct (SpCas9 NGG, SaCas9 NNGRRT, Cas12a TTTV).",
        "For Cas12a, AsCas12a and enAsCas12a are NOT interchangeable.",
        "CRISPick ranks are precomputed predictions, not a substitute for empirical validation.",
        "Validate edits (e.g., Sanger sequencing; TIDE/T7E1 for indels).",
    ]
    all_caveats = default_caveats + (caveats or [])

    md = [f"# sgRNA selection summary: {gene}", ""]
    md.append(f"**Tier used:** {tier}")
    if rationale:
        md.append(f"\n**Why:** {rationale}")
    md.append(f"\n**Guides selected:** {len(selected)}\n")
    if len(selected):
        # Compact markdown table of the key columns.
        show = selected[["sgRNA_sequence", "source", "rank_or_score",
                         "exon_or_position", "citation_or_dataset"]]
        md.append(show.to_markdown(index=False))
    md.append("\n## Caveats")
    for c in all_caveats:
        md.append(f"- {c}")
    md.append("")

    summary_path = os.path.join(outdir, f"{gene}_sgRNA_summary.md")
    with open(summary_path, "w") as fh:
        fh.write("\n".join(md))

    return {"csv": csv_path, "summary": summary_path}
