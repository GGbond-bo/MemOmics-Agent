# -*- coding: utf-8 -*-
"""PRISMA 系统综述流程记账测试（Mode C）：协议/阶段计数/筛选/检索/排除/导出/并发。"""
import importlib.util
import json
import os
import sys
import threading

import pytest

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pf = _load("prisma_flow", os.path.join(_ROOT, "memomics", "bio_tools", "prisma_flow.py"))

pytestmark = pytest.mark.unit


@pytest.fixture()
def rd(tmp_path):
    return str(tmp_path / "results")


# ── 协议与阶段计数 ──────────────────────────────────────────────────────────

def test_init_and_stage_counts(rd):
    r = json.loads(pf.init_prisma(rd, picot="P: 老年人 I: 运动 C: 不运动 O: 肌肉量",
                                  inclusion=["RCT"], exclusion=["综述"],
                                  databases=["PubMed", "EuropePMC"]))
    assert r["ok"] is True
    assert r["protocol"]["databases"] == ["PubMed", "EuropePMC"]

    assert json.loads(pf.update_stage(rd, "identified", 120))["count"] == 120
    assert json.loads(pf.update_stage(rd, "deduplicated", 98))["count"] == 98
    # add 模式累加
    assert json.loads(pf.update_stage(rd, "identified", 10, mode="add"))["count"] == 130
    # 非法 stage / count
    assert json.loads(pf.update_stage(rd, "bogus", 5))["ok"] is False
    assert json.loads(pf.update_stage(rd, "included", "abc"))["ok"] is False
    # 负值钳 0
    assert json.loads(pf.update_stage(rd, "included", -3))["count"] == 0


def test_exclusion_categories(rd):
    assert json.loads(pf.record_exclusion(rd, "duplicate", 22))["count"] == 22
    assert json.loads(pf.record_exclusion(rd, "title_abstract", 30))["count"] == 30
    assert json.loads(pf.record_exclusion(rd, "title_abstract", 5))["count"] == 35  # 累计
    assert json.loads(pf.record_exclusion(rd, "bogus"))["ok"] is False


# ── 筛选记录 ────────────────────────────────────────────────────────────────

def test_screening_records(rd):
    r1 = json.loads(pf.record_screening(rd, "10.1000/alpha", "include", reason="主题相关"))
    assert r1["ok"] is True and r1["total"] == 1
    r2 = json.loads(pf.record_screening(rd, "10.1000/beta", "exclude", reason="非RCT"))
    assert r2["total"] == 2
    # 同 item+stage 更新而非追加
    r3 = json.loads(pf.record_screening(rd, "10.1000/alpha", "exclude",
                                        reason="复核后排除", stage="fulltext"))
    assert r3["total"] == 3  # 不同 stage → 新记录
    r4 = json.loads(pf.record_screening(rd, "10.1000/alpha", "include",
                                        reason="改判纳入", stage="title_abstract"))
    assert r4["total"] == 3  # 同 stage → 更新
    # 非法参数
    assert json.loads(pf.record_screening(rd, "", "include"))["ok"] is False
    assert json.loads(pf.record_screening(rd, "10.1000/x", "maybe"))["ok"] is False
    assert json.loads(pf.record_screening(rd, "10.1000/x", "include",
                                          stage="bogus"))["ok"] is False


def test_search_log(rd):
    assert json.loads(pf.record_search(rd, "PubMed", "muscle AND aging", 45))["searches"] == 1
    assert json.loads(pf.record_search(rd, "EuropePMC", "muscle AND aging",
                                       30, date="2026-08-25"))["searches"] == 2
    assert json.loads(pf.record_search(rd, "", "x", 1))["ok"] is False


# ── 状态与导出 ──────────────────────────────────────────────────────────────

def _full_flow(rd):
    """跑一遍完整 PRISMA 流程（C1-C8 模拟）。"""
    pf.init_prisma(rd, picot="test", databases=["PubMed"])
    pf.update_stage(rd, "identified", 90)
    pf.record_exclusion(rd, "duplicate", 5)
    pf.update_stage(rd, "deduplicated", 85)
    for i in range(70):
        pf.record_screening(rd, f"10.1000/s{i}", "exclude", reason="标题不符")
    pf.record_exclusion(rd, "title_abstract", 70)
    pf.update_stage(rd, "screened", 15)
    for i in range(3):
        pf.record_screening(rd, f"10.1000/f{i}", "exclude", reason="全文无数据",
                            stage="fulltext")
    pf.record_exclusion(rd, "fulltext", 3)
    pf.update_stage(rd, "fulltext", 15)
    pf.update_stage(rd, "eligible", 12)
    pf.update_stage(rd, "included", 12)


def test_status_and_mermaid(rd):
    _full_flow(rd)
    st = json.loads(pf.prisma_status(rd))
    assert st["stages"] == {"identified": 90, "deduplicated": 85, "screened": 15,
                            "fulltext": 15, "eligible": 12, "included": 12}
    assert st["exclusions"]["duplicate"] == 5
    assert st["exclusions"]["title_abstract"] == 70
    assert st["screening_total"] == 73
    assert st["screening_include"] == 0 and st["screening_exclude"] == 73
    # mermaid 图包含关键数字
    m = st["mermaid"]
    assert "flowchart TD" in m
    assert "n=90" in m and "n=85" in m and "n=15" in m and "n=12" in m
    assert "排除 70" in m and "排除 3" in m


def test_export_report(rd):
    _full_flow(rd)
    ex = json.loads(pf.export_prisma(rd))
    assert ex["ok"] is True and ex["included"] == 12
    with open(ex["path"], "r", encoding="utf-8") as f:
        md = f.read()
    assert "PRISMA 系统综述流程报告" in md
    assert "| 纳入（定量综合） | 12 |" in md
    assert "| 重复 | 5 |" in md
    assert "```mermaid" in md
    assert "10.1000/s0" in md  # 筛选记录


def test_empty_state_status(rd):
    st = json.loads(pf.prisma_status(rd))
    assert st["ok"] is True and st["stages"]["identified"] == 0
    assert "flowchart TD" in st["mermaid"]


# ── 一致性（C9）与并发 ──────────────────────────────────────────────────────

def test_consistency_math(rd):
    """C9 自检：各阶段单调 + 排除数 ≈ 阶段差值。"""
    _full_flow(rd)
    st = json.loads(pf.prisma_status(rd))
    s = st["stages"]
    assert s["identified"] >= s["deduplicated"] >= s["screened"] >= s["fulltext"] >= s["eligible"] >= s["included"]
    assert s["deduplicated"] - s["screened"] == st["exclusions"]["title_abstract"]  # 85-15=70
    assert s["fulltext"] - s["eligible"] == st["exclusions"]["fulltext"]  # 15-12=3


def test_concurrent_updates_no_corruption(rd):
    errors = []

    def _w(i):
        try:
            for j in range(10):
                pf.update_stage(rd, "screened", 1, mode="add")
                pf.record_screening(rd, f"10.1000/c{i}-{j}", "exclude", reason="r")
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=_w, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    st = json.loads(pf.prisma_status(rd))
    assert st["stages"]["screened"] == 40, f"4×10 add，got {st['stages']['screened']}"
    assert st["screening_total"] == 40
    # 无 tmp 残留
    assert not [f for f in os.listdir(os.path.join(rd, "review"))
                if f.endswith(".tmp")]
