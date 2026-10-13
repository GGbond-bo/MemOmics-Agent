# 模板化复刻：扒用户代码 / 还原参考图 / 换数据出 N 张

场景（2026-09-30 实测）：用户丢来 6 个路径（5 个 merged DEG xlsx + 1 个 `VolcanoPlot.html`）+
一句「**你能不能根据火山图直接换个代码，分别做出五个火山图…我只要 8 个亚群，之前跟你说过的。
你自己看看代码，我只要里面最完整的图**」。

拆解：参考物 = 他**自己 notebook 导出的 HTML**（不是脚本文件）；目标是 5 张同风格图；
「8 个亚群」是他前几轮定稿的子集；「最完整的图」是代码里最靠后那版累积结果。

---

## 1. 从 nbconvert HTML 扒三样东西

```python
import re, html
s = open(HTML, encoding="utf-8", errors="ignore").read()

# ① 代码单元（nbconvert 的 highlight 块）
cells = re.findall(r'<div class="highlight[^"]*"><pre>(.*?)</pre></div>', s, re.S)
clean = lambda c: html.unescape(re.sub(r'<[^>]+>', '', c))
cells = [clean(c) for c in cells]          # 本次 24 个单元：0-2 载入、3-4-6-7 是 aging 的 p/p2/p3…

# ② 内嵌成品图 —— 关键：{200,} 必须配 re.S 允许空白
imgs = re.findall(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]{200,})', s, re.S)
#    严格字符集（不含 \s）会 0 命中 —— 本会话踩过，白等一轮「没有内嵌图」的错误结论
raw = base64.b64decode(re.sub(r'\s+', '', b64) + "=" * (-len(b64) % 4))
#    本次 10 张：9 张 1920×1440 真图（3 组 × p/p2/p3）+ 1 张 8×5 占位

# ③ 单元格输出文本（他 print(head(df)) 留下的列名/类型，比猜列名省事）
outs = re.findall(r'<pre>(.*?)</pre>', s, re.S)
#    本次由此读到：X.1 / X / gene / p / coef / ci.hi / ci.lo / fdr / celltype / age_group / group / type
#    ⇒ 源 CSV 自带 group 与 type 列，我只需从 coef 正负补 group
```

**判据：代码单元数 = 24、图 9 张、输出块含列名** —— 三样齐了就不必再问用户「代码在哪」。
R 侧补充：`execute_r` 里跑脚本用 **`source("x.R", encoding="UTF-8")`**（`exec()` 是 Python 的，
R 里不存在 —— 本会话第一跑就报 `could not find function "exec"`）。

---

## 2. 「最完整的图」= 最靠后的累积版本

他的 notebook 是 `p → p2 → p3` 递进：p = 灰底柱 + 抖动点 + 标签 + 图例 + `theme_bw`；
p2 = p + `geom_tile(y=0)` 彩色亚群标签块；p3 = p2 + `labs(x=…)` + `theme_minimal` 终版主题
（轴题 13 bold、`legend.position="top"` 左对齐、`legend.text` 15、`guides(override.aes(size=4.5))`、
`axis.text.x = element_blank()` —— 因为标签块已充当 x 轴文字）。

⇒ 复刻 p3 一版即可，**不要**把 p/p2 也出出来。

---

## 3. 从渲染 PNG 反推参考图的顺序与配色（不靠 OCR）

```python
mx, mn = a.max(2), a.min(2); sat = (mx - mn) > 40           # 饱和像素
# ① 定位「色块带」：逐行数色相种类数，不要数饱和像素总数
for y in range(300, 1300, 4):
    hs = [int(colorsys.rgb_to_hsv(*c/255)[0]*36) for c in a[y][sat[y]]]
    major = [h for h, c in zip(*np.unique(hs, return_counts=True)) if c >= 30]
    if len(major) >= 5: print(y, len(major))     # 本次命中 y≈700–796，9 种色相各 ~200 px
# ② 每块颜色：沿该行按「三通道差和 >90 或近黑边框」切段，取段内众数色
#    → 还原出 9 块：#DBA478 #F9A213 #969730 #2F3084 #43A8A8 #76A5D9 #197638 #3C75A9 #A44395
# ③ 块内文字：裁带 → 放大 3× → OCR（原尺寸读不出）
```

⚠️ 两个反例（本会话都踩了）：
- 用「饱和像素最多的行」找带 → 命中 y=870，那是**散点云**（纯 `#0000FF`），不是标签块
- 直接对原尺寸图 OCR → 只吐出基因名（ASB5/MYH1/PDLIM3…），块内文字一个没读到；放大 3× 才有

---

## 4. 最值钱的发现：参考图与当前数据「不同命名代」

放大 OCR 后读到块内文字：`ANKRD1_II` / `BMPR1B_MF` / `GALNTL6_I` / `GALNTL6_II` /
`Type_I` / `Type_I_1` / `Type_II` / `Type_II_1` / `Type_IIX` —— **9 个，且是另一套命名**，
与现存 merged 表的 10 个 sheet（`Pure Type I/IIA/IIX`、`RP_high(I)/(II)`、`LRP1B+(I)`、
`OTUD1+(I)/(II)`、`RSS`、`Specialized MF`）**没有一一对应关系**。

结论：**那份 notebook 是样式模板**，不是本数据集的分析产物。因此：
- 参考图的 x 顺序、9→N 的配色映射**本来就无从复刻**，别硬凑
- 改用**本项目内用户已定稿的同类图顺序**（本例：他多轮改过的柱子图脚本里的 `ORDER`，
  剔除 RSS / Specialized MF 后正好 8 个）
- 交付说明里**写明**「原顺序不可复原（原始 `MF_all_sDEG.csv` 已不在磁盘）+ 我沿用了哪套顺序」

> 通用判据：**一旦发现参考图的类目名与当前数据的类目名对不上，就停止\"忠实复刻\"的尝试**，
> 转为「样式复刻 + 顺序/配色以用户现有定稿为准」，并把差异摊在明面上。

---

## 5. 多对比单脚本循环骨架（R / ggplot2）

```r
ORDER <- c(...)                                  # 用户定稿的类目顺序
COMPS <- list(list(label="Aging", file="merged_Y_Pre_vs_O_Pre.xlsx",  cmp="Y_Pre_vs_O_Pre"),
              list(label="DM",    file="merged_O_Pre_vs_OD_Pre.xlsx", cmp="O_Pre_vs_OD_Pre"), ...)
for (cs in COMPS) {
  lst   <- read_sheets(file.path(DIR, cs$file), ORDER)          # 只读这 8 个 sheet
  d     <- bind_rows(lst) %>%
             mutate(celltype = factor(celltype, levels = ORDER),
                    group    = ifelse(coef > 0, "up", "down"))  # 源表无 group 时按 coef 正负补
  # …—— 以下 4 段逐字照抄用户代码（预处理 / top_genes / dfbar / p → p2 → p3）——
  ggsave(..., .png", dpi = 300); ggsave(..., .pdf", device = cairo_pdf); ggsave(..., .svg")
  write.csv(top_genes[...], file.path(SRC, paste0(stem, "_source_data_toplabels.csv")))
}
```

- **每图标题必须带对比名**（`Aging (Y_Pre_vs_O_Pre)`）—— N 张分开的文件不给标题就无法区分，
  这是硬约束，不是审美改动；照抄用户代码里的通用标题（`Enhanced Volcano Plot with
  Background Range`）会得到 5 张分不清的图
- 一口气把 5 个对比的计数汇总成一张 summary CSV 落盘（比对基线用），本轮耗时 **0.58 min**

---

## 6. R 读 xlsx：后端自适应 + openxlsx 工作簿坑

```r
RLIB44 <- "<另一 R 版本的 user library>"          # 内核库里没有 readxl 时先试借
USE_READXL <- tryCatch({ suppressWarnings(library(readxl, lib.loc = RLIB44)); TRUE },
                       error = function(e) FALSE)
read_sheets <- function(f, sheets) {
  if (USE_READXL) lapply(sheets, function(sh) as.data.frame(readxl::read_excel(f, sheet = sh)))
  else { wb <- openxlsx::loadWorkbook(f)          # ← 只解析一次工作簿
         lapply(sheets, function(sh) as.data.frame(openxlsx::read.xlsx(wb, sheet = sh))) }
}
```

- 🔴 **`openxlsx::read.xlsx(f, sheet = <名字向量>)` 会报 `invalid type of argument[1]: 'symbol'`**
  （Rcpp 层错误，非参数拼写问题）⇒ **必须传 Workbook 对象逐 sheet 读**
- 逐 sheet 传**文件路径**读 8 次 = 把 20 MB 工作簿解析 8 遍；`loadWorkbook()` 一次后复用才快
- 20 MB × 8 sheet × 5 文件全流程 0.58 min（openxlsx 后端），无需预转格式

---

## 7. 导出核验（交付前必做）

```r
raw <- readBin(pdf_path, "raw", file.info(pdf_path)$size)
grepRaw("/FontFile", raw, all = FALSE)   # 空 ⇒ 字体未嵌入（投稿会被退）
```

- `ggsave(.pdf)` 默认 base `pdf()` 设备 → **无 `FontFile`**；显式 `device = cairo_pdf` 后
  5 个 PDF 全部命中（2.8–3.4 MB 无嵌入 → 1.8–2.2 MB 已嵌入）
- SVG 侧验「文字可编辑」：数 `<text` 元素（本次每图 ~100 个）+ 确认具名色块色值在文件里
  （8/8 命中）
- PNG 侧验尺寸/墨迹：2400×1800 @300dpi、墨迹 13–27%、每图 8 色块 8 色相
- 灰度/色觉量化（见 scientific-figure-export 的灰度亮度公式）：本次 `RP_high(I)` vs
  `RP_high(II)` 灰度 ΔL 仅 **0.2**、`OTUD1+(I)` vs `(II)` **2.3** ⇒ 靠**色块内文字标注**消歧
  （这正是用户原设计的冗余通道）；白字对比度 2.6:1 偏低但属用户原配色，**不擅自改**

---

## 8. 消费 `merged_*_vs_*.xlsx`：既有结构 + 计数口径不可比

> 本节内容原属 `deg-analysis`（该 skill 为手工撰写，禁止自动改），故落在此处。

### 8.1 表结构（不要再重新聚合，直接读来出图/统计）

| 项 | 实测（2026-09-30） |
|---|---|
| sheet | `ALL_merged` + 每个亚群一个 sheet（本例 10 个：Pure Type I/IIA/IIX、RP_high(I)/(II)、LRP1B+(I)、OTUD1+(I)/(II)、RSS、Specialized MF） |
| 列 | `gene, coef, se, z, p, fdr, coef_D, p_D, fdr_D, celltype, comparison, direction, method, nRUV_used, n_cells` |
| **缺口** | 表里**没有 `group` 列** —— up/down 得自己按 `coef > 0` 补；`direction` 列只是方向语义（如 `O_Pre > Y_Pre (coef>0)`） |
| `method` | 同一批对比里**混用** `bayesglm` / `glmer`（`nRUV_used` 也不同：10 vs 5/8），跨对比比较时留意 |

⇒ **子集图表（如「只要 8 个亚群」）用 sheet 白名单读，不要读全表再筛**：既省时，
又天然排除不想进的类目（本例剔除 RSS / Specialized MF）。

### 8.2 🔴 同一批 DEG 在不同阈值口径下**计数完全不可比**

**症状**：用户拿两版数字对数对不上（本例 Aging：柱子图版 ΣUp 16,535 / ΣDown 380 vs
火山图口径算出 42,488 / 1,334）。

**根因**：柱子图版叠加了 `|coef| > 0.25 & FDR < 0.05`；火山图按用户脚本的
`FDR ≤ 0.001 + coef 正负` 分级。**数万基因规模下没有 |coef| 下限时几乎全基因都"显著"** ——
本例 Aging 出现 75% up vs 2.4% down 的极端不对称。

**纪律**：
- 汇报任何 up/down 计数，**必须写明口径**：FDR 阈值 + 有无 |coef|/|LFC| 下限 + 基因宇宙 N
- 用户脚本自带的显著性分级**照画**，但**主动提示**「这版数字与你上一版图不可直接对比，口径不同」
  —— 这类异步是用户最容易当场抓的点（他会逐位对数）
- 要跨版本可比 ⇒ 同一口径重算，或显式声明各自判据