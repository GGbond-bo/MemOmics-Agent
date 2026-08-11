# -*- coding: utf-8 -*-
"""会话级记忆测试网：资产表 / session_state / 诉求捕获 / 多源检索。

分层（多场景 x 多角度）：
1. store 层  —— assets CRUD/FTS/去重/pending 隔离 + session_state upsert（临时 db）
2. 模块层    —— session_state.py 诉求捕获/升级/资产提取/任务状态（临时 db）
3. 注入层    —— holographic prefetch 四源 + system_prompt_block（临时 db + 临时 state.db）

护栏：
- 全部使用 tmp_path，绝不触碰真实 hermes_home/memory_store.db 与 state.db
- prefetch 的 history 源通过 monkeypatch get_hermes_home 指向临时目录
- 断言不依赖真实 LLM / 网络 / 服务
"""
import json
import os

import pytest

# conftest.py 已把项目根、webui 与 hermes-agent 加入 sys.path
from plugins.memory.holographic.store import MemoryStore
from plugins.memory.holographic import HolographicMemoryProvider, _extract_query_keywords

import session_state as ss


# ---------------------------------------------------------------------------
# 1) store 层
# ---------------------------------------------------------------------------

class TestAssetsStore:
    def test_add_search_confirm_used(self, tmp_path):
        s = MemoryStore(db_path=str(tmp_path / "m.db"))
        aid = s.add_asset(name="heatmap.R", path=r"E:\x\heatmap.R", kind="script",
                          purpose="热图", session_id="s1", status="confirmed")
        s.add_asset(name="01_qc.R", path=r"E:\x\01_qc.R", kind="script",
                    purpose="QC", session_id="s1", status="confirmed")
        s.confirm_asset(aid)
        s.mark_asset_used(aid)
        r = s.search_assets("热图")
        assert any(x["name"] == "heatmap.R" for x in r)
        r2 = s.search_assets("qc")
        assert any(x["name"] == "01_qc.R" for x in r2)
        used = s.list_assets(session_id="s1")
        heat = [x for x in used if x["name"] == "heatmap.R"][0]
        assert heat["use_count"] >= 1
        s.close()

    def test_add_dedup(self, tmp_path):
        s = MemoryStore(db_path=str(tmp_path / "m.db"))
        a = s.add_asset(name="a.R", path="/p/a.R", session_id="s1")
        b = s.add_asset(name="a.R", path="/p/a.R", session_id="s1")
        assert a == b
        c = s.add_asset(name="a.R", path="/p/a.R", session_id="s2")  # 不同会话不算重复
        assert c != a
        s.close()

    def test_pending_isolation(self, tmp_path):
        s = MemoryStore(db_path=str(tmp_path / "m.db"))
        s.add_asset(name="pending.R", path="/p/p.R", purpose="x", session_id="s1")
        assert s.search_assets("pending") == []
        assert s.search_assets("pending", status=None) != []  # 显式关 status 才可见
        s.close()

    def test_has_asset(self, tmp_path):
        s = MemoryStore(db_path=str(tmp_path / "m.db"))
        assert not s.has_asset("x.R", "/p/x.R", "s1")
        s.add_asset(name="x.R", path="/p/x.R", session_id="s1")
        assert s.has_asset("x.R", "/p/x.R", "s1")
        assert not s.has_asset("x.R", "/p/x.R", "s9")
        s.close()

    def test_session_state_upsert_partial(self, tmp_path):
        s = MemoryStore(db_path=str(tmp_path / "m.db"))
        s.update_session_state("s1", task_json=json.dumps({"title": "QC", "step": 1}),
                               requests_json=json.dumps([{"entity": "热图", "ts": "x"}]))
        st = s.get_session_state("s1")
        assert json.loads(st["task_json"])["step"] == 1
        s.update_session_state("s1", task_json=json.dumps({"title": "QC", "step": 2}))
        st2 = s.get_session_state("s1")
        assert json.loads(st2["task_json"])["step"] == 2
        assert json.loads(st2["requests_json"])[0]["entity"] == "热图"  # 部分更新不覆盖
        assert s.get_session_state("nope") == {"task_json": "{}", "requests_json": "[]"}
        s.close()


# ---------------------------------------------------------------------------
# 2) session_state 模块层
# ---------------------------------------------------------------------------

class TestSessionState:
    @pytest.fixture
    def store(self, tmp_path):
        st = MemoryStore(db_path=str(tmp_path / "m.db"))
        yield st
        st.close()

    def test_capture_normal_request(self, store):
        r = ss.capture_user_request("s1", "继续跑热图", store=store, intent="analysis")
        assert r["entity"] == "热图" and not r["escalated"]

    def test_capture_repeat_escalates(self, store):
        ss.capture_user_request("s1", "继续跑热图", store=store)
        r = ss.capture_user_request("s1", "再帮我画一下热图", store=store)
        assert r["escalated"] is True
        facts = store.search_facts("用户诉求", limit=5)
        assert any("再帮我画一下热图" in f["content"] for f in facts)

    def test_capture_remember_escalates(self, store):
        r = ss.capture_user_request("s1", "记住以后都用 Seurat 做整合", store=store)
        assert r["escalated"] is True and r["entity"] == "seurat"
        facts = store.search_facts("用户诉求", limit=5)
        assert any("记住以后都用 Seurat" in f["content"] for f in facts)

    def test_capture_chat_no_entity(self, store):
        r = ss.capture_user_request("s1", "好的谢谢", store=store)
        assert r["entity"] == "" and not r["escalated"]

    def test_capture_dedup_60s(self, store):
        ss.capture_user_request("s1", "继续跑热图", store=store)
        r = ss.capture_user_request("s1", "继续跑热图", store=store)  # 相同文本 60s 内
        assert r["escalated"] is False
        st = store.get_session_state("s1")
        assert len(json.loads(st["requests_json"])) == 1  # 未重复追加

    def test_capture_max_20(self, store):
        for i in range(30):
            ss.capture_user_request("s1", f"消息 {i}", store=store)
        st = store.get_session_state("s1")
        assert len(json.loads(st["requests_json"])) <= 20

    def test_update_task_state_merge(self, store):
        t = ss.update_task_state("s1", store=store, title="QC", step=1, total_steps=6)
        assert t["title"] == "QC" and t["step"] == 1
        t2 = ss.update_task_state("s1", store=store, step=3, current_script=r"E:\x\01_qc.R")
        assert t2["step"] == 3 and t2["title"] == "QC" and t2["current_script"] == r"E:\x\01_qc.R"

    def test_update_task_state_empty_no_clobber(self, store):
        ss.update_task_state("s1", store=store, step=3)
        t = ss.update_task_state("s1", store=store, step="")
        assert t["step"] == 3

    def test_extract_assets_real_path_only(self, store, tmp_path):
        real = tmp_path / "my_script.R"
        real.write_text("x <- 1", encoding="utf-8")
        fake = r"E:\data\no_such_12345.R"
        found = ss.extract_assets("s1", f"用 {real} 跑，另外 {fake} 也看一下", store=store)
        assert len(found) == 1
        assert found[0]["name"].lower() == "my_script.r"
        assert all(a["path"] != fake for a in found)

    def test_extract_assets_dedup(self, store, tmp_path):
        real = tmp_path / "my_script.R"
        real.write_text("x <- 1", encoding="utf-8")
        ss.extract_assets("s1", f"跑 {real}", store=store)
        found2 = ss.extract_assets("s1", f"再跑 {real}", store=store)
        assert found2 == []
        assert len(store.list_assets(session_id="s1")) == 1

    def test_cross_session_isolation(self, store):
        ss.capture_user_request("s1", "跑火山图", store=store)
        ss.capture_user_request("s2", "跑热图", store=store)
        st1 = store.get_session_state("s1")
        assert all(x["entity"] != "热图" for x in json.loads(st1["requests_json"]))


# ---------------------------------------------------------------------------
# 3) holographic 注入层
# ---------------------------------------------------------------------------

class TestHolographicInjection:
    @pytest.fixture
    def provider(self, tmp_path, monkeypatch):
        p = HolographicMemoryProvider(config={})
        p._config["db_path"] = str(tmp_path / "mem.db")
        p.initialize(session_id="sess-test-1")
        yield p
        p.shutdown()

    @pytest.fixture
    def fake_history_db(self, tmp_path, monkeypatch):
        """临时 state.db + 两条本会话消息 + 一条其他会话消息。"""
        from hermes_state import SessionDB
        db_path = tmp_path / "state.db"
        sdb = SessionDB(db_path=db_path)
        sdb.create_session("sess-test-1", source="webui")
        sdb.append_message("sess-test-1", role="user",
                           content="帮我用 pheatmap 画一个表达热图，样本分组标记一下")
        sdb.append_message("sess-test-1", role="user", content="QC 过滤后重新跑一遍")
        sdb.create_session("sess-other-999", source="webui")
        sdb.append_message("sess-other-999", role="user", content="完全无关的火山图话题")
        sdb.close()
        monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: tmp_path)
        return tmp_path

    def test_keyword_extraction(self):
        assert _extract_query_keywords("继续跑热图") == "热图"
        assert _extract_query_keywords("帮我做一下 QC 分析") == "QC 分析"
        assert _extract_query_keywords("你好") == "你好"
        assert _extract_query_keywords("") == ""

    def test_prefetch_assets_source(self, provider):
        provider._store.add_asset(name="heatmap.R", path=r"E:\x\heatmap.R",
                                  purpose="热图", session_id="sess-test-1", status="confirmed")
        provider._store.add_asset(name="volcano.R", path="/tmp/o.R", purpose="火山图",
                                  session_id="sess-other", status="confirmed")
        out = provider.prefetch("继续跑热图", session_id="sess-test-1")
        assert "Related Assets" in out and "heatmap.R" in out
        assert "仅供参考" in out
        # 跨会话资产命中时带来源会话标注
        out2 = provider.prefetch("帮我画火山图", session_id="sess-test-1")
        assert "volcano.R" in out2 and "sess-other" in out2

    def test_prefetch_task_and_requests(self, provider):
        provider._store.update_session_state(
            "sess-test-1",
            task_json=json.dumps({"title": "QC", "step": 2, "total_steps": 6,
                                  "current_script": r"E:\x\01_qc.R"}),
            requests_json=json.dumps([{"text": "继续跑热图", "entity": "热图", "ts": "x"}]),
        )
        out = provider.prefetch("随便什么", session_id="sess-test-1")
        assert "当前任务状态" in out and "QC" in out and "第 2 步" in out
        assert "用户最近诉求" in out and "继续跑热图" in out

    def test_prefetch_history_source(self, provider, fake_history_db):
        out = provider.prefetch("继续跑热图", session_id="sess-test-1")
        assert "Related History" in out
        assert "pheatmap" in out
        assert "火山图" not in out  # 跨会话不泄漏

    def test_prefetch_history_like_fallback(self, provider, fake_history_db):
        out = provider.prefetch("QC", session_id="sess-test-1")
        assert "Related History" in out and "QC" in out

    def test_prefetch_no_hit_returns_state_only(self, provider):
        out = provider.prefetch("xyzzy-不存在-12345", session_id="sess-test-1")
        assert "Related Assets" not in out
        assert "Related History" not in out

    def test_system_prompt_block_assets(self, provider):
        provider._store.add_asset(name="qc.R", path=r"E:\x\qc.R", purpose="QC",
                                  session_id="sess-test-1", status="confirmed")
        provider._store.add_asset(name="other.R", path="/tmp/o.R", purpose="其他",
                                  session_id="sess-other", status="confirmed")
        blk = provider.system_prompt_block()
        assert "会话资产清单" in blk and "qc.R" in blk
        assert "other.R" not in blk  # 只注入本会话

    def test_prefetch_facts_source_unchanged(self, provider):
        provider._store.add_fact("用户偏好 dark theme 配色", category="pref")
        out = provider.prefetch("配色", session_id="sess-test-1")
        assert "Holographic Memory" in out and "dark theme" in out


# ---------------------------------------------------------------------------
# 4) 生产兼容：真实 memory_store.db 补表无损（只读验证）
# ---------------------------------------------------------------------------

class TestProdCompat:
    def test_real_db_opens_with_new_tables(self):
        """生产库必须能打开且新表自动补齐（只读检查，不写真实库）。"""
        import sqlite3
        from pathlib import Path
        # __file__ = webui/tests/test_session_memory.py → 上三级 = 项目根
        root = Path(__file__).resolve().parent.parent.parent
        real = root / "hermes_home" / "memory_store.db"
        if not real.exists():
            pytest.skip("生产库不存在（CI/临时环境）")
        conn = sqlite3.connect(f"file:{real}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert "assets" in tables and "session_state" in tables
            assert "facts" in tables  # 原表保留
        finally:
            conn.close()
