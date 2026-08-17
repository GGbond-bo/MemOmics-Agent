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

import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import subprocess
from datetime import datetime
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
    """搜索 EuropePMC (覆盖更广, 含 preprints).

    注意: sort=RELEVANCE 参数会导致 API 返回 0 条结果 (API bug), 不传 sort 参数即可。
    """
    try:
        encoded_q = urllib.parse.quote(query)
        # 不传 sort 参数 (传 sort=RELEVANCE 会导致 0 结果)
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={encoded_q}&format=json&pageSize={max_results}"
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
            pdf_url = ""
            if pmcid:
                # EuropePMC ?pdf=render 是最可靠的 OA PDF 源
                fulltext_url = f"https://europepmc.org/articles/{pmcid}"
                pdf_url = f"https://europepmc.org/articles/{pmcid}?pdf=render"

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
                "pdf_url": pdf_url,
            })
        return papers
    except Exception as e:
        print(f"EuropePMC search error: {e}", file=sys.stderr)
        return []


# ============ Source 3: Semantic Scholar ============

def _search_semantic_scholar(query: str, max_results: int = 10) -> list:
    """搜索 Semantic Scholar (含引用数). 429 限流时等待重试1次."""
    import urllib.error
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(query)}&limit={max_results}&fields=title,authors,year,abstract,citationCount,journal,externalIds,openAccessPdf"
    req = urllib.request.Request(url, headers={"User-Agent": "MemOmics/1.0"})

    for attempt in range(2):  # 最多尝试2次
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(2)  # 429 限流，等待2秒重试
                continue
            if e.code != 429:
                print(f"Semantic Scholar search error: {e}", file=sys.stderr)
            return []
        except Exception as e:
            print(f"Semantic Scholar search error: {e}", file=sys.stderr)
            return []
    else:
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

def _merge_and_dedup(papers: list) -> list:
    """合并去重，保留有 URL 的版本。

    去重策略：按 title 前60字符去重，但优先保留带 pdf_url/fulltext_url/pmcid 的版本。
    这样 EuropePMC/Semantic Scholar 的 URL 信息不会因 PubMed 先入而被丢弃。
    """
    seen = {}  # title_key -> paper
    for p in papers:
        title_key = p["title"].lower().strip()[:60]
        if not title_key:
            continue
        if title_key not in seen:
            seen[title_key] = p
        else:
            # 已存在，合并字段：保留非空字段
            existing = seen[title_key]
            for field in ["pdf_url", "fulltext_url", "pmcid", "doi", "citations", "abstract"]:
                if not existing.get(field) and p.get(field):
                    existing[field] = p[field]
            # 如果新版本有 URL 但旧版本没有，用新版本
            new_has_url = bool(p.get("pdf_url") or p.get("fulltext_url"))
            old_has_url = bool(existing.get("pdf_url") or existing.get("fulltext_url"))
            if new_has_url and not old_has_url:
                # 保留 existing 的字段，但用 p 作为基础
                for field in ["pdf_url", "fulltext_url", "pmcid"]:
                    if p.get(field):
                        existing[field] = p[field]
    return list(seen.values())


def search_papers(query: str, max_results: int = 10, sort: str = "relevance") -> str:
    """多源文献搜索.

    策略: PubMed → EuropePMC → Semantic Scholar, 合并去重。
    去重时优先保留带 pdf_url/fulltext_url 的版本。
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

    # 合并去重（保留 URL 版本）
    deduped = _merge_and_dedup(all_papers)

    # Source 3: Semantic Scholar (仅当不足时才查, 避免限流拖慢)
    semantic = []
    if len(deduped) < max_results * 2:
        semantic = _search_semantic_scholar(query, max_results)
        if semantic:
            deduped = _merge_and_dedup(deduped + semantic)

    # 排序
    if sort == "citations":
        deduped.sort(key=lambda x: x.get("citations", 0), reverse=True)
    elif sort == "date":
        deduped.sort(key=lambda x: x.get("year", "0"), reverse=True)
    else:
        # relevance: 有URL的优先，然后按引用数
        deduped.sort(key=lambda x: (x.get("citations", 0) + (100 if x["source"] == "pubmed" else 0) + (50 if x.get("pdf_url") or x.get("fulltext_url") else 0)), reverse=True)

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

def _unpaywall_lookup(doi: str) -> str:
    """通过 Unpaywall API 查找开放获取 PDF URL."""
    try:
        url = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email=memomics@research.org"
        # 优先 httpx
        try:
            import httpx
            with httpx.Client(timeout=15) as client:
                resp = client.get(url)
                data = resp.json()
        except Exception:
            req = urllib.request.Request(url, headers={"User-Agent": "MemOmics/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        # 优先选 best_oa_location 的 pdf_url
        best = data.get("best_oa_location", {}) or {}
        if best.get("url_for_pdf"):
            return best["url_for_pdf"]
        # 回退到任意 oa location
        for loc in data.get("oa_locations", []) or []:
            if loc.get("url_for_pdf"):
                return loc["url_for_pdf"]
        # 最后回退到 landing page
        if best.get("url_for_landing_page"):
            return best["url_for_landing_page"]
        return ""
    except Exception:
        return ""


def _doi_to_pmcid(doi: str) -> str:
    """用 DOI 查 PMC ID (通过 EuropePMC API)。"""
    try:
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{urllib.parse.quote(doi)}&format=json&pageSize=1"
        req = urllib.request.Request(url, headers={"User-Agent": "MemOmics/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = data.get("resultList", {}).get("result", [])
        if results:
            pmcid = results[0].get("pmcid", "")
            if pmcid:
                return pmcid
        return ""
    except Exception:
        return ""


def _doi_to_pdf_urls(doi: str) -> list:
    """用 DOI 尝试多个来源获取 PDF URL（强制下载）。

    优先级：
    1. EuropePMC ?pdf=render（最可靠的 OA PDF 源）
    2. Unpaywall OA URL
    3. DOI 直接解析（会跳转到出版商页面）
    """
    urls = []
    # 1. EuropePMC ?pdf=render（最可靠）
    pmcid = _doi_to_pmcid(doi)
    if pmcid:
        urls.append(("europepmc_pdf_render", f"https://europepmc.org/articles/{pmcid}?pdf=render"))
    # 2. Unpaywall（最可靠的 OA 查找）
    upw = _unpaywall_lookup(doi)
    if upw:
        urls.append(("unpaywall", upw))
    # 3. DOI 直接解析（会跳转到出版商页面）
    urls.append(("doi_redirect", f"https://doi.org/{doi}"))
    return urls


def _download_url_to_file(url: str, output_dir: Path, filename_hint: str = "") -> dict:
    """下载 URL 到文件，返回结果 dict。

    下载策略（逐级升级）：
    1. httpx — 快速 HTTP，能处理大部分开放文献（Nature、EuropePMC 等）
    2. urllib — httpx 失败时的回退
    3. Scrapling StealthyFetcher — 无头浏览器 + Cloudflare 绕过，用于反爬保护严格的网站
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    content = None
    sf_error = None  # Scrapling 状态跟踪（预定义，避免未定义引用）
    # 策略1: httpx (快速 HTTP)
    try:
        import httpx
        with httpx.Client(headers=headers, follow_redirects=True, timeout=60) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                content = resp.content
    except Exception:
        pass

    # 策略2: urllib 回退
    if content is None:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                content = resp.read()
        except Exception:
            pass  # 继续到策略3

    # 检查 httpx/urllib 结果是否为有效 PDF
    is_pdf = content is not None and content[:5] == b"%PDF-"

    # 策略3: Scrapling StealthyFetcher — 仅当 httpx/urllib 失败或返回非 PDF 时
    if not is_pdf:
        sf_error = None
        try:
            from scrapling.fetchers import StealthyFetcher
        except ImportError:
            sf_error = "Scrapling not installed (pip install scrapling[fetchers])"
        if sf_error is None:
            try:
                page = StealthyFetcher.fetch(url, headless=True, solve_cloudflare=True, network_idle=True)
                sf_content = page.body if hasattr(page, "body") else b""
                if sf_content and sf_content[:5] == b"%PDF-":
                    content = sf_content
                    is_pdf = True
                else:
                    sf_error = f"Scrapling returned non-PDF (status={getattr(page, 'status', '?')}, size={len(sf_content)})"
            except Exception as e:
                sf_error = f"Scrapling error: {str(e)[:120]}"
        # 记录 Scrapling 状态到结果中（不静默吞掉）
        if not is_pdf and sf_error:
            import sys
            print(f"[literature_search] Scrapling fallback: {sf_error}", file=sys.stderr)

    if not content:
        return {"success": False, "error": "All download methods failed (httpx + urllib + scrapling)", "scrapling_status": sf_error or "not attempted"}

    # 如果仍然不是 PDF，检查是否是 HTML 页面包含 PDF 链接
    if not is_pdf:
        if b"<html" in content[:500].lower() or b"<!DOCTYPE" in content[:500].lower():
            html = content.decode("utf-8", errors="replace")
            import re
            pdf_links = re.findall(r'href=["\']([^"\'>]+\.pdf[^"\'>]*)["\']', html, re.IGNORECASE)
            if pdf_links:
                pdf_url = pdf_links[0]
                if not pdf_url.startswith("http"):
                    from urllib.parse import urljoin
                    pdf_url = urljoin(url, pdf_url)
                return _download_url_to_file(pdf_url, output_dir, filename_hint)
            # 反爬验证页面
            if len(content) < 5000 and ("cloudflare" in html.lower() or "captcha" in html.lower() or "javascript" in html.lower()):
                return {"success": False, "error": f"Anti-bot protection (size={len(content)}, Cloudflare/JS check). Scrapling status: {sf_error or 'tried but failed'}"}
        return {"success": False, "error": f"Not PDF after all strategies (size={len(content)}, first bytes={content[:20]}). Scrapling status: {sf_error or 'N/A'}"}

    # 生成文件名
    if filename_hint:
        filename = filename_hint
    else:
        filename = url.split("/")[-1] or "paper.pdf"
    if not filename.endswith(".pdf"):
        filename = filename + ".pdf"
    filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)[:80]

    file_path = output_dir / filename
    with open(file_path, "wb") as f:
        f.write(content)

    return {
        "success": True,
        "file_path": str(file_path),
        "file_size": len(content),
        "message": f"Downloaded {filename} ({len(content)//1024}KB)"
    }


# ============ PDF 索引（批 C：文献库闭环） ============

def _sha256_of(file_path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()


def _index_downloaded_pdf(result: dict, output_dir: Path, doi: str, source_url: str) -> dict:
    """把下载成功的 PDF 写入索引（.pdf_index.json），并可选收录进引用库。

    - 索引文件与 PDF 同目录，记录 doi/来源 URL/大小/sha256/时间 → 支撑溯源与查重
    - 若会话结果目录可用，同时调用 save_reference 收录为 BibTeX/RIS 条目
    - 任何一步失败不影响下载结果本身
    """
    fp = result.get("file_path", "")
    entry = {
        "file": os.path.basename(fp),
        "path": fp,
        "doi": doi or "",
        "source_url": source_url or "",
        "size": result.get("file_size", 0),
        "sha256": _sha256_of(fp) if fp else "",
        "downloaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    index_file = output_dir / ".pdf_index.json"
    try:
        entries = []
        if index_file.is_file():
            try:
                entries = json.loads(index_file.read_text(encoding="utf-8"))
            except Exception:
                entries = []
        # 同文件去重（按 sha256 或文件名）
        if not any(e.get("sha256") and e["sha256"] == entry["sha256"] or e.get("file") == entry["file"] for e in entries):
            entries.append(entry)
        index_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        result["indexed"] = True
        result["index_file"] = str(index_file)
        result["sha256"] = entry["sha256"]
    except Exception as e:
        result["indexed"] = False
        result["index_error"] = str(e)[:200]

    # 引用库收录（会话级）
    if doi or source_url:
        try:
            from memomics.bio_tools.reference_library import save_reference
            meta = {
                "title": (doi or os.path.splitext(entry["file"])[0]).replace("_", " "),
                "doi": doi or "",
                "url": source_url or "",
                "entry_type": "article",
                "note": f"local_pdf: {fp}",
            }
            r = json.loads(save_reference("add", meta))
            result["reference_library"] = {"added": r.get("added"), "library": r.get("library"),
                                           "bibtex_key": r.get("bibtex_key")}
        except Exception:
            result["reference_library"] = None
    return result


def _auto_import_to_library(fp: str) -> dict:
    """下载成功后自动正式入库（批O5f 2026-08-16）。

    用户要求"下载即正式入库"：不再只是 work/papers 索引合并显示，而是走
    import_pdfs 完整链路——复制进 hermes_home/papers/ + Crossref 元数据反查 +
    去重 + 引用库注册。失败不影响下载结果本身（调用方保留下载索引兜底显示）。
    """
    try:
        from memomics.bio_tools.literature_library import import_pdfs
        r = json.loads(import_pdfs([fp], imported_by="download_pdf"))
        return {"ok": bool(r.get("ok")), "imported": int(r.get("imported") or 0),
                "skipped": int(r.get("skipped") or 0),
                "entries": r.get("entries") or [],
                "library_dir": r.get("library_dir", ""),
                "error": r.get("error", "")}
    except Exception as e:
        return {"ok": False, "imported": 0, "skipped": 0, "entries": [],
                "library_dir": "", "error": str(e)[:200]}


def _drop_agent_index_entry(fp: str):
    """正式入库成功后，从下载目录 .pdf_index.json 摘除该条目（防文献库双份显示）。

    按 sha256（非空时）或文件名匹配；摘除失败静默——list_library 侧还有
    跨库去重兜底（批O5f）。
    """
    try:
        idx_file = Path(fp).parent / ".pdf_index.json"
        if not idx_file.is_file():
            return
        try:
            entries = json.loads(idx_file.read_text(encoding="utf-8"))
        except Exception:
            return
        sha = _sha256_of(fp)
        base = os.path.basename(fp)
        keep = [e for e in entries
                if not ((sha and e.get("sha256") == sha) or e.get("file") == base)]
        if len(keep) != len(entries):
            idx_file.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _finish_download(result: dict, output_dir: Path, doi: str, source_url: str) -> str:
    """成功返回前的统一收尾：PDF 索引 + 引用库收录 + 自动入全局文献库（批O5f）。"""
    try:
        result = _index_downloaded_pdf(result, output_dir, doi, source_url)
    except Exception:
        pass
    fp = (result.get("file_path") or "").strip()
    if fp and os.path.isfile(fp):
        ai = _auto_import_to_library(fp)
        result["auto_import"] = ai
        if ai.get("ok") and (ai.get("imported") or ai.get("skipped")):
            _drop_agent_index_entry(fp)
    return json.dumps(result, ensure_ascii=False)


def download_pdf(url_or_pmid: str, output_dir: str = None, doi: str = "") -> str:
    """下载文献 PDF 到 work/papers/ 目录。强制多源尝试。

    下载成功后自动正式入库：复制到全局文献库 hermes_home/papers/ 并做
    Crossref 元数据反查（标题/期刊/作者/年份/卷期页码）+ 去重 + 引用库注册，
    无需再手动导入。入库失败时兜底：仍写 work/papers/.pdf_index.json，文献库
    照常显示（可后续点"补全元数据"）。

    下载策略（按优先级依次尝试）：
    1. 如果传入的是 PDF URL → 直接下载
    2. 如果传入的是 PMID → 查 PMC 全文 → 下载
    3. 如果有 DOI → 查 Unpaywall → 下载
    4. 如果有 DOI → DOI 直接解析 → 下载
    """
    try:
        if output_dir is None:
            project_root = Path(__file__).parent.parent.parent
            output_dir = project_root / "work" / "papers"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        attempts = []  # 记录每次尝试的结果
        url = url_or_pmid.strip()

        # 策略1: 直接 URL
        if url.startswith("http"):
            result = _download_url_to_file(url, output_dir)
            if result.get("success"):
                return _finish_download(result, output_dir, doi, url)
            attempts.append({
                "strategy": "direct_url",
                "result": result.get("error", ""),
                "scrapling_status": result.get("scrapling_status", ""),
            })

        # 策略2: PMID → PMC 全文
        if url.isdigit() or (url.startswith("PMID") and url[4:].strip().isdigit()):
            pmid = url.replace("PMID", "").strip()
            try:
                pmc_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&db=pmc&id={pmid}&retmode=json"
                req = urllib.request.Request(pmc_url, headers={"User-Agent": "MemOmics/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                linksets = data.get("linksets", [])
                if linksets and linksets[0].get("linksetdbs"):
                    pmc_id = linksets[0]["linksetdbs"][0]["links"][0]
                    pmc_pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"
                    result = _download_url_to_file(pmc_pdf_url, output_dir, filename_hint=f"PMID_{pmid}.pdf")
                    if result.get("success"):
                        return _finish_download(result, output_dir, doi, pmc_pdf_url)
                    attempts.append({
                        "strategy": "pmc_fulltext",
                        "result": result.get("error", ""),
                        "scrapling_status": result.get("scrapling_status", ""),
                    })
                else:
                    attempts.append({"strategy": "pmc_fulltext", "result": "No PMC full text"})
            except Exception as e:
                attempts.append({"strategy": "pmc_fulltext", "result": str(e)})

        # 策略3: DOI → 多源 PDF URL
        if doi:
            for source, pdf_url in _doi_to_pdf_urls(doi):
                result = _download_url_to_file(pdf_url, output_dir, filename_hint=f"{doi.replace('/', '_')}.pdf")
                if result.get("success"):
                    return _finish_download(result, output_dir, doi, pdf_url)
                attempts.append({
                    "strategy": source,
                    "result": result.get("error", ""),
                    "scrapling_status": result.get("scrapling_status", ""),
                })

        # 策略4: 如果 url_or_pmid 看起来像 DOI (含 /)
        if "/" in url and not url.startswith("http"):
            for source, pdf_url in _doi_to_pdf_urls(url):
                result = _download_url_to_file(pdf_url, output_dir, filename_hint=f"{url.replace('/', '_')}.pdf")
                if result.get("success"):
                    return _finish_download(result, output_dir, doi, pdf_url)
                attempts.append({
                    "strategy": source,
                    "result": result.get("error", ""),
                    "scrapling_status": result.get("scrapling_status", ""),
                })

        # 所有策略都失败
        return json.dumps({
            "success": False,
            "error": "All download strategies failed",
            "attempts": attempts,
            "output_dir": str(output_dir),
            "hint": "可以手动下载 PDF 放到 work/papers/ 目录，然后用 extract_params_from_pdf 提取参数"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ============ extract_params_from_pdf ============

def _find_extract_pdf_script() -> Path:
    """动态定位 literature-param-extraction skill 的 extract_pdf.py。

    运行环境不同（顶层 hermes_home / memomics 包内副本 / HERMES_HOME env），
    静态相对路径会失效，这里按候选顺序探测。
    """
    here = Path(__file__).resolve().parent  # .../memomics/bio_tools
    candidates = []
    # 1. 顶层 hermes_home skills（标准运行环境）
    candidates.append(here.parent.parent / "hermes_home" / "skills" / "bioinformatics" / "literature-param-extraction" / "scripts" / "extract_pdf.py")
    # 2. 包内 hermes_home 副本（memomics/hermes_home）
    candidates.append(here.parent / "hermes_home" / "skills" / "bioinformatics" / "literature-param-extraction" / "scripts" / "extract_pdf.py")
    # 3. 旧静态路径（源码树根 skills，保留兼容）
    candidates.append(here.parent.parent / "skills" / "literature-param-extraction" / "scripts" / "extract_pdf.py")
    # 4. HERMES_HOME 环境变量
    _hh = os.environ.get("HERMES_HOME")
    if _hh:
        candidates.append(Path(_hh) / "skills" / "bioinformatics" / "literature-param-extraction" / "scripts" / "extract_pdf.py")
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


def extract_params_from_pdf(pdf_path: str, species: str = "", tissue: str = "", direction: str = "") -> str:
    """从 PDF 提取生信参数（2026-08-14 升级：章节级拆分 + 参数对提示）。

    修复: 旧版只回传 text_preview[:3000]，Methods 参数基本丢失。
    现在: 调用 extract_pdf.py --sections，按章节预算返回（Methods 30K +
    其余各 4K），并附确定性抓取的参数对提示（参数→值→出处句）。
    """
    try:
        skill_script = _find_extract_pdf_script()
        if not skill_script.exists():
            return json.dumps({"success": False, "error": f"extract_pdf.py not found at {skill_script}"}, ensure_ascii=False)

        result = subprocess.run(
            [sys.executable, str(skill_script), pdf_path, "--method", "auto", "--sections"],
            capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        )

        if result.returncode != 0:
            return json.dumps({"success": False, "error": result.stderr[:500]}, ensure_ascii=False)

        structured = None
        try:
            # 某些 pymupdf 版本向 stdout 打弃用警告 → 从首个 '{' 起解析 JSON
            _stdout = result.stdout or ""
            _idx = _stdout.find("{")
            if _idx >= 0:
                structured = json.loads(_stdout[_idx:])
        except Exception:
            structured = None

        if isinstance(structured, dict) and "sections" in structured:
            # 章节预算: Methods 小节优先完整，其余章节各 4K
            _sections_out = []
            _methods_budget = 30000
            for s in structured.get("sections", []):
                _title = str(s.get("title", ""))
                _text = str(s.get("text", ""))
                if _title.lower().startswith("methods"):
                    _cap = _methods_budget
                    _methods_budget -= min(len(_text), _cap)
                    _cap = max(_cap, 0)
                else:
                    _cap = 4000
                _sections_out.append({
                    "title": _title,
                    "text": _text[:_cap] if _cap else "",
                    "truncated": len(_text) > _cap,
                })
            return json.dumps({
                "success": True,
                "full_text_length": structured.get("full_text_length", 0),
                "sections": _sections_out,
                "param_hints": structured.get("param_hints", [])[:60],
                "chart_pages": structured.get("chart_pages", [])[:8],
                "species_hint": species,
                "tissue_hint": tissue,
                "direction_hint": direction,
                "message": "PDF 已按章节拆分并抓取参数对提示；图表页已做本地视觉分析（chart_pages）。"
                           "请优先用 Methods 章节 + param_hints 做结构化参数提取，"
                           "每个参数必须注明出处句（context 字段）；图表页的定量信息以 chart_pages 的 OCR 为准。",
            }, ensure_ascii=False)

        # 兜底: 旧版脚本无 --sections → 纯文本
        text = result.stdout
        return json.dumps({
            "success": True,
            "text_length": len(text),
            "text_preview": text[:3000],
            "species_hint": species,
            "tissue_hint": tissue,
            "direction_hint": direction,
            "message": "PDF extracted (plain). Pass this text to LLM for structured parameter extraction."
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
            "description": (
                "下载文献 PDF 到 work/papers/ 目录。强制多源尝试下载。\n"
                "下载策略（依次尝试）：1)直接URL 2)PMID→PMC全文 3)DOI→Unpaywall 4)DOI直接解析\n"
                "下载成功后自动导入全局文献库（hermes_home/papers/，Crossref 元数据+去重），无需再手动导入。\n"
                "下载后可用 extract_params_from_pdf 提取参数。\n"
                "搜索文献时拿到 pdf_url/fulltext_url/doi/pmid 后，尽量传给此工具下载。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url_or_pmid": {"type": "string", "description": "PDF URL / PMID / DOI"},
                    "output_dir": {"type": "string", "description": "Save directory (default work/papers/)"},
                    "doi": {"type": "string", "description": "DOI (如 10.1038/xxx)，当 url_or_pmid 是 PMID 时传入 DOI 可启用 Unpaywall 兑底下载"},
                },
                "required": ["url_or_pmid"],
            },
        },
        handler=lambda args, **kw: download_pdf(
            args.get("url_or_pmid", ""),
            output_dir=args.get("output_dir"),
            doi=args.get("doi", ""),
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

# Alias for backward compatibility
literature_search = search_papers
