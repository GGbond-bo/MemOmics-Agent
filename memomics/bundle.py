# -*- coding: utf-8 -*-
"""MemOmics 资产包（bundle）：记忆 / 知识库 / 技能的导出、预览、导入、**内化激活**。

用户 2026-10-20 定稿：
  1) 记忆用 jsonl 导出（不拷 sqlite，跨版本安全）
  2) 脱敏：本机路径替换成占位符，不把路径带过去
  3) 冲突默认 skip，预览时列出来由用户勾选覆盖
  4) 支持按主题导出（--topic deg-analysis）
  5) **导入后要能被 MemOmics 真正读取/内化** → activate()：重建技能索引、清 KB 缓存、写记忆库+FTS

包结构（zip）::

    manifest.json            # schema/created/scopes/redactions/files(sha256)/counts
    kb/…                     # 相对 memomics/knowledge_base 原样路径
    skills/…                 # 相对 memomics_home/skills 原样路径
    memory/memory.jsonl      # 从 facts 表导出
    meta/imported_from.json  # 可追溯标记（导入时写入）
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile

SCHEMA = "memomics-bundle-v1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # E:\MemOmics-Agent

# 硬编码永不出包（即使用户手动指定）
SECRET_NAMES = ("config.yaml", "provider_keys.json", "dcs_cloud.json", "credentials.json",
                "model_config.json", ".env")
SECRET_PATTERNS = (r"\.pem$", r"\.key$", r"^id_[a-z]+$", r"\.db-journal$", r"\.env$")

# 脱敏替换表（顺序敏感：先长后短）
REDACTIONS = [
    (re.compile(r"[A-Za-z]:[\\/]MemOmics-Agent", re.I), "$MEMOMICS_HOME"),
    (re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/\s\"']+"), "$HOME"),
    (re.compile(r"/hwfssz3/PS_JLU/[^/\s\"']+"), "$CLUSTER_WORKDIR"),
    (re.compile(r"/home/[^/\s\"']+"), "$CLUSTER_HOME"),
    (re.compile(r"\\\\[^\\\s\"']+\\[^\\\s\"']+"), "$SHARE"),
]


def _home() -> str:
    return os.environ.get("MEMOMICS_HOME") or os.path.join(ROOT, "memomics_home")


def _kb_root() -> str:
    return os.path.join(ROOT, "memomics", "knowledge_base")


def _skills_root() -> str:
    return os.path.join(_home(), "skills")


def _memory_db() -> str:
    return os.path.join(_home(), "memory_store.db")


def _is_secret(path: str) -> bool:
    base = os.path.basename(path)
    if base in SECRET_NAMES:
        return True
    return any(re.search(p, base, re.I) for p in SECRET_PATTERNS)


def redact_text(text: str) -> tuple:
    """脱敏：返回 (脱敏后文本, 命中次数)。只在导出时用，导入还原由用户自己处理。"""
    if not text:
        return text, 0
    n = 0
    for pat, rep in REDACTIONS:
        text, k = pat.subn(rep, text)
        n += k
    return text, n


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# 2026-10-20：资产包只收"可移植的文本资产"。首次全量导出 146MB（技能里混了大量
# 图片/数据/二进制），跨机器转移不现实 → 白名单扩展名 + 单文件上限。
TEXT_EXT = (".md", ".json", ".py", ".sh", ".r", ".yaml", ".yml", ".txt",
            ".csv", ".tsv", ".toml", ".cfg", ".ini", ".js", ".ts", ".sql")
MAX_FILE_BYTES = 2 * 1024 * 1024


def _walk(base: str, exts=None, text_only=False, max_bytes=None) -> list:
    out = []
    if not os.path.isdir(base):
        return out
    _exts = TEXT_EXT if text_only else exts
    for cur, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules", ".ipynb_checkpoints")]
        for fn in files:
            if fn.endswith((".pyc", ".pyo")):
                continue
            if _exts and not fn.lower().endswith(tuple(_exts)):
                continue
            p = os.path.join(cur, fn)
            if _is_secret(p):
                continue
            if max_bytes:
                try:
                    if os.path.getsize(p) > max_bytes:
                        continue
                except Exception:
                    continue
            out.append(p)
    return out


# ---------------- 导出 ----------------
def _collect_kb(topic=None) -> list:
    files = _walk(_kb_root(), (".yaml", ".yml"))
    if not topic:
        return files
    words = [w.strip().lower() for w in str(topic).split(",") if w.strip()]
    if not words:
        return files
    hit = []
    for p in files:
        rel = os.path.relpath(p, _kb_root()).lower()
        if any(w in rel for w in words):
            hit.append(p)
            continue
        try:
            head = open(p, encoding="utf-8", errors="replace").read(4000).lower()
        except Exception:
            continue
        if any(w in head for w in words):
            hit.append(p)
    return hit


def _collect_skills(topic=None) -> list:
    files = _walk(_skills_root(), text_only=True, max_bytes=MAX_FILE_BYTES)
    if not topic:
        return files
    words = [w.strip().lower() for w in str(topic).split(",") if w.strip()]
    keep = []
    for p in files:
        rel = os.path.relpath(p, _skills_root()).lower()
        if any(w in rel for w in words):
            keep.append(p)
            continue
        if os.path.basename(p) in ("SKILL.md", "skill.json"):
            try:
                head = open(p, encoding="utf-8", errors="replace").read(3000).lower()
            except Exception:
                continue
            if any(w in head for w in words):
                keep.append(p)
    return keep


def _collect_memory(topic=None) -> list:
    """从 facts 表导出为 [{content, category, tags, trust_score}] + FTS 由导入侧重建。"""
    db = _memory_db()
    if not os.path.exists(db):
        return []
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = c.execute("SELECT content, category, tags, trust_score FROM facts").fetchall()
        c.close()
    except Exception:
        return []
    words = [w.strip().lower() for w in str(topic or "").split(",") if w.strip()]
    out = []
    for content, cat, tags, trust in rows:
        if not content:
            continue
        if words and not any(w in str(content).lower() or w in str(tags).lower() for w in words):
            continue
        out.append({"content": content, "category": cat or "general",
                    "tags": tags or "", "trust_score": trust})
    return out


def export_bundle(scopes, out_dir, topic=None, redact=True, include_env=False, dry_run=False) -> dict:
    """打包。scopes: ['kb','skills','memory','experience'] 的子集。"""
    if isinstance(scopes, str):
        scopes = [s.strip() for s in scopes.split(",") if s.strip()]
    scopes = [s for s in (scopes or []) if s in ("kb", "skills", "memory", "experience", "env")]
    if not scopes:
        return {"ok": False, "error": "scopes 为空（可选 kb/skills/memory）"}
    files = []          # (arcname, bytes, kind)
    counts = {}
    warnings = []
    redactions_hit = 0

    if "kb" in scopes:
        kbf = _collect_kb(topic)
        counts["kb"] = len(kbf)
        for p in kbf:
            rel = os.path.relpath(p, _kb_root()).replace("\\", "/")
            data = open(p, "rb").read()
            if redact:
                try:
                    txt, n = redact_text(data.decode("utf-8"))
                    redactions_hit += n
                    data = txt.encode("utf-8")
                except Exception:
                    pass
            files.append((f"kb/{rel}", data, "kb"))
    if "skills" in scopes:
        skf = _collect_skills(topic)
        counts["skills"] = len({os.path.dirname(os.path.relpath(p, _skills_root())) for p in skf})
        counts["skills_files"] = len(skf)
        for p in skf:
            rel = os.path.relpath(p, _skills_root()).replace("\\", "/")
            data = open(p, "rb").read()
            if redact:
                try:
                    txt, n = redact_text(data.decode("utf-8"))
                    redactions_hit += n
                    data = txt.encode("utf-8")
                except Exception:
                    pass
            files.append((f"skills/{rel}", data, "skills"))
    if "memory" in scopes:
        mem = _collect_memory(topic)
        counts["memory"] = len(mem)
        buf = io.StringIO()
        for m in mem:
            rec = dict(m)
            if redact:
                rec["content"], n = redact_text(rec.get("content") or "")
                redactions_hit += n
            buf.write(json.dumps(rec, ensure_ascii=False) + "\n")
        files.append(("memory/memory.jsonl", buf.getvalue().encode("utf-8"), "memory"))
    if "env" in scopes or include_env:
        for name in ("cluster_envs.json", "environment.json"):
            p = os.path.join(_home(), name)
            if os.path.exists(p):
                files.append((f"env/{name}", open(p, "rb").read(), "env"))

    manifest = {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "created_by": "memomics-bundle",
        "scopes": scopes,
        "topic": topic or "",
        "redacted": bool(redact),
        "redactions_applied": redactions_hit,
        "locators_redacted": bool(redact),
        "excluded": list(SECRET_NAMES),
        "counts": counts,
        "warnings": warnings,
        "files": [{"path": a, "sha256": _sha256_bytes(b), "bytes": len(b)} for a, b, _ in files],
    }
    if dry_run:
        return {"ok": True, "dry_run": True, "manifest": manifest,
                "counts": counts, "files": [a for a, _, _ in files][:200],
                "total_files": len(files)}

    os.makedirs(out_dir, exist_ok=True)
    tag = "+".join(scopes)
    if topic:
        tag += "_" + re.sub(r"[^A-Za-z0-9_-]+", "-", topic)[:24]
    path = os.path.join(out_dir, f"memomics_bundle_{time.strftime('%Y%m%d_%H%M%S')}_{tag}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for arc, data, _ in files:
            zf.writestr(arc, data)
    return {"ok": True, "path": path, "bytes": os.path.getsize(path),
            "manifest": manifest, "counts": counts}


# ---------------- 预览 ----------------
def preview_bundle(zip_path) -> dict:
    if not os.path.exists(zip_path):
        return {"ok": False, "error": "包不存在"}
    try:
        zf = zipfile.ZipFile(zip_path)
    except Exception as exc:
        return {"ok": False, "error": f"不是合法 zip: {exc}"}
    try:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    except Exception:
        return {"ok": False, "error": "包内没有 manifest.json（不是 MemOmics 资产包）"}
    version_ok = str(manifest.get("schema", "")).startswith("memomics-bundle-v")
    secrets_found = [n for n in zf.namelist() if _is_secret(n)]
    conflicts, new_files, missing = [], [], []
    target_map = {"kb": _kb_root(), "skills": _skills_root()}
    for item in (manifest.get("files") or []):
        arc = item["path"]
        top = arc.split("/", 1)[0]
        base = target_map.get(top)
        if not base:
            continue
        rel = arc.split("/", 1)[1]
        local = os.path.join(base, rel.replace("/", os.sep))
        if os.path.exists(local):
            conflicts.append({"path": arc, "kind": top,
                              "local_mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(local))),
                              "bundle_bytes": item.get("bytes"),
                              "local_bytes": os.path.getsize(local),
                              "choose": "skip"})
        else:
            new_files.append(arc)
    mem_count = 0
    if "memory/memory.jsonl" in zf.namelist():
        mem_count = len([x for x in zf.read("memory/memory.jsonl").decode("utf-8").splitlines() if x.strip()])
    return {"ok": True, "version_ok": version_ok, "schema": manifest.get("schema"),
            "created_at": manifest.get("created_at"), "scopes": manifest.get("scopes"),
            "topic": manifest.get("topic"), "redacted": manifest.get("redacted"),
            "locators_redacted": manifest.get("locators_redacted"),
            "counts": manifest.get("counts"), "memory_entries": mem_count,
            "secrets_found": secrets_found,
            "conflicts": conflicts, "new_files": new_files,
            "files": [it["path"] for it in (manifest.get("files") or [])],
            "total_files": len(manifest.get("files") or [])}


# ---------------- 导入 ----------------
def _backup(paths, tag="pre_import") -> str:
    dst = os.path.join(_home(), "backups", f"{time.strftime('%Y%m%d_%H%M%S')}_{tag}")
    os.makedirs(dst, exist_ok=True)
    for src in paths:
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, os.path.basename(src)), dirs_exist_ok=True)
        elif os.path.isfile(src):
            shutil.copy2(src, os.path.join(dst, os.path.basename(src)))
    return dst


def import_bundle(zip_path, overrides=None, backup=True, activate_after=True) -> dict:
    """导入。overrides: {arc_path: 'overwrite'}（默认 skip）。"""
    pv = preview_bundle(zip_path)
    if not pv.get("ok"):
        return pv
    if not pv.get("version_ok"):
        return {"ok": False, "error": f"不兼容的包版本: {pv.get('schema')}"}
    overrides = overrides or {}
    zf = zipfile.ZipFile(zip_path)
    target_map = {"kb": _kb_root(), "skills": _skills_root()}
    bk = _backup([target_map["kb"], target_map["skills"]], "pre_import") if backup else ""
    written, skipped, mem_added = [], [], 0
    try:
        for item in (pv.get("files") or []):
            arc = item["path"] if isinstance(item, dict) else item
            top = arc.split("/", 1)[0]
            base = target_map.get(top)
            if not base:
                continue
            rel = arc.split("/", 1)[1]
            local = os.path.join(base, rel.replace("/", os.sep))
            exists = os.path.exists(local)
            if exists and overrides.get(arc) != "overwrite":
                skipped.append(arc)
                continue
            os.makedirs(os.path.dirname(local), exist_ok=True)
            with open(local, "wb") as f:
                f.write(zf.read(arc))
            written.append(arc)
        # 记忆：按 content 去重写入 facts + 重建 FTS
        if "memory/memory.jsonl" in zf.namelist():
            mem_added = _import_memory(zf.read("memory/memory.jsonl").decode("utf-8"))
        # 可追溯标记
        try:
            meta_dir = os.path.join(_home(), "imports")
            os.makedirs(meta_dir, exist_ok=True)
            rec = {"imported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "bundle": os.path.basename(zip_path),
                   "scopes": pv.get("scopes"), "topic": pv.get("topic"),
                   "written": len(written), "skipped": len(skipped), "memory_added": mem_added}
            with open(os.path.join(meta_dir, "imported_experience.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
    except Exception as exc:
        return {"ok": False, "error": f"导入失败（已备份到 {bk}）: {exc}", "backup": bk}
    act = activate(scopes=pv.get("scopes") or [], touched=written) if activate_after else {}
    return {"ok": True, "written": written, "skipped": skipped, "memory_added": mem_added,
            "backup": bk, "activate": act}


def _norm_for_dedup(text: str) -> str:
    """脱敏归一化：把本机路径也替换成占位符后再比较，
    否则「导出脱敏 → 导回自己」会因为 content 变了而重复插入（实测 2523→2527）。"""
    t, _ = redact_text(text or "")
    return re.sub(r"\s+", " ", t).strip().lower()


def _import_memory(jsonl_text: str) -> int:
    db = _memory_db()
    added = 0
    try:
        c = sqlite3.connect(db)
        _seen = {}
        for (row_content,) in c.execute("SELECT content FROM facts"):
            _seen[_norm_for_dedup(row_content)] = True
        for ln in (jsonl_text or "").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            content = (rec.get("content") or "").strip()
            if not content:
                continue
            _key = _norm_for_dedup(content)
            if _key in _seen:          # 归一化后已存在 → 跳过（不制造重复）
                continue
            try:
                before = c.total_changes
                c.execute("INSERT OR IGNORE INTO facts(content, category, tags, trust_score) VALUES(?,?,?,?)",
                          (content, rec.get("category") or "general",
                           rec.get("tags") or "", rec.get("trust_score") or 0.5))
                if c.total_changes > before:
                    added += 1
                    _seen[_key] = True
            except Exception:
                continue
        try:
            c.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")
        except Exception:
            pass
        c.commit()
        c.close()
    except Exception:
        pass
    return added if isinstance(added, int) else 0


# ---------------- 内化激活 ----------------
def activate(scopes=None, touched=None) -> dict:
    """导入后**让它真的被 MemOmics 用到**：重建技能索引、清 KB 缓存、报告记忆条数。"""
    out = {"ok": True, "steps": []}
    scopes = scopes or ["kb", "skills", "memory"]
    if "skills" in scopes:
        try:
            r = subprocess.run([sys.executable, "-m", "webui.skills_registry", "--build"],
                               cwd=ROOT, capture_output=True, text=True, timeout=300)
            tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-1:] or [""]
            out["steps"].append({"step": "skills_index", "ok": r.returncode == 0, "detail": tail[0][:160]})
        except Exception as exc:
            out["steps"].append({"step": "skills_index", "ok": False, "detail": str(exc)})
    if "kb" in scopes:
        try:
            from memomics.bio_tools import kb_search as _kb
            _kb._file_cache.clear()
            out["steps"].append({"step": "kb_cache", "ok": True, "detail": "kb_search 文件缓存已清空"})
        except Exception as exc:
            out["steps"].append({"step": "kb_cache", "ok": False,
                                 "detail": f"同进程清理失败（新会话/TTL 300s 后自然生效）: {exc}"})
        out["steps"].append({"step": "kb_note", "ok": True,
                             "detail": "被覆盖条目的 locator 若已脱敏，请本机复核证据定位"})
    if "memory" in scopes:
        try:
            c = sqlite3.connect(_memory_db())
            n = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            c.close()
            out["steps"].append({"step": "memory", "ok": True, "detail": f"facts 现有 {n} 条（FTS 已 rebuild）"})
        except Exception as exc:
            out["steps"].append({"step": "memory", "ok": False, "detail": str(exc)})
    out["ok"] = all(s.get("ok") for s in out["steps"] if s.get("step") != "kb_note")
    return out


def rollback(backup_dir) -> dict:
    if not backup_dir or not os.path.isdir(backup_dir):
        return {"ok": False, "error": "备份目录不存在"}
    restored = []
    for name, target in (("knowledge_base", _kb_root()), ("skills", _skills_root())):
        src = os.path.join(backup_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, target, dirs_exist_ok=True)
            restored.append(name)
    return {"ok": True, "restored": restored}


def list_bundles(out_dir=None) -> list:
    out = []
    for base in (out_dir or os.path.join(_home(), "exports"),):
        if not os.path.isdir(base):
            continue
        for fn in sorted(os.listdir(base), reverse=True):
            if fn.endswith(".zip") and fn.startswith("memomics_bundle_"):
                p = os.path.join(base, fn)
                out.append({"name": fn, "path": p, "mb": round(os.path.getsize(p) / 1048576.0, 2),
                            "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p)))})
    return out
