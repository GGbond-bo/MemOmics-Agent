---
id: "skill_7ef1858e91dd4b7fbe5daddf31e5002a"
name: "polygenic-risk-score-prs-catalog"
when_to_use: "[polygenic-risk-score-prs-catalog] 需使用polygenic risk score prs catalog功能，适用于相关生信分析场景"
display-name: "Polygenic Risk Score (PGS Catalog)"
category: GWAS/Genetics
short-description: "Calculate polygenic risk scores using pre-computed weights from the PGS Catalog for single or multiple traits with population comparisons."
detailed-description: "Apply pre-computed polygenic risk score (PRS) weights from the PGS Catalog to target genotypes. Supports multi-trait scoring (e.g., cardiometabolic risk panel), population-stratified comparisons across 5 super-populations using 1000 Genomes Phase 3, and combined risk dashboards with correlation matrices and composite risk rankings. No GWAS summary statistics or LD computation needed — uses peer-reviewed, published scoring weights from 5,000+ available traits."
starting-prompt: Calculate polygenic risk scores for cardiometabolic traits using the PGS Catalog with 1000 Genomes example data . .
---
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。以下规则覆盖所有 Biomni 默认行为。

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



# Polygenic Risk Score (PGS Catalog)

## When to Use This Skill

- **You have a trait of interest** and want to calculate PRS using published, peer-reviewed weights
- **Multi-trait risk profiling** (e.g., cardiometabolic panel: CAD, T2D, LDL, BMI, blood pressure)
- **Population comparisons** of genetic risk across ancestry groups
- **No GWAS summary statistics needed** — uses pre-computed weights from PGS Catalog
- **Quick PRS** — minutes per trait (download + score), no LD computation required

**For de novo PRS from raw GWAS summary statistics**, use the `polygenic-risk-score` skill (LDpred2-auto) instead.

## Installation

```r
install.packages(c("data.table", "ggplot2", "ggprism", "dplyr", "R.utils", "jsonlite", "remotes"))
remotes::install_github("privefl/bigsnpr")
```

| Software | Version | License | Commercial Use | Install |
|----------|---------|---------|----------------|---------|
| bigsnpr | ≥1.12 | GPL-3 | ✅ Permitted | `remotes::install_github("privefl/bigsnpr")` |
| data.table | ≥1.14 | MPL-2.0 | ✅ Permitted | `install.packages('data.table')` |
| ggplot2 | ≥3.4 | MIT | ✅ Permitted | `install.packages('ggplot2')` |
| ggprism | ≥1.0.3 | GPL (≥3) | ✅ Permitted | `install.packages('ggprism')` |
| dplyr | ≥1.1 | MIT | ✅ Permitted | `install.packages('dplyr')` |
| jsonlite | ≥1.8 | MIT | ✅ Permitted | `install.packages('jsonlite')` |
| R.utils | ≥2.12 | LGPL (≥2.1) | ✅ Permitted | `install.packages('R.utils')` |

## Inputs

- **Target genotypes:** PLINK binary format (.bed/.bim/.fam) — or use 1000 Genomes Phase 3 example data (2,490 individuals, 5 super-populations)
- **PGS Catalog score IDs:** One or more PGS IDs (e.g., `PGS000018` for CAD) — use `search_pgs_catalog()` to discover available scores
- **Genome build:** GRCh37 (default, matches 1000 Genomes) or GRCh38

## Outputs

**Per-trait files:**
- `prs_scores_<trait>.csv` — Individual PRS (z-scores, percentiles, population labels)
- `distribution_<trait>.png/svg` — PRS distribution histogram
- `population_<trait>.png/svg` — PRS by super-population boxplot

**Combined files:**
- `combined_prs_scores.csv` — All individuals x all traits (wide format) + composite risk
- `prs_correlation_matrix.csv` — Trait-trait PRS correlation matrix
- `population_summary.csv` — Mean PRS by super-population per trait
- `match_reports.csv` — Variant matching summary per trait

**Dashboard plots:**
- `dashboard_correlation_matrix.png/svg` — Heatmap of trait PRS correlations
- `dashboard_composite_risk.png/svg` — Composite risk distribution by population
- `dashboard_population_heatmap.png/svg` — Mean PRS by trait x super-population

**Analysis objects (RDS):**
- `prs_analysis.rds` — Complete analysis object for downstream use
  - Load with: `obj <- readRDS('prs_analysis.rds')`
  - Contains: combined_scores, per_trait, cor_matrix, match_reports, snp_weights, trait_info

## Clarification Questions

1. **Input Data** (ASK THIS FIRST):
   - Do you have specific genotype files (.bed/.bim/.fam) to score?
   - **Or use 1000 Genomes Phase 3 example data?** (2,490 individuals, 26 populations, 5 super-populations)

2. **Traits to Score:**
   - *(If using example data)* The demo scores 5 cardiometabolic traits (CAD, T2D, LDL, BMI, SBP). Choose analysis mode:
     - a) Full cardiometabolic panel — all 5 traits (recommended)
     - b) Select specific traits from the panel
   - *(If using your own data)* What traits do you want to score? Use `search_pgs_catalog("trait name")` to find PGS IDs.

3. **Analysis Options:**
   - a) Standard analysis with dashboard (recommended)
   - b) Individual trait scoring only (no dashboard)

## Standard Workflow

🚨 **MANDATORY: USE SCRIPTS EXACTLY AS SHOWN - DO NOT WRITE INLINE CODE** 🚨

**Step 1 - Load reference genotypes and PGS weights:**
```r
source("scripts/load_reference_data.R")
ref_data <- load_reference_data()

source("scripts/load_pgs_weights.R")
trait_weights <- load_demo_weights()
```
**DO NOT write custom download or parsing code. Use the scripts.**

**Step 2 - Score all traits:**
```r
source("scripts/score_traits.R")
```
**DO NOT write inline scoring code (big_prodVec, allele matching, etc.). Just source the script.**

**Step 3 - Generate visualizations:**
```r
source("scripts/generate_plots.R")
generate_all_plots(all_results, output_dir = "results")
```
🚨 **DO NOT write inline plotting code (ggsave, ggplot, geom_tile, etc.). Just use the script.** 🚨

**The script handles PNG + SVG export with graceful fallback for SVG dependencies.**

**Step 4 - Export results:**
```r
source("scripts/export_results.R")
export_all(all_results, output_dir = "results")
```
**DO NOT write custom export code. Use export_all().**

**✅ VERIFICATION - You should see:**
- After Step 1: `"✓ Reference data loaded successfully"` and `"✓ PGS Catalog weights loaded: 5/5 traits"`
- After Step 2: `"✓ Multi-trait PRS scoring completed successfully! (5 traits, 2490 individuals)"`
- After Step 3: `"✓ All plots generated successfully!"`
- After Step 4: `"=== Export Complete ==="`

**❌ IF YOU DON'T SEE THESE:** You wrote inline code. Stop and use source().

⚠️ **CRITICAL - DO NOT:**
- ❌ **Write inline scoring code** → **STOP: Use `source("scripts/score_traits.R")`**
- ❌ **Write inline plotting code (ggsave, ggplot, etc.)** → **STOP: Use `generate_all_plots()`**
- ❌ **Write custom export code** → **STOP: Use `export_all()`**
- ❌ **Try to install svglite** → script handles SVG fallback automatically

**⚠️ IF SCRIPTS FAIL - Script Failure Hierarchy:**
1. **Fix and Retry (90%)** — Install missing package, re-run script
2. **Modify Script (5%)** — Edit the script file itself, document changes
3. **Use as Reference (4%)** — Read script, adapt approach, cite source
4. **Write from Scratch (1%)** — Only if genuinely impossible, explain why

**NEVER skip directly to writing inline code without trying the script first.**

## Scoring Custom Traits

To score a single custom trait instead of the demo panel:
```r
source("scripts/load_reference_data.R")
ref_data <- load_reference_data()

source("scripts/load_pgs_weights.R")
# Search for available scores
scores <- search_pgs_catalog("your trait name")
# Download specific score
trait_weights <- list()
tw <- download_pgs_weights("PGS_ID_HERE")
trait_weights[["TRAIT"]] <- list(
    weights = tw$weights, pgs_id = tw$pgs_id, score_meta = tw$score_meta,
    trait_name = "Your Trait", short_name = "TRAIT"
)

# Then continue with Steps 2-4 as above
source("scripts/score_traits.R")
```

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| **"bigsnpr not found"** | **Missing core dependency** | **`remotes::install_github("privefl/bigsnpr")`** |
| **Download timeout** | **Large scoring file or slow connection** | **Set `options(timeout = 900)` before running Step 1** |
| **Low match rate (<50%)** | **Genome build mismatch** | **Ensure PGS weights and genotypes use same build (GRCh37 for 1000G)** |
| **PGS ID not found** | **Wrong or deprecated PGS ID** | **Use `search_pgs_catalog("trait")` to find valid IDs** |
| **SVG export error** | **Missing optional dependency** | **`generate_all_plots()` handles fallback automatically. DO NOT install svglite manually.** |
| **"catalog_data not found"** | **Wrong script for this skill** | **Use `score_traits.R` (not `pgs_catalog_scoring.R` from the LDpred2 skill)** |
| **Memory error during scoring** | **Very large scoring file** | **Normal for genome-wide scores. Ensure ≥8GB RAM available.** |

## Suggested Next Steps

After completing multi-trait PRS:
1. **Downstream analysis** — Load `prs_analysis.rds` for custom analyses
2. **Additional traits** — Add more PGS scores to expand the risk panel
3. **De novo PRS** — Use `polygenic-risk-score` skill for traits without PGS Catalog scores
4. **GWAS interpretation** — Pair with functional annotation skills

## Related Skills

- `polygenic-risk-score` — De novo PRS using LDpred2-auto (requires GWAS summary statistics)
- `eqtl-colocalization-coloc` — Colocalization of GWAS signals with eQTLs

## References

1. Lambert SA, et al. (2021). The Polygenic Score Catalog as an open database for reproducibility and systematic evaluation. *Nature Genetics*, 53(4), 420-425.
2. 1000 Genomes Project Consortium (2015). A global reference for human genetic variation. *Nature*, 526(7571), 68-74.
3. Privé F, et al. (2022). Portability of 245 polygenic scores when derived from the UK Biobank and applied to 9 ancestry groups from the same cohort. *AJHG*, 109(1), 12-23.
4. Khera AV, et al. (2018). Genome-wide polygenic scores for common diseases identify individuals with risk equivalent to monogenic mutations. *Nature Genetics*, 50(9), 1219-1224.
5. PGS Catalog: https://www.pgscatalog.org/


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

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="{当前分析} 参数与结果 —— {样本}",
     context="参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<预查的 KB 内容>,
   )
   辩论维度：参数合理性、方法选择正确性、与KB生物学知识一致性、统计方法正确性
3. save_conclusions(module="{模块}", topic="{分析名}", debate_json=<debate返回JSON>, output_dir=<session results_dir>)
   → 写入 {module}/conclusions.md + conclusions.json
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。
⛔ debate confidence=low → 调整参数重跑。
