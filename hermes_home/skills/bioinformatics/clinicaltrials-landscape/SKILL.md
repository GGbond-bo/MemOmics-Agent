---
id: "skill_546a8868863342c093eb2570dcd538f4"
name: "clinicaltrials-landscape"
when_to_use: "[clinicaltrials-landscape] 需使用clinicaltrials landscape功能，适用于相关生信分析场景"
display-name: "ClinicalTrials.gov Disease Landscape Scanner"
category: Clinical
short-description: "Query ClinicalTrials.gov API v2 to map the clinical trial landscape for any disease area by mechanism, phase, and sponsor."
detailed-description: "Programmatically query the free ClinicalTrials.gov API v2 to pull all active clinical trials for a disease area, classify by therapeutic mechanism of action, and generate competitive landscape visualizations. Supports any disease with pre-built configs for IBD (Crohn's, UC). Generic mode classifies by intervention type when no disease config exists. Supports filtering by mechanism, phase, sponsor, and status. Exports structured CSVs, publication-quality plots, and pickle objects for downstream analysis. No API key required."
starting-prompt: Show me the current clinical trial landscape for IBD
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



# ClinicalTrials.gov Disease Landscape Scanner

## When to Use This Skill

- **Map competitive landscape** across therapeutic mechanisms for any disease
- **Track specific mechanism classes** (e.g., anti-IL23, anti-TL1A, JAK inhibitors)
- **Identify sponsors** and their pipeline positions by phase
- **Phase distribution analysis** for business development diligence
- **Pipeline monitoring** for a specific sponsor's disease portfolio
- **Pre-built disease configs** available (IBD with 14 mechanism classes); generic mode for any other disease

**Do NOT use for:**
- Detailed single-trial protocol analysis
- Efficacy/safety comparisons (requires literature review skill)

---

## Installation

| Software | Version | License | Commercial Use | Installation |
|----------|---------|---------|----------------|-------------|
| pandas | ≥1.3 | BSD-3 | ✅ Permitted | `pip install pandas` |
| requests | ≥2.25 | Apache-2.0 | ✅ Permitted | `pip install requests` |
| numpy | ≥1.20 | BSD-3 | ✅ Permitted | `pip install numpy` |
| plotnine | ≥0.10 | MIT | ✅ Permitted | `pip install plotnine` |
| plotnine-prism | ≥0.3 | MIT | ✅ Permitted | `pip install plotnine-prism` |
| seaborn | ≥0.11 | BSD-3 | ✅ Permitted | `pip install seaborn` |
| matplotlib | ≥3.4 | PSF | ✅ Permitted | `pip install matplotlib` |
| reportlab | ≥3.6 | BSD | ✅ Permitted | `pip install reportlab` |
| pyyaml | ≥5.0 | MIT | ✅ Permitted | `pip install pyyaml` |

```bash
pip install pandas requests numpy plotnine plotnine-prism seaborn matplotlib reportlab pyyaml
```

**System requirements:** Internet connection for ClinicalTrials.gov API calls.

---

## Inputs

**Required:**
- **Disease / condition terms** — list of conditions to search ClinicalTrials.gov

**Optional:**
- **Disease config** — pre-built config ID (e.g., `"ibd"`) for mechanism taxonomy, or `None` for generic
- **Mechanism filter** — e.g., "Anti-IL-23 (p19)", "Anti-TL1A", "JAK Inhibitor"
- **Sponsor filter** — e.g., "Takeda", "AbbVie"
- **Status filter** — Default: all active (Recruiting + Active not recruiting + Not yet recruiting)
- **Phase filter** — Phase 1, 2, 3, 4

---

## Outputs

**Visualizations (PNG + SVG):**
- `landscape_overview.png/.svg` — 6-panel landscape figure (300 DPI)
  - Mechanism × Phase heatmap, top sponsors, phase stacked bars, mechanism counts, timeline, sponsor type
- `landscape_supplementary.png/.svg` — 4-panel supplementary figure
  - Top 15 countries, study design by phase, enrollment distribution, phase transition funnel

**Results (CSV):**
- `trials_all.csv` — All trials with 46 columns (mechanism, phase, sponsor, geography, study design, arms, endpoints, eligibility, regulatory)
- `trials_by_mechanism.csv` — Mechanism × phase cross-tabulation
- `trials_by_sponsor.csv` — Sponsor summary with trial counts
- `trials_filtered.csv` — Filtered subset (if mechanism/sponsor filter applied)

**Reports:**
- `landscape_report.pdf` — Publication-quality PDF with 24 sections: executive summary, mechanism deep-dives, geographic landscape, study design, phase transition funnel, endpoint comparison, combination therapies, biosimilar assessment, whitespace analysis, and more
- `landscape_report.md` — Markdown version with identical 24-section structure

**Analysis objects (Pickle):**
- `analysis_object.pkl` — Complete landscape for downstream use
  - Load with: `import pickle; obj = pickle.load(open('analysis_object.pkl', 'rb'))`
  - Contains: trials_df (46 columns), mechanism/phase/sponsor distributions, geographic stats, design stats, parameters

---

## Clarification Questions

1. **Data Source** (ASK THIS FIRST):
   - This skill queries the ClinicalTrials.gov API v2 directly (free, no key needed).
   - **Use live API data?** (recommended, ~30 seconds)
   - **Or use cached demo data?** Pre-loaded IBD landscape snapshot for quick demo

2. **Disease Area:**
   - Which disease area to analyze?
     - a) IBD (Inflammatory Bowel Disease) — pre-built config with 14 mechanism classes
     - b) Oncology (generic intervention-type classification)
     - c) Autoimmune / Rheumatology (generic classification)
     - d) Other (specify disease and condition terms)

3. **Scope** *(if IBD selected)*:
   - Which conditions?
     - a) All IBD (Crohn's, UC, and IBD unspecified) — recommended
     - b) Crohn's Disease only
     - c) Ulcerative Colitis only
   - *(If other disease)* — Provide list of condition search terms

4. **Focus:**
   - Any mechanism or sponsor to highlight?
     - *(IBD)* a) Anti-IL-23 — recommended for demo | b) Anti-TL1A | c) All mechanisms
     - *(Other)* Specify or skip highlighting

---

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Step 1 — Load config and query ClinicalTrials.gov:**
```python
import sys; sys.path.insert(0, ".")
from scripts.disease_config import load_disease_config, get_default_conditions
from scripts.query_clinicaltrials import query_trials

# Load disease config (use "ibd" for IBD, or None for generic)
config = load_disease_config("ibd")

# Get conditions from config or specify manually
conditions = get_default_conditions(config) or ["Crohn's Disease", "Ulcerative Colitis", "Inflammatory Bowel Disease"]

raw_trials = query_trials(
    conditions=conditions,
    statuses=["RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION", "NOT_YET_RECRUITING"],
)
```
**✅ VERIFICATION:** `"✓ Retrieved {N} trials from ClinicalTrials.gov"`

**Step 2 — Classify and compile:**
```python
from scripts.classify_mechanisms import classify_all
from scripts.compile_trials import compile_trials

classified = classify_all(raw_trials, config=config)
trials_df = compile_trials(classified, output_dir="landscape_results")
```
**DO NOT write inline classification code. The script loads mechanism taxonomy from config.**

**✅ VERIFICATION:** `"✓ Trial data compiled successfully!"`

**Step 3 — Generate visualizations:**
```python
from scripts.generate_landscape_plots import generate_landscape_plots

generate_landscape_plots(
    trials_df,
    output_dir="landscape_results",
    highlight_mechanism="Anti-IL-23 (p19)",  # or None for no highlight
    highlight_sponsor=None,                   # or "Takeda" to highlight
    config=config,
)
```
🚨 **DO NOT write inline plotting code. The script handles all 6 panels + PNG/SVG export.** 🚨

**✅ VERIFICATION:** `"✓ All landscape visualizations generated successfully!"`

**Step 4 — Export results:**
```python
from scripts.export_all import export_all

export_all(
    trials_df,
    parameters={
        "conditions": conditions,
        "statuses": ["RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION", "NOT_YET_RECRUITING"],
        "highlight_mechanism": "Anti-IL-23 (p19)",
    },
    output_dir="landscape_results",
    config=config,
)
```
**DO NOT write custom export code. Use export_all().**

**✅ VERIFICATION:** `"=== Export Complete ==="`

---

## ⚠️ CRITICAL — DO NOT:

- ❌ **Write inline classification code** → **STOP: Use `classify_all()` from scripts**
- ❌ **Write inline plotting code (ggplot, plt, sns)** → **STOP: Use `generate_landscape_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Try to scrape ClinicalTrials.gov HTML** → **Use the API via `query_trials()`**

---

## ⚠️ IF SCRIPTS FAIL — Script Failure Hierarchy:

1. **Fix and Retry (90%)** — Install missing package, re-run script
2. **Modify Script (5%)** — Edit the script file itself, document changes
3. **Use as Reference (4%)** — Read script, adapt approach, cite source
4. **Write from Scratch (1%)** — Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

---

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| **ConnectionError / Timeout** | ClinicalTrials.gov unreachable | Check internet connection; retry after 30 seconds |
| **HTTP 429 Too Many Requests** | Rate limit exceeded | Increase `RATE_LIMIT_DELAY` in query_clinicaltrials.py |
| **ModuleNotFoundError: plotnine** | Missing visualization package | `pip install plotnine plotnine-prism` |
| **Empty results (0 trials)** | Overly restrictive filters | Broaden condition/status/phase filters |
| **Many "Unclassified" mechanisms** | No disease config or new drugs | Use a disease config (e.g., `"ibd"`) or update `disease_configs/*.yaml` |
| **SVG export failed** | Missing SVG backend | Normal — PNG is always generated as fallback |
| **Sponsor name variants** | Same company, different names | Update `SPONSOR_NORMALIZATION` in compile_trials.py |
| **ModuleNotFoundError: yaml** | Missing pyyaml | `pip install pyyaml` |

---

## Interpretation Guidelines

- **Mechanism classification** is based on intervention names and descriptions — some trials with vague descriptions (e.g., "Study Drug") will be classified as "Other Biologic" or "Unclassified"
- **Phase 2/3** indicates a combined Phase 2/3 study design
- **Sponsor normalization** groups subsidiaries under parent company (e.g., Millennium → Takeda)
- **Industry vs Academic** based on ClinicalTrials.gov `leadSponsor.class` field
- The landscape reflects **registered trials**, not all pipeline programs (pre-IND programs won't appear)
- **Disease configs** provide curated mechanism taxonomies; without config, classification uses generic intervention types

---

## Suggested Next Steps

1. **Deep-dive a mechanism** — Use `literature-preclinical` to review mechanism biology
2. **Track a sponsor's full pipeline** — Use `development-landscape` for broader pipeline view
3. **Biomarker analysis** — Use `lasso-biomarker-panel` to identify response biomarkers from trial data
4. **Export to presentation** — Use landscape_report.md and plots for stakeholder review

---

## Related Skills

- `development-landscape` — Broader, multi-source pipeline landscape for any target
- `literature-preclinical` — Literature review for mechanism biology
- `lasso-biomarker-panel` — Biomarker discovery from expression data

---

## References

- ClinicalTrials.gov API v2: https://clinicaltrials.gov/data-api/api
- ClinicalTrials.gov: https://clinicaltrials.gov/
- See `references/api-parameters.md` for full API parameter reference
- See `references/mechanisms.md` for mechanism taxonomy details
- See `references/output-schema.md` for output column definitions


## 🔒 审查机制（rail_review）

本 skill 执行代码前**必须**调用  进行前置审查，执行后**必须**调用  进行后置审查。

### 审查内容
- **pre 审查**：环境检查（包是否安装）→ 参数校验（参数是否合理）→ 代码审查（语法/逻辑）→ 硬件检查（内存/GPU是否够）
- **post 审查**：结果质量评估（输出是否合理）→ 图表检查（图是否生成）→ 数值检查（细胞数/基因数是否异常）→ 错误检查（有无 warning/error）

### 审查不通过
- pre 不通过 → **阻断执行**，修正后重新审查
- post 不通过 → **阻断下一步**，修正后重跑，直到通过
- 失败时调用  记录错误
- 修复成功后调用  +  替换脚本
