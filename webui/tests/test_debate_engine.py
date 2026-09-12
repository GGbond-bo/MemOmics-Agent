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
        assert da._check_consistency({"verdict": "need_more_info", "confidence": "low"}) == []

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

    def test_analysis_conclusion_default_l2(self):
        lvl, _, _ = enf.debate_gate(_mk_es("analysis"), "conclusion")
        assert lvl == enf.DEBATE_L2

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
        """预算护栏：超预算非强制 L2 → 降 L1"""
        lvl, reasons, force = enf.debate_gate(_mk_es("analysis", count=3, budget=3), "conclusion")
        assert lvl == enf.DEBATE_L1 and force is False
        assert any("预算" in r for r in reasons)


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
