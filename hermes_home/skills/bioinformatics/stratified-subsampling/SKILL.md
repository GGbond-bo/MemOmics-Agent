---
name: stratified-subsampling
description: "分层抽样：3种场景 — 降采样均衡、训练/测试拆分、可视化抽样。Seurat/Scanpy通用"
when_to_use: "[stratified-subsampling] 分层抽样下采样：大数据集→分层(细胞类型/样本)→均衡下采样→代表性数据子集"
version: 1.1.0
author: MemOmics
license: MIT
metadata:
  hermes:
    tags: [subsampling, stratified, umap, visualization, train-test-split, scrna]
    difficulty: basic
    language: R+Python
    category: scRNA
prerequisites:
  r_packages: [Seurat, ggplot2, dplyr]
  python_packages: [scanpy, anndata, numpy]
---

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

---

# 分层抽样 (Stratified Subsampling)

单细胞分析中按样本（sample/group）抽样的4种常见场景。适用于已有多样本Seurat/AnnData对象的场景。

## 4种场景

### 场景1: 分层降采样 (Stratified Downsampling)
每个sample取相同数量细胞，避免大样本主导下游分析（聚类、DEG、composition）。

**触发**: "分层降采样" / "每个样本取N个细胞" / "均衡样本"

### 场景2: 分层训练/测试拆分 (Stratified Train/Test Split)
按sample分层拆分，确保每个样本的细胞同时出现在训练集和测试集中，用于机器学习。

**触发**: "分层拆分训练测试" / "按样本拆分" / "ML准备"

### 场景3: 分层可视化抽样 (Stratified Visualization Sampling)
每个sample随机抽N个细胞画UMAP/tSNE，避免overplotting（大样本点太多遮盖小样本）。

**触发**: "分层可视化抽样" / "每个sample抽N个画UMAP" / "抽样可视化"

### 场景4: 纯随机抽样 (Pure Random Sampling)
从全量数据中随机抽取N个细胞，不做分层保证。简单直接，但**稀有细胞类型可能被严重稀释**（如 MastCells 0.2% → 10k 中仅 ~20 cells）。

**触发**: "随机抽样" / "random subset" / "随机抽取N个细胞"

**⚠️ 风险**: 纯随机与分层抽样的关键区别——稀有类型（<1%）在纯随机中可能只有个位数细胞，影响下游分析统计功效。若下游需要每种细胞类型都有足够代表，改用场景1的分层降采样。

**实现**: `np.random.choice(n_total, size=N, replace=False)` + `adata[selected].to_memory()`

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
| min_per_type | 30 | 稀有细胞类型保底数（stratify_by=celltype时） |

## ⚠️ Pitfalls

- **🔴 用户要"简单代码"时先给最简版**：当用户说"给我简单的代码" / "只要一两行" / "只要R"时，**先给每群 `sample(min(2000, n))` 的最简 2-3 行版本**，把分层策略作为"提醒"一句话附在后面（"此版未按条件分层，小条件可能抽没；需要分层版告诉我"）。不要先给长分层脚本——用户明确表达过要简单版（2026-07 骨骼肌 MF 抽样：我先给了 50 行分层版，用户连续两次纠正"给我简单的代码，每群取2000就行，不足就全取，只要一两行代码"）。先满足当前请求，再提示风险，让用户选择是否升级。
- **稀有细胞类型保底**：比例分配可能使稀有类型（<0.5%）分配到过少细胞（如 MastCells 0.2%→20 cells）。设 `min_per_type` 保底值（推荐≥30），超出部分从大类型扣减。验证：`assert allocation.sum() == target_total`
- **rail_review code_executed 必须多行**：执行后审查 `rail_review(post)` 对 `code_executed` 参数有最低长度要求。单行摘要（如"Loaded h5ad, stratified sampling"）会被判"代码过短"拒绝。**必须**用多行伪代码风格（6 行以上），标注 Step 1/2/3、变量名和关键参数。失败后只需用更长的 `code_executed` 重新提交即可通过。示例格式见 `references/code_executed_format.md`
- **样本数差异大时**：场景3中N_PER_SAMPLE应≤最小样本的细胞数，否则小样本全取后仍被大样本主导
- **UMAP必须已存在**：抽样前确保对象已有UMAP降维结果，抽样后重新算UMAP会改变布局
- **抽样后不要重新聚类**：抽样后的对象仅用于可视化/ML，聚类结果不可靠
- **Seurat subset很慢**：大量细胞时用 `WhichCells` + `subset` 替代循环subset
- **🔴 每步至少1张图**：`rail_review(post)` 强制要求 `figure_count >= 1`。抽样完成后必须生成分布图（如年龄柱状图 + 细胞类型条形图 + 比例饼图的 3-panel），否则审查直接 `passed=false`。跑完抽样立即绘图，不要等到下游分析。

## References

- 脚本模板: `scripts/stratified_viz_umap.R` — 场景3的完整R脚本
- 场景详解: `references/scenarios.md`
- 审查格式: `references/code_executed_format.md` — rail_review(post) code_executed 多行格式要求
- 对比图脚本: `scripts/subsample_comparison_figure.py` — 3-panel 抽样前后对比图 (celltype + group + proportionality)

---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用 debate_analysis 工具进行多角色辩论。

### 辩论规则
- **正方 3 位专业编辑**（各自独立，互相看不到）：生物学编辑 / 统计学编辑 / 生信编辑
- **反方 4 位专业编辑**（各自独立，互相看不到，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）

### 触发场景
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

---

## 🔒 审查机制（rail_review）

### 执行前审查 (rail_review pre)
- 检查环境：R/Python 版本、必需包是否安装
- 检查参数：参数来源（知识库/文献/辩论/经验），不能凭空设值
- 检查数据：输入数据格式、细胞数、维度是否合理

### 执行后审查 (rail_review post)
- 检查输出：文件是否生成、大小是否合理
- 检查质量：QC 指标、聚类质量、注释置信度
- 检查图表：是否生成了预期图表、图表是否合理（至少1张）
- **code_executed 必须多行**：见 `references/code_executed_format.md`

**审查通过后** → 调用 skill_evolution(action="record_run") 记录成功经验
**审查失败后** → 修复重跑，成功后记录；脚本报错则 record_error

## Proven Scripts

| 物种 | 组织 | 方向 | 日期 | 脚本 | 评分 |
|------|------|------|------|------|------|
| human | skeletal_muscle | aging | 2026-07-17 | subsample_10k.py | 9/10 |
| human | skeletal_muscle | aging | 2026-07-17 | subsample_10k_random.py | 9/10 | 纯随机, MastCells仅11个 |
