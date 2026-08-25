# -*- coding: utf-8 -*-
"""结果完成契约（P0-2）：analysis_manifest 协议测试

回归目标：
- 提交 manifest 版本递增（v1 → v2），历史保留
- 服务端自动补全 schema/created_at/model/git 溯源
- list_results / api/results 返回 manifest 信息
- 参数校验（无 session_id / 非 dict → 4xx）
"""
import os
import shutil
import sys

import pytest

from conftest import cleanup_session

pytestmark = pytest.mark.integration


def _submit(client, sid, manifest, expect=200):
    r = client.post("/api/results/manifest", json={"session_id": sid, "manifest": manifest})
    assert r.status_code == expect
    return r.json()


def test_manifest_submit_and_versioning(client, new_session):
    """提交两次：版本递增 1→2，历史保留"""
    sid = new_session
    d1 = _submit(client, sid, {"title": "测试分析", "metrics": {"n_cells": 100}})
    assert d1["ok"] and d1["version"] == 1
    d2 = _submit(client, sid, {"title": "测试分析 v2", "metrics": {"n_cells": 200}})
    assert d2["ok"] and d2["version"] == 2

    base = d1["path"].replace("/", os.sep)
    assert os.path.isfile(os.path.join(base, "analysis_manifest.json"))
    assert os.path.isfile(os.path.join(base, "analysis_manifest.v1.json"))
    assert os.path.isfile(os.path.join(base, "analysis_manifest.v2.json"))


@pytest.mark.skipif(sys.platform != "win32", reason="manifest 自动溯源依赖本机 git/路径语义")
def test_manifest_auto_provenance(client, new_session):
    """自动补全：schema/version/created_at/model/git"""
    sid = new_session
    d = _submit(client, sid, {"title": "溯源测试"})
    base = d["path"].replace("/", os.sep)
    import json as _json
    with open(os.path.join(base, "analysis_manifest.json"), encoding="utf-8") as f:
        m = _json.load(f)
    assert m["schema"] == "memomics.analysis_manifest.v1"
    assert m["version"] == 1
    assert m["created_at"]
    assert m["model"]["model"]  # 当前模型名
    assert m["provenance"]["git"]["commit"]  # git commit
    assert "dirty" in m["provenance"]["git"]


def test_list_results_returns_manifest(client, new_session):
    """list_results 返回 manifest + 版本列表"""
    sid = new_session
    _submit(client, sid, {"title": "面板测试", "metrics": {"auc": 0.9},
                          "artifacts": [{"path": "Figures/pca.png", "type": "figure"}]})
    r = client.get(f"/api/results/{sid}")
    assert r.status_code == 200
    d = r.json()
    assert d["manifest"]["title"] == "面板测试"
    assert d["manifest"]["metrics"]["auc"] == 0.9
    assert d["manifest_versions"] == [1]


def test_results_list_has_manifest_flag(client, new_session):
    """会话结果列表标记 has_manifest"""
    sid = new_session
    _submit(client, sid, {"title": "列表标记"})
    all_r = client.get("/api/results").json()["sessions"]
    mine = [s for s in all_r if s["results_dir"].endswith(sid)]
    assert mine, "测试会话结果未出现在 /api/results"
    assert mine[0]["has_manifest"] is True
    assert mine[0]["manifest_versions"] == [1]


def test_manifest_validation(client):
    """参数校验：无 session_id / manifest 非 dict → 4xx"""
    r = client.post("/api/results/manifest", json={"manifest": {"title": "x"}})
    assert r.status_code == 400
    r2 = client.post("/api/results/manifest", json={"session_id": "memomics-test", "manifest": "not-a-dict"})
    assert r2.status_code == 400
    cleanup_session("memomics-test")  # 防御：可能创建了目录
