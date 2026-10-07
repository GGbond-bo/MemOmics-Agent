#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
per-tile 门控 z 的「来源复现 + 语义审计」探针
================================================
触发场景（任一）：
  · 用户要求「查这三个 z 的实际算法来源」（专利里 z=+3.85 / +3.09 / +3.27）
  · 准备引用某个「匹配零假设 z」支撑 claim 之前
  · 怀疑 strata 零假设是循环构造（观测自估期望）

它做三件事：
  ① 逐字复现 03_three_baseline_comparison.py 的 per-tile 门控扫描 z（校验可复现）
  ② 审计该零假设的「语义」：期望从哪来 / 包含性 / exp 是否低于无信息基准
  ③ 给出判决：能否主张"优于随机"、能否主张"门控挑出同向元件"

判据依据：cross-species-cre-conservation/references/tile-level-da-significance-floor.md §9.6
         patent-analysis/references/null-hypothesis-selection-and-circular-null-audit.md §2

用法：
  python repro_pertile_gate_z.py \
      --table E:/专利/P3_L1_data/M2_repro_gene_conservation_all.csv \
      --expect-from-disk E:/专利/交付_跨物种衰老可替代性专利/results/pertile_gate_sweep.csv
"""
import argparse
import sys

import numpy as np
import pandas as pd

THRS = [0.3, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0]
NO_INFO_BASE = 0.5          # 无信息基准（掷硬币）
SMALL_SELF_INCL = 0.01      # 自我包含 < 1% ⇒ 判「条件检验」而非「恒等式」


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True,
                    help="元件表：需含 Z_human/Z_monkey/p_monkey/n_tiles_h/n_tiles_m")
    ap.add_argument("--expect-from-disk", default=None,
                    help="可选：磁盘上的 pertile_gate_sweep.csv，用于对照复现")
    ap.add_argument("--thr-strong", type=float, default=12.0,
                    help="|Z_h| 强效应阈值（仅用于分层参考，默认 12）")
    ap.add_argument("--bins", type=int, default=10, help="分层数（默认 10 = 十分位）")
    a = ap.parse_args()

    df = pd.read_csv(a.table)
    need = ["Z_human", "Z_monkey", "p_monkey", "n_tiles_h", "n_tiles_m"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        print(f"[FATAL] 缺列: {missing}；实有列: {list(df.columns)}")
        return 2

    # 一致率：优先用表里的 same_direction 列，否则按符号现算
    if "same_direction" in df.columns:
        sd = df["same_direction"].astype(str).str.strip().str.lower().isin(
            ["true", "1", "yes"]).to_numpy()
    else:
        sd = (np.sign(df.Z_human) == np.sign(df.Z_monkey)).to_numpy()

    zh, zm = df.Z_human.to_numpy(float), df.Z_monkey.to_numpy(float)
    pm = df.p_monkey.to_numpy(float)
    nh, nm = df.n_tiles_h.to_numpy(float), df.n_tiles_m.to_numpy(float)
    N = len(df)

    print("=" * 78)
    print(f"[输入] {a.table}")
    print(f"       N = {N} | 全局一致率 = {sd.mean():.4f} | "
          f"r(Z1,Z2) = {np.corrcoef(zh, zm)[0, 1]:+.4f}")
    print("=" * 78)

    # ---- 复刻 L39-42：观测自估的十分层期望 ----
    q = pd.qcut(np.abs(zh), a.bins, labels=False, duplicates="drop")
    base = pd.Series(sd).groupby(q).mean()
    p_base = base.reindex(q).to_numpy(float)
    sizes = pd.Series(q).groupby(q).size()

    print("\n[分层] |Z_h| 十分层的『观测』一致率（= 被当作『期望』的东西）")
    print(pd.DataFrame({"decile": range(len(base)),
                        "n": sizes.to_numpy(),
                        "obs_rate": base.to_numpy().round(4),
                        "below_0.5": base.to_numpy() < NO_INFO_BASE
                        }).to_string(index=False))
    print(f"  ⇒ 顶层(|Z_h| 最高) 观测率 = {base.iloc[-1]:.4f}    "
          f"最底层 = {base.iloc[0]:.4f}")

    # ---- 复刻 L45-63 + L96-105：门控扫描 ----
    zb_h = zh / np.sqrt(np.maximum(nh, 1))
    zb_m = zm / np.sqrt(np.maximum(nm, 1))

    rows = []
    for thr in THRS:
        m = (np.abs(zb_h) >= thr) & (np.abs(zb_m) >= thr)
        n = int(m.sum())
        if n == 0:
            continue
        obs = float(sd[m].mean())
        exp = float(p_base[m].mean())
        var = float((p_base[m] * (1 - p_base[m])).sum() / n ** 2)
        z = float((obs - exp) / np.sqrt(var)) if var > 0 else np.nan
        dec = q[m]
        layers = sorted(set(dec.tolist()))
        layer_size = int(sum(sizes[d] for d in layers))
        rows.append(dict(thr=thr, n_out=n, obs=round(obs, 4), exp=round(exp, 4),
                         z=round(z, 2), layers=f"{layers[0]}-{layers[-1]}",
                         self_incl=round(n / layer_size, 4) if layer_size else np.nan,
                         exp_below_noinfo=exp < NO_INFO_BASE,
                         z_pos_but_obs_below=bool(z > 0 and obs < NO_INFO_BASE)))

    tab = pd.DataFrame(rows)
    print("\n[复现] per-tile 门控扫描（z̄ = Z/√n，零假设 = 层内观测自估均值）")
    print(tab.to_string(index=False))

    # ---- 与磁盘原表对照 ----
    if a.expect_from_disk:
        try:
            disk = pd.read_csv(a.expect_from_disk)
            ref = disk.set_index("thr")["z"].to_dict()
            print(f"\n[对照] 磁盘 {a.expect_from_disk}")
            bad = []
            for r in rows:
                exp_z = ref.get(r["thr"], ref.get(str(r["thr"])))
                if exp_z is None:
                    continue
                ok = abs(float(r["z"]) - float(exp_z)) < 0.015
                print(f"  thr={r['thr']:<4} 复现 z={r['z']:+.2f}  磁盘 z={float(exp_z):+.2f}  "
                      f"{'✓' if ok else '✗ 不一致'}")
                if not ok:
                    bad.append(r["thr"])
            print("  ⇒ " + ("逐字一致 ⇒ 来源定位正确"
                            if not bad else f"不一致档位 {bad} ⇒ 存在未捕获的实现差异"))
        except Exception as e:                                    # noqa: BLE001
            print(f"\n[对照] 读取失败（跳过）：{type(e).__name__}: {e}")

    # ---- 判决 ----
    print("\n" + "=" * 78)
    print("[判决] 该零假设的语义（§9.6 三问）")
    if tab.empty:
        print("  所有档位 n_out = 0，无法判定")
        return 0

    all_exp_below = bool(tab["exp_below_noinfo"].all())
    max_self = float(tab["self_incl"].max())
    traps = tab[tab["z_pos_but_obs_below"]]

    print(f"  ① 期望来源：观测自估（groupby(strata).mean()，非外部先验、非置换）")
    print(f"  ② 最大自我包含 = {max_self:.4f}")
    if max_self >= 0.5:
        print("     ⇒ 🔴 判『恒等式区间』：检验几乎不可失败，数值即不可用（按循环口径处理）")
    elif max_self < SMALL_SELF_INCL:
        print("     ⇒ 判『条件检验』：不是恒等式、检验会失败 ⇒ "
              "**不可判为循环（勿冤判）**，但语义须改写")
    else:
        print("     ⇒ 介于两者之间：需逐档看，包含性最高的档位按循环口径警惕")
    print(f"  ③ exp 是否全部低于无信息基准 0.5：{all_exp_below}")
    if all_exp_below:
        print("     ⇒ 🔴 禁称『优于随机』——exp 本身低于 0.5，"
              "z>0 只代表『高于同层均值』")

    print("\n[结论]")
    if all_exp_below:
        print("  · 这三个 z **不是** p 的反变换（不是 §9.1 那种退化量），数值可用；")
        print("  · 但**不得**表述为『门控能挑出同向/可迁移元件』或『显著优于随机』；")
        print("  · 正确表述：『在同等 |Z₁| 强度条件下，门控集合的同向率高于同层基准"
              "（层内条件检验）』，并同时列出 exp；")
        print("  · 送审前把 exp 一并披露（同时暴露基准 < 50%，与诚实披露口径一致）。")
    if not traps.empty:
        print(f"\n  🔴 决策性反例（z>0 而观测率<0.5）：档位 "
              f"{list(traps['thr'])} ⇒ 一句话即可反驳『优于随机』主张：")
        for _, r in traps.iterrows():
            print(f"     thr={r['thr']}: obs={r['obs']:.4f} (<0.5) 但 z={r['z']:+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
