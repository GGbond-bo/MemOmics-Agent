---
name: deg-analysis
description: "Pseudobulk DESeq2+Wilcoxon+MAST多方法差异表达分析。使用场景：已注释的scRNA-seq，需找不同条件/群之间的差异基因，含多重检验校正"
when_to_use: "[deg-analysis] Pseudobulk DESeq2+Wilcoxon+MAST多方法差异表达分析。使用场景：已注释的scRNA-seq，需找不同条件/群之间的差异基因，含多重检验校正"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [deg, DESeq2, pseudobulk, differential-expression, 03_高级分析]
    difficulty: intermediate
    language: R+Python
    category: scRNA
prerequisites:
  r_packages: ["DESeq2", "Seurat", "edgeR", "clusterProfiler", "org.Hs.eg.db", "org.Mm.eg.db"]
  python_packages: ["scanpy", "diffxpy"]
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

# 差异表达分析

Pseudobulk DESeq2+Wilcoxon+MAST多方法, 含多重检验校正

适用场景: 有分组的scRNA-seq

分析步骤:
  - Pseudobulk aggregation: Aggregate by celltype/sample
  - DESeq2 DE: Wald test + LFC shrinkage
  - Wilcoxon test: FindMarkers single-cell DE
  - MAST (optional): GLM with detection rate
  - Multiple testing correction: BH correction + filter
  - VolcanoPlot/Heatmap: Visualize DEG

依赖包: org.Hs.eg.db, clusterProfiler, DESeq2, Seurat, scanpy, org.Mm.eg.db, diffxpy, edgeR

难度: intermediate

触发提示: "进行差异表达分析"

别名: Bulk RNA-seq DE (DESeq2)

## When to Use

适用于: 有分组的scRNA-seq

## Pipeline

1. **Pseudobulk aggregation**
   - Aggregate by celltype/sample
   - Tool: `terminal`
2. **DESeq2 DE**
   - Wald test + LFC shrinkage
   - Tool: `terminal`
3. **Wilcoxon test**
   - FindMarkers single-cell DE
   - Tool: `terminal`
4. **MAST (optional)**
   - GLM with detection rate
   - Tool: `terminal`
5. **Multiple testing correction**
   - BH correction + filter
   - Tool: `terminal`
6. **VolcanoPlot/Heatmap**
   - Visualize DEG
   - Tool: `terminal`

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `r_packages` | DESeq2, Seurat, edgeR, clusterProfiler, org.Hs.eg.db, org.Mm.eg.db | |
| `python_packages` | scanpy, diffxpy | |
| `steps` | Pseudobulk aggregation -> DESeq2 DE -> Wilcoxon test -> MAST (optional) -> Multiple testing correction -> VolcanoPlot/Heatmap | |

> **Parameter Adaptation**: Adjust parameters based on tissue quality, species, and condition. Literature values take priority, then official defaults, then tissue-specific adjustments.

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

| Homo sapiens | heart | sinoatrial node aging | 2026-07-12 | run_deg.R | 7.5 | 6.0 | ✅ |
| Homo sapiens | heart | sinoatrial node aging | 2026-07-12 | run_deg.R | 7.5 | 6.0 | ✅ |
| Homo sapiens | heart | sinoatrial node aging | 2026-07-12 | run_deg.R | 7.5 | 6.0 | ✅ |
| human | skeletal_muscle | aging | 2026-07-14 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-07-17 | run_deg.R | - | - |  |
| human | skeletal_muscle | aging | 2026-07-17 | run_deg_pseudobulk.R | - | - |  |
| human | skeletal_muscle | aging | 2026-07-17 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-07-17 | test_degs.r | - | - |  |
| human | skeletal_muscle | aging | 2026-07-17 | test_degs.r | - | - |  |
## 🚨 Critical Pitfalls

### P1: Pseudobulk per subcluster×condition breaks DESeq2
**Symptom**: `Error: The design matrix has the same number of samples and coefficients to fit`
**Root cause**: Aggregating by subcluster×condition produces exactly 1 pseudobulk sample per combination. DESeq2 requires replicates.
**Fix**: Aggregate by **sample** (samplename/donor) × subcluster, not by condition. Then use condition (age_group, treatment) as the design variable. This gives n_donors × n_subclusters pseudobulk samples with real biological replicates.

### P2: Donor random effects matter for aging studies with imbalanced groups
**Symptom**: Debate flags DEG count as inflated, low validation rate.
**Root cause**: Design `~subcluster + age_group` treats every pseudobulk sample as independent, but multiple subcluster pseudobulks from the same donor share donor-level variation. This inflates effective sample size.
**Mitigation**: When possible, use `~subcluster + age_group + (1|donor)` with variancePartition::dream. When impractical (as in our 2026-07-14 run with 143 samples), report the limitation and validate with Wilcoxon on the most balanced subcluster.

### P3: Sample imbalance >3:1 inflates DEG count
**Symptom**: Old=110, Young=33 → 3,864 DEGs; debate flags >3,000 as potentially inflated.
**Mitigation**: Apply |LFC|>1 filter post-hoc, report both filtered and unfiltered counts, validate top hits with independent method (e.g. Wilcoxon on zone5).

### P4: apeglm shrinkage unavailable by default
**Symptom**: `lfcShrink(type="apeglm")` fails with package-not-found.
**Fix**: Use `type="normal"` or `type="ashr"` as fallback, or skip shrinkage and report raw LFC with caveat.

### P5: h5ad → Seurat via SeuratDisk fails with HDF5 errors
**Symptom**: `Convert(h5ad, dest="h5seurat")` → HDF5-API Errors / `decrementing ID ref count` → R session crash.
**Root cause**: HDF5 version mismatch between anndata and SeuratDisk; `obs` columns may contain non-standard types.
**Fix**: Export counts/features/barcodes as MTX from Python, then `ReadMtx()` in R. See `references/h5ad-to-mtx-workaround.md` for the two-step procedure (Python export + R import).

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| there is no package called 'MAST' | MAST not installed | `BiocManager::install('MAST')` |
| design matrix = samples/coefficients | Pseudobulk aggregated by condition, not sample | Aggregate by donor×subcluster, use condition as design variable |
| lfcShrink type='apeglm' fails | apeglm not installed | Use type='normal' or skip shrinkage |
| DEG count >3,000 | Sample imbalance >3:1 without donor RE | Apply |LFC|>1, validate with Wilcoxon on balanced subcluster |

## References

- Source: MemOmics built-in
- Category: transcriptomics
- Language: R+Python

## 📊 DEG 质量评估（必输出）

### 必输出指标
| 指标 | 通过 | 警告 | 阻断 |
|------|------|------|------|
| **MA 图对称性**（中位 LFC 偏离） | < 0.2 | 0.2-0.5 | > 0.5 |
| **p-value 分布均匀性** | 均匀（峰在 p=0） | 轻微偏差 | U型/U型明显 |
| **BH 校正后 DEG 数合理性** | 50-3000 | 30-50 或 3000-5000 | < 30 或 > 5000 |
| **火山图分布** | 对称、有正负 LFC | 轻微偏斜 | 严重偏斜 |

### 不通过处理
- DEG 过少 → 放宽 FDR / 降低 logFC 阈值 / 检查分组对比设计
- DEG 过多 → 收紧 FDR / 提高 logFC 阈值 / 检查是否未校正批次
- MA 不对称 → 检查归一化 / 可能需 TMM/quantile 替代


---

## ⛔ Terminal 完成后强制协议（铁律 26 · 读完本 skill 即生效）

```
1. rail_review(phase='post', code_executed=<完整脚本代码>)

2. debate_analysis(
     topic="DEG 参数与结果 —— {对比组}",
     context="对比: {A} vs {B} | 方法: {DESeq2/limma/Wilcox} | 参数: FDR<{x} logFC>{y} | 结果: {up}个上调 {down}个下调",
     knowledge_base_info=<预查的 KB 内容>,
   )
   辩论: FDR/logFC阈值合理？方法假设满足？DEG数量合理？跟KB已知marker一致？

3. save_conclusions(module="02_basic"或"03_advanced", topic="DEG", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md

⛔ 不准一次跑完所有对比组。每对对比单独跑，单独辩论。
⛔ debate confidence=low → 调整参数重跑。
