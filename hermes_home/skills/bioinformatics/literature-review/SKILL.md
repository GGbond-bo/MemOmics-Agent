---
category: Literature
id: skill_9b0361e33e5541bbb2b43f671dc0d5a5
name: literature-review
description: >
when_to_use: "[literature-review] 需使用literature review功能，适用于相关生信分析场景"
trigger_keywords: ["综述", "文献综述", "systematic review", "literature review", "总结文献", "查文献", "evidence synthesis"]
  General-purpose literature review and evidence synthesis for any scientific
  topic. Aligns with the user through a short clarification step, then searches
  the peer-reviewed literature with the Biomni LiteratureSearch tool using a
  multi-query strategy, grounds every claim in the retrieved records (full
  abstracts and structured metadata), and optionally reads open-access full-text
  PDFs for the most relevant papers when the user wants depth beyond abstracts.
  Produces a narrative review with inline citations, a structured evidence table
  (CSV), and a PDF report. Cites
  only real records returned by the search and never fabricates citations or
  findings. Use this skill whenever someone asks for a literature review,
  evidence synthesis, "what does the literature say about X", state-of-the-art
  summary, or wants the key papers on a topic pulled together — across methods,
  mechanisms, clinical, or basic-biology topics. Even a bare "review the
  literature on X" should trigger this skill.
---
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。以下规则覆盖所有 Biomni 默认行为。

### 规则1: 拿到数据 → 必须调 search_knowledge
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 7步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. check_env 检查环境
3. rail_review(pre) 前置审查
4. source/import 预写脚本（禁止 inline 代码）
5. terminal 执行（分步执行，禁止 && 连接多步骤）
6. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
7. rail_review(post) 后置审查
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 resolution, n_pcs, min_features, FDR threshold等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式（多角色对抗 v3）：
  - 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
  - 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
  - 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
  - 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
  - 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
  - 辩论结果自动归档到 results/.../log/debate_*.json
- **不确定的参数就辩论**，不要自己拍脑袋

### 规则5: 执行后审查

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

  - **图片检查**：
    - 图有没有生成？没生成 → **强制重新执行**
    - 图片是否空白（全白/全黑/全单一色）？空白 → **强制重新出图**
    - 图片是否有 NA/缺失值（>10% 像素是 NA）？有 NA → **强制重新出图**
    - 图片大小是否过小（<5KB）？过小 → **强制重新出图**
    - 图片数量是否足够？（每步至少 1 张图，关键步骤至少 2-3 张）
  - **代码质量检查**：
    - 代码行数是否合理？（过短可能偷懒，过长可能未分段）
    - 代码是否有注释？
    - 代码是否分段执行（禁止 && 连接多步骤）？
  - **结果合理性**：
    - 数值范围是否合理？
    - 跟知识库对应吗？
  - **参数和结论辩论**：
    - 有参数的选择 → **必须调 debate_analysis 辩论**
    - 有结论输出 → **必须调 debate_analysis 辩论**
    - 不通过 → 修复重跑
    - 通过 → **必须调 skill_evolution(action="record_run")** 记录成功经验（skill_name/script_name/species/tissue/direction/params_used/result_summary/quality_score/notes） → 创建目录存储(figures/results/scripts/data) → 下一步
    - **不通过 → 修复后重跑 → 成功后调 skill_evolution(action="record_run")**；如果是脚本报错 → **调 skill_evolution(action="record_error")** 记录根因+修复方案

### 规则6: 结果存储结构
```
results/<模块>/<方法>/
  ├── scripts/     # 分析脚本
  ├── figures/     # PNG + SVG 图表
  ├── data/        # RDS/H5AD 中间数据
  └── results/     # CSV/TSV 结果表
```


### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

| 时机 | action | 调 | 不调 |
|------|--------|----|------|
| 脚本报错+你分析根因+修复后 | record_error | ✅ R/Python 脚本报错，你找到根因并修复 | ❌ trivial 错误（打字错误、路径不存在） |
| 脚本成功+结果通过 rail_review | record_success | ✅ 分析步骤完成，图生成，审查通过 | ❌ 闲聊/方法咨询/非分析任务 |
| 修复后脚本验证稳定有效 | update_script | ✅ 同一错误修复了，重跑成功 | ❌ 只改参数没改脚本；未验证就更新 |

---



# Literature Review

Align with the user on scope, search the peer-reviewed literature with the
Biomni `LiteratureSearch` tool, ground the synthesis in the retrieved records
(abstracts by default, with an optional deeper pass that reads open-access
full-text PDFs), and deliver a narrative review (with inline citations), a
structured evidence table, and a PDF report.

This skill is **search + synthesis**, not custom code: it relies on the
built-in `LiteratureSearch` tool and existing Biomni formatting skills rather
than shipping its own scripts.

---

## When to Use This Skill

Use this skill when the user wants to:
- **Survey what is known** about a topic, method, mechanism, target, disease, or technology
- **Summarize the state of the art** or recent advances in an area
- **Pull together the key papers** and synthesize their findings
- **Build an evidence table** of relevant studies with structured metadata
- **Compare or contextualize** findings across multiple papers, including agreements, conflicts, and open gaps

This works for **any** topic — computational methods, molecular mechanisms,
clinical evidence, basic biology, tooling, etc.

**Do NOT use this skill for:**
- **Deep preclinical extraction** (structured in vitro / in vivo experiment
  details per paper) — use `literature-preclinical` instead.
- **Quantitative meta-analysis / statistical pooling** of effect sizes — this
  skill synthesizes narratively; it does not pool data.
- **Methods/tool benchmarking landscapes** (head-to-head algorithm comparison
  with truth sets) — use `methods-landscape-review` instead.
- **Clinical trial landscape mapping** (by phase/sponsor/status) — use
  `clinicaltrials-landscape` instead.

---

## Step 1 — Clarify Scope (required, but skip what the user already gave)

Before searching, confirm the items below that the user has **not** already
specified. Ask them together in one concise round. For anything the user
skips, **proceed with a sensible default and state the default you used** —
do not block.

Clarify:
1. **Topic & scope** — what the review is about, and how broad vs. focused it
   should be.
2. **Key questions / angle** — what they want answered (e.g. mechanism,
   efficacy, methods comparison, controversies, what's new, practical
   recommendations).
3. **Time window** — recent only vs. comprehensive
   (*default: last ~5 years, but include foundational/older work when it is
   central to the topic*).
4. **Breadth / depth** — roughly how many papers and how deep
   (*default: ~25–40 papers across several queries*).
5. **Quality / study filters** — e.g. high-impact journals only, human studies
   only, specific study designs, minimum sample size (*default: no hard
   filters; prioritize relevance and quality during triage*).
6. **Evidence depth** — review from abstracts only, or also read **open-access
   full-text PDFs** for the most relevant papers? Full text is more thorough but
   slower, and OA is not available for every paper (paywalled papers fall back
   to their abstract). (*default: abstracts only; offer full text as an
   upgrade*). If the user wants full text, confirm roughly how many papers to
   read in full (*default: the top ~10–15 most relevant/pivotal*).
7. **Deliverables** — confirm the defaults below or pick a subset
   (*default: narrative review + evidence table CSV + PDF report*).

Do **not** re-ask anything the user already provided. If the request is
already specific, state your assumed defaults briefly and proceed.

---

## Step 2 — Search with `LiteratureSearch` (multi-query + dedup)

Use the Biomni **`LiteratureSearch`** tool for all searching. Do **not** write
inline API/scraping code.

**Multi-query strategy (default).** One 20-paper call is usually too thin for
a review. Decompose the topic into several focused queries and run them, then
merge and deduplicate:
- Cover **subtopics / facets** (e.g. mechanism, methods, outcomes,
  applications, limitations).
- Include **synonyms and alternate names** (genes, drugs, methods often have
  several; e.g. `PD-L1` / `CD274` / `B7-H1`).
- Separate **"methods" vs. "results/outcomes"** angles when relevant.
- Use `max_papers` up to 20 per call; run as many focused calls as the chosen
  breadth requires.
- **Deduplicate** across calls — records accumulate in `references.jsonl`; drop
  duplicates by DOI first, then by normalized title.

**Map user intent to filters.** `LiteratureSearch` supports filters; apply them
from the clarification answers:

| User intent | Filter to use |
|---|---|
| Recent only | `year_min` |
| Exclude future-dated / cap year | `year_max` |
| High-quality / top journals only | `sjr_max` (1 = top quartile, 2 = top two, …) |
| Human studies only | `human=true` |
| Specific designs (RCT, meta-analysis, cohort, etc.) | `study_types` |
| Adequately powered studies | `sample_size_min` |

Note: filters apply to the Consensus provider; the Exa provider enforces the
year range only. If a filtered search returns too little, loosen filters and
rely on relevance triage instead.

---

## Step 3 — Ground the Synthesis in Retrieved Records

The inline one-sentence highlights are for **triage only** — they are not
enough to write from.

1. **Triage** on the one-liners to decide which papers are relevant and worth
   including.
2. **Read the full records** from `references.jsonl`
   (`/mnt/results/execution_trace/references.jsonl`). Each line is one record
   with `index`, `citation_id`, `title`, `authors`, `year`, `journal`, `doi`,
   `url`, `study_type`, `citation_count`, and the full `abstract`. Match papers
   by `index` (the inline `[N]`) or `citation_id`. Ground the narrative and the
   evidence table in these fields, not the one-liners.
3. For **pivotal papers** that need detail beyond the abstract (specific
   numbers, methods, subgroup results), read the open-access full text — see
   **Step 3.5** when the user has enabled full-text reading. A quick one-off
   `WebFetch` on the `doi`/`url` is fine even in abstract-only mode for a single
   key paper.

**Citation integrity (non-negotiable):**
- Cite **only** records actually returned by `LiteratureSearch`, using inline
  `[N]` where `N` is the returned record index.
- **Never invent** a PMID, DOI, title, or finding, and never attribute a claim
  to a paper that does not support it.
- Place `[N]` immediately after the claim it supports; combine as `[1, 4, 7]`.
- Use inline `[N]` only — do **not** append a separate "References"/
  "Bibliography" section (the platform renders the reference list).

---

## Step 3.5 — Read Open-Access Full Text (optional, only if enabled in Step 1)

**Skip this entire step unless the user opted into full-text reading.** The
default review is abstract-based (Step 3).

When enabled, deepen the synthesis by reading **open-access full-text PDFs** for
the most relevant papers. Default to the **top ~10–15 most relevant/pivotal**
records (or the count the user chose); read abstracts for the rest. Order
candidates by relevance to the user's key questions, breaking ties by recency
and citation count.

For each selected record, resolve a **legal open-access** copy from its `doi`
(both services are free; the second is a fallback):

1. **Unpaywall** — `GET https://api.unpaywall.org/v2/{doi}?email=YOUR_EMAIL`
   (use a real contact email; the parameter is required). If `is_oa` is `true`,
   use `best_oa_location.url_for_pdf` (preferred) or `best_oa_location.url`
   (landing page). This is the primary route to an OA PDF.
2. **Europe PMC** — query
   `https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{doi}&resultType=core&format=json`.
   If the record has `isOpenAccess=Y` / a `pmcid`, the OA full text is available
   from PMC (e.g. the `fullTextUrlList` entries or the `pmcid` article page).

Then **read the located full text with `WebFetch`**, passing a prompt that asks
for the parts a review needs (methods, key quantitative results, limitations,
and how the paper relates to the user's questions). For very large or scanned
PDFs, target the relevant sections rather than the whole document.

**Open-access only — do not bypass paywalls.** Use only legal OA copies
surfaced by Unpaywall/Europe PMC (or a publisher's own OA page). If no OA
full text is found, or retrieval fails, **fall back to the abstract** from
`references.jsonl` for that paper — never fabricate full-text content, and do
not attempt to obtain paywalled PDFs through unofficial sources.

**Track full-text provenance.** Note which papers were read in full vs.
abstract-only (this feeds an "evidence source" column in the evidence table and
keeps the synthesis honest about depth). Citation rules from Step 3 are
unchanged: cite by the `LiteratureSearch` index, and only claims actually
supported by what you read.

---

## Step 4 — Deliverables

Produce the deliverables confirmed in Step 1 (default: all three).

1. **Narrative review (`.md`)** — an organized synthesis grounded in the
   retrieved records, with inline `[N]` citations. Structure the sections
   around the topic and the user's key questions; explicitly note where studies
   **agree**, **conflict**, and where the **evidence is thin or missing**.
2. **Evidence table (`.csv`)** — one row per included paper, built from
   `references.jsonl`: title, authors, year, journal, DOI/URL, study type
   (when available), citation count, and a short key-finding / relevance note.
   When full-text reading was enabled (Step 3.5), add an **evidence source**
   column marking each row as `full-text` or `abstract`.
3. **PDF report** — a polished PDF of the review.

**Formatting is out of scope for this skill.** Do not embed report styling,
figure code, or plot specifications here. For the PDF (and any figures), defer
to the dedicated Biomni formatting skill (`pdf-report-generation`); for a Word
or slide deliverable use `docx-generation` or `pptx-generation`. This skill
decides *what* the deliverables contain; those skills decide *how* they look.

---

## Common Issues

| Issue | Cause | Solution |
|---|---|---|
| Too few results | Query too narrow, or name mismatch | Add synonyms/alternate names; broaden queries; loosen filters |
| Results off-topic | Query too broad or ambiguous | Split into more focused subtopic queries; add key entities |
| Thin synthesis | Wrote from one-liners only | Read full abstracts/metadata from `references.jsonl` before synthesizing |
| Missing specifics (numbers, subgroups) | Detail not in abstract | Enable full-text reading (Step 3.5), or `WebFetch` the DOI/URL for the pivotal papers |
| Filtered search returns little | Filters too strict (often `sjr_max`/`sample_size_min`) | Loosen or drop filters; prioritize relevance during triage |
| No OA full text for a paper | Paper is paywalled / not in Unpaywall or PMC | Fall back to the abstract for that paper; mark it `abstract` in the evidence table — do not bypass the paywall |
| Full-text run is slow | Reading many PDFs is heavy | Lower the full-text count to the top pivotal papers; abstracts cover the rest |

---

## Suggested Next Steps

After the review:
1. **Preclinical depth** — `literature-preclinical` for structured in vitro /
   in vivo experiment extraction on a target–disease pair.
2. **Methods comparison** — `methods-landscape-review` to compare tools/
   algorithms for a task with benchmarking evidence.
3. **Trial landscape** — `clinicaltrials-landscape` to map ongoing/completed
   trials for a disease area.
4. **Target genetics** — `open-targets` for target–disease association evidence.
5. **Formatted deliverables** — `pdf-report-generation`, `docx-generation`, or
   `pptx-generation` to package the review.
6. **Infographic** — if the user wants a visual summary or infographic of the
   review's key findings, use the `GenerateImage` tool.
