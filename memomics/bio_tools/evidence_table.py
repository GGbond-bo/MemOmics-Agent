# -*- coding: utf-8 -*-
"""文献证据表（evidence table）—— 上百篇文献综述的聚合真相源。

背景（2026-08-25）：MemOmics 单篇文献有 papers/knowledge 卡片 + 摘要 + DOI 索引，
但"跨 100 篇的证据综合"没有结构化载体——综述时模型只能现读卡片，既慢又容易
撞上下文墙。本模块提供"证据表"：一行 = 一条"结论↔来源"证据（DOI/结论/方法/
物种/方向/支持强度），JSONL 为真相源（字段丰富、追加原子写），CSV 供人看。

设计原则（沿用本仓库既有教训）：
- 文件系统是真相：evidence.jsonl 落盘，不塞上下文；查询/导出按需取
- 原子写 + 进程内锁：并发写不损坏（run_gate 同款：mkstemp + rename + RLock）
- 幂等去重：同 (doi, claim) 重复写入 = 更新而非追加
- 引用校验：verify_citations 从综述文本提取 DOI/PMID，对照证据表 + papers 索引
  返回缺失列表——防幻觉引用（literature-review 技能铁律的代码化）

工具注册：evidence_write（写一行）/ evidence_query（mode=query|export|stats|verify）。
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("memomics.evidence_table")

# 与 literature_library 对齐的 DOI 提取（含去垃圾）
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
_DOI_JUNK = ("wileyonlinelibrary", "sciencedirect", "tandfonline", "onlinelibrary",
             "doi.org", "dx.doi.org", "crossref", "pubmed", "scholar")
PMID_RE = re.compile(r"\bPMID[:\s]*(\d{5,9})\b", re.IGNORECASE)

STRENGTHS = ("strong", "moderate", "weak", "conflict")
_DEFAULT_STRENGTH = "moderate"

_LOCK = threading.RLock()  # 进程内读写互斥（并发写不损坏）


# ── 路径与原子 IO ───────────────────────────────────────────────────────────

def evidence_dir(results_dir: str) -> str:
    return os.path.join(results_dir or "", "review")


def evidence_path(results_dir: str) -> str:
    return os.path.join(evidence_dir(results_dir), "evidence.jsonl")


def _append_jsonl(path: str, payload: dict) -> bool:
    """追加一行（原子：写临时文件再 rename 合并——JSONL 追加用独立 tmp 避免
    读-改-写竞态，直接 append 模式 + fsync 即可，rename 兜底跨进程）。"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return True
    except Exception:
        logger.warning("[EvidenceTable] 写入失败", exc_info=True)
        return False


def _rewrite_jsonl(path: str, rows: list) -> bool:
    """整表重写（原子：mkstemp + rename）。"""
    _fd = None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _fd, tmp = tempfile.mkstemp(prefix="evidence.", suffix=".tmp", dir=os.path.dirname(path))
        with os.fdopen(_fd, "w", encoding="utf-8") as f:
            _fd = None
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        target = path
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
        logger.warning("[EvidenceTable] 重写失败", exc_info=True)
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


def _load_rows(results_dir: str) -> list:
    """读全部证据行（文件缺失 → []）。"""
    p = evidence_path(results_dir)
    if not os.path.isfile(p):
        return []
    rows = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("[EvidenceTable] 跳过损坏行: %s", line[:80])
    except Exception:
        logger.warning("[EvidenceTable] 读取失败", exc_info=True)
    return rows


# ── 核心操作 ────────────────────────────────────────────────────────────────

def _norm_doi(raw: str) -> str:
    """规范化 DOI：去空白/URL 前缀/垃圾后缀；非 DOI 格式返回空（无效）。"""
    doi = (raw or "").strip()
    for _p in ("https://doi.org/", "http://doi.org/", "doi:", "DOI:"):
        if doi.lower().startswith(_p.lower()):
            doi = doi[len(_p):].strip()
    if doi.lower().startswith("10."):
        m = DOI_RE.search(doi)
        if m:
            doi = m.group(0)
        else:
            return ""
    else:
        return ""  # 不是 10.xxxx/ 格式 → 无效
    if any(j in doi.lower() for j in _DOI_JUNK):
        return ""
    return doi


def write_evidence_row(results_dir: str, doi: str, claim: str, *,
                       method: str = "", species: str = "", tissue: str = "",
                       direction: str = "", strength: str = _DEFAULT_STRENGTH,
                       title: str = "", pmid: str = "", source: str = "",
                       note: str = "", added_by: str = "") -> str:
    """写入一条证据（同 doi+claim 幂等更新）。返回 JSON 结果。"""
    claim = (claim or "").strip()
    if not claim:
        return json.dumps({"ok": False, "error": "claim 不能为空"}, ensure_ascii=False)
    doi_n = _norm_doi(doi)
    if not doi_n:
        return json.dumps({"ok": False, "error": f"DOI 无效: {doi!r}"}, ensure_ascii=False)
    if strength not in STRENGTHS:
        strength = _DEFAULT_STRENGTH
    row = {
        "doi": doi_n,
        "claim": claim[:600],
        "method": (method or "")[:300],
        "species": (species or "")[:60],
        "tissue": (tissue or "")[:60],
        "direction": (direction or "")[:60],
        "strength": strength,
        "title": (title or "")[:200],
        "pmid": (pmid or "").strip()[:20],
        "source": (source or "")[:200],
        "note": (note or "")[:300],
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "added_by": (added_by or "")[:64],
    }
    with _LOCK:
        rows = _load_rows(results_dir)
        key = (row["doi"], row["claim"])
        updated = False
        for i, r in enumerate(rows):
            if (r.get("doi"), r.get("claim")) == key:
                rows[i] = row
                updated = True
                break
        if not updated:
            rows.append(row)
        ok = _rewrite_jsonl(evidence_path(results_dir), rows)
    return json.dumps({"ok": ok, "updated": updated, "row": row, "total": len(rows)},
                      ensure_ascii=False)


def _match(row: dict, topic: str = "", doi: str = "", direction: str = "",
           species: str = "") -> bool:
    if doi and _norm_doi(doi) != row.get("doi"):
        return False
    if direction and direction.lower() not in str(row.get("direction", "")).lower():
        return False
    if species and species.lower() not in str(row.get("species", "")).lower():
        return False
    if topic:
        t = topic.lower()
        hay = " ".join(str(row.get(k) or "") for k in
                       ("claim", "method", "title", "note", "direction", "species", "tissue")).lower()
        if t not in hay:
            return False
    return True


def query_evidence(results_dir: str, *, topic: str = "", doi: str = "",
                   direction: str = "", species: str = "", limit: int = 50) -> str:
    """查询证据表（过滤 + 关键词匹配，最新在前）。返回 JSON。"""
    with _LOCK:
        rows = _load_rows(results_dir)
    rows = [r for r in rows if _match(r, topic, doi, direction, species)]
    rows = rows[::-1]  # 最新在前
    if limit and limit > 0:
        rows = rows[:int(limit)]
    return json.dumps({"ok": True, "total_matched": len(rows), "rows": rows},
                      ensure_ascii=False)


def evidence_stats(results_dir: str) -> str:
    """统计：总行数 / 方向分布 / 支持强度分布 / 缺 DOI 数。返回 JSON。"""
    with _LOCK:
        rows = _load_rows(results_dir)
    from collections import Counter
    c_dir = Counter(str(r.get("direction") or "unknown") for r in rows)
    c_strength = Counter(str(r.get("strength") or "unknown") for r in rows)
    no_doi = sum(1 for r in rows if not r.get("doi"))
    return json.dumps({
        "ok": True,
        "total": len(rows),
        "by_direction": dict(c_dir),
        "by_strength": dict(c_strength),
        "missing_doi": no_doi,
        "file": evidence_path(results_dir).replace("\\", "/"),
    }, ensure_ascii=False)


def export_evidence_csv(results_dir: str, path: str = "") -> str:
    """导出 CSV（UTF-8 BOM，Excel 友好）。返回 JSON（含导出路径/行数）。"""
    with _LOCK:
        rows = _load_rows(results_dir)
    if not path:
        path = os.path.join(evidence_dir(results_dir), "evidence.csv")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cols = ["doi", "title", "claim", "method", "species", "tissue",
                "direction", "strength", "pmid", "source", "note", "added_at", "added_by"]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(buf.getvalue())
        return json.dumps({"ok": True, "path": path.replace("\\", "/"),
                           "rows": len(rows)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


# ── 引用校验（防幻觉引用） ─────────────────────────────────────────────────

def _extract_citations(text: str) -> list:
    """从文本提取引用标识：[(kind, id), ...] kind ∈ doi/pmid。"""
    out = []
    if not text:
        return out
    seen = set()
    for m in DOI_RE.finditer(text):
        doi = m.group(0)
        if doi.lower() in seen or any(j in doi.lower() for j in _DOI_JUNK):
            continue
        seen.add(doi.lower())
        out.append(("doi", doi))
    for m in PMID_RE.finditer(text):
        pid = m.group(1)
        if ("pmid:" + pid) in seen:
            continue
        seen.add("pmid:" + pid)
        out.append(("pmid", pid))
    return out


def verify_citations(results_dir: str, text: str, *,
                     check_paper_index: bool = True) -> str:
    """校验综述文本中的引用：DOI/PMID 是否在证据表（或 papers 索引）中。

    check_paper_index=True 时额外对照 hermes_home/papers/.pdf_index.json
    （证据表是综述产出，论文库是文献来源——两个库都认）。
    返回 {verified: [...], missing: [...], total}。
    """
    cites = _extract_citations(text)
    if not cites:
        return json.dumps({"ok": True, "total": 0, "verified": [], "missing": [],
                           "note": "文本中未提取到 DOI/PMID"}, ensure_ascii=False)
    with _LOCK:
        ev_rows = _load_rows(results_dir)
    ev_dois = {str(r.get("doi", "")).lower() for r in ev_rows}
    ev_pmids = {str(r.get("pmid", "")).strip() for r in ev_rows if r.get("pmid")}
    idx_dois, idx_pmids = set(), set()
    if check_paper_index:
        try:
            _lib_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "..", "hermes_home", "papers")
            _idx_f = os.path.join(_lib_dir, ".pdf_index.json")
            if os.path.isfile(_idx_f):
                with open(_idx_f, "r", encoding="utf-8") as f:
                    for e in json.load(f):
                        if e.get("doi"):
                            idx_dois.add(str(e["doi"]).lower())
                        if e.get("pmid"):
                            idx_pmids.add(str(e["pmid"]).strip())
        except Exception:
            pass
    verified, missing = [], []
    for kind, cid in cites:
        hit = False
        if kind == "doi":
            hit = cid.lower() in ev_dois or cid.lower() in idx_dois
        else:
            hit = cid in ev_pmids or cid in idx_pmids
        (verified if hit else missing).append({"kind": kind, "id": cid})
    return json.dumps({"ok": True, "total": len(cites),
                       "verified": verified, "missing": missing},
                      ensure_ascii=False)


# ── 工具注册（对齐 literature_library 模式） ───────────────────────────────

WRITE_SCHEMA = {
    "name": "evidence_write",
    "description": (
        "文献证据表：写入一条『结论↔文献来源』证据（DOI 必填 + 结论 + 方法/物种/"
        "方向/支持强度）。上百篇文献综述的核心载体——每读一篇就把关键结论结构化"
        "落一行，最终 evidence.csv 就是综述的证据底稿。同 DOI+结论重复写入会更新"
        "而非追加。strength ∈ strong/moderate/weak/conflict（conflict=与其他文献矛盾）。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doi": {"type": "string", "description": "文献 DOI（如 10.1016/j.cell.2024.09.042）"},
            "claim": {"type": "string", "description": "该文献支持/报告的一条结论（一句话，≤600 字）"},
            "method": {"type": "string", "description": "支持该结论的方法/实验（可选）"},
            "species": {"type": "string", "description": "物种（human/mouse/…，可选）"},
            "tissue": {"type": "string", "description": "组织（可选）"},
            "direction": {"type": "string", "description": "研究方向（aging/exercise/…，可选）"},
            "strength": {"type": "string", "description": "支持强度 strong/moderate/weak/conflict，默认 moderate"},
            "title": {"type": "string", "description": "文献标题（可选）"},
            "pmid": {"type": "string", "description": "PMID（可选）"},
            "source": {"type": "string", "description": "出处（页码/图表/引用来源，可选）"},
            "note": {"type": "string", "description": "备注（可选）"},
        },
        "required": ["doi", "claim"]
    }
}

QUERY_SCHEMA = {
    "name": "evidence_query",
    "description": (
        "文献证据表查询/导出/统计/引用校验（mode 参数切换）："
        "query=按主题/DOI/方向/物种过滤证据（默认）；export=导出 evidence.csv；"
        "stats=统计（总数/方向分布/强度分布）；verify=校验综述文本中的 DOI/PMID "
        "是否都在证据表或论文库中（防幻觉引用，返回缺失列表）。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "description": "query|export|stats|verify，默认 query"},
            "topic": {"type": "string", "description": "主题关键词（匹配结论/方法/标题，可选）"},
            "doi": {"type": "string", "description": "按 DOI 过滤（可选）"},
            "direction": {"type": "string", "description": "按方向过滤（可选）"},
            "species": {"type": "string", "description": "按物种过滤（可选）"},
            "limit": {"type": "integer", "description": "query 模式返回条数上限，默认 50"},
            "path": {"type": "string", "description": "export 模式导出路径（默认 results/<sid>/review/evidence.csv）"},
            "text": {"type": "string", "description": "verify 模式：待校验的综述文本"},
        },
        "required": []
    }
}


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="evidence_write",
            toolset="memomics",
            schema=WRITE_SCHEMA,
            handler=lambda args, **kw: write_evidence_row(
                kw.get("results_dir", "") or os.environ.get("MEMOMICS_RESULTS_DIR", ""),
                args.get("doi", ""), args.get("claim", ""),
                method=args.get("method", ""), species=args.get("species", ""),
                tissue=args.get("tissue", ""), direction=args.get("direction", ""),
                strength=args.get("strength", _DEFAULT_STRENGTH),
                title=args.get("title", ""), pmid=args.get("pmid", ""),
                source=args.get("source", ""), note=args.get("note", ""),
                added_by=kw.get("task_id", "")),
            emoji="📋",
            max_result_size_chars=4_000,
        )
        registry.register(
            name="evidence_query",
            toolset="memomics",
            schema=QUERY_SCHEMA,
            handler=lambda args, **kw: _query_handler(
                kw.get("results_dir", "") or os.environ.get("MEMOMICS_RESULTS_DIR", ""), args),
            emoji="🔎",
            max_result_size_chars=30_000,
        )
    except Exception as e:
        logger.warning(f"evidence table register failed: {e}")


def _query_handler(results_dir: str, args: dict) -> str:
    mode = str(args.get("mode") or "query")
    if mode == "export":
        return export_evidence_csv(results_dir, args.get("path", ""))
    if mode == "stats":
        return evidence_stats(results_dir)
    if mode == "verify":
        return verify_citations(results_dir, args.get("text", ""))
    return query_evidence(results_dir, topic=args.get("topic", ""),
                          doi=args.get("doi", ""), direction=args.get("direction", ""),
                          species=args.get("species", ""), limit=int(args.get("limit") or 50))


_register()
