# -*- coding: utf-8 -*-
"""辩论引擎极端/边界测试网（2026-08-27 补充） — 全部离线，不调用 LLM。

覆盖现有 test_debate_engine.py 未覆盖的边界：
- E1 输入极端：空 topic/context、超大 context、Unicode/控制字符、rounds/level 非法值
- E2 缓存极端：TTL 边界、损坏 JSON、指纹确定性/灵敏度
- E3 角色解析极端：provider 缺失/未知 role/多模型稳定性/无 key 回退
- E4 judge JSON 解析极端：嵌套参数、多个 JSON、破损片段、超长文本
- E5 一致性边界：大小写、None 参数、分数全零
- E6 L1 轻量流：采样数钳制、全失败回退、judge 失败降级、一致性不入缓存
- E7 L2 全流程（mock）：部分失败不缓存、成功结构化、空输入、非法 mode
- E8 门控极端：全矩阵、token 预算护栏、force 不可降级、budget=0
- E9 回调/回流极端：token_used 回收、topic 去重、low/error 不回流
"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from memomics.bio_tools import debate_analysis as da  # noqa: E402
import enforcement as enf  # noqa: E402


# ==================== fixtures ====================

@pytest.fixture
def tmp_debates_dir(tmp_path, monkeypatch):
    d = tmp_path / "_debates"
    d.mkdir()
    monkeypatch.setattr(da, "_get_debates_dir", lambda: d)
    return d


@pytest.fixture
def provider_keys(monkeypatch):
    pk = {
        "dcs-cloud": {"api_key": "dead-key", "base_url": "https://dcs.example/v1"},
        "deepseek": {"api_key": "sk-ds", "base_url": "https://api.deepseek.com/v1"},
        "opencode-go": {"api_key": "sk-oc", "base_url": "https://oc.example/v1"},
    }
    monkeypatch.setattr(da, "_load_provider_keys", lambda: pk)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    return pk


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.setattr(da, "_load_provider_keys", lambda: {})
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    return {}


def _role_reply(label, content=None):
    """构造 8 角色 mock 回复。"""
    content = content or f"[{label} 论点]"
    return {
        "content": content,
        "call_id": f"{label}_mock",
        "isolation_verified": True,
        "messages_count": 1,
        "error": False,
    }


def _patch_call_role(monkeypatch, fail_labels=(), judge_content=None):
    """monkeypatch _call_llm_role：按 label 返回，可注入失败/自定义裁判文本。"""
    calls = []
    def fake(label, prompt, cfg, temperature=None):
        calls.append((label, prompt, cfg))
        if label in fail_labels:
            return {**_role_reply(label), "error": True,
                    "content": f"[{label} 辩论生成失败]"}
        if label == "judge":
            return _role_reply(label, judge_content or '{"verdict":"ok","confidence":"high","recommended_params":{},"scores":{"pro_biology":7}}')
        return _role_reply(label)
    monkeypatch.setattr(da, "_call_llm_role", fake)
    return calls


def _patch_call_sync(monkeypatch, fail_labels=(), judge_content=None):
    """monkeypatch _call_llm_sync：供 L1 采样流使用。"""
    calls = []
    def fake(prompt, label, api_key, base_url, model, temperature=0.7, max_tokens=1024):
        calls.append({"label": label, "prompt": prompt, "temp": temperature,
                      "model": model, "tokens": max_tokens})
        if label in fail_labels:
            return {**_role_reply(label), "error": True,
                    "content": f"[{label} 辩论生成失败]"}
        if label == "l1_judge":
            return _role_reply(label, judge_content or '{"verdict":"ok","confidence":"high","recommended_params":{}}')
        return _role_reply(label, f"内容-{label}")
    monkeypatch.setattr(da, "_call_llm_sync", fake)
    return calls


def _mk_cfg(**kw):
    cfg = {"mode": "homogeneous", "rounds": 1, "judge": {}, "pro": {}, "con": {},
           "role_model_map": {}, "l1": {"samples": 3, "strategy": "sampling"},
           "token_budget": 0}
    cfg.update(kw)
    return cfg


# ==================== E1 输入极端 ====================

class TestInputExtreme:
    def test_empty_topic_context_hash(self):
        h = da._topic_hash("", "", "f")
        assert da._topic_hash("", "", "f") == h

    def test_whitespace_only_topic(self):
        assert da._topic_hash("   ", " c ", "f") == da._topic_hash("", "c", "f")

    def test_unicode_and_control_chars(self):
        t = "聚类分辨率\u0000\u001b[31m0.8\u001b[0m \U0001F9EC vs 1.0"
        c = "上下文\u0000\u0001\u001f\n\t\r\n"
        h1 = da._topic_hash(t, c, "f")
        assert h1 == da._topic_hash(t, c, "f")
        assert da._topic_hash(t, c, "g") != h1

    def test_large_context_hash_stable(self):
        big = "细胞数: 12345\n" + ("A" * 500_000)
        h = da._topic_hash("t", big, "f")
        assert h == da._topic_hash("t", big, "f")

    def test_rounds_clamped_to_one_offline(self, monkeypatch, tmp_debates_dir):
        """rounds=0 应钳制为 1 轮（8 次角色调用），不触网。"""
        monkeypatch.setattr(da, "_load_debate_config", lambda: _mk_cfg())
        monkeypatch.setattr(da, "_load_provider_keys", lambda: {"deepseek": {"api_key": "k", "base_url": "https://x/v1"}})
        calls = _patch_call_role(monkeypatch)
        da.debate_analysis("t", "c", rounds=0, auto_kb=False)
        assert len(calls) == 8

    def test_level_invalid_falls_back_l2(self, monkeypatch, tmp_debates_dir, no_keys):
        # 确保无 key -> fallback，不触网
        monkeypatch.setattr(da, "_load_debate_config", lambda: _mk_cfg())
        out = da.debate_analysis("t", "c", level="L3")
        obj = json.loads(out)
        assert "fallback" in obj.get("debate_format", "")

    def test_mode_invalid_treated_as_default(self, provider_keys):
        # 非法 mode 不应崩溃：_resolve_role_llm 走到默认分支
        for label in ("pro_biology", "con_history", "judge"):
            rc = da._resolve_role_llm(label, _mk_cfg(mode="bogus"))
            assert rc["api_key"]  # 有可用 key（provider 回退生效）


# ==================== E2 缓存极端 ====================

class TestCacheExtreme:
    def test_fingerprint_deterministic(self):
        cfg = {"mode": "adversarial", "judge": {"provider": "opencode-go", "model": "m1"},
               "pro": {"provider": "deepseek", "model": "m2"}, "con": {"provider": "opencode-go", "model": "m3"}}
        f1 = da._debate_fingerprint("adversarial", 2, {"judge": {"provider": "a", "model": "b"}}, cfg, level="L1")
        f2 = da._debate_fingerprint("adversarial", 2, {"judge": {"provider": "a", "model": "b"}}, cfg, level="L1")
        assert f1 == f2

    def test_fingerprint_sensitive_to_case(self):
        cfg = {"judge": {"provider": "opencode-go", "model": "M1"}}
        assert da._debate_fingerprint("homogeneous", 1, {}, cfg) !=                da._debate_fingerprint("homogeneous", 1, {}, {"judge": {"provider": "opencode-go", "model": "m1"}})

    def test_ttl_boundary(self, tmp_debates_dir):
        rec = {"timestamp": "2099-01-01 00:00:00", "result": {"verdict": "ok"}}
        h = da._topic_hash("t", "c", "f")
        (tmp_debates_dir / f"{h}.json").write_text(json.dumps(rec), encoding="utf-8")
        # 未来时间 → age 为负，不超 TTL → 命中
        assert da._load_debate("t", "c", max_age_hours=72, fingerprint="f") is not None

    def test_ttl_expired(self, tmp_debates_dir):
        past = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 200 * 3600))
        rec = {"timestamp": past, "result": {"verdict": "ok"}}
        h = da._topic_hash("t", "c", "f")
        (tmp_debates_dir / f"{h}.json").write_text(json.dumps(rec), encoding="utf-8")
        assert da._load_debate("t", "c", max_age_hours=72, fingerprint="f") is None

    def test_corrupt_cache_file_tolerated(self, tmp_debates_dir):
        h = da._topic_hash("t", "c", "f")
        (tmp_debates_dir / f"{h}.json").write_text("{not json!!!", encoding="utf-8")
        assert da._load_debate("t", "c", fingerprint="f") is None

    def test_save_never_overwrites_on_bad_result(self, tmp_debates_dir):
        # 保存失败结果后再保存正常结果，正常结果应可读
        da._save_debate("t", "c", json.dumps({"error": True}), fingerprint="f")
        da._save_debate("t", "c", json.dumps({"verdict": "ok"}), fingerprint="f")
        assert da._load_debate("t", "c", fingerprint="f")["result"]["verdict"] == "ok"


# ==================== E3 角色解析极端 ====================

class TestRoleResolveExtreme:
    def test_no_keys_anywhere(self, no_keys):
        for label in ("pro_biology", "judge"):
            rc = da._resolve_role_llm(label, _mk_cfg())
            assert not rc["api_key"]  # 空 key → debate_analysis 会走 fallback

    def test_debate_analysis_no_key_returns_fallback(self, monkeypatch, tmp_debates_dir, no_keys):
        monkeypatch.setattr(da, "_load_debate_config", lambda: _mk_cfg())
        out = da.debate_analysis("t", "c")
        obj = json.loads(out)
        assert "fallback" in obj.get("debate_format", "")
        assert obj["debate_instructions"]

    def test_unknown_role_uses_default(self, provider_keys):
        rc = da._resolve_role_llm("unknown_role", _mk_cfg())
        assert rc["api_key"] == "sk-ds"  # deepseek 优先

    def test_role_model_map_unknown_provider_falls_back(self, provider_keys):
        cfg = _mk_cfg(role_model_map={"judge": {"provider": "nope", "model": "x"}})
        rc = da._resolve_role_llm("judge", cfg)
        assert rc["api_key"] in ("sk-ds", "sk-oc")

    def test_group_model_without_provider_uses_env(self, provider_keys, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
        monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://env.example/v1")
        cfg = _mk_cfg(judge={"provider": "", "model": "glm-5.2"})
        rc = da._resolve_role_llm("judge", cfg)
        assert rc["provider"] == "env" and rc["model"] == "glm-5.2"

    def test_multi_model_stable_assignment(self, provider_keys):
        cfgs = [_mk_cfg(mode="multi_model"), _mk_cfg(mode="multi_model")]
        r1 = da._resolve_role_llm("pro_biology", cfgs[0])
        r2 = da._resolve_role_llm("pro_biology", cfgs[1])
        assert r1["provider"] == r2["provider"] and r1["model"] == r2["model"]

    def test_multi_model_only_dead_provider_falls_back(self, monkeypatch):
        monkeypatch.setattr(da, "_load_provider_keys", lambda: {"dcs-cloud": {"api_key": "x", "base_url": "https://x/v1"}})
        rc = da._resolve_role_llm("con_history", _mk_cfg(mode="multi_model"))
        assert rc["provider"] != "dcs-cloud"

    def test_temperature_stable_and_in_pool(self, provider_keys):
        r1 = da._resolve_role_llm("judge", _mk_cfg(mode="temperature"))
        r2 = da._resolve_role_llm("judge", _mk_cfg(mode="temperature"))
        assert r1["temperature"] == r2["temperature"]
        assert r1["temperature"] in da._TEMP_POOL


# ==================== E4 judge JSON 解析极端 ====================

class TestJudgeParseExtreme:
    def test_nested_recommended_params_with_braces(self):
        text = '{"verdict":"modify","scores":{"a":1},"recommended_params":{"a":{"b":{"c":[1,2]}}},"note":"}"}'
        r = da._parse_judge_json(text)
        assert r["verdict"] == "modify"
        assert r["recommended_params"]["a"]["b"]["c"] == [1, 2]

    def test_multiple_objects_picks_first_valid(self):
        text = '{"verdict":null} {"verdict":"modify","confidence":"high"}{"verdict":"need_more_info"}'
        r = da._parse_judge_json(text)
        assert r["verdict"] == "modify"

    def test_case_insensitive_regex_fallback(self):
        # 注意：verdict 正则区分大小写，confidence 正则不区分（当前实现）
        text = '一些前置文字 "verdict": "MODIFY", "Confidence": "HIGH" 后续'
        r = da._parse_judge_json(text)
        assert r["verdict"] == "modify" and r["confidence"] == "high"

    def test_uppercase_verdict_accepts_via_object_parse_only(self):
        # v2: verdict 归一化为小写合法枚举（再往下游只认 support/modify/need_more_info/ok）
        r = da._parse_judge_json('{"verdict": "MODIFY", "confidence": "HIGH"}')
        assert r["verdict"] == "modify" and r["confidence"] == "HIGH"

    def test_accepts_ok_verdict(self):
        assert da._parse_judge_json('{"verdict":"ok"}')["verdict"] == "ok"

    def test_huge_text_with_json(self):
        text = "前" * 20000 + '{"verdict":"support","confidence":"medium"}' + "后" * 20000
        r = da._parse_judge_json(text)
        assert r["verdict"] == "support"

    def test_braces_in_strings_not_parsed_wrongly(self):
        text = '{"reasoning":"包含 } 但正确转义\\"}","verdict":"support"}'
        r = da._parse_judge_json(text)
        assert r["verdict"] == "support"

    def test_no_valid_verdict_raises(self):
        with pytest.raises(ValueError):
            da._parse_judge_json('{"verdict": ""} {"confidence":"high"}')

    def test_non_string_verdict_rejected(self):
        # v2 加固：verdict 必须为合法枚举字符串，数字 1 不再被当作有效裁决
        with pytest.raises(ValueError):
            da._parse_judge_json('{"verdict": 1}')


# ==================== E5 一致性边界 ====================

class TestConsistencyExtreme:
    def test_case_insensitive_verdict_confidence(self):
        issues = da._check_consistency({"verdict": "Need_More_Info", "confidence": "HIGH"})
        assert issues

    def test_modify_none_params_inconsistent(self):
        issues = da._check_consistency({"verdict": "modify", "confidence": "medium",
                                        "recommended_params": None})
        assert issues

    def test_scores_all_zero_low_ok(self):
        assert da._check_consistency({"verdict": "support", "confidence": "low",
                                      "scores": {"a": 0, "b": 0}}) == []

    def test_scores_all_zero_high_inconsistent(self):
        assert da._check_consistency({"verdict": "support", "confidence": "high",
                                      "scores": {"a": 0, "b": 0}})

    def test_scores_none_ok(self):
        assert da._check_consistency({"verdict": "support", "confidence": "high",
                                      "scores": None}) == []

    def test_unknown_verdict_passes(self):
        # 只对已知组合做矛盾判定，未知 verdict 不误杀
        assert da._check_consistency({"verdict": "banana", "confidence": "high"}) == []


# ==================== E6 L1 轻量流 ====================

class TestL1Lightweight:
    def _run(self, monkeypatch, tmp_debates_dir, cfg=None, **llm_kw):
        monkeypatch.setattr(da, "_load_debate_config", lambda: cfg or _mk_cfg())
        monkeypatch.setattr(da, "_load_provider_keys", lambda: {"deepseek": {"api_key": "k", "base_url": "https://x/v1"}})
        monkeypatch.setattr(da, "_reflow_verdict", lambda r: None)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
        monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
        calls = _patch_call_sync(monkeypatch, **llm_kw)
        out = da._debate_l1_lightweight("t", "c", "kb", cfg or _mk_cfg(), "finger")
        return out, calls

    def test_samples_clamp_high_to_5(self, monkeypatch, tmp_debates_dir):
        out, calls = self._run(monkeypatch, tmp_debates_dir, cfg=_mk_cfg(l1={"samples": 99}))
        pro = [c for c in calls if c["label"].startswith("l1_pro")]
        assert len(pro) == 5
        obj = json.loads(out)
        assert obj["level"] == "L1"

    def test_samples_clamp_low_to_1(self, monkeypatch, tmp_debates_dir):
        out, calls = self._run(monkeypatch, tmp_debates_dir, cfg=_mk_cfg(l1={"samples": 0}))
        assert len([c for c in calls if c["label"].startswith("l1_pro")]) == 1

    def test_all_samples_fail_falls_back(self, monkeypatch, tmp_debates_dir):
        out, calls = self._run(monkeypatch, tmp_debates_dir,
                               fail_labels={"l1_pro_0", "l1_con_0", "l1_pro_1", "l1_con_1",
                                            "l1_pro_2", "l1_con_2"})
        obj = json.loads(out)
        assert "fallback" in obj.get("debate_format", "")

    def test_judge_failure_degrades_to_low_and_marks_error(self, monkeypatch, tmp_debates_dir):
        out, calls = self._run(monkeypatch, tmp_debates_dir,
                               fail_labels={"l1_judge"})
        obj = json.loads(out)
        assert obj["verdict"] == "need_more_info"
        assert obj["confidence"] == "low"
        # v2 加固：judge 失败有显式标记，下游可区分“信息不足”和“裁判故障”
        assert obj.get("judge_error") is True

    def test_judge_parse_failure_records_error(self, monkeypatch, tmp_debates_dir):
        out, calls = self._run(monkeypatch, tmp_debates_dir,
                               judge_content="完全不是 JSON")
        obj = json.loads(out)
        assert "verdict_parse_error" in obj
        assert obj["verdict"] == "need_more_info" and obj["confidence"] == "low"

    def test_inconsistent_l1_downgrades_and_no_cache(self, monkeypatch, tmp_debates_dir):
        out, calls = self._run(monkeypatch, tmp_debates_dir,
                               judge_content='{"verdict":"need_more_info","confidence":"high"}')
        obj = json.loads(out)
        assert obj["confidence"] == "low"
        assert "consistency_issues" in obj
        h = da._topic_hash("t", "c", "finger")
        assert not (tmp_debates_dir / f"{h}.json").exists()

    def test_successful_l1_is_cached(self, monkeypatch, tmp_debates_dir):
        out, calls = self._run(monkeypatch, tmp_debates_dir,
                               judge_content='{"verdict":"ok","confidence":"medium"}')
        obj = json.loads(out)
        assert obj["verdict"] == "ok"
        h = da._topic_hash("t", "c", "finger")
        assert (tmp_debates_dir / f"{h}.json").exists()


# ==================== E7 L2 全流程（mock） ====================

class TestL2FlowOffline:
    def _run(self, monkeypatch, tmp_debates_dir, topic="t", context="c", **kw):
        monkeypatch.setattr(da, "_load_debate_config", lambda: _mk_cfg())
        monkeypatch.setattr(da, "_load_provider_keys", lambda: {"deepseek": {"api_key": "k", "base_url": "https://x/v1"}})
        monkeypatch.setattr(da, "_reflow_verdict", lambda r: None)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
        monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
        calls = _patch_call_role(monkeypatch, **kw)
        out = da.debate_analysis(topic, context, auto_kb=False)
        return out, calls

    def test_success_result_structured_and_cached(self, monkeypatch, tmp_debates_dir):
        out, calls = self._run(monkeypatch, tmp_debates_dir,
                               judge_content='{"verdict":"modify","confidence":"medium","recommended_params":{"res":0.8},"scores":{"pro_biology":5}}')
        obj = json.loads(out)
        assert obj["verdict"] == "modify"
        assert obj["recommended_params"] == {"res": 0.8}
        assert obj["isolation_verification"]["pro_isolated"]
        assert obj["isolation_verification"]["judge_sees_all"]
        assert len(calls) == 8
        # 缓存 key = fingerprint 版本
        fp = obj["debate_config"]["fingerprint"]
        assert (tmp_debates_dir / f"{da._topic_hash('t', 'c', fp)}.json").exists()

    def test_partial_role_failure_returns_error_no_cache(self, monkeypatch, tmp_debates_dir):
        out, calls = self._run(monkeypatch, tmp_debates_dir,
                               fail_labels={"con_biology"})
        obj = json.loads(out)
        assert obj.get("error") is True
        assert obj["failed_roles"] == 1

    def test_empty_inputs_still_run(self, monkeypatch, tmp_debates_dir):
        out, calls = self._run(monkeypatch, tmp_debates_dir, topic="", context="")
        obj = json.loads(out)
        assert obj["topic"] == ""
        assert len(calls) == 8

    def test_rounds_loop_count(self, monkeypatch, tmp_debates_dir):
        monkeypatch.setattr(da, "_load_debate_config", lambda: _mk_cfg(rounds=3))
        monkeypatch.setattr(da, "_load_provider_keys", lambda: {"deepseek": {"api_key": "k", "base_url": "https://x/v1"}})
        calls = _patch_call_role(monkeypatch)
        da.debate_analysis("t", "c", auto_kb=False)
        assert len(calls) == 24  # 3 轮 × 8 角色

    def test_rounds_upper_cap_applied(self, monkeypatch, tmp_debates_dir):
        # v2 加固：rounds 受 rounds_max(默认5) 上限保护；请求 99 轮只跑 5 轮
        monkeypatch.setattr(da, "_load_debate_config", lambda: _mk_cfg(rounds=99))
        monkeypatch.setattr(da, "_load_provider_keys", lambda: {"deepseek": {"api_key": "k", "base_url": "https://x/v1"}})
        calls = _patch_call_role(monkeypatch)
        da.debate_analysis("t", "c", auto_kb=False)
        assert len(calls) == 5 * 8


# ==================== E8 门控极端 ====================

def _mk_es(level="analysis", count=0, budget=3, token_used=0, token_budget=0):
    es = enf.EnforcementState("ext_sid")
    es.analysis_level = level
    es.debate_count = count
    es.debate_budget = budget
    es.token_used = token_used
    es.token_budget = token_budget
    return es


class TestGateExtreme:
    def test_chat_skips_even_high_impact(self):
        lvl, _, force = enf.debate_gate(_mk_es("chat"), "conclusion", {"high_impact": True})
        assert lvl == enf.DEBATE_L0 and force is False

    def test_lightweight_skips(self):
        lvl, _, _ = enf.debate_gate(_mk_es("lightweight"), "conclusion")
        assert lvl == enf.DEBATE_L0

    def test_statistical_high_impact_l2(self):
        lvl, _, force = enf.debate_gate(_mk_es("statistical"), "conclusion",
                                        {"high_impact": True})
        assert lvl == enf.DEBATE_L2 and force

    def test_token_budget_depleted_l0(self):
        lvl, reasons, _ = enf.debate_gate(_mk_es("analysis", token_used=10, token_budget=5),
                                          "conclusion")
        assert lvl == enf.DEBATE_L0
        assert any("token" in r.lower() for r in reasons)

    def test_token_budget_force_ignored(self):
        lvl, _, force = enf.debate_gate(_mk_es("analysis", token_used=10, token_budget=5),
                                        "conclusion", {"high_impact": True})
        assert lvl == enf.DEBATE_L2 and force

    def test_uncertainty_escalates_before_script(self):
        lvl, reasons, _ = enf.debate_gate(_mk_es("analysis"), "before_script",
                                          {"uncertainty": True})
        assert lvl == enf.DEBATE_L2

    def test_conflict_escalates(self):
        lvl, reasons, force = enf.debate_gate(_mk_es("analysis"), "after_script",
                                              {"conflict": True})
        assert lvl == enf.DEBATE_L2

    def test_budget_exact_boundary_still_l2(self):
        lvl, _, _ = enf.debate_gate(_mk_es("analysis", count=2, budget=3), "conclusion")
        assert lvl == enf.DEBATE_L2

    def test_budget_zero_downgrades_all_non_force(self):
        lvl, reasons, force = enf.debate_gate(_mk_es("analysis", count=0, budget=0), "conclusion")
        assert lvl == enf.DEBATE_L1 and not force

    def test_force_with_budget_zero_stays_l2(self):
        lvl, _, force = enf.debate_gate(_mk_es("analysis", count=99, budget=0),
                                        "conclusion", {"high_impact": True})
        assert lvl == enf.DEBATE_L2 and force

    def test_after_script_mixed_signals_max(self):
        lvl, reasons, _ = enf.debate_gate(_mk_es("analysis"),
                                          "after_script",
                                          {"failed_retries": 3, "uncertainty": True})
        assert lvl == enf.DEBATE_L2


# ==================== E9 回流/回调极端 ====================

class TestReflowExtreme:
    def test_low_confidence_no_reflow(self, monkeypatch):
        called = []
        monkeypatch.setattr(da, "_load_debate_config", lambda: {"reflow_skill": "x"})
        from memomics.bio_tools import skill_evolution as se
        monkeypatch.setattr(se, "skill_evolution", lambda **kw: called.append(kw))
        da._reflow_verdict({"verdict": "modify", "confidence": "low",
                            "recommended_params": {"a": 1}, "topic": "t"})
        assert not called

    def test_error_no_reflow(self, monkeypatch):
        called = []
        monkeypatch.setattr(da, "_load_debate_config", lambda: {"reflow_skill": "x"})
        from memomics.bio_tools import skill_evolution as se
        monkeypatch.setattr(se, "skill_evolution", lambda **kw: called.append(kw))
        da._reflow_verdict({"error": True, "verdict": "ok", "confidence": "high", "topic": "t"})
        assert not called

    def test_no_verdict_no_reflow(self, monkeypatch):
        called = []
        monkeypatch.setattr(da, "_load_debate_config", lambda: {"reflow_skill": "x"})
        from memomics.bio_tools import skill_evolution as se
        monkeypatch.setattr(se, "skill_evolution", lambda **kw: called.append(kw))
        da._reflow_verdict({"confidence": "high"})
        assert not called


class TestCallbackExtreme:
    def _mk(self, tmp_path, agent=None):
        emitted = []
        import uuid
        sid = "cb_ext_" + uuid.uuid4().hex[:8]
        cbs = enf.create_enforcement_callbacks(
            {"id": sid, "results_dir": str(tmp_path)},
            lambda s, m: emitted.append(m),
            agent_ref=[agent] if agent else None)
        es = enf.get_enforcement(sid)
        es.analysis_level = "analysis"
        return cbs, es, emitted

    def test_debate_complete_records_token_usage(self, tmp_path):
        cbs, es, emitted = self._mk(tmp_path)
        # 先让 token_budget 生效
        es.token_budget = 100
        args = json.dumps({"topic": "t", "context": "c"})
        cbs["tool_start_callback"]("r1", "debate_analysis", args)
        cbs["tool_complete_callback"]("r1", "debate_analysis", args,
                                      json.dumps({"verdict": "ok", "usage": {"total": 1234}}))
        assert es.token_used == 1234
        assert es.debate_count == 1
        assert "t" in es.debated_topics

    def test_topic_dedupe_count_not_increment(self, tmp_path):
        cbs, es, emitted = self._mk(tmp_path)
        args = json.dumps({"topic": "same", "context": "c"})
        cbs["tool_start_callback"]("r1", "debate_analysis", args)
        cbs["tool_complete_callback"]("r1", "debate_analysis", args, "{}")
        cbs["tool_start_callback"]("r2", "debate_analysis", args)
        cbs["tool_complete_callback"]("r2", "debate_analysis", args, "{}")
        # 注意：enforcement 统计的是调用次数，topic 去重用于“是否再触发”，
        # 计数仍每次 +1（当前设计如此——预算护栏按调用次数计）
        assert es.debate_count == 2

    def test_before_script_gate_not_triggered_when_already_debated(self, tmp_path):
        class FakeAgent:
            def __init__(self):
                import threading
                self._pending_steer = None
                self._pending_steer_lock = threading.Lock()

        agent = FakeAgent()
        cbs, es, emitted = self._mk(tmp_path, agent)
        es.debated_topics.add("anything")
        cbs["tool_start_callback"]("c1", "execute_r", {"code": "FindClusters(res=0.5)"})
        reqs = [m for m in emitted if m.get("action") == "require"
                and "debate_analysis" in (m.get("require") or [])]
        assert not reqs, "已辩论过 topic 集合非空 → 不应再提示执行前辩论"

# ==================== v2 新增特性（2026-08-27） ====================

class TestV2Features:
    def test_core9_ten_roles(self, monkeypatch, tmp_debates_dir):
        monkeypatch.setattr(da, "_load_debate_config", lambda: _mk_cfg(role_preset="core9"))
        monkeypatch.setattr(da, "_load_provider_keys", lambda: {"deepseek": {"api_key": "k", "base_url": "https://x/v1"}})
        calls = _patch_call_role(monkeypatch)
        out = da.debate_analysis("t", "c", auto_kb=False)
        # core9: pro3 + con4 + neutral2 + judge1 = 10 次角色调用
        assert len(calls) == 10
        obj = json.loads(out)
        assert set(obj.get("neutral_reviews", {}).keys()) == {"design_review", "reproducibility_review"}

    def test_judge_count_3(self, monkeypatch, tmp_debates_dir):
        monkeypatch.setattr(da, "_load_debate_config", lambda: _mk_cfg(judge_count=3))
        monkeypatch.setattr(da, "_load_provider_keys", lambda: {"deepseek": {"api_key": "k", "base_url": "https://x/v1"}})
        calls = _patch_call_role(monkeypatch)
        out = da.debate_analysis("t", "c", auto_kb=False)
        obj = json.loads(out)
        # pro3 + con4 = 7 角色 + 3 裁判 = 10
        assert len(calls) == 10
        assert obj["judge_consensus"]["judge_count"] == 3
        assert obj["judge_consensus"]["majority_verdict"] == "ok"
        assert obj["judge_consensus"]["agreement"] == 1.0

    def test_evidence_fingerprint(self):
        a = da._evidence_fingerprint('[{"id":"a","pmid":"1","conclusion":"x"}]')
        b = da._evidence_fingerprint('[{"id":"b","pmid":"2","conclusion":"y"}]')
        assert a and b and a != b
        assert da._evidence_fingerprint("") == ""

    def test_fingerprint_includes_v2_params(self):
        f1 = da._debate_fingerprint("homogeneous", 1, {}, {"role_preset": "core7", "judge_count": 1})
        f2 = da._debate_fingerprint("homogeneous", 1, {}, {"role_preset": "core9", "judge_count": 1})
        f3 = da._debate_fingerprint("homogeneous", 1, {}, {"role_preset": "core7", "judge_count": 3})
        assert len({f1, f2, f3}) == 3

    def test_evidence_injected_into_role_prompt(self):
        p = da._v2_role_prompt("pro_biology", "t", "c", "kb", "", '[{"id":"e1","title":"文献A"}]')
        assert "[e1]" in p and "证据卡" in p

    def test_v2_prompt_contains_contract(self):
        p = da._v2_role_prompt("con_statistics", "t", "c", "kb", "")
        assert "证据契约" in p and "self_audit_failures" in p and "alternative_hypothesis" in p

    def test_consistency_high_with_missing(self):
        issues = da._check_consistency({"verdict": "support", "confidence": "high", "missing": ["缺 X"]})
        assert issues
        assert da._check_consistency({"verdict": "support", "confidence": "medium", "missing": ["缺 X"]}) == []


# ==================== 韧性加固（2026-09-13） ====================

class TestResilienceHardening:
    """judge 单点故障加固：失败正文回传 + 路由回退 + 瞬时失败重跑。

    背景（真实事故 2026-09-13）：opencode.ai zen 网关要求每个请求带
    x-opencode-session，缺失一律 400 MissingSessionID。8 个角色里只有 judge 走
    debate.judge 分组 provider（opencode-go），于是 7 个角色全部成功、judge 必挂，
    4 次 L2 辩论全部返回 error；而日志只留 "400 Bad Request"，根因被吞掉。
    """

    def test_transient_classifier(self):
        assert da._is_transient_error('HTTP 400 {"error":{"type":"MissingSessionID"}}') is False
        assert da._is_transient_error("HTTP 401 Unauthorized") is False
        assert da._is_transient_error("HTTP 429 rate limit") is True
        assert da._is_transient_error("ReadTimeout: timed out") is True
        assert da._is_transient_error("ConnectError: getaddrinfo failed") is True
        assert da._is_transient_error("HTTP 502 Bad Gateway") is True
        assert da._is_transient_error("") is False

    def test_llm_sync_keeps_http_error_body(self, monkeypatch, provider_keys):
        """400 的服务端正文必须回传到 error_detail（否则无法区分 MissingSessionID / key 失效 / 超限）。"""
        class _Resp:
            status_code = 400
            text = '{"error":{"type":"MissingSessionID"}}'

            def raise_for_status(self):
                raise RuntimeError("Client error '400 Bad Request'")

        class _Client:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, *a, **k):
                return _Resp()

        monkeypatch.setattr(da.httpx, "Client", _Client)
        monkeypatch.setattr(da.time, "sleep", lambda *_: None)
        r = da._call_llm_sync("p", "judge", "sk", "https://x/v1", "m")
        assert r["error"] is True
        assert "MissingSessionID" in r["error_detail"]
        assert r["transient"] is False
        assert "https://x/v1" in r["error_model"]

    def test_judge_fallback_when_group_route_fails(self, monkeypatch, provider_keys):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
        monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://env.example/v1")
        monkeypatch.setenv("DEEPSEEK_MODEL", "env-model")
        cfg = _mk_cfg(judge={"provider": "opencode-go", "model": "deepseek-v4-pro"})
        monkeypatch.setattr(da, "_call_llm_role", lambda label, prompt, cfg, temperature=None: {
            "content": "[judge 辩论生成失败]", "call_id": "j1", "error": True,
            "error_detail": "HTTP 400 MissingSessionID", "transient": False})
        seen = {}

        def fake_sync(prompt, label, api_key, base_url, model, temperature=0.7, max_tokens=1024):
            seen.update({"label": label, "model": model, "base_url": base_url})
            return {"content": '{"verdict":"ok"}', "call_id": "j2", "messages_count": 1}

        monkeypatch.setattr(da, "_call_llm_sync", fake_sync)
        r = da._call_llm_role_resilient("judge", "p", cfg)
        assert r["fallback_used"] is True
        assert r["fallback_from"].startswith("opencode-go/")
        assert "MissingSessionID" in r["fallback_detail"]
        assert seen["base_url"] == "https://env.example/v1"

    def test_non_judge_role_has_no_fallback(self, monkeypatch, provider_keys):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
        monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://env.example/v1")
        cfg = _mk_cfg(judge={"provider": "opencode-go", "model": "m"})
        monkeypatch.setattr(da, "_call_llm_role", lambda label, prompt, cfg, temperature=None: {
            "content": "[con_biology 辩论生成失败]", "call_id": "x1", "error": True})

        def _boom(*a, **k):
            raise AssertionError("非 judge 角色不应触发回退")

        monkeypatch.setattr(da, "_call_llm_sync", _boom)
        r = da._call_llm_role_resilient("con_biology", "p", cfg)
        assert r.get("fallback_used") is None

    def test_judge_fallback_skipped_when_same_route(self, monkeypatch, provider_keys):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
        monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
        cfg = _mk_cfg(judge={"provider": "deepseek", "model": "deepseek-v4-flash"})
        monkeypatch.setattr(da, "_call_llm_role", lambda label, prompt, cfg, temperature=None: {
            "content": "[judge 辩论生成失败]", "call_id": "j1", "error": True})

        def _boom(*a, **k):
            raise AssertionError("回退目标与主路由相同 → 不应重复调用")

        monkeypatch.setattr(da, "_call_llm_sync", _boom)
        r = da._call_llm_role_resilient("judge", "p", cfg)
        assert r.get("fallback_used") is None

    def test_transient_retry_only_reruns_transient(self, monkeypatch):
        called = []

        def fake_parallel(tasks, cfg=None):
            called.append([l for l, _ in tasks])
            return {l: _role_reply(l) for l, _ in tasks}

        monkeypatch.setattr(da, "_call_role_parallel", fake_parallel)
        tasks = [("pro_biology", "p1"), ("pro_statistics", "p2"), ("pro_bioinformatics", "p3")]
        results = {
            "pro_biology": {**_role_reply("pro_biology"), "error": True, "transient": True},
            "pro_statistics": {**_role_reply("pro_statistics"), "error": True, "transient": False},
            "pro_bioinformatics": _role_reply("pro_bioinformatics"),
        }
        out = da._retry_transient_roles(results, tasks, _mk_cfg())
        assert called == [["pro_biology"]]
        assert out["pro_biology"]["error"] is False
        assert out["pro_statistics"]["error"] is True

    def test_no_transient_failure_no_retry(self, monkeypatch):
        def _boom(*a, **k):
            raise AssertionError("无瞬时失败不应重跑")

        monkeypatch.setattr(da, "_call_role_parallel", _boom)
        tasks = [("pro_biology", "p1")]
        results = {"pro_biology": _role_reply("pro_biology")}
        assert da._retry_transient_roles(results, tasks, _mk_cfg()) is results

    def test_partial_failure_payload_carries_details(self, monkeypatch, tmp_debates_dir):
        monkeypatch.setattr(da, "_load_debate_config", lambda: _mk_cfg())
        monkeypatch.setattr(da, "_load_provider_keys", lambda: {"deepseek": {"api_key": "k", "base_url": "https://x/v1"}})
        monkeypatch.setattr(da, "_reflow_verdict", lambda r: None)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

        def fake(label, prompt, cfg, temperature=None):
            if label == "con_biology":
                return {**_role_reply(label), "error": True, "transient": False,
                        "content": "[con_biology 辩论生成失败]",
                        "error_detail": "HTTP 400 MissingSessionID", "error_model": "m @ u"}
            if label == "judge":
                return _role_reply(label, '{"verdict":"ok","confidence":"high"}')
            return _role_reply(label)

        monkeypatch.setattr(da, "_call_llm_role", fake)
        obj = json.loads(da.debate_analysis("t", "c", auto_kb=False))
        assert obj["error"] is True and obj["failed_roles"] == 1
        details = obj["failed_role_details"]
        assert details and any("MissingSessionID" in v["detail"] for v in details.values())
        assert any(v["model"] == "m @ u" for v in details.values())

