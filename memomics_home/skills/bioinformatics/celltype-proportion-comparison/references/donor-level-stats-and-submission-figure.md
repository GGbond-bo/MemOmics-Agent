# 投稿级多 panel 组合图配方 + 图注披露模板（供体级统计收官）

**来源**：2026-09-24 人骨骼肌肌核图谱投稿主图（`MF_2000.rds`，2,132 核 / 48 样本 / 24 供体 / 6 组 / 10 亚群）。
经 **两轮 L2 辩论**（首轮 `modify` → 逐项落地 → 复核 `support`：「可以按 v2 条件定稿投稿，剩余仅投稿包生产 QA」）定稿。
本文件是"样本级统计 → 分档措辞 → 一张能投稿的组合图 → 投稿包"的完整收官配方，可直接复用到其他组学数据。

---

## 1. Figure Contract（出图前写死，否则必返工）

| 项 | 本例 |
|---|---|
| **核心结论（一句话）** | 衰老与 T2D 使肌核组成与纤维身份程序**反向**重塑；运动只在老年/糖尿病肌肉激活再生程序 |
| **archetype** | `quantitative grid`（3 行 × 2 列，6 panel） |
| **panel → 论据** | a UMAP=图谱基底｜b marker DotPlot=**注释自证**（审稿必查）｜c 组成矩阵=组成重塑总览｜d 身份程序箱线=衰老轴｜e 比例箱线=组成位移｜f 状态程序=老年专属运动响应 |
| **导出契约** | 183 mm 双栏 × 196 mm；PNG 600 dpi + cairo PDF + svglite SVG（**文字可编辑**）+ TIFF 600 dpi；panel 字母 a–f；每 panel 标 n |
| **评审风险** | 抽样版功效 / 性别单一 / 已处理对象 / 反直觉打分 / 趋势被写成显著 |

**panel 选择纪律（宁删不凑）**：每个 panel 必须承载**唯一**论据。本例主动**放弃**「程序打分 × 亚群矩阵热图」——
18 个程序打分在该数据里跨亚群行内 z 全为负（区分度弱），做了也讲不出故事。
反之 `UMAP + marker DotPlot` **不要删**：它们承担"注释可信"这一独立论据，是审稿人必查项。

---

## 2. CVD / 灰度安全设计令牌

### 2.1 条件 × Pre/Post → 三色 + 双重编码

| 条件 | Okabe-Ito 色 | 灰度亮度(0-255) | Pre | Post |
|---|---|---|---|---|
| Young | `#009E73` 绿 | 106 | 浅色填充 + **虚线边框 + 空心圆** | 实色填充 + **实线边框 + 实心三角** |
| Old | `#0072B2` 蓝 | 87 | 同上 | 同上 |
| T2D | `#D55E00` 朱红 | 119 | 同上 | 同上 |

- Pre 浅色 = 本色混白 55%（`mix_white(hex, 0.55)`）→ 本例 `#8CD3C0`/`#8CC0DC`/`#ECB78C`（亮度 180–194）
- **Pre vs Post 明度差 ≥ 60**（180–194 vs 87–119）= 灰度可靠分离
- **三条件灰度亮度只差 13–32 ⇒ 绝不靠色相/灰度区分条件**，必须叠线型 + 形状：
  `scale_linetype_manual(c(Pre="dashed", Post="solid"))` + `scale_shape_manual(c(Pre=21, Post=24))`
- 🔴 **配色键必须是真实前缀 `Y/O/OD`**（`sub("_(Pre|Post)$","",type)` 的结果），写成 `Young/Old/T2D` 会静默变 NA → 空白箱体（见 SKILL.md §8）

### 2.2 多类别（10 亚群）→ 家族内明度梯度，跨家族色相

```r
SUB_COL <- c("Pure Type I"="#08306B","LRP1B+(I)"="#2171B5","OTUD1+(I)"="#4292C6","RP_high(I)"="#9ECAE1",
             "Pure Type IIA"="#7F2704","Pure Type IIX"="#D94801","OTUD1+(II)"="#F16913","RP_high(II)"="#FDAE6B",
             "Specialized MF"="#54278F","RSS"="#737373")
```
亮度实测：I 家族 43→191、II 家族 61→190（家族内单调）；**跨家族会撞车**（`#9ECAE1` 191 vs `#FDAE6B` 190、`#7F2704` 61 vs `#54278F` 64）
⇒ 必须给**直接文字标注**（UMAP `ggrepel`、矩阵 y 轴名、格内数值），不要只靠颜色。

### 2.3 类别多的组成图 → 单色顺序矩阵，不要堆叠柱

10 类堆叠柱在灰度/CVD 下不可辨（辩论反方判为高风险阻断项）。改为 **类别 × 组矩阵**：
`geom_tile(fill = 比例)` + **格内写数值** + 单一顺序色阶（Blues `#F7FBFF→#08306B`）。
顺序单色阶天然灰度单调、CVD 安全，格内数值替代图例。
⚠️ **代价**：丢失"整体占比"的视觉总和 ⇒ 图注必须给**分母 / 行和≈100% / 每组总 n**（见 §4 补丁）。

---

## 3. layout / 导出常量（改图只 patch 这几处）

```r
W_MM <- 183; H_MM <- 196;  w <- W_MM/25.4; h <- H_MM/25.4
plot_layout(heights = c(1.0, 1.0, 0.92), widths = c(1.05, 1.0))
theme_classic(base_size = 6, base_family = "sans") +   # axis.line/ticks linewidth 0.3；panel.grid 空
axis.text = base - 0.6; legend.key.size = unit(2.4, "mm")
ggsave(..., width = w, height = h, units = "in", dpi = 600,
       device = <"png" | grDevices::cairo_pdf | svglite::svglite | ragg::agg_tiff>,
       bg = "white", limitsize = FALSE)
```
⚠️ 不要用 `egg::set_panel_size` + `ggsave` 不传 width/height（会退到 7×7 in 画布，内容只占中间一小块）。
本类箱线图族的另一历史约定：**6 柱 = 30 mm、每少 1 柱 −2 mm、高 32 mm**。

---

## 4. 图内最小侵入披露（裁决要求：主图必须自包含）

底部一行 caption；**source data 路径 / 脚本号 / 软件版本不进图内**（太挤），放图注末或 Data/Code Availability。

```r
FOOT <- paste0(
  "n = 10 (Young) / 7 (Old) / 7 (T2D) donors; sampled dataset (45 nuclei per sample); all female; processed object. ",
  "Statistics: donor-level two-sided Mann-Whitney (cross-group) and paired Wilcoxon (Pre vs Post), BH-FDR within family ",
  "(proportion 50 tests / score 70 tests); all five FDR<0.05 hits also survive BH across the merged 120-test family (q = 0.012-0.038). ",
  "80%-power minimum detectable difference for proportion panels: 6 pp (RSS), 10 pp (Pure Type IIA, Specialized MF), 14 pp (Pure Type IIX). ",
  "Boxes: dashed border, open circle = Pre; solid border, filled triangle = Post.")
fig <- (...) + plot_annotation(tag_levels = "a", caption = FOOT) &
  theme(plot.tag = element_text(size = 8, face = "bold"),
        plot.caption = element_text(size = 4.3, colour = "grey20", hjust = 0, lineheight = 1.15))
```
必备字段：**每组 n｜抽样/数据构成限制｜处理状态｜检验名｜BH 家族与检验数｜全局校正复核结果｜MDE 与观测差｜Pre/Post 编码说明**。

**跨行一致性提醒**：`(pa|pb)/(pc|pd)/(pe|pf)` 用 `plot_annotation(tag_levels="a")` 产出 a–f；
行高比例 + 顶部 UMAP 的 `coord_fixed()` 会让第一行吃掉约 40% 高度（实测 4322×4629 px 下 band1≈40%），
行 3 里若 caption 很长会进一步挤压——出图后按三分带 color% 验证每行都有内容（见 §6）。

---

## 5. 图注 disclosure 段 + panel c 分母补丁（投稿图注模板）

```
**Dataset and power limits (please read together with the claims).** This is a **sampled dataset
(45 nuclei per sample)**, an **already processed object** (SCT + Harmony + UMAP + manual annotation)
and **all donors are female**; the data therefore support re-analysis only and cannot be presented as
newly generated sequencing. Because each sample contributed a fixed number of nuclei, proportions are
stepped (1/45 ≈ 2.2 percentage points). Monte-Carlo power calibration (1,000 simulations per cell,
donor-level Wilcoxon tests) gives an 80%-power minimum detectable difference (MDE) of …
Consequently: <超 MDE 的发现> is supported; <落在边界的> is reported as **indicative only**;
<不显著的> was **not detected at this sample size (underpowered)** and must not be stated as "no difference".
```

**panel c（矩阵版）分母补丁**（插到 panel c 描述后）：
> Each cell gives the mean percentage of nuclei of that subcluster within a group (per-donor percentages
> averaged across 10 Young / 7 Old / 7 T2D donors; values in a column sum to ≈100%). Group nuclei totals are
> 450 / 450 / 315 / 287 / 315 / 315 for Young Pre / Young Post / Old Pre / Old Post / T2D Pre / T2D Post.
> Exact per-donor values are provided as source data.

**禁用词**：更年轻 / 衰老负担降低 / 无差别 / 稳健下降 / 逆转 / 运动诱导。

---

## 6. 出图后必做：像素级验证（防静默失效）

跑 `scripts/verify_figure_pixels.R`。本例实测通过值（作对照基线）：

| 指标 | 实测 | 判据 |
|---|---|---|
| dark（RGB 全 <100） | 2.40 % | < 10 |
| colored（max−min > 30） | 8.49 % | > 1 |
| near-white（min > 240） | 87.74 % | 白底 |
| content bbox | rows 181–4611 / cols 35–4317 | 占满画布 |
| 三分带 colored | 1.92 / 23.55 / 3.35 % | 每行都有内容 |
| **逐组别色 hex 计数** | `#8CD3C0` 2043｜`#009E73` 3124｜`#8CC0DC` 15660｜`#0072B2` 2811｜`#ECB78C` 3377｜`#D55E00` 2930 | **任一为 0 = 该组填充失效** |

⚠️ **只报"非白%"或"文件大小"会漏判**：本次修复前 band3 colored = 0.00% 但 dark 仍有 3.70%（框线/坐标轴/文字还在），
单看 dark 或文件大小（1180 KB）完全正常。**必须逐预期 hex 计数**才是硬证据。
⚠️ 本地 vision 工具报的"主色 `#e0e0e0` 81%"是**分桶量化伪影**（实测该 hex 仅占 0.03%），不要据此判失败。

---

## 7. 辩论闭环（submit 级图必走）

`L2（场景判定 = figure_layout）` → 首轮可能给 `modify`（本例 4 项：panel 降级 / 图注披露 / CVD 配色改造 / 补 MDE 与 FDR 敏感性）
→ **逐项实际落地并重跑脚本** → 再跑一轮 L2 **复核**（topic 写明「这是对上一轮 modify 的复核，请勿重争已定稿事项」并列 3–4 个具体问题）
→ 复核得 `support`。
**为什么值得跑复核轮**：它会把剩余项拆成 `owner=ai`（低成本的披露核对表 / 审稿话术）与 `owner=user`（排版实测 / CVD 样张 / 凭证），
避免把**生产 QA 误当科学阻断**反复返工。复核轮成本低、收益高。
⚠️ 与 `L1 辩论裁判解析失败 → 同内容重试 1 次` 的区别：解析失败（`verdict_parse_error`）是重试，**内容裁决=modify 是必须落地**。

---

## 8. 交付物骨架（本例，可复用）

```
figures/Fig_<name>_v2.{png,pdf,svg,tiff}          # 主图 4 格式
figures/Supplementary_Fig_S1_<降级项>.{png,pdf}    # 被降级的 panel
results/FIG_caption_draft.md                      # 投稿图注（英文）+ 中文自查核对表
results/RESULTS_wording_tiers.md                  # 逐条结论分档（显著/提示性/未检出）
results/SUBMISSION_CHECKLIST.md                   # 披露核对表 + 图注逐字补丁 + 审稿应答话术
results/<stats>_{stats,MDE_vs_observed,fdr_sensitivity,wording_tiers}.csv
scripts/01_prep_*.R → 02_fig_v1.R → 03_mde_fdr_wording.R → 04_fig_v2.R
```
**审稿应答三话术**（经验证好用）：① FDR 家族预设 + 合并全局 BH 敏感性（附 q 区间）；② MDE 与观测差对照 ⇒ 5 显著/6 提示/2 未检出；
③ 反直觉打分外移补充图 + 签名局限引用（如 SenMayo 属泛 SASP、终末分化肌纤维证据不足）。

**诚实提示模板**（用户说"我要拿去投稿"时必说）：若数据是抽样版 / 已处理对象，图可以投，但**只能作为"再分析"证据**；
要当主图须在**全量数据**上按同一套 donor 级管线 + MDE 校准重跑定稿（脚本 01–04 改 `readRDS` 路径即可复用）。