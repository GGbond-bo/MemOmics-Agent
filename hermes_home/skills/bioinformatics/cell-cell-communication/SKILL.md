---
id: "skill_4fd6fa5f7294443f987c36586080b69f"
name: "cell-cell-communication"
when_to_use: "[cell-cell-communication] 需使用cell cell communication功能，适用于相关生信分析场景"
display-name: "Cell-Cell Communication Analysis (CellChat)"
category: scRNA
short-description: "Infer and visualize cell-cell communication networks from scRNA-seq data using CellChat v2 ligand-receptor interaction analysis."
detailed-description: "Analyze intercellular communication from annotated single-cell RNA-seq data using CellChat v2. Infers ligand-receptor interactions between cell populations, builds communication probability networks, computes signaling pathway activity, and identifies dominant sender/receiver/mediator roles. Generates chord diagrams, network plots, bubble plots, and signaling role heatmaps. Accepts Seurat objects directly — chains from scrnaseq-seurat-core-analysis."
starting-prompt: Analyze cell-cell communication from my scRNA-seq data using CellChat to identify ligand-receptor interactions and signaling networks between cell types.
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



# Cell-Cell Communication Analysis (CellChat v2)

## When to Use This Skill

✅ **Use when:**
- You have an annotated scRNA-seq dataset (Seurat object with cell type labels)
- You want to identify ligand-receptor interactions between cell types
- You want to visualize communication networks (chord diagrams, bubble plots)
- You want to find dominant sender/receiver cell populations
- **Chains from** `scrnaseq-seurat-core-analysis` output (`seurat_processed.rds`)

❌ **Don't use when:**
- Data is not annotated (run `scrnaseq-seurat-core-analysis` first)
- You need spatial cell-cell communication (CellChat v2 supports this but requires spatial coordinates)
- You want gene regulatory networks (use `grn-pyscenic` instead)
- You have bulk RNA-seq data

## Installation

| Package | Version | License | Commercial Use | Installation |
|---------|---------|---------|----------------|--------------|
| CellChat | ≥2.0.0 | GPL-3 | ✅ Permitted | `devtools::install_github("jinworks/CellChat")` |
| Seurat | ≥5.0.0 | MIT | ✅ Permitted | `install.packages('Seurat')` |
| SeuratData | ≥0.2.1 | GPL-3 | ✅ Permitted | `devtools::install_github('satijalab/seurat-data')` |
| NMF | ≥0.23.0 | GPL-2+ | ✅ Permitted | `install.packages('NMF')` |
| circlize | ≥0.4.12 | MIT | ✅ Permitted | `install.packages('circlize')` |
| ComplexHeatmap | ≥2.12.0 | MIT | ✅ Permitted | `BiocManager::install('ComplexHeatmap')` |
| ggprism | ≥1.0.3 | GPL-3 | ✅ Permitted | `install.packages('ggprism')` |
| presto | ≥1.0.0 | GPL-3 | ✅ Permitted | `remotes::install_github('immunogenomics/presto')` |
| ggalluvial | ≥0.12.0 | GPL-2 | ✅ Permitted | `install.packages('ggalluvial')` |
| rmarkdown | ≥2.20 | GPL-3 | ✅ Permitted | `install.packages('rmarkdown')` |

⚠️ **CellChat must be installed from GitHub** (not CRAN). Use the **jinworks** repository (active), not sqjin (archived).

## Inputs

**Required:**
- **Seurat object (.rds)** with:
  - Normalized expression data (`@assays$RNA@data`)
  - Cell type annotations in metadata (e.g., `celltype` column)
  - Minimum 3 cell types, ≥10 cells per type recommended

**Accepted sources:**
- `seurat_processed.rds` from `scrnaseq-seurat-core-analysis` (chains directly)
- Any annotated Seurat v5 object
- Example PBMC data (auto-loaded if no file provided)

## Outputs

**CSV tables:**
- `significant_interactions.csv` — All significant L-R pairs with source, target, pathway, probability
- `pathway_summary.csv` — Pathway-level communication summary
- `interaction_count_matrix.csv` — Cell type × cell type interaction counts
- `interaction_strength_matrix.csv` — Cell type × cell type communication weights
- `signaling_roles.csv` — Centrality scores (sender, receiver, mediator, influencer per pathway)
- `top_interactions.csv` — Top 20 interactions ranked by probability

**Visualizations (PNG + SVG):**
- `interaction_count_network` — Circle plot of interaction counts
- `interaction_strength_network` — Circle plot of communication strength
- `chord_aggregated` — Chord diagram of the full communication network
- `bubble_ligand_receptor` — Bubble plot of L-R pairs by cell type pairs
- `signaling_outgoing_heatmap` — Outgoing signaling patterns by cell type
- `signaling_incoming_heatmap` — Incoming signaling patterns by cell type
- `signaling_role_scatter` — Dominant senders vs receivers scatter

**Analysis objects (RDS):**
- `cellchat_object.rds` — Complete CellChat object for downstream use
  - Load with: `cellchat <- readRDS('cellchat_object.rds')`
  - Required for: multi-condition comparison, pathway-specific deep dives

**Reports:**
- `analysis_report.md` — Markdown report (always generated)
- `analysis_report.pdf` — PDF report (requires rmarkdown + LaTeX)

## Clarification Questions

🚨 **ALWAYS ask Question 1 FIRST. Do not proceed before the user answers.**

### 1. Input Files (ASK THIS FIRST):
- **Do you have an annotated Seurat object (.rds) from scRNA-seq analysis?**
  - If yes: provide the path to the `.rds` file
  - Expected: Seurat v5 object with cell type labels in metadata
- **Or use example data?** — PBMC 3k dataset (human immune cells, 2,638 cells, 8 cell types)
  - Uses `source("scripts/load_data.R"); seurat_obj <- load_example_pbmc()`

> 🚨 **IF EXAMPLE DATA SELECTED:** Parameters are pre-defined. Skip to Question 4 (or proceed directly to Step 1). Do NOT ask questions 2-3.

### 2. Species (own data only):
- a) Human (CellChatDB.human) — default
- b) Mouse (CellChatDB.mouse)

### 3. Cell Type Column (own data only):
- Which metadata column contains cell type annotations?
  - Common: `celltype`, `singler_labels`, `cell_type`, `predicted.celltype.l2`
  - Check with: `colnames(seurat_obj@meta.data)`

### 4. Analysis Scope (structured — works for demo and own data):
- a) **All signaling types** (Secreted + ECM-Receptor + Cell-Cell Contact) — ✅ recommended
- b) Secreted signaling only
- c) Cell-Cell Contact only

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN — DO NOT WRITE INLINE CODE** 🚨

**Step 1 — Load data:**
```r
source("scripts/load_data.R")
seurat_obj <- load_cellchat_data()  # example PBMC data
# OR: seurat_obj <- load_cellchat_data("path/to/seurat_processed.rds")
```

**Step 2 — Run CellChat analysis:**
```r
source("scripts/run_cellchat.R")
cellchat <- run_cellchat_analysis(seurat_obj, species = "human", group.by = "celltype")
```
**DO NOT write inline CellChat code. Just source the script and call the function.**

**Step 3 — Generate visualizations:**
```r
source("scripts/cellchat_plots.R")
generate_all_plots(cellchat, output_dir = "results")
```
🚨 **DO NOT write inline plotting code. Just use the script.** 🚨

**Step 4 — Export results:**
```r
source("scripts/export_results.R")
export_all(cellchat, seurat_obj = seurat_obj, output_dir = "results")
```
**DO NOT write custom export code. Use export_all().**

**✅ VERIFICATION — You should see:**
- After Step 1: `"✓ Data loaded successfully! [N] cells, [M] cell types"`
- After Step 2: `"✓ CellChat analysis completed! [N] significant interactions across [M] pathways"`
- After Step 3: `"✓ All plots generated successfully! [6] visualizations saved"`
- After Step 4: `"=== Export Complete ==="`

**❌ IF YOU DON'T SEE THESE:** You wrote inline code. Stop and use source().

⚠️ **CRITICAL — DO NOT:**
- ❌ **Write inline CellChat code** → **STOP: Use `source("scripts/run_cellchat.R")`**
- ❌ **Write inline plotting code** → **STOP: Use `generate_all_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Try to install system-level dependencies** → CellChat handles its own deps

**⚠️ IF SCRIPTS FAIL — Script Failure Hierarchy:**
1. **Fix and Retry (90%)** — Install missing package, re-run script
2. **Modify Script (5%)** — Edit the script file itself, document changes
3. **Use as Reference (4%)** — Read script, adapt approach, cite source
4. **Write from Scratch (1%)** — Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **CellChat not found** | Not installed from GitHub | `devtools::install_github("jinworks/CellChat")` — must use **jinworks** repo (not sqjin) |
| **"presto" required for Wilcoxon test** | Missing presto package | `remotes::install_github('immunogenomics/presto')` — script falls back to standard test if unavailable |
| **No significant interactions** | Too few cells per type or stringent filtering | Lower `min.cells` parameter or merge rare cell types |
| **Memory error on large datasets** | >50k cells uses substantial RAM | Subsample or increase memory; see [references/cellchat-guide.md](references/cellchat-guide.md) |
| **Chord diagram error** | Missing circlize package | `install.packages('circlize')` |
| **SVG export error "svglite required"** | Missing optional dependency | Use `generate_all_plots()` — it handles fallback automatically. DO NOT try to install svglite manually. |
| **svglite dependency conflict** | System library version mismatch | Normal — `generate_all_plots()` falls back to base R svg() device automatically. Both PNG and SVG will be created. |
| **"group.by not found"** | Wrong column name for cell types | Check: `colnames(seurat_obj@meta.data)` |
| **Seurat v5 slot error ("no slot of name images")** | Old Seurat object from v3/v4 | Script handles this — `UpdateSeuratObject()` is called automatically |
| **NMF not available** | NMF package not installed | `install.packages('NMF')` |
| **PDF report skipped** | No LaTeX installation | `install.packages('tinytex'); tinytex::install_tinytex()` — markdown report still available |

## Suggested Next Steps

After cell-cell communication analysis, consider:

1. **Multi-condition comparison** — Compare communication between disease vs healthy, treated vs untreated
   - See [references/cellchat-guide.md](references/cellchat-guide.md) for `mergeCellChat()` workflow
2. **Pathway deep dive** — Examine specific pathways (e.g., TNF, MHC-II) with hierarchy plots
3. **Gene regulatory networks** — Use `grn-pyscenic` to find transcription factors driving the communication
4. **Functional enrichment** — Run pathway analysis on sender/receiver gene sets

## Related Skills

| Skill | Relationship |
|-------|-------------|
| `scrnaseq-seurat-core-analysis` | **Upstream** — produces the annotated Seurat object input |
| `scrnaseq-scanpy-core-analysis` | Alternative upstream (Python-based, convert to Seurat for CellChat) |
| `grn-pyscenic` | Complementary — gene regulatory networks from same scRNA-seq data |

## References

- Jin S, et al. **Inference and analysis of cell-cell communication using CellChat.** *Nature Communications*. 2021;12:1088.
- Jin S, et al. **CellChat for systematic analysis of cell-cell communication from single-cell and spatially resolved transcriptomics.** *Nature Protocols*. 2024.
- [CellChat v2 GitHub (active)](https://github.com/jinworks/CellChat)
- [CellChat tutorials](https://github.com/jinworks/CellChat/tree/main/tutorial)
- Detailed patterns: [references/cellchat-guide.md](references/cellchat-guide.md)
- Visualization options: [references/visualization-guide.md](references/visualization-guide.md)


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
     topic="细胞通讯分析 —— {样本}",
     context="方法: CellChat/LIANA/NicheNet | DB: {数据库} | 结果: {n}条配受体对",
     knowledge_base_info=<KB内容>,
   )
   辩论: 关键L-R对跟已知生物学一致吗？sender-receiver模式合理吗？
3. save_conclusions(module="03_advanced", topic="Cell Communication", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```
