# -*- coding: utf-8 -*-
"""科学文献连接器测试（P1-6）

- 单元：provenance 结构、OpenAlex abstract 重建、参数校验（离线）
- 网络（@pytest.mark.network）：真实 arXiv/OpenAlex 请求（默认排除）
"""
import pytest

from tools.science_connectors import _provenance, _reconstruct_abstract, arxiv_search, openalex_search

pytestmark = pytest.mark.unit


def test_provenance_structure():
    p = _provenance("arxiv", "single cell")
    assert p == {"source": "arxiv", "query": "single cell", "fetched_at": p["fetched_at"]}
    assert p["fetched_at"]


def test_reconstruct_abstract():
    inv = {"Hello": [0], "world": [1], "of": [2], "science": [3]}
    assert _reconstruct_abstract(inv) == "Hello world of science"
    assert _reconstruct_abstract(None) == ""
    assert _reconstruct_abstract({}) == ""


def test_arxiv_error_path(monkeypatch):
    """网络失败返回结构化 error（不抛异常）"""
    def _boom(url, timeout=20):
        raise OSError("connection refused")
    import tools.science_connectors as sc
    monkeypatch.setattr(sc.urllib.request, "urlopen", _boom)
    r = arxiv_search("cell", limit=3)
    assert r["total"] == 0 and r["results"] == [] and "error" in r


def test_openalex_error_path(monkeypatch):
    import tools.science_connectors as sc

    def _boom(url, timeout=20):
        raise OSError("timeout")
    monkeypatch.setattr(sc, "_fetch_json", _boom)
    r = openalex_search("cancer", limit=3)
    assert r["total"] == 0 and r["results"] == [] and "error" in r


# ============ 网络测试（默认排除：pytest -m network 手动跑） ============

@pytest.mark.network
def test_arxiv_live():
    r = arxiv_search("single cell rna seq", limit=2)
    assert r["total"] > 0
    rec = r["results"][0]
    assert rec["title"] and rec["source"] == "arxiv" and rec["fetched_at"]


@pytest.mark.network
def test_openalex_live():
    r = openalex_search("cellular senescence", limit=2)
    assert r["total"] > 0
    rec = r["results"][0]
    assert rec["title"] and rec["source"] == "openalex" and rec["fetched_at"]


@pytest.mark.network
def test_api_endpoint_live(client):
    """server /api/science/search 端点（带溯源）"""
    r = client.get("/api/science/search", params={"q": "aging", "source": "openalex", "limit": 2})
    assert r.status_code == 200
    d = r.json()
    assert d["total"] > 0
    assert d["results"][0]["source"] == "openalex"
