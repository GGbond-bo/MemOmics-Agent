"""任务完成闸门（P1-A）— 确定性 task_state 状态机，替代 task_plan.md 文本词判定。

背景：_schedule_self_check 自唤醒看门狗靠 task_plan.md 文本标记（"completed/完成"）
判定任务是否完成，文本不可靠且 session dict 是内存态（server 重启即丢），
导致"老任务被自动重启"。本模块把完成状态落盘为显式状态机：
  - 状态文件：<results_dir>/.task_state.json（磁盘持久化，server 重启不丢）
  - 状态迁移：pending → running → done | blocked →（用户新消息）→ pending
  - 闸门规则：task_state == done 时拒绝一切自动唤醒（self-check / watchdog）；
    只有用户主动发新消息才重置为 pending（用户主动 = 新指令，不算自动重启）。

2026-08 迁移 DSH 后台能力（M2/M3/M4）：
    - M2 armed（许可）：**2026-10-18 改为进程内生效（借鉴 DSH goal 语义）**。
      旧实现把 armed 落盘并"重启即全量 disarm"，于是每次重启都把在跑任务冻住，
      必须用户发消息才解锁（实测 7 天 1293 次自动唤醒被拦，是"任务跑一半就停"
      的结构性原因）。现在：默认 armed（机器在跑 = 已授权），只有**显式暂停**
      （paused_at>0 / activation=paused，由用户 stop 或工具主动调用）才拦；
      旧文件里没有暂停标记的 armed=False 一律按 armed 迁移，不再永久冻结。
      失控仍由轮数预算（max_rounds，默认 256）+ 退役状态（done/cancelled）兜住。
  - M3 硬轮数预算：rounds_started / max_rounds（默认 256，与 DSH maxGoalRounds
    一致）。每次真正注入唤醒回合 +1（admit_round），到上限自动唤醒一律 stop；
    用户消息重置预算（交互式模型的"人类监督刷新时钟"）。
  - M4 reconcile：启动一致性对账，修复 RunGate 与 task_plan.md 的确定性漂移
    （done 但 task_plan 未归档 → 补归档），并报告可疑孤儿任务。

设计原则：纯逻辑模块，不 import webui/server，可独立单测；所有失败返回安全默认
（默认放行 run，绝不因本模块故障阻断正常对话）。
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from typing import Optional, Tuple

logger = logging.getLogger("memomics.run_gate")

STATE_FILE = ".task_state.json"
VALID_STATES = ("pending", "running", "done", "blocked", "cancelled")
# 任务类型（2026-08-16）：normal=普通任务（画图/轻量分析，默认）；
# long_running=长任务管线（后台进程/心跳监督）。运行时证据自动升级，不降级。
VALID_TASK_CLASSES = ("normal", "long_running")

# 2026-10-18：许可模型（借鉴 DSH goal 的 activation）
#   armed  = 进程内默认许可（机器在跑即视为已授权）
#   paused = 用户/工具显式暂停（唯一会拦自动续跑的状态）
ACTIVATION_ARMED = "armed"
ACTIVATION_PAUSED = "paused"

# M3: 硬轮数预算默认上限（与 DSH maxGoalRounds 默认 256 对齐）
DEFAULT_MAX_ROUNDS = 256

# 判"用户显式继续/新任务"的最小词表（命中才重置退役状态）
RESET_HINT_WORDS = ("继续", "接着", "下一步", "新任务", "换一个", "重跑", "重新",
                    "continue", "next", "new task", "restart", "重新开始", "开始做")

# 进程内读写互斥（2026-08 极端测试修复）：Windows 上 os.replace 要求目标文件
# 无打开句柄，并发读(load_state)+写(os.replace)会 PermissionError。
# 单锁串行化所有状态文件访问——生产单线程零开销，多线程/多写者时保证不损坏。
_LOCK = threading.RLock()


def _state_path(results_dir: str) -> str:
    return os.path.join(results_dir, STATE_FILE)


def _default_state() -> dict:
    """缺失/损坏文件的默认状态：视为全新任务（用户在场）→ armed=True、预算未用。"""
    return {
        "state": "pending",
        "reason": "",
        "updated_at": 0.0,
        "task_class": "normal",
        "armed": True,
        "armed_at": 0.0,
        "armed_by": "",
        # 2026-10-18：进程内许可 + 显式暂停（不再靠重启 disarm）
        "activation": ACTIVATION_ARMED,
        "paused_at": 0.0,
        "paused_by": "",
        # 2026-10-18（对齐 DSH）：许可绑定"进程"。换进程 = 自动失权，需用户消息/显式 resume 再武装。
        "proc_id": 0,
        "rounds_started": 0,
        "max_rounds": DEFAULT_MAX_ROUNDS,
    }


def load_state(results_dir: str) -> dict:
    """读取落盘状态；文件缺失/损坏返回 pending（安全默认：视为新任务）。

    M2 语义：文件存在但没有 armed 字段（升级前旧文件/重启恢复）→ armed=False，
    即"重启后未重新授权"。文件缺失（全新目录）→ armed=True（用户在场创建）。
    """
    if not results_dir:
        return _default_state()
    with _LOCK:
        try:
            with open(_state_path(results_dir), "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("state") not in VALID_STATES:
                return _default_state()
            if data.get("task_class") not in VALID_TASK_CLASSES:
                data["task_class"] = "normal"
            # 2026-10-18：许可改为进程内生效 —— 只有"显式暂停"才 paused。
            # 迁移：旧版启动扫描写的 armed=False 没有 paused_at 标记 → 按 armed 处理，
            # 历史文件不会再把任务永久冻住；用户主动 stop 会写 paused_at。
            _paused_at = 0.0
            try:
                _paused_at = float(data.get("paused_at") or 0.0)
            except (TypeError, ValueError):
                _paused_at = 0.0
            _explicit_pause = (str(data.get("activation") or "") == ACTIVATION_PAUSED
                               or _paused_at > 0.0)
            data["activation"] = ACTIVATION_PAUSED if _explicit_pause else ACTIVATION_ARMED
            data["armed"] = data["activation"] == ACTIVATION_ARMED   # 兼容字段
            # 2026-10-18（DSH resume/fork 语义）：许可只在**同一进程**内有效。
            # 记录里的 proc_id 与本进程不一致（= 服务重启过）→ 自动置 paused，
            # 必须用户发消息（arm）或显式 resume 才恢复。这样"重启后还在自动跑"不会再发生。
            try:
                _rec_pid = int(data.get("proc_id") or 0)
            except (TypeError, ValueError):
                _rec_pid = 0
            _now_pid = os.getpid()
            if _rec_pid and _rec_pid != _now_pid:
                data["activation"] = ACTIVATION_PAUSED
                data["armed"] = False
                data["paused_at"] = time.time()
                data["paused_by"] = "process restart (需用户消息或显式 resume 再武装)"
            data["proc_id"] = _now_pid
            data.setdefault("paused_at", _paused_at)
            data.setdefault("paused_by", str(data.get("paused_by") or ""))
            # 字段级防御：rounds/max_rounds 损坏只修该字段，绝不整体回退状态机
            # （整体回退会把 done 任务重置成 pending+armed → 老任务被自动重启）
            try:
                data["rounds_started"] = max(0, int(data.get("rounds_started", 0) or 0))
            except (TypeError, ValueError):
                data["rounds_started"] = 0
            try:
                data["max_rounds"] = int(data.get("max_rounds", DEFAULT_MAX_ROUNDS) or DEFAULT_MAX_ROUNDS)
            except (TypeError, ValueError):
                data["max_rounds"] = DEFAULT_MAX_ROUNDS
            if data["max_rounds"] < 1:
                data["max_rounds"] = DEFAULT_MAX_ROUNDS
            return data
        except FileNotFoundError:
            return _default_state()
        except Exception:
            logger.warning("[RunGate] 读取 task_state 失败，按 pending+未武装 处理", exc_info=True)
            # 文件存在但损坏 = 状态未知：不自动唤醒（保守；缺失文件才视为新任务 armed=True）
            _d = _default_state()
            _d["armed"] = False
            return _d


def _write_state(results_dir: str, payload: dict) -> bool:
    """原子写落盘（唯一临时文件 + rename，兼容并发写者）。失败返回 False（不抛异常）。

    2026-08 极端测试修复：原实现所有写者共用同一 .tmp 路径，Windows 上并发
    write/rename 互相踩（WinError 32）。改用 mkstemp 生成唯一临时文件；
    模块级 _LOCK 串行化读-改-写（Windows os.replace 要求目标无打开句柄，
    并发读会 PermissionError）；rename 仍保留小重试兜底跨进程竞争。
    """
    if not results_dir:
        return False
    with _LOCK:
        _fd = None
        try:
            os.makedirs(results_dir, exist_ok=True)
            _fd, tmp = tempfile.mkstemp(prefix=STATE_FILE + ".", suffix=".tmp", dir=results_dir)
            with os.fdopen(_fd, "w", encoding="utf-8") as f:
                _fd = None
                json.dump(payload, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            target = _state_path(results_dir)
            for _attempt in range(5):
                try:
                    os.replace(tmp, target)
                    return True
                except OSError:
                    if _attempt == 4:
                        raise
                    time.sleep(0.01)
            return False
        except Exception:
            logger.warning("[RunGate] 写入 task_state 失败", exc_info=True)
            return False
        finally:
            if _fd is not None:
                try:
                    os.close(_fd)
                except Exception:
                    pass
            try:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            except Exception:
                pass


def save_state(results_dir: str, state: str, reason: str = "",
               *, armed: Optional[bool] = None,
               rounds_started: Optional[int] = None,
               max_rounds: Optional[int] = None) -> bool:
    """写入落盘状态（原子写）。保留任务类型/armed/预算等已有字段。

    新建记录（文件不存在）→ armed=True（用户在场创建任务）、预算清零。
    显式覆盖通过关键字参数传入；否则保留现有值。
    """
    if state not in VALID_STATES:
        return False
    if not results_dir:
        return False
    # 显式预算参数防御（损坏值不炸 API）
    if rounds_started is not None:
        try:
            rounds_started = max(0, int(rounds_started or 0))
        except (TypeError, ValueError):
            rounds_started = 0
    if max_rounds is not None:
        try:
            max_rounds = int(max_rounds or 0)
        except (TypeError, ValueError):
            max_rounds = DEFAULT_MAX_ROUNDS
        if max_rounds < 1:
            # 0/负值 = 非法 → 回退默认（与 load_state 语义一致）
            max_rounds = DEFAULT_MAX_ROUNDS
    _existing = load_state(results_dir) if os.path.isfile(_state_path(results_dir)) else None
    _base = _existing if _existing is not None else _default_state()
    payload = {
        "state": state,
        "reason": reason,
        "updated_at": time.time(),
        "task_class": _base.get("task_class", "normal"),
        "armed": _base.get("armed", True) if armed is None else bool(armed),
        "armed_at": _base.get("armed_at", 0.0) if armed is None else (time.time() if armed else 0.0),
        "armed_by": _base.get("armed_by", "") if armed is None else ("save_state" if armed else ""),
        # 2026-10-18：activation/paused_* 必须随写盘保留，否则一次 save_state 就丢暂停语义
        # 2026-10-18：**新建**状态文件时绝不默认 armed（实测踩坑：任何对"无状态文件"的会话
        # 写一次状态，就会凭空生成 armed 文件 → 重启后又自动续跑）。新建一律 paused，
        # 必须用户消息（arm）或显式 resume 才武装。
        "activation": (ACTIVATION_ARMED if armed
                       else (ACTIVATION_PAUSED if _existing is None
                             else (_base.get("activation") or ACTIVATION_ARMED))),
        "paused_at": _base.get("paused_at", 0.0) if armed is None else (0.0 if armed else time.time()),
        "paused_by": _base.get("paused_by", "") if armed is None else ("" if armed else "save_state"),
        "proc_id": os.getpid(),
        "rounds_started": _base.get("rounds_started", 0) if rounds_started is None else rounds_started,
        "max_rounds": _base.get("max_rounds", DEFAULT_MAX_ROUNDS) if max_rounds is None else max_rounds,
    }
    ok = _write_state(results_dir, payload)
    if ok:
        logger.info("[RunGate] %s -> %s (%s)", os.path.basename(results_dir), state, reason)
    return ok


def arm(results_dir: str, by: str = "user_message") -> bool:
    """恢复自动续跑许可（显式暂停的反操作）。保留状态机 phase 与预算。"""
    if not results_dir:
        return False
    st = load_state(results_dir)
    st["armed"] = True
    st["armed_at"] = time.time()
    st["armed_by"] = str(by)[:80]
    st["activation"] = ACTIVATION_ARMED
    st["paused_at"] = 0.0
    st["paused_by"] = ""
    st["proc_id"] = os.getpid()
    return _write_state(results_dir, st)


def disarm(results_dir: str, reason: str = "") -> bool:
    """**显式暂停**自动续跑（用户 stop / 主动叫停）。不改变状态机 phase。

    2026-10-18 语义变更：重启扫描不再调用本函数（进程内许可默认 armed），
    所以这里等价于"暂停"，会写 paused_at 标记；arm()/用户消息可恢复。
    """
    if not results_dir:
        return False
    st = load_state(results_dir)
    st["armed"] = False
    st["armed_at"] = 0.0
    st["armed_by"] = ""
    st["activation"] = ACTIVATION_PAUSED
    st["paused_at"] = time.time()
    st["paused_by"] = str(reason)[:120] or "user"
    ok = _write_state(results_dir, st)
    if ok:
        logger.info("[RunGate] %s paused (%s)", os.path.basename(results_dir), reason)
    return ok


def normalize_proc(results_dir: str) -> bool:
    """把"上个进程留下的 armed"在磁盘上纠正为 paused（2026-10-18，DSH resume/fork 语义）。

    load_state 只是"读时生效"，文件里仍写着 armed —— 端口探测/巡检/别处代码直接读 JSON 会误判。
    启动时调用本函数把磁盘状态统一纠正过来，返回 True 表示确实改写过。
    """
    if not results_dir or not os.path.isfile(_state_path(results_dir)):
        return False
    try:
        with open(_state_path(results_dir), "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return False
        try:
            _pid = int(raw.get("proc_id") or 0)
        except (TypeError, ValueError):
            _pid = 0
        if _pid and _pid == os.getpid():
            return False      # 本进程写的，保留
        if str(raw.get("activation") or "") == ACTIVATION_PAUSED:
            return False      # 已是 paused
        st = load_state(results_dir)      # load_state 已按 proc_id 判成 paused
        st["paused_by"] = st.get("paused_by") or "process restart (需用户消息或显式 resume 再武装)"
        return _write_state(results_dir, st)
    except Exception:
        return False


def is_armed(results_dir: str) -> bool:
    """当前是否允许自动续跑（进程内许可：默认 armed，显式暂停才 False）。"""
    return str(load_state(results_dir).get("activation") or ACTIVATION_ARMED) == ACTIVATION_ARMED


def is_paused(results_dir: str) -> bool:
    """是否被显式暂停（供 UI/自检日志区分"暂停"与"退役/预算耗尽"）。"""
    return not is_armed(results_dir)


def admit_round(results_dir: str) -> bool:
    """M3: 登记一个真正进入的自动唤醒回合（rounds_started + 1）。

    与 DSH 的 roundsStarted 同语义：只有真正注入唤醒才计数。
    返回 False 表示该回合不应注入（任务已退役 / 预算耗尽 / 无任务状态文件）。
    状态文件不存在 = 没有任务 = 不计数（防止对空目录凭空创建激活记录）。
    """
    if not results_dir or not os.path.isfile(_state_path(results_dir)):
        return False
    st = load_state(results_dir)
    if st.get("state") in ("done", "cancelled"):
        return False
    if int(st.get("rounds_started", 0)) >= int(st.get("max_rounds", DEFAULT_MAX_ROUNDS)):
        return False
    st["rounds_started"] = int(st.get("rounds_started", 0)) + 1
    st["updated_at"] = time.time()
    ok = _write_state(results_dir, st)
    if ok and int(st["rounds_started"]) in (1, 10, 50, 100, 200, 250, 256):
        logger.info("[RunGate] %s round %d/%d",
                    os.path.basename(results_dir), st["rounds_started"], st.get("max_rounds"))
    return ok


def reset_rounds(results_dir: str) -> bool:
    """M3: 用户消息刷新预算（人类监督重置时钟；DSH 中 resume 的交互式版）。"""
    if not results_dir:
        return False
    st = load_state(results_dir)
    st["rounds_started"] = 0
    st["updated_at"] = time.time()
    return _write_state(results_dir, st)


def round_budget(results_dir: str) -> dict:
    """M3: 预算可见性快照。"""
    st = load_state(results_dir)
    return {
        "rounds_started": int(st.get("rounds_started", 0)),
        "max_rounds": int(st.get("max_rounds", DEFAULT_MAX_ROUNDS)),
    }


def mark_done(results_dir: str, reason: str = "task completed") -> bool:
    """显式置 done —— 由完成信号（文本判定/agent 汇报）触发，只写一次。"""
    return save_state(results_dir, "done", reason)


def mark_running(results_dir: str, reason: str = "task started") -> bool:
    return save_state(results_dir, "running", reason)


def mark_blocked(results_dir: str, reason: str = "task blocked") -> bool:
    return save_state(results_dir, "blocked", reason)


def mark_cancelled(results_dir: str, reason: str = "user cancelled") -> bool:
    """用户放弃任务 → 确定性标记 cancelled（退役：自动唤醒不再恢复）。"""
    return save_state(results_dir, "cancelled", reason)


def is_done(results_dir: str) -> bool:
    return load_state(results_dir).get("state") == "done"


def is_retired(results_dir: str) -> bool:
    """任务是否已退役（完成或放弃）—— 退役状态不得污染新任务。"""
    return load_state(results_dir).get("state") in ("done", "cancelled")


def get_task_class(results_dir: str) -> str:
    """当前任务类型：normal（默认，画图/轻量分析）| long_running（长任务管线）。"""
    return load_state(results_dir).get("task_class", "normal")


def set_task_class(results_dir: str, task_class: str) -> bool:
    """标记任务类型（运行时证据升级 long_running），不改变 state/reason。"""
    if task_class not in VALID_TASK_CLASSES or not results_dir:
        return False
    try:
        _st = load_state(results_dir)
        _st["task_class"] = task_class
        return _write_state(results_dir, _st)
    except Exception:
        logger.warning("[RunGate] 写入 task_class 失败", exc_info=True)
        return False


def user_restarts(results_dir: str, user_text: str) -> bool:
    """用户新消息是否算"显式继续/新任务"（命中才把 done 重置为 pending）。

    用户主动发消息本身即是新指令；此处仅做保守细化：命中词表立即重置，
    未命中时由 check_gate 返回 ask_user 而非直接放行。
    """
    if not user_text:
        return False
    t = user_text.lower().strip()
    return any(w in t for w in RESET_HINT_WORDS)


def check_gate(results_dir: str, *, interrupt_requested: bool = False,
               user_message: Optional[str] = None, is_auto_wake: bool = True) -> Tuple[str, str]:
    """每轮运行前的闸门判定。返回 (verdict, reason)。

    verdict:
      run       — 放行（新任务 / 用户显式继续 / 状态 running）
      stop      — 拒绝（task_state == done 的自动唤醒 / 未武装的自动唤醒 /
                   轮数预算耗尽的自动唤醒 / 中断置位）
      ask_user  — 状态 done 但用户发了消息且未命中词表：交由上层决定
                  （上层可发确认消息，或直接重置为新任务）

    is_auto_wake=True 表示本轮由 self-check/watchdog 触发（非用户消息）。
    M2：非退役任务的自动唤醒要求 armed（重启后需用户消息重新授权）。
    M3：非退役任务的自动唤醒要求 rounds_started < max_rounds。
    """
    # 中断优先：任何路径都尊重中断
    if interrupt_requested:
        return "stop", "interrupt requested"

    st = load_state(results_dir)
    state = st.get("state", "pending")

    if state == "done" or state == "cancelled":
        if is_auto_wake:
            return "stop", f"task_state={state}: 自动唤醒被闸门拦截（任务已退役，防止重启）"
        # 用户消息路径
        if user_restarts(results_dir, user_message or ""):
            save_state(results_dir, "pending", "user explicitly restarted")
            return "run", "user explicitly restarted (task_state reset to pending)"
        return "ask_user", f"task_state={state}: 用户消息未命中继续词表，由上层决定是否开新任务"

    # 2026-10-18：自动唤醒只被"显式暂停"拦住（进程内许可默认 armed，重启不再冻结）
    if is_auto_wake and str(st.get("activation") or ACTIVATION_ARMED) != ACTIVATION_ARMED:
        return "stop", ("paused: 任务已被显式暂停（%s）——发消息或恢复运行即可继续"
                        % (st.get("paused_by") or "user"))

    # M3: 硬轮数预算（自动唤醒到上限即停）
    if is_auto_wake and int(st.get("rounds_started", 0)) >= int(st.get("max_rounds", DEFAULT_MAX_ROUNDS)):
        return "stop", (f"round budget exhausted: {st.get('rounds_started')}/"
                        f"{st.get('max_rounds')} 轮已用尽，需用户消息刷新预算")

    if state == "blocked":
        if is_auto_wake:
            # blocked 的自动唤醒：允许（看门狗可尝试恢复），但上限由上层控制
            return "run", "task_state=blocked: 允许自动唤醒尝试恢复"
        return "run", "user message on blocked task"

    # pending / running：自动唤醒与用户消息均放行
    return "run", f"task_state={state}: 放行"


def reconcile(results_dir: str) -> list:
    """M4: 启动一致性对账。返回告警/修复描述列表（空 = 干净）。

    自动修复确定性漂移：
      - state == done 但 task_plan.md 仍在 → 归档为 task_plan.done.md（与
        _schedule_self_check 的完成归档逻辑一致）
    只读告警：
      - 非退役状态但无 task_plan.md → 可疑孤儿任务
      - 非退役但未武装 → 提示重启后需用户消息重新授权（M2 预期行为）
    """
    if not results_dir or not os.path.isdir(results_dir):
        return []
    notes: list = []
    st = load_state(results_dir)
    state = st.get("state", "pending")
    _plan = os.path.join(results_dir, "task_plan.md")
    _plan_done = os.path.join(results_dir, "task_plan.done.md")

    if state in ("done", "cancelled"):
        if os.path.isfile(_plan):
            try:
                if os.path.exists(_plan_done):
                    os.remove(_plan_done)
                os.rename(_plan, _plan_done)
                notes.append(f"task_state={state} 但 task_plan.md 未归档 → 已归档 task_plan.done.md")
            except Exception as e:
                notes.append(f"task_state={state} 但 task_plan.md 归档失败: {e}")
    else:
        if not os.path.isfile(_plan) and not os.path.isfile(_plan_done):
            notes.append(f"task_state={state} 但无 task_plan.md（可疑孤儿任务，需人工确认）")
        if not st.get("armed", False):
            notes.append("非退役任务未武装：重启后自动唤醒已暂停，用户发消息即恢复（M2 预期）")
    return notes
