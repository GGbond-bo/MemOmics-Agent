#!/usr/bin/env python3
"""
caliber_switch_impact.py —— 效应量口径切换的影响量化探针（d_av <-> d_z）

用途
    用户/审稿人问「配对比较的效应量要不要从 d_av 换成 d_z（或反向）」时，
    ⛔ 不要凭公式给建议（「d_z 虚高 58%」只在**高 r** 成立，r 低/为负时方向翻转）。
    先跑本探针量出**实际代价**。

判据（核心）
    完整双旗（p<阈值 且 |d|>阈值）翻转数 == 0
        ⇒ 换口径只是换注脚，不是改结论（风险极低，可直接改）
    有翻转
        ⇒ 把翻转的格摆给用户拍板，并说明是变宽还是变窄

四个审计量（本类项目实测样例：660 配对格，eff=d_av / aux1=d_z）
    Spearman rho                    0.986          图的高低形态几乎不动
    完整双旗翻转                     18->18 / 43->43 / 12->12 = 0   显著性结论零改变
    单看 |d|>阈值                    净减 65 格（全被 p 旗拦住）
    逐栏缩放 (d_z/d_av 中位)         ExYoung 0.978 / ExOld 0.888 / ExT2D 0.651

用法（effect5_effsize_v3.csv 的典型形态）
    python caliber_switch_impact.py \
        --csv effect5_effsize_v3.csv \
        --eff-col eff --dz-col aux1 --p-col p_np \
        --score-col score --sub-col sub --effect-col effect \
        --paired-effects ExYoung,ExOld,ExT2D

⚠️ 表结构陷阱（本类建表脚本实测）
    多用途列：配对行的 `aux1` = d_z，但**独立行的 `aux1` = J（Hedges 校正因子）**。
    ⇒ 必须用 --paired-effects 过滤到配对栏；若表里有 eff_type 列，本脚本会自动加一道护栏。
    判行类型一律先看 eff_type，不要把 aux1 直接当 d_z 用（Aging 行会拿到 J≈0.949）。
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="量化效应量口径切换（d_av<->d_z）的实际影响")
    ap.add_argument("--csv", required=True, help="效应量表（长表：每行 = 一个量 x 一个效应格）")
    ap.add_argument("--eff-col", default="eff", help="d_av 列（默认 eff）")
    ap.add_argument("--dz-col", default="aux1", help="d_z 列（默认 aux1；配对行才有意义）")
    ap.add_argument("--p-col", default="p_np", help="p 值列（默认 p_np）")
    ap.add_argument("--score-col", default="score", help="量/程序列（默认 score）")
    ap.add_argument("--sub-col", default="sub", help="分层列（如亚群，默认 sub）")
    ap.add_argument("--effect-col", default="effect", help="效应列（默认 effect）")
    ap.add_argument("--type-col", default="eff_type",
                    help="行类型列（默认 eff_type；配对行通常 = d_av）。不存在则跳过护栏")
    ap.add_argument("--paired-effects", required=True,
                    help="配对效应名，逗号分隔（只对这几栏做切换，独立栏必须排除）")
    ap.add_argument("--d-thresh", type=float, default=0.5, help="效应量旗阈值（默认 0.5）")
    ap.add_argument("--p-thresh", type=float, default=0.05, help="p 值旗阈值（默认 0.05）")
    ap.add_argument("--target", default="dz", choices=["dz", "dav"],
                    help="往哪个方向切：dz=算 d_av->d_z 的代价（默认）")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)
    df = pd.read_csv(a.csv)

    need = [a.eff_col, a.dz_col, a.p_col, a.effect_col]
    missing = [c for c in need if c not in df.columns]
    if missing:
        print(f"[FATAL] 表里缺列: {missing}\n实际列: {list(df.columns)}", file=sys.stderr)
        return 2

    paired = [e.strip() for e in a.paired_effects.split(",") if e.strip()]
    sub = df[df[a.effect_col].isin(paired)].copy()

    # ---- 护栏 1：只留配对行（独立行 aux1 = J，不是 d_z）----
    if a.type_col in sub.columns:
        types = sub[a.type_col].astype(str)
        looks_paired = types.str.contains("d_av|dz|paired", case=False, na=False)
        if looks_paired.any():
            dropped = int((~looks_paired).sum())
            sub = sub[looks_paired]
            print(f"[guard] 按 {a.type_col} 过滤掉 {dropped} 个非配对行（独立行 {a.dz_col}=J，非 d_z）")
    else:
        print(f"[warn] 无 {a.type_col} 列 → 只靠 --paired-effects 过滤，请自行确认栏内全是配对行")

    sub = sub.dropna(subset=[a.eff_col, a.dz_col, a.p_col])
    if sub.empty:
        print("[FATAL] 过滤后无可用行，检查 --paired-effects 名称是否与表内一致", file=sys.stderr)
        return 2

    dav = sub[a.eff_col].to_numpy(float)
    dz = sub[a.dz_col].to_numpy(float)
    p = sub[a.p_col].to_numpy(float)
    eff = sub[a.effect_col].astype(str).to_numpy()

    # ---- 四个审计量 ----
    rho = spearmanr(dav, dz).statistic

    def flag(d, thr_d, thr_p):
        return (p < thr_p) & (np.abs(d) > thr_d)

    fav, fz = flag(dav, a.d_thresh, a.p_thresh), flag(dz, a.d_thresh, a.p_thresh)
    mag_av = np.abs(dav) > a.d_thresh
    mag_z = np.abs(dz) > a.d_thresh

    print(f"\n=== 口径切换影响：{a.eff_col}={a.target=='dz' and 'd_av' or 'd_z'} "
          f"→ {a.dz_col if a.target=='dz' else a.eff_col} | {len(sub)} 格 / {len(paired)} 栏 ===")
    print(f"跨格排序一致性  Spearman rho = {rho:.3f}   (越接近 1，图的形态越不动)")

    print(f"\n完整双旗（p<{a.p_thresh} 且 |d|>{a.d_thresh}）逐栏翻转：")
    tot_flip = 0
    rows = []
    for e in paired:
        m = eff == e
        if not m.any():
            continue
        n_av, n_z = int(fav[m].sum()), int(fz[m].sum())
        flip = int((fav[m] != fz[m]).sum())
        tot_flip += flip
        ratio = float(np.nanmedian(np.abs(dz[m]) / np.abs(dav[m]))) if np.abs(dav[m]).any() else np.nan
        rows.append((e, n_av, n_z, flip, ratio))
        print(f"  {e:<10} {n_av:>4} → {n_z:<4}  翻转 {flip:<4}  |d|缩放中位 {ratio:.3f}")

    net_mag = int(mag_z.sum() - mag_av.sum())
    print(f"\n单看 |d|>{a.d_thresh}（不看 p）：{int(mag_av.sum())} → {int(mag_z.sum())}  净变化 {net_mag:+d}")
    print("  （这些格若被 p 旗拦住，就不进最终显著集 —— 上表翻转数才是结论级影响）")

    per = pd.DataFrame(rows, columns=["effect", "n_flag_dav", "n_flag_dz", "n_flip", "abs_d_ratio"])
    per.to_csv("caliber_switch_per_effect.csv", index=False)
    print("\n逐栏表已写 caliber_switch_per_effect.csv")

    if tot_flip == 0:
        print("\n[判定] 完整双旗翻转 = 0 ⇒ 换口径只是换注脚，不是改结论（风险极低，可直接改）。")
        print("       仍应在交付里说明：某栏深浅会变（看 |d|缩放中位），不可跨栏直接比深浅。")
    else:
        print(f"\n[判定] 完整双旗翻转 = {tot_flip} ⇒ 结论会变，必须把翻转的格摆给用户拍板。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())