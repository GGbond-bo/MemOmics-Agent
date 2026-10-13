#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""秩检验「离散下界」探针 —— 回答「这个效应在本样本量下有没有资格显著」。

用法:
    python check_nonparametric_floor.py <effect_table.csv> [--alpha 0.05] [--pcol p_np] [--qcol q]

输入表需含列: effect, p_np(或 --pcol 指定), n1, n2 （可选: eff_type, q, aux2）
      n2 == n1 且 design.paired=True  → 配对（n1 = 对数）
      design.paired=False             → 独立（n1 vs n2）

⛔ 设计字典必须手写/从建表脚本抄，禁止从表里 n1==n2 推断配对与独立
   （n1=n2 在「独立 7vs7」和「配对 7 对」上完全同形）。

输出: 每效应 {下界, BH门槛, 可达性, 名义显著数, q显著数, 钉在下界数} + 配对恒等式核验。
"""
import argparse
import sys
from math import comb

import numpy as np
import pandas as pd

# ============================================================
# 设计字典 —— 改成你项目的（本例抄自 build_effect5_v3.py L24-29）
#   paired=True  → Wilcoxon 符号秩，n1 = 配对数，下界 = 2/2^n1
#   paired=False → Mann-Whitney U，下界 = 2/C(n1+n2, n1)
# 数值留 None = 从表里读 n1/n2（但仍须给 paired 标志）
# ============================================================
DESIGN = {
    "Aging":   dict(paired=False, n1=10, n2=7),
    "T2D":     dict(paired=False, n1=7,  n2=7),
    "ExYoung": dict(paired=True,  n1=10, n2=None),
    "ExOld":   dict(paired=True,  n1=7,  n2=None),
    "ExT2D":   dict(paired=True,  n1=7,  n2=None),
}


def floor_p(paired, n1, n2):
    """双侧最小可达 p。"""
    if paired:
        return 2.0 / (2 ** n1)
    return 2.0 / comb(n1 + n2, n1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("table")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--pcol", default="p_np")
    ap.add_argument("--qcol", default="q")
    a = ap.parse_args()

    df = pd.read_csv(a.table)
    for c in ("effect", a.pcol, "n1", "n2"):
        if c not in df.columns:
            sys.exit(f"表缺列 {c}；实际列: {list(df.columns)}")

    print(f"表: {a.table}  ({len(df)} 格)  alpha={a.alpha}")
    print(f"设计字典 {len(DESIGN)} 个效应（务必与建表脚本一致，勿从 n1==n2 推断）\n")

    hdr = f"{'效应':8s} {'检验':18s} {'n':11s} {'下界':>11s} {'门槛':>11s} {'可达':>5s} {'p<α':>6s} {'q<α':>6s} {'钉下界':>7s}"
    print(hdr)
    print("-" * len(hdr))

    unknown = [e for e in df.effect.unique() if e not in DESIGN]
    summary = {}
    for eff, d in DESIGN.items():
        s = df[df.effect == eff]
        if s.empty:
            continue
        n1 = d["n1"] if d["n1"] is not None else int(s.n1.iloc[0])
        n2 = d["n2"] if d["n2"] is not None else (n1 if d["paired"] else int(s.n2.iloc[0]))
        m = len(s)
        fl = floor_p(d["paired"], n1, n2)
        thr = a.alpha / m                      # BH 最严门槛（rank 1）
        kind = "Wilcoxon配对" if d["paired"] else "Mann-Whitney独立"
        nlab = f"{n1}对" if d["paired"] else f"{n1} vs {n2}"
        at = int(np.isclose(s[a.pcol].values, fl, rtol=1e-9, atol=1e-15).sum())
        nq = int((s[a.qcol] < a.alpha).sum()) if a.qcol in s.columns else -1
        print(f"{eff:8s} {kind:18s} {nlab:11s} {fl:11.3e} {thr:11.3e} "
              f"{'是' if fl < thr else '否':>5s} {int((s[a.pcol] < a.alpha).sum()):6d} "
              f"{(f'{nq:6d}' if nq >= 0 else '   n/a')} {at:7d}")
        summary[eff] = dict(floor=fl, thr=thr, reachable=fl < thr, n=m,
                            p_sig=int((s[a.pcol] < a.alpha).sum()), q_sig=nq, at_floor=at)

    print("\n判定:")
    for eff, r in summary.items():
        if r["reachable"]:
            print(f"  {eff}: 下界 {r['floor']:.3e} < 门槛 {r['thr']:.3e} → 有可能显著；"
                  f"实测 p<α {r['p_sig']}/{r['n']}"
                  + (f"，q<α {r['q_sig']}/{r['n']}" if r["q_sig"] >= 0 else ""))
        else:
            print(f"  {eff}: 下界 {r['floor']:.3e} > 门槛 {r['thr']:.3e} "
                  f"({r['floor']/r['thr']:.1f}×) → ⛔ 数学上不可能显著（不可检出，≠ 无效）;"
                  f" 钉在下界 {r['at_floor']}/{r['n']} 格（= 已饱和）")

    if unknown:
        print(f"\n⚠️ 表里出现但设计字典未定义: {unknown}")

    # 配对恒等式核验（aux2 = r）
    if "aux2" in df.columns and "eff" in df.columns:
        pc = df[(df.aux2.notna())]
        if len(pc):
            r = float(pc.aux2.median())
            ratio = float((pc.aux2 * 0 + 1).median())  # placeholder, see below
            print(f"\n配对恒等式核验: r(Pre,Post) 中位 = {r:.3f}")
            print(f"  理论 d_z/d_av = 1/sqrt(2(1-r)) = {1/np.sqrt(2*(1-r)):.3f}")
            print("  （拿表内 d_z 与 d_av 两列相除应与之吻合 ⇒ 证明逐 donor 配准；r≤0 说明配对无收益）")
            if r <= 0:
                print("  ⚠️ r ≤ 0：该组配对检验效率低于独立检验，须如实报告（不许偷偷切回独立口径掩盖）")

    print("\n措辞: 0 显著 ⇒ 「该样本量下统计上不可检出（可给出下界与门槛的数字）」，禁写「无效/没有效应」。")
    print("提功效四路: ① 缩小检验族 ② 聚合到程序层做方向一致性检验 ③ 加样本量 ④ 用 p_par（配对 t，无下界）做敏感性分析。")


if __name__ == "__main__":
    main()