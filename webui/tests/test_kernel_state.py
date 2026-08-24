# -*- coding: utf-8 -*-
"""L0/L1 kernel 状态可见化测试：
- L0: execute 响应带 kernel_rebuilt / kernel_uses；execute_r/execute_python 输出前缀
- L1: 逐出/回收/重建/重启事件记录 + 唤醒上下文注入（模型知道"变量已丢失"）
"""
import importlib.util
import os
import sys
import time

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..", "..")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pk = _load("persistent_kernel", os.path.join(_ROOT, "hermes-agent", "tools", "persistent_kernel.py"))
er = _load("execute_r", os.path.join(_ROOT, "memomics", "bio_tools", "execute_r.py"))

pytestmark = pytest.mark.unit


class _FakeWorker:
    """不 spawn 进程的假 worker：够 _evict_lru / _reap_idle 用的最小形态。"""

    def __init__(self, last_use=0.0):
        self.last_use = last_use
        self.closed = False

    def close(self):
        self.closed = True


# ── L1: 事件环 ──────────────────────────────────────────────────────────────

def test_kernel_events_ring_basic():
    pool = pk.KernelPool()
    pool._record_event("sess-a", "evicted")
    pool._record_event("sess-a", "reaped")
    pool._record_event("sess-b", "rebuilt")
    evs_a = pool.kernel_events("sess-a")
    assert len(evs_a) == 2
    assert evs_a[0].endswith("reaped"), "最新在前"
    assert any("sess-b" in e for e in pool.kernel_events()), "无过滤返回全部"
    assert pool.kernel_events("nope") == []


def test_kernel_events_ring_capped():
    pool = pk.KernelPool()
    for i in range(12):
        pool._record_event("sess-c", f"e{i}")
    evs = pool.kernel_events("sess-c")
    assert len(evs) <= 8, "事件环有上限"
    assert evs[0].endswith("e11"), "保留最新"


def test_evict_lru_records_event():
    pool = pk.KernelPool()
    pool._workers["r:sess-old"] = _FakeWorker(last_use=100.0)
    pool._workers["r:sess-new"] = _FakeWorker(last_use=200.0)
    pool._workers["r:sess-extra"] = _FakeWorker(last_use=150.0)
    pool._evict_lru("r")  # 上限 2 → 逐出最久未用（sess-old）
    assert "r:sess-old" not in pool._workers
    assert "r:sess-new" in pool._workers
    evs = pool.kernel_events("sess-old")
    assert evs and "LRU" in evs[0], f"逐出必须记录事件: {evs}"
    assert "变量已丢失" in evs[0]


def test_reap_idle_records_event():
    pool = pk.KernelPool()
    pool._workers["python:sess-idle"] = _FakeWorker(last_use=time.monotonic() - 10_000)
    pool._workers["python:sess-fresh"] = _FakeWorker(last_use=time.monotonic())
    pool._reap_idle()
    assert "python:sess-idle" not in pool._workers
    assert "python:sess-fresh" in pool._workers
    evs = pool.kernel_events("sess-idle")
    assert evs and "空闲回收" in evs[0]


# ── L0: 真实执行 rebuilt/uses 语义 ──────────────────────────────────────────

def test_execute_rebuilt_flag_and_uses():
    """真实 Python worker：首次 rebuilt=True，复用 rebuilt=False + uses 递增。"""
    pool = pk.KernelPool()
    tid = "kstate-test-%d" % int(time.time())
    try:
        r1 = pool.execute("print(1 + 1)", tid, timeout=30, language="python")
        assert r1.get("status") == "ok", r1
        assert r1.get("kernel_rebuilt") is True, "首次执行必须是新建"
        assert r1.get("kernel_uses", 0) >= 1
        r2 = pool.execute("print(2 + 2)", tid, timeout=30, language="python")
        assert r2.get("status") == "ok", r2
        assert r2.get("kernel_rebuilt") is False, "复用不得标记为新建"
        assert r2.get("kernel_uses", 0) > r1.get("kernel_uses", 0), "uses 递增"
        # 事件里有"新建"
        assert any("新建" in e for e in pool.kernel_events(tid))
    finally:
        pool.close()


# ── L0: execute_r / execute_python 输出前缀 ─────────────────────────────────

def test_kernel_note_prefixes():
    assert "[kernel: 新建" in er._kernel_note({"kernel_rebuilt": True})
    assert "复用" in er._kernel_note({"kernel_rebuilt": False, "kernel_uses": 8})
    assert er._kernel_note({"kernel_rebuilt": False, "kernel_uses": 2}) == ""
    assert er._kernel_note({}) == ""
    assert er._kernel_note(None) == ""


def test_execute_r_output_carries_kernel_note(monkeypatch):
    """execute_r 的成功/错误输出都带 kernel 状态前缀（不破坏原有结构）。"""
    calls = {}

    class _FakePool:
        def execute(self, code, task_id, timeout, language, cwd):
            calls["task"] = task_id
            calls["lang"] = language
            return {"status": "ok", "output": "loaded 100 cells",
                    "kernel_rebuilt": True, "kernel_uses": 1}

    # execute_r 内部 `from tools.persistent_kernel import KERNEL_POOL` 是延迟 import，
    # 必须 patch 真实模块（sys.modules 里的 tools.persistent_kernel）
    import tools.persistent_kernel as tpk
    monkeypatch.setattr(tpk, "KERNEL_POOL", _FakePool())
    out = er.execute_r("obj <- readRDS('x.rds')", task_id="sess-test")
    assert "kernel: 新建" in out
    assert "loaded 100 cells" in out
    assert '"status": "success"' in out
    assert calls.get("lang") == "r", "以 R 语言进入 pool"


# ── L1: 唤醒上下文注入 ──────────────────────────────────────────────────────

def test_wake_history_injects_kernel_events(monkeypatch):
    import server

    class _FakePool:
        def kernel_events(self, sid):
            assert sid == "sess-k"
            return ["[sess-k] r kernel 被空闲回收（30 分钟无请求），此前所有变量已丢失，需重新加载数据"]

    import tools.persistent_kernel as tpk
    monkeypatch.setattr(tpk, "KERNEL_POOL", _FakePool())

    sess = {"id": "sess-k", "results_dir": "", "messages": [
        {"role": "user", "content": "继续跑"},
        {"role": "assistant", "content": "好的"},
    ]}
    hist = server._build_self_check_wake_history(sess)
    joined = "\n".join(m.get("content", "") for m in hist)
    assert "kernel 状态提醒" in joined
    assert "空闲回收" in joined
    assert "重新加载" in joined
    # 无事件时不注入、不炸
    monkeypatch.setattr(tpk, "KERNEL_POOL",
                        type("P2", (), {"kernel_events": lambda self, sid: []})())
    hist2 = server._build_self_check_wake_history(sess)
    assert "kernel 状态提醒" not in "\n".join(m.get("content", "") for m in hist2)
