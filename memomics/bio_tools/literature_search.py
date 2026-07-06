#!/usr/bin/env python3
"""literature_search.py — 文献搜索与下载工具 (多源增强版)

支持3个文献源:
1. PubMed (NCBI E-utilities, 免费)
2. EuropePMC (免费, 覆盖更广, 含全文链接)
3. Semantic Scholar (免费 API, 含引用数)

搜索策略: PubMed → EuropePMC → (不足时) Semantic Scholar
合并去重, 相关性优先排序 (查询特异度 > 引用数)。

注册为 hermes 工具。
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path


# ============ Source 1: PubMed ============

def _search_pubmed(query: str, max_results: int = 10, sort: str = "relevance") -> list:
    """搜索 PubMed."""
    try:
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        sort_param = "pub_date" if sort == "date" else "relevance"

        search_url = f"{base}/esearch.fcgi?db=pubmed&term={urllib.parse.quote(query)}&retmax={max_results}&sort={sort_param}&retmode=json"
        req = urllib.request.Request(search_url, headers={"User-Agent": "MemOmics/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())

        id_list = data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        # esummary
        ids_str = ",".join(id_list)
        summary_url = f"{base}/esummary.fcgi?db=pubmed&id={ids_str}&retmode=json"
        req2 = urllib.request.Request(summary_url, headers={"User-Agent": "MemOmics/1.0"})
        with urllib.request.urlopen(req2, timeout=20) as resp:
            summary_data = json.loads(resp.read())

        # efetch abstracts
        try:
            abstract_url = f"{base}/efetch.fcgi?db=pubmed&id={ids_str}&rettype=abstract&retmode=text"
            req3 = urllib.request.Request(abstract_url, headers={"User-Agent": "MemOmics/1.0"})
            with urllib.request.urlopen(req3, timeout=20) as resp:
                abstract_text = resp.read().decode("utf-8", errors="replace")
            abstracts = _parse_pubmed_abstracts(abstract_text)
        except Exception:
            abstracts = {}

        papers = []
        result = summary_data.get("result", {})
        for pmid in id_list:
            info = result.get(pmid, {})
            authors = [a.get("name", "") for a in info.get("authors", [])[:5]]
            doi = ""
            for d in info.get("articleids", []):
                if d.get("idtype") == "doi":
                    doi = d.get("value", "")
            papers.append({
                "pmid": pmid,
                "title": info.get("title", "").rstrip("."),
                "authors": authors,
                "journal": info.get("fulljournalname", info.get("source", "")),
                "year": info.get("pubdate", "")[:4],
                "doi": doi,
                "abstract": abstracts.get(pmid, "")[:800],
                "source": "pubmed",
                "citations": 0,
            })
        return papers
    except Exception as e:
        print(f"PubMed search error: {e}", file=sys.stderr)
        return []


def _parse_pubmed_abstracts(text: str) -> dict:
    """解析 PubMed efetch 返回的摘要文本."""
    abstracts = {}
    current_pmid = None
    current_lines = []
    for line in text.split("\n"):
        if line.strip().isdigit():
            if current_pmid and current_lines:
                abstracts[current_pmid] = " ".join(current_lines).strip()
            current_pmid = line.strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_pmid and current_lines:
        abstracts[current_pmid] = " ".join(current_lines).strip()
    return abstracts


# ============ Source 2: EuropePMC ============

def _search_europepmc(query: str, max_results: int = 10) -> list:
    """搜索 EuropePMC (覆盖更广, 含 preprints)."""
    try:
        encoded_q = urllib.parse.quote(query)
        # 默认相关性排序 (RELEVANCE), 不用 CITED desc 否则全是高引经典文献
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={encoded_q}&format=json&pageSize={max_results}&sort=RELEVANCE"
        req = urllib.request.Request(url, headers={"User-Agent": "MemOmics/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())

        papers = []
        for item in data.get("resultList", {}).get("result", []):
            pmid = item.get("pmid", "")
            pmcid = item.get("pmcid", "")
            doi = item.get("doi", "")
            authors = item.get("authorString", "").split(", ")[:5] if item.get("authorString") else []

            # 构建全文 PDF URL (如果有 PMC 全文)
            fulltext_url = ""
            if pmcid:
                fulltext_url = f"https://europepmc.org/articles/{pmcid}"

            papers.append({
                "pmid": pmid,
                "title": item.get("title", "").rstrip("."),
                "authors": authors,
                "journal": item.get("journalTitle", ""),
                "year": item.get("pubYear", ""),
                "doi": doi,
                "abstract": item.get("abstractText", "")[:800] if item.get("abstractText") else "",
                "source": "europepmc",
                "citations": int(item.get("citedByCount", 0) or 0),
                "pmcid": pmcid,
                "fulltext_url": fulltext_url,
            })
        return papers
    except Exception as e:
        print(f"EuropePMC search error: {e}", file=sys.stderr)
        return []


# ============ Source 3: Semantic Scholar ============

def _search_semantic_scholar(query: str, max_results: int = 10) -> list:
    """搜索 Semantic Scholar (含引用数). 429 限流时直接返回空, 不拖慢."""
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(query)}&limit={max_results}&fields=title,authors,year,abstract,citationCount,journal,externalIds,openAccessPdf"
        req = urllib.request.Request(url, headers={"User-Agent": "MemOmics/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code != 429:  # 429 限流很常见, 静默跳过
            print(f"Semantic Scholar search error: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Semantic Scholar search error: {e}", file=sys.stderr)
        return []

    papers = []
    for item in data.get("data", []):
        ext_ids = item.get("externalIds", {}) or {}
        journal = item.get("journal", {}) or {}
        authors = [a.get("name", "") for a in item.get("authors", [])[:5]]
        oap = item.get("openAccessPdf", {}) or {}

        papers.append({
            "pmid": ext_ids.get("PubMed", ""),
            "title": item.get("title", "").rstrip("."),
            "authors": authors,
            "journal": journal.get("name", ""),
            "year": str(item.get("year", "")),
            "doi": ext_ids.get("DOI", ""),
            "abstract": (item.get("abstract") or "")[:800],
            "source": "semantic_scholar",
            "citations": int(item.get("citationCount", 0) or 0),
            "pdf_url": oap.get("url", ""),
        })
    return papers


# ============ 统一搜索接口 ============

def search_papers(query: str, max_results: int = 10, sort: str = "relevance") -> str:
    """多源文献搜索.

    策略: PubMed → EuropePMC → Semantic Scholar, 合并去重。
    默认返回 15-30 篇 (3个源各搜 max_results).

    Args:
        query: 搜索关键词
        max_results: 每个源最多返回数量
        sort: relevance / date / citations
    """
    all_papers = []

    # Source 1: PubMed
    pubmed = _search_pubmed(query, max_results, "relevance")
    all_papers.extend(pubmed)

    # Source 2: EuropePMC
    europepmc = _search_europepmc(query, max_results)
    all_papers.extend(europepmc)

    # 去重 (按 title 模糊匹配)
    seen_titles = set()
    deduped = []
    for p in all_papers:
        title_key = p["title"].lower().strip()[:60]
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            deduped.append(p)

    # Source 3: Semantic Scholar (仅当 PubMed+EuropePMC 不足时才查, 避免限流拖慢)
    semantic = []
    if len(deduped) < max_results * 2:
        semantic = _search_semantic_scholar(query, max_results)
        for p in semantic:
            title_key = p["title"].lower().strip()[:60]
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                deduped.append(p)

    # 排序
    if sort == "citations":
        deduped.sort(key=lambda x: x.get("citations", 0), reverse=True)
    elif sort == "date":
        deduped.sort(key=lambda x: x.get("year", "0"), reverse=True)
    else:
        # relevance: PubMed 优先, 然后按引用数
        deduped.sort(key=lambda x: (x.get("citations", 0) + (100 if x["source"] == "pubmed" else 0)), reverse=True)

    return json.dumps({
        "success": True,
        "total": len(deduped),
        "papers": deduped[:max_results * 2],  # 返回最多 2x
        "sources": {
            "pubmed": len(pubmed),
            "europepmc": len(europepmc),
            "semantic_scholar": len(semantic),
        }
    }, ensure_ascii=False)


def search_papers_by_context(species: str, tissue: str, direction: str, assay: str = "", max_per_query: int = 5) -> str:
    """根据分析上下文智能搜索文献.

    自动构造多个查询, 覆盖生物学+生信两个角度:

    Args:
        species: 物种 (如 Homo sapiens / human)
        tissue: 组织 (如 skeletal muscle)
        direction: 方向 (如 aging)
        assay: 测序方法 (如 RNA / ATAC / spatial / bulk)
        max_per_query: 每个查询最多返回数

    Returns:
        JSON: {success, papers, query_count, summary}
    """
    # 物种别名
    species_map = {"homo sapiens": "human", "mus musculus": "mouse", "rattus norvegicus": "rat",
                   "danio rerio": "zebrafish", "macaca mulatta": "macaque", "monkey": "macaque"}
    sp = species_map.get(species.lower(), species)

    # 构造查询组
    queries = []

    # 生物学文献: species + tissue + direction
    if direction:
        queries.append(f"{sp} {tissue} {direction} biology")
    # 生信文献: species + tissue + direction + assay
    if assay:
        assay_term = {"RNA": "single cell RNA-seq", "ATAC": "ATAC-seq", "spatial": "spatial transcriptomics",
                      "bulk": "bulk RNA-seq"}.get(assay.upper(), assay)
        if direction:
            queries.append(f"{sp} {tissue} {direction} {assay_term}")
        queries.append(f"{sp} {tissue} {assay_term}")
    # 通用: species + tissue
    if not assay:
        queries.append(f"{sp} {tissue} single cell")
    # 如果同方向太少, 扩展到同物种同组织其他方向
    queries.append(f"{sp} {tissue} transcriptomics")

    all_papers = []
    seen_titles = set()

    for q in queries:
        result = json.loads(search_papers(q, max_per_query))
        for p in result.get("papers", []):
            title_key = p["title"].lower().strip()[:60]
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                p["matched_query"] = q
                all_papers.append(p)

    # 相关性优先排序: 查询越靠前(越特异)的文献排越前, 同查询内按引用数排
    # matched_query_index 越小 = 越特异的查询 = 相关性越高
    for p in all_papers:
        mq = p.get("matched_query", "")
        try:
            p["_relevance"] = queries.index(mq)
        except ValueError:
            p["_relevance"] = 99
    all_papers.sort(key=lambda x: (x.get("_relevance", 99), -x.get("citations", 0)))
    # 清理临时字段
    for p in all_papers:
        p.pop("_relevance", None)

    return json.dumps({
        "success": True,
        "total": len(all_papers),
        "query_count": len(queries),
        "queries": queries,
        "papers": all_papers,
        "summary": f"搜索了 {len(queries)} 个查询, 从 PubMed/EuropePMC/Semantic Scholar 合并去重后得到 {len(all_papers)} 篇文献",
    }, ensure_ascii=False)


# ============ download_pdf ============

def download_pdf(url_or_pmid: str, output_dir: str = None) -> str:
    """下载 PDF 文件."""
    try:
        if output_dir is None:
            project_root = Path(__file__).parent.parent.parent
            output_dir = project_root / "work" / "papers"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        url = url_or_pmid
        if url_or_pmid.isdigit():
            pmc_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&db=pmc&id={url_or_pmid}&retmode=json"
            req = urllib.request.Request(pmc_url, headers={"User-Agent": "MemOmics/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            linksets = data.get("linksets", [])
            if linksets and linksets[0].get("linksetdbs"):
                pmc_id = linksets[0]["linksetdbs"][0]["links"][0]
                url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"
            else:
                return json.dumps({"success": False, "error": "No PMC full text available for this PMID"}, ensure_ascii=False)

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read()

        filename = url.split("/")[-1] or "paper.pdf"
        if not filename.endswith(".pdf"):
            filename = filename + ".pdf"
        filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)[:80]

        file_path = output_dir / filename
        with open(file_path, "wb") as f:
            f.write(content)

        return json.dumps({
            "success": True,
            "file_path": str(file_path),
            "file_size": len(content),
            "message": f"Downloaded {filename} ({len(content)//1024}KB)"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ============ extract_params_from_pdf ============

def extract_params_from_pdf(pdf_path: str, species: str = "", tissue: str = "", direction: str = "") -> str:
    """从 PDF 提取生信参数."""
    try:
        skill_script = Path(__file__).parent.parent.parent / "skills" / "literature-param-extraction" / "scripts" / "extract_pdf.py"
        if not skill_script.exists():
            return json.dumps({"success": False, "error": f"extract_pdf.py not found at {skill_script}"}, ensure_ascii=False)

        result = subprocess.run(
            [sys.executable, str(skill_script), pdf_path, "--method", "auto"],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace"
        )

        if result.returncode != 0:
            return json.dumps({"success": False, "error": result.stderr[:500]}, ensure_ascii=False)

        text = result.stdout
        return json.dumps({
            "success": True,
            "text_length": len(text),
            "text_preview": text[:3000],
            "species_hint": species,
            "tissue_hint": tissue,
            "direction_hint": direction,
            "message": "PDF extracted. Pass this text to LLM for structured parameter extraction."
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ============ Hermes 工具注册 ============

def register(registry):
    registry.register(
        name="search_papers",
        toolset="memomics",
        schema={
            "name": "search_papers",
            "description": "用关键词搜索学术文献（PubMed/Europe PMC/Semantic Scholar），返回标题/摘要/作者/年份/DOI。用于知识库无匹配时搜索文献。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keywords, e.g. 'aging skeletal muscle single cell RNA-seq human'"},
                    "max_results": {"type": "integer", "description": "Max results per source (default 10)", "default": 10},
                    "sort": {"type": "string", "enum": ["relevance", "date", "citations"], "default": "relevance"},
                },
                "required": ["query"],
            },
        },
        handler=lambda args, **kw: search_papers(
            args.get("query", ""),
            max_results=args.get("max_results", 10),
            sort=args.get("sort", "relevance"),
        ),
        emoji="🔍",
    )

    registry.register(
        name="search_papers_by_context",
        toolset="memomics",
        schema={
            "name": "search_papers_by_context",
            "description": "根据物种/组织/方向智能搜索文献（Semantic Scholar API），返回标题/摘要/作者/年份/DOI/开放PDF链接。知识库为空时调用此工具搜索文献。",
            "parameters": {
                "type": "object",
                "properties": {
                    "species": {"type": "string", "description": "Species, e.g. 'Homo sapiens' or 'human'"},
                    "tissue": {"type": "string", "description": "Tissue, e.g. 'skeletal muscle'"},
                    "direction": {"type": "string", "description": "Research direction, e.g. 'aging'"},
                    "assay": {"type": "string", "description": "Assay type: RNA/ATAC/spatial/bulk (optional)"},
                    "max_per_query": {"type": "integer", "default": 5},
                },
                "required": ["species", "tissue", "direction"],
            },
        },
        handler=lambda args, **kw: search_papers_by_context(
            args.get("species", ""),
            args.get("tissue", ""),
            args.get("direction", ""),
            assay=args.get("assay", ""),
            max_per_query=args.get("max_per_query", 5),
        ),
        emoji="📚",
    )

    registry.register(
        name="download_pdf",
        toolset="memomics",
        schema={
            "name": "download_pdf",
            "description": "下载文献 PDF 到 work/papers/ 目录。支持 PDF URL 或 PMID。下载后可用 extract_params_from_pdf 提取参数。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url_or_pmid": {"type": "string", "description": "PDF URL or PMID"},
                    "output_dir": {"type": "string", "description": "Save directory (default work/papers/)"},
                },
                "required": ["url_or_pmid"],
            },
        },
        handler=lambda args, **kw: download_pdf(
            args.get("url_or_pmid", ""),
            output_dir=args.get("output_dir"),
        ),
        emoji="📄",
    )

    registry.register(
        name="extract_params_from_pdf",
        toolset="memomics",
        schema={
            "name": "extract_params_from_pdf",
            "description": "从下载的 PDF 文献中提取生信分析参数（QC阈值/归一化/降维/聚类/DEG等），返回结构化参数。提取后由 LLM 写入知识库 memomics/knowledge_base/。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pdf_path": {"type": "string", "description": "PDF file path"},
                    "species": {"type": "string"},
                    "tissue": {"type": "string"},
                    "direction": {"type": "string"},
                },
                "required": ["pdf_path"],
            },
        },
        handler=lambda args, **kw: extract_params_from_pdf(
            args.get("pdf_path", ""),
            species=args.get("species", ""),
            tissue=args.get("tissue", ""),
            direction=args.get("direction", ""),
        ),
        emoji="📖",
    )


# 模块加载时自动注册（与 debate_analysis.py 同模式）
try:
    from tools.registry import registry as _registry
    register(_registry)
except Exception:
    pass
