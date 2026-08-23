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


# ── 2026-08-22 加固：checkpoint 质量校验 ───────────────────
_CHECKPOINT_SECTIONS = ("§1", "§2", "§3", "§4", "§5", "§6", "§7", "§8", "§9", "§10", "§11")


def _checkpoint_quality(text: str) -> dict:
    """checkpoint 质量评分（加固核心）：§ 段覆盖数 + 有效内容 + 空壳惩罚。

    返回 {score, sections, chars}。score 范围 0-100：
    - 每覆盖一个 § 段 +8 分（§1-§11 满 88 分）
    - 段内有实质内容（非 "- x" 空壳）再加分
    - 空壳（总长 <80 或只有 "- x"）直接 0 分
    """
    t = (text or "").strip()
    if len(t) < 80:
        return {"score": 0, "sections": 0, "chars": len(t)}
    covered = [s for s in _CHECKPOINT_SECTIONS if f"## {s}" in t]
    # 空壳行检测："- x" / "-" 这种占位
    shell_lines = sum(1 for ln in t.splitlines() if ln.strip() in ("- x", "-", "x", "(none)"))
    n_sections = len(covered)
    score = n_sections * 8
    # 有实质内容的段数（按段块长度粗略判断）
    for s in covered:
        idx = t.find(f"## {s}")
        nxt = len(t)
        for s2 in covered:
            i2 = t.find(f"## {s2}", idx + 4)
            if 0 < i2 < nxt:
                nxt = i2
        seg = t[idx:nxt]
        if len(seg.strip()) > 40:
            score += 2
    # 空壳惩罚
    if shell_lines >= max(1, n_sections):
        score = min(score, 10)
    return {"score": min(score, 100), "sections": n_sections, "chars": len(t)}


def _best_checkpoint(session):
    """按质量分选最优 checkpoint 文件（加固：不再只看 400B，避免空壳顶掉好档）。"""
    d = checkpoints_dir(session)
    if not d or not os.path.isdir(d):
        return None
    try:
        fs = sorted(f for f in os.listdir(d) if f.endswith(".md"))
    except Exception:
        return None
    if not fs:
        return None
    best, best_q = None, {"score": -1, "sections": 0, "chars": 0}
    for f in fs:
        p = os.path.join(d, f)
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except Exception:
            continue
        q = _checkpoint_quality(text)
        if q["score"] > best_q["score"]:
            best, best_q = p, q
    return {"path": best, **best_q} if best else None


def read_checkpoint(session) -> dict:
    """读"最优" checkpoint（upto 边界 + 文本）。

    2026-08-22 加固：改用 _best_checkpoint 按质量分选（§ 段覆盖优先），
    空壳/占位档不会再顶掉含实质内容的摘要。
    """
    d = checkpoints_dir(session)
    if not d or not os.path.isdir(d):
        return {"text": "", "upto": 0, "path": None}
    best = _best_checkpoint(session)
    if not best or not best["path"]:
        return {"text": "", "upto": 0, "path": None}
    try:
        with open(best["path"], encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return {"text": "", "upto": 0, "path": None}
    m = re.search(r"upto_count:\s*(\d+)", text[:400])
    upto = int(m.group(1)) if m else 0
    return {"text": text, "upto": upto, "path": best["path"]}


def write_checkpoint(session, upto: int, text: str) -> str:
    """单一写者写 checkpoint 文件：写锁 + 路径守卫 + 文件头 + 数量上限(保留 4 个)。

    2026-08-22 加固：劣质输出（空壳/§ 段过少）拒绝落盘——
    不覆盖现有更优档，避免"空壳顶掉好摘要"。
    """
    d = checkpoints_dir(session)
    if not d:
        return ""
    path_guard(d, [_results_dir(session)])
    # 质量门禁：空壳/无实质 § 段 → 拒绝写入（保留既有档）
    q = _checkpoint_quality(text or "")
    best = _best_checkpoint(session)
    # 2026-08-22 加固：新档质量必须 ≥ 既有最优档才允许写入（防半截顶掉完整档）。
    # 严格小于才拒绝：同分（如 100 满分的更新档）允许写入——upto 边界前移仍有价值。
    if best and best.get("score", 0) >= 30 and q["score"] < best["score"]:
        return best["path"] or ""
    if q["score"] < 30:
        # 无既有档时首个写入（兜底留痕）；有更优档则拒绝（上面已处理）
        if best and best.get("score", 0) >= 30:
            return best["path"] or ""
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


def _sections_fallback(session, span_text: str) -> str:
    """确定性补全段：LLM checkpoint 缺 §7-§11 时，从 REQUIREMENTS/锚点/span 就近提取补全。

    加固目标：结论/知识/决策（§7/§8/§10）即使 LLM 截断也不丢——从
    已有持久记忆（REQUIREMENTS）+ 最近对话内容提取可验证信息。
    """
    parts = []
    rd = _results_dir(session)
    req = ""
    p = requirements_path(session)
    if p and os.path.isfile(p):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                req = " | ".join(l.strip() for l in f if l.strip())[:600]
        except Exception:
            req = ""
    if req:
        parts.append(f"## §3 Directives (user requirements)\n- {req}")
    # 从 span 提取用户消息（诉求）+ 工具痕迹，作为 §5/§6 的兜底
    user_msgs = []
    tool_hints = []
    for m in (span_text or "").split("\n"):
        m = m.strip()
        if not m:
            continue
        if len(m) > 20 and ("E:/" in m or "E:\\" in m or "C:/" in m or "C:\\" in m):
            tool_hints.append(m[:120])
        if m.startswith("user") or m.startswith("用户") or m.startswith("Human"):
            user_msgs.append(m[:150])
    if user_msgs:
        parts.append(f"## §1 Active intent\n- {'；'.join(user_msgs[-3:])}")
    if tool_hints:
        parts.append(f"## §6 Files and code sections\n- " + "\n- ".join(tool_hints[-5:]))
    parts.append("## §11 Open notes\n- 该折叠片段约 "
                 f"{len(span_text or '')} 字符；完整轨迹见 state.db（压缩永不丢证据）。")
    return "\n\n".join(parts)


def _merge_sections(llm_text: str, fallback_text: str, prior_text: str = "") -> str:
    """把 fallback/prior 中缺失的 § 段补进 LLM 输出（加固：§7-§11 缺失时补全）。

    - fallback_text: 确定性兜底段（REQUIREMENTS/锚点/span 提取）
    - prior_text: 上一版 checkpoint 文本（旧知识 §7/§8/§10 在 LLM 截断时保留）
    """
    if not llm_text or not llm_text.strip():
        return fallback_text
    out = llm_text.rstrip()
    # 找出 LLM 输出已有的 § 段
    have = set()
    for s in _CHECKPOINT_SECTIONS:
        if f"## {s}" in out:
            have.add(s)
    if len(have) >= 9:
        return out
    # 从 fallback + prior 补缺失段（prior 优先——它是历史确认过的知识）
    missing_blocks = []
    for src in (prior_text or "", fallback_text or ""):
        if not src:
            continue
        for s in _CHECKPOINT_SECTIONS:
            if s in have:
                continue
            idx = src.find(f"## {s}")
            if idx < 0:
                continue
            nxt = len(src)
            for s2 in _CHECKPOINT_SECTIONS:
                i2 = src.find(f"## {s2}", idx + 4)
                if 0 < i2 < nxt:
                    nxt = i2
            blk = src[idx:nxt].strip()
            if len(blk) > 30:
                missing_blocks.append(blk)
                have.add(s)  # 已补，不再重复
    if missing_blocks:
        out += "\n\n" + "\n\n".join(missing_blocks)
    return out


def run_writer(session, span_text: str, prior_text: str, upto: int, llm_fn) -> str:
    """执行一次 writer（LLM §1-§11 或确定性回退），写好 checkpoint 返回路径。

    2026-08-22 加固：
    - LLM 输出缺 § 段 → 用 _sections_fallback 补全（§7 知识/§8 错误/§10 决策不因截断丢失）
    - 劣质结果由 write_checkpoint 质量门禁拒绝（不覆盖更优档）
    """
    llm = llm_fn if callable(llm_fn) else None
    if not llm:
        return write_checkpoint(session, upto, _digest_fallback(session, span_text or ""))
    prompt = CHECKPOINT_PROMPT.format(span=(span_text or "")[:40000], prior=(prior_text or "")[:8000])
    try:
        out = (llm(prompt) or "").strip()
        if not out:
            # 空输出 → 占位（write_checkpoint 质量门禁会拒绝覆盖更优档，保留原行为语义）
            return write_checkpoint(session, upto, "(none)")
        merged = _merge_sections(out,
                                 _sections_fallback(session, span_text or ""),
                                 prior_text=prior_text or "")
        return write_checkpoint(session, upto, merged[:30000])
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
    blocks.append("[提示] 以上为早期对话的结构化摘要；紧接其后的消息是最近真实对话，请基于它们继续，不必复述摘要。"
                  "如需早期细节（具体数字/原话/中间结果），用 session_search 全文召回："
                  "session_search(query=关键词) → 找到 message_id → "
                  "session_search(session_id=..., around_message_id=<id>, window=5) 拉逐字上下文，禁止凭摘要编造。")
    out = [{"role": "system", "content": b} for b in blocks]
    tail = list(tail_messages or [])
    tc = int(c.get("recent_tail", 16000))
    while tail and measure(tail) > tc and len(tail) > 1:
        tail = tail[1:]
    return out + tail


# ── P3 FTS 召回 ─────────────────────────────────────────
def _cjk_tokens(text):
    """中文词级切分：优先 jieba（>1 字词），回退 2-gram。"""
    try:
        import jieba
        toks = [w for w in jieba.lcut(text or "") if w.strip() and len(w.strip()) > 1]
        if toks:
            return toks
    except Exception:
        pass
    s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", text or "")
    if not s:
        return []
    return [s[i:i + 2] for i in range(max(0, len(s) - 1))]


def _facts_db_path():
    hh = os.environ.get("HERMES_HOME", "")
    p = os.path.join(hh, "memory_store.db") if hh else ""
    return p if p and os.path.isfile(p) else ""


def recall_hybrid(query, limit=5, db_path=None):
    """中文词级召回（B，2026-08-21）：jieba(或 2-gram) 分词 → facts 表粗筛 → 词交并×trust 打分。

    解决 FTS5 unicode61 对中文不分词、MATCH 恒空命中的问题。db_path 可注入（单测用临时库）。
    返回格式与 fts_recall 一致：`[相关历史记忆 · 词级召回]` + 行，无命中返回 ""。"""
    try:
        p = db_path or _facts_db_path()
        if not p:
            return ""
        q = set(_cjk_tokens(query or ""))
        if not q:
            return ""
        import sqlite3
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=8)
        try:
            cond = " OR ".join("content LIKE ?" for _ in q)
            rows = conn.execute(
                f"SELECT content, trust_score FROM facts WHERE ({cond}) LIMIT 60",
                tuple(f"%{t}%" for t in q)).fetchall()
        finally:
            conn.close()
        scored = []
        for content, trust in rows:
            rw = set(_cjk_tokens(content or ""))
            inter = len(q & rw)
            if not inter:
                continue
            jac = inter / (len(q | rw) or 1)
            scored.append((jac * float(trust or 0.5), content))
        scored.sort(key=lambda x: -x[0])
        top = scored[:limit]
        if not top:
            return ""
        lines = ["[相关历史记忆 · 词级召回]"]
        for _, content in top:
            lines.append(f"- {str(content)[:110]}")
        return "\n".join(lines)
    except Exception:
        return ""


def fts_recall(query: str, limit: int = 5, db_path=None) -> str:
    """记忆召回（P3）：英文/数字优先 FTS5（BM25）；中文/空命中走词级召回（jieba/2-gram）。"""
    try:
        from memomics.bio_tools import memory_bridge
        rows = memory_bridge.search_memory(query or "", "", limit)
        if rows:
            lines = ["[相关历史记忆 · FTS 召回]"]
            for r in rows:
                lines.append(f"- {str(r.get('content', ''))[:110]}")
            return "\n".join(lines)
    except Exception:
        pass
    return recall_hybrid(query, limit, db_path=db_path)


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


def _aggressive_trigger(session, total, usable):
    """科研交互适配触发（A，2026-08-21）：MiMo 的"窗口占比"触发对 1M 窗口几乎永远不响，
    日常会话只靠逐字重放。这里加两个通道，让机制在科研场景真正上场：
      1) 显式 knob：MEMOMICS_AGGRESSIVE_COMPACT=1 时，历史 >= min(usable, MEMOMICS_AGGRESSIVE_THRESHOLD(默认150K))
      2) 长任务连续运行：自检唤醒计数 >=3 且历史 >=30K → 连续长跑的科研任务提前接管"""
    try:
        if os.environ.get("MEMOMICS_AGGRESSIVE_COMPACT", "0") == "1":
            t = _env_int("MEMOMICS_AGGRESSIVE_THRESHOLD", 150000)
            if total >= min(usable, t):
                return True
        try:
            sc = int(session.get("_self_check_count") or 0)
        except Exception:
            sc = 0
        if sc >= 3 and total >= 30000:
            return True
    except Exception:
        pass
    return False


def memomics_replay(session, history, llm_fn=None, budget=None, tail_len=None, caps=None):
    """P1-P5 主入口：返回发给模型的重放消息（超预算/科研适配触发时：后台 writer + 分段 rebuild；fail-open）。"""
    try:
        if not history:
            return []
        model = (session.get("model_config") or {}).get("model") or ""
        b = budget or compute_usable(model=model)
        total = measure(history)
        tlen = tail_len or _env_int("MEMOMICS_ROLLUP_TAIL", 40)
        if tlen <= 0 or len(history) <= tlen + 4:
            return history
        if total < b["usable"] and not _aggressive_trigger(session, total, b["usable"]):
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
