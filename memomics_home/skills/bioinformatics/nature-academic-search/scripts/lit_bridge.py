#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lit_bridge.py — nature-academic-search 的「无 MCP」检索桥（只用标准库）。

上游 nature-academic-search 把检索能力包在 mcp-server/ 里（MCP 协议 + requests/defusedxml/toml/
pybliometrics）。MemOmics 是单页 WebUI + 自研 agent 循环，进程里没有 MCP 客户端，MCP 工具名
（search_papers / get_paper_by_id / get_citation / lookup_mesh）一个都调不到，于是整条检索能力
等于装了个摆设。

本脚本按「同一套语义、不走 MCP 协议」把这四个核心工具重写成 CLI：
  search  <query>   多源并发检索：pubmed / crossref / arxiv / openalex
  paper   <id>      DOI / PMID / arXiv ID -> 单篇元数据（自动识别 id 类型）
  cite    <id>      DOI/PMID -> APA / GB-T 7714 / BibTeX / RIS
  mesh    <term>    MeSH 词表查询（入口词 + 树号）

设计约束（为什么不用上游 sources/）：
  1. 只用标准库（urllib + xml.etree + json + argparse + concurrent.futures），零 pip 安装；
     上游 sources/ 要 toml + defusedxml + pybliometrics，装在用户机器上会炸。
  2. 零 API key：PubMed E-utilities / Crossref / arXiv / OpenAlex 都无需 key（有 key 更快）。
  3. 读 HTTP_PROXY / HTTPS_PROXY（本机代理 http://127.0.0.1:6478）。
  4. 单源失败不影响其它源：错误逐源收集，最后一起报告（对齐上游「report specific tool
     failures and continue with remaining tools」）。
  5. 退出码：0 = 至少一个源返回结果；2 = 全部源失败或无结果。

用法示例：
  python lit_bridge.py search "skeletal muscle single-cell aging" --limit 5
  python lit_bridge.py search "sarcopenia exercise" --sources pubmed,openalex --year-from 2022 --json
  python lit_bridge.py paper 10.1038/s41586-020-2496-1
  python lit_bridge.py paper PMID:33361817
  python lit_bridge.py cite 10.1038/s41586-020-2496-1 --style gbt7714
  python lit_bridge.py mesh sarcopenia
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = "MemOmics-lit_bridge/1.0 (+https://github.com/GGbond-bo/MemOmics-Agent)"
TIMEOUT = 25
DEFAULT_MAILTO = os.environ.get("OPENALEX_MAILTO") or os.environ.get("CROSSREF_MAILTO") or ""

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
CROSSREF = "https://api.crossref.org"
OPENALEX = "https://api.openalex.org"
ARXIV = "https://export.arxiv.org/api/query"
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


# ---------------------------------------------------------------- HTTP
def http_get(url: str, params: dict | None = None, timeout: int = TIMEOUT) -> bytes:
    """GET 一个 URL，返回原始 bytes。代理由 urllib 自动从环境变量读取。"""
    if params:
        clean = {k: v for k, v in params.items() if v not in (None, "")}
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(clean)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_json(url: str, params: dict | None = None, timeout: int = TIMEOUT) -> dict:
    return json.loads(http_get(url, params, timeout).decode("utf-8", "replace"))


def _text(node, path: str, ns: dict | None = None) -> str:
    if node is None:
        return ""
    found = node.find(path, ns or {})
    return (found.text or "").strip() if found is not None and found.text else ""


def _year_of(*candidates) -> int | None:
    for c in candidates:
        if not c:
            continue
        m = re.search(r"(19|20)\d{2}", str(c))
        if m:
            y = int(m.group(0))
            if 1900 < y < 2100:
                return y
    return None


# ---------------------------------------------------------------- sources
def pubmed_search(query: str, limit: int = 10, year_from: int | None = None) -> list[dict]:
    """PubMed E-utilities：esearch -> esummary(JSON)。"""
    term = query
    if year_from:
        term = f"({query}) AND (\"{year_from}\"[dp] : \"3000\"[dp])"
    ids = http_json(EUTILS + "esearch.fcgi", {
        "db": "pubmed", "term": term, "retmax": limit, "retmode": "json", "sort": "relevance",
        "email": DEFAULT_MAILTO or None,
    })
    idlist = (((ids or {}).get("esearchresult") or {}).get("idlist")) or []
    if not idlist:
        return []
    summ = http_json(EUTILS + "esummary.fcgi", {
        "db": "pubmed", "id": ",".join(idlist), "retmode": "json",
        "email": DEFAULT_MAILTO or None,
    })
    result = (summ or {}).get("result") or {}
    out = []
    for pmid in idlist:
        it = result.get(pmid)
        if not isinstance(it, dict):
            continue
        doi = ""
        for aid in it.get("articleids") or []:
            if aid.get("idtype") == "doi":
                doi = aid.get("value") or ""
                break
        out.append({
            "source": "pubmed",
            "pmid": pmid,
            "doi": doi,
            "title": _clean_title(it.get("title")),
            "authors": [a.get("name", "") for a in (it.get("authors") or [])][:20],
            "year": _year_of(it.get("pubdate"), it.get("epubdate")),
            "venue": it.get("fulljournalname") or it.get("source") or "",
            "volume": it.get("volume") or "",
            "issue": it.get("issue") or "",
            "pages": it.get("pages") or "",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "citations": None,
            "type": (it.get("pubtype") or [""])[0] if it.get("pubtype") else "",
        })
    return out


def crossref_search(query: str, limit: int = 10, year_from: int | None = None) -> list[dict]:
    """Crossref /works：按题录相关度检索。"""
    params = {
        "query.bibliographic": query, "rows": limit, "mailto": DEFAULT_MAILTO or None,
        "select": "DOI,title,author,issued,container-title,volume,issue,page,is-referenced-by-count,type,URL",
    }
    if year_from:
        params["filter"] = f"from-pub-date:{year_from}-01-01"
    data = http_json(CROSSREF + "/works", params)
    out = []
    for it in ((data or {}).get("message") or {}).get("items") or []:
        authors = []
        for a in it.get("author") or []:
            nm = " ".join(x for x in [a.get("given"), a.get("family")] if x).strip() or a.get("name", "")
            if nm:
                authors.append(nm)
        issued = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
        out.append({
            "source": "crossref",
            "pmid": "",
            "doi": (it.get("DOI") or "").lower(),
            "title": _clean_title((it.get("title") or [""])[0]),
            "authors": authors[:20],
            "year": issued[0] if issued else None,
            "venue": (it.get("container-title") or [""])[0],
            "volume": it.get("volume") or "",
            "issue": it.get("issue") or "",
            "pages": it.get("page") or "",
            "url": it.get("URL") or (f"https://doi.org/{it.get('DOI')}" if it.get("DOI") else ""),
            "citations": it.get("is-referenced-by-count"),
            "type": it.get("type") or "",
        })
    return out


def openalex_search(query: str, limit: int = 10, year_from: int | None = None) -> list[dict]:
    """OpenAlex /works：无需 key，覆盖面最广（含引用数、OA 链接）。"""
    params = {"search": query, "per-page": limit, "mailto": DEFAULT_MAILTO or None}
    if year_from:
        params["filter"] = f"from_publication_date:{year_from}-01-01"
    data = http_json(OPENALEX + "/works", params)
    out = []
    for it in (data or {}).get("results") or []:
        loc = it.get("primary_location") or {}
        src = (loc.get("source") or {}) if isinstance(loc.get("source"), dict) else {}
        out.append({
            "source": "openalex",
            "pmid": (it.get("ids") or {}).get("pmid", "").rsplit("/", 1)[-1],
            "doi": (it.get("doi") or "").replace("https://doi.org/", "").lower(),
            "title": _clean_title(it.get("title")),
            "authors": [((a.get("author") or {}).get("display_name") or "") for a in (it.get("authorships") or [])][:20],
            "year": it.get("publication_year"),
            "venue": src.get("display_name") or "",
            "volume": (it.get("biblio") or {}).get("volume") or "",
            "issue": (it.get("biblio") or {}).get("issue") or "",
            "pages": "-".join(x for x in [(it.get("biblio") or {}).get("first_page"), (it.get("biblio") or {}).get("last_page")] if x),
            "url": loc.get("landing_page_url") or it.get("id") or "",
            "citations": it.get("cited_by_count"),
            "type": it.get("type") or "",
            "is_oa": bool((it.get("open_access") or {}).get("is_oa")),
        })
    return out


def arxiv_search(query: str, limit: int = 10, year_from: int | None = None) -> list[dict]:
    """arXiv Atom feed（预印本，生物信息学里多为方法学论文）。"""
    raw = http_get(ARXIV, {"search_query": f"all:{query}", "start": 0, "max_results": limit})
    root = ET.fromstring(raw)
    out = []
    for entry in root.findall("a:entry", ATOM):
        published = _text(entry, "a:published", ATOM)
        out.append({
            "source": "arxiv",
            "pmid": "",
            "doi": _text(entry, "arxiv:doi", ATOM),
            "title": " ".join(_text(entry, "a:title", ATOM).split()),
            "authors": [" ".join(_text(a, "a:name", ATOM).split()) for a in entry.findall("a:author", ATOM)][:20],
            "year": _year_of(published),
            "venue": "arXiv",
            "volume": "", "issue": "", "pages": "",
            "url": _text(entry, "a:id", ATOM),
            "citations": None,
            "type": "preprint",
        })
    return out


SOURCES = {
    "pubmed": pubmed_search,
    "crossref": crossref_search,
    "openalex": openalex_search,
    "arxiv": arxiv_search,
}


# ---------------------------------------------------------------- helpers
def _clean_title(t: str) -> str:
    """去掉 JATS 标签（<scp>/<i>…）和多余空白——Crossref 的题名经常带这些。"""
    return " ".join(re.sub(r"<[^>]+>", "", t or "").split())


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())[:80]


def dedup(records: list[dict]) -> list[dict]:
    """跨源去重：DOI > PMID > 归一化标题；保留先出现的（源顺序即优先级）。"""
    seen, out = set(), []
    for r in records:
        keys = []
        if r.get("doi"):
            keys.append("doi:" + r["doi"].lower())
        if r.get("pmid"):
            keys.append("pmid:" + str(r["pmid"]))
        if r.get("title"):
            keys.append("t:" + _norm_title(r["title"]))
        if keys and any(k in seen for k in keys):
            continue
        seen.update(keys)
        out.append(r)
    return out


def detect_id(raw: str) -> tuple[str, str]:
    """识别 id 类型：doi / pmid / arxiv / unknown。"""
    s = (raw or "").strip()
    low = s.lower()
    if low.startswith("pmid:"):
        return "pmid", s.split(":", 1)[1].strip()
    if low.startswith("arxiv:"):
        return "arxiv", s.split(":", 1)[1].strip()
    if low.startswith("doi:"):
        return "doi", s.split(":", 1)[1].strip()
    if low.startswith("10.") or "doi.org/" in low:
        return "doi", re.sub(r"^.*?doi\.org/", "", low)
    if re.fullmatch(r"\d{6,9}", s):
        return "pmid", s
    if re.fullmatch(r"(arxiv:)?\d{4}\.\d{4,5}(v\d+)?", low) or re.fullmatch(r"[a-z-]+(\.[A-Z]{2})?/\d{7}(v\d+)?", s):
        return "arxiv", low.replace("arxiv:", "")
    return "unknown", s


def fetch_paper(raw_id: str) -> dict:
    """按 id 取单篇元数据（DOI -> Crossref，PMID -> PubMed，arXiv -> Atom）。"""
    kind, value = detect_id(raw_id)
    if kind == "doi":
        data = http_json(CROSSREF + "/works/" + urllib.parse.quote(value), {"mailto": DEFAULT_MAILTO or None})
        it = (data or {}).get("message") or {}
        if not it:
            raise RuntimeError(f"Crossref 查不到 DOI: {value}")
        authors = []
        for a in it.get("author") or []:
            nm = " ".join(x for x in [a.get("given"), a.get("family")] if x).strip() or a.get("name", "")
            if nm:
                authors.append(nm)
        issued = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
        return {
            "source": "crossref", "id_type": "doi", "doi": value.lower(), "pmid": "",
            "title": _clean_title((it.get("title") or [""])[0]), "authors": authors,
            "year": issued[0] if issued else None,
            "venue": (it.get("container-title") or [""])[0],
            "volume": it.get("volume") or "", "issue": it.get("issue") or "", "pages": it.get("page") or "",
            "url": it.get("URL") or f"https://doi.org/{value}", "citations": it.get("is-referenced-by-count"),
            "type": it.get("type") or "",
            "publisher": it.get("publisher") or "",
            "issn": (it.get("ISSN") or [""])[0],
        }
    if kind == "pmid":
        recs = _pubmed_by_ids([value])
        if not recs:
            raise RuntimeError(f"PubMed 查不到 PMID: {value}")
        rec = recs[0]
        rec["id_type"] = "pmid"
        return rec
    if kind == "arxiv":
        raw = http_get(ARXIV, {"id_list": value, "max_results": 1})
        root = ET.fromstring(raw)
        entry = root.find("a:entry", ATOM)
        if entry is None:
            raise RuntimeError(f"arXiv 查不到: {value}")
        return {
            "source": "arxiv", "id_type": "arxiv", "doi": _text(entry, "arxiv:doi", ATOM), "pmid": "",
            "title": " ".join(_text(entry, "a:title", ATOM).split()),
            "authors": [" ".join(_text(a, "a:name", ATOM).split()) for a in entry.findall("a:author", ATOM)],
            "year": _year_of(_text(entry, "a:published", ATOM)), "venue": "arXiv",
            "volume": "", "issue": "", "pages": "", "url": _text(entry, "a:id", ATOM),
            "citations": None, "type": "preprint",
            "abstract": " ".join(_text(entry, "a:summary", ATOM).split()),
        }
    raise RuntimeError(f"无法识别 id 类型（支持 DOI / PMID / arXiv ID）: {raw_id}")


def _pubmed_by_ids(pmids: list[str]) -> list[dict]:
    summ = http_json(EUTILS + "esummary.fcgi", {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"})
    result = (summ or {}).get("result") or {}
    out = []
    for pmid in pmids:
        it = result.get(pmid)
        if not isinstance(it, dict):
            continue
        doi = ""
        for aid in it.get("articleids") or []:
            if aid.get("idtype") == "doi":
                doi = aid.get("value") or ""
                break
        out.append({
            "source": "pubmed", "pmid": pmid, "doi": doi,
            "title": _clean_title(it.get("title")),
            "authors": [a.get("name", "") for a in (it.get("authors") or [])],
            "year": _year_of(it.get("pubdate"), it.get("epubdate")),
            "venue": it.get("fulljournalname") or it.get("source") or "",
            "volume": it.get("volume") or "", "issue": it.get("issue") or "", "pages": it.get("pages") or "",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "citations": None,
            "type": (it.get("pubtype") or [""])[0] if it.get("pubtype") else "",
        })
    return out


def mesh_lookup(term: str, limit: int = 5) -> dict:
    """MeSH 词表查询：esearch(db=mesh) -> esummary。"""
    found = http_json(EUTILS + "esearch.fcgi", {"db": "mesh", "term": term, "retmax": limit, "retmode": "json"})
    ids = (((found or {}).get("esearchresult") or {}).get("idlist")) or []
    if not ids:
        return {"term": term, "count": 0, "entries": []}
    summ = http_json(EUTILS + "esummary.fcgi", {"db": "mesh", "id": ",".join(ids), "retmode": "json"})
    result = (summ or {}).get("result") or {}
    entries = []
    for uid in ids:
        it = result.get(uid)
        if not isinstance(it, dict):
            continue
        entries.append({
            "uid": uid,
            "name": it.get("ds_meshterms", [""])[0] if it.get("ds_meshterms") else it.get("title", ""),
            "mesh_terms": it.get("ds_meshterms") or [],
            "note": (it.get("ds_meshterms") or [""])[0] if it.get("ds_meshterms") else "",
            "see_also": it.get("ds_idxlinks") or [],
        })
    return {"term": term, "count": len(entries), "entries": entries}


# ---------------------------------------------------------------- citation format
def format_citation(rec: dict, style: str = "apa") -> str:
    authors = [a for a in (rec.get("authors") or []) if a]
    year = rec.get("year") or "n.d."
    title = (rec.get("title") or "").rstrip(".")
    venue = rec.get("venue") or ""
    vol, issue, pages = rec.get("volume") or "", rec.get("issue") or "", rec.get("pages") or ""
    doi = rec.get("doi") or ""
    style = (style or "apa").lower()
    if style in ("bibtex", "bib"):
        key = (authors[0].split()[-1].lower() if authors else "anon") + str(year)
        if doi:
            key += re.sub(r"[^a-z0-9]", "", doi.lower())[-10:]
        fields = [
            ("title", "{" + title + "}"),
            ("author", " and ".join(authors) if authors else ""),
            ("year", str(year)),
            ("journal", venue),
            ("volume", vol), ("number", issue), ("pages", pages),
            ("doi", doi),
            ("url", rec.get("url") or ""),
        ]
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields if v)
        return "@article{" + key + ",\n" + body + "\n}"
    if style in ("ris", "nbib"):
        lines = ["TY  - JOUR"]
        lines += [f"AU  - {a}" for a in authors]
        lines += [f"TI  - {title}", f"JO  - {venue}", f"PY  - {year}",
                  f"VL  - {vol}", f"IS  - {issue}", f"SP  - {pages}",
                  f"DO  - {doi}", f"UR  - {rec.get('url') or ''}"]
        if rec.get("pmid"):
            lines.append(f"AN  - PMID:{rec['pmid']}")
        lines.append("ER  - ")
        return "\n".join(x for x in lines if x.split("  - ", 1)[-1].strip())
    if style in ("gbt7714", "gbt", "gb/t7714", "cn"):
        a = ", ".join(authors[:3]) + (", et al" if len(authors) > 3 else "")
        tail = f"{venue}, {year}"
        if vol:
            tail += f", {vol}"
        if issue:
            tail += f"({issue})"
        if pages:
            tail += f": {pages}"
        out = f"{a}. {title}[J]. {tail}."
        if doi:
            out += f" DOI: {doi}."
        return out
    # APA 7
    if not authors:
        who = "Anonymous"
    elif len(authors) == 1:
        who = authors[0]
    elif len(authors) <= 20:
        who = ", ".join(authors[:-1]) + ", & " + authors[-1]
    else:
        who = ", ".join(authors[:19]) + ", ... " + authors[-1]
    out = f"{who} ({year}). {title}. {venue}"
    if vol:
        out += f", {vol}"
    if issue:
        out += f"({issue})"
    if pages:
        out += f", {pages}"
    out += "."
    if doi:
        out += f" https://doi.org/{doi}"
    return out


# ---------------------------------------------------------------- rendering
def render_human(records: list[dict]) -> str:
    lines = []
    for i, r in enumerate(records, 1):
        au = ", ".join((r.get("authors") or [])[:3]) + (" et al." if len(r.get("authors") or []) > 3 else "")
        cites = r.get("citations")
        lines.append(f"[{i}] ({r.get('source')}) {r.get('title') or '(no title)'}")
        lines.append(f"    {au} | {r.get('venue') or '-'} | {r.get('year') or '-'} | 引用 {cites if cites is not None else '-'}")
        ids = " ".join(x for x in [f"DOI:{r['doi']}" if r.get("doi") else "", f"PMID:{r['pmid']}" if r.get("pmid") else ""] if x)
        lines.append(f"    {ids or '-'} | {r.get('url') or '-'}")
    return "\n".join(lines)


def main(argv=None) -> int:
    global DEFAULT_MAILTO          # 必须在任何引用之前声明（--mailto 的默认值也引用它）
    ap = argparse.ArgumentParser(description="nature-academic-search 无 MCP 检索桥")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("search", help="多源并发检索")
    p.add_argument("query")
    p.add_argument("--sources", default="pubmed,crossref,openalex")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--year-from", type=int, default=None)
    p.add_argument("--mailto", default=DEFAULT_MAILTO)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-dedup", action="store_true")

    p = sub.add_parser("paper", help="按 DOI/PMID/arXiv ID 取单篇元数据")
    p.add_argument("id")
    p.add_argument("--citation", default=None, help="顺便输出引用（apa/gbt7714/bibtex/ris）")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("cite", help="生成引用文本")
    p.add_argument("id")
    p.add_argument("--style", default="apa", choices=["apa", "gbt7714", "bibtex", "ris"])

    p = sub.add_parser("mesh", help="MeSH 词表查询")
    p.add_argument("term")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if getattr(args, "mailto", ""):
        DEFAULT_MAILTO = args.mailto

    if args.cmd == "search":
        wanted = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
        picked = [s for s in wanted if s in SOURCES]
        unknown = [s for s in wanted if s not in SOURCES]
        records, errors = [], []
        with ThreadPoolExecutor(max_workers=max(1, len(picked))) as pool:
            futs = {pool.submit(SOURCES[s], args.query, args.limit, args.year_from): s for s in picked}
            for fut in as_completed(futs):
                name = futs[fut]
                try:
                    records.extend(fut.result() or [])
                except Exception as exc:  # 单源失败不拖垮整体
                    errors.append(f"{name}: {type(exc).__name__}: {exc}")
        if not args.no_dedup:
            records = dedup(records)
        for e in errors:
            print(f"[warn] 源失败 {e}", file=sys.stderr)
        if unknown:
            print(f"[warn] 未知源被忽略: {unknown}（可用: {list(SOURCES)}）", file=sys.stderr)
        if args.json:
            print(json.dumps({"query": args.query, "count": len(records),
                              "sources_used": picked, "errors": errors, "records": records},
                             ensure_ascii=False, indent=2))
        else:
            print(f"query={args.query!r} sources={picked} 命中 {len(records)} 条（已跨源去重）")
            print(render_human(records))
        return 0 if records else 2

    if args.cmd == "paper":
        try:
            rec = fetch_paper(args.id)
        except Exception as exc:
            print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        if args.citation:
            rec["citation"] = format_citation(rec, args.citation)
        print(json.dumps(rec, ensure_ascii=False, indent=2) if args.json else
              render_human([rec]) + ("\n\n" + rec["citation"] if args.citation else ""))
        return 0

    if args.cmd == "cite":
        try:
            rec = fetch_paper(args.id)
        except Exception as exc:
            print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        print(format_citation(rec, args.style))
        return 0

    if args.cmd == "mesh":
        try:
            data = mesh_lookup(args.term, args.limit)
        except Exception as exc:
            print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"MeSH 查询 {args.term!r} -> {data['count']} 条")
            for e in data["entries"]:
                print(f"  [{e['uid']}] {e['name']}")
                for t in (e.get("mesh_terms") or [])[:6]:
                    print(f"        - {t}")
                trees = []
                for x in (e.get("see_also") or []):
                    trees.append(x.get("treenum") if isinstance(x, dict) else str(x))
                trees = [t for t in trees if t]
                if trees:
                    print(f"        tree: {', '.join(trees[:5])}")
        return 0 if data["count"] else 2

    return 2


if __name__ == "__main__":
    sys.exit(main())
