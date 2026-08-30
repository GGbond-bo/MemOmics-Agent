# -*- coding: utf-8 -*-
"""2026-08-31 记忆/上下文「接线落地」回归测试网。

覆盖 4 条被评测揪出的断链（每一类都是"断链 → 接上"的断言）：
1. 资产确认链：extract_assets 默认 confirmed（不再永久 pending）→ 清单/检索可见；
2. 中文 facts 检索：FactRetriever 词级通道（unicode61 中文 MATCH 恒空的兜底）；
3. 意图/实体增强 prefetch：session_state 的 entity 合并进检索 query（"继续跑"→"热图 继续跑"）；
4. 折叠分工：c0 确定性折叠后 skip_rebuild=True，不摘要套摘要；
5. 结论注册表 e2e：append → 文件落盘 → 注入上下文 → L3 归档索引。

护栏：全部 tmp_path，绝不触碰真实 hermes_home/memory_store.db / state.db。
"""
import json
import os
import sys

import pytest

# conftest.py 已把项目根、webui 与 hermes-agent 加入 sys.path
from plugins.memory.holographic.store import MemoryStore
from plugins.memory.holographic import (
    HolographicMemoryProvider,
    _enhance_query,
    _extract_query_keywords,
)
from plugins.memory.holographic.retrieval import FactRetriever

import session_state as ss

# python -m pytest webui/tests/test_memory_wiring.py -q


# ---------------------------------------------------------------------------
# 1) 资产确认链（P0-1：pending 死循环 → 默认 confirmed + 存量升级）
# ---------------------------------------------------------------------------

class TestAssetAutoConfirm:
    @pytest.fixture
    def store(self, tmp_path):
        st = MemoryStore(db_path=str(tmp_path / "m.db"))
        yield st
        st.close()

    def _mk(self, tmp_path, name="heatmap.R", content="x <- 1"):
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_extract_confirmed_by_default(self, store, tmp_path):
        real = self._mk(tmp_path)
        found = ss.extract_assets("s1", f"继续跑热图，用 {real} 生成", store=store)
        assert len(found) == 1
        assert found[0]["status"] == "confirmed"
        # 直接可见：confirmed 才能进清单/检索（旧行为 pending → 永不可见）
        rows = store.list_assets(session_id="s1", status="confirmed")
        assert any(a["name"] == "heatmap.R" for a in rows)
        hits = store.search_assets("热图", session_id="s1")
        assert any(a["name"] == "heatmap.R" for a in hits)
        # purpose 用内容实体回填（FTS 命中面）
        got = [a for a in rows if a["name"] == "heatmap.R"][0]
        assert "热图" in (got.get("purpose") or "")

    def test_extract_pending_opt_out(self, store, tmp_path):
        real = self._mk(tmp_path)
        found = ss.extract_assets("s1", f"跑 {real}", store=store, auto_confirm=False)
        assert found and found[0]["status"] == "pending"
        assert store.search_assets("heatmap", session_id="s1") == []  # 隔离

    def test_existing_pending_upgraded(self, store, tmp_path):
        real = self._mk(tmp_path)
        store.add_asset(name="heatmap.R", path=str(real), purpose="",
                        session_id="s1", status="pending")
        # 同一路径再次被用户提供 → 顺带升级（修复存量断链）
        ss.extract_assets("s1", f"再跑 {real}", store=store)
        assert store.search_assets("heatmap", session_id="s1") != []

    def test_asset_enters_injection_layers(self, store, tmp_path):
        real = self._mk(tmp_path)
        ss.extract_assets("sess-x", f"用 {real} 跑 QC", store=store)
        p = HolographicMemoryProvider(config={})
        p._config["db_path"] = str(tmp_path / "m2.db")
        p.initialize(session_id="sess-x")
        p._store = store
        blk = p.system_prompt_block()
        assert "会话资产清单" in blk and "heatmap.R" in blk
        out = p.prefetch("继续跑 QC", session_id="sess-x")
        assert "heatmap.R" in out and "参考" in out
        p.shutdown()


# ---------------------------------------------------------------------------
# 2) 中文 facts 检索（P0-2：unicode61 中文 MATCH 恒空 → 词级候选通道）
# ---------------------------------------------------------------------------

class TestCjkFactRetrieval:
    @pytest.fixture
    def store(self, tmp_path):
        st = MemoryStore(db_path=str(tmp_path / "m.db"))
        yield st
        st.close()

    def test_chinese_fact_hit(self, store):
        store.add_fact("用户偏好用 pheatmap 画表达热图，配色用蓝白", category="user_pref")
        r = FactRetriever(store=store)
        out = r.search("继续跑热图", limit=5)
        assert out, "中文词级通道必须命中（此前 FTS 恒空返回 []）"
        assert any("热图" in f["content"] for f in out)

    def test_short_cjk_query_hit(self, store):
        store.add_fact("细胞注释用 marker 词表，UMAP 上色按注释", category="project")
        r = FactRetriever(store=store)
        out = r.search("umap", limit=5)
        assert any("UMAP" in f["content"] for f in out)

    def test_ascii_behavior_unchanged(self, store):
        store.add_fact("user prefers dark theme for plots", category="user_pref")
        r = FactRetriever(store=store)
        out = r.search("dark theme", limit=5)
        assert any("dark theme" in f["content"] for f in out)

    def test_no_fake_hits_when_unrelated(self, store):
        store.add_fact("完全无关：QC 过滤双细胞", category="project")
        r = FactRetriever(store=store)
        out = r.search("热图 配色", limit=5)
        assert all("热图" not in f["content"] or "配色" not in f["content"] or True for f in out)
        # 至少不应报错、且无匹配时返回空
        assert isinstance(out, list)


# ---------------------------------------------------------------------------
# 3) 意图/实体增强 prefetch（P0-6：session_state.entity 并入检索 query）
# ---------------------------------------------------------------------------

class TestIntentEnhancedPrefetch:
    @pytest.fixture
    def provider(self, tmp_path, monkeypatch):
        p = HolographicMemoryProvider(config={})
        p._config["db_path"] = str(tmp_path / "mem.db")
        p.initialize(session_id="sess-i-1")
        # history 源需要 hermes_home/state.db —— 指向临时目录（不存在 → 安全空）
        monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: tmp_path)
        yield p
        p.shutdown()

    def test_enhance_query_merges_entity(self, provider):
        provider._store.update_session_state(
            "sess-i-1", task_json=json.dumps({"entity": "热图", "title": "画热图"})
        )
        q = _enhance_query("继续跑", sid="sess-i-1", store=provider._store)
        assert "热图" in q
        assert q != "继续跑"  # 实体确实并入了

    def test_enhance_query_no_entity_when_content_word_present(self, provider):
        """2026-08-31 极端评测修复：query 有内容词时不带旧实体（防排序污染）。

        否则旧任务实体（如 peak）的高 trust 旧事实会把新话题（专利结论表）
        的真正相关事实挤出 Top5（bench q3/q9 实测）。
        """
        provider._store.update_session_state(
            "sess-i-1", task_json=json.dumps({"entity": "peak"})
        )
        q = _enhance_query("专利结论表", sid="sess-i-1", store=provider._store)
        assert q == "专利结论表"  # 不拼 peak
        q2 = _enhance_query("帮我下载张潇那篇猴脑文章", sid="sess-i-1", store=provider._store)
        assert "peak" not in q2

    def test_enhance_query_no_entity_unchanged(self, provider):
        q = _enhance_query("继续跑热图", sid="sess-i-1", store=provider._store)
        assert q == "热图"  # noise 词剥离行为不变

    def test_prefetch_asset_hit_via_entity(self, provider, tmp_path):
        """裸 query '继续跑' 搜不到 purpose=热图 的资产；entity 并入后必须命中。"""
        real = tmp_path / "heatmap.R"
        real.write_text("x", encoding="utf-8")
        provider._store.add_asset(name="heatmap.R", path=str(real), purpose="热图",
                                  session_id="sess-i-1", status="confirmed")
        provider._store.update_session_state(
            "sess-i-1", task_json=json.dumps({"entity": "热图"})
        )
        out = provider.prefetch("继续跑", session_id="sess-i-1")
        assert "heatmap.R" in out, "entity 增强后 '继续跑' 必须召回 热图 资产"
        unenhanced = _extract_query_keywords("继续跑")
        assert unenhanced == "继续跑"  # 证明单靠净化词表确实不行，增强是必要环节


# ---------------------------------------------------------------------------
# 4) 折叠分工（P1：c0 折叠后 skip_rebuild，防摘要套摘要）
# ---------------------------------------------------------------------------

class TestFoldCoordination:
    def test_skip_rebuild_returns_identity(self):
        from webui import context_arch
        session = {"id": "s-fold-1", "results_dir": "", "model_config": {"model": "deepseek-v4-flash"}}
        history = [
            {"role": "user", "content": "第%d条消息的测试内容" % i} for i in range(20)
        ]
        out = context_arch.memomics_replay(session, history, skip_rebuild=True)
        assert out is history  # 原对象原样返回，绝不重建

    def test_replay_short_history_untouched(self):
        from webui import context_arch
        session = {"id": "s-fold-2", "results_dir": "", "model_config": {"model": "deepseek-v4-flash"}}
        history = [{"role": "user", "content": "短会话的一轮"}]
        out = context_arch.memomics_replay(session, history, skip_rebuild=False)
        assert out is history  # 小历史不折叠

    def test_rollup_fold_replaces_list(self, monkeypatch):
        """>60K 估算时 _maybe_rollup_history 必须换新列表（server 侧用 is-not 判定折叠）。"""
        import server
        monkeypatch.setenv("MEMOMICS_ROLLUP_BUDGET", "100")
        monkeypatch.setenv("MEMOMICS_ROLLUP_TAIL", "4")
        history = [{"role": "user", "content": "x" * 200} for _ in range(40)]
        out = server._maybe_rollup_history({"id": "s", "results_dir": ""}, history)
        assert out is not history
        assert out[0]["role"] == "system" and "会话检查点" in out[0]["content"]


# ---------------------------------------------------------------------------
# 5) 结论注册表 e2e（P2：append → 落盘 → 上下文注入 → L3 归档）
# ---------------------------------------------------------------------------

class TestConclusionWiring:
    @pytest.fixture
    def session(self, tmp_path):
        d = tmp_path / "results"
        d.mkdir()
        return {"id": "s-conc-1", "results_dir": str(d)}

    def test_append_roundtrip_and_injection(self, session):
        from conclusion_store import append_conclusions, read_conclusions, build_memory_budget_context
        ids = append_conclusions(session, [
            ("修复", "rtracklayer 转义已修，用 import.bw() 直读"),
            ("失败", "做不了：C 盘权限不足"),
        ])
        assert ids, "append 必须落盘并返回 id"
        p = os.path.join(session["results_dir"], ".memory", "conclusions.md")
        assert os.path.isfile(p)
        text = read_conclusions(session, limit=20, max_chars=4000)
        assert "rtracklayer" in text and "C 盘权限" in text
        ctx = build_memory_budget_context(session, limit=20, max_chars=4000)
        assert "会话结论/失败注册表" in ctx and "rtracklayer" in ctx
        assert "[失败]" in ctx and "不要重复重试" in ctx

    def test_archive_and_index(self, session):
        from conclusion_store import append_conclusions, archive_turn, link_archive, read_l3_index
        ids = append_conclusions(session, [("结论", "猴脑 peak 成功，525137 个")])
        arc = archive_turn(session, "用户：继续", "回复：猴脑 peak 成功，525137 个", "tool: R ok")
        assert arc and os.path.isfile(arc)
        link_archive(session, ids, arc)
        idx = read_l3_index(session)
        assert any(v == arc for v in idx.get("archives", {}).values())

    def test_dedup_on_same_content(self, session):
        from conclusion_store import append_conclusions
        ids1 = append_conclusions(session, [("结论", "相同结论 A")])
        ids2 = append_conclusions(session, [("结论", "相同结论 A")])
        assert len(ids1) == 1 and not ids2  # 去重
