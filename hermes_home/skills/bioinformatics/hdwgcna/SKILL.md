---
name: hdwgcna
description: "WGCNA/hdWGCNA共表达网络分析。模块鉴定/hub基因/模块-性状关联"
when_to_use: "[hdwgcna] WGCNA/hdWGCNA共表达网络分析。模块鉴定/hub基因/模块-性状关联"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [hdwgcna, wgcna, co-expression, module, 03_高级分析]
    difficulty: advanced
    language: R
    category: scRNA
prerequisites:
  r_packages: ["hdWGCNA", "Seurat", "WGCNA", "igraph"]
  python_packages: []
---

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

---

# 共表达网络分析 (hdWGCNA)

WGCNA/hdWGCNA共表达网络分析。模块鉴定/hub基因/模块-性状关联

适用场景: 异质性高, >5K细胞, disease, aging

分析步骤:
  - Setup hdWGCNA: SetUpWGCNA initialize
  - Module detection: FindWGCNAModules
  - Module eigengenes: ModuleEigengenes
  - Hub gene identification: GetHubGenes per module
  - Module-trait correlation: CorrelateModules
  - Functional enrichment: GO/KEGG per module

依赖包: WGCNA, Seurat, hdWGCNA, igraph

难度: advanced

触发提示: "进行共表达网络分析"

别名: 共表达网络 (WGCNA/hdWGCNA)

## When to Use

适用于: 异质性高, >5K细胞, disease, aging

## Pipeline

1. **Setup hdWGCNA**
   - SetUpWGCNA initialize
   - Tool: `terminal`
2. **Module detection**
   - FindWGCNAModules
   - Tool: `terminal`
3. **Module eigengenes**
   - ModuleEigengenes
   - Tool: `terminal`
4. **Hub gene identification**
   - GetHubGenes per module
   - Tool: `terminal`
5. **Module-trait correlation**
   - CorrelateModules
   - Tool: `terminal`
6. **Functional enrichment**
   - GO/KEGG per module
   - Tool: `terminal`

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `r_packages` | hdWGCNA, Seurat, WGCNA, igraph | |
| `steps` | Setup hdWGCNA -> Module detection -> Module eigengenes -> Hub gene identification -> Module-trait correlation -> Functional enrichment | |

> **Parameter Adaptation**: Adjust parameters based on tissue quality, species, and condition. Literature values take priority, then official defaults, then tissue-specific adjustments.

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

| human | skeletal_muscle | aging | 2026-08-01 | run_step4.R + run_step5.R + run_step6.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-01 | run_hdwgcna_official_full.R + resume.R + resume2.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-01 | build_hdwgcna_figure.R + run_hdwgcna_official_*.R + go_kegg_official.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-01 | - | - | - |  |
## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| hdWGCNA/WGCNA 在 MF 亚群数据上拆不出模块：soft threshold R2 最高 | MF（终末分化肌纤维）的转录程序高度协调——慢肌/快肌/代谢基因共享一个主轴，共 | 改用 NMF（RcppML/nmf 包）做基因程序分解——已在同数据上成功拆出 6 个程序（快肌 P |
| `remotes::install_github("smorabit/hdWGCNA")` 超时/连接失败 | GitHub API 限流或网络不可达 | **优先用 `pak::pak("smorabit/hdWGCNA")`** — `pak` 使用独立 GitHub 认证通道，通常能绕过限流。本环境 pak v0.9.4 已预装。详见 `references/pak-github-fallback.md` |
| hdWGCNA 依赖 WGCNA 编译失败 | 缺少系统编译工具（Windows 需 Rtools） | Windows 先装 Rtools；或从 CRAN 装 WGCNA 预编译二进制包后再装 hdWGCNA |
| `FindWGCNAModules` 内存溢出 | 细胞数过多 (>50K) | subset 到 10-20K 细胞，或用 metacells 聚合 |

## References

- hdWGCNA GitHub: https://github.com/smorabit/hdWGCNA
- `pak` GitHub 安装回退方案: `references/pak-github-fallback.md`
- Source: MemOmics built-in
- Category: transcriptomics
- Language: R


## Reference Script (from External Skill)

> Auto-imported from external skill `08_coexpression-network`.
> This script is a verified reference implementation, NOT a run.py template.
> The agent can use it as a starting point or fetch official docs for the latest version.

- **Source**: `skills/external/08_coexpression-network/scripts/`
- **Imported scripts**: run_wgcna.R


---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用 debate_analysis 工具进行多角色辩论。

### 辩论规则
- **正方 3 位专业编辑**（各自独立，互相看不到）：生物学编辑 / 统计学编辑 / 生信编辑
- **反方 4 位专业编辑**（各自独立，互相看不到，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个编辑是独立的 LLM API 调用，messages 只包含自己的 prompt

### 触发场景
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）


## 🔒 审查机制（rail_review）

本 skill 执行代码前**必须**调用 rail_review 进行前置审查，执行后**必须**调用 rail_review 进行后置审查。

### 审查内容
- **pre 审查**：环境检查（包是否安装）→ 参数校验（参数是否合理）→ 代码审查（语法/逻辑）→ 硬件检查（内存/GPU是否够）
- **post 审查**：结果质量评估（输出是否合理）→ 图表检查（图是否生成）→ 数值检查（细胞数/基因数是否异常）→ 错误检查（有无 warning/error）

### 审查不通过
- pre 不通过 → **阻断执行**，修正后重新审查
- post 不通过 → **阻断下一步**，修正后重跑，直到通过
- 失败时调用 skill_evolution 记录错误
- 修复成功后调用 skill_evolution + skill_manage 替换脚本
---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="{当前分析} 参数与结果 —— {样本}",
     context="参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<KB内容>,
   )
3. save_conclusions(module="{模块}", topic="{分析名}", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。
⛔ debate confidence=low → 调整参数重跑。
