"""
Guardian — Git snapshot + rollback system for MemOmics.

Prevents AI from "repairing itself into a corner" by:
  1. Taking a git snapshot before every file modification
  2. Tracking consecutive rail_review(post) failures
  3. Auto-rolling back after 3 consecutive failures

Referred to by SOUL.md Iron Law 14.
"""

import os
import json
import subprocess
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # MEMOMICS_HOME/
STATE_FILE = REPO_ROOT / "memomics" / "config" / "guardian_state.json"


def _ensure_state_dir():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    _ensure_state_dir()
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {"consecutive_failures": 0, "last_snapshot": None, "snapshot_history": []}


def _save_state(state: dict):
    _ensure_state_dir()
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _run_git(args: list, cwd=None) -> tuple:
    cwd = cwd or str(REPO_ROOT)
    try:
        result = subprocess.run(["git"] + args, cwd=cwd,
                                capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", "git not found"
    except subprocess.TimeoutExpired:
        return -2, "", "git timeout"


def guardian_snapshot(label: str = "") -> dict:
    """Take a git snapshot BEFORE file modifications."""
    state = _load_state()
    rc, status, stderr = _run_git(["status", "--porcelain"])
    if rc != 0:
        return {"ok": False, "error": f"git status failed: {stderr}"}
    if not status:
        return {"ok": True, "commit_hash": None, "message": "no changes"}

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = f"guardian: {label} [{timestamp}]"

    rc_a, _, e_a = _run_git(["add", "-A"])
    if rc_a != 0:
        return {"ok": False, "error": f"git add failed: {e_a}"}

    rc_c, _, e_c = _run_git(["commit", "-m", commit_msg])
    if rc_c != 0:
        if "nothing to commit" in e_c.lower():
            return {"ok": True, "commit_hash": None, "message": "nothing to commit"}
        return {"ok": False, "error": f"git commit failed: {e_c}"}

    rc_h, commit_hash, _ = _run_git(["rev-parse", "HEAD"])
    if rc_h != 0:
        commit_hash = "unknown"

    state["last_snapshot"] = {"label": label, "commit_hash": commit_hash, "timestamp": timestamp}
    state["snapshot_history"].append(state["last_snapshot"])
    if len(state["snapshot_history"]) > 20:
        state["snapshot_history"] = state["snapshot_history"][-20:]
    _save_state(state)
    logger.info(f"guardian: snapshot '{label}' → {commit_hash[:8]}")
    return {"ok": True, "commit_hash": commit_hash, "message": f"snapshot '{label}' → {commit_hash[:8]}"}


def guardian_check(failure_count: int = 0, threshold: int = 3) -> dict:
    """Check if auto-rollback is needed after rail_review failure."""
    state = _load_state()
    state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
    current = state["consecutive_failures"]

    if current < threshold:
        _save_state(state)
        return {"action": "warn", "consecutive_failures": current,
                "message": f"rail_review failed ({current}/{threshold}). Try alternative."}

    # ROLLBACK
    last = state.get("last_snapshot", {})
    ch = last.get("commit_hash")
    if not ch:
        _save_state(state)
        return {"action": "error", "message": "No snapshot to rollback to!"}

    rc, _, stderr = _run_git(["reset", "--hard", ch])
    if rc != 0:
        _save_state(state)
        return {"action": "error", "message": f"Rollback failed: {stderr}"}

    state["consecutive_failures"] = 0
    state["last_rollback"] = {"commit": ch, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                               "reason": f"auto after {current} failures"}
    _save_state(state)
    return {"action": "rollback", "commit_hash": ch,
            "message": f"GUARDIAN ROLLBACK: {current} failures → reset to {ch[:8]}"}


def guardian_reset_counters() -> dict:
    state = _load_state()
    state["consecutive_failures"] = 0
    _save_state(state)
    return {"ok": True, "message": "failure counters reset"}


# ── Hermes registration ──
SCHEMA = {
    "name": "guardian",
    "description": "Guardian rollback: git snapshots before file mods; auto-rollback after 3 consecutive rail_review failures.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["snapshot", "check", "reset"]},
            "label": {"type": "string", "description": "Snapshot label (for action=snapshot)"},
            "failure_count": {"type": "integer", "description": "Failure count (for action=check)"},
        },
        "required": ["action"],
    },
}


def guardian(action: str, label: str = "", failure_count: int = 0) -> str:
    """guardian 工具入口。返回 JSON 字符串（Hermes 工具契约）。"""
    if action == "snapshot":
        result = guardian_snapshot(label=label)
    elif action == "check":
        result = guardian_check(failure_count=failure_count)
    elif action == "reset":
        result = guardian_reset_counters()
    else:
        result = {"ok": False, "error": f"unknown action: {action}"}
    return json.dumps(result, ensure_ascii=False)


def _register():
    """2026-08-15 修复: 旧版 register(registry) 从未被调用且签名过时 → 工具从未注册。"""
    try:
        from tools.registry import registry
        registry.register(
            name="guardian",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: guardian(
                args.get("action", "snapshot"),
                args.get("label", ""),
                args.get("failure_count", 0),
            ),
            emoji="🛡️",
            max_result_size_chars=4_000,
        )
    except Exception as e:
        logger.warning(f"guardian register failed: {e}")


_register()
