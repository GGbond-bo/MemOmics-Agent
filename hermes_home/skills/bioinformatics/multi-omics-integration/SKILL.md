---
id: "skill_b022f7a4010244ac8956c13d9dd60967"
name: "multi-omics-integration"
when_to_use: "[multi-omics-integration] 多组学数据整合：scRNA+scATAC+蛋白→MOFA/WNN/seurat5→联合降维→跨组学聚类"
display-name: "Multi-Omics Integration (MOFA+)"
category: Multi-omics
short-description: "Integrate 2+ omics layers using MOFA+ to identify latent factors explaining cross-omics variation, with variance decomposition and factor interpretation."
detailed-description: "Performs multi-omics factor analysis using MOFA2 to decompose multi-omics datasets into interpretable latent factors. Handles missing data across views, identifies shared and view-specific sources of variation, associates factors with clinical covariates, and exports factor scores for downstream patient stratification. Supports any combination of omics layers (RNA-seq, proteomics, methylation, drug response, mutations). Includes the CLL blood cancer dataset (200 patients, 4 omics) as a pharma-relevant demonstration."
starting-prompt: Integrate my multi-omics data using MOFA+ to identify latent factors driving cross-omics variation . .
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



# Multi-Omics Integration (MOFA+)

Identify **latent factors** driving variation across 2+ omics layers using **MOFA+** (Multi-Omics Factor Analysis). Decomposes multi-omics data into interpretable factors, each capturing shared or view-specific biological signal. Handles **missing data** across views natively.

## When to Use This Skill

**Use when you:**
- ✅ Have 2+ omics layers measured on overlapping samples (RNA-seq + proteomics, methylation + mutations, etc.)
- ✅ Want to find shared sources of variation across omics (not just per-omics analysis)
- ✅ Need to identify which omics layers contribute to each source of variation
- ✅ Have incomplete data (not all samples measured in all views) — MOFA handles this
- ✅ Want factor scores for downstream patient stratification or survival analysis

**Don't use for:**
- ❌ Single omics data (use `bulk-rnaseq-counts-to-de-deseq2` or `bulk-omics-clustering`)
- ❌ Supervised prediction (use `lasso-biomarker-panel` instead)
- ❌ Single-cell multi-modal (MOFA2 supports it, but consider `scrna-trajectory-inference`)
- ❌ Fewer than 10 samples per view

**Runtime:** ~5-8 minutes total (CLL example). First run adds ~1-3 min for Python environment setup.

## Installation

```r
# Bioconductor packages
if (!requireNamespace("BiocManager", quietly = TRUE)) install.packages("BiocManager")
BiocManager::install(c("MOFA2", "MOFAdata", "ComplexHeatmap"))

# CRAN packages
install.packages(c("ggprism", "circlize", "reshape2", "RColorBrewer"))
```

| Package | Version | License | Commercial Use | Installation |
|---------|---------|---------|----------------|--------------|
| MOFA2 | ≥1.12.0 | LGPL (≥3) | ✅ Permitted | `BiocManager::install("MOFA2")` |
| MOFAdata | ≥1.8.0 | Artistic-2.0 | ✅ Permitted | `BiocManager::install("MOFAdata")` (example data) |
| ComplexHeatmap | ≥2.18.0 | MIT | ✅ Permitted | `BiocManager::install("ComplexHeatmap")` |
| ggprism | ≥1.0.3 | GPL (≥3) | ✅ Permitted | `install.packages("ggprism")` |
| circlize | ≥0.4.15 | MIT | ✅ Permitted | `install.packages("circlize")` |
| reshape2 | ≥1.4.4 | MIT | ✅ Permitted | `install.packages("reshape2")` |
| RColorBrewer | ≥1.1 | Apache-2.0 | ✅ Permitted | `install.packages("RColorBrewer")` |
| rmarkdown | ≥2.25 | GPL-3 | ✅ Permitted | `install.packages("rmarkdown")` (optional, PDF) |

## Inputs

- **Multi-omics data:** Named list of matrices (features × samples), one per omics view
  - Minimum 2 views, any combination of omics types
  - Samples as columns, features as rows
  - Missing samples across views OK (MOFA handles incomplete overlap)
- **Sample metadata** (optional): CSV/TSV with sample IDs + clinical variables (for factor-trait associations)
- **Supported formats:** R matrices, CSV/TSV files, or MultiAssayExperiment

## Outputs

**Analysis objects (RDS):**
- `mofa_model.rds` — Complete trained MOFA model for downstream use
  - Load with: `model <- readRDS('mofa_results/mofa_model.rds')`
  - Required for: `bulk-omics-clustering` (factor-based clustering), `lasso-biomarker-panel` (feature selection)

**CSV results:**
- `factor_values.csv` — Sample factor scores (samples × factors)
- `weights_*.csv` — Feature weights per view (features × factors)
- `variance_explained_per_factor.csv` — R² per factor per view
- `variance_explained_total.csv` — Total R² per view
- `top_features_per_factor.csv` — Top 20 features per factor per view

**Visualizations (PNG + SVG):**
- `mofa_variance_per_factor` — Heatmap: R² per factor per view (signature MOFA plot)
- `mofa_total_variance` — Bar chart: total R² per view
- `mofa_factor_scatter` — Scatter: Factor 1 vs 2 colored by clinical variable
- `mofa_factor_correlation` — Tile: factor-factor correlations
- `mofa_top_weights` — Faceted bar: top feature weights per factor
- `mofa_factor_heatmap` — ComplexHeatmap: factors × samples with annotations
- `mofa_factor_clinical` — Box plots: factor values by clinical groups

**Reports:**
- `analysis_report.md` — Markdown summary with methods, results, references
- `analysis_report.pdf` — PDF report with embedded figures (requires rmarkdown + LaTeX)

## Clarification Questions

1. **Input Files** (ASK THIS FIRST):
   - Do you have multi-omics data matrices to integrate?
   - Expected: Named list of matrices (features × samples), or CSV files per omics view
   - **Or use example data?** CLL blood cancer dataset (200 patients: mRNA, methylation, mutations, drug response)

> 🚨 **IF EXAMPLE DATA SELECTED:** Skip questions 3-4. Proceed directly to Step 1.

2. **Analysis Options:**
   - *(If using example data)* Number of factors:
     - a) 15 factors — standard analysis (recommended)
     - b) 5 factors — quick demo (~2 min faster)
   - *(If using own data)* Number of factors:
     - a) 15 (recommended starting point)
     - b) Custom number

3. *(Own data only)* **Data types per view:**
   - Which omics types? (RNA-seq, proteomics, methylation, mutations, metabolomics, drug response, other)
   - Are any views binary (0/1)? MOFA uses Bernoulli likelihood for binary data.

4. *(Own data only)* **Sample metadata:**
   - Do you have a sample metadata file (CSV/TSV) with clinical variables?
   - Variables for factor-trait associations (e.g., disease status, treatment, subtype)?

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Step 1 - Load data:**
```r
# For CLL example data:
source("scripts/load_example_data.R")
cll <- load_cll_data()

# For user data:
# source("scripts/load_example_data.R")
# cll <- load_user_data(
#   file_paths = list(RNA = "rna.csv", Protein = "protein.csv"),
#   metadata_path = "metadata.csv"
# )
```
**✅ VERIFICATION:** `"✓ Data loaded successfully!"` with per-view dimensions

---

**Step 2 - Run MOFA analysis:**
```r
source("scripts/mofa_workflow.R")
model <- run_mofa_analysis(
    data_list = cll$data,
    metadata = cll$metadata,
    n_factors = 15,
    output_dir = "mofa_results"
)
```
**DO NOT write inline MOFA code. Just call `run_mofa_analysis()`.**

⏱️ **Takes ~2-5 min** (+ ~1-3 min extra on first run for Python environment setup via basilisk).

**✅ VERIFICATION:** `"✓ MOFA model trained successfully!"` with variance explained summary

---

**Step 3 - Generate visualizations:**
```r
source("scripts/mofa_plots.R")
generate_all_plots(model, output_dir = "mofa_results")
```
🚨 **DO NOT write inline plotting code (ggsave, ggplot, Heatmap, etc.). Just use the script.** 🚨

**The script handles PNG + SVG export with graceful fallback for SVG dependencies.**

**✅ VERIFICATION:** `"✓ All plots generated successfully!"` with file count

---

**Step 4 - Export results:**
```r
source("scripts/export_results.R")
export_all(model, output_dir = "mofa_results")
```
**DO NOT write custom export code. Use `export_all()`.**

**✅ VERIFICATION:** `"=== Export Complete ==="` with file list

---

⚠️ **CRITICAL - DO NOT:**
- ❌ **Write inline MOFA code** → **STOP: Use `run_mofa_analysis()`**
- ❌ **Write inline plotting code (ggsave, ggplot, Heatmap, etc.)** → **STOP: Use `generate_all_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Try to install basilisk/reticulate manually** → MOFA2 handles Python automatically

**⚠️ IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** — Install missing package, re-run script
2. **Modify Script (5%)** — Edit the script file itself, document changes
3. **Use as Reference (4%)** — Read script, adapt approach, cite source
4. **Write from Scratch (1%)** — Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| **basilisk Python env setup slow** | First-time setup of Python backend | **Normal — wait 1-3 minutes.** Only happens once per R installation. |
| **`run_mofa` hangs at "Training model..."** | Model training in progress | **Normal — wait 2-5 min.** Training is compute-intensive. |
| **`Error in py_call_impl`: Python error** | basilisk environment issue | Restart R session, retry. If persistent: `BiocManager::install("MOFA2", force = TRUE)` |
| **Metadata download failed** | EBI FTP blocked or offline | **Normal fallback.** Analysis runs without trait plots. Metadata is optional. |
| **"No convergence"** | Too many factors or too few samples | Reduce `n_factors` (try 5-10). Ensure ≥10 samples. |
| **SVG export failed** | Missing svglite/cairo | **Normal.** PNG always generated. `generate_all_plots()` handles fallback automatically. |
| **Memory error** | Dataset too large | Filter features to top 5,000 most variable per view before MOFA. |

## Interpretation Guide

### Variance Decomposition (Key MOFA Output)
- **High R² in one view:** Factor captures view-specific variation
- **High R² across views:** Factor captures **shared** cross-omics signal (most interesting)
- **Low total R²:** MOFA explains little variation in that view — consider adding features or views

### Factor Interpretation
| Pattern | Meaning |
|---------|---------|
| Factor active in mRNA + methylation | Epigenetic regulation of transcription |
| Factor active in mutations + drug response | Genetic determinants of drug sensitivity |
| Factor correlates with clinical subtype | Biologically meaningful patient stratification |
| Factor active in only one view | View-specific technical or biological variation |

**See:** `references/mofa-interpretation-guide.md` for detailed downstream analysis.

## Suggested Next Steps

After running MOFA:
- **Patient stratification:** Use `bulk-omics-clustering` on factor scores to define molecular subtypes
- **Biomarker discovery:** Use `lasso-biomarker-panel` on top-weighted features per factor
- **Pathway enrichment:** Use `functional-enrichment-from-degs` on top mRNA features per factor
- **Network analysis:** Use `coexpression-network` on factor-associated genes
- **Survival analysis:** Use `survival-analysis-clinical` with factor scores as covariates

## Related Skills

| Skill | Relationship |
|-------|-------------|
| `bulk-omics-clustering` | Downstream: cluster on MOFA factor scores |
| `lasso-biomarker-panel` | Downstream: select biomarkers from top factor features |
| `disease-progression-longitudinal` | Complementary: trajectory analysis on factor scores |
| `coexpression-network` | Downstream: network analysis on factor-associated genes |
| `functional-enrichment-from-degs` | Downstream: pathway enrichment on top factor features |
| `bulk-rnaseq-counts-to-de-deseq2` | Upstream: generate DE results as one omics view |

## References

- Argelaguet R, et al. (2020) MOFA+: a statistical framework for comprehensive integration of multi-modal single-cell data. *Genome Biology* 21:111.
- Argelaguet R, et al. (2018) Multi-Omics Factor Analysis—a framework for unsupervised integration of multi-omics data sets. *Molecular Systems Biology* 14:e8124.
- Dietrich S, et al. (2018) Drug-perturbation-based stratification of blood cancer. *Journal of Clinical Investigation* 128(1):427-445.

## 📊 集成质量评估（必输出）

> **铁轨规则**：多组学集成后，**必须**运行以下评估并输出图表。未输出 → rail_review(post) 阻断。

### 必输出指标

| # | 指标 | 说明 | 通过标准 |
|---|------|------|---------|
| 1 | **LISI (batch)** | 跨组学的批次混合度 | > N_batch×0.8 |
| 2 | **Cell type ASW** | 细胞类型保留度 | > 0.5 |
| 3 | **Factor variance explained** | MOFA/MOFA+ 因子解释的方差比例 | at least 2 factors & R² > 5% |
| 4 | **Cross-modal correlation** | RNA vs ATAC/Protein 的跨模态相关性 | Spearman R > 0.3 for top factors |

### 不通过处理
- 警告 → debate_analysis 辩论
- 阻断 → 调整因子数 / 切换方法（MOFA+ → WNN → Seurat v5 bridge）


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
