#!/usr/bin/env python3
"""query_ensembl.py — Ensembl 基因组数据库连接器

查询 Ensembl 基因组数据库，支持四种模式：
1. symbol: 基因符号→基因坐标/ID 映射
2. lookup: 按 Ensembl ID 获取基因详情
3. xrefs: 基因符号→所有外部数据库 ID 映射
4. sequence: 按 Ensembl ID 获取序列

API: Ensembl REST API (https://rest.ensembl.org/)
  需要 Accept: application/json header。
  无需 API key。

速率限制: Ensembl 限制 15 次/秒，建议间隔 0.1s。

注册为 hermes 工具。
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error

_BASE = "https://rest.ensembl.org"
_USER_AGENT = "MemOmics/1.0"
_TIMEOUT = 20
_RATE_LIMIT_DELAY = 0.1  # 15 requests/sec


def _http_get_json(url: str) -> dict:
    """发起 GET 请求并返回 JSON dict。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


def _http_post_json(url: str, body: dict) -> dict:
    """发起 POST 请求并返回 JSON dict。"""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


def _lookup_by_symbol(symbol: str, species: str = "human") -> list:
    """基因符号→基因信息: /lookup/symbol/{species}/{symbol}。

    支持单个符号或逗号分隔的多个符号（用 POST 批量端点）。
    """
    try:
        symbols = [s.strip() for s in symbol.replace(",", " ").split() if s.strip()]
        if len(symbols) == 1:
            url = f"{_BASE}/lookup/symbol/{species}/{urllib.parse.quote(symbols[0])}?expand=1"
            data = _http_get_json(url)
            return [_format_lookup_result(data)] if data else []
        else:
            # POST 批量查询
            url = f"{_BASE}/lookup/symbol/{species}"
            body = {"symbols": symbols}
            data = _http_post_json(url, body)
            results = []
            for sym, info in data.items():
                if info:
                    results.append(_format_lookup_result(info))
            return results
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return []
        print(f"Ensembl symbol lookup HTTP error: {e}", flush=True)
        return []
    except Exception as e:
        print(f"Ensembl symbol lookup error: {e}", flush=True)
        return []


def _format_lookup_result(data: dict) -> dict:
    """格式化 Ensembl lookup 结果。"""
    return {
        "ensembl_id": data.get("id", ""),
        "symbol": data.get("display_name", ""),
        "biotype": data.get("biotype", ""),
        "chromosome": data.get("seq_region_name", ""),
        "start": data.get("start", 0),
        "end": data.get("end", 0),
        "strand": data.get("strand", 1),
        "assembly": data.get("assembly_name", ""),
        "species": data.get("species", ""),
        "description": data.get("description", ""),
        "canonical_transcript": data.get("canonical_transcript", ""),
        "transcripts": [
            {
                "id": t.get("id", ""),
                "biotype": t.get("biotype", ""),
                "start": t.get("start", 0),
                "end": t.get("end", 0),
            }
            for t in data.get("Transcript", [])[:5]
        ] if "Transcript" in data else [],
        "ensembl_link": f"https://www.ensembl.org/{data.get('species','')}/Gene/Summary?g={data.get('id','')}",
    }


def _lookup_by_id(ensembl_id: str) -> dict:
    """按 Ensembl ID 获取详情: /lookup/id/{id}。"""
    try:
        url = f"{_BASE}/lookup/id/{urllib.parse.quote(ensembl_id)}?expand=1"
        data = _http_get_json(url)
        return _format_lookup_result(data) if data else {}
    except Exception as e:
        print(f"Ensembl lookup error: {e}", flush=True)
        return {}


def _get_xrefs(symbol: str, species: str = "human", max_results: int = 20) -> list:
    """符号→外部 ID 映射: /xrefs/symbol/{species}/{symbol}。"""
    try:
        url = f"{_BASE}/xrefs/symbol/{species}/{urllib.parse.quote(symbol)}?all=1"
        data = _http_get_json(url)
        results = []
        for xref in data[:max_results]:
            results.append({
                "db_name": xref.get("dbname", ""),
                "display_id": xref.get("display_id", ""),
                "primary_id": xref.get("primary_id", ""),
                "description": xref.get("description", ""),
                "info_type": xref.get("info_type", ""),
            })
        return results
    except Exception as e:
        print(f"Ensembl xrefs error: {e}", flush=True)
        return []


def _get_sequence(ensembl_id: str, seq_type: str = "genomic") -> str:
    """按 ID 获取序列: /sequence/id/{id}。"""
    try:
        url = f"{_BASE}/sequence/id/{urllib.parse.quote(ensembl_id)}?type={seq_type}"
        data = _http_get_json(url)
        return data.get("seq", "")
    except Exception as e:
        print(f"Ensembl sequence error: {e}", flush=True)
        return ""


def query_ensembl(query: str, query_type: str = "symbol", species: str = "human",
                  max_results: int = 10) -> str:
    """查询 Ensembl 基因组数据库。

    Args:
        query: 基因符号或 Ensembl ID
        query_type: 查询类型: 'symbol'(符号→坐标) / 'lookup'(ID→详情) / 'xrefs'(符号→外部ID) / 'sequence'(ID→序列)
        species: 物种 (默认 'human'，可用 'mouse', 'rat' 等)
        max_results: 最大返回数 (默认 10)

    Returns:
        JSON 字符串
    """
    if query_type == "lookup":
        details = _lookup_by_id(query)
        if details:
            return json.dumps({
                "success": True,
                "query_type": "lookup",
                "ensembl_id": query,
                "details": details,
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "success": False,
                "error": f"No Ensembl record found for ID '{query}'",
            }, ensure_ascii=False)

    elif query_type == "xrefs":
        xrefs = _get_xrefs(query, species, max_results)
        return json.dumps({
            "success": True,
            "query_type": "xrefs",
            "query": query,
            "species": species,
            "total": len(xrefs),
            "xrefs": xrefs,
        }, ensure_ascii=False)

    elif query_type == "sequence":
        seq = _get_sequence(query)
        if seq:
            return json.dumps({
                "success": True,
                "query_type": "sequence",
                "ensembl_id": query,
                "sequence": seq[:20000],
                "truncated": len(seq) > 20000,
                "length": len(seq),
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "success": False,
                "error": f"No sequence found for '{query}'",
            }, ensure_ascii=False)

    else:  # symbol (default)
        results = _lookup_by_symbol(query, species)
        return json.dumps({
            "success": True,
            "query_type": "symbol",
            "query": query,
            "species": species,
            "total": len(results),
            "genes": results[:max_results],
        }, ensure_ascii=False)


# ============ Hermes 工具注册 ============

def register(registry):
    registry.register(
        name="query_ensembl",
        toolset="memomics",
        schema={
            "name": "query_ensembl",
            "description": (
                "查询 Ensembl 基因组数据库。支持四种模式："
                "'symbol' 基因符号→坐标/ID（如 'TP53'）；"
                "'lookup' 按 Ensembl ID 获取详情（如 'ENSG00000141510'）；"
                "'xrefs' 基因符号→外部数据库 ID 映射；"
                "'sequence' 按 ID 获取序列。"
                "用于基因注释、坐标查询和 ID 映射。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Gene symbol or Ensembl ID, e.g. 'TP53' or 'ENSG00000141510'",
                    },
                    "query_type": {
                        "type": "string",
                        "enum": ["symbol", "lookup", "xrefs", "sequence"],
                        "default": "symbol",
                        "description": "Query mode: symbol=gene→coords, lookup=ID→details, xrefs=symbol→external IDs, sequence=ID→sequence",
                    },
                    "species": {
                        "type": "string",
                        "default": "human",
                        "description": "Species name: 'human', 'mouse', 'rat', etc.",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (default 10)",
                    },
                },
                "required": ["query"],
            },
        },
        handler=lambda args, **kw: query_ensembl(
            args.get("query", ""),
            query_type=args.get("query_type", "symbol"),
            species=args.get("species", "human"),
            max_results=args.get("max_results", 10),
        ),
        emoji="🔬",
        max_result_size_chars=50_000,
    )


# 模块加载时自动注册
try:
    from tools.registry import registry as _registry
    register(_registry)
except Exception:
    pass
