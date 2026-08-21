# -*- coding: utf-8 -*-
"""MemOmics -> MiMo-Code 上下文架构迁移（2026-08-21，P1-P5）。

P1 单一上下文边界 usable()：模型硬上限 - (压缩缓冲 + 输出预留)；按模型/环境可设 max_context
P2 独立 writer（后台线程 + LLM §1-§11 模板）写 checkpoint 落盘；主 Agent 不自维护记忆
P3 四层记忆：会话锚点/REQUIREMENTS(Session+Project) + MEMORY.md(Global) + state.db(History)；
   召回用 memory_store FTS5；每个结构化文件单一写者（文件头 writer 字段 + 写锁 + 路径守卫）
P4 Rebuild 分段预算：任务->最近用户原话->checkpoint->项目->全局->scripts 索引，每段独立 cap
P5 增量压缩：只摘"上次 checkpoint(边界 upto_count) 之后"的新片段，并与旧摘要合并

设计要点：所有 LLM 调用可通过 llm_fn 注入（离线单测 monkeypatch）；任何异常 fail-open
回确定性摘要/原历史，绝不影响主流程。
"""

import os
import re
import json
import time
import threading

# ── P1 预算 ─────────────────────────────────────────────
MODEL_CONTEXT_WINDOW = {
    "deepseek-v4-pro": 1_000_000,
    "deepseek-v4-flash": 1_000_000,
}
DEFAULT_CONTEXT_WINDOW = 1_000_000
DEFAULT_OUTPUT_TOKENS = 8192
COMPACTION_BUFFER = 4096


def model_context_window(model: str = "") -> int:
    w = MODEL_CONTEXT_WINDOW.get(model or "")
    if not w:
        try:
            w = int(os.environ.get("MEMOMICS_CONTEXT_WINDOW", DEFAULT_CONTEXT_WINDOW))
        except Exception:
            w = DEFAULT_CONTEXT_WINDOW
    return max(1024, w)


def _coerce_max_context(v):
    """把任意输入(max_context)规范化为 int 或 None/0（容忍 str/bytes/float/NaN/畸形）。"""
    if v is None:
        return 0
    try:
        if isinstance(v, float) and v != v:  # NaN
            return 0
        n = int(v) if not isinstance(v, str) else int(float(v.strip() or "0"))
        return n
    except Exception:
        return 0


def compute_usable(model: str = "", max_context=None) -> dict:
    """MiMo overflow.ts 语义：effective=min(hard, configured)；usable=effective-reserved。"""
    hard = model_context_window(model)
    reserved = COMPACTION_BUFFER + DEFAULT_OUTPUT_TOKENS
    if max_context is None:
        try:
            max_context = int(os.environ.get("MEMOMICS_MAX_CONTEXT", "0") or "0")
        except Exception:
            max_context = 0
    max_context = _coerce_max_context(max_context)
    effective, source = hard, "model"
    if max_context and 0 < max_context <= hard and max_context > reserved:
        effective, source = max_context, "config"
    usable = max(0, effective - reserved)
    return {"hard": hard, "effective": effective, "usable": usable,
            "reserved": reserved, "source": source}


def token_estimate(m) -> int:
    c = m.get("content") if isinstance(m, dict) else ""
    if not isinstance(c, str) or not c:
        return 4
    return max(4, len(c) // 2) + 4


def measure(history) -> int:
    return sum(token_estimate(m) for m in history)


# ── 单写者 + 路径守卫（P3）──────────────────────────────
_WRITE_LOCKS: dict = {}
_GC_LOCK = threading.Lock()


def _lock_for(path: str) -> threading.Lock:
    with _GC_LOCK:
        return _WRITE_LOCKS.setdefault(path, threading.Lock())


def path_guard(path: str, allowed_roots):
    """只允许写在白名单根目录下（仿 MiMo memory-path-guard）。"""
    p = os.path.normpath(os.path.abspath(path)).rstrip(os.sep)
    for r in allowed_roots:
        rp = os.path.normpath(os.path.abspath(r)).rstrip(os.sep)
        if p == rp or p.startswith(rp + os.sep):
            return p
    raise ValueError(f"memory write blocked: {path} outside allowed roots {allowed_roots}")


# ── 会话结构 ─────────────────────────────────────────────
def _results_dir(session) -> str:
    return session.get("results_dir") or ""


def memory_root(session) -> str:
    rd = _results_dir(session)
    return os.path.join(rd, ".memory") if rd else ""


def checkpoints_dir(session) -> str:
    return os.path.join(memory_root(session), "checkpoints") if memory_root(session) else ""


def requirements_path(session) -> str:
    rd = _results_dir(session)
    return os.path.join(rd, "REQUIREMENTS.md") if rd else ""


# ── P2 writer：§1-§11 checkpoint ─────────────────────────
CHECKPOINT_HEADER_TMPL = "<!-- memomics-checkpoint v1 | writer: context-arch.writer | upto_count: {upto} | created: {ts} -->"

CHECKPOINT_PROMPT = (
    "You are the memory-writer for a scientific research agent. Condense the conversation span BELOW "
    "into a durable structured checkpoint so a later turn resumes with no loss of essential context. "
    "If a previous checkpoint is included, merge it: keep still-true facts, drop stale ones.\n"
    "Output EXACTLY these 11 Markdown sections, in order, terse bullets:\n"
    "## §1 Active intent\n## §2 Next concrete action\n## §3 Directives (user requirements)\n"
    "## §4 Task tree (task_plan)\n## §5 Current work\n## §6 Files and code sections\n"
    "## §7 Discovered knowledge (cross-task)\n## §8 Errors and fixes\n## §9 Live resources\n"
    "## §10 Design decisions and discussion outcomes\n## §11 Open notes\n"
    "Write concise prose. Preserve exact file paths, commands, error strings, identifiers, numbers, "
    "user requirements and file paths verbatim. Do NOT mention this summarization request.\n"
    "Conversation span:\n{span}\n"
    "Previous checkpoint (merge, do not copy verbatim):\n{prior}\n"
)


def _digest_fallback(session, span_text: str) -> str:
    """LLM 不可用时的确定性最小摘要（全 § 段保形，内容从 REQUIREMENTS/锚点就近取）。"""
    rd = _results_dir(session)
    req = ""
    p = requirements_path(session)
    if p and os.path.isfile(p):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                req = " | ".join(l.strip() for l in f if l.strip())[:800]
        except Exception:
            req = ""
    n = len(span_text)
    return (
        f"## §1 Active intent\n- 早期对话已折叠(确定性回退摘要)。\n"
        f"## §5 Current work\n- 该折叠片段约 {n} 字符；详情见原始 state.db 全量记录。\n"
        f"## §3 Directives (user requirements)\n- {req or '(none)'}\n"
        f"## §6 Files and code sections\n- 会话锚点/REQUIREMENTS/scripts 详见会话目录。\n"
        f"## §11 Open notes\n- (none)\n"
    )


def _latest_checkpoint(session):
    d = checkpoints_dir(session)
    if not d or not os.path.isdir(d):
        return None
    fs = sorted(f for f in os.listdir(d) if f.endswith(".md"))
    if not fs:
        return None
    return os.path.join(d, fs[-1])


def read_checkpoint(session) -> dict:
    """读"最新且有实质内容"的 checkpoint（upto 边界 + 文本）。

    (2026-08-21 修正) 只在 checkpoints/ 里取"最新"文件的旧逻辑会被空壳/占位结果
    （如 writer 空返回、测试占位）顶掉真正含 §1-§11 的好摘要：优先选文件大小≥400B 的最新档，
    都没有才退回最新文件。
    """
    d = checkpoints_dir(session)
    if not d or not os.path.isdir(d):
        return {"text": "", "upto": 0, "path": None}
    try:
        fs = sorted(f for f in os.listdir(d) if f.endswith(".md"))
    except Exception:
        return {"text": "", "upto": 0, "path": None}
    if not fs:
        return {"text": "", "upto": 0, "path": None}
    paths = [os.path.join(d, f) for f in fs]  # fs 已按文件名(时间序)排序
    pick = None
    for p in reversed(paths):
        try:
            if os.path.getsize(p) >= 400:
                pick = p
                break
        except Exception:
            continue
    if pick is None:
        pick = paths[-1]
    try:
        with open(pick, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return {"text": "", "upto": 0, "path": None}
    m = re.search(r"upto_count:\s*(\d+)", text[:400])
    upto = int(m.group(1)) if m else 0
    return {"text": text, "upto": upto, "path": pick}


def write_checkpoint(session, upto: int, text: str) -> str:
    """单一写者写 checkpoint 文件：写锁 + 路径守卫 + 文件头 + 数量上限(保留 4 个)。"""
    d = checkpoints_dir(session)
    if not d:
        return ""
    path_guard(d, [_results_dir(session)])
    os.makedirs(d, exist_ok=True)
    # (2026-08-21 压测发现) 文件名只用 int(time) 会在同一秒内互相覆盖 → 加毫秒+随机后缀防碰撞
    p = os.path.join(d, f"checkpoint-{int(time.time()*1000)}-{os.urandom(3).hex()}.md")
    header = CHECKPOINT_HEADER_TMPL.format(upto=int(upto), ts=int(time.time()))
    with _lock_for(p):
        with open(p, "w", encoding="utf-8") as f:
            f.write(header + "\n\n" + (text or "(none)"))
    try:
        fs = sorted(x for x in os.listdir(d) if x.endswith(".md"))
        for old in fs[:-4]:
            try:
                os.remove(os.path.join(d, old))
            except Exception:
                pass
    except Exception:
        pass
    return p


def run_writer(session, span_text: str, prior_text: str, upto: int, llm_fn) -> str:
    """执行一次 writer（LLM §1-§11 或确定性回退），写好 checkpoint 返回路径。"""
    llm = llm_fn if callable(llm_fn) else None
    if not llm:
        return write_checkpoint(session, upto, _digest_fallback(session, span_text or ""))
    prompt = CHECKPOINT_PROMPT.format(span=(span_text or "")[:40000], prior=(prior_text or "")[:8000])
    try:
        out = llm(prompt)
        return write_checkpoint(session, upto, (out or "").strip()[:30000])
    except Exception:
        return write_checkpoint(session, upto, _digest_fallback(session, span_text or ""))


# ── P5 增量边界 ─────────────────────────────────────────
def new_span(history, upto: int, tail_len: int):
    """返回 (新片段, 新 upto)：只摘 ``upto .. len-tail`` —— 上次摘要之后的片段。

    upto 表示已覆盖的头部消息条数；tail_len 是保留的逐字尾窗。"""
    if not history:
        return [], len(history)
    n = max(0, int(upto))
    stop = max(0, len(history) - (tail_len or 0)) if tail_len else len(history)
    if n >= stop:
        return [], stop
    return history[n:stop], stop


# ── P4 Rebuild 分段预算 ─────────────────────────────────
def _env_int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return default


REBUILD_CAPS = {
    "task_plan": _env_int("MEMOMICS_CAP_TASKPLAN", 6000),
    "checkpoint": _env_int("MEMOMICS_CAP_CHECKPOINT", 11000),
    "req": _env_int("MEMOMICS_CAP_REQUIREMENTS", 4000),
    "global": _env_int("MEMOMICS_CAP_GLOBAL", 6000),
    "scripts": _env_int("MEMOMICS_CAP_SCRIPTS", 2000),
    "recent_tail": _env_int("MEMOMICS_CAP_TAIL", 16000),
    "reminder": 600,
}


def _cut(text, cap):
    if text is None:
        return ""
    if not isinstance(text, str):
        try:
            text = str(text)  # (fuzz 抓出) bytes/number/dict 等脏值先转 str，防 str+bytes 崩
        except Exception:
            return ""
    return text[: max(0, int(cap))]


def build_extras(session) -> dict:
    """项目记忆(REQUIREMENTS) + scripts 索引 + 全局记忆(MEMORY.md/USER.md)。"""
    rd = _results_dir(session)
    req = ""
    p = requirements_path(session)
    if p and os.path.isfile(p):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                lines = [l.strip() for l in f if l.strip()]
            paths = [l for l in lines if re.search(r"[A-Za-z]:[/\\]", l)]
            others = [l for l in lines if l not in paths]
            seen, sel = set(), []
            for l in (paths[-6:] + others[-6:]):
                if l not in seen:
                    seen.add(l)
                    sel.append(l)
            req = "\n".join(sel[-6:])
        except Exception:
            req = ""
    scripts = ""
    sd = os.path.join(rd, "scripts") if rd else ""
    if sd and os.path.isdir(sd):
        try:
            fs = sorted(f for f in os.listdir(sd) if os.path.isfile(os.path.join(sd, f)))[-5:]
            if fs:
                scripts = "、".join(fs)
        except Exception:
            pass
    gm = ""
    try:
        hh = os.environ.get("HERMES_HOME", "")
        for name in ("MEMORY.md", "USER.md"):
            mp = os.path.join(hh, "memories", name) if hh else ""
            if mp and os.path.isfile(mp):
                with open(mp, encoding="utf-8", errors="replace") as f:
                    gm = (gm + "\n" + f.read()) if gm else f.read()
    except Exception:
        pass
    return {"requirements": req, "scripts": scripts, "global_memory": gm}


def rebuild_context(session, tail_messages, checkpoint_text, extras, caps=None) -> list:
    """P4 分段注入（顺序对齐 MiMo rebuild）：任务→checkpoint→项目→全局→scripts→提醒，再逐字尾窗。"""
    c = dict(REBUILD_CAPS)
    if caps:
        c.update(caps)
    rd = _results_dir(session)
    blocks = []
    tp = ""
    p = os.path.join(rd, "task_plan.md") if rd else ""
    if p and os.path.isfile(p):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                tp = f.read()
        except Exception:
            tp = ""
    if tp.strip():
        blocks.append(("[任务清单(task_plan)]\n" + _cut(tp, c["task_plan"])))
    if checkpoint_text and checkpoint_text.strip():
        blocks.append("[会话检查点 · 跨压缩持久]\n" + _cut(checkpoint_text, c["checkpoint"]))
    if extras.get("requirements"):
        blocks.append("[持久用户要求/路径(REQUIREMENTS)]\n" + _cut(extras["requirements"], c["req"]))
    if extras.get("global_memory"):
        blocks.append("[全局记忆]\n" + _cut(extras["global_memory"], c["global"]))
    if extras.get("scripts"):
        blocks.append("[会话脚本索引(scripts/)]\n" + _cut(extras["scripts"], c["scripts"]))
    blocks.append("[提示] 以上为早期对话的结构化摘要；紧接其后的消息是最近真实对话，请基于它们继续，不必复述摘要。")
    out = [{"role": "system", "content": b} for b in blocks]
    tail = list(tail_messages or [])
    tc = int(c.get("recent_tail", 16000))
    while tail and measure(tail) > tc and len(tail) > 1:
        tail = tail[1:]
    return out + tail


# ── P3 FTS 召回 ─────────────────────────────────────────
def fts_recall(query: str, limit: int = 5) -> str:
    """memory_store FTS5 召回（中文按字符拆词 + BM25 排序的兜底实现）。"""
    try:
        from memomics.bio_tools import memory_bridge
        rows = memory_bridge.search_memory(query or "", "", limit)
        if not rows:
            return ""
        lines = ["[相关历史记忆 · FTS 召回]"]
        for r in rows:
            lines.append(f"- {str(r.get('content', ''))[:110]}")
        return "\n".join(lines)
    except Exception:
        return ""


# ── P1-P5 主编排 ────────────────────────────────────────
_WRITER_STATE: dict = {}


def _maybe_spawn_writer(session, history, ck, span, new_upto, llm_fn):
    sid = session.get("id", "")
    st = _WRITER_STATE.setdefault(sid, {"lock": threading.Lock(), "last": 0.0})
    now = time.time()
    if ck.get("path") and now - st["last"] < 300:
        return
    if not st["lock"].acquire(blocking=False):
        return

    def job():
        try:
            span_text = "\n".join(m.get("content", "") or "" for m in span)
            run_writer(session, span_text, ck.get("text", "") or "", new_upto, llm_fn)
        except Exception:
            pass
        finally:
            try:
                st["lock"].release()
            except Exception:
                pass

    st["last"] = now
    try:
        threading.Thread(target=job, daemon=True).start()
    except Exception:
        try:
            st["lock"].release()
        except Exception:
            pass


def memomics_replay(session, history, llm_fn=None, budget=None, tail_len=None, caps=None):
    """P1-P5 主入口：返回发给模型的重放消息（超预算时：后台 writer + 分段 rebuild；fail-open）。"""
    try:
        if not history:
            return []
        model = (session.get("model_config") or {}).get("model") or ""
        b = budget or compute_usable(model=model)
        total = measure(history)
        tlen = tail_len or _env_int("MEMOMICS_ROLLUP_TAIL", 40)
        if tlen <= 0 or len(history) <= tlen + 4:
            return history
        if total < b["usable"]:
            return history
        ck = read_checkpoint(session)
        span, new_upto = new_span(history, ck["upto"], tlen)
        # P5 单调性：只有存在"上次摘要之后的新片段"才重写 checkpoint。
        # 历史条数波动（(b) 剥离脚手架/尾窗变化）时 stop 可能 < 已存 upto ——
        # 若照旧重写会把边界回退并覆盖已合并摘要（记忆劣化 + 白烧一次 LLM）。
        if span:
            _maybe_spawn_writer(session, history, ck, span, new_upto, llm_fn)
        ck2 = read_checkpoint(session)
        ctext = ck2.get("text", "") or ""
        if not ctext.strip():
            ctext = _digest_fallback(session, "")
        tail = history[-tlen:]
        extras = build_extras(session)
        return rebuild_context(session, tail, ctext, extras, caps=caps)
    except Exception:
        return history
