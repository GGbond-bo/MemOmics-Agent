
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
Tier 1 / Method 1: Search the bundled Addgene validated-sgRNA database.

The bundled CSV (`references/resource/addgene_grna_sequences.csv`, 321 rows / 197 genes)
comes straight from Addgene's gRNA reference export. Two quirks in the raw file that the
original guide's example code did NOT handle and that silently break naive parsing:

  1. Real column names use SPACES, not underscores:
       'Application', 'Cas9 Species', 'Depositor', 'Plasmid ID', 'PubMed ID',
       'Target Gene', 'Target Sequence', 'Target Species'
     (the guide's snippets reference 'Target_Gene', 'Target_Species', etc.)

  2. 'Plasmid ID' and 'PubMed ID' cells are wrapped in HTML <a> tags, e.g.
       '<a href="/58252/">58252</a>'
       '<a href="https://www.ncbi.nlm.nih.gov/pubmed/24870050/">24870050</a>'
     so the visible ID and its URL must be extracted from the markup.

  3. Species/application values are messy: 'H. sapiens' vs 'C.elegans' vs 'C. elegans',
     'Synthetic' vs 'synthetic', trailing '&nbsp;'. Matching normalizes whitespace + case.

This module returns clean, de-HTML'd records suitable for citation.
"""

from __future__ import annotations

import html
import os
import re
import pandas as pd

# Resolve the bundled CSV relative to this script so the skill is standalone.
_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.normpath(
    os.path.join(_HERE, "..", "references", "resource", "addgene_grna_sequences.csv")
)

# Map user-facing intent -> Addgene 'Application' vocabulary actually present in the file.
# (Observed values: cut, activate, interfere, tag, nick, scaffold, visualize,
#  'RNA targeting', purify, methylation, 'activate/interfere', 'cut/nick', etc.)
APPLICATION_SYNONYMS = {
    "knockout": ["cut", "cut/nick"],
    "ko": ["cut", "cut/nick"],
    "cut": ["cut", "cut/nick"],
    "activation": ["activate", "activate/interfere"],
    "crispra": ["activate", "activate/interfere"],
    "activate": ["activate", "activate/interfere"],
    "inhibition": ["interfere", "rna targeting", "activate/interfere"],
    "interference": ["interfere", "rna targeting", "activate/interfere"],
    "crispri": ["interfere", "rna targeting", "activate/interfere"],
    "knockdown": ["interfere", "rna targeting"],
}

_TAG_RE = re.compile(r"<[^>]+>")
_HREF_RE = re.compile(r'href="([^"]+)"')


def _strip_html_text(cell: str) -> str:
    """Return the visible text of an HTML cell (e.g. '<a ...>58252</a>' -> '58252')."""
    if not isinstance(cell, str):
        return "" if pd.isna(cell) else str(cell)
    text = _TAG_RE.sub("", cell)
    return html.unescape(text).strip()


def _extract_href(cell: str, base: str = "") -> str:
    """Return the href URL inside an HTML cell, optionally prefixing a base for relative paths."""
    if not isinstance(cell, str):
        return ""
    m = _HREF_RE.search(cell)
    if not m:
        return ""
    url = html.unescape(m.group(1)).strip()
    # Placeholder hrefs with no real ID (e.g. "", "/", "//") -> return blank.
    if url.strip("/") == "":
        return ""
    if url.startswith("/") and base:
        url = base.rstrip("/") + url
    return url


def _norm(s: str) -> str:
    """Normalize a string for matching: unescape entities, collapse whitespace, lowercase."""
    if not isinstance(s, str):
        return ""
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def load_addgene(csv_path: str = DEFAULT_CSV) -> pd.DataFrame:
    """Load the bundled CSV and add cleaned helper columns (does not drop originals)."""
    df = pd.read_csv(csv_path)
    df = df.copy()
    df["plasmid_id"] = df["Plasmid ID"].apply(_strip_html_text)
    df["plasmid_url"] = df["Plasmid ID"].apply(
        lambda c: _extract_href(c, base="https://www.addgene.org")
    )
    df["pubmed_id"] = df["PubMed ID"].apply(_strip_html_text)
    df["pubmed_url"] = df["PubMed ID"].apply(_extract_href)
    df["_gene_norm"] = df["Target Gene"].apply(_norm)
    df["_species_norm"] = df["Target Species"].apply(_norm)
    df["_application_norm"] = df["Application"].apply(_norm)
    return df


def search_addgene(
    gene: str,
    species: str | None = None,
    application: str | None = None,
    csv_path: str = DEFAULT_CSV,
) -> pd.DataFrame:
    """
    Search the bundled Addgene validated-sgRNA database.

    Parameters
    ----------
    gene : str
        Gene symbol (case-insensitive), e.g. "TP53", "AAVS1".
    species : str, optional
        Organism filter, matched loosely (e.g. "H. sapiens", "human", "mouse").
        Common aliases handled: human->h. sapiens, mouse->m. musculus, rat->r. norvegicus.
    application : str, optional
        Intent: "knockout"/"cut", "activation"/"CRISPRa", "inhibition"/"CRISPRi", etc.
        Mapped to the file's vocabulary via APPLICATION_SYNONYMS.
    csv_path : str
        Path to the bundled CSV (defaults to the file inside this skill).

    Returns
    -------
    pandas.DataFrame
        Matching rows with clean columns:
        ['Target Gene', 'Target Sequence', 'Target Species', 'Application',
         'Cas9 Species', 'plasmid_id', 'plasmid_url', 'pubmed_id', 'pubmed_url', 'Depositor'].
        Empty DataFrame (with those columns) if no match — caller MUST then run Method 2.
    """
    df = load_addgene(csv_path)

    out_cols = [
        "Target Gene", "Target Sequence", "Target Species", "Application",
        "Cas9 Species", "plasmid_id", "plasmid_url", "pubmed_id", "pubmed_url", "Depositor",
    ]

    mask = df["_gene_norm"] == _norm(gene)

    if species:
        sp = _norm(species)
        species_aliases = {
            "human": "h. sapiens", "mouse": "m. musculus", "rat": "r. norvegicus",
            "zebrafish": "d. rerio", "fly": "d. melanogaster", "yeast": "s. cerevisiae",
            "worm": "c. elegans",
        }
        sp = species_aliases.get(sp, sp)
        # Loose contains match to absorb messy variants ('C.elegans', trailing spaces).
        sp_compact = sp.replace(" ", "")
        mask &= df["_species_norm"].str.replace(" ", "", regex=False).str.contains(
            re.escape(sp_compact), na=False
        )

    if application:
        wanted = APPLICATION_SYNONYMS.get(_norm(application), [_norm(application)])
        mask &= df["_application_norm"].isin(wanted)

    res = df.loc[mask, out_cols].reset_index(drop=True)
    return res


if __name__ == "__main__":
    import sys

    g = sys.argv[1] if len(sys.argv) > 1 else "TP53"
    sp = sys.argv[2] if len(sys.argv) > 2 else None
    app = sys.argv[3] if len(sys.argv) > 3 else None
    r = search_addgene(g, sp, app)
    print(f"Found {len(r)} validated sgRNA(s) for {g}"
          + (f" / {sp}" if sp else "") + (f" / {app}" if app else ""))
    if len(r):
        with pd.option_context("display.max_columns", None, "display.width", 200):
            print(r.to_string(index=False))
    else:
        print("No Addgene match -> you MUST still run Method 2 (literature search) "
              "before proceeding to Option 2 (CRISPick).")
