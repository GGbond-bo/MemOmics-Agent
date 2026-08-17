---
id: "skill_cf9489278b984eef91e08a40b68943be"
name: "upstream-regulator-analysis"
when_to_use: "[upstream-regulator-analysis] 上游调控因子分析：差异基因→Ingenuity/DecoupleR→激活/抑制调控因子→机制推测"
display-name: "Upstream Regulator Analysis"
category: scRNA
short-description: "Integrate ChIP-Atlas TF binding data with RNA-seq differential expression to identify upstream regulators driving transcriptomic changes."
detailed-description: "Identifies transcription factors driving differential expression by integrating ChIP-Atlas peak enrichment (433,000+ public ChIP-seq experiments) with RNA-seq DE results. Submits DE gene lists to ChIP-Atlas API, downloads target gene lists for top enriched TFs, computes Fisher's exact test for target-DE overlap, measures directional concordance (activator vs repressor), and ranks TFs by a combined regulatory score. Supports 10 genomes including human (hg38, hg19), mouse (mm10, mm9), rat (rn6), and model organisms."
starting-prompt: Identify upstream regulators driving my differential expression results using ChIP-Atlas binding data . .
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



# Upstream Regulator Analysis

Identify transcription factors (TFs) driving observed differential expression by integrating **ChIP-Atlas TF binding data** (epigenomics) with **RNA-seq DE results** (transcriptomics). Ranks TFs by a combined regulatory score incorporating binding enrichment, target-DE overlap (Fisher's exact test), and directional concordance (activator vs repressor).

## When to Use This Skill

**Use when you:**
- Have DE results and want to identify TFs driving expression changes
- Need to go beyond simple gene list enrichment to mechanistic TF-level evidence
- Want to distinguish **activators** (targets upregulated) from **repressors** (targets downregulated)
- Want to integrate epigenomics (ChIP-seq) with transcriptomics (RNA-seq) in one analysis

**Don't use for:**
- Single-cell DE results (designed for bulk RNA-seq DE)
- Organisms not in ChIP-Atlas (see supported genomes below)
- Histone mark analysis (use `chip-atlas-peak-enrichment` directly)
- When you only need TF binding enrichment without target gene integration

**Requires:** Internet access (ChIP-Atlas API + data server). Runtime: **15-25 minutes** (API polling + target gene downloads).

## Installation

```bash
pip install pandas numpy scipy requests matplotlib seaborn reportlab
```

| Package | Version | License | Commercial Use |
|---------|---------|---------|----------------|
| pandas | ≥1.5 | BSD-3 | ✅ Permitted |
| numpy | ≥1.21 | BSD-3 | ✅ Permitted |
| scipy | ≥1.9 | BSD-3 | ✅ Permitted |
| requests | ≥2.28 | Apache-2.0 | ✅ Permitted |
| matplotlib | ≥3.6 | PSF | ✅ Permitted |
| seaborn | ≥0.12 | BSD-3 | ✅ Permitted |
| reportlab | ≥3.6 | BSD | ✅ Permitted |

**Sibling skill dependencies:** Requires `chip-atlas-peak-enrichment` and `chip-atlas-target-genes` directories at the same level.

## Inputs

- **DE results CSV/TSV** with columns: gene symbol, log2 fold change, adjusted p-value
  - Supports DESeq2 (`log2FoldChange`, `padj`), edgeR (`logFC`, `FDR`), limma (`logFC`, `adj.P.Val`)
  - Column names auto-detected; override with parameters if needed
- **Genome:** hg38, hg19, mm10, mm9, rn6, dm6, dm3, ce11, ce10, sacCer3

## Outputs

**Analysis objects:**
- `analysis_object.pkl` - Complete analysis for downstream use
  - Load with: `import pickle; obj = pickle.load(open('analysis_object.pkl', 'rb'))`
  - Contains: regulon_scores, enrichment results, target gene data, DE data, parameters

**CSV results:**
- `regulon_scores_all.csv` - All scored TFs with regulatory score, Fisher's p-value, concordance, direction
- `regulon_scores_top.csv` - Top 20 TFs
- `target_overlaps.csv` - Per-TF target gene overlap with DE status (up/down)
- `enrichment_up.csv` / `enrichment_down.csv` - ChIP-Atlas peak enrichment results

**Visualizations (PNG + SVG):**
- `upstream_regulators_top_regulators` - Bar chart: TFs ranked by regulatory score
- `upstream_regulators_target_overlap` - Stacked bar: TF targets classified as up/down/unchanged
- `upstream_regulators_evidence_scatter` - Scatter: ChIP enrichment vs Fisher significance
- `upstream_regulators_heatmap` - Clustermap: TFs × regulatory evidence metrics

**Reports:**
- `summary_report.md` - Human-readable analysis summary
- `analysis_report.pdf` - Publication-quality PDF with Introduction, Methods, Results, Conclusions
  - Requires: `pip install reportlab` (optional — markdown report generated regardless)

## Clarification Questions

1. **Input Files** (ASK THIS FIRST):
   - Do you have DE results (CSV/TSV) to analyze?
   - If uploaded: Is this the DE results file you'd like to find upstream regulators for?
   - Expected columns: gene symbol + log2FoldChange + adjusted p-value
   - **Or use example data?** Three options:
     - a) **Estrogen/MCF7 dataset** (recommended) — real DE results from GSE51403 (estradiol-treated MCF7 breast cancer cells, ~58K genes). Expected top regulator: ESR1
     - b) **Airway dataset** — real DE results from GSE52778 (dexamethasone-treated airway smooth muscle cells, ~58K genes). Expected top regulator: NR3C1
     - c) Synthetic TP53-driven data (~200 genes, fast, offline)

2. **Analysis Options:**
   - *(If using example data)* Choose analysis parameters:
     - a) Standard analysis (top 10 TFs, q < 0.05) (recommended)
     - b) Comprehensive analysis (top 15 TFs, q < 0.1)
   - *(If using your own data)* What species/genome?
     - a) Human (hg38)
     - b) Human (hg19)
     - c) Mouse (mm10)
     - d) Other (specify)

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Step 1 - Load data:**
```python
# For example data (real estrogen/MCF7 dataset, downloads from EBI Expression Atlas):
from scripts.load_example_data import load_example_data
de_data = load_example_data(source="estrogen")

# Alternative: airway dataset (dexamethasone, real data):
de_data = load_example_data(source="airway")

# For synthetic data (offline, fast, TP53-driven):
de_data = load_example_data(source="synthetic")

# For user data:
from scripts.load_de_results import load_de_results
de_data = load_de_results("path/to/de_results.csv")
```
**✅ VERIFICATION:** `"✓ Data loaded successfully: N total genes, M DE genes (X up, Y down)"`

**Step 2 - Run integration analysis:**
```python
from scripts.run_integration_workflow import run_integration_workflow
results = run_integration_workflow(de_data, genome="hg38", output_dir="regulator_results")
```
**DO NOT write inline API code or custom scoring. Just call the workflow function.**

⏱️ **This step takes 15-25 minutes** (ChIP-Atlas API polling + target gene downloads).

**✅ VERIFICATION:** `"✓ Integration analysis completed successfully!"`

**Step 3 - Generate visualizations:**
```python
from scripts.generate_all_plots import generate_all_plots
generate_all_plots(results, output_dir="regulator_results")
```
🚨 **DO NOT write inline plotting code (ggplot, ggsave, etc.). Just use the script.** 🚨

**✅ VERIFICATION:** `"✓ All visualizations generated successfully!"`

**Step 4 - Export results:**
```python
from scripts.export_all import export_all
export_all(results, output_dir="regulator_results")
```
**DO NOT write custom export code. Use export_all().**

**✅ VERIFICATION:** `"=== Export Complete ==="`

⚠️ **CRITICAL - DO NOT:**
- ❌ **Write inline API code** → **STOP: Use `run_integration_workflow()`**
- ❌ **Write inline plotting code** → **STOP: Use `generate_all_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Write custom Fisher's test code** → **STOP: Built into `score_regulons()`**

**⚠️ IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, re-run script
2. **Modify Script (5%)** - Edit the script file itself, document changes
3. **Use as Reference (4%)** - Read script, adapt approach, cite source
4. **Write from Scratch (1%)** - Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| **ImportError: sibling skill not found** | Missing chip-atlas-peak-enrichment or chip-atlas-target-genes | Ensure both sibling skills are installed at the same directory level |
| **API 400 error** | Empty cellClass or invalid parameters | Use `cell_class="All cell types"` (must be non-empty) |
| **Both enrichment analyses failed** | Too few DE genes per direction | Need ≥3 genes in at least one direction (up or down) |
| **No TFs passed enrichment threshold** | Stringent cutoff or few DE genes | Try `min_enrichment_qvalue=0.1` or add more DE genes |
| **Target gene download timeout** | Large TF file or slow connection | Script retries; if persistent, reduce `max_tfs` |
| **No TFs with target gene data** | Enriched TFs are histone marks | Filter with `antigen_class="TFs and others"` (default) |
| **SVG export failed** | Missing svglite/cairo | Normal - PNG always generated; SVG is optional |

## Interpretation Guidelines

### Regulatory Score
Combined evidence: `-log10(Fisher P) × Concordance × -log10(ChIP Q)`

| Score | Evidence |
|-------|----------|
| >100 | Very strong — high ChIP enrichment + significant target overlap + high concordance |
| 50-100 | Strong |
| 20-50 | Moderate |
| <20 | Weak — interpret with caution |

### Direction Classification
- **Activator** (concordance >60%, majority up): TF likely activates these genes
- **Repressor** (concordance >60%, majority down): TF likely represses these genes
- **Mixed** (concordance ≤60%): No clear directional bias — context-dependent regulation

### Key Caveats
- Results biased toward well-studied TFs/cell types in ChIP-Atlas
- Binding enrichment ≠ regulatory causation (validate with perturbation)
- Directional labels assume simple activation/repression (ignores context-dependent regulation)
- Combined score is a heuristic ranking, not a formal multi-test correction
- Fisher's test assumes independence (may be violated if targets cluster in pathways)

## Suggested Next Steps

After identifying upstream regulators:
- **Validate binding:** Use `chip-atlas-target-genes` to examine cell-type-specific binding patterns for top TFs
- **Functional enrichment:** Use `functional-enrichment-from-degs` on TF-target gene subsets
- **Co-expression:** Use `gene-correlation-archs4` to check if TF and targets co-express
- **Network inference:** Use `grn-pyscenic` for single-cell GRN validation
- **Literature review:** Use `literature-review` to validate TF-disease associations

## Related Skills

- `chip-atlas-peak-enrichment` - Component: TF binding enrichment analysis
- `chip-atlas-target-genes` - Component: TF target gene retrieval
- `bulk-rnaseq-counts-to-de-deseq2` - Upstream: generates DE results input
- `de-results-to-gene-lists` - Upstream: generates filtered gene lists
- `functional-enrichment-from-degs` - Complementary: pathway-level enrichment

## References

- Zou Z, et al. (2024) ChIP-Atlas 3.0: a gene regulation data-mining platform. *Nucleic Acids Res.* 52(W1):W159-W166
- Oki S, et al. (2018) ChIP-Atlas: a data-mining suite. *EMBO Rep.* 19(12):e46255
- Fisher RA (1922) On the interpretation of chi-squared. *J R Stat Soc.* 85(1):87-94


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
