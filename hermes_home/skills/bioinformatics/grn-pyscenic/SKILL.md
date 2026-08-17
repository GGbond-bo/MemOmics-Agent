---
id: "skill_35e45ff33cb141a981a3fc5711c4760f"
name: "grn-pyscenic"
when_to_use: "[grn-pyscenic] 需使用grn pyscenic功能，适用于相关生信分析场景"
display-name: "Gene Regulatory Network Inference (pySCENIC)"
category: scRNA
short-description: Infer transcription factor regulatory networks and cell-level TF activity from single-cell RNA-seq data.
detailed-description: Discover gene regulatory networks (GRNs) de novo from single-cell RNA-seq using pySCENIC. Identifies transcription factor (TF) regulons through co-expression analysis (GRNBoost2), validates with motif enrichment (cisTarget), and calculates cell-level TF activity scores (AUCell). Use when you need to discover TF-target relationships directly from your data, identify cell-type-specific regulatory programs, or score individual cells for TF activity. Requires 500+ cells for robust inference. Not recommended for bulk RNA-seq (use functional enrichment or curated network approaches instead). Computationally intensive, requires reference databases and 16GB+ RAM.
starting-prompt: Infer gene regulatory networks and TF activity from my single-cell RNA-seq data . . 
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



# Gene Regulatory Network Inference (pySCENIC)

Infer gene regulatory networks (GRNs) de novo from single-cell RNA-seq data using pySCENIC. This workflow discovers transcription factor (TF) regulons directly from expression patterns and calculates cell-level TF activity scores.

## When to Use This Skill

Use pySCENIC GRN inference when you need to:
- ✅ **Discover TF-target relationships** de novo from single-cell RNA-seq data
- ✅ **Calculate cell-level TF activity** scores for regulatory programs
- ✅ **Identify cell-type-specific** transcriptional programs
- ✅ **Find key regulators** driving cell state transitions or differentiation
- ✅ **Compare regulatory programs** across conditions, tissues, or species

**Don't use this skill for:**
- ❌ Bulk RNA-seq with few samples → Use functional-enrichment-from-degs or tf-activity workflows
- ❌ Quick TF activity from DE results → Use curated network approaches (faster, less computational)
- ❌ <500 cells → Insufficient for robust GRN inference
- ❌ Limited computational resources → Requires 16GB+ RAM, several hours runtime

**Key Concept:** Unlike curated network approaches, pySCENIC infers TF-target relationships directly from your data using co-expression analysis, then validates them using motif enrichment in cis-regulatory regions.

**The SCENIC Pipeline:**
1. **GRN Inference (GRNBoost2)**: Identify co-expression modules linking TFs to potential target genes
2. **Regulon Prediction (cisTarget)**: Prune targets to those with TF binding motifs in promoters
3. **Cell Activity Scoring (AUCell)**: Score each cell for regulon activity

## Quick Start

**Fastest way to test the workflow (~10-15 minutes):**

```python
# Step 1: Load example PBMC data (500 cells)
from scripts.load_example_data import load_pbmc3k_example
adata, ex_matrix = load_pbmc3k_example(preprocess=True, subsample=500)

# Step 2: Run complete GRN workflow
from scripts.run_grn_workflow import run_complete_grn_workflow
results = run_complete_grn_workflow(
    ex_matrix=ex_matrix,
    tf_list_file="pyscenic_databases/allTFs_hg38.txt",
    database_glob="pyscenic_databases/*.feather",
    motif_annotations_file="pyscenic_databases/motifs-v10nr_clust-nr.hgnc-m0.001-o0.0.tbl",
    output_dir="scenic_test_results",
    n_workers=4
)

# Step 3: Visualize and export
from scripts.integrate_with_adata import integrate_with_adata
from scripts.plot_regulon_visualizations import generate_all_visualizations
from scripts.export_all import export_all

adata = integrate_with_adata(adata, results['auc_matrix'], results['regulons'])
generate_all_visualizations(results['auc_matrix'], results['regulons'], adata,
                            output_dir="scenic_test_results/plots")
export_all(results['regulons'], results['auc_matrix'], results['auc_summary'],
           results['adjacencies'], output_dir="scenic_test_results")
```

**Expected output:** 20-40 regulons, 13 output files (CSVs, plots, integrated H5AD)

**Note:** Requires databases to be downloaded first (see Installation → Reference Databases section).

## Installation

### Required Software

| Software | Version | License | Commercial Use | Installation |
|----------|---------|---------|----------------|--------------|
| pySCENIC | ≥0.12.0 | GPL-3.0 | ✅ Permitted | `pip install pyscenic` |
| arboreto | ≥0.1.6 | BSD-3-Clause | ✅ Permitted | Installed with pySCENIC |
| ctxcore | ≥0.2.0 | GPL-3.0 | ✅ Permitted | Installed with pySCENIC |
| scanpy | ≥1.9 | BSD-3-Clause | ✅ Permitted | `pip install scanpy` |
| pandas | ≥1.3 | BSD-3-Clause | ✅ Permitted | `pip install pandas` |
| numpy | ≥1.20 | BSD-3-Clause | ✅ Permitted | `pip install numpy` |
| loompy | ≥3.0 | BSD-3-Clause | ✅ Permitted | `pip install loompy` |
| networkx | ≥2.6 | BSD-3-Clause | ✅ Permitted | `pip install networkx` |
| seaborn | ≥0.11 | BSD-3-Clause | ✅ Permitted | `pip install seaborn` |
| matplotlib | ≥3.4 | PSF-based | ✅ Permitted | `pip install matplotlib` |
| reportlab | ≥3.6 | BSD | ✅ Permitted | `pip install reportlab` |

**Minimum Python version:** Python ≥3.8

**Quick install:**
```bash
pip install pyscenic scanpy pandas numpy loompy networkx seaborn matplotlib reportlab
```

**Note:** pySCENIC automatically installs arboreto (for GRNBoost2) and ctxcore (for cisTarget) as dependencies.

### Reference Databases (Required)

Download species-specific databases from [SCENIC resources](https://resources.aertslab.org/cistarget/):

**For human (hg38):**
```bash
wget https://resources.aertslab.org/cistarget/databases/homo_sapiens/hg38/refseq_r80/mc_v10_clust/gene_based/hg38_10kbp_up_10kbp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather
wget https://resources.aertslab.org/cistarget/motif2tf/motifs-v10nr_clust-nr.hgnc-m0.001-o0.0.tbl
wget https://resources.aertslab.org/cistarget/tf_lists/allTFs_hg38.txt
```

**For other species:** See [references/database_downloads.md](references/database_downloads.md)

**Database requirements:**
- Motif ranking database (.feather format, ~1-2GB)
- Motif annotation file (.tbl format)
- TF list for your species

## Inputs

### Required Input

1. **Single-cell expression matrix** (one of):
   - AnnData object (.h5ad) with raw or normalized counts
   - Loom file (.loom)
   - CSV/TSV matrix (genes × cells)

2. **Reference databases** (downloaded from SCENIC resources):
   - Motif ranking database (e.g., `hg38_10kbp_up_10kbp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather`)
   - Motif annotation file (e.g., `motifs-v10nr_clust-nr.hgnc-m0.001-o0.0.tbl`)
   - TF list (e.g., `allTFs_hg38.txt`)

### Data Requirements

- **Minimum cells**: 500 (1,000+ recommended for robust GRN inference)
- **Minimum genes**: 2,000+ expressed genes
- **Memory**: 16GB+ RAM (more for large datasets)
- **Runtime**: 1-4 hours depending on dataset size
- **QC**: Apply basic quality filtering before SCENIC (remove low-quality cells/genes)

## Outputs

### Files Generated

**Analysis objects (Pickle):**
- `regulons.pkl` - Regulon objects for downstream analysis
  - Load with: `regulons = pickle.load(open('regulons.pkl', 'rb'))`
  - Required for: Downstream TF activity analysis, network visualization
- `auc_matrix.pkl` - AUCell activity matrix (cells × regulons)
  - Load with: `auc_matrix = pickle.load(open('auc_matrix.pkl', 'rb'))`

**Results (CSV):**
- `adjacencies.csv` - Raw TF-target co-expression (GRNBoost2 output)
- `regulons.csv` - Final TF-target relationships after motif pruning
- `aucell_matrix.csv` - Cell × Regulon activity scores (values 0-1)
- `aucell_summary.csv` - Per-regulon statistics
- `scenic_regulon_summary.csv` - Comprehensive regulon summary

**Integrated data:**
- `adata_with_scenic.h5ad` - AnnData with integrated regulon activities

**Visualizations (PNG + SVG):**
- `regulon_heatmap.png/.svg` - Top regulons by variance
- `regulon_network.png/.svg` - TF-target network visualization

**Reports:**
- `scenic_report.md` - Analysis summary with top regulons
- `scenic_analysis_report.pdf` - Publication-quality PDF with Introduction, Methods, Results (embedded figures), Conclusions
  - Requires: `pip install reportlab` (optional — markdown report generated regardless)

## Clarification Questions

**Before running, confirm:**

1. **Input Files** (ASK THIS FIRST):
   - Do you have single-cell RNA-seq data to analyze?
   - If uploaded: Is this the .h5ad/.loom/matrix file you'd like to use?
   - Expected formats: AnnData (.h5ad), Loom (.loom), CSV/TSV matrix
   - **Or use example/demo data?** Use `load_example_data.py` for PBMC 3k (~2,700 cells, 30-45 min test)

2. **Species?**
   - Human (hg38) - most common, databases readily available
   - Mouse (mm10) - databases available
   - Other species - check database availability first

3. **Dataset size?**
   - 500-2,000 cells → Minimum viable, ~1-2 hours
   - 2,000-10,000 cells → Good, ~2-3 hours
   - 10,000+ cells → Excellent, may need subsampling, 3-4 hours

4. **Do you have the cisTarget databases downloaded?**
   - Yes → Provide paths to .feather, .tbl, and TF list files
   - No → Will download during setup (~2-3GB, 10-15 min)

5. **What outputs do you need?**
   - Regulons only (TF-target relationships)
   - AUCell scores (cell-level TF activity)
   - Both with visualizations (recommended)

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Step 1 - Load data and run GRN inference:**
```python
# Load expression data
# Option A: Load your own data
from scripts.load_expression_data import load_expression_data
adata, ex_matrix = load_expression_data("scrnaseq_data.h5ad")

# Option B: Load example PBMC 3k data for testing
# from scripts.load_example_data import load_pbmc3k_example
# adata, ex_matrix = load_pbmc3k_example()

# Run GRN inference with GRNBoost2
from scripts.run_grn_workflow import run_complete_grn_workflow
results = run_complete_grn_workflow(
    ex_matrix=ex_matrix,
    tf_list_file="allTFs_hg38.txt",
    database_glob="pyscenic_databases/*.feather",
    motif_annotations_file="pyscenic_databases/motifs-v10nr_clust-nr.hgnc-m0.001-o0.0.tbl",
    output_dir="scenic_results"
)
```
**DO NOT write inline GRNBoost2, cisTarget, or AUCell code. Use the script.**

**✅ VERIFICATION:** You should see:
- `"✓ Data loaded successfully: X cells, Y genes"`
- `"✓ GRN inference completed: X TF-target pairs"`
- `"✓ cisTarget pruning completed: X regulons"`
- `"✓ AUCell scoring completed"`

**Step 2 - Integrate with AnnData:**
```python
from scripts.integrate_with_adata import integrate_with_adata
adata = integrate_with_adata(
    adata,
    results['auc_matrix'],
    results['regulons'],
    output_file="scenic_results/adata_with_scenic.h5ad"
)
```

**✅ VERIFICATION:** `"✓ Integration completed: regulon activities added to adata.obsm['X_aucell']"`

**Step 3 - Generate visualizations:**
```python
from scripts.plot_regulon_visualizations import generate_all_visualizations
generate_all_visualizations(
    results['auc_matrix'],
    results['regulons'],
    adata,
    top_n=20,
    output_dir="scenic_results/plots"
)
```
🚨 **DO NOT write inline plotting code (matplotlib, seaborn, etc.). Just use the script.** 🚨

**The script handles PNG + SVG export with graceful fallback.**

**✅ VERIFICATION:** `"✓ All visualizations generated successfully!"`

**Step 4 - Export results:**
```python
from scripts.export_all import export_all
export_all(
    regulons=results['regulons'],
    auc_matrix=results['auc_matrix'],
    auc_summary=results['auc_summary'],
    adjacencies=results['adjacencies'],
    output_dir="scenic_results"
)
```
**DO NOT write custom export code. Use export_all().**

**✅ VERIFICATION:** `"=== Export Complete ==="`
**Note:** If reportlab is installed, a PDF report (`scenic_analysis_report.pdf`) is also generated.

⚠️ **CRITICAL - DO NOT:**
- ❌ **Write inline GRNBoost2/cisTarget code** → **STOP: Use `run_complete_grn_workflow()`**
- ❌ **Write inline plotting code** → **STOP: Use `generate_all_visualizations()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Try to install system dependencies** → Script checks availability

**⚠️ IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** - Install missing package, re-run script
2. **Modify Script (5%)** - Edit the script file itself, document changes
3. **Use as Reference (4%)** - Read script, adapt approach, cite source
4. **Write from Scratch (1%)** - Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| **Memory error during GRNBoost2** | Dataset too large | Subsample to 5,000-10,000 cells or filter to top 2,000-5,000 variable genes |
| **No regulons found** | TF names don't match gene symbols | Check TF list uses same nomenclature (HGNC/MGI); verify gene names in data |
| **cisTarget database error** | Wrong format or corrupted file | Re-download databases; ensure using Feather v2 format (.feather) |
| **Very slow GRN inference** | Too many genes or single-threaded | Filter to variable genes; increase `n_workers` parameter (4-8 recommended) |
| **AUCell scores all low** | Poor regulon quality or normalization | Check regulon sizes (need 10+ genes); verify input is normalized counts |
| **Database loading fails** | Path incorrect or file not found | Use absolute paths to databases; verify files exist |
| **SVG export error** | Missing optional dependency | **Normal - script falls back to PNG automatically. Both formats will be created.** |
| **NumPy AttributeError: np.object** | NumPy >=2.0 removed `np.object` | **Patch pyscenic source**: `pip install pyscenic` then edit `transform.py` → replace `np.object` with `object` (3 occurrences). Quick fix: `python -c \"import pyscenic.transform as t; src=inspect.getfile(t)\"` then patch. |
| **TypeError: object of type 'generator' has no len()** | Incompatible Dask + dask-expr | **Install dask 2024.8.0**: `pip install 'dask[complete]==2024.8.0'` then `pip uninstall -y dask-expr` |
| **RegDiffusion: 'RegDiffusionME' object has no attribute 'adj_matrix'** | `memory_efficient=True` uses different class | **Use `get_adj()` instead**: `adj_matrix = trainer.model.get_adj()` returns numpy float16 array |
| RegDiffusion: cisTarget corrupts gene names | RegDiffusion adjacencies use HVG gene names, cisTarget motif DB uses different IDs | Direct TF activity scoring: Skip cisTarget, use top N target genes per TF from adjacencies to compute activity (mean expression of target genes per cell) |
| **AssertionError: Signatures dataframe is empty!** | Expression data gene names (ENSEMBL IDs with version suffixes like `AL669831.1`) don't match cisTarget database HGNC symbols | Pre-filter expression matrix: Load the .feather ranking database, extract its column names (`set(db.column_names)`), filter the expression matrix to only keep genes in that set. The hg38 10kb db has 27,091 HGNC symbols. Run GRNBoost2 on the filtered matrix. |
| **RuntimeError on Windows: multiprocessing spawn** | Python multiprocessing on Windows uses `spawn` (not `fork`), re-executing all module-level code | Wrap all execution code in `if __name__ == '__main__':` guard. Mandatory for `run_complete_grn_workflow()` on Windows. |

## Suggested Next Steps

After completing pySCENIC analysis:

1. **Identify key regulators**: Focus on high-variance regulons with cell-type-specific activity
2. **Validate regulons**: Compare with literature, ChIP-seq data, or perturbation experiments
3. **Downstream analysis**:
   - Differential regulon activity between conditions (Scanpy/Seurat)
   - Trajectory analysis with regulon dynamics (RNA velocity + SCENIC)
   - Integration with other modalities (ATAC-seq, ChIP-seq)
4. **Functional enrichment**: Analyze target genes of top regulons
5. **Network analysis**: Identify TF-TF interactions and regulatory hierarchies

## Related Skills

- **scrnaseq-scanpy-core-analysis** - Upstream: Single-cell preprocessing and clustering
- **scrnaseq-seurat-core-analysis** - Upstream: Alternative single-cell preprocessing (R)
- **functional-enrichment-from-degs** - Related: Pathway analysis of regulon targets
- **de-results-to-plots** - Related: Visualizing differential activity results

## References

- Aibar et al. (2017). SCENIC: single-cell regulatory network inference and clustering. *Nature Methods*. [doi:10.1038/nmeth.4463](https://doi.org/10.1038/nmeth.4463)
- Van de Sande et al. (2020). A scalable SCENIC workflow for single-cell gene regulatory network analysis. *Nature Protocols*. [doi:10.1038/s41596-020-0336-2](https://doi.org/10.1038/s41596-020-0336-2)
- Huynh-Thu et al. (2010). Inferring regulatory networks from expression data using tree-based methods. *PLoS ONE*. [doi:10.1371/journal.pone.0012776](https://doi.org/10.1371/journal.pone.0012776)
- pySCENIC Documentation: https://pyscenic.readthedocs.io/
- SCENIC Resources: https://resources.aertslab.org/cistarget/

## 📊 pySCENIC GRN 质量评估（必输出）

### 必输出指标
| 指标 | 通过 | 警告 | 阻断 |
|------|------|------|------|
| **AUC 阈值分布** | 双峰（成功分离） | 峰不明显 | 单峰（过拟合） |
| **调控子基因数中位数** | 10-50 | 5-10 或 50-200 | < 5 或 > 200 |
| **靶基因数据库重叠率**（TRRUST/ENCODE） | > 20% | 10-20% | < 10% |
| **调控子-细胞类型特异性** | 有 cell-type specific regulons | 部分共享 | 全部共享/无特异性 |

### 不通过处理
- AUC 单峰 → 增加迭代 / 调整 motif 数据库 / 检查基因过滤
- 调控子过大 → 提高 AUC 阈值（默认 0.057 → 0.06）
- 无特异性 → 可能是细胞类型分得不清楚 → 返回聚类步骤


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
