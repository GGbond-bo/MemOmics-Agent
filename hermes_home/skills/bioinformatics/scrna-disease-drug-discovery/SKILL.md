---
id: "skill_d7c1ec9d98a54a4eb7ae69a23c8314fe"
name: "scrna-disease-drug-discovery"
when_to_use: "[scrna-disease-drug-discovery] scRNA疾病药物发现pipeline：scRNA数据→靶点识别→化合物筛选→已有药重定位→候选药物+证据强度→结果排序"
display-name: "scRNA-seq Disease Drug Discovery Pipeline"
category: scRNA
short-description: "End-to-end scRNA-seq disease analysis with genetic evidence integration for multi-omics drug target prioritization."
detailed-description: "Comprehensive disease-focused drug discovery pipeline integrating single-cell RNA-seq analysis with human genetic evidence. From annotated scRNA-seq data (or raw with built-in preprocessing), performs pseudobulk differential expression per cell type, pathway enrichment (GSEA/ORA via decoupler and gseapy), ligand-receptor interaction analysis (liana-py multi-method consensus), and integrates disease-specific genetic evidence from Open Targets GWAS/ClinVar/gene burden, GeneBass rare variant burden, TWAS Atlas, eQTL Catalogue, and Open Targets L2G. Produces composite multi-omics drug target prioritization integrating transcriptomic DE, pathway centrality, L-R involvement, cell-type specificity, genetic association evidence, and druggability. Targets with convergent genetic + transcriptomic evidence receive highest priority. Demo dataset: GSE195452 systemic sclerosis skin biopsies."
starting-prompt: "Run an end-to-end scRNA-seq disease drug discovery analysis on GSE195452 systemic sclerosis skin biopsies with genetic evidence integration to identify and prioritize therapeutic targets. Perform differential expression, pathway analysis, ligand-receptor interactions, genetic target evidence from Open Targets and GeneBass, and multi-omics target prioritization. Generate a PDF report with intro, methods, results, conclusions and figures."
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



# scRNA-seq Disease Drug Discovery Pipeline

Identify and prioritize drug targets from disease scRNA-seq data by integrating transcriptomic evidence (differential expression, pathway enrichment, ligand-receptor interactions) with human genetic evidence (Open Targets GWAS/ClinVar, GeneBass rare variant burden, TWAS, eQTL). Targets with convergent multi-omics evidence receive the highest priority.

## When to Use This Skill

- **You have scRNA-seq data from a disease vs. control comparison** and want therapeutic targets
- **You want multi-omics target prioritization** combining expression + genetic evidence
- **You need cell-type-resolved drug discovery insights** (which cell types drive disease?)
- **You want to identify druggable targets** with convergent transcriptomic and genetic support

**Chains from** `scrnaseq-scanpy-core-analysis` output (`adata_processed.h5ad`) or accepts raw data.

**Don't use for:**
- Cell type annotation only (use `scrnaseq-scanpy-core-analysis`)
- Genetic-only target discovery (use `genetic-target-hypothesis`)
- Gene regulatory networks (use `grn-pyscenic`)
- Spatial transcriptomics (use `spatial-transcriptomics`)

## Quick Start (Demo Data)

**Test the full pipeline on SSc demo data (~20-40 min including API queries):**

```python
# Load demo dataset (GSE195452 SSc skin biopsies)
from load_data import load_demo_ssc_data
adata = load_demo_ssc_data()

# Run full pipeline
from pseudobulk_de import run_pseudobulk_de, get_disease_signature_genes
de_results = run_pseudobulk_de(adata, reference="Healthy", layer="counts")

from pathway_enrichment import run_pathway_analysis
pathway_results = run_pathway_analysis(adata, de_results)

from ligand_receptor import run_lr_analysis
lr_results = run_lr_analysis(adata)

sig_genes = get_disease_signature_genes(de_results)
candidate_genes = list(set(g for genes in sig_genes.values() for g in genes))[:200]

from genetic_evidence import collect_genetic_evidence
genetic_results = collect_genetic_evidence(candidate_genes, "systemic sclerosis")

from query_opentargets import query_target_annotations
ot_annotations = query_target_annotations(candidate_genes[:50])

from target_scoring import score_targets
scores = score_targets(de_results, pathway_results, lr_results, genetic_results, ot_annotations)

from generate_visualizations import generate_all_plots
generate_all_plots(adata, de_results, pathway_results, lr_results, genetic_results, scores)

from export_results import export_all
export_all(adata, de_results, pathway_results, lr_results, genetic_results, scores, ot_annotations)
```

**What you get:**
- **Dataset:** 277K cells from 165 SSc + healthy skin biopsies (subsampled for compute)
- **Expected results:** 100-700 DEGs across fibroblast subtypes, TGF-beta/ECM/IFN pathway enrichment, 15+ MEDIUM/HIGH priority targets with convergent genetic + transcriptomic evidence
- **Outputs:** ranked_targets.csv, 7+ PNG/SVG visualizations, per-cell-type DE CSVs, GSEA results, L-R interactions, genetic evidence summary, analysis_manifest.json

## Installation

| Package | Version | License | Commercial Use | Installation |
|---------|---------|---------|----------------|--------------|
| scanpy | >=1.9 | BSD-3-Clause | Permitted | `pip install scanpy` |
| anndata | >=0.8 | BSD-3-Clause | Permitted | `pip install anndata` |
| pydeseq2 | >=0.4 | MIT | Permitted | `pip install pydeseq2` |
| decoupler | >=1.4 | MIT | Permitted | `pip install decoupler` |
| liana-py | >=0.1.7 | BSD-3-Clause | Permitted | `pip install liana` |
| gseapy | >=1.0 | BSD-3-Clause | Permitted | `pip install gseapy` |
| requests | >=2.28 | Apache-2.0 | Permitted | `pip install requests` |
| pyarrow | >=10.0 | Apache-2.0 | Permitted | `pip install pyarrow` |
| matplotlib | >=3.4 | PSF | Permitted | `pip install matplotlib` |
| seaborn | >=0.12 | BSD-3-Clause | Permitted | `pip install seaborn` |
| adjustText | >=0.8 | MIT | Permitted | `pip install adjustText` |
| numpy | >=1.20 | BSD-3-Clause | Permitted | `pip install numpy` |
| pandas | >=1.3 | BSD-3-Clause | Permitted | `pip install pandas` |

**Install all:** `pip install scanpy anndata pydeseq2 decoupler liana gseapy requests pyarrow matplotlib seaborn adjustText`

**Optional (for preprocessing raw data):** `pip install scrublet celltypist harmonypy`

## Inputs

**Required:**
- **Annotated AnnData (.h5ad)** with cell type labels, condition labels, and sample/donor IDs
  - Expected from `scrnaseq-scanpy-core-analysis` or equivalent pipeline
  - Minimum: 3 cell types, >=10 cells per type, 2 conditions (disease + control)

**OR:**
- **Raw/filtered count matrix** (10X, H5, CSV) -- the skill will preprocess internally

**Required metadata columns:**
- `cell_type` (or user-specified) -- cell type annotations
- `condition` (or user-specified) -- disease status (e.g., "SSc", "Healthy")
- `sample_id` (or user-specified) -- biological replicate IDs for pseudobulk DE

**Optional:**
- Disease name for genetic evidence matching (default: inferred from condition labels)
- Species: Human (default) or Mouse

## Outputs

**Ranked target list:**
- `ranked_targets.csv` -- All scored targets with evidence columns: DE score, pathway score, L-R score, genetic score, druggability score, composite score, priority tier, convergence flag
- `target_evidence_cards.json` -- Per-target evidence summaries for report generation

**Differential expression:**
- `de_results_{celltype}.csv` -- Per-cell-type DE results (gene, log2FC, padj, baseMean)
- `de_summary.csv` -- Cross-cell-type DEG summary

**Pathway analysis:**
- `pathway_enrichment_{celltype}.csv` -- GSEA results per cell type
- `pathway_activity_scores.csv` -- decoupler pathway activity matrix

**Ligand-receptor interactions:**
- `lr_interactions.csv` -- Significant L-R pairs with source/target cell types, methods, consensus rank
- `lr_disease_specific.csv` -- Disease-enriched interactions (disease vs control comparison)

**Genetic evidence:**
- `genetic_ot_disease_genetics.csv` -- Open Targets GWAS/ClinVar/gene burden evidence
- `genetic_twas_associations.csv` -- TWAS Atlas results
- `genetic_summary.csv` -- Integrated genetic evidence per gene

**Analysis objects:**
- `adata_analyzed.h5ad` -- AnnData with DE results, pathway scores in .uns
  - Load with: `import scanpy as sc; adata = sc.read_h5ad('adata_analyzed.h5ad')`
- `analysis_manifest.json` -- Provenance: timestamp, parameters, step timing, output paths

**Visualizations (PNG + SVG at 300 DPI):**
- UMAP overview (cell type + condition)
- Volcano plots per cell type
- DEG heatmap across cell types (gene symbols, sorted by significance)
- Pathway activity heatmap (sorted by max |NES|, not alphabetical)
- L-R dot plot (disease-relevant interactions prioritized)
- Multi-omics convergence heatmap (targets x evidence types)
- Target ranking bar chart

**Reports:**
- `drug_discovery_report.pdf` -- Comprehensive PDF with Methods, Results, Figures, Conclusions

**PDF style rules:**
- **US Letter page size (8.5 x 11 in)** -- always set explicitly
- **No Unicode superscripts** -- use `3.36e-06` not Unicode chars
- **No half-empty pages** -- group headings with content
- **Figures >=80% page width**

## Decision Guide

| Decision | Quick Guide | Reference |
|----------|-------------|-----------|
| **Data type** | 10X Chromium (default). Smart-seq2/plate: lower min_cells to 3-5 | [references/workflow-details.md](references/workflow-details.md) |
| **Subsampling** | >50K cells: subsample to 2-5K per cell type per condition. Do NOT use flat global cap | [references/workflow-details.md](references/workflow-details.md) |
| **DE layer** | Always pass `layer="counts"` if .X is log-normalized. Auto-detected if layers["counts"] exists | [references/workflow-details.md](references/workflow-details.md) |
| **GSEA ranking** | Combined stat sign(LFC) x -log10(padj) (default). Skips cell types with failed DE | [references/workflow-details.md](references/workflow-details.md) |
| **Genetic evidence** | Open Targets GWAS/ClinVar is primary; GeneBass if disease is in UKB; TWAS/eQTL supplementary | [references/genetic_evidence_guide.md](references/genetic_evidence_guide.md) |
| **Analysis scope** | Full pipeline (default). Transcriptomics-only if no genetic evidence needed | Below |

## Clarification Questions

**Default settings (use unless user specifies otherwise):**
- Species: Human | Genetic evidence: Enabled | All analyses: Enabled

### 1. **Input Files** (ASK THIS FIRST):
   - Do you have an annotated scRNA-seq AnnData (.h5ad) with disease and control conditions?
   - **Or use demo data?** GSE195452: Systemic sclerosis skin biopsies (SSc + healthy controls)
   - If your own data: provide path to .h5ad file

### 2. **Metadata columns** (own data only):
   - Which column contains cell type labels? (default: `cell_type`)
   - Which column contains disease/condition labels? (default: `condition`)
   - Which column contains sample/donor IDs? (default: `sample_id`)

### 3. **Disease context** (own data only):
   - What disease are you studying? (needed for Open Targets genetic evidence and pathway context)
   - Species: Human (default) or Mouse?

### 4. **Analysis scope:**
   - a) Full pipeline with genetic evidence (recommended)
   - b) Transcriptomics only (DE + pathways + L-R, no genetic evidence)
   - c) Custom: specify which analyses

> :warning: **IF DEMO DATA SELECTED:** All parameters are pre-defined (SSc, human, full pipeline). **DO NOT ask questions 2-4.** Proceed directly to Step 1.

## Data Integrity Rules

:rotating_light: **NEVER reconstruct results from memory, notes, or session summaries.** :rotating_light:

If you cannot find the expected output CSV files after a crash or restart:
1. **STOP immediately** -- do NOT type quantitative values from memory
2. Check standard locations: `results/`, `./results/`, `/mnt/results/`, the working directory
3. Each analysis step saves CSVs incrementally (DE per cell type, GSEA per cell type, ranked_targets.csv) -- check for partial results
4. If files are truly missing, **re-run the analysis step** from the saved h5ad
5. **NEVER** hardcode target data like `[('GENE1', 0.82, 'HIGH'), ...]` from session notes

**Every quantitative value in the final report must be read from a CSV file on disk, not from session memory.**

**If the session crashed (OOM, kernel restart):** Partial CSVs from completed steps are on disk. Re-run only the steps that didn't complete. The h5ad file is the checkpoint -- all analysis can be re-derived from it.

## Standard Workflow

:rotating_light: **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** :rotating_light:

**Detailed step-by-step code:** [references/workflow-details.md](references/workflow-details.md)

**CRITICAL - DO NOT:**
- Write inline analysis code -- **STOP: Use the script functions**
- Write custom export code -- **STOP: Use `export_all()`**
- Skip verification messages -- **STOP: Check for verification messages after each step**
- Reconstruct values from memory after a crash -- **STOP: Read from saved CSVs or re-run**

**IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, re-run script
2. **Modify Script (5%)** - Edit the script file itself, document changes
3. **Use as Reference (4%)** - Read script, adapt approach, cite source
4. **Write from Scratch (1%)** - Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

---

**Step 1 -- Load and validate data:**
```python
# Option A: Demo data (GSE195452 SSc)
from load_data import load_demo_ssc_data
adata = load_demo_ssc_data()

# Option B: Pre-annotated h5ad
from load_data import load_annotated_h5ad
adata = load_annotated_h5ad("path/to/adata.h5ad",
                             celltype_key="cell_type",
                             condition_key="condition",
                             sample_key="sample_id")

# Option C: Raw data (will preprocess)
from load_data import load_raw_data
from preprocess import run_preprocessing_pipeline
adata = load_raw_data("path/to/data")
adata = run_preprocessing_pipeline(adata, species="human")

# CHECKPOINT: Save AnnData to disk immediately (OOM/timeout resilience)
# If the kernel restarts, reload from this file instead of rebuilding.
adata.write_h5ad("results/adata_processed.h5ad")
print("Checkpoint saved: results/adata_processed.h5ad")
```
**DO NOT write inline data loading code.**
**CHECKPOINT:** After loading, ALWAYS save the AnnData to disk. If the kernel restarts later, reload with `sc.read_h5ad("results/adata_processed.h5ad")` instead of re-downloading and rebuilding from GEO.

**VERIFICATION:** You MUST see: `"Data loaded successfully! N cells, M genes, K cell types, C conditions"`
**If you don't see this:** Check file path, verify .h5ad has required metadata columns (cell_type, condition, sample_id).

---

**Step 2 -- Run analysis:**

**Sample selection:** Use ALL available samples — statistical power depends on biological replicates, not cell count. Subsample CELLS within samples if needed for memory, but do NOT drop samples. For datasets with >100K cells, subsample to ~3000-5000 cells per cell type per condition while keeping all samples represented. For plate-based data (Smart-seq2), use patient_id (not amplification batch) as the pseudobulk grouping variable. See [references/workflow-details.md](references/workflow-details.md) for details.

**GSEA thresholds:** GSEA output tables report all pathways with FDR < 0.25 (standard for GSEA reporting and exploration). Target scoring uses stricter FDR < 0.05 for pathway_score contribution. Both thresholds are intentional.

```python
# 2a. Differential expression (disease vs control per cell type)
# IMPORTANT: pass layer="counts" if adata.X is log-normalized
from pseudobulk_de import run_pseudobulk_de, get_disease_signature_genes
de_results = run_pseudobulk_de(adata,
                                condition_key="condition",
                                sample_key="sample_id",
                                celltype_key="cell_type",
                                reference="Healthy",
                                layer="counts")

# 2b. Pathway enrichment (uses combined ranking: sign(LFC) x -log10(padj))
from pathway_enrichment import run_pathway_analysis
pathway_results = run_pathway_analysis(adata, de_results, species="human")

# 2c. Ligand-receptor interactions
# Auto-merges to max 20 cell types, subsamples to 2000 cells/type, 100 permutations
# for tractable runtime (~5-10 min). Increase n_perms for publication-quality.
from ligand_receptor import run_lr_analysis
lr_results = run_lr_analysis(adata,
                              celltype_key="cell_type",
                              condition_key="condition",
                              max_celltypes=20,
                              max_cells_per_type=2000,
                              n_perms=100)

# 2d. Collect candidate gene list from DE results (for genetic + OT queries)
sig_genes = get_disease_signature_genes(de_results, padj_threshold=0.05, log2fc_threshold=0.25)
candidate_genes = list(set(g for genes in sig_genes.values() for g in genes))[:200]

# 2e. Genetic evidence (queries Open Targets GWAS/ClinVar + TWAS + eQTL + L2G)
from genetic_evidence import collect_genetic_evidence
genetic_results = collect_genetic_evidence(
    gene_list=candidate_genes,
    disease_name="systemic sclerosis",
    include_genebass=True)

# 2f. Target scoring
# CRITICAL: Use score_targets_simple() — DO NOT write custom scoring code.
# Custom scorers miss: convergence bonus, cross-compartment L-R bridging,
# adaptive reweighting, NES-weighted pathway scoring, and DE cap logic.
from target_scoring import score_targets_simple
scores = score_targets_simple({
    "de": de_results,
    "pathway": pathway_results,
    "lr": lr_results,
    "genetic": genetic_results,
})
# Druggability auto-queried for top 20 genes. For all: pass "ot_annotations" key.

# 2g. GWAS Gene Landscape (MANDATORY for SSc demo)
# Maps top SSc GWAS genes to their cell-type expression context.
# Separate from the DE-derived target list — bridges immune-fibroblast disconnect.
from genetic_evidence import get_top_gwas_genes, assess_gwas_genes_in_adata
gwas_genes = get_top_gwas_genes("systemic sclerosis", n=20)
gwas_context = assess_gwas_genes_in_adata(adata, gwas_genes, de_results=de_results)
```
**DO NOT write custom scoring code.** The `score_targets_simple()` function handles adaptive reweighting, convergence bonuses, cross-compartment L-R bridging, and NES-weighted pathway scoring. Custom scorers miss these and produce invalid priority tiers.

**VERIFICATION:** After 2f you MUST see: `"Target scoring complete! N targets scored, M HIGH, ..."`
After 2g: `"GWAS gene landscape: N genes mapped, M are DE in at least one cell type"`
**If DE returns 0 DEGs for a cell type:** DESeq2 auto-falls back to Wilcoxon. GSEA quality gate skips cell types with failed DE.
**If LIANA takes >15 min:** Normal for large datasets. Partial results saved at each step.

**Report structure:** The PDF report should have TWO target sections:
1. **Multi-omics targets** — DE-derived, scored across all evidence dimensions (from `score_targets`)
2. **GWAS gene landscape** — top SSc genetic targets mapped to cell types (from `assess_gwas_genes_in_adata`), showing which GWAS genes are expressed where and whether they're DE. This bridges the immune-fibroblast disconnect: GWAS targets (IRF5, STAT4) are immune genes, while DE targets are fibroblast genes. Both are real biology.

---

**Step 3 -- Generate visualizations:**
```python
from generate_visualizations import generate_all_plots
generate_all_plots(adata, de_results, pathway_results, lr_results,
                    genetic_results, scores, output_dir="results",
                    gwas_context_df=gwas_context)
```
**DO NOT write inline plotting code. This generates 11 standard visualizations including the GWAS gene landscape.**

**VERIFICATION:** You MUST see: `"All plots generated successfully! N visualizations saved"`
**If a plot fails:** Non-fatal -- other plots still generated. Check WARNING messages.

---

**Step 4 -- Export results:**
```python
from export_results import export_all
export_all(adata, de_results, pathway_results, lr_results,
            genetic_results, scores, output_dir="results")
```
**DO NOT write custom export code. Use export_all().**

**VERIFICATION:** You MUST see: `"=== Export Complete ==="`
**If you don't see "Export Complete":** The export did not complete. Re-run the export function.

## Target Scoring Methodology

See [references/target_scoring_methodology.md](references/target_scoring_methodology.md) for full details.

**Multi-omics composite score (convergent genetic + transcriptomic evidence):**

| Component | Weight | Description |
|-----------|--------|-------------|
| Differential expression | 0.20 | -log10(padj) weighted by log2FC magnitude. Multi-cell-type DE bonus. |
| Pathway centrality | 0.15 | Disease-relevant enriched pathways containing the gene (FDR < 0.05). |
| L-R involvement | 0.15 | Consensus rank for disease-specific interactions. Reweighted to 0 if unavailable. |
| Cell-type specificity | 0.10 | Tau-like specificity of disease effect in disease-relevant cell types. |
| Genetic evidence | 0.25 | Open Targets GWAS/ClinVar (primary) + GeneBass + TWAS + eQTL + L2G. |
| Druggability | 0.15 | Open Targets tractability, known drugs, genetic constraint. |

**Convergence bonus (1.2x):** Targets with BOTH genetic AND transcriptomic evidence.

**Priority tiers:** HIGH (>=0.55), MEDIUM (0.35-0.55), LOW (<0.35)

**Adaptive reweighting:** If L-R or genetic evidence is unavailable, those weights are redistributed to remaining components (weights always sum to 1.0).

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| `ImportError: liana` | Not installed | `pip install liana` |
| `ImportError: decoupler` | Not installed | `pip install decoupler` |
| Pseudobulk DE blocked: N=1 | Single sample per condition | Need >=2 replicates. Fallback: cell-level Wilcoxon (exploratory) |
| DESeq2 degenerate results (all padj = 1.0) | Insufficient pseudobulk replicates for a cell type | Auto-falls back to Wilcoxon for that cell type. GSEA quality gate skips it. |
| GSEA skipped for a cell type | 0 significant DEGs (DE failure) | Expected -- GSEA on failed DE produces artifacts. Only runs on cell types with real signal. |
| GeneBass data not found | Not on Biomni datalake | Skill uses Open Targets GWAS/ClinVar as primary genetic evidence instead |
| No significant L-R interactions | Too few cell types or cells | Need >=3 cell types, >=10 cells per type. L-R weight redistributed in scoring. |
| LIANA takes >15 minutes | Large dataset with many cell types | Normal for >10K cells x 10+ cell types. Partial results saved at each step. |
| TWAS Atlas timeout | API issues | Retry with backoff (built-in). Falls back to other genetic evidence. |
| Open Targets rate limit | Too many gene queries | Built-in rate limiting (0.5s between requests) |
| SVG export failed | Missing svglite/cairocffi | Normal -- PNG always generated. Both created in most environments. |

**Expected warnings (not errors):**

| Warning | Meaning | Action |
|---------|---------|--------|
| DESeq2 degenerate results, falling back to Wilcoxon | Cell type has too few samples for pseudobulk | Normal for subsampled data. Wilcoxon results are exploratory. |
| Skipping GSEA for [cell type] | DE failed for that cell type | GSEA quality gate working correctly. No action needed. |
| L-R consensus_rank is all NaN | liana version mismatch | Auto-falls back to specificity_rank. Scoring reweights. |

## Suggested Next Steps

1. **Deep-dive on top targets** -- Use `genetic-target-hypothesis` for detailed genetic characterization of top-scored targets
2. **Trajectory analysis** -- Use `scrna-trajectory-inference` to trace disease progression in key cell types
3. **Regulatory networks** -- Use `grn-pyscenic` to identify TF regulators of disease programs
4. **Validation** -- Use `literature-review` to check published evidence for top targets

## Related Skills

**Upstream:** scrnaseq-scanpy-core-analysis (produces input h5ad) | **Complementary:** genetic-target-hypothesis (genetics-first approach), cell-cell-communication (R/CellChat alternative), functional-enrichment-from-degs (R/clusterProfiler alternative) | **Downstream:** grn-pyscenic, scrna-trajectory-inference, literature-review

## References

1. **Scanpy:** Wolf FA, et al. (2018) *Genome Biol*. 19:15.
2. **PyDESeq2:** Muzellec B, et al. (2023) *Bioinformatics*. 39(9):btad547.
3. **LIANA:** Dimitrov D, et al. (2022) *Nat Commun*. 13:3224.
4. **decoupler:** Badia-i-Mompel P, et al. (2022) *Bioinformatics*. 38(Supplement_2):ii81-ii88.
5. **GeneBass:** Karczewski KJ, et al. (2022) *Nature*. 590:791-797.
6. **Open Targets:** Ochoa D, et al. (2023) *Nucleic Acids Res*. 51(D1):D1302-D1310.
7. **TWAS Atlas:** TWAS Atlas 2.0 (2025) *Nucleic Acids Res*.

**Detailed guides:** [references/workflow-details.md](references/workflow-details.md) | [references/common-patterns.md](references/common-patterns.md) | [references/ssc_biology.md](references/ssc_biology.md) | [references/target_scoring_methodology.md](references/target_scoring_methodology.md) | [references/genetic_evidence_guide.md](references/genetic_evidence_guide.md) | [references/dataset_guide.md](references/dataset_guide.md) | [references/liana_methods.md](references/liana_methods.md)

**Scripts:** [scripts/](scripts/) | **Evaluation:** [assets/eval/](assets/eval/)


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
     topic="疾病药物靶点发现 —— {疾病}",
     context="数据: {细胞数} cells | 方法: {scRNA+遗传证据整合} | 结果: {n}个候选靶点",
     knowledge_base_info=<KB内容>,
   )
   辩论: 靶点优先级排序合理吗？遗传证据支持吗？与文献已知靶点一致吗？
3. save_conclusions(module="03_advanced", topic="Drug Target Discovery", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```
