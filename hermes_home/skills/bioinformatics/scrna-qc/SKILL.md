---
name: scrna-qc
description: "scRNA-seq质控+Doublet+Ambient RNA去除。使用场景：拿到raw矩阵第一步，需过滤低质量细胞/双胞/环境RNA，自动推荐阈值，支持人/鼠"
when_to_use: "[scrna-qc] scRNA-seq质控+Doublet+Ambient RNA去除。使用场景：拿到raw矩阵第一步，需过滤低质量细胞/双胞/环境RNA，自动推荐阈值，支持人/鼠"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [qc, doublet, ambient-rna, scRNA-seq, 01_质控]
    difficulty: basic
    language: R+Python
    category: scRNA
prerequisites:
  r_packages: ["Seurat", "patchwork", "ggplot2", "dplyr"]
  python_packages: ["scanpy", "matplotlib", "harmonypy"]
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

### 规则8: execute_r 持久 kernel 复用（防每步重读重存大对象）
- execute_r 在同一会话复用同一个 R worker：变量（如 obj）和已加载的包**跨调用保留**
- ✅ 第 1 步加载后，后续步骤直接复用 obj，禁止每步 readRDS 重新加载
- ❌ 禁止每步 saveRDS 写中间副本（900MB 级对象反复落盘极慢）
- ⚠️ 仅当报 `object 'obj' not found`（kernel 超时/重启）时才重新 readRDS

---

# scRNA-seq质量控制

质控+Doublet去除+Ambient RNA去除, 支持人/鼠, 自动推荐阈值

适用场景: 所有scRNA-seq

分析步骤:
  - Read10X/ReadH5: Load 10X/Smart-seq2 data
  - QC metrics (mt/ribo): PercentageFeatureSet
  - Doublet removal: DoubletFinder/scDblFinder
  - Ambient RNA (SoupX): Correct ambient RNA
  - Filter cells: By nFeature/percent.mt
  - QC report + Violin: Before/after comparison

依赖包: ggplot2, matplotlib, harmonypy, Seurat, scanpy, patchwork, dplyr

难度: basic

触发提示: "对我的单细胞数据进行质控"

## When to Use

适用于: 所有scRNA-seq

## Step 0: Detect Data State (CRITICAL — do before any QC)

Before writing QC code, determine whether `adata.X` contains **raw counts** or **already-normalized values**. This changes which filters are valid.

**Detection checklist (Python/Scanpy):**
1. Check `adata.X.dtype` — `float32`/`float64` suggests normalized; `int` suggests raw
2. Sample values: `adata.X[:5,:10].toarray()` — if non-integer floats → normalized
3. Check `adata.raw is not None` — raw counts may be stored there
4. Check `adata.layers` for a `'counts'` key
5. Check `np.allclose(X.data, np.round(X.data))` — False → normalized
6. Sanity-check total_counts median: raw scRNA-seq typically 2,000–50,000+ UMIs; if median < 5,000 and values are floats → likely normalized

**If data is already normalized:**
- ✅ `n_genes_by_counts` filter still valid (gene detection unaffected by normalization)
- ✅ `pct_counts_mt` usable as relative reference (computed from normalized expression)
- ❌ Do NOT filter by `total_counts` / `n_counts` (normalized sums are not UMIs)
- ❌ Doublet detection (Scrublet/DoubletFinder) requires raw counts — skip if unavailable
- ❌ SoupX ambient RNA removal requires raw counts — skip if unavailable
- Note in QC report that data was pre-normalized and raw counts unavailable

## Pipeline

1. **Read10X/ReadH5**
   - Load 10X/Smart-seq2 data
   - Tool: `terminal`
2. **Step 0: Detect data state** (see above)
3. **QC metrics (mt/ribo)**
   - R: `PercentageFeatureSet` | Python: `sc.pp.calculate_qc_metrics`
   - Human mt genes: `MT-` prefix | Mouse: `mt-` prefix
   - Tool: `terminal`
4. **Doublet removal** (SKIP if data is normalized — requires raw counts)
   - DoubletFinder/scDblFinder (R) | Scrublet (Python)
   - Tool: `terminal`
5. **Ambient RNA (SoupX)** (SKIP if data is normalized — requires raw counts)
   - Correct ambient RNA
   - Tool: `terminal`
6. **Filter cells**
   - Raw data: filter by n_genes + n_counts + pct_mt
   - Normalized data: filter by n_genes + pct_mt ONLY (skip n_counts)
   - Tool: `terminal`
7. **Gene filter**
   - `min_cells=3` (remove genes in <3 cells)
8. **QC report + Violin**
   - Before/after comparison + by-group (age_group/sample_id) breakdown
   - Tool: `terminal`

## Parameters

### Standard QC thresholds (by species/tissue)

| Species | Tissue | min_genes | max_genes | max_pct_mt | min_counts | max_counts |
|---------|--------|-----------|-----------|------------|------------|------------|
| Human | Skeletal muscle | 200 | 6000 | 15% | 500 | 50000 |
| Human | Default | 200 | 6000 | 20% | 500 | 50000 |
| Mouse | Default | 200 | 6000 | 20% | 500 | 50000 |

> **Note**: Skeletal muscle cells have naturally high mitochondrial content — use 15% (not 10%) to avoid over-filtering. For normalized data, omit `min_counts`/`max_counts` columns entirely.

### Parameter adaptation priority
1. Literature values (search_knowledge + web_search for tissue-specific thresholds)
2. AGENTS.md project defaults
3. Official Scanpy/Seurat defaults
4. Tissue-specific adjustments (e.g., muscle mt% naturally higher)

| Parameter | Default | Notes |
|-----------|---------|-------|
| `r_packages` | Seurat, patchwork, ggplot2, dplyr | |
| `python_packages` | scanpy, matplotlib, seaborn, harmonypy | |
| `steps` | Detect data state → QC metrics → (Doublet) → (SoupX) → Filter → Gene filter → Report | |
| `gene_min_cells` | 3 | Remove genes detected in <3 cells |

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score | Script |
|---------|--------|-----------|------|-------|--------|
| Human | Skeletal muscle | Aging (Young vs Old) | 2026-07-02 | PASS (58/58 checks) | `scripts/scanpy_qc_normalized.py` |

> See also: `references/normalized_data_detection.md` for the detection technique.

| human | skeletal_muscle | aging | 2026-08-14 | qc_validation.R | - | - |  |
| - | - | - | 2026-08-14 | env_check_and_load.R | - | - |  |
| - | - | - | 2026-08-14 | qc_report.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-14 | 03_qc_visualization.R | - | - |  |
| - | - | - | 2026-08-14 | 03_qc_visualization.R | - | - |  |
| - | - | - | 2026-08-14 | pytest_collect_check | - | - |  |
| - | - | - | 2026-08-14 | pytest_offline_run | - | - |  |
## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| Test error for verification | 测试根因 | 测试修复 |
| sc.pp.filter_genes() → anndata copy() → numpy._Arr | sc.pp.filter_genes internally calls .cop | Replace sc.pp.filter_genes() with inplace: gene_co |
| `TypeError: Axes.violinplot() got an unexpected keyword argument 'showextremes'` | matplotlib ≥3.9 removed `showextremes` param entirely (even `=False` crashes) | Remove `showextremes` from all `ax.violinplot()` calls; use `showmedians=True` only |
| `FutureWarning: Use scanpy.set_figure_params instead` | scanpy renamed `sc.settings.set_figure_params` | Use `sc.settings.set_figure_params(...)` (warning only, still works) |
| QC filter removes 0% cells | Data was already pre-filtered/QC'd upstream (common for annotated h5ad from public datasets) | Expected behavior — document in QC report, proceed to next step |
| `pct_counts_mt` very low (<5%) on muscle data | Data is normalized or pre-filtered | Check Step 0 data detection; low mt% confirms upstream QC was done |

## References

- Source: MemOmics built-in
- Category: transcriptomics
- Language: R+Python


## Reference Script (from External Skill)

> Auto-imported from external skill `29_scrnaseq-seurat-core-analysis`.
> This script is a verified reference implementation, NOT a run.py template.
> The agent can use it as a starting point or fetch official docs for the latest version.

- **Source**: `skills/external/29_scrnaseq-seurat-core-analysis/scripts/`
- **Imported scripts**: qc.R, filter_cells.R


---

## ⛔ Terminal 完成后强制协议（铁律 26 · 读完本 skill 即生效）

**本 skill 只执行一个分析步骤。terminal 返回后，你必须立即按顺序完成 5 件事：**

```
1. rail_review(phase='post', code_executed=<用 read_file 读脚本文件，传入完整代码>)
   审查：QC图是否生成？过滤后细胞数合理？MT%/ribo%/doublet比例是否在正常范围？

2. debate_analysis(
     topic="scRNA QC 过滤参数与质量 —— {样本信息}",
     context="数据: {物种} {组织} 原始{细胞数}cells | 参数: MT<{x}% gene>{y} doublet_method={z} | 结果: 过滤后{保留数}cells ({保留率}%)",
     knowledge_base_info=<预查的 KB 内容>,
   )
   辩论维度：
   - 参数: MT阈值合适吗？gene数阈值合适吗？doublet方法选对了吗？
   - 质量: 过滤后细胞质量分布合理吗？有没有过度过滤？
   - 场景: 衰老/疾病样本是否用了更宽松的阈值？

3. save_conclusions(
     module="01_decontamination" (或"02_basic"，取决于QC的位置),
     topic="scRNA QC",
     debate_json=<debate_analysis 返回的完整 JSON>,
     output_dir=<session results_dir>
   )
   → 写入 {module}/conclusions.md + conclusions.json

4. skill_evolution(action="record_run",
     skill="scrna-qc",
     script=<脚本路径>,
     params_json=<实际过滤参数 JSON>,
     result_summary=<过滤前后细胞数 + MT%/ribo%分布 + 辩论结论>,
     quality_score=<1-10>
   )

5. 更新 task_plan.md: QC Phase 标记完成
```

**⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。**
**⛔ 禁止在同一个 terminal 中跑完 QC + 归一化 + 聚类。每次只跑一个分析。**
**⛔ 如果 debate 裁判给出 confidence=low，必须先调整参数重跑，再 record_run。**
