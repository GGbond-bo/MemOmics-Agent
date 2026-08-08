# -*- coding: utf-8 -*-
"""会话生命周期测试

回归目标：
- 新建会话出现在列表首位（last_active 降序 → 刷新后 autoSelect 选中它）
- 会话创建接口稳定
"""
import pytest
import uuid

from conftest import cleanup_session

pytestmark = pytest.mark.sessions


def test_session_create(client):
    r = client.post("/api/sessions/new", params={"title": f"pytest 回归测试-{uuid.uuid4().hex[:6]}"})
    assert r.status_code == 200
    d = r.json()
    assert d["id"]
    assert d["title"].startswith("pytest 回归测试")
    cleanup_session(d["id"])


def test_new_session_appears_first(client):
    """新建会话排列表首位（回归：刷新后跳回旧会话的 bug 链）"""
    import time
    time.sleep(1.2)  # last_active 秒精度，确保与上个会话不同秒
    r = client.post("/api/sessions/new", params={"title": f"pytest 排序测试-{uuid.uuid4().hex[:6]}"})
    sid = r.json()["id"]
    try:
        sessions = client.get("/api/sessions").json()["sessions"]
        assert sessions[0]["id"] == sid, "新会话未排首位（last_active 排序失效）"
    finally:
        cleanup_session(sid)


def test_sessions_list_shape(client):
    r = client.get("/api/sessions")
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    assert isinstance(sessions, list)
    for s in sessions[:3]:
        assert "id" in s and "title" in s and "created" in s
