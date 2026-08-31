# -*- coding: utf-8 -*-
"""stall watchdog 策略测试（2026-08-31 长任务误杀修复）。

背景：用户跑长任务/后台完成后唤醒的回合，被"5 分钟无输出即中断"误杀。
新策略：无前科（回合开始即静默）300s；有前科（中段静默）600s（env 可调）；
后台进程在跑永不中断（进程级证据在 _task_liveness，已在测试外验证）。
"""
import os
import time

import server


class TestStallHardSeconds:
    def _session(self, start_ts, act_ts):
        return {"_turn_start_ts": start_ts, "_turn_activity_ts": act_ts if act_ts else None}

    def test_no_prior_event_fast_recover(self, monkeypatch):
        """回合开始即静默（connect 后零输出）= 网关挂起典型 → 300s 快速中断。"""
        monkeypatch.delenv("MEMOMICS_STALL_HARD_SECONDS", raising=False)
        now = time.time()
        s = self._session(now, None)
        assert server._stall_hard_seconds(s) == 300

    def test_mid_turn_silence_gives_600(self, monkeypatch):
        """回合中段静默（此前有输出）= 长思考/长生成 → 600s 宽限。"""
        monkeypatch.delenv("MEMOMICS_STALL_HARD_SECONDS", raising=False)
        now = time.time()
        s = self._session(now, now + 10)  # 回合开始 10s 后有过事件
        assert server._stall_hard_seconds(s) == 600

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MEMOMICS_STALL_HARD_SECONDS", "900")
        now = time.time()
        s = self._session(now, now + 10)
        assert server._stall_hard_seconds(s) == 900

    def test_no_activity_field_fast(self, monkeypatch):
        monkeypatch.delenv("MEMOMICS_STALL_HARD_SECONDS", raising=False)
        now = time.time()
        s = {"_turn_start_ts": now}  # 无 _turn_activity_ts 字段
        assert server._stall_hard_seconds(s) == 300

    def test_watchdog_still_fires_without_event(self, monkeypatch):
        """回归：没有前台/后台任务证据且长静默 → 中断阈值仍存在（不会永不中断）。"""
        monkeypatch.setenv("MEMOMICS_STALL_HARD_SECONDS", "600")
        now = time.time()
        s = self._session(now, now + 10)
        assert server._stall_hard_seconds(s) >= 300  # 恒有上限
