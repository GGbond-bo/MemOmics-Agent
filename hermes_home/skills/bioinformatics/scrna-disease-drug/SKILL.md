---
name: scrna-disease-drug
description: "疾病scRNA-seq+遗传证据整合的药物靶点优先级排序。Open Targets/GWAS/eQTL"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [, 04_个性化分析]
    difficulty: basic
    language: Python
    category: drug_discovery
prerequisites:
  r_packages: []
  python_packages: []
---

# scRNA-seq疾病药物发现

疾病scRNA-seq+遗传证据整合的药物靶点优先级排序。Open Targets/GWAS/eQTL

分析步骤:
  - Disease DE analysis: Disease vs control celltype DEG
  - Drug-gene interaction (DGIdb): DEG targets match drugs
  - Drug ranking: Multi-dimension scoring

触发提示: "从疾病scRNA-seq数据发现和优先排序药物靶点"

## When to Use

当你需要 scRNA-seq疾病药物发现 时触发

## Pipeline

1. **Disease DE analysis**
   - Disease vs control celltype DEG
   - Tool: `terminal`
2. **Drug-gene interaction (DGIdb)**
   - DEG targets match drugs
   - Tool: `terminal`
3. **Drug ranking**
   - Multi-dimension scoring
   - Tool: `terminal`

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `steps` | Disease DE analysis -> Drug-gene interaction (DGIdb) -> Drug ranking | |

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

- Source: MemOmics built-in
- Category: drug_discovery
- Language: Python


## Reference Script (from External Skill)

> Auto-imported from external skill `26_scrna-disease-drug-discovery`.
> This script is a verified reference implementation, NOT a run.py template.
> The agent can use it as a starting point or fetch official docs for the latest version.

- **Source**: `skills/external/26_scrna-disease-drug-discovery/scripts/`
- **Imported scripts**: genetic_evidence.py


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


## 🔒 审查机制（rail_review）

本 skill 执行代码前**必须**调用  进行前置审查，执行后**必须**调用  进行后置审查。

### 审查内容
- **pre 审查**：环境检查（包是否安装）→ 参数校验（参数是否合理）→ 代码审查（语法/逻辑）→ 硬件检查（内存/GPU是否够）
- **post 审查**：结果质量评估（输出是否合理）→ 图表检查（图是否生成）→ 数值检查（细胞数/基因数是否异常）→ 错误检查（有无 warning/error）

### 审查不通过
- pre 不通过 → **阻断执行**，修正后重新审查
- post 不通过 → **阻断下一步**，修正后重跑，直到通过
- 失败时调用  记录错误
- 修复成功后调用  +  替换脚本


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
### 多角色辩论 (debate_analysis)
当遇到**不确定的参数选择或结果判断**时，**必须**调用 ：
- 正方 3 角色（各自独立，互相不知道）：生物学 agent / 统计学 agent / 生信 agent
- 反方 4 角色（各自独立，互相不知道，也看不到正方）：生物学 agent / 统计学 agent / 生信 agent / 历史经验 agent
- 裁判：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
- 上下文隔离：每个角色独立 HTTP API 调用，messages 只有自己的 prompt

### 辩论触发场景
- 聚类分辨率选择（0.3 vs 0.5 vs 0.8 vs 1.2）
- QC 阈值设定（MT% 10% vs 15% vs 20%）
- 细胞类型注释争议（marker 不明显时）
- 归一化方法选择（SCT vs LogNormalize）
- 降维参数选择（PC 数量 10 vs 20 vs 30）
- 差异表达阈值（p<0.05 vs p<0.01, logFC 阈值）
- 任何需要多方审视的分析决策
