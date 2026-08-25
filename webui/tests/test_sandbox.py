# -*- coding: utf-8 -*-
"""沙箱探测与可写路径白名单测试（P1-4）

回归目标：
- 探测返回结构（sandboxed/degraded/backends）
- 白名单判定：允许内放行、系统路径拒绝、相对路径（cwd）放行
- 静态写路径检查：to_csv/savefig/open('w') 识别、open('r') 不误伤
- execute_code degraded 拦截：写系统路径被拒、白名单内放行
"""
import json
import os
import sys

import pytest

from tools.sandbox_probe import (
    check_script_write_roots,
    get_allowed_write_roots,
    is_write_path_allowed,
    probe_sandbox_capability,
)

# 2026-08-26: 沙箱语义为 Windows 专属（C:\Windows 系统路径白名单判定），
# Linux 上白名单/系统路径集合不同 → 跳过非 win32 平台
pytestmark = [pytest.mark.unit,
              pytest.mark.skipif(sys.platform != "win32",
                                 reason="Windows sandbox semantics")]


def test_probe_structure():
    p = probe_sandbox_capability()
    assert "sandboxed" in p and "degraded" in p and "backends" in p
    assert p["sandboxed"] is not p["degraded"]  # 互斥
    assert isinstance(p["backends"], list)


def test_write_roots_defaults(monkeypatch):
    """未配置时默认 cwd + temp"""
    monkeypatch.delenv("MEMOMICS_ALLOWED_WRITE_ROOTS", raising=False)
    roots = get_allowed_write_roots()
    assert os.getcwd() in roots
    assert any(r == os.path.normpath(os.environ.get("TEMP", "")) or "temp" in r.lower() for r in roots)


def test_write_roots_custom(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMOMICS_ALLOWED_WRITE_ROOTS", str(tmp_path))
    roots = get_allowed_write_roots()
    assert str(tmp_path) in roots


def test_is_write_path_allowed(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMOMICS_ALLOWED_WRITE_ROOTS", str(tmp_path))
    assert is_write_path_allowed(str(tmp_path / "out" / "x.csv")) is True
    assert is_write_path_allowed(str(tmp_path)) is True
    assert is_write_path_allowed(r"C:\Windows\System32\evil.exe") is False
    assert is_write_path_allowed("/etc/passwd") is False
    assert is_write_path_allowed("http://evil.com/x") is False
    # 相对路径 → 基于 cwd 解析（cwd 默认白名单）
    monkeypatch.setenv("MEMOMICS_ALLOWED_WRITE_ROOTS", "")
    assert is_write_path_allowed("output/fig.png") is True


def test_check_script_write_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMOMICS_ALLOWED_WRITE_ROOTS", str(tmp_path))
    code_bad = 'df.to_csv("C:/Windows/Temp/evil.csv")\nplt.savefig("/etc/x.png")'
    v = check_script_write_roots(code_bad)
    assert len(v) == 2
    code_ok = f'df.to_csv("{tmp_path / "ok.csv"}")\nplt.savefig("fig.png")'
    assert check_script_write_roots(code_ok) == []
    # open('r') 读取不误伤
    code_read = 'open("C:/Windows/win.ini", "r")'
    assert check_script_write_roots(code_read) == []
    # open('w') 写系统路径 → 拦截
    code_open_w = 'open("C:/Windows/evil.txt", "w")'
    assert check_script_write_roots(code_open_w) != []


def test_execute_code_degraded_block(monkeypatch):
    """degraded 模式：写白名单外路径的代码被 execute_code 拒绝"""
    from tools.code_execution_tool import execute_code
    monkeypatch.setenv("MEMOMICS_ALLOWED_WRITE_ROOTS", os.getcwd())
    # 强制 degraded（无论本机是否有 docker/wsl）
    import tools.sandbox_probe as sp
    monkeypatch.setattr(sp, "probe_sandbox_capability",
                        lambda: {"sandboxed": False, "backends": [], "degraded": True, "detail": "test"})
    # 需绕过 sandbox 前置检查直接测拦截路径：用 try_persistent 不适用场景
    r = json.loads(execute_code('open("C:/Windows/evil.txt", "w")', task_id="sbx-test"))
    assert r["status"] == "error"
    assert "白名单" in (r.get("error") or "")


def test_execute_code_degraded_allows_whitelisted(monkeypatch, tmp_path):
    """degraded 模式：白名单内写入放行"""
    from tools.code_execution_tool import execute_code
    monkeypatch.setenv("MEMOMICS_ALLOWED_WRITE_ROOTS", str(tmp_path))
    import tools.sandbox_probe as sp
    monkeypatch.setattr(sp, "probe_sandbox_capability",
                        lambda: {"sandboxed": False, "backends": [], "degraded": True, "detail": "test"})
    r = json.loads(execute_code(f'open(r"{tmp_path / "ok.txt"}", "w").write("hi")', task_id="sbx-test2"))
    assert r["status"] == "ok", r
