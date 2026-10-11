#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
deg_table_power_probe.py — 多对比 DEG 表的「能不能做交集」体检器

在做任何交集 / 逆转分析之前跑它。回答四个必须先知道的问题：

  1. 每张 DEG 表的形态（宽表/长表？有哪些列？多少基因？）
  2. 每个对比的检出功效（显著数）—— 检出数是个位数的对比，交集必为 0，别做
  3. 阈值到底在不起作用（|effect| 中位数 vs 阈值）—— 中位数 > 阈值 = 阈值不设防
  4. 每对集合的真实交集 vs 随机期望 E=|A||B|/N、OR、Jaccard —— 没有基线的交集数没有信息量

用法
----
  # 宽表：一次对比一张表（.csv / .xlsx 混放也认）
  python deg_table_power_probe.py D:/path/DEG_file --threshold 0.25 --fdr 0.05

  # 长表：多对比堆在一张表（含 contrast / celltype 列）→ 必须拆分后再评估
  python deg_table_power_probe.py D:/path/file --split-by contrast
  python deg_table_power_probe.py D:/path/file --split-by contrast,celltype

  # 已知基因宇宙（推荐显式给；不给则用观测到的最大唯一基因数并标注 inferred）
  python deg_table_power_probe.py D:/path --universe 27015

  # 列名不对时手工指定
  python deg_table_power_probe.py D:/path --gene-col gene --effect-col logFC --fdr-col adj.P.Val

输出三个表：POWER / THRESHOLD / OVERLAP，最后一段是 VERDICT 判读。
无第三方依赖（pandas 之外只用标准库；scipy 有则给出 Fisher p，没有则跳过）。
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

GENE_KEYS = ("gene", "gene_symbol", "symbol", "genes", "gene_name", "feature", "x", "geneid")
EFF_KEYS = ("coef", "logfc", "avg_log2fc", "log2fc", "estimate", "beta", "lfc", "effect", "diff")
P_KEYS = ("p", "pval", "p_value", "p.value", "pval_nominal", "pvaladj")
FDR_KEYS = ("fdr", "padj", "p_adj", "adj.p.val", "p_adjust", "qval", "p_val_adj", "adj_p")


def pick(cols, keys):
    """按关键字优先、子串兜底挑列；挑不到返回 None。"""
    low = {c: str(c).strip().lower() for c in cols}
    for k in keys:
        for c, l in low.items():
            if l == k:
                return c
    for k in keys:
        for c, l in low.items():
            if k in l:
                return c
    return None


def read_any(path):
    """csv / tsv / xlsx 通吃；返回 DataFrame 或 None。"""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(path)
        if ext in (".tsv", ".txt"):
            return pd.read_csv(path, sep="\t", low_memory=False)
        return pd.read_csv(path, low_memory=False)
    except Exception as e:  # noqa: BLE001
        print(f"  !! 读不了 {os.path.basename(path)}: {e}")
        return None


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += sorted(glob.glob(os.path.join(p, "*.csv")))
            out += sorted(glob.glob(os.path.join(p, "*.tsv")))
            out += sorted(glob.glob(os.path.join(p, "*.xlsx")))
            out += sorted(glob.glob(os.path.join(p, "*.xls")))
        else:
            out.append(p)
    # 去重 + 按名排序
    seen, uniq = set(), []
    for f in out:
        k = os.path.abspath(f)
        if k not in seen and os.path.isfile(f):
            seen.add(k)
            uniq.append(f)
    return uniq


def fisher_or_p(a, b, c, d):
    """OR + (可选) Fisher p。2x2: [[a,b],[c,d]]"""
    if b * c == 0:
        return float("nan"), float("nan")
    orv = (a * d) / (b * c)
    try:
        from scipy.stats import fisher_exact  # type: ignore

        _, p = fisher_exact([[a, b], [c, d]])
        return orv, float(p)
    except Exception:  # noqa: BLE001
        return orv, float("nan")


def main():
    ap = argparse.ArgumentParser(description="多对比 DEG 表功效与交集基线体检")
    ap.add_argument("paths", nargs="+", help="DEG 文件或目录（可多个）")
    ap.add_argument("--gene-col", default=None)
    ap.add_argument("--effect-col", default=None)
    ap.add_argument("--fdr-col", default=None)
    ap.add_argument("--p-col", default=None)
    ap.add_argument("--threshold", type=float, default=0.25, help="|effect| 阈值（默认 0.25）")
    ap.add_argument("--fdr", type=float, default=0.05, help="FDR 阈值（默认 0.05）")
    ap.add_argument("--universe", type=int, default=None, help="基因宇宙 N（不给我会推断并标注）")
    ap.add_argument("--split-by", default=None, help="长表拆分列，逗号分隔，如 contrast,celltype")
    ap.add_argument("--min-power", type=int, default=50, help="低于此检出数视为功效不足（默认 50）")
    args = ap.parse_args()

    files = collect(args.paths)
    if not files:
        print("没有找到任何文件。检查路径。")
        return 1
    print(f"扫描到 {len(files)} 个文件\n")

    split_cols = [s.strip() for s in args.split_by.split(",")] if args.split_by else []

    # ---------- 装载 ----------
    groups: dict[str, dict] = {}   # name -> {genes:set, eff:dict, nrow, cols}
    for f in files:
        df = read_any(f)
        if df is None or df.empty:
            continue
        base = os.path.splitext(os.path.basename(f))[0]

        if args.gene_col:
            gcol = args.gene_col
        else:
            gcol = pick(df.columns, GENE_KEYS)
        scol = args.effect_col or pick(df.columns, EFF_KEYS)
        qcol = args.fdr_col or pick(df.columns, FDR_KEYS)
        pcol = args.p_col or pick(df.columns, P_KEYS)

        print(f"· {os.path.basename(f)}")
        print(f"    rows={len(df):,}  cols={list(df.columns)[:10]}")
        print(f"    识别列: gene={gcol} effect={scol} fdr={qcol} p={pcol}")
        if gcol is None or scol is None:
            print("    !! 识别不到基因列或效应量列 → 用 --gene-col/--effect-col 手工指定，跳过该文件\n")
            continue

        if split_cols:
            missing = [c for c in split_cols if c not in df.columns]
            if missing:
                print(f"    !! 缺拆分列 {missing}，该文件按整表处理")
            else:
                for key, sub in df.groupby(split_cols):
                    if not isinstance(key, tuple):
                        key = (key,)
                    name = base + " | " + " / ".join(str(k) for k in key)
                    _absorb(groups, name, sub, gcol, scol, qcol)
                print(f"    按 {split_cols} 拆成 {df.groupby(split_cols).ngroups} 组\n")
                continue

        _absorb(groups, base, df, gcol, scol, qcol)
        print()

    if not groups:
        print("没有任何可用分组。")
        return 1

    # ---------- 基因宇宙 ----------
    obs_universe = max((len(g["eff"]) for g in groups.values()), default=0)
    N = args.universe or obs_universe
    tag = "" if args.universe else "  (inferred = 观测最大唯一基因数，建议显式 --universe)"

    # ---------- POWER ----------
    print("=" * 92)
    print(f"POWER 表  (FDR<{args.fdr}, |effect|>{args.threshold}, N={N:,}{tag})")
    print("=" * 92)
    print(f"{'group':<52}{'rows':>8}{'genes':>8}{'sigFDR':>9}{'sigBOTH':>9}{'med|eff|':>10}")
    sigsets: dict[str, set] = {}
    effs: dict[str, dict] = {}
    for name, g in sorted(groups.items()):
        eff, q = g["eff"], g["fdr"]
        genes = list(eff)
        n_sig = 0
        if q is not None:
            n_sig = int(np.sum([q[k] < args.fdr for k in genes]))
        n_both = int(np.sum([abs(eff[k]) > args.threshold and (q is None or q[k] < args.fdr) for k in genes]))
        med = float(np.median([abs(v) for v in eff.values()])) if eff else float("nan")
        print(f"{name[:50]:<52}{g['nrow']:>8,}{len(genes):>8,}{n_sig:>9,}{n_both:>9,}{med:>10.4f}")
        sigsets[name] = {k for k in genes if abs(eff[k]) > args.threshold and (q is None or q[k] < args.fdr)}
        effs[name] = eff

    # ---------- THRESHOLD ----------
    print()
    print("=" * 92)
    print("THRESHOLD 诊断  (med|eff| > threshold → 阈值没在筛选)")
    print("=" * 92)
    for name, g in sorted(groups.items()):
        eff = g["eff"]
        if not eff:
            continue
        med = float(np.median([abs(v) for v in eff.values()]))
        flag = "!! 阈值不设防（砍不动）" if med > args.threshold else "ok 阈值在起作用"
        print(f"{name[:50]:<52} med|eff|={med:.4f}  thr={args.threshold}  {flag}")

    # ---------- OVERLAP ----------
    names = sorted(sigsets)
    print()
    print("=" * 92)
    print("OVERLAP 表  (obs=真实交集 / E=随机期望 |A||B|/N / OR / Jaccard)")
    print("=" * 92)
    print(f"{'A':<26}{'B':<26}{'|A|':>7}{'|B|':>7}{'obs':>7}{'E':>8}{'obs/E':>7}{'OR':>8}{'Jacc':>7}")
    warn = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            A, B = sigsets[names[i]], sigsets[names[j]]
            if not A or not B:
                continue
            obs = len(A & B)
            E = len(A) * len(B) / N if N else float("nan")
            ratio = obs / E if E else float("nan")
            a = obs
            b = len(A) - obs
            c = len(B) - obs
            d = N - a - b - c
            orv, _ = fisher_or_p(a, b, c, d)
            jac = obs / len(A | B) if (A | B) else float("nan")
            print(
                f"{names[i][:24]:<26}{names[j][:24]:<26}{len(A):>7,}{len(B):>7,}"
                f"{obs:>7,}{E:>8.1f}{ratio:>7.2f}{orv:>8.2f}{jac:>7.3f}"
            )
            if obs <= E:
                warn.append(f"{names[i]} ∩ {names[j]}: obs({obs}) <= E({E:.0f}) → 无富集证据")
            if min(len(A), len(B)) < args.min_power:
                warn.append(f"{names[i]} ∩ {names[j]}: 一边仅 {min(len(A), len(B))} 个基因 < {args.min_power} → 功效不足，交集不可解释")

    # ---------- VERDICT ----------
    print()
    print("=" * 92)
    print("VERDICT")
    print("=" * 92)
    low = [(n, len(s)) for n, s in sigsets.items() if len(s) < args.min_power]
    if low:
        print(f"[!] {len(low)} 个集合功效不足（<{args.min_power} 基因），涉及它们的交集不要下结论：")
        for n, s in sorted(low, key=lambda x: x[1])[:12]:
            print(f"      {n[:60]:<62} {s} 个")
    else:
        print("[ok] 所有集合检出数都在可用范围")
    for w in warn[:15]:
        print(f"[!] {w}")
    if N and sigsets:
        mx = max(len(s) for s in sigsets.values())
        if mx / N > 0.5:
            print(f"[!] 存在超大集合（{mx:,}/{N:,} = {mx/N:.0%} 的基因宇宙）→ 任何与它的交集都会被它吞掉，"
                  f"必须报 OR/Jaccard，不能报原始交集数")
    print("[next] 1) 锁定文件名 A_vs_B 的正负号语义（找已知方向的 marker 做正对照）")
    print("       2) 按四象限拆交集（同向=加剧 / 反向=逆转），不要合并成一个数")
    print("       3) 富集背景用 N，不用全基因组；小交集以 GSEA 为主")
    return 0


def _absorb(groups, name, df, gcol, scol, qcol):
    """把一张（或拆分后的）表收进 groups；同基因取首个出现的值。"""
    eff, fdr = {}, {}
    for g, v, q in zip(df[gcol], df[scol], df[qcol] if qcol else [None] * len(df)):
        if pd.isna(g) or pd.isna(v):
            continue
        g = str(g)
        if g in eff:
            continue
        eff[g] = float(v)
        if qcol:
            fdr[g] = float(q) if not pd.isna(q) else 1.0
    groups[name] = {"eff": eff, "fdr": fdr if qcol else None, "nrow": len(df)}


if __name__ == "__main__":
    sys.exit(main())