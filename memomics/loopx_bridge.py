"""MemOmics × LoopX 桥接层（P1-A 的 LoopX 照搬核心）。

LoopX v0.4.1（MIT，零依赖，纯标准库）已 vendor 到 memomics/vendor/loopx/。
本模块把 MemOmics 会话状态映射到 LoopX 控制平面状态，直接调用其纯函数：
  - build_quota_should_run  → 长任务"该不该继续跑"的确定性决策（quota 状态机）
  - collect_status         → 聚合 goal/todo/花销/阻塞为统一状态
  - build_heartbeat_prompt → 四档心跳汇报提示词（full/compact/brief/thin）
  - build_scheduler_hint   → 自检轮询间隔建议（退避表）
  - AppendOnlyStateEventStore → goal 生命周期事件（可选，P2）

关键适配（LoopX 假设无人值守，MemOmics 是交互式）：
  - operator_gate 状态在"用户在线/刚发消息"时由本桥裁决放行（gate_waived=True）
  - 状态文件落在 <results_dir>/.loopx/ —— 每会话独立目录，两会话控制平面天然隔离
  - 所有 loopx 调用带 try/except：失败返回安全默认，绝不阻断主流程（不修坏东西）
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("memomics.loopx_bridge")

# ── vendor 路径注入（相对本文件：memomics/vendor/loopx）─────────────────────
_VENDOR = Path(__file__).resolve().parent / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

# 延迟 import（vendor 未就位时模块仍可加载）
_loopx = None

# MemOmics 自托管调度声明（LoopX 执行上下文）：webui 后台调度 = local_scheduler + host_automation + hosted_automation
_SCHEDULER_CTX = {
    "host_surface": "local_scheduler",
    "scheduler_owner": "host_automation",
    "execution_mode": "hosted_automation",
    "source": "explicit",
}


def _load_loopx():
    global _loopx
    if _loopx is not None:
        return _loopx
    try:
        import loopx  # noqa: F401
        from loopx.control_plane.scheduler.scheduler_hint import build_scheduler_hint
        from loopx.heartbeat_prompt import build_heartbeat_prompt
        from loopx.quota import build_quota_should_run
        from loopx.status import collect_status
        _loopx = {
            "collect_status": collect_status,
            "build_quota_should_run": build_quota_should_run,
            "build_heartbeat_prompt": build_heartbeat_prompt,
            "build_scheduler_hint": build_scheduler_hint,
        }
        logger.info("[LoopXBridge] vendor loopx 已加载")
    except Exception:
        logger.warning("[LoopXBridge] vendor loopx 加载失败（功能降级为安全默认）", exc_info=True)
        _loopx = {}
    return _loopx


MIN_GOAL = {
    "id": None,  # 会话 sid
    "domain": "memomics",
    "status": "active",
    "role": "primary",
    "repo": None,  # results_dir
    "state_file": ".loopx/ACTIVE_GOAL_STATE.md",
    "authority_sources": [],
    "adapter": {"kind": "project_goal", "status": "active"},
    "spawn_policy": {"mode": "sequential", "allowed": True, "max_children": 0, "allowed_domains": []},
    "coordination": {"write_scope": "repo", "requires_parent_approval": []},
    "execution_profile": {"mode": "interactive", "allowed": True, "default_effort": "normal",
                          "allowed_efforts": ["normal"]},
    "quota": {"compute": 100, "window_hours": 24, "slot_minutes": 30,
              "allowed_slots": 500, "spent_slots": 0},
    "guards": [],
}


class LoopXBridge:
    """单会话桥：构造时在 <results_dir>/.loopx/ 注册 goal（幂等）。"""

    def __init__(self, sid: str, results_dir: str, user_online: bool = True):
        self.sid = sid
        self.results_dir = results_dir or ""
        self.user_online = user_online
        self.loopx_dir = Path(results_dir) / ".loopx" if results_dir else None
        self.registry_path = self.loopx_dir / "registry.json" if self.loopx_dir else None
        self._goal_id = None
        self._ensure_goal()

    # ── 状态注册 ────────────────────────────────────────────────────────────
    def _ensure_goal(self) -> Optional[str]:
        """幂等注册 goal（registry.json）。失败返回 None（安全降级）。"""
        if not self.loopx_dir:
            return None
        try:
            self.loopx_dir.mkdir(parents=True, exist_ok=True)
            registry = {"schema_version": "loopx_registry_v0", "goals": []}
            if self.registry_path.exists():
                try:
                    registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
                except Exception:
                    registry = {"schema_version": "loopx_registry_v0", "goals": []}
            for g in registry.get("goals", []):
                if g.get("id") == self.sid:
                    self._goal_id = self.sid
                    return self._goal_id
            goal = dict(MIN_GOAL)
            goal["id"] = self.sid
            goal["repo"] = self.results_dir
            registry.setdefault("goals", []).append(goal)
            tmp = self.registry_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.registry_path)
            self._goal_id = self.sid
            return self._goal_id
        except Exception:
            logger.warning("[LoopXBridge] goal 注册失败（降级）", exc_info=True)
            return None

    # ── 核心查询 ────────────────────────────────────────────────────────────
    def collect(self, limit: int = 80) -> dict:
        """聚合会话控制平面状态。loopx 不可用/异常 → 空 dict（上层走安全默认）。"""
        api = _load_loopx()
        if not api or not self.registry_path or not self.registry_path.exists():
            return {}
        try:
            # 注意：scan_roots 必须传 Path（LoopX 内部 .resolve()）
            return api["collect_status"](
                registry_path=self.registry_path,
                runtime_root_override=str(self.loopx_dir),  # 项目内隔离：runs 读 .loopx/goals/<sid>/runs/
                scan_roots=[Path(self.results_dir)],
                limit=limit,
                goal_id=self.sid,
            )
        except Exception:
            logger.warning("[LoopXBridge] collect_status 失败（降级）", exc_info=True)
            return {}

    def should_run(self) -> Dict[str, Any]:
        """照搬 LoopX quota 状态机的"该不该继续跑"决策 + 交互式适配。

        返回（安全默认：放行）:
          {should_run: True/False, state, decision, reason, gate_waived, source}
        """
        api = _load_loopx()
        base = {"should_run": True, "state": "eligible", "decision": "run",
                "reason": "loopx unavailable (safe default)", "gate_waived": False,
                "source": "default"}
        if not api:
            return base
        status = self.collect()
        if not status:
            return base
        try:
            decision = api["build_quota_should_run"](
                status, goal_id=self.sid, agent_id=None,
                scheduler_execution_context=_SCHEDULER_CTX)
        except Exception:
            logger.warning("[LoopXBridge] quota 决策失败（降级放行）", exc_info=True)
            return base
        if not isinstance(decision, dict):
            return base
        state = decision.get("state") or "eligible"
        should = bool(decision.get("should_run"))
        verdict = decision.get("decision") or "run"
        reason = decision.get("reason") or ""
        gate_waived = False
        # LoopX 融合（2026-08-07）：Codex work-item 语义（waiting/skip）对 MemOmics 无意义——
        # 活跃工作可能完全在外部（bash 管线/Rscript 子进程），这些状态不应停掉自检唤醒。
        # 只尊重明确的硬停状态（blocked/paused/throttled）+ 数据完整性保护（blocked_health）。
        if not should and state in ("waiting", "skip", "no_run", "connected_without_run"):
            should = True
            verdict = "run"
            reason = "loopx " + state + " 忽略（Codex 工作项语义；活跃工作可能在外部管线）: " + reason
        # 交互式适配：operator_gate 且用户在线 → 放行（LoopX 无人值守假设不适用）
        if state == "operator_gate" and not should and self.user_online:
            should = True
            verdict = "run"
            gate_waived = True
            reason = "operator gate waived: user online (interactive session)"
        return {"should_run": should, "state": state, "decision": verdict,
                "reason": reason, "gate_waived": gate_waived, "source": "loopx"}

    def heartbeat_prompt(self, mode: str = "thin") -> str:
        """心跳汇报文本：优先照搬 LoopX 状态汇总骨架（goal/todo/最近运行/阻塞），
        无状态时返回空串（调用方按需忽略）。

        LoopX 原版 build_heartbeat_prompt 返回的是 CLI 命令（进程内无 CLI），
        故取其数据源 collect_status 的相同字段构建文本骨架。
        """
        status = self.collect(limit=60)
        if not status:
            return ""
        lines = []
        # goal 状态
        gs = status.get("goal_state") or {}
        lines.append(f"goal: {gs.get('status', 'active')} | attention: {gs.get('attention_verdict', 'ok')}")
        # todo 概览（照搬 LoopX 心跳的 todo 摘要字段）
        todos = status.get("todos") or []
        if todos:
            by_status: dict = {}
            for t in todos:
                s = str(t.get("status") or "unknown")
                by_status[s] = by_status.get(s, 0) + 1
            lines.append("todos: " + ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())))
            for t in todos[:3]:
                if t.get("status") not in ("completed", "cancelled"):
                    lines.append(f"  - [{t.get('status')}] {str(t.get('summary') or t.get('title') or '')[:70]}")
        else:
            lines.append("todos: none")
        # 最近运行
        runs = status.get("runs") or []
        if runs:
            last = runs[0]
            lines.append(f"last run: {last.get('ts', '')} {str(last.get('summary') or last.get('status') or '')[:60]}")
        # 阻塞/等待
        att = status.get("attention") or {}
        if att.get("needs_user_or_controller"):
            lines.append("blockers: waiting on user/controller")
        if att.get("needs_codex"):
            lines.append("blockers: agent work pending")
        # quota 花销（LoopX 心跳固定包含）
        quota = gs.get("quota") or {}
        if quota:
            lines.append(f"quota: {quota.get('spent_slots', 0)}/{quota.get('allowed_slots', '?')} slots")
        text = "\n".join(lines)
        return text[:1800]

    def next_poll_interval(self, default_seconds: int = 300) -> int:
        """LoopX scheduler hint → 下次自检轮询间隔（秒）。

        P1-15(2026-08-13) 映射修正：读 vendor 真实契约字段
        `local_scheduler.recommended_interval_minutes`（此前读幻觉字段
        `interval_seconds`，永远落回 default=300s）。cadence_class 真实词汇：
          active_work   → 勤查 60s（有活干）
          unchanged_noop / agent_scope_wait / monitor_wait / quiet_wait
                        → recommended 间隔（含 vendor 的 progression 退避）
          human_gate    → 600s（等用户，别打扰）
          quota_paused / terminal_no_followup / control_plane_repair
          / agent_monitor_only → 2400s（暂停/终止态，交由自检完成判定收尾）
        """
        api = _load_loopx()
        if not api:
            return default_seconds
        try:
            status = self.collect(limit=40)
            if not status:
                return default_seconds
            hint = api["build_scheduler_hint"](status, scheduler_execution_context=_SCHEDULER_CTX)
            if not isinstance(hint, dict):
                return default_seconds
            cc = str(hint.get("cadence_class") or "")
            ls = hint.get("local_scheduler") or {}
            rec_min = ls.get("recommended_interval_minutes") if isinstance(ls, dict) else None
            if isinstance(rec_min, (int, float)) and rec_min > 0:
                base_sec = int(rec_min * 60)
            else:
                base_sec = default_seconds
            if cc == "active_work":
                return max(60, min(base_sec, 600))
            if cc in ("unchanged_noop", "agent_scope_wait", "monitor_wait", "quiet_wait"):
                return max(60, min(base_sec, 2400))
            if cc == "human_gate":
                return 600
            if cc in ("quota_paused", "terminal_no_followup",
                      "control_plane_repair", "agent_monitor_only"):
                return 2400
            return max(30, min(base_sec, 900))
        except Exception:
            return default_seconds

    def handoff_note(self, max_lines: int = 16) -> str:
        """照搬 LoopX handoff budget（≤16 行/≤1800 字符）—— 会话交接摘要。

        从 collect_status 的 goal 状态/todo 概览提取。失败返回空串。
        """
        api = _load_loopx()
        if not api:
            return ""
        status = self.collect(limit=40)
        if not status:
            return ""
        try:
            goal_state = status.get("goal_state") or {}
            lines = []
            lines.append(f"# MemOmics 会话交接 · {self.sid[:12]}")
            lines.append(f"- goal: {goal_state.get('status', 'unknown')}")
            lines.append(f"- 状态: {goal_state.get('attention_verdict', '')}")
            todos = status.get("todos") or []
            if todos:
                lines.append(f"- 待办 {len(todos)} 项:")
                for t in todos[:6]:
                    lines.append(f"  - [{t.get('status', '?')}] {str(t.get('summary') or t.get('title') or '')[:60]}")
            else:
                lines.append("- 待办: 无")
            note = "\n".join(lines)[:1800].rstrip()
            return "\n".join(note.splitlines()[:max_lines])
        except Exception:
            return ""

    # ── 事件溯源（P2 可选，已备好 API）──────────────────────────────────────
    def record_turn_delivery(self, *, outcome: str = "outcome_progress",
                             turn_kind: str = "product_path_execution",
                             batch_scale: str = "status_only",
                             summary: str = "", elapsed_s: float = 0.0,
                             model: str = "", ok: bool = True) -> bool:
        """回合交付记录 → .loopx/runs/（index.jsonl + json/md 简件，LoopX 兼容）。

        执行层核心（2026-08-07）：agent 每回合结束后调用，collect_status 才能看到
        运行历史（run_count>0）→ scheduler_hint 的 cadence 真实生效
        （run_now 勤查 / backoff 退避，而不是永远固定默认值）。
        字符串直接写（不强制枚举校验），LoopX normalize 对未知值自动降级。
        """
        if not self.loopx_dir:
            return False
        try:
            from loopx.history import now_local, write_reserved_run_artifacts
            # LoopX 约定：runs 在 <runtime_root>/goals/<goal_id>/runs/（runtime_root = .loopx/ 项目内隔离；
            # collect_status 的 run_history 按该目录的 index.jsonl 扫描，goal 过滤靠目录 + record.goal_id）
            runs_dir = self.loopx_dir / "goals" / self.sid / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)
            generated_at = now_local()
            record = {
                "goal_id": self.sid,
                "agent_id": None,
                "delivery_outcome": str(outcome),
                "delivery_turn_kind": str(turn_kind),
                "delivery_batch_scale": str(batch_scale),
                "summary": str(summary)[:200],
                "elapsed_s": float(elapsed_s or 0),
                "model": str(model)[:60],
                "ok": bool(ok),
                "generated_at": generated_at,
            }
            def _render(payload: dict) -> str:
                return json.dumps(payload, ensure_ascii=False, indent=2)
            write_reserved_run_artifacts(
                runs_dir=runs_dir,
                generated_at=generated_at,
                record=record,
                index_record=dict(record),
                payload=dict(record),
                render_markdown=_render,
            )
            return True
        except Exception:
            return False

    def append_event(self, event_type: str, payload: Optional[dict] = None) -> bool:
        """goal 生命周期事件落 .loopx/events.jsonl（幂等 append）。"""
        api = _load_loopx()
        if not api or not self.loopx_dir:
            return False
        try:
            from loopx.event_sourced_state import AppendOnlyStateEventStore
            store = AppendOnlyStateEventStore(self.loopx_dir / "events.jsonl")
            # LoopX 事件类型白名单：TODO_* / REFRESH_RECORDED / RUN_RECORDED /
            # QUOTA_SPENT / EVIDENCE_ATTACHED / SUPERVISOR_*
            store.append({
                "event_id": f"{self.sid}-{int(time.time() * 1000)}",
                "goal_id": self.sid,
                "agent_id": None,
                "event_type": "refresh_recorded",
                "payload": {"note": event_type, **(payload or {})},
                "ts": time.time(),
            })
            return True
        except Exception:
            return False
