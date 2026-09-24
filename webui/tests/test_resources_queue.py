# -*- coding: utf-8 -*-
"""资源队列视图 · 真并发回归测试（2026-09-24）。

ResourceScheduler 是"谁能跑、谁在排"的唯一裁判，之前一个测试都没有。
这里用真 asyncio 起真协程把队列压出来：排第几、等多久、谁在跑、取消后不留幽灵。
（本机没装 pytest-asyncio，所以用 asyncio.run 自己开事件循环跑真协程。）

D 组刻意钉住一个既有行为：严格 FIFO —— 队首的超大请求会挡住后面的小请求。
不是 bug（不插队换来"排第几就是第几"），但要让改的人知道它是有意的。
"""
import asyncio
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "webui"))

from webui.runtime.resources import (  # noqa: E402
    QueuedWaiter,
    ResourceCapacity,
    ResourceLease,
    ResourceRequest,
    ResourceScheduler,
)

pytestmark = [pytest.mark.unit, pytest.mark.memory]


def _sched(cpu=2, mem=8.0, gpu=0):
    return ResourceScheduler(ResourceCapacity(cpu_cores=cpu, memory_gb=mem, gpu_slots=gpu))


async def _settle(loops=6):
    """让出若干轮事件循环，把已经就绪的协程推到底。"""
    for _ in range(loops):
        await asyncio.sleep(0)


def test_a1_capacity_env_overrides(monkeypatch):
    """容量显式可覆盖：压小容量才能复现排队（运维也能主动限流）。"""
    monkeypatch.setenv("MEMOMICS_CPU_CORES", "3")
    monkeypatch.setenv("MEMOMICS_MEMORY_GB", "5.5")
    monkeypatch.setenv("MEMOMICS_GPU_SLOTS", "0")
    cap = ResourceCapacity.detect()
    assert cap.cpu_cores == 3 and cap.memory_gb == 5.5 and cap.gpu_slots == 0
    monkeypatch.setenv("MEMOMICS_CPU_CORES", "不是数字")
    monkeypatch.setenv("MEMOMICS_MEMORY_GB", "也乱写")
    fallback = ResourceCapacity.detect()
    assert fallback.cpu_cores >= 1 and fallback.memory_gb > 0


async def _b1():
    """排在后面的人：位置从 1 数起、带着名字、等着的时间在涨。"""
    s = _sched(cpu=1)
    first = await s.acquire("sess-A", ResourceRequest(cpu_cores=1, memory_gb=1.0), label="跑 QC")
    t2 = asyncio.ensure_future(s.acquire("sess-B", ResourceRequest(cpu_cores=1, memory_gb=1.0), label="跑 ATAC"))
    t3 = asyncio.ensure_future(s.acquire("sess-C", ResourceRequest(cpu_cores=1, memory_gb=1.0)))
    await _settle()
    snap = s.snapshot()
    assert [w["session_id"] for w in snap["waiting"]] == ["sess-B", "sess-C"]
    assert [w["position"] for w in snap["waiting"]] == [1, 2]
    assert snap["waiting"][0]["label"] == "跑 ATAC" and snap["waiting"][1]["label"] == ""
    assert snap["waiting"][0]["enqueued_at"].endswith("+00:00"), snap["waiting"][0]
    assert snap["waiting"][0]["waited_sec"] >= 0.0
    assert snap["queue"]["active"] == 1 and snap["queue"]["waiting"] == 2
    assert snap["queue"]["head_wait_sec"] == snap["waiting"][0]["waited_sec"]
    assert snap["queue"]["max_wait_sec"] >= snap["waiting"][0]["waited_sec"]
    assert snap["active"][0]["label"] == "跑 QC" and snap["active"][0]["lease_id"] == first.lease_id
    assert snap["active"][0]["acquired_at"].endswith("+00:00")
    assert snap["active"][0]["held_sec"] >= 0.0
    json.dumps(snap)  # 快照必须能直接进 HTTP 响应
    await s.release(first)
    lease2 = await asyncio.wait_for(t2, timeout=5)
    assert lease2.session_id == "sess-B"
    assert s.snapshot()["queue"]["waiting"] == 1, "容量 1 核：B 拿到后 C 还得排"
    assert s.snapshot()["waiting"][0]["position"] == 1
    await s.release(lease2)
    lease3 = await asyncio.wait_for(t3, timeout=5)
    assert lease3.session_id == "sess-C"
    await s.release(lease3)
    assert s.snapshot()["queue"]["waiting"] == 0 and s.snapshot()["queue"]["active"] == 0


def test_b1_waiter_sees_position_label_and_wait():
    asyncio.run(_b1())


async def _b2():
    """waited_sec 是真实等待时长（不是摆设）。"""
    s = _sched(cpu=1)
    held = await s.acquire("sess-A", ResourceRequest(cpu_cores=1, memory_gb=1.0))
    t2 = asyncio.ensure_future(s.acquire("sess-B", ResourceRequest(cpu_cores=1, memory_gb=1.0), label="等一会"))
    await _settle()
    await asyncio.sleep(0.35)
    waited = s.snapshot()["waiting"][0]["waited_sec"]
    assert 0.2 <= waited <= 2.0, waited
    await s.release(held)
    await asyncio.wait_for(t2, timeout=5)


def test_b2_wait_time_reflects_reality():
    asyncio.run(_b2())


async def _c1():
    """排队中途被取消（排队超时/断开）：队列里不留幽灵，后面的人照常前进。"""
    s = _sched(cpu=1)
    held = await s.acquire("sess-A", ResourceRequest(cpu_cores=1, memory_gb=1.0), label="占着")
    doomed = asyncio.ensure_future(s.acquire("sess-B", ResourceRequest(cpu_cores=1, memory_gb=1.0)))
    alive = asyncio.ensure_future(s.acquire("sess-C", ResourceRequest(cpu_cores=1, memory_gb=1.0)))
    await _settle()
    assert [w["session_id"] for w in s.snapshot()["waiting"]] == ["sess-B", "sess-C"]
    doomed.cancel()
    with pytest.raises(asyncio.CancelledError):
        await doomed
    await _settle()
    snap = s.snapshot()
    assert [w["session_id"] for w in snap["waiting"]] == ["sess-C"]
    assert snap["waiting"][0]["position"] == 1
    await s.release(held)
    lease = await asyncio.wait_for(alive, timeout=5)
    assert lease.session_id == "sess-C"


def test_c1_cancel_while_queued_leaves_no_ghost():
    asyncio.run(_c1())


async def _c2():
    """取消队首不能让整队卡死（notify_all 要唤醒下一个）。"""
    s = _sched(cpu=1)
    held = await s.acquire("sess-HOLD", ResourceRequest(cpu_cores=1, memory_gb=1.0), label="占着")
    head = asyncio.ensure_future(s.acquire("sess-A", ResourceRequest(cpu_cores=1, memory_gb=1.0)))
    tail = asyncio.ensure_future(s.acquire("sess-B", ResourceRequest(cpu_cores=1, memory_gb=1.0)))
    await _settle()
    assert [w["session_id"] for w in s.snapshot()["waiting"]] == ["sess-A", "sess-B"]
    head.cancel()
    with pytest.raises(asyncio.CancelledError):
        await head
    await _settle()
    assert [w["session_id"] for w in s.snapshot()["waiting"]] == ["sess-B"], "取消队首后，后面的要顶上来"
    await s.release(held)
    lease = await asyncio.wait_for(tail, timeout=5)
    assert lease.session_id == "sess-B"


def test_c2_deadlock_not_caused_by_cancel_head_waiter():
    asyncio.run(_c2())


async def _d1():
    """严格 FIFO：队首的大请求挡住后面的小请求（不插队），面板上排第几才可信。"""
    s = _sched(cpu=2)
    half = await s.acquire("sess-A", ResourceRequest(cpu_cores=1, memory_gb=1.0))
    big = asyncio.ensure_future(s.acquire("sess-B", ResourceRequest(cpu_cores=2, memory_gb=1.0), label="大任务"))
    small = asyncio.ensure_future(s.acquire("sess-C", ResourceRequest(cpu_cores=1, memory_gb=1.0), label="小任务"))
    await _settle()
    snap = s.snapshot()
    assert [w["label"] for w in snap["waiting"]] == ["大任务", "小任务"]
    assert snap["available"]["cpu_cores"] == 1  # 空着 1 核，但小任务不插队
    await s.release(half)
    first_done = await asyncio.wait_for(big, timeout=3)
    assert first_done.session_id == "sess-B"
    await s.release(first_done)
    assert (await asyncio.wait_for(small, timeout=3)).session_id == "sess-C"


def test_d1_head_of_line_blocking_is_intentional():
    asyncio.run(_d1())


async def _e1():
    """超容量的请求当场被拒，不能在队列里留一条永远排不到的记录。"""
    s = _sched(cpu=2, mem=4.0)
    with pytest.raises(ValueError):
        await s.acquire("sess-A", ResourceRequest(cpu_cores=9, memory_gb=1.0))
    with pytest.raises(ValueError):
        await s.acquire("sess-B", ResourceRequest(cpu_cores=1, memory_gb=99.0))
    with pytest.raises(ValueError):
        await s.acquire("", ResourceRequest())
    assert s.snapshot()["queue"]["waiting"] == 0 and s.snapshot()["active"] == []


def test_e1_rejected_request_leaves_no_queue_entry():
    asyncio.run(_e1())


async def _f1():
    """GPU 是稀缺资源：谁占着、谁为 GPU 排队，快照里都得看得见。"""
    s = _sched(cpu=4, mem=16.0, gpu=1)
    gpu_lease = await s.acquire("sess-A", ResourceRequest(cpu_cores=1, memory_gb=2.0, gpu_slots=1), label="训练")
    waiter = asyncio.ensure_future(s.acquire("sess-B", ResourceRequest(cpu_cores=1, memory_gb=2.0, gpu_slots=1), label="等 GPU"))
    await _settle()
    snap = s.snapshot()
    assert snap["active"][0]["gpu_slots"] == 1 and snap["available"]["gpu_slots"] == 0
    assert snap["waiting"][0]["gpu_slots"] == 1 and snap["waiting"][0]["label"] == "等 GPU"
    assert snap["available"]["cpu_cores"] == 3, "GPU 排队的任务不该把 CPU 也算进去"
    await s.release(gpu_lease)
    assert (await asyncio.wait_for(waiter, timeout=3)).session_id == "sess-B"


def test_f1_gpu_slot_queueing_shows_in_queue():
    asyncio.run(_f1())


def test_g1_snapshot_keeps_old_keys_and_types():
    """老字段一个都不能少（面板/外部脚本已经在用），新字段是加出来的。"""
    s = _sched(cpu=4, mem=8.0, gpu=1)
    snap = s.snapshot()
    for key in ("enforcement", "capacity", "used", "available", "active", "waiting"):
        assert key in snap, key
    assert set(snap["capacity"]) == {"cpu_cores", "memory_gb", "gpu_slots"}
    assert set(snap["available"]) == {"cpu_cores", "memory_gb", "gpu_slots"}
    assert snap["enforcement"]["admission"] == "cooperative_fifo"
    assert snap["queue"]["active"] == 0 and snap["queue"]["waiting"] == 0
    assert json.dumps(snap, ensure_ascii=False)


def test_g2_waiting_rows_carry_the_viewer_fields():
    """面板画队列要的字段（位置/名字/等了多久/要多少）在快照里定死。"""
    s = _sched(cpu=1)
    s._waiting.append(QueuedWaiter(ticket="t1", session_id="sess-X",
                                   request=ResourceRequest(cpu_cores=1, memory_gb=2.0),
                                   label="QC", enqueued_at="2026-01-01T00:00:00+00:00",
                                   enqueued_monotonic=time.monotonic()))
    row = s.snapshot()["waiting"][0]
    for key in ("session_id", "position", "label", "enqueued_at", "waited_sec",
                "cpu_cores", "memory_gb", "gpu_slots"):
        assert key in row, key
    assert row["position"] == 1 and row["waited_sec"] >= 0.0
    assert ResourceLease("l", "s", ResourceRequest()).label == ""