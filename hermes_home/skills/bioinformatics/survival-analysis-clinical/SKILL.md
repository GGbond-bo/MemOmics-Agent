---
id: "skill_827c499e76084524a2e098d80383a3a4"
name: "survival-analysis-clinical"
when_to_use: "[survival-analysis-clinical] 临床生存分析：临床信息+表达→Kaplan-Meier→Cox回归→log-rank test→预后标志物"
display-name: "Clinical Survival & Outcome Analysis"
category: Clinical
short-description: "Perform Kaplan-Meier estimation, Cox proportional hazards regression, and risk stratification from clinical time-to-event data."
detailed-description: "Analyze clinical survival outcomes using Kaplan-Meier estimation with log-rank tests, Cox proportional hazards regression with automatic covariate selection, proportional hazards assumption testing (Schoenfeld residuals), and risk stratification (median/tertile/quartile split). Produces publication-quality survival curves with risk tables, forest plots of hazard ratios, and diagnostic plots. Supports TCGA, clinical trial, and real-world evidence datasets. Exports risk scores and analysis objects (RDS) for downstream integration with biomarker panel discovery and multi-omics stratification."
starting-prompt: Run a survival analysis on breast cancer clinical data to identify prognostic factors and stratify patients by risk. Generate a PDF report with an intro, methods, results, conclusions and figures from all of the analyses you perform.
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
- 辩论格式：正方（支持当前参数）vs 反方（质疑+替代方案）→ 裁判决断
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



# Clinical Survival & Outcome Analysis

Kaplan-Meier survival estimation, Cox proportional hazards regression, and risk stratification for clinical and real-world evidence (RWE) datasets.

## When to Use This Skill

Use this skill when you need to:
- **Estimate survival curves** (Kaplan-Meier) with confidence intervals and risk tables
- **Identify prognostic factors** via Cox proportional hazards regression
- **Stratify patients by risk** using Cox model linear predictor
- **Test proportional hazards assumption** with Schoenfeld residuals
- **Compare survival between groups** (molecular subtypes, treatment arms, biomarker levels)
- **Generate forest plots** of hazard ratios for multi-covariate models

**Don't use this skill for:**
- ❌ Biomarker panel selection from omics → use `lasso-biomarker-panel`
- ❌ Differential expression analysis → use `bulk-rnaseq-counts-to-de-deseq2`
- ❌ Disease trajectory / longitudinal modeling → use `disease-progression-longitudinal`
- ❌ Genetic association / Mendelian randomization → use `mendelian-randomization-twosamplemr`

## Installation

```r
options(repos = c(CRAN = "https://cloud.r-project.org"))
if (!require('BiocManager', quietly = TRUE)) install.packages('BiocManager')

# Core (required)
install.packages(c('survival', 'ggplot2', 'ggprism', 'scales'))

# Enhanced KM curves with risk tables (recommended)
install.packages('survminer')

# Example data: TCGA BRCA (optional, needed for tcga_brca demo)
BiocManager::install('RTCGA.clinical')

```

| Software | Version | License | Commercial Use | Installation |
|----------|---------|---------|----------------|-------------|
| survival | >=3.5 | LGPL (>=2) | ✅ Permitted | `install.packages('survival')` |
| ggplot2 | >=3.4 | MIT | ✅ Permitted | `install.packages('ggplot2')` |
| ggprism | >=1.0.3 | GPL (>=3) | ✅ Permitted | `install.packages('ggprism')` |
| scales | >=1.2 | MIT | ✅ Permitted | `install.packages('scales')` |
| survminer | >=0.4.9 | GPL (>=2) | ✅ Permitted | `install.packages('survminer')` |

## Inputs

**Required:**
- **Clinical data** with columns for:
  - **Time-to-event** (numeric: days, months, or years)
  - **Event indicator** (binary: 0 = censored, 1 = event)
- Minimum 50 patients recommended (20+ events for reliable Cox estimates)

**Optional:**
- **Stratification variable** (e.g., molecular subtype, treatment arm, biomarker group)
- **Covariates** for Cox model (age, stage, receptor status, etc.)
- **Pre-computed risk scores** from upstream skills (e.g., `lasso-biomarker-panel`)

**Formats:** CSV/TSV with headers, or R data frame

## Outputs

**Primary results:**
- `cox_coefficients.csv` — Hazard ratios with 95% CI and p-values for all covariates
- `risk_scores.csv` — Patient-level risk scores and risk group assignments
- `clinical_annotated.csv` — Full clinical data with added risk group column
- `survival_summary.csv` — Summary statistics per risk group (N, events, event rate, median survival)
- `ph_assumption_test.csv` — Schoenfeld residual test results (chi-sq, p-value per covariate)

**Analysis objects (RDS):**
- `survival_model.rds` — Complete analysis object for downstream use
  - Load with: `model <- readRDS('results/survival_model.rds')`
  - Contains: KM fits, Cox model, PH test, risk groups, clinical data, metadata
  - Access risk scores: `model$cox$risk_scores`
  - Access Cox model: `model$cox$model`
  - Required for: `lasso-biomarker-panel` (risk scores as features), downstream integration

**Plots (PNG + SVG at 300 DPI):**
- `km_overall.png/.svg` — Overall Kaplan-Meier curve with confidence interval
- `km_stratified.png/.svg` — Stratified survival curves with log-rank p-value
- `forest_plot.png/.svg` — Forest plot of hazard ratios with significance markers
- `km_risk_groups.png/.svg` — Risk group survival curves with log-rank test
- `schoenfeld_diagnostics.png/.svg` — PH assumption diagnostic plots
- `cumulative_hazard.png/.svg` — Cumulative hazard function

**Reports:**
- `survival_report.md` — Comprehensive markdown report
- `survival_report.pdf` — Agent-generated PDF report with Introduction, Methods, Results, Conclusions, and embedded figures

**⚠️ PDF style rules:**
- **US Letter page size (8.5 × 11 in)** — always set page dimensions explicitly; do not rely on library defaults
- **No Unicode superscripts** — use `3.36e-06` or `3.36 × 10^(-6)`, not Unicode superscript chars (they render as ■ in PDF fonts)
- **No half-empty pages** — group headings with their content; only page-break before major sections (Results, Conclusions)
- **Figures ≥80% page width** — multi-panel figures must be large enough to read; never embed below 50% width

## Clarification Questions

🚨 **ALWAYS ask Question 1 FIRST.**

### 1. **Example or Own Data?** (ASK THIS FIRST):
   - **a) TCGA Breast Cancer** (recommended for demo)
     - 1,100+ patients with overall survival, molecular subtypes (HR+/HER2-, HR+/HER2+, HER2+, Triple Negative), stage, age, ER/PR/HER2 status
     - **Requires download** (~50MB via RTCGA.clinical, cached after first run)
   - **b) NCCTG Lung Cancer** (quick demo, no download)
     - 228 advanced lung cancer patients, sex stratification, ECOG performance status
     - Built-in R dataset — runs instantly
   - **c) I have my own clinical data to analyze**
     - Continue to Questions 2-3 below

> **IF EXAMPLE SELECTED (option a or b):** Proceed to Question 2 for analysis options. Skip Question 3.

### 2. **Analysis Options** *(structured — for all datasets)*:
   - **Stratification variable?**
     - a) Default for dataset (mol_subtype for TCGA BRCA, sex for Lung)
     - b) Stage
     - c) Age group
   - **Risk stratification method?**
     - a) Median split — 2 groups (recommended)
     - b) Tertiles — 3 groups
     - c) Quartiles — 4 groups

### 3. **Data Details** *(own data only — free-text OK)*:
   - What is the time column name? Units (days/months/years)?
   - What is the event column name? What does 1 represent (death/relapse/progression)?
   - What stratification variable? What covariates for the Cox model?

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Step 1 - Load data:**
```r
source("scripts/load_example_data.R")
data <- load_example_data(dataset = "tcga_brca")
# OR: data <- load_example_data(dataset = "lung")
# OR: data <- load_user_data("path/to/clinical.csv", time_col = "time", event_col = "status")
```
**DO NOT write custom data loading code. Use the loader functions.**

**✅ VERIFICATION:** You MUST see: `"✓ TCGA BRCA data loaded successfully!"` (or similar)

**Step 2 - Run survival analysis:**
```r
source("scripts/basic_workflow.R")
result <- run_survival_analysis(data)
# Optional: result <- run_survival_analysis(data, risk_strata_method = "tertiles")
# Optional: result <- run_survival_analysis(data, covariates = c("age", "stage"))
```
**DO NOT write inline Cox/KM code (coxph, survfit, etc.). Just source and call.**

**✅ VERIFICATION:** You MUST see: `"✓ Survival analysis completed successfully!"`

**❌ IF YOU DON'T SEE THIS:** You wrote inline code. Stop and use `source()`.

**Step 3 - Generate visualizations:**
```r
source("scripts/survival_plots.R")
generate_all_plots(result, output_dir = "results")
```
🚨 **DO NOT write inline plotting code (ggsave, ggplot, ggsurvplot, etc.). Just use `generate_all_plots()`.** 🚨

**The script handles PNG + SVG export with graceful fallback for SVG dependencies.**

**✅ VERIFICATION:** You MUST see: `"✓ All survival plots generated successfully!"`

**Step 4 - Export results:**
```r
source("scripts/export_results.R")
export_all(result, output_dir = "results")
```
**DO NOT write custom export code. Use `export_all()` to save all outputs including RDS.**

**✅ VERIFICATION:** You MUST see:
- `"=== Export Complete ==="`

⚠️ **CRITICAL - DO NOT:**
- ❌ **Write inline Cox/KM code (coxph, survfit)** → **STOP: Use `source("scripts/basic_workflow.R")`**
- ❌ **Write inline plotting code (ggsave, ggplot, ggsurvplot)** → **STOP: Use `generate_all_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Try to install svglite** → script handles SVG fallback automatically

**⚠️ IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, re-run script
2. **Modify Script (5%)** - Edit the script file itself, document changes
3. **Use as Reference (4%)** - Read script, adapt approach, cite source
4. **Write from Scratch (1%)** - Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

## Common Issues

| Error | Cause | Fix |
|-------|-------|-----|
| **"No valid covariates found"** | All columns have >20% missing or single value | Provide covariates explicitly: `run_survival_analysis(data, covariates = c("age", "stage"))` |
| **"Cox model failed with all covariates"** | Collinear or non-convergent covariates | Script auto-falls back to stepwise. Inspect individual p-values. |
| **PH assumption violated (global p < 0.05)** | Time-varying effects | Note in report. Consider stratified analysis. See `references/cox-regression-guide.md`. |
| **"Event column must be binary (0/1)"** | Non-standard event coding | Recode: e.g., `survival::lung` uses 1=censored, 2=dead → script handles this. |
| **RTCGA.clinical download fails** | Network/firewall issue | Use `dataset = "lung"` as fallback (no download needed). |
| **SVG export failed** | Missing optional dependency | Normal — `generate_all_plots()` falls back automatically. PNG always generated. |
| **KM curve drops steeply despite low event rate** | **Heavy censoring (correct behavior)** | **NOT A BUG.** With heavy censoring (e.g., 90% censored), the at-risk set shrinks so each late event causes a large survival drop. The KM tail (N at risk < 30) is unreliable. Report **landmark survival rates** instead. |
| **Subtype medians have upper CI = NA** | **KM never crosses 50% for that group** | The median is an unreliable extrapolation. The script flags this — use landmark rates instead. Do NOT report these medians as reliable point estimates. |

## Agent Summary Guidelines

When presenting final results to the user, the agent MUST:
1. **Report the C-index** (concordance) from the Cox model — but see EPV rule below
2. **Check `result$median_reliable`** — if FALSE, report "Median survival: Not reached" and use **landmark survival rates** (from `result$landmark_survival`) instead
3. **Report landmark survival rates** (1-year, 3-year, 5-year OS with 95% CI) — these are always more robust than median, especially for low-event datasets
4. **State PH assumption result** (satisfied or violated, with global p-value)
5. **List significant covariates** with HR, 95% CI, and p-value
6. **Report EPV** (events per variable) — if `result$epv < 10`, warn that model may be overfitted
7. **Report excluded patients** — if `result$n_excluded > 0`, note how many were excluded from Cox model
8. **Report risk group separation** (log-rank chi-sq and p-value)
9. **Report PDF status** — if PDF generation failed, say so and note markdown report is available
10. **Never fabricate survival curve descriptions** — reference the actual generated plots
11. **Never report unreliable medians as if they are reliable** — when upper CI = NA, the KM curve did not cross 50% and the median is an unreliable extrapolation
12. **Methods section MUST match actual model** — list only covariates from `names(coef(result$cox$model))`. Check `result$dropped_covariates` and report what was excluded and why. NEVER list covariates from memory; always verify against the fitted model.
13. **Report dropped covariates** — if `result$dropped_covariates` is non-empty, list each dropped variable and reason (rare levels, collinearity) in the Methods section
14. **Report reference groups** — for each categorical covariate, state the reference level and its N (from `result$reference_levels`). If N < 50, flag the HR as "unstable due to small reference group (N=X)"
15. **Report informative missingness** — if any entry in `result$diagnostics$missing_assessment` has `informative = TRUE`, report the event rate comparison prominently and note selection bias risk
16. **Report follow-up anomalies** — if `result$diagnostics$followup_anomaly` is TRUE, investigate and explain prominently. Do NOT dismiss as "expected" without evidence.

⚠️ **CRITICAL REPORTING RULES:**
- **EPV < 10 + C-index:** If `result$epv < 10`, you MUST describe the C-index as "potentially overfitted" or "unreliable". NEVER use "good" or "moderate discrimination" without this caveat. The C-index is optimistically biased when EPV is low.
- **PH violation + forest plot/Cox table:** If global PH test p < 0.05, you MUST include a prominent warning on the forest plot caption AND any Cox results table: "PH assumption violated (p=X) — HRs represent time-averaged effects and may be misleading." Do NOT present HRs as primary findings without this warning.
- **Small reference groups:** If a key finding involves a categorical covariate whose reference group has N < 50, flag the estimate as unstable. State the reference group N explicitly.
- **Never fabricate group sizes or statistics.** All Ns, HRs, CIs, and p-values in the report text MUST be copied from the script console output or exported CSV files. Do NOT estimate, round from memory, or recalculate group sizes. If a number is not in the output, re-run the relevant step or read the exported file.

## Interpretation Guidelines

- **C-index > 0.7:** Good model discrimination — **ONLY if EPV >= 10**. If EPV < 10, say "potentially overfitted (EPV = X)"
- **C-index 0.6-0.7:** Moderate — useful combined with clinical factors
- **C-index ~ 0.5:** No better than chance
- **HR > 1:** Higher hazard (worse prognosis) per unit increase
- **HR < 1:** Lower hazard (protective effect)
- **HR 95% CI includes 1.0:** Not statistically significant
- **PH global p < 0.05:** Proportional hazards assumption violated — HRs are time-averaged and may be misleading. Must be stated prominently on forest plots and Cox tables, not buried in a later section.
- **EPV < 10:** Model underpowered — C-index likely optimistically biased; consider fewer covariates. NEVER call the C-index "good" when EPV < 10.
- **Median survival "Not reached":** KM curve never crosses 50% — use landmark survival rates instead
- **Low event rate (<15%):** KM curves may drop steeply in the tail due to small at-risk set (heavy censoring), not because most patients die. Always check N at risk at each timepoint.
- **Median follow-up < 2 yr with max obs > 5 yr:** Likely a data quality artifact — investigate completeness of follow-up times for censored patients before interpreting results.

## Suggested Next Steps

1. **Biomarker panel discovery** — Use risk scores as features → `lasso-biomarker-panel`
2. **Pathway enrichment** — If molecular subtypes differ → `functional-enrichment-from-degs`
3. **Multi-omics integration** — Combine clinical + omics → `multi-omics-integration-mofa`
4. **Disease trajectory** — Map temporal progression → `disease-progression-longitudinal`
5. **Clinical trial landscape** — Search related interventional trials → `clinicaltrials-landscape`

## Related Skills

| Skill | Relationship |
|-------|-------------|
| `lasso-biomarker-panel` | **Downstream** — Use risk scores as features for biomarker selection |
| `disease-progression-longitudinal` | **Complementary** — Trajectory analysis on same clinical data |
| `multi-omics-integration-mofa` | **Upstream** — Factor scores as Cox covariates |
| `bulk-rnaseq-counts-to-de-deseq2` | **Upstream** — DE results inform covariate selection |
| `coexpression-network` | **Upstream** — Module eigengenes as survival predictors |

## References

- Cox DR. Regression Models and Life-Tables. J R Stat Soc B. 1972;34(2):187-220.
- Kaplan EL, Meier P. Nonparametric Estimation from Incomplete Observations. JASA. 1958;53(282):457-481.
- Cancer Genome Atlas Network. Comprehensive molecular portraits of human breast tumours. Nature. 2012;490:61-70.
- Loprinzi CL, et al. Prospective evaluation of prognostic variables from patient-completed questionnaires. J Clin Oncol. 1994;12:601-607.
- Therneau TM. A Package for Survival Analysis in R. R package survival.
- See [references/cox-regression-guide.md](references/cox-regression-guide.md) for detailed Cox PH interpretation
- See [references/risk-stratification-guide.md](references/risk-stratification-guide.md) for risk group methodology


---

## 🔒 审查与辩论机制（分析 skill 必须执行）

### 执行前审查 (rail_review pre)
使用此 skill 的分析步骤前，**必须**调用 ：
- 检查环境：R/Python 版本、必需包是否安装
- 检查参数：参数来源（知识库/文献/辩论/经验），不能凭空设值
- 检查数据：输入数据格式、细胞数、维度是否合理
- 不通过则阻断，修正后重试

### 执行后审查 (rail_review post)
分析步骤完成后，**必须**调用 ：
- 检查输出：文件是否生成、大小是否合理
- 检查质量：QC 指标、聚类质量、注释置信度
- 检查图表：是否生成了预期图表、图表是否合理
- 不通过则阻断，修正后重试
- **失败时**：调用  记录错误
- **修复成功后**：调用  +  替换脚本

### 多角色辩论 (debate_analysis)
当遇到**不确定的参数选择或结果判断**时，**必须**调用 ：
- 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
- 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
- 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
- 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
- 辩论结果自动归档到 results/.../log/debate_*.json

### 辩论触发场景
- 聚类分辨率选择（0.3 vs 0.5 vs 0.8 vs 1.2）
- QC 阈值设定（MT% 10% vs 15% vs 20%）
- 细胞类型注释争议（marker 不明显时）
- 归一化方法选择（SCT vs LogNormalize）
- 降维参数选择（PC 数量 10 vs 20 vs 30）
- 差异表达阈值（p<0.05 vs p<0.01, logFC 阈值）
- 任何需要多方审视的分析决策


---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="{当前分析} 参数与结果 —— {样本}",
     context="参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<预查的 KB 内容>,
   )
   辩论维度：参数合理性、方法选择正确性、与KB生物学知识一致性、统计方法正确性
3. save_conclusions(module="{模块}", topic="{分析名}", debate_json=<debate返回JSON>, output_dir=<session results_dir>)
   → 写入 {module}/conclusions.md + conclusions.json
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。
⛔ debate confidence=low → 调整参数重跑。
