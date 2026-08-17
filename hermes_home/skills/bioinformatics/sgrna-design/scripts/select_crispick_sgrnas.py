
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
Tier 2 / Step 3: Filter and rank sgRNAs from a downloaded CRISPick dataset.

After find_crispick_dataset.py gives a URL and you have run wget + gunzip, you have a large
tab-delimited `.txt`. This module loads it, filters to your gene, ranks candidates, and
selects 3-4 guides (by default spread across distinct exons for redundancy).

DEFENSIVE COLUMN RESOLUTION (important):
The source guide is internally inconsistent about CRISPick column names. Its Section 2.5 uses
spaced/title-case names ('Target Gene Symbol', 'Combined Rank', 'sgRNA Sequence'), while its
"Quick Start" Example 1 uses underscored names ('Gene_Symbol', 'sgRNA_score', 'Exon_ID',
'Off_target_stringency'). Real CRISPick exports use the spaced names; older/derived files vary.
We resolve each needed field against a list of known aliases so selection works on either layout.
"""

from __future__ import annotations

import pandas as pd

# Candidate column names for each logical field, in priority order.
COLUMN_ALIASES = {
    "gene": ["Target Gene Symbol", "Gene_Symbol", "Target Gene ID", "Gene Symbol", "Gene"],
    "sequence": ["sgRNA Sequence", "sgRNA_sequence", "sgRNA Sequence (5' to 3')", "Guide Sequence"],
    "combined_rank": ["Combined Rank", "Combined_Rank", "Pick Order"],
    "on_target_rank": ["On-Target Rank", "On_Target_Rank", "On-Target Efficacy Rank"],
    "off_target_rank": ["Off-Target Rank", "Off_Target_Rank", "Off-Target Rank (specificity)"],
    "on_target_score": ["On-Target Efficacy Score", "sgRNA_score", "On-Target Score"],
    "off_target_score": ["Off-Target Stringency", "Off_target_stringency", "Aggregate RS3 Score"],
    "exon": ["Exon Number", "Exon_ID", "Exon"],
    "cut_position": ["sgRNA Cut Position (1-based)", "sgRNA 'Cut' Position", "Cut Position"],
    "pam": ["PAM Sequence", "PAM"],
    "target_cut_pct": ["Target Cut %", "Target Cut Length %", "Target Cut Percent"],
    "tss_offset": ["sgRNA 'Cut' Site TSS Offset", "TSS Offset"],
}


def _resolve(df: pd.DataFrame, field: str) -> str | None:
    """Return the first alias for `field` actually present in df, else None."""
    for cand in COLUMN_ALIASES.get(field, []):
        if cand in df.columns:
            return cand
    return None


def load_crispick(path: str) -> pd.DataFrame:
    """Load a (gunzipped) CRISPick tab-delimited dataset."""
    return pd.read_csv(path, sep="\t", low_memory=False)


def select_crispick_sgrnas(
    path_or_df,
    gene: str,
    n: int = 4,
    rank_by: str = "combined",
    spread_across_exons: bool = True,
    exon: int | None = None,
    cut_position_range: tuple[int, int] | None = None,
    max_target_cut_pct: float | None = None,
) -> pd.DataFrame:
    """
    Filter to `gene` and select the top `n` sgRNAs from a CRISPick dataset.

    Parameters
    ----------
    path_or_df : str | pandas.DataFrame
        Path to the gunzipped CRISPick `.txt`, or an already-loaded DataFrame.
    gene : str
        Target gene symbol (matched case-insensitively).
    n : int
        Number of sgRNAs to return (guide recommends 3-4).
    rank_by : {"combined", "on_target", "off_target"}
        Ranking criterion. "combined" (default) balances efficiency and specificity.
        Uses *Rank columns (lower is better) when present; otherwise falls back to
        *score columns (higher is better).
    spread_across_exons : bool
        If True and an exon column exists, take the best guide per exon before filling
        out to `n` (redundancy across the gene body, per the guide's Step 4).
    exon : int, optional
        Restrict to a specific exon number.
    cut_position_range : (int, int), optional
        Restrict to a genomic cut-position window (inclusive).
    max_target_cut_pct : float, optional
        Keep only guides cutting within the first X% of the protein (knockout impact).

    Returns
    -------
    pandas.DataFrame of selected guides (subset of original columns + a 'rank_value' helper).
    """
    df = path_or_df if isinstance(path_or_df, pd.DataFrame) else load_crispick(path_or_df)

    gene_col = _resolve(df, "gene")
    seq_col = _resolve(df, "sequence")
    if gene_col is None or seq_col is None:
        raise ValueError(
            "Could not find gene/sequence columns. Available columns:\n  "
            + ", ".join(map(str, df.columns))
        )

    sub = df[df[gene_col].astype(str).str.upper() == str(gene).upper()].copy()
    if sub.empty:
        return sub  # caller proceeds to Option 3 (de novo)

    # Optional filters.
    exon_col = _resolve(sub, "exon")
    if exon is not None and exon_col is not None:
        sub = sub[sub[exon_col] == exon]
    pos_col = _resolve(sub, "cut_position")
    if cut_position_range is not None and pos_col is not None:
        lo, hi = cut_position_range
        sub = sub[(sub[pos_col] >= lo) & (sub[pos_col] <= hi)]
    pct_col = _resolve(sub, "target_cut_pct")
    if max_target_cut_pct is not None and pct_col is not None:
        sub = sub[sub[pct_col] <= max_target_cut_pct]

    if sub.empty:
        return sub

    # Choose the ranking column and direction.
    rank_field = {"combined": "combined_rank", "on_target": "on_target_rank",
                  "off_target": "off_target_rank"}.get(rank_by, "combined_rank")
    rank_col = _resolve(sub, rank_field)
    if rank_col is not None:
        sub["rank_value"] = sub[rank_col]
        ascending = True  # ranks: lower = better
    else:
        # Fall back to score columns (higher = better) when rank columns are absent.
        score_field = {"combined": "on_target_score", "on_target": "on_target_score",
                       "off_target": "off_target_score"}.get(rank_by, "on_target_score")
        score_col = _resolve(sub, score_field)
        if score_col is None:
            raise ValueError(
                f"No rank or score column available for rank_by='{rank_by}'. "
                f"Columns: {', '.join(map(str, sub.columns))}"
            )
        sub["rank_value"] = sub[score_col]
        ascending = False

    sub = sub.sort_values("rank_value", ascending=ascending)

    if spread_across_exons and exon_col is not None and exon is None:
        # Best guide per exon, then fill to n with the next-best remaining.
        best_per_exon = sub.groupby(exon_col, as_index=False).head(1)
        chosen = best_per_exon.head(n)
        if len(chosen) < n:
            remaining = sub[~sub.index.isin(chosen.index)]
            chosen = pd.concat([chosen, remaining.head(n - len(chosen))])
        chosen = chosen.sort_values("rank_value", ascending=ascending)
    else:
        chosen = sub.head(n)

    return chosen.reset_index(drop=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python select_crispick_sgrnas.py <crispick.txt> <GENE> [n]")
        raise SystemExit(1)
    path, gene = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    res = select_crispick_sgrnas(path, gene, n=n)
    print(f"Selected {len(res)} sgRNA(s) for {gene}")
    if len(res):
        with pd.option_context("display.max_columns", None, "display.width", 220):
            print(res.to_string(index=False))
