#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
逐实体对账：判定两次跑的结果是否来自同一输入口径。

用法
----
# 1) 正本 vs 两个候选复现（标准用法）
python diff_two_runs.py --ref 正本.csv --cand continuous.csv --cand all.csv

# 2) 指定比对列 / 实体 key
python diff_two_runs.py --ref a.csv --cand b.csv --key symbol --cols Z_monkey,Z_human

# 3) 单实体溯源（打印某实体的全部字段）
python diff_two_runs.py --ref a.csv --cand b.csv --entity AGBL2

判读（三判决，见 SKILL.md「输入口径对账与复现溯源」）
-------------------------------------------------
① 一致率 ~100% 且最大差 ~0            → 同一输入表（差异只在聚合/桥接取舍）
② 一致率 ~0%   且中位差/最大差显著>0  → 输入表不同，调参无用
③ 实体数相同但值不同                  → 同一坐标网格、不同值体系 ⇒ 一定是另一张输入表

输出四元组：共有实体数 / 一致率(±1e-4) / 中位差 / 最大差
"""
import argparse
import sys

import numpy as np
import pandas as pd

TOL = 1e-4


def load(path, key):
    df = pd.read_csv(path)
    if key not in df.columns:
        sys.exit(f"[ERR] {path} 缺 key 列 '{key}'；实际列: {list(df.columns)}")
    dup = df[key].duplicated().sum()
    if dup:
        print(f"[WARN] {path} 的 key '{key}' 有 {dup} 个重复值，merge 会膨胀行数")
    return df


def compare(ref, cand, key, cols):
    """返回 (共有数, 一致率, 中位差, 最大差, 每列明细)"""
    m = ref.merge(cand, on=key, suffixes=('_ref', '_cand'))
    if m.empty:
        return 0, np.nan, np.nan, np.nan, {}
    detail = {}
    for c in cols:
        a, b = m.get(f"{c}_ref"), m.get(f"{c}_cand")
        if a is None or b is None:
            continue
        d = (a.astype(float) - b.astype(float)).abs()
        detail[c] = (float(np.mean(d < TOL)), float(d.median()), float(d.max()))
    if not detail:
        return len(m), np.nan, np.nan, np.nan, {}
    # 用第一个可用列作为汇总口径（默认 Z_monkey）
    first = detail[cols[0]] if cols[0] in detail else next(iter(detail.values()))
    return len(m), first[0], first[1], first[2], detail


def verdict(rate, med, mx):
    if np.isnan(rate):
        return "无法判定（共有实体为 0）"
    if rate >= 0.99 and (mx is None or mx < 1e-3):
        return "① 同一输入表 —— 差异仅为聚合/桥接取舍"
    if rate <= 0.01:
        return "② 输入表不同 —— 停止调参，改查输入文件"
    return "③ 部分一致 —— 需按实体分层核查（可能是网格/过滤口径差异）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="正本（参考）结果 csv")
    ap.add_argument("--cand", action="append", required=True, help="候选复现 csv，可多次传入")
    ap.add_argument("--key", default="symbol", help="实体 key 列（默认 symbol）")
    ap.add_argument("--cols", default="Z_monkey,Z_human,S,n_tiles_m,n_tiles_h",
                    help="要比对的数值列，逗号分隔")
    ap.add_argument("--entity", default=None, help="额外打印该实体的逐字段溯源表")
    args = ap.parse_args()

    cols = [c.strip() for c in args.cols.split(",") if c.strip()]
    ref = load(args.ref, args.key)
    print(f"[REF ] {args.ref}  ({len(ref)} 实体)\n")

    for cp in args.cand:
        cand = load(cp, args.key)
        n, rate, med, mx, detail = compare(ref, cand, args.key, cols)
        print(f"[CAND] {cp}  ({len(cand)} 实体)")
        print(f"       共有 {n} | 一致率(±{TOL}) {rate:.1%} | 中位差 {med:.4f} | 最大差 {mx:.4f}")
        for c, (r, md, x) in detail.items():
            print(f"         - {c:12s} 一致率 {r:6.1%}  中位差 {md:8.4f}  最大差 {x:9.4f}")
        print(f"       判决: {verdict(rate, med, mx)}\n")

        if args.entity:
            r = ref[ref[args.key] == args.entity]
            c = cand[cand[args.key] == args.entity]
            if r.empty or c.empty:
                print(f"       [{args.entity}] 在其中一方缺失：ref={len(r)} cand={len(c)}\n")
            else:
                print(f"       [{args.entity}] 逐字段溯源")
                keep = [k for k in list(r.columns) if k != args.key]
                for k in keep:
                    print(f"         {k:20s} ref={r.iloc[0][k]!s:24s} cand={c.iloc[0][k]!s}")
                print()


if __name__ == "__main__":
    main()
