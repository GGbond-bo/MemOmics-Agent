---
name: generate_embeddings_with_state
description: "Generate State embeddings for single-cell RNA-seq data using the SE-600M model. This function downloads the SE-600M model from Hugging Face, installs required dependencies (git-lfs, uv, arc-state), an"
when_to_use: "[generate_embeddings_with_state] Generate State embeddings for single-cell RNA-seq data using the SE-600M model. This function downloads the SE-600M model from Hugging Face, installs required dependencies (git-lfs, uv, arc-state), an"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: []
    difficulty: basic
    language: Python
    category: scRNA
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

# Generate Embeddings With State

Generate State embeddings for single-cell RNA-seq data using the SE-600M model. This function downloads the SE-600M model from Hugging Face, installs required dependencies (git-lfs, uv, arc-state), and generates embeddings for the input AnnData object. The SE-600M model is a state-of-the-art embedding model for single-cell data that can capture complex biological patterns and cell states. Features include real-time streaming output, automatic retry with reduced batch size on failure, GPU detection and warnings, and input validation.

## When to Use

When you need generate embeddings with state analysis

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `adata_filename` | [Required] Name of the input AnnData file (.h5ad format) (str) | |
| `data_dir` | [Required] Directory containing the input data file (str) | |
| `model_folder` | [Required] Directory where the SE-600M model will be downloaded and stored (str) | |
| `output_filename` | [Optional] Name of the output embeddings file. If None, will use input filename with '_state_embeddings' suffix | |
| `checkpoint` | [Optional] Path to the specific model checkpoint. If None, uses the latest checkpoint in model_folder | |
| `embed_key` | [Optional] Name of key to store embeddings in the output AnnData object (default: X_state) | |
| `protein_embeddings` | [Optional] Path to protein embeddings override (.pt). If omitted, auto-detects in model folder | |
| `batch_size` | [Optional] Batch size for embedding forward pass. Increase to use more VRAM and speed up embedding (default: 500) | |

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
- Category: genomics
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


## 🔒 审查机制（rail_review）

本 skill 执行代码前**必须**调用  进行前置审查，执行后**必须**调用  进行后置审查。

### 审查内容
- **pre 审查**：环境检查（包是否安装）→ 参数校验（参数是否合理）→ 代码审查（语法/逻辑）→ 硬件检查（内存/GPU是否够）
- **post 审查**：结果质量评估（输出是否合理）→ 图表检查（图是否生成）→ 数值检查（细胞数/基因数是否异常）→ 错误检查（有无 warning/error）

### 审查不通过
- pre 不通过 → **阻断执行**，修正后重新审查
- post 不通过 → **阻断下一步**，修正后重跑，直到通过


**★ 强制审查项（任一不通过则重新执行）：**
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
  - 数值范围是否合理？跟知识库对应吗？
- **参数和结论辩论**：
  - 有参数的选择 → **必须调 debate_analysis 辩论**
  - 有结论输出 → **必须调 debate_analysis 辩论**
  - 不通过 → 修复重跑
  - 通过 → **必须调 skill_evolution(action="record_run")** 记录成功经验（skill_name/script_name/species/tissue/direction/params_used/result_summary/quality_score/notes） → 创建目录存储(figures/results/scripts/data) → 下一步
    - **不通过 → 修复后重跑 → 成功后调 skill_evolution(action="record_run")**；如果是脚本报错 → **调 skill_evolution(action="record_error")** 记录根因+修复方案
- 失败时调用  记录错误
- 修复成功后调用  +  替换脚本
