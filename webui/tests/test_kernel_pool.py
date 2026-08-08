# -*- coding: utf-8 -*-
"""持久 kernel 池测试（P0-1）

回归目标：
- 跨调用状态保持（变量/模块在 worker 中存活）
- task_id 级隔离（不同任务互不干扰）
- 超时 kill 卡死 worker 并可自动恢复
- 快速路径判定（纯计算走持久，沙箱/进程代码走旧路径）
- 输出捕获 / 异常语义
"""
import json
import os

import pytest

from tools.persistent_kernel import KERNEL_POOL, try_persistent_kernel

pytestmark = pytest.mark.unit


def test_state_persists_across_calls():
    """同一 task 两次调用：变量保留（持久内核核心价值）"""
    r1 = KERNEL_POOL.execute("x = 42", "pool-task-1", timeout=15)
    assert r1["status"] == "ok"
    r2 = KERNEL_POOL.execute("x * 2", "pool-task-1", timeout=15)
    assert r2["status"] == "ok"
    assert "84" in r2["output"]


def test_task_isolation():
    """不同 task 变量不共享（NameError → status error）"""
    KERNEL_POOL.execute("y = 1", "pool-task-a", timeout=15)
    r = KERNEL_POOL.execute("y", "pool-task-b", timeout=15)
    assert r["status"] == "error"
    assert "y" in (r.get("error") or "")


def test_print_capture():
    r = KERNEL_POOL.execute("print('hello-kernel'); print(1 + 1)", "pool-task-1", timeout=15)
    assert r["status"] == "ok"
    assert "hello-kernel" in r["output"]
    assert "2" in r["output"]


def test_error_semantics():
    r = KERNEL_POOL.execute("1 / 0", "pool-task-1", timeout=15)
    assert r["status"] == "error"
    assert "ZeroDivisionError" in (r.get("error") or "")


def test_timeout_kill_and_recover():
    """卡死 worker 被 kill，下次调用自动重建"""
    r1 = KERNEL_POOL.execute("import time; time.sleep(100)", "pool-task-t", timeout=2)
    assert r1["status"] == "timeout"
    r2 = KERNEL_POOL.execute("40 + 2", "pool-task-t", timeout=15)
    assert r2["status"] == "ok"
    assert "42" in r2["output"]


def test_router_pure_compute():
    """纯计算代码走持久路径（返回 JSON 字符串）"""
    out = try_persistent_kernel("6 * 7", "pool-task-1", 15)
    assert out is not None
    d = json.loads(out)
    assert d["status"] == "ok"
    assert "42" in d["output"]


def test_router_sandbox_code_skipped():
    """沙箱/进程代码不走持久路径（None → 旧路径）"""
    assert try_persistent_kernel("from hermes_tools import read_file", "pool-task-1", 15) is None
    assert try_persistent_kernel("import subprocess; subprocess.run(['echo','hi'])", "pool-task-1", 15) is None


def test_fresh_escape_hatch(monkeypatch):
    """MEMOMICS_KERNEL_FRESH=1 强制走旧路径"""
    monkeypatch.setenv("MEMOMICS_KERNEL_FRESH", "1")
    assert try_persistent_kernel("1 + 1", "pool-task-1", 15) is None


# ==================== R kernel（P0-1） ====================

def test_r_state_persists_across_calls():
    """R 同 task 两次调用：变量保留"""
    r1 = KERNEL_POOL.execute("x <- 42", "r-task-1", timeout=20, language="r")
    assert r1["status"] == "ok", r1
    r2 = KERNEL_POOL.execute("x * 2", "r-task-1", timeout=20, language="r")
    assert r2["status"] == "ok", r2
    assert "84" in r2["output"]


def test_r_print_capture():
    r = KERNEL_POOL.execute("cat('hello-r\n'); print(1 + 1)", "r-task-1", timeout=20, language="r")
    assert r["status"] == "ok", r
    assert "hello-r" in r["output"]
    assert "2" in r["output"]


def test_r_error_semantics():
    r = KERNEL_POOL.execute("stop('boom-r')", "r-task-1", timeout=20, language="r")
    assert r["status"] == "error"
    assert "boom-r" in (r.get("error") or "")


def test_r_timeout_kill_and_recover():
    """R 卡死 worker 被 kill，下次调用自动重建"""
    r1 = KERNEL_POOL.execute("Sys.sleep(100)", "r-task-t", timeout=2, language="r")
    assert r1["status"] == "timeout"
    r2 = KERNEL_POOL.execute("40 + 2", "r-task-t", timeout=20, language="r")
    assert r2["status"] == "ok"
    assert "42" in r2["output"]
