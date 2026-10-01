# -*- coding: utf-8 -*-
"""LoopX 自检唤醒的刹车（2026-10-02 用户报「重复答案 + LoopX 一直有任务」）。

三处叠加让循环停不下来：
  1. loopx_bridge.should_run() 把 LoopX 的 waiting/skip/no_run/connected_without_run
     无条件改写成「继续跑」。LoopX 自己说的是 waiting、理由 "no active Codex-ready
     work is currently selected"（就是没活干了）。
  2. server._schedule_self_check 只认 blocked/blocked_health/paused/throttled 四个硬停
     状态，state=waiting 时即使 should_run=False 也照样唤醒 —— 于是连"尊重 LoopX"
     这条路都被堵死，循环完全没有刹车（.loopx/runs 一天 63 条，实测）。
  3. 唤醒撞上运行中回合时，重排会把自己标成 urgent；urgent 把延迟压到 3 秒并绕开
     「外部工作无新进展就跳过 LLM 唤醒」的省 token 闸门 → 3 秒一轮的 #1/3 #2/3 #3/3
     重试风暴。

另修：waiting_review 是唤醒提示词指示模型用的状态（server.py:2350），紧急唤醒判据也
在读它（server.py:18712「待审阅任务，触发立即唤醒」），但它不在 TodoStore.VALID_STATUSES
里 → _validate 静默改写成 pending → 那条紧急唤醒分支一直是死代码。
"""
import importlib.util
import os
import sys
import uuid

import pytest

import server  # noqa: F401  —— 顺带把 hermes-agent 挂上 sys.path（tools.todo_tool 需要）

from memomics import loopx_bridge as bridge_mod


def _tmp_results(tmp_path, name="memomics-test-" + uuid.uuid4().hex[:8]):
    """造一个带 .loopx/registry.json 的结果目录（LoopXBridge 构造时幂等建注册表）。"""
    rd = tmp_path / name
    rd.mkdir(parents=True, exist_ok=True)
    return str(rd)


def _fake_loopx(decision):
    """替掉 vendor loopx：collect 有返回、quota 给固定判定。"""
    return {
        "collect_status": lambda **kw: {"goals": [{"id": "g"}], "run_count": 0},
        "build_quota_should_run": lambda status, **kw: dict(decision),
        "build_heartbeat_prompt": lambda *a, **kw: "",
        "build_scheduler_hint": lambda *a, **kw: {},
    }


WAITING = {"should_run": False, "state": "waiting", "decision": "wait",
           "reason": "no active Codex-ready work is currently selected"}


# --- 1. 核心回归：LoopX 说 waiting、且确无外部工作 → 真的停 ---

def test_waiting_without_activity_stops_the_loop(tmp_path, monkeypatch):
    """改造前：无条件 should_run=True，循环永远跑（这就是用户报的根因）。"""
    monkeypatch.setattr(bridge_mod, "_load_loopx", lambda: _fake_loopx(WAITING))
    b = bridge_mod.LoopXBridge("memomics-test", _tmp_results(tmp_path), user_online=True)
    d = b.should_run()
    assert d["state"] == "waiting"
    assert d["should_run"] is False, "产出窗口内没有任何真实写入，就该尊重 LoopX 的 waiting"
    assert d["decision"] == "wait"
    assert "无真实写入" in d["reason"]


def test_waiting_with_activity_still_runs(tmp_path, monkeypatch):
    """老注释的担忧仍然成立：外部管线在动（有真实产出）→ 继续盯。"""
    monkeypatch.setattr(bridge_mod, "_load_loopx", lambda: _fake_loopx(WAITING))
    rd = _tmp_results(tmp_path)
    with open(os.path.join(rd, "figures_volcano.png"), "w", encoding="utf-8") as f:
        f.write("x")
    d = bridge_mod.LoopXBridge("memomics-test", rd, user_online=True).should_run()
    assert d["should_run"] is True
    assert d["decision"] == "run"
    assert "外部管线在动" in d["reason"]


def test_hard_stop_states_still_stop(tmp_path, monkeypatch):
    """blocked/paused/throttled 这类硬停不受影响（不因新判据被放行）。"""
    blocked = {"should_run": False, "state": "paused", "decision": "stop", "reason": "quota paused"}
    monkeypatch.setattr(bridge_mod, "_load_loopx", lambda: _fake_loopx(blocked))
    rd = _tmp_results(tmp_path)
    with open(os.path.join(rd, "fresh.txt"), "w", encoding="utf-8") as f:
        f.write("x")
    d = bridge_mod.LoopXBridge("memomics-test", rd, user_online=True).should_run()
    assert d["should_run"] is False
    assert d["state"] == "paused"


# --- 2. 活动判据本身（纯文件系统，不依赖 LoopX）---

def test_has_live_activity_ignores_platform_selfwrites(tmp_path):
    """只看平台自写的记账文件 → 没有真实工作。否则循环会被自己写的 token_usage
    喂活，永远停不下来（server.py 的产出判定也是排除这几项的）。"""
    rd = _tmp_results(tmp_path)
    for name in ("token_usage.jsonl", ".task_state.json", "task_plan.md"):
        with open(os.path.join(rd, name), "w", encoding="utf-8") as f:
            f.write("x")
    os.makedirs(os.path.join(rd, "log"), exist_ok=True)
    with open(os.path.join(rd, "log", "run.log"), "w", encoding="utf-8") as f:
        f.write("x")
    os.makedirs(os.path.join(rd, ".loopx", "goals"), exist_ok=True)
    with open(os.path.join(rd, ".loopx", "goals", "run.json"), "w", encoding="utf-8") as f:
        f.write("x")
    assert bridge_mod.LoopXBridge("s", rd).has_live_activity() is False


def test_has_live_activity_sees_nested_and_respects_window(tmp_path):
    """真产出现在子目录里（figures/…），只比顶层目录 mtime 会漏判；
    超过窗口的老文件不算。"""
    rd = _tmp_results(tmp_path)
    figdir = os.path.join(rd, "figures")
    os.makedirs(figdir, exist_ok=True)
    old_ts = os.path.getmtime(figdir) - 3 * 3600
    os.utime(figdir, (old_ts, old_ts))  # 回拨目录 mtime，隔离出"嵌套文件"这一项
    assert bridge_mod.LoopXBridge("s", rd).has_live_activity() is False, "只剩老目录，不算活动"
    nested = os.path.join(figdir, "volcano.png")
    with open(nested, "w", encoding="utf-8") as f:
        f.write("x")
    assert bridge_mod.LoopXBridge("s", rd).has_live_activity() is True
    # 回拨"3 小时前"：注意写文件会刷新父目录 mtime，所以父目录也要一起回拨，
    # 否则剩下的是"父目录刚被动过"这个信号（那本身也是合法的活动信号）。
    old = 3 * 3600
    for _p in (nested, figdir):
        _t = os.path.getmtime(_p) - old
        os.utime(_p, (_t, _t))
    assert bridge_mod.LoopXBridge("s", rd).has_live_activity() is False, "3 小时前的产出不算活动"


def test_fresh_directory_counts_as_activity(tmp_path):
    """有意的：agent 建完 figures/ 往往要算很久才写第一个文件，
    这期间只比"目录刚被创建"就该继续盯，不能误判成没活。"""
    rd = _tmp_results(tmp_path)
    os.makedirs(os.path.join(rd, "figures"), exist_ok=True)
    assert bridge_mod.LoopXBridge("s", rd).has_live_activity() is True


def test_has_live_activity_survives_missing_dir(tmp_path):
    """目录不存在/不可读 → False，不抛（桥接有安全默认兜底）。"""
    assert bridge_mod.LoopXBridge("s", str(tmp_path / "nope")).has_live_activity() is False
    assert bridge_mod.LoopXBridge("s", "").has_live_activity() is False


# --- 3. 服务端两处接线（改造点靠源码结构断言，避免"改了这边漏了那边"）---

def _server_src():
    return open(os.path.join(os.path.dirname(server.__file__), "server.py"), encoding="utf-8").read()


def test_server_no_longer_gates_stop_on_hard_stop_only():
    """服务端原来只认四个硬停状态，waiting 的 should_run=False 被忽略 → 没刹车。"""
    src = _server_src()
    assert '_HARD_STOP = {"blocked", "blocked_health", "paused", "throttled"}' not in src, \
        "硬停白名单又回来了：waiting 会被放行"
    assert 'if not _dec.get("should_run") and not urgent:' in src, "没接上"
    assert "LoopX {_state} 停止唤醒" in src


def test_wakeup_retry_only_urgent_when_it_was_urgent():
    """重排不许无条件设 urgent（urgent=3 秒延迟 + 绕开省 token 闸门）。"""
    # 全仓有 11 处合法地设 _urgent_wakeup（cron 告警/说而不做/空响应重试…），
    # 这里只盯"重排"那一处：它必须带上 if urgent 条件。
    src = _server_src()
    i = src.index("唤醒遇运行中回合")
    window = src[max(0, i - 320):i + 60]
    assert 's["_urgent_wakeup"] = True' in window, "找不到重排点的赋值"
    assert "if urgent:" in window, \
        "重排点没接上 if urgent 条件，urgent 重试风暴会复发"


# --- 4. waiting_review 对齐 ---

def test_waiting_review_survives_a_round_trip():
    """提示词让模型标 waiting_review，store 却把它改写成 pending → 紧急唤醒判据
    （server.py:18712）永远为假。"""
    spec = importlib.util.spec_from_file_location(
        "hermes_todo_tool_wr",
        os.path.join(os.path.dirname(server.__file__), "..", "hermes-agent", "tools", "todo_tool.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_todo_tool_wr"] = mod
    spec.loader.exec_module(mod)
    store = mod.TodoStore()
    store.write([{"id": "t1", "content": "待审阅的聚类结果", "status": "waiting_review"}])
    got = store.read()[0]
    assert got["status"] == "waiting_review", "又被改写成 %r 了" % got["status"]
    store.write([{"id": "t1", "status": "completed"}], merge=True)
    assert store.read()[0]["status"] == "completed"
