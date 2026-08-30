# -*- coding: utf-8 -*-
"""L0 conclusion store v2: failure markers + L3 index tests (2026-08-31)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import conclusion_store as cs


def _sess(tmp_path):
    return {"id": "s1", "results_dir": str(tmp_path / "results")}


class TestExtract:
    def test_extracts_conclusion_fix_decision(self):
        out = cs.extract_turn_conclusions("问题", "结论：猴脑 peak 成功了，525137 个。\n根因：rtracklayer 可用，之前失败是正则转义。\n决定：改用 rtracklayer。")
        kinds = [k for k, _ in out]
        assert "结论" in kinds and "修复" in kinds and "决策" in kinds
        assert len(out) == 3

    def test_failure_lines_recorded(self):
        out = cs.extract_turn_conclusions("", "还没有解决这个问题。\n无法确定根因。\n没有结论。\n做不了，缺少 UCSC 依赖。")
        kinds = [k for k, _ in out]
        assert len(out) >= 3 and all(k == "失败" for k in kinds)

    def test_fix_beats_failure(self):
        out = cs.extract_turn_conclusions("", "之前失败，现已修复根因。")
        assert out and out[0][0] == "修复"

    def test_skips_non_conclusive_lines(self):
        out = cs.extract_turn_conclusions("", "运行成功。\n```r\nsaveRDS(x)\n```\nmermaid 图已生成\n这是普通说明文字")
        assert out == []

    def test_dedup_in_same_reply(self):
        out = cs.extract_turn_conclusions("", "结论：这是A结论\n\n结论：这是A结论\n\n结论：这是B结论")
        texts = [t for _, t in out]
        assert len(texts) == 2 and any("这是A结论" in t for t in texts) and any("这是B结论" in t for t in texts)

    def test_truncates_long_line(self):
        longline = "结论：" + "很长" * 500
        out = cs.extract_turn_conclusions("", longline)
        assert out and len(out[0][1]) <= 203

    def test_huge_text_no_crash(self):
        huge = "结论：" + "数据" * 20000
        out = cs.extract_turn_conclusions("", huge)
        assert out and len(out[0][1]) <= 203

    def test_empty_and_control_chars(self):
        assert cs.extract_turn_conclusions("", "") == []
        assert cs.extract_turn_conclusions("", "\u0000\u001b\ufffd") == []
        assert cs.extract_turn_conclusions("", "！！！") == []

    def test_code_only_reply(self):
        out = cs.extract_turn_conclusions("", "```python\nimport pandas as pd\n```")
        assert out == []

    def test_mixed_languages(self):
        out = cs.extract_turn_conclusions("", "结论: Fixed the peak bug now.\n根因: rtracklayer import.bw() works.")
        assert len(out) >= 2


class TestStore:
    def test_append_and_read_dedup(self, tmp_path):
        s = _sess(tmp_path)
        ids1 = cs.append_conclusions(s, [("结论", "A"), ("修复", "B")])
        ids2 = cs.append_conclusions(s, [("结论", "A"), ("结论", "C")])
        assert len(ids1) == 2 and len(ids2) == 1
        txt = cs.read_conclusions(s, limit=10)
        assert "A" in txt and "B" in txt and "C" in txt and "[id:1]" in txt
        assert txt.count("A") == 1

    def test_failure_entry_has_id(self, tmp_path):
        s = _sess(tmp_path)
        cs.append_conclusions(s, [("失败", "做不了：缺 UCSC 依赖")])
        txt = cs.read_conclusions(s)
        assert "[失败]" in txt and "[id:1]" in txt and "UCSC" in txt

    def test_ids_incremental(self, tmp_path):
        s = _sess(tmp_path)
        a = cs.append_conclusions(s, [("结论", "X1"), ("失败", "X2")])
        b = cs.append_conclusions(s, [("结论", "X3")])
        assert a == [1, 2] and b == [3]

    def test_archive_and_l3_index(self, tmp_path):
        s = _sess(tmp_path)
        ids = cs.append_conclusions(s, [("失败", "做不了：rtracklayer 报错")])
        arc = cs.archive_turn(s, "用户问题", "回复内容：rtracklayer 报错", "tool: R error")
        assert arc and arc.endswith(".md")
        cs.link_archive(s, ids, arc)
        idx = cs.read_l3_index(s)
        assert idx.get("archives", {}).get(str(ids[0])) == arc

    def test_cap_100_entries(self, tmp_path):
        s = _sess(tmp_path)
        for i in range(120):
            cs.append_conclusions(s, [("结论", f"结论编号{i}")])
        p = cs.conclusions_path(s)
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("- [")]
        assert len(lines) == 100
        t = cs.read_conclusions(s, limit=20)
        assert "结论编号119" in t and "结论编号0" not in t

    def test_max_chars_cap(self, tmp_path):
        s = _sess(tmp_path)
        for i in range(20):
            cs.append_conclusions(s, [("结论", f"结论{i} 内容" * 10)])
        t = cs.read_conclusions(s, limit=20, max_chars=300)
        assert len(t) <= 310

    def test_no_results_dir_returns_empty(self, tmp_path):
        s = {"id": "s1", "results_dir": ""}
        assert cs.append_conclusions(s, [("结论", "X")]) == []
        assert cs.read_conclusions(s) == ""

    def test_build_context(self, tmp_path):
        s = _sess(tmp_path)
        cs.append_conclusions(s, [("结论", "重要的是这条"), ("失败", "做不了那条")])
        ctx = cs.build_memory_budget_context(s, "问题")
        assert "会话结论/失败注册表" in ctx and "重要的是这条" in ctx and "做不了那条" in ctx
        assert "不要重复重试" in ctx

    def test_unicode_entries(self, tmp_path):
        s = _sess(tmp_path)
        cs.append_conclusions(s, [("结论", "🧬 phyloP 保守性✅ 501bp")])
        t = cs.read_conclusions(s)
        assert "phyloP" in t and "501bp" in t
