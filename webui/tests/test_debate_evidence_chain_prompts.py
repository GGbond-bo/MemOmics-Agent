# -*- coding: utf-8 -*-
"""辩论提示词的「证据链」改造回归（2026-10-12）。

用户口径：辩论 = 从不同方向找证据链，不是观点对抗。
  · 知识库已验知识（L0 无来源 / L1 有来源未验证 / L2 湿实验 / L3 临床级，对齐 kb-evidence-v1）
  · 统计线：统计方法与过程有没有问题
  · 生信线：步骤与方法有没有错误（上游 QC / 比对定量 / 注释版本 / 工具参数 / 可复现性）

并锁死裁判路由换快模型（dcs-cloud/deepseek-flash：实测 ~1.6s vs 原 opencode-go/v4-pro ~5.0s 起步）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from memomics.bio_tools import debate_analysis as da  # noqa: E402


def _role_prompt(label="pro_bioinformatics"):
    return da._v2_role_prompt(label, "snRNA-seq 批次校正后 DEG 数量远超预期",
                              "上下文：DEG 表 n=1246", "KB 条目：L2 湿实验验证", "", "")


class TestEvidenceChainContract:
    def test_contract_has_chain_and_levels(self):
        p = _role_prompt()
        for token in ("证据契约 v3", "证据链", "结论 → 证据节点 → 反证/失效条件",
                      "L0", "L1", "L2", "L3", "kb-evidence-v1"):
            assert token in p, token

    def test_contract_has_three_lineages(self):
        p = _role_prompt()
        for token in ("知识库线", "统计线", "生信线", "比对与定量", "可复现性"):
            assert token in p, token

    def test_output_spec_requires_chains(self):
        p = _role_prompt()
        for token in ("evidence_chain", "lineage_audit", "counter", "step",
                      "self_audit_failures", "alternative_hypothesis", "needed_evidence"):
            assert token in p, token

    def test_judge_scores_by_chain_not_tone(self):
        j = da._v2_judge_prompt("topic", "ctx", "正方论证", "反方论证", "", "", digest="")
        for token in ("按证据链判", "chain_verdicts", "断链", "missing"):
            assert token in j, token

    def test_l1_and_l2_share_the_same_contract(self):
        """L1 走的是同一套 v2 模板（_debate_l1_lightweight 用 pro_biology/con_biology + judge）。"""
        assert "证据契约 v3" in da._EVIDENCE_CONTRACT
        assert "证据契约 v3" in _role_prompt("pro_biology")

    def test_v2_prompts_are_default(self, monkeypatch):
        monkeypatch.delenv("MEMOMICS_DEBATE_LEGACY_PROMPTS", raising=False)
        assert da._use_v2_prompts({}) is True


class TestJudgeRouteIsFast:
    def test_no_slow_judge_pin(self):
        """用户 2026-10-12 要求「裁判换快路由」。

        钉两件事（可移植，不依赖某一台机器的 config）：
          ① 引擎默认 cfg 不硬编码 judge（留空 → 走当前使用模型的提供商，本身就是快路由）；
          ② 本机若显式配了 judge，不许 pin 回慢的 pro 路由（opencode-go/deepseek-v4-pro：
             实测最小延迟 5.0s/次，且曾 ReadTimeout 到 3×120s）。
        """
        cfg = da._load_debate_config()
        judge = cfg.get("judge") or {}
        if judge:
            assert "opencode-go" not in str(judge.get("provider", "")), judge
            assert "v4-pro" not in str(judge.get("model", "")), judge

    def test_l1_budget_is_capped_below_l2(self):
        """L1 限时（用户：统计线最多 L1，且不要拖延时间）——但也要够跑完整场：
        实测 L1 整场 200-300s，180s 会把裁判掐死（judge_error → 引擎兜底 = 白跑）。"""
        assert da._L1_BUDGET_DEFAULT < da._DEBATE_BUDGET_DEFAULT
        assert da._L1_BUDGET_DEFAULT <= 420


class TestChainFieldsSurvive:
    def test_judge_chain_verdicts_are_carried_into_result(self):
        """冒烟实测裁判会输出 chain_verdicts（哪一方断链、断在哪一步）——
        这类字段必须被带回结果，否则用户只能在原始 JSON 里翻。"""
        dst = {"verdict": "need_more_info"}
        da._copy_decision_fields(dst, {
            "verdict": "need_more_info",
            "decision": "先算 FDR 前后比例", "next_actions": [{"action": "x", "owner": "ai"}],
            "chain_verdicts": {"pro": "断链（断点：无数据锚点）", "con": "部分", "decisive": "双方都缺锚点"},
        })
        assert dst.get("chain_verdicts", {}).get("pro", "").startswith("断链")
        assert dst.get("decision") == "先算 FDR 前后比例"

    def test_parse_fallback_keeps_chain_verdicts(self):
        """残缺 JSON（content 里只有思考链）也要能抓到 chain_verdicts。"""
        txt = ('思考：… {"verdict": "need_more_info", "confidence": "low", '
               '"chain_verdicts": {"pro": "断链", "con": "断链"}, "decision": "先补数据"}')
        obj = da._parse_judge_json(txt)
        assert obj.get("chain_verdicts") == {"pro": "断链", "con": "断链"}, obj