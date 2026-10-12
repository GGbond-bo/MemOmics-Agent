# -*- coding: utf-8 -*-
"""claim 账本（结论级溯源 + C 级分级 + PTR 自检 + 辩论参数通道）回归。

依据：plans/closed-loop-agent-roadmap-20261012.md §2.2/§2.3/§2.4①/§2.6
      plans/benchmark/tasks-15-v0.md §0.4（PTR 五要件 / ABR 弃权 / COST）
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from memomics.bio_tools import claim_ledger as cl  # noqa: E402


def _mk_results(tmp_path, with_env=True, with_manifest=True):
    rd = str(tmp_path / "memomics-zz")
    os.makedirs(os.path.join(rd, "data"), exist_ok=True)
    os.makedirs(os.path.join(rd, "scripts"), exist_ok=True)
    os.makedirs(os.path.join(rd, "logs"), exist_ok=True)
    (tmp_path / "memomics-zz" / "data" / "counts.csv").write_text("gene,s1\nA,1\nB,2\n", encoding="utf-8")
    (tmp_path / "memomics-zz" / "scripts" / "deg.R").write_text("library(DESeq2)\n", encoding="utf-8")
    (tmp_path / "memomics-zz" / "logs" / "deg.log").write_text("done\n", encoding="utf-8")
    if with_env:
        (tmp_path / "memomics-zz" / "environment.json").write_text(
            json.dumps({"conda": "scanpy310", "R": "4.4.1", "python": "3.12"}), encoding="utf-8")
    if with_manifest:
        (tmp_path / "memomics-zz" / "analysis_manifest.json").write_text(
            json.dumps({"schema": "memomics.analysis_manifest.v1", "session": "zz",
                        "params": {"padj": 0.05}}, ensure_ascii=False), encoding="utf-8")
    return rd


class TestPTR:
    def test_empty_dir_scores_zero_with_hints(self, tmp_path):
        rd = str(tmp_path / "empty")
        os.makedirs(rd, exist_ok=True)
        rep = cl.ptr_report(rd)
        assert rep["score"] == 0.0 and rep["verdict"] == "fail"
        assert len(rep["missing"]) == 5, rep["missing"]

    def test_full_dir_scores_one(self, tmp_path):
        rd = _mk_results(tmp_path)
        rep = cl.ptr_report(rd)
        assert rep["score"] == 1.0 and rep["verdict"] == "pass", rep
        assert all(c["ok"] for c in rep["checks"].values())

    def test_partial_when_env_missing(self, tmp_path):
        rd = _mk_results(tmp_path, with_env=False)
        rep = cl.ptr_report(rd)
        assert rep["score"] == 0.8 and rep["verdict"] == "partial", rep
        assert any("环境指纹" in m for m in rep["missing"])

    def test_ptr_writes_report_file(self, tmp_path):
        rd = _mk_results(tmp_path)
        cl.ptr_report(rd)
        p = os.path.join(rd, "claims", "ptr.json")
        assert os.path.isfile(p)
        assert json.load(open(p, encoding="utf-8"))["schema"] == "memomics.ptr_report.v1"


class TestLevelGate:
    """C 级准入门槛：只降不升（防虚高）。"""

    def test_c4_without_verifiers_downgrades_to_c0(self, tmp_path):
        rd = _mk_results(tmp_path)
        c = cl.add_claim(rd, "老年组 II 型纤维基因下调", level="C4")
        assert c["level"] == "C0", c
        reasons = " ".join(c.get("level_downgrade_reasons") or [])
        assert "无湿实验" in reasons and "hold-out" in reasons and "≥2 种方法" in reasons

    def test_climb_step_by_step(self, tmp_path):
        rd = _mk_results(tmp_path)
        c = cl.add_claim(rd, "claim-A", level="C0")
        # 统计门禁 + 两种方法 → C2
        c = cl.add_verifier(rd, c["claim_id"],
                            {"kind": "statistical_gate", "passed": True, "target_level": "C2"})
        cl.record_decision(rd, topic="方法选择", decision="用 DESeq2 + edgeR 双跑",
                           params={"method": ["DESeq2", "edgeR"], "padj": 0.05})
        c = cl.add_verifier(rd, c["claim_id"], {"kind": "holdout", "dataset": "GSE164471",
                                                "direction": "consistent", "target_level": "C2"})
        assert c["level"] == "C2", c
        # 重跑一致 → 已经够 C2；再加 hold-out → C3
        c = cl.add_verifier(rd, c["claim_id"], {"kind": "independent_rerun", "runs": 3,
                                                "agreement": "3/3", "target_level": "C3"})
        assert c["level"] == "C3", c

    def test_wetlab_required_for_c4(self, tmp_path):
        rd = _mk_results(tmp_path)
        cl.record_decision(rd, topic="t", decision="d", params={"method": ["a", "b"]})
        c = cl.add_claim(rd, "claim-B", level="C0")
        c = cl.add_verifier(rd, c["claim_id"], {"kind": "statistical_gate", "target_level": "C4"})
        c = cl.add_verifier(rd, c["claim_id"], {"kind": "holdout", "target_level": "C4"})
        c = cl.add_verifier(rd, c["claim_id"], {"kind": "independent_rerun", "runs": 2,
                                                "agreement": "2/2", "target_level": "C4"})
        assert c["level"] == "C3", c
        c = cl.add_verifier(rd, c["claim_id"], {"kind": "wetlab", "target_level": "C4"})
        assert c["level"] == "C4", c


class TestParamsChannel:
    """辩论/裁决 → 参数决策通道（用户口径：辩论结论要能用于后面的分析）。"""

    def test_decision_from_debate_result(self, tmp_path):
        rd = _mk_results(tmp_path)
        result = {
            "topic": "批次校正 vs 直接出差异", "level": "L2", "verdict": "modify",
            "confidence": "medium", "decision": "先 sva 校正再出差异",
            "recommended_params": {"batch_method": "sva", "padj": 0.05},
            "chain_verdicts": {"pro": "完整", "con": "部分", "decisive": "批次混杂证据"},
            "next_actions": [{"action": "跑 sva", "owner": "ai"}],
            "missing": ["批次列"],
        }
        out = cl.record_decision_from_result(rd, result)
        assert out["params"]["batch_method"] == "sva", out
        pj = cl.read_params(rd)
        assert pj["decision"] == "先 sva 校正再出差异"
        assert any("证据链决定项" in e for e in pj["evidence"])
        # 再辩一次 → history 累积、参数后写覆盖
        cl.record_decision_from_debate = None  # 防误用（占位）
        cl.record_decision(rd, topic="再议", decision="改用 limma",
                           params={"batch_method": "limma"})
        pj2 = cl.read_params(rd)
        assert pj2["params"]["batch_method"] == "limma"
        assert len(pj2["history"]) == 2

    def test_params_available_to_ptr(self, tmp_path):
        rd = _mk_results(tmp_path, with_manifest=False)   # 没有 manifest，只有辩论通道
        cl.record_decision(rd, topic="t", decision="d", params={"padj": 0.1})
        rep = cl.ptr_report(rd)
        assert rep["checks"]["params"]["ok"] is True, rep["checks"]["params"]
        assert rep["checks"]["params"]["detail"]["source"] == "claims/params.json"


class TestClaimStorage:
    def test_appends_and_indexes(self, tmp_path):
        rd = _mk_results(tmp_path)
        c1 = cl.add_claim(rd, "结论一", level="C0")
        c2 = cl.add_claim(rd, "结论二", level="C1")
        idx = cl.load_claims(rd)
        assert set(idx) == {c1["claim_id"], c2["claim_id"]}
        lines = open(os.path.join(rd, "claims", "claims.jsonl"), encoding="utf-8").read().strip().splitlines()
        assert len(lines) == 2
        assert [json.loads(l)["event"] for l in lines] == ["add", "add"]

    def test_evidence_autofill_from_results(self, tmp_path):
        rd = _mk_results(tmp_path)
        c = cl.add_claim(rd, "结论三", level="C0")
        ev = c["evidence"]
        assert ev["data"] and ev["data"][0]["digest"], ev
        assert ev["code"] and ev["logs"], ev
        assert ev["env"].get("conda") == "scanpy310"

    def test_manifest_gets_claims_block(self, tmp_path):
        rd = _mk_results(tmp_path)
        cl.add_claim(rd, "结论四", level="C0")
        man = json.load(open(os.path.join(rd, "analysis_manifest.json"), encoding="utf-8"))
        assert man["schema"] == "memomics.analysis_manifest.v1"     # v1 字段不动
        assert man["claim_count"] == 1 and man["claims"][0]["statement"] == "结论四"

    def test_status_and_agent_text(self, tmp_path):
        rd = _mk_results(tmp_path)
        c = cl.add_claim(rd, "结论五", level="C0")
        cl.set_status(rd, c["claim_id"], "needs_more_evidence")
        txt = cl.format_for_agent(rd, {"action": "list", "claims": cl.list_claims(rd)})
        assert "needs_more_evidence" in txt and "C0" in txt


class TestCostAndDebateChannel:
    """COST 账本 + 辩论引擎自动落参数通道（用户口径：辩论结论要能用于后面的分析）。"""

    def test_cost_from_token_usage(self, tmp_path):
        rd = _mk_results(tmp_path)
        with open(os.path.join(rd, "token_usage.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "2026-10-14T10:00:00",
                                "cumulative": {"input_tokens": 1000, "output_tokens": 200,
                                               "llm_ms": 60000, "api_calls": 3}}) + "\n")
            f.write(json.dumps({"ts": "2026-10-14T10:20:00",
                                "cumulative": {"input_tokens": 3000, "output_tokens": 500,
                                               "llm_ms": 120000, "api_calls": 7}}) + "\n")
        cost = cl.cost_from_session(rd)
        assert cost["tokens"] == 3500 and cost["api_calls"] == 7
        assert cost["wall_min"] == 20.0 and cost["turns"] == 2
        c = cl.add_claim(rd, "带成本结论", level="C0")
        assert c["cost"]["tokens"] == 3500, c["cost"]
        assert cl.ptr_report(rd)["cost"]["tokens"] == 3500

    def test_debate_engine_persists_channel(self, tmp_path):
        """debate_analysis._persist_decision_channel：辩论跑完自动把参数决策落通道。"""
        from memomics.bio_tools import debate_analysis as da
        rd = _mk_results(tmp_path)
        da.set_session_context(sid="zz", results_dir=rd, model_config={})
        result = {"topic": "阈值选择", "level": "L1", "verdict": "modify", "confidence": "medium",
                  "decision": "padj<0.05 + |log2FC|>1", "recommended_params": {"padj": 0.05, "lfc": 1.0},
                  "chain_verdicts": {"pro": "断链", "con": "部分", "decisive": "阈值敏感性缺证据"}}
        da._persist_decision_channel(result)
        assert result.get("params_channel") == "claims/params.json"
        assert result.get("params_channel_hint")
        pj = cl.read_params(rd)
        assert pj["params"]["padj"] == 0.05 and pj["params"]["lfc"] == 1.0
        da.set_session_context(sid="", results_dir="", model_config={})