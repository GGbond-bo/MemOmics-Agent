# -*- coding: utf-8 -*-
"""刷新不该再"多一个空会话"：WS 只读/控制类消息禁止隐式建会话（2026-10-12）。

用户反馈：「更新后的版本，刷新就弹出欢迎框」。真因不是欢迎画面本身，而是一条链：
  * 前端 ws.onopen 里立刻调 refreshContextUsage()，发的是
    `{type:'get_context_usage', session_id: null}`（那一刻 currentSid 还没选好）；
  * 后端 ws_endpoint 对**所有**消息都走 `_get_or_create_session(sid)`，而
    `_get_or_create_session(None)` → `_create_session()`，会**新建一个空「新会话」**；
  * 于是每刷新一次就留下一个空会话；下一次刷新 autoSelectLatestSession 又优先选中
    最新那条空会话 → 用户只看到欢迎画面（"刷新就弹欢迎框"）。

本文件锁死三件事：
  ① 无 session_id 的只读/控制消息 → 回 error，**不建会话**；
  ② 指向不存在会话的 switch_session → 回 error，**不建会话**（不偷偷新建顶上）；
  ③ chat 这条老路仍允许隐式建会话 —— 反向守卫，别把隐式建会话一刀切掉。
"""
import json

import server


def _session_keys():
    return set(server._sessions.keys())


def test_stateless_message_without_session_id_does_not_create_session(client):
    """就是前端 onopen 发的那条 get_context_usage（无 session_id）——不许再留空会话。"""
    before = _session_keys()
    with client.websocket_connect("/ws") as sock:
        sock.send_text(json.dumps({"type": "get_context_usage"}))
        msg = json.loads(sock.receive_text())
    assert msg.get("type") == "error", msg
    assert "session_id" in (msg.get("content") or ""), msg
    assert _session_keys() == before, "只读消息不得隐式新建会话"


def test_switch_to_unknown_session_is_rejected_not_created(client):
    """指向不存在会话的切换：回错，而不是新建一个空会话顶上（并污染下一次刷新）。"""
    before = _session_keys()
    with client.websocket_connect("/ws") as sock:
        sock.send_text(json.dumps({"type": "switch_session",
                                   "session_id": "no-such-session-xyz"}))
        msg = json.loads(sock.receive_text())
    assert msg.get("type") == "error", msg
    assert _session_keys() == before, "不存在的会话不得偷偷新建一个顶上"


def test_chat_still_allows_implicit_session(client, monkeypatch):
    """反向守卫：chat / steer 的隐式建会话必须保留（首条消息、会话恢复都靠它）。"""
    called = {}

    def _spy(sid=None):
        called["sid"] = sid
        raise RuntimeError("SPY_STOP")

    monkeypatch.setattr(server, "_get_or_create_session", _spy)
    with client.websocket_connect("/ws") as sock:
        sock.send_text(json.dumps({"type": "chat", "message": "hello"}))
        msg = json.loads(sock.receive_text())
    assert "SPY_STOP" in json.dumps(msg, ensure_ascii=False), msg
    assert called.get("sid") is None