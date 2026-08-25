# -*- coding: utf-8 -*-
"""文献证据表测试：写入/幂等去重/查询过滤/统计/CSV 导出/引用校验/并发写。"""
import csv
import importlib.util
import json
import os
import sys
import tempfile
import threading

import pytest

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


et = _load("evidence_table", os.path.join(_ROOT, "memomics", "bio_tools", "evidence_table.py"))

pytestmark = pytest.mark.unit

REAL_DOI = "10.1016/j.devcel.2026.03.010"  # 真实库 papers 索引里的 DOI


@pytest.fixture()
def rd(tmp_path):
    return str(tmp_path / "results")


# ── 写入与幂等 ──────────────────────────────────────────────────────────────

def test_write_and_idempotent_update(rd):
    r1 = json.loads(et.write_evidence_row(
        rd, "10.1016/j.devcel.2026.03.010",
        "NMJ 在肌肉萎缩时发生轴突丢失", method="snRNA+snATAC+spatial",
        species="mouse", direction="aging", strength="strong"))
    assert r1["ok"] is True and r1["total"] == 1
    # 同 (doi, claim) 再写 → 更新而非追加
    r2 = json.loads(et.write_evidence_row(
        rd, "https://doi.org/10.1016/j.devcel.2026.03.010",  # URL 前缀也能规范化
        "NMJ 在肌肉萎缩时发生轴突丢失", strength="conflict"))
    assert r2["updated"] is True and r2["total"] == 1
    assert r2["row"]["strength"] == "conflict"
    # 不同 claim → 追加
    r3 = json.loads(et.write_evidence_row(
        rd, "10.1016/j.devcel.2026.03.010", "出现特化突触肌核 SynM"))
    assert r3["total"] == 2


def test_write_rejects_invalid(rd):
    assert json.loads(et.write_evidence_row(rd, "", "x"))["ok"] is False  # 空 DOI
    assert json.loads(et.write_evidence_row(rd, "not-a-doi", "x"))["ok"] is False
    assert json.loads(et.write_evidence_row(rd, "10.1000/xyz", ""))["ok"] is False  # 空 claim
    # 非法 strength → 回退 moderate
    r = json.loads(et.write_evidence_row(rd, "10.1000/xyz", "claim", strength="bogus"))
    assert r["row"]["strength"] == "moderate"


def test_doi_normalization(rd):
    for raw, want in [
        ("https://doi.org/10.1038/s41467-025-56896-6", "10.1038/s41467-025-56896-6"),
        ("DOI: 10.1000/abc", "10.1000/abc"),
        ("10.1016/j.freeradbiomed.2024.07.026", "10.1016/j.freeradbiomed.2024.07.026"),
    ]:
        assert et._norm_doi(raw) == want, raw


# ── 查询 / 统计 / 导出 ──────────────────────────────────────────────────────

def test_query_filters(rd):
    et.write_evidence_row(rd, "10.1000/a", "结论A", direction="aging", species="human")
    et.write_evidence_row(rd, "10.1000/b", "结论B about mitochondria", direction="exercise", species="mouse")
    et.write_evidence_row(rd, "10.1000/c", "结论C", direction="aging", species="mouse")
    # 主题过滤
    q = json.loads(et.query_evidence(rd, topic="mitochondria"))
    assert q["total_matched"] == 1 and q["rows"][0]["doi"] == "10.1000/b"
    # 方向 + 物种过滤
    q2 = json.loads(et.query_evidence(rd, direction="aging", species="mouse"))
    assert q2["total_matched"] == 1 and q2["rows"][0]["doi"] == "10.1000/c"
    # DOI 过滤
    q3 = json.loads(et.query_evidence(rd, doi="10.1000/a"))
    assert q3["total_matched"] == 1
    # limit
    q4 = json.loads(et.query_evidence(rd, limit=2))
    assert len(q4["rows"]) == 2
    # 最新在前
    assert q4["rows"][0]["doi"] == "10.1000/c"


def test_stats_and_export(rd):
    et.write_evidence_row(rd, "10.1000/a", "c1", direction="aging", strength="strong")
    et.write_evidence_row(rd, "10.1000/b", "c2", direction="exercise", strength="weak")
    st = json.loads(et.evidence_stats(rd))
    assert st["total"] == 2
    assert st["by_direction"] == {"aging": 1, "exercise": 1}
    assert st["by_strength"] == {"strong": 1, "weak": 1}
    ex = json.loads(et.export_evidence_csv(rd))
    assert ex["ok"] is True and ex["rows"] == 2
    with open(ex["path"], "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["doi"] == "10.1000/a"
    assert "claim" in rows[0]


# ── 引用校验 ────────────────────────────────────────────────────────────────

def test_extract_citations():
    text = ("本文引用 10.1016/j.devcel.2026.03.010 与 PMID: 42612631，"
            "另见 https://doi.org/10.1038/s41467-025-56896-6 和 doi.org/10.1000/x，"
            "重复的 10.1016/j.devcel.2026.03.010 只算一次。")
    cites = et._extract_citations(text)
    kinds = [k for k, _ in cites]
    assert kinds.count("doi") == 3, f"got {cites}"  # devcel + ncomms + 10.1000/x
    assert ("pmid", "42612631") in cites
    assert len(cites) == len(set(cites))


def test_verify_citations_real_index(rd):
    """真实 papers 索引对照：真实 DOI 命中（论文库）、编造 DOI 缺失。"""
    et.write_evidence_row(rd, REAL_DOI, "NMJ 重塑")
    text = (f"支持证据：{REAL_DOI}（库内）与 10.9999/fake-doi-2026（编造），"
            "PMID: 1234567（编造）")
    v = json.loads(et.verify_citations(rd, text))
    assert v["ok"] is True and v["total"] == 3
    verified_ids = [x["id"] for x in v["verified"]]
    missing_ids = [x["id"] for x in v["missing"]]
    assert REAL_DOI in verified_ids, f"真实 DOI 应命中: {verified_ids}"
    assert "10.9999/fake-doi-2026" in missing_ids
    assert "1234567" in missing_ids


def test_verify_empty_text(rd):
    v = json.loads(et.verify_citations(rd, "没有引用"))
    assert v["total"] == 0


# ── 并发写 ──────────────────────────────────────────────────────────────────

def test_concurrent_writes_no_corruption(rd):
    errors = []

    def _w(i):
        try:
            for j in range(15):
                et.write_evidence_row(rd, f"10.1000/doc{i}", f"结论 {i}-{j}")
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=_w, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    st = json.loads(et.evidence_stats(rd))
    assert st["total"] == 60, f"4 线程 × 15 行 = 60，got {st['total']}"
    # 文件可解析、无 tmp 残留
    assert not [f for f in os.listdir(os.path.join(rd, "review"))
                if f.endswith(".tmp")]
