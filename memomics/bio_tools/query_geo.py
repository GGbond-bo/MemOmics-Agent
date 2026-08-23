#!/usr/bin/env python3
"""query_geo.py — NCBI GEO 数据库连接器

搜索 NCBI Gene Expression Omnibus (GEO) 数据集，支持自然语言查询和
GSE/GDS 编号检索。返回数据集元数据（GSE号/标题/物种/样本数/平台/摘要/链接）。

API: NCBI E-utilities (https://eutils.ncbi.nlm.nih.gov/entrez/eutils/)
  - esearch.fcgi?db=gds  — 搜索 GEO 数据集
  - esummary.fcgi?db=gds — 获取数据集摘要
  - efetch.fcgi?db=gds   — 获取完整记录

速率限制: NCBI 无 key 时 3 次/秒，每次请求间隔 0.34s。
注册为 hermes 工具。
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error

# NCBI E-utilities base
_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_USER_AGENT = "MemOmics/1.0"
_TIMEOUT = 20
_RATE_LIMIT_DELAY = 0.34  # 3 requests/sec without API key


def _http_get_json(url: str) -> dict:
    """发起 GET 请求并返回 JSON dict。"""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


def _http_get_text(url: str) -> str:
    """发起 GET 请求并返回纯文本。"""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _search_geo_datasets(query: str, max_results: int = 10) -> list:
    """搜索 GEO DataSets (db=gds)，返回 GDS 记录列表。"""
    try:
        search_url = (
            f"{_BASE}/esearch.fcgi?db=gds"
            f"&term={urllib.parse.quote(query)}"
            f"&retmax={max_results}&retmode=json"
        )
        data = _http_get_json(search_url)
        id_list = data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        time.sleep(_RATE_LIMIT_DELAY)

        # 获取摘要
        ids_str = ",".join(id_list)
        summary_url = (
            f"{_BASE}/esummary.fcgi?db=gds&id={ids_str}&retmode=json"
        )
        summary_data = _http_get_json(summary_url)

        results = []
        for doc_id in id_list:
            doc = summary_data.get("result", {}).get(doc_id, {})
            if not doc:
                continue
            # GDS 记录的 entryType: GDS (dataset) 或 GSM (sample)
            results.append({
                "id": doc_id,
                "accession": doc.get("accession", ""),
                "title": doc.get("title", ""),
                "entry_type": doc.get("entrytype", ""),
                "gpl": doc.get("gpl", ""),
                "gse": doc.get("gse", ""),
                "summary": doc.get("summary", ""),
                "n_samples": doc.get("n_samples", 0),
                "platform": doc.get("gpl", ""),
                "taxon": doc.get("taxon", ""),
                "pubmed_id": doc.get("pubmedids", []),
                "geo_link": f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={doc.get('accession', '')}",
            })
        return results
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return []  # 限流，静默返回
        print(f"GEO search HTTP error: {e}", flush=True)
        return []
    except Exception as e:
        print(f"GEO search error: {e}", flush=True)
        return []


def search_geo(query: str, max_results: int = 10) -> str:
    """搜索 GEO 数据集。

    Args:
        query: 搜索关键词，如 'brain cancer single cell RNA-seq' 或 GSE 编号
        max_results: 最大返回数 (默认 10)

    Returns:
        JSON 字符串: {"success": True, "total": N, "datasets": [...]}
    """
    datasets = _search_geo_datasets(query, max_results)
    return json.dumps({
        "success": True,
        "total": len(datasets),
        "query": query,
        "datasets": datasets,
    }, ensure_ascii=False)


def get_geo_details(accession: str) -> str:
    """获取 GEO 数据集详情（通过 accession 号如 GSE12345）。

    Args:
        accession: GEO accession 号，如 'GSE12345'

    Returns:
        JSON 字符串: {"success": True, "accession": "...", "details": {...}}
    """
    try:
        # 直接用 accession 搜索
        datasets = _search_geo_datasets(accession, max_results=1)
        if datasets:
            return json.dumps({
                "success": True,
                "accession": accession,
                "details": datasets[0],
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "success": False,
                "error": f"No GEO record found for accession '{accession}'",
            }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"GEO detail fetch error: {e}",
        }, ensure_ascii=False)


# ============ Hermes 工具注册 ============

def register(registry):
    registry.register(
        name="search_geo",
        toolset="memomics",
        schema={
            "name": "search_geo",
            "description": (
                "搜索 NCBI GEO 数据库中的基因表达数据集（GDS/GSE），"
                "返回数据集编号/标题/物种/样本数/平台/摘要/链接。"
                "用于查找公开测序数据集。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords, e.g. 'brain cancer single cell RNA-seq human' or a GSE accession like 'GSE12345'",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max number of results (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
        handler=lambda args, **kw: search_geo(
            args.get("query", ""),
            max_results=args.get("max_results", 10),
        ),
        emoji="🧬",
        max_result_size_chars=50_000,
    )

    registry.register(
        name="get_geo_details",
        toolset="memomics",
        schema={
            "name": "get_geo_details",
            "description": (
                "通过 GEO accession 号（如 GSE12345/GDS1234）获取数据集详细信息，"
                "包括完整摘要、样本数、平台、物种等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "accession": {
                        "type": "string",
                        "description": "GEO accession number, e.g. 'GSE12345'",
                    },
                },
                "required": ["accession"],
            },
        },
        handler=lambda args, **kw: get_geo_details(
            args.get("accession", ""),
        ),
        emoji="📋",
        max_result_size_chars=50_000,
    )


# 模块加载时自动注册（与 literature_search.py 同模式）
try:
    from tools.registry import registry as _registry
    register(_registry)
except Exception:
    pass
