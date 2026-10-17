"""子 agent 的持久邮箱 + 会话记录（借鉴 DSH subagent 的 continuable children 与 durable mailbox）。

现状（改造前）：`delegate_task` 派出的子 agent 跑完即销毁 ——
  - 子 agent 的对话只留在返回值里，进程重启后无从续聊；
  - 想给子 agent 补一句话没有任何通道（只能重新派发一次，重花 50 步预算）。

本模块补两件事：
  1. **transcript 落盘**：每个 delegation_id 一份 JSON（messages + goal + model），
     存 <MEMOMICS_HOME>/delegations/<deleg_id>.json；
  2. **持久邮箱**：mailbox 里挂 pending 消息，子 agent 下次被唤醒/续聊时先取走。

配套 `delegate_tool.continue_subagent()`：命内存里的子 agent 就直接续聊，
否则从 transcript 冷启（当前版本冷启会明确告知需重新派发 + 给出 transcript 路径）。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

_LOCK = threading.RLock()
_MAX_MAILBOX = 64


def root_dir() -> str:
    for env in ("MEMOMICS_HOME", "HERMES_HOME"):
        home = os.environ.get(env) or ""
        if home:
            return os.path.join(home, "delegations")
    return os.path.join(tempfile.gettempdir(), "memomics_delegations")


def _path(delegation_id: str) -> str:
    safe = "".join(ch for ch in str(delegation_id or "") if ch.isalnum() or ch in "-_.")[:80]
    safe = safe.strip("._") or "deleg"   # 2026-10-18：去掉前导/尾随点，杜绝 "....x.json" 这类怪名
    return os.path.join(root_dir(), f"{safe}.json")


def _read(delegation_id: str) -> Dict[str, Any]:
    p = _path(delegation_id)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(delegation_id: str, data: Dict[str, Any]) -> bool:
    try:
        os.makedirs(root_dir(), exist_ok=True)
        p = _path(delegation_id)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def save_child(delegation_id: str, *, goal: str = "", messages: Optional[List[Dict[str, Any]]] = None,
               model: str = "", session_id: str = "", summary: str = "") -> bool:
    """保存/更新一个子 agent 的会话记录（messages 会被整体覆盖）。"""
    if not delegation_id:
        return False
    with _LOCK:
        data = _read(delegation_id)
        data.update({
            "delegation_id": delegation_id,
            "goal": goal or data.get("goal", ""),
            "model": model or data.get("model", ""),
            "session_id": session_id or data.get("session_id", ""),
            "summary": summary or data.get("summary", ""),
            "updated_at": time.time(),
        })
        if messages is not None:
            data["messages"] = list(messages)
        data.setdefault("created_at", time.time())
        data.setdefault("mailbox", [])
        return _write(delegation_id, data)


def load_child(delegation_id: str) -> Dict[str, Any]:
    with _LOCK:
        return _read(delegation_id)


def queue_message(delegation_id: str, text: str) -> bool:
    """把一条消息投进某子 agent 的持久邮箱（pending）。"""
    text = (text or "").strip()
    if not delegation_id or not text:
        return False
    with _LOCK:
        data = _read(delegation_id)
        if not data:
            data = {"delegation_id": delegation_id, "created_at": time.time(), "messages": []}
        box = data.get("mailbox")
        if not isinstance(box, list):
            box = []
        box.append({"text": text, "ts": time.time(), "state": "pending"})
        data["mailbox"] = box[-_MAX_MAILBOX:]
        data["updated_at"] = time.time()
        return _write(delegation_id, data)


def take_pending(delegation_id: str) -> List[str]:
    """取出并标记已投递的邮箱消息（只有 state=pending 的会被取走）。"""
    with _LOCK:
        data = _read(delegation_id)
        box = data.get("mailbox")
        if not isinstance(box, list) or not box:
            return []
        out = []
        changed = False
        for item in box:
            if isinstance(item, dict) and item.get("state") == "pending":
                out.append(str(item.get("text") or ""))
                item["state"] = "delivered"
                item["delivered_at"] = time.time()
                changed = True
        if changed:
            data["updated_at"] = time.time()
            _write(delegation_id, data)
        return [t for t in out if t]


def list_children(session_id: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    """列出落过盘的子 agent（供 /delegations 面板或 CLI 查看）。"""
    d = root_dir()
    out: List[Dict[str, Any]] = []
    try:
        names = [n for n in os.listdir(d) if n.endswith(".json")]
    except Exception:
        return out
    for n in names:
        data = _read(n[:-5])
        if not isinstance(data, dict) or not data:
            continue
        if session_id and data.get("session_id") not in ("", session_id):
            continue
        box = data.get("mailbox") or []
        out.append({
            "delegation_id": data.get("delegation_id") or n[:-5],
            "goal": (data.get("goal") or "")[:120],
            "updated_at": data.get("updated_at", 0),
            "messages": len(data.get("messages") or []),
            "pending": sum(1 for m in box if isinstance(m, dict) and m.get("state") == "pending"),
        })
    out.sort(key=lambda r: r.get("updated_at", 0), reverse=True)
    return out[:limit]
