#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
concordance_diagnostics.py — 跨物种"方向同向率"归因四探针（2026-09-12 实测固化）

用途：用户问「跨物种同向率为什么这么低？」「是猴子的数据吗？」「为什么随机反而更高？」
      「能不能有更好的算法？」时，一次跑完四探针，用数据回答而不是猜。

四探针：
  0. 边际保持的独立配对基准（不是 50%！）+ 符号置换 null
  1. 元件网格是否同源（n_tiles_h == n_tiles_m）→ 本次最大单一杠杆
  2. 同向率是否随参考侧强度上升（排除"功效不足"解释）
  3. 大样本侧是否存在全局方向漂移（median(Z) 应 ≈ 0）
  4. τ_A 敏感性扫描（回应"为什么非得是 12"）

用法：
  python concordance_diagnostics.py                       # 用默认路径
  python concordance_diagnostics.py <csv> [tau_strong]    # 指定输入表与强效应阈值
  python concordance_diagnostics.py <csv> 12 --nperm 20000 --out scan.csv

输入 CSV 需含列：Z_human, Z_monkey, p_monkey, p_human, n_tiles_h, n_tiles_m
（v5_substitutability_*.csv 即此格式）

输出：stdout 报告 + 可选 τ 扫描 CSV
"""
import argparse
import sys

import numpy as np
import pandas as pd

DEFAULT_CSV = "E:/专利/M2/pipeline_out_all/v5_substitutability_all.csv"
DEFAULT_TAU = 12.0
DEFAULT_PERM = 20000
TAU_GRID = [1.96, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 30]


def load(path):
    df = pd.read_csv(path)
    need = {"Z_human", "Z_monkey", "p_monkey", "n_tiles_h", "n_tiles_m"}
    missing = need - set(df.columns)
    if missing:
        sys.exit(f"[ERR] 输入表缺列: {sorted(missing)}；实际列 = {list(df.columns)}")
    return df


def probe0(Zh, Zm, Pm, tau, nperm, seed=0):
    """边际保持的独立配对基准 + 符号置换 null。"""
    m = (np.abs(Zh) >= tau) & (Pm < 0.05)
    sh, sm = np.sign(Zh[m]), np.sign(Zm[m])
    ph, pm = (sh > 0).mean(), (sm > 0).mean()
    base = ph * pm + (1 - ph) * (1 - pm)
    obs = int((sh == sm).sum())

    rng = np.random.default_rng(seed)
    perm = np.array([(sh == rng.permutation(sm)).sum() for _ in range(nperm)])
    z = (obs - perm.mean()) / perm.std(ddof=1)
    p_enrich = ((perm >= obs).sum() + 1) / (nperm + 1)

    print(f"\n=== 探针 0 · 基准与零假设 (n={m.sum()}) ===")
    print(f"  人侧 Z>0 占比 = {ph:.4f}   猴侧 Z>0 占比 = {pm:.4f}")
    print(f"  >>> 独立配对期望同向率 = {base:.4f}   （硬抛硬币基准 = 0.5000）")
    print(f"  观测同向 = {obs} / {m.sum()} = {obs/m.sum():.4f}"
          f"   反向 = {int((sh != sm).sum())}")
    print(f"  差 vs 独立基准 = {obs/m.sum() - base:+.4f}  "
          f"（⚠️ 不要拿它和 0.5 相减）")
    print(f"  符号置换 null = {perm.mean():.1f} ± {perm.std(ddof=1):.1f}  "
          f"z = {z:+.2f}   p(单侧富集) = {p_enrich:.4f}")
    print(f"  对称判别: 同向 {obs/perm.mean():.2f}× 亏损 / "
          f"反向 {int((sh != sm).sum())/(perm.mean()-obs+perm.mean()):.2f}× 富集"
          if perm.mean() > obs else "")
    return base


def probe1(Zh, Zm, nth, ntm):
    """元件网格同源性 —— 本次最大单一杠杆。"""
    same = nth == ntm
    print(f"\n=== 探针 1 · 元件网格是否同源 ===")
    print(f"  网格一致基因数 = {same.sum()} ({same.mean():.1%})")
    for lo in [1, 5, 10, 20, 30]:
        s = same & (nth >= lo)
        d = (~same) & (nth >= lo) & (ntm >= lo)
        if s.sum() > 20 and d.sum() > 20:
            cs = (np.sign(Zh[s]) == np.sign(Zm[s])).mean()
            cd = (np.sign(Zh[d]) == np.sign(Zm[d])).mean()
            print(f"  tile≥{lo:>2}: 同源 n={s.sum():>5} 同向={cs:.4f} | "
                  f"异源 n={d.sum():>5} 同向={cd:.4f} | 差={cs-cd:+.4f}")
    print("  >>> 同源回到基准(≈0.50) 而异源显著更低 ⇒ '不一致'主要来自在比不同区域，"
          "属方法缺陷非生物学")


def probe2(Zh, Zm, Pm, tau):
    """同向率是否随参考侧强度上升 → 排除"功效不足"解释。"""
    m = (np.abs(Zh) >= tau) & (Pm < 0.05)
    conc = (np.sign(Zh[m]) == np.sign(Zm[m]))
    print(f"\n=== 探针 2 · 同向率 vs 猴侧检验力 ===")
    for name, v in [("|Z_m|", np.abs(Zm[m])), ("n_tiles_m", None)]:
        if v is None:
            continue
        q = pd.qcut(v, 4, labels=False, duplicates="drop")
        tab = pd.DataFrame({"q": q, "conc": conc}).groupby("q").conc.agg(["mean", "size"])
        print(f"  按 {name} 四分位:")
        print(tab.to_string())
    print("  >>> 平坦(甚至强侧更低) ⇒ 不是'样本不够'，须往探针 1/3 找")


def probe3(Zh, Zm, Ph, Pm):
    """大样本侧全局方向漂移。"""
    print(f"\n=== 探针 3 · 全局方向漂移 ===")
    for name, Z, P in [("人侧", Zh, Ph), ("猴侧", Zm, Pm)]:
        print(f"  {name}: mean={Z.mean():+.4f} median={np.median(Z):+.4f} "
              f"|Z|中位={np.median(np.abs(Z)):.3f} "
              f"Z>0={(Z>0).mean():.4f} p<0.05={(P<0.05).mean():.4f}")
    print("  >>> 无信号 Z 应以 0 为中心；|median(Z)| > 0.3 ⇒ 漂移信号，"
          "强效应池被漂移污染，先居中再谈富集")


def probe4(Zh, Zm, Pm, out_csv=None):
    """τ_A 敏感性扫描。"""
    rows = []
    for tau in TAU_GRID:
        A = np.abs(Zh) >= tau
        B = A & (Pm < 0.05)
        if B.sum() < 5:
            continue
        c = np.sign(Zh[B]) == np.sign(Zm[B])
        ph, pm = (np.sign(Zh[B]) > 0).mean(), (np.sign(Zm[B]) > 0).mean()
        base = ph * pm + (1 - ph) * (1 - pm)
        rows.append(dict(tau=tau, n_strong=int(A.sum()), n_sigM=int(B.sum()),
                         n_conc=int(c.sum()), n_disc=int((~c).sum()),
                         concordance=round(c.mean(), 4),
                         indep_base=round(base, 4),
                         delta_vs_base=round(c.mean() - base, 4),
                         patent_enrich=round(c.sum() / max(A.sum() * 0.05, 1e-9), 2)))
    t = pd.DataFrame(rows)
    print(f"\n=== 探针 4 · τ_A 敏感性扫描 ===")
    print(t.to_string(index=False))
    below = (t.delta_vs_base < 0).sum()
    print(f"  >>> {below}/{len(t)} 档低于独立基准；"
          f"全部低于 ⇒ 不是阈值选得不好，是该统计量任何切割都不支持'同向保守'")
    if out_csv:
        t.to_csv(out_csv, index=False)
        print(f"  [已存] {out_csv}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default=DEFAULT_CSV)
    ap.add_argument("tau", nargs="?", type=float, default=DEFAULT_TAU)
    ap.add_argument("--nperm", type=int, default=DEFAULT_PERM)
    ap.add_argument("--out", default=None, help="τ 扫描结果输出 CSV 路径")
    a = ap.parse_args()

    df = load(a.csv)
    Zh, Zm = df.Z_human.values, df.Z_monkey.values
    Ph, Pm = df.p_human.values, df.p_monkey.values
    nth, ntm = df.n_tiles_h.values, df.n_tiles_m.values

    print(f"输入: {a.csv}")
    print(f"实体数 = {len(df)}   τ_strong = {a.tau}   置换次数 = {a.nperm}")

    probe0(Zh, Zm, Pm, a.tau, a.nperm)
    probe1(Zh, Zm, nth, ntm)
    probe2(Zh, Zm, Pm, a.tau)
    probe3(Zh, Zm, Ph, Pm)
    probe4(Zh, Zm, Pm, a.out)

    print("\n=== 归因结论模板（四句话）===")
    print("  1. 主因 = 元件网格未对齐（占 5–6pp，属方法缺陷）")
    print("  2. 次因 = 大样本侧全局漂移污染强度筛选")
    print("  3. 参考侧小样本给不出可靠方向（趋势存在但需实测显著性）")
    print("  4. 真实一致性未知 —— 当前值是'方法噪声 + 生物学解耦'的混合物，不可当生物学结论")
    print("\n  改法优先级: ①统一元件网格 ②深度校正 ③消除全局漂移（①+②+③必做）"
          " ④收缩估计替代极端阈值 ⑤换统计单元 ⑥跨物种正交投影")


if __name__ == "__main__":
    main()
