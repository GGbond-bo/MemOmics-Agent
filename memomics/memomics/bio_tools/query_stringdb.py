#!/usr/bin/env python3
"""query_stringdb.py — STRING 蛋白互作数据库连接器

查询 STRING 数据库中的蛋白-蛋白相互作用（PPI），支持三种模式：
1. resolve: 蛋白名称→STRING ID 映射
2. network: 获取蛋白互作网络
3. enrichment: 功能富集分析

API: STRING DB REST API (https://string-db.org/api/)
  返回 JSON 格式。

STRING score 语义:
  0      — 无互作
  1-399  — 低置信度
  400-699 — 中等置信度
  700-899 — 高置信度
  900-1000 — 最高置信度

速率限制: STRING 建议请求间隔，大批量查询建议分批。

注册为 hermes 工具。
"""

import json
import urllib.request
import urllib.parse
import urllib.error

_BASE = "https://string-db.org/api"
_USER_AGENT = "MemOmics/1.0"
_TIMEOUT = 30  # STRING 响应可能较慢


def _http_get_json(url: str) -> list:
    """发起 GET 请求并返回 JSON (STRING 通常返回 list)。"""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


def _resolve_proteins(proteins: str, species: int = 9606) -> list:
    """蛋白名称→STRING ID: json/resolve。

    Args:
        proteins: 蛋白名（逗号分隔）
        species: NCBI taxonomy ID (9606=human, 10090=mouse, 4932=yeast)
    """
    try:
        gene_list = [g.strip() for g in proteins.replace(",", " ").split() if g.strip()]
        # STRING 要求 identifiers 用 %0d (CR) 分隔
        identifiers = "%0d".join(gene_list)
        url = (
            f"{_BASE}/json/resolve"
            f"?identifiers={identifiers}"
            f"&species={species}"
            f"&limit=5"
        )
        data = _http_get_json(url)
        results = []
        for item in data:
            results.append({
                "query_item": item.get("queryItem", ""),
                "string_id": item.get("stringId", ""),
                "preferred_name": item.get("preferredName", ""),
                "annotated_name": item.get("annotation", ""),
                "ncbi_taxon_id": item.get("ncbiTaxonId", 0),
            })
        return results
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return []
        print(f"STRING resolve HTTP error: {e}", flush=True)
        return []
    except Exception as e:
        print(f"STRING resolve error: {e}", flush=True)
        return []


def _get_interactions(proteins: str, species: int = 9606, score_threshold: int = 400,
                      max_results: int = 50) -> list:
    """获取互作网络: json/network。

    Args:
        proteins: 蛋白名（逗号分隔）
        species: NCBI taxonomy ID
        score_threshold: 最低置信度分数 (默认 400=中等)
        max_results: 最大互作对数
    """
    try:
        gene_list = [g.strip() for g in proteins.replace(",", " ").split() if g.strip()]
        identifiers = "%0d".join(gene_list)
        url = (
            f"{_BASE}/json/network"
            f"?identifiers={identifiers}"
            f"&species={species}"
            f"&required_score={score_threshold}"
            f"&limit={max_results}"
        )
        data = _http_get_json(url)
        results = []
        for item in data:
            score = item.get("score", 0)
            # STRING score 是 0-1 的浮点数，乘以 1000 得到 0-1000 的整数分
            score_int = int(score * 1000) if score <= 1.0 else int(score)
            results.append({
                "protein_a": item.get("preferredName_A", ""),
                "protein_b": item.get("preferredName_B", ""),
                "string_id_a": item.get("stringId_A", ""),
                "string_id_b": item.get("stringId_B", ""),
                "score": score_int,
                "score_level": _score_level(score_int),
                "ncbi_taxon_id": item.get("ncbiTaxonId", 0),
            })
        return results
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return []
        print(f"STRING network HTTP error: {e}", flush=True)
        return []
    except Exception as e:
        print(f"STRING network error: {e}", flush=True)
        return []


def _score_level(score: int) -> str:
    """将 STRING score 转为置信度等级。"""
    if score == 0:
        return "none"
    elif score < 400:
        return "low"
    elif score < 700:
        return "medium"
    elif score < 900:
        return "high"
    else:
        return "highest"


def query_string(proteins: str, species: int = 9606, query_type: str = "network",
                 score_threshold: int = 400, max_results: int = 50) -> str:
    """查询 STRING 蛋白互作数据库。

    Args:
        proteins: 蛋白/基因名（逗号分隔），如 'TP53,MDM2,BAX'
        species: NCBI taxonomy ID (9606=human, 10090=mouse, 4932=yeast)
        query_type: 查询类型: 'resolve'(名称→ID) / 'network'(互作网络) / 'enrichment'(功能富集)
        score_threshold: 最低互作置信度 (默认 400=中等)
        max_results: 最大返回数 (默认 50)

    Returns:
        JSON 字符串
    """
    if query_type == "resolve":
        results = _resolve_proteins(proteins, species)
        return json.dumps({
            "success": True,
            "query_type": "resolve",
            "total": len(results),
            "proteins": results,
        }, ensure_ascii=False)

    elif query_type == "enrichment":
        # 功能富集分析
        try:
            gene_list = [g.strip() for g in proteins.replace(",", " ").split() if g.strip()]
            identifiers = "%0d".join(gene_list)
            url = (
                f"{_BASE}/json/enrichment"
                f"?identifiers={identifiers}"
                f"&species={species}"
            )
            data = _http_get_json(url)
            results = []
            for item in data:
                results.append({
                    "category": item.get("category", ""),
                    "term": item.get("term", ""),
                    "description": item.get("description", ""),
                    "p_value": item.get("p_value", 1.0),
                    "fdr": item.get("fdr", 1.0),
                    "genes": item.get("inputGenes", []),
                    "foreground_count": item.get("number_of_genes", 0),
                })
            return json.dumps({
                "success": True,
                "query_type": "enrichment",
                "total": len(results),
                "enrichments": results[:max_results],
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"STRING enrichment error: {e}",
            }, ensure_ascii=False)

    else:  # network (default)
        interactions = _get_interactions(proteins, species, score_threshold, max_results)
        return json.dumps({
            "success": True,
            "query_type": "network",
            "total": len(interactions),
            "proteins": proteins,
            "species": species,
            "score_threshold": score_threshold,
            "interactions": interactions,
        }, ensure_ascii=False)


# ============ Hermes 工具注册 ============

def register(registry):
    registry.register(
        name="query_string",
        toolset="memomics",
        schema={
            "name": "query_string",
            "description": (
                "查询 STRING 蛋白互作数据库。支持三种模式："
                "'resolve' 蛋白名→STRING ID 映射；"
                "'network' 获取蛋白-蛋白互作网络（返回互作对+置信度分数）；"
                "'enrichment' 功能富集分析。"
                "用于蛋白互作网络分析和功能富集。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "proteins": {
                        "type": "string",
                        "description": "Protein/gene names, comma-separated, e.g. 'TP53,MDM2,BAX'",
                    },
                    "species": {
                        "type": "integer",
                        "default": 9606,
                        "description": "NCBI taxonomy ID: 9606=human, 10090=mouse, 4932=yeast",
                    },
                    "query_type": {
                        "type": "string",
                        "enum": ["resolve", "network", "enrichment"],
                        "default": "network",
                        "description": "Query mode: resolve=name→ID, network=PPI network, enrichment=functional enrichment",
                    },
                    "score_threshold": {
                        "type": "integer",
                        "default": 400,
                        "description": "Min interaction confidence score (400=medium, 700=high, 900=highest)",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max results (default 50)",
                    },
                },
                "required": ["proteins"],
            },
        },
        handler=lambda args, **kw: query_string(
            args.get("proteins", ""),
            species=args.get("species", 9606),
            query_type=args.get("query_type", "network"),
            score_threshold=args.get("score_threshold", 400),
            max_results=args.get("max_results", 50),
        ),
        emoji="🕸️",
        max_result_size_chars=50_000,
    )


# 模块加载时自动注册
try:
    from tools.registry import registry as _registry
    register(_registry)
except Exception:
    pass
