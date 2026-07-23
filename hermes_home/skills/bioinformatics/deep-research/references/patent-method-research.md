# Bioinformatics Method Patent Prior-Art Research Methodology

> Proven workflow from 2026-07-18 session: monkey→human hippocampus scRNA-seq replaceability patent research.
> 8 parallel tool calls → 13 core papers filtered → structured report with gap analysis.

## When to Use
User asks for: method patents, prior art, patent landscape, 软著调研, cross-species comparability patents, or "is my method idea patentable?"

## Multi-Pronged Parallel Search Strategy

### Round 1: Parallel Launch (6-8 calls simultaneously)
```
search_knowledge(query, species, tissue, direction)     # Internal KB: cell types, markers, existing methods
search_papers_by_context(species, tissue, direction)    # Semantic Scholar: domain papers
search_papers(query="cross-species ... patent method")  # Broad patent-aware query
search_papers(query="cross-species ... benchmark")      # Method-focused query
search_papers(query="hippocampus aging macaque human")  # Tissue-specific query
search_papers(query="cross-species ortholog gene ...")  # Ortholog/conservation query
```
**Key insight**: Launch ALL 6 queries simultaneously. Don't wait for results to refine — the overlap and unique hits across queries is the value.

### Round 2: Download + Deepen
- `download_pdf` on top-5 papers (expect 50% failure rate from paywalls/Cloudflare)
- `search_papers` with refined queries from Round 1 findings
- If patent APIs fail (Google Patents, Espacenet, WIPO, Lens.org all likely blocked), pivot to **literature-driven gap analysis** — identify what exists in papers to infer where patent gaps are.

### Round 3: Compile Report
Structure:
1. 核心判断 (Core judgment — is there a gap?)
2. 核心参考文献 (Tiered: 🔴 must-read / 🟡 important / 🟢 supplementary)
3. 知识库已有资源 (What KB already has)
4. 专利/软著调研结果 (Patent search results + manual search strategies)
5. 核心创新点建议 (Suggested patent claims)
6. 推荐行动路线 (Actionable next steps)
7. 风险提示 (Risk assessment)
8. 关键发现可视化 (ASCII/Mermaid diagram of the landscape)

## Patent Database Search Strategies (for user to manually execute)

| Database | URL | Query Template |
|----------|-----|----------------|
| Google Patents | patents.google.com | `"cross-species" "single-cell" transcriptomics` |
| WIPO Patentscope | patentscope.wipo.int | `FP:(cross-species AND single-cell)` |
| Espacenet | worldwide.espacenet.com | `cross-species single cell RNA` |
| SooPAT (Chinese) | soopat.com | `跨物种 单细胞 方法` |
| CNKI Patent | kns.cnki.net | `跨物种 AND 单细胞 AND 转录组` |
| Lens.org | lens.org | `cross-species single cell transcriptomics` |

## Key Pattern: Literature → Patent Gap Inference

When patent APIs are inaccessible:
1. Search all major literature databases (PubMed, Europe PMC, Semantic Scholar, bioRxiv)
2. Filter for methodology papers (benchmarks, pipelines, integration tools)
3. Map the literature landscape across 3 layers:
   - **Theory layer**: benchmark/comparison papers (e.g., Song 2023 Nat Commun)
   - **Implementation layer**: pipeline/tool papers (e.g., Ruz Jurado 2024 GigaScience)
   - **Application layer**: domain-specific comparisons (e.g., Xiong 2025 Mol Biol Evol)
4. Identify the GAP between what exists in literature and what could be a patentable method
5. The gap IS the patent opportunity

## Report Template Pitfalls
- NEVER list papers without explaining WHY they matter to the user's specific project
- NEVER give equal weight to all papers — use 🔴🟡🟢 priority tiers
- ALWAYS include a visual summary (ASCII diagram or Mermaid flowchart)
- ALWAYS give actionable next steps, not just "interesting findings"
- For graduation-related research, emphasize the "research gap → patent opportunity" narrative

## Known API Limitations
- Google Patents, Espacenet, WIPO, Lens.org: all likely blocked from server-side access
- Nature publishing group PDFs: Cloudflare anti-bot protection
- Workaround: bioRxiv PDFs usually succeed; PubMed Central PDFs are hit-or-miss
- Strategy: download what you can, summarize abstracts for the rest, tell user to manually fetch
