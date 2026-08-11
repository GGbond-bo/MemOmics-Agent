# -*- coding: utf-8 -*-
"""会话自动标题总结回归测试：内容感知总结、手动名保护、防抖防重入、持久化。

不变量：
- 用户手动改名（title_source=manual）后，自动总结永不覆盖；
- 自动总结每 5 条消息/分析完成触发，后台异步、失败静默；
- 撞名自动续号（state.db title 唯一约束不炸）；
- title_source 经 kv 表持久化，重启可恢复。
"""
import uuid
import httpx
import pytest

import server

pytestmark = pytest.mark.api


def _inject_user_msgs(sid, n):
    s = server._sessions[sid]
    for i in range(n):
        s["messages"].append({
            "role": "user",
            "content": f"第{i + 1}条消息：分析人类骨骼肌单细胞数据",
            "time": "",
        })


class FakeResp:
    """mock chat/completions 响应：固定总结出一个标题"""

    def __init__(self, title="人类骨骼肌单细胞分析"):
        self._title = title

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._title}}]}


def test_manual_title_never_overwritten(new_session):
    """用户手动改名后，自动总结永不覆盖（title_source=manual 守卫）"""
    s = server._sessions[new_session]
    s["title"] = "我的专属会话名"
    s["title_source"] = "manual"
    server._persist_title_source(new_session, "manual")
    _inject_user_msgs(new_session, 10)
    s["_title_summary_at_msg"] = 0
    server._title_summary_locks.clear()
    server._schedule_title_summary(new_session)
    assert new_session not in server._title_summary_locks  # 没启动线程
    assert s["title"] == "我的专属会话名"  # 原封不动


def test_debounce_skips_early(new_session):
    """防抖：距上次总结不足 4 条用户消息 → 不调度"""
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    _inject_user_msgs(new_session, 5)
    s["_title_summary_at_msg"] = 3  # 距上次只有 2 条
    server._title_summary_locks.clear()
    server._schedule_title_summary(new_session)
    assert new_session not in server._title_summary_locks


def test_reentrancy_skips_running(new_session):
    """防重入：已有总结线程在跑 → 不重复调度"""
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    _inject_user_msgs(new_session, 8)
    s["_title_summary_at_msg"] = 0
    server._title_summary_locks.add(new_session)  # 模拟已有线程
    server._schedule_title_summary(new_session)
    assert new_session in server._title_summary_locks  # 集合保留，未启动新线程
    server._title_summary_locks.discard(new_session)


def test_auto_summary_updates_title(new_session, monkeypatch):
    """总结执行：mock LLM → 标题更新 + title_source=auto + state.db 同步 + WS 事件"""
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _inject_user_msgs(new_session, 8)
    s["_title_summary_at_msg"] = 0
    server._title_summary_locks.clear()
    server._auto_summarize_title(new_session)
    assert new_session not in server._title_summary_locks  # finally 清理
    assert s["title"].startswith("人类骨骼肌单细胞分析")  # 容忍其他测试留下的同名
    assert s["title_source"] == "auto"
    db = server._get_session_db()
    if db:
        assert db.get_session_title(new_session) == "人类骨骼肌单细胞分析"
    # WS 推送事件已记录（切回该会话时前端靠它刷新标题）
    evs = [m for m in s.get("progress_log", []) if m.get("type") == "session_title"]
    assert evs and evs[-1]["title"] == "人类骨骼肌单细胞分析"


def test_auto_summary_title_collision_continues(new_session, monkeypatch):
    """撞名：state.db title 唯一约束 → 自动续号而非失败（用唯一标题，避免跨进程残留撞名）"""
    s = server._sessions[new_session]
    s["title_source"] = "auto"
    s["title"] = "pytest-初始标题"
    _inject_user_msgs(new_session, 8)
    s["_title_summary_at_msg"] = 0
    db = server._get_session_db()
    other = None
    collide_title = f"人类骨骼肌单细胞分析-{uuid.uuid4().hex[:4]}"
    try:
        if db:
            other = server._create_session(title=f"占位-{uuid.uuid4().hex[:4]}")["id"]
            db.set_session_title(other, collide_title)  # 占用同名
        server._title_summary_locks.clear()
        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp(collide_title))
        server._auto_summarize_title(new_session)
        assert s["title"].startswith(collide_title)
        assert s["title"] != collide_title  # 已续号
    finally:
        if other:
            server._sessions.pop(other, None)
            if db:
                try:
                    db.set_session_title(other, None)  # 清掉 db 里的标题，释放唯一约束
                except Exception:
                    pass


def test_title_source_kv_roundtrip(new_session):
    """kv 持久化：manual/auto 标记可恢复；未标记会话默认 auto（历史兼容）"""
    server._persist_title_source(new_session, "manual")
    assert server._load_title_source(new_session) == "manual"
    server._persist_title_source(new_session, "auto")
    assert server._load_title_source(new_session) == "auto"
    assert server._load_title_source(f"memomics-{uuid.uuid4().hex[:8]}") == "auto"
