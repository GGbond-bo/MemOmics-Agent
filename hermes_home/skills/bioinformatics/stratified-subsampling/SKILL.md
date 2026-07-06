---
name: stratified-subsampling
description: "分层抽样：3种场景 — 降采样均衡、训练/测试拆分、可视化抽样。Seurat/Scanpy通用"
version: 1.0.0
author: MemOmics
license: MIT
metadata:
  hermes:
    tags: [subsampling, stratified, umap, visualization, train-test-split, scrna]
    difficulty: basic
    language: R+Python
    category: bioinformatics
prerequisites:
  r_packages: [Seurat, ggplot2, dplyr]
  python_packages: [scanpy, anndata, numpy]
---

# 分层抽样 (Stratified Subsampling)

单细胞分析中按样本（sample/group）分层抽样的3种常见场景。适用于已有多样本Seurat/AnnData对象的场景。

## 3种场景

### 场景1: 分层降采样 (Stratified Downsampling)
每个sample取相同数量细胞，避免大样本主导下游分析（聚类、DEG、composition）。

**触发**: "分层降采样" / "每个样本取N个细胞" / "均衡样本"

### 场景2: 分层训练/测试拆分 (Stratified Train/Test Split)
按sample分层拆分，确保每个样本的细胞同时出现在训练集和测试集中，用于机器学习。

**触发**: "分层拆分训练测试" / "按样本拆分" / "ML准备"

### 场景3: 分层可视化抽样 (Stratified Visualization Sampling)
每个sample随机抽N个细胞画UMAP/tSNE，避免overplotting（大样本点太多遮盖小样本）。

**触发**: "分层可视化抽样" / "每个sample抽N个画UMAP" / "抽样可视化"

## 通用流程

1. 加载已有UMAP的Seurat/AnnData对象
2. 确认sample列名（`sample_id` / `sample` / `orig.ident`）
3. 按sample分组，每组建一个细胞池
4. 场景1: 每组取相同数量 → 合并
5. 场景2: 每组随机拆分为训练/测试 → 分别合并
6. 场景3: 每组取min(N, 可用) → 合并 → 画UMAP

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| N_PER_SAMPLE | 200 | 场景1/3每样本最大细胞数 |
| train_ratio | 0.7 | 场景2训练集比例 |
| seed | 42 | 随机种子，确保可复现 |
| sample_col | sample_id | 样本列名 |

## ⚠️ Pitfalls

- **样本数差异大时**：场景3中N_PER_SAMPLE应≤最小样本的细胞数，否则小样本全取后仍被大样本主导
- **UMAP必须已存在**：抽样前确保对象已有UMAP降维结果，抽样后重新算UMAP会改变布局
- **抽样后不要重新聚类**：抽样后的对象仅用于可视化/ML，聚类结果不可靠
- **Seurat subset很慢**：大量细胞时用 `WhichCells` + `subset` 替代循环subset

## References

- 脚本模板: `scripts/stratified_viz_umap.R` — 场景3的完整R脚本
- 场景详解: `references/scenarios.md`

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
