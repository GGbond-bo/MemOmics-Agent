---
name: segment_with_nn_unet
description: "Segment images using nnUNet with proper environment setup. Supports brain tumor segmentation and other medical image segmentation tasks."
when_to_use: "[segment_with_nn_unet] Segment images using nnUNet with proper environment setup. Supports brain tumor segmentation and other medical image segmentation tasks."
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: []
    difficulty: basic
    language: Python
    category: Bioimaging
prerequisites:
  r_packages: []
  python_packages: []
### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

---

# Segment With Nn Unet

Segment images using nnUNet with proper environment setup. Supports brain tumor segmentation and other medical image segmentation tasks.

## When to Use

When you need segment with nn unet analysis

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `image_path` | [Required] Path to input image file or directory (str) | |
| `output_dir` | [Required] Directory to save segmentation results (str) | |
| `task_id` | [Required] Task identifier (e.g., 'Task001_BrainTumour') (str) | |
| `model_type` | [Optional] Model type for segmentation (default: 3d_fullres) | |
| `folds` | [Optional] Model folds to use for ensemble prediction (default: [0, 1, 2, 3, 4]) | |
| `use_tta` | [Optional] Use test time augmentation (default: False) | |
| `num_threads` | [Optional] Number of threads for preprocessing (default: 1) | |
| `mixed_precision` | [Optional] Use mixed precision for faster inference (default: True) | |
| `verbose` | [Optional] Enable verbose logging (default: True) | |
| `auto_prepare_input` | [Optional] Automatically prepare input for nnUNet (default: True) | |
| `results_folder` | [Optional] Path to nnUNet results folder | |

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
| *(accumulated from runs)* | | |

## References

- Source: Biomni
- Category: visualization
- Language: Python


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
