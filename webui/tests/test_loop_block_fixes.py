# -*- coding: utf-8 -*-
"""堵点修复（2026-10-13，② 针对性）：SSL 上下文复用 + 更新检查下放线程池。

证据：看门狗 log/slow_loop.log 抓到 4.7s 阻塞，主线程栈：
  browser_tool → vision 需求检查 → detect_local_server_type → httpx.Client()
  → ssl.create_default_context(cafile=certifi.where()) → load_verify_locations
即"在事件循环里反复重建 SSL 上下文（加载 certifi CA 包）"，实测 4~33 秒级卡顿。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MM = os.path.join(ROOT, "hermes-agent", "agent", "model_metadata.py")
SERVER = os.path.join(ROOT, "webui", "server.py")


def test_model_metadata_caches_ssl_context():
    src = open(MM, encoding="utf-8", errors="replace").read()
    assert "def _cached_ssl_context(" in src, "缺少 SSL 上下文缓存助手"
    sites = len(re.findall(r"verify=_cached_ssl_context\(\)", src))
    assert sites >= 2, f"应有多个 httpx 站点复用缓存上下文，实际 {sites}"
    assert "import ssl" in src


def test_cached_ssl_context_returns_same_object():
    sys.path.insert(0, os.path.join(ROOT, "hermes-agent", "agent"))
    try:
        import model_metadata  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - 依赖底座环境
        import pytest
        pytest.skip("hermes-agent 环境不可导入: %r" % (exc,))
    a = model_metadata._cached_ssl_context()
    b = model_metadata._cached_ssl_context()
    assert a is b, "必须复用同一个 SSLContext（否则每次都在加载 CA 包）"


def test_update_check_offloaded_to_thread_pool():
    src = open(SERVER, encoding="utf-8", errors="replace").read()
    assert "def _update_check_sync(" in src, "缺少同步实现"
    m = re.search(r"async def update_check\(\):(.{0,600})", src, re.S)
    assert m, "找不到 update_check"
    body = m.group(1)
    assert "run_in_executor" in body and "_update_check_sync" in body, (
        "update_check 必须把同步网络部分下放到线程池，避免堵事件循环")


def test_watchdog_threshold_env_override():
    sys.path.insert(0, os.path.join(ROOT, "webui", "runtime"))
    import slow_loop_watchdog  # noqa: PLC0415
    assert slow_loop_watchdog.DEFAULT_THRESHOLD_SEC > 0
    wd = slow_loop_watchdog.SlowLoopWatchdog(os.path.join(ROOT, "log", "noop.log"), threshold=0.05)
    assert wd.threshold == 0.2, "阈值下限保护（0.2s）"