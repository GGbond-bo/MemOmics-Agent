#!/usr/bin/env python3
"""query_ncbi.py — NCBI 广义数据库连接器

通用 NCBI E-utilities 接口，支持查询 NCBI 所有数据库：
  pubmed (文献), gds (GEO数据集), sra (测序数据),
  nuccore (核酸序列), protein (蛋白序列), biosample, biosystems 等

与 query_geo.py 的区别：GEO 连接器专注于 GDS/GSE 数据集的语义封装；
本连接器是通用 E-utilities 接口，通过 db 参数指定数据库。

API: NCBI E-utilities (https://eutils.ncbi.nlm.nih.gov/entrez/eutils/)
  - esearch.fcgi — 搜索
  - esummary.fcgi — 获取摘要
  - efetch.fcgi — 获取完整记录

速率限制: 无 key 时 3 次/秒，每次请求间隔 0.34s。

注册为 hermes 工具。
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error

_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_USER_AGENT = "MemOmics/1.0"
_TIMEOUT = 20
_RATE_LIMIT_DELAY = 0.34

# 常用 NCBI 数据库
_SUPPORTED_DBS = [
    "pubmed",    # 文献
    "gds",       # GEO DataSets
    "sra",       # Sequence Read Archive
    "nuccore",   # 核酸序列 (GenBank/RefSeq)
    "protein",   # 蛋白序列
    "biosample", # BioSample
    "biosystems",# BioSystems (通路/功能)
    "gene",      # Gene
    "clinvar",   # ClinVar (临床变异)
    "snp",       # dbSNP
    "taxonomy",  # Taxonomy
    "mesh",      # MeSH
]


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


def _search_ncbi(db: str, query: str, max_results: int = 10) -> list:
    """搜索 NCBI 数据库: esearch + esummary。"""
    try:
        search_url = (
            f"{_BASE}/esearch.fcgi?db={db}"
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
            f"{_BASE}/esummary.fcgi?db={db}&id={ids_str}&retmode=json"
        )
        try:
            summary_data = _http_get_json(summary_url)
        except Exception:
            # esummary 对某些 db 不支持，降级返回 id list
            return [{"uid": uid, "db": db} for uid in id_list]

        results = []
        for uid in id_list:
            doc = summary_data.get("result", {}).get(uid, {})
            if not doc:
                results.append({"uid": uid, "db": db})
                continue
            # 通用字段提取
            entry = {
                "uid": uid,
                "db": db,
                "title": doc.get("title", ""),
            }
            # 按数据库类型提取特有字段
            if db == "pubmed":
                entry["authors"] = [a.get("name", "") for a in doc.get("authors", [])[:5]]
                entry["journal"] = doc.get("fulljournalname", "")
                entry["pubdate"] = doc.get("pubdate", "")
                entry["doi"] = doc.get("elocationid", "")
            elif db == "gds":
                entry["accession"] = doc.get("accession", "")
                entry["entry_type"] = doc.get("entrytype", "")
                entry["taxon"] = doc.get("taxon", "")
                entry["n_samples"] = doc.get("n_samples", 0)
                entry["platform"] = doc.get("gpl", "")
                entry["summary"] = doc.get("summary", "")[:500]
                entry["geo_link"] = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={doc.get('accession','')}"
            elif db == "sra":
                entry["title"] = doc.get("title", "")
                entry["description"] = doc.get("description", "")[:500]
                entry["pubmed_id"] = doc.get("pubmed", "")
            elif db == "gene":
                entry["symbol"] = doc.get("name", "")
                entry["description"] = doc.get("description", "")
                entry["organism"] = doc.get("organism", {}).get("scientificname", "") if isinstance(doc.get("organism"), dict) else str(doc.get("organism", ""))
                entry["chromosome"] = doc.get("chromosome", "")
                entry["map_location"] = doc.get("maplocation", "")
            elif db == "protein" or db == "nuccore":
                entry["title"] = doc.get("title", "")
                entry["organism"] = doc.get("organism", "")
                entry["length"] = doc.get("slen", 0)
                entry["definition"] = doc.get("title", "")
            else:
                # 通用：把所有非冗余字段提取出来
                for key in ["title", "description", "name", "accession", "summary"]:
                    if key in doc and doc[key]:
                        entry[key] = doc[key] if isinstance(doc[key], str) else str(doc[key])
                        break

            results.append(entry)

        return results
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return []
        print(f"NCBI search HTTP error: {e}", flush=True)
        return []
    except Exception as e:
        print(f"NCBI search error: {e}", flush=True)
        return []


def query_ncbi(db: str, query: str, max_results: int = 10) -> str:
    """查询 NCBI 数据库（通用 E-utilities 接口）。

    Args:
        db: NCBI 数据库名，如 'pubmed'/'gds'/'sra'/'nuccore'/'protein'/'gene'/'biosystems'
        query: 搜索关键词
        max_results: 最大返回数 (默认 10)

    Returns:
        JSON 字符串: {"success": True, "total": N, "db": "...", "results": [...]}
    """
    if db not in _SUPPORTED_DBS:
        return json.dumps({
            "success": False,
            "error": f"Unsupported database '{db}'. Supported: {', '.join(_SUPPORTED_DBS)}",
        }, ensure_ascii=False)

    results = _search_ncbi(db, query, max_results)
    return json.dumps({
        "success": True,
        "db": db,
        "query": query,
        "total": len(results),
        "results": results,
    }, ensure_ascii=False)


def list_ncbi_databases() -> str:
    """列出所有支持的 NCBI 数据库。"""
    return json.dumps({
        "success": True,
        "databases": _SUPPORTED_DBS,
        "descriptions": {
            "pubmed": "Biomedical literature citations",
            "gds": "GEO DataSets (gene expression datasets)",
            "sra": "Sequence Read Archive (raw sequencing data)",
            "nuccore": "Nucleotide sequences (GenBank/RefSeq)",
            "protein": "Protein sequences",
            "biosample": "Biological sample metadata",
            "biosystems": "Biological systems (pathways/functional sets)",
            "gene": "Gene-centered information",
            "clinvar": "Clinical variation",
            "snp": "dbSNP (single nucleotide polymorphisms)",
            "taxonomy": "Taxonomy database",
            "mesh": "MeSH (Medical Subject Headings)",
        },
    }, ensure_ascii=False)


# ============ Hermes 工具注册 ============

def register(registry):
    registry.register(
        name="query_ncbi",
        toolset="memomics",
        schema={
            "name": "query_ncbi",
            "description": (
                "通用 NCBI E-utilities 查询接口，支持所有 NCBI 数据库："
                "pubmed(文献)/gds(GEO数据集)/sra(测序数据)/nuccore(核酸)/"
                "protein(蛋白)/gene(基因)/biosystems(通路)/biosample/snp/"
                "clinvar/taxonomy/mesh。"
                "用于查询 NCBI 管理的公共生物数据库。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "db": {
                        "type": "string",
                        "enum": _SUPPORTED_DBS,
                        "description": "NCBI database name: pubmed, gds, sra, nuccore, protein, gene, biosystems, biosample, clinvar, snp, taxonomy, mesh",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search keywords, e.g. 'BRCA1 human' or a specific ID/term",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (default 10)",
                    },
                },
                "required": ["db", "query"],
            },
        },
        handler=lambda args, **kw: query_ncbi(
            args.get("db", "pubmed"),
            args.get("query", ""),
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
