# -*- coding: utf-8 -*-
"""文献批注存储（文献库 2.0）。

设计约束（详见 docs/literature-library-architecture.md）：
- 不改 `.pdf_index.json`、不改 PDF、不改知识库；批注只写 `papers/.annotations/<stem>.json`。
- 坐标归一化 0–1，缩放/DPI 不变形。
- 原子替换 + 每篇文件锁 + revision 乐观锁（多标签页并发不写坏）。
- 路径只允许 papers 根下的 `<stem>.pdf`；stem 不允许出现分隔符。

对外 API：
    load(rel) / add(rel, mark, expected_revision) / update(rel, mark_id, patch, rev)
    delete(rel, mark_id, rev) / stats(rel)
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime

SCHEMA = "memomics.paper-marks.v1"
MAX_MARKS = 2000
MAX_RECTS = 80
MAX_QUOTE = 2000
MAX_COMMENT = 4000
MAX_ID_LEN = 64

KINDS = {"highlight", "note", "region"}
PALETTE = {
    "yellow": "#fcd34d",
    "green": "#86efac",
    "blue": "#7dd3fc",
    "pink": "#f9a8d4",
    "purple": "#d8b4fe",
}

_LOCK = threading.Lock()
_FILE_LOCKS: dict = {}

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,%d}$" % MAX_ID_LEN)


class MarksError(Exception):
    """带 HTTP 语义的批注错误。"""

    def __init__(self, code: str, message: str, status: int = 400, extra: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra or {}


def papers_root() -> str:
    """文献根目录。测试/部署可用 MEMOMICS_PAPERS_DIR 覆盖。"""
    env = os.environ.get("MEMOMICS_PAPERS_DIR")
    if env:
        return os.path.abspath(env)
    here = os.path.dirname(os.path.abspath(__file__))
    home = os.environ.get("MEMOMICS_HOME") or os.path.join(os.path.dirname(here), "memomics_home")
    return os.path.join(home, "papers")


def _file_lock(path: str) -> threading.Lock:
    with _LOCK:
        lk = _FILE_LOCKS.get(path)
        if lk is None:
            lk = threading.Lock()
            _FILE_LOCKS[path] = lk
        return lk


def _norm_rel(rel: str) -> str:
    name = str(rel or "").strip().replace("\\", "/")
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    if not name or name in (".", ".."):
        raise MarksError("bad_path", "缺少文献文件名", 400)
    if not name.lower().endswith(".pdf"):
        raise MarksError("bad_path", "只支持 PDF 文献", 400)
    if "\x00" in name:
        raise MarksError("bad_path", "非法文件名", 400)
    return name


def pdf_path(rel: str) -> str:
    """校验并返回 PDF 绝对路径（必须存在且在 papers 根内）。"""
    name = _norm_rel(rel)
    root = os.path.realpath(papers_root())
    full = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, full]) != root:
        raise MarksError("bad_path", "路径越界", 403)
    if not os.path.isfile(full):
        raise MarksError("not_found", "文献不存在: %s" % name, 404)
    return full


def marks_path(rel: str) -> str:
    name = _norm_rel(rel)
    stem = name[:-4]
    return os.path.join(papers_root(), ".annotations", stem + ".json")


def _sha256(rel: str) -> str:
    """优先取 `.pdf_index.json` 里登记的 sha256（避免每次读整份 PDF）。"""
    name = _norm_rel(rel)
    try:
        idx_path = os.path.join(papers_root(), ".pdf_index.json")
        with open(idx_path, encoding="utf-8") as f:
            entries = json.load(f) or []
        for e in entries if isinstance(entries, list) else []:
            if isinstance(e, dict) and str(e.get("file") or "") == name:
                return str(e.get("sha256") or "")
    except Exception:
        pass
    return ""


def _empty(rel: str) -> dict:
    return {
        "schema": SCHEMA,
        "pdf": _norm_rel(rel),
        "sha256": _sha256(rel),
        "revision": 0,
        "updated": "",
        "marks": [],
    }


def _read_file(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except FileNotFoundError:
        return None
    except Exception:
        # 损坏文件：改名留证，按空处理，绝不因批注文件坏掉而让文献打不开
        try:
            os.replace(path, path + ".bad-%d" % int(datetime.now().timestamp()))
        except Exception:
            pass
        return None


def load(rel: str) -> dict:
    """读取某篇文献的全部批注（不存在则返回空结构）。"""
    pdf_path(rel)  # 校验存在与路径
    data = _read_file(marks_path(rel)) or _empty(rel)
    data.setdefault("schema", SCHEMA)
    data.setdefault("pdf", _norm_rel(rel))
    data.setdefault("revision", 0)
    data.setdefault("marks", [])
    if not isinstance(data.get("marks"), list):
        data["marks"] = []
    cur = _sha256(rel)
    data["stale"] = bool(data.get("sha256") and cur and data["sha256"] != cur)
    if cur and not data.get("sha256"):
        data["sha256"] = cur
    return data


def _write(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _clamp01(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    if x != x:  # NaN
        return 0.0
    return max(0.0, min(1.0, x))


def normalize_mark(raw: dict) -> dict:
    """校验并规范化一条批注（越界 rect 夹到 0–1，非法字段拒绝）。"""
    if not isinstance(raw, dict):
        raise MarksError("bad_mark", "批注必须是对象", 400)
    kind = str(raw.get("kind") or "highlight").strip().lower()
    if kind not in KINDS:
        raise MarksError("bad_mark", "未知批注类型: %s" % kind, 400)
    try:
        page = int(raw.get("page"))
    except (TypeError, ValueError):
        raise MarksError("bad_mark", "page 必须是整数", 400)
    if page < 1 or page > 100000:
        raise MarksError("bad_mark", "page 超出范围", 400)
    space = str(raw.get("space") or "norm").strip().lower()
    if space not in ("norm", "reading"):
        raise MarksError("bad_mark", "未知坐标空间: %s" % space, 400)
    rects = []
    for r in (raw.get("rects") or [])[:MAX_RECTS]:
        if not isinstance(r, dict):
            continue
        rects.append({
            "x": round(_clamp01(r.get("x")), 5),
            "y": round(_clamp01(r.get("y")), 5),
            "w": round(_clamp01(r.get("w")), 5),
            "h": round(_clamp01(r.get("h")), 5),
        })
    rects = [r for r in rects if r["w"] > 0 and r["h"] > 0]
    blocks = []
    for b in (raw.get("blocks") or [])[:MAX_RECTS]:
        b = str(b or "").strip()
        if b and re.match(r"^[\w.-]{1,80}$", b) and b not in blocks:
            blocks.append(b)
    anchors = []
    for a in (raw.get("anchors") or [])[:MAX_RECTS]:
        if not isinstance(a, dict):
            continue
        block = str(a.get("block") or "").strip()
        if not block or not re.match(r"^[\w.-]{1,80}$", block):
            continue
        try:
            start = max(0, int(a.get("start") or 0))
            end = max(0, int(a.get("end") or 0))
        except (TypeError, ValueError):
            continue
        text = str(a.get("text") or "")[:MAX_QUOTE]
        if end <= start or not text:
            continue
        anchors.append({"block": block, "start": start, "end": end, "text": text})
    if space == "norm" and not rects:
        raise MarksError("bad_mark", "缺少有效的选区矩形", 400)
    if space == "reading" and not anchors:
        raise MarksError("bad_mark", "阅读模式批注缺少文字锚点", 400)
    if space == "reading":
        rects = []
    color = str(raw.get("color") or "yellow").strip().lower()
    if color not in PALETTE:
        color = "yellow"
    mid = str(raw.get("id") or "").strip()
    if mid and not _ID_RE.match(mid):
        raise MarksError("bad_mark", "非法批注 id", 400)
    if not mid:
        mid = "mk_" + uuid.uuid4().hex[:10]
    annotation_id = str(raw.get("annotation_id") or "").strip()
    if annotation_id and not _ID_RE.match(annotation_id):
        raise MarksError("bad_mark", "非法批注 annotation_id", 400)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    item = {
        "id": mid,
        "kind": kind,
        "page": page,
        "space": space,
        "rects": rects,
        "color": color,
        "quote": str(raw.get("quote") or "")[:MAX_QUOTE],
        "comment": str(raw.get("comment") or "")[:MAX_COMMENT],
        "created": str(raw.get("created") or now),
        "updated": now,
    }
    if space == "reading":
        item["blocks"] = blocks or list(dict.fromkeys(a["block"] for a in anchors))
        item["anchors"] = anchors
    if annotation_id:
        item["annotation_id"] = annotation_id
    return item


def _check_revision(data: dict, expected) -> None:
    if expected is None or expected == "":
        return
    try:
        exp = int(expected)
    except (TypeError, ValueError):
        return
    if exp != int(data.get("revision") or 0):
        raise MarksError("conflict", "批注已被其他窗口修改", 409,
                         {"revision": int(data.get("revision") or 0), "marks": data.get("marks") or []})


def add(rel: str, mark: dict, expected_revision=None) -> dict:
    path = marks_path(rel)
    pdf_path(rel)
    item = normalize_mark(mark)
    with _file_lock(path):
        data = _read_file(path) or _empty(rel)
        _check_revision(data, expected_revision)
        marks = [m for m in (data.get("marks") or []) if isinstance(m, dict) and m.get("id") != item["id"]]
        if len(marks) >= MAX_MARKS:
            raise MarksError("too_many", "单篇批注已达上限（%d）" % MAX_MARKS, 400)
        marks.append(item)
        data.update({"schema": SCHEMA, "pdf": _norm_rel(rel), "sha256": _sha256(rel),
                     "revision": int(data.get("revision") or 0) + 1,
                     "updated": item["updated"], "marks": marks})
        _write(path, data)
    return {"revision": data["revision"], "mark": item}


def update(rel: str, mark_id: str, patch: dict, expected_revision=None) -> dict:
    path = marks_path(rel)
    pdf_path(rel)
    mid = str(mark_id or "").strip()
    if not _ID_RE.match(mid):
        raise MarksError("bad_mark", "非法批注 id", 400)
    with _file_lock(path):
        data = _read_file(path) or _empty(rel)
        _check_revision(data, expected_revision)
        hit = next((m for m in (data.get("marks") or []) if isinstance(m, dict) and m.get("id") == mid), None)
        if hit is None:
            raise MarksError("not_found", "批注不存在", 404)
        if "color" in patch:
            color = str(patch.get("color") or "").strip().lower()
            if color in PALETTE:
                hit["color"] = color
        if "comment" in patch:
            hit["comment"] = str(patch.get("comment") or "")[:MAX_COMMENT]
        if "quote" in patch:
            hit["quote"] = str(patch.get("quote") or "")[:MAX_QUOTE]
        hit["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        data["revision"] = int(data.get("revision") or 0) + 1
        data["updated"] = hit["updated"]
        _write(path, data)
    return {"revision": data["revision"], "mark": hit}


def delete(rel: str, mark_id: str, expected_revision=None) -> dict:
    path = marks_path(rel)
    pdf_path(rel)
    mid = str(mark_id or "").strip()
    with _file_lock(path):
        data = _read_file(path) or _empty(rel)
        _check_revision(data, expected_revision)
        before = len(data.get("marks") or [])
        data["marks"] = [m for m in (data.get("marks") or []) if not (isinstance(m, dict) and m.get("id") == mid)]
        if len(data["marks"]) == before:
            raise MarksError("not_found", "批注不存在", 404)
        data["revision"] = int(data.get("revision") or 0) + 1
        data["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        _write(path, data)
    return {"revision": data["revision"], "deleted": mid}


def stats(rel: str) -> dict:
    data = load(rel)
    by_page: dict = {}
    for m in data.get("marks") or []:
        if isinstance(m, dict):
            p = int(m.get("page") or 0)
            by_page[p] = by_page.get(p, 0) + 1
    return {"count": len(data.get("marks") or []), "pages": by_page,
            "revision": data.get("revision"), "stale": data.get("stale", False)}