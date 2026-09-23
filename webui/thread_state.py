# -*- coding: utf-8 -*-
"""P2-2 显式 ThreadState（2026-09-23）——把「一个会话的活状态」从裸字典键收进显式对象。

## 为什么（体检实测数据，2026-09-23，见 E:/release/_p22_inventory.json）

对 webui/server.py（18263 行）做 AST 体检，实测：

- 模块级可变容器 39 个：其中 18 个从未被修改（其实是常量），7 个按会话/ID 分片，
  14 个是**进程级单例**（_current_model / _UPDATE_TASK / _UI_LANG_STATE / _weixin_* ...）。
- 会话字典上的隐式键 95 个（内部键 44 / 对外键 51），写入点 207 处、读取点 499 处，
  没有任何结构定义，没有 schema，没有锁。
- 全文件只有 2 把锁（_ENV_INV_LOCK 9992、_LIT_PDF_COUNT_LOCK 11562），都不护会话状态；
  308 个同步 handler 跑在 Starlette 线程池（约 40 线程）里，真并发可达。
- 唯一被当作「并发护栏」的 session["_user_turn_active"]：**4 个写入点、1 个读取点**
  （server.py:2237 自检/心跳的忙判定）。用户第二条消息进来根本不看它 →
  **同一会话可以两个回合同时在飞**，同一 agent 上交错流（历史注释里
  "single-writer 护栏砍掉在飞流导致工具参数被截断为空" 就是这个事故）。

## 这一层做什么 / 不做什么

做：给每个会话一个显式对象，接管**回合记账**——谁在跑、几个在跑、有没有重叠、
跑了多久；把「重叠」这件事从不可见变成可计数、可审计、可断言。
不做（本轮）：不串行化、不改任何现有行为。默认只记账；要真正拦并发需要显式打开
MEMOMICS_THREAD_SERIALIZE=1 并用 wait_for_idle()（本文件已提供，接线见后续 P2-2c）。

## 设计约束（与 P2-1 同一套纪律）

1. **fail-open**：任何异常都吞掉并返回安全值，绝不把主流程搞崩。
2. **零行为变更**：默认路径只在内存里加一次记账，不发事件、不阻塞、不改返回值。
3. **有界**：会话数、每会话活跃回合数、历史环形缓冲全部封顶，长跑不涨内存。
4. **可审计**：stats() 只吐计数器与聚合值，不含用户内容。
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

__all__ = [
    "GROUPS", "SESSION_STATE_SCHEMA", "check_schema", "schema_stats",
    "ThreadState", "ThreadRegistry", "TurnRecord",
    "enabled", "set_enabled", "should_serialize", "serialize_timeout",
    "get_state", "mark_turn_start", "mark_turn_end", "turn_active",
    "wait_for_idle", "wait_turn_idle", "begin_turn_serialized", "drop", "reset",
    "registry", "stats",
    "MAX_ACTIVE_PER_SESSION", "MAX_SESSIONS", "MAX_RECENT_TURNS",
    "DEFAULT_STALE_TURN_S", "stale_after",
]

VERSION = "p2-2.1"

# ---------------------------------------------------------------- 状态键 schema
# 分组口径：键属于「谁的状态」。这张表是 P2-2 的核心产出之一——
# 以前这 95 个键只存在于 207 个写入点的字面量里，现在有名字、有分类、可漂移检查。
GROUPS = {
    "identity": "会话身份与元信息（id/title/时间戳/来源）",
    "persist": "跨回合持久化的会话内容（messages/todos/goal/changes/技能/意图）",
    "llm": "模型与 agent 句柄（model_config/agent/running_*）",
    "turn": "单回合内的瞬时簿记（*_ts / _stall_* / _self_check_* / _*_active）",
    "transport": "传输层引用（ws_ref/ws_attached/loop_ref）",
    "domain": "运行时资源与产物路径（results_dir/进程/IO 计数）",
    "misc": "历史遗留或来自同名局部字典的键（保守登记，便于漂移检查）",
}

_KEYS = {
    "identity": (
        "id title title_source created last_active started_at restored source "
        "session_id ws_sender_id wx_sender_id"
    ),
    "persist": (
        "messages todos todos_revision _todos_blob goal changes _changes_pending "
        "_changes_skipped _pinned_expected pinned_skills _skills_used reasoning_log "
        "progress_log _ask_form_answers _pending_questions _pipeline_todos plan_path "
        "output_root analysis_dir preview domain intent intent_conf intent_meta lang "
        "lang_locked model_locked triggered message_count _msg_count _first_msg "
        "_last_msg _messages_loaded"
    ),
    "llm": "agent model_config running_agent running_task _api_calls _proc_hist",
    "turn": (
        "_user_turn_active _turn_count _turn_start_ts _turn_activity_ts "
        "_real_exec_this_turn _tool_dedup _force_tool_check _live_tool _live_tool_ts "
        "_live_tool_warned _stall_notice_last _stall_diag _stall_wake_active "
        "_stall_noevent_ts _self_check_count _self_check_last_sig _wakeup_retry_n "
        "_saying_wakeup_n _urgent_wakeup _loop_guard _last_event_ts _syslog_dedup "
        "_intent_confirmed _code_edit_asked _dir_created _form_ans_marker "
        "_title_summary_at_msg _red_hits _task_count _partial_text"
    ),
    "transport": "ws_ref ws_attached loop_ref",
    "domain": (
        "results_dir bg_running cwd resource_request cpu_seconds rss_bytes io_read "
        "io_write pid step_name tool"
    ),
    "misc": "name category",
}

SESSION_STATE_SCHEMA: Dict[str, str] = {}
for _g, _names in _KEYS.items():
    for _n in _names.split():
        SESSION_STATE_SCHEMA[_n] = _g
del _g, _names, _n

# 明确知道会出现的「非会话键」白名单：同名局部字典（进程信息 / 步骤 / 分类）也用了
# session/s/state 这些变量名，AST 体检会把它们算进来。登记为 misc 而不是删掉，
# 是为了让漂移检查既不误报也不漏报。
_SCHEMA_ORDER = tuple(GROUPS.keys())


def check_schema(session: Any) -> Dict[str, Any]:
    """检查一个会话字典的键是否都在 schema 里。返回 unknown / counts，不抛异常。"""
    try:
        keys = sorted(k for k in session.keys() if isinstance(k, str))
    except Exception:
        return {"unknown": [], "total": 0, "known": 0, "ok": True}
    unknown = [k for k in keys if k not in SESSION_STATE_SCHEMA]
    by_group: Dict[str, int] = {}
    for k in keys:
        g = SESSION_STATE_SCHEMA.get(k, "unregistered")
        by_group[g] = by_group.get(g, 0) + 1
    return {"unknown": unknown, "total": len(keys), "known": len(keys) - len(unknown),
            "ok": not unknown, "by_group": by_group}


def schema_stats() -> Dict[str, Any]:
    by_group: Dict[str, int] = {}
    for g in SESSION_STATE_SCHEMA.values():
        by_group[g] = by_group.get(g, 0) + 1
    return {"version": VERSION, "keys": len(SESSION_STATE_SCHEMA), "groups": by_group}


# ------------------------------------------------------------------ 回合记账
MAX_ACTIVE_PER_SESSION = 16     # 单会话同时活跃回合上限（超过只计数，不再记录，防涨内存）
MAX_SESSIONS = 2000             # 注册表会话数上限（LRU 淘汰）
MAX_RECENT_TURNS = 20           # 每会话保留的最近回合环形缓冲
DEFAULT_SERIALIZE_TIMEOUT = 1800.0  # wait_for_idle 默认最长等待 30 分钟
DEFAULT_STALE_TURN_S = 3600.0      # 超过这么久还没收尾的回合按僵尸处理（串行化自愈）


class TurnRecord(object):
    """一次回合的账目。不持有 agent 句柄，避免把大对象留在内存里。"""

    __slots__ = ("turn_id", "sid", "source", "seq", "started_at", "thread", "ended_at")

    def __init__(self, turn_id: str, sid: str, source: str, seq: int):
        self.turn_id = turn_id
        self.sid = sid
        self.source = source
        self.seq = seq
        self.started_at = time.time()
        self.thread = threading.current_thread().name
        self.ended_at: Optional[float] = None

    @property
    def elapsed(self) -> float:
        return (self.ended_at or time.time()) - self.started_at

    def snapshot(self) -> Dict[str, Any]:
        return {
            "turn_id": self.turn_id, "source": self.source, "seq": self.seq,
            "thread": self.thread, "started_at": round(self.started_at, 3),
            "elapsed": round(self.elapsed, 3), "ended": self.ended_at is not None,
        }


class ThreadState(object):
    """一个会话的运行时状态所有权：谁在跑这个会话，跑了几个，有没有重叠。"""

    __slots__ = ("sid", "created_at", "_lock", "_cond", "_seq", "_active",
                 "_recent", "total_turns", "conflicts", "overflows", "_last_conflict",
                 "_last_turn_at", "serialized_waits", "wait_timeouts", "stale_dropped")

    def __init__(self, sid: str):
        self.sid = sid
        self.created_at = time.time()
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._seq = 0
        self._active: Dict[str, TurnRecord] = {}
        self._recent: List[TurnRecord] = []
        self.total_turns = 0
        self.conflicts = 0
        self.overflows = 0
        self._last_conflict: Optional[Dict[str, Any]] = None
        self._last_turn_at = 0.0
        self.serialized_waits = 0    # 串行化门真的等过几次
        self.wait_timeouts = 0       # 等到超时（fail-open 放行）几次
        self.stale_dropped = 0       # 僵尸回合被清掉几次

    # -- 记账 ------------------------------------------------------------
    def begin_turn(self, source: str = "user") -> Optional[TurnRecord]:
        """记一个回合开始。已有活跃回合时计一次冲突（并发护栏被绕过的证据）。"""
        with self._lock:
            self._seq += 1
            rec = TurnRecord("%s#%d" % (self.sid, self._seq), self.sid, str(source), self._seq)
            self.total_turns += 1
            self._last_turn_at = rec.started_at
            if self._active:
                self.conflicts += 1
                other = next(iter(self._active.values()))
                self._last_conflict = {
                    "at": datetime.now().strftime("%H:%M:%S"),
                    "sids": self.sid,
                    "new_turn": rec.turn_id, "active_turn": other.turn_id,
                    "active_source": other.source, "active_thread": other.thread,
                    "overlap_s": round(rec.started_at - other.started_at, 3),
                }
            if len(self._active) >= MAX_ACTIVE_PER_SESSION:
                self.overflows += 1
                return None
            self._active[rec.turn_id] = rec
            return rec

    def end_turn(self, turn_id: Optional[str] = None) -> Optional[float]:
        """结束一个回合。turn_id 为空时结束最早开始的那个（finally 里拿不到 id 的场景）。"""
        with self._lock:
            if not self._active:
                return None
            rec = self._active.get(turn_id) if turn_id else None
            if rec is None:   # 没给 id / id 过期 → 结束最早开始的那个
                rec = min(self._active.values(), key=lambda r: r.started_at)
            self._active.pop(rec.turn_id, None)
            return self._finish(rec)

    def _finish(self, rec: TurnRecord) -> float:
        rec.ended_at = time.time()
        self._recent.append(rec)
        if len(self._recent) > MAX_RECENT_TURNS:
            del self._recent[:-MAX_RECENT_TURNS]
        if not self._active:
            self._cond.notify_all()
        return rec.elapsed

    # -- 查询 ------------------------------------------------------------
    def busy(self) -> bool:
        with self._lock:
            return bool(self._active)

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sid": self.sid,
                "active": [r.snapshot() for r in self._active.values()],
                "active_count": len(self._active),
                "total_turns": self.total_turns,
                "conflicts": self.conflicts,
                "overflows": self.overflows,
                "serialized_waits": self.serialized_waits,
                "wait_timeouts": self.wait_timeouts,
                "stale_dropped": self.stale_dropped,
                "last_conflict": self._last_conflict,
                "last_turn_at": round(self._last_turn_at, 3),
                "age_s": round(time.time() - self.created_at, 1),
            }

    def drop_stale(self, max_age: float = DEFAULT_STALE_TURN_S) -> int:
        """清掉超过 max_age 还没收尾的僵尸回合。串行化门的自愈阀——回合线程若是被
        强杀/连接异常退出，活跃账目会永久占位；这里让后来的回合能继续走。"""
        with self._lock:
            now = time.time()
            dead = [r for r in self._active.values() if now - r.started_at > max_age]
            for rec in dead:
                self._active.pop(rec.turn_id, None)
                rec.ended_at = now
                self._recent.append(rec)
                self.stale_dropped += 1
            if len(self._recent) > MAX_RECENT_TURNS:
                del self._recent[:-MAX_RECENT_TURNS]
            if dead:
                self._cond.notify_all()
            return len(dead)

    def wait_for_idle(self, timeout: float = DEFAULT_SERIALIZE_TIMEOUT) -> bool:
        """等到本会话没有活跃回合。串行化模式用（默认不接线）。"""
        deadline = time.time() + max(0.0, float(timeout))
        with self._cond:
            while self._active:
                remain = deadline - time.time()
                if remain <= 0:
                    return False
                self._cond.wait(remain)
            return True


class ThreadRegistry(object):
    """sid -> ThreadState 的注册表。整套操作有锁、有上限、不做 I/O。"""

    def __init__(self, max_sessions: int = MAX_SESSIONS):
        self._lock = threading.RLock()
        self._states: Dict[str, ThreadState] = {}
        self._max = int(max_sessions)
        self.evicted = 0

    def get(self, sid: Any) -> Optional[ThreadState]:
        if not sid:
            return None
        key = str(sid)
        if len(key) > 256:          # 脏 sid 不进注册表（P2-1 也做过同样的裁剪）
            key = key[:256]
        with self._lock:
            st = self._states.get(key)
            if st is None:
                if len(self._states) >= self._max:
                    oldest = min(self._states.items(), key=lambda kv: kv[1]._last_turn_at or kv[1].created_at)
                    self._states.pop(oldest[0], None)
                    self.evicted += 1
                st = ThreadState(key)
                self._states[key] = st
            return st

    def drop(self, sid: Any) -> bool:
        if not sid:
            return False
        with self._lock:
            return self._states.pop(str(sid), None) is not None

    def keys(self) -> List[str]:
        with self._lock:
            return sorted(self._states.keys())

    def reset(self) -> None:
        with self._lock:
            self._states.clear()
            self.evicted = 0

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            states = list(self._states.values())
            busy = [s for s in states if s.active_count()]
            conflicts = sum(s.conflicts for s in states)
            hot = sorted(states, key=lambda s: s.conflicts, reverse=True)[:3]
            return {
                "version": VERSION,
                "sessions": len(states),
                "busy_sessions": len(busy),
                "active_turns": sum(s.active_count() for s in states),
                "total_turns": sum(s.total_turns for s in states),
                "conflicts": conflicts,
                "overflows": sum(s.overflows for s in states),
                "serialized_waits": sum(s.serialized_waits for s in states),
                "wait_timeouts": sum(s.wait_timeouts for s in states),
                "stale_dropped": sum(s.stale_dropped for s in states),
                "evicted": self.evicted,
                "serialize": should_serialize(),
                "worst": [{"sid": s.sid[:12], "conflicts": s.conflicts,
                           "last_conflict": s._last_conflict} for s in hot if s.conflicts],
            }


# ------------------------------------------------------------------- 门面
_REGISTRY = ThreadRegistry()
_ENABLED = True


def registry() -> ThreadRegistry:
    return _REGISTRY


def enabled() -> bool:
    try:
        return bool(_ENABLED) and os.environ.get("MEMOMICS_THREAD_STATE", "1") != "0"
    except Exception:
        return False


def set_enabled(flag: bool) -> None:
    global _ENABLED
    _ENABLED = bool(flag)


def should_serialize() -> bool:
    """MEMOMICS_THREAD_SERIALIZE=1 时，调用方应当用 wait_for_idle() 串行化同会话回合。"""
    try:
        return os.environ.get("MEMOMICS_THREAD_SERIALIZE", "0") == "1"
    except Exception:
        return False


def stale_after() -> float:
    try:
        return float(os.environ.get("MEMOMICS_THREAD_STALE_S", DEFAULT_STALE_TURN_S))
    except Exception:
        return DEFAULT_STALE_TURN_S


def serialize_timeout() -> float:
    try:
        return float(os.environ.get("MEMOMICS_THREAD_SERIALIZE_TIMEOUT", DEFAULT_SERIALIZE_TIMEOUT))
    except Exception:
        return DEFAULT_SERIALIZE_TIMEOUT


def get_state(sid: Any) -> Optional[ThreadState]:
    try:
        if not enabled():
            return None
        return _REGISTRY.get(sid)
    except Exception:
        return None


def mark_turn_start(sid: Any, source: str = "user") -> Optional[str]:
    """记账入口：返回 turn_id，任何异常都返回 None（fail-open）。"""
    try:
        st = get_state(sid)
        if st is None:
            return None
        rec = st.begin_turn(source)
        return rec.turn_id if rec else None
    except Exception:
        return None


def mark_turn_end(sid: Any, turn_id: Optional[str] = None) -> Optional[float]:
    """记账出口：返回回合时长（秒），异常返回 None。"""
    try:
        st = get_state(sid)
        if st is None:
            return None
        return st.end_turn(turn_id)
    except Exception:
        return None


def turn_active(sid: Any) -> bool:
    try:
        st = get_state(sid)
        return bool(st and st.busy())
    except Exception:
        return False


def wait_for_idle(sid: Any, timeout: Optional[float] = None) -> bool:
    try:
        st = get_state(sid)
        if st is None:
            return True
        return st.wait_for_idle(serialize_timeout() if timeout is None else timeout)
    except Exception:
        return True


async def wait_turn_idle(sid: Any, timeout: Optional[float] = None, poll: float = 0.05) -> bool:
    """串行化门（P2-2 补丁）：等同一会话上一个回合收尾再开新回合。

    - 没开 MEMOMICS_THREAD_SERIALIZE 时**立刻返回 True**，不碰注册表、零开销、零行为变更；
    - 开着的时候在事件循环里 await 轮询（不阻塞 loop，其他会话照常跑）；
    - 超过 timeout 还没等到 → 记 wait_timeouts 并返回 False（fail-open，调用方按原行为继续）；
    - 活跃回合超过 MEMOMICS_THREAD_STALE_S 视为僵尸，直接清掉（自愈，防死锁）。

    返回 True = 可以开新回合（空闲 / 已等到 / 串行化关着），False = 等超时了。
    """
    try:
        if not should_serialize() or not enabled():
            return True
        st = _REGISTRY.get(sid)
        if st is None:
            return True
        deadline = time.time() + (serialize_timeout() if timeout is None else float(timeout))
        stale = stale_after()
        waited = False
        while st.busy():
            st.drop_stale(stale)
            if not st.busy():
                break
            if time.time() >= deadline:
                with st._lock:
                    st.wait_timeouts += 1
                return False
            waited = True
            await asyncio.sleep(poll)
        if waited:
            with st._lock:
                st.serialized_waits += 1
        return True
    except Exception:
        return True


async def begin_turn_serialized(sid: Any, source: str = "user",
                              timeout: Optional[float] = None,
                              poll: float = 0.05) -> Optional[str]:
    """串行化门 + 记账的**原子**版本（P2-2 补丁给 /ws 用的就是它）。

    为什么必须原子：分开写（先等空闲、再记账）会有 TOCTOU 缝隙——两个线程都等到空闲、
    然后都记账，conflicts 照样 +1。这里把"确认空闲"和"记账"放在同一把锁里，
    所以门上方的并发调用不会互相踩，conflicts 恒为 0。

    串行化关着时等价于 mark_turn_start（零开销、零行为变更）。
    等超时 → 记 wait_timeouts，仍然按原行为放行（fail-open），返回 turn_id。
    """
    try:
        if not should_serialize() or not enabled():
            return mark_turn_start(sid, source)
        st = _REGISTRY.get(sid)
        if st is None:
            return mark_turn_start(sid, source)
        deadline = time.time() + (serialize_timeout() if timeout is None else float(timeout))
        stale = stale_after()
        waited = False
        while True:
            st.drop_stale(stale)
            with st._lock:                     # ← 原子：空闲判定 + 记账同锁
                if not st._active:
                    if waited:
                        st.serialized_waits += 1
                    rec = st.begin_turn(source)
                    return rec.turn_id if rec else None
            if time.time() >= deadline:
                with st._lock:
                    st.wait_timeouts += 1
                    rec = st.begin_turn(source)  # fail-open：按原行为继续
                return rec.turn_id if rec else None
            waited = True
            await asyncio.sleep(poll)
    except Exception:
        return None


def drop(sid: Any) -> bool:
    try:
        return _REGISTRY.drop(sid)
    except Exception:
        return False


def reset() -> None:
    try:
        _REGISTRY.reset()
    except Exception:
        pass


def stats() -> Dict[str, Any]:
    try:
        out = _REGISTRY.stats()
    except Exception:
        out = {"version": VERSION, "error": "stats failed"}
    out["enabled"] = enabled()
    out["schema"] = schema_stats()
    return out


def _main() -> int:  # pragma: no cover - 手工排查用
    import json
    import sys
    if "--schema" in sys.argv:
        print(json.dumps({"version": VERSION, "schema": schema_stats(),
                          "groups": {k: v for k, v in GROUPS.items()}},
                         ensure_ascii=False, indent=1))
        return 0
    if "--selftest" in sys.argv:
        sid = "selftest"
        t1 = mark_turn_start(sid, "user")
        t2 = mark_turn_start(sid, "wakeup")
        print("two starts:", t1, t2, "conflicts:", stats()["conflicts"])
        mark_turn_end(sid)
        mark_turn_end(sid)
        print(json.dumps(stats(), ensure_ascii=False, indent=1))
        return 0
    print("usage: python -m webui.thread_state [--schema|--selftest]")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
