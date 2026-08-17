---
name: RGCCA Multiblock Analysis
description: Regularized Generalized Canonical Correlation Analysis for multi-omics
category: Multi-omics
tags: [rgcca, multiblock, integration]
when_to_use: "RGCCA多组学整合分析：多个数据块→正则化典型相关→共享变异→跨组学关联→组分可视化"
---
# RGCCA Multiblock Analysis Skill

## Scope

Runs the full RGCCA analysis pipeline — QC, design matrix construction, single or
grid-search fitting, optional CV/permutation tuning, plot generation, and ranked run
comparison — on any set of named data blocks. Uses the `RGCCA` R package (v3.0.3)
via `Rscript` subprocess. Does NOT perform upstream preprocessing (normalisation,
batch correction, feature selection) beyond scaling; those steps must be done before
calling this skill.

when_to_use: "[rgcca-multiblock] RGCCA多组块正则化典型相关分析：多组学数据块→RGCCA→共享变异→跨组学关联→组分可视化"
---

## Inputs

| Key | Type | Required | Description |
|---
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
- 辩论格式：正方（支持当前参数）vs 反方（质疑+替代方案）→ 裁判决断
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

--|------|----------|-------------|
| `blocks` | dict | yes | `{block_name: path_to_csv}` — one CSV per block |
| `sample_id_col` | str or null | no | Column name holding sample IDs; null = use row index |
| `response_block` | str | no | Name of the supervised response block |
| `design` | str or dict | yes | Named mode or explicit J×J connection matrix |
| `preprocessing` | dict | no | `scale`, `scale_block`, `NA_method` |
| `allow_constant_columns` | bool | no | Default false — fail loudly on constant columns |
| `parameter_grid` | list of dicts | yes | Each entry: lists of values for tau, ncomp, scheme, method, sparsity, superblock, comp_orth |
| `tuning.cv` | dict | no | CV tuning config (enabled, par_type, par_value, k, n_run, metric, prediction_model) |
| `tuning.permutation` | dict | no | Permutation tuning config (enabled, par_type, par_value, n_perms) |
| `ranking_criterion` | str | yes | Key from run manifest metrics to rank runs by |
| `ranking_direction` | str | no | "max" (default) or "min" |
| `plots.n_mark` | int | no | Top-N loadings shown per block (default 10) |
| `plots.comp` | list | no | Component indices to plot (default [1, 2]) |
| `seed` | int | no | Random seed (default 42) |

### Block CSV format

- Header row required.
- Rows = samples, columns = features (plus optional sample ID column).
- All values must be numeric (except the sample ID column).
- All blocks must share the same sample IDs.

### Design modes (both naming conventions accepted)

| Accepted strings | Meaning |
|-----------------|---------|
| `"full"`, `"pair"` | All block pairs connected (1 − I matrix) |
| `"all"` | All connections including self-loops |
| `"star"`, `"response"`, `"response-centered"` | Star topology centred on `response_block` |
| dict-of-dicts | Explicit J×J matrix: `{"blockA": {"blockB": 1, "blockC": 0}, ...}` |

### Valid RGCCA parameter values

- **method**: `"rgcca"`, `"sgcca"`, `"pca"`, `"spca"`, `"pls"`, `"spls"`, `"cca"`, `"ifa"`, `"ra"`, `"gcca"`, `"maxvar"`, `"maxvar-b"`, `"maxvar-a"`, `"mfa"`, `"mcia"`, `"mcoa"`, `"cpca-1"`, `"cpca-2"`, `"cpca-4"`, `"hpca"`, `"maxbet-b"`, `"maxbet"`, `"maxdiff-b"`, `"maxdiff"`, `"sabscor"`, `"ssqcor"`, `"ssqcov-1"`, `"ssqcov-2"`, `"ssqcov"`, `"sumcor"`, `"sumcov-1"`, `"sumcov-2"`, `"sumcov"`, `"sabscov-1"`, `"sabscov-2"`
- **scheme**: `"horst"`, `"centroid"`, `"factorial"`
- **NA_method**: `"na.ignore"`, `"na.omit"`
- **scale_block**: `"none"`, `"inertia"`, `"lambda1"`, `"ssq"`
- **tau**: scalar in [0, 1] or list per block; 0 = CCA-like, 1 = PCA-like
- **sparsity**: scalar in (0, 1] or list per block; 1 = no sparsity
- **ncomp**: positive integer or list per block

### Ranking criterion keys (available in run manifest)

- `AVE_inner_mean` — mean AVE_inner across components
- `AVE_outer_mean` — mean AVE_outer across components
- `AVE_inner_comp1` — AVE_inner for component 1
- `AVE_outer_comp1` — AVE_outer for component 1
- `crit_final` — final convergence criterion value
- `cv_metric_mean` — mean CV metric (only if CV tuning was run)
- `perm_best_crit` — best permutation criterion (only if permutation tuning was run)

---

## Outputs (all written to `/mnt/results/rgcca_<timestamp>/`)

```
rgcca_<timestamp>/
├── config_used.json
├── qc_report.txt
├── design_matrix.csv
├── run_manifest.json
├── ranked_runs.csv
├── ranked_runs_summary.md
├── tuning/
│   ├── cv_best_params.json, cv_stats.csv, cv_plot.png/.svg
│   └── perm_best_params.json, perm_stats.csv, perm_plot.png/.svg
└── runs/
    └── run_NNNN_<hash>/
        ├── config_run.json, manifest.json, summary.txt
        ├── scores_<block>.csv
        ├── weights_a_<block>.csv, weights_astar_<block>.csv
        └── plots/
            ├── plot_samples_*.png/.svg
            ├── plot_loadings_*.png/.svg
            ├── plot_cor_circle_*.png/.svg
            └── plot_ave.png/.svg
```

---

## Workflow Steps

1. **Load and validate config** — parse the config dict/JSON; raise `RGCCAConfigError` for missing required keys, unknown design modes, or unrecognised `ranking_criterion`.
2. **Load blocks** — read each CSV; parse or infer sample IDs.
3. **QC blocks** (`rgcca_qc.py`) — align sample IDs, check missingness, detect constant columns, duplicated IDs, non-numeric features. Fail loudly unless `allow_constant_columns: true`.
4. **Build design matrix** (`rgcca_design.py`) — construct J×J connection matrix from named mode or explicit dict; write to `design_matrix.csv`.
5. **Expand parameter grid** — Cartesian product of all grid entries; deduplicate.
6. **Fit each run** (`rgcca_fit.R`) — one `Rscript` call per parameter combination; serialise scores, loadings, AVE, manifest.
7. **Generate plots** (`rgcca_plots.R`) — one `Rscript` call per run; save all plot types as PNG + SVG.
8. **Run CV tuning** (`rgcca_tune_cv.R`) — if `tuning.cv.enabled`; serialise best params and stats.
9. **Run permutation tuning** (`rgcca_tune_perm.R`) — if `tuning.permutation.enabled`; serialise best params and stats.
10. **Rank runs** (`rgcca_compare.py`) — load all manifests; sort by `ranking_criterion`; write `ranked_runs.csv` and `ranked_runs_summary.md` explaining why the top run was selected.
11. **Return summary dict** — paths to all outputs, top-run params, key metrics.

---

## How to Call This Skill

```python
from rgcca_runner import run_rgcca

config = {
    "blocks": {
        "transcriptomics": "/path/to/rna.csv",
        "proteomics":      "/path/to/prot.csv",
        "clinical":        "/path/to/clin.csv"
    },
    "sample_id_col": "sample_id",
    "response_block": "clinical",
    "design": "star",
    "preprocessing": {
        "scale": True,
        "scale_block": "inertia",
        "NA_method": "na.ignore"
    },
    "allow_constant_columns": False,
    "parameter_grid": [
        {
            "tau":       [0, 0.5, 1],
            "ncomp":     [2],
            "scheme":    ["factorial"],
            "method":    ["rgcca"],
            "sparsity":  [1],
            "superblock":[False],
            "comp_orth": [True]
        }
    ],
    "tuning": {
        "cv": {
            "enabled": True,
            "par_type": "tau",
            "par_value": [0, 0.5, 1],
            "k": 5,
            "n_run": 10,
            "metric": "RMSE",   # RGCCA 3.0.3: "RMSE" or "MAE" only
            "prediction_model": "lm"
        },
        "permutation": {
            "enabled": True,
            "par_type": "tau",
            "par_value": [0, 0.5, 1],
            "n_perms": 100
        }
    },
    "ranking_criterion": "AVE_inner_mean",
    "ranking_direction": "max",
    "plots": {"n_mark": 10, "comp": [1, 2]},
    "seed": 42
}

result = run_rgcca(config)
print(result["ranked_runs_path"])
print(result["top_run"])
```

---

## Scientific Caveats

- **Sample size**: RGCCA is reliable with as few as 10–15 matched samples, but CV tuning with k=5 requires at least 5 samples. Use `k=3` or `k=2` (LOO) for very small datasets.
- **Block scaling**: `scale_block="inertia"` is recommended when blocks have very different numbers of features. Without it, large blocks dominate the solution.
- **tau interpretation**: tau=0 maximises inter-block covariance (CCA-like); tau=1 maximises within-block variance (PCA-like). For small n, tau=1 is more stable.
- **Sparsity and sgcca**: `method="sgcca"` with `sparsity < 1` performs variable selection. The selected variables are not stable across bootstrap resamples unless n is large; interpret with caution.
- **AVE_inner vs AVE_outer**: AVE_inner measures how well the latent components capture inter-block relationships; AVE_outer measures within-block variance explained. Neither is universally better — choose `ranking_criterion` based on your scientific goal.
- **Superblock**: Setting `superblock=True` adds a concatenated block; useful for visualising all variables in one space but changes the optimisation problem.
- **Reproducibility**: The seed is passed to both Python and R (`set.seed()`). Results are fully reproducible given the same RGCCA version.
- **RGCCA version**: This skill targets RGCCA 3.0.3. The API changed substantially between v2 and v3; do not use with v2.x.
- **SVG export**: SVG plots require the `svglite` R package. If `svglite` is unavailable (e.g., due to a `systemfonts` version conflict), the skill automatically falls back to PNG-only output. Install `svglite` with `install.packages("svglite")` in an environment where `systemfonts >= 1.3.0` is available.
- **CV metric**: `rgcca_cv()` in RGCCA 3.0.3 only accepts `"RMSE"` or `"MAE"` as the `metric` argument. The `"cor"` value used in older documentation is not valid.
- **Response block and cor_circle**: When a response block is specified, RGCCA enforces non-orthogonal components for the response block. The `cor_circle` plot is skipped for the response block in this case (RGCCA 3.0.3 restriction); this is handled gracefully.


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
