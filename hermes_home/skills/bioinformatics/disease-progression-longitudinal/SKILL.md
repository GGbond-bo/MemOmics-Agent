---
id: "skill_26fd7b7e1ad64ad89d97bb183182d4f0"
name: "disease-progression-longitudinal"
when_to_use: "[disease-progression-longitudinal] 疾病进展纵向分析：多样本时间点→轨迹分析→疾病动态→进展标志物→早期预警"
display-name: "Disease Progression Trajectory Analysis"
category: Clinical
short-description: Reconstruct disease progression trajectories from longitudinal patient omics data.
detailed-description: Analyze time-series patient data (RNA-seq, proteomics, metabolomics) to reconstruct consensus disease trajectories using TimeAx multiple alignment. Orders samples by disease pseudotime, identifies trajectory-associated features, and validates against clinical outcomes. Handles irregular sampling patterns and works with cross-sectional or longitudinal cohorts.
starting-prompt: Analyze disease progression trajectories from longitudinal patient omics data
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



# Disease Progression Trajectory Analysis

## When to Use This Skill

Use this skill when you have **longitudinal patient omics data** and want to:
- ✅ Reconstruct disease progression trajectories from time-series data
- ✅ Order samples by disease stage (pseudotime) with irregular sampling
- ✅ Identify biomarkers changing along disease trajectory
- ✅ Stratify patients as fast vs. slow progressors
- ✅ Predict clinical outcomes from trajectory position
- ✅ Validate computational staging against clinical measures

**Required data:**
- Minimum 10 patients with 3+ timepoints each
- Omics data: RNA-seq, proteomics, metabolomics, or clinical biomarkers
- Metadata: Patient IDs, timepoints (days/months/years), optional outcomes

**Primary method:** TimeAx multiple trajectory alignment (handles irregular sampling)

**Feature identification:** Polynomial regression (linear/quadratic/cubic) per the TimeAx paper (Frishberg et al., Nat Commun 2023), with FDR-corrected Q-value filtering. Captures both monotonic and non-monotonic dynamics.

**Alternative methods:** Linear Mixed Models (regular sampling), Hidden Markov Models (discrete stages)

## Installation

**R ≥ 4.0** with the TimeAx package (primary trajectory method):

```r
# Install TimeAx from GitHub
install.packages("remotes")
remotes::install_github("amitfrish/TimeAx")

# Required for plotting
install.packages(c("ggplot2", "ggprism"))

# Required for demo dataset (GSE128959 batch correction)
BiocManager::install("sva")
```

**Python ≥ 3.9** for the workflow wrapper and analysis pipeline:

```bash
# Core analysis packages
pip install numpy pandas scipy scikit-learn statsmodels lifelines

# Visualization packages
pip install seaborn matplotlib

# PDF report generation (optional)
pip install reportlab

# Optional
pip install hmmlearn        # Hidden Markov Models alternative
```

**For Linear Mixed Models alternative:** R packages `lme4`, `lmerTest`

**License compliance:** All packages use permissive licenses (MIT, BSD, Apache 2.0) - commercial AI agent use permitted.

For detailed installation and troubleshooting, see [troubleshooting_guide.md](references/troubleshooting_guide.md)

## Inputs

**Required files:**

1. **Data matrix** (features × samples)
   - CSV/TSV format with features as rows, samples as columns
   - Feature types: genes, proteins, metabolites, or clinical biomarkers
   - Normalized counts or continuous measurements
   - ⚠️ **TimeAx requires all-positive values** (e.g., log2-normalized, RMA). Do NOT Z-score normalize before TimeAx — it creates negative values that disable the `ratio` mechanism.

2. **Sample metadata** (CSV/TSV)
   - Required columns: `sample_id`, `patient_id`, `timepoint`
   - Optional: `outcome`, `treatment`, `batch`, clinical covariates
   - Timepoints: numeric values (days, months, years from baseline)

**Data requirements:**
- ≥10 patients minimum (20+ recommended)
- ≥3 timepoints per patient minimum
- Handles irregular sampling (different timepoints per patient)
- Works with cross-sectional + longitudinal cohorts

## Outputs

**Primary results:**
- `pseudotime_assignments.csv` - Disease pseudotime for each sample
- `trajectory_features.csv` - Features changing along trajectory, with polynomial degree, R², and direction
- `patient_summaries.csv` - Per-patient progression statistics
- `all_feature_statistics.csv` - Statistics for all tested features

**Analysis objects (for downstream use):**
- `timeax_model.pkl` - Complete TimeAx model object
  - Load with: `model = pickle.load(open('timeax_model.pkl', 'rb'))`
  - Required for: Projecting new samples, downstream trajectory analysis

**Reports:**
- `analysis_report.pdf` - Publication-quality PDF with Introduction, Methods, Results, Conclusions
  - Requires: `pip install reportlab` (optional — markdown report generated regardless)
- `SUMMARY.txt` - Plain-text summary report

**TimeAx R plots (PNG + SVG, generated in Step 2):**
- `timeax_pseudotime_vs_time.png/.svg` - Per-patient pseudotime vs actual time trajectories
- `timeax_progression_rates.png/.svg` - Patient progression rate comparison (fast vs slow)
- `timeax_seed_dynamics.png/.svg` - Seed feature expression trends along pseudotime
- `timeax_uncertainty.png/.svg` - Pseudotime uncertainty distribution

**Python plots (PNG + SVG, generated in Step 3):**
- `patient_trajectories_pca.png/.svg` - PCA with pseudotime coloring and patient trajectory lines
- `patient_trajectories_umap.png/.svg` - UMAP nonlinear projection
- `trajectory_heatmap.png/.svg` - Feature expression clustermap
- `trajectory_trends.png/.svg` - Polynomial fit trends for top features
- `pseudotime_vs_stage.png/.svg` - Pseudotime vs clinical tumor stage (biological validation)
- `patient_progression.png/.svg` - Per-patient pseudotime spaghetti plot
- `seed_feature_heatmap.png/.svg` - TimeAx seed feature dynamics heatmap

**Metadata:**
- `model_metadata.json` - Analysis parameters, quality metrics (monotonicity, robustness)

## Clarification Questions

🚨 **ALWAYS ask Question 1 FIRST. Do not ask about data type, study design, or analysis parameters before the user has answered Question 1.**

### 1. Input Files (ASK THIS FIRST)
   - **Do you have longitudinal patient omics data to analyze?**
     - If uploaded: Are these your data matrix and sample metadata files?
     - Expected: Data matrix (features × samples) + metadata (sample_id, patient_id, timepoint)
   - **Or use example/demo data?**
     - **GSE128959 bladder cancer recurrence** (18 patients, 84 samples, 17K genes) — from the TimeAx paper (Frishberg et al. 2023). Requires R + `sva` package. Downloads ~5MB on first run.

> 🚨 **IF EXAMPLE DATA SELECTED:** All parameters are pre-defined (bladder cancer microarray, 18 patients, 4-6 timepoints, tumor recurrence, TimeAx method with ComBat batch correction). **DO NOT ask questions 2-6.** Proceed directly to Step 1.

**Questions 2-6 are ONLY for users providing their own data:**

### 2. **Data Type**: Bulk RNA-seq, proteomics, metabolomics, clinical biomarkers, or multi-omics?
### 3. **Study Design**: Number of patients (min 10, recommend 20+)? Timepoints per patient (min 3)? Sampling pattern (regular/irregular)? Time units and range?
### 4. **Disease Context**: Disease type? Treatment status? Available clinical outcomes (survival, relapse, response)? Known clinical staging?
### 5. **Analysis Goals**: Pseudotime ordering, patient stratification, biomarker discovery, outcome prediction, or trajectory comparison?
### 6. **Method Preference**: TimeAx (recommended), Linear Mixed Models, Hidden Markov Models, or not sure?

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Step 1 - Load and preprocess data:**

**For example/demo data (GSE128959 bladder cancer):**
```python
from scripts.load_and_preprocess import load_example_data, load_and_preprocess_data

# Load GSE128959 (downloads and preprocesses via R on first run)
data, metadata = load_example_data()

# Save to files for the standard pipeline
data.to_csv('gse128959_expression.csv')
metadata.to_csv('gse128959_metadata.csv', index=False)

# Run through standard preprocessing
data, metadata, preprocessing_stats = load_and_preprocess_data(
    data_file='gse128959_expression.csv',
    metadata_file='gse128959_metadata.csv',
    data_type='rnaseq',
    min_patients=10,
    min_timepoints=3
)
```

**For your own data:**
```python
from scripts.load_and_preprocess import load_and_preprocess_data

data, metadata, preprocessing_stats = load_and_preprocess_data(
    data_file="patient_expression.csv",
    metadata_file="sample_metadata.csv",
    data_type='rnaseq',  # 'rnaseq', 'proteomics', 'metabolomics', 'clinical'
    min_patients=10,
    min_timepoints=3
)
```
**DO NOT write inline data loading or preprocessing code. Just use the script.**

**✅ VERIFICATION:** You MUST see: `"✓ Data loaded and preprocessed successfully!"`

**Step 2 - Run trajectory analysis:**
```python
from scripts.run_trajectory_analysis import run_trajectory_analysis

# Run TimeAx alignment and identify trajectory features
results = run_trajectory_analysis(
    data,
    metadata,
    method='timeax',  # 'timeax', 'lmm', 'hmm'
    patient_column='patient_id',
    time_column='timepoint'
)
# Extract: pseudotime, trajectory_features, model, robustness_score
```
**DO NOT write inline TimeAx or trajectory code. Just use the script.**

**✅ VERIFICATION:** You MUST see: `"✓ Trajectory analysis completed successfully!"`

**Step 3 - Generate visualizations:**
```python
from scripts.generate_all_plots import generate_all_plots

# Generate all plots (PNG + SVG with graceful fallback)
generate_all_plots(
    data,
    metadata,
    results,
    output_dir='trajectory_results'
)
```
🚨 **DO NOT write inline plotting code (plt.savefig, seaborn, etc.). Just use the script.** 🚨

**The script handles PNG + SVG export with graceful fallback for SVG dependencies.**

**✅ VERIFICATION:** You MUST see: `"✓ All visualizations generated successfully!"`

**Step 4 - Export results:**
```python
from scripts.export_results import export_all

# Export all results, model object, and metadata
export_all(
    data=data,
    metadata=metadata,
    results=results,
    output_dir='trajectory_results'
)
```
**DO NOT write custom export code. Use export_all().**

**✅ VERIFICATION:** You MUST see: `"=== Export Complete ==="`

---

⚠️ **CRITICAL - DO NOT:**
- ❌ **Write inline data loading code** → **STOP: Use `load_and_preprocess_data()`**
- ❌ **Write inline TimeAx/trajectory code** → **STOP: Use `run_trajectory_analysis()`**
- ❌ **Write inline plotting code** → **STOP: Use `generate_all_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**

**⚠️ IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, re-run script
2. **Modify Script (5%)** - Edit the script file itself, document changes
3. **Use as Reference (4%)** - Read script, adapt approach, cite source
4. **Write from Scratch (1%)** - Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

---

## Detailed Methodology

For comprehensive details on algorithms, parameters, and methods:

- **TimeAx algorithm:** [timeax_methodology.md](references/timeax_methodology.md)
- **Alternative methods (LMM, HMM):** [lmm_hmm_alternatives.md](references/lmm_hmm_alternatives.md)
- **Method comparison and selection:** [method_comparison.md](references/method_comparison.md)
- **Data preprocessing by type:** [data_preprocessing_guide.md](references/data_preprocessing_guide.md)
- **Validation framework:** [validation_framework.md](references/validation_framework.md)

## Quality Control

**Quick checklist:**
- ✅ ≥10 patients with ≥3 timepoints each
- ✅ Within-patient monotonicity >0.5 (good) or 0.3-0.5 (moderate)
- ✅ Pseudotime correlates with clinical measures (r >0.2, p <0.05)
- ✅ Trajectory features identified (seed feature fallback if FDR <0.05 yields 0)
- ✅ Samples don't cluster by batch (check PCA)

**Note on robustness:** The TimeAx `robustness()` function (v0.1.1) can produce misleading negative values even on valid data. Use **within-patient monotonicity** as the primary quality metric instead.

For comprehensive QC guidelines, see [validation_framework.md](references/validation_framework.md)

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| **Negative robustness score** | Known TimeAx v0.1.1 bug | **Normal.** The `robustness()` function is unreliable. Use **within-patient monotonicity** (>0.5 = good) as the primary quality metric instead. |
| **0 trajectory features (FDR <0.05)** | FDR too stringent for genome-wide test | **Normal with real data.** The script automatically falls back to testing TimeAx seed features (reduced FDR burden) and nominal p < 0.05. |
| **Memory error during alignment** | Too many features (>20,000) | Reduce to 5000-10000 most variable features before TimeAx. Script does this automatically. |
| **SVG export failed** | Missing cairo system library | **Normal - PNG still generated.** Script handles fallback automatically. DO NOT try to install cairo manually. |
| **Samples cluster by batch not time** | Uncorrected batch effects | Run ComBat batch correction before trajectory analysis. Set `batch_correction=True` in preprocessing. |
| **Negative values disable `ratio` mode** | Z-score or log-fold-change normalization | TimeAx `ratio=TRUE` requires positive values. Use log2 counts, RMA, or TPM — NOT Z-scores. |
| **"R TimeAx not available"** | R or TimeAx R package not installed | **STOP: Install R, then run:** `Rscript -e 'remotes::install_github("amitfrish/TimeAx")'`. See Installation section. |
| **PDF report not generated** | reportlab not installed | **Normal.** Install with `pip install reportlab`. SUMMARY.txt is always generated as fallback. |

For complete troubleshooting, see [troubleshooting_guide.md](references/troubleshooting_guide.md)

## Suggested Next Steps

After trajectory analysis, consider these downstream analyses:

1. **Functional enrichment** → Use `functional-enrichment-gprofiler` skill
   - Input: `trajectory_features.csv` (top up/down-regulated features)
   - Find pathways changing along disease trajectory

2. **Tissue expression analysis** → Use `tissue-expression-from-degs` skill
   - Input: `trajectory_features.csv`
   - Identify tissue-specific trajectory markers

3. **Transcription factor activity** → Use `tf-activity-dorothea` skill
   - Input: `pseudotime_assignments.csv` + original expression data
   - Find TFs driving disease progression

4. **Survival analysis** → Built into clinical validation
   - Input: `pseudotime_assignments.csv` + survival data
   - Stratify patients by pseudotime tertiles/quartiles

5. **Project new samples** → Use `scripts/timeax_inference.py`
   - Load: `timeax_model.pkl`
   - Stage new patients on trained trajectory

## Related Skills

**Upstream (data generation):**
- `bulk-rnaseq-counts-to-de-deseq2` - Generate expression data
- `proteomics-differential-expression` - Proteomics quantification
- `metabolomics-preprocessing` - Metabolite data

**Downstream (interpretation):**
- `functional-enrichment-gprofiler` - Pathway analysis of trajectory features
- `tissue-expression-from-degs` - Tissue-specific markers
- `tf-activity-dorothea` - Transcription factor drivers
- `grn-pyscenic` - Gene regulatory networks along trajectory

**Alternative trajectory methods:**
- `pseudotime-monocle` - For single-cell RNA-seq trajectories
- `trajectory-inference-slingshot` - Branching trajectories

## References

### Primary Citations

1. **TimeAx:** Frishberg A, van den Munckhof ICL, Ter Horst R, et al. Reconstructing disease dynamics for mechanistic insights and clinical benefit. *Nat Commun*. 2023;14(1):6940. [https://doi.org/10.1038/s41467-023-42354-8](https://doi.org/10.1038/s41467-023-42354-8)

2. **Linear Mixed Models:** Bates D, Mächler M, Bolker B, Walker S. Fitting Linear Mixed-Effects Models Using lme4. *J Stat Softw*. 2015;67(1):1-48.

3. **Disease Trajectories Review:** Schmidt AF, Heerspink HJL, Denig P, et al. Disease trajectory browser for exploring temporal, population-wide disease progression patterns. *Nat Commun*. 2020;11:4952.

### Software

| Software | Version | License | Commercial Use |
|----------|---------|---------|----------------|
| TimeAx | ≥0.1.0 | MIT | ✅ Permitted |
| NumPy | ≥1.21 | BSD | ✅ Permitted |
| Pandas | ≥1.3 | BSD | ✅ Permitted |
| scikit-learn | ≥1.0 | BSD | ✅ Permitted |
| seaborn | ≥0.11 | BSD | ✅ Permitted |
| matplotlib | ≥3.5 | BSD | ✅ Permitted |
| ggprism (R) | ≥1.0.3 | GPL (≥3) | ✅ Permitted |
| sva (R) | ≥3.40 | Artistic-2.0 | ✅ Permitted |
| reportlab | ≥3.6 | BSD | ✅ Permitted |

### Online Resources

- TimeAx GitHub: [https://github.com/amitfrish/TimeAx](https://github.com/amitfrish/TimeAx)
- TimeAx Documentation: [https://timeax.readthedocs.io/](https://timeax.readthedocs.io/)
- Disease Progression Modeling Review: [https://www.annualreviews.org/content/journals/10.1146/annurev-biodatasci-110123-041001](https://www.annualreviews.org/content/journals/10.1146/annurev-biodatasci-110123-041001)


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
