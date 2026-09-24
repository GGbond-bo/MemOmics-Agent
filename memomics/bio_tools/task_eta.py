# -*- coding: utf-8 -*-
"""阶段历史推 ETA —— 用「同类型任务的历史阶段耗时」回答「还要多久」。

为什么不拿进度百分比硬外推：一条 6 段生信流水线，各段耗时能差 100 倍
（读矩阵 2s、CellBender 40min、出图 3s），按百分比线性外推必然骗人。
所以分两级，并且**每一级都带出处**：

  1) 历史优先（source=history）：同类型（+ 同脚本名）的已结束任务，按阶段名汇总
     平均耗时；正在跑的那段按「历史均值 − 已跑」补差，没开始的段直接累加。
     样本不足 3 条或某一阶段查无历史时，用该类型的「平均单段耗时」兜底并降置信度。
  2) 没历史才用自身进度线性外推（source=progress，进度得过 5% 才有意义）。

任何一步算不出来就返回 sec=None —— 宁可不显示，也不显示一个没有出处的数字。
"""
from __future__ import annotations

import datetime
import os
# 契约里的时间是 UTC ISO（task_run.utc_now()），这里必须按 UTC 解析：
# 拿本机时区去比会整整差出一个时差，ETA 会算出「还要 8 小时」这种鬼话。
UTC = datetime.timezone.utc
from typing import Any, Dict, Iterable, List, Optional, Tuple

TERMINAL_STATES = ("done", "failed", "cancelled", "interrupted")
MAX_STAGES = 64


def fmt_sec(sec: Optional[float]) -> str:
    """秒 → 人话。**刻意和 task_run.Task._fmt_sec 逐字同口径**（<60s 用 Ns，否则 M:SS）。

    同一个面板上「已跑 12s」和「还要 1:20」必须是一套写法，
    所以这里不自己发明格式（连「负数算 0s」这种边角都跟它保持一致），
    并由 test_task_eta.py::test_a1 逐值对拍，防止以后两边漂掉。
    """
    if sec is None:
        return ""
    try:
        total = int(max(0.0, float(sec)))
    except (TypeError, ValueError):
        return ""
    return ("%d:%02d" % (total // 60, total % 60)) if total >= 60 else ("%ds" % total)


def _parse_time(raw: Any) -> Optional[datetime.datetime]:
    """契约时间 → 带时区的 UTC 时间。认 ISO(带 +00:00 / Z)，老格式（裸空格分隔）按 UTC 处理。"""
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        stamp = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        try:
            stamp = datetime.datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None
    return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(UTC)


def _as_utc(moment: Optional[datetime.datetime]) -> datetime.datetime:
    if moment is None:
        return _utc_now()
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _elapsed_sec(task: Dict[str, Any], now: Optional[datetime.datetime] = None) -> float:
    started = _parse_time(task.get("started_at"))
    if started is None:
        return 0.0
    return max(0.0, (_as_utc(now) - started).total_seconds())


def script_key(task: Dict[str, Any]) -> str:
    """同一条流水线的判定：类型 + 脚本文件名（没有脚本就用类型本身）。"""
    return os.path.basename(str(task.get("script") or "").strip())


def group_key(task: Dict[str, Any]) -> Tuple[str, str]:
    return (str(task.get("type") or "other"), script_key(task))


def stage_rows(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    stages = task.get("stages") or []
    return [s for s in stages[:MAX_STAGES] if isinstance(s, dict)]


def normalize_stages(task: Dict[str, Any]) -> List[Tuple[str, float]]:
    """契约里的 stages → [(名字, 秒数)]，只保留跑完且秒数有效的段。"""
    out: List[Tuple[str, float]] = []
    for row in stage_rows(task):
        if (row.get("status") or "") not in ("done", "failed", "cancelled"):
            continue
        try:
            sec = float(row.get("sec"))
        except (TypeError, ValueError):
            continue
        if sec < 0:
            continue
        name = str(row.get("name") or "").strip()
        if name:
            out.append((name, sec))
    return out


def collect_history(tasks: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """把已结束任务的阶段耗时汇成历史：{(type, script): {...}}。

    只统计真跑完（done/failed/cancelled）且至少有一段有效耗时的任务；
    没跑完、被中断、阶段全空的一律不进历史 —— 免得把「刚起就崩」的 0.3s 当基准。
    """
    buckets: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for task in tasks or []:
        if (task.get("status") or "") not in ("done", "failed", "cancelled"):
            continue
        rows = normalize_stages(task)
        if not rows:
            continue
        key = group_key(task)
        bucket = buckets.setdefault(key, {"tasks": 0, "stages": {}, "total_sec": 0.0})
        bucket["tasks"] += 1
        bucket["total_sec"] += sum(sec for _name, sec in rows)
        for name, sec in rows:
            slot = bucket["stages"].setdefault(name, {"n": 0, "sum": 0.0})
            slot["n"] += 1
            slot["sum"] += sec
    for bucket in buckets.values():
        count = bucket["tasks"] or 1
        bucket["mean_all"] = round(bucket["total_sec"] / count, 2)
        bucket["mean_stage"] = round(
            bucket["total_sec"] / max(1, sum(s["n"] for s in bucket["stages"].values())), 2)
        for name, slot in bucket["stages"].items():
            slot["mean"] = round(slot["sum"] / max(1, slot["n"]), 2)
    return buckets


def estimate(task: Dict[str, Any], history: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None,
             now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """估算一条任务还要多久 → {sec, text, basis, source, confidence, samples, partial}。

    sec=None 表示「不给数」（任务已结束 / 没历史也没进度 / 阶段信息缺失）。
    """
    blank: Dict[str, Any] = {"sec": None, "text": "", "basis": "", "source": "",
                             "confidence": "", "samples": 0, "partial": False}
    if not isinstance(task, dict):
        return blank
    if (task.get("status") or "") in TERMINAL_STATES:
        return blank
    rows = stage_rows(task)
    if not rows:
        return _by_progress(task, blank, now)
    now = _as_utc(now)

    pending = [r for r in rows if (r.get("status") or "") in ("pending", "running", "queued")]
    if not pending:
        return blank

    bucket = (history or {}).get(group_key(task)) or {}
    means = bucket.get("stages") or {}
    samples = int(bucket.get("tasks") or 0)
    partial = False
    total = 0.0
    for row in pending:
        name = str(row.get("name") or "").strip()
        slot = means.get(name) or {}
        if slot.get("mean") is not None:
            want = float(slot["mean"])
        elif bucket.get("mean_stage"):
            want = float(bucket["mean_stage"])
            partial = True
        else:
            want = None
        if want is None:
            continue
        if (row.get("status") or "") == "running":
            done_sec = 0.0
            started = _parse_time(row.get("started_at"))
            if started is not None:
                done_sec = max(0.0, (_as_utc(now) - started).total_seconds())
            total += max(0.0, want - done_sec)
        else:
            total += want

    if samples > 0 and total > 0:
        confidence = "高" if (samples >= 3 and not partial) else "中"
        basis = "按 %d 次同类型历史%s" % (samples, "（含均值兜底）" if partial else "")
        sec = round(total, 1)
        # 先取整再格式化：24.99 秒要是算成 sec=25.0 却显示 24s，面板上就是自相矛盾
        return {"sec": sec, "text": fmt_sec(sec), "basis": basis,
                "source": "history", "confidence": confidence, "samples": samples,
                "partial": partial}
    return _by_progress(task, blank, now)


def _by_progress(task: Dict[str, Any], blank: Dict[str, Any],
                 now: Optional[datetime.datetime]) -> Dict[str, Any]:
    """兜底：拿自身进度线性外推。进度没到 5% 就闭嘴（那点信息量外推等于瞎猜）。"""
    progress = (task.get("progress") or {}).get("value")
    try:
        value = float(progress)
    except (TypeError, ValueError):
        return blank
    if value < 0.05 or value > 1.0:
        return blank
    elapsed = _elapsed_sec(task, now)
    if elapsed <= 0:
        return blank
    sec = round(elapsed * (1.0 - value) / value, 1)
    return {"sec": sec, "text": fmt_sec(sec), "basis": "按当前进度 %.0f%% 外推" % (value * 100),
            "source": "progress", "confidence": "低", "samples": 0, "partial": True}
