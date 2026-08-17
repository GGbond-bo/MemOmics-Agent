---
name: Analysis Summary Report
description: Generate comprehensive analysis summary reports
category: General Utility
tags: [report, summary]
when_to_use: "生成分析总结报告：分析完成→自动汇总结果→生成综合报告→含图表/表格/结论"
---
# Analysis Summary Report — 分析后总结报告

## 🔒 报告完整性铁律（禁止偷懒）

1. **只要检查到有分析结果，所有分析辩论、图片都要加入报告，不许漏。**
2. **如果有图才几十 KB，那就是有问题的**——必须报告并重新生成。
3. 不特定说明的情况下，报告必须覆盖本次分析的所有模块和所有图片。
4. 每张图的 4 个面板（method/result/bio/param_source）全部必填，传空直接报错。
5. 报告中每张图的解读结论必须经过 `debate_figure_conclusions` 辩论。
6. 报告中每个分析模块的总结论必须经过 `debate_figure_conclusions` 辩论。

## 🔒 报告语言铁律

- 检测用户交互语言：用户用中文 → 报告全程中文；用户用英文 → 报告全英文。
- 无论重新生成多少次，语言必须与用户首次交互语言一致。

## 🔒 图片健康度铁律

- 放入 HTML 的每张图片必须检查（rail_review POST 审查会自动检测）：
  - 文件大小 < 5KB → 强制重新生成
  - 全白/全黑/全单一色 → 强制重新生成
  - 含大量 NA 值 → 画图不全，强制重新生成
  - 文件损坏 → 强制重新生成
- **不允许跳过任何问题图。**

## 触发场景

**触发条件（必须全部满足）：**
1. 已经完成真实分析（有 terminal 执行结果 + 生成了 figures）
2. 用户要求总结/报告/归纳

**不触发：**
- 没有做过分析，只是文献综述/整理结果
- 只有个别步骤完成，没有系统分析
- 概念咨询、闲聊

## 报告 7 模块结构

### 模块 1：📊 数据概览
- 数据来源（文件路径、格式）
- 细胞数、基因数
- 物种、组织、测序方法
- 硬件环境（CPU/内存/GPU/磁盘，来自 scan_data）

### 模块 2：🔬 分析流程
- 每步分析用了什么 skill
- 每步的参数（归一化方法、聚类分辨率、PC数等）
- 每步的执行时间
- 每步的 rail_review 结果（通过/不通过）

### 模块 3：📚 知识库来源
- 每个参数推荐来自哪条知识库记录
- 知识库类目（标准化/批次校正/聚类/注释/DEG等）
- 匹配的文献引用

### 模块 4：🗣️ 辩论记录
- 每轮 debate_analysis 的完整记录
- 正方论点（生物学/统计学/生信角度）
- 反方论点（同样角度 + 历史经验/报错记录）
- 裁决结果、分数、行动项

### 模块 5：📈 图表结果
- 每张图带 4 个面板：
  - 方法：用了什么方法生成
  - 结果：图展示了什么
  - 生物学意义：图说明了什么生物学发现
  - 参数来源：参数来自知识库/文献/辩论/经验
- 图片按分析模块排列（QC图 → PCA → UMAP → 标记基因 → DEG → 通路等）

### 模块 6：🧬 生物结论
- **结论辩论**（必须）：
  - 正方：从生物学（marker gene验证、已知生物学知识）、统计学（显著性、效应量）、生信（质量指标）角度支持结论
  - 反方：从同样角度 + 历史经验记录 + 报错记录质疑结论
  - 裁判：综合裁决，给出置信度（高/中/低）
  - 不互通上下文：正方不知道反方说了什么
- 结论必须**根据真实结果总结**，不能凭空编造
- 每条结论标注证据来源（哪张图、哪个分析、哪个辩论）

### 模块 7：⚠️ 质量评估
- QC 指标：nFeature、nCount、percent.mt 分布
- 双胞率
- 污染率（如果做了去污染）
- 线粒体阈值
- 细胞过滤前后数量对比

## 技术实现

基于 `bioinformatics-html-report` 的 ReportBuilder API：

```python
import sys
sys.path.insert(0, "hermes_home/skills/bioinformatics/bioinformatics-html-report")
from html_report_builder import ReportBuilder

rb = ReportBuilder(
    title="MemOmics Analysis Summary",
    subtitle="scRNA-seq Analysis Report",
    stats=[("细胞数", "30,000"), ("基因数", "20,000"), ("聚类数", "12")],
    key_findings=["发现 X 个主要细胞群", "衰老相关基因在 Type II 纤维中上调"]
)

# 模块 1-7 分别用 section
with rb.section("overview", "Data Overview", "数据概览"):
    ...

with rb.section("pipeline", "Analysis Pipeline", "分析流程"):
    ...

# 每张图用 add_figure（4面板）
rb.add_figure(
    fig_path="figures/umap.png",
    caption_en="UMAP Visualization",
    method_zh="Seurat UMAP 降维可视化",
    result_zh="12个细胞群清晰分离",
    bio_zh="Type II 纤维细胞是最大群体，符合骨骼肌组织特征",
    param_source_zh="聚类分辨率0.5来自知识库推荐（139条匹配）"
)

# 辩论记录用 add_debate
rb.add_debate(topic="聚类分辨率选择", rounds=[...])

rb.save("analysis_summary_report.html")
```

## 结论辩论要求

1. **正方**（3个角色，各自独立）：
   - 生物学编辑：从 marker gene 表达、已知细胞类型标记、组织生物学特征角度支持结论
   - 统计学编辑：从显著性检验、效应量、样本量角度支持结论
   - 生信编辑：从 QC 指标、双胞率、污染率、聚类质量角度支持结论

2. **反方**（4个角色，各自独立）：
   - 生物学编辑：从异质性、批次效应、标记基因重叠角度质疑
   - 统计学编辑：从多重比较、假阳性、统计功效角度质疑
   - 生信编辑：从降维质量、聚类稳定性、注释置信度角度质疑
   - 历史经验编辑：从 error_memory/errors.jsonl 历史报错记录角度质疑

3. **裁判**：看到所有角色论点，综合裁决，给出置信度（高/中/低）

4. **上下文隔离**：每个编辑独立 HTTP 调用，正方不知道反方说了什么，反之亦然

## 使用方式

```
# 在 SOUL.md 触发链路中：
分析完成后 → 用户要求总结 → skill_view("analysis-summary-report")
→ 收集会话历史中的分析记录
→ 对生物结论进行辩论
→ 用 ReportBuilder 生成 HTML
→ 保存到 results/{sid}/analysis_summary_report.html
```


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


### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

when_to_use: "[analysis-summary-report] 需使用analysis summary report功能，适用于相关生信分析场景"
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

### 多角色辩论 (debate_analysis)
当遇到**不确定的参数选择或结果判断**时，**必须**调用 ：
- 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
- 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
- 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
- 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
- 辩论结果自动归档到 results/.../log/debate_*.json

### 辩论触发场景
- 聚类分辨率选择（0.3 vs 0.5 vs 0.8 vs 1.2）
- QC 阈值设定（MT% 10% vs 15% vs 20%）
- 细胞类型注释争议（marker 不明显时）
- 归一化方法选择（SCT vs LogNormalize）
- 降维参数选择（PC 数量 10 vs 20 vs 30）
- 差异表达阈值（p<0.05 vs p<0.01, logFC 阈值）
- 任何需要多方审视的分析决策
