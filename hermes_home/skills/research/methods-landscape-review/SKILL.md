---
name: methods-landscape-review
description: >
  Systematic, verification-first comparison of bioinformatics methods/tools
  (head-to-head, e.g. "Seurat vs Scanpy 整合流程差异", 工具 A vs B 对比报告,
  method benchmarking landscape). Every citation is verified against NCBI
  PubMed by keyword search (never trust remembered PMIDs), abstracts are pulled
  via the efetch endpoint, official docs are scraped via curl + regex HTML
  extraction, and every report claim carries a verifiable source (PMID/DOI/URL).
  literature-review explicitly routes tool-benchmarking tasks here.
when_to_use: "[methods-landscape-review] 方法/工具对比调研：Seurat vs Scanpy、工具A vs 工具B 流程差异、方法学 benchmark 综述、'调研并输出 X vs Y 对比报告'。关键词：对比、比较、差异、landscape、head-to-head、流程差异"
---

# Methods / Tools Landscape Review（方法对比调研）

Verification-first comparison of two or more bioinformatics methods/tools, producing a structured report where **every claim is traceable to a verified source**.

`literature-review` 的职责边界：它做"文献综述"（search + synthesis）；**方法/工具 head-to-head 对比**由本 skill 负责（literature-review 的 Do NOT Use 与 Suggested Next Steps 均指向本 skill）。

## When to Use

- 用户要求对比两个工具/流程的差异（如 Seurat vs Scanpy 整合、R vs Python 生态）
- 方法选型调研（benchmark 结论、适用场景、性能数据）
- 需要给出"选 A 还是选 B"的结构化中文/双语报告

## Core Workflow（7 步）

1. **加载相关分析 skill**：任务涉及的具体工具若有 skill（如 scrnaseq-seurat-core-analysis / scrnaseq-scanpy-core-analysis），先 skill_view 拿其 references（如 integration_methods.md）——里面有方法谱系、参数与评估标准，是报告的"基线知识"。
2. **KB 检索**（search_knowledge）：命中则作为基线；**若 KB 工具不可用（如 SQLite 线程错误），尝试 2 次即止，立即切换到第 3 步的双源验证**——绝不因 KB 不可用而降低证据标准。
3. **文献验证（PubMed 为主）**：
   - **绝不信任记忆中的 PMID/DOI**（本 skill 首次使用时记忆中的 5 个 PMID 全部错误）。一律用 `query_ncbi(db='pubmed', query='标题关键词+第一作者')` 关键词检索确认；找不到再按 DOI 检索。
   - 拿全文摘要用 efetch 端点（query_ncbi 只返回元数据，不含摘要）：
     `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=<PMID1>,<PMID2>&rettype=abstract&retmode=text`（curl 抓取）——benchmark 结论（推荐方法、指标、规模）必须来自摘要原文，不可凭印象转述。
   - 关键 benchmark 文献（单细胞整合领域）：Tran 2020（PMID 31948481）、Luecken 2022（PMID 34949812）；引用结论见 references/seurat-vs-scanpy-integration.md。
4. **官方文档验证（curl + HTML→文本提取）**：
   - `curl -sL <url> -o work/docs/<name>.html`，再用 Python 正则提取正文（去 script/style → 去标签 → html.unescape → 压缩空白）。文档里可直接搜关键词引用原文（如 "leaves the data matrix itself invariant"）。
   - **猜的 URL 404 时不要反复试**：下载教程/文档索引页，正则 `href="([^"]+)"` 提取真实链接再抓（本 skill 首次使用时 harmony 教程与 multi_tools 页面均 404，靠此方法定位到 `basics/integrating-data-using-ingest.html` 等正确 URL）。
5. **写报告**：结构化中文报告，含一句话结论 → 核心对比表 → 各维度详细说明（每节标注来源）→ 参考来源列表（文献表带 PMID/DOI，官方文档带 URL）。发现引用错误立即修正（如 Squair 2021 PMID 由记忆值 34650260 核正为 34584091）。
   - **查不到的引用 → 显式标注"待核实"**，绝不静默丢弃或编造：如用户点名某批评文献（"Hurlock 等"）检索无果时，在报告末尾列"待核实项"并注明所用检索词，正文不引用。这比假装没看见更专业，也保留后续补查入口。
   - **全文核验模式（关键论断必须看原文）**：benchmark/局限性/阈值类论断（如 "Z<5 未保存"、"100 permutations"、"spurious correlations"）仅靠摘要不够时，抓全文 PDF 后本地关键词提取：
     - `curl -sL -A "Mozilla/5.0" "https://europepmc.org/articles/PMC<id>?pdf=render" -o work/papers/<name>.pdf`（PMC 全文 PDF 的稳定直链，download_pdf/web_extract 失败时的兜底）
     - Python PyMuPDF（`fitz`）逐页 `get_text()` 后正则搜关键词（如 "permutation"/"Zsummary"/"Limitations of the study"/"false positive"），把论断与原文逐字核对、记录页码/上下文。
6. **交叉核对**：报告里的每个数字/结论至少有一个可验证来源；两来源矛盾时以 PubMed 摘要原文为准。
7. **沉淀**：把带验证引用的领域知识写入本 skill 的 `references/`（见下），避免下次重新检索。

## Pitfalls

- **记忆 PMID 必错**：所有 PMID/DOI 必须经 PubMed 关键词检索核实（见过 5/5 全错的实例）。
- **search_papers 对方法学检索精度差**：返回结果多为"应用型"论文（用 WGCNA 做疾病研究的文章）且摘要常为空；方法学批评/基准类文献要用 `query_ncbi(db='pubmed', query='标题关键词+作者')` 精确检索，再用 `web_search` 交叉验证。搜到未知 PMID 后用 `query_ncbi(query='<PMID>[uid]')` 反查补全期刊/DOI。
- **query_ncbi 无摘要**：摘要要走 efetch `rettype=abstract&retmode=text`。
- **文档 URL 易 404**：readthedocs/satijalab 页面改版频繁；从索引页提取 href 定位真实链接。
- **KB 工具故障 ≠ 免验证**：KB 不可用时用 PubMed + 官方文档双源验证兜底，报告须注明 KB 不可用及替代路径。
- **禁止环境性负面结论**：工具/接口一次失败（如 SQLite 线程错误、404）只记录"当时不可用+替代路径"，不写"该工具不能用"。

## Deliverable Shape

Markdown 报告（必要时 HTML）：一句话结论 → 核心对比表 → 分维度详解（定位/数据对象/方法谱系/前处理/结果表示/评估/性能/适用场景）→ 参考来源（文献表含核实过的 PMID+DOI、官方文档 URL、skill 内嵌知识来源）。

## References

- `references/seurat-vs-scanpy-integration.md` — Seurat vs Scanpy 单细胞整合流程对比知识库（已核实的 13 篇文献 PMID/DOI、benchmark 结论、官方文档原文要点、2026-08 调研产出）
