# -*- coding: utf-8 -*-
"""辩论总预算回归测试（2026-09-26）

背景：8 席位 / 并发 3 / 每席位 3 次重试 × httpx timeout=120s ≈ 18 分钟；
日志实测最慢一场 debate_analysis 1253s。用户看到的是「卡住，长时间不输出内容」。
这里锁死三道闸：
1) 单次 HTTP 上限 60s（可覆盖）；
2) 配置类错误（401/403/400/MissingSessionID/模型不存在）不再重试 3 次；
3) 整场辩论总预算（默认 480s），耗尽后一个 HTTP 都不发。
全部离线：httpx.Client 被换成假客户端。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from memomics.bio_tools import debate_analysis as da  # noqa: E402

SID = "memomics-budget-test"


class _FakeResp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP %d" % self.status_code)

    def json(self):
        return self._payload


class _FakeClient:
    """记录每次构造的 timeout 和每次 POST，用来数重试次数。"""

    calls = []
    timeouts = []
    responder = None

    def __init__(self, timeout=None, **kw):
        self.timeout = timeout
        _FakeClient.timeouts.append(timeout)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None):
        _FakeClient.calls.append(url)
        return _FakeClient.responder()


OK_PAYLOAD = {"choices": [{"message": {"content": "这是一个足够长的论点" * 4}}]}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    _FakeClient.calls = []
    _FakeClient.timeouts = []
    _FakeClient.responder = lambda: _FakeResp(200, OK_PAYLOAD)
    monkeypatch.setattr(da.httpx, "Client", _FakeClient)
    monkeypatch.setattr(da.time, "sleep", lambda s: None)   # 别真睡 3 秒
    with da._DEADLINE_LOCK:
        da._DEADLINES.clear()
    da.set_session_context(SID, "", None)
    yield
    with da._DEADLINE_LOCK:
        da._DEADLINES.clear()
    da.set_session_context("", "", None)


def _call(label="pro_biology"):
    return da._call_llm_sync("prompt", label, "key", "https://example.invalid/v1", "test-model")


def _expire_budget():
    """把本会话的截止时间直接拨到过去 —— 不靠 sleep（time.sleep 被替身成空操作）。"""
    da._set_debate_deadline(60)
    with da._DEADLINE_LOCK:
        da._DEADLINES[SID] = __import__("time").time() - 5


# ==================== 1. 单次超时：120s → 60s ====================

def test_http_timeout_default_is_60():
    assert da._HTTP_TIMEOUT_DEFAULT == 60.0, "单次上限必须降下来，否则 3 重试 × 分波还是十几分钟"


def test_timeout_used_when_no_budget():
    r = _call()
    assert not r.get("error")
    assert _FakeClient.timeouts == [60.0]


def test_timeout_clamped_to_remaining_budget():
    da._set_debate_deadline(30)
    r = _call()
    assert not r.get("error")
    t = _FakeClient.timeouts[0]
    assert 5.0 <= t <= 30.0, f"单次超时不能超过剩余预算，实际 {t}"


# ==================== 2. 重试闸：配置类错误不再重试 3 次 ====================

def test_config_error_retries_once_only():
    _FakeClient.responder = lambda: _FakeResp(401, text="Unauthorized: invalid api key")
    r = _call()
    assert r.get("error")
    assert len(_FakeClient.calls) == 1, f"401 重试了 {len(_FakeClient.calls)} 次，纯属烧时间"
    assert r.get("transient") is False


def test_transient_error_still_retries_three_times():
    _FakeClient.responder = lambda: _FakeResp(503, text="503 Service Unavailable")
    r = _call()
    assert r.get("error")
    assert len(_FakeClient.calls) == 3, "瞬时错误仍要重试 3 次兜底"
    assert r.get("transient") is True


def test_model_not_found_not_retried():
    _FakeClient.responder = lambda: _FakeResp(400, text="400 model_not_found: no such model")
    _call()
    assert len(_FakeClient.calls) == 1


# ==================== 3. 总预算：耗尽后一个 HTTP 都不发 ====================

def test_budget_left_is_infinite_without_deadline():
    assert da._budget_left() == float("inf")


def test_set_deadline_uses_default_budget():
    dl = da._set_debate_deadline()
    assert dl > 0
    left = da._budget_left()
    assert da._DEBATE_BUDGET_DEFAULT - 2 <= left <= da._DEBATE_BUDGET_DEFAULT + 1


def test_budget_exhausted_makes_no_http_call():
    _expire_budget()
    r = _call()
    assert r.get("error") and r.get("budget_exhausted") is True
    assert r.get("error_detail") == "budget_exhausted"
    assert _FakeClient.calls == [], "预算耗尽后还敢发 HTTP —— 这就是卡 20 分钟的根源"


def test_seat_skipped_when_budget_exhausted(monkeypatch):
    """席位阶段：预算没了就别再排席位。"""
    _expire_budget()
    res = da._call_role_parallel([("pro_biology", "p"), ("con_biology", "c")], {"mode": "homogeneous"})
    assert set(res) == {"pro_biology", "con_biology"}
    assert all(r.get("budget_exhausted") for r in res.values())
    assert _FakeClient.calls == []


def test_budget_is_per_session(monkeypatch):
    """A 会话的预算不能把 B 会话一起掐死。"""
    _expire_budget()
    da.set_session_context("memomics-other-session", "", None)
    assert da._budget_left() == float("inf"), "别的会话不该被 A 会话的预算掐死"
    da.set_session_context(SID, "", None)
    assert da._budget_left() <= 0


# ==================== 4. 失败时保留已完成席位 ====================

def test_failure_result_keeps_partial_arguments():
    import inspect
    src = inspect.getsource(da.debate_analysis)
    assert '"partial_seats"' in src and '"partial_arguments"' in src
    assert '"budget_exhausted"' in src
