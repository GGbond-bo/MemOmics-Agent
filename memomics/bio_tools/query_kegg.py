#!/usr/bin/env python3
"""query_kegg.py — KEGG 通路数据库连接器

查询 KEGG 通路/基因/化合物数据库，支持三种模式：
1. 搜索通路：按关键词搜索 KEGG 通路
2. 获取详情：按 pathway ID 获取通路详情
3. 基因→通路映射：查询基因列表参与的通路

API: KEGG REST API (http://rest.kegg.jp/)
  无需 API key，无需认证，返回纯文本（非 JSON）。

速率限制: 官方建议请求间隔，无需严格 sleep。

注册为 hermes 工具。
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error

_BASE = "http://rest.kegg.jp"
_USER_AGENT = "MemOmics/1.0"
_TIMEOUT = 20


def _http_get_text(url: str) -> str:
    """发起 GET 请求并返回纯文本。"""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _search_pathways(query: str, max_results: int = 10) -> list:
    """搜索 KEGG 通路: find/pathway/{query} → TSV (pathway_id \t description)。"""
    try:
        url = f"{_BASE}/find/pathway/{urllib.parse.quote(query)}"
        text = _http_get_text(url)
        results = []
        for line in text.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                pathway_id, description = parts
                results.append({
                    "pathway_id": pathway_id.strip(),
                    "description": description.strip(),
                    "kegg_link": f"https://www.kegg.jp/entry/{pathway_id.strip()}",
                })
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        print(f"KEGG search error: {e}", flush=True)
        return []


def _get_pathway_details(pathway_id: str) -> dict:
    """获取通路详情: get/{id} → 带字段的纯文本。"""
    try:
        url = f"{_BASE}/get/{urllib.parse.quote(pathway_id)}"
        text = _http_get_text(url)
        details = {"pathway_id": pathway_id, "raw": text}

        # 解析字段（KEGG 返回格式: FIELD  value）
        current_field = None
        current_value = []
        for line in text.split("\n"):
            if line.startswith("            "):
                # 续行
                current_value.append(line.strip())
            elif line and not line.startswith(" "):
                if current_field:
                    details[current_field.lower().replace(" ", "_")] = " ".join(current_value)
                parts = line.split(None, 1)
                current_field = parts[0] if parts else None
                current_value = [parts[1]] if len(parts) > 1 else []
            else:
                current_value.append(line.strip())
        if current_field:
            details[current_field.lower().replace(" ", "_")] = " ".join(current_value)

        # 提取常用字段
        details["kegg_link"] = f"https://www.kegg.jp/entry/{pathway_id}"
        return details
    except Exception as e:
        print(f"KEGG detail error: {e}", flush=True)
        return {"pathway_id": pathway_id, "error": str(e)}


def _resolve_gene_symbols(gene_list: list, organism: str = "hsa") -> dict:
    """基因符号→KEGG gene ID 映射: find/{organism}/{symbol}。

    KEGG link API 需要 KEGG gene ID（organism:entrez_id），不接受基因符号。
    用 find 端点做符号→KEGG ID 映射。
    """
    try:
        resolved = {}
        for sym in gene_list:
            try:
                url = f"{_BASE}/find/{organism}/{urllib.parse.quote(sym)}"
                text = _http_get_text(url)
                # find 返回 TSV: gene_id \t description
                for line in text.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        gene_id = parts[0].strip()  # e.g. hsa:7157
                        desc = parts[1].strip()
                        # 确认匹配：描述里应包含基因符号
                        if sym.upper() in desc.upper():
                            resolved[sym] = gene_id
                            break
            except Exception:
                continue
            time.sleep(0.1)  # KEGG 速率限制
        return resolved
    except Exception as e:
        print(f"KEGG gene resolve error: {e}", flush=True)
        return {}


def _genes_to_pathways(genes: str, organism: str = "hsa") -> list:
    """基因→通路映射: link/pathway/{organism}:{gene1 organism}:{gene2...}。

    Args:
        genes: 逗号或空格分隔的基因名（基因符号或 Entrez ID）
        organism: KEGG organism code (如 hsa=human, mmu=mouse)

    Note: KEGG link API 需要 KEGG gene ID（格式 organism:entrez_id），
    不接受基因符号。本函数会先尝试用 find 端点把符号解析为 KEGG ID。
    如果传入的已经是纯数字 Entrez ID，直接用 organism:{id} 格式。
    """
    try:
        gene_list = [g.strip() for g in genes.replace(",", " ").split() if g.strip()]
        if not gene_list:
            return []

        # 区分纯数字（Entrez ID）和符号
        kegg_ids = []
        symbols = []
        for g in gene_list:
            if g.isdigit():
                kegg_ids.append(f"{organism}:{g}")
            else:
                symbols.append(g)

        # 解析符号→KEGG ID
        if symbols:
            resolved = _resolve_gene_symbols(symbols, organism)
            for sym in symbols:
                if sym in resolved:
                    kegg_ids.append(resolved[sym])
                else:
                    # 回退：直接尝试用符号（某些 organism 可能支持）
                    kegg_ids.append(f"{organism}:{sym}")

        if not kegg_ids:
            return []

        # 构建 identifiers: hsa:7157+hsa:4193
        identifiers = "+".join(kegg_ids)
        url = f"{_BASE}/link/pathway/{identifiers}"
        text = _http_get_text(url)

        # 解析 TSV: gene_id \t pathway_id
        pathway_map = {}  # pathway_id → [genes]
        for line in text.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                gene_id, pathway_id = parts[0].strip(), parts[1].strip()
                gene_name = gene_id.split(":")[-1] if ":" in gene_id else gene_id
                if pathway_id not in pathway_map:
                    pathway_map[pathway_id] = {
                        "pathway_id": pathway_id,
                        "genes": [],
                        "kegg_link": f"https://www.kegg.jp/entry/{pathway_id}",
                    }
                if gene_name not in pathway_map[pathway_id]["genes"]:
                    pathway_map[pathway_id]["genes"].append(gene_name)

        return list(pathway_map.values())
    except Exception as e:
        print(f"KEGG genes→pathway error: {e}", flush=True)
        return []


def query_kegg(query: str, query_type: str = "pathway", max_results: int = 10,
               organism: str = "hsa") -> str:
    """查询 KEGG 数据库。

    Args:
        query: 搜索关键词、通路 ID 或基因列表
        query_type: 查询类型: 'pathway'(搜索通路) / 'details'(获取详情) / 'genes'(基因→通路映射)
        max_results: 最大返回数 (默认 10)
        organism: KEGG 物种代码 (默认 'hsa'=human)，仅在 genes 模式下使用

    Returns:
        JSON 字符串
    """
    if query_type == "details":
        details = _get_pathway_details(query)
        return json.dumps({
            "success": True,
            "query_type": "details",
            "details": details,
        }, ensure_ascii=False)

    elif query_type == "genes":
        pathways = _genes_to_pathways(query, organism)
        return json.dumps({
            "success": True,
            "query_type": "genes",
            "query": query,
            "organism": organism,
            "total": len(pathways),
            "pathways": pathways[:max_results],
        }, ensure_ascii=False)

    else:  # pathway search (default)
        pathways = _search_pathways(query, max_results)
        return json.dumps({
            "success": True,
            "query_type": "pathway",
            "query": query,
            "total": len(pathways),
            "pathways": pathways,
        }, ensure_ascii=False)


# ============ Hermes 工具注册 ============

def register(registry):
    registry.register(
        name="query_kegg",
        toolset="memomics",
        schema={
            "name": "query_kegg",
            "description": (
                "查询 KEGG 通路数据库。支持三种模式："
                "'pathway' 按关键词搜索通路（如 'apoptosis'）；"
                "'details' 按通路ID获取详情（如 'hsa04210'）；"
                "'genes' 查基因列表参与的通路（基因名逗号分隔）。"
                "用于通路富集分析和通路信息查询。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword, pathway ID, or gene list (comma/space separated)",
                    },
                    "query_type": {
                        "type": "string",
                        "enum": ["pathway", "details", "genes"],
                        "default": "pathway",
                        "description": "Query mode: pathway=search, details=get by ID, genes=gene→pathway mapping",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (default 10)",
                    },
                    "organism": {
                        "type": "string",
                        "default": "hsa",
                        "description": "KEGG organism code (hsa=human, mmu=mouse, etc.), only for genes mode",
                    },
                },
                "required": ["query"],
            },
        },
        handler=lambda args, **kw: query_kegg(
            args.get("query", ""),
            query_type=args.get("query_type", "pathway"),
            max_results=args.get("max_results", 10),
            organism=args.get("organism", "hsa"),
        ),
        emoji="🛤️",
        max_result_size_chars=50_000,
    )


# 模块加载时自动注册
try:
    from tools.registry import registry as _registry
    register(_registry)
except Exception:
    pass
