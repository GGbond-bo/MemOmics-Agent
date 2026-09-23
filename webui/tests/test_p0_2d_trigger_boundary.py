# -*- coding: utf-8 -*-
"""P0-2d(2026-09-23) 置顶 skill 触发判定的词边界契约测试。

用户原话："先做 P0-2d 把触发判定收干净"（承接 P0-2b 给 RED 路由加的 short_ascii_boundary）。
旧实现 webui/server.py::_skill_trigger_hit 是纯子串匹配（kl in low），英文触发词会从别的
单词肚子里命中，实测抓到 14 例真误触发：
  cell ⊂ excellent / core ⊂ score / GO ⊂ category,logout,ongoing,non-negotiable
  find ⊂ DoubletFinder / flow ⊂ workflow / set ⊂ dataset,settings / code ⊂ encode
  sites ⊂ websites / genomic ⊂ 10xgenomics / processing ⊂ preprocessing / grn ⊂ sgrna
  gate ⊂ investigate / Excel ⊂ excellent / ima ⊂ estimate
量化（439 篇 SKILL.md、424 万字符语料）：1226 个 ASCII 候选里 216 个存在「词中命中」，
89933 次出现中 13839 次（15.4%）落在别的单词内部。

契约（contracts/skill_triggers.json → matching.pinned_skill_boundary）：
  档 1 纯 ASCII 且 <=3 位：左右都不许紧贴英文字母（与 RED 的 short_ascii_boundary 同一套规则）；
  档 2 更长的 ASCII：左边不许贴字母数字（词首边界），右边只允许词形变化（cells/primers/genes）
        或非英文字母，其余不算命中；
  含 CJK/标点：仍走子串（中文没有词边界，"做primer设计"、"网络调研" 必须照命中）。
不变量：改后新命中恒为旧命中的子集 —— 只删误触发，从不新增。
"""
import io
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import server  # noqa: E402

# 真实技能 × 真实句子 × 不该命中的触发词（全部跑真实现 _skill_meta + _skill_trigger_hit）
FALSE_POSITIVES = [
    ("用 DoubletFinder 去掉 doublets", "find_restriction_sites", "find"),
    ("category 分错了", "functional-enrichment", "GO"),
    ("logout 之后重连", "functional-enrichment", "GO"),
    ("ongoing tracking", "functional-enrichment", "GO"),
    ("workflow 怎么配", "analyze_flow_cytometry_immunophenotyping", "flow"),
    ("dataset 有点大", "gene_set_enrichment_analysis", "set"),
    ("settings 在哪儿", "gene_set_enrichment_analysis", "set"),
    ("preprocessing 太慢", "windows-bioinformatics-batch-processing", "processing"),
    ("encode 一下这段", "code-writer", "code"),
    ("websites 打不开", "find_restriction_sites", "sites"),
    ("sgrna design 的注意事项", "grn-pyscenic", "grn"),
    ("10xgenomics 数据", "analyze_genomic_region_overlap", "genomic"),
    ("这个脚本写得 excellent，帮我看看", "analysis-summary-report", "Excel"),
    ("estimate 一下这个参数", "map_to_ima_interpret_scRNA", "ima"),
    ("investigate 一下这个现象", "design_golden_gate_oligos", "gate"),
    ("roadmap 看一下", "calculate_brain_adc_map", "map"),
]

# 真实技能 × 真实句子 × 必须命中的触发词（词形变化 / 中文紧贴 / 词首边界都不许误杀）
TRUE_POSITIVES = [
    ("帮我做 primer design", "design_primer", "primer"),
    ("做primer设计", "design_primer", "primer"),
    ("primers 怎么设计", "design_primer", "primer"),
    ("这些 genes 的富集怎么做", "gene_set_enrichment_analysis", "gene"),
    ("限制性酶切 sites 分析", "find_restriction_sites", "sites"),
    ("GO 富集分析", "functional-enrichment", "GO"),
    ("做一次 GO富集", "functional-enrichment", "GO"),
    ("flow cytometry 怎么做", "analyze_flow_cytometry_immunophenotyping", "flow"),
    ("Golden Gate 组装怎么设计", "design_golden_gate_oligos", "gate"),
    ("帮我做 cell senescence 分析", "analyze_cell_senescence_and_apoptosis", "senescence"),
    ("用 DoubletFinder 去双细胞", "doubletfinder-remove-doublets", "doubletfinder"),
    ("帮我做网络调研", "web-research", "网络调研"),
    ("环境rna 怎么去背景", "soupx-remove-background", "环境rna"),
]


def _legacy_hit(meta, user_text):
    """P0-2d 之前的实现（原样保留，作为「只准收窄」的参照物）。"""
    if not user_text or not meta:
        return []
    low = user_text.lower()
    hits, seen, cands = [], set(), []
    for k in list(meta.get("trigger_keywords") or []) + list(meta.get("aliases") or []):
        cands.append(k)
    nm = meta.get("name") or ""
    dp = meta.get("display") or ""
    if len(nm) >= 3:
        cands.append(nm)
    if len(dp) >= 3 and dp != nm:
        cands.append(dp)
    for k in cands:
        kl = str(k or "").lower().strip()
        if not kl or kl in seen:
            continue
        seen.add(kl)
        if len(kl) >= 2 and kl in low:
            hits.append(k)
        elif " " in kl:
            parts = [p for p in kl.split() if len(p) >= 3]
            if parts and all(p in low for p in parts):
                hits.append(k)
    return hits[:8]


def _contract():
    p = os.path.join(server.MEMOMICS_DIR, "contracts", "skill_triggers.json")
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


# ==================== A. 规则本身 ====================


@pytest.mark.parametrize("text,kw,want", [
    ("做primer设计", "primer", True),
    ("primers 怎么设计", "primer", True),
    ("帮我分析这些 cells", "cell", True),
    ("这个脚本写得 excellent", "cell", False),
    ("GO 富集分析", "go", True),
    ("category 分错了", "go", False),
    ("logout 了", "go", False),
    ("set 一下参数", "set", True),
    ("settings 在哪儿", "set", False),
    ("dataset 有点大", "set", False),
    ("map 通路", "map", True),
    ("roadmap 看一下", "map", False),
    ("pre 处理一下", "pre", True),
    ("preprocessing 太慢", "pre", False),
    ("限制性酶切 sites 分析", "sites", True),
    ("websites 打不开", "sites", False),
    ("investigate 一下", "gate", False),
    ("Golden Gate 组装", "gate", True),
    ("Code 报错", "code", True),
    ("encode 一下", "code", False),
    ("网络调研", "网络调研", True),
    ("环境rna 去背景", "环境rna", True),
    ("seurat 聚类", "seurat", True),
    ("seuratobject 是什么", "seurat", False),
])
def test_kw_boundary_matrix(text, kw, want):
    """边界判定的最小矩阵：真实现 _kw_any_hit，逐条钉死。"""
    assert server._kw_any_hit(text.lower(), kw) is want


def test_rule_is_documented_in_contract():
    """规则必须写进契约（否则下一个人改回子串匹配没人拦得住）。"""
    m = _contract()["matching"]
    blk = m.get("pinned_skill_boundary")
    assert blk, "契约缺 matching.pinned_skill_boundary"
    assert blk["tier1"]["max_len"] == server._SHORT_ASCII_KW_MAX == 3
    assert set(blk["tier2"]["inflect_suffixes"]) == set(server._KW_INFLECT_SUFFIXES)
    assert blk["cjk"] == "substring"
    assert blk["invariant"] == "new_hits_subset_of_legacy"
    assert m.get("pinned_skill_boundary_note"), "要写清为什么（14 例实测误触发）"


# ==================== B. 真实现端到端 ====================


@pytest.mark.parametrize("text,name,kw", FALSE_POSITIVES)
def test_midword_false_positive_is_gone(text, name, kw):
    meta = server._skill_meta(name)
    assert meta, "技能不存在: %s" % name
    assert kw in _legacy_hit(meta, text), "旧实现本来就该命中（否则这条用例没意义）: %s" % kw
    assert kw not in server._skill_trigger_hit(meta, text), "词中命中必须收掉: %s ⊂ %s" % (kw, text)


@pytest.mark.parametrize("text,name,kw", TRUE_POSITIVES)
def test_true_positive_survives(text, name, kw):
    meta = server._skill_meta(name)
    assert meta, "技能不存在: %s" % name
    hits = server._skill_trigger_hit(meta, text)
    assert kw in hits, "真阳性被误杀: %s | %s -> %s" % (text, name, hits)


def test_synthetic_bare_words_never_substring_hit():
    """P0-2c 已把这些裸词从真技能里清掉（34 处技能元数据），这里用合成元数据把
    算法层的洞钉死：将来谁再往 trigger_keywords 写裸 cell/core/excel，也不会从词中命中。"""
    meta = {"name": "synthetic-x", "display": "合成",
            "trigger_keywords": ["cell", "core", "excel", "set", "GO"]}
    assert server._skill_trigger_hit(meta, "这个脚本写得 excellent") == []
    assert server._skill_trigger_hit(meta, "模型的 score 是 0.93") == []
    assert server._skill_trigger_hit(meta, "export 到 Excel") == ["excel"]
    got = server._skill_trigger_hit(meta, "做个 cell 分析")
    assert "cell" in got and "core" not in got, got
    assert server._skill_trigger_hit(meta, "看一下 GO 条目") == ["GO"]
    assert server._skill_trigger_hit(meta, "ongoing 的任务") == []


def test_multiword_parts_must_start_at_word_boundary():
    """多词短语的「实词全中」兜底也要踩词首边界：'excellent cycle' 不许命中 'cell cycle'。"""
    meta = {"name": "synthetic-y", "trigger_keywords": ["cell cycle"]}
    assert server._skill_trigger_hit(meta, "the cell is in cycle") == ["cell cycle"]   # 词序散开仍算（设计如此）
    assert server._skill_trigger_hit(meta, "excellent cycle model") == []
    assert server._skill_trigger_hit(meta, "cell-cycle 分析") == ["cell cycle"]        # 连字符算边界，"cell-cycle" 该中


def test_never_adds_hits_against_legacy():
    """只准收窄：随机技能 × 真实 SKILL.md 句子，新命中恒为旧命中的子集。"""
    import random
    skills = []
    for n in sorted(set(os.path.basename(os.path.dirname(p))
                        for p in _sample_skill_dirs()))[:40]:
        m = server._skill_meta(n)
        if m:
            skills.append((n, m))
    assert len(skills) >= 20, "采样到的技能太少: %d" % len(skills)
    random.seed(20260923)
    lines = _sample_md_lines()
    assert len(lines) >= 200, "语料太少"
    pairs = 0
    for sent in random.sample(lines, 300):
        for name, meta in skills:
            old = set(_legacy_hit(meta, sent))
            new = set(server._skill_trigger_hit(meta, sent))
            pairs += 1
            assert new <= old, "新命中冒出旧实现没有的项: %s | %s | %s" % (sent[:40], name, sorted(new - old))
    assert pairs >= 300 * 20


def test_pinned_expect_emit_ignores_midword_noise(new_session, monkeypatch):
    """接口层：句子里只有「词中噪音」时不许报告「本轮应加载」；真命中照旧报告。"""
    sent = []
    monkeypatch.setattr(server, "_session_emit", lambda s, m: sent.append(m))
    server._pinned_skills_set(new_session, ["functional-enrichment", "find_restriction_sites"])
    try:
        sess = server._sessions.get(new_session) or {"id": new_session}
        got = server._pinned_expect_emit(sess, "这个脚本写得 excellent，category 也分错了")
        assert got == [], "只有词中噪音时不该要求加载: %s" % got
        got2 = server._pinned_expect_emit(sess, "帮我做 GO 富集分析和限制性酶切 sites 统计")
        names = [x["name"] for x in got2]
        assert "functional-enrichment" in names, "真命中丢了: %s" % got2
        assert all(x["hits"] for x in got2), "要带上命中的触发词"
    finally:
        server._pinned_skills_set(new_session, [])


def test_catalog_search_box_keeps_substring_semantics(client):
    """目录搜索框只是搜索框，不参与触发判定：用户打 'cell' 仍要能搜到技能（不许被边界规则收紧）。"""
    d = client.get("/api/skills/catalog", params={"q": "cell"}).json()
    assert d["total"] > 0, "搜索框被误改成边界匹配了"
    names = [x["name"] for x in d["skills"]]
    assert any("cell" in n.lower() for n in names)


def test_red_router_results_unchanged_by_p0_2d():
    """P0-2d 只动置顶判定；RED 路由结果必须逐条不变（路由矩阵另有一整套测试）。"""
    hits = server._match_red_skill_hits("帮我做质控和双细胞去除")
    assert any(h["name"] == "scrna-qc" for h in hits), hits
    assert server._match_red_skill_hits("今天天气不错") == []


# ==================== 采样工具 ====================


def _sample_skill_dirs():
    import glob as _g
    root = os.path.join(server.MEMOMICS_DIR, "hermes_home", "skills")
    return _g.glob(os.path.join(root, "**", "skill.json"), recursive=True)


def _sample_md_lines():
    import glob as _g
    root = os.path.join(server.MEMOMICS_DIR, "hermes_home", "skills")
    out = []
    for p in _g.glob(os.path.join(root, "**", "SKILL.md"), recursive=True)[:120]:
        try:
            with io.open(p, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if 20 <= len(line) <= 160:
                        out.append(line)
        except OSError:
            continue
    return out
