# L3 Proportion Boxplots — Paired 6-Group Design (validated 2026-08-12)

Validated on human skeletal muscle MF, metadata `E:/骨骼肌锻炼/MF_L3_meta_new.csv`
(508,662 cells, 48 samples, 6 groups Y/O/OD × Pre/Post). Delivered one celltype at a
time with user confirmation before finalizing groups + panel width.

## Data / design

- 10 L3 subtypes; plotting excludes RSS + Specialized MF (user decision), but
  **significance is computed for ALL 10** (user explicit).
- 6 groups: Y_Pre/Y_Post (young, n=10 pairs), O_Pre/O_Post (old control, n=7),
  OD_Pre/OD_Post (old diabetic, n=7). Pair key = samplename minus `_Pre`/`_Post`
  (`extract_base_id`), i.e. "Old_5C_Pre" → "Old_5C".
- Sample mapping regex: `^Young_\\d+_(Pre|Post)$` → Y; `^Old_\\d+C_(Pre|Post)$` → O;
  `^Old_\\d+_(Pre|Post)$` (no C) → OD. Watch the C/no-C distinction.

## 6 comparisons (v3, 2026-08-12 — 5 effect axes + young-vs-disease)

```
Aging      Y_Pre  vs O_Pre   unpaired Wilcoxon + cliffs_delta
T2D        O_Pre  vs OD_Pre  unpaired Wilcoxon + cliffs_delta
Ex-Young   Y_Pre  vs Y_Post  paired Wilcoxon (base_id) + median_diff
Ex-Old     O_Pre  vs O_Post  paired Wilcoxon (base_id) + median_diff
Ex-T2D     OD_Pre vs OD_Post paired Wilcoxon (base_id) + median_diff
YoungVsT2D Y_Pre  vs OD_Pre  unpaired Wilcoxon + cliffs_delta   ← v3 added
```

The 6th comparison (user asked: "是不是还要做一下年轻运动前跟老年糖尿病运动前的比较？")
proves disease-state fiber loss relative to YOUNG, not just vs age-matched control.
Muscle result: Y 42.8% vs OD 26.3%, p=0.033, FDR_per_celltype=0.099 (marginal after
BH) — report raw p + direction consistency per small-n protocol. ⚠️ Adding a
comparison changes the significance CSV to 10 × 6 = 60 rows; FDR must be recomputed
(per-celltype 6 BH + global 60 BH), never reuse the 50-row FDR column. Version the
output file (v3_with_YvsOD.csv).

## ⛔ THE direction trap (root cause of a misreport)

The user's script had TWO different effect-size conventions:

| comparison type | code | positive means |
|---|---|---|
| paired | `median(v2 - v1)` | pair2 (Post) higher |
| unpaired | `cliffs_delta(x, y)` x=pair[1] | **pair1 higher** ← opposite |

Reading `cliffs_delta(O, OD) = +0.84` as "OD higher" was WRONG; it meant O higher →
diabetes DECREASES Pure Type I. The user caught it from the boxplot ("我图中看出来了，
糖尿病明明显著下降").

**Fix (validated):**
```r
# unify: positive = pair2 higher everywhere
es <- cliffs_delta(y, x)   # y = pair2, x = pair1  (NOT cliffs_delta(x, y))
# then direction column:
direction = case_when(
  effect_size > 0 ~ paste0(group2, " 高于 ", group1),
  effect_size < 0 ~ paste0(group2, " 低于 ", group1))
```
**Always verify against raw medians before writing any interpretation:**
```r
pt1 %>% group_by(type) %>% summarise(median_prop = median(Proportion))
# O_Pre 39.17%  vs  OD_Pre 30.83%  →  diabetes lowers Pure Type I ✓ (7/7 individuals)
```

## Corrected significant results (FDR_per_celltype < 0.05, direction fixed, v2 50-row)

| celltype | comparison | p.value | FDR_ct | FDR_global | es | direction |
|---|---|---|---|---|---|---|
| RSS | Y vs O | 0.00021 | 0.001 | 0.010 | −0.97 | O 高于 Y (aging ↑ RSS) |
| Pure Type IIA | Y vs O | 0.0046 | 0.023 | 0.116 | +0.80 | O 低于 Y (aging ↓ IIA, type-II atrophy) |
| Pure Type I | O vs OD | 0.0070 | 0.035 | 0.117 | −0.84 | OD 低于 O (diabetes ↓ slow fibers) |
| LRP1B+(I) | OD Pre→Post | 0.0156 | 0.046 | 0.185 | −2.26 | Post 低于 Pre (exercise ↓ in T2D) |
| LRP1B+(I) | Y vs O | 0.0185 | 0.046 | 0.185 | −0.69 | O 高于 Y (aging ↑) |

After direction fix, everything is biologically coherent (RSS aging↑, IIA atrophy↓,
Pure Type I diabetes↓) — the data were right; the mislabeled direction was mine.

v3 (60-row) adds: Y vs OD significant on RSS (p=1.0e-4, FDR_ct=0.0006) and
Specialized MF (p=1.0e-4) — even the non-plotted subtypes give the strongest signal
in the added comparison; Pure Type IIA Y vs OD p=0.033 / FDR_ct=0.099 (marginal).

## One-subtype plotting loop (user's exact workflow)

```
for each subtype (one at a time, user confirms before next):
  1. plot 6 groups with all comparisons, raw p annotation (exploration)
  2. present significance table + interpretation (逆转衰老/逆转糖尿病/共同趋势?)
  3. user decides which groups to draw + panel width
  4. final PDF: egg::set_panel_size(width=unit(W,"mm"), height=unit(32,"mm"))
     W = 30 mm @ 6 bars, 28 @ 5 bars, −2 mm per bar fewer
  5. final annotation: switch to FDR_per_celltype (or global) for paper
```

## ⛔ "改成p值" ≠ 新画一张 p 值图 (user correction 2026-08-12)

用户原话："你在画什么鬼？我给你的脚本，里面不是FDR吗？改成p值不就行了吗？p值有些
可以显著的吧？" + "把你画的那两个不需要的图删掉，我没让你画他们俩".

- 用户已有绘图脚本（plot_celltype_proportion，标注列默认 FDR_per_celltype）说
  "画p值的图" → **把标注列从 FDR 换成 p.value**，标签 "FDR=" → "p="，不是画一张
  -log10(p) 条形图或其他新的可视化。
- 最小修改原则：只动标注列 + 标签前缀 + 筛选列（!is.na(p)），分组/箱线/配对连线/
  括号定位/防重叠全部不动。
- raw p 下 FDR 被校正掉的边缘比较也会显示（如 O Pre→Post p=0.047 但 FDR=0.117）
  ——这就是探索版价值；论文终稿再换回 FDR。
- 探索中多画的图，用户没要的必须删掉。
- 实现：plot_celltype_proportion 加 use_p_value 参数；sig_col <- if(use_p_value)
  "p.value" else "FDR_per_celltype"；label 前缀由 sig_col 决定（"p=" / "FDR="）。

## ⛔ FDR 版全标注规则（user: "FDR 版标注，都标记吧，然后这版图就这6个" 2026-08-12）

用户要 FDR 版时**不要只标 FDR<0.05 的比较**——全部比较的括号都标注（含 O vs OD
FDR=1.000 这类非显著行），显著性判断交给读者。实现：sig_data 只过滤
`!is.na(.data[[sig_col]])`，**不加 `< 0.05` 条件**；label 前缀按 sig_col 切换
（`FDR_per_celltype`→"FDR="，`p.value`→"p="）。\n
定稿流程：用户确认组别（Pure Type IIA 最终 = 6 组全画）后即锁定该亚群，不再改版；
每亚群定稿 = 用户原版脚本 × 两个标注列（FDR 版 + p 值版）各 PNG+PDF。

## ⛔ 非显著配对效应的个体响应分解 (2026-08-12)

OD 组运动后 IIA 中位数 +6.5pp 但配对 Wilcoxon p=0.469 — 表面"有效果"不可信。
分解到个体级：
1. 列 7 个体 Pre→Post delta：4 升 3 降（3 强响应者 +14~+18pp 拉高均值，3 下降
   −3~−10pp）→ "响应者异质性"，不是一致生物学效应。
2. **中位数之差 ≠ 配对差的中位数**：+6.5pp 是中位数之差（误导）；配对检验看差的
   中位数（+2.8pp）。报告时务必区分两种度量。
3. 响应者 vs 非响应者基线对比（Mann-Whitney p=1.0）：基线无差异 → 不能讲
   floor-effect；有差异才可讲"低基线个体运动后回升"。本例只能如实说异质性无基线
   解释。
4. 画个体配对连线图（每线一个个体，响应者/非响应者双色）给用户看原始结构。
5. 措辞：n=7 下"运动促快肌"只能作探索性观察 + 响应者异质性，不能作普遍性主结论。

## Storytelling guidance for a "no reversal" subtype (Pure Type I example)

When a subtype shows NO reversal narrative (diabetes lowers, exercise also lowers,
young exercise rises), do NOT force a reversal story. Valid angles:
- "diabetes-specific slow-fiber loss" (7/7 individuals, big Cliff's δ) — a real finding
- "exercise response direction switch with age/disease" (Y↑ but O/OD↓) — young vs
  pathological muscle respond oppositely to the SAME exercise stimulus
- **Caveat language**: proportion change may reflect MYH7 transcription downregulation
  (classification shift) rather than fiber loss — write "slow program proportion
  decreases" not "slow fibers disappear". This was surfaced by the debate engine.

## CNS 优化版（用户要求"先按我脚本画，再CNS优化一版" 2026-08-12）

用户原话："画 4 组（O_Pre/O_Post/OD_Pre/OD_Post），出两张图，一个FDR，一个原始P值，
先按照我给你的脚本画，然后你按照CNS级别优化一下出一版图，我看看你优化怎么样"。

双版本交付（每亚群定稿前）：
- **V1 用户原版**：`plot_celltype_proportion` 只改 groups / 标注列(sig_col) / 宽度，
  其余（6 组配色、箱线+点、虚线配对、手动括号防重叠）全不动 → 用户核对数值。
- **V2 CNS 版**：
  - 同色系 Pre/Post 配对：O_Pre `#80B1D3` → O_Post `#1F78B4`、OD_Pre `#FB9A99` →
    OD_Post `#E31A1C`（4 组时天然形成 O 蓝 / OD 红两对，干预前后一眼可辨）
  - 星号体系替代 "FDR=0.035" 长文本：`* p<0.05, ** p<0.01, ns`（更期刊化）
  - theme_classic(base_size=6-7) + 无网格 + 细边框 + 配对线 0.35 半透明
  - 导出 SVG（可编辑）+ PDF + PNG(300dpi)，egg::set_panel_size 固定面板
- 用户拍板选版 → 下一亚群统一按被选版出。

## 每张交付图必须过像素检查 (2026-08-12 二次纠正)

用户："你画的好多图都是空的，你都不检查"（第二次）——第一次的教训（文件大小≠内容）修完，
第二次暴露**"非白像素%"单指标本身有漏洞：纯黑背景 100% 非白，会被误判成"有内容"**。
黑底假图（egg::set_panel_size + ggsave 缺 bg="white"）实测 94.8% 纯黑 [0,0,0] + 4% 灰线，
非白检查全过但视觉=黑屏。正确三指标检查（PIL）：
```python
from PIL import Image
import numpy as np
arr = np.array(Image.open(f).convert("RGB")).astype(int)
r, g, b = arr[...,0], arr[...,1], arr[...,2]
mx = np.maximum(np.maximum(r,g),b); mn = np.minimum(np.minimum(r,g),b)
dark    = (mx < 100).mean()*100      # 黑底判定：>50% = 黑底图 ❌（必须 <10）
colored = ((mx-mn) > 30).mean()*100  # 彩色（箱体/点）比例：正常箱线图 >1%
# 内容边界框：非白像素的 y/x 范围；空图 bbox 为 0 或极小
# 判定：dark<10 且 colored>1 且 bbox 合理 → ✅
```
任何 PNG 交付前都跑三指标；黑底图第一眼被 dark% 抓出，直接查 ggsave 是否缺 bg="white"。

## Windows R 出图坑（本会话实测）

- `theme(base_family="Arial")` / `gpar(fontfamily="Arial")` 报"字体类别出错"（grid
  不认裸名 Arial）→ 删掉 family 参数用默认 sans。
- **png() 设备 + `print(set_panel_size(p))` → 3.9KB 空白 PNG**；同一对象走
  `ggsave()` **若不加 `bg="white"` 会出 94.8% 纯黑背景的"假图"**（黑底 + 4% 灰线，
  视觉=黑屏，用户判"图是空的"；文件 50-60KB 照样黑）。**修复：ggsave 三处（PNG/PDF/
  SVG）一律显式 `bg = "white"`**，或 pdf() 设备 + `grid::grid.draw(p_scaled)`。
  黑底修复后用像素三指标验证（见下节），不能只看文件大小。
- **函数默认参数同名递归引用**：`f <- function(..., fdr_table = fdr_table, ...)`
  参数默认值与全局变量同名 → R 报"递归缺省参数参考"。参数名避开全局名
  （`sig_table = fdr_table`），函数体内全部改用参数名。
- CSV 首列可能是空表头的行号列 → `read.csv(row.names=1)` 再读，别把行号当数据列。
- **执行节奏提醒（用户"刚上是崩了吗?"）**：R 分析脚本的验证 = 真实执行(exit 0) +
  产出物确认（文件存在/大小/非空白），**不需要也不能用 pytest 验证**（pytest 不执行
  R，webui/tests 不覆盖 results/ 脚本）。不要在无 Python 改动时反复跑无关 pytest 补
  "验证证据"——用户在等待出图时看到 Agent 反复跑无关验证会以为卡死/崩溃。用户要的
  是图，不是验证仪式。

## R 调用效率审计 (user: "为什么调用这么多R呢?" 2026-08-12)

多亚群逐群画图时用户会质疑 R 调用次数。逐条审计，诚实区分必要 vs 浪费：
- 必要：显著性计算（一次性全亚群存 CSV）、按用户脚本出图、CNS 优化版
- 浪费：自作主张画用户没要的图型（-log10 p 条形图）、每次 `Rscript --vanilla`
  冷启动重复加载包 30-60s、3-4 次 bug 重跑本可 pre-flight 避免
- 改进：① 显著性一次性算完存 CSV，画图只读 CSV 不重算 ② 复用 execute_r 持久内核
  同一 worker（比冷启动快 3-5 倍）③ 流程收敛两步：探索图（用户定组别）→ 定稿两版
  （FDR + p 值一次出）
- 孤儿 `_kernel_worker.R` 进程不是本平台 bug（reasonix 测试遗留，用户澄清），
  无需平台修复；但清理命令保留在
  `windows-bioinformatics-batch-processing/references/kernel-worker-leak-cleanup.md`

## Debate trigger

User asked "为什么不触发辩论呢?" when direction was contested. Contested effect
direction IS a debate-class decision: run debate_analysis (L2) with the raw direction
evidence + literature. It surfaced: (1) MYH7-transcription confounder, (2) FDR_global
0.117 not significant with n=7, (3) both belong in final wording. Verdict was
need_more_info/low-confidence — direction still reportable but phrase as
"diabetes ↓ Pure Type I proportion (7/7 individuals, p=0.007, per-celltype FDR=0.035)"
without overclaiming global significance.
