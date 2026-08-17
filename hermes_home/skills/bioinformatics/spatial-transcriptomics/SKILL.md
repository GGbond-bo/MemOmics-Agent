---
id: "skill_30b65ae0dee54a929017fbc760aefe01"
name: "spatial-transcriptomics"
when_to_use: "[spatial-transcriptomics] 需使用spatial transcriptomics功能，适用于相关生信分析场景"
display-name: "Spatial Transcriptomics Visium Analysis"
category: Spatial
short-description: "Analyze 10x Visium spatial transcriptomics data from QC through spatial domain analysis with clustering, spatially variable genes, and neighborhood enrichment."
detailed-description: "Complete spatial transcriptomics analysis for 10x Visium data using Squidpy and Scanpy. Performs quality control, normalization, Leiden clustering, spatial neighbor graph construction, spatially variable gene identification via Moran's I, neighborhood enrichment analysis, and co-occurrence scoring. Produces publication-ready spatial tissue overlays, UMAP plots, enrichment heatmaps, and SVG bar charts. Supports Space Ranger output, H5AD files, or built-in 10x Genomics example datasets including V1_Human_Heart for cardiometabolic research."
starting-prompt: Analyze spatial transcriptomics data from a 10x Visium experiment to identify spatially variable genes and tissue domains.
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



# Spatial Transcriptomics Visium Analysis

## When to Use This Skill

- You have **10x Visium** spatial gene expression data (with or without H&E image)
- You want to identify **spatially variable genes** across a tissue section
- You want to discover **spatial tissue domains** via clustering
- You want to quantify **neighborhood enrichment** between cell clusters
- You want to analyze **co-occurrence** patterns of cell types across distances
- Input is Space Ranger output, `.h5ad`, or `.h5` file

**Not for:** Single-molecule FISH (MERFISH/Xenium), Slide-seq, or single-cell RNA-seq without spatial coordinates. For scRNA-seq, use `scrnaseq-scanpy-core-analysis`.

## Installation

```bash
pip install squidpy scanpy anndata scikit-misc plotnine plotnine-prism seaborn matplotlib numpy pandas scikit-learn
```

| Package | Version | License | Commercial Use | Installation |
|---------|---------|---------|----------------|--------------|
| squidpy | ≥1.4 | BSD-3-Clause | ✅ Permitted | `pip install squidpy` |
| scanpy | ≥1.9 | BSD-3-Clause | ✅ Permitted | `pip install scanpy` |
| anndata | ≥0.8 | BSD-3-Clause | ✅ Permitted | `pip install anndata` |
| plotnine | ≥0.12 | MIT | ✅ Permitted | `pip install plotnine` |
| plotnine-prism | ≥0.2 | MIT | ✅ Permitted | `pip install plotnine-prism` |
| seaborn | ≥0.11 | BSD-3-Clause | ✅ Permitted | `pip install seaborn` |
| matplotlib | ≥3.5 | PSF | ✅ Permitted | `pip install matplotlib` |
| scikit-learn | ≥1.0 | BSD-3-Clause | ✅ Permitted | `pip install scikit-learn` |
| scikit-misc | ≥0.1 | BSD-3-Clause | ✅ Permitted | `pip install scikit-misc` |
| numpy | ≥1.21 | BSD-3-Clause | ✅ Permitted | `pip install numpy` |
| pandas | ≥1.3 | BSD-3-Clause | ✅ Permitted | `pip install pandas` |

**License Compliance:** All packages use permissive licenses (BSD, MIT, PSF) that permit commercial use in AI agent applications.

## Inputs

| Input | Format | Description |
|-------|--------|-------------|
| Visium data | `.h5ad`, `.h5`, or Space Ranger directory | Gene expression + spatial coordinates |
| H&E image | Embedded in above | Tissue histology (optional, enhances spatial plots) |

**Built-in example:** V1_Human_Heart from 10x Genomics (~4,247 spots, ~33,538 genes, includes H&E image).

## Outputs

**Analysis objects:**
- `adata_processed.h5ad` — Complete processed AnnData for downstream use
  - Load with: `adata = sc.read_h5ad('adata_processed.h5ad')`
  - Contains: clusters, embeddings, SVG results, spatial graph

**Tables (CSV):**
- `spatially_variable_genes.csv` — SVGs ranked by Moran's I with FDR
- `cluster_assignments.csv` — Spot barcodes + Leiden cluster + spatial coordinates
- `neighborhood_enrichment.csv` — Cluster-cluster enrichment z-scores
- `spot_metadata.csv` — All spot-level QC and annotation metadata
- `analysis_summary.txt` — Human-readable report

**Plots (PNG + SVG):**
- `qc_violins` — QC metric distributions
- `spatial_clusters` — Leiden clusters overlaid on tissue
- `spatial_markers` — Selected marker gene expression on tissue
- `umap_clusters` — UMAP embedding colored by cluster
- `neighborhood_enrichment` — Cluster enrichment heatmap
- `co_occurrence` — Co-occurrence probability vs distance
- `top_svgs` — Bar chart of top spatially variable genes
- `spatial_svg_[GENE]` — Spatial expression of top SVG

## Clarification Questions

**ALWAYS ask Question 1 FIRST:**

### 1. Input Files (ASK THIS FIRST):
- Do you have Visium data files to analyze?
  - **Supported formats:** `.h5ad`, `.h5`, or Space Ranger output directory
- **Or use example data?** V1_Human_Heart from 10x Genomics (human cardiac tissue, ~4K spots)

> 🚨 **IF EXAMPLE DATA SELECTED:** All parameters are pre-configured. **Skip remaining questions.** Proceed directly to Step 1.

### 2. Analysis Parameters (ONLY if user provides own data):
- **Clustering resolution?**
  - a) 0.5 (fewer, broader clusters)
  - b) 0.8 (standard — recommended)
  - c) 1.2 (more, finer clusters)
- **Mitochondrial threshold?**
  - a) 50% (recommended for cardiac/muscle tissue — high MT is normal)
  - b) 20% (standard for most tissues)
  - c) 30% (moderate)

### 3. Marker Genes (ONLY if user provides own data):
- Which marker genes to highlight in spatial plots?
  - Provide a list or use tissue-appropriate defaults

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN — DO NOT WRITE INLINE CODE** 🚨

> **Note:** Run from the `spatial-transcriptomics/` directory, or add `scripts/` to `sys.path`:
> ```python
> import sys; sys.path.insert(0, 'scripts')
> ```

**Step 1 — Load data:**
```python
from load_example_data import load_visium_heart
adata = load_visium_heart()
```
**DO NOT write inline data loading code. Just use the script.**

**✅ VERIFICATION:** You MUST see: `"✓ Data loaded successfully!"`

---

**Step 2 — Run analysis:**
```python
from spatial_workflow import run_spatial_analysis
adata = run_spatial_analysis(adata, output_dir="visium_results")
```
**DO NOT write inline analysis code. Just use the script.**

**✅ VERIFICATION:** You MUST see: `"✓ Spatial analysis completed successfully!"`

**❌ IF YOU DON'T SEE THIS:** You wrote inline code. Stop and use the script.

---

**Step 3 — Generate visualizations:**
```python
from generate_all_plots import generate_all_plots
generate_all_plots(adata, output_dir="visium_results")
# For non-cardiac tissue, pass tissue-appropriate markers:
# generate_all_plots(adata, output_dir="visium_results", marker_genes=["GENE1", "GENE2"])
```
🚨 **DO NOT write inline plotting code (plt.savefig, ggplot, clustermap, etc.). Just use the script.** 🚨

**The script handles PNG + SVG export with graceful fallback for SVG.**

**✅ VERIFICATION:** You MUST see: `"✓ All visualizations generated successfully!"`

---

**Step 4 — Export results:**
```python
from export_results import export_all
export_all(adata, output_dir="visium_results")
```
**DO NOT write custom export code. Use export_all().**

**✅ VERIFICATION:** You MUST see:
```
==================================================
=== Export Complete ===
==================================================
```

---

⚠️ **CRITICAL — DO NOT:**
- ❌ **Write inline analysis code** → **STOP: Use `run_spatial_analysis()`**
- ❌ **Write inline plotting code** → **STOP: Use `generate_all_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Try to install system libraries** → scripts handle optional deps gracefully

**⚠️ IF SCRIPTS FAIL — Script Failure Hierarchy:**
1. **Fix and Retry (90%)** — Install missing package, re-run script
2. **Modify Script (5%)** — Edit the script file itself, document changes
3. **Use as Reference (4%)** — Read script, adapt approach, cite source
4. **Write from Scratch (1%)** — Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

## Common Issues

| Error | Cause | Fix |
|-------|-------|-----|
| **`ModuleNotFoundError: squidpy`** | Missing package | `pip install squidpy` |
| **`ModuleNotFoundError: plotnine_prism`** | Missing theme package | `pip install plotnine-prism` |
| **SVG export failed** | Missing SVG backend | Normal — PNG always generated. SVG is best-effort. |
| **`ValueError: coord_type='grid'`** | Non-grid spatial data | Use `coord_type='generic'` for non-Visium data |
| **0 SVGs found (FDR < 0.05)** | Low signal or few permutations | Increase `svgs_n_perms=1000` or relax FDR threshold |
| **Memory error on large dataset** | Too many spots/genes | Filter more aggressively or use `sc.pp.subsample()` |
| **`KeyError: 'spatial'`** | Missing spatial coordinates | Ensure data was loaded with `sc.read_visium()` or has `.obsm['spatial']` |
| **NaN in co-occurrence** | Known squidpy issue with `n_splits` | Use default `n_splits` parameter (do not override) |

## Interpreting Results

**Spatially Variable Genes (SVGs):**
- **Moran's I close to +1** → Gene expression is spatially clustered (strong spatial pattern)
- **Moran's I close to 0** → No spatial structure (random distribution)
- **Moran's I close to -1** → Dispersed pattern (checkerboard; rare in practice)
- **FDR < 0.05** is the standard significance threshold; use < 0.01 for stringent filtering
- Top SVGs typically include tissue-specific markers and boundary genes

**Neighborhood Enrichment Z-scores:**
- **Z > 2** → Clusters are significantly co-localized (tend to be spatially adjacent)
- **Z < -2** → Clusters are significantly segregated (avoid each other spatially)
- **-2 to 2** → No significant spatial preference
- Diagonal values (self-enrichment) indicate how spatially cohesive each cluster is

**Co-occurrence Curves:**
- Probability above expected → Clusters co-occur more than random at that distance
- Distance-dependent changes reveal spatial organization (e.g., border zone cell types co-occur at short range)

**Cluster-to-Tissue Mapping:**
- Compare spatial cluster plots with H&E histology to validate biological relevance
- Well-defined spatial clusters that match visible tissue structures (e.g., myocardium, fibrotic region) indicate meaningful tissue domains

## Agent Summary Guidelines

When presenting results to the user, the agent should:

- **Report key numbers:** spots analyzed, clusters found, number of significant SVGs
- **Highlight top 5-10 SVGs** with Moran's I values and known biological roles
- **Describe spatial patterns:** which clusters are co-localized vs segregated
- **Connect to biology:** relate spatial patterns to tissue architecture visible in H&E
- **Note limitations:** permutation count affects SVG p-values; low `n_perms` may miss weak signals
- **DO NOT** hallucinate gene functions — only report known annotations or suggest looking up unknown genes
- **DO NOT** over-interpret co-occurrence curves from small datasets or few clusters

**Mitochondrial content note:** Cardiac/muscle tissue has naturally high MT% (~30-40%) due to mitochondria-rich cells. The default `max_pct_mito=50%` is appropriate for heart tissue. For other tissues (brain, liver, immune), use 20% or lower.

## Suggested Next Steps

- **Functional enrichment** on SVG gene sets → `functional-enrichment-from-degs`
- **Cell type deconvolution** with cell2location or RCTD (specialized workflow)
- **Cell-cell communication** with CellChat or COMMOT on spatial data
- **Multi-sample integration** for comparing conditions (e.g., MI vs healthy)
- **Gene regulatory networks** on spatial clusters → `grn-pyscenic`

## Related Skills

| Skill | Relationship |
|-------|-------------|
| `scrnaseq-scanpy-core-analysis` | Companion scRNA-seq analysis (non-spatial) |
| `functional-enrichment-from-degs` | Downstream: enrichment on SVG gene lists |
| `de-results-to-gene-lists` | Downstream: gene list preparation from SVGs |
| `grn-pyscenic` | Downstream: regulatory networks from spatial clusters |
| `coexpression-network` | Downstream: co-expression on spatial domains |

## References

- **Squidpy:** Palla G, et al. "Squidpy: a scalable framework for spatial omics analysis." *Nature Methods* (2022). doi:10.1038/s41592-021-01358-2
- **Scanpy:** Wolf FA, et al. "SCANPY: large-scale single-cell gene expression data analysis." *Genome Biology* (2018). doi:10.1186/s13059-017-1382-0
- **Moran's I:** Moran PAP. "Notes on continuous stochastic phenomena." *Biometrika* (1950). doi:10.2307/2332142
- **10x Visium:** 10x Genomics. "Visium Spatial Gene Expression." https://www.10xgenomics.com/platforms/visium

**Detailed parameter guidance:** See `references/spatial-analysis-guide.md`


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
     topic="空间转录组 —— {样本}",
     context="技术: {Visium/MERFISH/Xenium} | 参数: {spot数} | 结果: {n}个空间域",
     knowledge_base_info=<KB内容>,
   )
   辩论: 空间域跟组织学一致吗？marker基因空间表达模式合理吗？
3. save_conclusions(module="03_advanced", topic="Spatial", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```
