#!/usr/bin/env python3
# ============================================================
# sample_size_feasibility.py —— 回答「FDR 不显著，是不是因为样本太少了？」
#
# 把「不显著」拆成两堵墙，各自定量：
#   墙 A（硬）离散下界 —— 只由 n 与检验族 m 决定，【与效应量无关】
#   墙 B（软）80% 功效所需 n —— 由观测效应量决定
# 两者必须分开答：它们给出的「需要多少样本」差一个数量级。
#
# 用法:
#   python sample_size_feasibility.py <effect_table.csv> [family] [alpha]
# 表需含: effect / p_np / n1 / n2 / eff
# 可选:   q（显著格数）/ aux1（配对组 = d_z，独立组 = Hedges J）/ eff_type
#
# ⛔ DESIGN 字典必须手写 —— 不许从 n1 == n2 推断配对：
#    独立 7vs7 与配对 7 对在表里完全同形（唯一可信来源 = 建表脚本的设计字典）
# ============================================================
import sys
from math import comb

import numpy as np
import pandas as pd
from scipy import stats

# ---------------- 唯一需要改的地方 ----------------
DESIGN = {  # effect: (检验, 是否配对)   "mw" = Mann-Whitney, "wil" = Wilcoxon signed-rank
    "Aging":   ("mw",  False),
    "T2D":     ("mw",  False),
    "ExYoung": ("wil", True),
    "ExOld":   ("wil", True),
    "ExT2D":   ("wil", True),
}
# --------------------------------------------------

PATH = sys.argv[1] if len(sys.argv) > 1 else "effect5_effsize_v3.csv"
FAMILY = int(sys.argv[2]) if len(sys.argv) > 2 else 220
ALPHA = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05

df = pd.read_csv(PATH)
a_adj = ALPHA / FAMILY
z_a = stats.norm.ppf(1 - a_adj / 2)
z_b = stats.norm.ppf(0.80)

print(f"表: {PATH}  ({len(df)} 行)")
print(f"检验族 m={FAMILY} → BH 第一名门槛 = {ALPHA}/{FAMILY} = {a_adj:.4e}")
print(f"z(1-α/2)={z_a:.3f} | z(0.80)={z_b:.3f}\n")


def floor_theory(test, n1, n2):
    """无并列值理想情形下的双侧最小可达 p（下界 = 可达性的乐观上界）"""
    return 2 / 2 ** n1 if test == "wil" else 2 / comb(n1 + n2, n1)


rows = []
for eff, (test, paired) in DESIGN.items():
    s = df[df.effect == eff]
    if s.empty:
        continue
    n1, n2 = int(s.n1.iloc[0]), int(s.n2.iloc[0])
    fl = floor_theory(test, n1, n2)
    rows.append(dict(
        effect=eff,
        test="配对 Wilcoxon" if paired else "独立 MWU",
        n=f"{n1} 对" if paired else f"{n1} vs {n2}",
        floor_theory=fl, floor_obs=float(s.p_np.min()), ratio=fl / a_adj,
        eligible=fl < a_adj,
        n_at_floor=int((s.p_np <= fl * 1.0001).sum()),
        med_abs=float(s.eff.abs().median()), max_abs=float(s.eff.abs().max()),
        n_sig=int((s.q < 0.05).sum()) if "q" in s.columns else -1,
    ))
r = pd.DataFrame(rows)

print("=" * 98)
print("① 可达性：当前 n 下有没有【资格】显著（与效应量无关，纯组合数学）")
print("=" * 98)
for _, x in r.iterrows():
    print(f"{x.effect:8s} {x.test:14s} n={x.n:9s} 下界(理论)={x.floor_theory:.3e} "
          f"下界(实测)={x.floor_obs:.3e} 下界/门槛={x.ratio:6.2f}× "
          f"{'✅ 够资格' if x.eligible else '❌ 无资格'}  钉界格数={x.n_at_floor:3d}  显著={x.n_sig}")
print("\n下界/门槛 > 1 才有资格；< 1 = 【无论效应量多大都进不去】")
print("⛔ 理论下界是乐观上界：有并列值/零差值时 scipy 退化正态近似，实测下界只会更高")
print("   A/B 实测差异是【效应强度】的证据：实测 == 理论 ⇒ 有格取到完全分离（效应极强）\n")

print("=" * 98)
print("② 要多少样本才【够门槛】(理论下界 < 门槛)")
print("=" * 98)
for eff, (test, paired) in DESIGN.items():
    s = df[df.effect == eff]
    if s.empty:
        continue
    n1 = int(s.n1.iloc[0])
    if test == "wil":
        need = int(np.ceil(np.log2(2 / a_adj)))
        print(f"{eff:8s} 配对 Wilcoxon  需 n ≥ {need} 对 （现 {n1} 对，+{max(0, need - n1)}）")
    else:
        need = next(k for k in range(2, 500) if 2 / comb(k + k, k) < a_adj)
        print(f"{eff:8s} 独立 MWU       需每组 n ≥ {need} （现 {n1}，+{max(0, need - n1)}）")
print("注：并列值会抬高实测下界 ⇒ 实际需要的 n 只会更多\n")

print("=" * 98)
print("③ 要多少样本才【真检出】(80% 功效 @ 门槛 α)  ← 墙 B")
print("=" * 98)
print(f"{'效应':8s} {'分位':>6s} {'|效应|':>8s} {'需要n':>9s} {'现有n':>7s} {'差距':>9s}")
for eff, (test, paired) in DESIGN.items():
    s = df[df.effect == eff]
    if s.empty:
        continue
    # 配对检验的功效取决于 d_z（不是 d_av）——d_av 是给跨面板色标同尺度用的
    if paired and "aux1" in s.columns:
        d_all = s.aux1.abs()
    else:
        d_all = s.eff.abs()
    have = int(s.n1.iloc[0])
    for qq, nm in [(0.50, "p50"), (0.90, "p90"), (1.00, "max")]:
        d = float(d_all.quantile(qq))
        if d <= 0:
            continue
        need = (int(np.ceil((z_a + z_b) ** 2 / d ** 2)) if paired
                else int(np.ceil(2 * (z_a + z_b) ** 2 / d ** 2)))
        print(f"{eff:8s} {nm:>6s} {d:8.3f} {need:9d} {have:7d} {need - have:+9d}")
    print("-" * 98)
print("读法：中位效应所需 n 常不现实 ⇒ 结论转向【效应量 + 方向一致性】，显著性降辅助；")
print("      而最强那批格现有 n 往往已够 ⇒ 卡住它们的是墙 A（下界），不是墙 B（功效）\n")

print("=" * 98)
print("④ 换更小的检验族能否救活（n 不变，只改 m）")
print("=" * 98)
for m, nm in [(FAMILY, "当前"), (50, "每程序"), (35, "每效应×生物轴"), (7, "每生物轴")]:
    th = ALPHA / m
    ok = [x.effect for _, x in r.iterrows() if x.floor_theory < th]
    print(f"族={nm:14s} {m:5d} 格  门槛={th:.3e}  有资格: {ok}")
print("⛔ 族不得切到 <20 格：门槛被稀释会造出零星假显著")
print("   （详见 references/fdr-family-definition-audit.md）")
print("\n⛔ 换族只能救【下界已接近门槛】的效应；下界远高于门槛的（如配对 n=7 → 1.56e-2）")
print("   任何族都救不了，只能加样本 —— 这是两堵墙的分工")