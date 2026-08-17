# scTour Multi-Configuration Comparison — 2026-07-08 Human Skeletal Muscle (Second Run)

> **关键教训**：同一数据集、同一三配置方案，第二次运行因 **辩论关注点不同** 产生了不同的优胜者。这证明了多配置对比不是一次性的，辩论标准直接影响结论。

## Data Context

| Field | Value |
|-------|-------|
| Species | human (Homo sapiens) |
| Tissue | skeletal_muscle |
| Direction | aging + diabetes + exercise |
| Cells | 11,630 |
| Genes | 51,227 (HVG subset: 1,000) |
| Annotation | subcluster: TypeI, TypeII, RSS |
| Counts location | `.layers['counts']` |
| Environment | Python 3.10 venv, CPU mode, RTX 5070 Ti (Blackwell) |

## Three Configurations (same as 2026-07-07)

| Config | `alpha_recon_lec` | `alpha_recon_lode` | `n_latent` | `random_state` |
|:------:|:---:|:---:|:---:|:---:|
| run1_balanced | 0.5 | 0.5 | 5 | 0 |
| run2_encoder | 0.8 | 0.2 | 8 | 42 |
| run3_ode | 0.3 | 0.7 | 3 | 123 |

## Results Comparison (2026-07-08)

| Run | Young_mean | Old_mean | Delta | Avg_KS | Selected? |
|:---:|:----------:|:--------:|:-----:|:------:|:---------:|
| run1_balanced | 0.468 | 0.541 | +0.073 | **0.356** | **Yes** |
| run2_encoder | 0.580 | 0.574 | -0.006 | 0.238 | No (direction reversed) |
| run3_ode | 0.104 | 0.233 | +0.129 | 0.309 | No (compressed range) |

### Exercise-Specific KS Results (from run1_balanced)

| Group Pair | KS_stat | KS_pval | Separability |
|:-----------|:-------:|:-------:|:------------|
| Old_normal_Post vs Old_diabete | 0.2933 | 2.79e-18 | good |
| Old_normal vs Old_normal_Post | **0.5237** | 3.98e-94 | **excellent** |
| Young_normal vs Old_normal | 0.4613 | 9.55e-48 | excellent |
| Old_diabete vs Old_diabete_Post | 0.2114 | 4.92e-23 | good |
| Young_normal vs Young_normal_Post | **0.6338** | 5.53e-91 | **excellent** |

**Key biological finding**: Exercise effect (Old_normal vs Old_normal_Post KS=0.52) was stronger than aging effect (Young_normal vs Old_normal KS=0.46).

## Why Different Verdict from 2026-07-07?

| Aspect | Run 1 (07-07) | Run 2 (07-08) |
|:-------|:-------------|:-------------|
| Debate focus | Direction (+0.014 vs -0.014) | Overall KS separability (avg_ks=0.356) |
| Winner | run2_encoder (better direction) | run1_balanced (better total separability) |
| Aging KS | not computed | 0.46*** |
| Diabetes KS | not computed | 0.27*** |
| Exercise KS | not computed | 0.52*** (Old), 0.63*** (Young) |

### Lesson Learned

The optimal config **depends on which biological question is primary**:
- **Aging as primary question** → Balanced captures the trajectory best
- **Exercise intervention as primary** → Balanced wins decisively (KS=0.52 for Pre vs Post)
- **Diabetes-specific signal** → ODE or Encoder may be better

**Recommendation**: Always run at least 3 configs (Balanced/Encoder/ODE). The debate **must** consider ALL group comparisons, not just one binary split. Use the `avg_ks` metric across all biologically meaningful pairs as an objective tiebreaker.

## Self-Evolution Logging Lesson

This session exposed a critical workflow gap:

1. **Initial run**: Agent skipped `skill_evolution(action="record_run")` entirely → no `.run_logs/` created, no Proven Scripts updated
2. **User asks**: "为什么没有触发日志呢？自进化呢？" → retroactive fix triggered
3. **Record_run called**: 6 calls, first 4 worked, last 2 returned Success but didn't write → user asked again "日志不是要放到结果文件吗？log目录下"
4. **Final fix**: Manual copy from wrong path (`hermes-agent/results/.../log/`) to correct path (`results/.../log/`)

**Workflow fix**: The SKILL.md now mandates:
- Step 9: `skill_evolution(action="record_run")` + **IMEDIATE verify** file on disk
- Step 10: Check BOTH `results/.../log/` AND skill's `.run_logs/`
- The `execution-checklist.md` reference file documents this in detail

## Key Workflow Steps (Verified Working)

1. **Count extraction**: `adata.X = adata.layers['counts'].copy()` before HVG selection
2. **Dtype fix**: `.X` to float32 (avoid PyTorch Double/Float mismatch)
3. **Sparse→dense**: SparseCSRView to dense (avoid `.A` attribute error)
4. **HVG**: `flavor='seurat_v3', n_top_genes=1000`
5. **Model save**: `tnode.save_model(save_dir, 'sctour_model')` for each run
6. **Figure save**: Each run's figures go to `figures/run{1,2,3}_{config}/`
7. **Comparison**: KS test across ALL group pairs, not just Young vs Old
8. **Report**: HTML report embeds 9 figures + debate records + KS table

## Report

Generated via `generate_report` tool with custom HTML containing:
- 9 embedded PNG figures (3 runs × 3 key views per run)
- Parameter comparison table
- KS test results (21 pair comparisons)
- Debate verdict and biological interpretation

**Path**: `results/human_skeletal_muscle_aging_diabetes_exercise_20260708/03_advanced/scTour/scTour_Trajectory_Report.html`

**Size**: ~4MB (9 embedded base64 figures + HTML structure)