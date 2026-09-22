---
name: go-enrichment-visualization
description: >
  Visualize curated GO/KEGG/pathway enrichment results (hand-picked terms with -log10(q))
  as publication-grade heatmaps or dotplots for single-cell / bulk cluster-vs-term figures.
  Covers the sparse-matrix heatmap recipe, truncated color scale for extreme q outliers,
  block-diagonal no-clustering layout, the R-env CSV bridge for ComplexHeatmap, AND
  a proven Python matplotlib fallback for reference-figure style matching and when
  ComplexHeatmap rowname bugs strike. Includes reusable template script.
when_to_use: >
  User has a curated enrichment table (Cluster / GO term / Log(q-value)) and wants a CNS-level
  enrichment heatmap or dotplot. e.g. "把选好的GO富集词条画成CNS级别的热图" or
  "按这个张图的样子绘制热图" (reference-figure style matching), or
  "先把每个亚群的词条和对应的基因列出来，我自己挑" (selection worksheet FIRST — see
  references/term-selection-worksheet.md).
version: 1.1.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    category: Visualization
    tags: [visualization, cns, enrichment, heatmap, dotplot, ComplexHeatmap]
    difficulty: basic
    language: R
---

# GO / pathway enrichment visualization

## When
User hands over a *curated* GO/KEGG enrichment table (terms already hand-picked per
cluster/cell-type) and wants a publication heatmap/dotplot. Typical input `.xlsx` columns:
`Cluster | GO ID | GO term (Path) | Genes | Log(q-value) | ...`
where `Log(q-value)` = `-log10(q)` (negative; magnitude = significance exponent).

## Heatmap recipe (ComplexHeatmap — verified working)
- **Sparse matrix**: `m <- matrix(NA_real_, nrow=length(terms), ncol=length(clusters), dimnames=list(terms, clusters))`
  then `m[cbind(match(term), match(cluster))] <- abs(logq)`. Hand-picked terms are mostly
  cluster-specific → most cells NA. `na_col="#f0f0f0"`.
- **Truncated color scale is mandatory** when `-log10(q)` spans e.g. 1.5→97 (ribosome `translation`).
  A linear scale flattens everything < ~10 to white. Use:
  `colorRamp2(c(0,2,5,10,20,60,100), c("#f7f7f7","#fee0d2","#fc9272","#fb6a4a","#ef3b2c","#cb181d","#67000d"))`
  and cap the legend at `>=60`.
- **No clustering** (rows or cols) when terms are hand-picked and columns carry biological names.
  Order rows by "main cluster" (the cluster with the max value for that term), group via
  `row_split`, sort within each block by `-log10(q)` desc → block-diagonal layout. Columns stay
  in the author's original order.
- Rows = GO term name; gray = "this cluster lacks this term".
- Export `svg` + `pdf` + `png@300dpi` (editable vector text for submission).

## Dotplot note
For enrichment *dotplots* (x=cluster, y=term, size=gene count, color=-log10(q)), the user
prefers a light-red→dark-red ramp; clusterProfiler's 7-step RdBu = `#b2182b → #2166ac`.
When the data is the same hand-picked "each term belongs to one cluster" shape, the block-diagonal
heatmap above is cleaner than a full dotplot grid.

## R environment bridge (reuse existing envs — do NOT reinstall or re-probe)
`ComplexHeatmap`/`circlize` are NOT actually in the main R 4.5.3 (`E:/R-libs/R-4.5.3`) *despite
`environment.json` listing them in key_pkgs*; they live in **R 4.4.2**
(`C:/Users/23136/AppData/Local/R/R-4.4.2/`, ~526 pkgs). R 4.5.3 has `openxlsx`/`svglite`/`ragg`,
R 4.4.2 lacks them. Zero-install bridge:
1. `execute_r` (kernel = R 4.5.3, has `openxlsx`) reads the `.xlsx`, cleans (drop rows where
   col1 == `"Cluster"`, keep rows whose GO ID matches `^GO:`), writes `data/go_heatmap_data.csv`.
2. `terminal` runs R 4.4.2 Rscript (has ComplexHeatmap):
   `"C:/Users/23136/AppData/Local/R/R-4.4.2/bin/x64/Rscript.exe" script.R`
3. Export via **base `grDevices`** `png()`/`pdf()`/`svg()` — these ship with R and do NOT need
   svglite/ragg, so R 4.4.2 emits all three formats despite missing those packages.
   (A `circlize` "built under R 4.4.3" warning is harmless; `null device 1` lines are normal dev.off.)

## Pitfalls
- **Verify the figure is not blank/black** after plotting (the user checks this explicitly).
  Confirm file size > 0 AND labels/color present (via vision_describe/OCR), not just `exit_code == 0`.
- `execute_r` persistent kernel = R 4.5.3 only; R 4.4.2 runs exclusively via `terminal` + Rscript.
- Cleaning the xlsx: the sheet can contain repeated header rows (`Cluster`, `Path ID`, ...) interleaved
  with data — filter on col1 != "Cluster" AND col2 matches `^GO:`.

## ComplexHeatmap rowname trap (CRITICAL)

ComplexHeatmap's `rownames<-` on sparse enrichment matrices is fragile:
- **Symptom**: `错误于dimnames(x) <- dn: 'dimnames'的长度[1]必需与陈列范围相等` — occurs when `paste0`/`make.unique` generates row labels that don't match matrix row count (e.g. after dedup, NA filtering, or index misalignment).
- **Failed fixes**: `make.unique()`, integer index + `right_annotation` with `anno_text` — all failed in the same session.
- **Proven workaround**: Switch to **Python matplotlib** when:
  - Row labels are long (GO term + gene list) and need truncation/formatting
  - User wants iterative style tweaking (reference-figure matching)
  - ComplexHeatmap keeps throwing dimnames errors after 2 attempts
- **Python recipe**: `np.zeros((n_paths, n_clusters))` → `ax.imshow()` → `ax.set_yticklabels([])` + `ax.twinx()` for right-side labels → `fig.colorbar()` at bottom.

## pheatmap user-reference path (2026-09-07 — CRITICAL, user accepted only this)

**When the user says "照着画" / "按参考代码画" and provides pheatmap code, the reference code IS the spec. Follow it EXACTLY — do NOT switch to ComplexHeatmap or matplotlib.** (This session: ComplexHeatmap AND matplotlib iterations were rejected as poor quality; the pheatmap reference path was what the user wanted.)

### Ordering rules (2026-09-08 — user's TOP complaint, MUST follow)
User's exact words: *"你最大的问题是，没有按照亚群的顺序进行排高低，亚群顺序我不是弄好了吗？从左到右，从高到低，共享的词条，优先按照亚群顺序来排列"*

- **Column order = `unique(d$Cluster)` from the xlsx** (the order clusters first appear in the Excel IS the user's pre-arranged left→right / high→low order). NEVER re-sort columns by your own logic (e.g. Type I / IIA / IIX ordering or alphabetical). Just use `clusters <- unique(d$Cluster)`.
- **Row order**: each term is anchored by its *most-front* (leftmost) cluster in that same cluster order. `first_idx <- sapply(terms, function(p) min(cl_idx[d$Cluster[d$Path==p]]))` where `cl_idx <- setNames(seq_along(clusters), clusters)`; then `path_order <- terms[order(first_idx, match(terms, d$Path))]` (ties keep Excel row order). Shared terms (appearing in many clusters) thus sit next to the block of their earliest cluster.

### User's reference code (keep verbatim — 2026-09-08 FINAL accepted version)
```r
library(pheatmap); library(RColorBrewer)
my_colors <- colorRampPalette(c("#FEE9E7", "#FF9999", "#8B0000"))(100)
# 低端是 #FEE9E7 浅粉红(非纯白!) — 用户两轮定稿: 先 #FDE0DD(253,224,221) 2026-09-08,
# 后又要求"再浅一点点,但不能是白色" → #FEE9E7(254,233,231) 2026-09-08 晚, 为现行终版。
# 若用户再提"太浅/不够浅", 在浅粉红区间内微调 RGB(G/B 通道 ±5~10), 永远不要用纯白 #FFFFFF。
pheatmap(m, color = my_colors,
  cluster_rows = FALSE, cluster_cols = FALSE,      # keep author order
  display_numbers = FALSE,                          # NO cell numbers
  fontsize_row = 9, fontsize_col = 10, angle_col = 45,
  border_color = NA,                                # no cell borders
  legend = TRUE,
  legend_breaks = c(0, 5, 10),                      # MUST pair with legend_labels
  legend_labels = c("0","5","10"), legend_title = "-log10 Q")
```
- **低端颜色 = `#FEE9E7`（浅粉红，非纯白）** — 用户 2026-09-08 明确把参考代码低端改为 `#FDE0DD`（"q值的颜色改为 my_colors <- colorRampPalette(c(\"#FDE0DD\", ...))"），当晚又追加"这个颜色再浅一点点，但不能是白色" → 定稿 `#FEE9E7` (RGB 254,233,231)。**下次画图直接用 #FEE9E7**；若用户仍嫌不够浅，在浅粉红区间内微调（G/B +5~10），禁止用 #FFFFFF。
- ⚠️ **legend 刻度陷阱**: 只传 `legend_labels=c("0","5","10")` 不生效 — pheatmap 按数据范围自动画 10/8/6/4/2 刻度（本地 OCR 验证过）。必须同时传 `legend_breaks = c(0, 5, 10)` 才能锁死 0/5/10。
- ⚠️ 不要手动传 `breaks=` 与本 legend 组合 — breaks 会覆盖 legend tick 位置，恢复默认刻度。

### Post-reference amendments (2026-09-08 — user accepted, build ON TOP of reference code, don't rewrite it)
1. **四色配色（用户把 3 色扩成 4 色，中间加鲜红档）**: `colorRampPalette(c("#FEE9E7", "#FF9999", "#FF2E2E", "#8B0000"))(100)` — 浅粉→淡红→**鲜红**→深红。用户原话"在这个颜色上再丰富一点，变成四个颜色，中间加个鲜红"；鲜红档用户接受 `#FF2E2E`。低端永远保留 `#FEE9E7`（非白，若嫌浅微调 G/B +5~10）。
2. **Legend 右下角 + 横放 + 缩短（用户明确要求）**: pheatmap 版 = 关内置 legend（`legend=FALSE`）后手动 `grid` 画 ~4cm 宽横向色条放右下角；ComplexHeatmap 版 = `heatmap_legend_param=list(direction="horizontal", legend_width=unit(4,"cm"), at=c(0,5,10), position="bottom_right")`。验证：OCR 常捕捉不到小刻度文字，需再采样右下角像素确认横向红系渐变条真实存在。
3. **编辑级配色咨询口径（用户问"skill 里有没有更好的颜色搭配"时）**: 期刊标准 GO 热图红系 = ColorBrewer Reds（顺序数据感知均匀+印刷友好+色盲安全）：`c("#F7F7F7","#FEE0D2","#FC9272","#FB6A4A","#EF3B2C","#CB181D","#67000D")`。用户自定义 `#FF2E2E` 饱和度过高（academic-figure-skill 规则 2 "Limit Saturated Color Area"：大块高饱和红=alarmist+印刷渗色）。推荐替换映射：`#FF9999→#FC9272`, `#FF2E2E→#EF3B2C`, `#8B0000→#67000D`；低端仍保留 `#FEE9E7`。给三个候选方案 + 保持现状，推荐方案 A（四色·换鲜红）。
4. **同色系微调不可感知（2026-09-08 晚 · ABC 对比教训）**: 用户要求"自己测试 ABC 版本看看选择"时，若三版只是同一色相内的色阶微调（如 #FF9999 vs #FFC9C9 vs #FF8C8C、鲜红档细微差异），用户反馈"没什么区别啊"——**人眼对同色系内微小色阶差本就不敏感**。给对比方案必须换到**色族/色相层面有质区别**的候选（纯红 vs 黄橙红 vs 黄绿蓝），并一次性给出各方案的编辑点评与推荐，不要在同一色相里贴多档亮度。
5. **非红色系咨询口径（用户放开"不局限于红色"时 · 2026-09-08 晚）**: -log10(q) 是**顺序数据**（0→10 单调，"越显著"）→ 必须用**顺序色板（sequential colormap）**；**发散色板（RdYlBu/RdBu）明确排除**（无正负极，会误导读者以为有上调/下调两极）。推荐序：
   - ⭐ 首选 **YlOrRd（黄→橙→红）**: `c("#FEE8C8","#FDD49E","#FDBB84","#FC8D59","#EF6548","#D7301F","#990000")`。期刊惯例（clusterProfiler/ComplexHeatmap 生态富集图默认方向）、"越热越显著"直觉、色盲安全（红绿色盲仍有亮度梯度）、低端浅黄非白（兼容"不要纯白低端"偏好）。
   - ✅ **已获用户采纳定稿（2026-09-08）**: 出的对比实图里用户选 "D · YlOrRd 黄→橙→红非常不错" → **YlOrRd 成为该项最终配色**。定稿用 5 档版本：pheatmap `colorRampPalette(c("#FFF7EC","#FDD49E","#FC8D59","#D7301F","#7F0000"))(100)`；ComplexHeatmap `colorRamp2(c(0,2.5,5,7.5,10), c("#FFF7EC","#FDD49E","#FC8D59","#D7301F","#7F0000"))`。
   - **配色对比必须出实图，不能只贴色板字符串**（ABC 同色相微调教训的正面应用）：用户认可 YlOrRd 是因为看到了拼好的 `compare_overview` 渲染图，而不是看十六进制色值。
   - 次选 **OrRd**（橙红，更收敛）、**YlGnBu**（冷色系，可选）。
   - ⚠️ **Viridis** 感知均匀+色盲安全，但**低端深紫会让 0 值空白格显眼**——与"0 值格=空白背景"设计冲突，需重设计 0 值格表现再考虑。
   - ❌ **RdYlBu/RdBu 发散色板**：顺序数据禁用。
6. **`angle_col=45` 最左列标签被截断（2026-09-08 晚 · 用户报 "Type IIA 被截断了"）**: 行标签很长（GO 词条名最长 67 字符）+ 画布宽度不足时，pheatmap/ComplexHeatmap 45° 旋转的列名最左端（如 `Pure Type IIA`）会被画布左缘裁掉。**修复 = 加宽 png 画布**：纯词条版 2400→**3800px**、基因右列版 2800→**4200px**（res=300）。ComplexHeatmap 版再显式设 `row_names_max_width = max_text_width(rownames(m), gp=gpar(fontsize=9))`。验证：裁剪左上角列标签区放大 + OCR 确认 `Pure Type IIA` 完整出现（置信 ≥0.9），不要只看整图 OCR——45° 旋转文字整图 OCR 常漏最左列。

### Matrix convention (pheatmap path)
- Values = `abs(logq)` clipped to 0-10: `d$logq_abs <- abs(d$Log); d$logq_clip <- pmin(d$logq_abs, 10)`.
- **Empty cells (term not enriched in that cluster) = 0** → white background (NOT NA + na_col; the reference code starts from a 0-filled matrix and overlays block values). This differs from the ComplexHeatmap path's NA convention.
- Build sparse matrix: `m <- matrix(0, nrow=length(terms), ncol=length(clusters), dimnames=list(terms, clusters))`, fill `m[i, sub$Cluster[j]] <- sub$logq_clip[j]` per term-subset.
- Row labels: two-line `"term\n(gene1, gene2, ...)"` set via `rownames(m)` (pheatmap renders \n fine).

### Gene-selection rule (user requirement — MUST apply)
1. Each term shows **2-3 representative genes**, chosen from **biology knowledge + cluster identity** (e.g. slow fibers MYH7/TNNT1, fast fibers TNNT3/ACTN3/ATP2A1, NMJ CHRNA1/MUSK/LRP4/COLQ, RP_high = EEF2/RPL7A/RPS6/COX7A1, oxidative phosphorylation = COX7A1/ATP5F1E/NDUFB10/CYC1).
2. When the **same term is shared across multiple clusters** (e.g. muscle structure development ×6 clusters, myofibril assembly ×3, supramolecular fiber organization ×3, translation/ribosome biogenesis/ATP biosynthetic ×2), **merge into ONE row** and pick **4 genes** — prefer overlap genes shared by all clusters, else the most representative per fiber type (e.g. myofibril assembly → ACTN2, FLNC, NRAP, CSRP3 all shared).
3. Input for this session: 68 rows / 15 clusters / ~48 unique terms / 337 unique genes; dedupe terms before building matrix; report dims + non-zero % after building.

### Two-version delivery rule (2026-09-08 — user: "基因和词条不要重叠")
When the two-line label `"term\n(genes)"` makes gene text collide with the term in the row label, the user wants **TWO separate versions** (not one compromise):
1. **v-A 基因右列版**: row name = term ONLY (left), genes in a **right annotation column** via ComplexHeatmap `rowAnnotation(Genes = anno_text(genes_vec, gp=gpar(fontsize=8), just="left", location=0))` — genes are physically separate, ZERO overlap. Runs on **R 4.4.2** (`ComplexHeatmap` lives there, not R 4.5.3). Proven in `scripts/go_heatmap_MF_SMF_v3_genes_right.R` (works; earlier "rownames trap" does NOT hit anno_text right-annotation — dimnames error came from setting rownames on the matrix, not from the annotation).
2. **v-B 纯词条版**: row name = term only, NO genes — strictly the user's pheatmap reference code (`scripts/go_heatmap_MF_SMF_v3_words_only.R`, one-shot in execute_r R 4.5.3).
Always deliver BOTH files side by side and tell the user which is which; the genes themselves are unchanged from the approved v2 selection — only layout differs.

### Env note (pheatmap path needs NO CSV bridge)
`pheatmap` + `RColorBrewer` are in **BOTH** R 4.5.3 (`execute_r` kernel, also has `openxlsx`) and R 4.4.2. So the whole pheatmap pipeline runs one-shot inside `execute_r`: read xlsx → build matrix → pheatmap → png/pdf/svg via base grDevices (`png(res=300)` + `pdf()` + `svg()`). Unlike the ComplexHeatmap path, no terminal-Rscript bridge required.

### execute_r gotcha
`execute_r` executes R code — run a saved script with `source("scripts/x.R", encoding="UTF-8")`, NOT Python's `exec(open(...).read())` (that errors with `unexpected symbol`).

## Term/gene selection worksheet — LIST FIRST, let the user pick (2026-09-15 · user-mandated)

**When the input is a *curated* enrichment table and the user has to choose which terms/genes end up in the figure, DO NOT pre-filter or auto-pick "each cluster's top N". Export the FULL candidate list and let the user select.**

User's exact words: *"不一定top2，你先把每个亚群的词条和对应的词条基因列出来，我自己看一看，然后我选给你。画图的大小你来决定，按照美学来。"*

- **Dividing line**: the *user* decides which terms and which genes; the *agent* decides layout + canvas size only.
- Output a per-cluster worksheet, grouped under each cluster heading, **in the cluster order already present in the xlsx**:
  `| 词条 | -log10q | 共享 | 基因(完整池) |`
- **Mark cross-cluster shared terms** (present in ≥2 clusters) in a `共享` column — those rows must be merged and get 4 genes instead of 2-3. Append a *shared-terms summary* table (term → #clusters → which clusters).
- **Do NOT truncate the gene pool at this stage** — list every gene so the user can see the candidates (even 60+ ribosomal genes). Truncating to "representative 2-3" is the *post-selection* figure step, not the worksheet step.
- Report dims / non-zero % **after** the user picks, not before.
- This **supersedes the auto-filter instinct** for this task class: P5's density filter is for *uncurated* matrices. Once the user has curated, listing everything for selection wins.

Ready-to-run R snippet (one-shot in `execute_r`): `references/term-selection-worksheet.md`.

### Aesthetic canvas sizing (rows drive height; width is locked)
User: *"亚群只有15个，词条却是有几十个。所以肯定是偏长的形状"* / *"长和宽要协调"* / *"画图的大小你来决定，按照美学来"*.

| 参数 | 取值 | 理由 |
|---|---|---|
| 单元格 | **0.36 in 宽 × 0.28 in 高** | 宽>高的扁格子，期刊热图惯例，不方头方脑 |
| 绘图区宽 | clusters × 0.36 in（15 亚群 → 5.4 in） | 格子不被拉宽变形 |
| 绘图区高 | **rows × 0.28 in** | 行数驱动高度 → 自然形成竖长比例 |
| 行名区 | 3.6 in（term + 括号基因） | 最长行名约 60 字符，留足不挤压 |
| 列名区 | 45° 斜排 + 1.1 in | 延续 `angle_col=45` |
| 图例 | 右下角横放短条，0/5/10 | 用户定稿 |
| **总尺寸** | ≈ **7.5 in 宽 × (rows×0.28 + 2.2) in 高** | 24 行 → 7.5×8.9 in（竖长 ✓）；15 行 → 7.5×6.4 in（近方，可接受） |

Row-count math: 每亚群 2 条 → 30 行；13 个共享词条合并后 → **~21-24 行**（正好落在竖长甜区）。
渲染画布（`png(res=300)`）必须 ≥ 该英寸尺寸 ×300，且 **≥3800px 宽**以防 45° 列名截断（见上第 6 条）。

## Narrow-body / wide-label handoff mode (2026-09-15 · Illustrator-editable delivery)

User: *"先不挑选，就先按照当前全部词条出，只不过在 v6 的基础上，把图形变窄，让词条有更多的空间，我自己会放到 Adope illustrator 里去调整的"*

- **No term filtering at all** when the user says 先不挑选 — plot every row of the curated table. Do NOT apply the P5 density filter or a "top-N per cluster" cut. (The worksheet rule above still governs when the user has *not* decided yet.)
- **"图形变窄" = 收窄热图本体，不是收窄画布**: lock the physical cell size and let the row-label area keep its full natural width. Target: row-label area ≥ 1.5× body width. Verified good render: 15 cols × 11 pt ≈ **5.8 cm body** vs **8.8 cm label area** (labels ≈ 53% of canvas, cells 0.53 cm).
- Ship `.svg` (primary) + `.pdf` (vector) + `.png@300dpi` (preview) — the user hand-edits the SVG in Illustrator, so never flatten/rasterise it.
  ⚠️ **But base R `svg()` does NOT emit live text — it outlines glyphs.** See "svg() outlines text" below; use `svglite::svglite()` if the user needs double-click-editable text.

### 画布加宽 + 左边距：用 `gtable_add_padding`，别再靠猜画布宽度（2026-09-15 v11）

> ⚠️ **尺寸部分已被下文「🔴 零裁切画布反推（v12b）」取代**：v11 靠"加大画布 + padding 兜底"不能证明零裁切——v12 实测内容左右各被裁 ≈0.4 cm。padding 思路保留（它是对的），但**画布尺寸必须来自测量而非估计**（锁死 `cellwidth/cellheight`(pt) → null 设备内 `convertWidth(sum(gt$widths))` → 反推）。下方段落作为历史沿革保留。
用户亲手在 Illustrator 调图时会连续微调两三版（v9 太窄 → v10 加宽到 9 in → v11 还要再宽 + 左边距调大 + `Pure Type IIA` 仍被截断）。**只加大画布治不住**——45° 长列名截断的根因是内容溢出**设备画布边界**；`gtable_add_padding` 从结构上留出四周空白，比反复加宽画布可控得多：

```r
draw <- function(){
  p  <- pheatmap(m, color=cols, cluster_rows=FALSE, cluster_cols=FALSE,
                 display_numbers=FALSE, fontsize_row=8, fontsize_col=9,
                 angle_col=45, border_color=NA, legend=FALSE, main="",
                 silent=TRUE)                      # silent=TRUE 才返回 gtable
  gt <- gtable_add_padding(p$gtable, unit(c(0.5, 0.9, 0.35, 1.8), "cm"))  # 上/右/下/左
  grid.newpage(); grid.draw(gt)
  make_legend()                                    # 自绘 legend 在 padding 之后画
}
```

- padding 顺序 = **c(top, right, bottom, left)**；左边距要最大（45° 列名向左上延伸），终版 **1.8 cm**。需 `library(gtable)`（R 4.5.3 已装，`installed.packages()` 可查）。
- 自绘 legend 用 npc viewport 定位，在 padding 之外，不受影响。
- **终版尺寸：Wi = 10.5 in × Hi = 11.5 in**（v10 是 9×11）→ 300dpi = 3150×3450 px；行名 8pt / 列名 9pt / 全部 48 词条。
- 完整可跑版：`templates/go_heatmap_cns_handoff_pheatmap.R`。

### 验证列名是否被截断（OCR 不可用 / SVG 文字已转曲时）
`vision_describe` 的 OCR 引擎会不可用，SVG 文字又是路径 → **不要靠反复跑 vision**。用一次像素扫描定论：

```python
nb = (np.array(Image.open(png).convert("RGB")) < 245).any(axis=2)
firstx = np.array([np.argmax(nb[y]) if nb[y].any() else W for y in range(H)])
# 判据：列名区(top 25%)左边缘 0 非白像素 + 行名区 first_x 全局统一 → 不截断
```
v11 实测：列名区左边缘 0 非白像素、行名区左边界统一 x=73px（0.62 cm）→ 不截断。注意**左边缘 <15px 的残留像素若集中在图像最底部，那是右下角 legend 的刻度字，不是列名**——别误判成截断。

### ⚠️ 验证预算：图定稿后最多核 3 项，然后交付
本类任务极易陷入"反复测量"循环（系统会判定循环失控并强制中断）。图生成后**只核 3 项**：① 三格式文件大小非零 ② 内容占比 >30%（非空白，见上文 probe）③ 列名区左边缘无贴边。三项过了立刻汇报交付，不要再跑第二轮 vision / 像素分析。

### 🔴 pheatmap `cellwidth`/`cellheight` are POINTS, not cm (cost a whole broken round)
`pheatmap(cellwidth = 0.38, cellheight = 0.45)` is read as **0.38 pt / 0.45 pt** → the body collapses to a dot: the PNG measured **1.4% non-background pixels / 98.6% empty white** while R exited 0.

| 目标物理尺寸 | 传入值 |
|---|---|
| 0.39 cm 列宽 | `cellwidth = 11` (pt) |
| 0.46 cm 行高 | `cellheight = 13` (pt) |
| 换算 | **cm × 28.35 = pt** |

Heuristic: if you typed a decimal below ~2 for cell size, you meant cm — multiply by 28.35. Sanity-check after render that the measured body ≈ `ncol × CW / 28.35` cm.

### Canvas width from the real label width (no guessing)
```r
lab_w_cm <- (max(strwidth(rownames(m), units = "inches", cex = 8/12)) + 0.12) * 2.54
W_cm <- lab_w_cm + ncol(m) * CW / 28.35 + 1.5   # slack for 45° col labels + legend
H_cm <- nrow(m) * CH / 28.35 + 3.4
```
`strwidth(units = "cm")` errors `invalid units` on a null device — use `units="inches"` then convert.

### 3-format export: run it in an independent Rscript, then verify non-blank NUMERICALLY
Opening `png()` + `pdf()` + `svg()` inside one `execute_r` call produced a **100% white PNG** (device state carried over in the persistent kernel). Export the trio from a standalone process instead — `terminal` → `"C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe" script.R`, or `subprocess.run` inside `execute_python`. Then measure, don't trust the exit code:

```python
bg = most_common_colour(png)          # modal colour
share = (pixels != bg).mean()         # non-background ratio
# <0.05 -> broken/blank (v7 1.4%, v8 0.0%)   >0.30 -> healthy (v9 47.8%)
```
Full working script skeleton + measurement probe: `references/pheatmap-sizing-and-export.md`.

## 🔴 零裁切画布反推（2026-09-15 v12b 终版 · 根治内容左右被裁）

**裁切的真正根因不是「画布不够宽」，而是 `cellwidth` 未指定时 pheatmap 把矩阵宽度按设备 npc 比例缩放** → gtable 总宽不可预测；内容一旦超过设备，`grid.draw` 默认居中 → **溢出部分左右各裁一半**。实测 v12：内容 17.78 cm + 边距 4.6 cm = 22.38 cm vs 画布 21.59 cm（8.5 in）→ 左右各裁 ≈0.4 cm；像素证据 = x=0 与 x=W-1 **都有内容贴边**。只加宽画布治不住（矩阵会跟着变宽）。

**正确顺序（锁死几何 → 量 → 反推画布 → 导出）**：
1. **锁死格子物理尺寸**（单位 pt！`cm × 28.35`）：`cellwidth = 24.66`（0.87 cm/格）、`cellheight = 9`（0.32 cm/行）。
2. **在 null 设备里量内容真实尺寸**：
```r
pdf(NULL); gt <- build()                                   # build() = pheatmap(silent=TRUE) + gtable_add_padding
tot_w <- convertWidth(sum(gt$widths),   "cm", valueOnly = TRUE)
tot_h <- convertHeight(sum(gt$heights), "cm", valueOnly = TRUE)
dev.off()
Wi <- (tot_w + 0.20)/2.54; Hi <- (tot_h + 0.20)/2.54        # +0.2 cm 缓冲
```
3. **用算出的 Wi/Hi 开设备**导出 png/pdf/svg。
4. **一次性像素验证零裁切**：`scripts/verify_figure_no_clip.py <png>`（判据：四边留白 > 0 px + 内容占比 > 30%）。

⚠️ **第 2 步必须包在 `pdf(NULL) … dev.off()` 内**：直接在无设备上下文里跑 `build()`/`convertWidth()` 会留下隐式设备，把随后开的 `png()` 吞成**全白**（v12b 首跑：PNG 8818 B、`extrema=(255,255)` 全白，而 SVG 321 KB 正常）。此症状**在独立 Rscript 进程内同样会发生**——「换独立进程」不是它的解，null 设备包裹才是。判据：PNG `extrema=(255,255)` = 全白坏图。

**终版参数（用户 2026-09-15 认可「V12就可以，但是把左右边距再调大一点，确认所有词条被容纳」）**：
`cellwidth=24.66` / `cellheight=9` / `PAD(上右下左) = c(1.2, 3.5, 2.0, 4.5) cm` → 画布 **11.92 × 8.33 in**（3576×2500 px @300dpi），左 4.5 / 右 3.5 cm 边距，48 词条 × 15 亚群零裁切。

**最小增量原则**：用户说「Vxx 就可以，但是把 X 调一下」时，**只 patch 那一个参数重跑**，不要借机重设计配色/布局/字号（本会话用户已明确\"V12 就可以\"）。交付只报「改了什么 + 新文件路径」，不要重述全部规格。

完整配方（含诊断阶梯、pixel 探针、PNG mode P 坑）：`references/pheatmap-noclip-canvas-geometry.md`。

### 🔴 「只调边距、其他不变」= 本体与边距必须解耦（2026-09-15 v13 · 用户严格约束，第二次为此发火）

用户原话：*"你写代码的时候，不能把热图大小固定吗？边距是边距，怎么把热图本体也变大了？我要的是热图按照12的来，左右边距调节一下，这代码不是很好写的吗？"*

→ **布局参数耦合是这个用户的高频雷区**：加宽画布时若热图本体跟着变宽，会被直接斥为"没把大小固定"。**任何"只改边距 / 只改宽度 / 按 Vxx 来"的请求，动手前先自问：这次改动会不会联动改变本体尺寸？**

两条实现路径，按用户措辞选（不要擅自升级方案）：

| 路径 | 何时用 | 做法 | 代价 |
|---|---|---|---|
| **A. Δ画布宽 = Δ左右边距**（最贴合"照这个代码来，其他不变"） | 用户要保留原脚本的 pheatmap 调用（`cellwidth` 未指定 → 本体是 **null 单位**，随设备宽解算） | `body = W_dev − 行名区 − padding` ⇒ **画布宽增量必须恰好等于左右边距增量**，本体像素级不变 | 本体仍由设备宽解算，跨格式/字体度量可能微漂 |
| **B. 锁死 `cellwidth`(pt) + 反推画布**（几何绝对可控） | 用户要绝对可控，或已出现过裁切 | 见上节：`cellwidth = cm×28.35` + `pdf(NULL)` 内量尺反推画布 | 改动了原脚本的调用——用户若说"其他不变"，先说明再改 |

**路径 A 实例（v13，已交付）**：v12 = 画布 8.5×11.5 in、`PAD(上右下左)=c(1.0,1.8,1.8,2.8)` cm。用户要左右边距加大 ⇒ `PAD=c(1.0,4.0,1.8,5.0)`（+4.4 cm）、画布宽 `8.5 + 4.4/2.54 = **10.23 in**`；高度、配色、字号、行序、图例、`angle_col` **逐字不动**（同一个 R 脚本只 patch 两行）。
公式：`Wi_new = Wi_old + (Δleft + Δright) / 2.54`（in）；同理 `Hi_new = Hi_old + (Δtop + Δbottom)/2.54`。

**⚠️ 验证诚实性铁律（本轮教训）**：像素掩码**不总能**识别热图本体——透明/调色板 PNG、YlOrRd 低端近白（`#FFF7EC`）都会让掩码把整幅判成内容（v12/v13 两版都测出"本体=整幅画布"，数字自相矛盾）。**测量方法本身不可信时，禁止用它的数字宣称"已验证"**：要么改结构化测量（`pdf(NULL)` 内 `convertWidth(sum(gt$widths))` → 一次定论），要么如实汇报"数学推导成立、像素未实测，请你在 Illustrator 里定夺"。**谎报"已验证"比承认未验证严重得多。**

细节、实测数字与降级脚本回退法：`references/pheatmap-margin-only-adjustment.md`。

## Reference-figure style matching workflow

When user provides a reference image ("按这个张图的样子绘制"):
1. **Analyze with `vision_describe`** — extract: label position (left/right/top), color scheme, aspect ratio, font size, grid lines, value annotations, legend position.
2. **Style comparison table** — create markdown table: Feature | Reference | Current | Need fix?
3. **Implement in Python matplotlib** (not ComplexHeatmap) — faster iteration, no rowname traps.
4. **Iterate** — user often wants 2-3 rounds of refinement; keep prior versions (`_v2`, `_v3`).

### 反向移植：用户拿 Python 脚本要 R 版（"颜色这些都要对的上"）

当用户给的是一个**已经跑通的 matplotlib 脚本**（`ax.add_patch(Rectangle(...))` 拼格子 +
`TwoSlopeNorm` + `plt.cm.RdBu_r` + 手动 `subplots_adjust`）并说「**能不能把这个脚本变成 R**」——
这不是重新设计图，是**逐格复刻**：选 base graphics（不是 ggplot2）、`par(xaxs="i")` 防 4% 外扩、
`subplots_adjust` → `par(mai)` 英寸换算、`cex = pt/9`、手写 11 锚点 256 级 LUT（取色索引要 +1）、
`par(fig=..., new=TRUE)` 放色标，交付前必须做**矩阵逐格比对 + 像素颜色直方图**两道验证。

⛔ **动手前先 `search_files` 扫一遍会话 `scripts/`**——本轮用户问这句话时 R 版其实已经写好了（差点重复劳动）。
完整配方（实测数字 + 跨语言模板陷阱 + QA 证据写法）：`references/matplotlib-to-base-r-port.md`。

### 分组色条 = 分类声明：交付必须附「分组依据」（2026-09-15 · 用户追问「每个基因集的分类是什么依据？」）

图上只要出现**分组色条 / 类别标签 / 基因集分块**，读者（和用户）第一个问题必然是「**这个分类依据是什么**」。三种来源必须在图注/说明里写明是哪一级：**L1 外部标准**（MSigDB Hallmark / GO / Reactome 官方集）· **L2 数据驱动**（聚类/共表达模块）· **L3 展示分组**（作者按功能轴人工归组，如脚本里的 `PROG_GROUPS`）。⛔ 最常见失分点 = **把 L3 当 L1 呈现**（读者默认它是数据库分类）。

- 交付四件套：**成员清单（逐条列名）+ 分组判据（一句说清什么轴）+ 每个成员的来源（PMID/DOI 或标自建）+ 来源缺失时明写并给回填路径**。
- 打分/富集矩阵 CSV **只带数值列、不含基因成员** → **禁止凭记忆重建基因列表或基因数**；数字一律回原始来源查证（`search_papers` 取 PMID/DOI），与本项目「数字必须可溯源」要求一致。
- 组色条放行标签外侧、同组成员连续成块；组色用定性色板，与热图的连续发散/顺序色标明确区分（色条=分类，色块=数值）。
- 可复用实例（18 程序 → 5 组 + Identity 的分法与引文，含 SenMayo PMID 35974106 / MSigDB Hallmark PMID 26771021）：`references/grouped-heatmap-grouping-provenance.md`。
- **🔴 深挖版（2026-09-15 · 用户要求「用生物知识分类，让我有理由」）——只讲机制不够，必须给数据理由**：辩论裁判会直接索要**基因集间 Jaccard 重叠矩阵**（实测裁决 `need_more_info`，missing 第一条就是它）。三步必做：
  1. **先审表**：逐集基因数与源表对照。派生「CLEAN 版」会**静默截断**——实测 `pathway_score_CLEAN_v2.xlsx` 有 10/22 个签名被砍到恰好 23 个基因（原始 44–200），共丢 744 基因，下游打分完全看不出来。识破信号 = 多个集基因数**恰好相同** + 截断停在**字母序中途**。
  2. **再验分类**：算两两 Jaccard，报**轴内均值 vs 轴间均值**（实测 0.0424 vs 0.0064，差 6.6 倍 = 分类成立）+ 对 `1−J` 做层次聚类看是否复现拟分类的轴。
  3. **交付附边界说明**：跨轴弱配对（0.07 量级）≠ 分错，是真实通路串扰；某集与所有集 J<0.05 时归轴属**调控归属**而非基因重叠归属，必须写明。
  配方（含损坏 xlsx 的 zip/XML 兜底读法、合并单元格 Class 列填充、22 签名溯源表、6 功能轴机制理由 + 实测 Jaccard）：`references/geneset-provenance-and-axis-classification.md`。
- ⚠️ **引文核对**：不要拿自己检索到的 PMID 去"纠正"用户原表——同一作者同主题常有多篇（Machado 2021 有 33609440 原始出处 + 34074577 方法学评论）。以原表 annotation 为准，检索到的作并列补充。

### 图上标签可读性 / 格中心对齐 / 转置（2026-09-15 · 用户三连返工，逐条照做即免返工）

| 用户原话 | ❌ 错误反应 | ✅ 正确动作 |
|---|---|---|
| "label 变小一点啊，**这么长干什么**？" | 只降字号 | **先缩短显示名，再降 pt**：剥冗余前缀（`scoreOxPhos`→`OxPhos`）、长名规范化缩写（`FattyAcidMetabolism`→`Fatty acid metab.`）。只缩字号 = 字变小但依旧又长又挤——**用户嫌的是"长"，不是"大"** |
| "标签**对齐自己的热图**啊" | 去挪标签距离 / 加偏移 | 让标签锚在**它自己那一格的中心**（`x0 + ci + 0.5`），不是格边界（`x0 + ci`）；45° 长标签用 `adj=c(1,1)`，水平短标签用 `axis(2, at=行中心, las=1)`。45° 标签"没对齐"的观感多半就是锚点取错 |
| "亚群在 y 轴、基因集在 X 轴"（转置） | 只把绘制循环顺序换一下 | 转置必须**三件一起改**：① **数值矩阵不重算**——同一个行内 z 矩阵，只调换取值下标（口径一致优先）；② **分组色条跟着搬**——左竖条 → 顶部横条，组名改横排居中于该组跨度；③ **重算画布几何**——列数/行数一变原 `figsize` 必错：`W = 列数×U + 左右边距`、`H = 行数×U + 上下边距`，**同一 `U`（每数据单位英寸数）才保色块正方形** |

### 🔴 行标签必须「贴着热图」+ 分类名黑色（2026-09-19 · 用户两项硬要求）

用户原话：*"label要贴着热图啊，然后分类的名字换成黑色字体。"*

| 要求 | ❌ 错误反应 | ✅ 正确动作 |
|---|---|---|
| 「label 要贴着热图」 | 以为标签已右对齐就没事 —— v4 实测标签右端距热图**仍留 20–23 px（0.07 in）白缝**，右对齐 ≠ 贴合 | 收紧**标签锚点常量** `LBLX`（−0.10 → **−0.04 数据单位** = 0.010 in = 3 px @300dpi），不要去调字号/边距/画布。判据 = **视觉无白缝**（0.25 mm 已被接受） |
| 「分类的名字换成黑色」 | 保留"轴名 = 轴色"的配色惯例 | 轴名 `col = ax$color` → **`COL_TXT` (#1A1A1A) 黑**；色块本身保留轴色（分类信息由色块承载，文字不必再染色）。顺手把竖排轴名 x 由 −4.30 移到 **−4.27** 紧贴色块 |

**这是本图族（base-graphics 转置矩阵热图）的长期版式偏好**：换数据重画时直接照做，
不要退回「轴名用轴色 / 标签留白缝」的默认；汇报用「你要的 → 我的落地 → 核验证据」三列表。

**🔴 45° 标签被静默裁切 = 出图后必查项**：长标签 + `adj=c(1,1)` 超出画布底部会被无声切掉——**图不报错、文件大小正常、扫一眼看不出**。实测本会话老版 FigA3：10 个亚群只渲染出 8 个（`RSS` / `Specialized MF` 已被切掉）。
- **核验动作**：`vision_describe` 读 PNG → **OCR 文本条数 ≥ 预期标签数**（本例应 ≥10 亚群 + 18 基因集）；**少任何一个即裁切**，回去加下边距。
- **下边距反推**（优于"试着加 0.5 in"）：`最长标签字符数 × 0.55 × pt / 72 × sin(45°)` + 0.1 in 余量；加完仍需 OCR 复核一次。

**🔑 用户问"图里的分类对不对？"时，先 diff 两处常量再回答**：图上的分组来自**脚本里的分组常量**（如 `PROG_GROUPS`），与交付给用户的分类文档（原表 `Class` 列 / 机制轴表）常是**两套不同体系**。先 diff 再说，别顺着现有图解释分类——那等于替一张过期的图辩护。

**技术伪影 / QC 组（如解离应激 Stress index，PMID 34074577）——先隔离，但用户最终裁决是「从图上删掉」**：L2 辩论（8 角色）双方 + 裁判的共识是"**不应与生物学程序等权展示**" ⇒ **过渡方案** = 单列一组 + 该组之后的间隙调大（实测 0.25 → 0.7 数据单位）做视觉分离，而不是只靠颜色不同。
⚠️ **2026-09-15 更新（本 skill 旧版只写了"隔离"，已被用户推翻，别再照旧版保留伪影轴）**：用户看到隔离版后直接下令 **「Stress index 这个不要了，重新画，应该很快吧」** —— **诊断性用"单列"表达，最终交付用"删除"表达**。**用户裁决 > 辩论共识 > 你的设计直觉**：删除后不要再拿"辩论说要保留"把它加回来（在脚本注释里留一行"依据：用户 2026-09-15 决定移除"即可）。
**删除任一成员 = 四件套一起改**（只改前两处必报错、只改后两处留残余）：① `PROGRAM` 向量去掉该项（18→17）；② `AXES` 删掉整个轴对象（6→5，否则 `stopifnot(setequal(gene_order, PROGRAM))` 中断）；③ `DISP` 删掉显示名；④ `GAPX_AFTER` 之类"隔离专用间隙"一并删（已无被隔离对象，留着就是无意义空白）。⑤ 脚本结尾的 `cat(..., "| X 是否已移除:", !("X" %in% PROGRAM))` 一起加，让"删干净"成为可验证 stdout。
✅ **画布尺寸不要手改**：`U` 是常量时 `W = 列数×U + 边距` 自动收窄且**色块保持正方形**（实测 18→17 列：9.60 → 9.39 in，恰好少一个 `U=0.42`，无拉伸）。只有当画布是手填常数时才会变形——先改成推导式再删。

📄 完整配方（base R 零依赖矩阵热图骨架、缩短显示名的 DISP 映射写法、格中心对齐代码、45° 裁切的下边距反推公式、转置三件套、画布几何推导）：`references/matrix-heatmap-labels-and-transpose.md`。
📄 **增删成员/分组轴的最小编辑协议（四件套 + 画布自解 + OCR 正负向核验 + 两处落盘交付 + 速度期望）**：`references/matrix-heatmap-add-remove-members.md`。
📄 **🔴 绘制顺序静默裁切 + `axis(2)` 半格偏移 + 三层核验链（base R 零依赖路径必读）**：`references/base-graphics-draw-order-and-layer-verification.md`（一键核验：`scripts/verify_figure_layers.py`）。
📄 **🔴 外侧装饰（分类色块 / 竖排轴名 / 标题）几何 + 「标题不与顶部标签重叠」两层布局 + 文字宽度自检 + 迭代改图纪律**：`references/r-base-graphics-outer-layout.md`。
📄 **🔴 栅格级版式取证（"标签贴没贴着热图 / 有没有对齐 / 其他元素动没动"）—— 列剖面、深色格污染排除、对齐方向判定、脚本内自检符号坑、实测基线表**：`references/raster-layout-measurement-forensics.md`。

### 🔴 迭代改图纪律（vN 脚本 + 像素级"没动"证据 + 一次核验即止）

- **每次改图新建 vN 脚本**（如 `fig_A3_CNS_v4.R`），旧版连同 4 种格式一起 copy 到 `archive_superseded/`（带版本后缀），**不覆盖、不删除**上一版。
- **用户说"其他不变"时必须给像素级证据**，不能只说"没动"：逐列色值多重集一致 = 纯置换（实测 18/18 列一致、逐行值不变仅位置移动）；删除元素用**颜色命中数反向验证**（左侧色条 5115/5104/2542 px → 0/0/0 px）。
- **交付前 `vision_describe` 核验成图 PNG**（行/列顺序、是否在画布内、新增或删除元素是否生效）——OCR 是发现「标题被裁、标签重叠、元素没删干净」的**唯一手段**，光读脚本看不出来（本会话标题被裁就是 OCR 抓到的）。
- **一次出图 + 一次核验即止**：命令成功、产物非空之后不要再反复重跑同一张图做确认（重复验证会触发循环干预）；要再改就直接改脚本重出。
- 版式元素（分类色块在左/右侧、是否画某条注释条、标签位置）按用户**逐图指定**执行，不套用上一张图的默认；汇报用「你要的 → 我的落地 → 核验证据」三列表。

**🔑 用户说「标签能不能对齐自己的热图 / 搞个色块表示分类吧」时的正确姿势 = 先查渲染，再改代码。**
本会话实测：用户要的「分类色块」在代码里**早就写了**（`draw_group_stripes()`），只是被绘制顺序 bug 静默裁掉从没显示过。
所以这类「补一个已有元素 / 让已有元素对齐」的请求，**第一步永远是核验它有没有真的渲染出来**
（SVG 搜颜色 → 0 命中即没画出来，见上表），而不是立刻去调坐标、加图例、换配色——
否则会把一个「元素不存在」的问题当成「元素位置不对」来修，白改好几轮。

### 🔴 重分组重出图 → 结论必须重新取证，禁止搬运旧结论（2026-09-15 · 实测被推翻）

改分组 / 删成员后重出的图，**矩阵数值一字未变**（只有标签与行序变）——所以图上「看出来的新发现」极可能只是旧结论的惯性搬运。**本会话实测教训**：重出 FigA2 五效应图后，我沿用了旧项目的结论「运动效应只作用于代谢-收缩轴、对炎症轴无效」，用**逐轴显著格子数**一查就被推翻——运动三个效应在**所有轴**都几乎不显著（生物轴 0–3.6% vs 炎症轴 0–2.5%，噪声级差异），根本不存在"轴特异性"。**结论必须由本次数据重新算出**：

```r
# 轴 × 效应：显著格子数与占比（格子 = 程序 × 亚群）
e$axis <- ""; for (a in names(AXES)) e$axis[e$score %in% AXES[[a]]] <- a
s <- e[e$axis == a & e$effect == ef, ]
data.frame(n_cells = nrow(s), median_abs_d = median(abs(s$d)),
           n_sig = sum(s$q < 0.05), pct_sig = 100 * mean(s$q < 0.05))
```

- **判据**：要断言「A 轴受影响、B 轴不受影响」，先看两轴 `pct_sig` **是否真的分得开**；分不开就只能写「均未检出显著变化」。
- **阴性结果措辞**：FDR q>0.05 且 n 小时写「**未检出显著变化**」，**不写「无效」**（本例 n=24 配对 + 170 格子多重检验，检验力有限）。
- 图面差异 ≠ 统计差异：`median|d|` 只作趋势，结论落在 `pct_sig` / 显著格子数上。
- 交付形态 = 图 + 配套效应汇总 CSV；这也是 debate 裁 `need_more_info` 时裁判**第一条索要的证据**。
- ⚠️ **同族静态坑——R 变量名遮蔽**：这类脚本里矩阵变量**不要叫 `d`/`q`/`p`/`sub`**——它们与 CSV 列名重合，且会被 `for (d in OUTS)` 这类循环变量**静默覆盖**，症状是绘图时 `V[ni, pi*n_sub+ci+1]: 量度数目不正确`。矩阵一律命名 `DM`/`QM`/`Z6`，循环变量用 `outdir`，`data.frame(dir=outdir, ...)` 同步改。
- 配方与实测数字：`references/regrouping-replot-and-claim-recheck.md`。

## User's heatmap style preferences (from 2026-09 session, CORRECTED after user rejection)

| Feature | Preference |
|---------|-----------:|
| **Row labels** | **Right side**, two-line format: `Pathway name\n(key genes)` |
| **Label truncation** | Pathway ≤35 chars, genes ≤28 chars, append `...` |
| **Color scheme** | **Pure red monochromatic gradient** (NOT multi-color!): `#FFFFFF` (white/zero) → `#FFE0E0` (light pink) → `#FF9999` → `#E85D5D` → `#C41E1E` → `#7A0000` (deep red). User explicitly rejected gray→blue→orange→red ramp ("原图哪有蓝色，不全都是浅红，红，深红吗？"). The reference figure uses ONLY red tones. |
| **Aspect ratio** | Compact/near-square (10×12 inches for 56×17 matrix), NOT tall/portrait |
| **Value annotations** | Show `-log10(q)` in cells; white text for val>6, dark gray `#333333` otherwise |
| **Grid lines** | Thin (`#CCCCCC`, 0.5pt), not heavy |
| **Column labels** | Top, 45° rotation, fontsize 8 |
| **Legend** | Vertical colorbar on right, labeled `-log₁₀(q-value)`, ticks [0,2,4,6,8,10] |

> ⚠️ 上面这行 legend ticks [0,2,4,6,8,10] 是 **matplotlib 探索路径**（用户早期版本）的参考；**pheatmap 验收路径以 0/5/10 为准**（`legend_breaks=c(0,5,10)` + `legend_labels=c("0","5","10")` 同传）。两条路径并存时以 pheatmap 参考代码段为最终规格。

## Critical pitfalls (from 2026-09-07 session — 4+ failed iterations)

### P1. Sparse matrix — most cells are EMPTY
Hand-picked GO tables are ~92% sparse (each cluster has 3-6 terms). The heatmap looks like "a few red dots on white" — this is CORRECT, not a bug. **Do NOT** try to make it look dense by changing colors. If user complains about sparse appearance, offer:
- **Dotplot instead** (only shows enriched pairs, no empty cells)
- **Remove all-zero rows/columns** to compress the matrix
- **Add more GO terms** per cluster (top 10-15 instead of 3-6)

### P2. Color scheme MUST match reference figure EXACTLY
When user says "按这个图的样子画" — they mean the **exact color palette**, not "similar warm colors." Never substitute a multi-color ramp for a monochromatic one. The user catches mismatches immediately.

### P3. Data preprocessing gotchas
- `logq` values are **negative** in the cleaned CSV — take `abs()` before plotting
- Column names: `cluster, path_id, path, genes, logq, val, ngene` (NOT `Path`, `Log_q`)
- Drop all-zero columns/rows before plotting

### P4. Value range clipping (0-10) is standard
`-log10(q)` can reach 97+. Clip to 10 for the color scale but label clipped cells as `"10.0"` — do NOT use raw 97 as vmax (flattens everything to near-white).

### P5. Sparse matrix filtering recipe (2026-09-07 — key breakthrough)
When heatmap is >90% empty, **filter before plotting** to boost information density:
- **Row filter**: pathways appearing in ≥2 clusters (removes cluster-unique singletons)
- **Column filter**: clusters with ≥4 enriched pathways (removes low-activity clusters)
- **Result**: 56×17 (8.2% non-zero) → 13×16 (16.3% non-zero) — 2× density gain
- **Always report** the filtered dimensions and non-zero ratio to user before plotting
- **Python recipe**:
```python
row_nz = (pv > 0).sum(axis=1)
col_nz = (pv > 0).sum(axis=0)
dense_paths = row_nz[row_nz >= 2].index
dense_cols = col_nz[col_nz >= 4].index
pv_filtered = pv.loc[dense_paths, dense_cols].copy()
# Order by density
row_order = row_nz[dense_paths].sort_values(ascending=False).index
col_order = col_nz[dense_cols].sort_values(ascending=False).index
pv_filtered = pv_filtered.loc[row_order, col_order]
```

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| debate_analysis L2 三次失败: judge_* 角色全部返回占位符 (judge_ | 外部 LLM API judge 角色调用返回占位符（可能是 provider  | 不阻塞交付：记录错误后跳过辩论（参数全为用户指定，无争议点），直接验证图片质量并交付 |
| `dimnames` length mismatch on `rownames<-` | Sparse matrix + long/duplicate labels after dedup | Switch to Python matplotlib (see rowname trap section above) |
| Blank/black figure after plotting | `dev.off()` without `draw()`, or wrong `cairo_pdf` | Verify file size > 5KB AND use `vision_describe` to confirm labels render |
| `circlize` built under R 4.4.3 warning | Version mismatch, harmless | Ignore — `circlize` works fine on R 4.4.2 |
| `'\/' is an unrecognized escape in character string` (execute_r) | 用 `gsub("\\|", ", ", x)` 拆 `A\|B\|C` 基因串时，工具层的反斜杠转义与 R 的字符串转义打架 | 用 **fixed 匹配**：`gsub("|", ", ", x, fixed = TRUE)` — 无需任何转义，稳定通过 |
| 45° 列名最左列被裁（如 `Pure Type IIA` 缺字） | 画布宽度不足 + 行名区过长 | 加宽画布至 ≥3800px(res=300)，ComplexHeatmap 再设 `row_names_max_width`；验证时裁剪左上角放大 OCR，别只看整图 |
| `pheatmap(cellwidth=0.38)` 出图被压成一个点 / 整图 98.6% 空白，但 exit 0 | **`cellwidth`/`cellheight` 单位是磅(pt)，不是 cm** | 传 `cellwidth = cm × 28.35`（0.39cm→11，0.46cm→13）；渲染后量本体宽度验证 |
| 三格式导出后 PNG 全白（`extrema=(255,255)`，文件大小≈PDF 大小） | ① 持久内核里一次连开 png+pdf+svg，图形设备状态串了；② **更常见：导出前做了「量尺寸」动作（`pheatmap(silent=TRUE)` / `convertWidth`）→ 留下隐式设备，把随后开的 png 吞成空白**（**独立 Rscript 进程内同样会发生**） | ① 导出放独立 Rscript 进程；② 量尺寸整段包进 `pdf(NULL) … dev.off()`；③ 判据：`Image.open(p).convert("L").getextrema() == (255,255)` 即全白坏图 |
| 内容**左右两侧各被裁掉一截**（x=0 与 x=W-1 都有内容贴边；改了几轮画布宽度都没用） | **`cellwidth` 未指定时 pheatmap 的矩阵宽度按设备 npc 比例缩放** → gtable 总宽不可预测，`grid.draw` 默认居中 → 溢出部分左右各裁一半（v12：内容+边距 22.38 cm vs 画布 21.59 cm → 每侧裁 ≈0.4 cm） | 锁死 `cellwidth/cellheight`(pt) → `pdf(NULL)` 内量 `sum(gt$widths/heights)` → 反推画布 = 内容 + 边距 + 0.2 cm。详见 §零裁切画布反推 + `references/pheatmap-noclip-canvas-geometry.md` |
| 用户要求「只加大边距」，结果**热图本体也跟着变宽了**（用户原话："边距是边距，怎么把热图本体也变大了？"） | `cellwidth` 未指定时本体是 **null 单位**，随设备宽解算 ⇒ 只加画布宽 = 本体一起变宽；只加 padding 不改画布 = 本体被压窄 | 二选一：① **Δ画布宽 = Δ(左+右 padding)**（保持原脚本其余不动）② 锁死 `cellwidth`(pt) + 反推画布。详见 §「只调边距、其他不变」 |
| 像素检测抛 `zero-size array to reduction operation minimum` / 说"图里没有任何非白像素" | ① 图真的全白（坏图）；② PNG 是**调色板模式 `mode P`**，阈值化前没 `convert("RGB")` | 一律 `Image.open(p).convert("RGB")` 再 `np.array()`；先看 `convert("L").getextrema()` 判全白 |
| 图定稿后被系统判定"循环失控"强制中断 | 反复用像素扫描/vision 重新确认同一件事（尺寸/裁切） | 几何问题用**结构化量尺寸一次定论**（`convertWidth(sum(gt$widths))`），不要靠重复像素分析；定稿后只跑 `scripts/verify_figure_no_clip.py` **一次**即交付 |
| `strwidth(x, units="cm")` 报 `invalid units` | 空设备（null device）下不支持 cm | 用 `units="inches"` 取值后再 ×2.54 |
| base `svg()` 出来的 SVG 里 `<text>` 数为 0，只有 `<use>`/`<path id="glyph-*">`，grep 文字内容 NOT FOUND | **R 的 `svg()` 设备把文字转成矢量轮廓（glyph paths），不是活文字**（2026-09-15 实测：756pt 宽的 SVG 里 `use`×1643 / `path`×801 / `text`×0）。**这是设备行为，不是坏图** | ① 只是"文字不可双击编辑"，用户仍可在 Illustrator 里改色/缩放/移动，通常够用；② 需要真活文字 → 改用 `svglite::svglite("x.svg", width=, height=)` 重出（R 4.5.3 已装 svglite）。③ **永远不要用 grep SVG 文字来验证图**（必然 0 命中）——改用像素扫描 |
| **分组色块条 / 轴名 / 分组名整条消失**（图上只剩热图；R exit 0、四格式文件大小全部正常、无 warning；SVG 里搜该**颜色** 0 命中而 `xlink:href` glyph 引用数正常） | **绘制顺序 bug**：某个辅助函数用 `par(fig=..., new=TRUE)` + `plot.window()` **重置了坐标系**（典型 = 画色标的 `draw_cbar()`），而在它**之后**调用的 `draw_*(...)` 仍按**数据坐标**发指令（如 `rect(x=-1.25, y=0..18.25)`）→ 全部落到画布外**被静默裁掉**（`xpd=NA` 也救不了，设备边界照样裁） | 把**所有数据坐标绘制**移到重置坐标系的函数**之前**（本例：`draw_group_stripes()` 移到 `draw_cbar()` 前）。诊断顺序 = ①按 `rgb(%)` 形式搜分组色 / 直接跑 `scripts/verify_figure_layers.py`（⚠️ **`grep '#RRGGBB'` 必然 0 命中 = 假阴性**；报 0 之前先拿一张**已知含该色**的图跑同一命令做阳性对照，阳性对照也 0 ⇒ 是取样方法问题，改用栅格层像素计数，别断言元素没渲染）②搜 `xlink:href`（正常则设备没问题）③直接查绘制顺序。波及面排查 `grep -n "group_stripes\|draw_cbar\|axis(2" scripts/fig_*.R`。详见 `references/base-graphics-draw-order-and-layer-verification.md` + 一键核验 `scripts/verify_figure_layers.py` |
| 标签整体**偏移半格**（不居中）| `axis(2, at = NROWS-1-row_pos)` 锚的是**格底边**，不是格中心 | 改 `at = NROWS - 0.5 - row_pos`。判据：改动后整批标签**位移 = 半个格子**（实测 1 单位=100.8px → 位移≈50px）；位移不是半格说明算错 |
| 标题右半截被裁（OCR 只读到前半句，缺 `(row z-score, all samples)`） | `mtext`/`text` 的 `at` 是**数据坐标**；把 `(MAI[2]+NCOL*CELL/2)/CELL` 当"图幅中心"属量纲混用，算出 10.29 > xlim 上限 10 → 标题画到画布右缘外**被静默裁掉** | 图幅中心 = `at = (W/2 - MAI[2]) / CELL`（`W = NCOL*CELL + MAI[2] + MAI[4]`）。详见 `references/r-base-graphics-outer-layout.md` |
| 标题与顶部色标/刻度标签**互相重叠**（用户报"头顶的标题和 label 不要重叠"） | 标题和色标都画在绘图区内同一带（`text(NCOL/2, TOP-0.10)` + 顶部色标），间距只剩 0.02 in | 两层分离：**标题改 `mtext(side=3, line=0.60)` 画到上边距**（`MAI[3] ≥ 0.55 in`），绘图区内只留色标（`TOP <- YMAX+0.95`，色标带 `y0=YMAX+0.60`，刻度标签 `y0-0.08`）⇒ 物理上不可能重叠（实测标题 y=109px vs 色标标签 y=171px） |
| `strwidth` 警告「PostScript字体数据库里找不到'Arial'」/ 量出的宽度不可信 | 用 `pdf(NULL)` 做文字尺寸自检——PostScript 设备没有 Arial，回退到未知字宽 | 换 **cairo 临时 png**（`png(tf, type="cairo", family=FAM)` → 量 → `dev.off(); unlink(tf)`）；自检块放在**出图循环之前**（否则 stopifnot 失败时坏图已落盘）；可用宽度符号别写反（`(-0.10 - LB0)` 不是 `(LB0 + 0.10)`）；竖排文字量 **`strheight`** 而非 `strwidth` |
| 像素实测「标签距热图 1 px」与脚本自检「0.010 in（=3 px）」**互相打架** | 找墨迹用 `max(RGB) < 200` 阈值，而**热图最深格 `#053061` 的 max(RGB)=97 也满足** → 深色热图格被当成文字墨迹，把缝量小 | 测量带严格限制在 `x < 热图左边界(MAI[2]×dpi) − 2px`，或排除饱和像素（`sat>25` = 色块/热图，文字 sat≈0）。**两来源不一致时先定位污染再汇报**，别先报一个数下轮改口。详见 `references/raster-layout-measurement-forensics.md` |

## 🔴 中文标签方框 + 导出默认 + 「数据整理步骤也要配图」（三件高频事）

### 中文全变方框 = 静默失败，agent 看不见
matplotlib 默认 `DejaVu Sans` **不含 CJK** → 图能生成、文件非空、无报错，但中文全是豆腐块。
唯一可靠判据是 `savefig` 的 `UserWarning: Glyph ... missing from font(s) DejaVu Sans`
——**它极易被 `2>&1 | grep -v warn` 顺手过滤掉，所以先裸跑一次看警告**。

```python
from matplotlib import font_manager
_cjk = sorted(set(f.name for f in font_manager.fontManager.ttflist
                  if any(k in f.name for k in ("YaHei", "SimHei", "SimSun", "Noto Sans CJK"))),
              key=lambda n: ("YaHei" not in n, "SimHei" not in n, n))
plt.rcParams["font.sans-serif"] = _cjk + ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False        # 负号也跟着变，别漏
print("CJK 字体:", _cjk or "⚠️ 未找到，中文会变方框")   # 自证
```
本机可用 `Microsoft YaHei`/`SimHei`/`SimSun`/`MS Gothic`；挂上后文件明显变大（实测 353 KB→423 KB）
= 中文真渲染出来的旁证。**交付前必须 OCR 核验中文可读**（纯文本模型看不到图，只能靠工具）。
⚠️ 不要为"字体统一"擅自装 DejaVu —— 声明差异让用户定。

### 导出默认（本用户长期要求，不必每轮再问）
**@300 dpi + 每张图附 SVG**；不要再出 150 dpi。
```python
for ext in ("png", "svg"):
    fig.savefig(f"{stem}.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
```

### 🔴 交付位置：定稿必须放到用户「翻得到」的目录（2026-09-15 实测 · 用户回「我没看到图」）

图**全部生成、4 格式非空、`rail_review(post)` 通过**，用户仍说**「我没看到图」**——根因**不是没出图**，而是图只写进了**工作子目录**（`figures/R_version/`），而用户翻的是**项目根的 `figures/`**。用户不会去子目录里找产物，agent 却以为"已交付"。

**交付三步（缺一步就会被再问一次）**：
1. 工作产物留在子目录（`figures/R_version/`，含 manifest QA CSV）；
2. **定稿按规范名复制到用户翻看的位置**（`figures/FigA3_program_subcluster.{png,pdf,svg}`）；
3. **被替换的旧版移入 `figures/archive_superseded/` 并改名带版本后缀**（如 `_v1_oldgrouping`）——**移动而非删除**（删除保护会拦，用户也要可回溯）；同时满足用户"禁止多版本产物并存"。

汇报时**给出根目录路径并当场 `ls -l` 实测**；只报子目录 = 用户看不到。判据：**任何"产物在子目录里"的交付，先自问一句「用户下次会去哪找它？」**

### 纯表格步骤也要配图
`rail_review(post)` 检查"每步至少 1 张图"，**表重建/数据清洗步骤没图会被判不通过**（即使产物全对）。
对策 = 把「数据质量核查图」作为标配产物：表重建 → 源表 vs 派生表逐项对照图（标出被截断/丢失项）；
清洗前后 → 丢失条目条形图。既过审查，又让用户一眼看到数据没被暗改。

配方细节：`references/cjk-font-and-export-defaults.md`

## Proven Scripts

| 物种 | 组织 | 方向 | 日期 | 脚本 | 说明 |
|------|------|------|------|------|------|
| human | skeletal_muscle | aging/exercise | 2026-09-07 | `scripts/go_heatmap_matplotlib_v3.py` | Reference-figure style: right labels, warm colors, compact ratio. **Use as template.** |
| human | skeletal_muscle | aging/exercise | 2026-09-07 | `scripts/go_heatmap_final_filtered.py` | **Final working version**: sparse-filtered (≥2 clusters, ≥4 pathways), pure red 6-stop gradient, 0-10 clip, gene annotations right-side. |
| human | skeletal_muscle | aging/exercise | 2026-09-07 | `templates/go_heatmap_pheatmap_template.R` | **pheatmap user-reference code copy**: matrix 0-fill + clip 0-10 + white→#FF9999→#8B0000, no clustering, angle=45. Copy & modify path_genes for new data. Runs one-shot in execute_r (R 4.5.3 has pheatmap+openxlsx). |

### Pure red gradient colormap (verified, no blue component)
```python
from matplotlib.colors import LinearSegmentedColormap, Normalize
colors_red = ['#FFFFFF', '#FFD4D4', '#FF8888', '#FF4444', '#CC0000', '#800000']
cmap = LinearSegmentedColormap.from_list('cns_pure_red', colors_red, N=256)
norm = Normalize(vmin=0, vmax=10)
```
**Never** use matplotlib built-in `Reds` or `RdBu` — they include blue/gray tones at the low end.
**Never** use `plt.cm.get_cmap('Reds')` — the user catches the blue/gray immediately.
**See**: `references/colormap-anti-patterns.md` for full list of colormaps to avoid and why.
| human | skeletal_muscle | aging | 2026-09-07 | read_MF_SMF_GO_select.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-07 | go_heatmap_pheatmap_MF_SMF.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-08 | go_heatmap_MF_SMF_v2.R | - | - |  |
| human | skeletal_muscle | aging/exercise | 2026-09-08 | `scripts/go_heatmap_MF_SMF_v3_words_only.R` | **v-B 纯词条版**（用户终版）：term-only 行标签，pheatmap 严格照抄用户参考代码参数，低端色 #FEE9E7。execute_r(R 4.5.3) 一键跑，三格式输出。 |
| human | skeletal_muscle | aging/exercise | 2026-09-08 | `scripts/go_heatmap_MF_SMF_v3_genes_right.R` | **v-A 基因右列版**（用户终版）：词条在左 + 基因 right_annotation 独立列，零重叠。R 4.4.2 Rscript 跑（ComplexHeatmap），三格式输出。 |
| human | skeletal_muscle | aging/exercise | 2026-09-08 | `scripts/go_heatmap_v6_final_YlOrRd_words_only.R` | **v6 定稿·YlOrRd 纯词条版**：pheatmap 严格照抄参考代码，画布 3800px 防列名截断，legend 右下手动 grid。execute_r(R 4.5.3) 一键，三格式。 |
| human | skeletal_muscle | aging/exercise | 2026-09-08 | `scripts/go_heatmap_v6_final_YlOrRd_genes_right.R` | **v6 定稿·YlOrRd 基因右列版**：ComplexHeatmap，画布 4200px + row_names_max_width 显式，防 Type IIA 截断。R 4.4.2 Rscript，三格式。 |
| human | skeletal_muscle | aging/exercise | 2026-09-15 | `templates/go_heatmap_cns_handoff_pheatmap.R` | **v11 定稿·Illustrator 交付版（首选模板）**：pheatmap `silent=TRUE` → `gtable_add_padding` 留四周空白（左 1.8cm 根治 45° 列名截断）→ 画布 10.5×11.5 in → 右下横放 legend → 独立 Rscript 三格式导出 + 3 项后验检查。全部 48 词条不筛选，收窄热图本体、放宽词条区。 |
| human | skeletal_muscle | aging/exercise | 2026-09-15 | `results/memomics-440038cf/scripts/go_heatmap_v11_wider_margin_words_only.R` | v11 实际运行脚本（项目内），与上面模板同源。 |
| human | skeletal_muscle | aging/exercise | 2026-09-15 | `scripts/go_heatmap_v12b_margin_words_only.R` | **v12b 终版·零裁切宽边距（用户认可，首选起点）**：`cellwidth=24.66pt` / `cellheight=9pt` 锁死几何 + `PAD(上右下左)=c(1.2,3.5,2.0,4.5)cm` + **null 设备内量尺寸反推画布** 11.92×8.33 in → 48 词条 × 15 亚群零裁切。项目内副本：`results/memomics-440038cf/scripts/go_heatmap_v12b_margin_words_only.R`。验收探针：`scripts/verify_figure_no_clip.py`（一次跑完，别反复像素扫描）。 |
| human | skeletal_muscle | aging | 2026-09-15 | `scripts/go_heatmap_v13_margin_words_only.R` | **v13 · 只加左右边距版（路径 A）**：严格照抄 v12，仅 `PAD` 左2.8→5.0 / 右1.8→4.0 cm + 画布宽 8.5→**10.23 in**（Δ画布=Δ边距 ⇒ 本体不变）；同源 v12b = 路径 B（锁 `cellwidth` 零裁切）。手册：`references/pheatmap-margin-only-adjustment.md`。 |
| human | skeletal_muscle | aging | 2026-09-15 | go_heatmap_v14_smaller_words_only.R | - | - |  |
| human | skeletal_muscle | aging/exercise | 2026-09-15 | `results/memomics-2274ab75/scripts/fig_A2_5effects_v3.R` | **base-graphics 多面板矩阵热图元脚本（零第三方依赖）**：17 程序 × 5 效应面板 × 10 亚群，`rect()` 拼格子 + `TwoSlopeNorm` 等价 256 级 LUT + FDR 星号 + 左侧**分组色块条**（5 轴色）+ `par(fig)` 右下/右侧色标。**已修两坑**：① 分组色块条移到 `draw_cbar()` **之前**绘制（v2 因顺序问题色块从未渲染）② 标签 `at = NROWS-0.5-row_pos` 行中心（v2 用底边偏半格）。四格式 @300dpi + manifest QA。**要复制这套版式就从 v3 起，不要从 v2 或 `fig_split_v10.R` 起——它们两坑都有**。同族：`scripts/fig_A3_transposed_v3.R`（转置版，干净）。 |
| human | skeletal_muscle | aging | 2026-09-19 | `results/memomics-2274ab75/scripts/fig_A3_CNS_v5.R` | **转置矩阵热图·定稿版式（用户认可）**：亚群 x × 程序 y，17 程序 / 5 轴 / 10 亚群，107.9×155.5 mm，base graphics 零第三方依赖 + Arial + `svglite`（SVG 文字可编辑）。**关键常量**：`CELL=0.255`、`MAI=c(0.75,1.35,0.55,0.35)`、`LBLX=-0.04`（行标签右端紧贴热图，实测缝 3 px）、`LB0=-3.40/LB1=-4.11`（左侧分类色块）、`LNX=-4.27`（竖排轴名，**黑色 `COL_TXT`**）、标题 `mtext(side=3, line=0.60, at=(W/2-MAI[2])/CELL)`。脚本自带 strwidth 版式自检 + `archive_superseded/` 归档上一版。 |
