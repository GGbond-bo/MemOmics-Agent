# -*- coding: utf-8 -*-
"""T9 守卫：后台任务面板的 WebSocket 订阅（面板进视图订阅、切走退订）。

为什么要有这条链路：面板原来每 2 秒轮询 /api/tasks，多开几个标签就是几份重复扫描，
任务一多就成了页面自己给自己加压。改成订阅制后：
  - 订阅当场回一份快照（首屏不空）；
  - 之后服务端只在「契约目录指纹」变化时推整份列表；
  - 退订 / 断线就把连接摘掉，不往死连接推。

真机端到端推送（真起任务、真收推送）在 T9 实测记录里；
这里锁死订阅协议本身：快照形状、与 HTTP 路由同源、退订摘连接、指纹会随契约变化。
"""
import importlib.util
import json
import os
import sys
import time

import pytest

import server

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
TRCLI = os.path.join(_REPO, "memomics", "bio_tools", "task_run.py")


def _tr():
    try:
        from memomics.bio_tools import task_run
        return task_run
    except Exception:
        spec = importlib.util.spec_from_file_location("task_run_ws", TRCLI)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


@pytest.fixture()
def tr():
    return _tr()


@pytest.fixture()
def home(tmp_path, monkeypatch):
    h = tmp_path / "hermes_home"
    (h / "runtime" / "tasks").mkdir(parents=True)
    monkeypatch.setattr(server, "HERMES_HOME_DIR", str(h))
    return h


@pytest.fixture()
def tasks_dir(home):
    return str(home / "runtime" / "tasks")


def _make(tr, tasks_dir, **kw):
    tr.TASKS_DIR = tasks_dir
    tr.FALLBACK_LOG_DIR = os.path.join(os.path.dirname(tasks_dir), "logs")
    os.makedirs(tr.FALLBACK_LOG_DIR, exist_ok=True)
    kw.setdefault("type", "qc")
    kw.setdefault("title", "WS 任务")
    return tr.new_task(**kw)


def test_w1_subscribe_returns_snapshot_same_shape_as_http(client, tr, tasks_dir):
    """订阅当场回快照，字段与 GET /api/tasks 同源（面板一套渲染代码吃两种来源）。"""
    t = _make(tr, tasks_dir, title="WS 快照")
    with client.websocket_connect("/ws") as sock:
        sock.send_text(json.dumps({"type": "task_subscribe"}))
        msg = json.loads(sock.receive_text())
        assert msg.get("type") == "tasks", msg.keys()
        assert msg.get("ok") is True
        ids = [row.get("task_id") for row in msg.get("tasks") or []]
        assert t.task_id in ids
        assert msg.get("api_token") and msg.get("tasks_dir")
        http = client.get("/api/tasks?refresh=1&limit=100").json()
        assert set(msg["counts"]) == set(http["counts"])
        push_row = [r for r in msg["tasks"] if r["task_id"] == t.task_id][0]
        http_row = [r for r in http["tasks"] if r["task_id"] == t.task_id][0]
        assert set(push_row) == set(http_row), "推送与 HTTP 的卡片字段必须一致"


def test_w2_unsubscribe_and_disconnect_drop_the_socket(client, tr, tasks_dir):
    """退订就摘；WS 断开也摘 —— 否则扫描循环会往死连接推、白烧 CPU。"""
    _make(tr, tasks_dir, title="WS 退订")
    server._TASK_WS_CLIENTS.clear()
    with client.websocket_connect("/ws") as sock:
        sock.send_text(json.dumps({"type": "task_subscribe"}))
        sock.receive_text()
        assert len(server._TASK_WS_CLIENTS) == 1
        sock.send_text(json.dumps({"type": "task_unsubscribe"}))
        for _ in range(50):
            if not server._TASK_WS_CLIENTS:
                break
            time.sleep(0.02)
        assert server._TASK_WS_CLIENTS == set(), "退订后还挂在订阅表里"
    for _ in range(50):
        if not server._TASK_WS_CLIENTS:
            break
        time.sleep(0.02)
    assert server._TASK_WS_CLIENTS == set(), "WS 断开后没摘掉订阅"


def test_w3_fingerprint_tracks_contract_changes(tr, tasks_dir):
    """指纹不变就不推、变了才推 —— 这条是「只在真变化时推送」的全部依据。"""
    before = server._tasks_fingerprint()
    t = _make(tr, tasks_dir, title="WS 指纹")
    after_new = server._tasks_fingerprint()
    assert after_new != before, "新增契约后指纹必须变"
    t.data["progress"] = {"value": 0.42, "text": "推送验证"}
    t.flush()
    after_flush = server._tasks_fingerprint()
    assert after_flush != after_new, "契约 flush 后指纹必须变"
    assert server._tasks_fingerprint() == after_flush, "没动的两次指纹必须一样"


def test_w4_payload_marks_read_failure_instead_of_lying(monkeypatch):
    """模块不可用时载荷必须 ok=False —— 面板宁可显示空列表，也不能拿假数据当真。"""
    monkeypatch.setattr(server, "_task_run", lambda: None)
    payload = server._tasks_payload(limit=10)
    assert payload["ok"] is False and payload["tasks"] == []
    assert "不可用" in payload["error"]
