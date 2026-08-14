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


def _bibtex_key(meta: dict) -> str:
    """生成 BibTeX key: 第一作者姓+年+标题首词（中文标题用标题首2字）。"""
    authors = meta.get("authors") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(";") if a.strip()]
    first = authors[0] if authors else ""
    parts = [p for p in first.split() if p]
    last = parts[-1] if parts else ""
    # "Smith J" / "Li W" → 姓是第一个词（末词是首字母缩写）
    if len(last) <= 2 and len(parts) > 1:
        last = parts[0]
    last = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", last or "")[:20]
    year = re.sub(r"[^0-9]", "", str(meta.get("year") or ""))[:4]
    title = str(meta.get("title") or "")
    tw = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", title)
    first_word = tw[0][:10] if tw else "ref"
    if not last:
        last = first_word
    return f"{last}{year}{first_word}"


def _escape_tex(s: str) -> str:
    return str(s or "").replace("&", "\\&").replace("%", "\\%").replace("_", "\\_").replace("#", "\\#")


def _to_bibtex(meta: dict) -> str:
    key = _bibtex_key(meta)
    etype = str(meta.get("entry_type") or "article")
    authors = meta.get("authors") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(";") if a.strip()]
    author_str = " and ".join(authors) if authors else "Unknown"
    fields = [
        f"  title = {{{_escape_tex(meta.get('title', ''))}}}",
        f"  author = {{{_escape_tex(author_str)}}}",
    ]
    if meta.get("journal"):
        fields.append(f"  journal = {{{_escape_tex(meta['journal'])}}}")
    if meta.get("year"):
        fields.append(f"  year = {{{meta['year']}}}")
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
    etype = str(meta.get("entry_type") or "article")
    ris_type = {"article": "JOUR", "preprint": "ELEC", "book": "BOOK",
                "review": "JOUR", "chapter": "CHAP"}.get(etype, "JOUR")
    authors = meta.get("authors") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(";") if a.strip()]
    lines = [f"TY  - {ris_type}"]
    for a in authors:
        lines.append(f"AU  - {a}")
    if meta.get("title"):
        lines.append(f"TI  - {meta['title']}")
    if meta.get("journal"):
        lines.append(f"JO  - {meta['journal']}")
    if meta.get("year"):
        lines.append(f"PY  - {meta['year']}")
    if meta.get("doi"):
        lines.append(f"DO  - {meta['doi']}")
    if meta.get("url"):
        lines.append(f"UR  - {meta['url']}")
    if meta.get("abstract"):
        lines.append(f"AB  - {meta['abstract'][:500]}")
    lines.append("ER  - ")
    return "\n".join(lines)


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
