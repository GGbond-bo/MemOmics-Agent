# -*- coding: utf-8 -*-
"""
venn_overlap_toolkit.py — 多对比基因集合交并 + 富集检验 + 手绘韦恩（可复用引擎）
==============================================================================
把"韦恩图 / 三组交集 / 逆转分析"这类任务固化下来：读多对比 DEG 表 → 方向语义自证
→ 建集合（基因级 / 指定群体子集）→ 精确超几何（2 集）+ 置换检验（3 集）
→ 手绘 3 集合与 2 集合韦恩（内置版式自检）→ 输出计数表 / 明细表 / 一行速贴清单。

输入约定：一个 xlsx，每个 sheet = 一个对比；每行 = 基因 × 细胞群体。
必需列：gene, celltype, coef 或 logFC, fdr 或 padj, regulation(Up/Down)。
强烈建议表里带 direction 列（自证 coef 符号指向谁），没有就自己在脚本里补断言。

▶ 最少调用（改顶部 CONFIG 后直接跑）：
    python venn_overlap_toolkit.py
▶ 或用命令行：
    python venn_overlap_toolkit.py --xlsx D:/x/DEG.xlsx --outdir results/task4 \
        --full-tables D:/x/merged_*.xlsx --triple ExA=sheetA,ExB=sheetB,ExC=sheetC \
        --pair Aging_up=sheetA:Up,ExOld_down=sheetC:Down

⚠️ universe 必须取自**未过滤全表**（--full-tables）；过滤表当分母会把期望值算成假的。
⚠️ 不要装 matplotlib_venn —— 本文件手绘，且能把版式自检焊进 save（见 §六 SKILL）。
"""
from __future__ import annotations

import argparse
import glob
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from mpl_text_layout_audit import save_figure            # 同目录复用
except Exception:                                            # pragma: no cover
    save_figure = None

# ---------------------------------------------------------------- CONFIG
CONFIG = dict(
    xlsx=r"D:/我的下载/DEG_fdr05_coef025_5contrasts.xlsx",
    outdir=r"E:/MemOmics-Agent/results/<sid>/task4",
    full_tables=[r"D:/肌肉锻炼/DEG_file/merged_*.xlsx"],      # universe 来源（未过滤）
    subset=None,          # 例: ["Pure Type I","Pure Type IIA"] —— 只算这些细胞群体
    triple={"Ex_Young": "Y_Pre_vs_Y_Post", "Ex_Old": "O_Pre_vs_O_Post",
            "Ex_DM": "OD_Pre_vs_OD_Post"},
    pairs={"Aging_up_x_ExOld_down": ("Y_Pre_vs_O_Pre:Up", "O_Pre_vs_O_Post:Down"),
           "Aging_down_x_ExOld_up": ("Y_Pre_vs_O_Pre:Down", "O_Pre_vs_O_Post:Up")},
)

plt_rc = {  # 投稿级字体/矢量设置
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "axes.unicode_minus": False,
}


# ============================================================== 1. 读表 + 语义自证
def load_tables(xlsx: str) -> dict[str, pd.DataFrame]:
    xl = pd.ExcelFile(xlsx)
    D = {s: xl.parse(s) for s in xl.sheet_names}
    for s, df in D.items():
        # 方向语义自证：regulation 与效应量符号必须一致；不一致说明表口径不明，先停下问
        if "regulation" in df.columns:
            bad = ((df["regulation"] == "Up") != (df.get("coef", df.get("logFC")) > 0))
            if bool(getattr(bad, "any", lambda: False)()):
                print(f"  ⚠ {s}: regulation 与 coef 符号不一致 {int(bad.sum())} 行 → 先核对口径，勿直接出结论")
        if "direction" in df.columns:
            print(f"  [{s}] direction = {sorted(set(df['direction']))}")
    return D


def universe(full_tables, subset=None) -> int:
    """被检验过的基因总数（各全表基因取交集）——两集合/三集合检验的分母。"""
    g = None
    for pat in full_tables:
        for f in glob.glob(pat):
            xl = pd.ExcelFile(f)
            cur = set()
            for sh in xl.sheet_names:
                df = xl.parse(sh)
                if subset and "celltype" in df.columns:
                    df = df[df["celltype"].isin(subset)]
                cur |= set(df["gene"])
            g = cur if g is None else (g & cur)
    if g is None:
        raise SystemExit("universe 为空：--full-tables 没匹配到文件")
    return len(g)


# ============================================================== 2. 集合
def build_set(D, cmp_name: str, reg: str, subset=None) -> set:
    df = D[cmp_name]
    if subset:
        df = df[df["celltype"].isin(subset)]
    return set(df.loc[df["regulation"] == reg, "gene"])


def detail(D, cmp_name: str, gene: str, subset=None) -> tuple:
    """(命中亚群, max|效应|, minFDR)"""
    df = D[cmp_name]
    if subset:
        df = df[df["celltype"].isin(subset)]
    d = df[df["gene"] == gene]
    if d.empty:
        return "", "", ""
    eff = "coef" if "coef" in d.columns else "logFC"
    return (";".join(d["celltype"].tolist()), round(float(d[eff].abs().max()), 3),
            f"{float(d['fdr'].min() if 'fdr' in d.columns else d['padj'].min()):.2e}")


# ============================================================== 3. 检验
def hyper_2sets(obs: int, nA: int, nB: int, N: int) -> tuple:
    """精确单尾超几何（math.comb 大整数，无溢出、零依赖）"""
    exp = nA * nB / N
    hi = min(nA, nB)
    p = sum(math.comb(nA, k) * math.comb(N - nA, nB - k) / math.comb(N, nB)
            for k in range(obs, hi + 1))
    return exp, p


def permutation_3sets(sA: set, sB: set, sC: set, N: int,
                      nperm: int = 5000, seed: int = 42) -> tuple:
    """三集合交集置换检验（从 universe 抽同大小集合；布尔数组算交，快）"""
    rng = np.random.default_rng(seed)
    obs = len(sA & sB & sC)
    hit = 0
    for _ in range(nperm):
        ms = []
        for k in (len(sA), len(sB), len(sC)):
            m = np.zeros(N, dtype=bool)
            m[np.argpartition(rng.random(N), k)[:k]] = True
            ms.append(m)
        if (ms[0] & ms[1] & ms[2]).sum() >= obs:
            hit += 1
    exp3 = len(sA) * len(sB) * len(sC) / (N ** 2)
    return obs, exp3, (hit + 1) / (nperm + 1)


# ============================================================== 4. 画韦恩
def draw_venn3(ax, sets, names, title="", sub="", col3=None):
    """三等圆。中心区存在条件 R < 2r/sqrt(3)；实测 R=0.50 r=0.62 (阈值 .716)"""
    from matplotlib.patches import Circle
    R, r = 0.50, 0.62
    cen = [(R * math.cos(math.radians(a)), R * math.sin(math.radians(a))) for a in (90, 210, 330)]
    for c, cc in zip(cen, col3 or ["#2f3084", "#43a8a8", "#d95f02"]):
        ax.add_patch(Circle(c, r, alpha=.42, facecolor=cc, edgecolor=cc, lw=1.8, zorder=1))
    A, B, C = sets
    pos = {"A": (0, R + 0.35), "B": (cen[1][0] - .30, cen[1][1] - .16),
           "C": (cen[2][0] + .30, cen[2][1] - .16), "AB": (-.47, .27),
           "AC": (.47, .27), "BC": (0, -.34), "ABC": (0, 0)}
    vals = {"A": len(A - B - C), "B": len(B - A - C), "C": len(C - A - B),
            "AB": len((A & B) - C), "AC": len((A & C) - B), "BC": len((B & C) - A),
            "ABC": len(A & B & C)}
    for k, v in vals.items():
        x, y = pos[k]
        ax.text(x, y, str(v), ha="center", va="center",
                fontsize=15 if k == "ABC" else 13, fontweight="bold",
                color="#B3121A" if (k == "ABC" and v) else "#111111", zorder=5)
    # 集合名：短名 + 贴边朝内经（长名会越出画布跑进隔壁面板）
    ax.text(cen[0][0], 1.16, names[0], ha="center", va="bottom", fontsize=13, fontweight="bold")
    ax.text(-1.30, -0.95, names[1], ha="left", va="center", fontsize=12.5, fontweight="bold")
    ax.text(1.30, -0.95, names[2], ha="right", va="center", fontsize=12.5, fontweight="bold")
    if title:
        ax.set_title(title, fontsize=13.5, fontweight="bold", pad=16)
    if sub:
        ax.text(0, -1.15, sub, ha="center", va="top", fontsize=9.5, color="#555555")
    ax.set_xlim(-1.38, 1.38); ax.set_ylim(-1.45, 1.52); ax.set_aspect("equal"); ax.axis("off")


def draw_venn2(ax, sa, sb, na, nb, title="", sub="", ca="#c0392b", cb="#2c6fbb"):
    """两等圆。集合名走**外侧角 + 集合色**，避免左右相撞（实测坑）"""
    from matplotlib.patches import Circle
    r, dx = 0.78, 0.50
    for x, cc in ((-dx, ca), (dx, cb)):
        ax.add_patch(Circle((x, 0), r, alpha=.42, facecolor=cc, edgecolor=cc, lw=1.8, zorder=1))
    ax.text(-dx - .36, -.02, f"{len(sa - sb)}", ha="center", va="center", fontsize=13,
            fontweight="bold", zorder=5)
    ax.text(dx + .36, -.02, f"{len(sb - sa)}", ha="center", va="center", fontsize=13,
            fontweight="bold", zorder=5)
    ax.text(0, -.02, f"{len(sa & sb)}", ha="center", va="center", fontsize=15, fontweight="bold",
            color="#B3121A" if len(sa & sb) else "#888888", zorder=5)
    ax.text(-1.52, 1.15, na, ha="left", va="top", fontsize=11, fontweight="bold", color=ca)
    ax.text(1.52, 1.15, nb, ha="right", va="top", fontsize=11, fontweight="bold", color=cb)
    if title:
        ax.set_title(title, fontsize=12.5, fontweight="bold", pad=12)
    if sub:
        ax.text(0, -1.00, sub, ha="center", va="top", fontsize=9.5, color="#555555", linespacing=1.6)
    ax.set_xlim(-1.55, 1.55); ax.set_ylim(-1.38, 1.22); ax.set_aspect("equal"); ax.axis("off")


# ============================================================== 5. 主流程
def run(cfg) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update(plt_rc)

    FIG = os.path.join(cfg["outdir"], "figures")
    RES = os.path.join(cfg["outdir"], "results")
    for d in (FIG, RES):
        os.makedirs(d, exist_ok=True)

    print("#TASK:STAGE 读入 + 方向语义自证")
    D = load_tables(cfg["xlsx"])
    sub = cfg.get("subset")
    N = universe(cfg["full_tables"], sub)
    print(f"  universe N = {N}   (subset={sub or '全部细胞群体'})")

    # ---- 三组交集（分 Up / Down）----
    TR = cfg["triple"]
    sets_up = {k: build_set(D, v, "Up", sub) for k, v in TR.items()}
    sets_dn = {k: build_set(D, v, "Down", sub) for k, v in TR.items()}
    ks = list(TR)
    up3 = set.intersection(*sets_up.values())
    dn3 = set.intersection(*sets_dn.values())
    print(f"  三组共同上调 {len(up3)}: {sorted(up3)}")
    print(f"  三组共同下调 {len(dn3)}: {sorted(dn3)}")

    note = f"gene-level (significant in any of the {len(set(D[list(TR.values())[0]]['celltype']))} cell populations); universe N={N:,}"
    for tag, S, col in (("up", sets_up, ["#c0392b", "#E07B39", "#7B241C"]),
                        ("down", sets_dn, ["#2c6fbb", "#3D8B7D", "#1B3A6B"])):
        fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.2))
        for ax, (rl, ss) in zip(axes, (("UP", S), ("DOWN", sets_dn if tag == "up" else sets_up))):
            draw_venn3(ax, [ss[k] for k in ks], ["Young", "Old", "Diabetes"],
                       title=f"{rl}-regulated genes", sub=note, col3=col)
        fig.suptitle("Shared transcriptional response across interventions",
                     fontsize=14, fontweight="bold")
        fig.subplots_adjust(wspace=0.22, top=0.84)
        if save_figure:
            save_figure(fig, f"fig_venn3_{tag}", FIG)
        else:
            for ext in ("png", "pdf", "svg"):
                fig.savefig(f"{FIG}/fig_venn3_{tag}.{ext}", dpi=300, bbox_inches="tight")
            plt.close(fig)

    # ---- 两两"逆转"交集 + 检验 ----
    rows, stat = [], []
    for label, (spec_a, spec_b) in cfg["pairs"].items():
        ca, ra = spec_a.rsplit(":", 1)
        cb, rb = spec_b.rsplit(":", 1)
        sa, sb = build_set(D, ca, ra, sub), build_set(D, cb, rb, sub)
        obs = len(sa & sb)
        exp, p = hyper_2sets(obs, len(sa), len(sb), N)
        fold = obs / exp if exp else float("nan")
        verdict = "富集" if (p < 0.05 and fold > 1.5) else "不显著/不富集"
        stat.append(dict(comparison=label, n1=len(sa), n2=len(sb), overlap=obs,
                         expected_by_chance=round(exp, 1), fold_vs_chance=round(fold, 2),
                         P_value=f"{p:.3e}", test="hypergeometric (exact, 1-sided)",
                         verdict=verdict))
        print(f"  {label}: overlap {obs} | expected {exp:.1f} | fold {fold:.2f} | P={p:.2e} → {verdict}")
        for g in sorted(sa & sb):
            da, db = detail(D, ca, g, sub), detail(D, cb, g, sub)
            rows.append({"comparison": label, "gene": g,
                         f"{ca}_subclusters": da[0], f"{ca}_absEff": da[1], f"{ca}_FDR": da[2],
                         f"{cb}_subclusters": db[0], f"{cb}_absEff": db[1], f"{cb}_FDR": db[2]})

    # 三组交集：置换检验
    for tag, S in (("Exercise shared UP (3-way)", sets_up), ("Exercise shared DOWN (3-way)", sets_dn)):
        obs, exp3, p = permutation_3sets(*[S[k] for k in ks], N)
        stat.append(dict(comparison=tag, n1=len(S[ks[0]]), n2=len(S[ks[1]]), overlap=obs,
                         expected_by_chance=round(exp3, 3),
                         fold_vs_chance=round(obs / exp3, 2) if exp3 else "",
                         P_value=f"{p:.3e}", test="permutation (5000x, from universe)",
                         verdict="富集" if p < 0.05 else "不显著"))

    pd.DataFrame(rows).to_csv(f"{RES}/overlap_gene_detail.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(stat).to_csv(f"{RES}/overlap_significance.csv", index=False, encoding="utf-8-sig")
    with open(f"{RES}/key_genes_plaintext.txt", "w", encoding="utf-8") as fh:
        fh.write(f"[三组共同上调] {len(up3)} 个: {', '.join(sorted(up3))}\n")
        fh.write(f"[三组共同下调] {len(dn3)} 个: {', '.join(sorted(dn3))}\n")
    print("#TASK:PROGRESS 1.0 done")
    print("#TASK:OUTPUT", FIG)
    print("#TASK:OUTPUT", RES)
    return {"up3": sorted(up3), "down3": sorted(dn3), "stats": stat}


def _cli():
    ap = argparse.ArgumentParser(description="多对比基因集合交并 + 富集检验 + 韦恩图")
    ap.add_argument("--xlsx", default=CONFIG["xlsx"], help="过滤后的 DEG xlsx（每 sheet 一对比）")
    ap.add_argument("--outdir", default=CONFIG["outdir"])
    ap.add_argument("--full-tables", nargs="+", default=CONFIG["full_tables"],
                    help="未过滤全表（glob），用于算 universe。务必传！")
    ap.add_argument("--subset", nargs="*", default=CONFIG["subset"],
                    help="只算这些细胞群体（不传=全部）")
    a = ap.parse_args()
    cfg = dict(CONFIG, xlsx=a.xlsx, outdir=a.outdir,
               full_tables=a.full_tables, subset=a.subset)
    run(cfg)


if __name__ == "__main__":
    _cli()