# -*- coding: utf-8 -*-
"""记忆治理 — 治理器（governor）

职责：
1. init_index()    — 扫描 MEMORY.md/USER.md 生成 memories/index.json（只读，零风险）
2. run_governance(dry_run=True) — 打分流转：L1→L2 下沉、L1/L2→L3 归档。
   默认 dry_run 只产出建议报告；apply=True 才真正迁移（保守设计）。

L2 外置：memory_store.db facts 表（holographic 已有 trust_score/retrieval_count）。
L3 归档：hermes_home/memories/archive/YYYY-MM.md（永不删除）。
"""
from __future__ import annotations

import json
import os
import time

from .memory_score import build_index, parse_entries, score_entry, decide_layer

MEMORIES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "hermes_home", "memories")
INDEX_PATH = os.path.join(MEMORIES_DIR, "index.json")
ARCHIVE_DIR = os.path.join(MEMORIES_DIR, "archive")
MEMORY_FILE = os.path.join(MEMORIES_DIR, "MEMORY.md")
USER_FILE = os.path.join(MEMORIES_DIR, "USER.md")


def _facts_lookup():
    """从 memory_store.db 读 facts 的检索次数（entry preview → (used_n, last_ts)）。"""
    lookup = {}
    try:
        import sqlite3
        db = os.path.join(os.path.dirname(MEMORIES_DIR), "memory_store.db")
        if not os.path.isfile(db):
            return lookup
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
        try:
            rows = conn.execute(
                "SELECT content, retrieval_count, last_retrieved FROM facts"
            ).fetchall()
            for content, rc, lr in rows:
                if content:
                    lookup[content[:120]] = (int(rc or 0),
                                            float(lr) if lr else None)
        except Exception:
            pass
        finally:
            conn.close()
    except Exception:
        pass
    return lookup


def register_entry(kind: str, content: str, importance: float = 0.5,
                   pinned: bool = False) -> None:
    """memory 工具写入后登记条目元数据到 index.json（2026-08-14）。

    kind: 'memory' | 'user'。失败静默（索引不是关键路径）。
    """
    try:
        os.makedirs(MEMORIES_DIR, exist_ok=True)
        idx = {}
        if os.path.isfile(INDEX_PATH):
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                idx = json.load(f)
        entries = idx.setdefault("entries", {})
        key = f"{kind}:reg:{int(time.time() * 1000)}"
        from .memory_score import score_entry
        entries[key] = {
            "layer": "L1",
            "source": kind,
            "importance": round(float(importance), 2),
            "used_n": 0,
            "pinned": bool(pinned),
            "score": score_entry(float(importance), 0, bool(pinned)),
            "last_used": "",
            "locator": f"{MEMORY_FILE if kind == 'memory' else USER_FILE}#new",
            "preview": content[:80],
        }
        idx.setdefault("stats", {})["L1"] = idx.get("stats", {}).get("L1", 0) + 1
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def init_index(verbose=True) -> dict:
    """扫描并生成索引（只读）。保留 register_entry 登记的 reg: 新条目。"""
    os.makedirs(MEMORIES_DIR, exist_ok=True)
    idx = build_index(MEMORY_FILE, USER_FILE, _facts_lookup())
    # 2026-08-14: 合并 register_entry 写入的 reg: 条目（文件扫描看不到它们）。
    # 孤儿清理：preview 不在对应源文件中的 reg: 条目 = 已被删除/替换的旧登记 → 丢弃，
    # 防止 memory 工具 remove/replace 后残留垃圾索引（实测积累了大量矛盾条目）。
    if os.path.isfile(INDEX_PATH):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                _old = json.load(f)
            _file_texts = {}
            for _k, _v in _old.get("entries", {}).items():
                if not _k.startswith(("memory:reg:", "user:reg:")):
                    continue
                if _k in idx["entries"]:
                    continue
                _src = "user" if _k.startswith("user:") else "memory"
                if _src not in _file_texts:
                    try:
                        with open(USER_FILE if _src == "user" else MEMORY_FILE,
                                  "r", encoding="utf-8") as _sf:
                            _file_texts[_src] = _sf.read()
                    except Exception:
                        _file_texts[_src] = ""
                _pv = str(_v.get("preview", ""))[:40]
                if _pv and _pv in _file_texts[_src]:
                    idx["entries"][_k] = _v
        except Exception:
            pass
    # 重算 stats
    _stats = {"L1": 0, "L2": 0, "L3": 0}
    for _v in idx["entries"].values():
        _stats[_v.get("layer", "L1")] = _stats.get(_v.get("layer", "L1"), 0) + 1
    idx["stats"] = _stats
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    if verbose:
        print(f"[MemoryGovernor] index 已生成: {INDEX_PATH}")
        print(f"[MemoryGovernor] 分层统计: L1={idx['stats']['L1']} "
              f"L2={idx['stats']['L2']} L3={idx['stats']['L3']}")
    return idx


def run_governance(dry_run: bool = True, verbose: bool = True) -> dict:
    """执行流转治理。返回 {moved_to_l2, moved_to_l3, kept_l1, report}。"""
    idx = build_index(MEMORY_FILE, USER_FILE, _facts_lookup())
    report = {"moved_to_l2": [], "moved_to_l3": [], "kept_l1": [], "dry_run": dry_run}
    if not dry_run:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # 2026-08-16: 按条目号降序处理 —— 替换条目为索引行会减少分隔符、重编号
    # 后续条目；从大到小处理保证低编号条目不受影响（升序会错位替换/归档）
    _sorted_keys = sorted(
        (k for k in idx["entries"].keys() if ":" in k and k.split(":")[1].isdigit()),
        key=lambda k: -int(k.split(":")[1]),
    )
    for key in _sorted_keys:
        ent = idx["entries"][key]
        # 2026-08-14 防御：reg: 等元数据登记键不是 "kind:int" 文件条目，
        # int() 会 ValueError 导致整个治理崩溃（孤儿清理后本应消失，双保险）
        _parts = key.split(":")
        if len(_parts) != 2 or not _parts[1].isdigit():
            continue
        kind, num = _parts
        path = USER_FILE if kind == "user" else MEMORY_FILE
        entries = _read_entries(path)
        if int(num) >= len(entries):
            continue
        entry_text = entries[int(num)]
        # 2026-08-14: legacy 条目（无元数据）只观察不迁移
        if ent["source"] == "legacy" or ent.get("src") == "legacy":
            report["kept_l1"].append(ent["preview"])
            continue
        if ent["pinned"] or ent["layer"] == "L1":
            # 2026-08-16: 补 L1→L2 下沉 —— 原实现永远保留 L1（L2/L3 恒 0），
            # L1 文件无限膨胀超 char 限额，每次新写入都触发 LLM consolidate 折腾。
            # 判据保守：score < 0.3 且未 pinned（用户铁律 importance≥0.8 →
            # score≥0.4 恒留 L1，不影响用户规则注入）。
            if (ent["layer"] == "L1" and not ent["pinned"]
                    and float(ent.get("score", 1.0) or 1.0) < 0.3):
                report["moved_to_l2"].append(ent["preview"])
                if not dry_run:
                    _sink_to_facts(entry_text, kind, ent)
                    _ent2 = dict(ent)
                    _ent2["layer"] = "L2"
                    _replace_entry_with_index_line(path, entry_text, _ent2)
            else:
                report["kept_l1"].append(ent["preview"])
            continue
        if ent["layer"] == "L2":
            report["moved_to_l2"].append(ent["preview"])
            if not dry_run:
                _sink_to_facts(entry_text, kind, ent)
                _replace_entry_with_index_line(path, entry_text, ent)
        elif ent["layer"] == "L3":
            report["moved_to_l3"].append(ent["preview"])
            if not dry_run:
                _archive_entry(entry_text, kind, ent)
                _replace_entry_with_index_line(path, entry_text, ent)

    # 重写索引（apply 后条目已迁移）
    if not dry_run:
        init_index(verbose=False)
    if verbose:
        print(f"[MemoryGovernor] {'DRY-RUN' if dry_run else 'APPLIED'}: "
              f"下沉L2={len(report['moved_to_l2'])} 归档L3={len(report['moved_to_l3'])} "
              f"保留L1={len(report['kept_l1'])}")
    return report


def _read_entries(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return parse_entries(f.read())
    except Exception:
        return []


def _sink_to_facts(entry_text: str, kind: str, ent: dict):
    """L2 下沉：写入 memory_store.db facts（holographic 检索注入）。"""
    try:
        import sqlite3
        db = os.path.join(os.path.dirname(MEMORIES_DIR), "memory_store.db")
        conn = sqlite3.connect(db, timeout=10)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO facts (content, category, tags, trust_score, retrieval_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (entry_text, "memory_governance", kind, ent["importance"], 0),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[MemoryGovernor] 下沉 facts 失败: {e}")


def _archive_entry(entry_text: str, kind: str, ent: dict):
    """L3 归档：append 到 archive/YYYY-MM.md（永不删除）。"""
    month = time.strftime("%Y-%m")
    path = os.path.join(ARCHIVE_DIR, f"{month}.md")
    header = f"\n---\n[{kind}] score={ent['score']} used={ent['used_n']} archived={time.strftime('%Y-%m-%d')}\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(header + entry_text + "\n")


def _replace_entry_with_index_line(path: str, entry_text: str, ent: dict):
    """把 L1 文件中的条目替换为一行索引（`[L2→fact]` 占位）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        locator = ent.get("locator", "")
        kind = "L2" if ent["layer"] == "L2" else "L3"
        line = f"[{kind}→外置] {ent['preview'][:50]} (score={ent['score']}, {locator})"
        new_text = text.replace(entry_text, line, 1)
        if new_text != text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
    except Exception as e:
        print(f"[MemoryGovernor] 替换索引行失败: {e}")
