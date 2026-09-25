# -*- coding: utf-8 -*-
"""知识库门禁 validate_kb 的回归测试。

回归目标（都是真实踩过的坑）：
- 早期校验把 index.yaml / default_kb_method.yaml 这类异构 schema 误判成「缺 content」，
  95 个文件报假错 -> payload 判定必须按「除元数据外有没有正文键」来做；
- source 里漏进 YAML 列表（换行 + "- " 前缀）这种脏数据必须报 error；
- 结构化 doi 字段重复 = 同一条记录写了两份，必须报 error；
- 基线只冻结历史问题：老问题不拦，新问题必须拦。

注：测试数据一律用 chr(10) 拼行，避免源码里出现裸换行转义（历史上这里翻过车）。
"""
import io
import os
from importlib.util import module_from_spec, spec_from_file_location

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VK_PATH = os.path.join(REPO, "memomics", "bio_tools", "validate_kb.py")
KB_ROOT = os.path.join(REPO, "memomics", "knowledge_base")

pytestmark = pytest.mark.kb

L = chr(10)


def _load_vk():
    spec = spec_from_file_location("validate_kb_under_test", VK_PATH)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vk = _load_vk()


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    io.open(str(p), "w", encoding="utf-8", newline="").write(text)
    return str(p)


GOOD = L.join([
    "type: kb_entry",
    "name: demo_method",
    "species: Homo_sapiens",
    "source: literature",
    "verified: partially_verified",
    "quality: medium",
    "last_updated: '2026-01-01'",
    "auto_trigger:",
    "- demo_method",
    "content: '真实正文'",
    "evidence: 'DOI 10.1038/s41586-024-07348-6 | PMID: 38500000 | 论文标题'",
    "",
])


def test_clean_entry_has_no_findings(tmp_path):
    p = _write(tmp_path, "demo_method.yaml", GOOD)
    assert vk.check_file(p, str(tmp_path)) == []


def test_metadata_only_file_is_missing_payload(tmp_path):
    """只有元数据、没有正文键 = 空条目（老规则误报的正是另一类：index/pipeline）。"""
    p = _write(tmp_path, "empty_entry.yaml", L.join([
        "type: kb_entry", "name: empty_entry", "source: literature", "verified: unverified", ""]))
    rules = [f["rule"] for f in vk.check_file(p, str(tmp_path))]
    assert "missing_payload" in rules


def test_heterogeneous_schema_is_not_missing_payload(tmp_path):
    """index.yaml（resources）/ default_kb_method.yaml（pipeline）都是合法载荷，不得报错。"""
    a = _write(tmp_path, "index.yaml", L.join([
        "type: common_resource", "last_updated: '2026-06-25'", "resources:",
        "  gene_protein_coding:", "    file: gene.csv", ""]))
    b = _write(tmp_path, "default_kb_method.yaml", L.join([
        "direction: ad", "omics: rna", "pipeline:", "  annotation:", "    method: SingleR", ""]))
    for path in (a, b):
        rules = [f["rule"] for f in vk.check_file(path, str(tmp_path))]
        assert "missing_payload" not in rules, rules


def test_source_multiline_leak_is_error(tmp_path):
    p = _write(tmp_path, "leak.yaml", L.join([
        "type: kb_entry", "name: leak", "source: |",
        "  - Lin et al. 2024", "  - Nikopoulou et al. 2023", "content: 'body'", ""]))
    fs = vk.check_file(p, str(tmp_path))
    hit = [f for f in fs if f["rule"] == "source_multiline_leak"]
    assert hit and hit[0]["level"] == "error"


def test_noncanonical_source_gets_suggestion(tmp_path):
    p = _write(tmp_path, "sug.yaml", L.join([
        "type: kb_entry", "name: sug",
        "source: Literature-driven, curated from 12+ papers", "content: 'b'", ""]))
    hit = [f for f in vk.check_file(p, str(tmp_path)) if f["rule"] == "source_noncanonical"]
    assert hit and "literature" in hit[0]["detail"]


def test_duplicate_record_doi_is_error(tmp_path):
    """同名 + 同 DOI 写两份 = 真重复，error。"""
    for stem in ("a", "b"):
        _write(tmp_path, stem + ".yaml", L.join([
            "type: kb_entry", "name: same_entry", "doi: 10.1038/abc", "content: 'b'", ""]))
    rep = vk.scan(str(tmp_path))
    dup = [f for f in rep["findings"] if f["rule"] == "duplicate_record_doi"]
    assert len(dup) == 1 and dup[0]["level"] == "error"


def test_shared_doi_across_entries_is_warn(tmp_path):
    """不同条目共引同一篇文献（化合物库、聚合型 key_findings）是正常数据，只提醒不拦。"""
    for stem in ("cmp1", "cmp2"):
        _write(tmp_path, stem + ".yaml", L.join([
            "type: kb_entry", "name: " + stem, "doi: 10.1038/shared", "content: 'b'", ""]))
    rep = vk.scan(str(tmp_path))
    rules = {f["rule"]: f["level"] for f in rep["findings"]}
    assert rules.get("doi_shared_by_entries") == "warn"
    assert "duplicate_record_doi" not in rules


def test_method_spec_does_not_require_verified_quality(tmp_path):
    """方法/流程规格（pipeline/methods）不是知识条目，不该被要求 verified/quality/evidence。"""
    _write(tmp_path, "cellchat.yaml", L.join([
        "analysis_type: cellchat", "methods:", "  - CellChat", "source: literature",
        "auto_trigger:", "  - cellchat", "date: '2026-01-01'", ""]))
    rules = [f["rule"] for f in vk.scan(str(tmp_path))["findings"]]
    for r in ("missing_verified", "missing_quality", "missing_evidence", "missing_name",
              "missing_type", "missing_last_updated"):
        assert r not in rules, (r, rules)


def test_data_driven_entry_needs_no_citation(tmp_path):
    """record_run 回流的实测条目按设计就没有文献 DOI/PMID，不该报缺引用。"""
    _write(tmp_path, "cellchat-v2_empirical.yaml", L.join([
        "type: kb_entry", "name: cellchat-v2_empirical", "source: data_driven",
        "evidence: 'run log: record_run(cellchat)'", "verified: partially_verified",
        "quality: high", "last_updated: '2026-01-01'", "auto_trigger:", "  - cellchat-v2_empirical",
        "content: 'params'", ""]))
    rules = [f["rule"] for f in vk.scan(str(tmp_path))["findings"]]
    assert "missing_doi" not in rules and "missing_pmid" not in rules, rules


def test_literature_entry_still_requires_citation(tmp_path):
    """文献来源的条目缺 DOI/PMID 仍要提醒（这是真待办，不是噪声）。"""
    _write(tmp_path, "paper_demo.yaml", L.join([
        "type: kb_entry", "name: paper_demo", "source: literature",
        "evidence: '某文'", "verified: unverified", "quality: medium",
        "last_updated: '2026-01-01'", "auto_trigger:", "  - paper_demo", "content: 'x'", ""]))
    rules = [f["rule"] for f in vk.scan(str(tmp_path))["findings"]]
    assert "missing_doi" in rules and "missing_pmid" in rules, rules


def test_index_blank_source_is_not_error(tmp_path):
    """index.yaml 顶层 source: 留空是历史正常写法，不该报 source_not_string。"""
    _write(tmp_path, "index.yaml", L.join([
        "type: common_resource", "source:", "resources:", "  - path: a.yaml", ""]))
    rules = [f["rule"] for f in vk.scan(str(tmp_path))["findings"]]
    assert "source_not_string" not in rules, rules


def test_blank_name_does_not_trigger_filename_mismatch(tmp_path):
    """name 为空时不要顺手报 name 与文件名不一致。"""
    _write(tmp_path, "atac_seq.yaml", L.join([
        "filters:", "  min_cells: 200", "source: default_seed", "date: '2026-01-01'", ""]))
    rules = [f["rule"] for f in vk.scan(str(tmp_path))["findings"]]
    assert "name_filename_mismatch" not in rules, rules


def test_same_doi_same_name_in_other_dir_is_not_duplicate(tmp_path):
    """同名文件在不同物种/组织目录下共引同一篇（Homo/Mus 的 key_findings）是正常数据。"""
    for sub in ("Homo_sapiens", "Mus_musculus"):
        _write(tmp_path / sub, "key_findings.yaml", L.join([
            "type: kb_entry", "name: key_findings", "doi: 10.1/shared", "content: 'b'", ""]))
    rep = vk.scan(str(tmp_path))
    rules = [f["rule"] for f in rep["findings"]]
    assert "duplicate_record_doi" not in rules


def test_dois_list_counts_as_structured(tmp_path):
    """dois: [...] 列表也算已结构化（聚合型条目引用多篇）。"""
    p = _write(tmp_path, "agg.yaml", L.join([
        "type: kb_entry", "name: agg", "dois: [\"10.1/a\", \"10.1/b\"]", "content: 'b'", ""]))
    rules = [f["rule"] for f in vk.check_file(p, str(tmp_path))]
    assert "missing_doi" not in rules


def test_baseline_only_gates_new_errors(tmp_path):
    empty = L.join(["type: kb_entry", "name: old", "content: ''", ""])
    _write(tmp_path, "old.yaml", empty)
    base = os.path.join(str(tmp_path), "base.json")
    assert vk.main(["--root", str(tmp_path), "--baseline", base, "--update-baseline", "--quiet"]) == 0
    assert vk.main(["--root", str(tmp_path), "--baseline", base, "--quiet"]) == 0      # 老问题冻结 -> 通过
    _write(tmp_path, "new.yaml", L.join(["type: kb_entry", "name: new", "content: ''", ""]))
    assert vk.main(["--root", str(tmp_path), "--baseline", base, "--quiet"]) == 1      # 新问题 -> 拦下


def test_real_kb_has_zero_errors():
    """真库门禁：KB 里当前 error 数必须是 0（含 6 个 source 漏值修复后的回归）。"""
    rep = vk.scan(KB_ROOT)
    errors = [f for f in rep["findings"] if f["level"] == "error"]
    assert errors == [], "KB 出现 error：%s" % errors[:5]
    assert rep["stats"]["files"] >= 200
