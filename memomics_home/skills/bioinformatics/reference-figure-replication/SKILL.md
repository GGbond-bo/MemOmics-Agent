---
name: reference-figure-replication
description: 按用户给的参考图（PDF/PNG/AI 导出件）反推精确规格，用自己的数据 1:1 复刻同款图。触发：按照这张图来画/照着这个风格出图/参考图/图里这些基因照着重画/按图中的顺序和配色重出/和 Figure SX 一样。
when_to_use: 用户给了一张已有图（论文 Figure、自己之前出的图、合作方给的图）并说「照这个画 / 按这个风格重出 / 图里这些基因我都要」时先加载本 skill。产出=同风格的图，不是"更好看的图"。
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  memomics:
    tags: [figure, replication, reference-figure, dotplot, ggplot2, seurat, pymupdf, 07_可视化]
    difficulty: intermediate
    language: R+Python
    category: bioinformatics
---

# 按参考图复刻出图（reference-figure replication）

## 与同族 skill 的分工（先认门，别用错）

| 用户诉求 | 用哪个 |
|---|---|
| 「**照这张图**画一版」（要一致） | **本 skill** |
| 「按 Nature/CNS 规范优化这张图」（要更好） | `academic-figure-skill` / `nature-figure` |
| 「我这脚本画得不对，你改改」（以脚本为基线） | `user-script-figure-optimization` |
| 只管导出格式/分辨率/CMYK | `scientific-figure-export` |
| 出完图自查版式几何（对齐、碰撞） | `figure-layout-geometry` |

🔴 **复刻 ≠ 美化**：用户要的是**一致**。顺序、基因、配色、字号、点径都不要自作主张"顺手优化"；
想改先问。用户不同意改时的原话口径：「你都 CNS 级别好像也不好看」。

---

## 🔴 铁律 1：规格必须**实测**，禁止目测 / 凭印象 / 凭"常见默认值"

「Seurat DotPlot 默认就是 90° 斜排 lightgrey-blue」这类先验**经常是错的**（本例实测参考图是 **45°** + `lightgrey→darkred`）。
chrome 里"看图"得到的只是印象；`vision_describe` 给的是粗糙 OCR 位置（**不能用来定坐标**）。
**唯一可信来源 = PDF 的文字/矢量坐标 + 色条位图采样。**

一步到位：`scripts/probe_reference_figure.py <参考图.pdf>`（本 skill 自带，直接跑，别手敲）。

---

## Step 1 — 解析参考图（PDF 为准）

| 要拿到什么 | 怎么拿（pymupdf） | 实测坑 |
|---|---|---|
| 画布尺寸 | `page.rect.width/72` × `/72` → 英寸 | 参考图常是超宽页（本例 1728×720 pt = **24×10 in**），别按 A4 猜 |
| **y 轴标签上→下顺序** | 取 `x1 <= 面板左边界` 的 span，按 `y0` **升序**聚类成行 | 🔴 **PDF 文字流顺序常与显示顺序相反**（本例文本流是 Adipocyte→Type I，实际显示 Type I 在最上）。**必须用坐标，不能用 `get_text("text")` 的顺序** |
| **x 轴标签左→右顺序** | 取底部 band（`y0 > 页高×0.9` 或 `>= 面板底`）的 span，按 `x0` 升序 | 本例恰好与文本流一致，但**仍要实测**，不要假设 |
| 标签旋转角 | `line["dir"]`：`(0.707,-0.707)` = **45°**；`(0,±1)` = 90°；`(1,0)` = 0° | 45° 与 90° 视觉上"都是斜的"，只有 dir 能区分 |
| 标签字号 | `span["size"]` | 注意"Features/Identity"等轴标题字号 ≠ 刻度标签字号（本例 14 vs 12） |
| **配色（色条两端）** | 色条通常是**内嵌位图**：`page.get_images()` → `doc.extract_image(xref)` → PIL 取中间列自上而下采样 | 🔴 `get_drawings()` **抓不到**位图色条（本例高矩形检索返回空，白折腾一轮） |
| 点径范围 | `get_drawings()` 里 fill 近正方矩形的 `width` 极值（pt） | 最大点可能同时出现在**尺寸图例**里（本例 24 pt，出现在左上角大点 + 右侧 legend 圈） |
| 图例位置/刻度 | 右侧 span（`x0 > 页宽×0.9`）按 y 排序 | 本例色条刻度自上而下 2→1→0→−1（即色条顶端=最大值） |

---

## Step 2 — 规格 → 绘图参数（映射表）

| 参考图实测 | 绘图参数（ggplot2 / Seurat） |
|---|---|
| `page.rect/72` | `ggsave(width=…, height=…, units="in")` |
| 点最大直径 **pt** | ggplot `size` 单位是 **mm** ⇒ `dot.scale ≈ dmax_pt / 2.8346`（本例 24 pt → **8.5**） |
| 色条两端 hex | `cols = c(浅, 深)`；R 颜色名对表：`#D3D3D3`=`lightgrey`、`#8B0000`=`darkred`（本例就是 `c("lightgrey","darkred")`） |
| 色条刻度范围（如 −1…2） | Seurat DotPlot：`col.min = -1, col.max = 2` + `scale = TRUE` |
| 标签 45° | `RotatedAxis()`（Seurat 内置就是 45°） |
| 标签 90° | `theme(axis.text.x = element_text(angle = 90, hjust = 1, vjust = 0.5))` |
| y 标签上→下顺序 | ggplot **首个 factor level 在最下** ⇒ `levels = rev(上→下顺序)` |
| 面板底色/网格 | 有底色就写 `panel.background = element_rect(fill = "…")`；网格线颜色也要看（别默认加/默认去） |

---

## Step 3 — 自己的数据 ↔ 参考图的轴映射（差集必须显式处理）

参考图的轴是"**别人那套分组**"，与本次数据的标签**不会天然相等**。三条硬要求：

1. **分组合并/差异必须在脚本里打印出来**：本例参考图有 `RSS` + `Specialized MF` 两行，而本次数据的 `annotation_L2`
   已把两者合并成 `non-canonical MF` 一行 → 输出 **23 行**（不是 24）。脚本要打印
   `setdiff(参考图序, 数据标签)` 与 `setdiff(数据标签, 参考图序)`，**不要静默丢行/补 NA**。
2. **基因存在性逐一核对**：`present <- genes[genes %in% rownames(obj)]`，缺失的剔除并落 `gene_presence.csv`
   + 在回复里点名缺失基因。不要直接 `DotPlot(features=all_genes)` 让缺基因的报错/静默吞掉。
3. **顺序以参考图为准**：即使数据里的自然排序（字母/簇号）不同，也要按参考图顺序 `factor(levels=…)`。

---

## Step 4 — 产出与自检

- 一次出齐 **PNG(300dpi) + PDF + SVG**（用户后续要放进 AI 里改），外加**数值表**（如 `dotplot_data.csv`）
  便于用户核对行列是否与参考图一致。
- 自检三条（出图后立刻核，别等用户问）：
  ① x 标签数 == 参考图基因数 − 缺失数；② y 标签数 == 参考图行数 − 合并掉的行数；
  ③ 色条方向与参考图一致（顶端=最大值）。
- 大对象（本例 ≈60 万 细胞 / 7 GB）在集群跑：脚本内写 `OUT <-` 常量 + 落 `#TASK:STAGE` 打点，
  产物 `pull` 回 `results/<sid>/`。集群侧纪律见 `remote-cluster-execution`。

---

## 常见坑（实测）

| 坑 | 现象 | 修法 |
|---|---|---|
| 用文本流顺序当显示顺序 | y 轴上下颠倒，用户一眼看出"顺序不一样" | 一律按 `bbox.y0` 排序（Step 1） |
| 用 `get_drawings()` 找色条 | 返回空 / 只拿到圆点，以为"图里没有色条" | 色条是**内嵌位图** → `get_images()` + `extract_image` |
| 照抄"库默认值"当参考图值 | 配色/角度不对（本例实测 45° + darkred，都不是默认） | 先跑 `scripts/probe_reference_figure.py` |
| 口语歧义「**去除**图中的基因」 | 到底是"删掉某些基因"还是"取出图中的基因清单"？ | 按上下文（本例用户同句说"全都是我需要的"）取"**取出全部**"，并**在回复里显式声明解读 + 请用户点头**；⛔ 不要含糊过去 |
| 参考图只有 `.ai` / `.pptx` | 解析链拿不到矢量文字 | 请用户从 AI 另存一份 PDF/SVG 再跑探针（或让其截图，但截图只能定顺序、定不了字号/色值） |
| 复刻完顺手"美化" | 用户："你怎么改我的风格了" | 复刻阶段**零改动**；要优化另出一版并说明 |

---

## 支持文件

- `scripts/probe_reference_figure.py` — 一条命令反推参考图规格（轴顺序 / 标签角度字号 / 色条两端色 / 点径 → 画布英寸），
  直接跑，输出 JSON 便于喂给下一步。
  完整实测数值、y/x 顺序推导、色条采样结果、点径→`dot.scale` 换算、R 脚本骨架、以及交付时的口径话术。