---
name: batch_register_images
description: "Perform batch registration of multiple images to a single reference image. Automatically processes all medical image files in a directory and registers them to the fixed reference. Supports rigid, aff"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: []
    difficulty: basic
    language: Python
    category: visualization
prerequisites:
  r_packages: []
  python_packages: []
---

# Batch Register Images

Perform batch registration of multiple images to a single reference image. Automatically processes all medical image files in a directory and registers them to the fixed reference. Supports rigid, affine, or deformable registration for all images.

## When to Use

When you need batch register images analysis

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `fixed_image_path` | [Required] Path to the reference (fixed) image file (str) | |
| `moving_images_dir` | [Required] Directory path containing multiple images to register (supports .nii, .nii.gz, .nrrd, .mha, .mhd formats) (str) | |
| `output_dir` | [Required] Directory path to save registration results for all images (str) | |
| `transform_type` | [Optional] Type of registration to perform: 'rigid', 'affine', or 'deformable' (default: rigid) | |
| `metric` | [Optional] Similarity metric for registration: 'mutual_information', 'mean_squares', 'correlation', or 'normalized_correlation' (default: mutual_information) | |
| `optimizer` | [Optional] Optimization method: 'gradient_descent', 'lbfgsb', 'powell', or 'amoeba' (default: gradient_descent) | |
| `preprocess` | [Optional] Whether to preprocess images (denoising and normalization) (default: True) | |
| `create_visualizations` | [Optional] Whether to create visualization plots for each registration (default: True) | |
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
- **正方 3 角色**（各自独立，互相看不到）：生物学 agent / 统计学 agent / 生信 agent
- **反方 4 角色**（各自独立，互相看不到，也看不到正方）：生物学 agent / 统计学 agent / 生信 agent / 历史经验 agent
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个角色是独立的 LLM API 调用，messages 只包含自己的 prompt

### 触发场景
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）
