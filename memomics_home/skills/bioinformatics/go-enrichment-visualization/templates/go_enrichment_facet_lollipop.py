# -*- coding: utf-8 -*-
"""
分面棒棒糖图模板 —— 稀疏富集矩阵的替代形式（非零率 >85% 时首选，别出矩形热图）

每个亚群一个独立 panel，只画它自己的 3-6 条词条 ⇒ 零空格子，面积利用率≈100%。
实测：53 词条 × 17 亚群（热图 901 格仅 8.3% 非零）→ 17 panel 网格 11.4×8.6 in 横版。

输入（先由 R/pandas 落盘为 CSV）：
  data/<PRE>_matrix_vN.csv   行=词条，列=亚群，值 = -log10(q) 已 clip 0-10，空格 = 0
  data/<PRE>_genes_vN.csv    列: path, genes    (genes 用 "," 分隔)
配色：YlOrRd 五档（用户定稿，见 SKILL.md §非红色系咨询口径）

运行：execute_python → exec(open("...this.py", encoding="utf-8").read())
"""
import os, textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.colors import LinearSegmentedColormap, Normalize

# ----------------- 改动点 -----------------
D    = "results/<sid>/"          # 结尾带 /
PRE  = "MF_SMF_go"               # 输入文件前缀
SUF  = "v15"                     # 输入文件后缀
TAG  = "facet_lollipop_v1"       # 输出文件标签
NCOL = 4                         # panel 列数（17 亚群 → 4 列 × 5 行）
FIGW, FIGH = 11.4, 8.6           # 实测 17 panel 的合适画布
TITLE = "Per-subtype GO enrichment  |  x = -log10(q)  |  one panel per subtype"
# ⚠️ TITLE 里只写代码真的实现了的编码 —— 参见 SKILL.md「假图注」条目
# -----------------------------------------

OUT = D + "figures/"
os.makedirs(OUT, exist_ok=True)

m = pd.read_csv(f"{D}data/{PRE}_matrix_{SUF}.csv", index_col=0)   # 词条 × 亚群
G = pd.read_csv(f"{D}data/{PRE}_genes_{SUF}.csv").set_index("path")["genes"].to_dict()

sparsity = 1 - (m.values > 0).mean()
print(f"矩阵 {m.shape} 稀疏度 {sparsity:.1%} "
      f"{'✅ 适用本模板' if sparsity > 0.85 else '⚠️ <85%，矩形热图可能更合适'}")

cmap = LinearSegmentedColormap.from_list(
    "ylorrd", ["#FFF7EC", "#FDD49E", "#FC8D59", "#D7301F", "#7F0000"])
norm = Normalize(0, 10)

# GO 词条名缩写表（panel 宽仅 ~1.1 in，67 字符原名放不下）
ABBR = [("negative regulation of ", "neg. reg. "), ("positive regulation of ", "pos. reg. "),
        ("regulation of ", "reg. of "), ("signaling pathway", "signaling"),
        ("signal transduction", "signal transd."), ("metabolic process", "metab."),
        ("biosynthetic process", "biosynth."), ("catabolic process", "catab."),
        ("organization", "org."), ("development", "dev."), ("response to ", "resp. to "),
        ("progression", "prog."), ("process", "proc."), ("pathway", "pathw."),
        ("extracellular matrix", "ECM"), ("G protein-coupled receptor", "GPCR")]


def shorten(p, width=26):
    for a, b in ABBR:
        p = p.replace(a, b)
    return "\n".join(textwrap.wrap(p, width)[:2])


def gene_short(g, n=3, width=24):
    parts = [x.strip() for x in str(g).split(",")]
    s = ", ".join(parts[:n]) + ("..." if len(parts) > n else "")
    return s[:width - 1] + "…" if len(s) > width else s


clusters = list(m.columns)
NROW = int(np.ceil(len(clusters) / NCOL))

fig = plt.figure(figsize=(FIGW, FIGH), facecolor="white")
# ⚠️ wspace 必须 ≥1.6：panel 的 y 轴标签画在 axes 左侧、会盖到前一列绘图区，
#    太小 ⇒ 标签压叠，OCR 读出乱码串（实测 RegOfsrePRR3SCA）
gs = GridSpec(NROW, NCOL, figure=fig, hspace=0.58, wspace=1.62,
              left=0.105, right=0.985, top=0.933, bottom=0.075)

for i, cl in enumerate(clusters):
    ax = fig.add_subplot(gs[i // NCOL, i % NCOL])
    v = m[cl]
    v = v[v > 0].sort_values()                 # 升序 → 最显著在顶部
    ypos = np.arange(len(v))
    ax.hlines(ypos, 0, v.values, color="#CCCCCC", lw=1.6, zorder=1)
    ax.scatter(v.values, ypos, s=46, c=v.values, cmap=cmap, norm=norm,
               edgecolors="#5A5A5A", linewidths=0.35, zorder=3)   # s 固定 → 图注不得声称 size 编码基因数
    ax.set_yticks(ypos)
    ax.set_yticklabels([f"{shorten(p)}\n({gene_short(G.get(p, ''))})" for p in v.index],
                       fontsize=5.6, linespacing=1.25)
    ax.set_ylim(-0.75, len(v) - 0.25)
    ax.set_xlim(0, 10.9)
    ax.set_xticks([0, 5, 10])
    ax.set_xticklabels(["0", "5", "10"], fontsize=5.2, color="#666666")
    ax.tick_params(axis="x", length=2, pad=1.2, color="#999999")
    ax.tick_params(axis="y", length=0, pad=2)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color("#BBBBBB")
    ax.spines["bottom"].set_linewidth(0.5)
    ax.grid(axis="x", color="#EEEEEE", lw=0.45, zorder=0)
    ax.set_axisbelow(True)
    ax.set_title(cl, fontsize=8.2, fontweight="bold", color="#1A1A1A", pad=5)

# 右下角横放短 legend
cax = fig.add_axes([0.70, 0.028, 0.19, 0.014])
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
cb = fig.colorbar(sm, cax=cax, orientation="horizontal", ticks=[0, 5, 10])
cb.ax.tick_params(labelsize=6, length=2, pad=1.5, color="#999999")
cb.outline.set_visible(False)
cb.set_label("-log10(q-value)", fontsize=6.4, labelpad=1.5, color="#333333")

fig.text(0.105, 0.970, TITLE, fontsize=7.6, color="#555555", ha="left", va="bottom")

for ext in ("png", "svg", "pdf"):
    fig.savefig(f"{OUT}GO_enrichment_{TAG}.{ext}", dpi=300, facecolor="white",
                bbox_inches="tight")
plt.close(fig)
print("done:", OUT + f"GO_enrichment_{TAG}.png")

# ---- 核验（棒棒糖图内容像素占比天然 ~6%，不要用 >30% 判坏图）----
# 判据 = OCR 文本条数 ≥ 预期元素数（panel 标题 + 每词条的名称/基因行）
# vision_describe(png) → 看 OCR 条数；实测 17 panel/53 词条 → 196 条