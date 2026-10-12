# -*- coding: utf-8 -*-
"""Analysis Claim 账本 —— 结论级溯源 + C 级分级 + 过程可追溯（PTR）自检。

对应 `plans/closed-loop-agent-roadmap-20261012.md` §2.2 / §2.3 / §2.4① 与
`plans/benchmark/tasks-15-v0.md` §0.4 的评分口径（CRR / PTR / ABR / COST）：

  · 一条 **claim** = 一句可判真伪的断言 + 证据链（数据/代码/参数/环境/产物）+ C 级 + 复核状态
  · C 级（只降不升，防虚高）：
      C0 探索性   跑通一次（有日志/产物即可）
      C1 可复现   同数据重跑 ≥2 次、数值或方向一致
      C2 跨方法   ≥2 种方法同向 + 统计门禁通过
      C3 独立复现 在 hold-out 数据（不同队列/物种）方向一致
      C4 实验验证 湿实验或人类队列验证
  · **PTR 五要件**（脚本可自动判定）：数据版本 / 代码位置 / 参数 / 环境 / 日志

落盘（都在会话 results 目录下，随会话一起归档）：
  claims/claims.jsonl   append-only 审计流水
  claims/index.json     最新状态（按 claim_id 覆盖）
  claims/params.json    **辩论/裁决 → 参数决策的落地通道**：后续分析读它，
                        而不是把重要参数留在辩论正文里
  claims/ptr.json       最近一次 PTR 自检结果

设计约束：本模块 **只读** 已有产物（脚本/日志/数据），不修改它们；写自己的 claims/ 目录。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import time
from datetime import datetime

CLAIM_SCHEMA = "memomics.analysis_claim.v1"
CLAIMS_SUBDIR = "claims"
LEVELS = ["C0", "C1", "C2", "C3", "C4"]
LEVEL_NAMES = {
    "C0": "探索性（跑通一次）",
    "C1": "可复现（同数据重跑一致）",
    "C2": "跨方法一致（≥2 方法同向 + 统计门禁）",
    "C3": "独立数据复现（hold-out 方向一致）",
    "C4": "实验验证（湿实验/人类队列）",
}
_STATUSES = ("draft", "confirmed", "refuted", "needs_more_evidence", "superseded")
_SMALL_FILE_LIMIT = 20 * 1024 * 1024      # ≤20MB 全量 sha256；更大的只做首尾部分摘要
_PARTIAL_CHUNK = 1024 * 1024


# ==================== 基础：路径与读写 ====================

def claims_dir(results_dir: str) -> str:
    return os.path.join(str(results_dir or ""), CLAIMS_SUBDIR)


def _ensure_dir(results_dir: str) -> str:
    d = claims_dir(results_dir)
    os.makedirs(d, exist_ok=True)
    return d


def _read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _append_jsonl(path: str, obj) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _next_claim_id(index: dict) -> str:
    n = 0
    for cid in (index or {}).keys():
        m = re.match(r"^c-(\d+)$", str(cid))
        if m:
            n = max(n, int(m.group(1)))
    return "c-%04d" % (n + 1)


# ==================== 证据自动补全（五要件的原料） ====================

def _digest(path: str) -> dict:
    """文件指纹：≤20MB 全量 sha256；更大 → 大小 + 首/尾 1MB 部分摘要（诚实标注）。"""
    try:
        size = os.path.getsize(path)
    except OSError:
        return {}
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            if size <= _SMALL_FILE_LIMIT:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
                kind = "sha256"
            else:
                head = f.read(_PARTIAL_CHUNK)
                f.seek(max(0, size - _PARTIAL_CHUNK))
                tail = f.read(_PARTIAL_CHUNK)
                h.update(head)
                h.update(tail)
                kind = "sha256_partial(head+tail 1MB)"
    except OSError:
        return {"bytes": size}
    return {"bytes": size, "digest_kind": kind, "digest": h.hexdigest()[:32],
            "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path)))}


_DATA_EXT = {".h5ad", ".h5", ".rds", ".csv", ".tsv", ".txt", ".mtx", ".loom", ".zarr",
             ".bam", ".fastq", ".gz", ".parquet", ".xlsx", ".fa", ".faidx", ".vcf"}
_SCRIPT_EXT = {".py", ".r", ".R", ".sh", ".ps1", ".ipynb", ".jl", ".rmd"}
_LOG_EXT = {".log", ".out", ".err", ".jsonl"}
_SKIP_DIRS = {".git", "__pycache__", "claims", "node_modules", ".venv"}


def scan_results_dir(results_dir: str, max_files: int = 400) -> dict:
    """扫 results 目录，分类数据/脚本/日志/产物（只读，不做哈希）。"""
    out = {"data": [], "scripts": [], "logs": [], "artifacts": [], "truncated": False}
    if not results_dir or not os.path.isdir(results_dir):
        return out
    n = 0
    for root, dirs, files in os.walk(results_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            n += 1
            if n > max_files:
                out["truncated"] = True
                return out
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, results_dir).replace("\\", "/")
            ext = os.path.splitext(fn)[1].lower()
            if ext in _SCRIPT_EXT or "scripts/" in rel or rel.startswith("scripts"):
                out["scripts"].append(rel)
            elif ext in _LOG_EXT:
                out["logs"].append(rel)
            elif ext in _DATA_EXT and ("data/" in rel or rel.startswith("data") or ext in (".h5ad", ".rds", ".loom")):
                out["data"].append(rel)
            elif ext in (".png", ".pdf", ".svg", ".tiff", ".tif"):
                out["artifacts"].append(rel)
    return out


def autofill_evidence(results_dir: str, limit: int = 6) -> dict:
    """从 results 目录自动补证据链五要件（含对关键文件的指纹）。"""
    scan = scan_results_dir(results_dir)
    ev = {"data": [], "code": [], "params": {}, "env": {}, "artifacts": [], "logs": []}
    for rel in scan["data"][:limit]:
        d = _digest(os.path.join(results_dir, rel))
        item = {"source": rel, "path": rel}
        item.update(d)
        ev["data"].append(item)
    for rel in scan["scripts"][:limit]:
        ev["code"].append({"path": rel, **_digest(os.path.join(results_dir, rel))})
    for rel in scan["logs"][:limit]:
        ev["logs"].append({"path": rel, **_digest(os.path.join(results_dir, rel))})
    ev["artifacts"] = scan["artifacts"][:limit]
    # 参数：辩论/裁决通道优先，其次 manifest 里记的参数
    pj = read_params(results_dir, include_history=False)
    if pj.get("params"):
        ev["params"] = dict(pj["params"])
        ev["params"]["_source"] = "claims/params.json（辩论/裁决落地通道）"
    else:
        man = _read_json(os.path.join(results_dir, "analysis_manifest.json"), {})
        if isinstance(man, dict) and man.get("params"):
            ev["params"] = dict(man["params"])
            ev["params"]["_source"] = "analysis_manifest.json"
    ev["env"] = env_fingerprint(results_dir)
    return ev


def cost_from_session(results_dir: str) -> dict:
    """从 token_usage.jsonl 汇总 COST（roadmap §2.6）：tokens / llm_ms / api_calls / wall_min。

    取最后一条的 cumulative（会话累计）；wall_min = 首末 ts 差。usd 不做臆测换算（留空，
    由 benchmarker 按当期价目表乘）。没有该文件 → 返回 {}（不假装有数据）。
    """
    p = os.path.join(str(results_dir or ""), "token_usage.jsonl")
    if not os.path.isfile(p):
        return {}
    first_ts = last_ts = ""
    cum = {}
    n = 0
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                n += 1
                if not first_ts:
                    first_ts = str(d.get("ts") or "")
                last_ts = str(d.get("ts") or last_ts)
                if isinstance(d.get("cumulative"), dict):
                    cum = d["cumulative"]
    except OSError:
        return {}
    wall_min = None
    try:
        if first_ts and last_ts:
            wall_min = round((datetime.fromisoformat(last_ts) - datetime.fromisoformat(first_ts)).total_seconds() / 60.0, 1)
    except Exception:
        pass
    return {
        "tokens": int(cum.get("input_tokens") or 0) + int(cum.get("output_tokens") or 0),
        "input_tokens": int(cum.get("input_tokens") or 0),
        "output_tokens": int(cum.get("output_tokens") or 0),
        "llm_ms": int(cum.get("llm_ms") or 0),
        "api_calls": int(cum.get("api_calls") or 0),
        "wall_min": wall_min,
        "turns": n,
        "source": "token_usage.jsonl",
    }


def env_fingerprint(results_dir: str = "") -> dict:
    """环境指纹：优先读会话里已落盘的环境文件，否则现场采集基础信息。"""
    for cand in ("environment.json", "env.json", "claims/env.json"):
        p = os.path.join(results_dir or "", cand)
        if os.path.isfile(p):
            d = _read_json(p, {})
            if isinstance(d, dict) and d:
                return {"source": cand, **{k: d.get(k) for k in list(d)[:12]}}
    info = {
        "source": "runtime_probe",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "time": _now(),
    }
    try:
        import importlib
        from importlib.metadata import version as _pkg_version, PackageNotFoundError as _PkgMissing
        for name in ("scanpy", "anndata", "numpy", "pandas", "statsmodels"):
            try:
                importlib.import_module(name)          # 只确认装没装（不读 __version__，避免弃用告警）
                try:
                    info[name] = _pkg_version(name)
                except _PkgMissing:
                    info[name] = "?"
            except Exception:
                continue
    except Exception:
        pass
    return info


# ==================== C 级校验（只降不升） ====================

def _methods_of(claim: dict) -> list:
    """claim 里声明的"方法清单"：证据链 params.method(s) + claim.methods + 复核记录里的 methods。"""
    out = []
    ev = claim.get("evidence") or {}
    p = ev.get("params") if isinstance(ev.get("params"), dict) else {}
    m = p.get("method") or p.get("methods")
    if isinstance(m, str):
        m = [m]
    for x in (m or []):
        if str(x).strip():
            out.append(str(x).strip())
    for x in (claim.get("methods") or []):
        if str(x).strip():
            out.append(str(x).strip())
    for v in (claim.get("verifiers") or []):
        if isinstance(v, dict):
            for x in (v.get("methods") or []):
                if str(x).strip():
                    out.append(str(x).strip())
    dedup = []
    for x in out:
        if x not in dedup:
            dedup.append(x)
    return dedup


def validate_level(claim: dict, requested: str = "") -> tuple:
    """按 roadmap §2.3 的准入门槛校验 C 级 —— 不达标就降级并写原因。

    返回 (level, reasons)。**只会降不会升**（防虚高，同 validate_kb 的思路）。
    """
    reasons = []
    lv = str(requested or claim.get("level") or "C0").upper()
    if lv not in LEVELS:
        reasons.append(f"未知 C 级 {lv!r} → 按 C0 处理")
        lv = "C0"
    ev = claim.get("evidence") or {}
    vers = claim.get("verifiers") or []

    def _has(kind):
        return any(str(v.get("kind") or "") == kind for v in vers if isinstance(v, dict))

    def _runs_agree():
        for v in vers:
            if not isinstance(v, dict):
                continue
            if str(v.get("kind") or "") in ("independent_rerun", "rerun"):
                try:
                    runs = int(v.get("runs") or 0)
                except Exception:
                    runs = 0
                agg = str(v.get("agreement") or "")
                m = re.match(r"^(\d+)\s*/\s*(\d+)$", agg.strip())
                if runs >= 2 and (not agg or (m and m.group(1) == m.group(2))):
                    return True
        return False

    if lv in ("C1", "C2", "C3", "C4"):
        if not (ev.get("data") and ev.get("logs")):
            reasons.append("缺数据指纹或运行日志（C0 门槛都没过）")
            lv = "C0"
    if lv in ("C2", "C3", "C4"):
        if lv == "C4":
            if not _has("wetlab") and not _has("human_cohort"):
                reasons.append("无湿实验/人类队列验证记录 → 降 C3")
                lv = "C3"
        if lv == "C3":
            if not (_has("holdout") or _has("independent_dataset")):
                reasons.append("无 hold-out 数据集方向一致记录 → 降 C2")
                lv = "C2"
        if lv == "C2":
            n_methods = len(_methods_of(claim))
            gate_ok = _has("statistical_gate") or str(claim.get("statistics_gate") or "") == "passed"
            if n_methods < 2:
                reasons.append(f"只有 {n_methods} 种方法（C2 要求 ≥2 种方法同向）→ 降 C1")
                lv = "C1"
            elif not gate_ok:
                reasons.append("统计门禁未通过/未记录（多重检验·功效·批次·敏感性）→ 降 C1")
                lv = "C1"
        if lv == "C1" and not _runs_agree():
            reasons.append("无「同数据重跑 ≥2 次一致」记录 → 降 C0")
            lv = "C0"
    return lv, reasons


# ==================== claim 增删查改 ====================

def add_claim(results_dir: str, statement: str, level: str = "C0",
              evidence: dict = None, verifiers: list = None, cost: dict = None,
              status: str = "", claim_id: str = "", kind: str = "finding",
              autofill: bool = True, source: str = "agent") -> dict:
    """登记一条 claim（自动补证据链、按门槛校验 C 级）。返回 claim dict。"""
    statement = " ".join(str(statement or "").split())
    if not statement:
        raise ValueError("statement 不能为空")
    _ensure_dir(results_dir)
    claim = {
        "schema": CLAIM_SCHEMA,
        "claim_id": claim_id or "",
        "kind": kind,                       # finding | decision | abstention
        "statement": statement,
        "level": str(level or "C0").upper(),
        "level_requested": str(level or "C0").upper(),
        "evidence": dict(evidence or {}),
        "verifiers": list(verifiers or []),
        "cost": dict(cost or {}) or cost_from_session(results_dir),
        "status": status or ("confirmed" if str(level).upper() != "C0" else "draft"),
        "source": source,
        "created_at": _now(),
        "updated_at": _now(),
    }
    if autofill and results_dir:
        auto = autofill_evidence(results_dir)
        for k, v in auto.items():
            if not claim["evidence"].get(k) and v:
                claim["evidence"][k] = v
    claim["level"], reasons = validate_level(claim, claim["level_requested"])
    if reasons:
        claim["level_downgrade_reasons"] = reasons
    idx_path = os.path.join(claims_dir(results_dir), "index.json")
    index = _read_json(idx_path, {}) or {}
    if not claim["claim_id"]:
        claim["claim_id"] = _next_claim_id(index)
    index[claim["claim_id"]] = claim
    _write_json(idx_path, index)
    _append_jsonl(os.path.join(claims_dir(results_dir), "claims.jsonl"),
                  {"event": "add", "at": claim["created_at"], **claim})
    sync_to_manifest(results_dir)
    return claim


def load_claims(results_dir: str) -> dict:
    return _read_json(os.path.join(claims_dir(results_dir), "index.json"), {}) or {}


def list_claims(results_dir: str, limit: int = 50, status: str = "") -> list:
    items = list(load_claims(results_dir).values())
    if status:
        items = [c for c in items if str(c.get("status") or "") == status]
    items.sort(key=lambda c: str(c.get("updated_at") or ""), reverse=True)
    return items[:limit]


def add_verifier(results_dir: str, claim_id: str, verifier: dict, status: str = "") -> dict:
    """加一条复核记录（重跑/hold-out/统计门禁/辩论）→ 可能提升 C 级（仍要过门槛校验）。"""
    idx_path = os.path.join(claims_dir(results_dir), "index.json")
    index = _read_json(idx_path, {}) or {}
    c = index.get(claim_id)
    if not c:
        raise KeyError(f"claim 不存在: {claim_id}")
    c.setdefault("verifiers", []).append(dict(verifier or {}))
    # 复核时把"运行参数通道"里的方法清单补进证据链（辩论/裁决定的方法往往在登记 claim 之后才落盘）
    try:
        pm = read_params(results_dir, include_history=False).get("params") or {}
        if pm:
            evp = c.setdefault("evidence", {}).setdefault("params", {})
            for k, v in pm.items():
                evp.setdefault(k, v)
    except Exception:
        pass
    for x in ((verifier or {}).get("methods") or []):
        c.setdefault("methods", [])
        if str(x).strip() and str(x).strip() not in c["methods"]:
            c["methods"].append(str(x).strip())
    if status:
        c["status"] = status
    # 用新 verifier 重新校验：先按"目标级"试（用户可在 verifier 里写 target_level）
    target = str((verifier or {}).get("target_level") or c.get("level") or "C0").upper()
    new_lv, reasons = validate_level(c, target)
    c["level"] = new_lv
    if reasons:
        c["level_downgrade_reasons"] = reasons
    c["updated_at"] = _now()
    index[claim_id] = c
    _write_json(idx_path, index)
    _append_jsonl(os.path.join(claims_dir(results_dir), "claims.jsonl"),
                  {"event": "verify", "at": c["updated_at"], "claim_id": claim_id, "verifier": verifier})
    sync_to_manifest(results_dir)
    return c


def set_status(results_dir: str, claim_id: str, status: str) -> dict:
    if status not in _STATUSES:
        raise ValueError(f"status 必须是 {_STATUSES} 之一")
    idx_path = os.path.join(claims_dir(results_dir), "index.json")
    index = _read_json(idx_path, {}) or {}
    c = index.get(claim_id)
    if not c:
        raise KeyError(f"claim 不存在: {claim_id}")
    c["status"] = status
    c["updated_at"] = _now()
    index[claim_id] = c
    _write_json(idx_path, index)
    _append_jsonl(os.path.join(claims_dir(results_dir), "claims.jsonl"),
                  {"event": "status", "at": c["updated_at"], "claim_id": claim_id, "status": status})
    return c


# ==================== 辩论/裁决 → 参数决策通道 ====================

def record_decision(results_dir: str, *, topic: str = "", decision: str = "",
                    params: dict = None, verdict: str = "", confidence: str = "",
                    evidence: list = None, source: str = "debate",
                    next_actions: list = None, missing: list = None) -> dict:
    """把一场辩论/一次裁决的**参数决策**落到 `claims/params.json`。

    为什么单开一个文件：辩论的产出只有落到"下一个脚本要读的地方"，才算真的用上了。
    后续分析应 `read_params()` 后按这里的 params 执行；每次更新追加 history，
    谁改的、依据是什么（verdict/证据）都留痕。
    """
    _ensure_dir(results_dir)
    path = os.path.join(claims_dir(results_dir), "params.json")
    cur = _read_json(path, {}) or {}
    entry = {
        "topic": " ".join(str(topic or "").split())[:200],
        "decision": " ".join(str(decision or "").split())[:400],
        "params": dict(params or {}),
        "verdict": str(verdict or ""),
        "confidence": str(confidence or ""),
        "evidence": list(evidence or [])[:10],
        "next_actions": list(next_actions or [])[:10],
        "missing": list(missing or [])[:10],
        "source": source,
        "at": _now(),
    }
    hist = cur.get("history") if isinstance(cur.get("history"), list) else []
    hist.append(entry)
    out = {
        "updated_at": entry["at"],
        "topic": entry["topic"],
        "decision": entry["decision"],
        "params": entry["params"],
        "verdict": entry["verdict"],
        "confidence": entry["confidence"],
        "evidence": entry["evidence"],
        "source": source,
        "history": hist[-50:],
    }
    # 合并历史里出现过的参数键（后写覆盖先写），并记来源
    merged = {}
    for h in out["history"]:
        if isinstance(h.get("params"), dict):
            merged.update(h["params"])
    if entry["params"]:
        merged.update(entry["params"])
    out["params"] = merged
    _write_json(path, out)
    return out


def record_decision_from_result(results_dir: str, result: dict, source: str = "debate") -> dict:
    """辩论结果 → 参数决策通道（辩论引擎跑完自动调用，不依赖 agent 记不记得）。"""
    if not results_dir or not isinstance(result, dict):
        return {}
    params = result.get("recommended_params") if isinstance(result.get("recommended_params"), dict) else {}
    chain = result.get("chain_verdicts") if isinstance(result.get("chain_verdicts"), dict) else {}
    ev = []
    if result.get("topic"):
        ev.append(f"topic: {result.get('topic')}")
    if result.get("level"):
        ev.append(f"level: {result.get('level')}")
    if chain.get("decisive"):
        ev.append(f"证据链决定项: {chain.get('decisive')}")
    for k in ("verdict", "confidence", "decision_source"):
        if result.get(k):
            ev.append(f"{k}: {result.get(k)}")
    return record_decision(
        results_dir,
        topic=str(result.get("topic") or ""),
        decision=str(result.get("decision") or ""),
        params=params,
        verdict=str(result.get("verdict") or ""),
        confidence=str(result.get("confidence") or ""),
        evidence=ev,
        source=source,
        next_actions=result.get("next_actions") if isinstance(result.get("next_actions"), list) else [],
        missing=result.get("missing") if isinstance(result.get("missing"), list) else [],
    )


def read_params(results_dir: str, include_history: bool = True) -> dict:
    d = _read_json(os.path.join(claims_dir(results_dir), "params.json"), {}) or {}
    if d and not include_history:
        d = {k: v for k, v in d.items() if k != "history"}
    return d


# ==================== PTR 五要件自检（D3 的核） ====================

def ptr_report(results_dir: str) -> dict:
    """过程可追溯率：数据版本 / 代码 / 参数 / 环境 / 日志，各 0.2，全有=1.0。"""
    checks = {}

    scan = scan_results_dir(results_dir)
    data_items = []
    for rel in scan["data"][:6]:
        d = _digest(os.path.join(results_dir, rel))
        data_items.append({"path": rel, **d})
    checks["data_version"] = {
        "ok": bool(data_items),
        "detail": data_items,
        "missing_hint": "缺数据文件或其指纹（把输入数据放到 results/<sid>/data/ 下）",
    }

    code_items = []
    for rel in scan["scripts"][:8]:
        d = _digest(os.path.join(results_dir, rel))
        code_items.append({"path": rel, **d})
    git_commit = ""
    try:
        import subprocess
        git_commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                    cwd=os.path.dirname(os.path.abspath(__file__)),
                                    capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        git_commit = ""
    checks["code"] = {
        "ok": bool(code_items),
        "detail": {"scripts": code_items, "repo_commit": git_commit},
        "missing_hint": "缺脚本文件（把实际执行的脚本保存到 results/<sid>/scripts/ 下）",
    }

    pj = read_params(results_dir, include_history=False)
    man = _read_json(os.path.join(results_dir, "analysis_manifest.json"), {})
    params = pj.get("params") if pj.get("params") else (man.get("params") if isinstance(man, dict) else {})
    checks["params"] = {
        "ok": bool(params),
        "detail": {"source": "claims/params.json" if pj.get("params") else "analysis_manifest.json",
                   "params": params or {}},
        "missing_hint": "缺参数记录（辩论/裁决落 claims/params.json；或提交 analysis_manifest 时带 params）",
    }

    env = env_fingerprint(results_dir)
    # 环境这一件要求"**这次运行**留下了环境记录"（environment.json / manifest.env / claims/env.json）。
    # 检查器现场探到的 python/platform 只作为补充信息（source=runtime_probe），不算通过 ——
    # 否则一个什么都没记录的目录也能白拿 0.2 分（D3 要判的是产物，不是检查器自己的环境）。
    env_recorded = str(env.get("source") or "") not in ("", "runtime_probe")
    checks["env"] = {
        "ok": env_recorded,
        "detail": env,
        "missing_hint": "缺环境指纹（把 environment.json（conda/R/包版本）落到 results/<sid>/）",
    }

    logs = []
    for rel in scan["logs"][:6]:
        logs.append({"path": rel, **_digest(os.path.join(results_dir, rel))})
    checks["logs"] = {
        "ok": bool(logs),
        "detail": logs,
        "missing_hint": "缺运行日志（把 stdout/stderr 落到 results/<sid>/logs/ 下）",
    }

    score = round(sum(0.2 for c in checks.values() if c["ok"]), 2)
    rep = {
        "schema": "memomics.ptr_report.v1",
        "results_dir": str(results_dir).replace("\\", "/"),
        "generated_at": _now(),
        "score": score,
        "verdict": "pass" if score >= 0.9 else ("partial" if score > 0 else "fail"),
        "checks": checks,
        "missing": [c["missing_hint"] for c in checks.values() if not c["ok"]],
        "cost": cost_from_session(results_dir),     # COST（roadmap §2.6）：拼接给 benchmarker
    }
    try:
        _ensure_dir(results_dir)
        _write_json(os.path.join(claims_dir(results_dir), "ptr.json"), rep)
    except Exception:
        pass
    return rep


# ==================== 与 analysis_manifest 同步（v2: claims[]） ====================

def sync_to_manifest(results_dir: str) -> dict:
    """把 claims 摘要并进 analysis_manifest.json（**只加键，不动 v1 已有字段**）。

    roadmap §2.4① 要求 manifest v2 带 `claims[]`；这里就地补 `claims`/`claim_count`/`ptr_score`，
    v1 的消费者读旧字段不受影响（未知键忽略）。
    """
    mpath = os.path.join(str(results_dir or ""), "analysis_manifest.json")
    man = _read_json(mpath, {})
    if not isinstance(man, dict) or not man:
        return {}
    try:
        index = load_claims(results_dir)
        man["claims"] = list(index.values())[-50:]
        man["claim_count"] = len(index)
        ptr = _read_json(os.path.join(claims_dir(results_dir), "ptr.json"), {})
        if ptr:
            man["ptr_score"] = ptr.get("score")
        man["claims_updated_at"] = _now()
        _write_json(mpath, man)
    except Exception:
        return {}
    return man


# ==================== 给 agent 看的紧凑文本 ====================

def format_for_agent(results_dir: str, data: dict = None) -> str:
    d = data or {}
    if d.get("action") == "ptr":
        rep = d.get("report") or {}
        lines = [f"PTR 自检：{rep.get('score')}（{rep.get('verdict')}）"]
        for k, c in (rep.get("checks") or {}).items():
            lines.append(f"  {'✅' if c.get('ok') else '❌'} {k}")
        for m in (rep.get("missing") or [])[:5]:
            lines.append(f"  · {m}")
        return "\n".join(lines)
    if d.get("action") == "params":
        pj = d.get("params") or {}
        if not pj.get("params"):
            return "claims/params.json：暂无参数决策记录（辩过重要参数后会自动落这里）"
        lines = [f"参数决策（来自 {pj.get('source')}，更新于 {pj.get('updated_at')}）",
                 f"  决策：{pj.get('decision')}"]
        for k, v in (pj.get("params") or {}).items():
            lines.append(f"  · {k} = {v}")
        if pj.get("verdict"):
            lines.append(f"  裁决：{pj.get('verdict')}（置信度 {pj.get('confidence')}）")
        return "\n".join(lines)
    claims = d.get("claims") or []
    if not claims:
        return "claims 账本为空（还没有登记结论）"
    lines = [f"claims 共 {len(claims)} 条："]
    for c in claims[:12]:
        lv = c.get("level")
        reasons = c.get("level_downgrade_reasons")
        note = f"（{'；'.join(reasons)[:60]}）" if reasons else ""
        lines.append(f"  {c.get('claim_id')} [{lv}] {str(c.get('statement'))[:60]} {c.get('status')}{note}")
    return "\n".join(lines)


# ==================== Tool 入口 ====================

def claim_ledger(results_dir: str = "", action: str = "list", statement: str = "",
                 level: str = "C0", claim_id: str = "", status: str = "",
                 verifier: dict = None, params: dict = None, topic: str = "",
                 decision: str = "", verdict: str = "", confidence: str = "",
                 evidence: list = None, results_dir_override: str = "", **kw) -> str:
    """工具入口：action ∈ add_claim / list / verify / status / ptr / params / read_params。"""
    try:
        from memomics.bio_tools.debate_analysis import get_session_results_dir
        rd = results_dir_override or results_dir or get_session_results_dir() or ""
    except Exception:
        rd = results_dir_override or results_dir or ""
    if not rd:
        return json.dumps({"ok": False, "error": "拿不到 results 目录（会话上下文缺失）"}, ensure_ascii=False)
    try:
        if action in ("add_claim", "add"):
            c = add_claim(rd, statement, level=level, verifiers=[verifier] if verifier else None)
            return json.dumps({"ok": True, "claim": c, "text": format_for_agent(rd, {"action": "list",
                                                                                     "claims": [c]})},
                              ensure_ascii=False, indent=2)
        if action in ("list",):
            return json.dumps({"ok": True, "claims": list_claims(rd), "text": format_for_agent(rd, {"action": "list", "claims": list_claims(rd)})},
                              ensure_ascii=False, indent=2)
        if action in ("verify", "add_verifier"):
            c = add_verifier(rd, claim_id, verifier or {}, status=status)
            return json.dumps({"ok": True, "claim": c}, ensure_ascii=False, indent=2)
        if action in ("status", "set_status"):
            c = set_status(rd, claim_id, status)
            return json.dumps({"ok": True, "claim": c}, ensure_ascii=False, indent=2)
        if action in ("ptr", "ptr_report"):
            rep = ptr_report(rd)
            return json.dumps({"ok": True, "report": rep, "text": format_for_agent(rd, {"action": "ptr", "report": rep})},
                              ensure_ascii=False, indent=2)
        if action in ("params_from_decision", "record_decision"):
            d = record_decision(rd, topic=topic, decision=decision, params=params or {},
                                verdict=verdict, confidence=confidence, evidence=evidence or [])
            return json.dumps({"ok": True, "params": d}, ensure_ascii=False, indent=2)
        if action in ("params", "read_params"):
            pj = read_params(rd)
            return json.dumps({"ok": True, "params": pj, "text": format_for_agent(rd, {"action": "params", "params": pj})},
                              ensure_ascii=False, indent=2)
        return json.dumps({"ok": False, "error": f"未知 action: {action}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)[:300]}, ensure_ascii=False)


SCHEMA = {
    "name": "claim_ledger",
    "description": (
        "结论级溯源账本（Analysis Claim）。**每条要对外说的结论都必须在这里登记**；\n"
        "登记时自动补证据链（数据指纹/脚本/参数/环境/日志）并按 C 级准入门槛校验（只降不升）。\n"
        "actions:\n"
        "  add_claim: 登记一条结论（statement + level C0-C4）\n"
        "  list: 列出本会话已登记的结论（含降级原因）\n"
        "  verify: 给结论加复核记录（independent_rerun/holdout/statistical_gate/wetlab）→ 可能升 C 级\n"
        "  status: 改状态（draft/confirmed/refuted/needs_more_evidence/superseded）\n"
        "  ptr: 过程可追溯自检（数据版本/代码/参数/环境/日志 五要件，返回可追溯率）\n"
        "  params: 读「辩论/裁决 → 参数决策」通道（**跑关键分析前必须先读**）\n"
        "  params_from_decision: 把一次参数决策写进通道（一般由辩论引擎自动写，手动用于人工决策）"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string",
                       "enum": ["add_claim", "list", "verify", "status", "ptr", "params", "params_from_decision"]},
            "statement": {"type": "string", "description": "claim 的一句话断言（可判真伪），add_claim 必填"},
            "level": {"type": "string", "enum": LEVELS,
                      "description": "请求的 C 级（会被门槛校验，可能降级）：C0 探索/C1 可复现/C2 跨方法/C3 独立数据/C4 实验验证"},
            "claim_id": {"type": "string", "description": "verify/status 指定 claim"},
            "status": {"type": "string", "enum": list(_STATUSES)},
            "verifier": {"type": "object",
                         "description": "复核记录，如 {\"kind\":\"independent_rerun\",\"runs\":3,\"agreement\":\"3/3\"} 或 {\"kind\":\"holdout\",\"dataset\":\"GSE...\",\"direction\":\"consistent\"} 或 {\"kind\":\"statistical_gate\",\"passed\":true}"},
            "topic": {"type": "string", "description": "params_from_decision：决策主题"},
            "decision": {"type": "string", "description": "params_from_decision：决策一句话"},
            "params": {"type": "object", "description": "params_from_decision：要落地的参数"},
            "verdict": {"type": "string"}, "confidence": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["action"],
    },
}

try:  # 注册进 MemOmics 工具表（与 skill_evolution 同样的方式）
    from tools.registry import registry  # type: ignore

    registry.register(
        name="claim_ledger",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: claim_ledger(
            action=args.get("action", "list"),
            statement=args.get("statement", ""),
            level=args.get("level", "C0"),
            claim_id=args.get("claim_id", ""),
            status=args.get("status", ""),
            verifier=args.get("verifier"),
            params=args.get("params"),
            topic=args.get("topic", ""),
            decision=args.get("decision", ""),
            verdict=args.get("verdict", ""),
            confidence=args.get("confidence", ""),
            evidence=args.get("evidence"),
        ),
    )
except Exception:
    pass