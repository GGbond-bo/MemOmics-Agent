# -*- coding: utf-8 -*-
"""通用 API 面测试：health / version / results"""
import pytest

pytestmark = pytest.mark.api


def test_health_returns_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert "MemOmics" in d["service"]


def test_version_returns_commit_and_started(client):
    """footer 版本号依赖此接口（回归：改完代码确认 server 已加载新版本）"""
    r = client.get("/api/version")
    assert r.status_code == 200
    d = r.json()
    assert d.get("version"), "version 缺失（git commit）"
    assert d.get("started"), "started 缺失（server 启动时间）"


def test_results_list_shape(client):
    r = client.get("/api/results")
    assert r.status_code == 200
    d = r.json()
    assert "sessions" in d
    assert isinstance(d["sessions"], list)


def test_index_serves_webui(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "MemOmics" in r.text
