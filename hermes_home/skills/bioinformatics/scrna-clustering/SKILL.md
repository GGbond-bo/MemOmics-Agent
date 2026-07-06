---
name: scrna-clustering
description: "完整Seurat v5聚类注释工作流。使用场景：QC后的scRNA-seq，需SCTransform→PCA→UMAP→聚类→注释→Markers，含SoupX/DoubletFinder/Harmony"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [clustering, SCTransform, UMAP, leiden, annotation, 02_基础分析]
    difficulty: basic
    language: R+Python
    category: transcriptomics
prerequisites:
  r_packages: ["SingleR", "celldex", "Seurat"]
  python_packages: ["scanpy", "celltypist"]
---


## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。使用本 skill 前，必须先通过 skill_view 加载本文件。以下规则覆盖所有默认行为。

### 规则1: 写代码前 → 必须先 search_knowledge + skill_view
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 8步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. skill_view 加载本 SKILL.md（获取脚本模板+审查规则+参数范围）
3. check_env 检查环境（缺包自动安装）
4. rail_review(pre) 前置审查（参数合理吗？包齐了吗？数据准备好了吗？）
5. 写这一步的代码（基于 skill 模板，只写这一步，不写后续步骤）
6. terminal 执行（分步执行，禁止 && 连接多步骤）
7. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
8. rail_review(post) 后置审查（图有没有？结果合理吗？跟知识库对应吗？）
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 resolution, n_pcs, min_features, FDR threshold 等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式：正方（支持当前参数）vs 反方（质疑+替代方案）→ 裁判决断
- **不确定的参数就辩论**，不要自己拍脑袋
- **辩论最多 3 轮**：3 轮后选最优参数结果

### 规则5: 执行后审查

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

# scRNA-seq聚类分析

从原始数据到细胞注释的完整Seurat v5工作流。含SoupX/DoubletFinder/SCTransform/Harmony/CCA/Pseudobulk DE

适用场景: 所有scRNA-seq

分析步骤:
  - Normalize (SCTransform): SCTransform recommended
  - HVG selection: FindVariableFeatures
  - PCA + PC selection: ElbowPlot/JackStraw
  - Batch correction (Harmony): Multi-sample integration
  - Cluster (Leiden): FindNeighbors+FindClusters
  - UMAP visualization: RunUMAP 2D projection
  - Cell annotation: SingleR/CellTypist/markers

## 依赖包: Seurat, scanpy, celltypist, celldex, SingleR

难度: basic

触发提示: "对我的单细胞数据进行聚类分析"

别名: scRNA-seq 完整分析 (Seurat v5), scRNA-seq 完整分析 (Scanpy)

## When to Use

适用于: 所有scRNA-seq

## Pipeline

0. **Pre-analysis: Data scan & metadata inspection**（参见 references/large-h5ad-metadata-inspection.md）\n   - 对 >5GB 的 h5ad 文件，先用 h5py 低内存方式读取 obs 元数据\n   - 识别：age分组（数值→Young/Old归类）、sample_id/donor_id分布、QC统计\n   - 确认双层抽样策略：celltype比例 + 样本平衡\n   - 知识库校对：匹配组织+物种+方向的参考阈值\n   - Tool: `execute_python` (用 h5py 而非 anndata)\n\n0a. **h5ad → Seurat loading**（参见 references/rhdf5-load-h5ad-to-seurat.md）\n   - Seurat v5.5.0 lacks `ReadH5AD` — use `rhdf5` (Bioconductor) for reliable loading\n   - For files > 3GB: subset in Python first, then load subset in R\n   - CSR matrix: build as `new("dgCMatrix")`, NOT `sparseMatrix()`\n   - Categorical obs: h5ad uses `categories` + `codes` groups (single underscore, not `__categories`)\n   - Pass metadata as `meta.data=` in `CreateSeuratObject()`, not via `$<-` after creation

1. **Normalize (SCTransform)**
   - SCTransform recommended
   - Tool: `terminal`
2. **HVG selection**
   - FindVariableFeatures
   - Tool: `terminal`
3. **PCA + PC selection**
   - ElbowPlot/JackStraw
   - Tool: `terminal`
4. **Batch correction (Harmony)**
   - Multi-sample integration
   - Tool: `terminal`
5. **Cluster (Leiden)**
   - FindNeighbors+FindClusters
   - Tool: `terminal`
6. **UMAP visualization**
   - RunUMAP 2D projection
   - Tool: `terminal`
7. **Cell annotation**
   - SingleR/CellTypist/markers
   - Tool: `terminal`

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `r_packages` | SingleR, celldex, Seurat | |
| `python_packages` | scanpy, celltypist | |
| `steps` | Normalize (SCTransform) -> HVG selection -> PCA + PC selection -> Batch correction (Harmony) -> Cluster (Leiden) -> UMAP visualization -> Cell annotation | |

> **Parameter Adaptation**: Adjust parameters based on tissue quality, species, and condition. Literature values take priority, then official defaults, then tissue-specific adjustments.

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| R fails to read h5ad | Seurat v5 lacks ReadH5AD; hdf5r crashes in Rscript | Use `rhdf5` (Bioconductor) — see `references/rhdf5-load-h5ad-to-seurat.md` |
| SCTransform OOM on 30k cells | scale.data is full dense matrix — huge save | Remove scale.data before saveRDS: `obj[["SCT"]]@scale.data <- new("matrix")` |
| MT% = 0 after QC | Seurat's `_`→`-` renaming mismatches `^MT-` pattern | Verify with `grep("^MT-", rownames(obj))`; pattern is correct after rename |
| Stratified sampling needed | Raw data has class imbalance for rare cell types | Use Python: proportional allocation by celltype + 50/50 Young/Old within each type |
| `No cell overlap between new meta data` | Adding metadata after CreateSeuratObject fails when cell barcodes mismatch | Pass metadata as `meta.data` argument in `CreateSeuratObject()` call |

## References

- Source: MemOmics built-in
- Category: transcriptomics
- Language: R+Python


## Reference Script (from External Skill)

> Auto-imported from external skill `29_scrnaseq-seurat-core-analysis`.
> This script is a verified reference implementation, NOT a run.py template.
> The agent can use it as a starting point or fetch official docs for the latest version.

- **Source**: `skills/external/29_scrnaseq-seurat-core-analysis/scripts/`
- **Imported scripts**: cluster_cells.R
