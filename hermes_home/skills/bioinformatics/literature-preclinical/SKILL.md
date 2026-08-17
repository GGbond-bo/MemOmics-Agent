---
category: Literature
id: skill_9a35bb68f5c948ca828a10aa8ea2d667
name: literature-preclinical
description: >
when_to_use: "[literature-preclinical] 需使用literature preclinical功能，适用于相关生信分析场景"
  Preclinical (non-clinical) evidence synthesis. Aligns with the user through a short clarification step, then searchesthe peer-reviewed literature with the Biomni LiteratureSearch tool using a multi-query strategy tuned for in vitro and in vivo work, grounds every claim in the retrieved records (full abstracts and structured metadata), and optionally reads open-access full-text PDFs for the most relevant papers when the user wants depth beyond abstracts. Extracts — narratively — the in vitro experiments (cell lines; viability, apoptosis, migration, colony-formation and other assays; direction of effect) and in vivo experiments (xenograft, PDX, syngeneic, GEMM/transgenic, orthotopic models; dose/route; tumor-growth, survival, PK/PD and toxicity endpoints) reported in each paper. Synthesizes the common model systems, in vitro / in vivo concordance, and the IND-enabling evidence landscape (efficacy / PK / tox coverage and gaps). Produces a narrative review with inline citations and a structured evidence table (CSV). Cites only real records returned by the search and never fabricates citations or findings. Use this skill whenever someone asks for the preclinical evidence on a target–disease pair, what the in vitro / in vivo data show, which cell lines or animal models are used, whether in vitro and in vivo findings agree, or wants the preclinical evidence landscape pulled together to support an
  IND-enabling decision — even a bare "what's the preclinical evidence for X in
  Y" should trigger this skill.
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



# Preclinical Literature Review

Align with the user on the target, disease, and scope; search the peer-reviewed
literature with the Biomni `LiteratureSearch` tool; ground the synthesis in the
retrieved records (abstracts by default, with an optional deeper pass that reads
open-access full-text PDFs); and deliver a **preclinical** narrative review (with
inline citations) plus a structured evidence table.

This skill is **search + synthesis**, not custom code: it relies on the built-in
`LiteratureSearch` tool and existing Biomni formatting skills rather than
shipping its own scripts. It is the `literature-review` workflow specialized to
**preclinical (non-clinical)** in vitro and in vivo evidence: the agent reads the
records and synthesizes the experiments **narratively** — there is no keyword
script and no rigid extraction schema.

---

## When to Use This Skill

Use this skill when the user wants to:
- **Survey the preclinical evidence** for a drug target in a disease indication.
- **Extract in vitro experiments** — cell lines, assay types (viability,
  apoptosis, migration/invasion, colony formation, proliferation, protein/gene
  expression, flow cytometry, etc.), and the key finding and direction of effect.
- **Extract in vivo experiments** — animal models (xenograft, PDX, syngeneic,
  GEMM/transgenic, orthotopic), dose and route, endpoints (tumor growth,
  survival, PK/PD, toxicity, histology, imaging), and the key findings.
- **Identify the common model systems** — which cell lines and animal models are
  most used for the target/disease.
- **Compare in vitro vs in vivo concordance** — for papers reporting both, do the
  in vitro and in vivo results agree?
- **Compile an IND-enabling evidence landscape** — coverage of efficacy, PK/PD,
  and toxicity, and the translational gaps that remain.

**Do NOT use this skill for:**
- **Clinical evidence** (trials, patient outcomes, efficacy/safety in humans) —
  use `literature-review` for general clinical/basic synthesis, or
  `clinicaltrials-landscape` to map the trial landscape by phase/sponsor/status.
- **Quantitative meta-analysis / statistical pooling** of effect sizes — this
  skill synthesizes narratively; it does not pool data.
- **Methods/tool benchmarking landscapes** (head-to-head algorithm comparison
  with truth sets) — use `methods-landscape-review` instead.
- **Citation management / formatting only** — formatting is handled by the
  dedicated Biomni formatting skills (see Step 4).

---

## Step 1 — Clarify Scope (required, but skip what the user already gave)

Before searching, confirm the items below that the user has **not** already
specified. Ask them together in one concise round. For anything the user skips,
**proceed with a sensible default and state the default you used** — do not block.

Clarify:
1. **Target & disease** — the molecular target (e.g. `CDK4/6`, `KRAS G12C`,
   `PD-L1`) and the disease/indication (e.g. `triple-negative breast cancer`,
   `pancreatic cancer`). This is the one required input. If the user just wants to
   try the skill, offer an example pair (e.g. *CDK4/6 in triple-negative breast
   cancer*, *KRAS in pancreatic cancer*, *PD-L1 in NSCLC*, *BRAF in melanoma*) and
   proceed with it.
2. **Key questions / angle** — what they want answered (e.g. mechanism, anti-tumor
   direction/efficacy, which model systems are used, in vitro / in vivo
   concordance, IND-enabling gaps such as missing PK or toxicity).
3. **Time window** — recent only vs. comprehensive (*default: last ~5 years, but
   include foundational/older work when it is central to the target*).
4. **Breadth / depth** — roughly how many papers and how deep (*default: ~25–40
   papers across several queries*).
5. **Quality / study filters** — e.g. high-impact journals only, minimum sample
   size, specific designs (*default: no hard filters; prioritize relevance and
   quality during triage*). Note: preclinical work is animal/in vitro, so **do
   not** restrict to human studies and do **not** filter to clinical study designs
   (RCT, cohort, etc.) unless the user explicitly wants that — those filters would
   exclude the preclinical literature this skill targets.
6. **Evidence depth** — review from abstracts only, or also read **open-access
   full-text PDFs** for the most relevant papers? Full text is more thorough
   (exact cell lines, doses, models, endpoints, effect sizes) but slower, and OA
   is not available for every paper (paywalled papers fall back to their
   abstract). (*default: abstracts only; offer full text as an upgrade*). If the
   user wants full text, confirm roughly how many papers to read in full
   (*default: the top ~10–15 most relevant/pivotal, favoring papers that report
   both in vitro and in vivo data*).
7. **Deliverables** — confirm the defaults below or pick a subset (*default:
   narrative review + evidence table CSV + PDF report*).

Do **not** re-ask anything the user already provided. If the request is already
specific, state your assumed defaults briefly and proceed.

---

## Step 2 — Search with `LiteratureSearch` (multi-query + dedup)

Use the Biomni **`LiteratureSearch`** tool for all searching. Do **not** write
inline API/scraping code, and do **not** use any external literature service —
`LiteratureSearch` is the only search interface.

**Multi-query strategy (default).** One 20-paper call is usually too thin for a
preclinical review. Decompose the target/disease into several focused queries,
run them, then merge and deduplicate:
- Pair the **target + disease** with **preclinical facets**: `in vitro`,
  `in vivo`, `cell line`, `mouse model`, `xenograft`, `patient-derived xenograft
  / PDX`, `syngeneic`, `genetically engineered mouse / transgenic`, `orthotopic`,
  and specific **assay / endpoint** terms (`viability`, `apoptosis`, `migration`,
  `colony formation`, `tumor growth`, `survival`, `pharmacokinetics`, `toxicity`).
- Include **synonyms and alternate names** for the target (genes, drugs, and
  targets often have several; e.g. `PD-L1` / `CD274` / `B7-H1`, or a pathway vs.
  the specific inhibitor).
- Separate a **mechanism / in vitro** angle from an **in vivo efficacy** angle
  when both matter.
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
| Adequately powered studies | `sample_size_min` |

**Preclinical filter caveats:**
- Do **not** set `human=true` — preclinical evidence is animal/in vitro, so this
  would exclude exactly what you want.
- Do **not** restrict `study_types` to clinical designs (RCT, cohort,
  meta-analysis, etc.) unless the user explicitly asks — preclinical studies are
  not indexed under those designs.
- Not every filter applies uniformly across all results, and strict filters can
  drop relevant preclinical papers. If a filtered search returns too little,
  loosen the filters and rely on relevance triage instead.

---

## Step 3 — Ground the Synthesis in Retrieved Records

The inline one-sentence highlights are for **triage only** — they are not enough
to write from.

1. **Triage** on the one-liners to decide which papers are relevant preclinical
   studies and worth including.
2. **Read the full records** from `references.jsonl`
   (`/mnt/results/execution_trace/references.jsonl`). Each line is one record with
   `index`, `citation_id`, `title`, `authors`, `year`, `journal`, `doi`, `url`,
   `study_type`, `citation_count`, and the full `abstract`. Match papers by
   `index` (the inline `[N]`) or `citation_id`. Ground the narrative and the
   evidence table in these fields, not the one-liners.
3. As you read each record, note — **narratively, with no rigid schema** — the
   preclinical details that feed the synthesis and the evidence table:
   - **Experiment type**: in vitro only, in vivo only, or both.
   - **In vitro**: cell line(s) used; assay type(s) (viability, apoptosis,
     migration/invasion, colony formation, proliferation, protein/gene
     expression, flow cytometry, etc.); the key finding and its direction of
     effect.
   - **In vivo**: animal model (xenograft, PDX, syngeneic, GEMM/transgenic,
     orthotopic); dose/route where stated; endpoints (tumor growth, survival,
     PK/PD, toxicity, histology, imaging); the key finding.
   - **Direction / modality**: does the paper test inhibition/knockdown vs.
     activation/overexpression, and is the reported effect anti-tumor/suppressive
     or the opposite?
4. For **pivotal papers** that need detail beyond the abstract (exact cell lines,
   doses, model construction, effect sizes, toxicity), read the open-access full
   text — see **Step 3.5** when the user has enabled full-text reading. A quick
   one-off `WebFetch` on the `doi`/`url` is fine even in abstract-only mode for a
   single key paper.

**Citation integrity (non-negotiable):**
- Cite **only** records actually returned by `LiteratureSearch`, using inline
  `[N]` where `N` is the returned record index.
- **Never invent** a PMID, DOI, title, cell line, model, or finding, and never
  attribute a result to a paper that does not support it.
- Place `[N]` immediately after the claim it supports; combine as `[1, 4, 7]`.
- Use inline `[N]` only — do **not** append a separate "References"/"Bibliography"
  section (the platform renders the reference list).

---

## Step 3.5 — Read Open-Access Full Text (optional, only if enabled in Step 1)

**Skip this entire step unless the user opted into full-text reading.** The
default review is abstract-based (Step 3).

When enabled, deepen the synthesis by reading **open-access full-text PDFs** for
the most relevant papers. Default to the **top ~10–15 most relevant/pivotal**
records (or the count the user chose); read abstracts for the rest. Order
candidates by relevance to the user's key questions, **favoring papers that
report both in vitro and in vivo data**, then breaking ties by recency and
citation count.

For each selected record, resolve a **legal open-access** copy from its `doi`
(both services are free; the second is a fallback):

1. **Unpaywall** — `GET https://api.unpaywall.org/v2/{doi}?email=YOUR_EMAIL` (use
   a real contact email; the parameter is required). If `is_oa` is `true`, use
   `best_oa_location.url_for_pdf` (preferred) or `best_oa_location.url` (landing
   page). This is the primary route to an OA PDF.
2. **Europe PMC** — query
   `https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{doi}&resultType=core&format=json`.
   If the record has `isOpenAccess=Y` / a `pmcid`, the OA full text is available
   from PMC (e.g. the `fullTextUrlList` entries or the `pmcid` article page).

Then **read the located full text with `WebFetch`**, passing a preclinical-focused
prompt that asks for the parts this review needs: the exact cell lines and animal
models, doses and routes, assay and endpoint details, effect sizes and direction
of effect, and any PK/PD or toxicity results — plus how the paper relates to the
user's questions. For very large or scanned PDFs, target the relevant sections
(methods, results) rather than the whole document.

**Open-access only — do not bypass paywalls.** Use only legal OA copies surfaced
by Unpaywall/Europe PMC (or a publisher's own OA page). If no OA full text is
found, or retrieval fails, **fall back to the abstract** from `references.jsonl`
for that paper — never fabricate full-text content, and do not attempt to obtain
paywalled PDFs through unofficial sources.

**Track full-text provenance.** Note which papers were read in full vs.
abstract-only (this feeds an "evidence source" column in the evidence table and
keeps the synthesis honest about depth). Citation rules from Step 3 are
unchanged: cite by the `LiteratureSearch` index, and only claims actually
supported by what you read.

---

## Step 4 — Deliverables

Produce the deliverables confirmed in Step 1 (default: all three).

1. **Narrative review (`.md`)** — an organized synthesis grounded in the retrieved
   records, with inline `[N]` citations. Structure it around these preclinical
   axes, and explicitly note where studies **agree**, **conflict**, and where the
   **evidence is thin or missing**:
   - **In vitro landscape** — the cell lines used, the assay types employed
     (viability, apoptosis, migration/invasion, colony formation, etc.), and the
     key in vitro findings with their direction of effect.
   - **In vivo landscape** — the animal models used (xenograft, PDX, syngeneic,
     GEMM/transgenic, orthotopic), dose/route where reported, the endpoints
     measured (tumor growth, survival, PK/PD, toxicity, histology, imaging), and
     the key in vivo findings.
   - **Model systems & concordance** — which cell lines and animal models are most
     common for this target/disease, and, for papers reporting **both** in vitro
     and in vivo data, whether the two levels of evidence **concord**.
   - **IND-enabling readiness** — how well the evidence covers efficacy, PK/PD,
     and toxicity; the translational gaps (e.g. cell-line-only with no in vivo
     work, no PDX/patient-relevant models, no PK/PD, no toxicity data); and the
     resulting readiness caveats.
2. **Evidence table (`.csv`)** — one row per included paper, built from
   `references.jsonl`: title, authors, year, journal, DOI/URL, study type (when
   available), citation count, and a short key-finding / relevance note. Add
   lightweight preclinical columns captured narratively during reading (Step 3):
   **experiment type** (in vitro / in vivo / both), **model system(s)** (cell
   line(s) and/or animal model(s)), and a short **direction-of-effect** note. When
   full-text reading was enabled (Step 3.5), add an **evidence source** column
   marking each row as `full-text` or `abstract`.
3. **PDF report** — a polished PDF of the review.

**Formatting is out of scope for this skill.** Do not embed report styling, figure
code, or plot specifications here. For the PDF (and any figures), defer to the
dedicated Biomni formatting skill (`pdf-report-generation`); for a Word or slide
deliverable use `docx-generation` or `pptx-generation`; for a visual summary or
infographic use the `GenerateImage` tool. This skill decides *what* the
deliverables contain; those skills decide *how* they look.

---

## Common Issues

| Issue | Cause | Solution |
|---|---|---|
| Too few results | Query too narrow, or target/disease name mismatch | Add target synonyms and preclinical terms (`in vitro`, `xenograft`, `cell line`, etc.); broaden queries; loosen filters |
| Results off-topic (clinical or unrelated) | Query too broad or ambiguous | Split into focused subtopic queries; add the target, disease, and model/assay entities |
| Thin synthesis | Wrote from one-liners only | Read full abstracts/metadata from `references.jsonl` before synthesizing |
| Missing specifics (doses, cell lines, effect sizes) | Detail not in abstract | Enable full-text reading (Step 3.5), or `WebFetch` the DOI/URL for the pivotal papers |
| Filtered search returns little / excludes preclinical work | `human=true` or clinical `study_types` filters applied; or `sjr_max`/`sample_size_min` too strict | Remove the human/clinical-design filters (they exclude preclinical studies); loosen the rest; prioritize relevance during triage |
| No OA full text for a paper | Paper is paywalled / not in Unpaywall or PMC | Fall back to the abstract for that paper; mark it `abstract` in the evidence table — do not bypass the paywall |
| Full-text run is slow | Reading many PDFs is heavy | Lower the full-text count to the top pivotal papers (favor in vitro + in vivo papers); abstracts cover the rest |

---

## Suggested Next Steps

After the preclinical review:
1. **Broader / clinical context** — `literature-review` for general synthesis
   including clinical and basic-biology evidence.
2. **Trial landscape** — `clinicaltrials-landscape` to map ongoing/completed
   trials for the indication.
3. **Methods comparison** — `methods-landscape-review` to compare tools/algorithms
   for a task with benchmarking evidence.
4. **Target genetics** — `open-targets` for target–disease association evidence.
5. **Pathway analysis** — `functional-enrichment-from-degs` on genes from
   relevant pathways.
6. **TF binding targets** — `chip-atlas-target-genes` to identify transcription
   factor targets for the gene.
7. **Formatted deliverables** — `pdf-report-generation`, `docx-generation`, or
   `pptx-generation` to package the review; `GenerateImage` for a visual summary
   or infographic.
