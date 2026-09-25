---
name: nature-academic-search
description: "Search literature across sources, verify or manage citations, and build MeSH strategies or citation-impact audits. Use for 文献检索、引文核对、参考文献管理、严格他引 and evidence-backed citer profiles; not for translating a paper or drafting manuscript prose."
category: literature
when_to_use: "[nature-academic-search] 多源文献检索与引文核对：关键词或作者→PubMed+Crossref+OpenAlex+arXiv 并发检索→跨源去重→DOI/PMID 精确取数→APA/GB-T 7714/BibTeX/RIS 引用→MeSH 词表策略→严格他引审计。不用于单篇论文翻译或正文写作"
trigger_keywords: [多源文献检索, 引文核对, 参考文献管理, 严格他引, MeSH词表, 检索桥, 查PubMed和Crossref, 多源检索]
trigger_level: RED
---

# Academic Search — Router

## Routing protocol

For local citation-file conversion with complete supplied records, load
`references/workflows/wf4-citation-file-mgmt.md` and its format reference directly.
Source lookup, API setup, and network preflight apply only when retrieval or verification is
needed; do not require them for a requested offline conversion.

For a new task, load the core and matching resources below. Reuse already loaded guidance on follow-ups; load more only when the task needs it.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). It declares the `workflow` axis, the allowed values, and the file paths each value maps to.

Also read every file listed under `always_load`:

- `static/core/tools.md` — 工具清单：**本仓库没有 MCP**，检索一律用 `scripts/lit_bridge.py` 的四个子命令（对应上游 search_papers / get_paper_by_id / get_citation / lookup_mesh），另有 MemOmics 原生文献工具与共享模块表。
- `static/core/routing-and-ops.md` — the T1→T2→T3 source routing quick guide, environment setup, error handling, and limitations.

### 2. Detect the workflow

Map the user's need to one or more `workflow` values:

- `multi-source-search` — find literature across sources.
- `citation-verification` — verify citations extracted from a document.
- `mesh-strategy` — build a MeSH/PubMed search strategy.
- `citation-file-mgmt` — convert/manage `.nbib`/`.ris`/`.bib` files.
- `reference-mgmt` — BibTeX, related-article discovery, ID conversion.
- `strict-other-citation-impact-audit` — determine strict independent other-citations, build article-level citation metric tables, identify high-profile citers (academy members, presidents/deans, talent-award holders, fellows, field leaders), and extract how they cited the target paper.

A combined request (for example search then export) may need more than one. State the detected workflow(s) in one short line before proceeding.

### 3. Load the matching workflow fragment(s)

Read the file mapped for each detected workflow (under `references/workflows/`). Do **not** read every workflow. Each workflow file links to the shared modules it needs.

### 4. Run the workflow using the loaded material

Apply the loaded material in this order:

1. Core tools and routing (`core/tools.md`, `core/routing-and-ops.md`) — which **lit_bridge.py 子命令** for which need（不是 MCP 工具名）, and the T1→T2→T3 fallback chain for source retrieval.
2. The workflow fragment — its specific steps.
3. Shared modules and scripts on demand (dedup, citation parser, search strategy, RIS/BibTeX format, format converter).

Report specific tool failures and continue with remaining tools; broaden terms when there are no results. 本仓库没有 MCP —— 不要尝试调用 MCP 工具名；脚本连续失败两次就如实报告失败源与错误文本，**不要**编造检索结果或伪造文献条目。

### 5. Reach for references only when needed

The files under `references/` (and `scripts/`) are deep references, not defaults. Open them on demand per the `references.on_demand` table in the manifest — for example `references/source-tiers.md` for the full reliability classification, `references/dedup-engine.md` / `references/citation-parser.md` / `references/search-strategy.md` / `references/ris-bibtex-format.md` for the shared modules, and `scripts/academic_search.py` (no-MCP fallback discovery search) / `scripts/format-converter.py` / `scripts/preflight.py` for the tooling.
