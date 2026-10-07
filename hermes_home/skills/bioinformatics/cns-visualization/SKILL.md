---
name: cns-visualization
description: "Nature/Cell/Science级别出图模板: UMAP+DotPlot+Violin+Heatmap+Sankey"
when_to_use: "[cns-visualization] Nature/Cell/Science级别出图模板: UMAP+DotPlot+Violin+Heatmap+Sankey"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [visualization, cns, ggplot2, umap, dotplot, 07_可视化]
    difficulty: basic
    language: R+Python
    category: Visualization
prerequisites:
  r_packages: []
  python_packages: []

---

# CNS级可视化

Nature/Cell/Science级别出图模板: UMAP+DotPlot+Violin+Heatmap+Sankey

> ### 规则N: 运行记录只是参考，不能跳过审查
> - skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
> - 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
> - 禁止因"之前跑过"而跳过任何审查步骤
> - 禁止直接用历史日志里的脚本运行而不经本次审查
> - 运行日志是"参考"不是"免审凭证"

分析步骤:
  - UMAP FeaturePlot (Nature): Unified palette + hi-res
  - DotPlot: Marker genes across celltypes
  - ViolinPlot: Expression distribution + stats
  - Heatmap: Top DEG + annotation bars
  - Sankey/Alluvial: Cell type flow diagram

触发提示: "生成CNS级可视化图表"

## When to Use

当你需要 CNS级可视化 时触发

## Pipeline

1. **UMAP FeaturePlot (Nature)**
   - Unified palette + hi-res
   - Tool: `terminal`
2. **DotPlot**
   - Marker genes across celltypes
   - Tool: `terminal`
3. **ViolinPlot**
   - Expression distribution + stats
   - Tool: `terminal`
4. **Heatmap**
   - Top DEG + annotation bars
   - Tool: `terminal`
5. **Sankey/Alluvial**
   - Cell type flow diagram
   - Tool: `terminal`

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `steps` | UMAP FeaturePlot (Nature) -> DotPlot -> ViolinPlot -> Heatmap -> Sankey/Alluvial | |

> **Parameter Adaptation**: Adjust parameters based on tissue quality, species, and condition. Literature values take priority, then official defaults, then tissue-specific adjustments.

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

| human | skeletal_muscle | aging | 2026-08-17 | plot_umap_annotation.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-20 | fig_C1_AMPK_violin_4sub.py | - | - |  |
| human | skeletal_muscle | aging | 2026-08-20 | fig_C1_AMPK_violin_4sub.py | - | - |  |
| human | skeletal_muscle | aging | 2026-08-20 | fig_C1_AMPK_violin_4sub.py | - | - |  |
| human | skeletal_muscle | aging | 2026-08-20 | fig_C1_5sub_rawp_effsize.py | - | - |  |
| human | skeletal_muscle | aging | 2026-08-21 | fig_C1_5sub_vs_pure_v2.py | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | data_probe_MF_2000 | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | step1_marker_RNA_SCT_sensitivity.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | step1b_marker_L3_10subclusters.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | step2_marker_heatmap.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | harmony_mixing_figures.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | step3_donor_consistency.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 04_figures.py | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 04_figures.py | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 04_figures.py | - | - |  |
| human | skeletal_muscle | aging | 2026-09-25 | fig_A3_CNS_v5.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-25 | fig_A3_CNS_v6.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-25 | FigA3_CNS_v6_gray_cvd_audit.py | - | - |  |
| human | skeletal_muscle | aging | 2026-09-30 | 37_MF_v7_arrows_vertical.py | - | - |  |
| human | skeletal_muscle | exercise+aging | 2026-09-30 | 41_volcano5_8sub_userstyle.R | - | - |  |
| human | skeletal_muscle | exercise+aging | 2026-09-30 | 41_volcano5_8sub_userstyle.R | - | - |  |
| human | skeletal_muscle | exercise+aging | 2026-09-30 | 42_volcano5_8sub_FINAL.R | - | - |  |
| human | skeletal_muscle | exercise+aging | 2026-09-30 | 42_volcano5_8sub_FINAL.R | - | - |  |
| human | skeletal_muscle | exercise+aging | 2026-09-30 | 42_volcano5_8sub_FINAL.R | - | - |  |
| human | skeletal_muscle | exercise+aging | 2026-09-30 | 42_volcano5_8sub_FINAL.R | - | - |  |
| human | skeletal_muscle | aging | 2026-10-01 | 43_sankey_3group_common_deg.py | - | - |  |
| human | skeletal_muscle | exercise+aging | 2026-10-01 | 43_sankey_3group_common_deg.py | - | - |  |
| human | skeletal_muscle | exercise+aging | 2026-10-01 | 47_mef2c_deg_heatmap.py | - | - |  |
| human | skeletal_muscle | exercise+aging | 2026-10-01 | 43_sankey_3group_common_deg.py | - | - |  |
| human | skeletal_muscle | exercise+aging | 2026-10-01 | 43_sankey_3group_common_deg.py | - | - |  |
## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| numbers of columns of arguments do not match | 补标行追加时对 dplyr tibble 使用 base::rbind。dply | 在 rbind 前把 tibble 降级为普通 data.frame（top_genes <- as |
| error in evaluating the argument 'object' in selec | ComplexHeatmap 的 rowAnnotation 长度必须等于热图矩 | 图2（亚群平均表达热图）中 rowAnnotation(`n`=anno_text(ct_tab[l |
| *(accumulated from runs)* | | |

## References

- Source: MemOmics built-in
- Category: visualization
- Language: R+Python


---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用  工具进行多角色辩论。

### 辩论规则
- **正方 3 位专业编辑**（各自独立，互相看不到）：生物学编辑 / 统计学编辑 / 生信编辑
- **反方 4 位专业编辑**（各自独立，互相看不到，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个编辑是独立的 LLM API 调用，messages 只包含自己的 prompt
- **分科知识库**：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
- **辩论结果自动归档**到 results/.../log/debate_*.json

### 触发场景
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）

---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
   审查: 图是否生成？分辨率是否发表级(300dpi)？配色是否符合期刊规范？
2. debate_analysis(
     topic="可视化图表质量 —— {图表类型}",
     context="类型: {UMAP/Volcano/Heatmap/DotPlot} | 分辨率: 300dpi | 配色: {期刊要求}",
     knowledge_base_info=<KB内容>,
   )
   辩论: 图表类型选对了吗？信息密度合理吗？配色无障碍友好吗？
3. save_conclusions(module="{模块}", topic="Visualization", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```
