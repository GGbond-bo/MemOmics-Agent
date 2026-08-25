# -*- coding: utf-8 -*-
"""会话隔离测试（2026-08-25 DSH 模型迁移）：每会话独立 kernel 子池。

核心验证：
- 两会话并行各自持有独立 worker，跨会话不再互逐出（原全局池每语言 2 个上限
  → 会话 A 的 R 变量会被会话 B/C 顶掉；现在每会话自己的 2 个上限）
- worker_snapshot 带 session 标识（多会话可见性）
- restart(task_id) / close(task_id) 只影响目标会话
- 事件按会话隔离
"""
import importlib.util
import os
import sys
import time

import pytest

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pk = _load("persistent_kernel", os.path.join(_ROOT, "hermes-agent", "tools", "persistent_kernel.py"))

pytestmark = pytest.mark.unit


class _FakeWorker:
    def __init__(self, last_use=0.0):
        self.last_use = last_use
        self.closed = False

    def close(self):
        self.closed = True


def test_two_sessions_independent_pools():
    """两会话各自子池：A 塞满不碰 B。"""
    pool = pk.KernelPool()
    pa, pb = pool._pool_for("sess-A"), pool._pool_for("sess-B")
    assert pa is not pb, "两会话必须各自独立子池"
    assert pa.session_id == "sess-A" and pb.session_id == "sess-B"


def test_lru_eviction_is_per_session_not_global():
    """核心：每会话每语言 2 个上限——两会话各 2 个 R worker 共存（原全局池会逐出）。"""
    pool = pk.KernelPool()
    pa, pb = pool._pool_for("sess-A"), pool._pool_for("sess-B")
    # 每会话塞 2 个 R worker（超过旧全局上限 2 的场景）；last_use 越大越新
    pa._workers["r:sess-A"] = _FakeWorker(last_use=300.0)
    pa._workers["r:sess-A2"] = _FakeWorker(last_use=200.0)
    pb._workers["r:sess-B"] = _FakeWorker(last_use=100.0)
    pb._workers["r:sess-B2"] = _FakeWorker(last_use=50.0)
    # 会话 A 再加第 3 个（最旧）→ 只逐出 A 自己的最久未用，B 完全不动
    pa._workers["r:sess-A3"] = _FakeWorker(last_use=10.0)
    pa._evict_lru("r")
    assert "r:sess-A3" not in pa._workers, "A 最久未用（last_use 最小）应被逐出"
    assert "r:sess-A" in pa._workers and "r:sess-A2" in pa._workers
    assert len(pa._workers) == 2
    assert len(pb._workers) == 2, "会话 B 的 worker 不得被 A 的逐出影响"
    assert "r:sess-B" in pb._workers and "r:sess-B2" in pb._workers
    # B 自己的逐出同理（只影响 B）
    pb._workers["r:sess-B3"] = _FakeWorker(last_use=5.0)
    pb._evict_lru("r")
    assert "r:sess-B3" not in pb._workers
    assert len(pa._workers) == 2, "B 逐出不碰 A"


def test_snapshot_marks_session():
    pool = pk.KernelPool()
    pa = pool._pool_for("sess-A")
    pa._workers["python:sess-A"] = _FakeWorker(last_use=1.0)
    snap = pool.worker_snapshot()
    assert len(snap) == 1 and snap[0]["session"] == "sess-A"
    snap_a = pool.worker_snapshot(task_id="sess-A")
    assert len(snap_a) == 1
    assert pool.worker_snapshot(task_id="sess-B") == []


def test_restart_targets_one_session():
    pool = pk.KernelPool()
    pa, pb = pool._pool_for("sess-A"), pool._pool_for("sess-B")
    pa._workers["r:sess-A"] = _FakeWorker()
    pb._workers["r:sess-B"] = _FakeWorker()
    r = pool.restart(task_id="sess-A")
    assert pa._workers == {}, "A 应被重启清空"
    assert len(pb._workers) == 1, "B 不受影响"
    assert r and "sess-A" in r or "closed" in r


def test_close_targets_one_session():
    pool = pk.KernelPool()
    pa, pb = pool._pool_for("sess-A"), pool._pool_for("sess-B")
    pa._workers["r:sess-A"] = _FakeWorker()
    pb._workers["r:sess-B"] = _FakeWorker()
    pool.close(task_id="sess-A")
    assert "sess-A" not in pool._pools
    assert "sess-B" in pool._pools and len(pb._workers) == 1
    pool.close()
    assert pool._pools == {}


def test_default_session_isolated():
    """无 task_id（default）与会话池互不干扰。"""
    pool = pk.KernelPool()
    pd = pool._pool_for(None)
    pa = pool._pool_for("sess-A")
    assert pd is not pa
    pd._workers["python:default"] = _FakeWorker()
    assert pa._workers == {}


def test_real_two_sessions_parallel_python():
    """真实运行：两会话各执行 Python，各自持有独立 worker（rebuilt/uses 独立）。"""
    pool = pk.KernelPool()
    tid_a, tid_b = "iso-A-%d" % time.time(), "iso-B-%d" % time.time()
    try:
        r1a = pool.execute("print(1)", tid_a, timeout=30, language="python")
        r1b = pool.execute("print(2)", tid_b, timeout=30, language="python")
        assert r1a.get("kernel_rebuilt") is True
        assert r1b.get("kernel_rebuilt") is True
        assert pool.worker_snapshot(task_id=tid_a)[0]["session"] == tid_a
        assert pool.worker_snapshot(task_id=tid_b)[0]["session"] == tid_b
        # 复用各自 worker（互不干扰）
        r2a = pool.execute("print(3)", tid_a, timeout=30, language="python")
        r2b = pool.execute("print(4)", tid_b, timeout=30, language="python")
        assert r2a.get("kernel_rebuilt") is False
        assert r2b.get("kernel_rebuilt") is False
        assert r2a.get("kernel_uses", 0) > r1a.get("kernel_uses", 0)
        assert r2b.get("kernel_uses", 0) > r1b.get("kernel_uses", 0)
    finally:
        pool.close()
