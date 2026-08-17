---
id: "skill_aaafb560ba89480dbb01b2979f49630d"
name: "chip-atlas-target-genes"
when_to_use: "[chip-atlas-target-genes] 有ChIP-Atlas peak坐标或transcription factor名，需查询这些peak调控的靶基因列表，输出TF→target调控表"
display-name: "ChIP-Atlas Target Genes"
category: Data Query
short-description: "Retrieve pre-computed target genes for any transcription factor from ChIP-Atlas public ChIP-seq data."
detailed-description: "Downloads binding score data across all public ChIP-seq experiments for a specified protein/TF, ranking genes by MACS2 scores with cell-type-specific filtering and STRING protein interaction integration. Supports 10 genomes - human (hg38, hg19), mouse (mm10, mm9), rat (rn6), fly (dm6, dm3), worm (ce11, ce10), yeast (sacCer3)."
starting-prompt: Find target genes for a transcription factor using ChIP-Atlas public ChIP-seq data . .
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



# ChIP-Atlas Target Genes

Find target genes for any transcription factor using pre-computed ChIP-Atlas public ChIP-seq data.

## When to Use This Skill

Use ChIP-Atlas target genes when you need to:
- **Identify target genes of a specific TF** from all public ChIP-seq experiments
- **Rank potential targets** by MACS2 binding score across hundreds of experiments
- **Compare TF binding across cell types** using per-experiment binding scores
- **Validate known TF-target relationships** with independent ChIP-seq evidence
- **Cross-reference with STRING** protein interaction data for high-confidence targets

**Don't use for:**
- Finding which TFs bind near your genes (use **chip-atlas-peak-enrichment** instead)
- Histone mark targets (only non-histone antigens/TFs available)
- Offline analysis (requires internet for data download)
- Raw ChIP-seq analysis from FASTQ/BAM files

**Key Concept:** Downloads pre-computed TSV files containing MACS2 binding scores for every gene, across all public ChIP-seq experiments for the specified protein. Genes are ranked by average binding score. No API job submission needed — data is served as static files. STRING protein interaction scores are **pre-embedded columns** in the ChIP-Atlas TSV — no separate STRING API query is performed.

## Installation

| Software | Version | License | Commercial Use | Installation |
|----------|---------|---------|----------------|--------------|
| pandas | >=1.3 | BSD-3-Clause | Permitted | `pip install pandas` |
| requests | >=2.25 | Apache-2.0 | Permitted | `pip install requests` |
| numpy | >=1.20 | BSD-3-Clause | Permitted | `pip install numpy` |
| plotnine | >=0.12 | MIT | Permitted | `pip install plotnine` |
| plotnine_prism | >=0.1 | MIT | Permitted | `pip install plotnine_prism` |
| matplotlib | >=3.4 | PSF-based | Permitted | `pip install matplotlib` |
| seaborn | >=0.12 | BSD-3-Clause | Permitted | `pip install seaborn` |

```bash
pip install pandas requests numpy plotnine plotnine_prism matplotlib seaborn
```

**System requirements:** Internet connection (downloads from ChIP-Atlas data server)

## Inputs

**Query parameters:**
- **Protein/TF name:** Case-sensitive gene symbol (e.g., "TP53", "CTCF", "MYC")
- **Genome:** hg38 (default), hg19, mm10, mm9, rn6, dm6, dm3, ce11, ce10, sacCer3
- **Distance from TSS:** 1kb, 5kb (default), or 10kb

**Optional filters:**
- **min_score:** Minimum average MACS2 binding score (default: 0)
- **top_n:** Keep top N genes (default: 500)
- **cell_types:** List of cell types to subset (recalculates averages)
- **min_string_score:** Minimum STRING interaction score
- **min_binding_rate:** Minimum fraction of experiments with binding

## Outputs

**Analysis objects (Pickle):**
- `analysis_object.pkl` - Complete results for downstream use
  - Load with: `import pickle; obj = pickle.load(open('analysis_object.pkl', 'rb'))`
  - Contains: target_genes, experiment_data, cell_types, protein, parameters, metadata

**Results (CSV):**
- `target_genes_all.csv` - All target genes (gene, avg_score, string_score, binding_rate, num_bound, max_score, colocated_group)
- `target_genes_top50.csv` - Top 50 by average binding score
- `target_genes_with_string.csv` - Genes with STRING interaction evidence
- `experiment_scores_top50.csv` - Wide-format per-experiment scores for top 50

**Visualizations (PNG + SVG, plotnine with Prism theme):**
- `target_genes_top_targets.png/.svg` - Top target genes barplot
- `target_genes_score_distribution.png/.svg` - Binding score distribution histogram
- `target_genes_heatmap.png/.svg` - Binding heatmap (top genes × experiments)
- `target_genes_string_vs_binding.png/.svg` - STRING vs binding scatter

**Reports:**
- `summary_report.md` - Human-readable analysis summary

## Clarification Questions

🚨 **ALWAYS ask Question 1 FIRST. Do not ask about species, genome, or analysis parameters before the user has answered Question 1.**

### 1. **Query** (ASK THIS FIRST):
   - Which transcription factor / protein do you want to find target genes for?
   - Protein name is **case-sensitive** (e.g., "TP53" not "tp53")
   - **Or use example data?** `tp53` (large, ~16K genes), `e2f1` (cell cycle), `myc` (moderate)

> 🚨 **IF EXAMPLE DATA SELECTED:** All parameters are pre-defined (human hg38, ±5kb TSS, all cell types, no score threshold). **DO NOT ask question 2.** Proceed directly to Step 1.

**Question 2 is ONLY for users providing their own query:**

### 2. **Analysis parameters:**
   - **Species/genome?** Human hg38 (default), hg19, mouse mm10/mm9, rat rn6, fly, worm, yeast
   - **Distance from TSS?** ±5kb (default), ±1kb (proximal only), ±10kb (distal included)
   - **Cell type filter?** All cell types (default), or specific types to get cell-type-specific rankings
   - **Score threshold?** No minimum (default), or set min_score to focus on strong targets

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Step 1 - Load query:**
```python
# Option 1: Example query
from scripts.load_example_query import load_example_query
query = load_example_query("tp53")

# Option 2: Your own protein
# from scripts.load_user_query import load_user_query
# query = load_user_query("TP53", genome="hg38", distance=5)
```
**VERIFICATION:** `"✓ Query loaded: TP53 target genes (hg38, ±5kb)"`

**Step 2 - Run target genes analysis:**
```python
from scripts.run_target_genes_workflow import run_target_genes_workflow

results = run_target_genes_workflow(
    protein=query['protein'],
    genome=query['genome'],
    distance=query['distance'],
    top_n=500,
    output_dir="target_genes_results"
)
```
**DO NOT write inline download/parsing code. Just use the script.**

**VERIFICATION:** `"✓ Target genes analysis completed successfully!"`

**Step 3 - Generate visualizations:**
```python
from scripts.generate_all_plots import generate_all_plots
generate_all_plots(results, output_dir="target_genes_results", top_n=25)
```
**DO NOT write inline plotting code. The script handles PNG + SVG with graceful fallback.**

**VERIFICATION:** `"✓ All visualizations generated successfully!"`

**Step 4 - Export results:**
```python
from scripts.export_all import export_all
export_all(results, output_dir="target_genes_results")
```
**DO NOT write custom export code. Use export_all().**

**VERIFICATION:** `"=== Export Complete ==="`

⚠️ **CRITICAL - DO NOT:**
- ❌ **Write inline download/parsing code** → **STOP: Use `run_target_genes_workflow()`**
- ❌ **Write inline plotting code** → **STOP: Use `generate_all_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**

**⚠️ IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, check internet, re-run
2. **Modify Script (5%)** - Edit the script file itself, document changes
3. **Use as Reference (4%)** - Read script, adapt approach, cite source
4. **Write from Scratch (1%)** - Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| **HTTP 404 for protein** | **Invalid or unavailable antigen** | **Check case sensitivity ("TP53" not "tp53"). Histone marks not available. See [references/target_genes_data_format.md](references/target_genes_data_format.md).** |
| **Download timeout** | **Large file or slow connection** | **TP53 is ~13MB; allow up to 2 minutes. Try smaller TF first (e.g., MYC).** |
| **Memory error on large file** | **Very wide TSV (100s of columns)** | **Use top_n parameter to limit genes. Cell-type filter reduces columns.** |
| **No STRING data (all zeros)** | **Protein not in STRING database** | **Normal for less-studied TFs. Binding scores still valid without STRING.** |
| **Empty results after filtering** | **Filters too strict** | **Lower min_score, remove cell_type filter, increase top_n.** |
| **SVG export error** | **Missing optional dependency** | **Normal - `generate_all_plots()` handles fallback. PNG always created.** |

## Interpretation Guidelines

**Average Binding Score (MACS2):** −10 × log10(Q-value). Higher = stronger binding evidence.
- **≥500:** Very strong binding (Q ≤ 1e-50) — high-confidence direct target
- **100-500:** Strong binding — likely direct target
- **50-100:** Moderate binding — possible target, may be cell-type-specific
- **<50:** Weak binding — marginal evidence

**Note:** The Q-value thresholds above apply to **individual experiment** scores. Average scores include zeros from non-binding experiments, so an average of 500 reflects a *consensus* level — not that every experiment shows Q ≤ 1e-50.

**Binding Rate:** Fraction of experiments with any binding, shown as % with n/N count (e.g., "66.3% (260/392)"). >50% = consistent across cell types; <10% = cell-type-specific.

**STRING Score:** Independent evidence of regulatory interaction. >400 = medium confidence; >700 = high confidence. Genes with BOTH high binding + high STRING = highest-confidence targets. **STRING score of 0 does NOT mean "not a target"** — even well-characterized targets (e.g., BBC3/PUMA for TP53) can have STRING score 0 due to gaps in STRING coverage.

**Caveats:**
- **Averaging includes zeros:** Average scores are computed across ALL experiments (including those with score 0). Use `max_score` and `binding_rate` for complementary views.
- **Cell-type bias:** Experiments are unevenly distributed — a few well-studied cell lines dominate. See the "Experiment Composition" section in `summary_report.md` for exact distribution.
- **Co-located genes:** Some genes share identical binding scores because they sit at the same genomic locus within the TSS window. The `colocated_group` column in the CSV flags these genes. For pathway enrichment, consider collapsing co-located groups to avoid double-counting loci. See `summary_report.md` Caveats for exact counts.
- **External annotations:** ChIP-Atlas provides binding data only. Any biological role descriptions in the agent's summary are from general knowledge, not from this analysis output. Always cite the actual data columns (avg_score, binding_rate, string_score) when reporting results.

## Reporting Results

🚨 **CRITICAL: Follow these rules when presenting results to the user.**

1. **Rankings MUST come from the data files.** Read `summary_report.md` or `target_genes_all.csv` for exact gene names, ranks, and scores. **NEVER construct ranking tables from general biological knowledge** — even if a gene is a well-known target, its rank must match the data.
2. **Do NOT substitute biologically famous genes** into top-N lists where the data ranks them lower. If a well-known target is not in the top 10, say so explicitly (e.g., "BAX, a well-characterized target, ranks #17 with avg_score 368.8").
3. **Use exact values from the CSV/report** (1 decimal place for scores, 1 decimal for percentages). Do not round to integers.
4. **Cite the data source** as: ChIP-Atlas (Zou et al., 2024) with the DOI from the References section.
5. **Mention co-located gene groups** if the summary report flags them — they affect the effective number of independent targets.
6. **Label biological annotations:** When describing gene functions or pathway roles, explicitly note these come from general knowledge (e.g., "CDKN1A — known cell cycle arrest effector — ranks #1"), not from ChIP-Atlas output.

## Suggested Next Steps

1. **Run peak enrichment** with top target genes to find co-regulatory factors (chip-atlas-peak-enrichment)
2. **Cell-type-specific analysis** — re-run with `cell_types` filter matching your experimental system
3. **Gene regulatory network** construction using top targets as nodes
4. **Functional enrichment** of top target genes (GO, pathway analysis)

## Related Skills

- **[chip-atlas-peak-enrichment](../chip-atlas-peak-enrichment/)** - Find enriched TFs near YOUR gene list (reverse query)
- **[gene-correlation-archs4](../gene-correlation-archs4/)** - Co-expression across 600K RNA-seq samples
- **[grn-pyscenic](../grn-pyscenic/)** - Gene regulatory networks from single-cell data

## References

- Zou et al. (2024). ChIP-Atlas 3.0: a data-mining suite to explore chromosome architecture. *Nucleic Acids Research*. [doi:10.1093/nar/gkad884](https://doi.org/10.1093/nar/gkad884)
- Zou et al. (2022). ChIP-Atlas 2021 update. *Nucleic Acids Research*. [doi:10.1093/nar/gkab933](https://doi.org/10.1093/nar/gkab933)
- Oki et al. (2018). ChIP-Atlas: a data-mining suite. *EMBO Reports* 19(12):e46255. [doi:10.15252/embr.201846255](https://doi.org/10.15252/embr.201846255)
- ChIP-Atlas: https://chip-atlas.org
- Target Genes documentation: See [references/target_genes_data_format.md](references/target_genes_data_format.md)
- MACS2 binding scores: See [references/macs2_binding_scores.md](references/macs2_binding_scores.md)
- STRING integration: See [references/string_scores.md](references/string_scores.md)


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
