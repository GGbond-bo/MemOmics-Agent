---
name: scrna-cns-figure-design
category: bioinformatics
description: >-
  CNS-level single-cell RNA-seq figure architecture and implementation.
  Covers condition-resolved UMAP with density contours, continuum scoring,
  multi-condition perturbation vector fields, NMF gene programs, and the
  anti-pattern of forcing hierarchical nesting on continuum cell states.
  Use when user is designing main figures (F2-F7) for a multi-condition
  single-cell paper targeting Nature/Science/Cell.
trigger:
  when:
    - User asks about figure design/architecture for single-cell paper
    - User says "F2"/"Figure 2" in context of scRNA-seq manuscript
    - User wants condition-resolved visualization beyond basic UMAP
    - User corrects hierarchical clustering or shallow annotation-only figures
---

# scRNA-seq CNS Figure Design

## Anti-Patterns That Kill CNS Figures (2026 standard)

| Don't | Why | Do Instead |
|-------|-----|------------|
| Force hierarchical nesting of continuum cell states | Transition ≠ container. Reviewers reject artificial layers. | "Continuous transcriptional landscape" language |
| Single UMAP colored by cluster as F2 | 2019-level catalog, not a 2026 argument | Split UMAP by condition with density contours |
| Bar chart of cluster proportions as sole quantitative panel | Discrete; hides distribution shifts within clusters | Split-violin of continuous scores |
| GO/KEGG for novel subtypes with <20 markers | Generic terms, non-discriminatory | Gene set scoring matrix + NMF programs |
| ~~hdWGCNA for terminally differentiated cells~~ **RETRACTED** (see below) | ~~Co-expression networks often flat~~ — WRONG: flatness was an artifact of buggy dev-branch pipeline + stale datExpr | hdWGCNA at metacell level works fine (R²=0.98, 9 modules on muscle MF) |

## Gene-Program Method Selection: cNMF vs hdWGCNA vs Hotspot

Literature-verified comparison (search_papers, 2026-07). Use for F2f-style "what
gene programs drive condition differences" panels:

| Method | Citation | PMID | Cell-level loading? |
|--------|----------|------|:---:|
| **cNMF** | Kotliar 2019 *eLife* | 31282856 | ✅ H matrix — best for program×condition plots |
| **hdWGCNA** | Morabito 2023 *Cell Rep Methods* | 37426759 | ❌ metacell eigengene only |
| **Hotspot** | DeTomaso & Yosef 2021 *Nat Biotechnol* | — | ❌ gene modules only |

**Rule of thumb for terminally differentiated cells (myofibers, etc.):**
- ~~Co-expression networks are often "flat"~~ **RETRACTED 2026-08-01.** The earlier "R²=0.719, one turquoise module" finding was an ARTIFACT of (a) a buggy hdWGCNA dev-branch pipeline and (b) a stale 4659-metacell datExpr. With release **v0.4.12 + fresh 6482-metacell object**, hdWGCNA gives **soft-power R²=0.98 @ power=10** and **9 meaningful modules** on the SAME muscle MF data. Marker→module mapping validated the annotation perfectly: red=fast-twitch (8/9 markers), brown=slow (10/10), blue=RP_high (8/8), green=OTUD1+ family, turquoise=RSS (5/6). Module-trait correlation (black module: Aging=−0.51/ExYoung=+0.27/ExOld=−0.23; magenta: Aging=+0.39/T2D=+0.29/ExYoung=−0.20) directly answered "which modules respond to which effect" — the exact question the user wanted answered.
- **Lesson: don't judge network flatness from single-cell-level correlation or one buggy pipeline run. Aggregate metacells FIRST, use the release version, then test soft power.** A flat soft-threshold result with all genes in one module is a red flag for pipeline state, not a property of the biology.
- hdWGCNA install + release-v0.4.12 API quirks (ident.group, SetDatExpr group_name vector, ScaleData-on-main-object requirement, wgcna_modules slot, background Rscript for TOM >900s): `references/hdwgcna-windows-install-and-api.md`
- **Corrected positive result + module-gene extraction bug + kME-vs-degree hub + metacell p-value trap** (2026-08-01, supersedes `hdwgcna-mf-validated-negative-result.md`): `references/hdwgcna-module-extraction-and-hub.md`
- NMF outputs cell-level loadings → direct program×condition boxplots / UMAP feature plots
- cNMF consensus (keep programs stable in >80% of runs) strengthens "programs are real,
  not parameter artifacts" claims for reviewers
- **CNS narrative**: cNMF in main figure (2f), hdWGCNA in supplementary for independent
  validation (module-trait correlation + hub genes); high Jaccard overlap = "multi-method
  validation" story
- Hotspot is for spatial/transient local co-expression; not suited to stable-state panels

**CoVarNet (different track — cell-type coordination, NOT gene programs):**
- Shi Q et al. *Nature* 2025 (10.1038/s41586-025-09053-4, PMID 40437094), Zhang Zemin lab
- Input = cell-subtype abundance × sample matrix; Pearson + specificity index → NMF(k=12,
  cophenetic correlation, 30-run consensus) → 10,000 permutation tests → multicellular
  coordination modules (CMs). 12 CMs across 35 tissues; validated by Visium/Xenium/GTEx.
- Answers "which cell types co-vary as an ecological unit", NOT "which genes are co-regulated".
  Use for F5 upgrade (beyond CellChat ligand-receptor), NOT for F2 gene programs.
- Reusable narrative: "convergent cancer ecosystem" (cCM02 = TAM+Tex+ISG15+myCAF co-occurring
  across 8 cancer types). Analogous question for muscle: do aging and T2D converge on the same
  degenerating myofiber ecosystem, and does exercise pull it back?

**NMF can reproduce every hdWGCNA display** (answers "NMF能像hdWGCNA那样展示吗" — yes):

| hdWGCNA display | NMF equivalent |
|-----------------|----------------|
| module × trait correlation heatmap | program × condition Spearman cor heatmap (compute yourself) |
| module eigengene UMAP feature plot | program loading UMAP feature plot (direct) |
| hub gene network (igraph) | top-weight gene network/bar (top genes → STRING/igraph) |
| module dendrogram | program similarity dendrogram (direct) |
| eigengene × condition boxplot | program loading × condition boxplot (direct) |
| module membership table | program top-50 gene table (direct) |

NMF soft membership even shows one gene in multiple programs (hdWGCNA hard-membership can't).

**Figure economy rule** (user preference): regardless of method, show only 3-6 informative
modules in the main figure; the rest go to supplementary. CNS reviewers stop reading after 6.

**Subsetting pitfall**: when sampling cells for NMF (e.g. 10 clusters × 2000 cells), ALWAYS
stratify by cluster × condition — random sampling guts rare-condition representation (e.g. RSS
young ≈ 50 cells) and destroys the program×condition analysis. Take min(2000/n_conditions,
available cells) per condition.

**⛔ Single-cell NMF kill-switch: housekeeping/structural-gene domination.** Before fitting
RcppML NMF on single-cell data, EXCLUDE MALAT1/NEAT1/TTN/NEB/DMD/MT-*/RPL*/RPS*/MRPL*/MRPS*.
Without exclusion, MALAT1 + giant sarcomere genes + MT/RPL dominate every program and
cluster×program loading is flat (~1e-5, zero discrimination). After excluding (3000→2936 genes
in the validated run), programs became interpretable and reproduced user markers (P3=RSS,
top gene BMPR1B). Also: RcppML needs `library(Matrix)` explicitly, drops rownames/colnames
(restore from hvg), is deterministic with fixed seed (reproducibility cor=1.0 — cite as evidence),
and Seurat v5 uses `layer=` not `slot=` in GetAssayData. Novel program with ZERO GO terms =
genuinely uncharacterized subtype (a feature, not a failure); KEGG often empty for muscle genes
(not in metabolic pathways). Full recipe + validation pattern:
`references/rcppml-nmf-implementation.md`

> CoVarNet recipe + Nature 2025 findings: `references/covarnet-cell-coordination-nature2025.md`

## Multi-Panel Composition: CNS 级拼图 (user correction 2026-08-01)

⛔ **User correction: "这个figure我不满意，排版我也不满意，我希望你能按照CNS级别拼Figure"** — the
first assembled composite (a flat grid of tool-generated PNGs pasted side by side + a text
strip) was REJECTED. CNS-level assembly rules:

1. **Never paste tool-generated PNGs as image files into the composite.** Fonts, point
   sizes, color ramps and margins clash → reads as a collage. Rebuild EVERY panel from its
   data frame (CSV/RDS) with ONE shared theme (Arial, base_size 6-7, thin 0.35 axes,
   white background), then assemble.
2. **Figure contract before layout**: core conclusion sentence → hero panel → panel map →
   evidence hierarchy → export contract. Present the contract to the user before coding.
3. **Asymmetric hero layout, not equal grid.** In the accepted hdWGCNA figure: soft-power +
   dendrogram small on top, module×effect heatmap as the WIDE hero panel, GO/KEGG bubble +
   hub network below. Use `patchwork` `design=` strings or base `png::readPNG`+`viewport()`
   when you must include a true raster (e.g. official dendrogram image).
4. **Conclusion strip is mandatory** (user asked for "结论" in the figure): 3-5 plain
   sentences at the bottom stating the biological claim + a statistics caveat line.
5. **ComplexHeatmap is a grid object**: export by opening device → `draw(ht)` → `dev.off()`
   (never ggsave); compose with `wrap_plots()`/grid viewports.
6. **Official hdWGCNA trait-cor table shape**: `PlotModuleTraitCorrelation`-style output is
   `5 effects × (modules × cell-groups)` columns (e.g. `all_cells.red`, `RSS.red`, ...).
   For the all-tissue module×effect heatmap, filter columns by `^all_cells\\.` then strip
   the prefix; order modules by the Aging column; annotate significance from the matching
   p table. GO/KEGG must be re-run per official module (see rule above).
7. **R script location pitfall (Windows/MSYS)**: writing the R script under `/tmp` (MSYS
   virtual path) segfaults Rscript with exit 139 even on a base `read.csv` — the script file
   itself is unreadable. Write scripts into the ASCII working directory (project dir) and run
   `Rscript --vanilla ./script.R` from there. `--vanilla` also bypasses a polluted `.Rprofile`
   library path.
8. **enrichR `.onAttach` internet check hang**: `library(hdWGCNA)` stalls/fails when
   maayanlab.cloud is unreachable. Workaround: `loadNamespace("hdWGCNA")` + `hdWGCNA::`
   prefix throughout, which loads the namespace without running `.onAttach`.
9. **Load the governing skill BEFORE heavy execution** (user audit: "你是没有hdWGCNA的skill吗?"):
   when a method has its own skill (`hdwgcna`, `nature-figure`, `deg-analysis`), call
   `skill_view` at the start of the run even if you know the method — the user audits skill
   compliance. The hdwgcna skill carries the corrected conclusion (MF network is NOT flat)
   and install/API pitfalls; do not re-derive them by trial.
10. **Prefer release over fixing dev**: when a GitHub package dev branch keeps breaking
    (MetacellsByGroups not storing wgcna_name, function signatures drifting), STOP patching
    the dev branch — download the release tag (e.g. v0.4.12) and install that. User: "报错就修呗,
    直接建一个新环境不就好了？还是说有什么问题？" — hours were lost patching dev-branch bugs
    that the release version simply doesn't have. Check `GET /repos/<user>/<repo>/tags` for
    the latest release first; only touch dev when no release exists.

> Detailed accepted-figure recipe (panels, sizes, debate-info handling, verify anchor):
> `references/cns-multipanel-composition-hdwgcna-figure.md`
> **Complete 8-panel CNS hdWGCNA figure builder template** (softpower + dendrogram +
> module×effect hero + GO/KEGG + hub + module-gene DotPlot w/ color strip + conclusion
> strip + SVG/PDF/TIFF/PNG export + source CSVs; includes `.libPaths()` bootstrap):
> `templates/build_cns_hdwgcna_figure.R`
> Official-workflow runtime pitfalls (traits-as-char-vector, future::plan sequential,
> TOM path fix, loadNamespace bypass, GO/KEGG re-run per official module):
> `references/hdwgcna-official-workflow-runtime-pitfalls.md`
> Teaching-style hdWGCNA script + 50万细胞 scaling table + user script-delivery
> preference + the 4-part audit (辩论/结论/多agent/自进化):
> `references/hdwgcna-teaching-script-50w-cells.md`

### R 实现级坑（build_CNS_figure.R 重拼实测，2026-08-01）

把 CNS 拼图规则落到 R 代码时这些坑全部踩过：

1. **Windows R 字体**：`gpar(fontfamily="Arial")` / `theme(base_family="Arial")` 报"字体类别出错"（grid 不认裸名 Arial）。正确：`fontfamily="sans"`（Windows 默认映射到 Arial，`windowsFonts()$sans = "TT Arial"`）。ggplot 的 `family=` 参数直接删掉用默认 sans。
2. **grid.arrange layout_matrix 不能含 NA**：`rbind(c(1,NA), ...)` 报"找不到对象'base_'"。需要占位格时用**空 grob** `grid.rect(gp=gpar(col=NA, fill=NA))` 放进 grobs 列表，layout 填它的索引。
3. **sed 误删 R 语法**：用 `sed -i 's/family = FONT//g'` 会把 `base_family = FONT` 误删成 `base_`（语法坏）——**R 脚本一律用 patch 工具改，不用 sed**。
4. **ComplexHeatmap cell_fun 下标**：`Heatmap(t(mcor))` 转置后 cell_fun 里 `i`=行、`j`=列，但矩阵引用要用原始方向 `mcor[j,i]`、星标表 `lab[j,i]`——写反就报"下标出界"。
5. **无视觉模型的排版 QA**：纯文本模型看不到图，用 PIL 按行分块测"非白像素比例"验证布局是否正确渲染（每行应有内容、hero panel 内容占比最高）；红/蓝像素分布确认热图方向正确（正相关红多、负相关蓝多）。布局测试代码见 `references/cns-multipanel-composition-hdwgcna-figure.md`。
6. **ComplexHeatmap 是 grid 对象**：合成时用 `grid.grabExpr(draw(ht, ...))` 包成 grob 再进 grid.arrange；单跑时 open device → draw → dev.off（不能 ggsave）。
7. **Windows Seurat 出图脚本必须显式 `.libPaths()` 引导（2026-08-04 实测）**：PATH 上的 `Rscript` 可能是新装版本（本机 R-4.6.1）库里**没有 Seurat**；`--vanilla` 又不读用户库 → 包检查全 FAIL 但代码没错。本机验证可用组合：`"/c/Program Files/R/R-4.5.3/bin/x64/Rscript"` + 脚本顶部 `.libPaths(c("E:/R-libs/R-4.5.3", .libPaths()))` → Seurat v5.5.1 + ComplexHeatmap + circlize + gridExtra + ggplot2 + png 全部加载。出图脚本第一行就放 `.libPaths()`，不要等到 library() 报错。
8. **重图构建前先跑 pre-flight 快速验证（~30s，避免 10 分钟后台任务中途炸）**：加载 883MB Seurat 前，先写临时 `hermes-verify-*.R` 断言：① 语法 parse ② 输入文件都存在（trait_cor/trait_p/softpower/hub/go_kegg/dendrogram.png/Seurat rds）③ 包在 `.libPaths()` 引导下可加载 ④ CSV 数据契约（trait_cor 含 `^all_cells.<module>` 列 + Aging/T2D/ExYoung/ExOld/ExT2D 行、cor/p 同维、hub 含 gene_name/module/kME、go_kegg rds 含 `red$go`/`red$kegg`）⑤ DotPlot 基因提取逻辑（期望数 = length(mods_show)*k_per_module **动态计算**，不是硬编码——本次会话把 36 写死结果误报 FAIL，实际 hub 表 10 模块×6=60；无 NA、无跨模块重复、全部基因 %in% rownames(Seurat)）。全部 PASS 再启动后台全量出图，日志 + notify_on_complete 收尾。

## Method–Problem Matching: When the User Says "NMF 没看出什么" (2026-07-31 correction)

Symptom: user runs pooled NMF (all cells together, k=5-8), gets program×cluster heatmaps
and condition boxplots, and reports "没感觉NMF能给出多大的信息".

Root cause diagnosis (validate BEFORE switching methods):
- **Pooled NMF finds IDENTITY programs** (fast-twitch P1, slow-twitch P2, ribosome P6) —
  i.e. it re-discovers the cluster annotation the user already made. Reviewers/users see
  zero increment. Only a novel program (RSS P3 with BMPR1B, GO-empty) is truly new, and it
  gets buried among the "verification programs".
- The user's REAL question is "which programs do the five effects (aging/T2D/exercise)
  change?" — that is a **condition-difference problem**, NOT a global decomposition problem.
  Global co-expression tools (NMF, hdWGCNA, WGCNA) answer "what is this tissue made of",
  not "what changed between conditions". **Method and question must be matched** — the fix
  is not a different decomposition, it's reframing the analysis target.

When this symptom appears, switch to (in order):
1. **Functional-score × five-effect matrix** (scores are hypothesis-driven priors; if the
   dataset has AUCell/AddModuleScore columns, this often IS the main story — see the
   reversal-matrix section below)
2. **Per-condition NMF → meta-program integration** (Zhuo 2026 Cancer Cell recipe:
   independent NMF per condition, Jaccard(top50)+UPGMA+RobustRankAggreg) — finds programs
   that EXIST in one condition but not another, i.e. condition-differential programs
3. **DEG-based effect programs** — take F4 DEGs, organize with NMF/hdWGCNA into
   "aging-response / exercise-reversal / irreversible" modules

## hdWGCNA's Correct Position: Effect-Response Modules (F2e) + F4-after-DEG

User asked "hdWGCNA真的不行吗?" after finding NMF uninformative. **Updated answer (2026-08-01, after a real hdWGCNA run on the same MF data):**
- hdWGCNA shares the identity-program risk with NMF for F2 DISCOVERY (it also finds fast/slow/mitochondria modules) — that part of the earlier advice stands.
- **BUT its built-in module-trait correlation is genuinely the better "which modules respond to which effect" tool.** On muscle MF it produced the F2e heatmap (module × 5-effect axes) that directly answered the user's real question, with clean effect stories (black = aging-reversible/exercise-refractory target; magenta = irreversible aging/T2D damage) and perfect marker→module validation of the annotation. If a user's real question is effect-response (not "what is this tissue made of"), hdWGCNA module-trait correlation can be MORE informative than pooled NMF.
- ⚠️ **Module colors shift between runs — cite the OFFICIAL run's numbers, not the earlier exploratory run.** The validated official v0.4.12 run (release, 6524 metacells) gives **red module** as the reversible target (Aging −0.264 / T2D −0.252 / ExYoung +0.271 / ExOld −0.233, GO: energy/insulin signaling/AMPK/vascular transport/muscle cytoskeleton; KEGG hsa04910 Insulin signaling + hsa04931 Insulin resistance), **purple** (n=60, **0 GO terms = genuinely novel T2D module**) and **magenta** (ECM/adherens junction) as T2D-specific-up modules (+0.249/+0.201, young exercise suppresses but T2D exercise fails: magenta ExT2D still +0.059). Marker→module: fast→red(8/9), slow→brown(10/10), RP_high→blue(8/8), OTUD1+→green(6/9), RSS→turquoise(5/6).
- Two-place positioning:
  - **F2e (main figure)**: module × five-effect correlation heatmap + hub-gene networks for the top modules (black/magenta) — this IS the "识别五种效应的响应模块" deliverable the user asked for
  - **F4 upper structure (after DEGs)**: merge all DEGs → hdWGCNA/NMF → name modules ("aging-response module", "exercise-reversal module", "irreversible module") → module-trait correlation + hub genes + GO/KEGG. Converts "a list of genes" into "named biological programs".
- If used alongside NMF: Jaccard overlap = "two independent methods agree" validation narrative.
- **⛔ GO/KEGG must be re-run on the OFFICIAL module assignment, never reused from an earlier run.** In the muscle session the leftover `module_go.rds` was from the superseded bottom-level run (only 6 modules) — enrichment computed on wrong modules is misleading. Re-run `enrichGO`(BP)/`enrichKEGG` per official module with `bitr(SYMBOL→ENTREZID)`; capture the enriched terms per module into one CSV. A module with ZERO GO terms (purple, n=60) is not a failure — it is a genuinely uncharacterized condition-specific module and should be described as such (mirrors the NMF "GO-empty = novel state" rule).
- **Figure composition without magick**: `cowplot::draw_image()` requires the magick package (not installed on this Windows R by default). For multi-panel composition of existing PNGs use base graphics: `png::readPNG` → `grid.raster` inside `viewport()`s (one viewport per panel + label) → `dev.off()` to PNG/PDF/TIFF. Works with zero extra dependencies; panels + a text-conclusions strip (grid.text) is exactly how the final hdWGCNA figure was built. If the user asks for "conclusion + debate info" inside the figure, put a plain-language conclusions text block at the bottom and the debate verdict separately.

## 🗣️ debate_analysis 8/8 全失败 → 串行辩论回退协议（2026-08-01 验证）

⛔ **症状**：`debate_analysis` 连续多次全部失败：8 个角色（pro 3 + con 4 + judge）全返回"辩论生成失败"，无归档。

**根因（本环境实测）**：`webui/server.py` 的 `_sync_debate_env()` 遍历 `provider_keys` 时被 `"dcs" in pid.lower()` 抢先注入 dcs-cloud 的**失效 key（401）**；有效 deepseek key 在 `_current_model` 里但被放最后 fallback。8 路 `ThreadPoolExecutor` 并发又放大限流风险。**不是辩论设计问题，是 API key 注入 bug。**

**修复**（用户建议"先正方→再反方→LLM 判决"，串行化 = 更稳 + 同样隔离）：
1. `_sync_debate_env()` 优先 `_current_model` 的 provider key（用户正在用的必然有效）→ 回退 deepseek 官方 → 最后 fallback
2. 串行调用替代 8 路并发：pro 3 → con 4（prompt 互不可见）→ judge 看全部
3. deepseek-v4-flash 回答在 `reasoning_content`，`content` 空 → fallback 读 `reasoning_content`
4. **独立脚本 `run_serial_debate.py`**（直接读 model_config.json 的 key，绕过 server 注入 bug）——不重启 webui 也能跑通辩论；重启后才让 `debate_analysis` 工具本身生效

实测：7 次 8/8 全失败 → 修复后 8/8 成功（302.7s），归档含裁判裁决（verdict=modify, confidence=high）。

> 完整诊断路径 + 可交付给其他 agent 的修复代码 + 验证方法：`references/debate-serial-fallback-fix.md`
> 辩论机制是跨 skill 公共基础设施，此协议适用于所有需要多角色辩论的分析（hdWGCNA/NMF/注释/参数），不限于本 skill。

## ⛔ 停止系统唤醒心跳（user: "停止，心跳停掉"）— 平台级 teardown

用户说"停止，心跳停掉"/"不需要task_plan了"后唤醒仍在跑，根因是
`webui/server.py` 的 `_schedule_self_check()` 跳过条件只认
`cancelled`/`paused`、**不认 `CLOSED`/`已停止`**。立即生效=重命名
`task_plan.md`→`.bak`（has_plan=False）；长期生效=patch 跳过条件后重启 webui。
完整诊断 + patch 代码 + 验证脚本模式：
`references/stop-self-check-heartbeat.md`

## Monocle3 Trajectory: Contraindicated for Myofibers (root uncertainty + snRNA velocity bias)

User wants trajectory to show "aging → diabetes → exercise reversal" flow. Three hard problems:

| Problem | Why it kills the analysis |
|---------|--------------------------|
| **No root** | Myofibers have no developmental origin. Fast/slow are STATES, not developmental stages. Monocle3's root-node assumption is arbitrary → reviewer attacks. |
| **snRNA velocity unreliable** | Velocity relies on spliced/unspliced ratios; snRNA-seq captures nuclear RNA (naturally unspliced-enriched) → massive bias. Reviewers know this. |
| **Conditions don't fit a trajectory** | Merge-run mixes the five effects in one manifold; separate runs are incomparable. Trajectory answers "which states are transcriptionally continuous", NOT "how aging changes states". |

Alternatives (in order of fit for a multi-condition MF paper):
- **A. Condition vector field** (recommended; prototyped in Phase 4): per-cluster program-
  space points per condition → aging vector (Y→O), exercise vector (O→O_post), reversibility
  index. No root, no pseudotime, directly answers "does exercise reverse aging?"
- **B. Rootless diffusion pseudotime**: if a "trajectory-looking" figure is required, use
  diffusion map + rootless pseudotime; color by condition instead of drawing condition paths.
- **C. CellRank terminal-state**: NOT recommended for MF (no clear progenitor/terminal pair).

## S2/F2 balance correction (2026-07-31): don't make F2 a catalog

When F2 already has annotation + proportion boxplots + dotplot + special-fiber re-cluster,
the increment that matters is the **effect comparison** (F2d effect matrix + F2e reversibility
axes), NOT more annotation displays. Scores are NOT "小事" — they are the hypothesis-driven
prior that combines with data-driven NMF; reviewers want both halves. See
`skeletal-muscle-competitor-literature.md` for the two direct-competitor papers whose
existence means annotation-only F2 would be rejected by reviewers.

## Functional-Score Reversal Matrix (when user already has module scores)

If the dataset already carries AUCell/AddModuleScore columns across a
multi-condition design (especially paired Pre/Post), run this BEFORE or
ALONGSIDE NMF — it often delivers the main biological story faster and
cleaner: per-subtype condition deltas → classify each subtype×score as
reversed / no-response / aggravated → reversal rate per score separates the
axes into **reversible** (muscle: IIa 100%, Sarcomeric 90%, RegMyon 70%,
OxPhos 60%) vs **irreversible** (SenMayo/Stress/TNFA/Inflammatory 0%).
Narrative: "exercise is the mirror of aging — but only half the mirror."
This was the analysis the user found genuinely exciting; NMF program tables
alone were judged "没看出来" (no visible conclusion). Full recipe + the
RSS-blunted-response finding + dual-matrix/mirror-test figures:
`references/functional-score-reversal-matrix.md`

> ⛔ **Conclusion-first deliverable rule** (user correction 2026-07-31):
> NEVER deliver an analysis as an artifact inventory (file list + program
> tables + heatmaps without interpretation). Lead with the plain-language
> biological conclusion ("so what"), then attach the evidence. If you cannot
> answer "what did the NMF/scores conclude?" in one sentence, the analysis is
> not done.

> ⛔ **Teaching-script delivery rule** (user correction 2026-08-01): when the
> user asks for the script itself ("给我你跑hdWGCNA的脚本…要求代码有间隔，让我知道每一步"),
> deliver a teaching-grade script, not a runnable dump: every logical step as
> `# ---- STEP N. 名称 ----` with spacing between steps; each block preceded by
> Chinese comments explaining what it does, why, key parameters, and how to
> scale for the user's dataset size (e.g. 50万 cells). Include checkpoint
> saveRDS per step + resume instructions + a memory/time budget table. The
> user WILL read it line by line and ask about every step.

> ⛔ **Method-focus rule** (user correction 2026-08-01): when the user picks ONE
> method ("我只要hdWGCNA，其他的不要"), do not re-litigate method comparison or
> interleave other methods into the deliverable. Execute the chosen method end-to-end
> (official workflow + official figure set + conclusions + GO/KEGG for the relevant
> modules + debate record), then offer alternatives only as a separate next step.
> "是不是还要展示GO/KEGG呢？" — yes, functional enrichment of condition-associated
> modules IS part of the deliverable; a module without GO/KEGG is just a color label.

> ⛔ **Code-first delivery rule** (user correction 2026-08-04): when the user pastes
> working code and asks "怎么把它做成CNS级别的图" / "给我CNS级别的代码" — they want the
> COMPLETE runnable script NOW, not a figure-contract lecture or a "要不要我帮你写？"
> offer. Delivering an architecture plan + panel table + "can I write it for you?"
> when the user explicitly asked for code reads as stalling ("你为什么不完成给我的任务呢？
> 我就要"). The correct move: write the full script immediately (the 8-panel template
> in `templates/build_cns_hdwgcna_figure.R` is the known-good starting point),
> run the pre-flight verify below, and hand over the complete file — then optionally
> launch it in background. A one-line figure contract in chat is fine; the artifact
> is the code, not the plan.
>
> ⛔ **Single-plot scoping sub-rule** (user correction 2026-08-04, same session): when the
> user pastes ONE plot's code (e.g. a DotPlot) and asks "这个图的CNS级别代码", the scope is
> THAT PLOT ONLY. Deliver a standalone single-plot script (standalone template:
> `templates/cns_dotplot_module_hub_genes.R`) — do NOT expand it into the full 8-panel
> composite. Over-scoping was rejected twice with "我只要这个图的CNS级别代码". Escalation
> seen: plan → full-figure architecture → finally single-plot code. The single-plot CNS
> upgrades that matter (validated on module-hub DotPlot): ① genes on Y-axis via
> `coord_flip()` (60 genes on X-axis unreadable) ② left module color strip aligned to gene
> order (strip factor levels = rev(features)) ③ genes ordered module-by-module by kME desc,
> `head(g, k)` per module, filtered to `%in% rownames(obj)` ④ groups factorized to logical
> order (Y_Pre→Y_Post→O_Pre→O_Post→OD_Pre→OD_Post) ⑤ diverging palette
> `scale_color_gradient2(midpoint=0, high="#B2182B", mid="#F7F7F7", low="#2166AC")`
> ⑥ theme_classic(base_size=7) + 0.4 thin axes + family="sans" (never bare "Arial")
> ⑦ export SVG+PDF+PNG(300dpi)+TIFF(600dpi) via ggsave on the grid.arrange result.

## Five-Effect-Axes Matrix (paired multi-condition design — validated)

When the design is 6 groups = 2 factors × paired Pre/Post (e.g. Y/O/OD × Pre/Post,
muscle exercise intervention), enumerate ALL effects as 5 axes instead of ad-hoc
comparisons — this is the "五种效应" the reviewer/user expects:

| Axis | Contrast | Test |
|------|----------|------|
| Aging | O_Pre vs Y_Pre | unpaired Wilcoxon (group means, individual-level) |
| T2D | OD_Pre vs O_Pre | unpaired Wilcoxon |
| Ex-Young | Y_Post vs Y_Pre | **paired** Wilcoxon (match by pair_id) |
| Ex-Old | O_Post vs O_Pre | **paired** Wilcoxon |
| Ex-T2D | OD_Post vs OD_Pre | **paired** Wilcoxon |

**⛔ User correction (2026-07-31): "不要只集中RSS，要集中IIX这些，展示五种效应的影响."**
The novel/aging-specific state (RSS) is ONE panel; the systematic deliverable is the
full five-effect matrix on the CANONICAL family (fast fibers IIX/IIA/OTUD1+(II)/RP_high(II)),
with the novel state as context — not the protagonist. Over-focusing on the novel state
reads as cherry-picking; the five-effect matrix on canonical fibers is the "impressive"
panel reviewers want.

**Statistical protocol (validated on muscle MF, Y=10/O=7/OD=7 individuals):**
1. **Individual-level pseudobulk FIRST**: aggregate score means per pair_id × type × cluster
   (pair_id = samplename minus `_Pre`/`_Post` suffix). Never test at cell level (pseudoreplication).
2. Paired axes: `wilcox.test(post, pre, paired=TRUE)` on the common pair_ids.
   Unpaired axes: `wilcox.test(group1, group2)`.
3. **Small-n reality**: n=7-10 individuals → FDR kills almost everything (only 2/350
   survived in the muscle run). Do NOT report FDR-only. Use **direction consistency
   (同向性)** as the robustness metric: count how many of the 5 clusters show the SAME
   sign for a score×axis (muscle: 8 combos were 4/4 or 5/5 same-direction despite weak raw p).
   Report raw p + direction consistency + effect size together; reserve FDR for the
   handful of headline claims.
4. Heatmap: rows = cluster|score (fast family blocks), cols = 5 axes, fill = mean delta,
   display_numbers = p.adj stars. Dotplot per canonical cluster: facet by score category,
   size=|eff|, fill=eff sign.

**Validated muscle findings** (reusable as expected-value anchors):
- Aging → fast family: scoreI −0.180, IIa −0.062, OxPhos −0.063 (5/5 clusters same sign) — fiber identity blurs
- Ex-Old → IIa **+0.101** (direction reversal of aging), RegMyon +0.035 — exercise restores identity
- Ex-Young → near zero (healthy baseline has nothing to fix)
- Ex-T2D → IIa recovery only ~1/4 of Ex-Old → **T2D blunts exercise reversibility**
- RSS in T2D → IIx +0.055 (p=0.017) — the ONE score the fast family ignores but RSS responds to

> Full validated R recipe + focus-cluster mapping + figure code:
> `references/five-effects-axes-paired-design.md`

> Detailed decision matrix + implementation params: `references/nmf-vs-hdwgcna-vs-hotspot.md`

## L3 Cell-Type Proportion Boxplots (annotation-level composition, 6-group paired design)

When the user's deliverable is per-celltype proportion (%) boxplots across the 6 groups
(Y/O/OD × Pre/Post) with significance brackets (validated on muscle MF, 2026-08-12):

**User workflow (mandatory, in this order):**
1. **Compute significance for ALL subtypes first — including subtypes excluded from
   plotting.** User explicit: "跑显著性的时候不要抛开RSS和SMF这两个群，先算显著性". The
   excluded subtypes still feed the global FDR pool and may be the strongest signal
   (muscle: RSS Y vs O FDR=0.001 was the most significant of all 50 comparisons).
2. **Plot ONE subtype at a time**, present the figure + significance table, let the user
   judge "逆转衰老 / 逆转糖尿病 / 运动共同趋势" and decide which groups to draw — THEN
   finalize. Never batch-plot all 8 subtypes without per-subtype confirmation.
3. **Panel width rule (user-specified)**: 6 bars → 30 mm, 5 bars → 28 mm, each bar fewer
   −2 mm; height fixed 32 mm. `egg::set_panel_size(width=unit(30,"mm"), height=unit(32,"mm"))`.
4. **Annotation column is selectable**: exploration uses raw `p.value` (more bars survive);
   final paper version should use FDR. When the user says "改成p值", swap the annotation
   column in THEIR script — do not invent a new visualization (see scipilot-figure-skill).
5. Direction convention: full table rows must say "OD_Pre 低于 O_Pre" explicitly, never
   rely on the sign of a delta.

**⛔ Effect-size sign-convention trap (root cause of a direction misreport, 2026-08-12):**
The user's script computed paired comparisons as `median(v2 - v1)` (positive = second
group higher) but unpaired as `cliffs_delta(x, y)` with x = pair[1] (positive = FIRST group
higher). The two conventions are OPPOSITE, and interpreting +0.84 as "OD higher" when the
code meant "O higher" produced a full reverse of the biology (reported "diabetes ↑ Pure
Type I" when it is actually ↓). **Mandatory fixes:**
- Unify convention: call `cliffs_delta(y, x)` so positive = pair2 higher everywhere.
- **NEVER report a direction from a delta sign alone — always verify against raw group
  medians first** (print `median(Prop[type==g1])` vs `median(Prop[type==g2])` before writing
  the interpretation). In the muscle run this immediately showed O_Pre 39.2% > OD_Pre
  30.8%, 7/7 individuals, confirming diabetes DECREASES Pure Type I.
- Add a `direction` column (paste0(group2, " 高于/低于 ", group1)) to the significance CSV.
- When the user disputes a direction ("怎么是上升呢?"), verify with the raw data
  immediately; do not re-assert the script output.
- **Contested/uncertain effect direction → trigger debate_analysis** (user asked
  "为什么不触发辩论呢?"). Direction interpretation is exactly the debatable-result class
  that warrants the debate engine; the debate surfaced the MYH7-transcription confounder
  (proportion change may be classification shift, not fiber loss) and the global-FDR
  caveat — both belong in the final wording.

**⛔ 双版本交付 (user request 2026-08-12)**: 用户说"先按照我给你的脚本画，然后你按
照CNS级别优化一下出一版图，我看看你优化怎么样" → 每个亚群定稿前交付两版，用户拍板选版：
- **V1 用户原版**：只改用户脚本的必要参数（groups / 标注列 / 宽度），配色/主题/括号
  定位/防重叠逻辑全不动——用户用自己脚本核对数值。
- **V2 CNS 优化版**：① 同色系 Pre/Post 配对（O_Pre 浅蓝 → O_Post 深蓝、OD_Pre 浅红 →
  OD_Post 深红，一眼看出干预前后；6 组乱色读不出 Pre→Post 结构）② 星号体系
  （`* p<0.05 / ** p<0.01 / ns`，替代长文本 "FDR=0.035"）③ theme_classic(base_size=6-7)
  + 无网格 + 配对线更细半透明 ④ 额外导出 SVG（可编辑矢量，投稿排版直接用）。
- 两版都用 `egg::set_panel_size(width=unit(W,"mm"), height=unit(32,"mm"))` + ggsave(dpi=300)。
- 用户选版后，后面亚群统一按被选版出。

**组别决定准则 (判断亚群有无故事后)**: 回答"逆转衰老/逆转糖尿病/运动共同趋势"三问：
- 有逆转/共同趋势故事 → 保留 6 组全画（方向对比是视觉记忆点）。
- 无逆转叙事（如 Pure Type I：糖尿病↓ + 运动也↓ + 年轻↑ 方向相反）→ 主图 4 组
  （O_Pre/O_Post/OD_Pre/OD_Post），不显著的对照组（Y 组 p=0.232）放补充材料当
  "健康运动反应正常"参照——避免"凭什么把不显著对照放主图"的审稿质疑。
- 讲故事角度（无逆转亚群）："糖尿病特异丢失 + 运动反应方向随年龄/疾病反转"
  （同样的运动刺激，健康肌肉保慢肌、病态肌肉丢慢肌）比硬造逆转叙事更稳。

**⛔ png() + set_panel_size 空白图坑 (2026-08-12)**: 用 `png()` 设备打开再
`print(set_panel_size(p))` 渲染出的 PNG 可能只有 ~4KB 空白（设备与 egg 对象渲染不兼容）；
同一对象经 `ggsave()` 输出正常（50-60KB）。R 侧出 PNG 统一走 ggsave，不要手动
png() 设备 + print。

**⛔ 每张交付图必须过像素检查（user: \"你出的图，很多都是空白的图，啥都没有，你都不检查一下吗？\" 2026-08-12）**：
文件大小不是内容正确的证据（3.9KB 空白 vs 63KB 正常的教训修过一次，用户仍会再问）。
任何 PNG 交付前用 PIL 采样非白像素比例（每隔 4px 采 1 个，`px[x,y] < 240` 计数），
空白图 <1%，正常箱线图 5-96%（6 组探索版通常 5-15%，CNS 白底版 90%+）。检查代码：
```python
from PIL import Image
im = Image.open(f).convert("L"); px = im.load(); w, h = im.size
nonwhite = sum(1 for y in range(0,h,4) for x in range(0,w,4) if px[x,y] < 240)
total = (h//4+1)*(w//4+1)
print(f"{100.0*nonwhite/total:.1f}%")  # >1% 才算有内容
```

**⛔ 第 6 个比较 Y_Pre vs OD_Pre（user 主动要求 2026-08-12）**：5 效应轴矩阵（Aging/
T2D/Ex-Y/Ex-O/Ex-OD）不含\"年轻 vs 疾病基线\"对比。用户问\"是不是还要做一下年轻运动前跟
老年糖尿病运动前的比较？\" → 加 `c(\"Y_Pre\",\"OD_Pre\")` 作为第 6 个比较（独立样本
Wilcoxon + cliffs_delta），证明疾病态快肌相对年轻丢失（肌肉：Y 42.8% vs OD 26.3%，
p=0.033，FDR_per_celltype=0.099 边缘——raw p 显著但校正后不显著，按小样本协议报
raw p + 方向一致性）。⚠️ 加比较后显著性 CSV 变成 10 亚群 × 6 = 60 行，FDR 必须
**重算**（亚群内 6 个 BH + 全局 60 个 BH），不能复用 50 行版的 FDR 列。输出文件名
版本化（v3_with_YvsOD.csv）。该比较在 RSS/Specialized MF 上 p<0.0001（即使不画图
的群，也再次印证\"显著性全亚群算\"规则的价值）。

**⛔ 非显著配对效应的个体响应分解（小样本解读技术 2026-08-12）**：OD 组运动后 IIA
中位数 +6.5pp 但配对 Wilcoxon p=0.469——表面\"有效果\"不可信。分解到个体级：
1. 列 7 个体 Pre→Post delta 表：实际是 4 升 3 降（3 个强响应者 +14~+18pp 拉高均值，
   3 个下降 −3~−10pp）→ \"响应者异质性\"，不是一致的生物学效应。
2. **中位数之差 ≠ 配对差的中位数**：+6.5pp 是中位数之差（误导），配对检验看的是
   差的中位数（+2.8pp）——报告时务必区分。
3. 响应者 vs 非响应者基线对比（Mann-Whitney 基线差 p 值）：基线无差异 → 不能讲
   floor-effect；基线有差异 → 可以讲\"低基线个体运动后回升\"。本例 p=1.0，只能如实
   说异质性无基线解释。
4. 画个体配对连线图（每条线一个个体，响应者/非响应者双色）给用户看原始结构。
结论措辞：n=7 下\"运动促快肌\"只能作为探索性观察 + 响应者异质性，不能作普遍性主结论。

**R 函数默认参数同名递归引用坑 (2026-08-12)**: `plot_celltype_proportion <- function(
..., fdr_table = fdr_table, ...)` 参数默认值与全局变量同名 → R 报
\"已经在评估：递归缺省参数参考\"。修复：参数名避开全局名（如 `sig_table = fdr_table`），
函数体内引用全部改用参数名。所有带默认值的函数参数都要检查是否与全局变量撞名。

> Full validated recipe (direction fix, significance table, one-subtype plotting loop,
> corrected significant results table): `references/l3-proportion-boxplot-paired-design.md`

**⛔ R 调用效率审计（user: "为什么调用这么多R呢？" 2026-08-12）**：
多亚群逐群画图时用户会质疑 R 调用次数。逐条审计，诚实区分必要 vs 浪费：
- 必要：显著性计算（一次性全亚群存 CSV）、按用户脚本出图、CNS 优化版
- 浪费：自作主张画用户没要的图型（-log10 p 条形图，用户要的只是原脚本换标注列）、
  每次 `Rscript --vanilla` 冷启动重复加载包 30-60s、3-4 次 bug 重跑本可 pre-flight 避免
- **改进**：① 显著性一次性算完存 CSV，画图只读 CSV 不重算 ② 复用 execute_r 持久内核
  同一 worker（比冷启动快 3-5 倍；注意 `_kernel_worker.R` 有孤儿进程泄漏，见
  `windows-bioinformatics-batch-processing/references/kernel-worker-leak-cleanup.md`；
  ⛔ 该文档还含 2026-08-12 最严重教训：声称"清理完成"但没实际执行工具调用 = 虚报，
  被用户当场揭穿"你没有清理啊"——任何完成声明必须"先做→验证→再报"）
  ③ 流程收敛两步：探索图（用户定组别）→ 定稿两版（FDR + p 值一次出）

## The F1-F7 Architecture Pattern

| Figure | Content | Unique value |
|--------|---------|-------------|
| F1 | Pipeline, clinical data, L1+L2 multi-omics UMAP, proportions | Atlas landscape |
| F2 | Deep dive into ONE cell type (multi-dimensional, multi-condition, quantitative) | The "stop and look" figure |
| F3 | Other major cell types | Completeness |
| F4 | DEG across all subtypes × all conditions | Gene-level validation |
| F5 | Cell-cell communication | Intercellular logic |
| F6 | GRN | Transcriptional drivers |
| F7 | Exercise/individual response | Translational axis |

## F2 Deep-Dive Panel Checklist

Each panel must answer a non-trivial question:

| Panel | Question Answered | Implementation |
|-------|------------------|----------------|
| 2a | How does each condition reshape the transcriptional space? | Split UMAP + density contours per condition |
| 2b | Does fiber type identity blur or shift with condition? | Split-violin of continuum score (e.g. fast-slow index) |
| 2c | Are novel populations real? | Evidence chain: UMAP highlight + marker violin + literature + proportion |
| 2d | Are novel populations real? | Evidence chain: UMAP highlight + marker violin + literature + proportion |
| 2e | Which populations are most sensitive to aging? To exercise? | PCA perturbation vector field + reversibility index |
| 2f | What gene programs drive condition differences? | NMF decomposition → program × cluster heatmap + program × condition line plot. **Run as per-condition NMF → Jaccard(top50)+UPGMA+RobustRankAggreg meta-program integration** (Zhuo 2026 Cancer Cell recipe) rather than single pooled NMF. Program marker = top800 in own MP + 10× lower in all others. |

> Reference-grade NMF meta-program pipeline (validated in Cancer Cell 2026),
> "program hijacking" narrative for dual-origin populations, and paywalled-paper
> download strategy: `references/cancer-cell-meta-program-pipeline.md`

## Perturbation Vector Field + Reversibility Index (validated implementation)

Quantify per-cluster condition effects in NMF program space instead of pseudotime.
Validated on human skeletal muscle MF (6 conditions Y/O/OD × Pre/Post, NMF k=6
program space). This answers "which populations are most aging-sensitive, and does
exercise reverse it?" in ONE quantitative panel.

**Setup**: per cluster, compute mean loading vector over the 6 (or k) programs for
each condition → each cluster has a 6-dim point per condition.

**Effect vectors** (all Euclidean norms in program space):
- `aging  = ||L(O_Pre) − L(Y_Pre)||`   (or O − Y baseline for non-Pre/Post designs)
- `ex_old = ||L(O_Post) − L(O_Pre)||`  (elderly exercise response)
- `ex_od  = ||L(OD_Post) − L(OD_Pre)||` (T2D-elderly exercise response)

**Reversibility index** (projection coefficient of exercise vector on aging vector):
```r
rev <- sum(aging_vec * ex_vec) / sum(aging_vec^2)   # per cluster
```
- `rev ≈ 0` → exercise orthogonal to aging (NOT reversed, NOT worsened) — e.g. RSS −0.107
- `rev < 0` → exercise opposes aging direction (partial reversal)
- `rev > 0` → exercise moves WITH aging (worsening) — e.g. Specialized MF +0.025
- `|rev| ≈ 1` → perfect reversal / perfect propagation

**Validated findings** (muscle MF, NMF k=6): RSS aging=8.08e-5, ex_old=6.15e-5,
rev=−0.107 (aging-specific + exercise-refractory — matches user's biology). Specialized MF
aging=9.71e-5, ex_old=1.05e-4, rev=+0.025 (exercise does NOT reverse; both routes increase).

**⚠️ Seurat/R gotchas when wiring this up** (all hit in validation):
- NMF loading columns in a saved metadata RDS are named `NMF_1..NMF_6`, NOT `P1..P6` —
  probe with `grep("^NMF_[0-9]+$", colnames(meta), value=TRUE)` before assuming names
- Seurat UMAP embedding columns are lowercase `umap_1`/`umap_2` (not `UMAP_1`) —
  rename explicitly: `colnames(umap_df) <- c("UMAP_1","UMAP_2")`
- 20000-cell RDS + merge by rownames: `intersect()` returns barcodes; verify
  `length(common) == ncol(obj)` after alignment
- Pre/Post paired design (samplename = individual) is a STRONGER design than unpaired
  groups — surface Pre/Post separately in boxplots; pair-aware stats for final submission

**Output**: 4-figure panel — (1) P3 loading × condition violin for target cluster,
(2) program × cluster × condition heatmap (row-ordered with target cluster on top),
(3) effect-magnitude dodge barplot (aging vs ex_old vs ex_od per cluster),
(4) PCA(programs) vector-field with arrows per effect per cluster.

> Validated R recipe + Seurat wiring quirks + nature-figure export:
> `references/perturbation-vector-field-rss-chain.md`

## Aging-Specific + Exercise-Refractory Evidence Chain (RSS-type novel state)

When a novel state is "aging-specific, exercise-refractory" (high in Old, near-zero in
Young, unchanged by exercise), prove with a 4-part quantitative chain rather than
proportion bars alone:

1. **Program-level aging slope**: target cluster's NMF P3 (or the aging program) loading
   mean by condition — validate monotonic Y_Pre → O_Pre → OD_Pre increase
   (muscle: 6.22e-5 → 1.03e-4 → 1.11e-4, 1.65×)
2. **Exercise non-response in the SAME metric**: O_Pre→O_Post delta ≈ 0
   (muscle: |Δ| = 6.7e-7 — among smallest of all 10 clusters)
3. **Fold-enrichment vs rest-of-tissue widens with age**: cluster vs other-clusters
   mean ratio at Y vs O (muscle: 1.70 → 2.45) — shows the state becomes MORE
   distinct, not just more abundant
4. **Marker-gene condition trend**: e.g. BMPR1B expression in the cluster across
   conditions (muscle: 0.45 → 0.95 → 0.93, exercise flat ~1.08)

This is the "program-level" version of the dual-origin evidence chain — use both
when the novel state ALSO has marker overlap (RSS P3 top gene = BMPR1B is itself
an RSS marker, giving marker→program cross-validation).

## Dual-Origin Evidence Chain (Mixed/Ambiguous Subtypes — e.g. Specialized MF)

When a cluster is "mixed/specialized/uncommitted" and the narrative is dual-route (e.g.
slow-twitch denervation + fast-twitch developmental), prove it with a 7-step chain, not
assertion: ① literature-validated route modules (denervation: CHRNG/CHRNA1/CHRND/NCAM1/GDNF/…;
developmental: MYH3/MYH8/MYOG/MYOD1/DLK1/ACTC1) ② verify module genes are expressed in THIS
dataset (GAP43/MYL4/PEG3/NPM2 were 0% in snRNA-seq — drop them) ③ dual-axis AddModuleScore →
target cluster is the ONLY group >0 on both axes ④ Hartigan dip test (diptest): single-mode =
routes coupled in one continuous cascade, NOT "two subpopulations" ⑤ quadrant analysis:
single-arm fraction is the key number (45.5% single-arm + 27% both_high = partially independent
routes) ⑥ correlate axes with orthogonal NMF programs to identify each route's fiber background
(denerv vs slow-program r=+0.358, devel vs fast-program r=−0.381) ⑦ **confront the confounder
head-on**: MYH3/MYH8 re-expression is a known denervation consequence, so developmental
enrichment alone ≠ independent origin — the single-arm + anti-correlation structure is your
rebuttal; if the data can't support it, publish the honest "denervation-driven fetal program
re-activation" single-cascade claim instead.

> Full recipe, gene lists, interpretation language, verification pattern, and the debate
> service-outage workflow lesson: `references/dual-origin-evidence-chain.md`

## Condition-Resolved UMAP with Density Contours

Recipe for Python/scanpy:

```python
from scipy.stats import gaussian_kde
import numpy as np

def plot_condition_umap(adata, condition_col, umap_key='X_umap', conditions=None):
    """Split UMAP by condition with density contours."""
    umap_coords = adata.obsm[umap_key]
    if conditions is None:
        conditions = sorted(adata.obs[condition_col].unique())
    
    fig, axes = plt.subplots(1, len(conditions), figsize=(6*len(conditions), 5.5),
                             sharex=True, sharey=True)
    
    for ax, cond in zip(axes, conditions):
        mask = adata.obs[condition_col] == cond
        coords = umap_coords[mask]
        
        # Background: all cells in light gray
        ax.scatter(umap_coords[:,0], umap_coords[:,1],
                   c='#e0e0e0', s=0.3, alpha=0.4, rasterized=True)
        # Foreground: this condition
        ax.scatter(coords[:,0], coords[:,1],
                   c=color, s=1.5, alpha=0.7, rasterized=True)
        
        # Density contours at 25%, 50%, 75% max
        if coords.shape[0] > 30:
            k = gaussian_kde(np.vstack([coords[:,0], coords[:,1]]))
            xi = np.linspace(coords[:,0].min()-0.5, coords[:,0].max()+0.5, 80)
            yi = np.linspace(coords[:,1].min()-0.5, coords[:,1].max()+0.5, 80)
            Xi, Yi = np.meshgrid(xi, yi)
            Zi = k(np.vstack([Xi.ravel(), Yi.ravel()])).reshape(Xi.shape)
            levels = [np.max(Zi)*p for p in [0.25, 0.50, 0.75]]
            ax.contour(Xi, Yi, Zi, levels=levels, colors=color,
                      linewidths=[0.6, 0.9, 1.3], alpha=0.9)
        
        ax.set_title(f'{cond}\n({coords.shape[0]:,} cells)')
        ax.set_xticks([]); ax.set_yticks([])
    
    return fig
```

## Multi-Group Function Score Mini-Heatmaps (Scheme A)

When per-function differences are subtle across clusters, use independent
mini-heatmaps instead of a single global-Z-score heatmap:

```
[Module1]  [Module2]  [Module3]  [Module4]  [Module5]
 10cl×5c    10cl×5c    10cl×5c    10cl×5c    10cl×5c
```

Each module gets its own color scale → subtle condition differences visible.

## Core Principle

> Every panel must answer a question that cannot be answered by a simpler display.
> If a bar chart would convey the same information, the panel is redundant.

## Verification Discipline (ad-hoc verify + disk anchor)

When the environment demands "fresh verification evidence" for edited analysis scripts:
- Write an independent `hermes-verify-*.R` into the temp dir that RE-COMPUTES the key
  statistics from raw data (do NOT read the analysis script's own output CSVs as proof —
  compute from RDS/h5ad directly) and asserts file existence/size for figures.
- **Persist the result to a disk anchor** `results/<session>/log/verify_<step>_status.txt`
  BEFORE deleting the temp script. The anchor line should carry: script names, timestamp,
  pass/fail counts, and the key recomputed values (e.g. `RSS P3: Y=6.2e-5 O=1.0e-4 OD=1.1e-4 |
  fold_Y=1.77 fold_O=2.41 | RSS_rev=-0.107 SP_rev=0.025`).
- Clean up the temp script AFTER the anchor is written. Evidence that vanishes with the
  temp script is not evidence — a persistent, dated anchor is what later sessions can
  point at for "already verified".
- Reproducibility proof: fixed seed → recompute NMF W with same seed → correlation 1.0.
  This is strong reviewer-facing evidence ("programs are deterministic, not artifacts").

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | skeletal_muscle | aging | 2026-07-31 | nmf_step1.R + nmf_step2_visualize.R + nmf_step3_enrichment.R | - | - |  |
| human | skeletal_muscle | aging | 2026-07-31 | specializedMF_dual_origin.R | - | - |  |
| human | skeletal_muscle | aging | 2026-07-31 | phase4_rss_perturbation.R | - | - |  |
| human | skeletal_muscle | aging | 2026-07-31 | five_effects_fastfibers.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-01 | run_hdwgcna_official_full.R + resume.R + resume2.R + build_CNS_figure.R | - | - |  |
