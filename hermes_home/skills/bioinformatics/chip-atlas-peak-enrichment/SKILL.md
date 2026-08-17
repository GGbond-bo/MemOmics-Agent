---
id: "skill_dd3e525ed3e84cb9a73aa45781117110"
name: "chip-atlas-peak-enrichment"
when_to_use: "[chip-atlas-peak-enrichment] ChIP-Atlas peak富集分析：peak列表→基因组区域注释→motif富集→GO/KEGG通路富集→调控网络"
display-name: "ChIP-Atlas Peak Enrichment"
category: Data Query
short-description: "Analyze enrichment of ChIP-seq peaks from 433,000+ experiments via the ChIP-Atlas API."
detailed-description: "Analyze enrichment of ChIP-seq peaks from 433,000+ experiments via the official ChIP-Atlas Enrichment Analysis API. Submits gene lists for Fisher's exact test enrichment with Benjamini-Hochberg Q-values against all public ChIP-seq data. Generates 4-panel visualization. Supports 10 genomes - human (hg38, hg19), mouse (mm10, mm9), rat (rn6), fly (dm6, dm3), worm (ce11, ce10), yeast (sacCer3)."
starting-prompt: Find ChIP-seq peak enrichment near my genes using ChIP-Atlas database . .
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



# ChIP-Atlas Peak Enrichment

Find ChIP-seq peak enrichment near your genes using the official ChIP-Atlas Enrichment Analysis API.

## When to Use This Skill

Use ChIP-Atlas peak enrichment when you need to:
- **Identify transcription factors binding near your genes** from DE analysis or pathway results
- **Discover chromatin regulators** (TFs, histone modifications, chromatin remodelers) enriched near your gene set
- **Validate regulatory relationships** between factors and target genes using public ChIP-seq data
- **Find cell-type-specific regulators** by filtering to specific cell classes
- **Query 433,000+ ChIP-seq experiments** via the official API without manual downloads

**Don't use for:**
- Direct ChIP-seq analysis from raw reads (use peak calling workflows)
- Single gene lookups (use ChIP-Atlas web interface directly)
- Offline analysis (requires internet for API calls)

**Key Concept:** Submits your gene list to the ChIP-Atlas API, which performs Fisher's exact test enrichment analysis against all public ChIP-seq experiments. Returns fold enrichment, P-values, and BH-corrected Q-values.

## Installation

| Software | Version | License | Commercial Use | Installation |
|----------|---------|---------|----------------|--------------|
| pandas | >=1.3 | BSD-3-Clause | Permitted | `pip install pandas` |
| requests | >=2.25 | Apache-2.0 | Permitted | `pip install requests` |
| numpy | >=1.20 | BSD-3-Clause | Permitted | `pip install numpy` |
| plotnine | >=0.10 | MIT | Permitted | `pip install plotnine` |
| plotnine-prism | >=0.3 | MIT | Permitted | `pip install plotnine-prism` |

```bash
pip install pandas requests numpy plotnine plotnine-prism
```

**System requirements:** Internet connection (API calls to ChIP-Atlas and Ensembl)

## Inputs

**Gene list:**
- Gene symbols (e.g., ["TP53", "MYC", "EGFR"])
- Minimum: 3 genes; Recommended: 5-100 genes
- Formats: Python list, plain text (one per line), CSV with gene column

**Parameters:**
- **Genome:** hg38 (default), hg19, mm10, mm9, rn6, dm6, dm3, ce11, ce10, sacCer3
- **Antigen class:** "TFs and others" (default), "Histone", "ATAC-Seq", "DNase-seq", "RNA polymerase"
- **Cell class:** "All cell types" (default), "Blood", "Neural", "Breast", etc.
- **Threshold:** Peak-calling stringency (MACS2 -10×log10(p)): 50 (default, ~p<1e-5), 100 (~p<1e-10), 200 (~p<1e-20), 500 (~p<1e-50). Higher = fewer, more confident peaks. See [references/peak_thresholds.md](references/peak_thresholds.md).
- **TSS window:** 5000bp upstream, 5000bp downstream (default)

## Outputs

**Analysis objects (Pickle):**
- `analysis_object.pkl` - Complete results for downstream use
  - Load with: `import pickle; obj = pickle.load(open('analysis_object.pkl', 'rb'))`
  - Contains: enrichment_results, input_genes, input_regions, metadata, parameters

**Results (CSV):**
- `enrichment_results_all.csv` - All experiments (experiment_id, antigen, cell_type, fold_enrichment, p_value, q_value, overlap_rate, regions_with_overlaps, total_regions)
- `enrichment_results_significant.csv` - Significant enrichments (q < 0.05, BH-corrected)
- `enrichment_results_top20.csv` - Top 20 by significance (q-value, minimum 2 gene overlaps)

**Visualizations (PNG + SVG):**
- `chipatlas_enrichment.png/.svg` - 4-panel summary figure: top factors by significance, p-value distribution, overlap vs fold enrichment scatter, volcano plot (300 DPI)

**Reports:**
- `summary_report.md` - Human-readable analysis summary

## Clarification Questions

1. **Input Files** (ASK THIS FIRST):
   - Do you have a gene list to analyze?
   - Expected formats: Plain text (one gene per line), CSV with gene column, or DE results file
   - **Or use example data?** `tp53_targets` (5 genes, fast test) or `immune_response` (20 genes)

2. **Analysis parameters:**
   - **Species/genome?** Human hg38 (default), hg19, mouse mm10/mm9, rat rn6, fly, worm, yeast
   - **Experiment type?** "TFs and others" (default), "Histone", "ATAC-Seq"
   - **Cell type class?** "All cell types" (default), or specific: "Blood", "Neural", "Breast", etc.
   - **Peak threshold?** 50 (default, balanced), 100 (stringent), 200 (very stringent)
   - **TSS window?** 5000bp up/down (default), or custom distance_up/distance_down

## Standard Workflow

**Step 1 - Load data:**
```python
# Option 1: Example data
from scripts.load_example_data import load_example_data
data = load_example_data("tp53_targets")
gene_list = data['genes']

# Option 2: Your own genes
# from scripts.load_user_data import load_user_data
# gene_list = load_user_data("my_genes.txt")
```
**VERIFICATION:** `"Data loaded successfully: {N} genes"`

**Step 2 - Run enrichment analysis:**
```python
from scripts.run_enrichment_workflow import run_enrichment_workflow

results = run_enrichment_workflow(
    gene_list=gene_list,
    genome="hg38",
    antigen_class="TFs and others",
    cell_class="All cell types",
    threshold=50,
    output_dir="chipatlas_results"
)
```
**DO NOT write inline API query code. Just use the script.**

**VERIFICATION:** `"Enrichment analysis completed successfully!"`

**Step 3 - Generate visualizations:**
```python
from scripts.generate_all_plots import generate_all_plots
generate_all_plots(results, output_dir="chipatlas_results", top_n=15)
```
**DO NOT write inline plotting code. The script handles PNG + SVG with graceful fallback.**

**VERIFICATION:** `"All visualizations generated successfully!"`

**Step 4 - Export results:**
```python
from scripts.export_all import export_all
export_all(results, output_dir="chipatlas_results")
```
**DO NOT write custom export code. Use export_all().**

**VERIFICATION:** `"=== Export Complete ==="`

**IF SCRIPTS FAIL - Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, check internet, re-run
2. **Modify Script (5%)** - Edit the script, document changes
3. **Use as Reference (4%)** - Read script, adapt approach
4. **Write from Scratch (1%)** - Only if impossible, explain why

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| **API 400 error** | **Invalid parameters** | **Both antigenClass and cellClass must be non-empty. Use "All cell types" for all cells. See [references/chipatlas_metadata_format.md](references/chipatlas_metadata_format.md) for valid values.** |
| **API timeout (>10 min)** | **Large analysis or server load** | **Normal for "All cell types" with many experiments. Wait up to 10 minutes. Reduce scope by selecting specific cell_class.** |
| **Ensembl API timeout** | **Network or rate limiting** | **The workflow script automatically retries once after 60 seconds. If it still fails, the Ensembl step is skipped — enrichment results are unaffected but lack coordinate verification. Report this to the user (see interpretation rules).** |
| **Gene not found** | **Retired symbol or typo** | **Script auto-retries with known aliases (e.g., IL8→CXCL8). Check HGNC (genenames.org) for current symbol. Only affects input_regions, not enrichment results.** |
| **Fold enrichment >100,000x** | **Sentinel value (zero background overlap)** | **Not a real enrichment. Results are ranked by Q-value so these are deprioritized. Check overlap count — genuine hits have ≥2 gene overlaps.** |
| **No significant enrichments** | **Gene set not enriched** | **Try: (1) Lower threshold (50), (2) Widen TSS window, (3) Check if genes are regulatory targets.** |
| **SVG export error** | **Missing optional dependency** | **Normal - `generate_all_plots()` handles fallback automatically. Both PNG and SVG attempted; PNG always created.** |

## Interpretation Guidelines

**Q-value (BH-corrected, primary ranking):** <0.001 highly significant, <0.01 significant, <0.05 genome-wide significant
**Fold Enrichment:** >10x very strong, 5-10x strong, 2-5x moderate, <2x weak, >100,000x likely sentinel value (zero background overlap)
**Overlap Rate:** >50% core regulon, 20-50% key targets, <20% subset/indirect
**Threshold:** Controls MACS2 peak-calling stringency. Default 50 ≈ p<1e-5. See [references/peak_thresholds.md](references/peak_thresholds.md).

**⚠️ CRITICAL — When summarizing results to the user:**
- **Explain threshold meaning on first mention.** When first discussing the threshold in your interpretation, state what it means in practical terms (e.g., "threshold=50 corresponds to MACS2 peak-calling at approximately p < 1e-5, balancing sensitivity and specificity"). Do not defer this explanation to a caveats section only.
- **Cite overlap rates from `summary_report.md`.** Use the "Overlap Rate Summary" section for aggregate statistics. Do NOT round up or generalize (e.g., do not say "70–95%" if the report shows median 53%).
- **Distinguish experiments from factors.** Multiple experiments for the same TF are independent datasets, not independent regulators. Use the "Top Factors (aggregated)" table when reporting unique factor counts.
- **Acknowledge data availability bias.** If a factor has many experiments (>20), note that its prominence partly reflects being well-studied. Cite the experiment count from the aggregated table.
- **Use Median FE (Sig), not Median FE (All), to judge enrichment strength.** The aggregated table has two FE columns: "Median FE (Sig)" uses only significant experiments (q < 0.05), while "Median FE (All)" averages across all experiments with ≥2 overlaps including non-significant ones. For factors with many experiments but few significant (e.g., Experiments=137, Sig=5), the "All" median is diluted by non-significant experiments and will dramatically understate actual enrichment. **Do not conclude "weak enrichment" from a low Median FE (All) when Median FE (Sig) shows strong enrichment.** Always cite Median FE (Sig) when discussing a factor's enrichment strength.
- **Flag high experiment count with few significant.** If a factor has many experiments (>20) but few are significant (Sig column), note that most experiments for this factor do not show enrichment near these genes — only a subset of cell types/conditions do. Compare the Sig vs Experiments columns across factors to illustrate specificity differences.
- **Report gene discrepancies.** If the summary report shows the API used fewer regions than genes submitted, mention this to the user with possible causes. Do NOT speculate about which specific gene was dropped — the API does not report this information.
- **Report Ensembl vs API region count discrepancies prominently.** The Ensembl coordinate lookup and the ChIP-Atlas API use **different gene databases** (Ensembl vs RefSeq). Discrepancies are expected and should be explained clearly:
  - If Ensembl mapped **0 genes** while the API analyzed N: explain that these are independent systems; enrichment results are valid but lack independent coordinate verification. Do not dismiss this as merely "optional."
  - If Ensembl mapped **fewer genes** than the API (e.g., 4/5 vs 5/5): explain that the discrepancy reflects different database coverage — a gene may exist in RefSeq but have a failed/timed-out Ensembl lookup, or vice versa. State which system mapped how many genes and that the enrichment results use the API's own RefSeq mapping (not Ensembl).
  - In both cases, the enrichment results themselves are valid. The Ensembl step provides independent verification only.
- **Distinguish data-derived findings from background knowledge.** If citing known biology to interpret results, explicitly flag it as "from prior knowledge" or "based on known biology," not a conclusion from this analysis. Examples requiring explicit flagging: "TP63 and TP73 share the same DNA-binding domain as TP53" (protein family knowledge), "BRD4 is a bromodomain protein that binds acetylated histones at active promoters" (general factor biology), "these are canonical NF-κB targets" (pathway knowledge). Every such claim needs a phrase like "from prior knowledge of p53 family biology" — do not let background claims blend implicitly with data-derived findings.
- **Report the total count of significant factors, not just the top 10.** The aggregated table shows the top 10, but the summary report header states the total count (e.g., "Top 10 of 29 significantly enriched factors"). Always report this total — do not say "10 factors were identified" when more exist. Mention notable omissions if biologically relevant factors appear in the full `enrichment_results_significant.csv`.
- **Discuss all factors in the aggregated top table.** Every factor in the "Top Factors (aggregated)" table should be mentioned or briefly acknowledged. Do not silently omit factors — if one is less biologically interpretable, note that rather than skipping it.
- **Note multiple testing across aggregated factors.** The Q-values in the aggregated table are BH-corrected across experiments, not across factors. Each factor's "best Q-value" is cherry-picked from its most significant experiment. Interpreting all 10 top factors as independent discoveries overstates confidence — note this when presenting the aggregated table (e.g., "these per-experiment Q-values do not account for testing across multiple factors").
- **Small gene sets (≤10 genes): Lead with exploratory framing and connect every moderate-enrichment discussion to this caveat.** Frame the analysis as exploratory/demonstrative, not a powered study. **Your opening summary MUST lead with the exploratory nature** (e.g., "As an exploratory analysis with only 5 genes..." or "This demonstration-scale analysis with N genes identified...") rather than leading with the count of significant enrichments, which sounds more impressive than warranted at small N. Each gene contributes a large fraction of the overlap rate, so individual gene inclusion/exclusion substantially changes results. State this limitation prominently — do not bury it in a caveats section at the end. **Every time you discuss a factor with moderate fold enrichment (2–10x), you MUST explicitly note** that with only N input genes, a single gene's inclusion/exclusion could eliminate the signal entirely (e.g., "with only 5 input genes, this moderate enrichment should be interpreted with extra caution — removing a single gene could eliminate the signal").
- **Cite ChIP-Atlas publications.** When presenting results, cite the database: Zou et al. (2024) for ChIP-Atlas 3.0 and Oki et al. (2018) for the original ChIP-Atlas. Include these in any written summary or report to acknowledge the data source.

**Caveats (MUST include in any results summary):**
- Results biased toward well-studied factors and common cell types. Heavily studied TFs may appear enriched partly due to data availability (more experiments = more chances to be significant).
- Multiple experiments per factor are independent datasets, not independent biological signals. Use the aggregated factor table for deduplicated counts.
- Results depend on the peak-calling threshold used. Discuss the threshold chosen and note that results may differ at other stringencies.
- Validate key findings with orthogonal methods (expression, perturbation, motif analysis).

## Suggested Next Steps

1. **Threshold sensitivity check** — Re-run at threshold=100 or 200 to test whether top factors remain significant at more stringent peak-calling cutoffs. Offer this to the user as a robustness check (e.g., "Would you like me to re-run at threshold=100 to confirm these findings are robust?").
2. **Validate top factors** with literature, expression correlation, perturbation data
3. **Cell-type-specific analysis** with `cell_class` matching your experimental system
4. **Motif analysis** of promoter regions for top factor binding motifs
5. **Regulatory network** construction with top factors and target genes

## Related Skills

- **[gene-correlation-archs4](../gene-correlation-archs4/)** - Co-expression across 600K RNA-seq samples
- **[grn-pyscenic](../grn-pyscenic/)** - Gene regulatory networks from single-cell data

## References

- Zou et al. (2024). ChIP-Atlas 3.0: a data-mining suite to explore chromosome architecture. *Nucleic Acids Research*. [doi:10.1093/nar/gkad884](https://doi.org/10.1093/nar/gkad884)
- Zou et al. (2022). ChIP-Atlas 2021 update. *Nucleic Acids Research*. [doi:10.1093/nar/gkab933](https://doi.org/10.1093/nar/gkab933)
- Oki et al. (2018). ChIP-Atlas: a data-mining suite. *EMBO Reports* 19(12):e46255. [doi:10.15252/embr.201846255](https://doi.org/10.15252/embr.201846255)
- ChIP-Atlas: https://chip-atlas.org
- API documentation: See [references/chipatlas_metadata_format.md](references/chipatlas_metadata_format.md)
- Enrichment statistics: See [references/enrichment_statistics.md](references/enrichment_statistics.md)


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
