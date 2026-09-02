# -*- coding: utf-8 -*-
"""PRISMA 系统综述流程记账（Mode C，2026-08-25）。

背景：literature-review 的 Mode A（叙述综述）与 Mode B（库内综述）已覆盖探索性
综述；系统综述（Systematic Review）需要协议化、可复现的流程账——识别→去重→
标题/摘要筛选→全文资格→纳入，每一步的计数与排除原因都要留痕，最终产出
PRISMA 流程图数据（发综述论文的必需物）。

本模块 = PRISMA 流程的"记账本"（results/<sid>/review/prisma.json）：
  - stages: identified → deduplicated → screened → fulltext → eligible → included
  - exclusions: 排除原因分布（duplicate/title_abstract/fulltext/language/no_data/other）
  - screening: 逐篇筛选记录（doi/title → include/exclude + reason + stage）
  - search_log: 多库检索记录（database/query/date/hits）——可复现性
  - protocol: PICOS + 纳入/排除标准（init 时写入）

设计原则（沿用 evidence_table 同款）：
  - JSON 真相源 + 原子写（mkstemp+rename）+ RLock 并发安全
  - 幂等：同 stage 计数 set 语义、同 (doi,stage) 筛选记录去重
  - status 自动生成 mermaid 流程图（PRISMA 标准样式），export 落盘 md

工具注册：prisma_flow(mode=init|stage|screen|search|exclude|status|export)。
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger("memomics.prisma_flow")

# PRISMA 阶段（顺序即流程顺序）
STAGES = ("identified", "deduplicated", "screened", "fulltext", "eligible", "included")
STAGE_LABELS = {
    "identified": "识别（数据库检索）",
    "deduplicated": "去重后",
    "screened": "标题/摘要筛选",
    "fulltext": "全文资格评估",
    "eligible": "合格（定性综合）",
    "included": "纳入（定量综合）",
}
EXCLUSION_CATEGORIES = ("duplicate", "title_abstract", "fulltext", "language",
                        "no_data", "irrelevant", "other")
EXCLUSION_LABELS = {
    "duplicate": "重复",
    "title_abstract": "标题/摘要不符",
    "fulltext": "全文不符",
    "language": "语言不符",
    "no_data": "无可用数据",
    "irrelevant": "主题无关",
    "other": "其他",
}
SCREEN_DECISIONS = ("include", "exclude")

_LOCK = threading.RLock()


# ── 路径与 IO ───────────────────────────────────────────────────────────────

def prisma_dir(results_dir: str) -> str:
    return os.path.join(results_dir or "", "review")


def prisma_path(results_dir: str) -> str:
    return os.path.join(prisma_dir(results_dir), "prisma.json")


def _empty_state() -> dict:
    return {
        "schema_version": 1,
        "created_at": "",
        "updated_at": "",
        "protocol": {"picot": "", "inclusion": [], "exclusion": [], "databases": []},
        "stages": {s: 0 for s in STAGES},
        "exclusions": {c: 0 for c in EXCLUSION_CATEGORIES},
        "screening": [],
        "search_log": [],
    }


def _load(results_dir: str) -> dict:
    p = prisma_path(results_dir)
    if not os.path.isfile(p):
        return _empty_state()
    try:
        with open(p, "r", encoding="utf-8") as f:
            st = json.load(f)
        for s in STAGES:
            st.setdefault("stages", {}).setdefault(s, 0)
        for c in EXCLUSION_CATEGORIES:
            st.setdefault("exclusions", {}).setdefault(c, 0)
        st.setdefault("screening", [])
        st.setdefault("search_log", [])
        st.setdefault("protocol", {"picot": "", "inclusion": [], "exclusion": [], "databases": []})
        return st
    except Exception:
        logger.warning("[Prisma] 读取失败，按空状态处理", exc_info=True)
        return _empty_state()


def _save(results_dir: str, st: dict) -> bool:
    _fd = None
    try:
        os.makedirs(prisma_dir(results_dir), exist_ok=True)
        st["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _fd, tmp = tempfile.mkstemp(prefix="prisma.", suffix=".tmp", dir=prisma_dir(results_dir))
        with os.fdopen(_fd, "w", encoding="utf-8") as f:
            _fd = None
            json.dump(st, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        target = prisma_path(results_dir)
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
        logger.warning("[Prisma] 写入失败", exc_info=True)
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


# ── 核心操作 ────────────────────────────────────────────────────────────────

def init_prisma(results_dir: str, *, picot: str = "", inclusion: list = None,
                exclusion: list = None, databases: list = None) -> str:
    """初始化系统综述协议（幂等：已存在则只补 protocol 字段）。"""
    if not results_dir:
        return json.dumps({"ok": False, "error": "results_dir 为空"}, ensure_ascii=False)
    with _LOCK:
        st = _load(results_dir)
        if not st.get("created_at"):
            st["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if picot:
            st["protocol"]["picot"] = str(picot)[:500]
        if inclusion:
            st["protocol"]["inclusion"] = [str(x)[:200] for x in inclusion][:20]
        if exclusion:
            st["protocol"]["exclusion"] = [str(x)[:200] for x in exclusion][:20]
        if databases:
            st["protocol"]["databases"] = [str(x)[:100] for x in databases][:20]
        ok = _save(results_dir, st)
    return json.dumps({"ok": ok, "protocol": st["protocol"]}, ensure_ascii=False)


def update_stage(results_dir: str, stage: str, count: int,
                 mode: str = "set") -> str:
    """更新阶段计数。mode=set 直接设值（默认）；mode=add 累加。"""
    if stage not in STAGES:
        return json.dumps({"ok": False, "error": f"未知阶段 {stage}，可选 {STAGES}"},
                          ensure_ascii=False)
    try:
        count = max(0, int(count))
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": f"count 非法: {count!r}"}, ensure_ascii=False)
    with _LOCK:
        st = _load(results_dir)
        if not st.get("created_at"):
            st["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if mode == "add":
            st["stages"][stage] += count
        else:
            st["stages"][stage] = count
        ok = _save(results_dir, st)
    return json.dumps({"ok": ok, "stage": stage, "count": st["stages"][stage]},
                      ensure_ascii=False)


def record_exclusion(results_dir: str, category: str, count: int = 1) -> str:
    """记录排除原因（累计）。category ∈ duplicate/title_abstract/fulltext/language/no_data/irrelevant/other。"""
    if category not in EXCLUSION_CATEGORIES:
        return json.dumps({"ok": False,
                           "error": f"未知排除原因 {category}，可选 {EXCLUSION_CATEGORIES}"},
                          ensure_ascii=False)
    try:
        count = max(0, int(count))
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": f"count 非法: {count!r}"}, ensure_ascii=False)
    with _LOCK:
        st = _load(results_dir)
        st["exclusions"][category] += count
        ok = _save(results_dir, st)
    return json.dumps({"ok": ok, "category": category,
                       "count": st["exclusions"][category]}, ensure_ascii=False)


def record_screening(results_dir: str, doi_or_title: str, decision: str,
                     reason: str = "", stage: str = "title_abstract") -> str:
    """逐篇筛选记录（幂等：同 doi_or_title+stage 更新而非追加）。

    stage ∈ title_abstract（标题/摘要筛选）/ fulltext（全文资格评估）。
    """
    key = (doi_or_title or "").strip()
    if not key:
        return json.dumps({"ok": False, "error": "doi_or_title 为空"}, ensure_ascii=False)
    if decision not in SCREEN_DECISIONS:
        return json.dumps({"ok": False, "error": f"decision 必须是 include/exclude"},
                          ensure_ascii=False)
    if stage not in ("title_abstract", "fulltext"):
        return json.dumps({"ok": False, "error": "stage 必须是 title_abstract/fulltext"},
                          ensure_ascii=False)
    rec = {
        "item": key[:300],
        "decision": decision,
        "reason": (reason or "")[:200],
        "stage": stage,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with _LOCK:
        st = _load(results_dir)
        for i, r in enumerate(st["screening"]):
            if r.get("item") == key and r.get("stage") == stage:
                st["screening"][i] = rec
                break
        else:
            st["screening"].append(rec)
        st["screening"] = st["screening"][-5000:]  # 上限防爆
        ok = _save(results_dir, st)
    return json.dumps({"ok": ok, "updated": True, "total": len(st["screening"])},
                      ensure_ascii=False)


def record_search(results_dir: str, database: str, query: str,
                  hits: int, date: str = "") -> str:
    """记录一次数据库检索（可复现性）。"""
    if not database:
        return json.dumps({"ok": False, "error": "database 为空"}, ensure_ascii=False)
    try:
        hits = max(0, int(hits))
    except (TypeError, ValueError):
        hits = 0
    with _LOCK:
        st = _load(results_dir)
        st["search_log"].append({
            "database": str(database)[:100],
            "query": str(query)[:300],
            "hits": hits,
            "date": (date or datetime.now().strftime("%Y-%m-%d"))[:20],
        })
        st["search_log"] = st["search_log"][-100:]
        ok = _save(results_dir, st)
    return json.dumps({"ok": ok, "searches": len(st["search_log"])}, ensure_ascii=False)


# ── 状态与导出 ──────────────────────────────────────────────────────────────

def _mermaid(st: dict) -> str:
    """PRISMA 标准流程图（mermaid）。排除数按阶段差计算：
    标题/摘要排除 = deduplicated − screened；全文排除 = fulltext − eligible。"""
    s = st["stages"]
    ex = st["exclusions"]
    n_ident = s.get("identified", 0)
    n_dedup = s.get("deduplicated", 0)
    n_scr = s.get("screened", 0)
    n_ft = s.get("fulltext", 0)
    n_elig = s.get("eligible", 0)
    n_inc = s.get("included", 0)
    excl_scr = max(0, n_dedup - n_scr)
    excl_ft = max(0, n_ft - n_elig)
    dup = ex.get("duplicate", 0)
    lines = [
        "flowchart TD",
        f'  A["识别: 数据库检索 (n={n_ident})"] --> B["去重后 (n={n_dedup})"]',
        f'  B --> C["标题/摘要筛选 (n={n_scr})"]',
        f'  C -->|"排除 {excl_scr}（去重 {dup} + 其他）"| X1["排除"]',
        f'  C --> D["全文资格评估 (n={n_ft})"]',
        f'  D -->|"排除 {excl_ft}"| X2["排除"]',
        f'  D --> E["纳入: 定性综合 (n={n_inc})"]',
    ]
    return "\n".join(lines)


def prisma_status(results_dir: str) -> str:
    """当前 PRISMA 状态：阶段计数 + 排除原因分布 + 筛选统计 + mermaid 图。"""
    with _LOCK:
        st = _load(results_dir)
    s = st["stages"]
    ex = st["exclusions"]
    scr = st["screening"]
    n_inc_scr = sum(1 for r in scr if r.get("decision") == "include")
    n_exc_scr = sum(1 for r in scr if r.get("decision") == "exclude")
    return json.dumps({
        "ok": True,
        "stages": s,
        "exclusions": ex,
        "screening_total": len(scr),
        "screening_include": n_inc_scr,
        "screening_exclude": n_exc_scr,
        "searches": len(st["search_log"]),
        "protocol": st["protocol"],
        "mermaid": _mermaid(st),
    }, ensure_ascii=False)


def export_prisma(results_dir: str, path: str = "") -> str:
    """导出 PRISMA 报告（markdown：协议/检索记录/流程表格/排除原因/mermaid 图）。"""
    with _LOCK:
        st = _load(results_dir)
    if not path:
        path = os.path.join(prisma_dir(results_dir), "prisma_report.md")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        s = st["stages"]
        ex = st["exclusions"]
        lines = ["# PRISMA 系统综述流程报告",
                 f"> 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                 "",
                 "## 协议（Protocol）",
                 f"- PICOS: {st['protocol'].get('picot') or '(未填)'}",
                 f"- 纳入标准: {('; '.join(st['protocol'].get('inclusion') or []) ) or '(未填)'}",
                 f"- 排除标准: {('; '.join(st['protocol'].get('exclusion') or []) ) or '(未填)'}",
                 f"- 数据库: {(', '.join(st['protocol'].get('databases') or [])) or '(未填)'}",
                 "",
                 "## 检索记录（可复现）",
                 ]
        for r in st["search_log"]:
            lines.append(f"- [{r['date']}] {r['database']}: `{r['query']}` → {r['hits']} 条")
        lines += ["", "## 流程计数", "", "| 阶段 | 计数 |", "| --- | --- |"]
        for sname in STAGES:
            lines.append(f"| {STAGE_LABELS[sname]} | {s.get(sname, 0)} |")
        lines += ["", "## 排除原因分布", "", "| 原因 | 计数 |", "| --- | --- |"]
        for c in EXCLUSION_CATEGORIES:
            lines.append(f"| {EXCLUSION_LABELS[c]} | {ex.get(c, 0)} |")
        if st["screening"]:
            lines += ["", "## 筛选记录", "", "| 文献 | 决定 | 阶段 | 原因 |", "| --- | --- | --- | --- |"]
            for r in st["screening"][-200:]:
                lines.append(f"| {r['item'][:60]} | {r['decision']} | {r['stage']} | {r['reason'][:60]} |")
        lines += ["", "## PRISMA 流程图", "", "```mermaid", _mermaid(st), "```", ""]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return json.dumps({"ok": True, "path": path.replace("\\", "/"),
                           "included": s.get("included", 0)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


# ── 工具注册 ────────────────────────────────────────────────────────────────

FLOW_SCHEMA = {
    "name": "prisma_flow",
    "description": (
        "PRISMA 系统综述流程记账（Mode C）：mode=init 初始化协议（PICOS/纳入排除/"
        "数据库）；mode=stage 更新阶段计数（identified/deduplicated/screened/fulltext/"
        "eligible/included，set 或 add）；mode=screen 逐篇记录筛选决定（include/exclude"
        "+原因+阶段）；mode=search 记录检索式（库/query/命中数，可复现）；"
        "mode=exclude 累计排除原因（duplicate/title_abstract/fulltext/language/no_data/"
        "irrelevant/other）；mode=status 查看流程状态（含 mermaid 流程图）；"
        "mode=export 导出 PRISMA 报告 md。系统综述每个环节都必须记账，最终交付含"
        "流程图。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "description": "init|stage|screen|search|exclude|status|export"},
            "stage": {"type": "string", "description": "stage 模式：identified/deduplicated/screened/fulltext/eligible/included"},
            "count": {"type": "integer", "description": "stage/exclude 模式的计数（stage 默认 set，可传 mode=add 累加）"},
            "set_or_add": {"type": "string", "description": "stage 模式：set（默认，直接设值）或 add（累加）"},
            "category": {"type": "string", "description": "exclude 模式：排除原因分类"},
            "item": {"type": "string", "description": "screen 模式：文献 DOI 或标题"},
            "decision": {"type": "string", "description": "screen 模式：include/exclude"},
            "reason": {"type": "string", "description": "screen 模式：排除/纳入原因"},
            "screen_stage": {"type": "string", "description": "screen 模式：title_abstract（默认）/fulltext"},
            "database": {"type": "string", "description": "search 模式：数据库名（PubMed/EuropePMC/Embase…）"},
            "query": {"type": "string", "description": "search 模式：完整检索式"},
            "hits": {"type": "integer", "description": "search 模式：命中数"},
            "date": {"type": "string", "description": "search 模式：检索日期（默认今天）"},
            "picot": {"type": "string", "description": "init 模式：PICOS 问题陈述"},
            "inclusion": {"type": "array", "items": {"type": "string"}, "description": "init 模式：纳入标准列表"},
            "exclusion": {"type": "array", "items": {"type": "string"}, "description": "init 模式：排除标准列表"},
            "databases": {"type": "array", "items": {"type": "string"}, "description": "init 模式：数据库列表"},
        },
        "required": ["mode"]
    }
}


def _flow_handler(results_dir: str, args: dict) -> str:
    mode = str(args.get("mode") or "status")
    if mode == "init":
        return init_prisma(results_dir, picot=args.get("picot", ""),
                           inclusion=args.get("inclusion"), exclusion=args.get("exclusion"),
                           databases=args.get("databases"))
    if mode == "stage":
        return update_stage(results_dir, args.get("stage", ""),
                            args.get("count", 0), mode=str(args.get("set_or_add") or "set"))
    if mode == "screen":
        return record_screening(results_dir, args.get("item", ""),
                                args.get("decision", ""), reason=args.get("reason", ""),
                                stage=str(args.get("screen_stage") or "title_abstract"))
    if mode == "search":
        return record_search(results_dir, args.get("database", ""),
                             args.get("query", ""), args.get("hits", 0), date=args.get("date", ""))
    if mode == "exclude":
        return record_exclusion(results_dir, args.get("category", ""),
                                args.get("count", 1))
    if mode == "export":
        return export_prisma(results_dir, args.get("path", ""))
    return prisma_status(results_dir)


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="prisma_flow",
            toolset="memomics",
            schema=FLOW_SCHEMA,
            handler=lambda args, **kw: _flow_handler(
                kw.get("results_dir", "") or os.environ.get("MEMOMICS_RESULTS_DIR", ""), args),
            emoji="📊",
            max_result_size_chars=12_000,
        )
    except Exception as e:
        logger.warning(f"prisma flow register failed: {e}")


_register()
