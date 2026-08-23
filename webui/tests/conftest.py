# -*- coding: utf-8 -*-
"""pytest 公共设施：sys.path + TestClient + 测试会话工厂

所有测试都是 offline（本地 server），不需要外部资源。
TestClient 触发 FastAPI lifespan（startup 播种为后台线程，秒回）。
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# hermes-agent（tools/ 模块）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "hermes-agent"))

import pytest
from fastapi.testclient import TestClient

import server


@pytest.fixture(scope="module")
def client():
    """TestClient：module 级共享（每个测试文件一次 lifespan）"""
    with TestClient(server.app) as c:
        yield c


def cleanup_session(sid):
    """删除测试会话（内存 + state.db），保持生产环境干净"""
    server._sessions.pop(sid, None)
    try:
        db = server._get_session_db()
        if db:
            db.delete_session(sid)
    except Exception:
        pass
    # 清理测试结果目录（results/<sid> 或含短 id 的目录）
    try:
        import shutil as _sh
        _shutil = _sh
        for cand in (os.path.join(server.RESULTS_DIR, sid),):
            if os.path.isdir(cand):
                _shutil.rmtree(cand, ignore_errors=True)
        short = sid.split("-")[-1] if "-" in sid else ""
        if short and os.path.isdir(server.RESULTS_DIR):
            for p in os.listdir(server.RESULTS_DIR):
                if short in p and os.path.isdir(os.path.join(server.RESULTS_DIR, p)):
                    _shutil.rmtree(os.path.join(server.RESULTS_DIR, p), ignore_errors=True)
    except Exception:
        pass


@pytest.fixture()
def new_session(client):
    """创建测试会话，测试后清理（内存 + state.db）"""
    r = client.post("/api/sessions/new", params={"title": f"pytest-回归-{uuid.uuid4().hex[:6]}"})
    assert r.status_code == 200
    sid = r.json()["id"]
    yield sid
    cleanup_session(sid)


@pytest.fixture()
def kb_graph(client):
    """图谱数据 fixture（只请求一次，供多个断言复用）"""
    r = client.get("/api/kb/graph")
    assert r.status_code == 200
    return r.json()
