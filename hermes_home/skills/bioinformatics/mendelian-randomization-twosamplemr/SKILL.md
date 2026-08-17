---
id: "skill_6655c68c5e9249eba44e6519b7c0b11e"
name: "mendelian-randomization-twosamplemr"
when_to_use: "[mendelian-randomization-twosamplemr] 需使用mendelian randomization twosamplemr功能，适用于相关生信分析场景"
display-name: "Two-Sample Mendelian Randomization"
category: GWAS/Genetics
short-description: "Assess causal relationships between traits using GWAS summary statistics and genetic instruments."
detailed-description: "Performs two-sample Mendelian Randomization (MR) analysis using genetic variants as instrumental variables to test causal effects of an exposure on an outcome. Supports OpenGWAS database access and user-provided GWAS summary statistics. Applies IVW, MR-Egger, weighted median, and weighted mode methods with comprehensive sensitivity analyses."
starting-prompt: "I want to test whether LDL cholesterol has a causal effect on coronary heart disease using Mendelian Randomization."
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



# Two-Sample Mendelian Randomization

## When to Use This Skill

- You have **GWAS summary statistics** for an exposure and outcome trait
- You want to test **causal direction** between two traits (not just correlation)
- You need to assess whether an observed association is likely causal or confounded
- You want to use **genetic variants as instrumental variables** (natural experiment)
- You have OpenGWAS trait IDs **or** your own GWAS summary statistics files

**Not suitable for:** One-sample MR (individual-level data), non-linear MR, multivariable MR with >2 exposures

## Installation

```r
install.packages(c("remotes", "ggplot2", "ggprism", "dplyr", "rmarkdown"))
remotes::install_github("MRCIEU/TwoSampleMR")
# For PDF report generation (optional but recommended):
# install.packages("tinytex"); tinytex::install_tinytex()
# For MR-PRESSO outlier detection (optional but recommended):
# remotes::install_github("rondolab/MR-PRESSO")
```

| Software | Version | License | Commercial Use |
|----------|---------|---------|----------------|
| TwoSampleMR | ≥0.5.6 | GPL-3 | ✅ Permitted |
| ieugwasr | ≥0.2.1 | MIT | ✅ Permitted |
| ggplot2 | ≥3.4.0 | MIT | ✅ Permitted |
| ggprism | ≥1.0.3 | GPL (≥3) | ✅ Permitted |
| dplyr | ≥1.1.0 | MIT | ✅ Permitted |
| rmarkdown | ≥2.20 | GPL-3 | ✅ Permitted |

## Inputs

**Option A — OpenGWAS IDs (recommended):**
- Exposure ID (e.g., `"ieu-a-300"` for LDL cholesterol)
- Outcome ID (e.g., `"ieu-a-7"` for coronary heart disease)
- Browse available traits at: https://gwas.mrcieu.ac.uk/

**Option B — User-provided files (CSV/TSV):**
- Exposure GWAS summary statistics
- Outcome GWAS summary statistics

| Required Column | Description | Example |
|----------------|-------------|---------|
| SNP | rsID | rs1234567 |
| beta | Effect estimate | 0.05 |
| se | Standard error | 0.01 |
| pval | P-value | 5e-10 |
| effect_allele | Effect allele | A |
| other_allele | Other allele | G |
| eaf | Effect allele frequency (optional) | 0.3 |

## Outputs

**Results (CSV):**
- `mr_results.csv` — MR estimates from all 4 methods (beta, SE, p-value, nSNP, F-statistics)
- `heterogeneity_results.csv` — Cochran's Q test for instrument heterogeneity
- `pleiotropy_results.csv` — MR-Egger intercept test for directional pleiotropy
- `directionality_results.csv` — Steiger test confirming causal direction
- `harmonized_data.csv` — SNP-level harmonized exposure-outcome data
- `single_snp_results.csv` — Per-SNP Wald ratio estimates
- `leaveoneout_results.csv` — Leave-one-out robustness estimates
- MR-PRESSO outlier results (if heterogeneity significant and MRPRESSO installed)

**Plots (PNG + SVG):**
- `mr_scatter_plot` — SNP-exposure vs SNP-outcome with method regression lines
- `mr_forest_plot` — Individual + combined SNP effect estimates
- `mr_funnel_plot` — Precision vs effect size (asymmetry = pleiotropy)
- `mr_leaveoneout_plot` — Effect stability when removing each SNP

**Report:**
- `mr_report.pdf` — Structured analysis report (Introduction, Methods, Results, Figures, Conclusions)

**Analysis objects (RDS):**
- `mr_object.rds` — Complete analysis (results, sensitivity, harmonized data)
  - Load with: `mr_obj <- readRDS("mr_results/mr_object.rds")`

## Clarification Questions

1. **Input Data** (ASK THIS FIRST):
   - Do you have specific **GWAS summary statistics** or **OpenGWAS trait IDs**?
   - If files uploaded: Are these the exposure and outcome GWAS files?
   - Expected formats: CSV/TSV with SNP, beta, se, pval, effect_allele, other_allele
   - **Or use example data?** LDL Cholesterol → Coronary Heart Disease demo (drug-target validation example)

2. **Exposure and Outcome**:
   - *(If using example data)* Pre-set: Exposure = LDL Cholesterol, Outcome = Coronary Heart Disease — no need to specify
   - *(If using your own data)* What is the **exposure** (potential cause)? What is the **outcome** (potential effect)?

3. **Parameters** (defaults usually fine):
   - P-value threshold for instruments? (default: 5×10⁻⁸)
   - LD clumping r²? (default: 0.001)

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN — DO NOT WRITE INLINE CODE** 🚨

**Step 1 — Load and harmonize data:**
```r
source("scripts/load_data.R")
dat <- load_example_data()
# OR: dat <- load_from_opengwas("ieu-a-300", "ieu-a-7")
# OR: dat <- load_from_files("exposure.csv", "outcome.csv")
```
**DO NOT write inline data loading or harmonization code. Use the functions above.**

✅ **VERIFICATION:** You MUST see `"✓ Data loaded and harmonized successfully!"`

**Step 2 — Run MR analysis:**
```r
source("scripts/run_mr_analysis.R")
mr_results <- run_mr(dat)
sensitivity <- run_sensitivity(dat, mr_results)
```
**DO NOT write inline MR code. Just source the script and call the functions.**

✅ **VERIFICATION:** You MUST see `"✓ MR analysis completed successfully!"` AND `"✓ Sensitivity analyses completed successfully!"`

**Step 3 — Generate visualizations:**
```r
source("scripts/mr_plots.R")
generate_all_plots(mr_results, dat, sensitivity$singlesnp, sensitivity$leaveoneout, output_dir = "mr_results")
```
🚨 **DO NOT write inline plotting code (ggsave, ggplot, etc.). Just use the function.** 🚨

✅ **VERIFICATION:** You MUST see `"✓ All MR plots generated successfully!"`

**Step 4 — Export results and generate report:**
```r
source("scripts/export_results.R")
export_all(mr_results, sensitivity, dat, output_dir = "mr_results")
```
**DO NOT write custom export code. Use export_all(). It automatically generates the PDF report.**

✅ **VERIFICATION:** You MUST see `"✓ Report generated successfully!"` AND `"=== Export Complete ==="`

❌ **IF YOU DON'T SEE VERIFICATION MESSAGES:** You wrote inline code. Stop and use the scripts.

⚠️ **CRITICAL — DO NOT:**
- ❌ **Write inline MR analysis code** → **STOP: Use `run_mr()` and `run_sensitivity()`**
- ❌ **Write inline plotting code** → **STOP: Use `generate_all_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Write custom report code** → **STOP: Use `generate_report()`**
- ❌ **Try to install system dependencies** → Scripts handle package installation

⚠️ **IF SCRIPTS FAIL — Script Failure Hierarchy:**
1. **Fix and Retry (90%)** — Install missing R package, re-run script
2. **Modify Script (5%)** — Edit the script file, document changes
3. **Use as Reference (4%)** — Read script, adapt approach, cite source
4. **Write from Scratch (1%)** — Only if genuinely impossible, explain why

## Common Issues

| Issue | Cause | Solution |
|-------|-------|---------|
| **"No instruments found"** | No SNPs below p-value threshold | Try a less stringent threshold or check trait ID |
| **LD clumping API fails** | OpenGWAS/IEU API temporarily down | Script falls back to no clumping with warning; results may be affected by LD |
| **"Only N SNPs retained"** | Allele harmonization removed most SNPs | Check if exposure/outcome are from same genome build |
| **Steiger test fails** | Sample sizes unavailable in metadata | Normal for some datasets; other sensitivity tests still valid |
| **SVG export error** | Missing optional dependency | Normal — `generate_all_plots()` falls back to base R svg() automatically |
| **OpenGWAS rate limiting** | Too many API requests | Wait a few minutes and retry |
| **PDF report fails** | LaTeX/tinytex not installed | Install with `tinytex::install_tinytex()` — report auto-falls back to HTML or base R PDF |
| **Steiger R² warning for binary outcome** | Outcome is case-control, not quantitative | Use `get_r_from_lor()` with prevalence to compute liability-scale R² before directionality test |
| **MR-PRESSO not available** | MRPRESSO package not installed | `remotes::install_github('rondolab/MR-PRESSO')` — optional but recommended when heterogeneity is significant |
| **"Cannot find function"** | Script not sourced | Run `source("scripts/load_data.R")` before calling functions |

## Interpreting Results

See [references/interpretation-guide.md](references/interpretation-guide.md) for detailed guidance.

**Quick interpretation:**
- **Concordant methods** (IVW, Egger, WM, WMode agree on direction + significance) → stronger evidence
- **Any method non-significant or discordant** → must be discussed explicitly, not dismissed
- **IVW significant + no heterogeneity + no pleiotropy** → strongest evidence
- **Egger intercept p < 0.05** → directional pleiotropy may bias IVW
- **High heterogeneity (Q p < 0.05)** → run MR-PRESSO, flag outlier instruments
- **Steiger direction incorrect** → reverse causation concern (check binary outcome R² correction)
- **F-statistic < 10** → weak instrument bias toward the null

## Suggested Next Steps

- **Multiple exposures?** → Run bidirectional MR (swap exposure/outcome)
- **Pleiotropy detected?** → Consider MR-PRESSO or multivariable MR
- **Significant result?** → Replicate with independent GWAS datasets
- **Drug target validation?** → Use cis-MR with variants near gene of interest
- **Pathway analysis?** → Combine with functional enrichment skills

## Related Skills

- `polygenic-risk-score` — Polygenic risk score computation (LDpred2)
- `polygenic-risk-score-prs-catalog` — PRS from pre-computed PGS Catalog weights
- `eqtl-colocalization-coloc` — eQTL colocalization analysis (MR follow-up)

## References

- Sanderson E, et al. (2022). Mendelian randomization. *Nat Rev Methods Primers*. [PMC7384151](https://pmc.ncbi.nlm.nih.gov/articles/PMC7384151/)
- Hemani G, et al. (2018). The MR-Base platform supports systematic causal inference across the human phenome. *eLife*. DOI: 10.7554/eLife.34408
- TwoSampleMR package: https://github.com/MRCIEU/TwoSampleMR
- OpenGWAS database: https://gwas.mrcieu.ac.uk/
- STROBE-MR guidelines: https://doi.org/10.1001/jama.2023.1788


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

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="{当前分析} 参数与结果 —— {样本}",
     context="参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<KB内容>,
   )
3. save_conclusions(module="{模块}", topic="{分析名}", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。
⛔ debate confidence=low → 调整参数重跑。
