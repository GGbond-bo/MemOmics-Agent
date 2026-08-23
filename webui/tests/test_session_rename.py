# -*- coding: utf-8 -*-
"""会话改名回归测试：改名只动 title 字段，sid 是唯一身份锚点。

验证不变量：六条链路（会话恢复 / 结果目录 / 模型绑定 / 心跳 / 后台任务 / WS 分流）
全部按 sid 寻址——改名后 sid 必须不变、state.db 必须持久化、同名必须友好报错。
"""
import pytest

import server

pytestmark = pytest.mark.api


def test_rename_ok(new_session, client):
    """改名成功：内存 + state.db 双写，返回新 title"""
    r = client.post(f"/api/sessions/{new_session}/rename", json={"title": "衰老单细胞分析"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["title"] == "衰老单细胞分析"
    # 内存同步
    assert server._sessions[new_session]["title"] == "衰老单细胞分析"
    # state.db 持久化（重启后可恢复）
    db = server._get_session_db()
    if db:
        assert db.get_session_title(new_session) == "衰老单细胞分析"


def test_rename_sid_unchanged(new_session, client):
    """改名后 sid 不变——目录/恢复/WS/心跳/后台全按 sid 寻址的前提"""
    r = client.post(f"/api/sessions/{new_session}/rename", json={"title": "改名后"})
    assert r.status_code == 200
    assert r.json()["session_id"] == new_session
    # 会话列表仍可正常加载（对接不断）
    r2 = client.get("/api/sessions")
    assert r2.status_code == 200
    assert any(s["id"] == new_session for s in r2.json()["sessions"])


def test_rename_empty_rejected(new_session, client):
    """空白名拒绝（空串/纯空格归一化）"""
    r = client.post(f"/api/sessions/{new_session}/rename", json={"title": "   "})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_rename_unknown_session(client):
    """不存在的会话 → 404"""
    r = client.post("/api/sessions/does-not-exist-xyz/rename", json={"title": "x"})
    assert r.status_code == 404


def test_rename_duplicate_conflict(new_session, client):
    """同名冲突必须友好失败，不能静默覆盖（Hermes sessions 表 title 唯一约束）"""
    # 把 new_session 改成一个唯一名，再用另一个会话撞它
    r1 = client.post(f"/api/sessions/{new_session}/rename", json={"title": "撞名测试会话"})
    assert r1.json()["ok"] is True
    r2 = client.post("/api/sessions/new", params={"title": "pytest-撞名-临时"})
    sid2 = r2.json()["id"]
    try:
        r = client.post(f"/api/sessions/{sid2}/rename", json={"title": "撞名测试会话"})
        d = r.json()
        # 不能静默成功；必须 ok=False 或 409
        assert not (d.get("ok") is True)
        # 且 sid2 的 title 未被污染
        assert server._sessions[sid2]["title"] != "撞名测试会话"
    finally:
        from conftest import cleanup_session
        cleanup_session(sid2)
