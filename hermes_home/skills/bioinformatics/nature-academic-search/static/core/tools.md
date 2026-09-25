# 工具与检索桥（本仓库：无 MCP）

**先读这一句**：MemOmics-Agent 进程里只有自研 agent 循环，**没有 MCP 客户端**。所以
`search_papers` / `get_paper_by_id` / `get_citation` / `lookup_mesh` 这些 MCP 工具名
**调不到**，不要尝试调用，也不要声称调用过。检索走下面两条路。

## 1. 主路径：lit_bridge.py（标准库 / 零 API key / 不走 MCP）

`scripts/lit_bridge.py` 把上游 MCP 的四个核心工具重写成 CLI，语义一一对应：

| 上游 MCP 工具 | 本仓库等价命令 | 说明 |
|---|---|---|
| `search_papers` | `python scripts/lit_bridge.py search "<query>" [--sources pubmed,crossref,openalex,arxiv] [--limit N] [--year-from YYYY] [--json]` | 多源**并发**检索，默认 pubmed+crossref+openalex；跨源去重（DOI > PMID > 归一化标题） |
| `get_paper_by_id` | `python scripts/lit_bridge.py paper <DOI 或 PMID:123 或 arXiv:2401.00001>` | 自动识别 id 类型；加 `--citation apa` 顺带出引用 |
| `get_citation` | `python scripts/lit_bridge.py cite <DOI 或 PMID> --style apa / gbt7714 / bibtex / ris` | `gbt7714` 面向中文投稿 |
| `lookup_mesh` | `python scripts/lit_bridge.py mesh "<term>"` | MeSH 入口词 + 同义词 + 树号 |

**调用方式（Windows / 本仓库 venv，必须带代理）**：

```powershell
$env:HTTPS_PROXY="http://127.0.0.1:6478"; $env:HTTP_PROXY="http://127.0.0.1:6478"
.venv\Scripts\python.exe hermes_home\skills\bioinformatics\nature-academic-search\scripts\lit_bridge.py search "skeletal muscle single-cell aging" --limit 5 --json
```

**读结果的方式**：

- 退出码 **0** = 至少一个源有结果；**2** = 全部源失败或无结果 → 换词、换源、或按 T1→T2→T3 降级，不要假装有结果。
- `--json` 给出结构化记录（`source/doi/pmid/title/authors/year/venue/volume/issue/pages/citations/url`），直接喂给去重与排序模块（见 `references/dedup-engine.md`）。
- **单源失败不中断**：失败源写在 stderr（`[warn] 源失败 ...`）并出现在 JSON 的 `errors` 字段里。照实报告哪些源失败，**不要**把三个源的失败吞成一个"没找到"。
- 引用数只有 crossref / openalex 提供（pubmed 显示 `-`）；arXiv 是预印本，**不能**当正式发表引用。

## 2. 补充路径

| 场景 | 用什么 |
|------|--------|
| 按作者 / 机构 / ORCID 追一个人或一个实验室的产出 | `scripts/academic_search.py`（OpenAlex）`--author` / `--affiliation` / `--orcid` / `--list-authors` / `--sort cited_by_count` |
| 本地 `.nbib` / `.ris` / `.bib` 批量转换与批量下载 | `scripts/format-converter.py`（纯标准库） |
| 联网前的连通性预检 | `scripts/preflight.py` |
| MemOmics 进程内原生文献工具（与上面并存，按需混用） | `literature_search` / `search_papers` / `pubmed_search` / `search_papers_by_context` / `summarize_paper` / `literature_import` / `kb_extract_from_paper` |

## 3. 共享模块

| 模块 | 用途 |
|------|------|
| [Dedup Engine](../../references/dedup-engine.md) | 跨源去重（WF 1、2、5a） |
| [Citation Parser](../../references/citation-parser.md) | 从文档里抽取引文（WF 2） |
| [Search Strategy](../../references/search-strategy.md) | 检索式构造、选源、排序 |
| [RIS/BibTeX Format](../../references/ris-bibtex-format.md) | 格式规范与字段映射 |
| [Format Converter](../../scripts/format-converter.py) | 多源 .nbib/.ris/.bib 下载与转换 |

## 4. 不上 MCP：原 MCP 清单与遗留配置

上游 `mcp-server/` 还提供 Scopus / ScienceDirect 系列（`search_scopus`、`get_scopus_abstract`、
`get_scopus_citation_overview`、`search_scopus_authors`、PlumX 指标、ScienceDirect 元数据等）。
它们需要 Elsevier key + `pybliometrics` + 机构订阅，**本仓库不挂载、也不建议启用**。

`config/mcp-snippet.json`、`config/settings-snippet.json`、`agents/openai.yaml` 是给 Claude Code
挂 MCP 用的遗留配置，本仓库不读。确有 Scopus 需求时，明确告诉用户"需要 Elsevier 订阅与 key"，
走显式授权流程 —— 不要假装工具存在，也不要编造 Scopus 指标。
