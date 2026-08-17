---
name: Lipidomics Summary Statistics
description: Statistical analysis of lipidomics data
category: Lipidomics
tags: [lipidomics, statistics, summary]
when_to_use: "脂质组学统计汇总：脂质定量数据→描述统计→差异分析→脂质类别分布→可视化"
---
# Lipidomics Summary Statistics Pipeline

## Overview

This skill integrates complex lipid (CL) and free sterol (FS) data from separate
Excel spreadsheets into a single master workbook. For each metabolite it computes
log2 fold changes and Welch's t-test p-values across all specified pairwise
comparisons, then writes a styled Excel file with per-class tabs and a
consolidated significant-hit summary.

## Data Layout

Both CL and FS input files share the same row-per-sample layout:
- **Rows** = samples (one per mouse)
- **Columns** = metabolites
- First 4 columns: SampleID, Genotype, Virus, Condition
- Remaining columns: metabolite concentrations

The pipeline transposes this to metabolite-per-row for statistics computation.

## Inputs

### Required

| Parameter | Type | Description |
|-----------|------|-------------|
| `cl_file` | string | Path to the complex lipids Excel file (multi-tab, one tab per lipid class) |
| `fs_file` | string | Path to the free sterols Excel file (single-tab) |
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。以下规则覆盖所有默认行为。

### 规则1: 拿到数据 → 必须调 search_knowledge
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 7步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. check_env 检查环境
3. rail_review(pre) 前置审查
4. source/import 预写脚本（禁止 inline 代码）
5. terminal 执行（分步执行，禁止 && 连接多步骤）
6. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
7. rail_review(post) 后置审查
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 resolution, n_pcs, min_features, FDR threshold等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式（多角色对抗 v3）：
  - 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
  - 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
  - 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
  - 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
  - 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
  - 辩论结果自动归档到 results/.../log/debate_*.json
- **不确定的参数就辩论**，不要自己拍脑袋

### 规则5: 执行后审查

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

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
    - 通过 → **必须调 skill_evolution(action="record_run")** 记录成功经验（skill_name/script_name/species/tissue/direction/params_used/result_summary/quality_score/notes） → 创建目录存储(figures/results/scripts/data) → 下一步
    - **不通过 → 修复后重跑 → 成功后调 skill_evolution(action="record_run")**；如果是脚本报错 → **调 skill_evolution(action="record_error")** 记录根因+修复方案

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

-----|------|-------------|
| `cl_file` | string | Path to the complex lipids Excel file (multi-tab, one tab per lipid class) |
| `fs_file` | string | Path to the free sterols Excel file (single-tab) |

### Optional (with defaults)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sample_key` | data.frame | 21-sample mouse tumor key | Mapping of Sample IDs (character) to Condition names |
| `condition_order` | character vector | `c("WT","Cpt2-KO","Cpt1-KO","Tsc1-KO","Cpt2/Cpt1-DKO","Cpt2/Tsc1-DKO")` | Display order for conditions |
| `fc_threshold` | numeric | 1 | Minimum absolute log2FC for significance |
| `p_threshold` | numeric | 0.05 | Maximum p-value for significance |
| `min_per_group` | integer | 2 | Minimum positive non-NA values per group for t-test |
| `output_file` | string | `"CL_FS_Master_Summary_Statistics.xlsx"` | Output Excel filename |

### Sample Key Format

A data.frame with columns `SampleID` (character) and `Condition` (character):

```r
sample_key <- data.frame(
  SampleID = as.character(1:21),
  Condition = c("WT","WT","WT","WT","WT","WT",
                "Cpt2/Cpt1-DKO","Cpt2/Cpt1-DKO","Cpt2/Cpt1-DKO",
                "Cpt2/Tsc1-DKO","Cpt2/Tsc1-DKO","Cpt2/Tsc1-DKO",
                "Tsc1-KO","Tsc1-KO","Tsc1-KO",
                "Cpt1-KO","Cpt1-KO","Cpt1-KO",
                "Cpt2-KO","Cpt2-KO","Cpt2-KO"),
  stringsAsFactors = FALSE
)
```

## Pipeline Steps

### Step 1: Read & Harmonize Complex Lipid Data

For each class tab in the CL file:

1. Read with `read_excel(path, sheet = s, skip = 7)` — row 1 becomes the header (metabolite names)
2. Set first 4 column names to SampleID, Genotype, Virus, Condition
3. Filter rows to numeric Sample IDs only (`grepl("^[0-9]+$", SampleID)`)
4. Identify metabolite columns (skip first 4 + any "Total" columns)
5. Transpose to metabolite-per-row matrix
6. Drop metabolites where ALL values are NA
7. Compute per-metabolite, per-comparison statistics:
   - **log2FC**: `mean(log2(ko_vals)) - mean(log2(ref_vals))` where values are positive, non-NA, and each group has >= `min_per_group` values
   - **p-value**: `t.test(log2(ko_vals), log2(ref_vals))$p.value` (Welch's t-test)
8. Build a data.frame per class with sample values, means, log2 means, log2FC, p-values

Tab-to-class matching uses regex patterns with case-insensitive matching to handle
variations like "SM data" vs "SM Data".

### Step 2: Read & Harmonize Free Sterol Data

1. Read with `read_excel(fs_path, sheet = 1, skip = 8)` — **no row-1-as-header override** (different from CL)
2. Same transpose and statistics computation as Step 1
3. All FS metabolites are retained (even those with all-zero values)

### Step 3: Combine into Unified DataFrames

1. **"All Data" sheet**: `rbind` all per-class data.frames
2. **"Significant FC Summary" sheet**: long-format table of all significant hits with columns: Class, Metabolite, Comparison, Log2.FC, P.value, Direction

### Step 4: Write Styled Excel Workbook

- Blue header row (#4472C4) with white bold text
- Thin grey borders on all cells
- Number formatting (4 decimal places for p-values/FC/log2 means, 2 for concentrations/counts)
- Auto-width columns, frozen header row
- Sheet order: All Data, Significant FC Summary, then per-class sheets

## Comparisons

Nine pairwise comparisons are computed:

| # | KO Condition | Reference |
|---|-------------|-----------|
| 1 | Cpt2-KO | WT |
| 2 | Cpt1-KO | WT |
| 3 | Tsc1-KO | WT |
| 4 | Cpt2/Cpt1-DKO | WT |
| 5 | Cpt2/Tsc1-DKO | WT |
| 6 | Cpt1-KO | Cpt2-KO |
| 7 | Tsc1-KO | Cpt2-KO |
| 8 | Cpt2/Cpt1-DKO | Cpt2-KO |
| 9 | Cpt2/Tsc1-DKO | Cpt2-KO |

## Output Spec

The output Excel workbook contains:

| Sheet | Description |
|-------|-------------|
| All Data | All metabolites from all classes (1 row per metabolite) |
| Significant FC Summary | Long-format table of significant hits only |
| PC, P-PC, O-PC, LPC, PE, P-PE, LPE, PS, LPS, PI, PG, SM, Cer, TG, DG, AC, CE | Per-class CL data |
| FS | Free sterol data |

### Column Naming Convention

- Sample columns: `Sample.1(WT)`, `Sample.2(WT)`, ... (condition in parentheses)
- Counts: `n.WT`, `n.Cpt2-KO`, ...
- Means: `Mean.WT`, `Mean.Cpt2-KO`, ...
- Log2 means: `Log2.Mean.WT`, `Log2.Mean.Cpt2-KO`, ...
- Log2FC: `Log2.FC.Cpt2-KO/WT`, `Log2.FC.Cpt2/Cpt1-DKO/Cpt2-KO`, ...
- P-values: `p-value.Cpt2-KO/WT`, `p-value.Cpt2/Cpt1-DKO/Cpt2-KO`, ...

## Known Differences Between CL and FS Input Formats

| Aspect | Complex Lipids | Free Sterols |
|--------|---------------|--------------|
| Skip rows | 7 | 8 |
| Header override | Row 1 becomes header | No override needed |
| Number of tabs | Multiple (one per class) | Single tab |
| Class label | Derived from tab name via regex | "FS" |
| Concentration unit | pmol/mg | ng/mg |
| NA handling | All-NA metabolites dropped | All metabolites retained |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| R kernel crashes | Run via `Rscript` in Bash instead of the R kernel |
| Excel file is 0 bytes on /mnt/results | Write to `/workspace/` first, then `cp` to `/mnt/results/` (FUSE limitation) |
| Tab name mismatch | The pipeline uses regex patterns with case-insensitive matching; check config.yaml patterns |
| t-test fails with <2 values | Comparisons with fewer than `min_per_group` positive values per group produce NA |
| openxlsx not installed | Install with `install.packages("openxlsx", lib = "/mnt/shared-workspace/r-libs")` |
| readxl "New names" warnings | These are harmless — caused by empty cells in the header row before override |

## Dependencies

- R >= 4.0
- readxl
- openxlsx
---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="代谢组学分析 —— {样本}",
     context="方法: {PLS-DA/LIMMA/OPLS-DA} | 参数: VIP>{x} p<{y} | 结果: {n}差异代谢物",
     knowledge_base_info=<KB内容>,
   )
   辩论: 方法对吗？VIP/p值阈值合理？代谢物鉴定可信度？富集通路跟生物学一致？
3. save_conclusions(module="03_advanced", topic="Metabolomics", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```
