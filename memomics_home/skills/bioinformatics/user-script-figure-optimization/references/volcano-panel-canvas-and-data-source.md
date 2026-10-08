# 类目色块图（火山图/柱形图的 8 亚群标签带）：画布宽度 + 数据源判定 + 验收配方

来源：2026-09-30 会话（人骨骼肌 MF 8 亚群 × 5 DEG 对比火山图，复刻用户 Jupyter notebook 样式）。
场景：用户给「一张参考图 / 一段能跑的代码 + 新数据」，要求「根据这个火山图换个代码，做出 N 张」，
随后连续纠三处：① 图太窄、亚群名挤在一起 ② 用错了数据（应使用已过滤表）③ 只要最终版。

---

## 1. 标签挤在一起 = 画布不够宽（先算，再改）

### 1.1 量字（R，不落盘）

ggplot2 的 `size` 单位是 pt：`pt = size × 2.845`（`size = 6` → 17.07 pt）。

```r
pdf(NULL); par(ps = 12)                      # 空设备；默认 pointsize = 12
LAB <- c("Pure Type I","Pure Type IIA","Pure Type IIX","LRP1B+(I)",
         "RP_high(I)","RP_high(II)","OTUD1+(I)","OTUD1+(II)")
w <- sapply(LAB, function(s) strwidth(s, units = "inches", cex = (6*2.845)/12))
max(w)                                        # 1.415 inch（"Pure Type IIA"）@size=6
need_panel <- length(LAB) * max(w) * 1.06     # 12.0 inch
canvas_w   <- need_panel + 0.55               # ≥ 12.55 → 取整 13~14 inch
```

实测对照：

| 画布 | 每色块宽 | 需要 | 结果 |
|---|---|---|---|
| 8 × 6 in | 0.89 in（267 px @300dpi） | 1.415 in | **溢出 1.6×，名字重叠** |
| 14 × 7 in | 1.62 in（486 px @300dpi） | 1.415 in | 占比 0.87，零重叠 ✓ |

要点：
- **加宽而不是缩字号**（缩字改用户原稿观感）；`strwidth` 的 `cex` 必须按 `size×2.845/12` 换算，
  否则量出来偏大/偏小。
- 亚群数变化时按公式重算，不要沿用上一次的宽度。
- 画布变大后点/字**相对**变小（pt 绝对值）—— 交付说明里主动点出，给「联动放大」选项，
  但用户强调「只改指定项」时**保留他的 pt 值**。

### 1.2 验收：每块文字墨迹 vs 块宽（Python，确定性）

```python
import numpy as np
from PIL import Image
mycol = ["#2f3084","#76a5d9","#43a8a8","#3c75a9","#197638","#a44395","#f9a213","#dba478"]
rgb   = [np.array(tuple(int(c[i:i+2],16) for i in (1,3,5))) for c in mycol]
a = np.array(Image.open(png).convert("RGB")).astype(int); H, W, _ = a.shape

masks = [(np.abs(a - c).sum(2) <= 10) for c in rgb]
# 标签带 = 「8 种色同时出现」的行（别用饱和像素总数，散点云会误判）
band = np.where(np.array([sum(m[y].sum() > 20 for m in masks) for y in range(H)]) >= 8)[0]
y0, y1 = band.min(), band.max()

for m, lab in zip(masks, LAB):
    xs = np.where(m[y0:y1+1, :].any(0))[0]; tx0, tx1 = xs.min(), xs.max()
    inner = a[y0+4:y1-3, tx0+6:tx1-5]                    # 内缩，避开黑边框
    med = np.median(inner.reshape(-1,3), axis=0)
    ink = (np.abs(inner - med).sum(2) > 170)             # 与块底色差异大的像素 = 文字
    ixs = np.where(ink.any(0))[0]
    iw  = int(ixs.max() - ixs.min() + 1) if len(ixs) else 0
    print(f"{lab:14s} 块[{tx0},{tx1}] 宽={tx1-tx0+1:4d} 文字宽={iw:4d} 占比={iw/(tx1-tx0+1):.2f}"
          f" {'OK' if iw < (tx1-tx0+1)*0.92 else '溢出!'}")
```

坑（本人踩过两次，都是切片取空 → numpy 报 `Mean of empty slice`）：
- **`ys.min()` 是上边、`ys.max()` 是下边**，行切片必须 `a[y_top+2 : y_bot-2]`；
  写成 `a[y_bot+3 : y_bot-2]` 会得到空数组，全部误报「无文字墨迹」。
- 累积范围要把 `ys/xs` 分开存，别把 `(ys.min(), xs.min())` 混用成 x 区间（会把整带当成一个块）。
- 判据阈值：占比 **< 0.92** 算合格；同时检查 `块[i] 墨迹末端 < 块[i+1] 起点`（跨块 = 重叠）。

---

## 2. 数据源判定：过滤版 vs 全表版（本类任务最容易翻车处）

### 2.1 一行判定

```r
cat("max(fdr)=", max(d$fdr), " min|coef|=", min(abs(d$coef)), "\n")
```

| 结果 | 含义 |
|---|---|
| `max(fdr) ≈ 1.0`，`min|coef| ≈ 1e-5` | **未过滤全表** → 会带出「不显著」灰类 |
| `max(fdr) < α`（本次 0.039），`min|coef| = θ`（本次 0.25） | **已过滤导出** → 无效类别恒不存在 |

再与文件/上游命名交叉印证（文件名含 `fdr05` / `coef025` / `sDEG` 等）。

### 2.2 从用户成品图反证他当初的输入（最硬的证据）

```python
m = (np.abs(a - np.array([204,204,204])).sum(2) <= 12)   # grey80 = ggplot 的 "Not Significant"
print("grey80 px:", m.sum(), "/", a.shape[0]*a.shape[1])
```

本次：用户原图 **22 px / 2,764,800 px** ⇒ 他的输入是已过滤表，灰类本就不该出现。
⇒ **图上多出一个用户说「不该存在」的类别 = 数据源用错，不是画法错。**

（注意：过滤后仍会剩几百个散落的 204 灰像素 —— 那是浅灰底 `#f0f0f0` 的抗锯齿边缘，
判据看**数量级**与**是否成簇**，不要见到 1 px 就报警。）

### 2.3 找到那份过滤表 + 验明正身

```bash
for root in "D:/" "E:/" "C:/Users/<user>"; do
  find "$root" -maxdepth 6 \( -iname "*fdr05*" -o -iname "*coef025*" -o -iname "*<表名片段>*" \) 2>/dev/null | head -20
done
md5sum "<用户给的那份>" "<我方会话导出的副本>"     # 相同 → 同源，直接用
```

本次命中用户「下载」目录那份 = 我 task2 导出的副本（md5 `a45d67ee…` 一致）。

### 2.4 锁口径（防漂移）

```r
stopifnot(sum((dd$coef > 0) != (dd$regulation == "Up"), na.rm = TRUE) == 0)  # 符号列自洽
stopifnot(max(dd$fdr[dd$celltype %in% ORDER]) < 0.05)                        # 确认已过滤
```

类别映射里**整类删掉**「不显著」（不是设透明、不是不画点）——否则 `scale_*_manual` 会把
空类别自动补回图例。本次最终图例 OCR 直读只剩 3 项：
`Down (FDR <= 0.001)` / `Moderate Sig (0.001 < FDR < 0.05)` / `Up (FDR <= 0.001)`。

---

## 3. 图例内容怎么验：裁切 + OCR，别按色找键

失败的尝试（别重复）：在顶部 18–30% 条带里数 `(0,0,255)` / `(255,0,0)` 精确像素 → 得 **0 px**，
因为图例键点带 alpha / 抗锯齿，颜色并非纯色 → 会误判成「图例没有彩色项」。

可行的做法：

```python
im.crop((0, 0, 1400, 430)).resize((2100, 645)).save("_legend_crop.png")   # 裁图例带 + 放大
```

再对该裁图跑 OCR（本地管线 `vision_describe`）→ 逐条读出图例文字。
本次输出即 `Regulation & FDR` + 3 条类别，直接证明 `Not Significant` 已消失。

**分工**：散点/类别的存在性 → 数**面板内**的精确填充色像素；图例的条目/文字 → **裁切+OCR**。

---

## 4. 版本卫生

```bash
mkdir -p _deprecated_8inch_unfiltered
mv -v fig_*_userstyle.{png,pdf,svg} _deprecated_8inch_unfiltered/
```

- 移不删（可回溯），汇报写明「要彻底删除说一声」
- 终版命名 `fig_*_FINAL.*`，与旧代次一眼可分
- 交付格式一次给全：`png`(300 dpi 预览) + `pdf`(`cairo_pdf` 字体内嵌) + `svg` + `tiff`(lzw)
- 字体嵌入验收：`grep -c "FontFile" fig.pdf`，>0 才算嵌入（Windows R 直接 `ggsave(device="pdf")`
  常不嵌字体，投稿会被拒）

---

## 5. 箭头类图元：用矢量，别用字形（同一会话前段实测）

- 字体字形 `←`/`→` 在 Arial 里的墨宽是 `↑`/`↓` 的 **2.4 倍**（31 px vs 13 px @同字号），
  小字号下水平箭头在光栅层**完全不出墨**（SVG 里有字符、PNG 里 0 px）
- 正确做法：`FancyArrowPatch`（head 尺寸按 pt，各向同性、几何可控）
- 验收：在箭头窗口内量**竖直 run-length**（本次 33 px > 数字字高 26 px ⇒ 确实画出来了），
  再验左右/上下归属（Σ 行内「蓝墨全在中心线左、红墨全在右」这类硬判据）