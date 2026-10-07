---
name: functional-enrichment
description: "GSEA/ORA功能富集分析。使用场景：有DEG基因列表或排序列表，需GO/KEGG/Reactome/MSigDB通路富集，R用clusterProfiler Python用gseapy"
when_to_use: "[functional-enrichment] 有差异基因(DEG)列表或pre-ranked基因排序，需GO/KEGG/Reactome/MSigDB通路富集，用clusterProfiler或gseapy"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [03_高级分析]
    difficulty: basic
    language: R+Python
    category: Bulk RNA
prerequisites:
  r_packages: [fgsea, msigdbr, limma, edgeR, Matrix, Seurat, ggplot2]
  python_packages: []
---


## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。使用本 skill 前，必须先通过 skill_view 加载本文件。以下规则覆盖所有默认行为。

### 规则1: 写代码前 → 必须先 search_knowledge + skill_view
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
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
- 涉及数值参数时（如 resolution, n_pcs, min_features, FDR threshold 等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式（多角色对抗 v3）：
  - 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
  - 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
  - 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
  - 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
  - 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
  - 辩论结果自动归档到 results/.../log/debate_*.json
- **不确定的参数就辩论**，不要自己拍脑袋
- **辩论最多 3 轮**：3 轮后选最优参数结果

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

# 功能富集 (GSEA + ORA)

GSEA/ORA功能富集分析。clusterProfiler/gseapy。GO/KEGG/Reactome/MSigDB

分析步骤:
  - GO enrichment: BP/CC/MF via clusterProfiler
  - KEGG pathway: Pathway enrichment + network
  - GSEA (fgsea): Ranked gene set enrichment
  - Visualization: DotPlot + EnrichMap

触发提示: "对DEG做功能富集分析"

## When to Use

当你需要 功能富集 (GSEA + ORA) 时触发

## Pipeline

1. **GO enrichment**
   - BP/CC/MF via clusterProfiler
   - Tool: `terminal`
2. **KEGG pathway**
   - Pathway enrichment + network
   - Tool: `terminal`
3. **GSEA (fgsea)**
   - Ranked gene set enrichment
   - Tool: `terminal`
4. **Visualization**
   - DotPlot + EnrichMap
   - Tool: `terminal`

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `steps` | GO enrichment -> KEGG pathway -> GSEA (fgsea) -> Visualization | |

> **Parameter Adaptation**: Adjust parameters based on tissue quality, species, and condition. Literature values take priority, then official defaults, then tissue-specific adjustments.

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

| human | skeletal_muscle | aging | 2026-07-14 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-07-15 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-08-13 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-08-13 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-08-13 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-08-13 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-08-13 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-08-13 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-08-13 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-08-14 | 10_go_term_barplot.py + go_term_selection 分析 | - | - |  |
| human | skeletal_muscle | aging | 2026-08-14 | 10_go_term_barplot.py | - | - |  |
| human | skeletal_muscle | aging | 2026-08-14 | 10_go_term_barplot.py | - | - |  |
| - | - | - | 2026-08-14 | 10_go_term_barplot.py | - | - |  |
| - | - | - | 2026-08-14 | pytest_verify_go.log | - | - |  |
| human | skeletal_muscle | aging | 2026-09-15 | go_heatmap_v6_final_YlOrRd_words_only.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-15 | rebuild_clean_v3.py + write_clean_v3_xlsx.py + fig_signature_integrity_check.py | - | - |  |
| human | skeletal_muscle | aging | 2026-09-15 | signature_jaccard_axes.py + write_axis_classification.py | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 12_kegg_YPost_vs_OPost.R + 12b_kegg_validation.R + 12c_kegg_collapse_plot.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | inspect_MF_2000.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | env_pkg_and_design_probe.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 01_pseudobulk_limma_A_B_C.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 01_pseudobulk_limma_A_B_C.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 01_pseudobulk_limma_A_B_C.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | install_fgsea_fix.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 02_gsea_atrophy_oxphos.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | msigdbr_api_probe.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 02_gsea_atrophy_oxphos.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | fgsea_minrepro.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | fgsea_minrepro.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 02_gsea_atrophy_oxphos.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 02_gsea_atrophy_oxphos.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 03_fiber_stratified_qc_recheck.R | - | - |  |
| human | skeletal_muscle | - | 2026-09-24 | env_probe_GO_engine.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | inspect_deg_YPost_vs_OPost.csv | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 11_go_YPost_vs_OPost.R | - | - |  |
| - | - | - | 2026-09-24 | - | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | 11_go_YPost_vs_OPost.R | - | - |  |
| - | - | - | 2026-09-24 | 12_go_plot_YPost_vs_OPost.R | - | - |  |
| human | skeletal_muscle | aging | 2026-10-03 | ora_power_for_small_lists.py (execute_python 内联计算) | - | - |  |
## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| R 进程 PID 59900 在 19:25 后零 CPU/IO、RSS 2335MB 卡死，随后进 | enrichGO 用 pvalueCutoff=1/qvalueCutoff=1 | 拆分脚本：ORA 结果已落盘 → 不重跑 enrichGO；第 5 步 simplify(measu |
| <text>:1:106: unexpected symbol  1: exec(open("... | 在 execute_r 的持久 R 内核里沿用了 execute_python  | R 内核不支持 Python 的 exec(open(...).read()) 写法，改用 R 原生 |
| msigdbr() 报错: The `category` argument of `msigdbr( | msigdbr 10.0.0+ 弃用了 category/subcategory | msigdbr 26.1.0 新版 API：category→collection、subcateg |
| GO+KEGG混排气泡图误导 | KEGG基因集远大于GO CC/MF，统一用GeneCount做气泡大小导致KEGG视觉膨胀 | 按类别分面(facet_wrap)，气泡大小改用Rich Factor/Fold Enrichment；或GO和KEGG分两张图 |
| 分析前未创建会话目录 | 直接在results/根目录输出文件，散乱无法溯源 | 分析开始前必须先 `update_results_dir` 创建 `results/{species}_{tissue}_{direction}_{date}/`，再建子目录 `figures/scripts/data/results/` |
| fgsea 结果列名是 `pval` 不是 `pvalue`（fgsea ≥1.30） | 脚本写 `r$pvalue` 取到 NULL（长度 0）→ `data.frame()` 报 `arguments imply differing number of rows: 41, 0`，三口径全空 | 用 `pv <- if (!is.null(r$pval)) r$pval else r$pvalue` 兼容取值；**注意该报错文本会误导成"引擎损坏"，先核对列名** |
| `install.packages("fgsea")` 后 `requireNamespace` 仍 FALSE | 缺 CRAN 依赖 `fastmatch`（报"没有''fastmatch''这种依赖关系"） | 先装 fastmatch 再装 fgsea：`install.packages(c("fastmatch","fgsea"), lib=<主库>, repos=..., type="win.binary")`；Bioc 3.21 ↔ R 4.5 |
| fgsea `eps=0` 在大基因集列表上抛 `differing number of rows` | eps=0 下多级算法不产出结果（内置示例 15 个集合时恰好看不出来） | **不要传 `eps`**，用默认值（1e-10） |
| 小基因集（n<15）在小家族内 BH 后"显著" | 只在含 3 个集合的小家族做 BH，多重检验家族过窄 → 假显著（实例：GOBP_MUSCLE_ATROPHY n=9 padj=0.006，全 GO:BP 家族 3970 集合校正后 padj=0.119 不显著） | 预注册 `minSize≥15`；若要报告小集合，必须在**实际检验的全部集合家族**内统一 BH，并显式标注探索性 |
| 把 HALLMARK/KEGG/GO:BP 同通路"三口径一致"当作独立验证 | 三库 OXPHOS 高度共享基因（Jaccard 仅 0.25–0.48，三库共识 65/303 基因） | 报结论前先算 Jaccard/leading-edge 重叠；高度共享则**不得**按"多次独立复现"计分 |
| fgsea 与 clusterProfiler/org.Hs.eg.db 在同一 R 内核里状态不一致 | check_env 说已装但 `library()` 失败（DLL/依赖损坏假象） | 以 `library()` 实测为准；GSEA 路线用 **fgsea + msigdbr** 即可，不依赖 clusterProfiler/org.Hs.eg.db |
| 设计矩阵不满秩：`~ donor + age_grp` | 供体完全嵌套于年龄组（Y 组与 O 组供体无交集）→ 共线不可识别 | 固定效应路径不可用；配对信息只能由 `duplicateCorrelation(block=donor)` 随机效应承载；敏感性对照组改用 `~ age_grp` |

### Visualization Pitfalls (from debate)

> **2026-07-15 debate verdict (confidence: high)**: When visualizing enrichment across GO (BP/CC/MF) and KEGG on the same axes:
> 1. **Don't use Gene Count as bubble size** — KEGG pathways have inherently larger gene sets, creating false visual dominance. Use **Rich Factor** or **Fold Enrichment** instead.
> 2. **Facet by category** — GO sub-ontologies and KEGG have different statistical backgrounds; mixing them on one y-axis invites false cross-category comparisons.
> 3. **Show direction** — if up/down regulation is known, encode it with color or use bidirectional bars (GSEA NES).
> 4. **Verify cell purity first** — enrichment in muscle subclusters can be driven by contaminating vascular/stromal cells rather than myofibers. Validate with marker gene expression (e.g., ACTA2 for VSMC, MYH7 for slow fibers).
>
> Full debate archive: `references/enrichment-viz-debate-20260715.md`
>
> **Exception — small datasets (≤15 entries)**: When gene counts are comparable across categories (all in 3-15 range), a combined bubble+bar plot is acceptable and publication-grade. The visual bias from GeneCount bubbles is negligible at this scale. Template: `references/go-kegg-bubble-bar.R`.

### Bubble + Bar Template (Small-Dataset GO+KEGG)

For subcluster-level enrichment with ≤15 entries across GO+KEGG. One PDF per subcluster.

- **Template**: `references/go-kegg-bubble-bar.R`
- **Input**: Excel with columns Category | Description | Hits | neg_log_q | Subcluster
- **Layout**: left category blocks → bubbles (size=GeneCount, no text inside) → bars (-log10 q-value) → pathway name → gene list at bar end
- **Output**: transparent-background PDF (`ggsave(..., bg="transparent")`)
- **Height**: auto-scaled `max(5, nrow * 0.55 + 2)` inches
- **Category separators**: dashed lines between BP/CC/MF/KEGG blocks
- **Color scheme**: BP=#5B9BD5, CC=#63B5A0, MF=#88C4E8, KEGG=#E8836E

## References

- Source: MemOmics built-in
- Category: functional_analysis
- Language: R+Python


## Reference Script (from External Skill)

> Auto-imported from external skill `11_functional-enrichment-from-degs`.
> This script is a verified reference implementation, NOT a run.py template.
> The agent can use it as a starting point or fetch official docs for the latest version.

- **Source**: `skills/external/11_functional-enrichment-from-degs/scripts/`
- **Imported scripts**: run_enrichment.R


---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="富集分析结果 —— {对比组}",
     context="方法: {clusterProfiler/enrichR/GSEA} | 参数: p<{x} q<{y} | DB: {GO/KEGG/Reactome} | 结果: {n}条显著通路",
     knowledge_base_info=<KB内容>,
   )
   辩论: 通路跟实验背景吻合吗？top通路合理吗？p值校正方法对吗？
3. save_conclusions(module="03_advanced", topic="Functional Enrichment", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
