#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
triage_batch_deg.py —— 批量 DEG 产出分诊探针（本 skill §十五 的一键版）

用途：一批 `*_sDEG.csv`（逐亚群 × 比较组）跑完后，逐文件判「可用 / 仅探索 / 丢弃」，
并算出集中度、混杂因素交叉表、极性指纹、RUV 饱和指数。

用法：
    python triage_batch_deg.py <目录或通配符> [--out summary.csv] [--top 10]

示例：
    python triage_batch_deg.py results/Immune_RUV_result
    python triage_batch_deg.py "results/**/*_sDEG.csv"

约定（自动识别，无需改代码）：
  效应列 : coef / logFC / log2FC
  p   列 : p / p_val / pvalue
  FDR 列 : fdr / padj / p_val_adj / q
  分组列 : celltype / cell_type / cluster / subcluster   （缺失则用文件名推断）
  对比列 : comparison / contrast                          （缺失则用文件名推断）
  方法列 : method                                          （缺失记为 NA）
  k   列 : nRUV_used / n_ruv / k                           （缺失记为 NA）
  样本列 : n_samples / n_sample                            （缺失记为 NA）
  细胞列 : n_cells / n_cell                                （缺失记为 NA）

退出码：0 正常；2 没找到任何 csv。
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

import numpy as np
import pandas as pd

EFFECT_COLS = ["coef", "logFC", "log2FC", "logfc"]
P_COLS = ["p", "p_val", "pvalue", "p_value"]
FDR_COLS = ["fdr", "padj", "p_val_adj", "q", "FDR"]
CELLTYPE_COLS = ["celltype", "cell_type", "cluster", "subcluster", "annotation"]
COMP_COLS = ["comparison", "contrast", "comp"]
METHOD_COLS = ["method"]
K_COLS = ["nRUV_used", "n_ruv", "k", "k_ruv"]
NSAMP_COLS = ["n_samples", "n_sample"]
NCELL_COLS = ["n_cells", "n_cell"]

VERDICT_USABLE = "USABLE"
VERDICT_EXPLORE = "EXPLORE_ONLY"
VERDICT_DISCARD = "DISCARD"


def pick(cols, candidates):
    low = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in low:
            return low[cand.lower()]
    return None


def parse_comparison(name: str) -> str:
    """'Y_Pre_vs_Y_Post' -> 'Y_Pre_vs_Y_Post'；只用于 base 提取。"""
    return name


def comparison_type(comp: str) -> str:
    """
    从对比名判「组内配对」还是「跨组独立」。
    Y_Pre_vs_Y_Post  -> 两侧 base 都是 Y  -> within(paired)
    Y_Pre_vs_O_Pre   -> Y vs O            -> cross(independent)
    O_Pre_vs_OD_Pre  -> O vs OD           -> cross(independent)
    """
    if not isinstance(comp, str) or "_vs_" not in comp:
        return "unknown"
    a, b = comp.split("_vs_", 1)
    base_a = re.sub(r"_(Pre|Post|pre|post|preT|postT)$", "", a)
    base_b = re.sub(r"_(Pre|Post|pre|post|preT|postT)$", "", b)
    return "within(paired)" if base_a == base_b else "cross(independent)"


def infer_from_filename(path: str):
    """兜底：从 'immune_CD14__Mono_Y_Pre_vs_Y_Post_sDEG.csv' 猜 celltype/comp。"""
    stem = os.path.basename(path)
    for suf in ("_sDEG.csv", ".csv"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
    stem = re.sub(r"^(immune|muscle|MuSC|MF)_", "", stem)
    m = re.search(r"(.+)_([A-Za-z0-9]+_(?:Pre|Post|pre|post)_vs_[A-Za-z0-9]+_(?:Pre|Post|pre|post))$", stem)
    if m:
        return m.group(1).replace("__", "+"), m.group(2)
    return "NA", "NA"


def triage_one(path: str) -> dict | None:
    try:
        d = pd.read_csv(path)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 读不了 {path}: {e}", file=sys.stderr)
        return None
    if d.empty:
        return None

    cols = list(d.columns)
    c_eff = pick(cols, EFFECT_COLS)
    c_fdr = pick(cols, FDR_COLS)
    c_p = pick(cols, P_COLS)
    if c_fdr is None and c_p is None:
        print(f"[warn] {os.path.basename(path)} 找不到 p/fdr 列，跳过", file=sys.stderr)
        return None

    c_ct = pick(cols, CELLTYPE_COLS)
    c_cmp = pick(cols, COMP_COLS)
    c_meth = pick(cols, METHOD_COLS)
    c_k = pick(cols, K_COLS)
    c_ns = pick(cols, NSAMP_COLS)
    c_nc = pick(cols, NCELL_COLS)

    r0 = d.iloc[0]
    ct_guess, cmp_guess = infer_from_filename(path)
    celltype = str(r0[c_ct]) if c_ct else ct_guess
    comp = str(r0[c_cmp]) if c_cmp else cmp_guess

    n = len(d)
    fdr = pd.to_numeric(d[c_fdr] if c_fdr else d[c_p], errors="coerce")
    sig = d[fdr < 0.05]
    n_sig = int(len(sig))
    if c_eff is not None and n_sig:
        eff = pd.to_numeric(sig[c_eff], errors="coerce")
        n_up = int((eff > 0).sum())
        n_dn = int((eff < 0).sum())
    else:
        n_up = n_dn = 0

    k = pd.to_numeric(pd.Series([r0[c_k]]), errors="coerce").iloc[0] if c_k else np.nan
    ns = pd.to_numeric(pd.Series([r0[c_ns]]), errors="coerce").iloc[0] if c_ns else np.nan
    nc = pd.to_numeric(pd.Series([r0[c_nc]]), errors="coerce").iloc[0] if c_nc else np.nan

    pct = 100.0 * n_sig / n if n else 0.0
    # 极性：单一方向占比（>=50% 那一侧）
    pol = 100.0 * max(n_up, n_dn) / n_sig if n_sig else 0.0
    # RUV 饱和指数：(k + 截距 + stim) / n_samples —— 越接近 1 越饱和
    sat = (k + 2) / ns if (pd.notna(k) and pd.notna(ns) and ns > 0) else np.nan

    # 决策
    if pct > 40 or pol > 95:
        verdict = VERDICT_DISCARD
    elif pct > 5 or str(r0[c_meth]) != "glmer" if c_meth else (pct > 5):
        verdict = VERDICT_EXPLORE
    else:
        verdict = VERDICT_USABLE

    return dict(
        file=os.path.basename(path),
        celltype=celltype,
        comparison=comp,
        comp_type=comparison_type(comp),
        method=str(r0[c_meth]) if c_meth else "NA",
        k_ruv=k,
        n_samples=ns,
        n_cells=nc,
        n_genes=n,
        n_sig=n_sig,
        n_up=n_up,
        n_down=n_dn,
        pct_sig=round(pct, 4),
        polarity_pct=round(pol, 2),
        saturation_idx=round(sat, 3) if pd.notna(sat) else np.nan,
        verdict=verdict,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="目录、通配符或单个 csv")
    ap.add_argument("--out", default=None, help="汇总表输出路径（默认 <target>/batch_deg_triage.csv）")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    t = args.target
    if os.path.isdir(t):
        files = sorted(glob.glob(os.path.join(t, "*.csv")))
        default_out = os.path.join(t, "batch_deg_triage.csv")
    else:
        files = sorted(glob.glob(t, recursive=True))
        default_out = "batch_deg_triage.csv"
    # 排除自己刚写出的汇总表
    files = [f for f in files if not f.endswith("batch_deg_triage.csv")]

    if not files:
        print(f"[error] 没找到任何 csv: {t}", file=sys.stderr)
        return 2

    rows = [r for r in (triage_one(f) for f in files) if r]
    if not rows:
        print("[error] 全部读失败", file=sys.stderr)
        return 2
    S = pd.DataFrame(rows)

    out = args.out or default_out
    S.to_csv(out, index=False, encoding="utf-8-sig")

    # ---------- 报告 ----------
    print(f"[read] {len(S)} 个 csv -> {out}\n")

    print("=" * 78)
    print("① 完成度 / 质量三指标")
    print("=" * 78)
    print(f"  文件数            : {len(S)}")
    print(f"  显著率 中位        : {S.pct_sig.median():.3f} %")
    print(f"  显著率 >10% 的文件 : {int((S.pct_sig > 10).sum())}")
    print(f"  显著率 >40% 的文件 : {int((S.pct_sig > 40).sum())}")
    print(f"  总显著行           : {int(S.n_sig.sum()):,}")
    print(f"  决策分布           : {S.verdict.value_counts().to_dict()}")

    print("\n" + "=" * 78)
    print("② 集中度检查（单亚群 >40% 显著行 ⇒ 先单独查它）")
    print("=" * 78)
    conc = (S.groupby("celltype")
              .agg(n_files=("file", "size"), n_sig=("n_sig", "sum"))
              .sort_values("n_sig", ascending=False))
    conc["share_pct"] = (100.0 * conc.n_sig / max(S.n_sig.sum(), 1)).round(1)
    print(conc.head(args.top).to_string())
    if not conc.empty and conc.share_pct.iloc[0] > 40:
        print(f"\n  🔴 集中度告警：'{conc.index[0]}' 占全部显著行的 {conc.share_pct.iloc[0]:.1f}%")
        print("     先单独审查它，⛔ 不要把总显著数当整批的质量指标")
    else:
        print("\n  ✅ 无单亚群垄断（最高 <40%）")

    print("\n" + "=" * 78)
    print("③ 混杂因素分解：method × 对比类型（判问题跟哪个因素走）")
    print("=" * 78)
    if "comp_type" in S and S.comp_type.nunique() >= 1:
        xt = (S.groupby(["comp_type", "method"])
                .agg(n=("file", "size"),
                     pct_median=("pct_sig", "median"),
                     pct_max=("pct_sig", "max"))
                .round(3))
        print(xt.to_string())
        print("\n  读法：若只有 cross(independent)+bayesglm 高 ⇒ 是「无RE×跨组」的错，不是 k 单独造成的")

    print("\n" + "=" * 78)
    print("④ RUV 饱和指数 saturation_idx = (k+2)/n_samples  （>0.7 = 极端饱和）")
    print("=" * 78)
    sat = S.dropna(subset=["saturation_idx"]).sort_values("saturation_idx", ascending=False)
    if not sat.empty:
        print(sat.head(args.top)[["celltype", "comparison", "method", "k_ruv",
                                  "n_samples", "saturation_idx", "pct_sig"]].to_string(index=False))
        if (sat.saturation_idx > 0.7).any():
            print("\n  ⚠️ 存在 saturation_idx > 0.7 的文件：固定效应数逼近样本数，SE 会被系统性压低")
    else:
        print("  (无 k / n_samples 列，跳过)")

    print("\n" + "=" * 78)
    print("⑤ 极性指纹（单一方向 >95% = 技术偏移指纹，健康应 ≈50%）")
    print("=" * 78)
    pol = S[S.n_sig > 0].sort_values("polarity_pct", ascending=False)
    print(pol.head(args.top)[["celltype", "comparison", "n_up", "n_down",
                              "polarity_pct", "pct_sig"]].to_string(index=False))

    print("\n" + "=" * 78)
    print("⑥ 决策清单")
    print("=" * 78)
    for v, label in ((VERDICT_DISCARD, "❌ 丢弃（显著率>40% 或 极性>95%）"),
                     (VERDICT_EXPLORE, "⚠️ 仅探索（无RE 或 显著率 5–40%）"),
                     (VERDICT_USABLE, "✅ 可用（RE + 显著率<5% + 极性正常）")):
        sub = S[S.verdict == v]
        print(f"\n{label}  —— {len(sub)} 个")
        for _, r in sub.iterrows():
            print(f"    {r.celltype:<22} {r.comparison:<20} "
                  f"sig={r.n_sig:>5} ({r.pct_sig:.2f}%)  "
                  f"{r.method}  k={r.k_ruv}")

    print(f"\n[out] 逐文件明细 -> {os.path.abspath(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())