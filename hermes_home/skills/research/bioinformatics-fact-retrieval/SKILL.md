---
name: "bioinformatics-fact-retrieval"
description: "从官方文档与文献中获取并核实生信事实（方法对比、PMID/DOI 核验、docs 404 兜底链、摘要锚定）"
when_to_use: "[bioinformatics-fact-retrieval] 需要调研/对比生信方法并引用真实文献（PMID/DOI）或官方文档时；官方文档页面 404 或需要源文件（vignette Rmd/函数签名）时；需要把性能/结论声明锚定到论文摘要原文（防编造）时；文献检索工具漏检需要兜底时"
display-name: "Bioinformatics Fact Retrieval & Verification"
category: research
short-description: "Retrieve and verify bioinformatics facts from official docs and literature with fallback chains, real PMIDs/DOIs, and abstract-grounded claims."
---

# Bioinformatics Fact Retrieval（生信事实检索与核实）

调研类任务（方法对比、工具选型、文献支撑）的事实获取与核实规程。核心原则：**所有事实必须来自真实查询（官网文档、GitHub 源文件、PubMed/EuropePMC），不能凭记忆编造；拿不到就标注推断或缺失**。

## When to Use
- 方法/工具对比调研（如 Seurat vs Scanpy 批次整合），需要引用真实 PMID/DOI
- 官方文档页面 404，或需要比渲染网页更权威的源文件（vignette Rmd、函数签名、docstring）
- 需要把性能/结论声明锚定到论文摘要原文（例：Harmony 摘要 "~10^6 cells on a personal computer"）
- 文献检索工具漏检时需要兜底通道

## Workflow（按序执行）

### 1. 文献检索链（防漏检）
1. `search_papers(关键词)` — 混合 Europe PMC/Semantic Scholar，**会漏检**（例：BBKNN 论文关键词搜索未命中）
2. 漏检 → `query_ncbi(db='pubmed', query='<论文精确标题>')` 直查（例：BBKNN 靠此拿到 PMID 31400197）
3. 摘要核实/锚定声明 → Europe PMC REST：
   `https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:<PMID>&resultType=core&format=json`（取 `abstractText` 字段，用于引用性能/结论数字）

### 2. 官方文档链（404 兜底）
1. 官网页面（satijalab.org / scanpy.readthedocs.io / docs.scvi-tools.org）
2. 页面 404 → GitHub API 列目录确认源文件存在：
   `https://api.github.com/repos/<org>/<repo>/contents/<dir>?ref=<branch>`（例：`satijalab/seurat` 的 `vignettes/` 目录，返回文件列表含 default_branch）
3. 拉源文件用 jsdelivr CDN（raw.githubusercontent.com 可能被网络屏蔽）：
   `https://cdn.jsdelivr.net/gh/<org>/<repo>@<branch>/<path>`（例：`cdn.jsdelivr.net/gh/satijalab/seurat@main/vignettes/seurat5_integration_rpca.Rmd`）
4. 版本化文档 URL 可救回部分 404（如 scanpy `en/1.9.1/...`）

### 3. HTML→文本提取（批量抓文档时）
python 正则：去 `<script>/<style>` → 去标签 → `html.unescape` → `\s+` 折叠成单行 → 按关键词窗口（±250 字符）打印上下文。避免整页输出浪费 token。

### 4. 核实与诚实规则（不可违反）
- **只引用真实查询返回的 PMID/DOI**；检索接口可能不回传 DOI 字段（例：ComBat, PMID 16632515）→ 引用期刊标准 DOI 并在报告"注记"中标注，不静默编造
- 基于原理的推断（如"跨物种需 ortholog 化"）必须在报告中标注为推断，不得写成官方原文
- 性能/规模声明优先引用论文摘要原文（如 Harmony "~10^6 cells on a personal computer"、Luecken 2022 ">1.2 million cells / 68 method combinations"）
- 报告末尾附"诚实性注记"段落，列明推断项与缺失字段

## Pitfalls（真实踩坑记录）
| 现象 | 原因/处理 |
|---|---|
| satijalab.org 部分文章页 404（如 integrate_rpca.html、harmony 教程） | 文章未发布但 GitHub `vignettes/` 目录有源 Rmd（已确认：seurat5_integration.Rmd / seurat5_integration_rpca.Rmd / seurat5_integration_large_datasets.Rmd / seurat5_integration_bridge.Rmd / seurat5_weighted_nearest_neighbor_analysis.Rmd）→ 走 jsdelivr |
| raw.githubusercontent.com 拉取失败 | 网络屏蔽 → 换 jsdelivr CDN（同一路径格式） |
| github.io 站点页面 curl 报 SSL error 35（如 smorabit.github.io） | 不是重试能解决的 → 改拉 `raw.githubusercontent.com/<org>/<repo>/<branch>/<path>` 源码/vignette Rmd（raw 失败再换 jsdelivr） |
| web_extract 报 "search-only backend and cannot extract URL content" | 后端是 ddgs（仅搜索）→ 用 curl 下载 HTML 后 python 正则提取正文（去 script/style → 去标签 → html.unescape → 关键词窗口打印） |
| download_pdf 的 pmc_fulltext 策略失败 | 手动 curl `europepmc.org/articles/PMC<id>?pdf=render` 直接拿 PDF（开放获取可用） |
| 任务/需求描述中的期刊名/标题与实际不符（例："hdWGCNA 是 Nature Methods 2023"实为 Cell Reports Methods 2023;3(6):100498） | 引用前用 query_ncbi(pubmed, 作者+关键词) 核实卷期；查无此文就在报告"更正"段落如实标注，不顺着任务说法写 |
| 大文件 write_file 流超时 | 内容拆 3 部分分别 write_file 再 `cat` 合并，单次调用控制在 ~8K token 内 |
| scanpy readthedocs 个别生成页 404（scanpy.pp.combat 等） | 用已抓取页面的导航/API 索引确认函数确实存在；新版函数可能移位（pp.combat 曾属 external） |
| search_papers 关键词搜索无结果 | 混合源漏检 → query_ncbi 按精确标题直查 |
| terminal 连续 404 触发工具失败计数 | 每次换新 URL/新命令串，用 GitHub API/版本化 URL 换方案，不要原样重试 |

## References
- `references/seurat-vs-scanpy-batch-integration.md` — Seurat vs Scanpy 批次整合对比知识库：快速选型表、方法原理速查、v5/scanpy API 要点、11 篇核验文献（PMID/DOI）、官方文档获取技巧（本次调研沉淀）
- `references/hdwgcna-vs-wgcna-methodology.md` — hdWGCNA vs 经典 WGCNA 方法学要点（2026-08 核实）：文献引用更正（CRM 2023 非 Nature Methods）、metacell bagging+kNN 算法细节与聚合方式（仅 average/sum）、流程对比、eigengene/TOM 数学差异、论文 PDF/源码获取技巧
