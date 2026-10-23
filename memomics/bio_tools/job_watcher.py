# -*- coding: utf-8 -*-
"""作业轮询器（2026-10-18 用户定稿：5 分钟常规 + 30 秒首查）。

铁律（用户明确）：
  · **只对"活作业"轮询**：status ∈ {running, starting}；工作集为空 → **一条 ssh 都不发**
  · 完成/失败/丢失并通知后 → 移出工作集，**永不回头查**
  · 按 host 分组，每组一条 ssh（多节点不漏、不重复）
  · 新作业 30 秒首查（脚本秒挂能立刻发现），之后每 5 分钟
  · 通知写进会话（results/<sid>/log/job_notifications.jsonl），**不唤醒模型**
    —— 下个回合的 jobs_summary 会自然显示 done/failed 状态
  · 顺带对 queued 作业做 promote（资源宽松就放行）
"""
from __future__ import annotations

import json
import os
import threading
import time

from memomics.bio_tools import node_state as ns

INTERVAL = float(os.environ.get("MEMOMICS_JOB_WATCH_INTERVAL", "300"))    # 5 分钟
FIRST_CHECK = float(os.environ.get("MEMOMICS_JOB_FIRST_CHECK", "30"))     # 30 秒首查
_tick_count = 0
_started = False
_lock = threading.Lock()
_state = {"last_tick": 0.0, "last_polled": None, "quiet_ticks": 0, "notified": 0}


def _notify_path(sid: str) -> str:
    base = os.path.join(os.environ.get("MEMOMICS_RESULTS_ROOT", r"<安装目录>"), sid or "_unknown")
    return os.path.join(base, "log", "job_notifications.jsonl")


def append_notification(sid: str, job: dict, text: str) -> None:
    """通知落盘到会话目录（前端/后续回合可见），失败静默。"""
    try:
        p = _notify_path(sid)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(),
                                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "job_id": job.get("job_id"), "status": job.get("status"),
                                "exit_code": job.get("exit_code"),
                                "peak_rss_gb": job.get("peak_rss_gb"),
                                "text": text}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _active_jobs() -> list:
    return [j for j in ns.list_jobs() if j.get("status") in ("running", "starting")]


def tick(force: bool = False, do_first_check: bool = True) -> dict:
    """执行一轮：没有活作业就直接返回（0 ssh）。返回本轮摘要，便于测试/观测。"""
    jobs = _active_jobs()
    now = time.time()
    _state["last_tick"] = now
    if not jobs:
        _state["quiet_ticks"] = int(_state.get("quiet_ticks", 0)) + 1
        return {"checked": 0, "quiet": True, "active": 0, "ssh_calls": 0,
                "message": "无活作业 → 静默（未发任何 ssh）"}

    fresh = [j for j in jobs
             if do_first_check and not j.get("first_checked")
             and (now - float(j.get("started_at") or j.get("created_at") or now)) >= FIRST_CHECK]
    # 2026-10-20 实测 bug 修复：必须按**作业自己的连接参数**（user/key/跳板）分组，
    # 否则 ssh 缺少 -J/-i 会连不上 → 正在跑的作业被误判 lost（T3 实测踩到）。
    groups = {}
    for j in jobs:
        gk = (j.get("host") or "", j.get("user") or "", int(j.get("port") or 22),
              j.get("key") or "", tuple(j.get("extra_opts") or []))
        groups.setdefault(gk, {})[j["job_id"]] = j
    ssh_calls = 0
    polled = {}
    for (h, u, pt, kk, ex), gjobs in groups.items():
        try:
            r = ns._poll_one_host(h, gjobs, u, pt, kk, list(ex))
            ssh_calls += 1 if h else 0
            polled.update(r.get("jobs") or {})
        except Exception:
            continue
    hosts = sorted({g[0] for g in groups})
    # 状态变化 → 通知 + 标记（只发一次）
    notified = []
    for j in ns.list_jobs():
        if j.get("status") in ("done", "failed", "lost", "cancelled") and not j.get("notified"):
            sid = j.get("session_id") or "_unknown"
            if j.get("status") == "done":
                txt = (f"✅ 集群作业完成：{j['job_id']}（exit 0，"
                       f"node={j.get('node') or j.get('host')}）")
            elif j.get("status") == "failed":
                txt = (f"❌ 集群作业失败：{j['job_id']}（exit {j.get('exit_code')}，"
                       f"node={j.get('node') or j.get('host')}）—— 可 action=\"logs\" 看日志尾部")
            elif j.get("status") == "lost":
                txt = f"⚠️ 集群作业失联：{j['job_id']}（{j.get('reason') or '进程消失且无退出码'}）"
            else:
                txt = f"⏹ 集群作业已取消：{j['job_id']}"
            append_notification(sid, j, txt)
            ns.update_job(j["job_id"], notified=True, notified_at=now)
            notified.append({"job_id": j["job_id"], "status": j["status"], "session": sid})
    for j in fresh:
        if j.get("status") in ("running", "starting"):
            ns.update_job(j["job_id"], first_checked=True, first_checked_at=now)
    try:
        promo = ns.promote_queued()
    except Exception as exc:
        promo = {"error": str(exc)}
    _state["notified"] = int(_state.get("notified", 0)) + len(notified)
    _state["quiet_ticks"] = 0
    return {"checked": len(polled), "active": len(jobs), "hosts": hosts,
            "ssh_calls": ssh_calls, "first_checked": [j["job_id"] for j in fresh],
            "notified": notified, "promote": promo, "quiet": False}


def _loop(interval: float, first_check: float):
    global _tick_count
    time.sleep(10)                      # 服务启动后稍等再开始
    while True:
        try:
            _tick_count += 1
            tick()
        except Exception:
            pass
        time.sleep(max(interval, 5))


def start_watcher(interval: float = None, first_check: float = None) -> dict:
    """启动后台轮询线程（幂等）。工作集为空时它只是睡眠，不发 ssh。"""
    global _started
    with _lock:
        if _started:
            return {"started": False, "already": True, "interval": INTERVAL}
        _started = True
    threading.Thread(target=_loop, args=(interval or INTERVAL, first_check or FIRST_CHECK),
                     daemon=True, name="job-watcher").start()
    return {"started": True, "interval": interval or INTERVAL,
            "first_check": first_check or FIRST_CHECK}


def watcher_state() -> dict:
    return {**_state, "running": _started, "ticks": _tick_count,
            "interval": INTERVAL, "first_check": FIRST_CHECK,
            "active_jobs": len(_active_jobs())}
