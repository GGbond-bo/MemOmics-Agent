# -*- coding: utf-8 -*-
"""应用内重启端点与忙守卫（2026-10-13）。

用户口径（2026-10-13 勾选）：
  * 有任务在跑 → **拒绝**重启并列出在跑的任务（force=true 才强制）；
  * 只在"监管模式"下自动重启：服务以退出码 77 退出（并落盘 .restart_pending 兜底），
    由 启动.bat / start*.sh 自动重跑；
  * 非监管模式（手工 python webui/server.py）返回可操作指引，绝不自我退出。

监管判定为什么用"文件标记 + 环境变量"双通道：Windows 上 .venv/Scripts/python.exe 可能只是
转发器，会再起一个基础解释器承载真实进程，那条链路可能丢环境变量；标记文件丢不了。

测试注意：真实 `_schedule_restart_exit()` 会 os._exit(77) 杀掉 pytest 进程，
所有会走到它的用例都必须先 monkeypatch 掉（或用超长 delay）。
"""
import os
import time

import server


def _patch_exit(monkeypatch):
    called = {"exit": False}

    def _fake(*a, **k):
        called["exit"] = True

    monkeypatch.setattr(server, "_schedule_restart_exit", _fake)
    return called


def test_busy_refuses_restart_and_lists_tasks(client, monkeypatch):
    """有会话任务在跑 → 409 + 任务清单，且不触发退出。"""
    called = _patch_exit(monkeypatch)
    monkeypatch.setattr(server, "_is_supervised", lambda: True)
    monkeypatch.setattr(server, "_restart_busy_items",
                        lambda: [{"kind": "session", "id": "s1", "title": "airway DESeq2 正在跑"}])

    r = client.post("/api/system/restart", json={"confirmed": True})
    assert r.status_code == 409, r.text
    d = r.json()
    assert d["ok"] is False and d["busy"] and d["busy"][0]["id"] == "s1"
    assert called["exit"] is False, "忙时不得触发退出"


def test_force_overrides_busy(client, monkeypatch):
    """force=true（前端二次确认后）可强制重启。"""
    called = _patch_exit(monkeypatch)
    monkeypatch.setattr(server, "_is_supervised", lambda: True)
    monkeypatch.setattr(server, "_restart_busy_items",
                        lambda: [{"kind": "dcs_download", "id": "j9", "title": "下载中"}])

    r = client.post("/api/system/restart", json={"confirmed": True, "force": True})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert called["exit"] is True


def test_not_supervised_returns_actionable_hint(client, monkeypatch):
    """非监管模式：返回指引且不退出（避免"自己关掉自己"）。"""
    called = _patch_exit(monkeypatch)
    monkeypatch.setattr(server, "_is_supervised", lambda: False)
    monkeypatch.setattr(server, "_restart_busy_items", lambda: [])

    r = client.post("/api/system/restart", json={"confirmed": True})
    assert r.status_code == 400, r.text
    assert "监管" in (r.json().get("error") or "")
    assert r.json().get("hint")
    assert called["exit"] is False


def test_idle_supervised_restart_succeeds(client, monkeypatch):
    called = _patch_exit(monkeypatch)
    monkeypatch.setattr(server, "_is_supervised", lambda: True)
    monkeypatch.setattr(server, "_restart_busy_items", lambda: [])

    r = client.post("/api/system/restart", json={"confirmed": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True and d["restart_in"] > 0 and d["pid"] > 0
    assert called["exit"] is True


def test_is_supervised_env_and_marker(tmp_path, monkeypatch):
    """双通道判定：环境变量 / 标记文件（新鲜）都算监管；过期或缺失不算。"""
    marker = tmp_path / ".launcher_supervised"
    monkeypatch.setattr(server, "_supervised_marker_path", lambda: str(marker))
    monkeypatch.delenv("MEMOMICS_SUPERVISED", raising=False)

    assert server._is_supervised() is False, "无标记、无环境变量 → 不算监管"

    marker.write_text("supervised", encoding="utf-8")
    assert server._is_supervised() is True, "新鲜标记 → 监管"

    old = time.time() - 7 * 3600
    os.utime(marker, (old, old))
    assert server._is_supervised() is False, "超过 6 小时的旧标记 → 不算监管"

    monkeypatch.setenv("MEMOMICS_SUPERVISED", "1")
    assert server._is_supervised() is True, "环境变量通道"


def test_restart_exit_writes_pending_marker(tmp_path, monkeypatch):
    """重启前必须落盘 .restart_pending（防上层转发器吞掉退出码 77）。"""
    pending = tmp_path / ".restart_pending"
    monkeypatch.setattr(server, "_restart_pending_path", lambda: str(pending))
    monkeypatch.setattr(server, "_RESTART_DELAY_SEC", 3600.0)   # 别真退出：线程等 1 小时（daemon）

    server._schedule_restart_exit()
    for _ in range(20):
        if pending.exists():
            break
        time.sleep(0.05)
    assert pending.exists(), "未写入 .restart_pending"
    assert "pid=" in pending.read_text(encoding="utf-8")


def test_busy_items_detects_update_task(monkeypatch):
    """真实 _restart_busy_items：更新任务在跑也要算忙。"""
    monkeypatch.setattr(server, "_sessions", {})
    monkeypatch.setattr(server, "_dcs_dl_call", lambda *a, **k: {"jobs": []})
    monkeypatch.setitem(server._UPDATE_TASK, "running", True)
    try:
        items = server._restart_busy_items()
    finally:
        server._UPDATE_TASK["running"] = False
    assert any(i["kind"] == "update" for i in items), items


def test_launchers_declare_supervised_protocol():
    """启动器必须写监管标记、并把 77 / .restart_pending 都当重启请求（打包后=启动.bat/start.sh）。"""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    raw = open(os.path.join(root, "start.bat"), "rb").read().decode("gbk", "replace")
    assert "MEMOMICS_SUPERVISED=1" in raw
    assert ".launcher_supervised" in raw
    assert 'if "%MMRC%"=="77"' in raw
    assert ".restart_pending" in raw

    for name in ("launchers/start_linux.sh", "launchers/start_macos.sh"):
        t = open(os.path.join(root, name), encoding="utf-8", errors="replace").read()
        assert "MEMOMICS_SUPERVISED=1" in t, name
        assert ".launcher_supervised" in t, name
        assert ".restart_pending" in t, name
        assert '[ "$_mmrc" = "77" ]' in t, name