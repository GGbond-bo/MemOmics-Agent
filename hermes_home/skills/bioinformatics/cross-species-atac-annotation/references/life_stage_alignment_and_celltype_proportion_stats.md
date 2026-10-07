# Cross-Species Life-Stage Alignment + Cell-Type Proportion Statistics (2026-08-29)

Session lessons: after both species are annotated and ages verified, the next patent step is
cell-type × age-group proportion analysis. Two hard rules emerged.

## 1. Age-group alignment must be by LIFE STAGE, never by absolute age

Monkey (Zhang Xiao 2026) age groups and human (Zemke GSE278576) age groups are NOT
numerically comparable:

| Life stage | Monkey (张潇原文) | Human (Zemke) | Stage label (unified) |
|---|---|---|---|
| Young | 5-6 yr (n=6) | 20-40 (n=10) | Young |
| Middle-aged | 10-12 yr (n=5) | 40-60 (n=10) | Middle |
| Old | 22-23 yr (n=6) | 60-80 (n=10) | Old |
| Exceptionally old | 28-31 yr (n=6) | 80-100 (n=10) | Exceptionally old |

- Monkey lifespan ~25-30 yr; human ~80-100 yr. Monkey "20" is OLD, human "20" is YOUNG.
- Do NOT map Young↔20-40 by arithmetic; map by relative life stage.
- 张潇原文 quoted (manuscript Results, "They spanned four age groups"):
  "young adult (5-6 years, n = 6), middle-aged (10-12 years, n = 5), old (22-23 years, n = 6),
  and exceptionally old (28-31 years, n = 6). The exceptionally old group corresponds to the
  upper end of the typical lifespan for this species in captivity... Transitions from young to
  middle age, middle age to old, and old to exceptionally old were defined as the early, late,
  and very late stages of aging, respectively."
- Human side: add a unified stage column from Age_group:
  ```r
  stage <- c("20-40"="Young","40-60"="Middle","60-80"="Old","80-100"="Exceptionally old")
  proj$age_stage <- unname(stage[proj$Age_group])
  stopifnot(sum(is.na(proj$age_stage)) == 0)
  ```
- Monkey side already has the stage names; alias `age_stage <- Age_group` (rename Exceptionally old → EO if desired for axis readability).
- Deliverable for thesis: keep BOTH original interval names (evidence) AND unified stage (cross-species comparison).

## 2. Cell-type × age-group proportion analysis: statistical discipline

### Unit of analysis = INDIVIDUAL, never cell count (pseudoreplication, patent rule)
- Human: 40 individuals (10 per stage). Monkey: 21 individuals (Young 4 / Middle 5 / Old 6 / EO 6).
- Build per-individual proportion table FIRST:
  ```r
  tab <- as.data.frame(table(Sample=cd[[sm]], celltype=cd[[ct]], Age_group=cd[[ag]]))
  wide_pct <- tab |> pivot_wider(names_from=celltype, values_from=Freq, values_fill=0) |>
    mutate(total=rowSums(across(where(is.numeric)))) |>
    mutate(across(where(is.numeric) & !all_of("total"), ~round(100*.x/total, 2)))
  ```
- Then plot individual dots + median + significance per stage boxplot.

### Correlation with ordinal age groups → Spearman ρ, not Pearson
- Age_group is ordinal (4 levels), small n per group, non-normal → Spearman rank correlation.
- Readout in plot header: `hum: ρ=-0.65 ***` = human Spearman ρ, p<0.001.
- Sign = direction (+同向 / −反向 / 0无趋势); magnitude ≈ |ρ| (0.3-0.5 weak, 0.5-0.7 moderate, >0.7 strong); p = credibility.
- Reference: Schober et al. 2018, Anesthesia & Analgesia, PMID 29481436 (correlation coefficient selection: ordinal/non-normal → Spearman).

### "No significant change" IS a same-direction (conserved) result — positive thesis evidence
User asked: "InN这个人和猴子没有显著变化，是不是也是同向呢？因为我们要做到的是猴子跟人到底有多像，替代性如何"
- YES. For the substitutability claim, "both species unchanged" (ρ≈0, both ns) is as good as
  "both species change in same direction". Both are agreement between species.
- Frame in thesis: "InN proportion was stable across aging in both species (human ρ=0.03, monkey
  ρ=0.23, both ns), indicating cross-species conserved composition during senescence."
- ONLY a species-divergent pattern (human ↓ monkey ↑, or significant in one but flat in the other
  with a real difference) weakens substitutability.

## 3. Figure conventions for the proportion deliverable (用户偏好 2026-08-29)
- **Concordance 专图（per-celltype 跨物种一致性图，用户采用的主图样式）** — 每个共有细胞类型单独一张，直接可写进论文：
  ```python
  # 样式：两物种 mean±SEM 轨迹（errorbar）+ 个体散点 + Spearman ρ [Bootstrap 95% CI] p 进图例
  for sp, color, marker in [('human','#0072B2','o'), ('monkey','#D55E00','s')]:
      sub = df[(df.celltype==CT) & (df.species==sp)]
      rho, p = stats.spearmanr(sub.age_ord, sub.pct)
      ci = np.percentile(bootstrap_rhos(sub, 5000), [2.5,97.5])
      ax.errorbar(range(1,5), group_mean, yerr=group_sem, color=color, marker=marker,
                  ms=5, lw=1.4, capsize=3,
                  label=f"{sp}  ρ={rho:.2f} [{ci[0]:.2f},{ci[1]:.2f}]  p={p:.3f}")
      ax.scatter(sub.age_ord, sub.pct, s=14, color=color, alpha=0.4, zorder=3)
  # x=Young/Middle/Old/EO（4 序数阶段），文件名 <CT>_concordance_v2.{png,pdf,svg}，尺寸 4.2x3.0in，300dpi
  ```
  完整可复用脚本：`scripts/concordance_astro_opc.py`（Astro/OPC 已出；用户点名"跟 InN_v2 那张图一样"时，把脚本里 CT 循环列表改掉即可，三格式一次全存）。
- **用户说"画一张跟 XX 一样的图"＝复用现有脚本换参数，不新写一套绘图逻辑**（2026-08-29 实测：用户对 Astro/OPC 直接引用 InN_concordance_v2，只改 celltype 循环即可；grep 会话 scripts/ 目录先找已有脚本是第一步）。
- Stacked bar (species × stage × cell composition) + per-individual boxplot (celltype × stage, individual dots overlay, significance in panel header).
- Boxplot shows every individual as a point (not aggregates).
- Color palette is UNDER USER CONFIRMATION — when the user says "调整配色，等我同意，记住这个颜色" → wait for explicit approval, then save the approved hex palette for reuse in later project figures. Do not silently change palette across rounds.
- Human has Unknown class (C13), monkey has VS/ChP — not shared; note in figure legend / analysis scope. Use only shared cell types for the cross-species statistical comparison (6 shared: ExN/InN/Astro/Micro/OPC/ODC).

## 4. 专利结论表交付物（用户要求累积式，2026-08-29）
- 用户在论文阶段主动要求：把当前结论做成**结论表**（`conclusions/专利结论表.md`），每条含：结论（专业措辞，可直引进论文）+ 方法（统计口径：个体单位/检验类型）+ 来源（PMID/DOI/文件路径）。后续新结论**编号续写**（不重排、不覆盖旧条目）。
- 落盘统计源数据：`results/cross_species_trend_stats.csv`（人 40/猴 21 个体的每个细胞类型 ρ/p/Bootstrap CI，逐条可复现）。新增结论前先读该表拿权威数字，**禁止凭对话记忆写数字进结论表**。
- 用户验收标准："专业，并写好对应的方法和来源，干净清晰"——结论表述必须给可引述的英文句子（审稿人可用），同时保留中文解释。