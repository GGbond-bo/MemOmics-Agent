# -*- coding: utf-8 -*-
"""记忆治理 — 打分器（memory governance scoring）

2026-08-14 设计（docs/execution-and-memory-governance-plan-20260814.md）：
三层金字塔 L1(核心注入) / L2(外置 facts) / L3(归档)。
打分公式: score = 0.5×importance + 0.35×usage + 0.15×pinned
pinned=1 时保底 0.85（用户强调的一直保留）。
"""
from __future__ import annotations

import re
import time

# 条目元数据格式（写入 MEMORY.md/USER.md 条目首行，向后兼容：无元数据=旧条目）
META_RE = re.compile(r"^\[imp:([0-9.]+)\]\[used:([0-9]+)\]\[pinned:([01])\]\[src:(\w+)\]")

# 来源重要性启发（旧条目无元数据时按文件+关键词推断）
USER_FILE_BASE = 0.8      # USER.md 是用户偏好/纠正，天然重要
MEMORY_FILE_BASE = 0.55   # MEMORY.md 是 agent 笔记，中性起步
KEYWORD_BOOST = {
    "用户": 0.15, "纠正": 0.15, "偏好": 0.15, "要求": 0.15, "禁止": 0.15,
    "环境": 0.10, "路径": 0.10, "坑": 0.10, "失败": 0.10, "bug": 0.10,
    "确认": 0.05, "已验证": 0.05, "修复": 0.05,
    "临时": -0.15, "一次性": -0.15,
}


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def parse_meta(entry_text: str):
    """解析条目元数据行。返回 (imp, used_n, pinned, src) 或 None。"""
    first_line = entry_text.splitlines()[0].strip() if entry_text else ""
    m = META_RE.match(first_line)
    if not m:
        return None
    try:
        return (float(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4))
    except Exception:
        return None


def infer_importance(entry_text: str, kind: str) -> float:
    """无元数据的旧条目：按文件类型 + 关键词启发打分。"""
    base = USER_FILE_BASE if kind == "user" else MEMORY_FILE_BASE
    boost = 0.0
    for kw, delta in KEYWORD_BOOST.items():
        if kw in entry_text:
            boost += delta
    return clamp(base + boost, 0.1, 0.95)


def usage_score(used_n: int, last_used_ts: float = None) -> float:
    """使用程度 0-1：5 次命中即满；时间衰减 90 天 ×0.8、180 天 ×0.5。"""
    u = clamp(used_n / 5.0)
    if last_used_ts:
        days = (time.time() - last_used_ts) / 86400.0
        if days > 180:
            u *= 0.5
        elif days > 90:
            u *= 0.8
    return u


def score_entry(importance: float, used_n: int, pinned: bool = False,
                last_used_ts: float = None) -> float:
    """合成评分。pinned=1 保底 0.85（永不降级）。"""
    s = 0.5 * importance + 0.35 * usage_score(used_n, last_used_ts) + (0.15 if pinned else 0.0)
    if pinned:
        s = max(s, 0.85)
    return round(clamp(s), 3)


def decide_layer(score: float, pinned: bool, last_used_ts: float = None) -> str:
    """层流转判定：L1/L2/L3。"""
    if pinned:
        return "L1"
    days = None
    if last_used_ts:
        days = (time.time() - last_used_ts) / 86400.0
    if score >= 0.5 and (days is None or days < 90):
        return "L1"
    if score >= 0.3 and (days is None or days < 180):
        return "L2"
    return "L3"


def parse_entries(text: str) -> list:
    """按 § 切条目，去空。返回条目文本列表。

    2026-08-16: 跳过外置索引行（[L2→外置]/[L3→外置]）——它们是 L1→L2/L3
    迁移留下的占位符，不是真实记忆条目（此前被当条目 → 统计虚高 + 编号错位）。
    """
    parts = text.split("\n§\n")
    entries = []
    for p in parts:
        p = p.strip()
        # 跳过文件头（# Memory / <!-- --> 注释在第一个 § 之前）
        if p and not p.startswith("# ") and not p.startswith("<!--"):
            if p.startswith("[L2→外置]") or p.startswith("[L3→外置]"):
                continue
            entries.append(p)
    return entries


def build_index(memory_path: str, user_path: str, facts_lookup=None) -> dict:
    """扫描两个文件，构建 index.json 结构（facts_lookup: entry_text→(used_n,last_ts)）。"""
    entries = {}
    for kind, path in (("memory", memory_path), ("user", user_path)):
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue
        body = text.split("\n§\n", 1)[-1] if "\n§\n" in text else text
        for i, ent in enumerate(parse_entries(text)):
            meta = parse_meta(ent)
            if meta:
                imp, used, pinned, src = meta
                content = "\n".join(ent.splitlines()[1:]).strip() if "\n" in ent else ent
            else:
                imp = infer_importance(ent, kind)
                used, pinned, src = 0, False, "legacy"
                content = ent
            last_ts = None
            if facts_lookup:
                f = facts_lookup(content[:120])
                if f:
                    used, last_ts = f
            score = score_entry(imp, used, pinned, last_ts)
            # 2026-08-14 保守策略：legacy 条目（无元数据）只打分进观察期，暂留 L1；
            # 流转只对带元数据的新条目生效（渐进治理，不突然下沉历史记忆）。
            if src == "legacy":
                layer = "L1"
            else:
                layer = decide_layer(score, pinned, last_ts)
            key = f"{kind}:{i}"
            entries[key] = {
                "layer": layer,
                "source": kind,
                "importance": round(imp, 2),
                "used_n": used,
                "pinned": bool(pinned),
                "score": score,
                "last_used": time.strftime("%Y-%m-%d", time.localtime(last_ts)) if last_ts else "",
                "locator": f"{path}#entry{i}",
                "preview": content[:80],
            }
    stats = {"L1": 0, "L2": 0, "L3": 0}
    for v in entries.values():
        stats[v["layer"]] += 1
    return {"version": 1, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "entries": entries, "stats": stats}
