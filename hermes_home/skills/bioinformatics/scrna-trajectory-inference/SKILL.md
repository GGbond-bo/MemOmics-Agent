---
id: "skill_9971a7d3e3134ee9acc25ba3d0e1fdae"
name: "scrna-trajectory-inference"
display-name: "Single-Cell Trajectory Inference"
category: transcriptomics
description: "Infer differentiation trajectories, pseudotime ordering, RNA velocity, and cell fate probabilities from scRNA-seq data using PAGA, DPT, scVelo, CellRank, and scTour."
when_to_use: "[scrna-trajectory-inference] 单细胞轨迹推断与拟时序分析：RNA velocity→Monocle3/Slingshot→分化轨迹→命运决定"
short-description: "Infer differentiation trajectories, pseudotime ordering, RNA velocity, and cell fate probabilities from scRNA-seq data."
detailed-description: "Reconstruct developmental or differentiation trajectories from single-cell RNA-seq data using PAGA, diffusion pseudotime, scVelo RNA velocity, and CellRank fate mapping. Discovers cell ordering along pseudotime, identifies branching points and terminal fates, and reveals gene expression dynamics along trajectories. Chains from scrnaseq-scanpy-core-analysis or any preprocessed AnnData (.h5ad). Produces publication-ready trajectory visualizations and structured PDF reports."
starting-prompt: Infer differentiation trajectories from my single-cell RNA-seq data using PAGA, pseudotime, and RNA velocity
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



# Single-Cell Trajectory Inference

## When to Use This Skill

**Use when you have preprocessed scRNA-seq data and want to:**
- ✅ Order cells along a differentiation or disease trajectory (pseudotime)
- ✅ Identify branching points and terminal cell fates
- ✅ Discover genes driving cell state transitions
- ✅ Visualize RNA velocity (direction of cell state change)
- ✅ Compute cell fate probabilities with CellRank
- ✅ Chain from `scrnaseq-scanpy-core-analysis` output

**Do NOT use when:**
- ❌ Data is not yet preprocessed (use `scrnaseq-scanpy-core-analysis` first)
- ❌ You have bulk RNA-seq (use `disease-progression-longitudinal` instead)
- ❌ Cells are terminally differentiated with no trajectory (e.g., resting PBMCs)
- ❌ Fewer than 200 cells

## Installation

```bash
pip install scanpy anndata scvelo cellrank numpy pandas matplotlib seaborn scipy statsmodels reportlab
```

| Package | Version | License | Commercial Use | Notes |
|---------|---------|---------|----------------|-------|
| scanpy | ≥1.9 | BSD-3 | ✅ Permitted | Core trajectory (PAGA, DPT) |
| anndata | ≥0.8 | BSD-3 | ✅ Permitted | Data container |
| scvelo | ≥0.2.5 | BSD-3 | ✅ Permitted | RNA velocity (optional but recommended) |
| cellrank | ≥2.0 | BSD-3 | ✅ Permitted | Fate mapping (optional) |
| matplotlib | ≥3.4 | PSF | ✅ Permitted | Plotting |
| seaborn | ≥0.11 | BSD-3 | ✅ Permitted | Statistical plotting, heatmaps |
| scipy | ≥1.7 | BSD-3 | ✅ Permitted | Statistics |
| statsmodels | ≥0.13 | BSD-3 | ✅ Permitted | FDR correction |
| reportlab | ≥3.6 | BSD | ✅ Permitted | PDF report (optional) |

**Graceful degradation:** Core analysis (PAGA + pseudotime) requires only scanpy. scVelo and CellRank are optional — scripts detect availability and skip gracefully.

## Inputs

**Required:**
- Preprocessed AnnData (`.h5ad`) with PCA, UMAP, and cluster annotations
  - Output from `scrnaseq-scanpy-core-analysis` (`adata_processed.h5ad`) works directly
  - Must have ≥200 cells, ≥100 genes, cluster labels in `.obs`

**For RNA velocity (optional):**
- Spliced/unspliced count layers (`adata.layers['spliced']`, `adata.layers['unspliced']`)
- Generated by STARsolo, Cell Ranger, or velocyto

## Outputs

**Analysis objects (for downstream skills):**
- `adata_trajectory.h5ad` — AnnData with pseudotime, PAGA, diffusion map embedded
  - Load with: `adata = sc.read_h5ad('adata_trajectory.h5ad')`
  - Required for: downstream enrichment, regulatory network analysis
- `trajectory_results.pkl` — Full results dict (pseudotime, gene lists, model objects)
  - Load with: `results = pickle.loads(Path('trajectory_results.pkl').read_bytes())`

**Primary results (CSV):**
- `pseudotime_assignments.csv` — Cell barcode, pseudotime, cell type
- `trajectory_genes.csv` — Genes correlated with pseudotime (gene, correlation, FDR, direction)
- `velocity_genes.csv` — Top RNA velocity genes (if scVelo ran)
- `fate_probabilities.csv` — Cell fate probabilities (if CellRank ran)
- `driver_genes_*.csv` — Driver genes per terminal fate (if CellRank ran)

**Visualizations (PNG + SVG at 300 DPI):**
- `paga_graph.png/.svg` — PAGA cluster connectivity + UMAP
- `pseudotime_umap.png/.svg` — UMAP colored by pseudotime
- `pseudotime_violin.png/.svg` — Pseudotime distribution per cell type
- `diffusion_components.png/.svg` — Diffusion map components
- `gene_heatmap.png/.svg` — Top trajectory genes heatmap
- `gene_trends.png/.svg` — Gene expression trends along pseudotime
- `paga_connectivity.png/.svg` — PAGA connectivity heatmap
- `velocity_stream.png/.svg` — RNA velocity stream plot (if scVelo)
- `velocity_confidence.png/.svg` — Velocity confidence (if scVelo)
- `latent_time.png/.svg` — scVelo latent time (if dynamical model)
- `velocity_top_genes.png/.svg` — Phase portraits for top velocity genes (if scVelo)
- `fate_probabilities.png/.svg` — Cell fate UMAP (if CellRank)
- `fate_heatmap.png/.svg` — Fate probability heatmap (if CellRank)
- `driver_genes.png/.svg` — Top driver genes per terminal fate (if CellRank)

**Reports:**
- `trajectory_analysis_report.pdf` — Publication-quality PDF (requires reportlab)
- `trajectory_analysis_report.md` — Markdown fallback report
- `analysis_metadata.json` — Parameters and quality metrics

## Clarification Questions

🚨 **ALWAYS ask Question 1 FIRST. Do not ask about analysis parameters before the user has answered Question 1.**

### 1. Input Files (ASK THIS FIRST)
   - **Do you have a preprocessed scRNA-seq object (.h5ad)?**
     - If uploaded: Is this your processed AnnData file?
     - Expected: `.h5ad` with PCA, UMAP, and cluster annotations
   - **Or use example/demo data?**
     - Pancreatic endocrinogenesis (3,696 cells, branching trajectory into alpha/beta/delta/epsilon cells)

> 🚨 **IF EXAMPLE DATA SELECTED:** All parameters are pre-defined. **Only ask Question 2.** Then proceed to Step 1.

### 2. Analysis Scope (structured — works for both demo and user data)
   - a) **Core trajectory only** — PAGA + pseudotime (~3 min)
   - b) **Core + RNA velocity** — adds scVelo streams (~5 min) *(recommended)*
   - c) **Full analysis** — adds CellRank fate mapping (~8 min)

**Questions 3-5 are ONLY for users providing their own data:**

### 3. Root Cell Type
   - Which cell type represents the starting point of the trajectory?
   - *(For demo data: Ductal cells are the progenitors — pre-selected)*

### 4. Cluster Key
   - Which column in `.obs` contains your cell type annotations?
   - Common: `clusters`, `cell_type`, `leiden`, `louvain`

### 5. Expected Trajectory Structure
   - a) Linear differentiation (one lineage)
   - b) Branching (multiple fates from one progenitor)
   - c) Not sure — let the data decide

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN — DO NOT WRITE INLINE CODE** 🚨

**Step 1 — Load data:**
```python
from scripts.load_example_data import load_example_data
adata = load_example_data()
```
**DO NOT write inline data loading code. Just use the script.**

**✅ VERIFICATION:** You MUST see: `"✓ Data loaded successfully!"`

**Step 2 — Run trajectory analysis:**
```python
from scripts.run_trajectory_analysis import run_trajectory
results = run_trajectory(adata, root_cell_type="Ductal", cluster_key="clusters")
```
**DO NOT write inline trajectory code. Just use the script.**

**✅ VERIFICATION:** You MUST see: `"✓ Trajectory analysis completed successfully!"`

**Step 3 — Generate visualizations:**
```python
from scripts.generate_all_plots import generate_all_plots
generate_all_plots(adata, results, output_dir="trajectory_results", cluster_key="clusters")
```
🚨 **DO NOT write inline plotting code. Just use the script.** 🚨

**✅ VERIFICATION:** You MUST see: `"✓ All plots generated successfully!"`

**Step 4 — Export results:**
```python
from scripts.export_results import export_all
export_all(adata, results, output_dir="trajectory_results")
```
**DO NOT write custom export code. Use export_all().**

**✅ VERIFICATION:** You MUST see: `"=== Export Complete ==="`

---

⚠️ **CRITICAL — DO NOT:**
- ❌ **Write inline data loading code** → **STOP: Use `load_example_data()` or `load_user_data()`**
- ❌ **Write inline PAGA/DPT/scVelo code** → **STOP: Use `run_trajectory()`**
- ❌ **Write inline plotting code (plt.savefig, sc.pl, etc.)** → **STOP: Use `generate_all_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**

**⚠️ IF SCRIPTS FAIL — Script Failure Hierarchy:**
1. **Fix and Retry (90%)** — Install missing package, re-run script
2. **Modify Script (5%)** — Edit the script file itself, document changes
3. **Use as Reference (4%)** — Read script, adapt approach, cite source
4. **Write from Scratch (1%)** — Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| **"Root cell type not found"** | Cluster name mismatch | Check `adata.obs['clusters'].unique()` for exact names |
| **"scvelo not installed"** | Missing optional dependency | `pip install scvelo` — or skip velocity (core trajectory still works) |
| **"cellrank not installed"** | Missing optional dependency | `pip install cellrank` — or skip fate mapping |
| **scVelo dynamical model fails** | Insufficient spliced/unspliced counts | Script auto-falls back to stochastic model |
| **SVG export failed** | Missing system library | Normal — PNG still generated. Script handles fallback. |
| **"Too few cells"** | Dataset too small | Need ≥200 cells for meaningful trajectory |
| **CellRank terminal states incorrect** | Auto-detection picked wrong states | Check PAGA graph to verify expected terminal fates |

## Suggested Next Steps

1. **Functional enrichment** → Use `functional-enrichment-from-degs` skill
   - Input: `trajectory_genes.csv` (top up/down genes along pseudotime)
   - Find pathways driving differentiation

2. **Gene regulatory networks** → Use `grn-pyscenic` skill
   - Input: `adata_trajectory.h5ad`
   - Identify transcription factors controlling cell fate decisions

3. **Upstream regulator analysis** → Use `upstream-regulator-analysis` skill
   - Input: `trajectory_genes.csv`
   - Predict upstream regulators of trajectory dynamics

4. **Differential expression at branch points** → Use `scrnaseq-scanpy-core-analysis` (marker finding)
   - Compare cells at branch points to identify fate-determining genes

## Related Skills

**Upstream (data generation):**
- `scrnaseq-scanpy-core-analysis` — Preprocessing, clustering, UMAP → feeds `.h5ad` into this skill
- `scrnaseq-seurat-core-analysis` — R alternative (convert with SeuratDisk)

**Downstream (interpretation):**
- `functional-enrichment-from-degs` — Pathway analysis of trajectory genes
- `grn-pyscenic` — Gene regulatory networks
- `upstream-regulator-analysis` — Upstream regulators of trajectory genes

**Alternative trajectory methods:**
- `disease-progression-longitudinal` — Bulk/multi-omics longitudinal trajectories (TimeAx)
- `sctour-trajectory-inference` — scTour VAE-based deep learning pseudotime (no start cell needed, GPU-accelerated, batch-insensitive)

### 🔀 Dual-Route Trajectory Strategy

> **Problem**: When data contains **two independent biological processes** with different directions (e.g., denervation + stress→maturation), a single pseudotime axis conflates them. The VAE/scTour pulls both "high maturity endpoints" to the same pseudotime end, making intermediate cells ambiguous.

**When to use**:
- User has annotated subclusters with **two different biological process directions**
- scTour or other methods show counterintuitive "high maturity" clusters that don't fit the expected direction
- The user's core question is "who transitions to whom" but the trajectory method gives ambiguous results

**Signals to detect confusion**:
- A cluster expected to be intermediate shows highest "maturity" score
- Two clusters from different trajectories get pulled to the same pseudotime endpoint
- Gene markers from two different processes show conflicting gradient directions

**Dual-route workflow**:
```python
route_a = adata[adata.obs['subcluster'].isin(['RouteA_clusters'])].copy()
route_b = adata[adata.obs['subcluster'].isin(['RouteB_clusters'])].copy()
# Run trajectory inference independently on each route
```

**Validation strategies**:
| Method | What it checks | Expected |
|:-------|:---------------|:---------|
| **Gene anchor** | Known marker at trajectory end | Gene+ cells at end = correct direction |
| **Age gradient** | Age correlates with pseudotime | Spearman rho > 0.5 supports pathological direction |
| **Condition distribution** | Condition enrichment along trajectory | Most pathological condition at trajectory end |
| **KS test** | Adjacent subcluster separation | All adjacent pairs p < 0.05 |

**Reference**: See `sctour-trajectory-inference` skill's `references/smf-subcluster-transition-analysis.md` for a complete case study.

## References

### Primary Citations

1. **PAGA:** Wolf FA, Hamey FK, Plass M, et al. PAGA: graph abstraction reconciles clustering with trajectory inference through a topology preserving map of single cells. *Genome Biol*. 2019;20:59.

2. **Diffusion Pseudotime:** Haghverdi L, Büttner M, Wolf FA, et al. Diffusion pseudotime robustly reconstructs lineage branching. *Nat Methods*. 2016;13:845-848.

3. **scVelo:** Bergen V, Lange M, Peidli S, et al. Generalizing RNA velocity to transient cell states through dynamical modeling. *Nat Biotechnol*. 2020;38:1408-1414.

4. **CellRank:** Lange M, Bergen V, Klein M, et al. CellRank for directed single-cell fate mapping. *Nat Methods*. 2022;19:159-170.

5. **Example dataset:** Bastidas-Ponce A, Tritschler S, Dony L, et al. Comprehensive single cell mRNA profiling reveals a detailed roadmap for pancreatic endocrinogenesis. *Development*. 2019;146:dev173849.

### Software

| Software | Version | License | Commercial Use |
|----------|---------|---------|----------------|
| scanpy | ≥1.9 | BSD-3 | ✅ Permitted |
| scVelo | ≥0.2.5 | BSD-3 | ✅ Permitted |
| CellRank | ≥2.0 | BSD-3 | ✅ Permitted |
| seaborn | ≥0.11 | BSD-3 | ✅ Permitted |
| reportlab | ≥3.6 | BSD | ✅ Permitted |


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
