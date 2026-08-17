---
id: skill_40063c54fad9439a9acd36c76a25983f
name: experimental-design-statistics
when_to_use: "[experimental-design-statistics] 需使用experimental design statistics功能，适用于相关生信分析场景"
category: General Utility
short-description: "Design genomics experiments with power analysis, sample size estimation, batch design, and multiple testing correction."
detailed-description: Guide statistical experimental design for genomics studies including power analysis, sample size estimation, batch-balanced layouts, and multiple testing correction. Use when planning new experiments, justifying sample sizes for grants, optimizing budget constraints (depth vs. replicates), or designing batch structures. Supports RNA-seq, ATAC-seq, scRNA-seq, ChIP-seq, methylation, and proteomics. Includes pilot data-based power estimation, optimal batch assignment algorithms, and modern multiple testing methods (IHW, adaptive shrinkage). Best for pre-experiment planning with 4+ samples per group.
starting-prompt: "Help me design a bulk RNA-seq experiment with power analysis for sample size estimation and a batch-balanced layout. Generate a PDF report with an intro, methods, results, conclusions and figures from all of the analyses you perform."
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



# Experimental Design and Statistical Planning

Comprehensive workflow for statistical experimental design in genomics, from power analysis and sample size determination to batch-balanced experimental layouts and multiple testing strategy.

## When to Use This Skill

Use this skill when you need to:
- ✅ **Plan new experiments** - Design from scratch with statistical rigor
- ✅ **Justify sample sizes** - Calculate required replicates for grant proposals
- ✅ **Perform power analysis** - Determine statistical power for proposed designs
- ✅ **Design batch layouts** - Create balanced assignments preventing confounding
- ✅ **Optimize budgets** - Balance sequencing depth vs. number of replicates
- ✅ **Select correction methods** - Choose appropriate multiple testing approaches

**Don't use this skill for:**
- ❌ Post-experiment analysis → Use appropriate DE analysis skills
- ❌ Simple two-sample comparisons with fixed n → Use power calculators directly

## Installation

| Software | Version | License | Commercial Use | Installation |
|----------|---------|---------|----------------|--------------|
| DESeq2 | ≥1.30.0 | LGPL (≥3) | ✅ Permitted | `BiocManager::install('DESeq2')` |
| RNASeqPower | ≥1.30.0 | LGPL | ✅ Permitted | `BiocManager::install('RNASeqPower')` |
| RnaSeqSampleSize | ≥1.30.0 | GPL (≥2) | ✅ Permitted | `BiocManager::install('RnaSeqSampleSize')` |
| pwr | ≥1.3.0 | GPL (≥3) | ✅ Permitted | `install.packages('pwr')` (qPCR / ΔCt power) |
| IHW | ≥1.18.0 | Artistic-2.0 | ✅ Permitted | `BiocManager::install('IHW')` |
| anticlust | ≥0.8.0 | MIT | ✅ Permitted | `install.packages('anticlust')` |
| ggplot2 | ≥3.3.0 | MIT | ✅ Permitted | `install.packages('ggplot2')` |
| ggprism | ≥1.0.3 | GPL-3 | ✅ Permitted | `install.packages('ggprism')` |
| jsonlite | ≥1.7.0 | MIT | ✅ Permitted | `install.packages('jsonlite')` |
| pasilla | ≥1.18.0 | Artistic-2.0 | ✅ Permitted | `BiocManager::install('pasilla')` |

**Quick install:**
```r
if (!requireNamespace("BiocManager", quietly = TRUE)) install.packages("BiocManager")
BiocManager::install(c("DESeq2", "RNASeqPower", "RnaSeqSampleSize", "IHW", "pasilla"))
install.packages(c("anticlust", "ggplot2", "ggprism", "jsonlite", "pwr"))
```

**Full installation details:** [references/software_requirements.md](references/software_requirements.md)

## Inputs

**Required:**
- **Experimental design info**: Assay type, n conditions, sample relationship, planned n
- **Effect size expectations**: Target fold change, variability (CV or pilot data)
- **Statistical requirements**: Target power (0.80/0.90), α (0.05), multiple testing preference

**Optional:**
- **Practical constraints**: Budget, sample availability, batch structure, sequencing depth, covariates

**Detailed input requirements:** [references/experimental_design_best_practices.md#input-requirements](references/experimental_design_best_practices.md#input-requirements)

## Outputs

**Power and sample size:**
- `power_analysis_results.csv` - Power calculations for scenarios
- `sample_size_recommendation.txt` - Required n with justification
- `power_vs_n_curve.png` + `.svg` - Power relationship visualizations

**Batch design:**
- `batch_layout_for_lab.csv` - Batch assignment template (replace sample IDs with your own when using example data)
- `batch_design_validation.txt` - Confounding check results
- `batch_design_plot.png` + `.svg` - Visual layout

**Documentation:**
- `statistical_analysis_plan.md` - Complete pre-registration plan
- `lab_protocol_checklist.md` - Step-by-step processing guide
- `design_parameters.json` - All parameters (human-readable)

**Analysis objects (RDS) - For downstream use:**
- `batch_design.rds` - Load with: `readRDS('batch_design.rds')` (batch effect correction)
- `design_parameters.rds` - Load with: `readRDS('design_parameters.rds')` (validation, replication)
- `analysis_report.pdf` — Comprehensive PDF report with Introduction, Methods, Results, Conclusions, and embedded figures

**⚠️ PDF style rules:**
- **US Letter page size (8.5 × 11 in)** — always set page dimensions explicitly; do not rely on library defaults
- **No Unicode superscripts** — use `3.36e-06` or `3.36 × 10^(-6)`, not Unicode superscript chars (they render as ■ in PDF fonts)
- **No half-empty pages** — group headings with their content; only page-break before major sections (Results, Conclusions)
- **Figures ≥80% page width** — multi-panel figures must be large enough to read; never embed below 50% width

## Clarification Questions

🚨 **ALWAYS ask Question 1 FIRST. Do not ask about assay type, experimental structure, or design parameters before the user has answered Question 1.**

### 1. **Input Files** (ASK THIS FIRST):
   - **Do you have pilot data or existing results files to inform the experimental design?**
     - If uploaded: Are these pilot data files (DESeq2 objects, count matrices) for power calculations?
     - Expected formats: RDS (DESeqDataSet), CSV/TSV (count matrices)
   - **Or use literature-based estimates?**
     - Tissue-specific variability values from published data — all defaults pre-defined

> 🚨 **IF LITERATURE-BASED ESTIMATES SELECTED (no pilot data):** Use defaults (bulk RNA-seq, 2-group case-control, moderate fold change 1.5x, power 0.90 for grants, BH-FDR). **DO NOT ask questions 2-7, EXCEPT:** ask the user to select their approximate sample type for CV estimation:
>
> **Sample type (determines biological variability CV):**
> - a) Cell lines (CV ≈ 0.2 — low variability)
> - b) Sorted cells / PBMCs (CV ≈ 0.4 — moderate) **(default)**
> - c) Whole tissue biopsies (CV ≈ 0.5 — moderate-high)
> - d) Heterogeneous clinical samples (CV ≈ 0.6 — high variability)
> - e) Not sure — use default CV = 0.4 with sensitivity analysis
>
> Pass the selected CV and tissue label to `generate_design_recommendation(cv = X, tissue_type = "label")`. Then proceed directly to Step 1.

**Questions 2-7 are ONLY for users providing their own pilot data or specifying custom parameters:**

### 2. **Assay Type**: Bulk RNA-seq, scRNA-seq, ATAC-seq, ChIP-seq, methylation, proteomics, or other?
### 3. **Experimental Structure**: Number of conditions (2 case-control, 3+ multi-group, factorial)? Planned n? Sample type (independent/paired/repeated)? Covariates (sex, age, batch, site)?
### 4. **Effect Size & Variability**: Target fold change (large ≥2x, moderate 1.5-2x, small 1.2-1.5x)? Pilot data available?
### 5. **Statistical Requirements**: Power (0.80 standard, 0.90 grants)? Alpha (0.05 standard, 0.01 stringent)? Multiple testing (BH-FDR standard, IHW, Bonferroni)?
### 6. **Practical Constraints**: Budget/max samples? Sample availability? Batch structure? Sequencing depth target?
### 7. **Primary Objective**: Power analysis, sample size, batch design, multiple testing guidance, complete design, or budget optimization?

**Comprehensive clarification guide:** [references/experimental_design_best_practices.md#clarification-questions](references/experimental_design_best_practices.md#clarification-questions)

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

The experimental design workflow follows 4 steps: **Load** → **Calculate** → **Visualize** → **Export**

### **Step 1 - Load Parameters**

```r
source("scripts/load_example_data.R")
pilot_data <- load_example_data()
```

**With pilot data (preferred):**
- Uses `pilot_data$dds` for power calculations
- Uses `pilot_data$cv$median` for sample size estimation
- Provides realistic variability estimates

**Without pilot data (alternative):**
```r
source("scripts/load_example_data.R")
cv_db <- load_cv_database()
# Select appropriate tissue type from cv_db
```

**✅ VERIFICATION:** You MUST see: `"✓ Example pilot data loaded successfully!"`

**Decision:** Pilot data provides more accurate estimates. See [power_analysis_guidelines.md#pilot-vs-literature](references/power_analysis_guidelines.md#pilot-vs-literature)

---

### **Step 2 - Calculate Design**

🚨 **DO NOT write inline calculation code. Use the provided scripts.**

**A. Power Analysis** - Calculate power for your proposed design
```r
source("scripts/power_rnaseq.R")
power_result <- calc_power_rnaseq(
  depth = 20,
  n_per_group = 6,
  cv = pilot_data$cv$median,
  fold_change = 1.5,
  alpha = 0.05
)
```
**DO NOT write inline power calculation code. Just source the script and call the function.**

**B. Sample Size Determination** - Calculate required n

**With pilot data:**
```r
source("scripts/sample_size_de.R")
required_n <- samplesize_from_pilot(
  pilot_dds = pilot_data$dds,
  fold_change = 1.5,
  power = 0.9,
  fdr = 0.05
)
```

**Without pilot data (literature-based CV):**
```r
source("scripts/sample_size_de.R")
required_n <- calc_samplesize_de(cv = 0.40, fold_change = 1.5, power = 0.9, fdr = 0.05)
```
**DO NOT write inline sample size code. Use the functions from the script.**

**C. Batch Assignment** - Generate balanced batch layout for planned experiment
```r
source("scripts/batch_assignment.R")
batch_design <- assign_samples_to_batches(
  metadata = pilot_data$planned_metadata,
  batch_size = 10,
  balance_vars = c("condition", "sex")
)
```
**DO NOT manually create batch assignments. Use the anticlust-optimized function.**

**D. Design Recommendation** (ALWAYS run this)
```r
source("scripts/power_rnaseq.R")
recommendation <- generate_design_recommendation(
  cv = pilot_data$cv$median, target_fc = 1.5, target_power = 0.90
)
```
🚨 **This produces the complete, honest sample size recommendation with per-gene AND FDR-aware power. DO NOT make your own sample size recommendation — use this output directly. The function flags when targets cannot be practically met.**

**E. qPCR / ΔCt Power (continuous readout, NOT count data)** — use for qPCR / RT-qPCR / ddPCR designs analysed on the ΔCt (delta-Ct) scale, where the effect is a difference in cycle threshold and the test is a t-test (2 groups) or one-way ANOVA (3+ groups). The count-data functions above (RNASeqPower/DESeq2/ssizeRNA) do **not** apply to qPCR.
```r
source("scripts/power_qpcr.R")

# Smallest number of BIOLOGICAL replicates for target power
ss <- samplesize_qpcr_ddct(
  delta_ct = 1.0,        # ΔΔCt effect in Ct units (1 Ct ≈ 2-fold)
  sd_biological = 0.8,   # BIOLOGICAL ΔCt SD (prior ~0.5-1.0 Ct), NOT technical (~0.1-0.3)
  power = 0.9, test = "t",
  n_contrasts = 4, correction = "holm"   # multiple-testing correction of alpha
)

# Power at a proposed n, and sensitivity to the (uncertain) biological SD
pw   <- calc_power_qpcr_ddct(delta_ct = 1.0, sd_biological = 0.8, n_biological = 5,
                             test = "t", n_contrasts = 4, correction = "holm")
sens <- sensitivity_qpcr_over_sd(delta_ct = 1.0, n_biological = ss$required_n_biological,
                                 sd_range = c(0.4, 0.6, 0.8, 1.0),
                                 test = "t", n_contrasts = 4, correction = "holm")
```
- Cohen's d = `delta_ct / sd_biological` (t-test); ANOVA uses Cohen's f. Effect size, `effective_alpha` (after correction), `power`, and the `assumptions` are returned.
- **The unit is BIOLOGICAL replicates and `sd_biological` is the biological ΔCt SD** — this is enforced (see below). DO NOT supply a technical well-to-well SD.

🚨 **ENFORCED: biological vs. technical replication.** Replication unit is no longer just a documentation note — it is checked in code:
- `calc_power_qpcr_ddct()` / `samplesize_qpcr_ddct()` call `assert_biological_replication()`, which **stops with an error** if `sd_type = "technical"` or `n_unit = "technical"`. qPCR/ΔCt power MUST use the biological ΔCt SD (~0.5–1.0 Ct) and count biological replicates; technical replicates (~0.1–0.3 Ct well-to-well) are pseudoreplication and powering off them produces a badly underpowered design.
- The count-data functions (`calc_power_rnaseq`, `calc_sample_size_rnaseq`, `calc_samplesize_de`, `calc_power_atac`) take `n_unit = "biological"` (default) and **warn** if `n_unit = "technical"` is chosen. The statistics are unchanged; the warning flags that the CV/dispersion is biological and the result should be read as biological replicates.
- To check a unit/SD directly: `assert_biological_replication(n_unit, sd_type, context = "...")`.

⚠️ **CRITICAL - DO NOT:**
- ❌ Write inline power calculation code → **STOP: Use calc_power_rnaseq()**
- ❌ Write inline plotting code (ggsave, ggplot, etc.) → **STOP: Use visualization scripts**
- ❌ Manually assign samples to batches → **STOP: Use assign_samples_to_batches()**
- ❌ Write custom balancing algorithms → **STOP: Script uses anticlust optimal algorithms**
- ❌ Make your own sample size recommendation → **STOP: Use generate_design_recommendation()**
- ❌ Try to install svglite → scripts handle SVG fallback automatically

**⚠️ IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, re-run script
2. **Modify Script (5%)** - Edit the script file itself, document changes
3. **Use as Reference (4%)** - Read script, adapt approach, cite source
4. **Write from Scratch (1%)** - Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

**✅ VERIFICATION:** You should see:
- After power analysis: `"✓ Power analysis completed successfully!"`
- After sample size: `"✓ FDR-aware sample size estimation completed successfully!"`
- After batch design: `"✓ Batch design generated successfully!"`
- After recommendation: `"✓ Design recommendation generated successfully!"`
- After qPCR power: `"✓ qPCR ΔCt power analysis completed successfully!"` / `"✓ qPCR ΔCt sample size estimation completed successfully!"`

**CRITICAL RULE:** Batch must NEVER confound with condition. See [batch_effect_mitigation.md#cardinal-rule](references/batch_effect_mitigation.md#cardinal-rule)

**Decision points:**
- Power ≥0.80? If not, increase n or adjust expectations. See [power_analysis_guidelines.md#interpreting-power](references/power_analysis_guidelines.md#interpreting-power)
- Required n exceed budget? See [budget optimization](references/experimental_design_best_practices.md#budget-optimization)
- Confounding detected? Regenerate with different constraints. See [batch_effect_mitigation.md#troubleshooting](references/batch_effect_mitigation.md#troubleshooting)

---

### **Step 3 - Visualize Design**

**A. Generate power curves:**
```r
source("scripts/plot_power_curves.R")
plot_power_vs_samplesize(
  cv = pilot_data$cv$median,
  fold_changes = c(1.5, 2, 3),
  depth = 20,
  output_file = "design_results/power_vs_n"
)
```

**B. Validate and visualize batch design:**
```r
source("scripts/batch_validation.R")
confounding_check <- check_confounding(batch_design, "condition")
# Check covariates are not confounded with condition (batch balancing cannot fix this)
check_covariate_condition_balance(batch_design, "condition", c("sex", "age_group"))
visualize_batch_design(
  batch_design,
  condition_var = "condition",
  output_file = "design_results/batch_design"
)
```

🚨 **DO NOT write inline plotting code (ggsave, ggplot, etc.). Use the visualization scripts.** 🚨

**The scripts handle PNG + SVG export with graceful fallback for SVG dependencies.**

**✅ VERIFICATION:** You should see:
- `"Saving power curve plots:"` followed by PNG + SVG file paths
- `"PASS: No confounding detected"` or `"WARNING: Batch is CONFOUNDED"`
- `"Saving batch design plots:"` followed by PNG + SVG file paths

---

### **Step 4 - Export All Results**

```r
source("scripts/export_design.R")
export_complete_design(batch_design, design_params, output_dir = "design_results")
```

**DO NOT write custom export code. Use export_complete_design().**

**✅ VERIFICATION:** You MUST see: `"=== Export Complete ==="`

This will generate:
1. `batch_layout_for_lab.csv` - Batch assignment template (replace sample IDs with your own data)
2. `statistical_analysis_plan.md` - Pre-registration analysis plan
3. `lab_protocol_checklist.md` - Lab processing checklist
4. `batch_design.rds` - Batch design object (for downstream use)
5. `design_parameters.rds` - Design parameters (for downstream use)
6. `design_parameters.json` - Design parameters (human-readable)

**RDS objects are CRITICAL** for downstream workflows and validation studies.

---

### **Complete Workflow Example**

For a complete experimental design with all steps:

```r
# Step 1: Load pilot data
source("scripts/load_example_data.R")
pilot_data <- load_example_data()

# Step 2: Calculate design parameters
source("scripts/power_rnaseq.R")
source("scripts/sample_size_de.R")
source("scripts/batch_assignment.R")

power_result <- calc_power_rnaseq(depth = 20, n_per_group = 6, cv = pilot_data$cv$median, fold_change = 1.5)
required_n <- samplesize_from_pilot(pilot_data$dds, fold_change = 1.5, power = 0.9)
recommendation <- generate_design_recommendation(cv = pilot_data$cv$median, target_fc = 1.5,
                                                  target_power = 0.90)
batch_design <- assign_samples_to_batches(pilot_data$planned_metadata, batch_size = 10,
                                          balance_vars = c("condition", "sex"))

# Step 3: Visualize and validate
source("scripts/plot_power_curves.R")
source("scripts/batch_validation.R")

plot_power_vs_samplesize(cv = pilot_data$cv$median, fold_changes = c(1.5, 2, 3),
                         output_file = "design_results/power_vs_n")
check_confounding(batch_design, "condition")
visualize_batch_design(batch_design, "condition", output_file = "design_results/batch_design")

# Step 4: Export all results
source("scripts/export_design.R")
design_params <- list(assay = "RNA-seq", conditions = c("control", "treated"),
                     n_per_group = required_n$required_n_per_group, power = 0.90,
                     alpha = 0.05, effect_size = 1.5, multiple_testing = "BH-FDR")
export_complete_design(batch_design, design_params, output_dir = "design_results")
```

**Note:** Specific parameters depend on your experimental requirements (see Clarification Questions).

## Decision Guide

- **Pilot vs Literature:** Use pilot data if available (more accurate). Literature CV acceptable as fallback.
- **Sample Size vs Depth:** Prioritize more samples over deeper sequencing for DE. 15-20M reads sufficient.
- **Multiple Testing:** BH-FDR (standard), IHW (more power), Bonferroni (stringent).

**See:** [experimental_design_best_practices.md#decision-guide](references/experimental_design_best_practices.md#decision-guide) for comprehensive guidance.

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Power <0.80 with max budget | Effect size too small or CV too high | Increase n, increase depth, or revise effect size expectations. See [references/power_analysis_guidelines.md#low-power](references/power_analysis_guidelines.md#low-power) |
| Batch confounding detected | Unequal condition distribution across batches | Regenerate with stricter balance constraints or adjust batch size. See [references/batch_effect_mitigation.md#troubleshooting](references/batch_effect_mitigation.md#troubleshooting) |
| Required n exceeds sample availability | Pilot data shows high variability or small effect | Consider paired design, blocking by major covariates, or revise target fold-change. See [references/experimental_design_best_practices.md#budget-optimization](references/experimental_design_best_practices.md#budget-optimization) |
| Can't balance all covariates | Too many variables for batch size | Prioritize key covariates (condition > sex > age > others). Some minor imbalance acceptable. See [references/batch_effect_mitigation.md#covariate-priority](references/batch_effect_mitigation.md#covariate-priority) |
| CV estimate varies widely | Pilot data has outliers or low counts | Filter low-count genes (mean <10) before CV calculation. Use median, not mean CV. See [references/power_analysis_guidelines.md#cv-estimation](references/power_analysis_guidelines.md#cv-estimation) |
| Power calculations give n<3 | Very large effect size or low variability | Warning: n<3 too low for valid inference. Plan for minimum n=3-4 even if calculations suggest n=2 |
| Power seems high but few DE genes found | **Per-gene vs. experiment-wide power** | Use `generate_design_recommendation()` which reconciles both. Or use `calc_samplesize_de()` / `samplesize_from_pilot()` for FDR-aware n. |
| qPCR design powered off a tiny SD looks great but fails | **Technical SD used where biological is required** | qPCR/ΔCt power needs the biological ΔCt SD (~0.5–1.0 Ct), not technical (~0.1–0.3 Ct). `calc_power_qpcr_ddct()` errors via `assert_biological_replication()` if `sd_type='technical'`. Supply the SD of per-sample ΔCt across biological replicates. |
| qPCR power calculation: "Package 'pwr' is required" | **pwr not installed** | `install.packages('pwr')`. The qPCR module uses `pwr.t.test` / `pwr.anova.test`. |
| Multiple testing correction too stringent | Many tests, low discovery rate | Consider IHW (more powerful than BH-FDR) or independent filtering. See [references/multiple_testing_guide.md#choosing](references/multiple_testing_guide.md#choosing) |
| **SVG export error** | **Missing optional dependency or system library** | **Normal - scripts fall back automatically. Both PNG and SVG will be created in most environments.** |
| **"cannot open file 'Rplots.pdf'"** | **Default PDF device in non-interactive/container environment** | **Re-run the plotting function — scripts suppress this automatically. If persists, run `pdf(NULL)` before plotting.** |
| **FDR column blank in power table** | **RnaSeqSampleSize not installed** | **Install with `BiocManager::install('RnaSeqSampleSize')`. Per-gene power still valid but underestimates required n.** |
| **Covariate confounded with condition** | **Unequal covariate distribution across conditions** | **Batch balancing cannot fix this. Either balance covariates within conditions, or include in DE model (`~ covariate + condition`).** |

**Detailed troubleshooting:** [references/troubleshooting_guide.md](references/troubleshooting_guide.md)

## Suggested Next Steps

1. **Execute Experiment** - Use batch assignment file to guide sample processing
2. **Perform DE Analysis** - Use bulk-rnaseq-counts-to-de-deseq2 or appropriate skill
3. **Apply Multiple Testing** - Use `source("scripts/multiple_testing.R"); recommend_method(...)` to compare IHW vs BH-FDR
4. **Validate Results** - Check batch effects were controlled, verify power calculations

## Related Skills

**Upstream:** None - this is typically the first step in a project

**Downstream (after data collection):**
- **bulk-rnaseq-counts-to-de-deseq2** - Differential expression analysis
- **functional-enrichment-from-degs** - Pathway analysis
- **de-results-to-plots** - Visualization

**Alternative/complementary:**
- **bulk-omics-clustering** - Discover natural groupings post-hoc
- **batch-correction-combat** - Computational batch correction if needed

## References

**Detailed documentation:**
- [references/experimental_design_best_practices.md](references/experimental_design_best_practices.md) - General design principles, decision guide, common patterns
- [references/power_analysis_guidelines.md](references/power_analysis_guidelines.md) - Detailed power calculation methods, pilot vs literature
- [references/batch_effect_mitigation.md](references/batch_effect_mitigation.md) - Preventing/controlling batch effects, cardinal rule, troubleshooting
- [references/multiple_testing_guide.md](references/multiple_testing_guide.md) - Choosing correction methods
- [references/qc_guidelines.md](references/qc_guidelines.md) - Quality control checkpoints
- [references/troubleshooting_guide.md](references/troubleshooting_guide.md) - Common problems and solutions
- [references/software_requirements.md](references/software_requirements.md) - Installation and licenses
- [references/cv_tissue_database.csv](references/cv_tissue_database.csv) - Tissue-specific variability estimates

**Scripts:** See scripts/ directory for all analysis functions:
- Data loading: [load_example_data.R](scripts/load_example_data.R)
- Power/sample size: [power_rnaseq.R](scripts/power_rnaseq.R), [power_atacseq.R](scripts/power_atacseq.R), [sample_size_de.R](scripts/sample_size_de.R), [sample_size_scrna.R](scripts/sample_size_scrna.R)
- qPCR / ΔCt power (continuous readout, `pwr`): [power_qpcr.R](scripts/power_qpcr.R) — `calc_power_qpcr_ddct`, `samplesize_qpcr_ddct`, `sensitivity_qpcr_over_sd`, `assert_biological_replication`
- Batch design: [batch_assignment.R](scripts/batch_assignment.R), [batch_validation.R](scripts/batch_validation.R)
- Visualization: [plot_power_curves.R](scripts/plot_power_curves.R)
- Export: [export_design.R](scripts/export_design.R) (includes RDS saving)

**Key Papers:**
- Hart SN et al. (2013) *J Comput Biol* 20(12):970-978 - RNA-seq sample size
- Li CI et al. (2018) *BMC Bioinformatics* 19:191 - RnaSeqSampleSize (FDR-aware power)
- Papenberg M & Klau GH (2021) *Psychol Methods* 26(2):161-174 - Anticlustering (batch balance)
- Schurch NJ et al. (2016) *RNA* 22(6):839-851 - Biological replicates needed
- Leek JT et al. (2010) *Nat Rev Genet* 11(10):733-739 - Batch effects impact
- Benjamini & Hochberg (1995) *J R Stat Soc Series B* 57(1):289-300 - FDR control
- Love MI et al. (2014) *Genome Biol* 15(12):550 - DESeq2 methods


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
