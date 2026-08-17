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
import hashlib
import json
import logging
import os
import re
import time
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


def _load_index(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_index(path: str, entries: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


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


def _llm_content(prompt: str, label: str, temperature: float = 0.3,
                 max_tokens: int = 6000, retry_prefix: str = "") -> str:
    """LLM 调用 + 推理占满自动重试（批N 2026-08-16）。

    deepseek-v4-flash 是推理模型，偶尔把输出额度全花在 reasoning 上、
    content 为空（_call_llm_sync 回退返回 reasoning 草稿）→ 检测到后
    重试一次并要求直接输出最终结果。
    """
    from memomics.bio_tools.debate_analysis import _call_llm_sync, _default_role_llm
    cfg = _default_role_llm("", "", "deepseek-v4-flash", _load_provider_keys())
    r = _call_llm_sync(prompt, label, cfg["api_key"], cfg["base_url"], cfg["model"],
                       temperature=temperature, max_tokens=max_tokens)
    if r.get("used_reasoning_fallback"):
        logger.warning(f"{label} reasoning 占满 → 重试直接输出")
        r2 = _call_llm_sync((retry_prefix or "【重要：不要输出任何思考过程，立即输出最终结果】\n") + prompt,
                            label + "_retry", cfg["api_key"], cfg["base_url"], cfg["model"],
                            temperature=0.2, max_tokens=max_tokens)
        return r2.get("content", "") or r.get("content", "")
    return r.get("content", "")


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
    """分节合并成 ≤max_chars 的块（块内保留节标题）。"""
    chunks, cur = [], ""
    for title, content in sections:
        piece = f"## {title}\n{content}\n\n"
        if len(cur) + len(piece) > max_chars and cur:
            chunks.append(cur)
            cur = piece
        else:
            cur += piece
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


def import_pdfs(paths, progress_cb=None, imported_by: str = "") -> str:
    """导入本地 PDF 到全局文献库（去重 + 元数据标识 + 分类标签 + 引用库注册）。

    progress_cb(phase, done, total, detail): 进度回调——
    phase ∈ collect/file/classify/done；detail=当前文件名或说明。
    imported_by: 导入人标识（多用户场景记录在条目上）。
    """
    files = _collect_pdfs(paths)
    if not files:
        return json.dumps({"ok": False, "error": "未找到 PDF 文件（支持 .pdf 文件或目录路径）"},
                          ensure_ascii=False)
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
    for src in files:
        _cb("file", _n_done, len(files), os.path.basename(src))
        try:
            # 校验：空文件 / 非 PDF 直接报错跳过
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
            sha = _sha256_of(src)
            size = _sz
            if sha and sha in by_sha:
                skipped.append({"file": os.path.basename(src), "reason": "重复(sha256)"})
                continue
            if (os.path.basename(src), size) in by_name:
                skipped.append({"file": os.path.basename(src), "reason": "重复(同名同大小)"})
                continue
            # 复制进库
            dest_name = "".join(c if (c.isalnum() or c in "._-") else "_" for c in os.path.basename(src))
            dest = os.path.join(lib_dir, dest_name)
            n = 1
            while os.path.exists(dest):
                stem, ext = os.path.splitext(dest_name)
                dest = os.path.join(lib_dir, f"{stem}_{n}{ext}")
                n += 1
            with open(src, "rb") as fin, open(dest, "wb") as fout:
                fout.write(fin.read())
            # 元数据提取（PDF 文本 + Crossref）
            text = _pdf_text(dest, pages=2)
            meta = _extract_metadata(dest, text, src)
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
    if index and any(not e.get("tags") for e in index):
        _new = [e for e in index if not e.get("tags")]
        _cb("classify", _n_done, len(files), f"LLM 分类 {len(_new)} 篇文献…")
        try:
            _tags = _classify_papers(_new)
            for e in _new:
                if e.get("file") in _tags:
                    e["tags"] = _tags[e["file"]]
        except Exception as e:
            logger.warning(f"classification failed: {e}")
        _save_index(index_file, index)
    for it in imported:
        for e in index:
            if e.get("file") == it.get("file") and e.get("tags"):
                it["tags"] = e["tags"]
    _cb("done", _n_done, len(files), f"完成：导入 {len(imported)} 篇")
    return json.dumps({
        "ok": True, "imported": len(imported), "skipped": len(skipped), "errors": errors,
        "entries": imported, "library_dir": lib_dir.replace("\\", "/"),
        "bibtex_file": os.path.join(os.path.dirname(_library_dir()) or "", "references.bib").replace("\\", "/"),
        "ris_file": os.path.join(os.path.dirname(_library_dir()) or "", "references.ris").replace("\\", "/"),
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
        from memomics.bio_tools.debate_analysis import _call_llm_sync, _default_role_llm
        cfg = _default_role_llm("", "", "deepseek-v4-flash", _load_provider_keys())
        r = _call_llm_sync(prompt, "lit_classify", cfg["api_key"], cfg["base_url"],
                           cfg["model"], temperature=0.2, max_tokens=3000)
        txt = r.get("content", "")
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
                       retry_prefix="【不要思考，立即按 ###N### 编号输出译文】\n")
    res = _parse_numbered_output(out, len(blocks))
    missing = [i for i, t in enumerate(res) if not t]
    if not any(res):
        # 全空（可能整段输出格式不符/推理占满）→ 整体重试
        out2 = _llm_content(
            "【重要：不要输出任何思考过程，立即按 ###N### 编号逐段输出译文，"
            "每段必须以 ###数字### 单独一行开头】\n" + prompt,
            "lit_trans_blocks_retry", temperature=0.1, max_tokens=12000,
            retry_prefix="【直接输出译文，不要思考】\n")
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
            retry_prefix="【直接输出译文，不要思考】\n")
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

    batches = _batch_blocks(blocks)
    # 批O2：2 路并发翻译批次（每批编号直译互不依赖；结果按批次偏移回填保证顺序）
    indexed = []
    _off = 0
    for batch in batches:
        indexed.append((_off, batch))
        _off += len(batch)
    # 只翻译还有缺失段的批次（断点续译跳过已完成批次）
    pending = []
    for off, batch in indexed:
        if all(results[off + k] for k in range(len(batch))):
            continue
        pending.append((off, batch))
    if pending:
        _cb("translate", 0, len(pending), f"段落级编号直译 {len(pending)}/{len(indexed)} 批（并发2）")
    try:
        from concurrent.futures import ThreadPoolExecutor
        _mw = max(1, min(2, int(os.environ.get("MEMOMICS_LIT_TRANS_WORKERS", "2"))))

        def _one(off_batch):
            off, batch = off_batch
            return off, _translate_block_batch(batch)

        _n_done = 0
        with ThreadPoolExecutor(max_workers=_mw) as _ex:
            for off, part in _ex.map(_one, pending):
                for k, t in enumerate(part):
                    if t:
                        results[off + k] = t
                _n_done += 1
                _flush_part()  # 每完成一批落盘一次（服务重启可续）
                _cb("translate", _n_done, len(pending), f"段落级翻译 {_n_done}/{len(pending)} 批")
    except Exception as e:
        logger.warning(f"parallel translate failed, fallback serial: {e}")
        _n_done = 0
        for off, batch in pending:
            part = _translate_block_batch(batch)
            for k, t in enumerate(part):
                if t:
                    results[off + k] = t
            _n_done += 1
            _flush_part()
            _cb("translate", _n_done, len(pending), f"段落级翻译第 {_n_done}/{len(pending)} 批（{len(batch)} 段）")
    # 缺段单段兜底直译（保证 1:1 完整）
    for i, b in enumerate(blocks):
        if not results[i]:
            _cb("translate", i, len(blocks), f"补译第 {i + 1}/{len(blocks)} 段")
            results[i] = _llm_content(
                "把下面这段英文文献翻译成学术严谨的中文（保持 Markdown 标题格式），"
                "输出为**单个段落，不要空行**，只输出译文：\n" + b,
                f"lit_trans_fix_{i}", temperature=0.2, max_tokens=6000,
                retry_prefix="【不要思考，立即输出译文】\n").strip()
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
                retry_prefix="【重要：不要输出任何思考过程，立即输出最终 JSON 对象，第一个字符必须是 { 】\n")
            summary = _parse_json_object(txt)
        else:
            # 长文献：分节分块 → 每块提炼要点 → 合并成 9 项
            _cb("summarize", 0, 1, f"长文献分块解读: {len(_split_md_sections(md_text))} 节")
            chunks = _chunk_sections(_split_md_sections(md_text))
            bullets = {k: [] for k in _SUMMARY_FIELDS}
            for ci, chunk in enumerate(chunks):
                _cb("summarize", ci, len(chunks), f"解读第 {ci + 1}/{len(chunks)} 块")
                txt = _llm_content(
                    "你是文献解读助手。对下面的文献片段，按 9 个字段各提炼 1-2 句要点，"
                    '输出 JSON：{"idea":[],"background":[],"species":[],"tissue":[],'
                    '"problem":[],"solution":[],"methods":[],"conclusion":[],"validation":[]}'
                    "（值都是字符串数组；该片段没涉及的字段给空数组；不要其他文字）\n" + chunk,
                    f"lit_chunk_{ci}", temperature=0.2, max_tokens=3000,
                    retry_prefix="【不要思考，立即输出 JSON 数组，第一个字符必须是 { 】\n")
                part = _parse_json_object(txt)
                for k in _SUMMARY_FIELDS:
                    for v in (part.get(k) or []):
                        if isinstance(v, str) and v.strip():
                            bullets[k].append(v.strip())
            merged = "\n".join(f"{k}: " + "；".join(bullets[k][:12]) for k in _SUMMARY_FIELDS)
            txt = _llm_content(
                base + "以下是从全文各节提炼出的要点（按字段聚合），请据此写出最终的 9 项摘要，"
                "输出 JSON 对象（不要其他文字）:\n" + merged[:9000],
                "lit_summary_merge", temperature=0.3, max_tokens=6000,
                retry_prefix="【不要思考，立即输出最终 JSON 对象，第一个字符必须是 { 】\n")
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
                retry_prefix="【重要：不要输出任何思考过程，立即输出最终 JSON 对象，第一个字符必须是 { 】\n")
            knowledge = _parse_json_object(txt)
        else:
            _cb("extract", 0, 1, f"长文献分块提取: {len(_split_md_sections(md_text))} 节")
            chunks = _chunk_sections(_split_md_sections(md_text))
            bullets = {"biology": [], "bioinfo": []}
            for ci, chunk in enumerate(chunks):
                _cb("extract", ci, len(chunks), f"提取第 {ci + 1}/{len(chunks)} 块")
                txt = _llm_content(
                    "你是文献知识提炼助手。对下面的文献片段，按给出的 schema 提炼**结构化知识**，"
                    "输出 JSON 对象（不要其他文字）：\n" + _KNOWLEDGE_SCHEMA_HINT + "\n"
                    "（该片段没涉及的字段给空数组/空串）\n" + chunk,
                    f"lit_know_chunk_{ci}", temperature=0.2, max_tokens=4000,
                    retry_prefix="【不要思考，立即输出 JSON 对象，第一个字符必须是 { 】\n")
                part = _parse_json_object(txt)
                for sec in ("biology", "bioinfo"):
                    bullets[sec].append(part.get(sec) or {})
            merged = json.dumps(bullets, ensure_ascii=False)
            txt = _llm_content(
                base + "以下是从全文各节提取出的知识碎片（按 biology/bioinfo 聚合，数组可能有重复/冲突），"
                "请合并去重后输出最终的完整 JSON 对象（不要其他文字）:\n" + merged[:12000],
                "lit_knowledge_merge", temperature=0.3, max_tokens=6000,
                retry_prefix="【不要思考，立即输出最终 JSON 对象，第一个字符必须是 { 】\n")
            knowledge = _parse_json_object(txt)
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


def _bilingual_cache_path(stem: str) -> str:
    return os.path.join(_translations_dir(), f"{stem}.bilingual.json")


_BILINGUAL_SCHEMA = 2  # 模块结构版本（变动时自动重建缓存）


def build_bilingual(file_or_title: str, rebuild: bool = False) -> str:
    """构建双语对照文档（批O4 2026-08-16）。

    结构：
      {ok, file, stem, title, pages, has_zh,
       toc_source: 'toc'|'headings'|'none',
       modules: [{id, title, start_page, end_page, paras: [
                  {page, en, zh, rect:[x0,y0,x1,y1]|null}]}]}
    模块边界优先取 PDF 书签（get_toc），无书签时按页眉字号检测，都无 → 单模块"全文"。
    段落→页码靠逐页文本匹配；段落→矩形靠 search_for（点译文定位原文高亮）。
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
    # 段落 → 页码
    pages_text = _pdf_pages_text(pdf_path)
    page_of = _map_blocks_to_pages(blocks_en, pages_text) if pages_text else [-1] * len(blocks_en)
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
            rect = _find_block_rect(pdf_path, pg, en) if en else None
            m["paras"].append({"page": pg, "en": en, "zh": zh, "rect": rect})
        m["id"] = idx
    out = json.dumps({
        "ok": True, "file": hit.get("file"), "stem": stem,
        "title": hit.get("title") or "", "pages": len(pages_text),
        "has_zh": bool(blocks_zh), "toc_source": toc_source,
        "_schema": _BILINGUAL_SCHEMA,
        "modules": modules,
        "note": "左侧为原版 PDF（含图），右侧为按模块组织的译文；点模块/段落自动定位原文页与高亮区域。",
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
