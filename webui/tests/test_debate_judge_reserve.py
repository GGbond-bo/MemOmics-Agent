# -*- coding: utf-8 -*-
"""「角色阶段不许吃光预算」回归（2026-10-13）。

背景：L1/L2 的角色（采样）阶段曾经能把整场预算耗完 → 裁判整理 + 裁判一次都没跑上 →
judge_error=True → decision_source=engine_backfill（白跑一场）。修法 = 角色阶段限时
「当前剩余预算 − 裁判预留」，角色阶段结束再把预算还给裁判（MEMOMICS_DEBATE_JUDGE_RESERVE）。

L1 实测（2026-10-13 冒烟）：采样 106s → 裁判阶段 253s → 整场 303.6s → decision_source=judge。
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from memomics.bio_tools import debate_analysis as da  # noqa: E402


def _ctx(sid):
    da.set_session_context(sid=sid, results_dir="")


class TestJudgeReserve:
    def test_role_phase_reserves_judge_window(self):
        _ctx("t_reserve_a")
        da._set_debate_deadline(900)
        st = da._role_phase_begin()
        left = da._budget_left()
        assert 700 <= left <= 760, left          # 900 - 150 预留
        back = da._role_phase_end(st)
        assert back >= da._judge_reserve()
        assert da._budget_left() > 700            # 还回给裁判阶段

    def test_role_phase_end_never_below_reserve(self):
        """角色把预算吃光时，也要保证裁判阶段至少有预留秒数。"""
        _ctx("t_reserve_b")
        da._set_debate_deadline(900)
        back = da._role_phase_end((time.time() - 880, 900))    # 假装角色跑了 880s
        assert back == da._judge_reserve(), back
        left = da._budget_left()
        assert da._judge_reserve() - 2 <= left <= da._judge_reserve() + 2, left

    def test_no_deadline_means_no_interference(self):
        """没登记预算（inf）时不许乱设闸门。"""
        _ctx("t_reserve_c")
        with da._DEADLINE_LOCK:
            da._DEADLINES.pop("t_reserve_c", None)
            da._DEADLINE_BUDGETS.pop("t_reserve_c", None)
        st = da._role_phase_begin()
        assert da._budget_left() == float("inf")
        assert da._role_phase_end(st) == 0.0

    def test_l1_and_l2_use_the_same_helpers(self):
        """L1 与 L2 都必须挂上预留（源码级断言，防止以后只改一处）。"""
        import inspect
        src = inspect.getsource(da._debate_l1_lightweight)
        assert "_role_phase_begin()" in src and "_role_phase_end(" in src
        src2 = inspect.getsource(da.debate_analysis)
        assert "_role_phase_begin()" in src2 and "_role_phase_end(" in src2, "L2 轮次循环也要预留"

    def test_reserve_is_configurable(self, monkeypatch):
        monkeypatch.setenv("MEMOMICS_DEBATE_JUDGE_RESERVE", "200")
        assert da._judge_reserve() == 200.0
        monkeypatch.setenv("MEMOMICS_DEBATE_JUDGE_RESERVE", "5")     # 下限兜底
        assert da._judge_reserve() == 60.0