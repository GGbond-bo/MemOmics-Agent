# -*- coding: utf-8 -*-
"""辩论卡片展示证据链状态（2026-10-13）。

用户要求：卡片上直接展示 chain_verdicts —— 「哪一方断链、断在哪一步」比 verdict 本身更有用。
本文件只测后端那一半：/api/results/<sid>/debates 索引条目必须带上 chain_pro/chain_con/
chain_decisive（前端 index.html 的 _dcbEntry/debateShellHtml 负责渲染，兼容字符串与对象两种形态）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server  # noqa: E402


class TestDebateChainBits:
    def test_string_form(self):
        b = server._debate_chain_bits({
            "chain_verdicts": {"pro": "断链（断点：无数据锚点）", "con": "部分", "decisive": "数据锚点"}})
        assert b["has_chain"] is True
        assert b["chain_pro"].startswith("断链")
        assert b["chain_con"] == "部分"
        assert b["chain_decisive"] == "数据锚点"

    def test_object_form(self):
        """兼容 {"state": "断链", "break_at": "多重检验没查"} 形态。"""
        b = server._debate_chain_bits({
            "chain_verdicts": {"pro": {"state": "断链", "break_at": "多重检验没查"},
                               "con": {"state": "完整"}, "decisive": {"state": "正方断链"}}})
        assert "断点：多重检验没查" in b["chain_pro"], b
        assert b["chain_con"] == "完整"
        assert b["chain_decisive"] == "正方断链"

    def test_missing_is_empty_not_broken(self):
        b = server._debate_chain_bits({"verdict": "ok"})
        assert b == {"has_chain": False, "chain_pro": "", "chain_con": "", "chain_decisive": ""}

    def test_index_entry_carries_chain(self):
        """索引条目（折叠卡片数据源）也要带上，否则时间线卡片看不到链状态。"""
        rec = {"topic": "t", "verdict": "need_more_info", "confidence": "low",
               "chain_verdicts": {"pro": "断链（断点：无锚点）", "con": "部分", "decisive": "都缺锚点"}}
        entry = server._debate_index_entry("sid", "/tmp", "log/x.json", "/tmp/log/x.json",
                                           rec, "k1", 0.0)
        assert entry["has_chain"] is True and entry["chain_pro"].startswith("断链"), entry