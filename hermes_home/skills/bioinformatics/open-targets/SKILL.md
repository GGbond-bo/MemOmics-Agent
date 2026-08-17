---
id: open-targets
name: Open Targets Platform (GraphQL API)
when_to_use: "[open-targets] Open Targets平台查询：疾病/靶点→靶点-疾病关联证据→遗传/组学/文献→药物开发管线"
category: Drug Discovery
short-description: Query the Open Targets Platform GraphQL API for target–disease associations, evidence, and annotations supporting drug target identification.
detailed-description: Query the Open Targets Platform GraphQL API for drug target identification, validation, and prioritisation in human disease. Use whenever the user asks about target–disease associations, evidence linking a gene to a disease, gene/protein annotations relevant to drug discovery (tractability, essentiality, baseline expression, genetic constraint, safety liabilities, FAERS adverse events), disease annotations (ontology, known drugs, associated targets), drug/compound info (mechanism of action, indications, clinical trial phase), GWAS variants and studies, credible sets, colocalisation, or Locus-to-Gene (L2G) predictions — even if they don't say "Open Targets" by name. Also use when they mention Ensembl gene IDs (ENSG…), EFO disease IDs (EFO_…), ChEMBL drug IDs, or GWAS Catalog study IDs (GCST…) in a drug discovery context. Do NOT use for non-human biology, general literature search, or bulk extraction across many entities (point users to FTP/BigQuery downloads).
starting-prompt: "What targets are most strongly associated with Alzheimer's disease in Open Targets, and what evidence types support the top hits? . . "
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



# Open Targets Platform GraphQL API

Programmatic access to Open Targets target–disease associations, evidence, and annotations via a single GraphQL endpoint.

## When to Use This Skill

Use Open Targets when the user wants:

- ✅ **Target annotations** (genes/proteins by Ensembl ID): tractability, essentiality, expression, constraint, safety, known drugs
- ✅ **Disease annotations** (by EFO ID): ontology, known drugs, associated targets, clinical signs
- ✅ **Drug/compound info** (by ChEMBL ID): mechanism of action, indications, trial phase, pharmacovigilance
- ✅ **Target–disease association scores and evidence** across 20+ datasources, with optional custom weighting
- ✅ **Variants, GWAS studies, credible sets, L2G** (former Genetics Portal — now part of the Platform API)
- ✅ **Name → ID resolution** for genes, diseases, drugs

**Don't use Open Targets for:**
- ❌ Bulk/systematic extraction across many entities → use the FTP downloads, BigQuery (`open-targets-prod`), or AWS Open Data buckets instead
- ❌ Non-human biology, general literature search, EHR/clinical-trial-recruitment data, or proprietary datasets

## Quick Start

**Test this skill in ~30 seconds — no API key required:**

```python
import requests

URL = "https://api.platform.opentargets.org/api/v4/graphql"
query = """
query { disease(efoId: "MONDO_0004975") {
  name
  associatedTargets(page: { index: 0, size: 5 }) {
    rows { target { approvedSymbol } score }
  }
} }
"""
print(requests.post(URL, json={"query": query}).json())
```

**Expected:** Top 5 targets associated with Alzheimer's disease (MONDO_0004975) with overall association scores (0–1).

## Installation

**Required:**
```bash
pip install requests
```

**Optional (for tabular handling):**
```bash
pip install pandas
```

**No API key, no auth, no rate-limit headers in the public docs.** The maintainers ask you not to loop one entity at a time — use bulk downloads for that.

**License:** Open Targets data is released under CC0 1.0; the API is free to use.

## Inputs

**Required for most queries — one of the following standardised IDs:**

| Entity   | ID format             | Example            |
|----------|-----------------------|--------------------|
| Target   | Ensembl gene          | `ENSG00000169083`  |
| Disease  | EFO (or imported)     | `MONDO_0004975`    |
| Drug     | ChEMBL                | `CHEMBL1201583`    |
| Variant  | `chrom_pos_ref_alt`   | `19_44908822_C_T`  |
| Study    | GWAS Catalog          | `GCST005194`       |

**If the user provides a free-text name or non-primary identifier (gene symbol, disease name, drug brand, HGNC ID), resolve it first** with the `search` query before any other call.

## Outputs

GraphQL returns JSON shaped exactly like your query. Typical deliverables for the user:

- **Association tables**: target ↔ disease with `score` and per-datatype breakdowns
- **Evidence rows**: individual evidence records (datasource, score, supporting literature/links)
- **Annotation summaries**: target/disease/drug profile data
- **Variant & GWAS data**: credible sets, L2G predictions, colocalisation
- **Resolved IDs** from `search` hits

CSV/TSV export from the JSON is straightforward with `pandas.json_normalize`.

## Clarification Questions

Ask only for missing information. If the user already gave a standard ID and a clear goal, proceed directly.

### 1. **Entity & ID**:
- What entity is the question about — target, disease, drug, variant, or study?
- Do you already have an Ensembl/EFO/ChEMBL/GCST ID, or only a name? *(If only a name, this skill resolves it via `search` first.)*

### 2. **Goal**: Annotation lookup, target–disease associations, supporting evidence, or genetics (variant/GWAS/L2G)?

### 3. **Scope**:
- Single entity? → API is appropriate
- Tens to hundreds across many entities? → still OK with paginated queries
- Thousands or "all targets"? → **stop and recommend bulk downloads instead**

### 4. **Filters / weighting** (associations only): Default scoring, or custom datasource weights (e.g. "genetics-only", "downweight literature")? Roll up evidence through disease ontology descendants (`enableIndirect: true`)?

### 5. **Output**: Print summary, return JSON, or save to CSV/TSV?

## Standard Workflow

**Endpoint:** `https://api.platform.opentargets.org/api/v4/graphql`
**Playground (with built-in schema docs):** `https://api.platform.opentargets.org/api/v4/graphql/browser`

### Step 1 — Helper

```python
import requests

URL = "https://api.platform.opentargets.org/api/v4/graphql"

def ot_query(query: str, variables: dict | None = None) -> dict:
    r = requests.post(URL, json={"query": query, "variables": variables or {}})
    r.raise_for_status()
    payload = r.json()
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]
```

### Step 2 — Resolve names → IDs (only if needed)

```python
QUERY = """
query Search($q: String!) {
  search(queryString: $q, entityNames: ["target","disease","drug"]) {
    hits { id name entity }
  }
}
"""
ot_query(QUERY, {"q": "BRCA1"})
```

### Step 3 — Run the actual query

**Target annotation:**
```python
QUERY = """
query Target($ensemblId: String!) {
  target(ensemblId: $ensemblId) {
    id approvedSymbol biotype
    geneticConstraint { constraintType score oe oeLower oeUpper }
    tractability { label modality value }
  }
}
"""
ot_query(QUERY, {"ensemblId": "ENSG00000169083"})  # AR
```

**Disease → known drugs + top associated targets:**
```python
QUERY = """
query Disease($efoId: String!) {
  disease(efoId: $efoId) {
    id name
    knownDrugs { uniqueDrugs rows { drug { id name isApproved } } }
    associatedTargets(page: { index: 0, size: 25 }) {
      rows {
        target { id approvedSymbol }
        score
        datatypeScores { id score }
      }
    }
  }
}
"""
ot_query(QUERY, {"efoId": "MONDO_0004975"})  # Alzheimer's
```

**Target–disease evidence (filter to specific datasources):**
```python
QUERY = """
query Evidence($ensemblId: String!, $efoId: String!) {
  disease(efoId: $efoId) {
    evidences(ensemblIds: [$ensemblId],
              datasourceIds: ["europepmc","ot_genetics_portal"]) {
      count
      rows { datasourceId score literature }
    }
  }
}
"""
```

**Custom-weighted association scoring** (e.g. "genetics-only"):
```graphql
associatedTargets(
  datasources: [
    { id: "ot_genetics_portal", weight: 1.0, propagate: true, required: true }
    { id: "europepmc",          weight: 0.2, propagate: true, required: false }
  ]
) { rows { target { approvedSymbol } score } }
```

**Drug profile (mechanism, indications, FAERS adverse events):**
```python
QUERY = """
query Drug($chemblId: String!) {
  drug(chemblId: $chemblId) {
    id name drugType maximumClinicalStage
    mechanismsOfAction { rows { mechanismOfAction targetName actionType } }
    indications { count rows { disease { id name } maxClinicalStage } }
    adverseEvents(page: { index: 0, size: 10 }) {
      count
      rows { name count logLR }
    }
  }
}
"""
ot_query(QUERY, {"chemblId": "CHEMBL1201583"})  # bevacizumab
```

**Variant annotation (consequence, allele frequencies, credible-set membership):**
```python
QUERY = """
query Variant($variantId: String!) {
  variant(variantId: $variantId) {
    id chromosome position referenceAllele alternateAllele rsIds
    mostSevereConsequence { id label }
    alleleFrequencies { populationName alleleFrequency }
    transcriptConsequences {
      target { id approvedSymbol }
      variantConsequences { id label }
      isEnsemblCanonical
    }
  }
}
"""
ot_query(QUERY, {"variantId": "19_44908822_C_T"})  # APOE rs7412
```

**GWAS study metadata** (root field `study` for one ID, `studies` for batch):
```python
QUERY = """
query Study($studyId: String!) {
  study(studyId: $studyId) {
    id studyType traitFromSource pubmedId publicationFirstAuthor
    nSamples nCases nControls
    diseases { id name }
    credibleSets(page: { index: 0, size: 10 }) {
      count
      rows { studyLocusId region pValueMantissa pValueExponent }
    }
  }
}
"""
ot_query(QUERY, {"studyId": "GCST005194"})  # CAD GWAS
```

**Credible sets + L2G + colocalisation (the former "Genetics Portal" core query):**
```python
QUERY = """
query CredibleSets($studyIds: [String!]!) {
  credibleSets(page: { index: 0, size: 25 }, studyIds: $studyIds) {
    count
    rows {
      studyLocusId region
      pValueMantissa pValueExponent
      variant { id rsIds mostSevereConsequence { label } }
      l2GPredictions { rows { target { id approvedSymbol } score } }
      colocalisation { rows { otherStudyLocus { studyId } h4 clpp } }
    }
  }
}
"""
ot_query(QUERY, {"studyIds": ["GCST005194"]})
```

### Step 4 — Iterate / paginate

List fields take `page: { index, size }`. Don't fetch thousands of rows in one call; if the user wants more, paginate or switch to bulk downloads.

## Common Issues

| Issue | Solution |
|-------|----------|
| HTTP 200 but `errors` in response | GraphQL errors come back in the body, not as 4xx — always check `payload["errors"]` |
| `Cannot query field "X" on type "Y"` | Schema field name has changed; check the playground or run an introspection query |
| Empty `associatedTargets` for a broad disease | Add `enableIndirect: true` to roll up evidence from descendant ontology terms |
| Symbol/name not recognised | Run a `search` query first; the API only accepts standardised IDs (Ensembl/EFO/ChEMBL/GCST) |
| Truncated results | List fields are paginated — pass `page: { index, size }` and iterate |
| Slow or timing out across many IDs | Stop and switch to bulk downloads (FTP, BigQuery `open-targets-prod`, AWS) |
| Looking for old `api.genetics.opentargets.org` endpoint | Genetics data is now part of the main Platform API; use `variant`, `study`, `credibleSet` fields here |

## Best Practices

1. ✅ **Resolve names → IDs once** with `search`, then cache the IDs
2. ✅ **Request only the fields you need** — GraphQL gives you exactly what you ask for
3. ✅ **Traverse the graph in a single query** instead of chaining requests (e.g. `disease → associatedTargets → target { tractability }`)
4. ✅ **Always check `errors`** in the response body — not just the HTTP status
5. ✅ **Use `enableIndirect: true`** for broad disease terms so descendant evidence is included
6. ✅ **Paginate** lists with `page: { index, size }`
7. ⚠️ **Hand off to bulk downloads** when the user needs thousands of entities — the docs explicitly discourage looping the API
8. ✅ **Cite the data release version** in any report (`meta { dataVersion { year month } }`)

## Related Skills

- **Bulk Open Targets data** — for thousands of entities, use FTP/BigQuery/AWS downloads instead of this skill
- **GWAS / variant annotation skills** — for follow-up on variants returned here
- **ChEMBL** — for deeper drug/compound chemistry beyond what Open Targets exposes
- **EuropePMC literature search** — for the underlying papers behind text-mined evidence

## References

**Official documentation:**
- API landing page: https://platform.opentargets.org/api
- API docs: https://platform-docs.opentargets.org/data-access/graphql-api
- GraphQL playground (with schema): https://api.platform.opentargets.org/api/v4/graphql/browser
- Schema dump: https://api.platform.opentargets.org/api/v4/graphql/schema
- Bulk data downloads: https://platform-docs.opentargets.org/data-access/datasets
- Community / example queries: https://community.opentargets.org/

**Citation:**
- Open Targets Platform: Ochoa et al., *Nucleic Acids Research* (most recent release paper)

**License:** Data CC0 1.0; API free to use.
