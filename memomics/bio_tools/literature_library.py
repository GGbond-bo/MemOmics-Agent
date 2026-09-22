# -*- coding: utf-8 -*-
"""literature_library.py — 本地文献库：导入用户已有的 PDF + 元数据标识（批F，2026-08-16）。

用户问题：文献库"怎么算"——不只是 agent 自己下载的 PDF，用户自己下载好的文献也能导入。
本模块提供：
- import_pdfs(paths): 导入本地 PDF（文件或目录）到全局文献库 hermes_home/papers/
  - 自动提取元数据：DOI 正则 → Crossref 反查（期刊/文章名/作者/年份）
  - 标识字段：journal(期刊) / title(文章名) / authors / year / doi
    / downloaded_at(下载日期=原文件修改时间) / imported_at(导入时间) / sha256
  - 去重：同 sha256 或同 basename+size 跳过
  - 同步注册进全局引用库（BibTeX/RIS，save_reference global_lib）
- list_library(): 列出全部文献（用户导入 + agent 下载的 work/papers 索引合并）
"""
import difflib
import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("memomics.literature_library")

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
_DOI_JUNK = ("wileyonlinelibrary", "sciencedirect", "tandfonline", "onlinelibrary",
             "springer", "elsevier", "wiley", "logosociety", "societylogo",
             "logo", "academic", ".com", ".pdf", "pdf")
_CROSSREF_UA = {"User-Agent": "MemOmics-Library/1.1 (mailto:research@localhost)"}


def _clean_doi(raw: str) -> str:
    """清洗 PDF 文本里抓到的 DOI：去尾部标点与出版商水印（WILEY/logo 等）。

    例: "10.1111/acel.70485WILEYlogoSocietylogo" → "10.1111/acel.70485"
    """
    s = (raw or "").strip().rstrip(".,;)]}>\"'")
    while s:
        low = s.lower()
        cut = None
        for junk in _DOI_JUNK:
            i = low.find(junk)
            if i > 0 and (cut is None or i < cut):
                cut = i
        if cut is None:
            break
        s = s[:cut].rstrip(".,;-_/()[]")
    return s


def _library_dir() -> str:
    hh = os.environ.get("HERMES_HOME", "")
    if hh:
        return os.path.join(hh, "papers")
    here = Path(__file__).resolve().parent.parent.parent
    return str(here / "hermes_home" / "papers")


def _agent_papers_index() -> str:
    root = Path(__file__).resolve().parent.parent.parent
    return str(root / "work" / "papers" / ".pdf_index.json")


def _sha256_of(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()


def _pdf_text(path: str, pages: int = 2) -> str:
    try:
        import pymupdf as fitz
        doc = fitz.open(path)
        parts = []
        for i in range(min(pages, doc.page_count)):
            parts.append(doc[i].get_text("text"))
        doc.close()
        return "\n".join(parts)
    except Exception as e:
        logger.debug(f"pdf text failed: {e}")
        return ""


def _pdf_ocr_text(path: str, max_pages: int = 8, max_chars: int = 30000) -> str:
    """扫描版 PDF 兜底：逐页渲染 → RapidOCR（vision_tool 同一引擎，跨平台）。"""
    try:
        import pymupdf as fitz
        from memomics.bio_tools.vision_tool import _ocr_text
        from PIL import Image
        import io
        doc = fitz.open(path)
        parts = []
        total = 0
        for i in range(min(max_pages, doc.page_count)):
            pix = doc[i].get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            for item in _ocr_text(img):
                t = str(item.get("text") or "").strip()
                if t:
                    # 按 y 粗略分行：简单按原文顺序拼接
                    parts.append(t)
                    total += len(t)
                    if total >= max_chars:
                        break
            if total >= max_chars:
                break
        doc.close()
        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"pdf ocr failed: {e}")
        return ""


def _pdf_title_guess(path: str) -> str:
    """第一页最大字号文本行作为标题猜测。"""
    try:
        import pymupdf as fitz
        doc = fitz.open(path)
        if doc.page_count < 1:
            doc.close()
            return ""
        page = doc[0]
        spans = []
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                txt = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
                size = max((s.get("size", 0) for s in line.get("spans", [])), default=0)
                if txt:
                    spans.append((size, txt))
        doc.close()
        if not spans:
            return ""
        # 第一页按阅读顺序，取字号最大且像标题的行（长度 15-300，非纯数字/URL）
        order = [t for _, t in spans]
        best = max(spans, key=lambda x: x[0])
        for size, txt in sorted(spans, key=lambda x: -x[0]):
            if 12 <= len(txt) <= 300 and not re.fullmatch(r"[\d\s./-]+", txt) and "http" not in txt:
                return txt
        return best[1][:300]
    except Exception:
        return ""


def _crossref_by_doi(doi: str, timeout: float = 15.0) -> dict:
    import urllib.parse
    import urllib.request
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    req = urllib.request.Request(url, headers=_CROSSREF_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    m = (d.get("message") or {})
    authors = [f"{a.get('given','')} {a.get('family','')}".strip()
               for a in m.get("author", [])][:20]
    journal = ""
    ct = m.get("container-title") or []
    if ct:
        journal = ct[0]
    year = ""
    for k in ("published-print", "published-online", "published", "created"):
        v = m.get(k, {}).get("date-parts", [[None]])[0]
        if v and v[0]:
            year = str(v[0])
            break
    # 批O(2026-08-16)：补卷/期/页码/PMID（引用格式正确性必需）
    volume = m.get("volume") or ""
    issue = m.get("issue") or ""
    pages = m.get("page") or ""
    if not pages:
        pages = m.get("article-number") or ""
    pmid = ""
    try:
        _pmid = m.get("PMID") or ""
        if not _pmid:
            for _alt in (m.get("alternative-id") or []):
                if re.fullmatch(r"\d{7,8}", str(_alt)):
                    _pmid = _alt
                    break
        pmid = str(_pmid or "")
    except Exception:
        pass
    return {"title": (m.get("title") or [""])[0], "journal": journal,
            "authors": authors, "year": year, "doi": doi,
            "volume": volume, "issue": issue, "pages": pages, "pmid": pmid}


def _extract_metadata(pdf_path: str, text: str, original_path: str) -> dict:
    doi = ""
    m = DOI_RE.search(text or "")
    if m:
        doi = _clean_doi(m.group(0))
    meta = {"title": "", "journal": "", "authors": [], "year": "", "doi": doi,
            "volume": "", "issue": "", "pages": "", "pmid": "",
            "entry_type": "article", "url": f"https://doi.org/{doi}" if doi else ""}
    # 1. DOI → Crossref 反查
    if doi:
        try:
            cr = _crossref_by_doi(doi)
            for k in ("title", "journal", "authors", "year", "volume", "issue", "pages", "pmid"):
                if cr.get(k):
                    meta[k] = cr[k]
            return meta
        except Exception as e:
            logger.debug(f"crossref doi lookup failed: {e}")
    # 2. 标题猜测 → Crossref 书目检索（相似度把关，防张冠李戴；
    #    且绝不覆盖 PDF 文本里提取到的 DOI）
    guess = _pdf_title_guess(pdf_path) or Path(original_path).stem.replace("_", " ").replace("-", " ")
    if guess:
        try:
            import difflib
            import urllib.parse
            import urllib.request
            url = ("https://api.crossref.org/works?query.bibliographic="
                   + urllib.parse.quote(guess[:200]) + "&rows=3")
            req = urllib.request.Request(url, headers=_CROSSREF_UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode("utf-8"))
            items = (d.get("message") or {}).get("items") or []
            # 过滤同行评审记录（"Review for ..."）等噪音条目
            items = [it for it in items
                     if not ((it.get("title") or [""])[0] or "").lower().startswith("review for")]
            if items:
                best = max(items, key=lambda it: difflib.SequenceMatcher(
                    None, guess.lower()[:120], ((it.get("title") or [""])[0] or "").lower()[:120]).ratio())
                _ratio = difflib.SequenceMatcher(
                    None, guess.lower()[:120], ((best.get("title") or [""])[0] or "").lower()[:120]).ratio()
                if _ratio >= 0.55:  # 批O: 0.45→0.55，收紧防张冠李戴（NDRG1 误配书章节教训）
                    it = best
                    meta["title"] = (it.get("title") or [""])[0] or meta["title"]
                    ct = it.get("container-title") or []
                    meta["journal"] = ct[0] if ct else ""
                    meta["authors"] = [f"{a.get('given','')} {a.get('family','')}".strip()
                                       for a in it.get("author", [])][:20]
                    v = it.get("published", {}).get("date-parts", [[None]])[0]
                    if v and v[0]:
                        meta["year"] = str(v[0])
                    meta["volume"] = it.get("volume") or ""
                    meta["issue"] = it.get("issue") or ""
                    meta["pages"] = it.get("page") or it.get("article-number") or ""
                    if not meta.get("doi") and it.get("DOI"):
                        meta["doi"] = _clean_doi(it["DOI"])
                        meta["url"] = f"https://doi.org/{meta['doi']}"
                return meta
        except Exception as e:
            logger.debug(f"crossref bibliographic lookup failed: {e}")
    meta["title"] = meta["title"] or guess
    return meta


# ================= 2026-09-17 导入提速：Crossref 结果落盘缓存 + 并发预取 ===================
# 实测单篇 Crossref 反查 1.0–1.4s，且原实现是串行 —— 18 篇导入光网络就 20s+。
# 这里把"同一篇文献"的元数据结果缓存到 .crossref_cache.json（重复导入/补元数据零网络），
# 并按并发预取代价最高的网络查询。
_CROSSREF_CACHE_TTL = 30 * 86400.0   # 命中可用结果：30 天
_CROSSREF_MISS_TTL = 6 * 3600.0      # 未解析出期刊/作者/年份的弱结果：6 小时（避免死 DOI 每次重试）
_cr_cache_mem = None
_cr_cache_lock = threading.Lock()
_cr_cache_dirty = False
_cr_stats = {"hit": 0, "miss": 0, "write": 0}


def _cr_cache_path() -> str:
    return os.path.join(_library_dir(), ".crossref_cache.json")


def _cr_cache_get(key: str):
    global _cr_cache_mem
    with _cr_cache_lock:
        if _cr_cache_mem is None:
            raw = _load_index(_cr_cache_path())
            _cr_cache_mem = raw if isinstance(raw, dict) else {}
        rec = _cr_cache_mem.get(key)
    if not isinstance(rec, dict):
        return None
    try:
        if time.time() - float(rec.get("ts") or 0) > float(rec.get("ttl") or 0):
            return None
    except Exception:
        return None
    return rec.get("meta") or {}


def _cr_cache_put(key: str, meta: dict, ttl: float):
    global _cr_cache_mem, _cr_cache_dirty
    with _cr_cache_lock:
        if _cr_cache_mem is None:
            _cr_cache_mem = {}
        _cr_cache_mem[key] = {"ts": time.time(), "ttl": float(ttl), "meta": meta}
        _cr_cache_dirty = True


def _cr_cache_flush():
    """把缓存写回磁盘（导入结束时调用一次，避免每篇都写盘）。"""
    global _cr_cache_dirty
    with _cr_cache_lock:
        if not _cr_cache_dirty or not _cr_cache_mem:
            return
        data = dict(_cr_cache_mem)
        _cr_cache_dirty = False
    try:
        _save_index(_cr_cache_path(), data)
    except Exception as e:
        logger.debug(f"crossref cache save failed: {e}")


def _meta_cache_key(text: str, original_path: str) -> str:
    """缓存键：能抓到 DOI 就用 DOI，否则用"文件名/标题猜测"（同一篇文献跨导入稳定）。"""
    m = DOI_RE.search(text or "")
    if m:
        return "doi:" + _clean_doi(m.group(0)).lower()
    stem = _pdf_title_guess(original_path) or Path(original_path).stem
    return "name:" + re.sub(r"\s+", " ", str(stem)).strip().lower()[:200]


def _crossref_meta_cached(pdf_path: str, text: str, original_path: str) -> dict:
    """_extract_metadata + 磁盘缓存（并发调用安全）。"""
    key = _meta_cache_key(text, original_path)
    hit = _cr_cache_get(key)
    if hit is not None:
        _cr_stats["hit"] += 1
        return dict(hit)
    _cr_stats["miss"] += 1
    meta = _extract_metadata(pdf_path, text, original_path)
    resolved = bool(meta.get("journal") or meta.get("authors") or meta.get("year"))
    _cr_cache_put(key, meta, _CROSSREF_CACHE_TTL if resolved else _CROSSREF_MISS_TTL)
    _cr_stats["write"] += 1
    return meta


def _load_index(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


_INDEX_LOCK = threading.Lock()


def _save_index(path: str, entries: list):
    """原子写索引（tmp + os.replace）：防止并发任务（导入/翻译/知识提取同时改索引）
    读到一个写了一半的 JSON——最坏会把整个 .pdf_index.json 变成空数组。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _INDEX_LOCK:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def _collect_pdfs(paths) -> list:
    files = []
    for p in paths or []:
        p = str(p or "").strip().strip('"')
        if not p:
            continue
        # 安全：拒绝导入文件系统根（盘符根 / 系统根），防全盘递归
        if p == "/" or re.fullmatch(r"[A-Za-z]:[/\\]*", p):
            continue
        if os.path.isdir(p):
            for root, _dirs, fs in os.walk(p):
                # 跳过隐藏目录
                _dirs[:] = [d for d in _dirs if not d.startswith(".")]
                for f in fs:
                    if f.lower().endswith(".pdf"):
                        files.append(os.path.join(root, f))
        elif os.path.isfile(p) and p.lower().endswith(".pdf"):
            files.append(p)
    return files[:200]


def _balanced_slice(text: str, open_ch: str, close_ch: str) -> str:
    """从第一个 open_ch 起按引号/转义感知的括号平衡切出完整片段。"""
    i = text.find(open_ch)
    if i < 0:
        return ""
    depth = 0
    instr = False
    esc = False
    for j in range(i, len(text)):
        c = text[j]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
            continue
        if c == '"':
            instr = True
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    return ""


def _repair_json_via_llm(bad_text: str, target: str) -> str:
    """LLM 修复近似 JSON（转义换行/引号、删除多余解释）。"""
    try:
        from memomics.bio_tools.debate_analysis import _call_llm_sync, _default_role_llm
        cfg = _default_role_llm("", "", "deepseek-v4-flash", _load_provider_keys())
        r = _call_llm_sync(
            f"下面的内容不是严格的 JSON，请修正为严格的 JSON {target}"
            "（字符串内的换行/引号要转义，删除任何解释性文字），只输出 JSON，不要其他文字:\n"
            + (bad_text or "")[:6000],
            "json_repair", cfg["api_key"], cfg["base_url"], cfg["model"],
            temperature=0.0, max_tokens=3000)
        return r.get("content", "")
    except Exception as e:
        logger.warning(f"json repair failed: {e}")
        return ""


def _no_think_enabled() -> bool:
    """批量文献任务（翻译/提炼/知识提取）默认首轮就抑制推理。

    实测（2026-09-17，dcs-cloud/deepseek-flash，同一 1691 字符翻译单元 2×2 次）：
    带前缀 11.5/13.4s，不带 16.4/19.5s —— 快约 30%，且译文质量一致。
    环境变量 MEMOMICS_LIT_NO_THINK=0 可关掉。"""
    return os.environ.get("MEMOMICS_LIT_NO_THINK", "1").lower() not in ("0", "false", "no", "off")


_NO_THINK_PREFIX = "【不要输出任何思考/推理过程，直接输出最终结果】\n"


def _llm_content(prompt: str, label: str, temperature: float = 0.3,
                 max_tokens: int = 6000, retry_prefix: str = "",
                 no_think: bool = False) -> str:
    """LLM 调用 + 推理占满自动重试（批N 2026-08-16）。

    deepseek-v4-flash 是推理模型，偶尔把输出额度全花在 reasoning 上、
    content 为空（_call_llm_sync 回退返回 reasoning 草稿）→ 检测到后
    重试一次并要求直接输出最终结果。
    no_think=True：首轮就带上"不要思考"前缀（批量翻译/提炼用，实测快 30%，
    且省掉一次"推理占满→整轮重试"的重复调用）。重试仍用原始 prompt，避免前缀叠加。
    """
    from memomics.bio_tools.debate_analysis import _call_llm_sync, _default_role_llm
    cfg = _default_role_llm("", "", "deepseek-v4-flash", _load_provider_keys())
    r = _call_llm_sync((_NO_THINK_PREFIX if (no_think and _no_think_enabled()) else "") + prompt,
                       label, cfg["api_key"], cfg["base_url"], cfg["model"],
                       temperature=temperature, max_tokens=max_tokens)
    if r.get("used_reasoning_fallback"):
        logger.warning(f"{label} reasoning 占满 → 重试直接输出")
        r2 = _call_llm_sync((retry_prefix or "【重要：不要输出任何思考过程，立即输出最终结果】\n") + prompt,
                            label + "_retry", cfg["api_key"], cfg["base_url"], cfg["model"],
                            temperature=0.2, max_tokens=max_tokens)
        return r2.get("content", "") or r.get("content", "")
    return r.get("content", "")


def _llm_chunks_parallel(chunks: list, make_prompt, label_prefix: str,
                         progress_cb=None, phase: str = "extract",
                         max_tokens: int = 4000, retry_prefix: str = "",
                         workers: int = 0) -> list:
    """分块 LLM 提炼并发执行，按输入顺序返回解析后的 JSON dict 列表。

    各分块互不依赖（结果统一合并），并发不改变语义。实测某篇 170k 字符文献切 19 块，
    串行每块 20–40s；并发 5 路后整体 <2 分钟（MEMOMICS_LIT_CHUNK_WORKERS 可覆盖）。
    """
    out = [{} for _ in chunks]
    n = len(chunks)
    if not n:
        return out
    mw = workers or max(1, min(10, int(os.environ.get("MEMOMICS_LIT_CHUNK_WORKERS", "6"))))

    def _run(i: int):
        return _parse_json_object(_llm_content(
            make_prompt(i, chunks[i]), f"{label_prefix}_{i}", temperature=0.2,
            max_tokens=max_tokens, retry_prefix=retry_prefix, no_think=True))

    done = 0
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(mw, n)) as ex:
            futs = {ex.submit(_run, i): i for i in range(n)}
            for f in as_completed(futs):
                i = futs[f]
                try:
                    out[i] = f.result() or {}
                except Exception as e:
                    logger.warning(f"{label_prefix} 第{i + 1}块失败: {e}")
                    out[i] = {}
                done += 1
                if progress_cb:
                    progress_cb(phase, done, n, f"{label_prefix} {done}/{n} 块（并发{mw}）")
        # 批P4(2026-09-17)：没产出有效 JSON 的块重试一次——否则那块内容直接蒸发
        # （实测 lung_no-smoking 缺了 Methods 里的 FACETS/GISTIC：24 块里 1-2 块 JSON 没解析出来）
        _empty = [i for i in range(n) if not out[i]]
        if _empty:
            logger.warning(f"{label_prefix} {len(_empty)}/{n} 块未产出有效 JSON → 严格模式重试")

            def _run_strict(i: int):
                return _parse_json_object(_llm_content(
                    "【严格：只输出一个 JSON 对象，第一个字符必须是 { ，不要任何解释或思考】\n"
                    + make_prompt(i, chunks[i]), f"{label_prefix}_fix_{i}", temperature=0.1,
                    max_tokens=max_tokens, retry_prefix=retry_prefix, no_think=True))

            try:
                with ThreadPoolExecutor(max_workers=min(mw, len(_empty))) as ex2:
                    futs2 = {ex2.submit(_run_strict, i): i for i in _empty}
                    for f in as_completed(futs2):
                        i = futs2[f]
                        try:
                            got = f.result() or {}
                        except Exception as e:
                            logger.warning(f"{label_prefix} 第{i + 1}块严格重试失败: {e}")
                            got = {}
                        if got:
                            out[i] = got
                _fixed = sum(1 for i in _empty if out[i])
                if progress_cb:
                    progress_cb(phase, n, n, f"{label_prefix} 空块重试补齐 {_fixed}/{len(_empty)} 块")
            except Exception as e:
                logger.warning(f"strict chunk retry failed: {e}")
    except Exception as e:
        logger.warning(f"parallel chunk LLM failed, fallback serial: {e}")
        done = 0
        for i in range(n):
            try:
                out[i] = _run(i) or {}
            except Exception as e2:
                logger.warning(f"{label_prefix} 第{i + 1}块失败: {e2}")
                out[i] = {}
            done += 1
            if progress_cb:
                progress_cb(phase, done, n, f"{label_prefix} {done}/{n} 块")
    return out


def _cap_json_size(obj, cap: int):
    """把碎片 JSON 压到 ≤cap 字符，且保持 JSON 合法（按完整条目丢弃，不切字符串）。"""
    s = json.dumps(obj, ensure_ascii=False)
    if len(s) <= cap:
        return s
    import copy as _copy
    cur = _copy.deepcopy(obj)

    def _trim(node):
        changed = False
        for k, v in list(node.items()):
            if isinstance(v, list) and v:
                v.pop()
                changed = True
            elif isinstance(v, dict) and v:
                changed = _trim(v) or changed
        return changed

    while len(json.dumps(cur, ensure_ascii=False)) > cap and _trim(cur):
        pass
    return json.dumps(cur, ensure_ascii=False)


def _compact_fragments(parts: list) -> dict:
    """合并去重分块碎片（列表取并集、标量取首个非空）——压缩合并调用的输入。

    旧实现把碎片 JSON 硬截断到 12000 字符，长文献（19 块）后面几块的碎片
    直接被丢掉 → 知识缺失。去重后体积通常只剩零头，可完整送进合并调用。
    """
    agg = {}
    for part in parts:
        for k, v in (part or {}).items():
            if isinstance(v, list):
                bucket = agg.setdefault(k, [])
                seen = {json.dumps(x, ensure_ascii=False, sort_keys=True) for x in bucket}
                for it in v:
                    sig = json.dumps(it, ensure_ascii=False, sort_keys=True)
                    if sig not in seen:
                        seen.add(sig)
                        bucket.append(it)
            elif isinstance(v, str) and v.strip() and not agg.get(k):
                agg[k] = v
    return agg


def _markdown_dir() -> str:
    return os.path.join(_library_dir(), "markdown")


def pdf_to_markdown(path: str, force: bool = False) -> str:
    """PDF → Markdown 落盘（批N 2026-08-16）：hermes_home/papers/markdown/<名>.md。

    pymupdf4llm 优先（标题/段落结构化）；失败回退纯文本；扫描版走 OCR。
    已存在且非 force → 直接复用缓存。
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    os.makedirs(_markdown_dir(), exist_ok=True)
    md_path = os.path.join(_markdown_dir(), f"{stem}.md")
    if os.path.isfile(md_path) and os.path.getsize(md_path) > 100 and not force:
        try:
            with open(md_path, encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    md = ""
    try:
        import pymupdf4llm
        md = pymupdf4llm.to_markdown(path)
    except Exception as e:
        logger.warning(f"pymupdf4llm failed ({e}), fallback to raw text")
    if not md or not md.strip():
        md = _pdf_text(path, pages=200)
        if not md.strip():
            md = _pdf_ocr_text(path)
            if md.strip():
                md = "# (OCR 识别版)\n\n" + md
    if md.strip():
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)
    return md or ""


def _split_md_sections(md: str) -> list:
    """按 Markdown 标题切分节：[(标题, 内容), ...]。"""
    sections = []
    cur_title, cur = "", []
    for ln in (md or "").splitlines():
        if ln.startswith("#"):
            if cur or cur_title:
                sections.append((cur_title, "\n".join(cur).strip()))
            cur_title, cur = ln.lstrip("#").strip(), []
        else:
            cur.append(ln)
    if cur or cur_title:
        sections.append((cur_title, "\n".join(cur).strip()))
    return [(t, c) for t, c in sections if c.strip()]


def _chunk_sections(sections: list, max_chars: int = 9000) -> list:
    """分节合并成 ≤max_chars 的块（块内保留节标题）；超大节按段落再拆。

    批P2(2026-09-17)：旧实现只合并、从不拆分。遇到 pdf→markdown 没产出 # 标题的
    PDF 时整篇 = 1 节 → 拼出一个 170k 字符的巨型块，一次送模型必然「推理占满/超时」，
    知识提取直接报「未能提取出知识」（实测 lung_no-smoking_clinic.pdf 100% 失败）。
    """
    pieces = []
    for title, content in sections:
        head = f"## {title}\n" if title else ""
        for para in re.split(r"\n\s*\n", (content or "").strip()):
            para = para.strip()
            if not para:
                continue
            while len(para) > max_chars:      # 单段超长（无空行）→ 硬切
                pieces.append(para[:max_chars])
                para = para[max_chars:]
            pieces.append(head + para)
            head = ""
        if head:
            pieces.append(head)
    chunks, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) + 2 > max_chars:
            chunks.append(cur)
            cur = p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def _parse_json_object(text: str) -> dict:
    s = _balanced_slice(text or "", "{", "}")
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        s2 = _balanced_slice(_repair_json_via_llm(s, "对象"), "{", "}")
        if s2:
            try:
                return json.loads(s2)
            except Exception:
                return {}
        return {}


def _parse_json_array(text: str) -> list:
    s = _balanced_slice(text or "", "[", "]")
    if not s:
        return []
    try:
        return json.loads(s)
    except Exception:
        s2 = _balanced_slice(_repair_json_via_llm(s, "数组"), "[", "]")
        if s2:
            try:
                return json.loads(s2)
            except Exception:
                return []
        return []


_CLASSIFY_LOCK = threading.Lock()


def _apply_classification_bg(index_file: str, keymap: dict, fut):
    """后台补写 LLM 精细分类标签（不阻塞导入返回；只改条目 tags，不动其它字段）。"""
    try:
        tags = fut.result() or {}
    except Exception as e:
        logger.warning(f"background classification failed: {e}")
        return
    if not tags:
        return
    try:
        with _CLASSIFY_LOCK:
            cur = _load_index(index_file)
            changed = 0
            for fname, key in (keymap or {}).items():
                tg = tags.get(key)
                if not tg:
                    continue
                for e in cur:
                    if e.get("file") == fname and e.get("tags"):
                        e["tags"] = tg
                        changed += 1
                        break
            if changed:
                _save_index(index_file, cur)
            logger.info(f"background classification applied: {changed}/{len(keymap or {})}")
    except Exception as e:
        logger.warning(f"background classification save failed: {e}")


def import_pdfs(paths, progress_cb=None, imported_by: str = "") -> str:
    """导入本地 PDF 到全局文献库（去重 + 元数据标识 + 分类标签 + 引用库注册）。

    progress_cb(phase, done, total, detail): 进度回调——
    phase ∈ collect/file/classify/done；detail=当前文件名或说明。
    imported_by: 导入人标识（多用户场景记录在条目上）。

    2026-08-25 断点续传语义：已导入的 PDF 按 sha256（或同名同大小）跳过——
    大批量导入中断后直接重跑同一批路径，已完成的不重复处理；返回的 skipped
    列表即"本次跳过（此前已导入）"清单。注意 knowledge 卡片/摘要不在本函数
    生成（走 summarize_paper / kb_extract_from_paper），续传后对缺卡片的文献
    单独补提炼即可。
    """
    files = _collect_pdfs(paths)
    if not files:
        return json.dumps({"ok": False, "error": "未找到 PDF 文件（支持 .pdf 文件或目录路径）"},
                          ensure_ascii=False)
    _t0 = time.time()
    _cb = progress_cb or (lambda *a, **k: None)
    _cb("collect", 0, len(files), f"共发现 {len(files)} 个 PDF")
    lib_dir = _library_dir()
    os.makedirs(lib_dir, exist_ok=True)
    index_file = os.path.join(lib_dir, ".pdf_index.json")
    index = _load_index(index_file)
    by_sha = {e.get("sha256") for e in index if e.get("sha256")}
    by_name = {(e.get("file"), e.get("size")) for e in index}

    imported, skipped, errors = [], [], []
    _n_done = 0

    # ---- ① 本地预筛（快）：空文件 / 非 PDF / 重复 ----
    # 2026-09-17 提速：便宜判断在前 —— 原实现先无条件算 sha256（整文件读一遍）再判同名，
    # 重复导入时白读全文；现在同名同大小直接跳过，重复文件零读取。
    _cands = []
    for src in files:
        try:
            _sz = os.path.getsize(src)
            if _sz == 0:
                errors.append({"file": os.path.basename(src),
                               "error": "文件为空(0字节)，可能是下载失败的残留，请重新下载"})
                _n_done += 1
                continue
            with open(src, "rb") as _f:
                _head = _f.read(5)
            if not _head.startswith(b"%PDF-"):
                errors.append({"file": os.path.basename(src),
                               "error": "不是有效的 PDF 文件（文件头非 %PDF-）"})
                _n_done += 1
                continue
            if (os.path.basename(src), _sz) in by_name:
                skipped.append({"file": os.path.basename(src), "reason": "重复(同名同大小)"})
                _n_done += 1  # 2026-08-25: 续传跳过也算进度（原实现卡住计数）
                continue
        except Exception as e:
            errors.append({"file": os.path.basename(src), "error": str(e)[:200]})
            _n_done += 1
            continue
        sha = _sha256_of(src)
        if sha and sha in by_sha:
            skipped.append({"file": os.path.basename(src), "reason": "重复(sha256)"})
            _n_done += 1
            continue
        _cands.append((src, sha, _sz))

    # ---- ②③ 元数据预取：本地解析首页文本（快）→ 并发 Crossref 反查（网络是瓶颈）----
    _metas, _texts = {}, {}
    if _cands:
        _cb("meta", 0, len(_cands), f"解析首页文本（{len(_cands)} 篇）…")
        for _src, _sha, _sz in _cands:
            try:
                _texts[_src] = _pdf_text(_src, pages=2)
            except Exception:
                _texts[_src] = ""
        _workers = min(8, max(1, len(_cands)))
        _n_meta = 0
        with ThreadPoolExecutor(max_workers=_workers) as _ex:
            _futs = {_ex.submit(_crossref_meta_cached, _src, _texts.get(_src, ""), _src): _src
                     for _src, _sha, _sz in _cands}
            for _fu in as_completed(_futs):
                _src = _futs[_fu]
                try:
                    _metas[_src] = _fu.result() or {}
                except Exception as e:
                    logger.debug(f"metadata prefetch failed for {_src}: {e}")
                    _metas[_src] = {}
                _n_meta += 1
                _cb("meta", _n_meta, len(_futs), f"并发查询元数据 {_n_meta}/{len(_futs)}")

    # ---- ④ 分类（LLM，实测 15–20s/批）与后面的复制入库并行：LLM 等待被本地 IO 掩盖 ----
    _cls_pool, _cls_fut, _cls_order = None, None, []
    if _cands:
        try:
            _cls_order = [s for s, _h, _z in _cands]
            _cls_items = []
            for _i, _src in enumerate(_cls_order):
                _m = _metas.get(_src) or {}
                _cls_items.append({"file": f"__{_i}",
                                   "title": (_m.get("title") or os.path.basename(_src))[:200],
                                   "journal": (_m.get("journal") or "")[:80]})
            _cls_pool = ThreadPoolExecutor(max_workers=1)
            _cls_fut = _cls_pool.submit(_classify_papers, _cls_items)
        except Exception as e:
            logger.debug(f"classify prefetch failed: {e}")

    _entry_for = {}
    for src, sha, size in _cands:
        _cb("file", _n_done, len(files), os.path.basename(src))
        try:
            # 复制进库（2026-09-17: 改用 shutil.copyfile —— 原实现 fin.read() 把整个 PDF 读进内存）
            dest_name = "".join(c if (c.isalnum() or c in "._-") else "_" for c in os.path.basename(src))
            dest = os.path.join(lib_dir, dest_name)
            n = 1
            while os.path.exists(dest):
                stem, ext = os.path.splitext(dest_name)
                dest = os.path.join(lib_dir, f"{stem}_{n}{ext}")
                n += 1
            shutil.copyfile(src, dest)
            # 元数据：直接用预取结果（源文件已解析 + 已并发 Crossref），命中缓存时零网络
            meta = _metas.get(src) or _extract_metadata(dest, _pdf_text(dest, pages=2), src)
            entry = {
                "file": os.path.basename(dest),
                "path": dest.replace("\\", "/"),
                "sha256": sha,
                "size": size,
                "title": meta.get("title") or "",
                "journal": meta.get("journal") or "",
                "authors": meta.get("authors") or [],
                "year": meta.get("year") or "",
                "doi": meta.get("doi") or "",
                "url": meta.get("url") or "",
                "volume": meta.get("volume") or "",
                "issue": meta.get("issue") or "",
                "pages": meta.get("pages") or "",
                "pmid": meta.get("pmid") or "",
                "downloaded_at": datetime.fromtimestamp(os.path.getmtime(src)).strftime("%Y-%m-%d %H:%M:%S"),
                "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "imported_by": (imported_by or "").strip()[:64],
                "source": "user_import",
                "imported_from": src.replace("\\", "/"),
            }
            index.append(entry)
            by_sha.add(sha)
            by_name.add((entry["file"], size))
            imported.append({k: entry[k] for k in ("file", "title", "journal", "year", "doi", "downloaded_at")})
            _entry_for[src] = entry
            # 注册进全局引用库（BibTeX/RIS）
            try:
                from memomics.bio_tools.reference_library import save_reference
                save_reference("add", {
                    "title": entry["title"] or os.path.splitext(entry["file"])[0],
                    "authors": ";".join(entry["authors"]),
                    "year": entry["year"], "doi": entry["doi"], "journal": entry["journal"],
                    "url": entry["url"], "entry_type": "article",
                    "volume": entry["volume"], "issue": entry["issue"], "pages": entry["pages"],
                    "pmid": entry["pmid"],
                    "note": f"local_pdf: {entry['path']}",
                }, global_lib=True)
            except Exception as e:
                logger.warning(f"reference library register failed: {e}")
        except Exception as e:
            errors.append({"file": os.path.basename(src), "error": str(e)[:200]})
        _n_done += 1
        _cb("file", _n_done, len(files), f"已处理 {_n_done}/{len(files)}")
    # 自动分类打标（物种/组织/方向/assay/kb_category）——仅对新导入的
    # 2026-09-17 提速：分类的 LLM 调用在复制入库之前就已并发发出（见 ④），
    # 这里只取回结果 —— 实测该调用固定 15–20s，现在与复制/解析并行，不再叠加等待。
    if index and any(not e.get("tags") for e in index):
        _new = [e for e in index if not e.get("tags")]
        # 2026-09-17：先落规则标签（零成本、立即可用），再让 LLM 精细分类在后台改写——
        # 实测单次 LLM 分类固定 15–20s（一篇和十八篇一样），不该让用户等它。
        for e in _new:
            e["tags"] = _rule_classify(e.get("title") or "")
        _save_index(index_file, index)
        _keymap = {}
        for _i, _src in enumerate(_cls_order):
            _e = _entry_for.get(_src)
            if _e is not None:
                _keymap[_e.get("file")] = f"__{_i}"
        if _cls_fut is not None and _keymap:
            _cb("classify", _n_done, len(files),
                f"已按规则打标 {len(_new)} 篇；LLM 精细分类 {len(_keymap)} 篇后台进行（不阻塞导入）")
            threading.Thread(target=_apply_classification_bg,
                             args=(index_file, _keymap, _cls_fut), daemon=True).start()
        else:
            _cb("classify", _n_done, len(files), f"分类打标 {len(_new)} 篇（规则）")
    if _cls_pool is not None:
        try:
            _cls_pool.shutdown(wait=False)
        except Exception:
            pass
    for it in imported:
        for e in index:
            if e.get("file") == it.get("file") and e.get("tags"):
                it["tags"] = e["tags"]
    _cr_cache_flush()
    _elapsed = time.time() - _t0
    _cb("done", _n_done, len(files), f"完成：导入 {len(imported)} 篇（{_elapsed:.1f}s）")
    return json.dumps({
        "ok": True, "imported": len(imported), "skipped": len(skipped), "errors": errors,
        "entries": imported, "library_dir": lib_dir.replace("\\", "/"),
        "bibtex_file": os.path.join(os.path.dirname(_library_dir()) or "", "references.bib").replace("\\", "/"),
        "ris_file": os.path.join(os.path.dirname(_library_dir()) or "", "references.ris").replace("\\", "/"),
        "elapsed_s": round(_elapsed, 2),
        "crossref_cache": dict(_cr_stats),
    }, ensure_ascii=False, indent=2)


def list_library() -> str:
    """列出全部文献：用户导入 + agent 下载（批O5f 2026-08-16 起跨库去重）。

    正式库（user_import，含 download_pdf 自动入库的）优先；agent 下载索引里与
    正式库重复的条目（同 sha256 或同文件名，历史遗留双份）不再重复显示。
    """
    out = []
    seen_sha, seen_name = set(), set()
    for label, idx_path in (("user_import", os.path.join(_library_dir(), ".pdf_index.json")),
                            ("agent_download", _agent_papers_index())):
        if not idx_path or not os.path.isfile(idx_path):
            continue
        for e in _load_index(idx_path):
            _sha = (e.get("sha256") or "").strip()
            _fname = (e.get("file") or "").strip().lower()
            if label == "agent_download" and ((_sha and _sha in seen_sha)
                                              or (_fname and _fname in seen_name)):
                continue
            _s = e.get("summary") or {}
            out.append({
                "source": label,
                "file": e.get("file"), "title": e.get("title") or "",
                "journal": e.get("journal") or "", "year": e.get("year") or "",
                "doi": e.get("doi") or "",
                "authors": e.get("authors") or [],
                "volume": e.get("volume") or "", "issue": e.get("issue") or "",
                "pages": e.get("pages") or "", "pmid": e.get("pmid") or "",
                "downloaded_at": e.get("downloaded_at") or e.get("imported_at") or "",
                "imported_by": e.get("imported_by") or "",
                "path": e.get("path") or "",
                "tags": e.get("tags") or {},
                "summary_done": bool(e.get("summary_done")),
                "kb_done": bool(e.get("kb_done")),
                "knowledge_done": bool(e.get("knowledge_done")),
                "translated": bool(e.get("translated")),
                "summary_idea": str(_s.get("idea") or "")[:160],
                "meta_complete": bool(e.get("volume") and e.get("pages")),
            })
            if _sha:
                seen_sha.add(_sha)
            if _fname:
                seen_name.add(_fname)
    return json.dumps({"ok": True, "total": len(out), "library": out,
                       "library_dir": _library_dir().replace("\\", "/")},
                      ensure_ascii=False, indent=2)


def _load_provider_keys() -> dict:
    hh = os.environ.get("HERMES_HOME", "")
    if hh:
        try:
            with open(os.path.join(hh, "provider_keys.json"), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ── 自动分类打标（批G 2026-08-16）──
_SPECIES_VOCAB = ["human", "mouse", "rat", "zebrafish", "drosophila", "c.elegans",
                  "macaque", "monkey", "pig", "rabbit", "other"]
_DIRECTION_VOCAB = ["aging", "exercise", "t2d", "cancer", "development", "immunity",
                    "neurodegeneration", "metabolism", "regeneration", "inflammation",
                    "other"]

# 规则回退（LLM 不可用时按标题关键词粗分）
_RULE_SPECIES = [("mouse", ["mouse", "murine", "mus musculus"]),
                 ("human", ["human", "homo sapiens", "patient"]),
                 ("rat", ["rat", "rattus"]),
                 ("zebrafish", ["zebrafish", "danio"]),
                 ("drosophila", ["drosophila", "fly"]),
                 ("macaque", ["macaque", "monkey", "rhesus"])]
_RULE_TISSUE = [("skeletal_muscle", ["muscle", "myofiber", "myotube"]),
                ("liver", ["liver", "hepatocyte"]),
                ("brain", ["brain", "neuron", "cortex"]),
                ("heart", ["heart", "cardiac", "cardiomyocyte"]),
                ("adipose", ["adipose", "adipocyte", "fat"]),
                ("lung", ["lung", "pulmonary"]),
                ("kidney", ["kidney", "renal"]),
                ("blood", ["blood", "pbmc", "immune cell"])]
_RULE_DIR = [("aging", ["aging", "ageing", "senescen", "aged", "age-related"]),
             ("exercise", ["exercise", "training", "contraction"]),
             ("t2d", ["diabet", "t2d", "insulin", "glucose"]),
             ("cancer", ["cancer", "tumor", "tumour", "oncolog"]),
             ("development", ["development", "embryo", "differentiation"]),
             ("immunity", ["immun", "t cell", "macrophage"]),
             ("regeneration", ["regenerat", "repair", "satellite"]),
             ("neurodegeneration", ["alzheimer", "parkinson", "neurodegenerat"])]
_RULE_ASSAY = [("ATAC", ["atac", "chromatin accessibility", "peak"]),
               ("spatial", ["spatial", "visium", "slide-seq"]),
               ("RNA", ["scrna", "single-cell", "single cell", "rna-seq", "transcriptom"]),
               ("bulk", ["bulk", "microarray"])]


def _rule_classify(title: str) -> dict:
    tl = (title or "").lower()
    species = [s for s, kws in _RULE_SPECIES if any(k in tl for k in kws)] or ["unknown"]
    tissue = [t for t, kws in _RULE_TISSUE if any(k in tl for k in kws)]
    direction = [d for d, kws in _RULE_DIR if any(k in tl for k in kws)]
    assay = "RNA"
    for a, kws in _RULE_ASSAY:
        if any(k in tl for k in kws):
            assay = a
            break
    return {"species": species, "tissue": tissue, "direction": direction, "assay": assay}


def _classify_papers(entries: list) -> dict:
    """批量 LLM 分类打标：物种/组织/方向/assay/kb_category。失败回退规则匹配。"""
    tags = {}
    items = [{"file": e.get("file", ""), "title": (e.get("title") or "")[:200],
              "journal": (e.get("journal") or "")[:80]}
             for e in entries]
    prompt = (
        "你是生物信息学文献分类器。对下列文献按科研维度打标签，输出 JSON 数组（不要任何其他文字）：\n"
        f"物种可选: {_SPECIES_VOCAB}\n方向可选: {_DIRECTION_VOCAB}\n"
        "组织用英文小写下划线（如 skeletal_muscle、liver，未知给空数组）\n"
        "assay 可选: RNA / ATAC / spatial / bulk（单细胞转录组=RNA）\n"
        "kb_category 可选: 01_生物学知识 / 02_质控参数 / 03_测序方法\n"
        "格式: [{\"file\":\"...\",\"species\":[\"mouse\"],\"tissue\":[\"skeletal_muscle\"],"
        "\"direction\":[\"aging\"],\"assay\":\"RNA\",\"kb_category\":\"01_生物学知识\"}]\n"
        "文献列表:\n" + json.dumps(items, ensure_ascii=False)
    )
    try:
        # 2026-09-17：改用 _llm_content（no_think + 推理占满自动重试）。实测原实现 max_tokens=3000
        # 被 reasoning 全吃掉、无重试 → 11 篇 0/11 拿到 kb_category，静默退回规则标签
        # （用户在文献库里看到的物种/方向是规则结果，后台 LLM 精细分类从未生效）。
        txt = _llm_content(prompt, "lit_classify", temperature=0.2, max_tokens=8000,
                           retry_prefix="【不要思考，立即输出 JSON 数组，第一个字符必须是 [ 】\n",
                           no_think=True)
        arr = _parse_json_array(txt)
        for it in arr:
            if isinstance(it, dict) and it.get("file"):
                tags[it["file"]] = {
                    "species": it.get("species") or ["unknown"],
                    "tissue": it.get("tissue") or [],
                    "direction": it.get("direction") or [],
                    "assay": it.get("assay") or "RNA",
                    "kb_category": it.get("kb_category") or "01_生物学知识",
                }
    except Exception as e:
        logger.warning(f"LLM classification failed, fallback to rules: {e}")
    for e in entries:
        if e.get("file") not in tags:
            tags[e["file"]] = _rule_classify(e.get("title") or "")
    return tags


def _classify_single(title: str) -> dict:
    try:
        r = _classify_papers([{"file": "__single__", "title": title, "journal": ""}])
        return r.get("__single__", _rule_classify(title))
    except Exception:
        return _rule_classify(title)


def kb_extract_from_paper(file_or_title: str, progress_cb=None, force: bool = False) -> str:
    """把文献库中的一篇文献提炼成知识库条目（批G 2026-08-16；批O 2026-08-16 升级为
    结构化知识提取：生物学知识[结论/基因marker/细胞类型/通路/类器官/化学信息]
    + 生信知识[测序方法/流程/软件包/参数/QC/参考基因组/数据库]）。

    流程: 定位 PDF → 全文分块 → LLM 结构化提取 → knowledge/<名>.md 落盘
          + save_knowledge 五级目录 YAML（带 DOI/原文溯源 evidence）。
    progress_cb(phase, done, total, detail): 可选进度回调。
    force=True 时即使已入库也重新提炼（默认幂等跳过，防并发重复调用）。
    兼容旧调用方（agent 工具/一键入库），内部委托 extract_paper_knowledge。
    """
    r = json.loads(extract_paper_knowledge(file_or_title, progress_cb=progress_cb, force=force))
    if r.get("ok"):
        return json.dumps({
            "ok": True, "paper": r.get("paper"), "doi": r.get("doi"),
            "file": r.get("file"), "written": r.get("written") or [],
            "rejected": r.get("rejected") or [],
            "knowledge": r.get("knowledge") or {},
            "note": ("结构化知识已入库：生物学知识(结论/marker/类器官/化学) → 01_生物学知识；"
                     "生信知识(测序/流程/包/参数) → 03_测序方法；质控 → 02_质控参数。带 DOI 溯源。")},
            ensure_ascii=False, indent=2)
    return json.dumps(r, ensure_ascii=False)


def extract_all_papers(progress_cb=None) -> str:
    """一键入库（批I 2026-08-16；批O 2026-08-16 升级为结构化知识提取）：
    对文献库中未入库（kb_done≠true）的文献逐篇提取知识进知识库。
    （kb_done 与 knowledge_done 同步：提取成功即标记 kb_done。）

    progress_cb(phase, done, total, detail)。
    """
    r = json.loads(extract_all_knowledge(progress_cb=progress_cb))
    if r.get("ok"):
        r["note"] = ("结构化知识(生物学+生信)已写入 papers/knowledge/ 与 knowledge_base "
                     "五级目录，每篇 2-3 条，带 DOI 溯源。")
    return json.dumps(r, ensure_ascii=False, indent=2)


def _md_blocks(md: str) -> list:
    """段落级切块（与前端 litSplitBlocks 同规则）：空行切块 + 标题行独立成块。

    批O2(2026-08-16)：保证译文与原文段落数严格 1:1，中英对照逐段对齐。
    """
    blocks = []
    for seg in re.split(r"\n\s*\n", md or ""):
        seg = seg.strip()
        if not seg:
            continue
        cur = []
        for ln in seg.splitlines():
            if re.match(r"^#{1,6}\s", ln) and cur:
                blocks.append("\n".join(cur))
                cur = []
            cur.append(ln)
        if cur:
            blocks.append("\n".join(cur))
    return blocks


def _batch_blocks(blocks: list, max_chars: int = 6000, max_blocks: int = 4) -> list:
    """段落分组（每批 ≤max_chars 字符 且 ≤max_blocks 段，块内保持完整段落）。"""
    batches, cur, cur_n, cur_b = [], [], 0, 0
    for b in blocks:
        if cur and (cur_b >= max_blocks or cur_n + len(b) > max_chars):
            batches.append(cur)
            cur, cur_n, cur_b = [], 0, 0
        cur.append(b)
        cur_n += len(b)
        cur_b += 1
    if cur:
        batches.append(cur)
    return batches


def _parse_numbered_output(out: str, n: int) -> list:
    """解析 '###N###' 编号译文输出 → [译文1, 译文2, ...]（缺失给空串）。"""
    res = [""] * n
    cur_idx, cur = None, []
    for ln in (out or "").splitlines():
        m = re.match(r"^#{1,6}\s*(\d{1,3})\s*#{1,6}\s*(.*)$", ln.strip())
        if not m:
            m = re.match(r"^###(\d{1,3})###\s*(.*)$", ln.strip())
        if m:
            idx = int(m.group(1))
            if cur_idx is not None and 1 <= cur_idx <= n and cur:
                res[cur_idx - 1] = "\n".join(cur).strip()
            cur_idx, cur = idx, ([m.group(2)] if m.group(2).strip() else [])
        elif cur_idx is not None:
            cur.append(ln)
    if cur_idx is not None and 1 <= cur_idx <= n and cur:
        res[cur_idx - 1] = "\n".join(cur).strip()
    return res


_TRANS_PROMPT_HEAD = (
    "你是生物医学文献翻译专家。把下面编号的段落逐一翻译成学术严谨的中文。\n"
    "输出格式（严格遵守）：每段先单独一行输出编号标记 ###N###（N=段落编号），"
    "紧接着输出该段译文（可多行）；下一段从新的 ###N### 行开始。\n"
    "规则：① 段落以 # 开头的保持 Markdown 标题格式（# 号与编号保留在行首）"
    "② 术语用规范译名，基因名/蛋白名/阈值/数字/单位/统计量保持原文"
    "③ 人名、机构名保留英文 ④ 忠实原文不意译不增删 ⑤ 不要输出任何解释。\n\n")


def _translate_block_batch(blocks: list) -> list:
    """按 ###N### 编号批量直译一组段落，返回与输入等长的译文列表。

    三层兜底：① 首次整批编号直译 ② 全空→整体重试 ③ 部分缺失→只对缺失段
    重新发一次小批（编号沿用原编号）。仍缺失的段由调用方单段兜底。
    """
    prompt = _TRANS_PROMPT_HEAD
    for i, b in enumerate(blocks):
        prompt += f"[{i + 1}]\n{b}\n\n"
    out = _llm_content(prompt, "lit_trans_blocks", temperature=0.2, max_tokens=12000,
                       retry_prefix="【不要思考，立即按 ###N### 编号输出译文】\n",
                       no_think=True)
    res = _parse_numbered_output(out, len(blocks))
    missing = [i for i, t in enumerate(res) if not t]
    if not any(res):
        # 全空（可能整段输出格式不符/推理占满）→ 整体重试
        out2 = _llm_content(
            "【重要：不要输出任何思考过程，立即按 ###N### 编号逐段输出译文，"
            "每段必须以 ###数字### 单独一行开头】\n" + prompt,
            "lit_trans_blocks_retry", temperature=0.1, max_tokens=12000,
            retry_prefix="【直接输出译文，不要思考】\n", no_think=True)
        res = _parse_numbered_output(out2, len(blocks))
        missing = [i for i, t in enumerate(res) if not t]
    if missing and any(res):
        # 部分缺失（多为输出截断）→ 缺失段单独再发一小批
        sub_prompt = _TRANS_PROMPT_HEAD
        for i in missing:
            sub_prompt += f"[{i + 1}]\n{blocks[i]}\n\n"
        out3 = _llm_content(
            "【重要：不要输出任何思考过程，立即按 ###N### 编号逐段输出译文】\n" + sub_prompt,
            "lit_trans_blocks_sub", temperature=0.1, max_tokens=12000,
            retry_prefix="【直接输出译文，不要思考】\n", no_think=True)
        part3 = _parse_numbered_output(out3, len(blocks))
        for i in missing:
            if part3[i]:
                res[i] = part3[i]
    return res


def _normalize_zh(results: list, blocks: list) -> list:
    """译文块归一化：折叠块内空行/残余编号；空块回填原文。保证 zh 段数 == 原文段数。"""
    zh_parts = []
    for i, t in enumerate(results):
        t = (t or "").strip()
        t = re.sub(r"\n\s*\n+", "\n", t)
        t = re.sub(r"^#{1,6}\s*\d{1,3}\s*#{1,6}\s*", "", t, count=1)
        zh_parts.append(t or (blocks[i] if i < len(blocks) else ""))
    return zh_parts


def _split_text_sentences(text: str, max_chars: int = 1800) -> list:
    """按句子边界把长文本切成 ≤max_chars 的片段（单句超长时硬切）。"""
    out, cur = [], ""
    for part in re.split(r"(?<=[.!?。！？])\s+", text or ""):
        if not part:
            continue
        if cur and len(cur) + len(part) + 1 > max_chars:
            out.append(cur.strip())
            cur = part
        else:
            cur = (cur + " " + part) if cur else part
        while len(cur) > max_chars:
            out.append(cur[:max_chars].strip())
            cur = cur[max_chars:]
    if cur.strip():
        out.append(cur.strip())
    return [x for x in out if x] or [(text or "").strip()]


def _split_units(blocks: list, max_chars: int = 1800) -> list:
    """块 → 翻译单元 [(块下标, 文本)…]。

    PDF→Markdown 常把整页/整节并成一个“段”（实测某篇 31 段里 18 段 >6000 字符、
    最大 8995），整段送模型单次要 30–120s 且极易被 max_tokens 截断。
    这里按句子边界把超大段拆成小单元，译完再拼回原段，中英对照仍严格 1:1。
    """
    units = []
    for bi, b in enumerate(blocks):
        if len(b) <= max_chars:
            units.append((bi, b))
        else:
            for piece in _split_text_sentences(b, max_chars):
                units.append((bi, piece))
    return units


def _join_unit_texts(pieces: list) -> str:
    """把同一段的单元译文拼回一段（相邻都是中文则不插空格）。"""
    out = ""
    for p in pieces:
        p = (p or "").strip()
        if not p:
            continue
        if not out:
            out = p
            continue
        if re.search(r"[\u4e00-\u9fff]$", out) or re.match(r"^[\u4e00-\u9fff]", p):
            out += p
        else:
            out += " " + p
    return out


def translate_paper(file_or_title: str, progress_cb=None, force: bool = False) -> str:
    """学术中文翻译（批N2 2026-08-16；批O2 2026-08-16 升级为段落级编号直译）。

    旧实现按 9000 字符整块直译，段落会合并/分裂 → 中英对照无法逐段对齐。
    新实现：PDF→Markdown → 段落切块（与前端 litSplitBlocks 同规则）→
    每批 ≤8 段按 ###N### 编号直译 → 译文段落数与原文严格 1:1。
    幂等：已翻译且非 force 直接返回（不重复花钱）。
    progress_cb(phase, done, total, detail)。
    """
    _cb = progress_cb or (lambda *a, **k: None)
    try:
        lib = json.loads(list_library()).get("library", [])
    except Exception:
        lib = []
    needle = (file_or_title or "").strip().lower()
    hit = None
    for e in lib:
        if needle and (needle in (e.get("file") or "").lower()
                       or needle in (e.get("title") or "").lower()):
            hit = e
            break
    if not hit:
        return json.dumps({"ok": False, "error": f"文献库中未找到 '{file_or_title}'"},
                          ensure_ascii=False)
    pdf_path = _resolve_paper_path(hit)
    if not pdf_path or not os.path.isfile(pdf_path):
        return json.dumps({"ok": False, "error": f"PDF 文件不存在: {pdf_path}"}, ensure_ascii=False)
    stem = os.path.splitext(hit.get("file") or "")[0]
    os.makedirs(_translations_dir(), exist_ok=True)
    zh_path = os.path.join(_translations_dir(), f"{stem}.zh.md")
    if not force and os.path.isfile(zh_path) and os.path.getsize(zh_path) > 100:
        return json.dumps({"ok": True, "skipped": True, "paper": hit.get("title"),
                           "file": hit.get("file"),
                           "note": "已翻译过（幂等跳过）。force=true 可重新翻译。"},
                          ensure_ascii=False)
    _cb("convert", 0, 1, f"PDF → Markdown: {hit.get('file')}")
    md = pdf_to_markdown(pdf_path)
    if not md.strip():
        return json.dumps({"ok": False, "error": "PDF 无文字层且 OCR 不可用"}, ensure_ascii=False)
    blocks = _md_blocks(md)
    if not blocks:
        return json.dumps({"ok": False, "error": "Markdown 切段失败"}, ensure_ascii=False)
    # 批O3：断点续译——服务重启中断后，从 .part.json 恢复已译段落，只补未译批次
    part_json = zh_path + ".part.json"
    results = [""] * len(blocks)
    if force and os.path.isfile(part_json):
        try:
            with open(part_json, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, list) and len(saved) == len(blocks):
                results = saved
                _cb("convert", 0, 1, f"断点续译：已恢复 {sum(1 for t in saved if t)}/{len(blocks)} 段")
        except Exception as e:
            logger.warning(f"translation part load failed: {e}")

    def _flush_part():
        try:
            with open(part_json, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"translation part flush failed: {e}")

    # 批P1(2026-09-17)：超大段先拆成小单元再翻译。实测单段 3630 字符的整段直译要 32s，
    # 8–9k 字符的段会顶到 120s 超时/被 max_tokens 截断 → 拆单元后单次输出小，快且不截断。
    _uns = _split_units(blocks)
    _unit_text = [""] * len(_uns)
    batches = _batch_blocks([t for _bi, t in _uns], max_chars=6000, max_blocks=4)
    indexed = []
    _off = 0
    for batch in batches:
        indexed.append((_off, batch))
        _off += len(batch)
    # 断点续译：已完成的段（.part.json 里已有译文）直接用旧结果，其单元不再翻
    _block_done = [bool(results[i]) for i in range(len(blocks))]
    _units_of = {}
    for _ui, (_bi, _t) in enumerate(_uns):
        _units_of.setdefault(_bi, []).append(_ui)

    def _block_flush(bi):
        """某段所有单元都译完 → 拼回该段（保证译文段数 == 原文段数）。"""
        if _block_done[bi]:
            return
        _idxs = _units_of.get(bi) or []
        if _idxs and all(_unit_text[j] for j in _idxs):
            results[bi] = _join_unit_texts([_unit_text[j] for j in _idxs])
            _block_done[bi] = True

    pending = []
    for off, batch in indexed:
        if all(_block_done[_uns[off + k][0]] for k in range(len(batch))):
            continue
        pending.append((off, batch))
    # 批P1：默认 5 路并发（MEMOMICS_LIT_TRANS_WORKERS 可覆盖）
    _mw = max(1, min(10, int(os.environ.get("MEMOMICS_LIT_TRANS_WORKERS", "6"))))
    if pending:
        _cb("translate", 0, len(pending),
            f"段落级编号直译 {len(pending)}/{len(indexed)} 批（{len(_uns)} 单元，并发{_mw}）")
    _n_done = 0
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _one(off_batch):
            off, batch = off_batch
            return off, _translate_block_batch(batch)

        with ThreadPoolExecutor(max_workers=min(_mw, max(1, len(pending)))) as _ex:
            _futs = [_ex.submit(_one, ib) for ib in pending]
            for _f in as_completed(_futs):
                off, part = _f.result()
                for k, t in enumerate(part):
                    if t:
                        _unit_text[off + k] = t
                for bi in {_uns[off + k][0] for k in range(len(part))}:
                    _block_flush(bi)
                _n_done += 1
                _flush_part()  # 每完成一批落盘一次（服务重启可续）
                _cb("translate", _n_done, len(pending),
                    f"段落级翻译 {_n_done}/{len(pending)} 批（{sum(1 for d in _block_done if d)}/{len(blocks)} 段完成）")
    except Exception as e:
        logger.warning(f"parallel translate failed, fallback serial: {e}")
        _n_done = 0
        for off, batch in pending:
            part = _translate_block_batch(batch)
            for k, t in enumerate(part):
                if t:
                    _unit_text[off + k] = t
            for bi in {_uns[off + k][0] for k in range(len(part))}:
                _block_flush(bi)
            _n_done += 1
            _flush_part()
            _cb("translate", _n_done, len(pending), f"段落级翻译第 {_n_done}/{len(pending)} 批")
    # 缺单元兜底直译（单单元送模型，保证 1:1 完整）
    for _ui, (_bi, _txt) in enumerate(_uns):
        if _unit_text[_ui] or _block_done[_bi]:
            continue
        _cb("translate", _ui, len(_uns), f"补译第 {_ui + 1}/{len(_uns)} 单元")
        _unit_text[_ui] = _llm_content(
            "把下面这段英文文献翻译成学术严谨的中文（保持 Markdown 标题格式），"
            "输出为**单个段落，不要空行**，只输出译文：\n" + _txt,
            f"lit_trans_fix_{_ui}", temperature=0.2, max_tokens=6000,
            retry_prefix="【不要思考，立即输出译文】\n", no_think=True).strip()
        _block_flush(_bi)
        _flush_part()
    # 批O2c：块归一化——折叠块内空行/残余编号；仍为空的段落回填原文
    # （保证译文段落数与原文严格一致，中英对照逐段对齐不漂移）
    zh_parts = _normalize_zh(results, blocks)
    zh = "\n\n".join(zh_parts)
    if not zh.strip():
        return json.dumps({"ok": False, "error": "翻译失败：LLM 未返回译文"}, ensure_ascii=False)
    _cb("write", len(blocks), len(blocks), "写入 translations/<名>.zh.md")
    with open(zh_path, "w", encoding="utf-8") as f:
        f.write(zh)
    try:
        if os.path.isfile(part_json):
            os.remove(part_json)
    except Exception:
        pass
    # 索引标记 translated + 段落数（对照对齐依据）
    try:
        _idx_file = os.path.join(_library_dir(), ".pdf_index.json")
        _idx = _load_index(_idx_file)
        for _e in _idx:
            if _e.get("file") == hit.get("file"):
                _e["translated"] = True
                _e["translation_blocks"] = len(blocks)
        _save_index(_idx_file, _idx)
    except Exception as e:
        logger.warning(f"translated mark failed: {e}")
    _cb("done", len(blocks), len(blocks), "翻译完成")
    return json.dumps({"ok": True, "paper": hit.get("title"), "file": hit.get("file"),
                       "translation_file": f"hermes_home/papers/translations/{stem}.zh.md",
                       "blocks": len(blocks), "chars": len(zh)}, ensure_ascii=False, indent=2)


# ── 方向1：全文思路提炼（给人看，批J 2026-08-16）──
_SUMMARY_FIELDS = ["idea", "background", "species", "tissue", "problem",
                   "solution", "methods", "conclusion", "validation"]
_SUMMARY_FIELD_LABELS = {
    "idea": "思路", "background": "背景", "species": "物种", "tissue": "组织",
    "problem": "问题", "solution": "怎么解决", "methods": "方法",
    "conclusion": "结论", "validation": "怎么验证",
}


def _summaries_dir() -> str:
    return os.path.join(_library_dir(), "summaries")


def _translations_dir() -> str:
    return os.path.join(_library_dir(), "translations")


def _knowledge_dir() -> str:
    return os.path.join(_library_dir(), "knowledge")


def _load_summary_file(stem: str) -> str:
    p = os.path.join(_summaries_dir(), f"{stem}.md")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _resolve_paper_path(entry: dict) -> str:
    """文献 PDF 实际路径解析（批O5 2026-08-16：发布包可移植）。

    索引里存的是打包机上的绝对路径；用户解压到别的目录后路径失效。
    兜底策略：① 存路径存在直接用 ② 按文件名在当前文献库根目录找
    ③ 找不到才返回原路径（调用方会给出"PDF 不存在"错误）。
    """
    p = (entry.get("path") or "").strip()
    if p and os.path.isfile(p):
        return p
    f = (entry.get("file") or "").strip()
    if f:
        cand = os.path.join(_library_dir(), f)
        if os.path.isfile(cand):
            return cand
        # 宽松兜底：库内递归找同名文件（防历史条目放在子目录）
        try:
            for root, _dirs, fs in os.walk(_library_dir()):
                if f in fs:
                    return os.path.join(root, f)
        except Exception:
            pass
    return p


def _find_raw_entry(file_or_title: str) -> dict:
    """在两份索引（用户导入 + agent 下载）里按文件名/标题子串找原始条目。"""
    needle = (file_or_title or "").strip().lower()
    for idx_path in (os.path.join(_library_dir(), ".pdf_index.json"),
                     _agent_papers_index()):
        if not idx_path or not os.path.isfile(idx_path):
            continue
        for e in _load_index(idx_path):
            if needle and (needle in (e.get("file") or "").lower()
                           or needle in (e.get("title") or "").lower()):
                return e
    return {}


def _parse_summary_md(md: str) -> dict:
    """把 summaries/<stem>.md 的九项标题反解析回 dict（index 缺失时的兜底）。"""
    out = {}
    label_to_key = {v: k for k, v in _SUMMARY_FIELD_LABELS.items()}
    cur = None
    for ln in (md or "").splitlines():
        if ln.startswith("## "):
            key = label_to_key.get(ln[3:].strip())
            cur = key
            out.setdefault(key, [])
            continue
        if cur and ln.strip():
            out[cur].append(ln.strip())
    return {k: "\n".join(v).strip() for k, v in out.items() if v}


def _citations_for(entry: dict) -> dict:
    """为文献条目生成全套专业引文（GB/T 7714 ×2 / APA / NLM / MLA / BibTeX / RIS）。"""
    try:
        from memomics.bio_tools.reference_library import (_to_bibtex, _to_ris,
                                                          format_citation)
    except Exception:
        return {}
    meta = {"title": entry.get("title") or "", "authors": entry.get("authors") or "",
            "year": entry.get("year") or "", "doi": entry.get("doi") or "",
            "journal": entry.get("journal") or "",
            "url": entry.get("url") or (f"https://doi.org/{entry['doi']}" if entry.get("doi") else ""),
            "entry_type": entry.get("entry_type") or "article",
            "volume": entry.get("volume") or "", "issue": entry.get("issue") or "",
            "pages": entry.get("pages") or "", "pmid": entry.get("pmid") or ""}
    out = {"bibtex": _to_bibtex(meta), "ris": _to_ris(meta)}
    for style in ("gbt7714-numeric", "gbt7714-author-year", "apa", "nlm", "mla"):
        try:
            out[style] = format_citation(meta, style)
        except Exception as e:
            logger.warning(f"citation {style} failed: {e}")
            out[style] = ""
    return out


def get_summary(file_or_title: str) -> str:
    """查看某篇文献的完整详情（批O 2026-08-16 修复：从原始索引读全文摘要/作者/知识）。

    修复历史 bug：旧实现从 list_library 投影读 summary/authors（投影里根本没有
    这两个字段）→ 九项摘要恒为空、引用恒无作者。现在直读 .pdf_index.json 原始条目，
    摘要缺失时回退解析 summaries/<stem>.md。
    """
    hit = _find_raw_entry(file_or_title)
    if not hit:
        return json.dumps({"ok": False, "error": f"文献库中未找到 '{file_or_title}'"},
                          ensure_ascii=False)
    summary = dict(hit.get("summary") or {})
    stem = os.path.splitext(hit.get("file") or "")[0]
    md = _load_summary_file(stem)
    if not md and summary.get("markdown"):
        md = summary.get("markdown", "")
    if not summary:
        parsed = _parse_summary_md(md)
        if parsed:
            summary = parsed
    src_md = os.path.join(_markdown_dir(), f"{stem}.md")
    zh_md = os.path.join(_translations_dir(), f"{stem}.zh.md")
    knowledge = hit.get("knowledge") or {}
    k_md = os.path.join(_knowledge_dir(), f"{stem}.md")
    return json.dumps({"ok": True, "file": hit.get("file"), "title": hit.get("title"),
                       "journal": hit.get("journal"), "year": hit.get("year"),
                       "doi": hit.get("doi"), "authors": hit.get("authors") or [],
                       "volume": hit.get("volume") or "", "issue": hit.get("issue") or "",
                       "pages": hit.get("pages") or "", "pmid": hit.get("pmid") or "",
                       "imported_by": hit.get("imported_by") or "",
                       "summary": summary, "markdown": md,
                       "knowledge": knowledge,
                       "markdown_file": src_md.replace("\\", "/") if os.path.isfile(src_md) else "",
                       "translation_file": zh_md.replace("\\", "/") if os.path.isfile(zh_md) else "",
                       "knowledge_file": k_md.replace("\\", "/") if os.path.isfile(k_md) else "",
                       "citations": _citations_for(hit),
                       "summary_done": bool(hit.get("summary_done")),
                       "knowledge_done": bool(hit.get("knowledge_done")),
                       "kb_done": bool(hit.get("kb_done")),
                       "translated": bool(hit.get("translated")),
                       "meta_complete": bool(hit.get("volume") and hit.get("pages")),
                       }, ensure_ascii=False)


def summarize_paper(file_or_title: str, progress_cb=None, force: bool = False) -> str:
    """全文思路提炼（方向1，给人看）：9 项结构化摘要 + summaries/<名>.md 落盘。

    独立调用 LLM API（deepseek-v4-flash），模板与 literature-full-summary skill 一致。
    progress_cb(phase, done, total, detail)。force=True 时即使已提炼也重新提炼
    （默认幂等：已提炼直接返回，防并发重复调用烧 token）。
    """
    _cb = progress_cb or (lambda *a, **k: None)
    try:
        lib = json.loads(list_library()).get("library", [])
    except Exception:
        lib = []
    needle = (file_or_title or "").strip().lower()
    hit = None
    for e in lib:
        if needle and (needle in (e.get("file") or "").lower()
                       or needle in (e.get("title") or "").lower()):
            hit = e
            break
    if not hit:
        return json.dumps({"ok": False, "error": f"文献库中未找到 '{file_or_title}'"},
                          ensure_ascii=False)
    # 幂等守卫：直读索引原始条目（list_library 投影不含 summary 对象）
    _raw = {}
    for _e in _load_index(os.path.join(_library_dir(), ".pdf_index.json")):
        if _e.get("file") == hit.get("file"):
            _raw = _e
            break
    if not force and _raw.get("summary_done") and _raw.get("summary"):
        return json.dumps({"ok": True, "skipped": True, "paper": hit.get("title"),
                           "file": hit.get("file"),
                           "note": "已提炼过（幂等跳过）。如需重新提炼，用 force=true。"},
                          ensure_ascii=False)
    pdf_path = _resolve_paper_path(hit)
    if not pdf_path or not os.path.isfile(pdf_path):
        return json.dumps({"ok": False, "error": f"PDF 文件不存在: {pdf_path}"}, ensure_ascii=False)
    # 批N(2026-08-16)：PDF → Markdown 落盘 → 分节分块解读（替代 30K 字符一锅炖）
    _cb("convert", 0, 1, f"PDF → Markdown: {hit.get('file')}")
    md_text = pdf_to_markdown(pdf_path)
    if not md_text.strip():
        return json.dumps({"ok": False, "error": "PDF 无文字层且 OCR 不可用"}, ensure_ascii=False)
    stem = os.path.splitext(hit.get("file") or "")[0]
    md_path = os.path.join(_markdown_dir(), f"{stem}.md")
    _cb("summarize", 0, 1, f"分节解读(9项): {hit.get('title') or hit.get('file')} (md {len(md_text)} 字符)")
    base = (
        "你是生物医学文献解读员。按 literature-full-summary skill 的九问模板逐项提炼：\n"
        'JSON 字段：{"idea":"作者核心想法/切入点","background":"领域现状与空白",'
        '"species":"human/mouse/...","tissue":"skeletal_muscle/liver/...",'
        '"problem":"要回答的具体科学问题","solution":"如何设计实验/分析来回答",'
        '"methods":"关键技术/算法/统计方法(含阈值)","conclusion":"主要发现与结论",'
        '"validation":"如何验证(独立队列/实验/交叉方法)"}\n'
        "规则：每项 2-6 句中文，忠实原文；缺项写'未提及'，禁止编造；物种/组织用英文小写。\n"
        f"文献标题: {hit.get('title')} | 期刊: {hit.get('journal')} | DOI: {hit.get('doi')}\n"
    )
    summary = {}
    bullets = {}  # 批O: 合并失败时的兜底（分块要点直接拼成九项，不再整篇失败）
    try:
        if len(md_text) <= 18000:
            # 短文献：单次调用（Markdown 结构化后质量更好）
            txt = _llm_content(
                base + "输出 JSON 对象（不要其他文字）。以下为文献 Markdown（# 为标题）:\n" + md_text,
                "lit_summary", temperature=0.3, max_tokens=6000,
                retry_prefix="【重要：不要输出任何思考过程，立即输出最终 JSON 对象，第一个字符必须是 { 】\n",
                no_think=True)
            summary = _parse_json_object(txt)
        else:
            # 长文献：分节分块 → 每块提炼要点 → 合并成 9 项
            _cb("summarize", 0, 1, f"长文献分块解读: {len(_split_md_sections(md_text))} 节")
            chunks = _chunk_sections(_split_md_sections(md_text))
            bullets = {k: [] for k in _SUMMARY_FIELDS}

            def _sum_prompt(_i, chunk):
                return ("你是文献解读助手。对下面的文献片段，按 9 个字段各提炼 1-2 句要点，"
                        '输出 JSON：{"idea":[],"background":[],"species":[],"tissue":[],'
                        '"problem":[],"solution":[],"methods":[],"conclusion":[],"validation":[]}'
                        "（值都是字符串数组；该片段没涉及的字段给空数组；不要其他文字）\n" + chunk)

            _parts = _llm_chunks_parallel(
                chunks, _sum_prompt, "lit_chunk", progress_cb=_cb, phase="summarize",
                max_tokens=6000, retry_prefix="【不要思考，立即输出 JSON 数组，第一个字符必须是 { 】\n")
            for part in _parts:
                for k in _SUMMARY_FIELDS:
                    for v in (part.get(k) or []):
                        if isinstance(v, str) and v.strip():
                            bullets[k].append(v.strip())
            merged = "\n".join(f"{k}: " + "；".join(bullets[k][:12]) for k in _SUMMARY_FIELDS)
            txt = _llm_content(
                base + "以下是从全文各节提炼出的要点（按字段聚合），请据此写出最终的 9 项摘要，"
                "输出 JSON 对象（不要其他文字）:\n" + merged[:9000],
                "lit_summary_merge", temperature=0.3, max_tokens=12000,
                retry_prefix="【不要思考，立即输出最终 JSON 对象，第一个字符必须是 { 】\n",
                no_think=True)
            summary = _parse_json_object(txt)
    except Exception as e:
        logger.warning(f"lit_summary LLM 调用异常: {e}")
        summary = {}
    if not summary and bullets and any(bullets.values()):
        # 批O 兜底：合并调用失败时直接用分块要点拼九项（不烧 token、不整篇失败）
        logger.warning(f"lit_summary merge 失败，用分块要点兜底: file={hit.get('file')}")
        summary = {k: ("；".join(v[:8]) if v else "") for k, v in bullets.items()}
    if not summary or not any(summary.get(k) for k in _SUMMARY_FIELDS):
        logger.warning(f"lit_summary 最终失败: file={hit.get('file')}")
        return json.dumps({"ok": False,
                           "error": f"未能提炼出摘要（{hit.get('file')}：LLM 未输出有效 JSON，"
                                    "已自动重试；可稍后再试）"},
                          ensure_ascii=False)
    # 落盘 summaries/<stem>.md + 索引标记
    _cb("write", 1, 1, "写入摘要文件 + 标记已提炼")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md_lines = [f"# {hit.get('title') or hit.get('file')}",
                f"> 期刊 {hit.get('journal') or '—'} · {hit.get('year') or '—'} · DOI {hit.get('doi') or '—'} · 提炼于 {now}",
                ""]
    for k in _SUMMARY_FIELDS:
        v = str(summary.get(k) or "").strip() or "未提及"
        md_lines.append(f"## {_SUMMARY_FIELD_LABELS[k]}\n\n{v}\n")
    md = "\n".join(md_lines)
    os.makedirs(_summaries_dir(), exist_ok=True)
    with open(os.path.join(_summaries_dir(), f"{stem}.md"), "w", encoding="utf-8") as f:
        f.write(md)
    try:
        _idx_file = os.path.join(_library_dir(), ".pdf_index.json")
        _idx = _load_index(_idx_file)
        for _e in _idx:
            if _e.get("file") == hit.get("file"):
                _e["summary"] = dict(summary)
                _e["summary"].update({"markdown_file": f"papers/summaries/{stem}.md",
                                      "extracted_at": now})
                _e["summary_done"] = True
        _save_index(_idx_file, _idx)
    except Exception as e:
        logger.warning(f"summary mark failed: {e}")
    _cb("done", 1, 1, "全文提炼完成")
    return json.dumps({"ok": True, "paper": hit.get("title"), "file": hit.get("file"),
                       "summary": summary, "markdown_file": f"hermes_home/papers/summaries/{stem}.md"},
                      ensure_ascii=False, indent=2)


def summarize_all_papers(progress_cb=None) -> str:
    """一键全文提炼（方向1）：只处理未提炼（summary_done≠true）的文章。"""
    try:
        lib = json.loads(list_library()).get("library", [])
    except Exception:
        lib = []
    if not lib:
        return json.dumps({"ok": False, "error": "文献库为空"}, ensure_ascii=False)
    pending = [e for e in lib if not e.get("summary_done")]
    if not pending:
        return json.dumps({"ok": True, "total": len(lib), "pending": 0,
                           "results": [], "note": "全部文章都已提炼"},
                          ensure_ascii=False)
    _cb = progress_cb or (lambda *a, **k: None)
    n = len(pending)
    results = []
    for i, e in enumerate(pending):
        name = e.get("file") or e.get("title") or ""
        _cb("paper", i, n, f"[{i + 1}/{n}] 全文提炼: {e.get('title') or name}")
        try:
            r = json.loads(summarize_paper(name, progress_cb=(
                lambda ph, d, t, det, _i=i: _cb(ph, _i + (d / max(t, 1)) * 0.9, n,
                                                f"[{_i + 1}/{n}] {det}")
            )))
        except Exception as ex:
            r = {"ok": False, "error": str(ex)[:200]}
        results.append({"paper": e.get("title") or name, "ok": r.get("ok"),
                        "error": r.get("error", "")})
    ok_n = sum(1 for r in results if r["ok"])
    _cb("done", n, n, f"全文提炼完成: {ok_n}/{n} 篇成功")
    return json.dumps({"ok": ok_n > 0, "total": len(lib), "pending": n, "succeeded": ok_n,
                       "results": results,
                       "note": "9 项摘要已写入 hermes_home/papers/summaries/，可在文献库查看。"},
                      ensure_ascii=False, indent=2)


# ── 方向3：结构化知识提取（生物学知识 + 生信知识，批O 2026-08-16）──
_KNOWLEDGE_SCHEMA_HINT = (
    '{"biology":{"conclusions":["主要发现/结论，每条一句"],'
    '"gene_markers":[{"gene":"基因名","cell_type":"细胞类型","direction":"up/down/na","context":"说明"}],'
    '"cell_types":["涉及的细胞类型"],"pathways":["关键通路/信号轴"],'
    '"organoid":[{"name":"类器官名","species":"物种","media":"培养基","cytokines":["细胞因子"],'
    '"matrix":"基质胶/支架","duration":"培养时长"}],'
    '"chemicals":[{"compound":"化合物","target":"靶点","dose":"剂量","ic50":"IC50/EC50","model":"模型","effect":"效应"}]},'
    '"bioinfo":{"sequencing":[{"tech":"测序技术(如 scRNA-seq 10x v3)","platform":"测序平台","library":"建库","read_depth":"测序深度/读数"}],'
    '"pipeline":["分析步骤1 → 步骤2 → ..."],'
    '"software":[{"name":"软件/包名","version":"版本","lang":"R/Python","purpose":"用途"}],'
    '"parameters":[{"tool":"所属工具","param":"参数名","value":"参数值","context":"使用场景"}],'
    '"qc_params":[{"param":"质控参数","value":"阈值","context":"说明"}],'
    '"reference_genome":"参考基因组","databases":[{"name":"数据库","purpose":"用途"}]}}'
)


def _md_table(rows: list, columns: list) -> str:
    if not rows:
        return ""
    head = "| " + " | ".join(columns) + " |\n| " + " | ".join(["---"] * len(columns)) + " |\n"
    body = ""
    for r in rows:
        if not isinstance(r, dict):
            continue
        cells = [str(r.get(c) or "").replace("\n", " ").replace("|", "/") for c in columns]
        body += "| " + " | ".join(cells) + " |\n"
    return head + body


def _knowledge_to_markdown(k: dict, title: str, meta_line: str) -> str:
    """结构化知识 JSON → 人类可读 Markdown（knowledge/<stem>.md）。"""
    bio = k.get("biology") or {}
    bi = k.get("bioinfo") or {}
    L = [f"# {title}", f"> {meta_line}", ""]
    L.append("## 🧬 生物学知识")
    for label, key in (("📌 结论", "conclusions"), ("🫁 细胞类型", "cell_types"),
                       ("🔀 通路", "pathways")):
        vals = bio.get(key) or []
        if vals:
            L.append(f"### {label}\n" + "\n".join(f"- {v}" for v in vals) + "\n")
    markers = bio.get("gene_markers") or []
    if markers:
        L.append("### 🧬 基因 Marker\n" + _md_table(
            markers, ["gene", "cell_type", "direction", "context"]))
    organoid = bio.get("organoid") or []
    if organoid:
        L.append("### 🧫 类器官/培养条件\n" + _md_table(
            organoid, ["name", "species", "media", "cytokines", "matrix", "duration"]))
    chems = bio.get("chemicals") or []
    if chems:
        L.append("### ⚗️ 化合物/化学信息\n" + _md_table(
            chems, ["compound", "target", "dose", "ic50", "model", "effect"]))
    if not any(bio.get(x) for x in ("conclusions", "cell_types", "pathways",
                                    "gene_markers", "organoid", "chemicals")):
        L.append("（未提及）\n")
    L.append("## 💻 生信知识")
    seqs = bi.get("sequencing") or []
    if seqs:
        L.append("### 🔬 测序方法\n" + _md_table(
            seqs, ["tech", "platform", "library", "read_depth"]))
    pipe = bi.get("pipeline") or []
    if pipe:
        L.append("### 🧭 分析流程\n" + "\n".join(f"- {p}" for p in pipe) + "\n")
    soft = bi.get("software") or []
    if soft:
        L.append("### 📦 软件/包\n" + _md_table(soft, ["name", "version", "lang", "purpose"]))
    params = bi.get("parameters") or []
    if params:
        L.append("### 🎛️ 关键参数\n" + _md_table(params, ["tool", "param", "value", "context"]))
    qc = bi.get("qc_params") or []
    if qc:
        L.append("### 🧹 质控参数\n" + _md_table(qc, ["param", "value", "context"]))
    if bi.get("reference_genome"):
        L.append(f"### 🧬 参考基因组\n{bi['reference_genome']}\n")
    dbs = bi.get("databases") or []
    if dbs:
        L.append("### 🗄️ 数据库\n" + _md_table(dbs, ["name", "purpose"]))
    if not any(bi.get(x) for x in ("sequencing", "pipeline", "software", "parameters",
                                   "qc_params", "reference_genome", "databases")):
        L.append("（未提及）\n")
    return "\n".join(L)


def _safe_kb_name(stem: str, prefix: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.\-]", "_", stem or "paper")[:40].strip("_") or "paper"
    return f"{prefix}_{name}"[:64]


def _kb_write_fallbacks(tags: dict, k: dict) -> tuple:
    """物种列表标准化 + 组织/方向兜底（五级目录必填，缺失用 other 占位）。

    批O3: 物种走 save_knowledge.canonical_species（human→Homo_sapiens 等），
    返回去重后的标准物种列表（跨物种文章 → 多物种）。
    """
    from memomics.bio_tools.save_knowledge import canonical_species
    species = []
    for s in (tags.get("species") or []) or ["other"]:
        c = canonical_species(s)
        if c and c not in species:
            species.append(c)
    if not species:
        species = ["other"]
    ti = ((tags.get("tissue") or [""])[0] or "other").lower().replace(" ", "_")
    dr = ((tags.get("direction") or [""])[0] or "other").lower().replace(" ", "_")
    for seg in (ti, dr):
        if not re.fullmatch(r"[\w\u4e00-\u9fff_-]{1,64}", seg):
            ti, dr = "other", "other"
            break
    return species, ti, dr


def _write_knowledge_entries(hit: dict, k: dict, tags: dict, evidence: str) -> tuple:
    """把结构化知识写进 knowledge_base（批O3 2026-08-16 跨物种/化学域版）：

    - 生物学知识（结论/marker/细胞类型/通路/类器官）→ 每个物种各写一份 01_生物学知识
      （跨物种文章按物种拆分；基因名大小写由提取 prompt 保证，人全大写/鼠首字母大写）
    - 生信知识（测序/流程/软件/参数/参考基因组/数据库）→ 物种无关，只写一份
      common/general/03_测序方法/<assay>/
    - 质控阈值 → common/general/02_质控参数/<assay>/
    - 化合物 → 每化合物一条 chemistry/compounds/（化学类文章可检索复用）
    """
    from memomics.bio_tools.save_knowledge import save_knowledge
    written, rejected = [], []
    species_list, ti, dr = _kb_write_fallbacks(tags, k)
    stem = os.path.splitext(hit.get("file") or "")[0]
    bio = k.get("biology") or {}
    bi = k.get("bioinfo") or {}
    assay = str(tags.get("assay") or "RNA").upper()

    def _record(r, extra_note: str = ""):
        rec = {kk: r.get(kk) for kk in ("status", "name", "path", "error") if r.get(kk)}
        if extra_note:
            rec["note"] = extra_note
        (written if r.get("status") == "success" else rejected).append(rec)

    # 1) 生物学知识条目 —— 每个物种一份（跨物种拆分）
    bio_parts = []
    for label, key in (("结论", "conclusions"), ("细胞类型", "cell_types"), ("通路", "pathways")):
        vals = bio.get(key) or []
        if vals:
            bio_parts.append(f"## {label}\n" + "\n".join(f"- {v}" for v in vals))
    markers = bio.get("gene_markers") or []
    if markers:
        lines = [f"- {m.get('gene')}：{m.get('cell_type') or '—'}，{m.get('direction') or '—'}，{m.get('context') or ''}"
                 for m in markers if isinstance(m, dict)]
        bio_parts.append("## 基因 Marker\n" + "\n".join(lines))
    organoid = bio.get("organoid") or []
    if organoid:
        lines = [f"- {o.get('name')}：{o.get('species') or ''} | 培养基 {o.get('media') or '—'} | "
                 f"细胞因子 {', '.join(o.get('cytokines') or [])} | 基质 {o.get('matrix') or '—'} | {o.get('duration') or '—'}"
                 for o in organoid if isinstance(o, dict)]
        bio_parts.append("## 类器官/培养条件\n" + "\n".join(lines))
    chems = bio.get("chemicals") or []
    if chems:
        lines = [f"- {c.get('compound')}：靶点 {c.get('target') or '—'} | 剂量 {c.get('dose') or '—'} | "
                 f"IC50 {c.get('ic50') or '—'} | 模型 {c.get('model') or '—'} | {c.get('effect') or ''}"
                 for c in chems if isinstance(c, dict)]
        bio_parts.append("## 化合物/化学信息\n" + "\n".join(lines))
    if bio_parts:
        content = "\n\n".join(bio_parts)
        multi = len(species_list) > 1
        for sp in species_list:
            r = json.loads(save_knowledge(
                name=_safe_kb_name(stem, "paper_bio") + (f"_{sp.lower()}" if multi else ""),
                content=content,
                source="literature", evidence=evidence,
                verified="partially_verified",
                species=sp, tissue=ti, direction=dr,
                kb_category="01_生物学知识", assay_type=assay))
            _record(r, f"species={sp}")

    # 2) 生信知识条目 —— 物种无关，common 域一份
    bi_parts = []
    seqs = bi.get("sequencing") or []
    if seqs:
        lines = [f"- {s.get('tech')} | 平台 {s.get('platform') or '—'} | 建库 {s.get('library') or '—'} | 深度 {s.get('read_depth') or '—'}"
                 for s in seqs if isinstance(s, dict)]
        bi_parts.append("## 测序方法\n" + "\n".join(lines))
    pipe = bi.get("pipeline") or []
    if pipe:
        bi_parts.append("## 分析流程\n" + "\n".join(f"- {p}" for p in pipe))
    soft = bi.get("software") or []
    if soft:
        lines = [f"- {s.get('name')} {s.get('version') or ''}（{s.get('lang') or ''}）：{s.get('purpose') or ''}"
                 for s in soft if isinstance(s, dict)]
        bi_parts.append("## 软件/包\n" + "\n".join(lines))
    params = bi.get("parameters") or []
    if params:
        lines = [f"- {p.get('tool')}.{p.get('param')} = {p.get('value')}（{p.get('context') or ''}）"
                 for p in params if isinstance(p, dict)]
        bi_parts.append("## 关键参数\n" + "\n".join(lines))
    if bi.get("reference_genome"):
        bi_parts.append(f"## 参考基因组\n{bi['reference_genome']}")
    dbs = bi.get("databases") or []
    if dbs:
        bi_parts.append("## 数据库\n" + "\n".join(
            f"- {d.get('name')}：{d.get('purpose') or ''}" for d in dbs if isinstance(d, dict)))
    if bi_parts:
        r = json.loads(save_knowledge(
            name=_safe_kb_name(stem, "paper_bioinfo"),
            content="\n\n".join(bi_parts),
            source="literature", evidence=evidence,
            verified="partially_verified",
            domain="common", direction="general",
            kb_category="03_测序方法", assay_type=assay))
        _record(r, "domain=common")

    # 3) 质控参数条目 —— 物种无关，common 域
    qc = bi.get("qc_params") or []
    if qc:
        content = "\n".join(f"- {q.get('param')} = {q.get('value')}（{q.get('context') or ''}）"
                            for q in qc if isinstance(q, dict))
        r = json.loads(save_knowledge(
            name=_safe_kb_name(stem, "paper_qc"),
            content=content, source="literature", evidence=evidence,
            verified="partially_verified",
            domain="common", direction="general",
            kb_category="02_质控参数", assay_type=assay))
        _record(r, "domain=common")

    # 4) 化合物条目 —— chemistry/compounds/ 每化合物一条（化学类文章）
    for c in chems:
        if not isinstance(c, dict) or not c.get("compound"):
            continue
        slug = re.sub(r"[^A-Za-z0-9_.\-]", "_", str(c["compound"]))[:40].strip("_") or "compound"
        c_content = "\n".join(
            f"- {label}: {c.get(key) or '—'}"
            for label, key in (("靶点", "target"), ("剂量", "dose"), ("IC50/EC50", "ic50"),
                               ("模型", "model"), ("效应", "effect")))
        r = json.loads(save_knowledge(
            name=_safe_kb_name(stem, "chem") + f"_{slug}",
            content=c_content, source="literature", evidence=evidence,
            verified="partially_verified",
            domain="chemistry", direction="compounds"))
        _record(r, "domain=chemistry")
    return written, rejected


def extract_paper_knowledge(file_or_title: str, progress_cb=None, force: bool = False) -> str:
    """结构化知识提取（批O 2026-08-16）：生物学知识 + 生信知识。

    - 生物学知识：结论、基因 marker、细胞类型、通路、类器官/培养条件、化合物/化学信息
    - 生信知识：测序方法（技术/平台/建库/深度）、分析流程、软件包（含版本/语言）、
      关键参数、质控阈值、参考基因组、数据库
    产物：hermes_home/papers/knowledge/<名>.md（人读）+ 索引 knowledge JSON（机读）
          + knowledge_base 五级目录 YAML 条目（给 AI 检索复用）。
    """
    _cb = progress_cb or (lambda *a, **k: None)
    hit = _find_raw_entry(file_or_title)
    if not hit:
        return json.dumps({"ok": False, "error": f"文献库中未找到 '{file_or_title}'"},
                          ensure_ascii=False)
    if not force and hit.get("knowledge_done") and hit.get("knowledge"):
        return json.dumps({"ok": True, "skipped": True, "paper": hit.get("title"),
                           "file": hit.get("file"),
                           "note": "已提取过（幂等跳过）。force=true 可重新提取。"},
                          ensure_ascii=False)
    pdf_path = _resolve_paper_path(hit)
    if not pdf_path or not os.path.isfile(pdf_path):
        return json.dumps({"ok": False, "error": f"PDF 文件不存在: {pdf_path}"}, ensure_ascii=False)
    _cb("convert", 0, 1, f"PDF → Markdown: {hit.get('file')}")
    md_text = pdf_to_markdown(pdf_path)
    if not md_text.strip():
        return json.dumps({"ok": False, "error": "PDF 无文字层且 OCR 不可用"}, ensure_ascii=False)
    tags = hit.get("tags") or _classify_single(hit.get("title") or "")
    base = (
        "你是生信文献知识提炼专家。从文献中提取**可直接复用的知识**（给 AI 分析系统检索使用），"
        "输出 JSON 对象（不要其他文字）：\n"
        + _KNOWLEDGE_SCHEMA_HINT + "\n"
        "规则：① 只提取文献明确给出的信息，没有的字段给空数组/空串，禁止编造 ② 基因名/参数值/"
        "阈值/版本号必须原文原样 ③ 参数要带 tool 和 context（如 resolution=0.8 用于聚类）"
        " ④ 化学信息要给剂量/IC50/模型 ⑤ 类器官要给培养基/细胞因子/基质条件。\n"
        f"文献标题: {hit.get('title')} | 期刊: {hit.get('journal')} | DOI: {hit.get('doi')}\n"
        f"预分类: {json.dumps(tags, ensure_ascii=False)}\n"
    )
    knowledge = {}
    bullets = {}
    try:
        if len(md_text) <= 18000:
            txt = _llm_content(
                base + "输出 JSON 对象（不要其他文字）。以下为文献 Markdown（# 为标题）:\n" + md_text,
                "lit_knowledge", temperature=0.3, max_tokens=6000,
                retry_prefix="【重要：不要输出任何思考过程，立即输出最终 JSON 对象，第一个字符必须是 { 】\n",
                no_think=True)
            knowledge = _parse_json_object(txt)
        else:
            _cb("extract", 0, 1, f"长文献分块提取: {len(_split_md_sections(md_text))} 节")
            chunks = _chunk_sections(_split_md_sections(md_text))
            bullets = {"biology": [], "bioinfo": []}

            def _know_prompt(_i, chunk):
                return ("你是文献知识提炼助手。对下面的文献片段，按给出的 schema 提炼**结构化知识**，"
                        "输出 JSON 对象（不要其他文字）：\n" + _KNOWLEDGE_SCHEMA_HINT + "\n"
                        "（该片段没涉及的字段给空数组/空串）\n" + chunk)

            # max_tokens 4000 → 10000：实测 24 块里 20 块把 4000 额度全用在 reasoning 上、
            # content 为空 → 每块都白跑一遍再重试。给足额度后一次成型（推理+JSON 都装得下）。
            _parts = _llm_chunks_parallel(
                chunks, _know_prompt, "lit_know_chunk", progress_cb=_cb, phase="extract",
                max_tokens=10000, retry_prefix="【不要思考，立即输出 JSON 对象，第一个字符必须是 { 】\n")
            for part in _parts:
                for sec in ("biology", "bioinfo"):
                    bullets[sec].append(part.get(sec) or {})
            # 去重压缩后再合并：旧实现 merged[:12000] 会把后面几块的碎片直接截掉
            merged = json.dumps({sec: _compact_fragments(bullets[sec])
                                 for sec in ("biology", "bioinfo")}, ensure_ascii=False)
            # 批P3(2026-09-17)：碎片超长时不硬上合并调用。实测 24 块碎片（72k 字符）时
            # 合并调用必然失败（输出 JSON 过长 → 解析失败 → 退化），白花 20s 还丢内容。
            # 小/中篇走 LLM 合并（去重 + 冲突消解）；超长直接走下面的确定性聚合（内容一条不丢）。
            if len(merged) <= 14000:
                txt = _llm_content(
                    base + "以下是从全文各节提取出的知识碎片（按 biology/bioinfo 聚合，数组可能有重复/冲突），"
                    "请合并去重后输出最终的完整 JSON 对象（不要其他文字）:\n" + merged,
                    "lit_knowledge_merge", temperature=0.3, max_tokens=12000,
                    retry_prefix="【不要思考，立即输出最终 JSON 对象，第一个字符必须是 { 】\n",
                    no_think=True)
                knowledge = _parse_json_object(txt)
            else:
                logger.info(f"lit_knowledge 碎片 {len(merged)} 字符（{len(chunks)} 块）→ 跳过 LLM 合并，"
                            "用确定性聚合（去重并集，内容不丢）")
    except Exception as e:
        logger.warning(f"lit_knowledge LLM 调用异常: {e}")
        knowledge = {}
    if not knowledge and bullets.get("biology") and bullets.get("bioinfo"):
        # 兜底：合并失败时直接聚合分块碎片（列表字段并集、标量字段取首个非空）
        logger.warning(f"lit_knowledge merge 失败，用分块碎片兜底: file={hit.get('file')}")
        knowledge = {"biology": {}, "bioinfo": {}}
        for sec in ("biology", "bioinfo"):
            agg = {}
            for part in bullets[sec]:
                for k2, v2 in (part or {}).items():
                    if isinstance(v2, list):
                        agg.setdefault(k2, [])
                        for it in v2:
                            if it not in agg[k2]:
                                agg[k2].append(it)
                    elif isinstance(v2, str) and v2 and not agg.get(k2):
                        agg[k2] = v2
            knowledge[sec] = agg
    bio = knowledge.get("biology") or {}
    bi = knowledge.get("bioinfo") or {}
    if not any(bio.values()) and not any(bi.values()):
        return json.dumps({"ok": False,
                           "error": f"未能提取出知识（{hit.get('file')}：LLM 未输出有效 JSON，"
                                    "已自动重试；可稍后再试）"},
                          ensure_ascii=False)
    # 落盘 knowledge/<stem>.md + 索引 knowledge JSON
    _cb("write", 1, 1, "写入知识文件 + 知识库条目")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stem = os.path.splitext(hit.get("file") or "")[0]
    meta_line = (f"期刊 {hit.get('journal') or '—'} · {hit.get('year') or '—'} · "
                 f"DOI {hit.get('doi') or '—'} · 提取于 {now}")
    os.makedirs(_knowledge_dir(), exist_ok=True)
    with open(os.path.join(_knowledge_dir(), f"{stem}.md"), "w", encoding="utf-8") as f:
        f.write(_knowledge_to_markdown(knowledge, hit.get("title") or hit.get("file"), meta_line))
    evidence = f"DOI {hit.get('doi')} | {hit.get('title')} | {hit.get('path')}"
    written, rejected = _write_knowledge_entries(hit, knowledge, tags, evidence)
    try:
        _idx_file = os.path.join(_library_dir(), ".pdf_index.json")
        _idx = _load_index(_idx_file)
        for _e in _idx:
            if _e.get("file") == hit.get("file"):
                _e["knowledge"] = knowledge
                _e["knowledge_done"] = True
                _e["knowledge_extracted_at"] = now
                if written:
                    _e["kb_done"] = True
                    _e["kb_written_count"] = len(written)
        _save_index(_idx_file, _idx)
    except Exception as e:
        logger.warning(f"knowledge mark failed: {e}")
    _cb("done", 1, 1, f"知识提取完成: 写入 {len(written)} 条")
    return json.dumps({
        "ok": True, "paper": hit.get("title"), "file": hit.get("file"), "doi": hit.get("doi"),
        "knowledge": knowledge, "written": written, "rejected": rejected,
        "knowledge_file": f"hermes_home/papers/knowledge/{stem}.md",
        "note": "生物学知识(结论/marker/类器官/化学) → 01_生物学知识；生信知识(测序/流程/包/参数) → 03_测序方法；质控 → 02_质控参数。带 DOI 溯源。"},
        ensure_ascii=False, indent=2)


def extract_all_knowledge(progress_cb=None) -> str:
    """一键知识提取：只处理未提取（knowledge_done≠true）的文章（批O）。"""
    try:
        lib = json.loads(list_library()).get("library", [])
    except Exception:
        lib = []
    if not lib:
        return json.dumps({"ok": False, "error": "文献库为空"}, ensure_ascii=False)
    pending = [e for e in lib if not e.get("knowledge_done")]
    if not pending:
        return json.dumps({"ok": True, "total": len(lib), "pending": 0,
                           "results": [], "note": "全部文章都已提取知识"},
                          ensure_ascii=False)
    _cb = progress_cb or (lambda *a, **k: None)
    n = len(pending)
    results = []
    for i, e in enumerate(pending):
        name = e.get("file") or e.get("title") or ""
        _cb("paper", i, n, f"[{i + 1}/{n}] 知识提取: {e.get('title') or name}")
        try:
            r = json.loads(extract_paper_knowledge(name, progress_cb=(
                lambda ph, d, t, det, _i=i: _cb(ph, _i + (d / max(t, 1)) * 0.9, n,
                                                f"[{_i + 1}/{n}] {det}")
            )))
        except Exception as ex:
            r = {"ok": False, "error": str(ex)[:200]}
        results.append({"paper": e.get("title") or name, "ok": r.get("ok"),
                        "written": len(r.get("written") or []),
                        "rejected": len(r.get("rejected") or []),
                        "error": r.get("error", "")})
    ok_n = sum(1 for r in results if r["ok"])
    _cb("done", n, n, f"知识提取完成: {ok_n}/{n} 篇成功")
    return json.dumps({
        "ok": ok_n > 0, "total": len(lib), "pending": n, "succeeded": ok_n,
        "written_total": sum(r["written"] for r in results),
        "results": results,
        "note": "结构化知识(生物学+生信)已写入 papers/knowledge/ 与 knowledge_base 五级目录，带 DOI 溯源。"},
        ensure_ascii=False, indent=2)


# ── 元数据补全（批O 2026-08-16：引用格式正确性）──
_MOJIBAKE_MARKERS = ("茅", "帽", "鈥", "铆", "锚", "脜", "猫", "縫")


def _meta_suspect(e: dict) -> str:
    """判断元数据是否需要补全。返回 '' = 不需要。"""
    if not e.get("doi"):
        return "no_doi"
    blob = (str(e.get("title") or "") + " " + str(e.get("journal") or "") +
            " " + " ".join(e.get("authors") or []))
    if any(mk in blob for mk in _MOJIBAKE_MARKERS):
        return "mojibake"
    low = (e.get("doi") or "").lower()
    if any(j in low for j in _DOI_JUNK):
        return "junk_doi"
    if not (e.get("volume") and e.get("pages")):
        return "incomplete"
    return ""


def enrich_paper_metadata(file_or_title: str, progress_cb=None) -> str:
    """Crossref 补全/修正单篇元数据（卷/期/页码/PMID/作者乱码/错误 DOI/标题）。"""
    _cb = progress_cb or (lambda *a, **k: None)
    hit = _find_raw_entry(file_or_title)
    if not hit:
        return json.dumps({"ok": False, "error": f"文献库中未找到 '{file_or_title}'"},
                          ensure_ascii=False)
    pdf_path = _resolve_paper_path(hit)
    if not pdf_path or not os.path.isfile(pdf_path):
        return json.dumps({"ok": False, "error": f"PDF 文件不存在: {pdf_path}"}, ensure_ascii=False)
    _cb("read", 0, 1, f"重新提取 DOI: {hit.get('file')}")
    text = _pdf_text(pdf_path, pages=2)
    doi = ""
    m = DOI_RE.search(text or "")
    if m:
        doi = _clean_doi(m.group(0))
    # 1) 优先用 PDF 里新抓到的 DOI（可能修正了旧的水印脏 DOI）
    _updated = {}
    if doi and doi != hit.get("doi"):
        try:
            cr = _crossref_by_doi(doi)
            _updated.update(cr)
            _cb("fetch", 0, 1, f"Crossref 命中新 DOI: {doi}")
        except Exception as e:
            logger.debug(f"crossref {doi} failed: {e}")
    # 2) 否则用旧 DOI 补全
    if not _updated and hit.get("doi"):
        try:
            _updated.update(_crossref_by_doi(hit.get("doi")))
            _cb("fetch", 0, 1, f"Crossref 补全: {hit.get('doi')}")
        except Exception:
            _updated = {}
    # 3) 仍无结果 → 标题书目检索
    if not _updated:
        guess = hit.get("title") or _pdf_title_guess(pdf_path) or ""
        if guess:
            try:
                import difflib
                import urllib.parse
                import urllib.request
                url = ("https://api.crossref.org/works?query.bibliographic="
                       + urllib.parse.quote(guess[:200]) + "&rows=3")
                req = urllib.request.Request(url, headers=_CROSSREF_UA)
                with urllib.request.urlopen(req, timeout=15) as r:
                    d = json.loads(r.read().decode("utf-8"))
                items = (d.get("message") or {}).get("items") or []
                items = [it for it in items
                         if not ((it.get("title") or [""])[0] or "").lower().startswith("review for")]
                if items:
                    best = max(items, key=lambda it: difflib.SequenceMatcher(
                        None, guess.lower()[:120], ((it.get("title") or [""])[0] or "").lower()[:120]).ratio())
                    _ratio = difflib.SequenceMatcher(
                        None, guess.lower()[:120], ((best.get("title") or [""])[0] or "").lower()[:120]).ratio()
                    if _ratio >= 0.55:
                        it = best
                        _updated = {
                            "title": (it.get("title") or [""])[0],
                            "journal": (it.get("container-title") or [""])[0],
                            "authors": [f"{a.get('given','')} {a.get('family','')}".strip()
                                        for a in it.get("author", [])][:20],
                            "year": str((it.get("published", {}).get("date-parts", [[None]])[0] or [None])[0] or ""),
                            "doi": it.get("DOI") or "", "volume": it.get("volume") or "",
                            "issue": it.get("issue") or "", "pages": it.get("page") or it.get("article-number") or "",
                        }
                        _cb("fetch", 0, 1, f"Crossref 书目检索命中: {_updated['title'][:60]}")
            except Exception as e:
                logger.debug(f"crossref biblio enrich failed: {e}")
    if not _updated:
        return json.dumps({"ok": False, "error": "Crossref 未命中（DOI 无效且标题检索失败），元数据未改动"},
                          ensure_ascii=False)
    # 更新索引 + 引用库
    _cb("write", 1, 1, "更新索引与引用库")
    idx_file = os.path.join(_library_dir(), ".pdf_index.json")
    idx = _load_index(idx_file)
    changed = []
    for _e in idx:
        if _e.get("file") == hit.get("file"):
            for k in ("title", "journal", "authors", "year", "doi", "volume", "issue", "pages", "pmid"):
                v = str(_updated.get(k) or "").strip()
                if v and v != str(_e.get(k) or ""):
                    _e[k] = (_updated.get(k) if isinstance(_updated.get(k), list) else v)
                    changed.append(k)
            if _updated.get("doi") and _e.get("doi"):
                _e["url"] = f"https://doi.org/{_e['doi']}"
            break
    _save_index(idx_file, idx)
    try:
        from memomics.bio_tools.reference_library import save_reference
        for _e in idx:
            if _e.get("file") == hit.get("file"):
                save_reference("add", {
                    "title": _e.get("title") or "", "authors": ";".join(_e.get("authors") or []),
                    "year": _e.get("year") or "", "doi": _e.get("doi") or "",
                    "journal": _e.get("journal") or "", "url": _e.get("url") or "",
                    "entry_type": "article", "volume": _e.get("volume") or "",
                    "issue": _e.get("issue") or "", "pages": _e.get("pages") or "",
                    "pmid": _e.get("pmid") or "", "note": f"local_pdf: {_e.get('path')}",
                }, global_lib=True)
                break
    except Exception as e:
        logger.warning(f"reference re-register failed: {e}")
    _cb("done", 1, 1, "元数据补全完成")
    return json.dumps({"ok": True, "paper": _updated.get("title") or hit.get("title"),
                       "file": hit.get("file"), "changed": changed, "meta": _updated},
                      ensure_ascii=False, indent=2)


def enrich_all_metadata(progress_cb=None) -> str:
    """一键补全：对所有疑似缺卷/期/页、乱码作者、脏 DOI 的文献做 Crossref 补全（批O）。"""
    try:
        lib = json.loads(list_library()).get("library", [])
    except Exception:
        lib = []
    suspects = []
    for e in lib:
        reason = _meta_suspect(e)
        if reason:
            suspects.append((e, reason))
    if not suspects:
        return json.dumps({"ok": True, "total": len(lib), "pending": 0,
                           "results": [], "note": "元数据已全部完整"}, ensure_ascii=False)
    _cb = progress_cb or (lambda *a, **k: None)
    n = len(suspects)
    results = []
    for i, (e, reason) in enumerate(suspects):
        name = e.get("file") or e.get("title") or ""
        _cb("paper", i, n, f"[{i + 1}/{n}] 补全({reason}): {name[:80]}")
        try:
            r = json.loads(enrich_paper_metadata(name))
        except Exception as ex:
            r = {"ok": False, "error": str(ex)[:200]}
        results.append({"paper": e.get("title") or name, "file": e.get("file"),
                        "ok": r.get("ok"), "changed": r.get("changed") or [],
                        "error": r.get("error", "")})
        time.sleep(0.4)  # 温和限速，防 Crossref 限流
    ok_n = sum(1 for r in results if r["ok"])
    _cb("done", n, n, f"元数据补全完成: {ok_n}/{n} 篇")
    return json.dumps({"ok": ok_n > 0, "total": len(lib), "pending": n, "succeeded": ok_n,
                       "results": results, "note": "Crossref 补全卷/期/页码/PMID，修正乱码作者与脏 DOI。"},
                      ensure_ascii=False, indent=2)


def export_citations() -> str:
    """导出整库引文（批O 2026-08-16）：BibTeX/RIS/GB/T 7714 全量文本。"""
    lib = []
    for idx_path in (os.path.join(_library_dir(), ".pdf_index.json"),
                     _agent_papers_index()):
        if idx_path and os.path.isfile(idx_path):
            lib.extend(_load_index(idx_path))
    if not lib:
        return json.dumps({"ok": False, "error": "文献库为空"}, ensure_ascii=False)
    bibs, riss, gbts = [], [], []
    n = 0
    for e in lib:
        c = _citations_for(e)
        if not c:
            continue
        bibs.append(c.get("bibtex", ""))
        riss.append(c.get("ris", ""))
        g = c.get("gbt7714-numeric", "")
        if g:
            n += 1
            gbts.append(g.replace("[1] ", f"[{n}] ", 1))
    return json.dumps({
        "ok": True, "total": len(lib),
        "bibtex": "\n\n".join(b for b in bibs if b),
        "ris": "\n\n".join(r for r in riss if r),
        "gbt7714": "\n".join(gbts),
    }, ensure_ascii=False)


# ── 双语对照文档（批O4 2026-08-16：真 PDF 原文 + 模块化译文 + 点击互映射）──
def _norm_ws(s: str) -> str:
    """空白归一化（用于跨页面/PDF 文本匹配）。"""
    return re.sub(r"\s+", " ", (s or "")).strip()


def _pdf_pages_text(path: str) -> list:
    """逐页文本（空白归一化，用于段落→页码定位）。"""
    try:
        import pymupdf as fitz
        doc = fitz.open(path)
        pages = [_norm_ws(doc[i].get_text("text")) for i in range(doc.page_count)]
        doc.close()
        return pages
    except Exception as e:
        logger.warning(f"pdf pages text failed: {e}")
        return []


def _pdf_toc(path: str) -> list:
    """PDF 书签目录 → [{'level':int,'title':str,'page':int(0-based)}, ...]。"""
    try:
        import pymupdf as fitz
        doc = fitz.open(path)
        toc = doc.get_toc()
        doc.close()
        out = []
        for level, title, page in (toc or []):
            t = _norm_ws(title)
            if not t:
                continue
            pg = max(0, min(int(page) - 1, 9999))
            out.append({"level": int(level), "title": t[:120], "page": pg})
        return out
    except Exception as e:
        logger.warning(f"pdf toc failed: {e}")
        return []


def _pdf_heading_pages(path: str) -> list:
    """无书签时的模块检测：每页最大字号行 → [{'title','page'}, ...]（批O4）。

    过滤规则：行文本 6-90 字符、不以句末标点结尾、字号 ≥ 该页正文字号的 1.15 倍。
    """
    try:
        import pymupdf as fitz
        doc = fitz.open(path)
        out = []
        for i in range(doc.page_count):
            page = doc[i]
            body_sizes = []
            cands = []
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    txt = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
                    size = max((s.get("size", 0) for s in line.get("spans", [])), default=0)
                    if len(txt) >= 20:
                        body_sizes.append(size)
                    if 6 <= len(txt) <= 90 and not txt.endswith((".", ",", ";")) and size >= 10:
                        cands.append((size, txt))
            if not cands:
                continue
            body_med = sorted(body_sizes)[len(body_sizes) // 2] if body_sizes else 10
            cands = sorted(cands, key=lambda x: -x[0])
            best = cands[0]
            if best[0] >= body_med * 1.15 or len(body_sizes) < 3:
                out.append({"title": _norm_ws(best[1])[:120], "page": i, "level": 1})
        doc.close()
        return out
    except Exception as e:
        logger.warning(f"pdf heading pages failed: {e}")
        return []


def _map_blocks_to_pages(blocks: list, pages_text: list) -> list:
    """段落 → 页码（0-based）。前缀精确匹配 → 缩略前缀 → 全文包含兜底。"""
    page_of = []
    for b in blocks:
        nb = _norm_ws(re.sub(r"^#{1,6}\s*", "", b))
        hit = -1
        for prefix_len in (48, 28, 16):
            key = nb[:prefix_len]
            if len(key) < 8:
                continue
            for i, pt in enumerate(pages_text):
                if key in pt:
                    hit = i
                    break
            if hit >= 0:
                break
        if hit < 0 and len(nb) >= 8:
            for i, pt in enumerate(pages_text):
                if nb[:12] and nb[:12] in pt:
                    hit = i
                    break
        page_of.append(hit if hit >= 0 else -1)
    return page_of


def _find_block_rect(path: str, page_no: int, text: str) -> list:
    """段落首句在页面上的归一化矩形 [x0,y0,x1,y1]（0~1），找不到返回 null。

    用 page.search_for 逐级缩短前缀定位（PyMuPDF C 级文本定位，无需 OCR）。
    """
    try:
        import pymupdf as fitz
        doc = fitz.open(path)
        if page_no < 0 or page_no >= doc.page_count:
            doc.close()
            return None
        page = doc[page_no]
        p_w, p_h = page.rect.width, page.rect.height
        key = _norm_ws(re.sub(r"^#{1,6}\s*", "", text))
        words = key.split()
        for n in (12, 8, 5, 3):
            if len(words) < n:
                continue
            probe = " ".join(words[:n])
            rects = page.search_for(probe)
            if rects:
                r = rects[0]
                doc.close()
                return [round(r.x0 / p_w, 4), round(r.y0 / p_h, 4),
                        round(r.x1 / p_w, 4), round(r.y1 / p_h, 4)]
        doc.close()
        return None
    except Exception:
        return None


# ── 批Q(2026-09-23)：句级锚定引擎（点译文任意一句 → 精确框出原文）────────────────────
# 旧实现 _find_block_rect 只把"整段前 12/8/5/3 个词"在整页里 search_for 取第一个命中：
#   ① 双栏 PDF 常命中另一栏的同词 → 高亮框错位；
#   ② PDF→Markdown 的"段"可达数千字符，一次搜不到 → rect 为空（点译文毫无反应）。
# 新实现：把 PDF 文本层按"行"重建（行内间距 >12pt 断行、行尾连字符合并），
# 段落/句子用 token 锚定 + 贪婪扩展落到行区间 → 每句都有页码 + 逐行并集矩形。

_ANCH_TOK_RE = re.compile(r"\w+(?:['\u2019\-/]\w+)*")
_ANCH_SENT_RE = re.compile(r"[^.!?\u3002\uff01\uff1f]+(?:[.!?\u3002\uff01\uff1f]+[\"'\u201d\u2019)\]]*)?")
_ANCH_HYPHEN_RE = re.compile(r"[-\u2010\u00ad]\s*$")
_ANCH_TITLE_RE = re.compile(r"^#{1,6}\s*")
_ANCH_GAP_BREAK = 12.0     # 行内视觉断档（pt）：大于此值视为分栏/分列，断开成两行
_ANCH_LIG = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00ad": "",
    "\u00a0": " ", "\u2002": " ", "\u2003": " ", "\u2007": " ", "\u2009": " ",
    "\u200a": " ", "\u202f": " ", "\u3000": " ",
}


def _anch_norm_chars(s: str):
    """归一化（大小写/连字/引号/空白）→ (归一化串, 每个字符对应的原串下标)。

    连续空白折叠成单个空格：Markdown 里"行尾空格 + 换行"与 PDF 文本层的换行
    归一化后必须一致，否则整句永远匹配不上（实测某句因此漏配）。
    """
    out, idx = [], []
    prev_space = False
    for i, ch in enumerate(s or ""):
        lo = ch.lower()
        rep = _ANCH_LIG.get(lo)
        if rep is None:
            rep = " " if ch.isspace() else lo
        for r in rep:
            if r == " ":
                if prev_space:
                    continue
                prev_space = True
            else:
                prev_space = False
            out.append(r)
            idx.append(i)
    return "".join(out), idx


def _anch_norm_map(s: str):
    """归一化（大小写/连字/引号/空白）并给出每个归一化字符对应的原串下标。"""
    return _anch_norm_chars(s)


def _anch_tokens(norm_text: str) -> list:
    """归一化文本 → [(token, start, end)…]（锚定用的最小单位）。"""
    out = []
    for m in _ANCH_TOK_RE.finditer(norm_text or ""):
        t = m.group(0).strip("-'/")
        if len(t) >= 2:
            out.append((t, m.start(), m.end()))
    return out


_ANCH_ABBREV = {"fig", "figs", "eq", "eqs", "no", "nos", "vs", "etc", "al", "ref", "refs",
                "sec", "approx", "ca", "dr", "prof", "suppl", "supp", "resp", "sd", "sem",
                "min", "max", "inc", "ltd", "co", "st", "chr", "tab", "table", "extended", "data"}


def _anch_ends_abbrev(text: str, pos: int) -> bool:
    """pos 处是否是"缩写/编号"造成的假句末（Fig. / e.g. / A. / 5d,）。"""
    tail = (text or "")[max(0, pos - 18):pos]
    ch = (tail[-1:] or "")
    if ch in ",;:":
        return True
    w = re.search(r"([A-Za-z][A-Za-z\.]{0,12})\s*$", tail)
    if not w:
        return False
    word = w.group(1).strip(".").lower()
    if word in _ANCH_ABBREV:
        return True
    return len(word) == 1   # 单字母（人名缩写）不当句末


def _sentence_ranges(text: str) -> list:
    """句级切分（含末尾标点与右引号）→ [(start, end)…]（原串下标）。

    缩写/编号（Fig. 3a,b / e.g. / A. Smith）不算句末；下一片段以小写字母开头时
    也并回前句——否则会切出 "5e,f)." 这类永远定位不到的碎句。
    """
    out = []
    for m in _ANCH_SENT_RE.finditer(text or ""):
        raw = m.group(0)
        a = m.start() + (len(raw) - len(raw.lstrip()))
        b = m.end() - (len(raw) - len(raw.rstrip()))
        if b - a < 2:
            continue
        if not out:
            out.append([a, b])
            continue
        prev = out[-1]
        nxt = text[a:a + 1]
        prev_ch = text[prev[1] - 2:prev[1] - 1]
        merge = (_anch_ends_abbrev(text, prev[1]) or nxt.islower()
                 or (prev_ch.isdigit() and nxt.isdigit()))   # "88." + "5%" 不是句末
        if merge:
            prev[1] = b
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _anch_gap_split(xs: list, gap: float = _ANCH_GAP_BREAK) -> list:
    """按坐标间隔把一行切成若干段 → [[下标…]…]（栏/表格分列时用）。"""
    out, cur = [], []
    for i, x in enumerate(xs or []):
        if cur and (x - xs[i - 1]) > gap:
            out.append(cur)
            cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


def _anch_push_line(lines: list, page_no: int, seg: list, blk: int = -1):
    if not seg:
        return
    txt = "".join(c["c"] for c in seg).strip()
    if not txt or not txt.strip("-\u2010\u00ad"):
        return
    lines.append({
        "page": page_no, "blk": blk, "text": txt,
        "x0": min(c["bbox"][0] for c in seg), "y0": min(c["bbox"][1] for c in seg),
        "x1": max(c["bbox"][2] for c in seg), "y1": max(c["bbox"][3] for c in seg),
    })


def _pdf_line_layer(path: str) -> dict:
    """PDF 文本层 → 行（按 PDF 自身阅读顺序逐页）＋页面尺寸。

    行内字距 >_ANCH_GAP_BREAK 断成两行：双栏/多列表格同行文字不会被连成一行，
    两栏各自的换行才能被正确识别为"续行"（供连字符合并与矩形并集使用）。
    """
    out = {"n_pages": 0, "page_wh": [], "lines": []}
    try:
        import pymupdf as fitz
        doc = fitz.open(path)
    except Exception as e:
        logger.warning(f"text layer open failed: {e}")
        return out
    try:
        for pno in range(doc.page_count):
            page = doc[pno]
            out["page_wh"].append((page.rect.width or 595.0, page.rect.height or 842.0))
            raw = page.get_text("rawdict")
            for bi, blk in enumerate(raw.get("blocks", [])):
                if blk.get("type") != 0:
                    continue
                for ln in blk.get("lines", []):
                    chars = [c for sp in ln.get("spans", []) for c in sp.get("chars", []) if c.get("c")]
                    if not chars:
                        continue
                    seg = [chars[0]]
                    for prev, ch in zip(chars, chars[1:]):
                        if ch["bbox"][0] - prev["bbox"][2] > _ANCH_GAP_BREAK:
                            _anch_push_line(out["lines"], pno, seg, bi)
                            seg = []
                        seg.append(ch)
                    _anch_push_line(out["lines"], pno, seg, bi)
    except Exception as e:
        logger.warning(f"text layer build failed: {e}")
    finally:
        try:
            doc.close()
        except Exception:
            pass
    out["n_pages"] = len(out["page_wh"])
    return out


def _anch_is_continuation(a: dict, b: dict) -> bool:
    """b 是否是 a 的续行（同页同栏同块、紧邻下一行）——用于行尾连字符合并。

    必须同块：否则上一栏末行会与下一栏首行被连成"一行"，矩形横跨两栏。
    """
    if a.get("page") != b.get("page") or a.get("blk") != b.get("blk"):
        return False
    h = max(1.0, a["y1"] - a["y0"])
    gap = b["y0"] - a["y1"]
    return -1.5 <= gap <= max(8.0, 2.2 * h) and abs(b["x0"] - a["x0"]) <= 45.0


def _anch_index(lines: list, page_wh: list) -> dict:
    """行列表 → 锚定索引（拼接文本 + 归一化映射 + token 表 + 每页区间）。"""
    idx = {"lines": lines, "page_wh": page_wh, "ztext": "", "norm": "", "n2z": [],
           "z2n": [], "atom_of_z": [], "atoms": [], "toks": [], "tok_starts": [],
           "page_n": {}}
    if not lines:
        return idx
    atoms, parts, pos = [], [], 0
    i, n = 0, len(lines)
    while i < n:
        j = i
        while (j + 1 < n and _ANCH_HYPHEN_RE.search(lines[j].get("text") or "")
               and _anch_is_continuation(lines[j], lines[j + 1])):
            j += 1
        chunk = ""
        for k in range(i, j + 1):
            t = lines[k].get("text") or ""
            if k < j and _ANCH_HYPHEN_RE.search(t):
                t = _ANCH_HYPHEN_RE.sub("", t)
            chunk += t
        atoms.append({"lines": list(range(i, j + 1)), "z0": pos, "z1": pos + len(chunk)})
        parts.append(chunk)
        pos += len(chunk) + 1        # 行间以单个空格相接
        i = j + 1
    ztext = " ".join(parts)
    atom_of_z = [0] * len(ztext)
    for ai, a in enumerate(atoms):
        for z in range(a["z0"], min(a["z1"] + 1, len(ztext))):
            atom_of_z[z] = ai
    norm, n2z = _anch_norm_chars(ztext)
    z2n = [None] * (len(ztext) + 1)
    for ni, zi in enumerate(n2z):
        if z2n[zi] is None:
            z2n[zi] = ni
    nxt = len(n2z)
    for zi in range(len(ztext), -1, -1):
        if z2n[zi] is None:
            z2n[zi] = nxt
        else:
            nxt = z2n[zi]
    toks, starts, tok_pos, page_of_n = [], [], {}, []
    for m in _ANCH_TOK_RE.finditer(norm):
        t = m.group(0).strip("-'/")
        if len(t) < 2:
            continue
        toks.append((t, m.start(), m.end()))
        starts.append(m.start())
        tok_pos.setdefault(t, []).append(len(toks) - 1)
    page_n = {}
    for a in atoms:
        p = lines[a["lines"][0]]["page"]
        z0 = a["z0"]
        z1 = min(a["z1"], len(ztext) - 1) if ztext else 0
        n0, n1 = z2n[z0], z2n[z1]
        if p not in page_n:
            page_n[p] = [n0, n1]
        else:
            page_n[p][0] = min(page_n[p][0], n0)
            page_n[p][1] = max(page_n[p][1], n1)
    page_of_n = [0] * (len(norm) + 1)
    for ai, a in enumerate(atoms):
        p = lines[a["lines"][0]]["page"]
        n0, n1 = z2n[a["z0"]], z2n[min(a["z1"], max(0, len(ztext) - 1))]
        for n in range(n0, min(n1 + 1, len(page_of_n))):
            page_of_n[n] = p
    idx.update({"ztext": ztext, "norm": norm, "n2z": n2z, "z2n": z2n,
                "atom_of_z": atom_of_z, "atoms": atoms, "toks": toks,
                "tok_starts": starts, "tok_pos": tok_pos, "page_n": page_n,
                "page_of_n": page_of_n})
    return idx


def _anch_probes(qn: str, qtoks: list) -> list:
    """按 token 边界截取探针（长→短；前 1–3 个 token 在 PDF 里缺失时允许跳过）。

    探针必须完整 token 收尾（半截词永远匹配不上）；命中后由 _anch_refine 向两侧扩展
    把整句补齐，因此"短而稳"的探针反而最容易成功。
    """
    out = []
    if not qtoks:
        return [(qn.strip()[:400], 0, 0, len(qn.strip()[:400]))]
    for skip in (0, 1, 2, 3):
        if skip >= len(qtoks) - 1:
            break
        s0 = qtoks[skip][1]
        limits = (600, 320, 180, 90) if skip == 0 else (600,)
        for limit in limits:
            end, e0, e1 = None, 0, 0
            for (_t, s, e) in qtoks[skip:]:
                if e - s0 <= limit:
                    end, e0, e1 = e, s0, e
                else:
                    break
            if end and end - s0 >= 24:
                out.append((qn[s0:end], skip, e0, e1))
    return out


def _anch_find_norm(norm: str, probe: str) -> int:
    """探针在归一化文本中的位置（先精确；首端有胶连残留时从下一个完整 token 起找）。"""
    if not probe:
        return -1
    hit = norm.find(probe)
    if hit >= 0:
        return hit
    for cut in (1, 2, 3, 5):
        p2 = probe[cut:]
        if len(p2) < 24:
            break
        hit = norm.find(p2)
        if hit >= 0:
            return hit
    return -1


def _anch_refine(idx: dict, qtoks: list, n0: int, n1: int, q0: int = 0, q1: int = 0):
    """贪婪向两侧扩展 token 覆盖 → (n0, n1, 覆盖率)。

    q0/q1 是本次探针在"归一化 query"里的区间（query 坐标），覆盖率按 query token 算。
    """
    import bisect as _bs
    toks, starts = idx["toks"], idx["tok_starts"]
    norm = idx["norm"]

    def _cross_sentence(a: int, b: int) -> bool:
        """[a,b) 之间是否已经跨过句号（句号+空格+大写/数字）——跨过就不再扩展。"""
        return re.search(r"[.!?][\"\')\]]?\s+[A-Z0-9\u2018\u201c]", norm[a:b]) is not None

    qi = 0
    while qi < len(qtoks) and qtoks[qi][2] <= n1:
        qi += 1
    ai = _bs.bisect_left(starts, n1)
    edge = n1
    while qi < len(qtoks) and ai < len(toks):
        if (toks[ai][0] == qtoks[qi][0] and 0 <= toks[ai][1] - edge <= _ANCH_MAX_GAP
                and not _cross_sentence(n1, toks[ai][1])):
            edge = toks[ai][2]
            n1 = toks[ai][2]
            ai += 1
            qi += 1
        else:
            break
    qi = len(qtoks) - 1
    while qi >= 0 and qtoks[qi][1] >= n0:
        qi -= 1
    ai = _bs.bisect_left(starts, n0) - 1
    edge = n0
    while qi >= 0 and ai >= 0:
        if (toks[ai][0] == qtoks[qi][0] and 0 <= edge - toks[ai][2] <= _ANCH_MAX_GAP
                and not _cross_sentence(toks[ai][2], n0)):
            edge = toks[ai][1]
            n0 = toks[ai][1]
            ai -= 1
            qi -= 1
        else:
            break
    covered = sum(1 for (_t, s, e) in qtoks if s >= q0 and e <= q1) if q1 > q0 else 0
    return n0, n1, covered / max(1, len(qtoks))


def _anch_lines_rects(idx: dict, line_idx) -> list:
    """行下标 → 按页并集的归一化矩形 [{"page","rect","li"}…]（跨页自动拆分）。"""
    lines = idx["lines"]
    wh = idx.get("page_wh") or []
    groups = []
    for li in sorted(set(line_idx)):
        if li < 0 or li >= len(lines):
            continue
        ln = lines[li]
        if groups and groups[-1]["page"] == ln["page"] and li == groups[-1]["li"][-1] + 1:
            g = groups[-1]
            g["li"].append(li)
            g["x0"] = min(g["x0"], ln["x0"])
            g["y0"] = min(g["y0"], ln["y0"])
            g["x1"] = max(g["x1"], ln["x1"])
            g["y1"] = max(g["y1"], ln["y1"])
        else:
            groups.append({"page": ln["page"], "li": [li], "x0": ln["x0"], "y0": ln["y0"],
                           "x1": ln["x1"], "y1": ln["y1"]})
    out = []
    for g in groups:
        w, h = wh[g["page"]] if g["page"] < len(wh) else (595.0, 842.0)
        w = w or 595.0
        h = h or 842.0
        out.append({"page": g["page"], "li": g["li"],
                    "rect": [round(g["x0"] / w, 4), round(g["y0"] / h, 4),
                             round(g["x1"] / w, 4), round(g["y1"] / h, 4)]})
    return out


def _anch_span_rects(idx: dict, n0: int, n1: int) -> list:
    """归一化区间 → 文本层行区间矩形。"""
    n2z, atoms = idx["n2z"], idx["atoms"]
    if not n2z or not atoms:
        return []
    z0 = n2z[max(0, min(n0, len(n2z) - 1))]
    z1 = n2z[max(0, min(n1 - 1, len(n2z) - 1))]
    a0 = idx["atom_of_z"][z0]
    a1 = idx["atom_of_z"][min(z1, len(idx["atom_of_z"]) - 1)]
    li = []
    for ai in range(a0, a1 + 1):
        li.extend(atoms[ai]["lines"])
    return _anch_lines_rects(idx, li)


def _anch_pages(idx: dict, qtoks: list) -> list:
    """按 query token 命中数给候选页排名（全局探针失败时的逐页兜底）。"""
    norm = idx["norm"]
    score = {}
    for t in [x[0] for x in qtoks[:40]]:
        p = norm.find(t)
        if p < 0:
            continue
        for pg, (n0, n1) in idx["page_n"].items():
            if n0 <= p <= n1:
                score[pg] = score.get(pg, 0) + 1
                break
    return [p for p, _s in sorted(score.items(), key=lambda kv: -kv[1])[:2]]


def _anch_similarity(qn: str, seg: str) -> float:
    """query 归一化文本与命中片段归一化文本的相似度（抗断字/空格差异）。"""
    if not qn or not seg:
        return 0.0
    return difflib.SequenceMatcher(None, qn[:600], seg[:600]).ratio()


def _anch_span_ok(reps: list) -> bool:
    """矩形是否可信：跨行数不超上限，且不是"整页/整栏"式的大框。"""
    if not reps:
        return False
    li = [x for rep in reps for x in rep.get("li") or []]
    if not li or (max(li) - min(li)) > _ANCH_MAX_SPAN:
        return False
    for rep in reps:
        r = rep.get("rect") or []
        if len(r) == 4 and (r[2] - r[0]) > 0.55 and (r[3] - r[1]) > 0.55:
            return False
    return True


def _anch_grow_from(idx: dict, qtoks: list, qi: int, ni: int):
    """从"query 第 qi 个 token 命中文本层第 ni 个 token"出发向两侧对齐扩展。

    比"从句子开头找探针"更稳：句子开头若是页眉残留/被截断，仍能从中间某处锚定。
    """
    toks = idx["toks"]
    i, j = ni, qi
    while i > 0 and j > 0 and toks[i - 1][0] == qtoks[j - 1][0]:
        i -= 1
        j -= 1
    i0, j0 = i, j
    i, j = ni, qi
    while i + 1 < len(toks) and j + 1 < len(qtoks) and toks[i + 1][0] == qtoks[j + 1][0]:
        i += 1
        j += 1
    run = i - i0 + 1
    return toks[i0][1], toks[i][2], run / max(1, len(qtoks)), run


def _anch_search(q: str, idx: dict, hint_pages=None) -> list:
    """query → 文本层矩形（整篇定位失败时逐页重试）。"""
    norm = idx["norm"]
    qn, _qm = _anch_norm_map(q)
    qtoks = _anch_tokens(qn)
    if not qtoks:
        return []
    probes = _anch_probes(qn, qtoks)
    best = None
    for probe, _skip, q0, q1 in probes:
        hit = _anch_find_norm(norm, probe)
        if hit < 0:
            continue
        n0, n1, cov = _anch_refine(idx, qtoks, hit, hit + len(probe), q0, q1)
        if cov < _ANCH_MATCH_FLOOR:
            continue
        sim = _anch_similarity(qn, norm[n0:n1])
        if sim >= _ANCH_SIM_GOOD:
            return _anch_span_rects(idx, n0, n1)
        if best is None or sim > best[0]:
            best = (sim, n0, n1)
    if best and best[0] >= _ANCH_SIM_MIN:
        reps = _anch_span_rects(idx, best[1], best[2])
        if _anch_span_ok(reps):
            return reps
    for p in _anch_pages(idx, qtoks):
        n0p, n1p = idx["page_n"][p]
        sub = norm[n0p:n1p + 1]
        for probe, _skip, q0, q1 in probes:
            hit = sub.find(probe)
            if hit < 0:
                continue
            n0, n1, cov = _anch_refine(idx, qtoks, n0p + hit, n0p + hit + len(probe), q0, q1)
            reps = _anch_span_rects(idx, n0, n1) if cov >= 0.5 else []
            if reps:
                return reps
    # 末级兜底：任取句中一个 token 命中处向两侧扩展，取覆盖最长的一段
    best = None
    tok_pos = idx.get("tok_pos") or {}
    for qi in list(range(min(8, len(qtoks)))) + list(range(max(0, len(qtoks) - 4), len(qtoks))):
        for ni in (tok_pos.get(qtoks[qi][0]) or [])[:8]:
            n0, n1, cov, run = _anch_grow_from(idx, qtoks, qi, ni)
            if run < 10 or cov < 0.45:
                continue
            pg = idx["page_of_n"][n0] if idx.get("page_of_n") else -1
            score = (1 if (hint_pages and pg in hint_pages) else 0, round(cov, 3))
            if best is None or score > best[0]:
                best = (score, n0, n1)
    if best:
        reps = _anch_span_rects(idx, best[1], best[2])
        if _anch_span_ok(reps):
            return reps
    return []


def _anch_locate(query: str, idx: dict, memo: dict = None, hint_pages=None) -> list:
    """把一段文本锚定到文本层行 → [{"page","rect","li"}…]。"""
    q = _ANCH_TITLE_RE.sub("", (query or "").strip())
    if len(q) < 6 or not idx.get("norm"):
        return []
    key = (q[:120], tuple(sorted(hint_pages)) if hint_pages else None)
    if memo is not None and key in memo:
        return memo[key]
    res = _anch_search(q, idx, hint_pages=hint_pages)
    if memo is not None:
        memo[key] = res
    return res


def _anch_window(idx: dict, li0: int, li1: int, before: int = 0, after: int = 0,
                 lo: int = -1, hi: int = -1) -> list:
    """行区间 [li0,li1] 向两侧扩 before/after 行（lo/hi 为段落边界）→ 矩形。"""
    a = max(0, li0 - before) if lo < 0 else max(lo, li0 - before)
    b = (li1 + after) if hi < 0 else min(hi, li1 + after)
    if b < a:
        b = a
    return _anch_lines_rects(idx, list(range(a, b + 1)))


_ANCH_BRIDGE_LINES = 3      # 相邻句之间的空白行（页眉/夹注）允许跨过
_ANCH_MAX_SPAN = 34         # 锚定跨行上限（超过视为误配，宁可不框也不要框错）
_ANCH_MAX_GAP = 60          # 相邻 token 间允许的原始字符间隔（防"和/的"这类常用词把匹配拉飞）
_ANCH_MATCH_FLOOR = 0.45    # 最低 token 覆盖率：低于此判为误配，宁可退回段落框
_ANCH_SIM_GOOD = 0.78       # 归一化文本相似度闸门（防"匹配到别处的相似句子"）
_ANCH_SIM_MIN = 0.55        # 最低可接受相似度

def _anch_running_patterns(layer: dict) -> list:
    """页眉/页脚/页码行的正则（批Q）。

    Markdown 会把每页的 "532 | Nature | Vol 643 | 10 July 2025"、"Article" 混进段落，
    这些"运行页眉"既不是正文、又常与其它页重复 → 锚定前必须先剥掉。
    判据（从严，避免误伤正文）：① 页面上/下缘 5% 带内；② 行首是页码数字且行短；
    ③ 同一行文本在 ≥3 个不同页面出现（running head）。
    """
    lines = layer.get("lines") or []
    wh = layer.get("page_wh") or []
    occ = {}
    for ln in lines:
        txt = (ln.get("text") or "").strip()
        parts = txt.split()
        if not parts or len(parts) > 18:
            continue
        p = ln.get("page", 0)
        h = (wh[p][1] if p < len(wh) else 842.0) or 842.0
        occ.setdefault(txt.lower(), []).append(
            {"page": p, "y0": ln.get("y0", 0), "y1": ln.get("y1", 0), "h": h, "n": len(parts)})
    pats = []
    for key, rows in occ.items():
        ntok = rows[0]["n"]
        edge = any(r["y0"] < 0.05 * r["h"] or r["y1"] > 0.95 * r["h"] for r in rows)
        numbered = ntok <= 12 and re.match(r"^\d{1,4}\s*(?:\||$)", key) is not None
        pages = {r["page"] for r in rows}
        ys = [r["y0"] for r in rows]
        repeated = (len(pages) >= 5 and ntok <= 6
                    and (max(ys) - min(ys)) <= 10.0)
        if not (edge or numbered or repeated):
            continue
        pats.append(r"\s+".join(re.escape(x) for x in key.split()))
    pats.sort(key=len, reverse=True)
    return pats[:400]


def _anch_strip_heads(text: str, pats: list) -> str:
    """剥掉段落里混入的运行页眉/页脚（只影响锚定用的副本，不动译文展示）。"""
    for pat in pats:
        if not pat:
            continue
        # 词边界包夹：绝不允许把 "high" 这样的短页眉从 "highlighting" 里切掉
        rx = r"(?<![A-Za-z0-9])" + pat + r"(?![A-Za-z0-9])"
        if re.search(rx, text, flags=re.IGNORECASE):
            text = re.sub(rx, " ", text, flags=re.IGNORECASE)
    return text


def _anch_running_heads(idx: dict) -> list:
    return idx.get("head_pats") or []





def _anch_prepare(text: str, idx: dict):
    """段落 → (锚定用的 clean 文本, 句区间列表)。

    先把 Markdown 标题前缀与混进段落的运行页眉剥掉再切句——切句结果必须与
    译文侧（litSplitSentences）一致，否则译文句与原文句会错位一格。
    """
    title = _ANCH_TITLE_RE.match(text or "")
    clean = text[title.end():] if title else (text or "")
    clean = _anch_strip_heads(clean, _anch_running_heads(idx))
    return clean, _sentence_ranges(clean)


def _anchor_paragraph(text: str, idx: dict) -> dict:
    """段落级锚定 → {page, rects, units, pre, post}（批Q 2026-09-23）。

    逐句锚定：units[i] 与原文第 i 句一一对应（前端点译文任意一句 → 精确框原文那一句）；
    rects = 已定位句子的行并集（段落级"整段定位"）；pre/post = 首/末句上下一行的上下文宽框。
    句级定位失败的句子退化为 union 矩形并标 weak（前端虚线框），绝不整页乱框。
    """
    res = {"page": -1, "rects": [], "units": [], "pre": [], "post": []}
    if not text or not idx.get("lines") or not idx.get("norm"):
        return res
    clean, sents = _anch_prepare(text, idx)
    if not sents:
        return res
    memo = {}
    found = [None] * len(sents)
    for i, (s, e) in enumerate(sents):
        found[i] = _anch_locate(clean[s:e], idx, memo)
    located = [i for i, f in enumerate(found) if f]
    # 第二轮：用已定位的邻近句所在页做提示重试（跨栏/跨页句子常靠这一步救回）
    for i in [i for i, f in enumerate(found) if not f]:
        if not located:
            break
        near = min(located, key=lambda j: abs(j - i))
        hint = [found[near][0]["page"]]
        found[i] = _anch_locate(clean[sents[i][0]:sents[i][1]], idx, memo, hint)
        if found[i]:
            located.append(i)
    located.sort()
    # 段级 = 已定位句行并集（相邻句间隔 ≤_ANCH_BRIDGE_LINES 行则补齐中间行）
    li_all = []
    for i in located:
        sp = found[i]
        li_all.extend(range(min(sp[0]["li"]), max(sp[0]["li"]) + 1))
    li_all = sorted(set(li_all))
    if len(li_all) > _ANCH_MAX_SPAN:
        li_all = li_all[:_ANCH_MAX_SPAN]
    rects = _anch_lines_rects(idx, li_all) if li_all else []
    page = rects[0]["page"] if rects else -1
    pre = post = rects
    if located:
        f0, f1 = found[located[0]], found[located[-1]]
        pre = _anch_window(idx, min(f0[0]["li"]), max(f0[0]["li"]), before=2)
        post = _anch_window(idx, min(f1[0]["li"]), max(f1[0]["li"]), after=2)
    # 第三轮：位置推断——句子 i 没锚到，但前后句都锚到了 → 它必然夹在两者之间的行里
    infer = {}
    for i in range(len(sents)):
        if found[i]:
            continue
        prev = max([j for j in located if j < i], default=None)
        nxt = min([j for j in located if j > i], default=None)
        cand = []
        if prev is not None and nxt is not None:
            a, b = found[prev][0], found[nxt][0]
            la, lb = max(a["li"]), min(b["li"])
            if a["page"] == b["page"] and 0 <= lb - la - 1 <= 12:
                cand = _anch_lines_rects(idx, list(range(la + 1, lb)))
        if not cand and prev is not None:
            a = found[prev][0]
            cand = _anch_window(idx, max(a["li"]), max(a["li"]), after=2)
        if not cand and nxt is not None:
            b = found[nxt][0]
            cand = _anch_window(idx, min(b["li"]), min(b["li"]), before=2)
        if cand and _anch_span_ok(cand):
            infer[i] = cand
    units = []
    for i in range(len(sents)):
        sp = found[i]
        if sp and len(sp) == 1 and _anch_span_ok(sp):
            units.append({"p": sp[0]["page"], "r": sp[0]["rect"]})
        elif i in infer:
            c0 = infer[i][0]
            units.append({"p": c0["page"], "r": c0["rect"], "i": 1})
        elif sp:
            # 跨了页/栏：只留与最长片段同页的那部分，避免把整页都框进去
            best = max(sp, key=lambda x: len(x.get("li") or []))
            units.append({"p": best["page"], "r": best["rect"], "w": 1})
        else:
            units.append({"p": page, "r": (rects[0]["rect"] if rects else None), "w": 1})
    res.update({"page": page, "rects": rects, "pre": pre, "post": post, "units": units})
    return res


def _bilingual_cache_path(stem: str) -> str:
    return os.path.join(_translations_dir(), f"{stem}.bilingual.json")


# ---------------------------------------------------------------- 批Q：中英句级配对
_ANCH_CUE_RE = re.compile(r"[a-z]{0,3}\d{1,4}(?:[a-z]\d{0,2})?(?:[.,]\d+)*%?|[a-z]{4,}", re.I)
_ANCH_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_ZH_HEAD_NUM_RE = re.compile(r"\d+")


def _anch_cues(text: str) -> list:
    """句中的"锚点线索"：数字/编号（88.5%、2,293,951、CM08、E04、Fig. 3a）。

    翻译会保留数字与编号的先后顺序，用它们做中英句对的骨架对齐（LCS），
    比按句数比例切分稳得多——译文合并/拆句时也不会整段错位。
    """
    out = []
    for m in _ANCH_CUE_RE.finditer(text or ""):
        t = m.group(0).lower().strip(".")
        if len(t) >= 2 and (t[:1].isdigit() or re.match(r"^[a-z]{1,3}\d", t)):
            out.append(t)
    return out


def _anch_lcs_pairs(a: list, b: list) -> list:
    """最长公共子序列的配对下标 → [(ia, ib)…]（单调递增）。"""
    n, m = len(a), len(b)
    if not n or not m:
        return []
    if n * m > 400000:            # 超大段落退化为空（调用方走比例对齐）
        return []
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        row, nxt = dp[i], dp[i + 1]
        for j in range(m - 1, -1, -1):
            row[j] = nxt[j + 1] + 1 if a[i] == b[j] else max(nxt[j], row[j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if a[i] == b[j]:
            pairs.append((i, j))
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def _align_sentence_pairs(text_en: str, sents_en: list, text_zh: str, sents_zh: list) -> list:
    """中文句 → 英文句下标（单调不减，长度 = 中文句数）。

    骨架：两侧都出现的编号/数字做 LCS 配对；锚点之间按句数比例插值。
    与译文侧 litSplitSentences 的切分规则保持一致（同样断句 → 下标可直连）。
    """
    nz, ne = len(sents_zh or []), len(sents_en or [])
    if not nz or not ne:
        return []
    if nz == ne:
        return list(range(ne))
    flat_en = [(i, c) for i, (s, e) in enumerate(sents_en) for c in _anch_cues(text_en[s:e])]
    flat_zh = [(k, c) for k, (s, e) in enumerate(sents_zh) for c in _anch_cues(text_zh[s:e])]
    anchors = []
    if flat_en and flat_zh:
        for ia, ib in _anch_lcs_pairs([c for _, c in flat_en], [c for _, c in flat_zh]):
            i, k = flat_en[ia][0], flat_zh[ib][0]
            if anchors and (i <= anchors[-1][0] or k <= anchors[-1][1]):
                continue
            anchors.append([i, k])
    out = [0] * nz
    if not anchors:
        for k in range(nz):
            out[k] = min(ne - 1, int(round((k + 0.5) * ne / nz - 0.5)))
        return out
    i0, k0 = anchors[0]
    for k in range(0, k0):
        out[k] = max(0, min(ne - 1, int(round(i0 * (k + 1) / (k0 + 1)))))
    for ai in range(len(anchors)):
        i_a, k_a = anchors[ai]
        out[k_a] = i_a
        i_b, k_b = anchors[ai + 1] if ai + 1 < len(anchors) else (ne - 1, nz - 1)
        span_k, span_i = k_b - k_a, i_b - i_a
        for d in range(1, span_k):
            out[k_a + d] = i_a + int(round(d * span_i / span_k)) if span_k else i_a
    i_z, k_z = anchors[-1]
    for k in range(k_z + 1, nz):
        out[k] = i_z + int(round((k - k_z) * (ne - 1 - i_z) / max(1, nz - 1 - k_z)))
    for k in range(1, nz):
        if out[k] < out[k - 1]:
            out[k] = out[k - 1]
    return [max(0, min(ne - 1, x)) for x in out]


def _zh_sentence_payload(en: str, zh: str, anchor: dict, idx, zh_heads: set) -> list:
    """把一段中英对照切成"句子对" → [{z, u, w}]。

    o=[start,end] 为译文句中该句在 zh 段落里的字符区间（前端按区间切片渲染，零漂移）；
    u=对应原文句下标（_align_sentence_pairs）；w=1 表示该句锚定不可靠（前端画虚线框）。
    只返回需要渲染的句子——运行页眉整句被丢弃。
    """
    if not zh or not (zh or "").strip():
        return []
    if not idx:
        return [{"o": [s, e], "u": -1} for s, e in _sentence_ranges(zh)]
    clean_en, sents_en = _anch_prepare(en or "", idx)
    sents_zh = _sentence_ranges(zh)
    if not sents_zh:
        return []
    pairs = _align_sentence_pairs(clean_en, sents_en, zh, sents_zh)
    units = (anchor or {}).get("units") or []
    out = []
    for k, (s, e) in enumerate(sents_zh):
        if _zh_head_only(zh[s:e], zh_heads):
            continue
        u = pairs[k] if k < len(pairs) else -1
        unit = units[u] if 0 <= u < len(units) else None
        item = {"o": [s, e], "u": u}
        if unit is None or not unit.get("r") or unit.get("w"):
            item["w"] = 1
        out.append(item)
    return out


def _zh_running_keys(zh_text: str) -> set:
    """中文译文里重复出现的运行页眉/页脚行（数字归一后统计出现次数）。"""
    cnt = {}
    for ln in (zh_text or "").splitlines():
        ln = ln.strip()
        if not (2 <= len(ln) <= 90):
            continue
        key = _ZH_HEAD_NUM_RE.sub("#", ln.lower())
        if key.count("#") > 6:
            continue
        cnt[key] = cnt.get(key, 0) + 1
    # 整行重复出现 >=3 次才算运行页眉；正文句子几乎不可能整行重复，
    # 因此不会误伤（译文页眉里含"第643卷/2025年7月10日"这类中文，不能用"无中文"当判据）。
    return {k for k, v in cnt.items() if v >= 3}


def _zh_head_only(seg: str, keys: set) -> bool:
    """该句是否只是重复出现的运行页眉/页脚 → 不渲染、不参与配对。

    只认"重复出现"的整行（>=3 次）：参考文献条目等唯一内容一律保留。
    """
    t = (seg or "").strip()
    if not t:
        return True
    key = _ZH_HEAD_NUM_RE.sub("#", " ".join(t.split()).lower())
    if key in keys:
        return True
    return re.fullmatch(r"[\s\d|.–—]+", t) is not None   # 纯页码/分隔行


_BILINGUAL_SCHEMA = 3  # 模块结构版本（变动时自动重建缓存；批Q 句级锚定 + 中英句对）


def _anchor_cache_path(stem: str) -> str:
    return os.path.join(_translations_dir(), f"{stem}.anchors.json")


def _anchor_cache_ok(stem: str, md_path: str, zh_path: str) -> bool:
    """句级锚点缓存是否仍可用（schema 一致，且不早于原文 md / 译文）。"""
    p = _anchor_cache_path(stem)
    if not os.path.isfile(p):
        return False
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False
    if not data.get("paras") or data.get("_schema") != _BILINGUAL_SCHEMA:
        return False
    mt = os.path.getmtime(p)
    for src in (md_path, zh_path):
        if os.path.isfile(src) and os.path.getmtime(src) > mt:
            return False
    return True


def build_anchor_map(pdf_path: str, md_path: str, stem: str = "",
                     force: bool = False, progress_cb=None) -> list:
    """原文段落 → 文本层句级锚点（批Q 2026-09-23）。

    返回 [{"page","rects","pre","post","units":[{"p","r"}…]}…]，与 _md_blocks(md) 一一对应；
    缓存 translations/<stem>.anchors.json（原文 md 更新时自动重建）。
    """
    _cb = progress_cb or (lambda *a, **k: None)
    try:
        with open(md_path, encoding="utf-8") as f:
            md = f.read()
    except Exception as e:
        logger.warning(f"anchor md read failed: {e}")
        return []
    blocks = _md_blocks(md)
    stem = stem or os.path.splitext(os.path.basename(md_path))[0]
    cache_path = _anchor_cache_path(stem) if stem else ""
    if cache_path and not force and _anchor_cache_ok(stem, md_path,
                                                     os.path.join(_translations_dir(), f"{stem}.zh.md")):
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            if len(data.get("paras") or []) == len(blocks):
                return data["paras"]
        except Exception as e:
            logger.warning(f"anchor cache read failed: {e}")
    if not os.path.isfile(pdf_path):
        return [{"page": -1, "rects": [], "units": [], "pre": [], "post": []}] * len(blocks)
    _cb("anchor", 0, len(blocks), "构建句级锚点（文本层逐行定位）…")
    _layer = _pdf_line_layer(pdf_path)
    idx = _anch_index(_layer["lines"], _layer["page_wh"])
    idx["head_pats"] = _anch_running_patterns(_layer)
    paras, n_hit, n_units, n_u_hit, done = [], 0, 0, 0, 0
    for b in blocks:
        a = _anchor_paragraph(b, idx)
        if a.get("rects"):
            n_hit += 1
        n_units += len(a.get("units") or [])
        n_u_hit += sum(1 for u in (a.get("units") or []) if u.get("r"))
        paras.append(a)
        done += 1
        if done % 8 == 0 or done == len(blocks):
            _cb("anchor", done, len(blocks),
                f"句级锚点 {done}/{len(blocks)} 段（命中 {n_hit} 段 / {n_u_hit} 句）")
    logger.info(f"anchor map {stem}: 段命中 {n_hit}/{len(blocks)}，句命中 {n_u_hit}/{n_units}")
    if cache_path:
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"ok": True, "_schema": _BILINGUAL_SCHEMA, "stem": stem,
                           "blocks": len(blocks), "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           "paras": paras}, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"anchor cache write failed: {e}")
    return paras


def build_bilingual(file_or_title: str, rebuild: bool = False, progress_cb=None) -> str:
    """构建双语对照文档（批O4 2026-08-16；批Q 2026-09-23 句级锚定）。

    结构：
      {ok, file, stem, title, pages, has_zh,
       toc_source: 'toc'|'headings'|'none',
       modules: [{id, title, start_page, end_page, paras: [
                  {page, en, zh, rect:[x0,y0,x1,y1]|null}]}]}
    模块边界优先取 PDF 书签（get_toc），无书签时按页眉字号检测，都无 → 单模块"全文"。
    段落→页码/矩形走句级锚定（_anchor_paragraph）：文本层逐行定位，每句一个矩形，
    前端点译文任意一句即可精确框选原文（整段命中率低时退回 _find_block_rect 整体搜索）。
    结果缓存 translations/<stem>.bilingual.json（md/zh 更新时自动重建）。
    """
    hit = _find_raw_entry(file_or_title)
    if not hit:
        return json.dumps({"ok": False, "error": f"文献库中未找到 '{file_or_title}'"},
                          ensure_ascii=False)
    pdf_path = _resolve_paper_path(hit)
    if not pdf_path or not os.path.isfile(pdf_path):
        return json.dumps({"ok": False, "error": f"PDF 文件不存在: {pdf_path}"}, ensure_ascii=False)
    stem = os.path.splitext(hit.get("file") or "")[0]
    md_path = os.path.join(_markdown_dir(), f"{stem}.md")
    zh_path = os.path.join(_translations_dir(), f"{stem}.zh.md")
    cache_path = _bilingual_cache_path(stem)
    try:
        if not rebuild and os.path.isfile(cache_path):
            _src_newer = False
            for _p in (md_path, zh_path):
                if os.path.isfile(_p) and os.path.getmtime(_p) > os.path.getmtime(cache_path):
                    _src_newer = True
                    break
            if not _src_newer:
                with open(cache_path, encoding="utf-8") as f:
                    _cached = f.read()
                try:
                    _cj = json.loads(_cached)
                    if _cj.get("_schema") == _BILINGUAL_SCHEMA:
                        return _cached
                except Exception:
                    pass
    except Exception:
        pass
    # 原文 Markdown + 对齐译文
    md = pdf_to_markdown(pdf_path)
    blocks_en = _md_blocks(md)
    zh_text = ""
    if os.path.isfile(zh_path):
        try:
            with open(zh_path, encoding="utf-8") as f:
                zh_text = f.read()
        except Exception:
            zh_text = ""
    blocks_zh = _md_blocks(zh_text) if zh_text.strip() else []
    # 对齐（段数一致时 1:1；不一致按标题锚点/比例配平）
    if blocks_zh and len(blocks_zh) == len(blocks_en):
        pairs = [[i, i] for i in range(len(blocks_en))]
    elif blocks_zh:
        pairs = _align_blocks_backend(blocks_en, blocks_zh)
    else:
        pairs = [[i, None] for i in range(len(blocks_en))]
    # 段落 → 页码（批Q：优先用句级锚点的行级页号，命中更准）
    pages_text = _pdf_pages_text(pdf_path)
    page_of = _map_blocks_to_pages(blocks_en, pages_text) if pages_text else [-1] * len(blocks_en)
    anchors = []
    try:
        anchors = build_anchor_map(pdf_path, md_path, stem=stem, progress_cb=progress_cb)
    except Exception as e:
        logger.warning(f"anchor map failed: {e}")
    if anchors and len(anchors) == len(blocks_en):
        for i, a in enumerate(anchors):
            if (a or {}).get("page", -1) >= 0:
                page_of[i] = a["page"]
    # 批Q：中英句级配对（点译文任意一句 → 精确框原文那一句）
    _zh_heads = _zh_running_keys(zh_text)
    _anch_idx = None
    try:
        _lay = _pdf_line_layer(pdf_path)
        _anch_idx = _anch_index(_lay["lines"], _lay["page_wh"])
        _anch_idx["head_pats"] = _anch_running_patterns(_lay)
    except Exception as e:
        logger.warning(f"anchor index failed: {e}")
    # 模块边界
    toc = _pdf_toc(pdf_path)
    toc_source = "toc"
    if not toc:
        toc = _pdf_heading_pages(pdf_path)
        toc_source = "headings" if toc else "none"
    if not toc:
        toc = [{"title": hit.get("title") or "全文", "page": 0, "level": 1}]
    # 批O4：level-1 条目 = 模块；level>1 子节归入上一模块（subs 带页码可点击定位）
    _lvs = sorted({t.get("level", 1) for t in toc})
    _top_lv = 1 if 1 in _lvs else (_lvs[0] if _lvs else 1)
    modules = []
    for t in toc:
        lv = t.get("level", 1)
        page = max(0, min(t["page"], len(pages_text) - 1 if pages_text else 0))
        if not modules or lv <= _top_lv:
            modules.append({"title": t["title"], "start_page": page,
                            "end_page": page, "paras": [], "subs": []})
        else:
            modules[-1]["subs"].append({"title": t["title"], "page": page})
            modules[-1]["end_page"] = max(modules[-1]["end_page"], page)
    # end_page = 下一模块起始页 - 1（且 ≥ start，防同页条目倒挂）
    for i, m in enumerate(modules):
        if i + 1 < len(modules):
            m["end_page"] = max(m["start_page"], modules[i + 1]["start_page"] - 1)
        else:
            m["end_page"] = max(m["start_page"], (len(pages_text) - 1) if pages_text else m["start_page"])
    # 段落归属模块（按模块页区间）
    for idx, m in enumerate(modules):
        start, end = m["start_page"], m["end_page"]
        for pi, (ei, zi) in enumerate(pairs):
            pg = page_of[ei] if ei is not None else -1
            if pg < 0 or not (start <= pg <= end):
                continue
            en = blocks_en[ei] if ei is not None else ""
            zh = blocks_zh[zi] if zi is not None and zi < len(blocks_zh) else ""
            a = anchors[ei] if (ei is not None and ei < len(anchors)) else {}
            rect = (a or {}).get("rects") or None
            if not rect and en:
                rect = _find_block_rect(pdf_path, pg, en)
            m["paras"].append({"page": pg, "en": en, "zh": zh, "rect": rect,
                               "pre": (a or {}).get("pre") or [],
                               "post": (a or {}).get("post") or [],
                               "units": (a or {}).get("units") or [],
                               "zs": _zh_sentence_payload(en, zh, a, _anch_idx, _zh_heads)})
        m["id"] = idx
    out = json.dumps({
        "ok": True, "file": hit.get("file"), "stem": stem,
        "title": hit.get("title") or "", "pages": len(pages_text),
        "has_zh": bool(blocks_zh), "toc_source": toc_source,
        "_schema": _BILINGUAL_SCHEMA,
        "modules": modules,
        "note": "左侧为原版 PDF（含图），右侧为按模块组织的译文；"
                "点译文任意一句即框出对应原文（句级对齐），点原文页可回定位译文。",
    }, ensure_ascii=False)
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(out)
    except Exception as e:
        logger.warning(f"bilingual cache write failed: {e}")
    return out


def _align_blocks_backend(L: list, R: list) -> list:
    """与前端 litAlignBlocks 同规则的段落配平（后端版，供 build_bilingual 用）。"""
    if len(L) == len(R):
        return [[i, i] for i in range(len(L))]

    def _heads(arr):
        return [i for i, b in enumerate(arr) if re.match(r"^#{1,6}\s", b)]

    hL, hR = _heads(L), _heads(R)
    if hL and len(hL) == len(hR):
        pairs, li, ri = [], 0, 0
        for k in range(len(hL)):
            for j in range(max(hL[k] - li, hR[k] - ri)):
                pairs.append([li + j if li + j < hL[k] else None,
                              ri + j if ri + j < hR[k] else None])
            pairs.append([hL[k], hR[k]])
            li, ri = hL[k] + 1, hR[k] + 1
        while li < len(L) or ri < len(R):
            pairs.append([li if li < len(L) else None, ri if ri < len(R) else None])
            li += 1
            ri += 1
        return pairs
    n = max(len(L), len(R))
    out = []
    for j in range(n):
        lj = j if len(L) == n else round(j * (len(L) - 1) / max(n - 1, 1))
        rj = j if len(R) == n else round(j * (len(R) - 1) / max(n - 1, 1))
        out.append([lj, rj])
    return out


# ── 会话绑定（12 小时自动换绑，批J 2026-08-16）──
_BIND_TTL_SECONDS = 12 * 3600
def get_binding() -> dict:
    """当前文献库会话绑定：{session_id, bound_at, expired, remaining_hours}。"""
    p = os.path.join(_library_dir(), ".binding.json")
    try:
        with open(p, encoding="utf-8") as f:
            b = json.load(f)
    except Exception:
        return {"session_id": "", "expired": True, "remaining_hours": 0}
    bound_at = b.get("bound_at_ts", 0)
    remaining = max(0.0, _BIND_TTL_SECONDS - (time.time() - bound_at))
    expired = remaining <= 0
    return {"session_id": b.get("session_id", ""), "bound_at": b.get("bound_at", ""),
            "expired": expired, "remaining_hours": round(remaining / 3600, 1)}


def bind_session(session_id: str, force: bool = False) -> dict:
    """绑定文献库到会话。未绑定/已过期(12h) 自动绑定新会话；force 强制换绑。"""
    cur = get_binding()
    sid = (session_id or "").strip()
    if not sid:
        return {"ok": False, "error": "session_id required", **cur}
    if not force and cur.get("session_id") and not cur.get("expired"):
        return {"ok": True, "auto": False, **cur}
    b = {"session_id": sid, "bound_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "bound_at_ts": time.time()}
    os.makedirs(_library_dir(), exist_ok=True)
    with open(os.path.join(_library_dir(), ".binding.json"), "w", encoding="utf-8") as f:
        json.dump(b, f, ensure_ascii=False, indent=2)
    return {"ok": True, "auto": not force, **get_binding()}


SCHEMA = {
    "name": "literature_import",
    "description": (
        "导入用户已有的本地 PDF 文献（文件或目录路径）到全局文献库 hermes_home/papers/。"
        "自动提取并标识：期刊(journal)、文章名(title)、作者、年份、DOI、下载日期；"
        "自动注册进引用库（BibTeX/RIS）。重复文件自动跳过。"
        "用户说'这是我下载的文献/论文 PDF'时用它导入，不要用 download_pdf 重复下载。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "本地 PDF 文件或目录的绝对路径列表（目录会递归收集 .pdf）"
            }
        },
        "required": ["paths"]
    }
}


EXTRACT_SCHEMA = {
    "name": "kb_extract_from_paper",
    "description": (
        "把文献库里的一篇文献（用户导入或 download_pdf 下载的）做结构化知识提取并写入知识库："
        "生物学知识（结论/基因marker/细胞类型/通路/类器官培养条件/化合物化学信息）→ 01_生物学知识；"
        "生信知识（测序方法/分析流程/软件包含版本/关键参数/QC阈值/参考基因组/数据库）→ 03_测序方法；"
        "质控阈值 → 02_质控参数。写入 knowledge_base 五级目录（物种/组织/方向/类别/assay），"
        "evidence 带 DOI 溯源，另存人读版 hermes_home/papers/knowledge/<名>.md。"
        "用户说'把这篇文献的参数/生物学知识/生信知识提炼进知识库/入库'时使用。"
        "【重要】用户要'总结文章思路/论文解读/全文提炼/9项摘要'时不要用本工具——那走 summarize_paper。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_or_title": {
                "type": "string",
                "description": "文献文件名或文章名（支持子串匹配，如 paper_demo.pdf 或 aging muscle atlas）"
            }
        },
        "required": ["file_or_title"]
    }
}


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="literature_import",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: import_pdfs(args.get("paths") or []),
            emoji="📥",
            max_result_size_chars=30_000,
        )
        registry.register(
            name="kb_extract_from_paper",
            toolset="memomics",
            schema=EXTRACT_SCHEMA,
            handler=lambda args, **kw: kb_extract_from_paper(args.get("file_or_title", "")),
            emoji="🧬",
            max_result_size_chars=20_000,
        )
        registry.register(
            name="summarize_paper",
            toolset="memomics",
            schema={
                "name": "summarize_paper",
                "description": (
                    "文献全文思路提炼（给人看的方向）：对文献库里一篇文章提取 9 项结构化摘要"
                    "（思路、背景、物种、组织、问题、怎么解决、方法、结论、怎么验证），写入 "
                    "hermes_home/papers/summaries/ 并标记已提炼。"
                    "用户说'总结这篇文章/这篇文章的思路/讲了什么/论文解读/全文提炼/9项摘要'时使用。"
                    "【重要】提炼生信参数/知识库条目（给 AI 调用）走 kb_extract_from_paper，"
                    "两者分工不同，不要混用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_or_title": {"type": "string",
                                          "description": "文献文件名或文章名（子串匹配）"}
                    },
                    "required": ["file_or_title"]
                }
            },
            handler=lambda args, **kw: summarize_paper(args.get("file_or_title", "")),
            emoji="📝",
            max_result_size_chars=20_000,
        )
    except Exception as e:
        logger.warning(f"literature library register failed: {e}")


_register()
