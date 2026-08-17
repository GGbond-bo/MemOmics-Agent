---
name: cellchat-v2
description: "CellChat v2配体-受体细胞通讯分析。使用场景：已聚类注释的Seurat对象，需分析细胞间信号通路、配体受体互作、信号角色（发出者/接收者），多条件比较"
when_to_use: "[cellchat-v2] CellChat v2配体-受体细胞通讯分析。使用场景：已聚类注释的Seurat对象，需分析细胞间信号通路、配体受体互作、信号角色（发出者/接收者），多条件比较"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [cellchat, cell-communication, ligand-receptor, 03_高级分析]
    difficulty: intermediate
    language: R
    category: scRNA
prerequisites:
  r_packages: ["CellChat", "Seurat", "NMF", "reticulate"]
  python_packages: ["cellchat"]
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
- 辩论格式（多角色对抗 v3）：
  - 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
  - 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
  - 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
  - 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
  - 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
  - 辩论结果自动归档到 results/.../log/debate_*.json
- **不确定的参数就辩论**，不要自己拍脑袋
- **辩论最多 3 轮**：3 轮后选最优参数结果

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

# 细胞通讯分析 (CellChat v2)

CellChat v2配体-受体分析。和弦图/气泡图/信号角色热图。从Seurat输出链接

适用场景: 多细胞类型, disease, aging, development

分析步骤:
  - Create CellChat object: Import from Seurat
  - L-R interaction inference: CellChatDB v2 matching
  - Signal flow visualization: netVisual_aggregate
  - Comparison (multi-condition): compareInteractions
  - Source-target summary: Signal contribution

依赖包: reticulate, Seurat, CellChat, NMF, cellchat

难度: intermediate

触发提示: "分析细胞间通讯"

别名: 细胞通讯 (CellChat v2)

## When to Use

适用于: 多细胞类型, disease, aging, development

## Pipeline (with mandatory pre-steps)

0. **Metadata cleaning (h5ad→Seurat)** ⚠️ NEW
   - Clean `b'...'` bytes prefixes from h5ad metadata
   - Tool: `terminal` (R)
1. **Create CellChat object**
   - Import from Seurat
   - Tool: `terminal`
2. **L-R interaction inference**
   - CellChatDB v2 matching
   - Run with AND without `population.size=TRUE`, compare rankings
   - Tool: `terminal`
3. **Marker validation for ECM pathways** ⚠️ NEW
   - If LAMININ/COLLAGEN/FN1 are top pathways, validate PDGFRA/LUM/DCN/PDGFRB
   - See `references/ecm-contamination-validation.md`
   - Tool: `terminal` (R)
4. **Compute centrality** ⚠️ REQUIRED before heatmaps
   - `netAnalysis_computeCentrality(cellchat, slot.name="netP")`
5. **Signal flow visualization**
   - netVisual_aggregate (always pass explicit `signaling=` parameter)
   - Tool: `terminal`
6. **Comparison (multi-condition)**
   - compareInteractions
   - Tool: `terminal`
7. **Source-target summary**
   - Signal contribution
   - Tool: `terminal`

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `r_packages` | CellChat, Seurat, NMF, reticulate | |
| `python_packages` | cellchat | |
| `steps` | Create CellChat object -> L-R interaction inference -> Signal flow visualization -> Comparison (multi-condition) -> Source-target summary | |

> **Parameter Adaptation**: Adjust parameters based on tissue quality, species, and condition. Literature values take priority, then official defaults, then tissue-specific adjustments.

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

| human | skeletal_muscle | aging | 2026-07-14 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-07-17 | run_cellchat.R | - | - |  |
| human | skeletal_muscle | aging | 2026-07-17 | - | - | - |  |
## 🚨 Critical Pitfalls (from real runs)

### P1: h5ad → Seurat metadata corruption (`b'...'` prefix)
**Symptom**: `cellchat@idents` shows `b'zone1'`, `b'NMJ'` etc — every cell gets its own identity.
**Root cause**: Python `bytes` strings from `anndata` imported via reticulate carry `b'...'` literal prefix.
**Fix**: After h5ad→Seurat conversion, strip prefixes:
```r
clean_col <- function(x) {
  if (is.factor(x)) x <- as.character(x)
  if (is.character(x)) x <- gsub("^b['\"](.*?)['\"]$", "\\1", x)
  return(x)
}
for (col in colnames(seurat_obj@meta.data)) {
  seurat_obj@meta.data[[col]] <- clean_col(seurat_obj@meta.data[[col]])
}
```

### P2: `population.size=TRUE` dramatically changes rankings
**Symptom**: Small clusters (e.g. NMJ, 59 cells) appear as #1 sender without normalization; drop to #7 with normalization.
**Root cause**: CellChat v2 does NOT normalize for cluster size by default. `computeCommunProb(population.size=FALSE)` inflates weights for small clusters.
**Fix**: ALWAYS run both `population.size=FALSE` and `population.size=TRUE`, report both rankings, and debate the discrepancy. If cluster sizes differ >3x, prefer normalized results.

### P3: `netAnalysis_signalingRole_heatmap` fails without centrality
**Symptom**: `Error: Please run netAnalysis_computeCentrality to compute the network centrality scores!`
**Fix**: Always call `cellchat <- netAnalysis_computeCentrality(cellchat, slot.name = "netP")` BEFORE any signaling role plots.

### P4: `netVisual_chord_cell` requires explicit `signaling` parameter
**Symptom**: `Error: Please assign values to either signaling or net`
**Fix**: `netVisual_chord_cell(cellchat, signaling = "LAMININ", ...)` — never pass `signaling=NULL`.

### P5: ECM pathways (LAMININ/COLLAGEN) may reflect fibroblast contamination
**Symptom**: COL1A1/COL3A1/FN1 high in muscle fiber clusters → debate will flag as possible FAP contamination.
**Fix**: BEFORE interpreting ECM pathways, validate with fibroblast markers: PDGFRA, PDGFRB, LUM, DCN, LOX. If PDGFRA ≤ 1% and LUM < 10% across clusters, contamination is ruled out and ECM is genuinely from muscle fibers.

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| `b'...'` in idents | Python bytes from h5ad metadata | Clean with `gsub("^b['\"](.*?)['\"]$", "\\1", x)` |
| Small cluster inflated weight | No population.size normalization | Run both FALSE and TRUE, debate ranking changes |
| signaling role heatmap fails | Centrality not computed | `netAnalysis_computeCentrality(cellchat, slot.name="netP")` first |
| chord diagram fails | Missing `signaling` parameter | Always pass explicit signaling pathway name |
| ECM pathways over-interpreted | Possible fibroblast contamination | Validate PDGFRA/LUM/DCN/PDGFRB before interpreting |
| Seurat `data` layer empty | h5ad→Seurat only has `counts` layer | `NormalizeData(obj)` before `createCellChat()` |
| meta/data rownames mismatch | Barcodes don't match | `rownames(meta) <- colnames(obj)` before `createCellChat()` |

### P6: `compareInteractions`/`netVisual_diffInteraction` 产空白图
**Symptom**: `mergeCellChat` 后 `compareInteractions()` 输出 105B 空白图。
**Root cause**: Young/Old 通路集不对称（如 22 vs 43），merge 对象不兼容某些比较函数。
**Fix**: 跳过跨条件比较图，改用柱状图对比通路数量。见 `references/comparison-workaround.md`。

### P7: `rankComparison` 函数不存在
**Symptom**: `Error: could not find function "rankComparison"`
**Root cause**: CellChat 部分 CRAN 版本无此函数。
**Fix**: 手动排通路：`data.frame(pathway, score)` → `merge()` → `order(-abs(diff))`。

## References

- Source: MemOmics built-in
- Category: transcriptomics
- Language: R

## 📊 CellChat 通讯质量评估（必输出）

### 必输出指标
| 指标 | 通过标准 |
|------|---------|
| **显著互作对比例**（p < 0.05） | > 10% 但 < 50% |
| **配体-受体共表达验证** | 发送者 90%+ 的细胞表达配体（> 0 count in > 10% cells），接收者同理 |
| **已知通路覆盖度** | 关键通路（如 Notch/Wnt/BMP）应被检测到 |

### 不通过处理
- 互作对过少 → 降低 `min.cells` / 增加细胞类型数
- 假阳性过多 → 上调 p-value 阈值 / 检查细胞类型分得是否过细
- 配体未表达 → 可能是分泌蛋白低表达 → 检查文献确认


## Reference Script (from External Skill)

> Auto-imported from external skill `03_cell-cell-communication`.
> This script is a verified reference implementation, NOT a run.py template.
> The agent can use it as a starting point or fetch official docs for the latest version.

- **Source**: `skills/external/03_cell-cell-communication/scripts/`
- **Imported scripts**: run_cellchat.R


---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="CellChat 细胞通讯结果 —— {样本}",
     context="方法: CellChat v2 | DB: {SecretedSignaling/ECM-Receptor/Cell-Cell Contact} | 结果: {n}条显著配受体对",
     knowledge_base_info=<KB内容>,
   )
   辩论: 关键L-R对跟已知生物学一致吗？通讯网络拓扑合理吗？
   不同条件下通讯差异显著吗？outgoing/incoming pattern 符合预期？
3. save_conclusions(module="03_advanced", topic="CellChat", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
