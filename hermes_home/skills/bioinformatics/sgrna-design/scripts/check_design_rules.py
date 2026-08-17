
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
Option 3 helper: sanity-check a candidate sgRNA against the de-novo design rules.

This is a lightweight rule checker (length, GC 40-60%, TTTT terminator, >4 homopolymer runs,
and PAM verification for a given enzyme). It is NOT a genome-wide off-target search — use
Cas-OFFinder / CRISPOR or CRISPick's precomputed off-target ranks for real specificity.
"""

from __future__ import annotations

import re

# Enzyme -> (expected protospacer length range, PAM regex, PAM side).
# PAM regex uses IUPAC: N=ACGT, V=ACG, R=AG.
_IUPAC = {"N": "[ACGT]", "V": "[ACG]", "R": "[AG]", "Y": "[CT]", "W": "[AT]",
          "S": "[GC]", "K": "[GT]", "M": "[AC]"}

ENZYMES = {
    "SpCas9":     {"len": (20, 20), "pam": "NGG",    "side": "3'"},
    "SaCas9":     {"len": (20, 21), "pam": "NNGRRT", "side": "3'"},
    "AsCas12a":   {"len": (23, 25), "pam": "TTTV",   "side": "5'"},
    "enAsCas12a": {"len": (23, 25), "pam": "TTTV",   "side": "5'"},
}


def _pam_to_regex(pam: str) -> str:
    return "".join(_IUPAC.get(b, b) for b in pam.upper())


def gc_content(seq: str) -> float:
    seq = seq.upper()
    if not seq:
        return 0.0
    return 100.0 * (seq.count("G") + seq.count("C")) / len(seq)


def check_design_rules(protospacer: str, enzyme: str = "SpCas9", pam: str | None = None) -> dict:
    """
    Check one candidate protospacer against the de-novo rules.

    Parameters
    ----------
    protospacer : str
        The guide/protospacer sequence (without the PAM), 5'->3'.
    enzyme : str
        One of SpCas9, SaCas9, AsCas12a, enAsCas12a.
    pam : str, optional
        The observed PAM in the genome flanking the protospacer. If given, it is checked
        against the enzyme's PAM pattern.

    Returns
    -------
    dict: {'passes': bool, 'checks': {name: (ok, detail)}, 'enzyme': ..., 'gc': float}
    """
    seq = protospacer.upper().strip()
    spec = ENZYMES.get(enzyme)
    checks: dict[str, tuple[bool, str]] = {}

    if spec is None:
        return {"passes": False, "enzyme": enzyme, "gc": None,
                "checks": {"enzyme_known": (False, f"Unknown enzyme '{enzyme}'. "
                                            f"Known: {list(ENZYMES)}")}}

    lo, hi = spec["len"]
    checks["length"] = (lo <= len(seq) <= hi,
                        f"{len(seq)} bp (expected {lo}-{hi} for {enzyme})")

    gc = gc_content(seq)
    checks["gc_content"] = (40.0 <= gc <= 60.0, f"{gc:.0f}% (target 40-60%)")

    checks["no_TTTT"] = ("TTTT" not in seq, "TTTT terminator present" if "TTTT" in seq
                         else "no TTTT run")

    homo = re.search(r"(A{5,}|C{5,}|G{5,}|T{5,})", seq)
    checks["no_long_homopolymer"] = (homo is None,
                                     f"{homo.group(0)} run" if homo else "no run >4 nt")

    checks["valid_bases"] = (re.fullmatch(r"[ACGT]+", seq) is not None,
                             "non-ACGT characters present" if not re.fullmatch(r"[ACGT]+", seq)
                             else "all ACGT")

    if pam is not None:
        rx = _pam_to_regex(spec["pam"])
        ok = re.fullmatch(rx, pam.upper()) is not None
        checks["pam"] = (ok, f"observed '{pam.upper()}' vs required {spec['pam']} "
                         f"({spec['side']} of target)")

    passes = all(ok for ok, _ in checks.values())
    return {"passes": passes, "enzyme": enzyme, "gc": gc, "checks": checks}


def format_report(result: dict) -> str:
    lines = [f"Enzyme: {result['enzyme']}   Overall: {'PASS' if result['passes'] else 'FAIL'}"]
    for name, (ok, detail) in result["checks"].items():
        lines.append(f"  [{'OK ' if ok else 'XX '}] {name}: {detail}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    seq = sys.argv[1] if len(sys.argv) > 1 else "GAGGTTGTGAGGCGCTGCCC"
    enz = sys.argv[2] if len(sys.argv) > 2 else "SpCas9"
    pam = sys.argv[3] if len(sys.argv) > 3 else None
    print(format_report(check_design_rules(seq, enz, pam)))
