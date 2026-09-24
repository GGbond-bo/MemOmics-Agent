# -*- coding: utf-8 -*-
"""T10 守卫：阶段历史推 ETA（memomics/bio_tools/task_eta.py）。

面板要给「还要多久」，最怕给一个没出处的数字。这个文件的测试就守着三件事：
  A. 口径统一：时间格式化必须和 task_run.Task._fmt_sec 一模一样（同一个面板同一句话）；
  B. 历史要真：只统计真跑完的任务，按 (类型, 脚本名) 分组，逐阶段求平均；
  C. 算不出来就说不知道：没历史、没进度、任务已结束 —— 一律 sec=None，不许瞎猜。
"""
import datetime
import importlib.util
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
TRCLI = os.path.join(_REPO, "memomics", "bio_tools", "task_run.py")
ETACLI = os.path.join(_REPO, "memomics", "bio_tools", "task_eta.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def eta():
    return _load("task_eta_u", ETACLI)


@pytest.fixture()
def tr():
    try:
        from memomics.bio_tools import task_run
        return task_run
    except Exception:
        return _load("task_run_u", TRCLI)


def _mk(stages, status="done", ttype="qc", script="qc.R", progress=None, started_ago=None,
        started_at=None):
    """造一条契约（只放 ETA 会看的字段）。"""
    rows = []
    for row in stages:
        rows.append(dict(row))
    task = {"task_id": "t-" + str(abs(hash((ttype, script, status))) % 100000), "type": ttype,
            "script": script, "status": status, "stages": rows}
    if progress is not None:
        task["progress"] = {"value": progress, "text": ""}
    if started_ago is not None:
        base = datetime.datetime(2026, 9, 24, 12, 0, 0)
        task["started_at"] = (base - datetime.timedelta(seconds=started_ago)).strftime("%Y-%m-%d %H:%M:%S")
        task["_now"] = base
    if started_at:
        task["started_at"] = started_at
    return task


def _stage(name, status, sec=None, started_ago=None, now=None):
    row = {"name": name, "status": status}
    if sec is not None:
        row["sec"] = sec
    if started_ago is not None:
        row["started_at"] = ((now or datetime.datetime(2026, 9, 24, 12, 0, 0))
                             - datetime.timedelta(seconds=started_ago)).strftime("%Y-%m-%d %H:%M:%S")
    return row


# ------------------------------------------------------------------ A 口径
def test_a1_fmt_sec_same_convention_as_task_run(eta, tr):
    for value in (0, 1, 59, 60, 61, 599, 3600, 3661, 7325):
        assert eta.fmt_sec(value) == tr.Task._fmt_sec(value), value
    assert eta.fmt_sec(None) == ""
    assert eta.fmt_sec(-3) == tr.Task._fmt_sec(-3)
    assert eta.fmt_sec("bad") == ""
    assert eta.fmt_sec("90") == "1:30"


def test_a2_normalize_keeps_only_finished_stages_with_valid_sec(eta):
    task = _mk([_stage("读入", "done", 3.2), _stage("计算", "running"),
                _stage("出图", "pending"), {"name": "", "status": "done", "sec": 1},
                {"name": "坏秒", "status": "done", "sec": "x"}, {"name": "负秒", "status": "done", "sec": -2}])
    assert eta.normalize_stages(task) == [("读入", 3.2)]


def test_a2b_contract_timestamps_are_read_as_utc(eta):
    """契约时间是 UTC ISO；按本机时区读会整整差一个时差（东八区就差 8 小时）。"""
    got = eta._parse_time("2026-09-24T05:35:00+00:00")
    assert got is not None and got.tzinfo is not None
    assert eta._parse_time("2026-09-24T05:35:00Z").hour == 5
    assert eta._parse_time("2026-09-24 05:35:00").tzinfo is not None, "裸格式也必须当 UTC"
    assert eta._parse_time("") is None and eta._parse_time(None) is None
    assert eta._parse_time("不是时间") is None
    # 真跑一条：20 秒前起的、进度 50% → 还要 ~20 秒，而不是 8 小时
    now = datetime.datetime.now(datetime.timezone.utc)
    started = (now - datetime.timedelta(seconds=20)).isoformat(timespec="seconds")
    task = _mk([_stage("读入", "running")], status="running", progress=0.5, script="nobody.R")
    task["started_at"] = started
    out = eta.estimate(task, {}, now=now)
    assert out["sec"] == pytest.approx(20.0, abs=2.0), out


def test_a3_group_key_is_type_plus_script_name(eta):
    a = _mk([], ttype="cellbender", script=r"E:\sess\scripts\run.R")
    b = _mk([], ttype="cellbender", script="run.R")
    other = _mk([], ttype="cellbender", script="other.R")
    assert eta.group_key(a) == eta.group_key(b) == ("cellbender", "run.R")
    assert eta.group_key(other) != eta.group_key(a)


# ------------------------------------------------------------------ B 历史
def test_b1_history_groups_and_averages(eta):
    tasks = [
        _mk([_stage("读入", "done", 10), _stage("计算", "done", 30)], script="qc.R"),
        _mk([_stage("读入", "done", 20), _stage("计算", "done", 50)], script="qc.R"),
        _mk([_stage("读入", "done", 99)], script="other.R"),
        _mk([_stage("读入", "running", started_ago=5)], status="running", script="qc.R"),
        _mk([_stage("读入", "done", 1)], status="interrupted", script="qc.R"),
        _mk([{"name": "没秒数", "status": "done"}], script="qc.R"),
    ]
    hist = eta.collect_history(tasks)
    bucket = hist[("qc", "qc.R")]
    assert bucket["tasks"] == 2, "只该统计真跑完且有阶段耗时的任务"
    assert bucket["stages"]["读入"]["mean"] == 15.0
    assert bucket["stages"]["计算"]["mean"] == 40.0
    assert bucket["mean_stage"] == 27.5
    assert bucket["mean_all"] == 55.0
    assert ("qc", "other.R") in hist


# ------------------------------------------------------------------ C 估算
def test_c1_estimate_from_history_covers_running_and_pending(eta):
    hist = eta.collect_history([
        _mk([_stage("读入", "done", 10), _stage("计算", "done", 30), _stage("出图", "done", 20)]),
        _mk([_stage("读入", "done", 12), _stage("计算", "done", 28), _stage("出图", "done", 22)]),
        _mk([_stage("读入", "done", 8), _stage("计算", "done", 32), _stage("出图", "done", 18)]),
    ])
    now = datetime.datetime(2026, 9, 24, 12, 0, 0)
    running = _mk([_stage("读入", "done", 10), _stage("计算", "running", started_ago=8),
                   _stage("出图", "pending")], status="running", progress=0.5)
    out = eta.estimate(running, hist, now=now)
    # 计算历史均值 30，已跑 8 → 还 22；出图历史 20 → 合计 42
    assert out["source"] == "history" and out["sec"] == pytest.approx(42.0, abs=1.5), out
    assert out["confidence"] == "高" and out["samples"] == 3
    assert "3 次" in out["basis"] and out["text"] == eta.fmt_sec(out["sec"])


def test_c2_estimate_falls_back_to_progress_and_says_so(eta):
    now = datetime.datetime(2026, 9, 24, 12, 0, 0)
    task = _mk([_stage("读入", "done", 5), _stage("计算", "running", started_ago=20)],
               status="running", progress=0.5, ttype="novel", script="nobody.R", started_ago=20)
    out = eta.estimate(task, {}, now=now)
    assert out["source"] == "progress" and out["confidence"] == "低"
    assert out["sec"] == pytest.approx(20.0, abs=1.5), out
    assert "进度" in out["basis"]


def test_c3_no_history_no_progress_means_no_number(eta):
    now = datetime.datetime(2026, 9, 24, 12, 0, 0)
    tiny = _mk([_stage("读入", "running", started_ago=20)], status="running", progress=0.01,
               ttype="novel", script="nobody.R", started_ago=20)
    assert eta.estimate(tiny, {}, now=now)["sec"] is None
    done = _mk([_stage("读入", "done", 5)], status="done")
    assert eta.estimate(done, {}, now=now)["sec"] is None
    failed = _mk([_stage("读入", "done", 5)], status="failed")
    assert eta.estimate(failed, {}, now=now)["sec"] is None
    assert eta.estimate({"status": "running"}, {}, now=now)["sec"] is None
    assert eta.estimate(None, {}, now=now)["sec"] is None


def test_c4_stage_without_history_uses_mean_and_lowers_confidence(eta):
    hist = eta.collect_history([
        _mk([_stage("读入", "done", 10), _stage("计算", "done", 30)]),
        _mk([_stage("读入", "done", 10), _stage("计算", "done", 30)]),
    ])
    now = datetime.datetime(2026, 9, 24, 12, 0, 0)
    task = _mk([_stage("读入", "done", 10), _stage("没见过的段", "pending")], status="running")
    out = eta.estimate(task, hist, now=now)
    assert out["source"] == "history" and out["partial"] is True
    assert out["confidence"] == "中" and out["sec"] == pytest.approx(20.0, abs=0.5), out
    assert "兜底" in out["basis"]


def test_c5_overdue_running_stage_never_goes_negative(eta):
    hist = eta.collect_history([_mk([_stage("读入", "done", 10), _stage("计算", "done", 30)])])
    now = datetime.datetime(2026, 9, 24, 12, 0, 0)
    task = _mk([_stage("读入", "done", 10), _stage("计算", "running", started_ago=999),
                _stage("出图", "pending")], status="running")
    hist[("qc", "qc.R")]["stages"]["出图"] = {"n": 1, "sum": 20.0, "mean": 20.0}
    out = eta.estimate(task, hist, now=now)
    assert out["sec"] == pytest.approx(20.0, abs=0.5), "超时的段按 0 算，不能倒扣出负数"


def test_c5b_elapsed_without_started_at_falls_back_to_progress_only(eta):
    now = datetime.datetime(2026, 9, 24, 12, 0, 0)
    no_time = _mk([_stage("读入", "running")], status="running", progress=0.5, script="nobody.R")
    assert eta.estimate(no_time, {}, now=now)["sec"] is None, "连开始时间都没有，就别给数"


def test_c6_queued_task_gets_whole_history_estimate(eta):
    hist = eta.collect_history([
        _mk([_stage("读入", "done", 10), _stage("计算", "done", 30)]),
        _mk([_stage("读入", "done", 10), _stage("计算", "done", 30)]),
    ])
    queued = _mk([_stage("读入", "pending"), _stage("计算", "pending")], status="queued")
    out = eta.estimate(queued, hist)
    assert out["sec"] == pytest.approx(40.0, abs=0.5), out
