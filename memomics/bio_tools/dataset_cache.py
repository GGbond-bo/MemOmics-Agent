# -*- coding: utf-8 -*-
"""数据集持久化（用户 2026-10-18 要求）：
读过的**大文件**（默认 >100MB，尤其集群/HPC 远程数据）必须登记到会话的 data_index.json，
下一个任务直接从本地缓存复用，不再重复下载/读取。

设计（对齐 DSH 的"有状态工具 + 结构化事实"）：
  - register(results_dir, local_path, source=..., note=...) → 写/更新 results/<sid>/data_index.json
  - list_datasets(results_dir) → 条目列表（带 size/mtime 校验结果）
  - verify(entry) → 文件还在且大小/时间一致 = 可复用
  - build_cache_hint(results_dir) → 给模型的一段系统提示（每回合注入，模型才知道有缓存）
"""
from __future__ import annotations

import json
import os
import time

INDEX_NAME = "data_index.json"
DEFAULT_THRESHOLD_MB = 100          # >100MB 就属于"必须持久化"的大数据


def _index_path(results_dir: str) -> str:
    return os.path.join(results_dir, INDEX_NAME)


def _load(results_dir: str) -> dict:
    p = _index_path(results_dir)
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {"datasets": []}
    except Exception:
        return {"datasets": []}


def _save(results_dir: str, d: dict) -> bool:
    try:
        os.makedirs(results_dir, exist_ok=True)
        p = _index_path(results_dir)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def _stat(path: str) -> dict:
    try:
        st = os.stat(path)
        return {"size": int(st.st_size), "mtime": round(float(st.st_mtime), 3)}
    except Exception:
        return {}


def is_big(path: str, threshold_mb: int = DEFAULT_THRESHOLD_MB) -> bool:
    try:
        return os.path.getsize(path) >= threshold_mb * 1024 * 1024
    except Exception:
        return False


def register(results_dir: str, local_path: str, *, source: str = "", note: str = "",
             kind: str = "", threshold_mb: int = DEFAULT_THRESHOLD_MB) -> dict:
    """登记一个已就位的数据集（本地路径 + 来源）。重复登记会更新而不是重复条目。"""
    if not results_dir or not local_path:
        return {"ok": False, "error": "需要 results_dir 与 local_path"}
    lp = os.path.abspath(local_path)
    if not os.path.exists(lp):
        return {"ok": False, "error": f"路径不存在: {lp}"}
    d = _load(results_dir)
    items = d.get("datasets") or []
    st = _stat(lp)
    rec = {"path": lp, "size": st.get("size", 0), "mtime": st.get("mtime", 0),
           "source": source, "note": note, "kind": kind,
           "registered_at": time.time(), "last_used": time.time()}
    for i, it in enumerate(items):
        if os.path.normcase(it.get("path", "")) == os.path.normcase(lp):
            items[i] = {**it, **rec, "registered_at": it.get("registered_at", rec["registered_at"])}
            break
    else:
        items.append(rec)
    d["datasets"] = items
    d["updated_at"] = time.time()
    ok = _save(results_dir, d)
    return {"ok": ok, "path": lp, "size": rec["size"],
            "big": bool(rec["size"] >= threshold_mb * 1024 * 1024),
            "count": len(items)}


def verify(rec: dict) -> bool:
    """登记时的 size/mtime 仍一致 = 还能直接复用。"""
    try:
        cur = _stat(rec.get("path", ""))
        return bool(cur) and cur.get("size") == rec.get("size") and cur.get("mtime") == rec.get("mtime")
    except Exception:
        return False


def list_datasets(results_dir: str) -> list:
    out = []
    for it in (_load(results_dir).get("datasets") or []):
        o = dict(it)
        o["valid"] = verify(it)
        out.append(o)
    return out


def mark_used(results_dir: str, path: str) -> None:
    try:
        d = _load(results_dir)
        changed = False
        for it in (d.get("datasets") or []):
            if os.path.normcase(it.get("path", "")) == os.path.normcase(os.path.abspath(path)):
                it["last_used"] = time.time()
                changed = True
        if changed:
            _save(results_dir, d)
    except Exception:
        pass


def _human(n: int) -> str:
    try:
        n = float(n)
    except Exception:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"


def build_cache_hint(results_dir: str, threshold_mb: int = DEFAULT_THRESHOLD_MB) -> str:
    """每回合注入的系统提示：有哪些数据集可直接复用（模型因此不会重复下载/读取）。"""
    if not results_dir:
        return ""
    try:
        items = list_datasets(results_dir)
    except Exception:
        return ""
    if not items:
        return ""
    usable = [it for it in items if it.get("valid")]
    broken = [it for it in items if not it.get("valid")]
    lines = ["【数据集缓存（本会话已持久化，优先复用，禁止无谓重读/重新下载）】"]
    for it in usable[:12]:
        lines.append(f"  • {it['path']}  ({_human(it.get('size', 0))}"
                     + (f"，来源: {it['source']}" if it.get("source") else "")
                     + (f"，备注: {it['note'][:60]}" if it.get("note") else "") + ")")
    for it in broken[:5]:
        lines.append(f"  • [已失效，需重新获取] {it['path']}")
    lines.append(
        f"  规则：大于 {threshold_mb}MB 的数据（尤其集群/HPC 远程数据）读一次就要落盘并登记，"
        "下一个任务直接用上面路径；新的大数据先询问用户是否持久化到本地缓存再决定。")
    return "\n".join(lines) + "\n"


SCHEMA = {
    "name": "dataset_cache",
    "description": (
        "登记/查询本会话的数据集缓存（大于 100MB 或任何集群/HPC 远程数据读完后必须登记，"
        "下个任务直接复用本地路径，避免重复下载或重读）。action: register|list。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["register", "list"], "description": "register 登记 / list 查看"},
            "path": {"type": "string", "description": "已就位的本地路径（register 必填）"},
            "source": {"type": "string", "description": "来源（如 集群路径 / 数据库 / 用户提供）"},
            "note": {"type": "string", "description": "备注（样本数、基因数、处理状态等）"},
        },
        "required": ["action"],
    },
}


def dataset_cache_tool(action: str = "list", path: str = "", source: str = "", note: str = "") -> str:
    rd = ""
    try:
        from memomics.bio_tools.debate_analysis import get_session_results_dir
        rd = get_session_results_dir() or ""
    except Exception:
        rd = ""
    if not rd:
        return json.dumps({"ok": False, "error": "拿不到会话 results_dir"}, ensure_ascii=False)
    if action == "register":
        return json.dumps(register(rd, path, source=source, note=note), ensure_ascii=False)
    return json.dumps({"ok": True, "datasets": list_datasets(rd)}, ensure_ascii=False, indent=1)


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="dataset_cache",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: dataset_cache_tool(
                args.get("action", "list"), args.get("path", ""),
                args.get("source", ""), args.get("note", "")),
        )
    except Exception:
        pass


_register()
