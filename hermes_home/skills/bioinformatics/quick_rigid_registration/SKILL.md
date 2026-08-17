---
name: quick_rigid_registration
description: "Perform rigid image registration between two medical images using SimpleITK. Rigid registration handles translation and rotation only, preserving shape and size. Includes preprocessing, similarity met"
when_to_use: "[quick_rigid_registration] Perform rigid image registration between two medical images using SimpleITK. Rigid registration handles translation and rotation only, preserving shape and size. Includes preprocessing, similarity met"
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

# Quick Rigid Registration

Perform rigid image registration between two medical images using SimpleITK. Rigid registration handles translation and rotation only, preserving shape and size. Includes preprocessing, similarity metrics calculation, and visualization generation.

## When to Use

When you need quick rigid registration analysis

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `fixed_image_path` | [Required] Path to the reference (fixed) image file (supports .nii, .nii.gz, .nrrd, .mha, .mhd formats) (str) | |
| `moving_image_path` | [Required] Path to the image to be registered (moving image) (str) | |
| `output_dir` | [Required] Directory path to save registration results and outputs (str) | |
| `metric` | [Optional] Similarity metric for registration: 'mutual_information', 'mean_squares', 'correlation', or 'normalized_correlation' (default: mutual_information) | |
| `optimizer` | [Optional] Optimization method: 'gradient_descent', 'lbfgsb', 'powell', or 'amoeba' (default: gradient_descent) | |
| `preprocess` | [Optional] Whether to preprocess images (denoising and normalization) (default: True) | |
| `create_visualizations` | [Optional] Whether to create visualization plots (default: True) | |
| `learning_rate` | [Optional] Learning rate for gradient descent optimizer (default: 0.01) | |
| `number_of_iterations` | [Optional] Maximum number of optimization iterations (default: 100) | |
| `gradient_convergence_tolerance` | [Optional] Convergence tolerance for optimization (default: 1e-06) | |

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
