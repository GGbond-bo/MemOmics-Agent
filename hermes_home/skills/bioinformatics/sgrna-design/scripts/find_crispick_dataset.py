
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
Tier 2 / Step 1: Resolve a CRISPick precomputed-design download URL.

CRISPick (Broad Institute GPP) publishes genome-wide precomputed sgRNA designs. The bundled
`references/resource/CRISPick_download_links.txt` holds 238 URLs = 119 full datasets
(`.txt.gz`, 50-700 MB each) + 119 matching summary files (`.summary.txt`, 1-3 MB).

File naming convention:
  sgRNA_design_{TAXID}_{GENOME}_{CAS}_{APPLICATION}_{ALGORITHM}_{SOURCE}_{DATE}.txt.gz

This module filters those links by organism (TAXID), Cas enzyme, and application, and returns
the matching dataset URL(s). It does NOT download them (too large to bundle) — the caller runs
wget + gunzip, then uses select_crispick_sgrnas.py.

CRITICAL enzyme note (preserved from the source guide):
  AsCas12a (wild-type) and enAsCas12a (enhanced) are DIFFERENT enzymes with different activity
  profiles. Guides designed for one may NOT work with the other. Always match the dataset to
  your exact Cas12a variant.
"""

from __future__ import annotations

import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LINKS = os.path.normpath(
    os.path.join(_HERE, "..", "references", "resource", "CRISPick_download_links.txt")
)

# Common organism -> NCBI TAXID (subset present in the bundled file: 13 organisms).
ORGANISM_TAXID = {
    "human": "9606", "h. sapiens": "9606", "homo sapiens": "9606",
    "mouse": "10090", "m. musculus": "10090", "mus musculus": "10090",
    "rat": "10116", "r. norvegicus": "10116",
    "dog": "9615", "c. familiaris": "9615",
    "cow": "9913", "b. taurus": "9913",
    "monkey": "9544", "macaque": "9544", "rhesus": "9544", "m. mulatta": "9544",
    "fly": "7227", "drosophila": "7227", "d. melanogaster": "7227",
    "salmon": "8030", "pig": "9823", "chicken": "9031",
}

# User-facing Cas name -> token used in the file.
CAS_TOKEN = {
    "spcas9": "SpyoCas9", "spyocas9": "SpyoCas9", "s. pyogenes": "SpyoCas9", "sp": "SpyoCas9",
    "sacas9": "SaurCas9", "saurcas9": "SaurCas9", "s. aureus": "SaurCas9", "sa": "SaurCas9",
    "ascas12a": "AsCas12a", "as": "AsCas12a",
    "enascas12a": "enAsCas12a", "enas": "enAsCas12a", "enhanced": "enAsCas12a",
}

# Cas -> PAM (for reporting / sanity).
CAS_PAM = {
    "SpyoCas9": "NGG (3')",
    "SaurCas9": "NNGRRT (3')",
    "AsCas12a": "TTTV (5')",
    "enAsCas12a": "TTTV (5')",
}

# User-facing application -> token used in the file.
APP_TOKEN = {
    "knockout": "CRISPRko", "ko": "CRISPRko", "cut": "CRISPRko", "crisprko": "CRISPRko",
    "activation": "CRISPRa", "crispra": "CRISPRa", "activate": "CRISPRa",
    "inhibition": "CRISPRi", "crispri": "CRISPRi", "interference": "CRISPRi",
    "knockdown": "CRISPRi",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def load_links(links_path: str = DEFAULT_LINKS, full_only: bool = True) -> list[str]:
    """Return the list of CRISPick URLs. By default only full datasets (.txt.gz)."""
    with open(links_path) as fh:
        links = [ln.strip() for ln in fh if ln.strip()]
    if full_only:
        links = [ln for ln in links if ln.endswith(".txt.gz")]
    return links


def find_crispick_dataset(
    organism: str,
    cas: str = "SpCas9",
    application: str = "knockout",
    links_path: str = DEFAULT_LINKS,
    full_only: bool = True,
) -> dict:
    """
    Resolve CRISPick download URL(s) for an organism / Cas enzyme / application.

    Parameters
    ----------
    organism : str
        Organism name or NCBI TAXID (e.g. "human", "mouse", "9606").
    cas : str
        Cas enzyme: SpCas9 (default), SaCas9, AsCas12a, enAsCas12a.
    application : str
        "knockout"/"ko" (default), "activation"/"CRISPRa", "inhibition"/"CRISPRi".
    links_path : str
        Path to the bundled links file.
    full_only : bool
        If True, restrict to full `.txt.gz` datasets (the ones you actually parse).

    Returns
    -------
    dict with keys:
        taxid, cas_token, pam, app_token, matches (list of URLs), warning (str or None).
    """
    taxid = organism if re.fullmatch(r"\d+", str(organism)) else ORGANISM_TAXID.get(_norm(organism))
    cas_token = CAS_TOKEN.get(_norm(cas))
    app_token = APP_TOKEN.get(_norm(application))

    problems = []
    if taxid is None:
        problems.append(f"Unknown organism '{organism}'. Known: {sorted(set(ORGANISM_TAXID))}.")
    if cas_token is None:
        problems.append(f"Unknown Cas '{cas}'. Known: SpCas9, SaCas9, AsCas12a, enAsCas12a.")
    if app_token is None:
        problems.append(f"Unknown application '{application}'. Known: knockout, activation, inhibition.")

    links = load_links(links_path, full_only=full_only)
    matches = []
    if not problems:
        for url in links:
            fname = url.rsplit("/", 1)[-1]
            # TAXID is the first numeric token after 'sgRNA_design_'.
            m = re.match(r"sgRNA_design_(\d+)_", fname)
            if not m or m.group(1) != taxid:
                continue
            # Match Cas token exactly (so 'AsCas12a' does not match 'enAsCas12a' and vice versa).
            if not re.search(rf"_{re.escape(cas_token)}_", fname):
                continue
            if not re.search(rf"_{re.escape(app_token)}_", fname):
                continue
            matches.append(url)

    # Enzyme-variant warning for Cas12a.
    warning = None
    if cas_token == "AsCas12a":
        warning = ("You requested wild-type AsCas12a. Do NOT use an enAsCas12a dataset — the "
                   "enhanced variant has a different activity profile and guides may not transfer.")
    elif cas_token == "enAsCas12a":
        warning = ("You requested enhanced enAsCas12a. Do NOT use a wild-type AsCas12a dataset — "
                   "guides designed for one variant may not work with the other.")

    return {
        "taxid": taxid,
        "cas_token": cas_token,
        "pam": CAS_PAM.get(cas_token),
        "app_token": app_token,
        "matches": matches,
        "problems": problems,
        "warning": warning,
    }


if __name__ == "__main__":
    import sys
    org = sys.argv[1] if len(sys.argv) > 1 else "human"
    cas = sys.argv[2] if len(sys.argv) > 2 else "SpCas9"
    app = sys.argv[3] if len(sys.argv) > 3 else "knockout"
    r = find_crispick_dataset(org, cas, app)
    if r["problems"]:
        print("PROBLEMS:")
        for p in r["problems"]:
            print("  -", p)
    print(f"TAXID={r['taxid']}  Cas={r['cas_token']} (PAM {r['pam']})  App={r['app_token']}")
    if r["warning"]:
        print("WARNING:", r["warning"])
    print(f"{len(r['matches'])} matching dataset(s):")
    for u in r["matches"]:
        print("  ", u)
    if r["matches"]:
        print("\nDownload with:\n  wget '" + r["matches"][0] + "'\n  gunzip sgRNA_design_*.txt.gz")
