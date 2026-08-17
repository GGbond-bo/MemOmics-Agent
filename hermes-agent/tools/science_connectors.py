# -*- coding: utf-8 -*-
"""科学文献连接器（P1-6）：arXiv / OpenAlex，纯 stdlib（urllib + xml）

借鉴 OpenAI4S 的 source-attributed retrieval：每条记录携带
{source, query, fetched_at} 溯源元数据，入库/引用时知道记录来自哪、何时。
"""
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

_UA = {"User-Agent": "MemOmics-ScienceConnector/1.0 (research agent)"}
_ARXIV_NS = {"a": "http://www.w3.org/2005/Atom", "ar": "http://arxiv.org/schemas/atom"}


def _fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers={**_UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _provenance(source: str, query: str) -> dict:
    return {"source": source, "query": query,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")}


def _reconstruct_abstract(inverted_index: dict) -> str:
    """OpenAlex abstract_inverted_index → 原文（{word: [positions]}）"""
    if not inverted_index:
        return ""
    pos_map = {}
    for word, positions in inverted_index.items():
        for p in positions:
            pos_map[p] = word
    return " ".join(pos_map[i] for i in sorted(pos_map))


def arxiv_search(query: str, limit: int = 5, timeout: int = 20) -> dict:
    """arXiv API（Atom XML）→ 带溯源记录列表"""
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}", "max_results": min(int(limit), 20)})
    url = f"http://export.arxiv.org/api/query?{params}"
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=_UA), timeout=timeout) as r:
            root = ET.fromstring(r.read())
        records = []
        for e in root.findall("a:entry", _ARXIV_NS):
            title = (e.findtext("a:title", "", _ARXIV_NS) or "").strip().replace("\n", " ")
            summary = (e.findtext("a:summary", "", _ARXIV_NS) or "").strip()
            authors = [a.findtext("a:name", "", _ARXIV_NS)
                       for a in e.findall("a:author", _ARXIV_NS)]
            published = (e.findtext("a:published", "", _ARXIV_NS) or "")
            rec = {
                "title": title,
                "authors": authors,
                "abstract": summary[:500],
                "url": (e.findtext("a:id", "", _ARXIV_NS) or "").strip(),
                "published": published[:10],
                "source": "arxiv",
            }
            rec.update(_provenance("arxiv", query))
            records.append(rec)
        return {"query": query, "total": len(records), "results": records}
    except Exception as e:
        return {"query": query, "total": 0, "results": [], "error": str(e)}


def openalex_search(query: str, limit: int = 5, timeout: int = 20) -> dict:
    """OpenAlex works API → 带溯源记录列表"""
    params = urllib.parse.urlencode({"search": query, "per-page": min(int(limit), 20)})
    url = f"https://api.openalex.org/works?{params}"
    try:
        d = _fetch_json(url, timeout)
        records = []
        for w in d.get("results", [])[: int(limit)]:
            rec = {
                "title": w.get("title") or "",
                "authors": [a["author"]["display_name"]
                            for a in w.get("authorships", [])][:10],
                "abstract": _reconstruct_abstract(w.get("abstract_inverted_index") or {})[:500],
                "url": w.get("doi") or w.get("id", ""),
                "published": (w.get("publication_date") or "")[:10],
                "source": "openalex",
            }
            rec.update(_provenance("openalex", query))
            records.append(rec)
        return {"query": query, "total": d.get("meta", {}).get("count", len(records)),
                "results": records}
    except Exception as e:
        return {"query": query, "total": 0, "results": [], "error": str(e)}
