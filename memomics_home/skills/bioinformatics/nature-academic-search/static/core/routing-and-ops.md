# Source routing and operations

## Source routing

See [Source Tiers & Reliability](../../references/source-tiers.md) for source retrieval and fallback routing. Local format conversion from supplied complete records does not require source retrieval, credentials, or network preflight. Retrieve metadata only when the requested verification or missing fields require it; do not invent absent fields.

Quick guide:

| User need | Primary (T1) | Secondary (T2) | Last Resort (T3) |
|-----------|-------------|-----------------|-------------------|
| Medical / clinical | PubMed | Semantic Scholar | Google Scholar |
| Cross-disciplinary | CrossRef | Semantic Scholar | Scopus |
| Preprints / CS / physics | arXiv | bioRxiv / medRxiv | — |
| Exhaustive review | PubMed + CrossRef + arXiv | Semantic Scholar + bioRxiv/medRxiv | WoS / Scopus |
| Citation count sensitive | Semantic Scholar | CrossRef | — |
| Chinese literature | — | — | CNKI / 万方 (manual) |

## Environment setup

### API keys (optional but recommended)

| Service | Env Var | Register At | Free Tier |
|---------|---------|-------------|-----------|
| Semantic Scholar | `SEMANTIC_SCHOLAR_API_KEY` | [api.semanticscholar.org](https://api.semanticscholar.org/) | 100 req/s with key (1/s without) |
| NCBI E-utilities | `NCBI_API_KEY` | [ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/) | 10 req/s with key (3/s without) |
| Elsevier / Scopus / ScienceDirect | pybliometrics config | [dev.elsevier.com](https://dev.elsevier.com/) | Depends on API entitlement |

Set Semantic Scholar / NCBI keys via `export` or `.env` file. Elsevier keys are read from the local pybliometrics config, normally `~/.config/pybliometrics.cfg`; do not copy API keys into this plugin.

### Proxy (本机必须走代理)

本机（MemOmics 开发机）出口代理是 **http://127.0.0.1:6478**，lit_bridge / academic_search /
format-converter 都只认标准代理环境变量（urllib 自动读取）：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:6478"; $env:HTTPS_PROXY="http://127.0.0.1:6478"
```

不设代理时，PubMed / Crossref / OpenAlex / arXiv 会以超时或连接被拒的形式失败 —— 这种失败
要报成"网络/代理不可达"，并给出上面两行让用户自己设，**不要**报成"检索不到文献"。

### Pre-flight check

```bash
python scripts/preflight.py
```

Run before batch network operations to verify API endpoints are reachable.

### Format converter dependencies

The format converter (`scripts/format-converter.py`) uses Python stdlib only — no extra dependencies. Run `python scripts/format-converter.py --test` to verify the conversion pipeline.

### 主路径（MemOmics 本仓库没有 MCP）

MemOmics-Agent 进程里只有自研 agent 循环，**没有 MCP 客户端**，所以这一节不是"fallback"而是
**唯一可用路径**：检索一律走 stdlib-only 脚本直连公开 HTTP API（与 `nature-citation/scripts/nature_citation.py`
同一路数）。三个脚本分工：

- **多源检索（首选）** — `scripts/lit_bridge.py`：`search`（PubMed + Crossref + arXiv + OpenAlex 并发 + 跨源去重）、
  `paper`（DOI/PMID/arXiv ID 精确取数）、`cite`（APA / GB-T 7714 / BibTeX / RIS）、`mesh`（MeSH 词表）。
  零 key、零 pip 依赖；对应上游 MCP 的 search_papers / get_paper_by_id / get_citation / lookup_mesh 四个工具。
  ```powershell
  python scripts/lit_bridge.py search "skeletal muscle single-cell aging" --limit 5 --json
  python scripts/lit_bridge.py cite 10.1038/s41586-024-07348-6 --style gbt7714
  ```
- **作者/机构视角检索** — `scripts/academic_search.py` queries OpenAlex (free, no API key). OpenAlex indexes CrossRef, PubMed and arXiv-deposited works, so one endpoint covers journals and preprints for keyword/author search, with relevance re-ranking and author disambiguation (`--affiliation` / `--orcid` / `--list-authors`). Returns ranked JSON (title, DOI, authors, year, citations, abstract).
- **Download / convert** — `scripts/format-converter.py` turns the chosen DOIs/PMIDs/arXiv IDs into `.ris`/`.bib`/`.enw`/`.nbib` (CrossRef + PubMed + arXiv, also stdlib-only).

```bash
# discover, then export the picks
python scripts/academic_search.py "graph neural network potentials" --limit 10 --sort cited_by_count --mailto you@example.com
python scripts/format-converter.py --doi 10.1103/physrevlett.120.143001 --format ris
```

Be polite to the OpenAlex pool: pass `--mailto` or set `OPENALEX_MAILTO` / `CROSSREF_MAILTO`. Each script reports per-source failures (HTTP 429, timeout, network) on stderr and exits non-zero, so a caller treats each source independently and continues with another tool. 这套直连覆盖 T1→T2→T3 的检索面（lit_bridge 直连 PubMed/Crossref/arXiv/OpenAlex，academic_search 补 OpenAlex 的作者/机构视角）。上游的 MCP 路径在本仓库**不可用**（无 MCP 客户端），因此 Semantic Scholar / Scopus / ScienceDirect 拿不到 —— 需要时如实说明"需要额外 key 或订阅"，不要编造这些源的指标。

### 上游 MCP server（本仓库未挂载，仅存档）

以下是上游在 Claude Code 里跑 MCP server 的方式，MemOmics 用不上（没有 MCP 客户端）：

```bash
uv run --no-project --directory <mcp-server> --with "mcp>=1.0.0,<2.0.0" --with "requests>=2.28.0,<3.0.0" --with "toml>=0.10.2,<2.0.0" --with "lxml>=4.9.0,<6.0.0" --with "pybliometrics>=4.4.1,<5.0.0" python academic_search_server.py
```

上游 `search_papers` 默认 CrossRef + PubMed + arXiv，Scopus / ScienceDirect 是 opt-in（需要 `pybliometrics` 与本机 `~/.config/pybliometrics.cfg`，且消耗 Elsevier 配额）。本仓库：**不要尝试启动这个 MCP server**，也不要调用它的工具名 —— 用 `scripts/lit_bridge.py`。

## Error handling

- **某个源失败**（`[warn] 源失败 pubmed: HTTPError: 429`）：照实报告失败的源与错误文本，继续用其它源的结果 —— lit_bridge 已内置逐源容错，不要把它吞成一句"没检索到"。
- **全源失败 / 退出码 2**：先怀疑代理没设（见上），再降级换源（T1→T2→T3）、换检索词。
- **无结果**：放宽检索词、换源、让用户补充限定条件。
- **脚本连续失败两次**：如实报告"检索工具本身坏了 + 原始错误文本"，**不要**凭记忆编造文献条目、DOI 或引用数 —— 编造文献是这一行最严重的错误。

## Limitations

- Google Scholar and Semantic Scholar are scraped (not API-backed) — results may vary.
- Chinese literature (CNKI / 万方) not indexed by CrossRef or PubMed.
- Citation counts may be delayed (CrossRef updates monthly).
