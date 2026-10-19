# -*- coding: utf-8 -*-
"""中途引导（steer）投递链路回归（2026-10-19，K1/K2/K3 修复）。

K1: hermes 回合收尾才到达的插话（result["pending_steer"]）不再被 webui 丢弃
    （回路级回归在 hermes-agent/tests/run_agent/test_steer_exit_continuation.py）；
K2: 新回合清空 _pending_steer 残留时用户插话被抢救，系统干预段仍作废；
K3: 运行中插话落会话历史（source="steer"），刷新可见、审计可查。
"""
import threading

import server  # noqa: E402  (webui 目录由 tests/conftest.py 加入 sys.path)


class _FakeAgent:
    """最小 steer 槽 stub（与 run_agent.AIAgent.steer 同语义：线程锁 + 换行拼接）。"""

    def __init__(self):
        self._pending_steer = None
        self._pending_steer_lock = threading.Lock()

    def steer(self, text):
        if not text or not text.strip():
            return False
        with self._pending_steer_lock:
            self._pending_steer = (self._pending_steer + "\n" + text.strip()) if self._pending_steer else text.strip()
        return True


def test_salvage_passthrough_plain_user_text():
    assert server._salvage_steer_text("把配色换成深色") == "把配色换成深色"
    assert server._salvage_steer_text("") == ""
    assert server._salvage_steer_text(None) == ""


def test_salvage_drops_loop_intervention():
    raw = ("【系统循环检测·强制干预】检测到你已连续多轮重复（tool_loop：tail x3）。\n"
           "1. 停止再执行重复的监控/查看动作；\n"
           "2. 若任务产物已生成，直接视为完成；")
    assert server._salvage_steer_text(raw) == ""


def test_salvage_drops_enforcement_hint():
    raw = "【系统强制提示】⛔ 已连续 2 次尝试执行被拦截！停止重试。"
    assert server._salvage_steer_text(raw) == ""


def test_salvage_keeps_user_text_after_system_block():
    raw = ("【系统强制提示】⛔ 已连续 2 次尝试执行被拦截！\n"
           "先别管那个了，直接把图改成灰度")
    out = server._salvage_steer_text(raw)
    assert "先别管那个了，直接把图改成灰度" in out
    assert "系统强制提示" not in out


def test_steer_slot_concat_preserves_order():
    a = _FakeAgent()
    a.steer("第一条")
    a.steer("第二条")
    a.steer("第三条")
    assert (a._pending_steer or "").split("\n") == ["第一条", "第二条", "第三条"]
    assert a.steer("") is False
    assert a.steer("   ") is False
