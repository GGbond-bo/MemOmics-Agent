---
name: metabolomics-full-pipeline
description: "代谢组学全流程分析：LC-MS/GC-MS 峰表 QC → 归一化 → 缺失值填充 → 差异代谢物（t检验/火山图）→ 通路富集（MetaboAnalyst 风格）→ 可视化。输入 peak intensity matrix，输出差异表+富集图。"
version: 1.0.0
author: MemOmics (auto-created)
license: MIT
platforms: [windows, linux, macos]
category: Metabolomics
metadata:
  hermes:
    tags: ['metabolomics', '代谢组学', 'lc-ms', 'gc-ms', 'peak table', 'metaboanalyst', '差异代谢物', '通路富集']
    difficulty: intermediate
    language: Python
    category: Metabolomics
prerequisites:
  r_packages: []
  python_packages: ['pandas', 'numpy', 'scipy', 'statsmodels', 'matplotlib', 'seaborn']
related_skills: ['metabolomics-statistical-analysis', 'metabolomics-functional-enrichment']
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。使用本 skill 前，必须先通过 skill_view 加载本文件。以下规则覆盖所有默认行为。

### 规则1: 写代码前 → 必须先 search_knowledge + skill_view
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 search_papers_by_context 搜文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 8步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. skill_view 加载本 SKILL.md（获取脚本模板+审查规则+参数范围）
3. check_env 检查环境（缺包自动安装）
4. rail_review(pre) 前置审查（参数合理吗？包齐了吗？数据准备好了吗？）
5. 写这一步的代码（基于 skill 模板，只写这一步，不写后续步骤）
6. terminal 执行（分步执行，禁止 && 连接多步骤）
7. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
8. rail_review(post) 后置审查（图有没有？结果合理吗？跟知识库对应吗？）
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时，**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式：正方（支持当前参数）vs 反方（质疑+替代方案）→ 裁判决断
- **不确定的参数就辩论**，不要自己拍脑袋
- **辩论最多 3 轮**：3 轮后选最优参数结果

### 规则5: 执行后审查（强化版）
- 每步执行完调 `rail_review(post)` 审查，审查内容**全部强制**：
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
    - 数值范围是否合理？
    - 跟知识库对应吗？
  - **参数和结论辩论**：
    - 有参数的选择 → **必须调 debate_analysis 辩论**
    - 有结论输出 → **必须调 debate_analysis 辩论**
    - 不通过 → 修复重跑
    - 通过 → 创建目录存储(figures/results/scripts/data) → 下一步

### 规则6: 结果存储结构
```
results/<模块>/<方法>/
  ├── scripts/     # 分析脚本
  ├── figures/     # PNG + SVG 图表
  ├── data/        # RDS/H5AD 中间数据
  └── results/     # CSV/TSV 结果表
```

### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

| 时机 | action | 调 | 不调 |
|------|--------|----|------|
| 脚本报错+你分析根因+修复后 | record_error | ✅ R/Python 脚本报错，你找到根因并修复 | ❌ trivial 错误（打字错误、路径不存在） |
| 脚本成功+结果通过 rail_review | record_success | ✅ 分析步骤完成，图生成，审查通过 | ❌ 闲聊/方法咨询/非分析任务 |
| 修复后脚本验证稳定有效 | update_script | ✅ 同一错误修复了，重跑成功 | ❌ 只改参数没改脚本；未验证就更新 |

---

# 代谢组学全流程分析

处理代谢组学 peak intensity matrix：QC（缺失率/变异系数）→ 归一化（总峰面积/中位数）→ 缺失值填充 → 差异分析（两两组比较 + FDR）→ 富集分析（KEGG 通路注释简化版）→ 火山图/热图/箱线图输出。

## When to Use

[metabolomics-full-pipeline] 用户提供代谢组峰表（LC-MS/GC-MS/NMR 导出），需要完整流程（QC→归一化→差异→富集→可视化）时触发。

## Pipeline

### Step 1
```
Tool: terminal
读取峰表 + 样本分组信息
```

### Step 2
```
Tool: terminal
QC 过滤
```

### Step 3
```
Tool: terminal
归一化+填充
```

### Step 4
```
Tool: terminal
差异分析+FDR
```

### Step 5
```
Tool: terminal
KEGG 富集
```

### Step 6
```
Tool: terminal
可视化输出
```

## Parameters

| 参数 | 默认值 | 说明 |
|------|--------|------|
| min_fraction | 0.8 | 非缺失最低比例 |
| cv_threshold | 0.3 | CV 上限 |
| norm_method | total_area | 归一化方法 |
| fdr_threshold | 0.05 | FDR 阈值 |
| log2fc_threshold | 1.0 | log2FC 阈值 |

## Proven Scripts

> 经实际运行验证成功的脚本记录。`skill_evolution(action="record_run")` 自动追加至此表。
>
> 评分规则：`auto` 来自 rail_review 技术审查，`user` 来自用户认可。

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|:----|:----|:----|:----:|:-----|:----:|:----:|:-:|
| <!-- 首次运行后自动填充 --> | | | | | | | |

- `scripts/run.py` — 主脚本模板（含 MemOmics 审查辩论铁律头）
- `scripts/reference_script.py` — Python 参考实现

## Common Issues

1. 峰表含空列名 → 检查表头。
2. 归一化后全 0 → 先过滤。
## References

- MetaboAnalyst 5.0 官方文档: https://www.metaboanalyst.ca
- Chong J, Wishart DS, Xia J. Using MetaboAnalyst 4.0 for Comprehensive and Integrative Metabolomics Data Analysis. Curr Protoc Bioinformatics. 2019.
- Pang Z, et al. MetaboAnalystR 3.0. Metabolites. 2020.
- 参数对照: `references/metaboanalyst-params.md`（本 skill 与 MetaboAnalyst 的步骤/参数对应表）
