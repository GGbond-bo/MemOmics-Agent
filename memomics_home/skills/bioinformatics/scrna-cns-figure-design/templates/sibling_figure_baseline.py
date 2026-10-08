#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sibling_figure_baseline.py — 「同一图族」新增图的排版基线模板（matplotlib）

用途：当项目里**已经有一张被认可的图**，要再出一张放进同一图族（并排比对 / 同一篇论文）时，
      复制本文件改数据与标签即可 —— 排版基线、字体链、轴处理、数值标签、图例位置、
      非颜色冗余编码全部已对齐，避免因另起新代码而漂移。

配套规则见 SKILL.md「同族图一致性（figure family）」。

使用前必做（不可跳过）
--------------------
1. **读同族已有图的脚本**（search_files 找同目录/同前缀的 .py/.R），逐项照抄：
   字体链 / 字号 / figsize / 轴脊处理 / 图例位置 / 数值标签旋转 / 配色 / 刻度类型。
2. **横轴类别顺序沿用同族图**，不要按"更合逻辑"的新顺序重排 —— 否则两张图无法并排比对。
3. **复用已有统计产物，不重算**（读已落盘的 CSV），保证与同族图数字完全一致。
4. 重用的强调色若语义与本图不同 → **在图例文字里消歧**（见下 LEGEND 的 "(delivered set)"）。

⚠️ 颜色语义冲突的实测案例：同族旧图里 **红 = 上调**，本图不得不复用红表示 **已交付集**。
   若只靠颜色沟通，读者并排看两张图时会得出相反结论。解法 = 图例文字写死语义 +
   另加斜纹做非颜色冗余编码（灰度打印 / 色觉缺陷下仍可分辨）。
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------- 路径（改成实际值）
OUT_DIR = r"E:\...\figures"
PREFIX = "fig_my_new_sibling"

# ---------------------------------------------------------------- 排版基线（照抄同族）
plt.rcParams.update({
    # 字体链：英文标签一律 Arial→Helvetica→DejaVu，避免 CJK 字体缺字导致的 tofu 方块
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.family": "sans-serif",
    "axes.unicode_minus": False,
    "axes.labelsize": 9,
    "axes.titlesize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "axes.linewidth": 0.8,
    "pdf.fonttype": 42,          # TrueType 嵌入 → 期刊可编辑
    "ps.fonttype": 42,
    "hatch.linewidth": 0.6,
})

# ---------------------------------------------------------------- 数据（改成实际值）
ORDER = ["G1", "G2", "G3"]                       # ⚠️ 顺序沿用同族图，不重排
LABELS = ["Group 1\n(sub line)", "Group 2\n(sub line)", "Group 3\n(sub line)"]
SERIES = {                                        # 每档：值 + 颜色 + 斜纹（非颜色冗余编码）
    "before": dict(vals=[1000, 2000, 3000], color="#B0B7BC", hatch=None),
    "mid":    dict(vals=[400, 500, 600],    color="#E8A33D", hatch="//"),
    "strict": dict(vals=[200, 300, 400],    color="#B2182B", hatch="\\\\"),
}
LEGEND = {
    "before": "Before filtering: FDR < 0.05 only",
    "mid":    "After: FDR < 0.05 & |coef| > 0.20",
    "strict": "After: FDR < 0.05 & |coef| > 0.25  (delivered set)",   # ← 语义消歧写在图例里
}

SYMLOG = True          # 数值跨数量级（如 115 ~ 59,681）时必须开；否则小柱不可见
ROTATE_VALUES = True   # 柱子密集时数值标签转 90° 防重叠

# ---------------------------------------------------------------- 绘图
x = np.arange(len(ORDER))
keys = list(SERIES)
w = 0.8 / len(keys)

fig, ax = plt.subplots(figsize=(11, 5.0))         # figsize 照抄同族
for i, k in enumerate(keys):
    s = SERIES[k]
    offset = (i - (len(keys) - 1) / 2) * w
    ax.bar(x + offset, s["vals"], w, label=LEGEND[k], color=s["color"],
           hatch=s["hatch"], edgecolor="white" if s["hatch"] else None, linewidth=0.4)
    for xi, vv in zip(x + offset, s["vals"]):
        ax.text(xi, vv, f"{vv:,}", ha="center", va="bottom",
                fontsize=7, rotation=90 if ROTATE_VALUES else 0)

if SYMLOG:
    ax.set_yscale("symlog", linthresh=1)
ax.set_xticks(x)
ax.set_xticklabels(LABELS)
ax.set_ylabel("Number of genes\n(subcluster x gene rows, symlog)" if SYMLOG
              else "Number of genes")
ax.set_xlabel("Contrast")
# 标题只做中性描述（说清"画的是什么"），不要把结论写进图面 —— 机制说明交给 figure legend
ax.set_title("Descriptive title — state what is shown, not the conclusion\n"
             "(method / unit / scope in the subtitle)", loc="left")
ax.legend(frameon=False, ncol=len(keys), loc="upper center", bbox_to_anchor=(0.5, -0.16))
ax.spines[["top", "right"]].set_visible(False)    # 同族一致：隐藏 top/right
ax.grid(axis="y", alpha=0.25, lw=0.5)

for ext in ("png", "pdf"):
    fig.savefig(f"{OUT_DIR}\\{PREFIX}.{ext}", dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"[出图] {PREFIX}.png / .pdf")

# ---------------------------------------------------------------- 出图后必做自检（不可跳过）
# 1) 文件存在性 + 大小非空
# 2) 像素健康：
#      from PIL import Image; a = np.asarray(Image.open(p).convert("RGB")).astype(int)
#      nonwhite = (a.sum(axis=2) < 720).mean()*100      # <3% → 疑似空白图，必须重出
# 3) OCR 复核文字真的渲染了（防 tofu / 标签缺失）：
#      vision_describe(image_path=..., question="标题/轴/图例/数值标签分别是什么？有无方块乱码？")
#    ⚠️ 旋转 90° 的数值标签 OCR 会漏字符（如 59,681 → "59,68"），这是 OCR 对旋转文本的限制，
#       不是渲染 bug —— 数值以脚本 stdout 打印的为准，不要据此改图。