# -*- coding: utf-8 -*-
"""知识库测试：图谱 / 浏览 / 搜索 / 物种结构

回归目标：
- 图谱接口结构稳定（3D 星球/2D 平面/物种按钮都依赖它）
- 顶层物种完整（Homo_sapiens 等）
- 目录浏览与全文搜索可用
"""
import pytest

pytestmark = pytest.mark.kb


def test_kb_graph_structure(kb_graph):
    """图谱数据结构：节点/边/计数（3D 与 2D 渲染的数据源）"""
    nodes, edges = kb_graph["nodes"], kb_graph["edges"]
    assert len(nodes) >= 100, f"节点数异常: {len(nodes)}"
    assert len(edges) >= 100, f"边数异常: {len(edges)}"
    assert kb_graph["counts"]["nodes"] == len(nodes)
    # 节点字段完整（渲染依赖 id/label/type/path）
    for n in nodes[:5]:
        assert "id" in n and "label" in n and "type" in n


def test_kb_graph_has_species(kb_graph):
    """顶层物种存在（物种按钮栏的数据源）"""
    ids = {n["id"] for n in kb_graph["nodes"]}
    for sp in ("Homo_sapiens", "Mus_musculus", "zebrafish"):
        assert sp in ids, f"物种 {sp} 缺失"


def test_kb_graph_species_hierarchy(kb_graph):
    """物种层级：Homo_sapiens 应包含子节点（人 103 节点）"""
    ids = {n["id"] for n in kb_graph["nodes"]}
    human_children = [i for i in ids if i.startswith("Homo_sapiens/")]
    assert len(human_children) >= 10, "Homo_sapiens 子节点不足"


def test_kb_browse_root(client):
    r = client.get("/api/kb")
    assert r.status_code == 200
    d = r.json()
    assert d.get("path")
    assert isinstance(d.get("items"), list)
    assert len(d["items"]) > 0


def test_kb_browse_unknown_path_404(client):
    r = client.get("/api/kb", params={"path": "Z:/definitely-not-exist-xyz"})
    assert r.status_code == 404


def test_kb_search_shape(client):
    r = client.get("/api/kb/search", params={"q": "index"})
    assert r.status_code == 200
    d = r.json()
    assert "total" in d
    assert isinstance(d["results"], list)


def test_kb_search_empty_query(client):
    r = client.get("/api/kb/search", params={"q": "  "})
    assert r.status_code == 200
    assert r.json()["total"] == 0
