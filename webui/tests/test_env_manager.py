# -*- coding: utf-8 -*-
"""环境事务测试（P1-5）：plan/apply/rollback + 指纹 + manifest 溯源

真实 conda 操作分钟级，只测纯逻辑：快照 round-trip、plan dry-run、
错误路径（无 conda / 无快照回滚）、fingerprint 结构（本机有 conda 时只读）。
"""
import json
import os

import pytest

from tools import env_manager as em
from tools.env_manager import (
    ENVS_DIR,
    env_apply,
    env_plan,
    env_rollback,
    fingerprint,
    list_envs,
    _load_snapshot,
    _save_snapshot,
)

pytestmark = pytest.mark.unit


def test_list_envs_structure():
    envs = list_envs()
    assert isinstance(envs, list)
    if envs:
        assert "name" in envs[0] and "path" in envs[0]


def test_fingerprint_structure():
    f = fingerprint("base")
    assert "conda_env" in f and "packages" in f and "available" in f
    assert isinstance(f["packages"], dict)


def test_snapshot_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "ENVS_DIR", str(tmp_path))
    _save_snapshot("test-env", "pre", {"conda_env": "test-env", "packages": {"numpy": "1.26"}})
    got = _load_snapshot("test-env", "pre")
    assert got == {"conda_env": "test-env", "packages": {"numpy": "1.26"}}
    assert _load_snapshot("test-env", "post") is None


def test_env_plan_dry_run(monkeypatch):
    monkeypatch.setattr(em, "list_envs", lambda: [{"name": "existing", "path": "/x"}])
    p = env_plan("existing", packages=["numpy"])
    assert p["dry_run"] is True
    assert p["exists"] is True
    assert p["action"] == "update"  # create 时已存在 → update
    assert "apply_command" in p and "ops" in p
    p2 = env_plan("brand-new", packages=["numpy"])
    assert p2["action"] == "create"
    assert p2["exists"] is False


def test_env_apply_no_conda(monkeypatch):
    monkeypatch.setattr(em, "_conda_bin", lambda: None)
    r = env_apply("whatever", packages=["numpy"])
    assert r["ok"] is False
    assert "conda" in r["error"]


def test_env_rollback_no_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "ENVS_DIR", str(tmp_path))
    r = env_rollback("no-snapshot-env")
    assert r["ok"] is False
    assert "无 pre 快照" in r["error"]


def test_env_rollback_no_conda(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "ENVS_DIR", str(tmp_path))
    _save_snapshot("roll-env", "pre", {"conda_env": "roll-env", "python": "3.10",
                                       "packages": {"numpy": "1.26"}})
    monkeypatch.setattr(em, "_conda_bin", lambda: None)
    r = env_rollback("roll-env")
    assert r["ok"] is False
    assert "conda" in r["error"]


def test_manifest_env_provenance(client, new_session):
    """manifest 溯源自动补全 env 指纹（CONDA_DEFAULT_ENV 存在时）"""
    import os as _os
    if not _os.environ.get("CONDA_DEFAULT_ENV"):
        pytest.skip("无 CONDA_DEFAULT_ENV")
    r = client.post("/api/results/manifest", json={
        "session_id": new_session, "manifest": {"title": "env 溯源测试"}})
    assert r.status_code == 200
    base = r.json()["path"].replace("/", os.sep)
    with open(os.path.join(base, "analysis_manifest.json"), encoding="utf-8") as f:
        m = json.load(f)
    assert m["provenance"]["env"]["conda_env"] == _os.environ["CONDA_DEFAULT_ENV"]
    assert isinstance(m["provenance"]["env"]["packages"], dict)
