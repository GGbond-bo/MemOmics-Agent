# -*- coding: utf-8 -*-
"""辩论引擎 + 门控核心回归测试网（阶段A，2026-08-11）

全部离线：不调用 LLM、不读写生产缓存（monkeypatch 隔离临时目录）。
锁死 2026-08-10 真实测试修复的 6 个 bug + 阶段 B/C 的目标接口。

回归目标：
- A1 指纹隔离：mode/rounds/分组配置/role_model_map 变化 → 缓存 key 必不同
- A2 角色解析：temperature 空 key、multi_model 不发 dcs-cloud/glm 给 deepseek、
  分组配置全 mode 生效、dcs-cloud 永不默认回退
- A3 judge JSON 解析：围栏/reasoning 草稿/verdict=null 片段/无 JSON
- A4 debate_gate 门控矩阵：级别默认/强制/预算护栏/topic 去重
- A5 回调链路：_pending_steer 注入、无 agent 不崩、参数键 code/command
- A6 裁决回流：error/low 跳过
- B  裁决一致性：矛盾组合检测 + 回流禁止
- C  成本治理：token 分级 + L1 采样架构 + level 进指纹
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from memomics.bio_tools import debate_analysis as da  # noqa: E402
import enforcement as enf  # noqa: E402  (webui 目录由 tests/conftest.py 加入 sys.path)


# ==================== 公共 fixture ====================

@pytest.fixture
def tmp_debates_dir(tmp_path, monkeypatch):
    """隔离缓存目录，测试不碰生产 _debates/"""
    d = tmp_path / "_debates"
    d.mkdir()
    monkeypatch.setattr(da, "_get_debates_dir", lambda: d)
    return d


@pytest.fixture
def cfg_base():
    return {"mode": "homogeneous", "rounds": 1, "role_model_map": None}


@pytest.fixture
def provider_keys(monkeypatch):
    """伪造 provider_keys：dcs-cloud(失效) + deepseek + opencode-go"""
    pk = {
        "dcs-cloud": {"api_key": "dead-key", "base_url": "https://dcs.example/v1"},
        "deepseek": {"api_key": "sk-ds", "base_url": "https://api.deepseek.com/v1"},
        "opencode-go": {"api_key": "sk-oc", "base_url": "https://oc.example/v1"},
    }
    monkeypatch.setattr(da, "_load_provider_keys", lambda: pk)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    return pk


@pytest.fixture(autouse=True)
def _isolate_machine_state(monkeypatch):
    """隔离开发机状态：辩论路由不得依赖本机 hermes_home/model_config.json。

    2026-09-13：_current_model_route() 会读「界面当前模型」文件，单元测试必须置空，
    否则开发机的当前模型（dcs-cloud/deepseek-flash）会串进断言。
    """
    monkeypatch.setattr(da, "_load_global_model_config", lambda: {})
    monkeypatch.setattr(da, "_model_cfg_cache", {"path": "", "mtime": -1.0, "data": {}})
    monkeypatch.setattr(da, "_provider_default_models", lambda: {})
    monkeypatch.setattr(da, "_prov_models_cache", {"mtime": -1.0, "data": {}})
    da.set_session_context("", "")
    yield
    da.set_session_context("", "")


# ==================== A1 指纹隔离 ====================

class TestFingerprint:
    def test_mode_difference(self, cfg_base):
        """不同 mode → 指纹不同（防架构串缓存）"""
        f1 = da._debate_fingerprint("homogeneous", 1, None, cfg_base)
        f2 = da._debate_fingerprint("adversarial", 1, None, cfg_base)
        f3 = da._debate_fingerprint("temperature", 1, None, cfg_base)
        assert len({f1, f2, f3}) == 3

    def test_rounds_difference(self, cfg_base):
        assert da._debate_fingerprint("homogeneous", 1, None, cfg_base) != \
               da._debate_fingerprint("homogeneous", 2, None, cfg_base)

    def test_group_config_in_fingerprint(self, cfg_base):
        """P0-5 回归：改 judge 模型（mode 不变）→ 指纹必变（否则命中坏旧缓存）"""
        cfg_a = dict(cfg_base, judge={"provider": "deepseek", "model": "deepseek-v4-flash"})
        cfg_b = dict(cfg_base, judge={"provider": "opencode-go", "model": "deepseek-v4-pro"})
        fa = da._debate_fingerprint("homogeneous", 1, None, cfg_a)
        fb = da._debate_fingerprint("homogeneous", 1, None, cfg_b)
        assert fa != fb

    def test_role_model_map_in_fingerprint(self, cfg_base):
        rmm = {"pro_biology": {"provider": "deepseek", "model": "m1"}}
        assert da._debate_fingerprint("homogeneous", 1, None, cfg_base) != \
               da._debate_fingerprint("homogeneous", 1, rmm, cfg_base)

    def test_topic_hash_with_fingerprint(self):
        """不同指纹 → 不同缓存 key；无指纹 → 旧行为"""
        h1 = da._topic_hash("t", "c", "mode=A")
        h2 = da._topic_hash("t", "c", "mode=B")
        h0 = da._topic_hash("t", "c")
        assert len({h1, h2, h0}) == 3

    def test_topic_hash_normalization(self):
        """大小写/首尾空白归一（新签名）"""
        assert da._topic_hash("Topic ", " ctx", "f") == da._topic_hash("topic", "ctx", "f")

    def test_level_in_fingerprint(self, cfg_base):
        """C3 回归：L1/L2 缓存必须隔离（否则脚本阶段 L1 结果污染结论阶段 L2）"""
        f_l2 = da._debate_fingerprint("homogeneous", 1, None, cfg_base, level="L2")
        f_l1 = da._debate_fingerprint("homogeneous", 1, None, cfg_base, level="L1")
        assert f_l2 != f_l1
        # 不传 level 时向后兼容（= 现状指纹）
        assert da._debate_fingerprint("homogeneous", 1, None, cfg_base) == f_l2


class TestCacheRoundtrip:
    def test_save_load_isolation(self, tmp_debates_dir):
        """同 topic 不同指纹：两条独立缓存，互不命中"""
        da._save_debate("t", "c", json.dumps({"verdict": "ok"}), fingerprint="mode=A")
        da._save_debate("t", "c", json.dumps({"verdict": "ok2"}), fingerprint="mode=B")
        ra = da._load_debate("t", "c", fingerprint="mode=A")
        rb = da._load_debate("t", "c", fingerprint="mode=B")
        assert ra["result"]["verdict"] == "ok"
        assert rb["result"]["verdict"] == "ok2"

    def test_failed_result_never_returned(self, tmp_debates_dir):
        """P0-1 回归：失败占位符不进缓存返回"""
        da._save_debate("t", "c", json.dumps({"error": True, "judge_verdict": "[judge 辩论生成失败]"}), fingerprint="f")
        assert da._load_debate("t", "c", fingerprint="f") is None

    def test_legacy_hash_read_compat(self, tmp_debates_dir):
        """2026-07 旧存档（legacy hash 无 strip）仍可读"""
        h_legacy = da._topic_hash_legacy("  T ", " C ")  # 旧算法不 strip
        rec = {"timestamp": "2099-01-01 00:00:00", "topic": "  T ", "context": " C ",
               "hash": h_legacy, "result": {"verdict": "ok", "confidence": "high"}}
        (tmp_debates_dir / f"{h_legacy}.json").write_text(json.dumps(rec), encoding="utf-8")
        loaded = da._load_debate("  T ", " C ", fingerprint="")  # 无指纹 → 走 legacy 回退
        assert loaded is not None and loaded["result"]["verdict"] == "ok"


# ==================== A2 角色解析 ====================

class TestRoleResolve:
    def test_temperature_mode_has_key(self, provider_keys):
        """P2-8 回归：temperature 模式无环境变量时 api_key 不得为空（原 8/8 全崩）"""
        cfg = {"mode": "temperature"}
        for label in ("pro_biology", "con_history", "judge"):
            rc = da._resolve_role_llm(label, cfg)
            assert rc["api_key"], f"{label} api_key 为空"
            assert rc["temperature"] in da._TEMP_POOL

    def test_multi_model_skips_dead_provider(self, provider_keys):
        """P2-9 回归：multi_model 哈希分配必须跳过失效 dcs-cloud"""
        cfg = {"mode": "multi_model"}
        for label in ("pro_biology", "pro_statistics", "con_biology", "judge"):
            rc = da._resolve_role_llm(label, cfg)
            assert rc["provider"] != "dcs-cloud"

    def test_multi_model_deepseek_default_model(self, provider_keys):
        """P2-10 回归：deepseek 官方不得发 glm 系列（400 Bad Request）"""
        cfg = {"mode": "multi_model"}
        for label in ("pro_biology", "pro_statistics", "pro_bioinfo",
                      "con_biology", "con_statistics", "con_bioinformatics",
                      "con_history", "judge"):
            rc = da._resolve_role_llm(label, cfg)
            if rc["provider"] == "deepseek":
                assert not rc["model"].startswith("glm"), f"{label} 发 glm 给 deepseek"

    def test_group_config_all_modes(self, provider_keys):
        """P0-4 回归：judge/pro/con 分组配置在 homogeneous 下也生效"""
        cfg = {"mode": "homogeneous",
               "judge": {"provider": "opencode-go", "model": "deepseek-v4-pro"}}
        rc = da._resolve_role_llm("judge", cfg)
        assert rc["provider"] == "opencode-go" and rc["model"] == "deepseek-v4-pro"
        # pro/con 不受 judge 分组影响
        rc2 = da._resolve_role_llm("pro_biology", cfg)
        assert rc2["model"] != "deepseek-v4-pro"

    def test_role_model_map_highest_priority(self, provider_keys):
        cfg = {"mode": "homogeneous",
               "judge": {"provider": "opencode-go", "model": "deepseek-v4-pro"},
               "role_model_map": {"judge": {"provider": "deepseek", "model": "deepseek-v4-flash"}}}
        rc = da._resolve_role_llm("judge", cfg)
        assert rc["provider"] == "deepseek" and rc["model"] == "deepseek-v4-flash"

    def test_default_fallback_skips_dead(self, provider_keys, monkeypatch):
        """无环境变量 → 回退 provider_keys，但跳过 dcs-cloud、优先 deepseek"""
        rc = da._default_role_llm("", "", "glm-5.2", provider_keys)
        assert rc["provider"] == "deepseek"
        assert rc["model"] == "deepseek-v4-flash"  # deepseek 官方默认模型

    def test_env_var_takes_precedence(self, provider_keys, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
        monkeypatch.setenv("DEEPSEEK_MODEL", "my-model")
        rc = da._default_role_llm(os.environ["DEEPSEEK_API_KEY"], "", "my-model", provider_keys)
        assert rc["provider"] == "env" and rc["model"] == "my-model"


# ==================== A3 judge JSON 解析 ====================

class TestJudgeParse:
    def test_plain_json(self):
        r = da._parse_judge_json('{"verdict": "ok", "confidence": "high"}')
        assert r["verdict"] == "ok" and r["confidence"] == "high"

    def test_fenced_json(self):
        r = da._parse_judge_json('```json\n{"verdict": "modify", "confidence": "medium"}\n```')
        assert r["verdict"] == "modify"

    def test_reasoning_draft_multi_fragments(self):
        """P0-3 回归：reasoning 草稿多片段，含 "verdict": null 的残缺片段 → 取非空片段"""
        text = ('Need final verdict... {"verdict": null, "confidence": "low"} '
                'then {"verdict": "modify", "confidence": "high", "recommended_params": {"a": 1}}')
        r = da._parse_judge_json(text)
        assert r["verdict"] == "modify" and r["recommended_params"] == {"a": 1}

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            da._parse_judge_json("完全没有 JSON 的裁决文本")

    def test_all_null_verdict_raises(self):
        with pytest.raises(ValueError):
            da._parse_judge_json('{"verdict": null} {"verdict": ""}')


# ==================== B 裁决一致性 ====================

class TestConsistency:
    def test_need_more_info_high_is_inconsistent(self):
        """实证 bug：3 条 need_more_info+high 矛盾裁决"""
        issues = da._check_consistency({"verdict": "need_more_info", "confidence": "high"})
        assert issues, "need_more_info+high 必须判为矛盾"

    def test_modify_without_params_is_inconsistent(self):
        issues = da._check_consistency({"verdict": "modify", "confidence": "high",
                                        "recommended_params": {}})
        assert issues

    def test_consistent_verdict_passes(self):
        assert da._check_consistency({"verdict": "ok", "confidence": "high"}) == []
        assert da._check_consistency({"verdict": "modify", "confidence": "medium",
                                      "recommended_params": {"res": 0.8}}) == []
        # v3(2026-09-22): need_more_info 必须能指出缺什么，否则就是用户吐槽的"垃圾结论"
        assert da._check_consistency({"verdict": "need_more_info", "confidence": "low",
                                      "missing": ["缺批次信息 → 查 GEO 元数据"]}) == []

    def test_need_more_info_without_missing_is_inconsistent(self):
        """v3: 说了证据不足却指不出缺什么 = 矛盾裁决（不得静默通过）"""
        issues = da._check_consistency({"verdict": "need_more_info", "confidence": "low"})
        assert issues, "need_more_info 但 missing 为空必须判为矛盾"
        assert any("missing" in i for i in issues)


# ==================== v3 裁决必须带"下一步"（2026-09-22） ====================

class TestDecisionBlock:
    """用户原话："辩论了一大堆，最终得出'证据不足，先补数据再下结论'这种垃圾的结论…
    辩论结果有用于下一步的进程吗？没有，辩论什么？"
    本组测试锁死：任何裁决都必须带 decision + next_actions + fallback。"""

    def test_both_sides_lack_evidence_still_yields_plan(self):
        """正反双方都没证据（need_more_info）也不能空手而归 —— 必须给方案 + 临时路径"""
        r = da._ensure_decision_block({"verdict": "need_more_info", "confidence": "low",
                                       "missing": ["缺批次校正参数", "缺对照样本"]})
        assert r["decision"].strip(), "decision 不能为空"
        assert "证据不足" not in r["decision"]
        assert len(r["next_actions"]) >= 1, "必须给出下一步动作"
        assert r["fallback"]["path"].strip(), "必须给出临时路径"
        assert r["fallback"]["label"], "临时结论必须带标注"
        assert r["reopen_condition"].strip()
        assert r["has_ai_action"] is True, "至少一条 ai 自己能执行的动作"

    def test_missing_items_become_actions(self):
        r = da._ensure_decision_block({"verdict": "need_more_info", "confidence": "low",
                                       "missing": ["缺批次信息"]})
        acts = [a["action"] for a in r["next_actions"]]
        assert any("缺批次信息" in a for a in acts), "每条 missing 应转成一条补齐动作"

    def test_judge_supplied_plan_is_kept(self):
        """judge 真给了方案就用它的，引擎不得覆盖"""
        r = da._ensure_decision_block({
            "verdict": "need_more_info", "confidence": "low",
            "decision": "先按 batch-corrected 矩阵出草图，结论标注低置信",
            "next_actions": [{"action": "跑 sva 批次校正", "owner": "ai", "expected": "校正后矩阵"}],
            "fallback": {"path": "先用原始矩阵 + 标注", "risk": "批次效应", "label": "临时"},
            "missing": ["校准数据"],
        })
        assert r["decision_source"] == "judge"
        assert r["decision"].startswith("先按 batch-corrected")
        assert len(r["next_actions"]) == 1
        assert r["fallback"]["path"] == "先用原始矩阵 + 标注"

    def test_user_only_actions_get_ai_action_appended(self):
        """judge 只给"等用户给数据" → 引擎补一条 ai 现在就能做的"""
        r = da._ensure_decision_block({
            "verdict": "need_more_info", "confidence": "low", "missing": ["用户提供原始数据"],
            "next_actions": [{"action": "请用户提供原始数据", "owner": "user"}],
        })
        assert r["has_ai_action"] is True
        assert any("user" in w for w in r.get("decision_warnings", []))

    def test_engine_backfill_is_disclosed(self):
        r = da._ensure_decision_block({"verdict": "support", "confidence": "medium",
                                       "next_actions": [], "missing": []})
        assert r["decision_source"] == "engine_backfill"
        assert r.get("decision_warnings"), "回填必须标注来源，不得假装是 judge 给的"

    def test_backfill_is_idempotent(self):
        """重复调用不得把引擎回填标成 judge 给的"""
        r = da._ensure_decision_block({"verdict": "need_more_info", "confidence": "low",
                                       "missing": ["x"]})
        r2 = da._ensure_decision_block(r)
        assert r2["decision_source"] == "engine_backfill"
        assert r2["decision"] == r["decision"]

    def test_plan_fields_parsed_from_broken_json(self):
        """网关把 JSON 弄残时，行动方案字段也要能兜底抽出来（否则又变成没有下一步）"""
        broken = ('{"verdict": "need_more_info", "confidence": "low", "decision": "先按 X 走", '
                  '"next_actions": [{"action": "查 GEO 元数据", "owner": "ai"}], '
                  '"fallback": {"path": "用原始矩阵", "risk": "批次效应", "label": "临时"}, '
                  '"missing": ["批次信息"]')
        o = da._parse_judge_json(broken)
        assert o["verdict"] == "need_more_info"
        assert o["decision"] == "先按 X 走"
        assert o["next_actions"][0]["action"] == "查 GEO 元数据"
        assert o["fallback"]["path"] == "用原始矩阵"
        assert o["missing"] == ["批次信息"]

    def test_copy_decision_fields_clears_stale_backfill_mark(self):
        r = {"decision_source": "engine_backfill", "decision_warnings": [da._DECISION_BACKFILL_NOTE]}
        da._copy_decision_fields(r, {"decision": "judge 的方案",
                                     "next_actions": [{"action": "a"}]})
        assert r["decision"] == "judge 的方案"
        assert "decision_source" not in r, "judge 给了方案就不该再标引擎回填"

    def test_inconsistent_result_never_reflows(self, monkeypatch):
        """B2 回归：矛盾裁决禁止进入 skill_evolution（垃圾不得入库）"""
        called = []
        monkeypatch.setattr(da, "_load_debate_config", lambda: {"reflow_skill": "x"})
        from memomics.bio_tools import skill_evolution as se
        monkeypatch.setattr(se, "skill_evolution",
                            lambda **kw: called.append(kw))
        da._reflow_verdict({"verdict": "need_more_info", "confidence": "high",
                            "topic": "t", "judge_verdict": "..."})
        assert not called, "矛盾裁决不得回流"


# ==================== A4 门控矩阵 ====================

def _mk_es(level="analysis", count=0, budget=3):
    es = enf.EnforcementState("test_sid")
    es.analysis_level = level
    es.debate_count = count
    es.debate_budget = budget
    return es


class TestDebateGate:
    def test_chat_skip(self):
        lvl, reasons, force = enf.debate_gate(_mk_es("chat"), "conclusion")
        assert lvl == enf.DEBATE_L0

    def test_statistical_default_l1(self):
        lvl, _, _ = enf.debate_gate(_mk_es("statistical"), "conclusion")
        assert lvl == enf.DEBATE_L1

    def test_analysis_conclusion_without_fork_is_l1(self):
        """P1(2026-09-22): 没分歧的结论不再无条件 L2（用户：不要为了辩论而辩论）"""
        lvl, reasons, _ = enf.debate_gate(_mk_es("analysis"), "conclusion")
        assert lvl == enf.DEBATE_L1
        assert any("没有分歧" in r for r in reasons)

    def test_conclusion_with_fork_is_l2(self):
        lvl, reasons, _ = enf.debate_gate(_mk_es("analysis"), "conclusion", {"has_fork": True})
        assert lvl == enf.DEBATE_L2

    def test_conclusion_with_two_options_is_l2(self):
        lvl, _, _ = enf.debate_gate(_mk_es("analysis"), "conclusion",
                                    {"fork_options": ["harmony", "scanorama"]})
        assert lvl == enf.DEBATE_L2

    # ---- P1 "值不值得辩"过滤 ----

    def test_single_option_skips_debate(self):
        """只有 1 条可选路径 → 辩不出新东西"""
        lvl, reasons, _ = enf.debate_gate(_mk_es("analysis"), "conclusion", {"n_options": 1})
        assert lvl == enf.DEBATE_L0
        assert any("可选路径" in r for r in reasons)

    def test_fact_lookup_skips_debate(self):
        lvl, _, _ = enf.debate_gate(_mk_es("analysis"), "before_script", {"fact_lookup": True})
        assert lvl == enf.DEBATE_L0

    def test_readonly_skips_debate(self):
        lvl, _, _ = enf.debate_gate(_mk_es("analysis"), "before_script", {"readonly": True})
        assert lvl == enf.DEBATE_L0

    def test_linear_command_skips_debate(self):
        lvl, reasons, _ = enf.debate_gate(_mk_es("analysis"), "before_script",
                                          {"cmd": "ls -lh /data/raw && md5sum x.h5ad"})
        assert lvl == enf.DEBATE_L0

    def test_linear_signal_skips_debate(self):
        lvl, _, _ = enf.debate_gate(_mk_es("analysis"), "before_script", {"linear": True})
        assert lvl == enf.DEBATE_L0

    def test_repeat_topic_skips_debate(self):
        lvl, _, _ = enf.debate_gate(_mk_es("analysis"), "conclusion", {"repeat_topic": True})
        assert lvl == enf.DEBATE_L0

    def test_no_debate_flag_wins(self):
        lvl, _, _ = enf.debate_gate(_mk_es("analysis"), "conclusion", {"no_debate": True})
        assert lvl == enf.DEBATE_L0

    def test_worthiness_never_blocks_hard_signals(self):
        """高影响/失败/冲突是硬信号：即使只有 1 条路径也必须辩（强制 L2）"""
        lvl, _, force = enf.debate_gate(_mk_es("analysis"), "conclusion",
                                        {"n_options": 1, "high_impact": True})
        assert lvl == enf.DEBATE_L2 and force is True
        lvl2, _, _ = enf.debate_gate(_mk_es("analysis"), "conclusion",
                                     {"linear": True, "failed_retries": 2})
        assert lvl2 == enf.DEBATE_L2

    def test_analysis_before_script_l1(self):
        lvl, _, _ = enf.debate_gate(_mk_es("analysis"), "before_script")
        assert lvl == enf.DEBATE_L1

    def test_failures_escalate_l2(self):
        lvl, reasons, _ = enf.debate_gate(_mk_es("analysis"), "before_script",
                                          {"failed_retries": 2})
        assert lvl == enf.DEBATE_L2

    def test_high_impact_force_l2_no_downgrade(self):
        """高影响：强制 L2，预算护栏不得降级"""
        lvl, _, force = enf.debate_gate(_mk_es("analysis", count=99, budget=3),
                                        "conclusion", {"high_impact": True})
        assert lvl == enf.DEBATE_L2 and force is True

    def test_budget_guard_downgrades(self):
        """预算护栏：超预算的非强制 L2（有分歧）→ 降 L1"""
        lvl, reasons, force = enf.debate_gate(_mk_es("analysis", count=3, budget=3),
                                              "conclusion", {"has_fork": True})
        assert lvl == enf.DEBATE_L1 and force is False
        assert any("预算" in r for r in reasons)


# ==================== P2: 裁决驱动下一步 ====================

def _verdict_json(**kw):
    v = {
        "verdict": "need_more_info", "confidence": "low", "level": "L2",
        "topic": "批次校正 vs 直接出差异",
        "decision": "先跑 sva 校正，再出差异结论；期间先出一版标注低置信的草图",
        "next_actions": [
            {"action": "跑 sva 批次校正", "owner": "ai", "expected": "校正后矩阵",
             "blocks": ["出最终差异结论", "结果入库"]},
            {"action": "请用户确认分组列", "owner": "user"},
            {"action": "对比校正前后 PC1 占比", "owner": "ai"},
        ],
        "fallback": {"path": "用原始矩阵出草图", "risk": "批次效应未去除", "label": "临时"},
        "reopen_condition": "拿到批次信息后重开",
        "decision_source": "judge",
    }
    v.update(kw)
    return json.dumps(v, ensure_ascii=False)


class TestDecisionDrivesNextStep:
    """P2(2026-09-22): 辩论结论必须进入下一步进程（待办 + 硬约束）。"""

    def test_actions_become_session_todos(self):
        es = _mk_es()
        enf._ingest_debate_plan(es, _verdict_json())
        assert es.debate_plan["decision"].startswith("先跑 sva")
        titles = [t["title"] for t in es.debate_todos]
        assert titles == ["跑 sva 批次校正", "对比校正前后 PC1 占比"], titles
        assert es.debate_plan["fallback"]["path"] == "用原始矩阵出草图"

    def test_user_owned_actions_are_not_todos(self):
        """要让用户提供的东西不算待办（那是提问，不是 AI 的下一步）"""
        es = _mk_es()
        enf._ingest_debate_plan(es, _verdict_json(next_actions=[
            {"action": "请用户提供原始数据", "owner": "user"},
            {"action": "先出一版草图", "owner": "ai"},
        ]))
        assert [t["title"] for t in es.debate_todos] == ["先出一版草图"]

    def test_blocking_todo_is_first(self):
        """硬约束待办排最前（先做挡住产物的那件事）"""
        es = _mk_es()
        enf._ingest_debate_plan(es, _verdict_json())
        assert es.debate_todos[0]["blocks"], "带 blocks 的待办必须排第一"

    def test_blocked_todo_blocks_high_impact_tool(self):
        es = _mk_es()
        enf._ingest_debate_plan(es, _verdict_json())
        blk = enf._debate_block_gate(es, "generate_report")
        assert blk and blk["blocked"] is True
        assert "跑 sva 批次校正" in blk["message"]
        assert blk["debate_blocks"]

    def test_no_block_when_verdict_has_no_blocks(self):
        es = _mk_es()
        enf._ingest_debate_plan(es, _verdict_json(next_actions=[
            {"action": "出草图", "owner": "ai"}]))
        assert enf._debate_block_gate(es, "generate_report") is None

    def test_config_can_disable_blocking(self):
        es = _mk_es()
        enf._ingest_debate_plan(es, _verdict_json())
        es.debate_enforce_blocks = False
        assert enf._debate_block_gate(es, "generate_report") is None

    def test_completed_todo_releases_block(self):
        es = _mk_es()
        enf._ingest_debate_plan(es, _verdict_json())
        _id = es.debate_todos[0]["id"]
        assert enf.sync_debate_todos(es, [{"id": _id, "status": "completed"}]) == 1
        assert enf.pending_debate_blocks(es) == []
        assert enf._debate_block_gate(es, "generate_report") is None

    def test_cancelled_todo_releases_block(self):
        es = _mk_es()
        enf._ingest_debate_plan(es, _verdict_json())
        enf.sync_debate_todos(es, [{"title": es.debate_todos[0]["title"], "status": "cancelled"}])
        assert enf._debate_block_gate(es, "generate_report") is None

    def test_plan_surfaces_in_state(self):
        es = _mk_es()
        enf._ingest_debate_plan(es, _verdict_json())
        d = es.to_dict()
        assert d["debate_decision"].startswith("先跑 sva")
        assert d["debate_blocks_pending"] == 1
        assert len(d["debate_todos"]) == 2

    def test_broken_payload_does_not_crash(self):
        es = _mk_es()
        assert enf._ingest_debate_plan(es, "not json") == {}
        assert enf._ingest_debate_plan(es, json.dumps({"verdict": "support"}))["decision"] == ""


# ==================== A5 回调链路 ====================

class FakeAgent:
    def __init__(self):
        import threading
        self._pending_steer = None
        self._pending_steer_lock = threading.Lock()


class TestCallbacks:
    def _mk(self, tmp_path, agent=None):
        emitted = []
        cbs = enf.create_enforcement_callbacks(
            {"id": "cb_test", "results_dir": str(tmp_path)},
            lambda s, m: emitted.append(m),
            agent_ref=[agent] if agent else None)
        es = enf.get_enforcement("cb_test")
        es.analysis_level = "analysis"
        return cbs, es, emitted

    def _reqs(self, emitted):
        return [m for m in emitted if m.get("action") == "require"
                and "debate_analysis" in (m.get("require") or [])]

    def test_before_script_gate_and_hint_inject(self, tmp_path):
        """缺口①②回归：execute_r 首次执行 → L1 require + _pending_steer 注入"""
        agent = FakeAgent()
        cbs, es, emitted = self._mk(tmp_path, agent)
        cbs["tool_start_callback"]("c1", "execute_r", {"code": "FindClusters(res=0.5)"})
        reqs = self._reqs(emitted)
        assert reqs and reqs[-1]["level"] == "L1-轻量辩论"
        assert agent._pending_steer and "系统强制提示" in agent._pending_steer

    def test_same_command_no_repeat(self, tmp_path):
        agent = FakeAgent()
        cbs, es, emitted = self._mk(tmp_path, agent)
        cbs["tool_start_callback"]("c1", "execute_r", {"code": "same_cmd"})
        n = len(self._reqs(emitted))
        cbs["tool_start_callback"]("c2", "execute_r", {"code": "same_cmd"})
        assert len(self._reqs(emitted)) == n

    def test_param_key_code_command(self, tmp_path):
        """P2 回归：参数键兼容 code（execute_r）与 command（terminal）"""
        agent = FakeAgent()
        cbs, es, emitted = self._mk(tmp_path, agent)
        cbs["tool_start_callback"]("c1", "execute_python", {"code": "scanpy.leiden()"})
        assert self._reqs(emitted), "execute_python 的 code 参数必须被识别"

    def test_no_agent_ref_no_crash(self, tmp_path):
        cbs, es, emitted = self._mk(tmp_path, agent=None)
        cbs["tool_complete_callback"]("r1", "rail_review", {"phase": "post"},
                                      json.dumps({"phase": "post", "passed": True}))
        assert es.rail_post_done

    def test_debate_tool_records_topic(self, tmp_path):
        cbs, es, emitted = self._mk(tmp_path)
        args = json.dumps({"topic": "分辨率选择", "context": "x"})
        cbs["tool_start_callback"]("c1", "debate_analysis", args)
        cbs["tool_complete_callback"]("c1", "debate_analysis", args,
                                      json.dumps({"verdict": "ok"}))
        assert "分辨率选择" in es.debated_topics and es.debate_count == 1


# ==================== C 成本治理 ====================

class TestCostGovernance:
    def test_token_budget_fields(self):
        """C3 回归：EnforcementState 有 token 预算字段"""
        es = enf.EnforcementState("t")
        assert hasattr(es, "token_used") and hasattr(es, "token_budget")

    def test_l1_sampling_mode_config(self):
        """C2 回归：L1 采样架构 = 单模型 3 温度采样（默认模型上下文切断不变）"""
        cfg = da._load_debate_config()
        l1 = cfg.get("l1", {})
        assert l1.get("samples", 3) == 3
        assert l1.get("strategy") == "sampling"

    def test_level_param_accepted(self):
        """C2 回归：debate_analysis 接受 level 参数（签名级验证，不调 LLM）"""
        import inspect
        sig = inspect.signature(da.debate_analysis)
        assert "level" in sig.parameters
