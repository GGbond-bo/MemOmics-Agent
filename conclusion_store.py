# -*- coding: utf-8 -*-
"""L0 结论注册表 + L2 记忆分配（2026-08-31）。

设计对齐 DSH 的上下文分层：
  L0 结论注册表（新建）：每轮结束自动沉淀「关键结论/已解决错误/决策」到
      results/<sid>/.memory/conclusions.md —— 这是"下一轮不会忘"的确定性来源。
  L1/L2 注入：read_conclusions 给最近 20 条（cap 4k 字符），配合
      _build_recent_turns_digest（最近 QA）一起进上下文。
  不记：原始工具输出/日志/中间探索/重复内容 —— 一律不入注册表。
"""
import hashlib
import os
import re
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
_MAX_ENTRIES = 100
_MAX_LINE = 200
_TS_FMT = "%H:%M:%S"

# 分类关键词（含否定先排除）
_FIX_KW = ("修复", "根因", "已解决", "解决了", "成功修复", "已修复", "错误原因", "问题出在")
_CONC_KW = ("结论", "发现", "这说明", "结果表明", "确认了", "确认：", "证据", "验证通过", "结果是", "说明：")
_DEC_KW = ("决定", "采用", "改为", "换用", "选用", "定为")
_NEG_KW = ("没有解决", "未解决", "未修复", "没有结论", "无法确定", "还不确定", "未见")


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


def _clean_line(raw):
    raw = str(raw or "").strip()
    raw = re.sub(r"^#{1,6}\s*", "", raw)
    raw = re.sub(r"^[-*+]\s*", "", raw)
    raw = re.sub(r"^\d+[.、)]\s*", "", raw)
    raw = raw.replace("**", "").replace("\n", " ").strip()
    return raw


def _hash(line):
    return hashlib.md5(line.encode("utf-8", "ignore")).hexdigest()[:12]


def _entry(ts, kind, text):
    return f"- [{ts}] [{kind}] {text}"


def append_conclusions(session, lines, extra_kind=None):
    """追加注册表条目（去重 + 上限 100，保留最新）。返回新增条目数。"""
    if not lines:
        return 0
    p = conclusions_path(session)
    if p is None:
        return 0
    with _LOCK:
        existing = []
        try:
            if p.exists():
                existing = p.read_text(encoding="utf-8").splitlines()
        except Exception:
            existing = []
        hashes = set()
        for ln in existing:
            m = re.match(r"- \[(.*?)\] \[([^\]]+)\] (.*)$", ln)
            if m:
                hashes.add(_hash(m.group(3)))
        ts = time.strftime(_TS_FMT)
        added = 0
        for it in lines:
            if isinstance(it, str):
                kind, text = extra_kind or "结论", it
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
            existing.append(_entry(ts, kind, text))
            hashes.add(_hash(text))
            added += 1
        # 只保留最新 _MAX_ENTRIES
        if len(existing) > _MAX_ENTRIES:
            existing = existing[-_MAX_ENTRIES:]
        try:
            p.write_text("\n".join(existing) + "\n", encoding="utf-8")
        except Exception:
            pass
        return added


def read_conclusions(session, limit=20, max_chars=4000):
    """读取最近 limit 条结论（L1/L2 注入用），返回 text 或 ''. """
    p = conclusions_path(session)
    if p is None or not p.exists():
        return ""
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    # 去掉可能的最旧倒序？文件按追加顺序，latest 在尾部 → 取尾部
    keep = [ln for ln in lines if ln.startswith("- [")]
    keep = keep[-limit:]
    if not keep:
        return ""
    text = "\n".join(keep)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def extract_turn_conclusions(user_text, assistant_text, tool_summary=""):
    """从本轮"用户问题 + 最终回复"提取 L0 条目（纯启发式，不调 LLM）。

    Returns list of (kind, text)，最多 5 条。负向/无关/超短行不做结论。
    """
    out = []
    seen = set()
    corpus = str(assistant_text or "")
    if not corpus.strip():
        return out
    for raw in corpus.splitlines():
        line = _clean_line(raw)
        if not line or len(line) < 8:
            continue
        low = line.lower()
        if any(k in low for k in _NEG_KW):
            continue
        kind = None
        if any(k in line for k in _FIX_KW):
            kind = "修复"
        elif any(k in line for k in _DEC_KW):
            kind = "决策"
        elif any(k in line for k in _CONC_KW):
            kind = "结论"
        if kind is None:
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


def build_memory_budget_context(session, user_text="", limit=20, max_chars=4000):
    """L1/L2 注入文本：结论注册表 + （可选）最近轮速览标题。"""
    conc = read_conclusions(session, limit=limit, max_chars=max_chars)
    if not conc:
        return ""
    return ("## 会话结论注册表（L0/L1 · 最近的结论/修复/决策，可复用，勿重跑）\n"
            + conc + "\n"
            "【规则】以上是已经确认/沉淀过的事实：已被解决的错误不要再次提起；"
            "已给出的结论直接作为背景复用；与本轮冲突时以本轮用户消息为准。")
