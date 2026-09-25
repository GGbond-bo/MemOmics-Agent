# -*- coding: utf-8 -*-
"""辩论进度上报回归测试（2026-09-26）

用户反馈原话：「MemOmics 有时候会卡住，长时间不输出内容」。
实测根因：一场辩论 = 场景预判 + 7 席位 + 裁判，席位是非流式 HTTP
（httpx timeout=120，每席位最多 3 次重试，8 席位按 max_workers=3 分波），
日志实测 62 次调用最慢 1253s，期间工具只在开始发一次 tool.started →
界面 15-20 分钟一个字都不新增。修复：把阶段/席位/心跳推到前端时间线。

全部离线：不调 LLM、不碰生产缓存，只用假 server 实例收事件。
"""
import inspect
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from memomics.bio_tools import debate_analysis as da  # noqa: E402

SID = "memomics-progress-test"


class _FakeSrv:
    """冒充正在运行的 webui.server 实例：只提供 _live_server 需要的两个属性。"""

    def __init__(self, sid=SID, raise_on_emit=False):
        self._sessions = {sid: {"id": sid}}
        self.events = []
        self.raise_on_emit = raise_on_emit

    def _session_emit(self, sess, ev):
        if self.raise_on_emit:
            raise RuntimeError("emit boom")
        self.events.append(ev)


class _FakeHB:
    """替身心跳：只记录 start/stop，不真的起线程。"""

    instances = []

    def __init__(self, label, interval=30.0, max_seconds=2700.0):
        self.label = label
        self.interval = interval
        self.stopped = False
        self.done_text = ""
        _FakeHB.instances.append(self)

    def start(self):
        return self

    def stop(self, done_text=""):
        self.stopped = True
        self.done_text = done_text

    @property
    def elapsed(self):
        return 7


@pytest.fixture(autouse=True)
def _reset_progress_state(monkeypatch):
    """每条测试都把节流状态清零，避免上一条的 _PROGRESS_LAST_TS 把这条吞掉。"""
    monkeypatch.setattr(da, "_PROGRESS_LAST_TS", 0.0)
    monkeypatch.setattr(da, "_PROGRESS_MIN_GAP", 0.0)
    _FakeHB.instances = []
    da.set_session_context(SID, "", None)
    yield
    da.set_session_context("", "", None)


@pytest.fixture
def fake_srv(monkeypatch):
    srv = _FakeSrv()
    monkeypatch.setitem(sys.modules, "server", srv)
    return srv


def _events(srv):
    return [e for e in srv.events if e.get("type") == "tool_progress"]


# ==================== 1. 事件形状：前端 index.html 2519 行认这三个字段 ====================

def test_emit_progress_pushes_tool_progress_event(fake_srv):
    da._emit_progress("席位 pro_biology 完成", "done")
    evs = _events(fake_srv)
    assert len(evs) == 1
    ev = evs[0]
    assert ev["type"] == "tool_progress"
    assert ev["tool"] == "debate_analysis"
    assert ev["content"] == "席位 pro_biology 完成"
    assert ev["status"] == "done"
    assert ev["session_id"] == SID


def test_emit_progress_truncates_long_content(fake_srv):
    da._emit_progress("x" * 500)
    assert len(_events(fake_srv)[0]["content"]) == 180


# ==================== 2. 上报失败绝不影响辩论 ====================

def test_emit_progress_without_session_is_silent(fake_srv):
    da.set_session_context("", "", None)
    da._emit_progress("没人听")
    assert _events(fake_srv) == []


def test_emit_progress_without_server_module_is_silent(monkeypatch):
    """找不到 server 实例时不能抛异常（工具照常跑完）。"""
    monkeypatch.setattr(da, "_emit_progress", da._emit_progress, raising=False)
    import memomics.bio_tools.ask_user as au
    monkeypatch.setattr(au, "_live_server", lambda sid=None: None)
    da._emit_progress("没人听")


def test_emit_progress_swallows_emit_errors(monkeypatch):
    srv = _FakeSrv(raise_on_emit=True)
    monkeypatch.setitem(sys.modules, "server", srv)
    da._emit_progress("炸了也不许抛")   # 不抛就算过


def test_emit_progress_rate_limited(fake_srv, monkeypatch):
    monkeypatch.setattr(da, "_PROGRESS_MIN_GAP", 5.0)
    da._emit_progress("第一条")
    da._emit_progress("第二条")
    assert [e["content"] for e in _events(fake_srv)] == ["第一条"]


# ==================== 3. 心跳：静默期间必须持续有字 ====================

def test_heartbeat_emits_running_line_and_stops(monkeypatch):
    seen = []
    monkeypatch.setattr(da, "_emit_progress", lambda c, s="pending": seen.append((c, s)))
    hb = da._ProgressHeartbeat("席位辩论（8 席）", interval=5.0)
    hb.interval = 0.05          # 测试里不等 30 秒
    hb.start()
    time.sleep(0.3)
    hb.stop()
    running = [c for c, s in seen if "进行中" in c and "暂无输出" in c]
    assert running, "心跳没报「进行中」，长工具期间界面又会一片死寂"
    assert "已用" in running[0]


def test_heartbeat_stop_emits_done_text(monkeypatch):
    seen = []
    monkeypatch.setattr(da, "_emit_progress", lambda c, s="pending": seen.append((c, s)))
    hb = da._ProgressHeartbeat("裁判汇总").start()
    hb.stop("裁判汇总完成（1/1 位有效）")
    assert ("裁判汇总完成（1/1 位有效）", "done") in seen


def test_heartbeat_self_limits(monkeypatch):
    """万一某条路径没 stop()，心跳必须自己死掉，不能变成永远刷屏的幽灵线程。"""
    seen = []
    monkeypatch.setattr(da, "_emit_progress", lambda c, s="pending": seen.append((c, s)))
    hb = da._ProgressHeartbeat("幽灵")
    hb.interval = 0.02
    hb.max_seconds = 0.05
    hb.start()
    time.sleep(0.3)
    n = len(seen)
    time.sleep(0.3)
    assert len(seen) == n, "心跳超过自限寿命还在刷"


# ==================== 4. 席位阶段：每个席位完成都要冒泡 ====================

def test_call_role_parallel_reports_each_seat(monkeypatch, fake_srv):
    monkeypatch.setattr(da, "_ProgressHeartbeat", _FakeHB)
    monkeypatch.setattr(da, "_call_llm_role",
                        lambda label, prompt, cfg, temperature=None: {"content": "ok", "call_id": label})
    tasks = [("pro_biology", "p"), ("con_biology", "c")]
    res = da._call_role_parallel(tasks, {"mode": "homogeneous"})
    assert set(res) == {"pro_biology", "con_biology"}
    texts = [e["content"] for e in _events(fake_srv)]
    assert any("席位 pro_biology 完成" in t for t in texts)
    assert any("席位 con_biology 完成" in t for t in texts)
    assert any("1/2" in t for t in texts) and any("2/2" in t for t in texts)
    assert _FakeHB.instances and _FakeHB.instances[-1].stopped, "席位跑完心跳必须停"


def test_call_role_parallel_reports_seat_failure(monkeypatch, fake_srv):
    monkeypatch.setattr(da, "_ProgressHeartbeat", _FakeHB)

    def _boom(label, prompt, cfg, temperature=None):
        raise RuntimeError("read operation timed out")

    monkeypatch.setattr(da, "_call_llm_role", _boom)
    da._call_role_parallel([("con_history", "p")], {"mode": "homogeneous"})
    texts = [e["content"] for e in _events(fake_srv)]
    assert any("席位 con_history 调用失败" in t for t in texts)
    assert any("timed out" in t for t in texts)


def test_judge_consensus_reports_judge_progress(monkeypatch, fake_srv):
    monkeypatch.setattr(da, "_ProgressHeartbeat", _FakeHB)
    monkeypatch.setattr(da, "_call_llm_role_resilient",
                        lambda label, prompt, cfg, temperature=None: {"content": '{"verdict": "support"}'})
    da._collect_judge_consensus("judge prompt", {"judge_count": 2})
    texts = [e["content"] for e in _events(fake_srv)]
    assert any("裁判 1/2" in t for t in texts) and any("裁判 2/2" in t for t in texts)
    assert _FakeHB.instances[-1].done_text.startswith("裁判汇总完成")


# ==================== 5. 接线位置：四个长阶段都必须有上报 ====================

@pytest.mark.parametrize("fn,needle", [
    (da._call_role_parallel, "席位"),
    (da._collect_judge_consensus, "裁判汇总"),
    (da.debate_analysis, "场景预判"),
    (da._debate_l1_lightweight, "L1 第"),
])
def test_long_phase_is_wired(fn, needle):
    src = inspect.getsource(fn)
    assert "_emit_progress" in src, f"{fn.__name__} 没有任何进度上报 —— 又会静默十几分钟"
    assert needle in src


def test_httpx_timeout_still_documented():
    """超时值是「最坏 8 席 × 3 重试 × 120s」的乘数，改小之前先看这里。"""
    src = inspect.getsource(da._call_llm_sync)
    assert "timeout=" in src
