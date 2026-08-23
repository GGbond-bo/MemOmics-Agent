# -*- coding: utf-8 -*-
"""模型切换测试

回归目标（8-08 修复链）：
- 交互框下拉框按供应商分组、只列有 key 的模型
- 会话级切换只影响该会话、不污染全局（展示与实际一致）
- 未知模型返回 400（明确报错而非静默失败）
"""
import pytest

import server

pytestmark = pytest.mark.models


def test_models_available_grouped(client):
    """下拉框分组数据源：≥3 供应商、全部有 key"""
    r = client.get("/api/models/available")
    assert r.status_code == 200
    models = r.json()["models"]
    assert len(models) >= 20, f"有 key 模型数异常: {len(models)}"
    groups = {}
    for m in models:
        groups.setdefault(m["provider_name"], 0)
        groups[m["provider_name"]] += 1
    assert len(groups) >= 3, f"供应商分组不足: {list(groups)}"
    # 每个模型都属于已保存 key 的 provider
    keyed = {pid for pid, s in server._provider_keys.items() if s.get("api_key")}
    for m in models:
        assert m["provider_id"] in keyed, f"{m['id']} 的 provider 无 key"


def test_models_available_current_flag(client, new_session):
    """is_current 优先按会话级配置（回归：设置页 ●当前 标错）"""
    sid = new_session
    r = client.get("/api/models/available", params={"session_id": sid})
    models = r.json()["models"]
    # 无会话级配置时回退全局 current
    current = [m for m in models if m.get("is_current")]
    assert current, "应存在当前模型"


def test_models_switch_session_level(client, new_session):
    """会话级切换：只影响该会话 + 切换后 current 正确"""
    sid = new_session
    avail = client.get("/api/models/available", params={"session_id": sid}).json()["models"]
    assert avail, "无可切换模型"
    target = avail[0]
    r = client.post("/api/models/switch", json={"model": target["id"], "session_id": sid})
    assert r.status_code == 200
    after = client.get("/api/models/available", params={"session_id": sid}).json()["models"]
    current = [m for m in after if m.get("is_current")]
    assert current and current[0]["id"] == target["id"], \
        f"切换后 current 应为 {target['id']}，实际 {[m['id'] for m in current]}"


def test_models_switch_unknown_400(client, new_session):
    """未知模型明确报错（回归：静默失败 → 400）"""
    sid = new_session
    r = client.post("/api/models/switch", json={"model": "no-such-model-xyz", "session_id": sid})
    assert r.status_code == 400


# ==================== P2 本地模型自动发现 ====================

def test_local_models_structure(client):
    """探测端点返回结构（无本地服务器时 count=0 也合法）"""
    r = client.get("/api/models/local")
    assert r.status_code == 200
    d = r.json()
    assert "models" in d and "count" in d
    assert d["count"] == len(d["models"])


def test_local_models_detection(client, monkeypatch):
    """模拟 Ollama 在 11434 响应 → 探测到模型 + base_url 正确"""
    import io
    import json as _json

    class FakeResp:
        def __init__(self, data):
            self._data = data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._data

    def fake_urlopen(req, timeout=2):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "11434" in url:
            return FakeResp(_json.dumps({"data": [{"id": "qwen3:8b"}, {"id": "llama3"}]}).encode())
        raise OSError("not listening")

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", fake_urlopen)
    d = client.get("/api/models/local").json()
    assert d["count"] == 2
    ids = [m["id"] for m in d["models"]]
    assert "qwen3:8b" in ids
    assert d["models"][0]["server"] == "ollama"
    assert d["models"][0]["base_url"] == "http://127.0.0.1:11434/v1"


def test_add_local_provider(client, tmp_path, monkeypatch):
    """保存本地模型 provider：loopback 校验 + 免 key 出现在 available"""
    import server as _srv
    monkeypatch.setattr(_srv, "_PROVIDER_KEYS_FILE", str(tmp_path / "keys.json"))
    r = client.post("/api/provider/local", json={
        "model": "qwen3:8b", "base_url": "http://127.0.0.1:11434/v1", "server": "ollama"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] and d["provider_id"] == "local-ollama"
    # 免 key 模型出现在 available
    avail = client.get("/api/models/available").json()["models"]
    local = [m for m in avail if m["provider_id"] == "local-ollama"]
    assert local and local[0]["id"] == "qwen3:8b"
    # 非 loopback 拒绝
    r2 = client.post("/api/provider/local", json={
        "model": "x", "base_url": "http://evil.com/v1", "server": "evil"})
    assert r2.status_code == 400
    # 清理（恢复原 provider_keys）
    _srv._provider_keys.pop("local-ollama", None)
    _srv._PROVIDERS_INDEX.pop("local-ollama", None)
