# -*- coding: utf-8 -*-
"""对照翻译任务：整篇逐页翻译、进度持久化、译文 PDF 落盘（2026-11-16）。

用户规则：没有对比翻译时先创建任务；翻译成功并生成译文 PDF 后才允许打开对照。
任务状态与译文块都放在 papers/.translations/，进程重启后仍可恢复。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

from webui import lit_layout, lit_marks, lit_translation_pdf

_LOCK = threading.Lock()
_JOBS: dict = {}


def _paths(rel: str):
    src = lit_marks.pdf_path(rel)
    stem = os.path.splitext(os.path.basename(src))[0]
    root = os.path.join(lit_marks.papers_root(), ".translations")
    os.makedirs(root, exist_ok=True)
    return src, os.path.join(root, stem + ".compare-job.json"), \
        os.path.join(root, stem + ".compare-blocks.json")


def _write_json(path: str, data: dict) -> None:
    tmp = path + ".tmp-%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_blocks(path: str, rel: str, translations: dict) -> None:
    _write_json(path, {
        "schema": "memomics.compare-blocks.v1",
        "pdf": os.path.basename(lit_marks.pdf_path(rel)),
        "translations": translations,
        "updated": time.time(),
    })


def _update(key: str, job_file: str, **patch) -> dict:
    with _LOCK:
        cur = dict(_JOBS.get(key) or _read_json(job_file))
        cur.update(patch)
        cur["updated"] = time.time()
        _JOBS[key] = cur
        _write_json(job_file, cur)
        return dict(cur)


def _chunks(blocks: list, max_items: int = 40, max_chars: int = 11000):
    groups, cur, chars = [], [], 0
    for block in blocks:
        text = str(block.get("text") or "")
        if cur and (len(cur) >= max_items or chars + len(text) > max_chars):
            groups.append(cur)
            cur, chars = [], 0
        cur.append(block)
        chars += len(text)
    if cur:
        groups.append(cur)
    return groups


def _run(key: str, rel: str, translator) -> None:
    _src, job_file, blocks_file = _paths(rel)
    try:
        layout = lit_layout.load(rel)
        pages = layout.get("pages") or []
        total = sum(len(p.get("blocks") or []) for p in pages)
        translations = _read_json(blocks_file).get("translations") or {}
        if not isinstance(translations, dict):
            translations = {}
        _update(key, job_file, status="running", pages=len(pages), total_blocks=total,
                done_pages=0, done_blocks=0, percent=0, error="")
        done_pages = 0
        done_blocks = 0
        for pg in pages:
            blocks = pg.get("blocks") or []
            for group in _chunks(blocks):
                if not group:
                    continue
                answer = translator([str(b.get("text") or "") for b in group])
                values = (answer or {}).get("translations") or []
                if len(values) != len(group):
                    raise RuntimeError("翻译接口返回段落数不一致")
                for block, value in zip(group, values):
                    text = str(value or "").strip()
                    source = str(block.get("text") or "").strip()
                    if text and text != source:
                        translations[str(block.get("id"))] = text
                    done_blocks += 1
            done_pages += 1
            _save_blocks(blocks_file, rel, translations)
            _update(key, job_file, done_pages=done_pages, done_blocks=done_blocks,
                    percent=round(done_blocks * 100.0 / max(1, total), 1))
        if not translations:
            raise RuntimeError("没有得到可写回的有效译文")
        result = lit_translation_pdf.build(rel, layout, translations)
        _update(key, job_file, status="done", pdf_rel=result["rel"],
                written=result["written"], truncated=result["truncated"], percent=100)
    except Exception as e:
        _update(key, job_file, status="failed", error=str(e)[:500])


def status(rel: str, include_translations: bool = False) -> dict:
    src, job_file, blocks_file = _paths(rel)
    with _LOCK:
        job = dict(_JOBS.get(src) or _read_json(job_file))
    if not job:
        return {"ok": True, "path": os.path.basename(src), "status": "none",
                "percent": 0, "pages": 0, "done_pages": 0}
    if job.get("status") == "done":
        pdf = os.path.join(lit_marks.papers_root(), ".translations",
                           os.path.basename(str(job.get("pdf_rel") or "")))
        if not job.get("pdf_rel") or not os.path.isfile(pdf):
            job.update(status="failed", error="译文 PDF 不存在，请重新翻译")
    job["ok"] = True
    if include_translations:
        job["translations"] = _read_json(blocks_file).get("translations") or {}
    return job


def start(rel: str, translator) -> dict:
    src, job_file, _blocks_file = _paths(rel)
    current = status(rel)
    if current.get("status") in ("running", "queued", "done"):
        return current
    job_id = uuid.uuid4().hex[:12]
    job = {
        "ok": True, "job_id": job_id, "path": os.path.basename(src),
        "status": "queued", "percent": 0, "pages": 0, "done_pages": 0,
        "total_blocks": 0, "done_blocks": 0, "pdf_rel": "", "error": "",
        "created": time.time(), "updated": time.time(),
    }
    with _LOCK:
        _JOBS[src] = job
        _write_json(job_file, job)
    thread = threading.Thread(target=_run, args=(src, rel, translator),
                              name="lit-compare-" + job_id, daemon=True)
    thread.start()
    return dict(job)
