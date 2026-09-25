# -*- coding: utf-8 -*-
"""scripts/desktop_shot.py 回归测试（2026-09-25）。

computer_use 的截图只进模型上下文（base64 拼进 tool_result 图片块），不落盘；
而微信推图只认磁盘上的图片文件。desktop_shot.py 补的就是这一环，所以它必须：
字节原样落盘、父目录自动建、后端异常不静默、驱动缺失给可执行的提示。
"""
import base64
import importlib.util
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "desktop_shot.py")
PNG = b"\x89PNG\r\n\x1a\n" + b"payload" * 8


def _load():
    spec = importlib.util.spec_from_file_location("desktop_shot_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod():
    return _load()


class FakeCap(object):
    def __init__(self, b64=None, width=1568, height=882, elements=None):
        self.png_b64 = b64
        self.width = width
        self.height = height
        self.elements = elements if elements is not None else [1, 2, 3]


class FakeBackend(object):
    def __init__(self, cap=None, err=None):
        self.cap = cap if cap is not None else FakeCap(base64.b64encode(PNG).decode("ascii"))
        self.err = err
        self.started = False
        self.stopped = False
        self.calls = []

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def capture(self, mode="vision", app=None):
        self.calls.append({"mode": mode, "app": app})
        if self.err:
            raise self.err
        return self.cap


def test_capture_writes_exact_bytes_and_closes(mod, tmp_path):
    be = FakeBackend()
    out = tmp_path / "deep" / "shot.png"
    info = mod.capture_desktop(str(out), app="screen", backend=be)
    assert out.read_bytes() == PNG, "必须原样落盘，不能二次编码"
    assert info["bytes"] == len(PNG) and info["width"] == 1568 and info["elements"] == 3
    assert be.started and be.stopped and be.calls == [{"mode": "vision", "app": "screen"}]


def test_capture_stops_backend_on_failure(mod, tmp_path):
    be = FakeBackend(err=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        mod.capture_desktop(str(tmp_path / "x.png"), backend=be)
    assert be.stopped, "异常路径也必须 stop，否则驱动进程会泄漏"


def test_capture_rejects_empty_png(mod, tmp_path):
    be = FakeBackend(cap=FakeCap(b64=None))
    with pytest.raises(RuntimeError) as ei:
        mod.capture_desktop(str(tmp_path / "x.png"), app="NVIDIA Overlay", backend=be)
    assert "覆盖层" in str(ei.value)


def test_default_out_path_is_png_under_results(mod):
    p = mod.default_out_path()
    assert p.endswith(".png")
    assert os.path.join("results", "desktop_shots") in p


def test_main_success_exit_0(mod, tmp_path, monkeypatch, capsys):
    be = FakeBackend()
    monkeypatch.setattr(mod, "_backend", lambda: be)
    out = tmp_path / "a.png"
    assert mod.main(["--out", str(out), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["shot"]["path"] == str(out)
    assert out.exists()


def test_main_missing_driver_exit_2(mod, monkeypatch, capsys):
    def _boom():
        raise ImportError("cua_backend 不可用")
    monkeypatch.setattr(mod, "_backend", _boom)
    assert mod.main(["--out", "whatever.png"]) == 2
    assert "hermes computer-use install" in capsys.readouterr().err


def test_main_send_wechat_failure_exit_4(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_backend", lambda: FakeBackend())
    monkeypatch.setattr(mod, "send_to_wechat", lambda *a, **k: {"ok": False, "error": "限流"})
    assert mod.main(["--out", str(tmp_path / "b.png"), "--send-wechat"]) == 4


def test_send_to_wechat_posts_path_and_caption(mod, tmp_path, monkeypatch):
    seen = {}

    class _Resp(object):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true}'

    def _fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["body"] = json.loads(req.data.decode("utf-8"))
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    out = mod.send_to_wechat(str(tmp_path / "c.png"), "说明", url="http://127.0.0.1:8899")
    assert out == {"ok": True}
    assert seen["url"].endswith("/api/weixin/send_image")
    assert seen["body"] == {"path": str(tmp_path / "c.png"), "caption": "说明"}
def test_deps_gate_failure_hints_interpreter(mod, tmp_path, monkeypatch, capsys):
    """2026-09-25 实测事故：tools.computer_use 依赖门禁抛 FeatureUnavailable，
    真实原因却是 python 解释器选错。退出码 3 必须带上解释器与正确跑法。"""
    class FeatureUnavailable(Exception):
        pass

    def _boom():
        raise FeatureUnavailable(
            "Feature 'tool.computer_use' unavailable: install reported success but "
            "packages still not importable (may require Python restart).")

    monkeypatch.setattr(mod, "_backend", _boom)
    assert mod.main(["--out", str(tmp_path / "d.png")]) == 3
    err = capsys.readouterr().err
    assert "当前解释器" in err and "解释器选错" in err and ".venv" in err


def test_import_error_path_reports_interpreter(mod, monkeypatch, capsys):
    def _no_driver():
        raise ImportError("no cua_backend")

    monkeypatch.setattr(mod, "_backend", _no_driver)
    assert mod.main(["--out", "x.png"]) == 2
    err = capsys.readouterr().err
    assert "hermes computer-use install" in err and "当前解释器" in err

