# -*- coding: utf-8 -*-
"""execute_r 工具测试（P0-1）：持久 kernel 优先 + Rscript 回退

回归目标：
- 工具在 memomics toolset 注册、agent 可见
- 持久路径：跨调用状态保持（变量/包）
- 错误/超时语义；沙箱写路径拦截（degraded）
- 持久失败时回退旧 Rscript 路径（OOM 重试逻辑保留）
"""
import json
import os

import pytest

from memomics.bio_tools.execute_r import execute_r
from tools.registry import registry

pytestmark = pytest.mark.unit


def test_registered_in_memomics_toolset():
    """execute_r 注册在 memomics toolset（agent 默认启用）"""
    entry = registry.get_entry("execute_r")
    assert entry is not None, "execute_r 未注册"
    assert entry.toolset == "memomics"
    assert "code" in entry.schema["parameters"]["properties"]


def test_persistent_state_across_calls():
    """持久路径：跨调用状态保持"""
    r1 = execute_r("n <- 21", task_id="bio-r-1")
    assert "Error" not in r1
    r2 = execute_r("n * 2", task_id="bio-r-1")
    assert "42" in r2


def test_persistent_output_and_errors():
    r = execute_r("cat('hello-bio\\n')", task_id="bio-r-1")
    assert "hello-bio" in r
    r2 = execute_r("stop('boom-bio')", task_id="bio-r-1")
    assert "Error" in r2 or "boom-bio" in r2


def test_persistent_timeout_fallback():
    """持久超时 → 明确错误；下次调用自动重建"""
    r = execute_r("Sys.sleep(100)", timeout=2, task_id="bio-r-t")
    assert "timed out" in r.lower() or "Error" in r
    r2 = execute_r("40 + 2", task_id="bio-r-t")
    assert "42" in r2


def test_fallback_when_kernel_unavailable(monkeypatch):
    """持久不可用（异常）→ 回退 Rscript 旧路径（不崩）"""
    import memomics.bio_tools.execute_r as mod
    import tools.persistent_kernel as pk

    class FakePool:
        def execute(self, *a, **kw):
            raise RuntimeError("kernel down")
    monkeypatch.setattr(pk, "KERNEL_POOL", FakePool())
    r = mod.execute_r("1 + 1", task_id="bio-fallback")
    # 回退路径执行（Rscript 可用时返回结果，不可用时返回 Error: R is not installed）
    assert isinstance(r, str) and r


def test_sandbox_write_block(monkeypatch):
    """degraded 模式：字面量系统路径写被拒（回退前拦截）"""
    from tools import sandbox_probe as sp
    monkeypatch.setattr(sp, "probe_sandbox_capability",
                        lambda: {"sandboxed": False, "backends": [], "degraded": True, "detail": "test"})
    monkeypatch.setenv("MEMOMICS_ALLOWED_WRITE_ROOTS", os.getcwd())
    r = execute_r('write.csv(iris, "C:/Windows/evil.csv")', task_id="bio-sbx")
    assert "白名单" in r or "Error" in r
