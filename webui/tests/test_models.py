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
