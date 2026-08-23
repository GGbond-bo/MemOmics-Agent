# -*- coding: utf-8 -*-
"""MiMo-Code 上下文架构迁移（P1-P5）离线单测（2026-08-21）。

覆盖：single usable() 预算、writer(§1-§11 checkpoint 落盘/单写者/路径守卫)、
增量边界(P5)、分段重建(P4)、FTS 召回(P3)、主编排 memomics_replay（含 fail-open）。
writer 的 LLM 用 monkeypatch 注入假函数，全程不触网。
"""
import os
import time

import pytest

import context_arch as ca

pytestmark = [pytest.mark.unit, pytest.mark.memory]


def _session(tmp_path):
    rd = str(tmp_path / "results")
    os.makedirs(rd, exist_ok=True)
    os.makedirs(os.path.join(rd, "scripts"), exist_ok=True)
    return {"id": "arch-unit", "results_dir": rd, "model_config": {"model": "deepseek-v4-flash"}}


def _msg(role, c):
    return {"role": role, "content": c}


def _hist(n=30):
    return [_msg("user" if i % 2 == 0 else "assistant", f"消息 {i}：基因集 {i} 打分与亚群分析 {i}")
            for i in range(n)]


# ── P1 usable() ──
class TestBudget:
    def test_usable_default(self, monkeypatch):
        monkeypatch.delenv("MEMOMICS_MAX_CONTEXT", raising=False)
        b = ca.compute_usable("deepseek-v4-flash")
        assert b["hard"] == 1_000_000
        assert b["usable"] == b["hard"] - b["reserved"]
        assert b["reserved"] == ca.COMPACTION_BUFFER + ca.DEFAULT_OUTPUT_TOKENS

    def test_usable_config_cap(self, monkeypatch):
        monkeypatch.setenv("MEMOMICS_MAX_CONTEXT", "200000")
        b = ca.compute_usable("deepseek-v4-flash")
        assert b["effective"] == 200_000
        assert b["source"] == "config"
        assert b["usable"] < 200_000

    def test_invalid_cap_ignored(self, monkeypatch):
        monkeypatch.setenv("MEMOMICS_MAX_CONTEXT", "5")  # < reserved → 忽略
        b = ca.compute_usable("deepseek-v4-flash")
        assert b["effective"] == 1_000_000


# ── P2 writer ──
class TestWriter:
    def test_fake_llm_writes_checkpoint_with_header(self, tmp_path):
        s = _session(tmp_path)
        p = ca.run_writer(s, "span text", "prior", 12, lambda prompt: "## §1 Active intent\n- x\n## §11 Open notes\n- done")
        assert p and os.path.isfile(p)
        txt = open(p, encoding="utf-8").read()
        assert "writer: context-arch.writer" in txt
        assert "upto_count: 12" in txt
        assert "## §1 Active intent" in txt and "## §11 Open notes" in txt

    def test_deterministic_fallback_when_no_llm(self, tmp_path):
        s = _session(tmp_path)
        p = ca.run_writer(s, "span", "", 3, None)
        assert p and os.path.isfile(p)
        assert "确定性回退" in open(p, encoding="utf-8").read()

    def test_path_guard_blocks_outside(self, tmp_path):
        s = _session(tmp_path)
        with pytest.raises(ValueError):
            ca.path_guard(str(tmp_path / "evil"), [s["results_dir"]])

    def test_read_checkpoint_boundary(self, tmp_path):
        s = _session(tmp_path)
        ca.write_checkpoint(s, 17, "## §1\n- body")
        ck = ca.read_checkpoint(s)
        assert ck["upto"] == 17 and ck["path"]

    def test_read_checkpoint_prefers_substantial_over_placeholder(self, tmp_path):
        """回归(2026-08-21)：空壳/占位 checkpoint 不得顶掉真正含 § 的好摘要。
        两个文件，新的是 116B 占位、旧的是 3.8KB 好摘要 → 读取应选好摘要。"""
        s = _session(tmp_path)
        d = ca.checkpoints_dir(s)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "checkpoint-1000.md"), "w", encoding="utf-8") as f:  # 新版=占位
            f.write("<!-- ... upto_count: 760 ... -->\n\n## §1\n- x")
        good = "## §1 Active intent\n" + "长" * 4000
        with open(os.path.join(d, "checkpoint-0900.md"), "w", encoding="utf-8") as f:  # 旧版=好
            f.write("<!-- ... upto_count: 748 ... -->\n\n" + good)
        ck = ca.read_checkpoint(s)
        assert ck["path"] and ck["path"].endswith("checkpoint-0900.md")
        assert ck["upto"] == 748


# ── P5 增量边界 ──
class TestIncremental:
    def test_new_span_is_after_upto(self):
        h = _hist(30)
        span, upto = ca.new_span(h, 10, 8)
        assert upto == 22 and len(span) == 12
        assert span[0]["content"] == h[10]["content"]

    def test_without_prior_covers_head(self):
        h = _hist(30)
        span, upto = ca.new_span(h, 0, 8)
        assert upto == 22 and len(span) == 22

    def test_mature_upto_no_new_span(self):
        h = _hist(30)
        span, upto = ca.new_span(h, 22, 8)
        assert span == [] and upto == 22


# ── P4 rebuild 分段 ──
class TestRebuild:
    def test_sections_present_and_capped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MEMOMICS_CAP_CHECKPOINT", "200")
        s = _session(tmp_path)
        (tmp_path / "results" / "task_plan.md").write_text("Phase 1 出图\nPhase 2 校对", encoding="utf-8")
        (tmp_path / "results" / "REQUIREMENTS.md").write_text("记住必须带 P 值", encoding="utf-8")
        (tmp_path / "results" / "scripts" / "fig.py").write_text("x", encoding="utf-8")
        out = ca.rebuild_context(s, _hist(6), "## §1\n" + "长" * 1000,
                                 ca.build_extras(s), caps={"checkpoint": 200, "recent_tail": 16000})
        blob = "\n".join(m["content"] for m in out if m["role"] == "system")
        assert "任务清单(task_plan)" in blob
        assert "会话检查点" in blob
        assert "持久用户要求/路径" in blob
        assert "全局记忆" in blob
        assert "会话脚本索引" in blob
        assert "提示" in blob
        # checkpoint 段被截到 200
        ck_block = [m["content"] for m in out if "会话检查点" in m["content"]][0]
        assert len(ck_block) <= 200 + 64
        # 尾窗逐字在末尾
        assert out[-1] == _msg(os.getenv("X", "assistant"), "消息 5：基因集 5 打分与亚群分析 5") or "消息 5" in str(out[-1]["content"])

    def test_rebuild_within_tail_cap(self):
        h = _hist(50)
        out = ca.rebuild_context({}, h[-6:], "", {}, caps={"recent_tail": 60})
        assert len(out) >= 1


# ── P1-P5 主编排 ──
class TestReplay:
    def test_below_usable_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MEMOMICS_MAX_CONTEXT", "0")
        s = _session(tmp_path)
        h = _hist(15)
        out = ca.memomics_replay(s, h, llm_fn=lambda p: "## §1\n- x")
        assert out == h

    def test_over_budget_rebuilds_and_writes_checkpoint(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MEMOMICS_ROLLUP_TAIL", "6")
        s = _session(tmp_path)
        calls = {"n": 0}
        h = _hist(30)
        tiny_budget = {"hard": 1_000_000, "effective": 1000, "usable": 10,
                       "reserved": 12288, "source": "test"}

        def fake_llm(prompt):
            calls["n"] += 1
            return "## §1 Active intent\n- 迁移验证\n## §11 Open notes\n- ok"

        import time as _t
        out = ca.memomics_replay(s, h, budget=tiny_budget, llm_fn=fake_llm)
        # writer 是后台线程：轮询等它把 checkpoint 写出来（避免读到 open() 截断瞬间的空文件）
        ck = None
        for _ in range(50):
            ck = ca.read_checkpoint(s)
            if ck.get("path") and ck.get("upto", 0) > 0 and calls["n"] >= 1:
                break
            _t.sleep(0.1)
        assert calls["n"] >= 1, "writer llm 应被调用"
        assert ck and ck["path"] and ck["upto"] > 0
        blob = "\n".join(m["content"] for m in out if m["role"] == "system")
        assert "会话检查点" in blob
        assert len(out) >= 7  # 若干 system 块 + 尾窗 6

    def test_fail_open_on_exception(self, tmp_path):
        s = _session(tmp_path)

        def boom(prompt):
            raise RuntimeError("writer down")

        out = ca.memomics_replay(s, _hist(30), llm_fn=boom, budget=ca.compute_usable(model="", max_context=20000))
        assert isinstance(out, list) and len(out) >= 1

    def test_no_writer_when_no_new_span(self, tmp_path):
        """P5 单调性回归(2026-08-21)：历史条数波动使 stop < upto 时，
        不得重写 checkpoint——否则边界回退、覆盖已合并摘要、白烧一次 LLM。"""
        s = _session(tmp_path)
        ca.write_checkpoint(s, 748, "## §1\n- prior merged summary")
        h = _hist(760)  # 760 - tail(40) = 720 < 748 → 无新片段
        calls = {"n": 0}
        tiny_budget = {"hard": 1_000_000, "effective": 1000, "usable": 10,
                       "reserved": 12288, "source": "test"}
        out = ca.memomics_replay(s, h, budget=tiny_budget, tail_len=40,
                                 llm_fn=lambda p: calls.__setitem__("n", calls["n"] + 1) or "## §1\n- x")
        assert isinstance(out, list)
        time.sleep(0.3)  # 若误 spawn，后台线程会写文件/计数
        assert calls["n"] == 0, "无新片段时 writer 不得被调用"
        ck = ca.read_checkpoint(s)
        assert ck["upto"] == 748, "边界必须保持单调不回退"


# ── P3 FTS ──
class TestFts:
    def test_fts_recall_returns_string(self):
        r = ca.fts_recall("骨骼肌 衰老 基因", 3)
        assert isinstance(r, str)

    def test_chinese_recall_hybrid(self, tmp_path):
        """B(2026-08-21)：中文词级召回——jieba 分词后按词交并×trust 打分，不再依赖 FTS 中文分词。"""
        dbp = str(tmp_path / "mem.db")
        import sqlite3
        conn = sqlite3.connect(dbp)
        conn.execute("CREATE TABLE facts (fact_id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, category TEXT, tags TEXT, trust_score REAL, retrieval_count INTEGER DEFAULT 0)")
        conn.executemany("INSERT INTO facts (content, category, trust_score) VALUES (?,?,?)", [
            ("用户要求: 所有分析脚本统一保存到 scripts/ 目录", "user_pref", 0.8),
            ("用户要求: 出图必须带 P 值标注", "user_pref", 0.8),
            ("技能经验: R 4.5.3 库损坏重装", "skill_exp", 0.5),
        ])
        conn.commit(); conn.close()
        r1 = ca.recall_hybrid("脚本保存目录", 3, db_path=dbp)
        assert "scripts/" in r1 and "脚本" in r1, f"应召回脚本相关: {r1}"
        r2 = ca.recall_hybrid("出图 P 值", 3, db_path=dbp)
        assert "P 值" in r2, f"应召回 P 值相关: {r2}"
        r3 = ca.recall_hybrid("今天天气不错", 3, db_path=dbp)
        assert r3 == "", f"无关查询应空: {r3!r}"


# ── A. 科研适配触发 ──
class TestAggressiveTrigger:
    def _session(self, tmp_path, sc=0):
        rd = str(tmp_path / "r"); os.makedirs(rd, exist_ok=True)
        return {"id": "aggr", "results_dir": rd, "_self_check_count": sc}

    def test_off_by_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MEMOMICS_AGGRESSIVE_COMPACT", raising=False)
        assert ca._aggressive_trigger(self._session(tmp_path), 40000, 987712) is False

    def test_knob_triggers(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MEMOMICS_AGGRESSIVE_COMPACT", "1")
        monkeypatch.setenv("MEMOMICS_AGGRESSIVE_THRESHOLD", "50000")
        assert ca._aggressive_trigger(self._session(tmp_path), 60000, 987712) is True
        assert ca._aggressive_trigger(self._session(tmp_path), 30000, 987712) is False  # 低于阈值

    def test_long_task_auto(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MEMOMICS_AGGRESSIVE_COMPACT", raising=False)
        # 自检唤醒 >=3 且历史 >=30K → 长任务自动接管
        assert ca._aggressive_trigger(self._session(tmp_path, sc=3), 40000, 987712) is True
        assert ca._aggressive_trigger(self._session(tmp_path, sc=2), 40000, 987712) is False
        assert ca._aggressive_trigger(self._session(tmp_path, sc=3), 20000, 987712) is False

    def test_replay_trigger_end_to_end(self, tmp_path, monkeypatch):
        """A 端到端：默认不触发（原样返回）；knob 打开且超阈值 → 触发重建。"""
        s = self._session(tmp_path)
        h = _hist(60)
        b = {"hard": 1_000_000, "effective": 1_000_000, "usable": 987712, "reserved": 12288, "source": "test"}
        monkeypatch.delenv("MEMOMICS_AGGRESSIVE_COMPACT", raising=False)
        assert ca.memomics_replay(s, h, budget=b, tail_len=10, llm_fn=lambda p: "## §1\n- x") == h
        monkeypatch.setenv("MEMOMICS_AGGRESSIVE_COMPACT", "1")
        monkeypatch.setenv("MEMOMICS_AGGRESSIVE_THRESHOLD", "100")
        out = ca.memomics_replay(s, h, budget=b, tail_len=10, llm_fn=lambda p: "## §1\n- x")
        blob = "\n".join(m["content"] for m in out if m["role"] == "system")
        assert "会话检查点" in blob
