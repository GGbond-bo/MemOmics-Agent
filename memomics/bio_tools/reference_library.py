# -*- coding: utf-8 -*-
"""save_reference — 文献引用库工具（2026-08-15，审计整改批 C）。

科研闭环缺口 #1：有检索/下载/解读，但没有引文管理。
本工具把文献元数据（来自 search_papers 结果）沉淀为 BibTeX/RIS 引用库：
- 默认库: results/<sid>/references.bib + .ris（会话级）
- 全局库: hermes_home/references.bib（跨会话，species/tissue 场景复用）
- action: add(元数据) / list / locate(查已收录) / bibtex(转单条)
"""
import hashlib
import json
import logging
import os
import re

logger = logging.getLogger("memomics.reference_library")


_AUTHOR_PARTICLES = {"van", "von", "der", "den", "de", "la", "le", "du", "da",
                     "di", "del", "dell", "della", "delle", "ter", "ten",
                     "el", "al", "o", "af", "op", "san", "st", "sta", "mc"}
_AUTHOR_PREFIXES = {"ur", "bin", "ibn", "mc", "mac", "ben", "abu", "abdul"}
_AUTHOR_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "2nd", "3rd"}


def _author_list(meta: dict) -> list:
    """归一化作者列表：str(分号/逗号分隔) 或 list → ['Given Family', ...]（去掉空项）。"""
    authors = meta.get("authors") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r"[;；]", authors) if a.strip()]
    return [str(a).strip() for a in authors if a and str(a).strip()]


def _split_author(full: str):
    """'Georges E. Janssens' / 'van Weeghel, M.' / 'Janssens, Georges E.' → (family, given)。

    规则：优先 "Family, Given"；否则从尾部收集姓——姓 = 末词 + 其前连续的
    小写虚词（van/der/de...）；"Raza Ur Rahman" 的 Ur 属前缀集，仍并入姓。
    """
    s = (full or "").strip()
    if not s:
        return "", ""
    if "," in s:
        fam, _, giv = s.partition(",")
        return fam.strip(), giv.strip()
    parts = [p for p in s.split() if p]
    if not parts:
        return "", ""
    family = []
    for p in reversed(parts):
        low = p.lower().rstrip(".")
        core = low.replace("'", "").replace("\u2019", "")
        if low in _AUTHOR_SUFFIXES:
            continue
        if not family:
            family.append(p)
            continue
        # 前一个词若为小写虚词/前缀（Dell'/van/der/Ur...）→ 并入姓
        if core in _AUTHOR_PARTICLES or core in _AUTHOR_PREFIXES or p[0].islower() or len(p) == 1:
            family.append(p)
            continue
        break
    family = family[::-1]
    given = " ".join(parts[: len(parts) - len(family)])
    return " ".join(family), given


def _family_initials(full: str, upper: bool = False, periods: bool = False,
                     space_after: bool = True, initials_joined: bool = False) -> str:
    """姓 + 名首字母。upper=True → 全大写（GB/T 7714）；initials_joined=True → 'Janssens GE'（NLM）。"""
    fam, giv = _split_author(full)
    fam = fam or full
    inits = []
    for w in giv.split():
        w = w.strip()
        if not w:
            continue
        # "D'Amico" 的首字母带撇号；"-" 连字符名取两段首字母（Jean-Pierre → JP）
        core = re.sub(r"[^A-Za-z\u00c0-\u024f]", "", w)
        if core:
            inits.extend(ch for ch in re.split(r"[-]", core) if ch)
    letters = [ch[0] for ch in inits if ch]
    if upper:
        fam = fam.upper()
        letters = [c.upper() for c in letters]
    if initials_joined:
        return fam + (" " + "".join(letters) if letters else "")
    if periods:
        letters = [c + "." for c in letters]
    sep = " " if space_after else ""
    return (fam + sep + sep.join(letters)).strip()


def _bibtex_key(meta: dict) -> str:
    """BibTeX key: 第一作者姓 + 年 + 标题首词（无作者时用标题首词）。"""
    authors = _author_list(meta)
    first = authors[0] if authors else ""
    fam, _g = _split_author(first)
    last = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", fam or "")[:20]
    year = re.sub(r"[^0-9]", "", str(meta.get("year") or ""))[:4]
    title = str(meta.get("title") or "")
    tw = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", title)
    _stop = {"a", "an", "the", "of", "on", "in", "and", "for"}
    first_word = next((w[:10] for w in tw if w.lower() not in _stop), tw[0][:10] if tw else "ref")
    if not last:
        last = first_word
    return f"{last.lower()}{year}{first_word}"


def _escape_tex(s: str) -> str:
    return (str(s or "").replace("\\", "\\textbackslash{}").replace("&", "\\&")
            .replace("%", "\\%").replace("_", "\\_").replace("#", "\\#"))


def _to_bibtex(meta: dict) -> str:
    """标准 BibTeX @article：author(and 连接)/title/journal/year/volume/number/pages/doi。"""
    key = _bibtex_key(meta)
    etype = str(meta.get("entry_type") or "article")
    authors = _author_list(meta)
    author_str = " and ".join(authors) if authors else "Unknown"
    fields = [
        f"  author = {{{_escape_tex(author_str)}}}",
        f"  title = {{{_escape_tex(meta.get('title', ''))}}}",
    ]
    if meta.get("journal"):
        fields.append(f"  journal = {{{_escape_tex(meta['journal'])}}}")
    if meta.get("year"):
        fields.append(f"  year = {{{meta['year']}}}")
    if meta.get("volume"):
        fields.append(f"  volume = {{{meta['volume']}}}")
    if meta.get("issue"):
        fields.append(f"  number = {{{meta['issue']}}}")
    if meta.get("pages"):
        fields.append(f"  pages = {{{meta['pages']}}}")
    if meta.get("doi"):
        fields.append(f"  doi = {{{meta['doi']}}}")
    if meta.get("pmid"):
        fields.append(f"  pmid = {{{meta['pmid']}}}")
    if meta.get("url"):
        fields.append(f"  url = {{{meta['url']}}}")
    if meta.get("abstract"):
        fields.append(f"  abstract = {{{_escape_tex(meta['abstract'][:500])}}}")
    return f"@{etype}{{{key},\n" + ",\n".join(fields) + "\n}"


def _to_ris(meta: dict) -> str:
    """标准 RIS：AU 用 'Family, Given'；含 VL/IS/SP/EP/PMID。"""
    etype = str(meta.get("entry_type") or "article")
    ris_type = {"article": "JOUR", "preprint": "ELEC", "book": "BOOK",
                "review": "JOUR", "chapter": "CHAP"}.get(etype, "JOUR")
    lines = [f"TY  - {ris_type}"]
    for a in _author_list(meta):
        fam, giv = _split_author(a)
        lines.append(f"AU  - {fam + ', ' + giv if giv else fam}")
    if meta.get("title"):
        lines.append(f"TI  - {meta['title']}")
    if meta.get("journal"):
        lines.append(f"JO  - {meta['journal']}")
    if meta.get("year"):
        lines.append(f"PY  - {meta['year']}")
    if meta.get("volume"):
        lines.append(f"VL  - {meta['volume']}")
    if meta.get("issue"):
        lines.append(f"IS  - {meta['issue']}")
    pages = str(meta.get("pages") or "")
    if pages:
        seg = re.split(r"[-–—]", pages)
        lines.append(f"SP  - {seg[0].strip()}")
        if len(seg) > 1:
            lines.append(f"EP  - {seg[-1].strip()}")
    if meta.get("doi"):
        lines.append(f"DO  - {meta['doi']}")
    if meta.get("pmid"):
        lines.append(f"AN  - {meta['pmid']}")
    if meta.get("url"):
        lines.append(f"UR  - {meta['url']}")
    if meta.get("abstract"):
        lines.append(f"AB  - {meta['abstract'][:500]}")
    lines.append("ER  - ")
    return "\n".join(lines)


def _citation_author_short(authors: list, max_n: int = 3, upper: bool = False,
                           initials_joined: bool = False) -> str:
    """GB/T / NLM 用作者串：≤max_n 全列，超出取前 max_n + 'et al.'。"""
    out = [_family_initials(a, upper=upper, initials_joined=initials_joined)
           for a in authors]
    if len(out) > max_n:
        out = out[:max_n] + ["et al."]
    return ", ".join(out)


def _citation_apa_authors(authors: list) -> str:
    """APA 7：≤20 全列（末位 & 连接），>20 前 19 + '... ' + 末位。
    姓名格式 'Janssens, G. E.'（姓后逗号 + 首字母缩写）。"""
    def _one(full):
        fam, giv = _split_author(full)
        fam = fam or full
        inits = []
        for w in giv.split():
            core = re.sub(r"[^A-Za-z\u00c0-\u024f]", "", w)
            if core:
                inits.extend(ch for ch in re.split(r"[-]", core) if ch)
        letters = [c[0] + "." for c in inits if c]
        return fam + (", " + " ".join(letters) if letters else "")

    fmt = [_one(a) for a in authors]
    if not fmt:
        return "(佚名)"
    if len(fmt) == 1:
        return fmt[0]
    if len(fmt) <= 20:
        return ", ".join(fmt[:-1]) + ", & " + fmt[-1]
    return ", ".join(fmt[:19]) + ", ... " + fmt[-1]


def _citation_mla_authors(authors: list) -> str:
    """MLA 9：1 人全名；2 人 'A, and B.'；≥3 'A, et al.'（第一作者 Given Family）。"""
    fam, giv = _split_author(authors[0]) if authors else ("", "")
    first = f"{giv} {fam}".strip() or "佚名"
    if len(authors) == 1:
        return first
    if len(authors) == 2:
        fam2, giv2 = _split_author(authors[1])
        return f"{first}, and {giv2} {fam2}".strip()
    return f"{first}, et al."


def _vol_issue(meta: dict) -> str:
    vol = str(meta.get("volume") or "").strip()
    iss = str(meta.get("issue") or "").strip()
    return vol + (f"({iss})" if iss else "") if vol else ""


def format_citation(meta: dict, style: str = "gbt7714-numeric") -> str:
    """按专业格式生成单条引文（2026-08-16 批O·文献引用专业化）。

    style: gbt7714-numeric(顺序编码制) | gbt7714-author-year(著者-出版年制)
           | apa(APA 7) | nlm(NLM/Vancouver) | mla(MLA 9)
    缺卷/期/页码时按各规范省略规则优雅降级，不编造。
    """
    authors = _author_list(meta)
    title = str(meta.get("title") or "").strip() or "(无题名)"
    journal = str(meta.get("journal") or "").strip()
    year = str(meta.get("year") or "").strip()
    vol_issue = _vol_issue(meta)
    pages = str(meta.get("pages") or "").strip().replace("--", "-")
    doi = str(meta.get("doi") or "").strip()
    url = str(meta.get("url") or "").strip() or (f"https://doi.org/{doi}" if doi else "")

    def _page_tail() -> str:
        return (", " + pages) if pages else ""

    def _join_author(au: str, sep: str) -> str:
        """作者串以 '.' 结尾（et al./首字母缩写）时不再重复加句点。"""
        return au + (sep if not au.endswith(".") else sep[1:])

    if style == "gbt7714-numeric":
        au = _citation_author_short(authors, 3, upper=True) or "佚名"
        s = f"[1] {_join_author(au, '. ')}{title}[J]"
        if journal:
            s += f". {journal}"
        tail = []
        if year:
            tail.append(year)
        if vol_issue:
            tail.append(vol_issue)
        if tail:
            s += ", " + ", ".join(tail)
        if pages:
            s += f": {pages}"
        s += "."
        if doi:
            s += f" DOI:{doi}."
        return s

    if style == "gbt7714-author-year":
        au = _citation_author_short(authors, 3, upper=True) or "佚名"
        s = f"{_join_author(au, '. ')}"
        if year:
            s += f"{year}. "
        s += f"{title}[J]"
        if journal:
            s += f". {journal}"
        tail = []
        if vol_issue:
            tail.append(vol_issue)
        if tail:
            s += ", " + ", ".join(tail)
        if pages:
            s += f": {pages}"
        s += "."
        if doi:
            s += f" DOI:{doi}."
        return s

    if style == "apa":
        au = _citation_apa_authors(authors)
        s = f"{au} ({year}). " if year else f"{au}. "
        s += f"{title}."
        if journal:
            s += f" {journal}"
        if vol_issue:
            s += f", {vol_issue}"
        s += _page_tail() + "."
        if url:
            s += f" {url}"
        return s

    if style == "nlm":
        au = _citation_author_short(authors, 6, initials_joined=True) or "佚名"
        s = f"{_join_author(au, '. ')}{title}."
        if journal:
            s += f" {journal}."
        tail = []
        if year:
            tail.append(year)
        if vol_issue:
            tail.append(vol_issue)
        if tail:
            s += " " + ";".join(tail)
        if pages:
            s += f":{pages}"
        s += "."
        if doi:
            s += f" doi:{doi}."
        return s

    if style == "mla":
        au = _citation_mla_authors(authors)
        s = f'{_join_author(au, ". ")}"{title}."'
        if journal:
            s += f" {journal}"
        if vol_issue:
            vol = str(meta.get("volume") or "").strip()
            iss = str(meta.get("issue") or "").strip()
            s += f", vol. {vol}"
            if iss:
                s += f", no. {iss}"
        if year:
            s += f", {year}"
        if pages:
            s += f", pp. {pages}"
        s += "."
        if url:
            s += f" {url}."
        return s

    # 兜底：GB/T 顺序编码制
    return format_citation(meta, "gbt7714-numeric")


def _session_lib_dir():
    try:
        from memomics.bio_tools.debate_analysis import get_session_results_dir
        rd = get_session_results_dir()
        if rd:
            return os.path.join(rd, "references")
    except Exception:
        pass
    return ""


def _global_lib_path():
    hh = os.environ.get("HERMES_HOME", "")
    if not hh:
        try:
            hh = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))), "hermes_home")
        except Exception:
            pass
    return os.path.join(hh, "references.bib") if hh else ""


def _load_entries(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_entries(path: str, entries: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def _append_text(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text + "\n\n")


def save_reference(action: str = "add", metadata: dict = None, global_lib: bool = False,
                   title: str = "", doi: str = "") -> str:
    """文献引用库：add / list / locate / export。

    add    : 收录一条文献（metadata: title/authors/year/doi/journal/url/abstract）
    list   : 列出已收录条目
    locate : 按 title/doi 查是否已收录（去重）
    export : 返回 BibTeX/RIS 文件路径（自动同步生成）
    """
    metadata = metadata or {}
    if action == "locate":
        needle = (title or doi or "").strip().lower()
        for path in [_p for _p in (_session_lib_dir() and os.path.join(_session_lib_dir(), "library.json"),
                                   _global_lib_path().replace(".bib", ".json")) if _p]:
            for e in _load_entries(path):
                t = str(e.get("title", "")).lower()
                d = str(e.get("doi", "")).lower()
                if needle and (needle in t or (doi and d and needle in d)):
                    return json.dumps({"found": True, "entry": e, "library": path}, ensure_ascii=False)
        return json.dumps({"found": False}, ensure_ascii=False)

    if action == "list":
        out = []
        for path in [_p for _p in (os.path.join(_session_lib_dir(), "library.json") if _session_lib_dir() else "",
                                   _global_lib_path().replace(".bib", ".json")) if _p]:
            entries = _load_entries(path)
            out.append({"library": path, "count": len(entries),
                        "entries": [{k: e.get(k) for k in ("title", "year", "doi", "journal")}
                                    for e in entries][-20:]})
        return json.dumps(out, ensure_ascii=False, indent=2)

    if action == "export":
        paths = []
        if _session_lib_dir():
            paths.append(os.path.join(_session_lib_dir(), "references.bib"))
            paths.append(os.path.join(_session_lib_dir(), "references.ris"))
        if global_lib:
            paths.append(_global_lib_path())
        return json.dumps({"ok": True, "files": [p for p in paths if os.path.isfile(p)],
                           "note": "Zotero/EndNote 可直接导入 .bib/.ris"}, ensure_ascii=False)

    if action != "add":
        return json.dumps({"ok": False, "error": f"unknown action: {action}"}, ensure_ascii=False)

    if not metadata.get("title"):
        return json.dumps({"ok": False, "error": "metadata.title 必填"}, ensure_ascii=False)

    # 去重（同 DOI 或同标题）
    if metadata.get("doi"):
        loc = json.loads(save_reference("locate", doi=metadata["doi"]))
        if loc.get("found"):
            return json.dumps({"ok": True, "added": False, "duplicate": True,
                               "library": loc.get("library")}, ensure_ascii=False)

    # 会话库优先
    if _session_lib_dir() or global_lib:
        if global_lib and not _session_lib_dir():
            jpath = _global_lib_path().replace(".bib", ".json")
            bib_path = _global_lib_path()
            ris_path = _global_lib_path().replace(".bib", ".ris")
        else:
            jpath = os.path.join(_session_lib_dir(), "library.json")
            bib_path = os.path.join(_session_lib_dir(), "references.bib")
            ris_path = os.path.join(_session_lib_dir(), "references.ris")
        entries = _load_entries(jpath)
        # 同库去重
        needle = str(metadata.get("doi", "")).lower()
        for e in entries:
            if needle and str(e.get("doi", "")).lower() == needle:
                return json.dumps({"ok": True, "added": False, "duplicate": True,
                                   "library": jpath}, ensure_ascii=False)
        entries.append(metadata)
        _save_entries(jpath, entries)
        _append_text(bib_path, _to_bibtex(metadata))
        _append_text(ris_path, _to_ris(metadata))
        return json.dumps({"ok": True, "added": True, "library": jpath,
                           "bibtex_file": bib_path, "ris_file": ris_path,
                           "bibtex_key": _bibtex_key(metadata)}, ensure_ascii=False)

    return json.dumps({"ok": False, "error": "无法定位引用库目录（会话结果目录不可用，且 global_lib=false）"},
                      ensure_ascii=False)


SCHEMA = {
    "name": "save_reference",
    "description": (
        "文献引用库：把检索到的文献（search_papers 结果）沉淀为 BibTeX/RIS 引用条目，"
        "供论文写作/投稿引用（Zotero/EndNote 可直接导入）。add 收录 / locate 查重 / "
        "list 列出 / export 返回文件路径。写论文前必须用本工具收录所有引用文献。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "list", "locate", "export"],
                       "description": "add=收录; list=列出; locate=查重; export=文件路径"},
            "metadata": {"type": "object",
                         "description": "文献元数据: {title, authors(分号分隔), year, doi, journal, url, abstract, entry_type}"},
            "global_lib": {"type": "boolean", "default": False,
                           "description": "true=写入全局库 hermes_home/references.bib(跨会话复用)"},
            "title": {"type": "string", "description": "locate 用: 按标题查重"},
            "doi": {"type": "string", "description": "locate 用: 按 DOI 查重"},
        },
        "required": ["action"],
    },
}


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="save_reference",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: save_reference(
                args.get("action", "add"),
                args.get("metadata") or {},
                args.get("global_lib", False),
                args.get("title", ""),
                args.get("doi", ""),
            ),
            emoji="📚",
            max_result_size_chars=20_000,
        )
    except Exception as e:
        logger.warning(f"save_reference register failed: {e}")


_register()
