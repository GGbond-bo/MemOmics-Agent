# 图表导出、空白图判定、多条件对比敏感性审计（2026-09-24 实测配方）

来源会话：人骨骼肌 MF_2000 细胞通讯分析（CellChat 1.6.1，Young 900 cells vs Old 602 cells，annotation_L3 十分群）。
本文只记录**可复用配方**，不记录该数据集结论。

---

## 1. ComplexHeatmap 系函数必须用 `draw()` 导出，不能用 ggsave

**现象**：4 张热图 100% 纯白（colors=1、白占比 100.00%），PID 退出码 0、文件 8237 B / 6414 B（看着正常）。
**日志**：`"grid.draw"没有适用于"c('Heatmap', 'AdditiveUnit')"目标对象的方法`
**根因**：函数返回 `ComplexHeatmap::Heatmap` S4 对象（非 ggplot）；`ggsave()` 走 `grid.draw` 失败 → 写出空白画布。

```r
# 通用导出器：PNG + PDF 双格式，设备残留兜底
export_ht <- function(ht, base, w = 5.6, h = 7.2) {
  for (dev in c("png", "pdf")) {
    tryCatch({
      if (dev == "png") png(paste0(base, ".png"), width = w, height = h, units = "in", res = 300)
      else              pdf(paste0(base, ".pdf"), width = w, height = h)
      ComplexHeatmap::draw(ht); dev.off()
    }, error = function(e) { while (dev.cur() > 1) dev.off(); cat(dev, "失败:", conditionMessage(e), "\n") })
  }
  cat(basename(base), file.size(paste0(base, ".png")), "bytes\n")
}
ht <- netAnalysis_signalingRole_heatmap(cc, pattern = "outgoing", width = 8, height = 11, font.size = 7)
export_ht(ht, file.path(fig, "04_signalingRole_outgoing_Young"))
```

**同类函数的正确导出方式**（判据：返回值类型决定导出方式）

| 函数 | 返回 | 正确导出 |
|------|------|---------|
| `netAnalysis_signalingRole_heatmap` / `netVisual_heatmap` | ComplexHeatmap::Heatmap | `ComplexHeatmap::draw()` + png/pdf |
| `netVisual_aggregate(layout="circle")` / `netVisual_chord_cell` | base graphics | `png()/pdf()` 设备包裹，**不加 print()** |
| `netVisual_bubble` | ggplot | `pdf(); print(p); dev.off()`（最稳，不依赖 ggsave） |
| `compareInteractions` / `rankNet` | ggplot | ggsave 可用（实测 1.6.1 正常出图，20–38 KB） |

⚠️ **`dev.off()` 兜底不可省**：一张图导出失败后设备残留，后续所有图都写进那个坏设备（表现为"越往后图越少/越空白"）。

---

## 2. 空白图判定：颜色数是决定性判据，文件大小不是

**反例**：6414 B 的图通过了 `<5 KB` 尺寸闸门，实为 100% 纯白。
**另一反例**：8237 B 的图同样纯白。

```python
from PIL import Image
import os
fig = r"<figures 目录>"
for f in sorted(os.listdir(fig)):
    if not f.lower().endswith(".png"): continue
    p = os.path.join(fig, f)
    im = Image.open(p).convert("RGB")
    cols = im.getcolors(maxcolors=2_000_000)
    n = len(cols) if cols else 999999
    wpct = 0.0
    if cols:
        t = sorted(cols, reverse=True)[0]
        if t[1] == (255, 255, 255): wpct = t[0] / (im.width * im.height)
    bad = (os.path.getsize(p) < 5000) or (n <= 1)
    print(f"{f:44s} {os.path.getsize(p):>7d}B {im.width}x{im.height} colors={n:<6} white={wpct:6.2%}{'  <== BLANK' if bad else ''}")
```

**判据表**

| 情形 | 判定 |
|------|------|
| `colors == 1` | 空白（纯白/纯黑/单色） |
| 白占比 >99% 且 `colors <= 2` | 空白 |
| 白占比 90–97%、`colors` 数百 | **正常**（散点图/网络图/气泡图白底） |
| 白占比 ~0%、`colors` 数百 | 正常（满幅热图/DotPlot） |

⚠️ 逐张单发检查会触发循环检测 → **一个脚本一次打印全部结论**。

---

## 3. 调色板 PNG 被误报"图片损坏"→ PIL 重编码即修复

**现象**：rail_review(post) 报 `图片可能损坏无法打开: 01/02/03.png`，而 PIL `verify()` 实测 OK、尺寸颜色全部正常。
**根因**：少色图（<256 色）被写为**调色板 PNG（含 `PLTE` chunk）**；报错的 3 张含 PLTE，正常的 5 张只有 `IHDR/pHYs/IDAT/IEND`。

```python
from PIL import Image
im = Image.open(p).convert("RGB"); im.load()
im.save(p, format="PNG", optimize=False, dpi=(300, 300))   # 像素不变，仅换编码
```
复验 `verify()` + size 一致 → 重提 rail_review(post) **一次通过**。
⛔ **不要重跑出图脚本**（图内容没错，属"编码类 issue"，重跑不改判定、白吃一轮循环告警）。

---

## 4. CellChat（1.6.1）概率取值 —— `LRsig` 没有 prob 列

**两次报错递进**：`order(-r$prob)` → `一进列运算符的参数无效`（S4 DataFrame 不能用 `$`）；`as.data.frame()` 后 → `LRsig 无 prob 列`。
**实测列名**：`interaction_name, pathway_name, ligand, receptor, agonist, antagonist, co_A_receptor, co_I_receptor, evidence, annotation, interaction_name_2`
**结论**：`LRsig` 只存 **LR 元数据**，**没有 prob/pval**；概率必须从数组槽取。

```r
# LR 级 top 互作对
pr  <- cc@net$prob                        # 3D array: source × target × LR
lrn <- dimnames(pr)[[3]]
s   <- vapply(lrn, function(l) sum(pr[, , l]), numeric(1)); o <- order(-s)
map <- as.data.frame(cc@LR$LRsig)[, c("interaction_name", "interaction_name_2", "pathway_name")]
data.frame(LR_pair = map$interaction_name_2[match(lrn[o], map$interaction_name)],
           pathway = map$pathway_name[match(lrn[o], map$interaction_name)],
           prob    = round(s[o], 4))

# 通路相对信息流（%）：不依赖任何 ranking 函数，最稳
pws <- function(cc, p) { pr <- cc@netP$prob; if (is.null(pr) || !(p %in% dimnames(pr)[[3]])) 0 else sum(pr[, , p]) }
# 发送者归属：rowSums 沿 source 维
snd <- sort(rowSums(cc@netP$prob[, , "LAMININ"]), decreasing = TRUE)   # names = 细胞群
```

**同族**：rankNet 缺失时用上面相对信息流手动排名（P7 fallback）；`compareInteractions` 在 1.6.1 + merge 对象上实测**可以正常出图**，不必默认它必空白。

---

## 5. 多条件对比的敏感性审计（出结论前的闸门）

**教训**：`Young(900 cells) vs Old(602 cells)` 只报点估计 → L2 辩论裁决 **need_more_info / confidence=low**，rubrics 中 `design_balance=3`、`artifact_control=2`。裁判明确列出必须先跑的动作，未做则结论不得进入主结论、报告/入库会被 `blocks` 硬拦。

| 审计 | 做法 | 回答什么问题 |
|------|------|------------|
| 深度/检出量匹配 | 比 `nCount_RNA` / `nFeature_RNA` 中位数与均值，报告比值 | 组间差异是否只是测序深度伪像 |
| 去主导通路重算 | 从 `netP$prob` 排除该通路后重算相对信息流 % | 63% 占比是分母依赖/单 LR 假象还是真实主导 |
| 等量下采样重跑 | 大组随机下采样至小组 n，**跑 3 次**，记录总权重/每细胞/通路数 | 整体强弱差是否只是细胞数伪像 |
| 小群去除稳定性 | 对"100% 驱动某通路的 88–108 细胞小群"各去一半重跑 | 单群驱动的独有通路是否留存 |
| bootstrap 提升 | nboot 100 → ≥1000 + 置换 | CI 宽度与显著性（成本高，可在报告中列为后续工作） |

**结论口径铁律**
- 未做审计前，把结论标为**低置信方向**；`prob≈0` 的通路（本次 TGFb）**不予解读**。
- nboot 与主分析保持一致时要在报告里**声明**："沿用 nboot=100 以保证与主分析严格可比，提升 nboot 属后续工作"。
- 单群 100% 驱动的通路、单一同源 LR 独占 >50% 相对信息流的通路，一律写成"技术可疑 / 待验证"，不写成生物学发现。
- 文献锚点是低成本高收益的一步：本次检索到 **PTPRM 是内皮细胞异质性 marker（PMID 12895029）**，直接支撑了"肌纤维群中 PTPRM-PTPRM 独占 63% 更像血管/内皮残余信号"的判断。

---

## 6. 检索工具：`search_papers` 查询词过长的静默失败

**现象**：`"laminin LAMA2 DAG1 NRG ERBB aging skeletal muscle sarcopenia cell-cell communication"` → `total: 0`（三源全 0）；同一主题拆成 `"PTPRM muscle"` / `"sarcopenia neuromuscular junction NRG1 ERBB"` → 立刻命中 8–11 篇。
**处置**：查询词压到 **≤5 个词**，一个查询只问一件事；**同主题拆成 2–3 次短查询**，不要堆基因名。
⚠️ 返回 0 不等于"没有文献"——先拆词重查再下结论。