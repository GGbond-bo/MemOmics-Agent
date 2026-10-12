# -*- coding: utf-8 -*-
"""「任务状态和实际对不上」的回归（2026-10-12）。

用户反馈两种相反方向：
  * 「都已经停了，实际上还在跑」——/api/sessions 的 is_running 用
    `bool(running_agent or running_task)`，**跑完但引用还没清**的 asyncio.Task 也算运行中；
  * 「跑到一半，图还没有出现」——结果面板只在 complete 时补刷一次(2.5s)就停轮询，
    最后落盘的图/表比事件晚，就永远不显示（前端侧改动见 index.html 的 _resultsGraceUntil）。

本文件锁死后端那半：is_running 必须按「Task 是否真的没跑完」判定。
"""
import server


class _FakeTask:
    """最小替身：被测代码只调 .done()。"""

    def __init__(self, done):
        self._done = done

    def done(self):
        return self._done


def test_finished_task_is_not_running():
    """跑完的 Task（引用还没被 done_callback 清掉）不能算运行中——就是这个坑。"""
    assert server._session_run_flags({"running_agent": object(), "running_task": _FakeTask(True)}) is False


def test_pending_task_is_running():
    assert server._session_run_flags({"running_agent": object(), "running_task": _FakeTask(False)}) is True


def test_string_sentinel_is_running():
    """微信链路用的是字符串哨兵（weixin_agent），没有 done() 可问 → 视为运行中。"""
    assert server._session_run_flags({"running_agent": True, "running_task": "weixin_agent"}) is True


def test_agent_object_without_task_counts_as_running():
    """建 task 之前的窗口期：只有 running_agent 对象。"""
    assert server._session_run_flags({"running_agent": object(), "running_task": None}) is True


def test_idle_session_is_not_running():
    assert server._session_run_flags({"running_agent": None, "running_task": None}) is False
    assert server._session_run_flags({}) is False


def test_broken_task_object_does_not_crash():
    class _Weird:
        def done(self):
            raise RuntimeError("boom")

    assert server._session_run_flags({"running_task": _Weird()}) is True   # 问不出来就当在跑，别误报"停了"