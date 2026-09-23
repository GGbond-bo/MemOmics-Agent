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
import re
import shutil
import time

from .memory_score import (build_index, parse_entries, parse_meta, score_entry,
                           decide_layer)

MEMORIES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "hermes_home", "memories")
INDEX_PATH = os.path.join(MEMORIES_DIR, "index.json")
ARCHIVE_DIR = os.path.join(MEMORIES_DIR, "archive")
MEMORY_FILE = os.path.join(MEMORIES_DIR, "MEMORY.md")
USER_FILE = os.path.join(MEMORIES_DIR, "USER.md")
BACKUP_DIR = os.path.join(MEMORIES_DIR, ".backup")

# 2026-09-24: 条目自称的低价值标注（内容前缀，不是 META_RE 元数据）。
# 实测本机 219 条里，全部分数落在 0.325~0.475，L1→L2 的 score<0.3 规则永远不触发
# → 治理永远搬不动东西，而记忆文件已经 98% 满。所以补一条"按自知重要性归档"的通道：
# 只归档 agent 自己在条目开头写了 [imp:0.6]/[imp:0.7] 的条目（它自己都标了低价值）。
_INLINE_IMP_RE = re.compile(r"^\[imp:([0-9.]+)\]")
# 单次归档不得超过条目总数的 60%：防参数写错一次把记忆掏空（要越过得显式 force）
MAX_ARCHIVE_RATIO = 0.6
# 归档一条至少得真腾出这么多字符，否则不动（索引行本身也要占地方：
# 短条目换索引行反而会变长 —— 治理的目的是腾空间，腾不出来就别碰）
MIN_FREE_GAIN = 40


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
    # 重算 stats —— 2026-09-24: 只数 "kind:int" 的真实文件条目。
    # 老实现把所有键都算进去，把 50 个 user:reg:*/memory:reg:* 登记键也算成记忆条目
    # （真机 200 条记忆显示成 250 条），面板上的"分层统计"因此虚高，属于误导性数字。
    _stats = {"L1": 0, "L2": 0, "L3": 0}
    _other = 0
    for _k, _v in idx["entries"].items():
        _p = _k.split(":")
        if len(_p) == 2 and _p[1].isdigit():
            _stats[_v.get("layer", "L1")] = _stats.get(_v.get("layer", "L1"), 0) + 1
        else:
            _other += 1
    idx["stats"] = _stats
    idx["stats_other_keys"] = _other
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
# ---------------------------------------------------------------------------
# 2026-09-24 追加：体检（只读）+ 按"自知重要性"归档（真腾地方、永不删除内容）
#
# 背景（真机实测）：run_governance 的唯一流转判据是 score<0.3，而本机 219 条记忆
# 分数全在 0.325~0.475 → 0 条达标 → 治理点了等于没点；同时 MEMORY.md 已 29530/30000
# 字符，写什么都顶格。这里补一条显式、可解释、可回滚的通道。
# ---------------------------------------------------------------------------


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def inline_importance(entry_text):
    """条目开头的 [imp:x] 自称重要性；带正式元数据或没标 → None。

    为什么排掉带 META_RE 元数据的条目：那些归 run_governance 管（有 pinned 保底），
    两条通道各管一段，避免"用户铁律被人肉标了低分"被误归档。
    """
    text = (entry_text or "").strip()
    if not text:
        return None
    if parse_meta(text):
        return None
    m = _INLINE_IMP_RE.match(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _index_line(ent_text, imp, kind, archive_name):
    """归档后留在原文件里的一行索引（前缀必须是 [L3→外置]，parse_entries 会跳过它）。

    刻意写短：它是留着占地方的成本，摘要 36 字够 agent 知道"这条在归档里"，要细节
    就去读 archive/<月>.md（那里一字不少）。
    """
    summary = " ".join(ent_text.split())[:36]
    return "[L3→外置] imp=%s %s (%s)" % (imp, summary, archive_name)


def survey(threshold=0.7, limits=None):
    """只读体检：占用/余量、分层统计、分数分布、可归档候选、预计释放字符。零改动。"""
    limits = limits or {}
    archive_name = time.strftime("%Y-%m") + ".md"
    files, candidates = {}, []
    total_entries = 0
    skipped_short = 0
    for kind, path in (("memory", MEMORY_FILE), ("user", USER_FILE)):
        name = os.path.basename(path)
        text = _read_text(path)
        entries = parse_entries(text)
        total_entries += len(entries)
        limit = limits.get(name) or 0
        files[name] = {
            "chars": len(text),
            "entries": len(entries),
            "limit": limit,
            "pct": round(100.0 * len(text) / limit, 1) if limit else None,
            "headroom": (limit - len(text)) if limit else None,
        }
        for i, ent in enumerate(entries):
            imp = inline_importance(ent)
            if imp is None or imp > threshold + 1e-9:
                continue
            line = _index_line(ent, imp, kind, archive_name)
            if len(ent) - len(line) < MIN_FREE_GAIN:
                skipped_short += 1
                continue
            candidates.append({
                "target": name,
                "index": i,
                "imp": imp,
                "chars": len(ent),
                "freed": max(0, len(ent) - len(line)),
                "preview": " ".join(ent.split())[:80],
            })
    idx = build_index(MEMORY_FILE, USER_FILE, _facts_lookup())
    scores = sorted(float(v.get("score", 0.0) or 0.0) for v in idx["entries"].values())
    freed = sum(c["freed"] for c in candidates)
    ratio = (len(candidates) / float(total_entries)) if total_entries else 0.0
    return {
        "threshold": threshold,
        "files": files,
        "layers": idx.get("stats", {}),
        "total_entries": total_entries,
        "score": {
            "min": scores[0] if scores else None,
            "median": scores[len(scores) // 2] if scores else None,
            "max": scores[-1] if scores else None,
            "below_0_3": sum(1 for s in scores if s < 0.3),
        },
        "candidates": candidates,
        "skipped_too_short": skipped_short,
        "min_free_gain": MIN_FREE_GAIN,
        "freed_estimate": freed,
        "guard": {"ratio": round(ratio, 3), "limit": MAX_ARCHIVE_RATIO,
                  "ok": ratio <= MAX_ARCHIVE_RATIO or not candidates},
        "note": ("L1→L2 自动下沉需要 score<0.3，当前达标 %d 条"
                 % sum(1 for s in scores if s < 0.3)),
    }


def _backup_files(ts):
    """整档备份 MEMORY.md / USER.md / index.json 到 memories/.backup/<ts>/。"""
    dest = os.path.join(BACKUP_DIR, ts)
    os.makedirs(dest, exist_ok=True)
    for path in (MEMORY_FILE, USER_FILE, INDEX_PATH):
        if os.path.isfile(path):
            shutil.copy2(path, os.path.join(dest, os.path.basename(path)))
    return dest


def archive_low_value(threshold=0.7, dry_run=True, limits=None, force=False):
    """把"自己标了低价值"的条目归档到 archive/YYYY-MM.md，并在原文件留一行索引。

    - dry_run=True（默认）：只出报告，一个字节都不写。
    - apply：先整档备份到 memories/.backup/<ts>/，再归档；内容永不删除（archive 只增）。
    - 单次归档超过条目总数 60% 时拒绝执行（要显式 force=True）。
    返回 {ok, dry_run, threshold, archived, freed, before, after, backup, ...}
    """
    limits = limits or {}
    sv = survey(threshold, limits)
    cands = sv["candidates"]
    total = sv["total_entries"]
    report = {
        "ok": True, "dry_run": bool(dry_run), "threshold": threshold,
        "archived": list(cands), "freed": sv["freed_estimate"],
        "before": {k: v["chars"] for k, v in sv["files"].items()},
        "after": {}, "backup": None, "guard": sv["guard"],
        "archive_file": os.path.join(ARCHIVE_DIR, time.strftime("%Y-%m") + ".md"),
        # 体检字段整包带上：面板一次请求就能画占用条 + 候选清单 + 分层，
        # 不用再打第二个接口（真机踩过：接口只回 archived，面板读 candidates 显示"0 条"）
        "files": sv["files"], "layers": sv["layers"], "score": sv["score"],
        "total_entries": sv["total_entries"], "candidates": list(cands),
        "freed_estimate": sv["freed_estimate"],
        "skipped_too_short": sv["skipped_too_short"],
        "min_free_gain": sv["min_free_gain"], "note": sv["note"],
    }
    if not cands:
        report["after"] = dict(report["before"])
        report["note"] = "没有可归档条目（严格小于等于阈值的 [imp:x] 条目）"
        return report
    if not sv["guard"]["ok"] and not force:
        report["ok"] = False
        report["guard_blocked"] = True
        report["note"] = ("候选占 %.0f%% > 上限 %.0f%%，已拒绝执行（确认无误会重跑并带 force）"
                          % (100.0 * sv["guard"]["ratio"], 100.0 * MAX_ARCHIVE_RATIO))
        report["after"] = dict(report["before"])
        return report
    if dry_run:
        report["after"] = {
            k: v["chars"] - sum(c["freed"] for c in cands if c["target"] == k)
            for k, v in sv["files"].items()
        }
        return report

    # ---- apply ----
    report["backup"] = _backup_files(time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    by_target = {}
    for c in cands:
        by_target.setdefault(c["target"], []).append(c)
    for kind, path in (("memory", MEMORY_FILE), ("user", USER_FILE)):
        name = os.path.basename(path)
        picks = by_target.get(name)
        if not picks:
            continue
        text = _read_text(path)
        news = text
        for c in picks:
            ent = None
            for e in parse_entries(text):
                if (" ".join(e.split())[:80] == c["preview"]):
                    ent = e
                    break
            if ent is None:
                continue
            with open(report["archive_file"], "a", encoding="utf-8") as f:
                f.write("\n---\n[%s] imp=%s archived=%s threshold=%s\n%s\n"
                        % (kind, c["imp"], stamp, threshold, ent))
            news = news.replace(ent, _index_line(
                ent, c["imp"], kind, os.path.basename(report["archive_file"])), 1)
        if news != text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(news)
    init_index(verbose=False)
    report["after"] = {name: len(_read_text(os.path.join(MEMORIES_DIR, name)))
                       for name in report["before"]}
    report["freed"] = sum(max(0, report["before"][k] - report["after"][k])
                          for k in report["before"])
    return report


# ---------------------------------------------------------------------------
# 2026-09-24 追加：条目清单（只读）+ 删除单条记忆（用户显式操作）
#
# 用户要求"记忆支持删除"：面板里逐条可见、逐条可删。删是真删，所以先备份 + 前端二次确认。
# ---------------------------------------------------------------------------


def _entry_files():
    return (("MEMORY.md", MEMORY_FILE), ("USER.md", USER_FILE))


def list_entries(preview_chars=100):
    """给面板用的条目清单（只读）：序号、字符数、自称重要性、pinned、预览。"""
    out = {}
    for name, path in _entry_files():
        text = _read_text(path)
        items = []
        for i, ent in enumerate(parse_entries(text)):
            meta = parse_meta(ent) or {}
            items.append({
                "index": i,
                "chars": len(ent),
                "imp": inline_importance(ent),
                "pinned": (1 if meta.get("pinned") else 0) if meta else None,
                "preview": " ".join(ent.split())[:preview_chars],
            })
        out[name] = {"path": path, "count": len(items), "items": items}
    return out


def delete_entry(target, index, backup=True):
    """删掉 target 里第 index 条记忆（用户点的删除 —— 含铁律，想删就删）。

    安全约定：先整档备份到 memories/.backup/<ts>/；未知文件 / 序号越界 / 条目定位失败
    一律**不改动任何字节**。与"归档"不同，这是真删（archive/ 里的历史不受影响）。
    """
    name = os.path.basename(str(target or "").strip())
    paths = dict(_entry_files())
    if name not in paths:
        return {"ok": False, "error": "未知记忆文件: %s（只支持 MEMORY.md / USER.md）" % target}
    path = paths[name]
    if not os.path.isfile(path):
        return {"ok": False, "error": "记忆文件不存在: %s" % name}
    text = _read_text(path)
    entries = parse_entries(text)
    try:
        i = int(index)
    except Exception:
        return {"ok": False, "error": "条目序号非法: %r" % (index,)}
    if i < 0 or i >= len(entries):
        return {"ok": False, "error": "条目序号越界: %d（当前共 %d 条）" % (i, len(entries))}
    ent = entries[i]
    before = len(text)
    # 连分隔符一起删，避免留下空的 § 块（空块会被 parse_entries 当成一条空记忆）
    if ("\n§\n" + ent) in text:
        news = text.replace("\n§\n" + ent, "", 1)
    elif (ent + "\n§\n") in text:
        news = text.replace(ent + "\n§\n", "", 1)
    else:
        news = text.replace(ent, "", 1)
    if news and not news.endswith("\n"):
        news += "\n"
    if news == text:
        return {"ok": False, "error": "条目定位失败，未改动任何内容"}
    bdir = _backup_files(time.strftime("%Y%m%d-%H%M%S")) if backup else None
    with open(path, "w", encoding="utf-8") as f:
        f.write(news)
    init_index(verbose=False)
    return {"ok": True, "target": name, "index": i,
            "removed": " ".join(ent.split())[:80], "removed_chars": len(ent),
            "before": {"chars": before, "count": len(entries)},
            "after": {"chars": len(news), "count": len(parse_entries(news))},
            "freed": max(0, before - len(news)), "backup": bdir}

