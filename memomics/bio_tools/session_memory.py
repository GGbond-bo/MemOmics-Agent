# -*- coding: utf-8 -*-
"""会话锚点工具 — 跨上下文压缩持久的关键信息标记（2026-08-14）。

科研会话超长运行的核心保障：
- 用户重要的文件/路径/脚本/结论/偏好 → session_memory(add) 确定性写入
  hermes_home/session_anchors/<sid>.md（JSON Lines，不依赖 LLM 摘要）
- 每轮对话自动注入锚点摘要（server.py _inject_anchors），压缩后依然找回
- 系统自动标记：results/ 新产物、用户消息中的路径
"""
import json
import os
import re
import time
import logging

logger = logging.getLogger("memomics.session_memory")

# 相对 hermes_home：<repo>/hermes_home/session_anchors/<sid>.md
_MEMOMICS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ANCHORS_DIR = os.path.join(_MEMOMICS_DIR, "hermes_home", "session_anchors")

_KINDS = ("file", "path", "script", "finding", "preference", "decision", "todo")
# 值得锚定的产物扩展名
_ANCHOR_EXTS = (".r", ".py", ".sh", ".csv", ".tsv", ".h5ad", ".rds", ".png",
                ".jpg", ".pdf", ".xlsx", ".svg", ".txt", ".md")
# 每会话锚点上限（超限丢弃最旧的非置顶条目）
_MAX_ANCHORS = 120
# 单个锚点内容上限
_MAX_CONTENT = 240


def _anchors_path(sid: str) -> str:
    _safe = re.sub(r"[^\w\-.]", "_", sid or "default")
    return os.path.join(_ANCHORS_DIR, f"{_safe}.md")


def _load(sid: str) -> list:
    try:
        p = _anchors_path(sid)
        if not os.path.isfile(p):
            return []
        with open(p, "r", encoding="utf-8") as f:
            items = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                    if isinstance(o, dict) and o.get("content"):
                        items.append(o)
                except Exception:
                    continue
            return items
    except Exception:
        return []


def _save(sid: str, items: list) -> None:
    try:
        os.makedirs(_ANCHORS_DIR, exist_ok=True)
        # 超限：先丢弃最旧的非 pinned
        if len(items) > _MAX_ANCHORS:
            _non_pinned = [it for it in items if not it.get("pinned")]
            if len(_non_pinned) > 0:
                _drop = _non_pinned[0]
                items = [it for it in items if it is not _drop]
        with open(_anchors_path(sid), "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _anchor_add(sid: str, kind: str, content: str, importance: float = 0.5,
                pinned: bool = False) -> bool:
    """添加一条锚点。content 按路径去重（同内容同 kind 只保留最新）。"""
    try:
        if not content or not content.strip():
            return False
        kind = kind if kind in _KINDS else "finding"
        content = content.strip()[: _MAX_CONTENT]
        items = _load(sid)
        for it in items:
            if it.get("kind") == kind and it.get("content") == content:
                it["ts"] = time.time()
                it["importance"] = max(it.get("importance", 0.5), float(importance))
                it["pinned"] = bool(it.get("pinned") or pinned)
                _save(sid, items)
                return False  # 已存在 → 更新，不算新增
        items.append({
            "kind": kind,
            "content": content,
            "importance": round(float(importance), 2),
            "pinned": bool(pinned),
            "ts": time.time(),
        })
        _save(sid, items)
        return True
    except Exception as e:
        logger.warning(f"session_memory add failed: {e}")
        return False


def build_digest(sid: str, max_items: int = 12, max_chars: int = 700) -> str:
    """生成注入上下文的锚点摘要（确定性，压缩后依然存在）。"""
    try:
        items = _load(sid)
        if not items:
            return ""
        # 排序：pinned 优先 → importance 降序 → 时间降序
        items = sorted(items, key=lambda x: (
            0 if x.get("pinned") else 1,
            -(x.get("importance", 0.5)),
            -(x.get("ts", 0)),
        ))
        _icons = {"file": "📁", "path": "📂", "script": "📜", "finding": "🔬",
                  "preference": "⭐", "decision": "⚖️", "todo": "☐"}
        lines = ["[会话锚点 · 跨压缩持久 · 重要文件/路径/脚本以这里为准]"]
        _used = 0
        for it in items[:max_items]:
            _pin = "📌" if it.get("pinned") else "  "
            _line = f"{_pin}{_icons.get(it.get('kind', ''), '•')} {it.get('content', '')}"
            if _used + len(_line) > max_chars:
                break
            lines.append(_line)
            _used += len(_line)
        if _used == 0:
            return ""
        return "\n".join(lines)
    except Exception:
        return ""


def auto_anchor_recent_files(sid: str, results_dir: str, since_ts: float,
                             max_files: int = 6) -> int:
    """自动锚定 results_dir 下自 since_ts 以来新产生的产物文件（系统级标记）。"""
    try:
        if not results_dir or not os.path.isdir(results_dir):
            return 0
        found = []
        for root, dirs, files in os.walk(results_dir):
            depth = root[len(results_dir):].count(os.sep)
            if depth > 3:
                dirs[:] = []
                continue
            for fn in files:
                if not fn.lower().endswith(_ANCHOR_EXTS):
                    continue
                fp = os.path.join(root, fn)
                try:
                    if os.path.getmtime(fp) >= since_ts:
                        found.append((os.path.getmtime(fp), fp))
                except OSError:
                    continue
        found.sort(reverse=True)
        n = 0
        for _mt, fp in found[:max_files]:
            _kind = "script" if fp.lower().endswith((".r", ".py", ".sh")) else "file"
            if _anchor_add(sid, _kind, fp.replace("\\", "/"), 0.55, False):
                n += 1
        return n
    except Exception:
        return 0


def auto_anchor_user_mentions(sid: str, user_text: str) -> int:
    """从用户消息中提取路径并锚定（用户点名的文件/路径 = 重点标记）。"""
    try:
        if not user_text:
            return 0
        n = 0
        for m in re.finditer(r"[A-Za-z]:[\\/][^\s,，;；:：]+", user_text):
            p = m.group(0).rstrip("。.，,;；")
            if len(p) > 4 and _anchor_add(sid, "path", p.replace("\\", "/"), 0.9, True):
                n += 1
        for m in re.finditer(r"(?<![\\/\w])(?:results|data|figures)[\\/][^\s,，;；:：]+", user_text):
            p = m.group(0).rstrip("。.，,;；")
            if _anchor_add(sid, "path", p.replace("\\", "/"), 0.8, True):
                n += 1
        return n
    except Exception:
        return 0


def session_memory(action: str = "add", kind: str = "finding", content: str = "",
                   importance: float = 0.5, pinned: bool = False, task_id: str = "") -> str:
    """会话锚点工具：add / list / remove。

    add     : 标记关键信息（文件/路径/脚本/结论/偏好），pinned=true 永不因超限淘汰
    list    : 列出当前会话全部锚点
    remove  : 按 content 删除一条锚点
    """
    from .debate_analysis import get_session_sid
    sid = task_id or get_session_sid() or "default"
    try:
        if action == "list":
            items = _load(sid)
            if not items:
                return json.dumps({"ok": True, "count": 0, "items": [],
                                   "note": "尚无锚点。用 add 标记重要文件/路径/结论。"},
                                  ensure_ascii=False)
            return json.dumps({"ok": True, "count": len(items),
                               "items": [{"kind": it.get("kind"), "content": it.get("content"),
                                          "pinned": it.get("pinned", False),
                                          "importance": it.get("importance", 0.5)}
                                         for it in sorted(items, key=lambda x: -(x.get("ts", 0)))[:50]]},
                              ensure_ascii=False)
        if action == "remove":
            items = _load(sid)
            before = len(items)
            items = [it for it in items if it.get("content") != content]
            _save(sid, items)
            return json.dumps({"ok": True, "removed": before - len(items)}, ensure_ascii=False)
        if action == "add":
            added = _anchor_add(sid, kind, content, importance, pinned)
            return json.dumps({"ok": True, "added": added, "sid": sid,
                               "total": len(_load(sid))}, ensure_ascii=False)
        return json.dumps({"ok": False, "error": f"未知 action: {action}（支持 add/list/remove）"},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)[:200]}, ensure_ascii=False)


SCHEMA = {
    "name": "session_memory",
    "description": (
        "会话锚点（跨上下文压缩持久的关键信息标记）。科研长会话中，把用户重要的"
        "文件路径、关键脚本、阶段结论、用户偏好写入锚点文件——每轮对话自动注入摘要，"
        "上下文压缩后依然可精确找回。重要信息必须用本工具标记，禁止只写在对话里"
        "（压缩可能丢失）。add 标记；list 查看；remove 删除。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "list", "remove"],
                       "description": "add=标记关键信息; list=列出全部锚点; remove=删除一条"},
            "kind": {"type": "string",
                     "enum": list(_KINDS),
                     "description": "锚点类型: file=文件 / path=目录或路径 / script=脚本 / "
                                    "finding=阶段结论 / preference=用户偏好 / decision=决策 / todo=待办"},
            "content": {"type": "string",
                        "description": "锚点内容（路径用绝对路径，结论一句话说清）"},
            "importance": {"type": "number", "minimum": 0, "maximum": 1,
                           "description": "重要度 0-1，用户点名的重点信息建议 ≥0.8"},
            "pinned": {"type": "boolean",
                       "description": "置顶=true 时永不因超限淘汰（用户特别强调的信息）"},
        },
        "required": ["action"],
    },
}


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="session_memory",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: session_memory(
                args.get("action", "add"),
                args.get("kind", "finding"),
                args.get("content", ""),
                args.get("importance", 0.5),
                args.get("pinned", False),
                kw.get("task_id", ""),
            ),
            emoji="📌",
            max_result_size_chars=12_000,
        )
    except Exception as e:
        logger.warning(f"session_memory register failed: {e}")


_register()
