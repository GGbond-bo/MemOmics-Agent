#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
二维经验贝叶斯 + local FDR 五态判定探针（只读可行性评估，秒级）

用途：用户需求里点名了"二维经验贝叶斯五态判定 + local FDR"这类方法时，
      先把它真跑一遍，判断它救的是【信号】还是【新颖性】。
      —— 不能只回答"用了/没用"，要给实测数字。

用法：
    python ebayes_lfdr_probe.py <元件表.csv> [out_dir] [--col-z1 X --col-z2 Y --col-p Y]

输入表要求：含两物种标准效应量列（默认 Z_human / Z_monkey；p 列可省）。
           仅需汇总表即可，不需要 tile×sample 计数矩阵。

输出：<out_dir>/lfdr_probe_summary.json + lfdr_probe_scatter.png/.pdf
"""
import os
import sys
import json
import argparse

import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.ndimage import gaussian_filter


def emp_null(z):
    """Efron 25–75 百分位稳健经验零假设估计（比 MLE 稳、抗真实效应污染）。"""
    q25, q50, q75 = np.percentile(z, [25, 50, 75])
    return float(q50), float((q75 - q25) / (norm.ppf(0.75) - norm.ppf(0.25)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("table")
    ap.add_argument("out_dir", nargs="?", default=".")
    ap.add_argument("--col-z1", default="Z_human")
    ap.add_argument("--col-z2", default="Z_monkey")
    ap.add_argument("--col-p2", default="p_monkey")
    ap.add_argument("--q", type=float, default=0.05, help="lfdr 阈值")
    ap.add_argument("--n-perm", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=20260912)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    d = pd.read_csv(args.table)
    z1 = d[args.col_z1].to_numpy(dtype=float)
    z2 = d[args.col_z2].to_numpy(dtype=float)
    ok = np.isfinite(z1) & np.isfinite(z2)
    z1, z2 = z1[ok], z2[ok]
    n = len(z1)
    print(f"[input] {args.table}  有效元件 n={n}")

    # ---------- 1) 经验零假设标定（必做：先看 Z 的标定是否可信） ----------
    mu1, s1 = emp_null(z1)
    mu2, s2 = emp_null(z2)
    print(f"[经验零假设] 轴1 mu={mu1:+.3f} sigma={s1:.3f} | 轴2 mu={mu2:+.3f} sigma={s2:.3f}")
    if max(s1, s2) > 1.5:
        print(f"  ⚠️ sigma={max(s1, s2):.2f} >> 1 ⇒ 名义 |Z| 阈值被夸大 {max(s1, s2):.2f} 倍，"
              f"例如 |Z|>=12 实际只相当于 {(12 - mu1) / s1:.2f} 个经验 sigma")
        print("  疑因排查顺序：① p 用的 n 是供体数还是 tile/细胞数 "
              "② Stouffer ΣZ/√n 的独立性前提 ③ 是否做过全局居中（median Z 应≈0）")

    box = (np.abs(z1 - mu1) < 1.5 * s1) & (np.abs(z2 - mu2) < 1.5 * s2)
    rho0 = float(np.corrcoef(z1[box], z2[box])[0, 1]) if box.sum() > 10 else 0.0
    pi0 = float(min(1.0, box.mean() / (2 * norm.cdf(1.5) - 1) ** 2))
    print(f"[零假设相关] 中心区 n={box.sum()} rho0={rho0:+.4f} | pi0={pi0:.4f}")

    # ---------- 2) 二维直方图 → 平滑 → 联合密度 f ----------
    bw, lim = 0.5, 80.0
    edges = np.arange(-lim, lim + bw, bw)
    H, xe, ye = np.histogram2d(np.clip(z1, -lim, lim), np.clip(z2, -lim, lim),
                               bins=[edges, edges])
    f = gaussian_filter(H, sigma=1.5) / (H.sum() * bw * bw)
    cx = (xe[:-1] + xe[1:]) / 2
    cy = (ye[:-1] + ye[1:]) / 2
    G1, G2 = np.meshgrid(cx, cy, indexing="ij")

    # ---------- 3) 二维零假设密度 f0（含 rho0）→ lfdr ----------
    C = np.sqrt(1 - rho0 ** 2)
    u1 = (G1 - mu1) / s1
    u2 = (G2 - mu2) / s2
    f0 = norm.pdf(u1) / s1 * norm.pdf((u2 - rho0 * u1) / C) / (s2 * C)
    lfdr_grid = np.clip(pi0 * f0 / np.maximum(f, 1e-300), 0, 1)

    i1 = np.clip(((z1 + lim) / bw).astype(int), 0, len(cx) - 1)
    i2 = np.clip(((z2 + lim) / bw).astype(int), 0, len(cy) - 1)
    lfdr = lfdr_grid[i1, i2]

    # ---------- 4) 五态判定 ----------
    sig1 = np.abs(z1 - mu1) > 1.96 * s1      # 经验零假设下双侧 p<0.05
    sig2 = np.abs(z2 - mu2) > 1.96 * s2
    same = np.sign(z1) == np.sign(z2)
    both = sig1 & sig2
    state = np.full(n, "E_无信号", dtype=object)
    state[sig1 ^ sig2] = "C_单侧可判定"
    state[both & (lfdr > args.q)] = "D_双侧但证据不足"
    state[both & (lfdr <= args.q) & same] = "A_同向可信"
    state[both & (lfdr <= args.q) & ~same] = "B_反向可信"
    vc = pd.Series(state).value_counts()
    print(f"\n[五态分布 · 二维经验贝叶斯 + lfdr<={args.q}]")
    for k in ["A_同向可信", "B_反向可信", "C_单侧可判定", "D_双侧但证据不足", "E_无信号"]:
        c = int(vc.get(k, 0))
        print(f"  {k:<14}: {c:>6}  ({c / n * 100:5.2f}%)")

    # ---------- 5) 同号率 vs 符号置换零假设（保边际、破配对） ----------
    sgn1_b, sgn2_b = np.sign(z1[both]), np.sign(z2[both])
    obs_same = int((sgn1_b * sgn2_b > 0).sum())
    n_both = int(both.sum())
    rng = np.random.default_rng(args.seed)
    null_same = np.array([int((rng.permutation(sgn2_b) * sgn1_b > 0).sum())
                          for _ in range(args.n_perm)])
    zsc = (obs_same - null_same.mean()) / null_same.std()
    print(f"\n[双侧过阈] {n_both}，同号 {obs_same} ({obs_same / max(n_both, 1) * 100:.1f}%)"
          f"，独立零假设期望 50.0%")
    print(f"[符号置换 N={args.n_perm}] 观测 {obs_same} | null {null_same.mean():.1f}"
          f"±{null_same.std():.1f}  z={zsc:+.2f}")

    summary = dict(
        input=os.path.abspath(args.table), n_elements=n,
        emp_null=dict(axis1=[mu1, s1], axis2=[mu2, s2]),
        rho0=rho0, pi0=pi0, q=args.q,
        states={k: int(vc.get(k, 0)) for k in
                ["A_同向可信", "B_反向可信", "C_单侧可判定", "D_双侧但证据不足", "E_无信号"]},
        both_sig=n_both, both_same=obs_same,
        same_rate=round(obs_same / max(n_both, 1), 4),
        sign_perm=dict(n_perm=args.n_perm, null_mean=float(null_same.mean()),
                       null_sd=float(null_same.std()), z=float(zsc)),
        verdict=("同向未超反向 ⇒ 救新颖性/误差控制，不救效果层"
                 if int(vc.get("A_同向可信", 0)) <= int(vc.get("B_反向可信", 0))
                 else "同向多于反向 ⇒ 需再核标定与混杂"),
    )
    p_json = os.path.join(args.out_dir, "lfdr_probe_summary.json")
    with open(p_json, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(f"\n[判读] {summary['verdict']}")

    # ---------- 6) 出图 ----------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(12, 5.2))
        sub = np.random.default_rng(0).choice(n, size=min(9000, n), replace=False)
        colors = {"A_同向可信": "#009E73", "B_反向可信": "#D55E00",
                  "C_单侧可判定": "#56B4E9", "D_双侧但证据不足": "#E69F00",
                  "E_无信号": "#BBBBBB"}
        for k, c in colors.items():
            idx = sub[state[sub] == k]
            if len(idx):
                ax[0].scatter(np.clip(z1[idx], -lim, lim), np.clip(z2[idx], -lim, lim),
                              s=4, c=c, alpha=.55, linewidths=0,
                              label=f"{k} ({int(vc.get(k, 0))})")
        ax[0].axhline(0, lw=.6, c="k"); ax[0].axvline(0, lw=.6, c="k")
        ax[0].set_xlabel(f"{args.col_z1}"); ax[0].set_ylabel(f"{args.col_z2}")
        ax[0].set_title("Five states by 2D empirical Bayes + local FDR")
        ax[0].legend(fontsize=7, loc="upper left", frameon=False)
        im = ax[1].pcolormesh(cx, cy, np.log10(np.maximum(lfdr_grid, 1e-6)).T,
                              cmap="viridis_r", shading="auto")
        ax[1].set_xlim(-20, 20); ax[1].set_ylim(-20, 20)
        ax[1].set_xlabel(f"{args.col_z1}"); ax[1].set_ylabel(f"{args.col_z2}")
        ax[1].set_title("log10(local FDR)")
        plt.colorbar(im, ax=ax[1], shrink=.85)
        plt.tight_layout()
        for ext in ("png", "pdf"):
            plt.savefig(os.path.join(args.out_dir, f"lfdr_probe_scatter.{ext}"), dpi=180)
        plt.close(fig)
        print(f"[出图] {args.out_dir}/lfdr_probe_scatter.png/.pdf")
    except Exception as e:  # 出图失败不影响数值结论
        print(f"[warn] 出图跳过：{e}")
    print(f"[汇总] {p_json}")


if __name__ == "__main__":
    sys.exit(main())
