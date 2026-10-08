#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""方向门控前提审计探针 —— 反向侧对照法（direction-premise audit）。

用途
----
任何以「某侧方向可信」为核心特征的方法（S=Z1*w(Z2)、sign gate、
concordance / direction-consistency 筛选），在把结论写进专利 claim 或论文之前，
用本探针检验该前提是否真的被数据支持。

核心洞察
--------
只检验「同向侧是否富集」会被共享技术混杂（覆盖度/检验力）骗过。
必须做反向侧对照：反向侧若同样富集（甚至更富集），则富集与方向无关。

用法
----
  python direction_premise_audit.py --table <csv> --z1 Z_human --z2 Z_monkey \
         --p2 p_monkey --thr 12 [--tiles2 n_tiles_m]

输出五组
--------
  ① 全局同向率            sign(Z1)==sign(Z2) 二项检验 vs 0.5
  ② 强效应池同向率        |Z1|>=thr 子集
  ③ 最可信子集同向率      p2<0.05 且 |Z1|>=thr      <-- 最致命，最该同向之处
  ④ 反向侧对照            反向&p2<0.05 富集倍数 vs 同向&p2<0.05
  ⑤ 共享混杂分解          corr(|Z1|,|Z2|) / corr(tiles2,p2) / 按覆盖度分层同向率

判读
----
③ 或 ① 同向率显著 <0.5，或 ④ 反向富集 >= 同向富集
  → 方向门控前提不成立；富集来自共享技术混杂，不是方向保守；claim 必须改。
详见 references/substitutability-direction-premise-audit.md

实测（跨物种衰老可替代性专利 all 口径）: ① 0.4636 p=3.2e-20 | ② 0.4131 p=7.2e-11
③ 0.3993 (357同 vs 537反) p=1.9e-9 | ④ 反向13.0x > 同向12.3x  → 前提不成立
"""
from __future__ import annotations

import argparse
import numpy as np
import pandas as pd
from scipy import stats as st


def _binom(tag: str, k: int, n: int) -> float:
    """同向率二项检验（vs 0.5 双侧）。"""
    if n == 0:
        print(f"{tag}: n=0 无法检验")
        return float("nan")
    p = st.binomtest(int(k), int(n), 0.5, alternative="two-sided").pvalue
    flag = ""
    if k < n * 0.5 and p < 0.05:
        flag = ">>> 同向率显著低于随机【前提可疑】"
    elif k > n * 0.5 and p < 0.05:
        flag = ">>> 同向率显著高于随机【前提被支持】"
    print(f"{tag}: n={n}  同向={k} ({k / n:.4f})  期望={n * 0.5:.0f}  二项 p={p:.3e}  {flag}")
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True, help="基因级表 CSV（含 Z1/Z2/p2 列）")
    ap.add_argument("--z1", default="Z_human", help="大样本/主体侧标准化效应量列名")
    ap.add_argument("--z2", default="Z_monkey", help="小样本/参考侧标准化效应量列名")
    ap.add_argument("--p2", default="p_monkey", help="参考侧 p 值列名")
    ap.add_argument("--thr", type=float, default=12.0, help="主体侧强效应阈值 tau_A")
    ap.add_argument("--tiles2", default="", help="参考侧 tile 数（可选，用于混杂分解/分层）")
    a = ap.parse_args()

    df = pd.read_csv(a.table)
    missing = [c for c in (a.z1, a.z2, a.p2) if c not in df.columns]
    if missing:
        print(f"[FATAL] 缺列 {missing}；实际列 = {list(df.columns)}")
        return 2

    z1 = df[a.z1].to_numpy(float)
    z2 = df[a.z2].to_numpy(float)
    p2 = df[a.p2].to_numpy(float)
    sd = np.sign(z1) == np.sign(z2)
    strong = np.abs(z1) >= a.thr

    print(f"表: {a.table}   n={len(df)}   thr={a.thr:g}")
    print(f"同向定义: sign({a.z1}) == sign({a.z2})\n")

    print("=== (1) 全局同向率 ===")
    _binom("全局", int(sd.sum()), int(len(sd)))

    print("\n=== (2) 强效应池同向率 ===")
    _binom(f"|{a.z1}|>={a.thr:g}", int(sd[strong].sum()), int(strong.sum()))

    print("\n=== (3) 最可信子集同向率（最致命）===")
    sel = strong & (p2 < 0.05)
    _binom(f"|{a.z1}|>={a.thr:g} & {a.p2}<0.05", int(sd[sel].sum()), int(sel.sum()))

    print("\n=== (4) 反向侧对照（核心）===")
    same_pool = int(sd[strong].sum())
    diff_pool = int(strong.sum()) - same_pool
    ns = int((strong & (p2 < 0.05) & sd).sum())
    nd = int((strong & (p2 < 0.05) & ~sd).sum())
    es = ns / (same_pool * 0.05) if same_pool else float("nan")
    ed = nd / (diff_pool * 0.05) if diff_pool else float("nan")
    print(f"  同向池={same_pool}  命中 {ns}  期望 {same_pool * 0.05:.1f}  富集 {es:.1f}x")
    print(f"  反向池={diff_pool}  命中 {nd}  期望 {diff_pool * 0.05:.1f}  富集 {ed:.1f}x")
    if np.isfinite(es) and np.isfinite(ed):
        if ed >= es:
            print("  >>> 反向侧富集 >= 同向侧 → 富集来自共享混杂，非方向保守【claim 必须改】")
        else:
            print("  >>> 同向侧富集 > 反向侧 → 门控确有选择性【前提部分被支持】")

    print("\n=== (5) 共享混杂分解 ===")
    print(f"  corr(|{a.z1}|,|{a.z2}|)      = {np.corrcoef(np.abs(z1), np.abs(z2))[0, 1]:+.4f}")
    print(f"  corr({a.z1}, {a.z2})         = {np.corrcoef(z1, z2)[0, 1]:+.4f}")
    print(f"  corr(|{a.z1}|,-log10{a.p2})  = "
          f"{np.corrcoef(np.abs(z1), -np.log10(np.clip(p2, 1e-300, 1)))[0, 1]:+.4f}")
    if a.tiles2 and a.tiles2 in df.columns:
        t2 = df[a.tiles2].to_numpy(float)
        print(f"  corr({a.tiles2},|{a.z2}|)    = {np.corrcoef(t2, np.abs(z2))[0, 1]:+.4f}")
        print(f"  corr({a.tiles2},{a.p2})      = {np.corrcoef(t2, p2)[0, 1]:+.4f}"
              f"   (负 = 覆盖高→p 小→检验力混杂)")
        q = pd.qcut(t2, 4, labels=["Q1low", "Q2", "Q3", "Q4high"], duplicates="drop").astype(str)
        print("  按参考侧覆盖度分层的同向率（各层均<0.5 → 方向系统性反相关，非单层所致）:")
        for lab in ("Q1low", "Q2", "Q3", "Q4high"):
            m = (q == lab).to_numpy()
            if m.sum() == 0:
                continue
            print(f"    {lab}: n={int(m.sum())}  全局={sd[m].mean():.4f}"
                  f"  池内={sd[m & strong].mean():.4f} (n={int((m & strong).sum())})")
    else:
        print("  (未提供 --tiles2，跳过覆盖度分层)")

    print("\n判读：③ 显著<0.5 或 ④ 反向>=同向 → 方向门控前提不成立，claim 必须改。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
