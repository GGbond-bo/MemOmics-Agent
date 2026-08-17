---
id: "skill_08c0e01956d643148a85f5334cfd7abd"
name: "proteomics-diff-exp"
when_to_use: "[proteomics-diff-exp] 蛋白质组差异表达分析 蛋白组学差异分析 proteomics：蛋白定量矩阵→limma/DEP差异分析→差异蛋白筛选→火山图/热图→通路富集→蛋白互作网络"
display-name: "Proteomics Differential Expression (limma + DEqMS)"
category: Proteomics
description: "Differential protein expression analysis for mass spectrometry proteomics data using limma and DEqMS. For no-replicate data use references/no-replicate-proteomics.md."
short-description: "Differential protein expression analysis on mass spectrometry proteomics data using limma and DEqMS with PSM-aware variance estimation."
detailed-description: "Analyze TMT or LFQ mass spectrometry proteomics data for differential protein expression. Uses limma linear models with DEqMS spectra-count-aware empirical Bayes variance estimation for improved statistical power. Supports MaxQuant, Proteome Discoverer, or generic protein intensity matrices. Includes missing value imputation (MinProb/kNN), normalization, QC visualization, and publication-quality plots."
starting-prompt: Perform differential protein expression analysis on my proteomics mass spectrometry data.
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



# Proteomics Differential Expression (limma + DEqMS)

Differential protein expression analysis for TMT/LFQ mass spectrometry proteomics data using limma linear models with DEqMS PSM-count-aware variance correction.

## When to Use This Skill

Use this skill when you have:
- ✅ **Protein quantification data** from TMT or LFQ mass spectrometry
- ✅ **PSM/peptide counts per protein** (for DEqMS variance correction)
- ✅ **Biological replicates** (≥2 per condition, ≥3 recommended)
- ✅ Need for **PSM-aware statistical testing** (improved power over standard limma)

**Don't use this skill for:**
- ❌ RNA-seq data → use bulk-rnaseq-counts-to-de-deseq2
- ❌ Metabolomics data → different normalization/statistics needed
- ❌ Pre-computed fold changes without raw intensities
- ❌ **No-replicate / low-N proteomics** → use `references/no-replicate-proteomics.md` (includes mandatory replicate detection before analysis)
- ❌ **Secretome / conditioned medium classification** → use `references/secretome-classification.md`

## Quick Start (Example Data)

**Test this skill with real TMT proteomics data in ~2 minutes:**

```r
source("scripts/load_example_data.R")
data <- load_example_data()    # Auto-downloads A431 TMT 10-plex data (~30s)
psm_data <- data$psm_data      # 316,726 PSMs × 10 TMT channels
metadata <- data$metadata       # 4 conditions: ctrl, miR191, miR372, miR519

# Run complete workflow
source("scripts/basic_workflow.R")  # Creates fit_deqms, deqms_results + prints summary
```

**What you get:**
- **Dataset:** A431 human epidermoid carcinoma cells treated with miRNAs (TMT 10-plex)
- **Comparison:** miR372 vs ctrl (3 vs 3 replicates)
- **Expected results:** ~9,000 proteins quantified, significant DE proteins at adj.p < 0.05

**For your own data:** Replace data loading with your protein intensity matrix and metadata (see [Inputs](#inputs) section).

## Installation

**Core packages (required):**
```r
options(repos = c(CRAN = "https://cloud.r-project.org"))
if (!require('BiocManager', quietly = TRUE)) install.packages('BiocManager')
BiocManager::install(c('limma', 'DEqMS', 'ExperimentHub'))
```

**Visualization packages (required):**
```r
install.packages(c('ggplot2', 'ggprism', 'ggrepel', 'circlize', 'matrixStats'))
BiocManager::install('ComplexHeatmap')
```

**Optional packages:**
```r
install.packages(c('rmarkdown', 'knitr'))        # PDF report
BiocManager::install(c('impute', 'vsn'))          # kNN imputation, VSN normalization
```

| Software | Version | License | Commercial Use | Installation |
|----------|---------|---------|----------------|--------------|
| limma | ≥3.50.0 | GPL (≥2) | ✅ Permitted | `BiocManager::install('limma')` |
| DEqMS | ≥1.12.0 | LGPL | ✅ Permitted | `BiocManager::install('DEqMS')` |
| ExperimentHub | ≥2.0.0 | Artistic-2.0 | ✅ Permitted | `BiocManager::install('ExperimentHub')` |
| ggplot2 | ≥3.4.0 | MIT | ✅ Permitted | `install.packages('ggplot2')` |
| ggprism | ≥1.0.3 | GPL (≥3) | ✅ Permitted | `install.packages('ggprism')` |
| ggrepel | ≥0.9.0 | GPL-3 | ✅ Permitted | `install.packages('ggrepel')` |
| ComplexHeatmap | ≥2.10.0 | MIT | ✅ Permitted | `BiocManager::install('ComplexHeatmap')` |
| circlize | ≥0.4.15 | MIT | ✅ Permitted | `install.packages('circlize')` |
| matrixStats | ≥0.60.0 | Artistic-2.0 | ✅ Permitted | `install.packages('matrixStats')` |
| rmarkdown | ≥2.20 | GPL-3 | ✅ Permitted | Optional |

**Note:** Scripts automatically generate both PNG and SVG formats. SVG export uses base R svg() device (always available) or svglite if installed. No additional setup needed.

## Inputs

**Required:**
- **Protein intensity matrix**: Rows = proteins, Columns = samples
  - PSM-level table with gene/protein column (recommended — enables medianSweeping aggregation)
  - OR protein-level intensities (log2 or raw)
- **Sample metadata**: data.frame with `condition` column

**Optional but recommended:**
- **PSM/peptide counts per protein** (critical for DEqMS variance correction)

**Supported formats:** MaxQuant proteinGroups.txt, Proteome Discoverer export, generic CSV/TSV

## Outputs

**Result tables (CSV):**
- `all_results.csv` — Full DEqMS results (logFC, sca.P.Value, sca.adj.pval, count)
- `significant_results.csv` — Filtered by adjusted p-value and fold change
- `normalized_protein_matrix.csv` — Log2 normalized protein intensities
- `psm_counts.csv` — PSM counts per protein
- `top100_proteins.csv` — Top 100 by DEqMS adjusted p-value

**Analysis objects (RDS):**
- `analysis_object.rds` — Complete analysis object for downstream skills
  - Load with: `obj <- readRDS('results/analysis_object.rds')`
  - Contains: fit_deqms, deqms_results, protein_matrix, metadata, psm_counts

**Plots (PNG + SVG):**
- `intensity_distribution` — Before/after normalization boxplots
- `missing_values_heatmap` — Missing value pattern across samples
- `pca_plot` — PCA colored by condition
- `sample_correlation_heatmap` — Pearson correlation between samples
- `volcano_plot` — Differential expression with labeled top hits
- `ma_plot` — Log2 fold change vs average expression
- `variance_psm_plot` — DEqMS variance vs PSM count relationship

**Reports:**
- `analysis_report.pdf` — PDF report (requires rmarkdown + LaTeX)
- `analysis_report.md` — Markdown report (always generated)

## Clarification Questions

### 1. **Input Files** (ASK THIS FIRST):
- Do you have proteomics data files to analyze?
  - If uploaded: What format? (MaxQuant proteinGroups.txt / Proteome Discoverer / CSV)
  - Expected: protein intensity matrix + sample metadata
  - **Or use example data?** TMT 10-plex A431 cancer cell line dataset (auto-downloads ~30s)

### 2. **Analysis Options** (structured):
- *(If using example data)* The demo dataset contains A431 human cancer cells treated with miRNAs (3 ctrl + 3 miR372 replicates). Choose analysis mode:
  - a) Standard analysis with default comparison miR372 vs ctrl (recommended)
  - b) Custom comparison (miR191 vs ctrl or miR519 vs ctrl)
- *(If using your own data)* Which conditions to compare? (e.g., Treatment-Control)

### 3. **Thresholds:**
- a) Standard: adjusted p-value < 0.05, |log2FC| > 0.58 / 1.5-fold change (recommended)
- b) Relaxed: adjusted p-value < 0.1, |log2FC| > 0 (any fold change)
- c) Stringent: adjusted p-value < 0.01, |log2FC| > 1 (2-fold change)

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Step 1 - Load data:**
```r
source("scripts/load_example_data.R")
data <- load_example_data()
psm_data <- data$psm_data
metadata <- data$metadata
```
**For your own data:** Replace with your loading code, then call `validate_input_data()`.

**Step 2 - Run DE analysis:**
```r
source("scripts/basic_workflow.R")
```
**DO NOT expand this into inline code. DO NOT write limma/DEqMS steps manually. Just source the script.**

**Step 3 - Generate plots:**
```r
source("scripts/qc_plots.R")
generate_all_plots(fit_deqms, deqms_results, protein_matrix,
                    metadata, output_dir = "results", raw_matrix = raw_matrix)
```
🚨 **DO NOT write inline plotting code (ggsave, ggplot, Heatmap, etc.). Just use the script.** 🚨

**Step 4 - Export results:**
```r
source("scripts/export_results.R")
export_all(fit_deqms, deqms_results, protein_matrix, metadata,
            output_dir = "results")
```
**DO NOT write custom export code. Use export_all() to save all outputs including RDS.**

**✅ VERIFICATION - You should see:**
- After Step 1: `"✓ Example data loaded successfully"` with PSM/protein counts
- After Step 2: `"✓ Proteomics DE analysis completed successfully!"` with summary
- After Step 3: `"✓ All plots generated successfully!"`
- After Step 4: `"=== Export Complete ==="` with file list

**❌ IF YOU DON'T SEE THESE MESSAGES:** You wrote inline code. Stop and use source().

⚠️ **CRITICAL - DO NOT:**
- ❌ **Write inline limma/DEqMS code** → **STOP: Use `source("scripts/basic_workflow.R")`**
- ❌ **Write inline plotting code** → **STOP: Use `generate_all_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Try to install svglite** → scripts handle SVG fallback automatically
- ❌ **Use absolute paths** → Always use `scripts/file.R`

**⚠️ IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, re-run script
2. **Modify Script (5%)** - Edit the script file itself, document changes
3. **Use as Reference (4%)** - Read script, adapt approach, cite source
4. **Write from Scratch (1%)** - Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

**What the scripts provide:**
- [scripts/load_example_data.R](scripts/load_example_data.R) — `load_example_data()`, `validate_input_data()`
- [scripts/basic_workflow.R](scripts/basic_workflow.R) — Complete limma+DEqMS pipeline with PSM aggregation, imputation, normalization
- [scripts/qc_plots.R](scripts/qc_plots.R) — Publication-quality plots with ggprism/ComplexHeatmap (PNG + SVG with automatic fallback)
- [scripts/export_results.R](scripts/export_results.R) — `export_all()` saves all outputs (CSV, RDS, PDF report)

## Customizing the Analysis

**To change the comparison** (before sourcing basic_workflow.R):
```r
comparison_name <- "miR519-ctrl"  # or any valid contrast
source("scripts/basic_workflow.R")
```

**To change imputation/normalization:**
```r
imputation_method <- "kNN"         # "MinProb" (default) or "kNN"
normalization_method <- "quantile" # "median" (default), "quantile", or "none"
source("scripts/basic_workflow.R")
```

**For detailed method documentation:** See [references/proteomics-reference.md](references/proteomics-reference.md)
**For normalization guidance:** See [references/normalization-guide.md](references/normalization-guide.md)

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| **Not seeing verification messages** | Wrote inline code instead of source() | Stop and use Standard Workflow commands exactly |
| **"cannot open file" error** | Using absolute paths | Use relative paths: `source("scripts/file.R")` |
| **ExperimentHub download fails** | Network timeout | Set `options(timeout = 300)` and retry |
| **Missing package errors** | Package not installed | `BiocManager::install('package')` or `install.packages('package')` |
| **SVG export error "svglite required"** | Missing optional dependency | Use `generate_all_plots()` — it handles fallback automatically. DO NOT try to install svglite manually |
| **svglite dependency conflict** | System library version mismatch | Normal — `generate_all_plots()` falls back to base R svg() device automatically. Both PNG and SVG will be created |
| **All proteins filtered out** | Too stringent missing value filter | Adjust filter threshold in basic_workflow.R |
| **No significant proteins** | Weak effect or wrong comparison | Check PCA for condition separation; try relaxed thresholds |
| **⛔ Two columns treated as conditions but actually replicates** | r > 0.9 in correlation check | **STOP**: columns are replicates, not conditions. Switch to `references/no-replicate-proteomics.md` Path A (abundance-based). NEVER compute log2FC on replicates — all fold changes are noise. |

## Suggested Next Steps

After running this skill:
1. **Pathway enrichment** → functional-enrichment skill with significant proteins
2. **Biomarker panel** → lasso-biomarker-panel with DE proteins as features
3. **Network analysis** → coexpression-network with protein matrix
4. **PPI network** → query_string + literature-curated interactions
5. **No-replicate data?** → See `references/no-replicate-proteomics.md`. **MANDATORY**: run replicate detection (Step 0) first. If r > 0.9 → Path A (abundance-based). If r < 0.7 → Path B (fold-change only, no stats).
6. **Secretome/CM data?** → Classify proteins by existence form using `references/secretome-classification.md`. For anti-aging relevance, cross-reference with UniProt aging annotations and KB gene sets.

## Related Skills

| Skill | Relationship | When to Use |
|-------|-------------|-------------|
| bulk-rnaseq-counts-to-de-deseq2 | Alternative | RNA-seq count data (not proteomics) |
| lasso-biomarker-panel | Downstream | Build biomarker panel from DE proteins |
| coexpression-network | Downstream | Protein co-expression modules |

## References

- **DEqMS:** Zhu Y, et al. *Molecular & Cellular Proteomics*. 2020;19(6):1047-1057
- **limma:** Ritchie ME, et al. *Nucleic Acids Research*. 2015;43(7):e47
- [Detailed method reference](references/proteomics-reference.md)
- [Normalization guide](references/normalization-guide.md)


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
     topic="蛋白组学分析 —— {样本}",
     context="方法: {limma/DEP/MSstats} | 参数: FDR<{x} | 结果: {n}差异蛋白",
     knowledge_base_info=<KB内容>,
   )
   辩论: 方法选对了吗？阈值合理？差异蛋白跟RNA一致吗？富集通路合理？
3. save_conclusions(module="03_advanced", topic="Proteomics", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```
