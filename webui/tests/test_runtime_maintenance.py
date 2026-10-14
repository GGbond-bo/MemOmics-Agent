# -*- coding: utf-8 -*-
"""运行期诊断/保养（2026-10-13）：慢循环看门狗 + SQLite 保养 + 任务注册表收紧。

背景：用户反馈 memomics-2274ab75 "卡住、暂停不立即解决"。实测 /api/sessions（纯内存遍历，
正常 0.03s）耗时 33.4s → 事件循环被同步重活堵住；state.db 1,090MB + WAL 300MB。
"""
import os
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "webui", "runtime"))

import db_maintenance  # noqa: E402
import slow_loop_watchdog  # noqa: E402
from job_store import JobStore  # noqa: E402


def test_watchdog_logs_stall_with_stack(tmp_path):
    """心跳停住 → 记「阻塞开始」+ 调用栈；恢复 → 记「阻塞结束」。"""
    log = tmp_path / "slow_loop.log"
    wd = slow_loop_watchdog.SlowLoopWatchdog(str(log), threshold=0.6).start()
    try:
        time.sleep(1.8)                      # 故意不打心跳
        text = log.read_text(encoding="utf-8") if log.is_file() else ""
        assert "阻塞开始" in text, text
        assert "thread" in text and "File" in text, "必须带调用栈（指出堵在哪）"
        for _ in range(6):                    # 恢复心跳
            wd.heartbeat()
            time.sleep(0.3)
        assert "阻塞结束" in log.read_text(encoding="utf-8")
    finally:
        wd.stop()


def test_watchdog_silent_when_healthy(tmp_path):
    log = tmp_path / "slow_loop.log"
    wd = slow_loop_watchdog.SlowLoopWatchdog(str(log), threshold=0.6).start()
    try:
        for _ in range(10):
            wd.heartbeat()
            time.sleep(0.15)
        assert not log.is_file() or "阻塞开始" not in log.read_text(encoding="utf-8")
    finally:
        wd.stop()


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t(a INTEGER PRIMARY KEY, b TEXT)")
    conn.executemany("INSERT INTO t(b) VALUES(?)", [("x" * 100,) for _ in range(2000)])
    conn.commit()
    return conn


def test_db_maintenance_runs_and_logs(tmp_path):
    db = tmp_path / "state.db"
    conn = _make_db(str(db))
    conn.close()
    log = tmp_path / "db_maintenance.log"
    stats = db_maintenance.run_maintenance(str(db), str(log), wal_threshold_mb=0.0)
    assert stats.get("error") is None, stats
    assert stats["checkpoint"] != "skipped", "阈值 0 时必须真的 checkpoint"
    assert stats["optimize"] == "ok"
    assert stats["fts_optimize"] == [], "没有 FTS 表时应为空列表（跳过）"
    assert stats["vacuum"] in ("ok", "skipped")
    assert "wal_mb_after" in stats
    assert log.is_file() and "保养完成" in log.read_text(encoding="utf-8")


def test_db_maintenance_skips_unknown_db(tmp_path):
    stats = db_maintenance.run_maintenance(str(tmp_path / "nope.db"), str(tmp_path / "l.log"))
    assert stats.get("skipped") == "db not found"


def test_db_maintenance_never_raises_on_locked_db(tmp_path):
    """数据库被别人占着时只跳过，绝不阻塞/抛错。"""
    db = tmp_path / "locked.db"
    conn = _make_db(str(db))
    conn.execute("BEGIN EXCLUSIVE")           # 占住写锁
    try:
        stats = db_maintenance.run_maintenance(str(db), str(tmp_path / "l.log"), wal_threshold_mb=0.0)
        assert isinstance(stats, dict)
    finally:
        conn.execute("ROLLBACK")
        conn.close()


def test_job_store_history_limit_default_is_tightened(tmp_path):
    assert JobStore(str(tmp_path / "jobs.json")).history_limit == 300


def test_server_wires_watchdog_and_maintenance():
    src = open(os.path.join(ROOT, "webui", "server.py"), encoding="utf-8", errors="replace").read()
    assert "_start_runtime_maintenance" in src
    assert "slow_loop_watchdog" in src and "db_maintenance" in src
    assert "_slow_loop_heartbeat" in src