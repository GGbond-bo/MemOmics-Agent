#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
coef_threshold_audit.py — DEG 效应量阈值（|coef| / |logFC|）依据审计探针

在确定效应量阈值（0.20 / 0.25 / 0.5 …）之前一次性跑出全部判据，避免逐个手写：

  ① 分母膨胀检查   显著集 vs 全集 |effect| 中位数 / 显著率 / 方向不对称 / SE 与 |z| 量级
  ② 过滤前后计数   各 θ 档的保留数、滤掉数、保留率、相对上一档额外砍掉比例
  ③ 边界带区分力   被砍掉那一带（如 0.20<|coef|<=0.25）的 fdr 与 |z| 中位数
  ④ z 等效尺度     θ 相当于几倍 SE（对比 1.96 惯例）
  ⑤ 正对照召回     已知真信号在每个 θ 档下的存活比例 + 逐个基因的 |coef|

用法
----
python coef_threshold_audit.py \
  --in Aging.csv --name Aging \
  --in Ex_Old.csv --name Ex_Old \
  --group celltype \
  --theta 0.20 0.25 \
  --poscontrol CDKN1A,GADD45G,FBXO32,MYOG \
  --out threshold_audit.csv

也可以给目录：python coef_threshold_audit.py --in /path/to/tables --glob "*.csv" --theta 0.25

列名自动识别（可用 --coef/--se/--p/--fdr/--gene/--group 显式覆盖）。
缺 se 或 p 时对应判据自动跳过并标注，不会报错。

判读标准见 references/effect-size-threshold-justification.md
"""
from __future__ import annotations

import argparse
import glob as globmod
import os
import sys

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- 列名解析
ALIASES = {
    "coef": ["coef", "logFC", "log2FC", "log2fc", "estimate", "avg_log2FC",
             "avg_logFC", "lfc", "LFC"],
    "se":   ["se", "SE", "se.std.error", "std.error", "stderr", "std_error"],
    "p":    ["p", "P", "pval", "p_val", "p_value", "p.value", "P.Value", "pvalue"],
    "fdr":  ["fdr", "FDR", "padj", "p.adjust", "p_adj", "adj.P.Val", "p_val_adj",
             "padj_fdr", "qval", "q_value"],
    "gene": ["gene", "symbol", "gene_name", "Gene", "genes", "feature"],
    "group": ["celltype", "cell_type", "subcluster", "cluster", "annotation_L3", "group"],
}


def resolve(df: pd.DataFrame, key: str, override: str | None) -> str | None:
    """在 df 中找出该语义对应的实际列名；找不到返回 None。"""
    if override:
        if override not in df.columns:
            raise SystemExit(f"[ERR] 指定的 {key} 列 '{override}' 不在文件里，"
                             f"现有列：{list(df.columns)[:25]}")
        return override
    for a in ALIASES[key]:
        if a in df.columns:
            return a
    lower = {c.lower(): c for c in df.columns}          # 大小写不敏感兜底
    for a in ALIASES[key]:
        if a.lower() in lower:
            return lower[a.lower()]
    return None


def read_table(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        sheets = pd.read_excel(path, sheet_name=None)
        if len(sheets) == 1:
            return next(iter(sheets.values()))
        return pd.concat([d.assign(__sheet=k) for k, d in sheets.items()], ignore_index=True)
    if ext in (".tsv", ".txt"):
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def med(s) -> float:
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.median()) if len(s) else float("nan")


# ---------------------------------------------------------------- 单数据集审计
def audit_one(df, name, ths, cols, poscontrol):
    c_coef, c_se, c_p, c_fdr = cols["coef"], cols["se"], cols["p"], cols["fdr"]
    c_gene, c_grp = cols["gene"], cols["group"]

    if c_coef is None:
        raise SystemExit(f"[ERR] {name}: 找不到效应量列（coef/logFC/log2FC…），请用 --coef 指定")
    if c_fdr is None:
        raise SystemExit(f"[ERR] {name}: 找不到 FDR 列（fdr/padj/p.adjust…），请用 --fdr 指定")

    d = df.copy()
    d["_coef"] = pd.to_numeric(d[c_coef], errors="coerce")
    d["_fdr"] = pd.to_numeric(d[c_fdr], errors="coerce")
    d["_se"] = pd.to_numeric(d[c_se], errors="coerce") if c_se else np.nan
    d = d.dropna(subset=["_coef", "_fdr"])
    d["_abs"] = d["_coef"].abs()

    n_tested = len(d)
    sig = d[d["_fdr"] < 0.05]
    n_sig = len(sig)
    if n_sig == 0:
        return dict(dataset=name, n_tested=n_tested, n_fdr05=0,
                    note="FDR<0.05 集为空，无法审计"), []

    # ① 分母膨胀检查
    med_sig, med_all = med(sig["_abs"]), med(d["_abs"])
    n_up = int((sig["_coef"] > 0).sum())
    n_dn = int((sig["_coef"] < 0).sum())
    se_med_sig = med(sig["_se"]) if c_se else float("nan")
    z_med_sig = med(sig["_coef"].abs() / sig["_se"].replace(0, np.nan)) if c_se else float("nan")

    row = dict(
        dataset=name, n_tested=n_tested, n_fdr05=n_sig,
        pct_fdr05_of_tested=round(100.0 * n_sig / n_tested, 2),
        n_up=n_up, n_dn=n_dn,
        direction_asymmetry=round(max(n_up, n_dn) / max(min(n_up, n_dn), 1), 2),
        median_abs_coef_sig=round(med_sig, 4),
        median_abs_coef_all=round(med_all, 4),
        ratio_sig_over_all=round(med_sig / med_all, 3) if med_all else np.nan,
        median_se_sig=round(se_med_sig, 4) if c_se else np.nan,
        median_z_sig=round(z_med_sig, 2) if c_se else np.nan,
        n_subclusters=int(d[c_grp].nunique()) if c_grp else 1,
        n_genes_unique=int(d[c_gene].nunique()) if c_gene else np.nan,
    )

    # ② 过滤前后计数 + ④ z 尺度
    prev_theta = 0.0
    for t in ths:
        keep = int((sig["_abs"] > t).sum())
        prev_keep = int((sig["_abs"] > prev_theta).sum()) if prev_theta else n_sig
        row[f"keep_{t:.2f}"] = keep
        row[f"drop_{t:.2f}"] = n_sig - keep
        row[f"pct_keep_{t:.2f}"] = round(100.0 * keep / n_sig, 2)
        row[f"extra_drop_vs_prev_{t:.2f}"] = prev_keep - keep
        row[f"pct_extra_drop_vs_prev_{t:.2f}"] = round(100.0 * (prev_keep - keep) / prev_keep, 2)
        if c_se and se_med_sig and not np.isnan(se_med_sig):
            row[f"z_equivalent_{t:.2f}"] = round(t / se_med_sig, 2)
        prev_theta = t

    # ⑤ 正对照召回
    if poscontrol and c_gene:
        pc = d[d[c_gene].isin(poscontrol) & (d["_fdr"] < 0.05)]
        row["poscontrol_in_fdr05"] = len(pc)
        for t in ths:
            hit = int((pc["_abs"] > t).sum())
            row[f"poscontrol_recall_{t:.2f}%"] = round(100.0 * hit / max(len(pc), 1), 2)

    # ③ 边界带诊断（相邻阈值之间）
    bands = []
    edges = [0.0] + sorted(ths)
    for lo, hi in zip(edges[:-1], edges[1:]):
        b = sig[(sig["_abs"] > lo) & (sig["_abs"] <= hi)]
        bands.append(dict(
            dataset=name, band=f"{lo:.2f} < |coef| <= {hi:.2f}",
            n_band=len(b),
            pct_of_sig=round(100.0 * len(b) / n_sig, 2),
            median_fdr_band=float(f"{med(b['_fdr']):.3g}") if len(b) else np.nan,
            median_z_band=round(med(b["_coef"].abs() / b["_se"].replace(0, np.nan)), 2)
            if (c_se and len(b)) else np.nan,
        ))
    return row, bands


def poscontrol_detail(dfs, ths, poscontrol, cols_by_name):
    """逐个正对照基因取各数据集内 |coef| 最大值 + 各档是否过关。"""
    if not poscontrol:
        return []
    out = []
    for name, df in dfs.items():
        c = cols_by_name[name]
        if not c["gene"] or not c["coef"]:
            continue
        d = df[[c["gene"], c["coef"]]].copy()
        d.columns = ["gene", "coef"]
        d["coef"] = pd.to_numeric(d["coef"], errors="coerce")
        d = d[d["gene"].isin(poscontrol)].dropna()
        if not len(d):
            continue
        g = d.groupby("gene")["coef"].apply(lambda s: s.abs().max()).reset_index()
        g.columns = ["gene", "max_abs_coef"]
        g["dataset"] = name
        for t in ths:
            g[f"pass_{t:.2f}"] = g["max_abs_coef"] > t
        out.append(g)
    return out


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="DEG 效应量阈值依据审计探针")
    ap.add_argument("--in", dest="inputs", action="append", required=True,
                    help="DEG 表路径（可多次；也可给目录）")
    ap.add_argument("--name", dest="names", action="append", default=None,
                    help="与 --in 一一对应的数据集名（缺省用文件名）")
    ap.add_argument("--glob", default="*.csv", help="--in 给目录时的匹配模式")
    ap.add_argument("--theta", type=float, nargs="+", default=[0.20, 0.25],
                    help="要评估的效应量阈值（默认 0.20 0.25）")
    ap.add_argument("--poscontrol", default="",
                    help="正对照基因，逗号分隔；或 @file.txt（每行一个）")
    for k in ("coef", "se", "p", "fdr", "gene", "group"):
        ap.add_argument(f"--{k}", default=None, help=f"显式指定 {k} 列名")
    ap.add_argument("--out", default="", help="落盘 CSV 前缀（可选）")
    a = ap.parse_args()

    paths: list[str] = []
    for p in a.inputs:
        if os.path.isdir(p):
            paths += sorted(globmod.glob(os.path.join(p, a.glob)))
        else:
            paths.append(p)
    if not paths:
        raise SystemExit("[ERR] 没有找到任何输入文件")

    names = a.names or []
    if names and len(names) != len(paths):
        raise SystemExit(f"[ERR] --name 数量({len(names)}) 与输入文件数({len(paths)}) 不一致")

    poscontrol = []
    if a.poscontrol.startswith("@"):
        with open(a.poscontrol[1:], encoding="utf-8") as fh:
            poscontrol = [x.strip() for x in fh if x.strip()]
    elif a.poscontrol:
        poscontrol = [x.strip() for x in a.poscontrol.split(",") if x.strip()]

    ths = sorted(a.theta)
    rows, bands_all, cols_by_name, dfs = [], [], {}, {}
    for i, path in enumerate(paths):
        name = names[i] if names else os.path.splitext(os.path.basename(path))[0]
        df = read_table(path)
        cols = {k: resolve(df, k, getattr(a, k)) for k in ALIASES}
        cols_by_name[name] = cols
        dfs[name] = df
        missing = [k for k in ("se", "p") if cols[k] is None]
        row, bands = audit_one(df, name, ths, cols, poscontrol)
        if missing:
            row["note"] = "缺 " + "/".join(missing) + " 列 → 相关判据跳过"
        rows.append(row)
        bands_all += bands

    main_df = pd.DataFrame(rows)
    band_df = pd.DataFrame(bands_all)
    pc_df = pd.DataFrame(poscontrol_detail(dfs, ths, poscontrol, cols_by_name))

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 80)

    print("=" * 100)
    print("① 分母膨胀检查 + ② 过滤前后计数 + ④ z 等效尺度")
    print("=" * 100)
    print(main_df.to_string(index=False))
    print("\n判读：ratio_sig_over_all ≈ 1.0 → 显著性由分母决定，与效应量无关（阈值救不了，先修 SE）")
    print("      pct_fdr05_of_tested > 70 或 direction_asymmetry > 10 → 分母膨胀指纹")
    print("      median_z_sig 远大于 1.96 → SE 被低估；z_equivalent_θ = 该阈值要求几倍 SE（惯例 1.96）")
    print("=" * 100)

    if len(band_df):
        print("\n③ 边界带区分力（被更严阈值砍掉那一带还剩多少统计证据）")
        print(band_df.to_string(index=False))
        print("判读：median_fdr_band 仍极小（1e-16 级）→ p 值无法区分两档阈值，属生物学判断")

    if len(pc_df):
        print("\n⑤ 正对照基因逐个 |coef|（同一通路基因散落阈值两侧 = 阈值人为性的直接证据）")
        print(pc_df.sort_values(["dataset", "max_abs_coef"], ascending=[True, False])
              .to_string(index=False))

    if a.out:
        main_df.to_csv(a.out, index=False)
        if len(band_df):
            band_df.to_csv(a.out.replace(".csv", "_bands.csv"), index=False)
        if len(pc_df):
            pc_df.to_csv(a.out.replace(".csv", "_poscontrol.csv"), index=False)
        print(f"\n[落盘] {a.out}")


if __name__ == "__main__":
    sys.exit(main())