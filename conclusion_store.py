# -*- coding: utf-8 -*-
"""L0 结论/失败注册表 + L1/L2/L3 索引（2026-08-31 v2）。

新增（用户补充）：
  1. 失败条目 [失败]：MemOmics 尝试过但失败/做不了的必须沉淀，下一轮禁止无脑重试；
  2. L3 索引：每条结论带 [id:N]，可落到 turn_archive/{hash}.md 完整回合详情；
     memory_index.json 记录 id -> kind/text/archive，各层据此对接 L3。
分层：L1/L2=注册表摘要(常驻/近期)；L3=完整回合归档 + state.db 原文。
"""
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
_MAX_ENTRIES = 100
_MAX_LINE = 200
_MAX_ARCHIVES = 50
_TS_FMT = "%H:%M:%S"

_FIX_KW = ("修复", "根因", "已解决", "解决了", "成功修复", "已修复", "错误原因", "问题出在")
_FAIL_KW = ("失败", "做不了", "无法读取", "无法完成", "无法解决", "不能", "不支持", "不可用",
            "死路", "报错", "缺少", "没有安装", "没有解决", "未解决", "无法确定", "没有结论", "还不确定", "不行")
_DEC_KW = ("决定", "采用", "改为", "换用", "选用", "定为")
_CONC_KW = ("结论", "发现", "这说明", "结果表明", "确认了", "确认：", "证据", "验证通过", "结果是", "说明：")


def conclusions_path(session):
    rd = session.get("results_dir") or ""
    if not rd:
        return None
    p = Path(rd) / ".memory" / "conclusions.md"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def archive_dir(session):
    rd = session.get("results_dir") or ""
    if not rd:
        return None
    p = Path(rd) / ".memory" / "turn_archive"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def index_path(session):
    rd = session.get("results_dir") or ""
    if not rd:
        return None
    return Path(rd) / ".memory" / "memory_index.json"


def _clean_line(raw):
    raw = str(raw or "").strip()
    raw = re.sub(r"^#{1,6}\s*", "", raw)
    raw = re.sub(r"^[-*+]\s*", "", raw)
    raw = re.sub(r"^\d+[.、)]\s*", "", raw)
    raw = raw.replace("**", "").replace("\n", " ").strip()
    return raw


def _hash(text):
    return hashlib.md5(text.encode("utf-8", "ignore")).hexdigest()[:12]


def _existing_entries(p):
    try:
        if p and p.exists():
            return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("- [")]
    except Exception:
        pass
    return []


def _next_id(lines):
    mx = 0
    for ln in lines:
        m = re.search(r"\[id:(\d+)\]", ln)
        if m:
            mx = max(mx, int(m.group(1)))
    return mx + 1


def append_conclusions(session, lines):
    """追加注册表条目（去重 + 上限 100，保留最新）。返回新增 id 列表。"""
    if not lines:
        return []
    p = conclusions_path(session)
    if p is None:
        return []
    with _LOCK:
        existing = _existing_entries(p)
        hashes = set()
        for ln in existing:
            m = re.match(r"- \[(.*?)\] \[([^\]]+)\] \[id:(\d+)\] (.*)$", ln)
            if m:
                hashes.add(_hash(m.group(4)))
        nid = _next_id(existing)
        ts = time.strftime(_TS_FMT)
        added_ids = []
        for it in lines:
            if isinstance(it, str):
                kind, text = "结论", it
            elif isinstance(it, (tuple, list)) and len(it) >= 2:
                kind, text = it[0], it[1]
            else:
                continue
            text = _clean_line(text)
            if not text:
                continue
            if len(text) > _MAX_LINE:
                text = text[:_MAX_LINE - 3] + "..."
            if _hash(text) in hashes:
                continue
            existing.append(f"- [{ts}] [{kind}] [id:{nid}] {text}")
            hashes.add(_hash(text))
            added_ids.append(nid)
            nid += 1
        if len(existing) > _MAX_ENTRIES:
            existing = existing[-_MAX_ENTRIES:]
        try:
            p.write_text("\n".join(existing) + "\n", encoding="utf-8")
        except Exception:
            pass
        return added_ids


def read_conclusions(session, limit=20, max_chars=4000):
    p = conclusions_path(session)
    keep = _existing_entries(p)[-limit:] if p else []
    if not keep:
        return ""
    text = "\n".join(keep)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def extract_turn_conclusions(user_text, assistant_text, tool_summary=""):
    """从本轮最终回复提取 L0 条目：修复/失败/决策/结论（纯启发式）。最多 5 条。"""
    out = []
    seen = set()
    corpus = str(assistant_text or "")
    if not corpus.strip():
        return out
    for raw in corpus.splitlines():
        line = _clean_line(raw)
        if not line:
            continue
        kind = None
        if any(k in line for k in _FIX_KW):
            kind = "修复"
        elif any(k in line for k in _FAIL_KW):
            kind = "失败"
        elif any(k in line for k in _DEC_KW):
            kind = "决策"
        elif any(k in line for k in _CONC_KW):
            kind = "结论"
        if kind is None:
            continue
        # 允许短“失败”句（如 做不了/不能/缺依赖），其余仍要求 >=8 字
        if len(line) < 8 and not (kind == "失败" and len(line) >= 4):
            continue
        if _hash(line) in seen:
            continue
        seen.add(_hash(line))
        if len(line) > _MAX_LINE:
            line = line[:_MAX_LINE - 3] + "..."
        out.append((kind, line))
        if len(out) >= 5:
            break
    return out


def archive_turn(session, user_text, assistant_text, tool_summary=""):
    """L3: 完整回合归档 -> turn_archive/{hash}.md；返回路径或空串。"""
    d = archive_dir(session)
    if d is None:
        return ""
    try:
        full = (str(user_text or "") + "\n\n" + str(assistant_text or "") + "\n\n" + str(tool_summary or ""))
        fn = f"turn_{_hash(full)[:10]}.md"
        path = d / fn
        files = sorted(d.glob("turn_*.md"))
        while len(files) >= _MAX_ARCHIVES:
            try:
                files.pop(0).unlink()
            except Exception:
                pass
        path.write_text(
            f"# L3 回合详情\n\n## 用户\n{user_text}\n\n## 回复\n{assistant_text}\n\n## 工具摘要\n{tool_summary}\n",
            encoding="utf-8")
        return str(path)
    except Exception:
        return ""


def link_archive(session, ids, archive_path):
    """把新增 id 与 L3 归档文件写进 memory_index.json。"""
    ip = index_path(session)
    if ip is None or not ids or not archive_path:
        return
    with _LOCK:
        idx = {}
        try:
            if ip.exists():
                idx = json.loads(ip.read_text(encoding="utf-8"))
        except Exception:
            idx = {}
        arch = idx.get("archives") or {}
        for i in ids:
            arch[str(i)] = archive_path
        idx["archives"] = arch
        try:
            ip.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def read_l3_index(session):
    ip = index_path(session)
    if ip is None or not ip.exists():
        return {}
    try:
        return json.loads(ip.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_memory_budget_context(session, user_text="", limit=20, max_chars=4000):
    conc = read_conclusions(session, limit=limit, max_chars=max_chars)
    if not conc:
        return ""
    return ("## 会话结论/失败注册表（L0/L1 · 含 L3 id 索引，可复用，勿重跑）\n"
            + conc + "\n"
            "【规则】[结论]/[修复] 已确认事实直接复用；[失败] 表示该尝试已失败（原因与细节见 [id:N] 或 L3 归档），"
            "除非条件变化（权限/平台/数据到位），不要重复重试；与本轮冲突以本轮为准。")
