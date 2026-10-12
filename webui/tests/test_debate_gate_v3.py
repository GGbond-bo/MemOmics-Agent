# -*- coding: utf-8 -*-
"""辩论门控 v3 矩阵（2026-10-12 用户口径重写）。

用户原话：
  · 「方案/脚本/设计 … 图/绘图/配色 —— 这些不需要辩论，意义不大。」
  · 「统计分析，这类结果有问题，grill me 进行询问即可，最多触发 L1 辩论，但是不要拖延时间；
      什么时候辩论呢，就是得到的结果太离谱。」
  · 「重要辩论：生信分析 + 有重要参数 + 结论跟实际/预期不一样、真实数据差异很大
      → 正方反方找证据链。」
  · 「辩论是从不同方向寻找证据链：知识库已验知识（L0/L1/L2/L3）、统计学（统计方法和过程
      有没有问题）、生信（步骤/方法有没有错误）。」

本文件把新矩阵钉死，防止以后再退回「什么结论都辩」。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import enforcement as enf  # noqa: E402  (webui 目录由 tests/conftest.py 加入 sys.path)


def _mk_es(level="analysis", count=0, budget=3, topic="", last_result=""):
    es = enf.EnforcementState("test_sid")
    es.analysis_level = level
    es.debate_count = count
    es.debate_budget = budget
    es.topic_hint = topic
    es._last_terminal_result = last_result
    return es


# ==================== 题类分类器 ====================

class TestClassifyTopicKind:
    def test_figure_beats_bioinfo(self):
        """画图的脚本里也会写统计/生信字样 —— 图优先，按用户口径不辩。"""
        assert enf.classify_topic_kind("画一个 snRNA-seq 的 UMAP 图，配色改一下") == enf._DEBATE_KIND_FIGURE
        assert enf.classify_topic_kind("用 ggplot 出火山图，色标换 viridis") == enf._DEBATE_KIND_FIGURE

    def test_design_beats_stats(self):
        assert enf.classify_topic_kind("脚本设计方案：统计检验用哪种写法比较好") == enf._DEBATE_KIND_DESIGN

    def test_stats(self):
        assert enf.classify_topic_kind("配对样本量不够，多重检验要不要用 FDR") == enf._DEBATE_KIND_STATS

    def test_bioinfo(self):
        assert enf.classify_topic_kind("snRNA-seq 做完批次校正后 DEG 数量怎么判") == enf._DEBATE_KIND_BIOINFO

    def test_empty_is_other(self):
        assert enf.classify_topic_kind("") == enf._DEBATE_KIND_OTHER


class TestLooksAbsurd:
    def test_hits(self):
        for t in ("结果太离谱了", "与预期不符", "真实数据差异很大", "这批 p 值假阳性偏多",
                  "outliers everywhere, inconsistent with prior"):
            assert enf.looks_absurd(t), t

    def test_misses(self):
        for t in ("跑通了，输出 3 个文件", "p=0.03，与预期一致"):
            assert not enf.looks_absurd(t), t


# ==================== 门控矩阵 v3 ====================

class TestDebateGateV3:
    def test_design_never_debates_even_with_hard_signals(self):
        """方案/脚本/设计：永不辩 —— 即使高影响/连续失败也不辩（报错该修错，不该开辩论）。"""
        for sig in ({}, {"high_impact": True}, {"failed_retries": 3}, {"has_fork": True}):
            s = dict(sig)
            s["topic_kind"] = enf._DEBATE_KIND_DESIGN
            lvl, reasons, force = enf.debate_gate(_mk_es(), "conclusion", s)
            assert lvl == enf.DEBATE_L0 and force is False, (sig, lvl, reasons)

    def test_figure_never_debates(self):
        lvl, reasons, _ = enf.debate_gate(_mk_es(), "conclusion",
                                          {"topic_kind": enf._DEBATE_KIND_FIGURE})
        assert lvl == enf.DEBATE_L0
        assert any("图/绘图/配色" in r for r in reasons)

    def test_stats_without_anomaly_skips(self):
        lvl, reasons, _ = enf.debate_gate(_mk_es("statistical", topic="配对检验"),
                                          "conclusion", {"topic_kind": enf._DEBATE_KIND_STATS})
        assert lvl == enf.DEBATE_L0
        assert any("未见离谱" in r for r in reasons)

    def test_stats_with_absurd_result_is_l1_and_grills(self):
        lvl, reasons, force = enf.debate_gate(
            _mk_es("statistical", topic="统计检验"),
            "conclusion",
            {"topic_kind": enf._DEBATE_KIND_STATS, "deviation": "结果太离谱"})
        assert lvl == enf.DEBATE_L1 and force is False
        assert any("grill" in r for r in reasons)
        tools, text = enf._debate_require_payload(enf._DEBATE_KIND_STATS, lvl, reasons)
        assert tools == ["ask_user"], "统计线必须先问用户，不是直接开辩论"
        assert "ask_user" in text and "L1" in text

    def test_stats_is_capped_at_l1_even_high_impact(self):
        lvl, reasons, force = enf.debate_gate(
            _mk_es("statistical", topic="统计"),
            "conclusion",
            {"topic_kind": enf._DEBATE_KIND_STATS, "deviation": "与预期不符", "high_impact": True})
        assert lvl == enf.DEBATE_L1 and force is False, reasons

    def test_bioinfo_important_params_plus_deviation_is_l2_evidence_chain(self):
        lvl, reasons, force = enf.debate_gate(
            _mk_es("analysis", topic="snRNA-seq 批次校正后 DEG 数量远超预期"),
            "conclusion",
            {"topic_kind": enf._DEBATE_KIND_BIOINFO, "important_params": True,
             "deviation": "远超预期"})
        assert lvl == enf.DEBATE_L2, reasons
        assert any("证据链" in r for r in reasons)
        tools, text = enf._debate_require_payload(enf._DEBATE_KIND_BIOINFO, lvl, reasons)
        assert tools == ["debate_analysis"]
        for token in ("L0", "L1", "L2", "L3", "统计线", "生信线"):
            assert token in text, token

    def test_bioinfo_without_important_params_skips(self):
        lvl, reasons, _ = enf.debate_gate(
            _mk_es("analysis", topic="snRNA-seq 分析"),
            "conclusion",
            {"topic_kind": enf._DEBATE_KIND_BIOINFO, "deviation": "与预期不符"})
        assert lvl == enf.DEBATE_L0
        assert any("无重要参数" in r for r in reasons)

    def test_bioinfo_params_but_consistent_result_skips(self):
        """参数重要但结果和预期一致 → 不辩（用户：只在结论对不上时才辩）。"""
        lvl, reasons, _ = enf.debate_gate(
            _mk_es("analysis", topic="snRNA-seq 分析"),
            "conclusion",
            {"topic_kind": enf._DEBATE_KIND_BIOINFO, "important_params": True})
        assert lvl == enf.DEBATE_L0
        assert any("无异常信号" in r for r in reasons)

    def test_bioinfo_params_with_fork_is_l1(self):
        lvl, _, _ = enf.debate_gate(
            _mk_es("analysis", topic="snRNA-seq"),
            "conclusion",
            {"topic_kind": enf._DEBATE_KIND_BIOINFO, "important_params": True,
             "fork_options": ["harmony", "scanorama"]})
        assert lvl == enf.DEBATE_L1

    def test_other_kind_with_absurd_result_is_l2(self):
        lvl, _, _ = enf.debate_gate(_mk_es(), "conclusion", {"deviation": "差异非常大"})
        assert lvl == enf.DEBATE_L2

    def test_other_kind_without_signal_skips(self):
        lvl, reasons, _ = enf.debate_gate(_mk_es(), "conclusion")
        assert lvl == enf.DEBATE_L0
        assert any("未识别到" in r for r in reasons)

    def test_budget_guard_stops_instead_of_downgrading(self):
        """超预算的非强制场次必须**真停**（旧实现只降 L2→L1，等于没停）。"""
        lvl, reasons, force = enf.debate_gate(
            _mk_es("analysis", count=3, budget=3, topic="snRNA-seq DEG"),
            "conclusion",
            {"topic_kind": enf._DEBATE_KIND_BIOINFO, "important_params": True, "deviation": "远超预期"})
        assert lvl == enf.DEBATE_L0 and force is False
        assert any("预算护栏" in r for r in reasons)

    def test_forced_high_impact_bypasses_budget_guard(self):
        lvl, _, force = enf.debate_gate(
            _mk_es(count=99, budget=3), "conclusion", {"high_impact": True})
        assert lvl == enf.DEBATE_L2 and force is True


class TestGateReadsStateHints:
    """门控要能从 es 的运行时提示里拿信号（server 侧只写 es.topic_hint / 工具结果）。"""

    def test_topic_hint_drives_kind(self):
        lvl, reasons, _ = enf.debate_gate(_mk_es("analysis", topic="帮我出个图，配色好看点"), "conclusion")
        assert lvl == enf.DEBATE_L0 and any("图/绘图/配色" in r for r in reasons)

    def test_last_result_deviation_is_detected(self):
        lvl, _, _ = enf.debate_gate(
            _mk_es("analysis", topic="snRNA-seq DEG 分析",
                   last_result="85% 基因显著，p 中位数 2.4e-288，结果太离谱"),
            "conclusion", {"topic_kind": enf._DEBATE_KIND_BIOINFO, "important_params": True})
        assert lvl == enf.DEBATE_L2