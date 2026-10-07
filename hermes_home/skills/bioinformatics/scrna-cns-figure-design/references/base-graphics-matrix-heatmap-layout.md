# base graphics 矩阵热图：版式不变量与「渲染后核验」配方

适用：**零第三方依赖**（base graphics + grDevices）画 CNS 级 score × 亚群 矩阵热图。
触发场景：用户要求"把这张热图转置 / 加一行 / 删一行 / 改成 CNS 级 / 长而不宽"，
或任何 program × subcluster（基因集 × 细胞亚群）矩阵热图。

实测来源：memomics-2274ab75（2026-09-18）。人骨骼肌 MF 亚群 × AUCell 打分矩阵，
FigA3 由横向（18 程序 × 10 亚群）改为**纵向转置**（20 程序 × 10 亚群，116.6 × 175.8 mm）。
用户追加需求：加 Type I/II/IIX score（去掉 Stress）、新三个单列为身份轴、亚群放 X 轴。

---

## 1. 版式不变量（每条都真踩过）

| # | 规则 | 为什么 |
|---|------|--------|
| 1 | **行序自顶向下赋值**：`yc <- YMAX`，循环里 `yc <- yc - 1` | R 的 y 轴**向上增长**。若按 `yc <- 0` 起累加，`AXES` 列表的**第一个轴会落在图底**——与"参照轴置顶"的设计正好相反。本次第一版渲染出来 `Fiber identity` 在底、`Fibrosis` 在顶，就是这个错 |
| 2 | 总高 = `NROW + GAPY * (length(AXES) - 1)`；循环里**最后一个轴之后不再减间隙** | 对每个轴都减一次 GAPY 会多减一格，`yc` 期末落在 `-GAPY` 而非 0（`stopifnot` 报 "不是所有的 abs(yc) < 1e-09 都是 TRUE" 抓到的就是它） |
| 3 | 布局循环后立刻 `stopifnot(abs(yc) < 1e-9)` | 一行断言把上条的算术错当即暴露，省掉一整轮"图看着怪但说不清哪怪" |
| 4 | `CELL`（单元格边长，英寸）作**唯一自由参数**，纸宽纸高全部由它反解：`W = ncol*CELL + mai[2] + mai[4]`；`H = (rows + gaps + top_furniture)*CELL + mai[1] + mai[3]` | "长而不宽"才能定量落地。本次 CELL=0.255 in → 116.6 × 175.8 mm（1:1.5）。⛔ 反过来"先定纸宽再反解 CELL"只适合横向版式；转置后行数 > 列数会失控 |
| 5 | `par(xaxs='i', yaxs='i')` 必设 | 默认 `'r'` 每端外扩 4% → 色块被压缩约 7%（几何不可控）。同族：`pheatmap` 的 `cellwidth/cellheight` 单位是**磅非 cm**，不传则随画布 npc 缩放 |
| 6 | 色标**画在同一坐标系内**，全程不 `par(fig)` 重置 | `par(fig)` 插值会重置坐标系 → 色块被裁（历史 bug）。转置后色标改横向置顶，同样不重置 |
| 7 | 色表索引 `floor(n * 256) + 1`，写 `255` 会整体偏一档 | 256 档 LUT 的下标边界 |
| 8 | 单元格白细线：`rect(..., border = "white", lwd = 0.45)` | CNS 热图惯例，且让"几行几列"肉眼可数 |
| 9 | Arial + `svglite` → SVG 文字可编辑；字体能力**探测后回退**：`tryCatch({pdf(NULL); par(family=f); dev.off(); TRUE}, error=…, warning=…)` | 纯 base 环境下字体/设备能力要实测再回退，别硬编码 |
| 10 | 左/下行标签 `axis(2, at = rowy[PROGS] + 0.5, las = 1, tick = FALSE, line = 0.40)` | 行中心对齐（`+0.5`）；`line` 太大会在标签与热图之间留死空白（本次 `line=1.30` 实测 0.67 in 空白，改 0.40 + 收紧左栏后色块 0.285→0.306 in） |

## 2. 渲染后核验：**脚本 stdout 不是证据** ⭐

本次最重要的一条。脚本里 `cat("行序（自上而下）:", ...)` 打印的是**设计意图**——
第一版行序翻转的那次，stdout 照样印着 `Type I score > ... > Fibrosis`，与成图完全相反。
**凡"标签顺序 / 元素是否还在 / 朝向"这类断言，必须落到栅格或 SVG 上核验。**

```
① vision_describe(<png>) → 看 OCR 标签清单 + 坐标
   - 首/末标签的 y 坐标（本次：Type I score y=265 = 顶；Fibrosis y=1808 = 底）
   - 分类标签 x 是否单调递增（本次 10 个亚群 x 222→911，最左 = 指定顺序第一个）
   - 被删元素是否真消失（本次全图无 "Stress" 字样）
② "其他不变"要像素证据，不能口头保证
   - 同列色值**多重集**一致 + 行值序列变化 ⇒ 纯置换（本次 18/18 列多重集完全一致）
   - 删掉的图形元素：数它那个精确 hex 的像素数 before→after
     （本次左侧三色条 #3F3F3F / #B0B0B0 / #C98A3C = 5115 / 5104 / 2542 px → 0 / 0 / 0）
③ OCR 已知噪声（别当 bug 去修）
   - 90° 旋转小字必被读花或漏读："Fiber identity"→"Taertrty"、"Nutrient"→"Lad"
     ⇒ 竖排轴名的存在性改用 **SVG 里的 text 元素**核验
   - 罗马数字常错："Type II"→"Type Ill"、"Type IIX"→"Type lIX"
   - 横轴刻度只读出 1–2 个属正常（漏读，非未绘制）；可用"数据单位→像素"换算复核位置
```

## 3. 改版纪律（本项目用户约定，与 SKILL.md 的"保留上一版样式骨架"同源）

- **改版前先归档上一版**：`file.copy(old, "archive_superseded/<base>_<版本>_<朝向>.<ext>")`，
  四格式全归档；**绝不删除**已交付版本。
- **逐版本留档**：`<base>_manifest_QA.csv`（每格式 存在性+字节数）+ `<base>_geometry.csv`
  （W/H/mm/CELL/程序数/轴数/dpi/字体/svg 后端）。换版本换文件名，不覆盖同名 CSV。
- **改动严格限定用户点名范围**；同族的兄弟图要么同步改、要么在汇报里明确说明改没改，
  让用户能一键回退。
- **删掉承载信息的图形元素时必须提醒**：本次按要求删掉左侧纤维型色条后，
  "LRP1B+(I)/OTUD1+(I)/RP_high(I) 属 Type I、OTUD1+(II)/RP_high(II) 属 Type II"
  这层信息不再由图形承载 → 汇报时点明"图注需补一句"，别默默交付。

## 4. 加新 score 行之前：先查列是否已存在

用户甩来"基因集定义表"（xlsx，Class/Signature/Annotation/Genes）时，
**它常常只用来确认定义来源，不需要重算打分**：本次 `scoreI_AUC / scoreII_AUC / scoreIIx_AUC`
已现成躺在 meta CSV 里（定义来自 Murgia et al.），重算 AUCell 需要表达矩阵而本地没有。
判别式：

```r
col_of <- function(s) if (paste0(s, "_AUC") %in% hdr) paste0(s, "_AUC")
                      else if (s %in% hdr) s else NA_character_
message("列命中 ", length(have), "/", length(PROGS))   # 不足立即停手问用户
```

⛔ 不要带着 NA 出图——`aggregate` 出来一片空白，看着像"这个程序没信号"。

## 5. 何时该起一个独立轴

用户要求"把新加入的三个分类成 muscle 的身份"（Type I / II / IIX score）时的判据：
新 score 与既有轴**性质不同** → 单独立轴。它们是**注释参照/身份标记**，
不是功能程序（代谢/营养/收缩/炎症/失代偿），所以命名 `Fiber identity` 并置顶作参照轴，
而不是塞进任一功能轴。轴色取一个**未被占用**的色（本次 `#C98A3C`），
并在汇报里说明"为什么这样分"（用户会问"你看看怎么分类比较好"）。

⚠️ 交付这类"新轴是否真实"的图时，L2 辩论会追问三件事，**出图前先备好答案**：
① 该 score 是不是**技术轴**（与 nCount/nFeature/percent.mt 的偏相关）；
② 与已有轴的**共线性**（Type II vs IIX 基因集重叠）；③ **省略某个 score 是否属选择性报告**
（本次 Type IIA 因"效果不好"不展示 → 需要预注册式说明或敏感性分析）。
本次裁决 = `need_more_info`：版式执行被认可，但"分类恰当性"仍缺上述证据。