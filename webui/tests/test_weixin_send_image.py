# -*- coding: utf-8 -*-
"""POST /api/weixin/send_image 回归测试（2026-09-25）。

为什么要有这个接口：/api/weixin/send 只能发文本，图片发送只存在于进程内（_send_weixin_image），
于是「computer_use 截图 → 发微信」在纯聊天会话里没有出口 —— 聊天会话不创建 results 目录，
_scan_new_figures() 扫不到图，自动推图那条路根本不会触发。这个出口必须做到：
只发图片、文件必须存在、失败要说清原因、限流仍由 _gate_weixin_send 兜底。
"""
import asyncio
import json
import os

import pytest
from fastapi.responses import JSONResponse

from webui import server as srv


def _call(body):
    """直接调用路由协程，返回 (status_code, payload)。"""
    resp = asyncio.run(srv.weixin_send_image(body))
    if isinstance(resp, JSONResponse):
        return resp.status_code, json.loads(resp.body.decode("utf-8"))
    return 200, resp


@pytest.fixture()
def wired(monkeypatch):
    """把适配器与发送函数换成假的，返回记录列表。"""
    calls = []
    msgs = []

    async def _fake_send(path, caption=""):
        calls.append({"path": path, "caption": caption})
        return True

    monkeypatch.setattr(srv, "_weixin_adapter", object())
    monkeypatch.setattr(srv, "_send_weixin_image", _fake_send)
    monkeypatch.setattr(srv, "_append_weixin_msg", lambda m: msgs.append(m))
    return calls, msgs


def test_missing_path_is_400():
    code, body = _call({})
    assert code == 400 and body["ok"] is False and "path" in body["error"]


def test_non_image_extension_rejected(tmp_path, wired):
    calls, _ = wired
    p = tmp_path / "note.txt"
    p.write_text("hi", encoding="utf-8")
    code, body = _call({"path": str(p)})
    assert code == 400
    assert "只允许图片文件" in body["error"]
    assert calls == [], "非图片文件绝不能触发发送"


def test_missing_file_is_404(wired, tmp_path):
    code, body = _call({"path": str(tmp_path / "nope.png")})
    assert code == 404 and "不存在" in body["error"]


def test_success_sends_and_records(tmp_path, wired):
    calls, msgs = wired
    p = tmp_path / "shot.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    code, body = _call({"path": str(p), "caption": "🖼️ 桌面截图"})
    assert code == 200 and body["ok"] is True
    assert body["bytes"] == p.stat().st_size
    assert calls == [{"path": str(p), "caption": "🖼️ 桌面截图"}]
    assert msgs and msgs[0]["direction"] == "out" and "shot.png" in msgs[0]["text"]


def test_send_failure_reports_throttle_reason(tmp_path, monkeypatch):
    async def _fail(path, caption=""):
        return False
    monkeypatch.setattr(srv, "_weixin_adapter", object())
    monkeypatch.setattr(srv, "_send_weixin_image", _fail)
    p = tmp_path / "shot.png"
    p.write_bytes(b"x")
    code, body = _call({"path": str(p)})
    assert code == 200 and body["ok"] is False
    assert "限流" in body["error"]


def test_adapter_missing_reports_not_connected(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_weixin_adapter", None)
    p = tmp_path / "shot.png"
    p.write_bytes(b"x")
    code, body = _call({"path": str(p)})
    assert code == 200 and body["ok"] is False and "未连接" in body["error"]
