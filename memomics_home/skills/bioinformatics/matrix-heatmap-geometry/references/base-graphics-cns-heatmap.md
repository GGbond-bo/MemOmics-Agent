# 零第三方包手绘 CNS 级矩阵热图 —— 完整配方与实测数字

来源：2026-09-15 人骨骼肌 10 个肌纤维亚群 × 17–18 个基因集 AUCell 行内 z-score 热图
（`scripts/fig_A3_CNS.R`，base graphics + grDevices，零第三方包；ComplexHeatmap 在本机不可加载）。
本文件是 `matrix-heatmap-geometry` 的实证附录：**每条结论都带当时的实测数字**。

---

## 1. 目标与约束

- 用户要求：**CNS 级别优化**（期刊尺寸、可编辑矢量、版式层次）
- 硬约束：无 ComplexHeatmap、无 pheatmap → 必须 base graphics 手绘
- 用户全局偏好：**300 dpi + 必附 SVG**；交付汇报用「类别 → 相对路径」；同名旧版先归档不删除

## 2. 最终几何参数（可直接复用）

```r
GAPX <- 0.22                              # 轴间间隔（数据单位）
MAI  <- c(1.10, 1.00, 0.62, 0.74)         # 下/左/上/右（英寸）
CELL <- (183 / 25.4 - MAI[2] - MAI[4]) / XMAX   # 183 mm = Nature 双栏；由纸宽反解
W    <- XMAX * CELL + MAI[2] + MAI[4]     # → 7.205 in = 183.0 mm（stdout 实测）
H    <- NTOP * CELL + MAI[1] + MAI[3]     # 17 列 → 5.158 in（131 mm）；18 列 → 4.939 in（125.5 mm）
```

实得色块边长：**0.306 in**（17 列）/ **0.286 in**（18 列）。
第一版是 `MAI[2]=1.30, line=1.30` → 色块 0.285 in 且左侧 0.67 in 死白；收紧后色块变大。

> 行数越多、`NTOP = NSUB + 1.25` 里的 1.25 数据单位是**顶部组色条 + 组名 + 标题**的预留高度，
> 不要塞进 `mai[3]`（否则顶部元素会被画到画布外）。

## 3. 绘制顺序（同坐标系，结构性免疫）

```
① 热图本体（含白细分隔线）
② 顶部组色条 + 组名（NSUB+0.10 ~ +0.34 色条、+0.46 组名）
③ 左侧行注释条 + 类型名（x 用负数据单位：条 -0.34~-0.16、类型名 -0.44 且 srt=90）
④ 行标签 axis(2, at=行中心, line=0.40)
⑤ 列标签 text(srt=45, adj=c(1,1), y=-0.10)
⑥ 标题（可选）
⑦ 右缘色标（x = XMAX+0.42 ~ +0.66 数据单位，xpd=NA 越出绘图区）
```

**关键**：③ 必须在 ⑦ 之前，且 ⑦ 绝不用 `par(fig=..., new=TRUE)` + `plot.window()`。
本图第一版脚本把色标写成 `par(fig=c(CBAR1,CBAR2,0.22,0.80), new=TRUE)` —— 坐标系被重置成整图 0–1 窗口，
其后的分组色条用数据坐标 `rect(x=-1.25, ...)` 绘制 → **整条落在画布外被裁**；SVG 里 5 个分组色 0 命中。

## 4. 导出

```r
png  : png(..., units="in", res=300, type="cairo", family=FAM)
pdf  : cairo_pdf(..., family=FAM)
svg  : svglite::svglite(..., bg="white")          # 文字保持可编辑；cairo 的 svg() 会转 glyph
tiff : tiff(..., units="in", res=300, compression="lzw", type="cairo", family=FAM)
FAM  : tryCatch({pdf(NULL); par(family="Arial"); dev.off(); TRUE}, error=…, warning=…) → "Arial" / "sans"
```

本机实测落盘体积（同一张图四格式，可作"是否真的写成功"的量级参照）：
PNG 129–132 KB｜PDF 45–46 KB｜SVG(可编辑) 65–67 KB｜TIFF(lzw) 427–429 KB。

## 5. 双路核验（实测命令与判据）

**① SVG hex 计数**（仅 svglite SVG 有效；cairo SVG 会全假阴性）

```bash
grep -o -i -E "#2c7fb8|#1b9e77|#7ba05b|#d64550|#8c5fa8|#3f3f3f|#b0b0b0|#c98a3c" FigX.svg | sort | uniq -c
```

实测结果与判据：

| 色 | 命中 | 期望 | 判定 |
|----|------|------|------|
| #2C7FB8 Metabolism | 5 | 4 成员 + 1 组名文字 | ✅ |
| #1B9E77 Nutrient | 5 | 4 + 1 | ✅ |
| #7BA05B Contractile | 4 | 3 + 1 | ✅ |
| #D64550 Inflamm-aging | 5 | 4 + 1 | ✅ |
| #8C5FA8 Decompensation | 3 | 2 + 1 | ✅ |
| #3F3F3F Type I（行注释） | 4 | 4 行 | ✅ |
| #B0B0B0 Type II | 4 | 4 行 | ✅ |
| #C98A3C Specialized | 2 | 2 行 | ✅ |
| #8F8F8F Artifact（仅归档口径版） | 2 | 1 成员 + 1 组名 | ✅ |

**② OCR 核验**（`vision_describe` 本地管道）判据：

- 标签**数量**齐（17 程序名 + 5 组名 + 10 亚群名 + 3 个类型名 + 色标文字）
- **行距恒定** = 行中心对齐：实测 91 px（色块 0.306 in × 300 dpi ≈ 92 px），OCR y 坐标 LRP1B+(I) 329 → OTUD1+(I) 420 → OTUD1+(II) 511 …
- 修复前的"偏半格"版本：17 个标签整体比行中心低 ≈50 px（恰好半格）
- 全部标签落在画布内（max x 2050 < 宽 2161；列标签底 y 1223 < 高 1547）

## 6. 口径决策的实证（哪些程序该上图）

被要求"去掉某个打分"时，用数字而不是印象裁决（30000 细胞随机子样本 Spearman，vs 细胞复杂度/QC）：

| 程序 | rho(nCount_RNA) | rho(nFeature_RNA) | rho(percent.mt) | 跨亚群动态范围（相对幅度） |
|------|-----------------|-------------------|-----------------|---------------------------|
| scoreOxPhos（合法对照） | 0.555 | 0.568 | 0.392 | 0.149–0.241（**55%**） |
| **scoreStress（原判"解离伪影"）** | **0.548** | **0.533** | **0.185** | 0.122–0.145（**15%**） |
| scoreAtrophy | 0.412 | 0.402 | 0.177 | 0.144–0.182（26%） |
| scoreTNFA | 0.334 | 0.325 | 0.194 | — |
| scoreROS | 0.222 | 0.231 | 0.185 | — |
| scoreSenMayo | 0.175 | 0.175 | 0.145 | — |
| scoreInflammatory | 0.143 | 0.137 | −0.009 | 0.0371–0.0402（8%） |

结论（**推翻**"Stress index 是解离伪影"的旧说法）：

1. AUCell 打分随细胞复杂度上升是**方法学通用性质**（大基因集 0.4–0.57，小基因集 0.14–0.23）。
2. 该程序复杂度 rho（0.548）**不高于**合法对照 OxPhos（0.555），percent.mt 关联（0.185）还**更低** → 伪影说法无 QC 证据。
3. 真正该排除它的理由是**动态范围只有 15%**：行内 z 化后噪声占比高 → 不宜单列成轴。
4. 图注必须写明"行内 z-score 只反映行内相对差异，不代表绝对水平"（多角色辩论裁决强制项）。

诊断脚本模板要点（本次 `scripts/check_scoreStress_artifact.R`）：4 个 QC 列 × 7 个程序 Spearman 表 + 亚群均值矩阵
+ 4 面板诊断 PNG（散点带拟合线 / rho 柱状带阈值线 / 分布直方 / 亚群均值行 z 热图）→
即 rail_review(post) 需要的"图产出"与"证据"一次满足。

## 7. 多角色辩论在本类任务里的用法

- `debate_analysis(level="L1")` 若报 `TypeError: 'in <string>' ... not list` → 传 `auto_kb=false` 即通（本轮两次均成功）。
- L1 + `auto_kb=false` 时角色可能只回传 `*_draft_only: true` 的 reasoning 草稿 → 裁判裁决仍可用，但**引用时须说明这是草稿强度**，不要当成满血 L2。
- 首轮裁 `need_more_info` 时，把裁判 `missing[]` 当 to-do 逐条补证据，**同一 topic 补证后重裁**：本例 verdict 从 `need_more_info(low)` → `modify(medium)`，
  推荐参数 = 主图 17 程序/5 轴、含灰轴的 18 程序版仅归档、图注强制写相对差异声明。
- 把 `valuation` 里给出的推荐参数落进 task_plan 与汇报，别让它只躺在 JSON 里。

## 8. 交付与归档约定（本机用户偏好）

- 交付名不带版本后缀（`FigX.…`）；版本副本放 `figures/<version>/`；**旧版移入 `figures/archive_superseded/` 而不是删除**。
- 用户可能点名一个归档文件（如 `..._pre_v3.png`）要求"把它 CNS 化" → 先 `search_files` 定位 + `vision_describe` 读它的分组标签，
  确认口径后再用参数化函数并行出两套，汇报里明确建议哪套作主图。