"""SQLite 保养（2026-10-13）。

背景：实测 `memomics_home/state.db` **1,090 MB** + `state.db-wal` **300 MB**（未及时
checkpoint）→ 写延迟尖刺、事件循环被堵、界面间歇性卡住。本模块在启动后于**后台线程**
做一次保守保养（绝不在请求路径上跑）：

  1) WAL 超过阈值（默认 100 MB）→ `PRAGMA wal_checkpoint(TRUNCATE)`；
  2) `PRAGMA optimize`；
  3) 两个全文索引（messages_fts / messages_fts_trigram）→ `VALUES('optimize')`；
  4) 碎片率高（freelist/page_count > 0.25）且 24h 内没做过 → `VACUUM`（可能几十秒）；
  5) `PRAGMA journal_mode` 保持 WAL。

日志：`<root>/log/db_maintenance.log`。全部异常吞掉（保养失败不能影响应用）。
`timeout=5s`：数据库被占用时直接跳过，绝不排队等锁。
"""

from __future__ import annotations

import os
import sqlite3
import time

DEFAULT_WAL_THRESHOLD_MB = 100.0
DEFAULT_VACUUM_RATIO = 0.25
DEFAULT_MIN_INTERVAL_H = 24.0


def _log(log_path: str, text: str) -> None:
    try:
        d = os.path.dirname(log_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
    except OSError:
        pass


def _wal_size_mb(db_path: str) -> float:
    for suffix in ("-wal",):
        p = db_path + suffix
        try:
            return os.path.getsize(p) / 1024 / 1024
        except OSError:
            pass
    return 0.0


def _last_vacuum_ts(db_path: str, log_path: str) -> float:
    """从保养日志里读上次 VACUUM 时间（没有则 0）。"""
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in reversed(f.readlines()[-200:]):
                if "VACUUM 完成" in line:
                    stamp = line[:19]
                    return time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))
    except (OSError, ValueError):
        pass
    return 0.0


def run_maintenance(db_path: str, log_path: str, *,
                    wal_threshold_mb: float = DEFAULT_WAL_THRESHOLD_MB,
                    vacuum_ratio: float = DEFAULT_VACUUM_RATIO,
                    min_interval_h: float = DEFAULT_MIN_INTERVAL_H) -> dict:
    """执行一次保养，返回统计（不抛异常）。"""
    stats: dict = {"db": db_path, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    if not os.path.isfile(db_path):
        stats["skipped"] = "db not found"
        return stats
    wal_mb = _wal_size_mb(db_path)
    stats["wal_mb_before"] = round(wal_mb, 1)
    try:
        conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
        cur = conn.cursor()
        try:
            if wal_mb >= wal_threshold_mb:
                row = cur.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                stats["checkpoint"] = list(row) if row else "ok"
            else:
                stats["checkpoint"] = "skipped"
            cur.execute("PRAGMA optimize")
            stats["optimize"] = "ok"
            fts_done = []
            for tbl in ("messages_fts", "messages_fts_trigram"):
                try:
                    cur.execute(f"INSERT INTO {tbl}({tbl}) VALUES('optimize')")
                    fts_done.append(tbl)
                except sqlite3.Error:
                    pass
            stats["fts_optimize"] = fts_done
            try:
                page_count = cur.execute("PRAGMA page_count").fetchone()[0]
                freelist = cur.execute("PRAGMA freelist_count").fetchone()[0]
                ratio = (freelist / page_count) if page_count else 0.0
                stats["free_ratio"] = round(ratio, 3)
                last = _last_vacuum_ts(db_path, log_path)
                age_h = (time.time() - last) / 3600 if last else 1e9
                if ratio > vacuum_ratio and age_h >= min_interval_h:
                    t0 = time.time()
                    cur.execute("VACUUM")
                    stats["vacuum"] = "ok"
                    stats["vacuum_sec"] = round(time.time() - t0, 1)
                else:
                    stats["vacuum"] = "skipped"
            except sqlite3.Error as exc:
                stats["vacuum"] = "error: %s" % exc
        finally:
            conn.close()
    except sqlite3.Error as exc:
        stats["error"] = str(exc)
    stats["wal_mb_after"] = round(_wal_size_mb(db_path), 1)
    _log(log_path, "保养完成：%s" % stats)
    return stats


def run_maintenance_async(db_path: str, root_dir: str) -> None:
    """在后台线程里跑一次保养（启动时调用，不阻塞）。"""
    import threading
    log_path = os.path.join(root_dir, "log", "db_maintenance.log")
    t = threading.Thread(target=lambda: run_maintenance(db_path, log_path),
                         name="db-maintenance", daemon=True)
    t.start()