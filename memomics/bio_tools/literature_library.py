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
_CROSSREF_UA = {"User-Agent": "MemOmics-Library/1.0 (mailto:research@localhost)"}


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
    return {"title": (m.get("title") or [""])[0], "journal": journal,
            "authors": authors, "year": year, "doi": doi}


def _extract_metadata(pdf_path: str, text: str, original_path: str) -> dict:
    doi = ""
    m = DOI_RE.search(text or "")
    if m:
        doi = m.group(0).rstrip(".,;")
    meta = {"title": "", "journal": "", "authors": [], "year": "", "doi": doi,
            "entry_type": "article", "url": f"https://doi.org/{doi}" if doi else ""}
    # 1. DOI → Crossref 反查
    if doi:
        try:
            cr = _crossref_by_doi(doi)
            for k in ("title", "journal", "authors", "year"):
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
                if _ratio >= 0.45:
                    it = best
                    meta["title"] = (it.get("title") or [""])[0] or meta["title"]
                    ct = it.get("container-title") or []
                    meta["journal"] = ct[0] if ct else ""
                    meta["authors"] = [f"{a.get('given','')} {a.get('family','')}".strip()
                                       for a in it.get("author", [])][:20]
                    v = it.get("published", {}).get("date-parts", [[None]])[0]
                    if v and v[0]:
                        meta["year"] = str(v[0])
                    if not meta.get("doi") and it.get("DOI"):
                        meta["doi"] = it["DOI"]
                        meta["url"] = f"https://doi.org/{it['DOI']}"
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


def import_pdfs(paths, progress_cb=None) -> str:
    """导入本地 PDF 到全局文献库（去重 + 元数据标识 + 分类标签 + 引用库注册）。

    progress_cb(phase, done, total, detail): 进度回调——
    phase ∈ collect/file/classify/done；detail=当前文件名或说明。
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
                "downloaded_at": datetime.fromtimestamp(os.path.getmtime(src)).strftime("%Y-%m-%d %H:%M:%S"),
                "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
    """列出全部文献：用户导入 + agent 下载。"""
    out = []
    for label, idx_path in (("user_import", os.path.join(_library_dir(), ".pdf_index.json")),
                            ("agent_download", _agent_papers_index())):
        if not idx_path or not os.path.isfile(idx_path):
            continue
        for e in _load_index(idx_path):
            _s = e.get("summary") or {}
            out.append({
                "source": label,
                "file": e.get("file"), "title": e.get("title") or "",
                "journal": e.get("journal") or "", "year": e.get("year") or "",
                "doi": e.get("doi") or "",
                "downloaded_at": e.get("downloaded_at") or e.get("imported_at") or "",
                "path": e.get("path") or "",
                "tags": e.get("tags") or {},
                "summary_done": bool(e.get("summary_done")),
                "kb_done": bool(e.get("kb_done")),
                "summary_idea": str(_s.get("idea") or "")[:160],
            })
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


def kb_extract_from_paper(file_or_title: str, progress_cb=None) -> str:
    """把文献库中的一篇文献提炼成知识库 YAML 条目（批G 2026-08-16）。

    流程: 定位 PDF → 全文提取(≤30K字符) → LLM 提炼 1-3 个 KB 条目 →
          save_knowledge 五级目录落库（带 DOI/原文溯源 evidence）。
    progress_cb(phase, done, total, detail): 可选进度回调。
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
        return json.dumps({"ok": False, "error": (
            f"文献库中未找到 '{file_or_title}'。可先用 literature_import 导入 PDF，"
            "或用 save_reference list / 文献库面板查看已入库文献。")},
            ensure_ascii=False)
    pdf_path = hit.get("path", "")
    if not pdf_path or not os.path.isfile(pdf_path):
        return json.dumps({"ok": False, "error": f"PDF 文件不存在: {pdf_path}"}, ensure_ascii=False)
    _cb("read", 0, 1, f"读取全文: {hit.get('title') or hit.get('file')}")
    text = _pdf_text(pdf_path, pages=200)[:30000]
    _ocr_used = False
    if not text.strip():
        # 扫描版 PDF：RapidOCR 逐页兜底
        _cb("read", 0, 1, f"扫描版无文字层，OCR 识别中: {hit.get('file')}")
        text = _pdf_ocr_text(pdf_path)
        _ocr_used = bool(text.strip())
    if not text.strip():
        return json.dumps({"ok": False, "error": "PDF 无文字层且 OCR 不可用（可尝试装 rapidocr_onnxruntime）"},
                          ensure_ascii=False)
    tags = hit.get("tags") or _classify_single(hit.get("title") or "")
    from memomics.bio_tools.debate_analysis import _call_llm_sync, _default_role_llm
    prompt = (
        "你是生信知识库提炼员。从文献中提炼 1-3 条可直接复用的知识库条目（参数/方法/生物学结论），"
        "输出 JSON 数组（不要其他文字）：\n"
        "[{\"name\":\"英文小写短名_下划线\",\"content\":\"条目内容(≤300字,含关键参数/数值)\","
        "\"kb_category\":\"01_生物学知识|02_质控参数|03_测序方法\",\"assay_type\":\"RNA|ATAC|spatial|bulk\","
        "\"species\":\"human/mouse/...\",\"tissue\":\"英文小写下划线\",\"direction\":\"aging/exercise/...\"}]\n"
        f"文献: {hit.get('title')} | 期刊 {hit.get('journal')} | DOI {hit.get('doi')}\n"
        f"预分类: {json.dumps(tags, ensure_ascii=False)}\n"
        + ("注意: 以下正文来自 OCR 识别，可能有识别噪声，忽略乱码部分。\n" if _ocr_used else "")
        + "优先提炼: ① 该文献特有的参数(阈值/基因集/统计方法) ② 物种组织方向特异结论 ③ 可被"
        "search_knowledge 检索复用的方法要点。文献正文:\n" + text
    )
    _cb("extract", 0, 1, f"LLM 提炼: {hit.get('title') or hit.get('file')}")
    try:
        cfg = _default_role_llm("", "", "deepseek-v4-flash", _load_provider_keys())
        r = _call_llm_sync(prompt, "kb_extract", cfg["api_key"], cfg["base_url"],
                           cfg["model"], temperature=0.3, max_tokens=2500)
        txt = r.get("content", "")
        items = _parse_json_array(txt)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"LLM 提炼失败: {str(e)[:200]}"}, ensure_ascii=False)
    if not items:
        return json.dumps({"ok": False, "error": "未能提炼出条目"}, ensure_ascii=False)
    from memomics.bio_tools.save_knowledge import save_knowledge
    written, rejected = [], []
    for _i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        _cb("write", _i + 1, len(items), f"写入知识库: {it.get('name')}")
        sp = (it.get("species") or (tags.get("species") or ["unknown"])[0]).lower()
        ti = (it.get("tissue") or (tags.get("tissue") or [""])[0]).lower().replace(" ", "_")
        dr = (it.get("direction") or (tags.get("direction") or [""])[0]).lower().replace(" ", "_")
        # 清洗多值字段（如 "human;mouse" / "skeletal muscle, liver"）：取第一个合法值
        def _first_seg(v: str) -> str:
            for seg in re.split(r"[;,，、/；]", v):
                seg = seg.strip().replace(" ", "_")
                if re.fullmatch(r"[\w\u4e00-\u9fff_-]{1,64}", seg):
                    return seg
            return ""
        sp = _first_seg(sp)
        ti = _first_seg(ti)
        dr = _first_seg(dr)
        if sp == "unknown" or not ti or not dr:
            rejected.append({"name": it.get("name"), "error": "物种/组织/方向缺失，无法定位五级目录"})
            continue
        r = json.loads(save_knowledge(
            name=str(it.get("name") or "")[:64],
            content=str(it.get("content") or ""),
            source="literature",
            evidence=f"DOI {hit.get('doi')} | {hit.get('title')} | {hit.get('path')}",
            verified="partially_verified",
            species=sp, tissue=ti, direction=dr,
            kb_category=str(it.get("kb_category") or "01_生物学知识"),
            assay_type=str(it.get("assay_type") or tags.get("assay") or "RNA").upper(),
        ))
        (written if r.get("status") == "success" else rejected).append(
            {k: r.get(k) for k in ("status", "name", "path", "error") if r.get(k)})
    _cb("done", 1, 1, f"提炼完成: 写入 {len(written)} 条")
    # 标记 kb_done（方向2：给 AI 调用的知识库条目）
    try:
        _idx_file = os.path.join(_library_dir(), ".pdf_index.json")
        _idx = _load_index(_idx_file)
        for _e in _idx:
            if _e.get("file") == hit.get("file") and written:
                _e["kb_done"] = True
                _e["kb_written_count"] = len(written)
        _save_index(_idx_file, _idx)
    except Exception as e:
        logger.warning(f"kb_done mark failed: {e}")
    return json.dumps({
        "ok": bool(written), "paper": hit.get("title"), "doi": hit.get("doi"),
        "written": written, "rejected": rejected,
        "note": "写入 knowledge_base 五级目录（物种/组织/方向/类别/assay），带 DOI 溯源。"},
        ensure_ascii=False, indent=2)


def extract_all_papers(progress_cb=None) -> str:
    """一键入库（批I 2026-08-16；批K 2026-08-16 只处理未入库）：
    对文献库中未入库（kb_done≠true）的文献逐一提炼进知识库。

    progress_cb(phase, done, total, detail)。
    """
    try:
        lib = json.loads(list_library()).get("library", [])
    except Exception:
        lib = []
    if not lib:
        return json.dumps({"ok": False, "error": "文献库为空——先导入 PDF 再一键提炼"},
                          ensure_ascii=False)
    pending = [e for e in lib if not e.get("kb_done")]
    if not pending:
        return json.dumps({"ok": True, "total": len(lib), "pending": 0,
                           "results": [], "note": "全部文献都已入库"},
                          ensure_ascii=False)
    _cb = progress_cb or (lambda *a, **k: None)
    n = len(pending)
    results = []
    for i, e in enumerate(pending):
        name = e.get("file") or e.get("title") or ""
        _cb("paper", i, n, f"[{i + 1}/{n}] 提炼: {e.get('title') or name}")
        try:
            r = json.loads(kb_extract_from_paper(name, progress_cb=(
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
    _cb("done", n, n, f"全部完成: {ok_n}/{n} 篇成功")
    return json.dumps({
        "ok": ok_n > 0, "total": len(lib), "pending": n, "succeeded": ok_n,
        "written_total": sum(r["written"] for r in results),
        "results": results,
        "note": "只处理未入库文献，逐篇提炼进 knowledge_base 五级目录，每篇 1-3 条（参数/方法/结论），带 DOI 溯源。"},
        ensure_ascii=False, indent=2)


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


def _load_summary_file(stem: str) -> str:
    p = os.path.join(_summaries_dir(), f"{stem}.md")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def get_summary(file_or_title: str) -> str:
    """查看某篇文献的全文思路摘要（方向1）。"""
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
    md = _load_summary_file(os.path.splitext(hit.get("file") or "")[0])
    if not md and hit.get("summary"):
        md = hit["summary"].get("markdown", "")
    return json.dumps({"ok": True, "file": hit.get("file"), "title": hit.get("title"),
                       "summary": hit.get("summary") or {}, "markdown": md,
                       "summary_done": bool(hit.get("summary_done")),
                       "kb_done": bool(hit.get("kb_done"))}, ensure_ascii=False)


def summarize_paper(file_or_title: str, progress_cb=None) -> str:
    """全文思路提炼（方向1，给人看）：9 项结构化摘要 + summaries/<名>.md 落盘。

    独立调用 LLM API（deepseek-v4-flash），模板与 literature-full-summary skill 一致。
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
    pdf_path = hit.get("path", "")
    if not pdf_path or not os.path.isfile(pdf_path):
        return json.dumps({"ok": False, "error": f"PDF 文件不存在: {pdf_path}"}, ensure_ascii=False)
    _cb("read", 0, 1, f"读取全文: {hit.get('title') or hit.get('file')}")
    text = _pdf_text(pdf_path, pages=200)[:30000]
    _ocr_used = False
    if not text.strip():
        _cb("read", 0, 1, f"扫描版无文字层，OCR 识别中: {hit.get('file')}")
        text = _pdf_ocr_text(pdf_path)
        _ocr_used = bool(text.strip())
    if not text.strip():
        return json.dumps({"ok": False, "error": "PDF 无文字层且 OCR 不可用"}, ensure_ascii=False)
    _cb("summarize", 0, 1, f"LLM 全文提炼(9项): {hit.get('title') or hit.get('file')}")
    from memomics.bio_tools.debate_analysis import _call_llm_sync, _default_role_llm
    prompt = (
        "你是生物医学文献解读员。按 literature-full-summary skill 的九问模板，"
        "对下面这篇文献逐项提炼，输出 JSON 对象（不要其他文字）：\n"
        '{"idea":"作者核心想法/切入点","background":"领域现状与空白","species":"human/mouse/...",'
        '"tissue":"skeletal_muscle/liver/...","problem":"要回答的具体科学问题",'
        '"solution":"如何设计实验/分析来回答","methods":"关键技术/算法/统计方法(含阈值)",'
        '"conclusion":"主要发现与结论","validation":"如何验证(独立队列/实验/交叉方法)"}\n'
        "规则：每项 2-6 句中文，忠实原文；缺项写'未提及'，禁止编造；物种/组织用英文小写。\n"
        f"文献标题: {hit.get('title')} | 期刊: {hit.get('journal')} | DOI: {hit.get('doi')}\n"
        + ("注意: 正文来自 OCR，忽略乱码。\n" if _ocr_used else "")
        + "正文:\n" + text
    )
    try:
        cfg = _default_role_llm("", "", "deepseek-v4-flash", _load_provider_keys())
        r = _call_llm_sync(prompt, "lit_summary", cfg["api_key"], cfg["base_url"],
                           cfg["model"], temperature=0.3, max_tokens=2500)
        txt = r.get("content", "")
        summary = _parse_json_object(txt)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"LLM 提炼失败: {str(e)[:200]}"}, ensure_ascii=False)
    if not summary or not any(summary.get(k) for k in _SUMMARY_FIELDS):
        return json.dumps({"ok": False, "error": "未能提炼出摘要"}, ensure_ascii=False)
    # 落盘 summaries/<stem>.md + 索引标记
    _cb("write", 1, 1, "写入摘要文件 + 标记已提炼")
    stem = os.path.splitext(hit.get("file") or "")[0]
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
        "把文献库里的一篇文献（用户导入或 download_pdf 下载的）提炼成知识库 YAML 条目。"
        "自动：定位 PDF → 全文提取 → LLM 提炼 1-3 条（参数/方法/结论）→ 写入 "
        "knowledge_base 五级目录（物种/组织/方向/类别/assay），evidence 带 DOI 溯源。"
        "用户说'把这篇文献整理进知识库/提炼这篇论文'时使用。"
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
                    "（思路/背景/物种/组织/问题/怎么解决/方法/结论/怎么验证），写入 "
                    "hermes_home/papers/summaries/ 并标记已提炼。"
                    "用户说'总结这篇文章/这篇文章的思路是什么/全文提炼'时使用。"
                    "注意：给 AI 调用的参数/知识条目走 kb_extract_from_paper，两者分工不同。"
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
