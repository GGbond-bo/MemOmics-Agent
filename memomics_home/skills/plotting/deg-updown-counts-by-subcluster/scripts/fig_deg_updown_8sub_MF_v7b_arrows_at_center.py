# -*- coding: utf-8 -*-
"""
fig_deg_updown_8sub_MF_v3_optimized
基线 = fig_deg_updown_8sub_freescale_v2_optimized（用户选定最优版）
只解决用户指出的三个问题，柱区配色/顺序/顶部区结构不变：

问题1 左侧重排 —— 原「家族括号(x=0.150) + 旋转家族名(x=0.137)」与右对齐的亚群名
      互相压叠（亚群名 6.6pt 13 字符左缘约 0.094，实测已越过 0.150 括号 → 必压叠）。
      改为：单一模块竖带「MF」贴在柱区左侧。
      阅读顺序 = 轴名 → 亚群名（右对齐）→ MF 模块 → 柱形图。
      保留 Pure / Derived 的极浅虚线分隔（无色无字，仅作视觉分块）。

问题2 x 轴统一标准 —— 改为 symlog(linthresh=1) + 十倍阶梯刻度 0/10/100/1,000/10,000，
      五个面板共用同一根统一轴（对齐 fig_deg_updown_8sub_CNS_v2_minimal 的 Aging）。
      symlog 让 16,535（Aging）与 15（Ex_Young）能在同一根轴上同时按比例可读，
      Aging 的衰老幅度因此显出来。刻度标签在轴下方，与柱内数值标签不同纵向带，不冲突。

问题3 每根柱标注自身基因数 —— 外侧 2.5 pt 贴近标注（"贴近但不重合"）；
      柱端若已进入轴的最外侧 20%（frac>0.80）→ 改柱内白字右对齐，
      保证任何情况下都不互相重合、不越出面板。
"""
import os
import math
import numpy as np
import pandas as pd
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, FancyArrowPatch

OUT = r"E:/MemOmics-Agent/results/memomics-afd2d418/task2/figures"
SRC = r"E:/MemOmics-Agent/results/memomics-afd2d418/task2/results/deg_subcluster_updown_coef025_matrix.csv"
# 变体开关（内核 exec 时可注入）：right = 竖直箭头在各自数字右侧 | center = 竖直箭头贴中心线内侧
MF_VARIANT = globals().get("MF_VARIANT", "center")
STEM = globals().get("STEM_OVERRIDE") or "fig_deg_updown_8sub_MF_v7b_arrows_at_center"
os.makedirs(OUT, exist_ok=True)

# ---------- 字体链 Arial -> Helvetica -> DejaVu ----------
_fam = "DejaVu Sans"
for _f in ["Arial", "Helvetica"]:
    try:
        mpl.font_manager.findfont(mpl.font_manager.FontProperties(family=_f), fallback_to_default=False)
        _fam = _f
        break
    except Exception:
        pass
mpl.rcParams.update({
    "font.family": _fam, "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "xtick.major.size": 2.0,
    "text.color": "#1A1A1A", "axes.labelcolor": "#1A1A1A",
    "xtick.color": "#1A1A1A", "figure.facecolor": "white", "savefig.facecolor": "white",
})

UP, DN = "#B2182B", "#2166AC"            # 沿用（用户选定）：右=上调 左=下调
INK, INK2 = "#1A1A1A", "#5A5A5A"
FAM_COND, FAM_EX = "#3D3B4F", "#0F5F6E"  # 条件对比 vs 运动响应（顶部区沿用）
MF_INK = "#2B2B2B"

ORDER = ["Pure Type I", "Pure Type IIA", "Pure Type IIX", "LRP1B+(I)",
         "RP_high(I)", "RP_high(II)", "OTUD1+(I)", "OTUD1+(II)"]
SPLIT_AFTER = 2                           # 第 3 行下画浅虚线（Pure / Derived 分块）
PANELS = [("Aging", "Y_Pre_vs_O_Pre", "cond"),
          ("DM", "O_Pre_vs_OD_Pre", "cond"),
          ("Ex_Young", "Y_Pre_vs_Y_Post", "ex"),
          ("Ex_Old", "O_Pre_vs_O_Post", "ex"),
          ("Ex_DM", "OD_Pre_vs_OD_Post", "ex")]

# ---------- 数据（复用已算好的计数表，不重算统计）----------
df = pd.read_csv(SRC).set_index("celltype")
df = df.loc[ORDER]                                    # 剔除 RSS / Specialized MF
UP_M = np.vstack([df[f"{c}_Up"].values.astype(float) for _, c, _ in PANELS])
DN_M = np.vstack([df[f"{c}_Down"].values.astype(float) for _, c, _ in PANELS])

# ---------- 统一轴参数（问题2）----------
TMAX = float(max(UP_M.max(), DN_M.max()))             # 全局最大 = Aging 上调 16,535
XMAX = TMAX * 1.30
LINTHRESH = 1.0
LADDER = [0.0]
for _k in range(1, 7):
    if 10.0 ** _k <= TMAX:
        LADDER.append(10.0 ** _k)
LADDER = sorted(set(LADDER))                          # 0, 10, 100, 1,000, 10,000
TICKS = sorted(set(LADDER + [-v for v in LADDER if v > 0]))
TLAB = [f"{abs(v):,.0f}" for v in TICKS]

# ---------- 画布几何 ----------
FW, FH = 7.087, 3.45          # 180 x 88 mm
LM, RM, BM, TM = 0.126, 0.014, 0.135, 0.300    # LM 左移（问题1 省下的横向空间给柱区）
GAP = 0.0130
PW = (1.0 - LM - RM - GAP * (len(PANELS) - 1)) / len(PANELS)
PH = 1.0 - BM - TM
fig = plt.figure(figsize=(FW, FH))
YROW = np.arange(len(ORDER))[::-1]
COL = {"cond": FAM_COND, "ex": FAM_EX}

X_AXNAME = 0.008        # 旋转轴名
X_NAMES = 0.090         # 亚群名右对齐基准
MF_L, MF_R = 0.098, LM  # MF 模块竖带
MF_TXT = (MF_L + MF_R) / 2

# ---------- 柱区 ----------
axs = []
SIGMA_TXT = []          # Σ 行文字对象（末尾统一加竖直矢量箭头）
for i, (name, colkey, fam) in enumerate(PANELS):
    L = LM + i * (PW + GAP)
    ax = fig.add_axes([L, BM, PW, PH])
    up, dn = UP_M[i], DN_M[i]
    ax.set_xscale("symlog", linthresh=LINTHRESH, linscale=1.0, base=10)
    ax.set_xlim(-XMAX, XMAX)
    ax.set_ylim(-0.62, len(ORDER) - 0.38)
    ax.barh(YROW, up, height=0.70, color=UP, edgecolor="white", lw=0.45, zorder=3)
    ax.barh(YROW, -dn, height=0.70, color=DN, edgecolor="white", lw=0.45, zorder=3)
    ax.axvline(0, color=INK, lw=0.7, zorder=4)
    ax.set_xticks(TICKS)
    ax.set_xticklabels(TLAB, fontsize=5.2)
    ax.set_yticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(INK2)
    ax.tick_params(axis="x", pad=1.5)

    # ---- 问题3：每根柱标自身基因数 ----
    tr = ax.xaxis.get_transform()
    f0 = float(tr.transform(0.0))
    f1 = float(tr.transform(XMAX))

    def frac(v, plus=True):
        fv = float(tr.transform(v if plus else -v))
        return (fv - f0) / (f1 - f0) if plus else (f0 - fv) / (f0 - float(tr.transform(-XMAX)))

    for r in range(len(ORDER)):
        yv = YROW[r]
        uv, dv = up[r], dn[r]
        pad_u, pad_d = (4.2, 4.2) if uv == 0 else (2.5, 0), (4.2, 4.2) if dv == 0 else (2.5, 0)
        # 上调（右）
        if frac(uv, True) > 0.80:
            ax.annotate(f"{uv:,.0f}", xy=(uv, yv), xytext=(-2.2, 0), textcoords="offset points",
                        ha="right", va="center", fontsize=4.7, color="white", zorder=6)
        else:
            ax.annotate(f"{uv:,.0f}", xy=(uv, yv), xytext=(pad_u[0], 0), textcoords="offset points",
                        ha="left", va="center", fontsize=4.7, color=UP, zorder=6)
        # 下调（左）
        if frac(dv, False) > 0.80:
            ax.annotate(f"{dv:,.0f}", xy=(-dv, yv), xytext=(2.2, 0), textcoords="offset points",
                        ha="left", va="center", fontsize=4.7, color="white", zorder=6)
        else:
            ax.annotate(f"{dv:,.0f}", xy=(-dv, yv), xytext=(-pad_d[0], 0), textcoords="offset points",
                        ha="right", va="center", fontsize=4.7, color=DN, zorder=6)
    axs.append(ax)

# ---------- 顶部：家族超标题 + 家族细线（沿用基线）----------
fam_span = {}
for i, (_, _, fam) in enumerate(PANELS):
    L = LM + i * (PW + GAP)
    fam_span.setdefault(fam, []).append((L, L + PW))
for fam, spans in fam_span.items():
    x0, x1 = min(s[0] for s in spans), max(s[1] for s in spans)
    yl = 0.930
    fig.add_artist(Line2D([x0, x1], [yl, yl], color=COL[fam], lw=1.4,
                          solid_capstyle="butt", zorder=5))
    fig.text((x0 + x1) / 2, yl + 0.014, "Condition contrast" if fam == "cond"
             else "Exercise response  (Pre \u2192 Post)", ha="center", va="bottom",
             fontsize=7.2, color=COL[fam], fontweight="bold")

# ---------- 顶部：面板字母 / 标题 / 标题下色条 / Σ 计数（沿用基线）----------
for i, (name, _, fam) in enumerate(PANELS):
    L = LM + i * (PW + GAP)
    c = COL[fam]
    fig.text(L + PW / 2, 0.862, name, ha="center", va="center",
             fontsize=8.2, fontweight="bold", color=INK)
    fig.add_artist(Line2D([L, L + PW], [0.830, 0.830], color=c, lw=1.5,
                          solid_capstyle="butt", zorder=5))
    su, sd = UP_M[i].sum(), DN_M[i].sum()
    cx = L + PW / 2
    # 顺序与柱子左右方向一致：左 = 下调(蓝) / 右 = 上调(红)
    _t_dn = fig.text(cx - 0.016, 0.789, f"{sd:,.0f}", ha="right", va="center",
                     fontsize=6.6, color=DN, fontweight="bold")
    _t_up = fig.text(cx + 0.016, 0.789, f"{su:,.0f}", ha="left", va="center",
                     fontsize=6.6, color=UP, fontweight="bold")
    SIGMA_TXT.append((_t_dn, _t_up, cx))
    fig.add_artist(Line2D([cx - 0.0006, cx + 0.0006], [0.789, 0.789], color="#D9D9D9",
                          lw=0.7, zorder=4))

fig.add_artist(Line2D([LM, 1 - RM], [0.750, 0.750], color="#C8C8C8", lw=0.7, zorder=4))

# ---------- 右上共享图例（沿用基线）----------
lx = 1 - RM
for j, (cc, tt) in enumerate([(UP, "Up-regulated"), (DN, "Down-regulated")]):
    yy = 0.945 - j * 0.055
    fig.add_artist(Rectangle((lx - 0.148, yy - 0.011), 0.011, 0.022,
                             facecolor=cc, edgecolor="none", zorder=6))
    fig.text(lx - 0.132, yy, tt, ha="left", va="center", fontsize=6.4, color=INK2)

# ---------- 左侧（问题1 重排）----------
def yfrac(row):
    return BM + (PH / (len(ORDER) - 0.38 + 0.62)) * (YROW[row] + 0.62)

# 1) 旋转轴名
fig.text(X_AXNAME, BM + PH / 2, "Subpopulation", rotation=90, ha="center", va="center",
         fontsize=6.6, color=INK, fontweight="bold")

# 2) Pure / Derived 极浅虚线分块（无色无字）
ys = yfrac(SPLIT_AFTER) + 0.006
fig.add_artist(Line2D([X_NAMES - 0.078, LM], [ys, ys], color="#D0D0D0", lw=0.6,
                      linestyle=(0, (1, 1.6)), zorder=4))

# 3) 亚群名（右对齐，位于 MF 模块左侧）
for r, nm in enumerate(ORDER):
    fig.text(X_NAMES, yfrac(r), nm, ha="right", va="center", fontsize=6.4, color=INK)

# 4) MF 模块竖带：浅底 + 右缘竖线 + 旋转模块名
y0, y1 = BM - 0.004, BM + PH + 0.004
fig.add_artist(Rectangle((MF_L, y0), MF_R - MF_L, y1 - y0, facecolor="#F4F4F4",
                         edgecolor="none", zorder=0))
fig.add_artist(Line2D([MF_R, MF_R], [y0, y1], color=MF_INK, lw=1.7,
                      solid_capstyle="butt", zorder=5))
fig.add_artist(Line2D([MF_L, MF_R], [y1, y1], color=MF_INK, lw=0.8, zorder=5))
fig.add_artist(Line2D([MF_L, MF_R], [y0, y0], color=MF_INK, lw=0.8, zorder=5))
fig.text(MF_TXT, BM + PH / 2, "MF", rotation=90, ha="center", va="center",
         fontsize=7.6, color=MF_INK, fontweight="bold")

# ---------- 底部共享轴名 ----------
fig.text(LM + (1 - RM - LM) / 2, 0.072,
         "Number of differentially expressed genes", ha="center", va="center",
         fontsize=6.8, color=INK)
fig.text(LM + (1 - RM - LM) / 2, 0.030,
         "Unified symmetric-log scale across panels  \u00b7  decade ticks (0 / 10 / 10\u00b2 / 10\u00b3 / 10\u2074)"
         "  \u00b7  |coef| > 0.25 & FDR < 0.05  \u00b7  RSS and Specialized MF excluded",
         ha="center", va="center", fontsize=5.2, color=INK2, style="italic")

# ---------- Σ 行竖直矢量箭头（不依赖字体字形）----------
#   蓝 ↓ = 下调方向 / 红 ↑ = 上调方向
#   right  -> 箭头紧跟各自数字右侧   380 ↓ | 16,535 ↑
#   center -> 箭头贴中心线内侧       380 ↓ | ↑ 16,535
fig.canvas.draw()
_REND = fig.canvas.get_renderer()
_AH, _AG = 0.0125, 0.0026
for _at_dn, _at_up, _acx in SIGMA_TXT:
    if MF_VARIANT == "right":
        _ax_dn = _at_dn.get_window_extent(renderer=_REND).transformed(
            fig.transFigure.inverted()).x1 + _AG
        _ax_up = _at_up.get_window_extent(renderer=_REND).transformed(
            fig.transFigure.inverted()).x1 + _AG
    else:
        _ax_dn, _ax_up = _acx - 0.0065, _acx + 0.0065
    for _ax, _aup, _acc in ((_ax_dn, False, DN), (_ax_up, True, UP)):
        _ay0, _ay1 = ((0.789 - _AH, 0.789 + _AH) if _aup
                      else (0.789 + _AH, 0.789 - _AH))
        fig.add_artist(FancyArrowPatch((_ax, _ay0), (_ax, _ay1), transform=fig.transFigure,
                                       arrowstyle="-|>", mutation_scale=3.8, lw=0.85,
                                       color=_acc, shrinkA=0, shrinkB=0, zorder=6))

# ---------- 导出 ----------
png = os.path.join(OUT, STEM + ".png")
fig.savefig(png, dpi=400)
fig.savefig(os.path.join(OUT, STEM + ".pdf"))
fig.savefig(os.path.join(OUT, STEM + ".svg"))
fig.savefig(os.path.join(OUT, STEM + ".tiff"), dpi=600, pil_kwargs={"compression": "tiff_lzw"})
plt.close(fig)

# source data
sd = pd.DataFrame({"subpopulation": ORDER})
for i, (name, c, _) in enumerate(PANELS):
    sd[f"{name}_Up"] = UP_M[i].astype(int)
    sd[f"{name}_Down"] = DN_M[i].astype(int)
sd.to_csv(os.path.join(OUT, STEM + "_source_data.csv"), index=False)

print("OK ->", STEM)
for e in ("png", "pdf", "svg", "tiff"):
    p = os.path.join(OUT, STEM + "." + e)
    print(f"  {e:5s} {os.path.getsize(p):>10,} B")
print("统一轴 XMAX =", f"{XMAX:,.0f}", "| 刻度 =", TLAB)
print("剔除校验 (Aging):", int(UP_M[0].sum() + DN_M[0].sum()), "= 8亚群合计")
print("面板总计 Up :", [f"{n}={int(u.sum())}" for (n, _, _), u in zip(PANELS, UP_M)])
print("面板总计 Dn :", [f"{n}={int(d.sum())}" for (n, _, _), d in zip(PANELS, DN_M)])
print("每面板标注数 =", len(ORDER) * 2, "个/面板 (8 上调 + 8 下调，含 0 值)")