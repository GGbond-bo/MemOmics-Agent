#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
detect_circular_matched_null.py — 「分层匹配基准率」零假设的循环性检测（三判据）

背景：很多方法类交付件用「按混杂分层后的匹配基准率（matched base rate）」当零假设，
      若层内率是用**观测值自己**算出来的，则该零假设永不可失败（z≈0 是恒等式）。
      本探针一次输出三条判据的机器判定，并同屏给出「无信息基准 0.5」的对照。

三判据：
  ① 包含性   mask 是否完全落在单个分层内（mask \\ 顶层 == 0）
  ② 等值性   expB 是否等于该层自身的观测率
  ③ 不可失败性  顶层的任意子集 z 是否恒 ≈ 0

用法：
  python detect_circular_matched_null.py \
      --table M2_repro_gene_conservation_all.csv \
      --z1 Z_human --z2 Z_monkey --p2 p_monkey --thr 12 --bins 10
"""
import argparse
import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True, help="逐单元表（csv），每行一个元件")
    ap.add_argument("--z1", default="Z_human", help="主体物种标准化效应量列")
    ap.add_argument("--z2", default="Z_monkey", help="参考物种标准化效应量列")
    ap.add_argument("--p2", default=None, help="参考侧双侧 p 值列（用于构造门控掩码，可选）")
    ap.add_argument("--thr", type=float, default=12.0, help="强效应阈值 |Z1|>=")
    ap.add_argument("--bins", type=int, default=10, help="分层数（默认十分位）")
    ap.add_argument("--alpha", type=float, default=0.05, help="门控显著性水平")
    a = ap.parse_args()

    df = pd.read_csv(a.table)
    z1 = df[a.z1].to_numpy(float)
    z2 = df[a.z2].to_numpy(float)
    N = len(df)
    sd = np.sign(z1) == np.sign(z2)                      # 一致/同向指示
    q = np.asarray(pd.qcut(np.abs(z1), a.bins, labels=False, duplicates="drop"))
    top = q == q.max()
    top_rate = float(sd[top].mean())

    print(f"N={N}")
    print(f"全局一致率 = {sd.mean():.4f}")
    print(f"分层观测一致率 = {np.round(pd.Series(sd).groupby(q).mean().to_numpy(), 4)}")
    print(f"顶层（第 {q.max()} 层）n={int(top.sum())}  自身观测一致率 = {top_rate:.4f}")

    masks = {"强效应池 |Z1|>=%.0f" % a.thr: np.abs(z1) >= a.thr}
    if a.p2:
        masks["门控触发"] = masks["强效应池 |Z1|>=%.0f" % a.thr] & (df[a.p2].to_numpy(float) < a.alpha)

    pb = pd.Series(sd).groupby(q).mean().reindex(q).to_numpy(float)   # ← 观测自估的层内率

    circular = False
    for nm, m in masks.items():
        n = int(m.sum())
        if n == 0:
            print(f"\n[{nm}] 空集，跳过")
            continue
        obs = float(sd[m].mean())
        expB = float(pb[m].mean())
        varB = float((pb[m] * (1 - pb[m])).sum() / n ** 2)
        zB = (obs - expB) / np.sqrt(varB) if varB > 0 else np.nan
        z_naive = (obs - 0.5) / np.sqrt(0.25 / n)

        frac_top = float((q[m] == q.max()).mean())
        c1 = frac_top == 1.0
        c2 = abs(expB - top_rate) < 1e-9
        c3 = abs(zB) < 0.5
        is_circ = c1 and (c2 or c3)
        circular |= is_circ

        print(f"\n[{nm}]  n={n}")
        print(f"  ① 落在顶层的比例 = {frac_top:.4f}   {'✅ 全在单层' if c1 else ''}")
        print(f"  ② 分层期望 expB = {expB:.4f}   顶层自身观测率 = {top_rate:.4f}   "
              f"{'✅ 两者相等（期望=观测自估）' if c2 else ''}")
        print(f"  ③ 观测 {obs:.4f} | 分层期望 zB = {zB:+.3f} | 无信息 0.5 的 z = {z_naive:+.3f}"
              f"   {'✅ zB≈0（不可失败）' if c3 else ''}")
        print(f"  ⇒ 判定：{'【循环零假设】不可用于消解「低于随机」，须改层内置换或交叉拟合期望' if is_circ else '未被判循环（仍需人工确认层内率来源）'}")

    print("\n" + "=" * 60)
    print("判读要点：")
    print("  · 循环零假设下 z≈0 是恒等式，不是检验 —— 不能用来论证「观测与期望一致」。")
    print("  · 正确做法：层内置换（层内期望恒 0.5）或 leave-one-stratum-out / K-fold 交叉拟合期望。")
    print("  · 「观测低于随机」不是计算错误的证据：bug 给噪声，不给有一致符号的系统偏差。")
    if circular:
        print("  · 🔴 本次检出循环零假设，交付件中据其作出的「不是缺陷」结论必须删改。")


if __name__ == "__main__":
    main()
