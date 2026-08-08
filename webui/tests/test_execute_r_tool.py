# -*- coding: utf-8 -*-
"""execute_r 工具测试（P0-1 补齐）：注册 / 状态保持 / 沙箱拦截 / 白名单"""
import json
import os

import pytest

from tools.execute_r_tool import execute_r
from tools.registry import registry

pytestmark = pytest.mark.unit


def test_registered_in_registry():
    defs = registry.get_definitions({"execute_r"})
    assert len(defs) == 1
    fn = defs[0]["function"]
    assert fn["name"] == "execute_r"
    assert "code" in fn["parameters"]["properties"]
    assert "persistent" in fn["description"].lower()


def test_execute_r_state_persists():
    r1 = json.loads(execute_r("n <- 21", task_id="ert-reg"))
    assert r1["status"] == "ok"
    r2 = json.loads(execute_r("n * 2", task_id="ert-reg"))
    assert r2["status"] == "ok"
    assert "42" in r2["output"]


def test_execute_r_error_semantics():
    r = json.loads(execute_r("stop('r-tool-boom')", task_id="ert-reg"))
    assert r["status"] == "error"
    assert "r-tool-boom" in (r.get("error") or "")


def test_execute_r_empty_code():
    r = json.loads(execute_r("   ", task_id="ert-reg"))
    assert r["status"] == "error"


def test_execute_r_sandbox_block(monkeypatch):
    """degraded 模式：字面量系统路径拦截（write.csv 第二参数）"""
    from tools import sandbox_probe as sp
    monkeypatch.setattr(sp, "probe_sandbox_capability",
                        lambda: {"sandboxed": False, "backends": [], "degraded": True, "detail": "test"})
    monkeypatch.setenv("MEMOMICS_ALLOWED_WRITE_ROOTS", os.getcwd())
    r = json.loads(execute_r('write.csv(iris, "C:/Windows/evil.csv")', task_id="ert-sbx"))
    assert r["status"] == "error"
    assert "白名单" in (r.get("error") or "")


def test_execute_r_sandbox_allow_relative(monkeypatch):
    """degraded 模式：相对路径（cwd）放行"""
    from tools import sandbox_probe as sp
    monkeypatch.setattr(sp, "probe_sandbox_capability",
                        lambda: {"sandboxed": False, "backends": [], "degraded": True, "detail": "test"})
    monkeypatch.setenv("MEMOMICS_ALLOWED_WRITE_ROOTS", os.getcwd())
    r = json.loads(execute_r('writeLines("hi", "_r_tool_tmp.txt"); "ok"', task_id="ert-sbx2"))
    assert r["status"] == "ok", r
    try:
        os.remove("_r_tool_tmp.txt")
    except OSError:
        pass
