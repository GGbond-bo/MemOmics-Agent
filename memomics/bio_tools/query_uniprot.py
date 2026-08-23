#!/usr/bin/env python3
"""query_uniprot.py — UniProt 蛋白质数据库连接器

查询 UniProt 蛋白质数据库，支持三种模式：
1. search: 按关键词搜索蛋白质条目
2. accession: 按 accession 号获取详情
3. fasta: 批量获取 FASTA 序列

API: UniProt REST API (https://rest.uniprot.org/)
  无需 API key。

速率限制: UniProt 建议合理使用，无严格限制。

注册为 hermes 工具。
"""

import json
import urllib.request
import urllib.parse
import urllib.error

_BASE = "https://rest.uniprot.org"
_USER_AGENT = "MemOmics/1.0"
_TIMEOUT = 30


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


def _parse_uniprot_entry(entry: dict) -> dict:
    """解析 UniProt JSON 条目，提取常用字段。"""
    # 提取 organism
    organism = ""
    organism_scientific = ""
    if "organism" in entry:
        organism = entry["organism"].get("scientificName", "")
        organism_scientific = entry["organism"].get("scientificName", "")

    # 提取 gene names
    gene_names = []
    for gene in entry.get("genes", []):
        if "geneName" in gene:
            gene_names.append(gene["geneName"].get("value", ""))

    # 提取 protein name
    protein_name = ""
    protein_desc = ""
    if "proteinDescription" in entry:
        rec = entry["proteinDescription"].get("recommendedName", {})
        if rec:
            protein_name = rec.get("fullName", {}).get("value", "")

    # 提取 function
    function = ""
    for comment in entry.get("comments", []):
        if comment.get("commentType") == "FUNCTION":
            for text in comment.get("texts", []):
                function += text.get("value", "") + " "
            function = function.strip()

    # 提取 accession
    accessions = entry.get("secondaryAccessions", [])
    primary_accession = entry.get("primaryAccession", "")

    # 提取 sequence length
    seq_len = entry.get("sequence", {}).get("length", 0)

    # 提取 PTM / subcellular location
    subcellular_locations = []
    for comment in entry.get("comments", []):
        if comment.get("commentType") == "SUBCELLULAR_LOCATION":
            for loc in comment.get("subcellularLocations", []):
                loc_name = loc.get("location", {}).get("value", "")
                if loc_name:
                    subcellular_locations.append(loc_name)

    # 提取 keywords
    keywords = [kw.get("name", "") for kw in entry.get("keywords", [])]

    # 提取 publications
    pub_count = len(entry.get("uniProtKBCrossReferences", []))

    # 提取 PDB cross-references
    pdb_ids = []
    for xref in entry.get("uniProtKBCrossReferences", []):
        if xref.get("database") == "PDB":
            pdb_ids.append(xref.get("id", ""))

    return {
        "accession": primary_accession,
        "secondary_accessions": accessions[:5],
        "protein_name": protein_name,
        "gene_names": gene_names,
        "organism": organism_scientific,
        "length": seq_len,
        "function": function[:2000] if function else "",
        "subcellular_locations": subcellular_locations,
        "keywords": keywords,
        "pdb_ids": pdb_ids[:10],
        "uniprot_link": f"https://www.uniprot.org/uniprot/{primary_accession}",
    }


def _search_uniprot(query: str, max_results: int = 10, reviewed: bool = True) -> list:
    """搜索 UniProt: /uniprotkb/search?query={query}&format=json&size={n}。"""
    try:
        # 构建 query，可选只看 reviewed (Swiss-Prot)
        full_query = query
        if reviewed:
            full_query = f"({query}) AND reviewed:true"

        url = (
            f"{_BASE}/uniprotkb/search"
            f"?query={urllib.parse.quote(full_query)}"
            f"&format=json"
            f"&size={max_results}"
        )
        data = _http_get_json(url)
        results = []
        for entry in data.get("results", []):
            results.append(_parse_uniprot_entry(entry))
        return results
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return []
        print(f"UniProt search HTTP error: {e}", flush=True)
        return []
    except Exception as e:
        print(f"UniProt search error: {e}", flush=True)
        return []


def _get_by_accession(accession: str) -> dict:
    """按 accession 获取详情: /uniprotkb/{accession}。"""
    try:
        url = f"{_BASE}/uniprotkb/{urllib.parse.quote(accession)}?format=json"
        data = _http_get_json(url)
        return _parse_uniprot_entry(data)
    except Exception as e:
        print(f"UniProt accession error: {e}", flush=True)
        return {}


def _get_fasta(accession_or_query: str, max_results: int = 10) -> str:
    """批量获取 FASTA: /uniprotkb/stream?query={query}&format=fasta。"""
    try:
        # 判断是 accession 还是 query
        if accession_or_query.startswith(("P", "Q", "O", "A")) and len(accession_or_query) <= 10:
            # 可能是 accession，直接取
            url = f"{_BASE}/uniprotkb/{urllib.parse.quote(accession_or_query)}.fasta"
        else:
            url = (
                f"{_BASE}/uniprotkb/stream"
                f"?query={urllib.parse.quote(accession_or_query)}"
                f"&format=fasta"
                f"&size={max_results}"
            )
        return _http_get_text(url)
    except Exception as e:
        print(f"UniProt FASTA error: {e}", flush=True)
        return ""


def query_uniprot(query: str, query_type: str = "search", max_results: int = 10,
                  reviewed: bool = True) -> str:
    """查询 UniProt 蛋白质数据库。

    Args:
        query: 搜索关键词或 accession 号
        query_type: 查询类型: 'search'(搜索) / 'accession'(按ID) / 'fasta'(取序列)
        max_results: 最大返回数 (默认 10)
        reviewed: 是否只查 reviewed (Swiss-Prot) 条目 (默认 True)

    Returns:
        JSON 字符串
    """
    if query_type == "accession":
        details = _get_by_accession(query)
        if details:
            return json.dumps({
                "success": True,
                "query_type": "accession",
                "accession": query,
                "details": details,
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "success": False,
                "error": f"No UniProt entry found for accession '{query}'",
            }, ensure_ascii=False)

    elif query_type == "fasta":
        fasta = _get_fasta(query, max_results)
        if fasta:
            return json.dumps({
                "success": True,
                "query_type": "fasta",
                "query": query,
                "fasta": fasta[:10000],  # 限制返回大小
                "truncated": len(fasta) > 10000,
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "success": False,
                "error": f"No FASTA sequence found for '{query}'",
            }, ensure_ascii=False)

    else:  # search (default)
        results = _search_uniprot(query, max_results, reviewed)
        return json.dumps({
            "success": True,
            "query_type": "search",
            "query": query,
            "total": len(results),
            "proteins": results,
        }, ensure_ascii=False)


# ============ Hermes 工具注册 ============

def register(registry):
    registry.register(
        name="query_uniprot",
        toolset="memomics",
        schema={
            "name": "query_uniprot",
            "description": (
                "查询 UniProt 蛋白质数据库。支持三种模式："
                "'search' 按关键词搜索（如 'insulin human'）；"
                "'accession' 按 accession 号获取详情（如 'P01308'）；"
                "'fasta' 获取 FASTA 序列。"
                "返回蛋白名称/基因名/物种/功能/亚细胞定位/PDB结构等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword or UniProt accession (e.g. 'P01308' or 'insulin human')",
                    },
                    "query_type": {
                        "type": "string",
                        "enum": ["search", "accession", "fasta"],
                        "default": "search",
                        "description": "Query mode: search=keyword search, accession=get by ID, fasta=get sequence",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (default 10)",
                    },
                    "reviewed": {
                        "type": "boolean",
                        "default": True,
                        "description": "Only search reviewed (Swiss-Prot) entries (default true)",
                    },
                },
                "required": ["query"],
            },
        },
        handler=lambda args, **kw: query_uniprot(
            args.get("query", ""),
            query_type=args.get("query_type", "search"),
            max_results=args.get("max_results", 10),
            reviewed=args.get("reviewed", True),
        ),
        emoji="🧪",
        max_result_size_chars=50_000,
    )


# 模块加载时自动注册
try:
    from tools.registry import registry as _registry
    register(_registry)
except Exception:
    pass
