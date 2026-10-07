# -*- coding: utf-8 -*-
"""
观测单位审计 —— 一条命令回答「组织级 pseudobulk 的衰老效应里混了什么」。

用途：评估「观测单位重构型」外部方案时（详见 references/method-upgrade-plan-evaluation.md
核心原则七/八），回盘核五件事，不照抄方案的描述：
  A 细胞类型归属核实 —— 方案引用的细胞数是谁的（主体侧还是参考侧）
  B 每种内组成偏移 —— 每个细胞类型 Young vs Old 占比 + Δ + 倍数
  C 🔴 两物种构成对比 —— 主判据：两侧 pseudobulk 是否在测同一批细胞
  D 资产可行性 —— 每侧计数矩阵覆盖率 / RNA 模态有无（决定分层与 regulon 层能不能做）
  E 年龄轴分辨率 —— 唯一整数年龄 vs 年龄组 vs 退化组（组内零方差）

另出三面板图：A 组成偏移绝对占比 / B 偏移幅度 / C 两物种年龄轴分辨率。

用法：
  python observation_unit_audit.py \
      --meta H:/data/human_meta.csv  --species 人 \
      --meta-b H:/data/monkey_meta.csv --species-b 猴 \
      --celltype celltype --age Age --group age_group --individual individual \
      --group-young Young --group-old Old \
      --arrow-root H:/data --arrow-pattern "*.arrow" \
      --out H:/results/observation_unit_audit.png

  单物种（只做 A/B/E）可省略 --meta-b / --species-b。
  列名因数据集而异，务必按 --help 显式传；不要靠猜。

退出码：0 正常；1 主判据（两物种构成对比）缺失或关键列找不到。
纯 pandas + numpy + matplotlib，无 scipy 依赖。
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd


def _pick(df, want, label):
    """按显式列名取列；找不到就列可用列并退出（不静默兜底）。"""
    if want in df.columns:
        return want
    cand = [c for c in df.columns if want.lower() in c.lower()]
    if len(cand) == 1:
        print(f"  [提示] {label} 列 '{want}' 未找到，自动落到 '{cand[0]}'")
        return cand[0]
    print(f"  [错误] {label} 列 '{want}' 未找到，候选={cand}，可用列={list(df.columns)}")
    sys.exit(1)


def load_meta(path, ct, age, grp, ind):
    df = pd.read_csv(path)
    print(f"  {os.path.basename(path)}: shape={df.shape}")
    return df, _pick(df, ct, "celltype"), _pick(df, age, "age"), _pick(df, grp, "age_group"), _pick(df, ind, "individual")


def section_a(df, ctcol, species):
    """A 细胞类型归属：方案引用的细胞数是谁的。"""
    print(f"\n--- A. {species}侧 celltype 分布 (共 {len(df):,} 细胞) ---")
    vc = df[ctcol].value_counts()
    print(vc.to_string())
    print(f"  → 合计 {len(df):,} | 个体数 {df.iloc[:, 0].nunique()}（请对照检查）")
    return vc


def section_b(df, ctcol, grpcol, gyoung, gold):
    """B 组成偏移：每个细胞类型 Young vs Old 占比。"""
    comp = pd.crosstab(df[ctcol], df[grpcol], normalize="columns") * 100
    if gyoung not in comp.columns or gold not in comp.columns:
        print(f"  [警告] 组名 '{gyoung}'/'{gold}' 不在 {list(comp.columns)}；改报全组表")
        print(comp.round(2).to_string())
        return comp, None
    comp = comp.copy()
    comp["Δ(Old-Young)"] = comp[gold] - comp[gyoung]
    comp["倍数"] = comp[gold] / comp[gyoung].replace(0, np.nan)
    print(comp.reindex(comp["Δ(Old-Young)"].abs().sort_values(ascending=False).index).round(3).to_string())
    return comp, comp


def section_c(comp_a, comp_b, ctcol, sa, sb):
    """C 主判据：两物种构成对比 —— 两侧 pseudobulk 是否在测同一批细胞。"""
    print("\n" + "=" * 72)
    print("C. 🔴 主判据：两物种细胞类型构成对比")
    print("=" * 72)
    if comp_a is None or comp_b is None:
        print("  [跳过] 需要两侧数据")
        return False
    # 用「各年龄组均值」代表该物种的整体构成
    base_cols_a = [c for c in comp_a.columns if c not in ("Δ(Old-Young)", "倍数")]
    base_cols_b = [c for c in comp_b.columns if c not in ("Δ(Old-Young)", "倍数")]
    ma = comp_a[base_cols_a].mean(axis=1)
    mb = comp_b[base_cols_b].mean(axis=1)
    cmpdf = pd.DataFrame({sa: ma, sb: mb}).fillna(0).sort_values(sa, ascending=False)
    cmpdf["占比差(pp)"] = cmpdf[sa] - cmpdf[sb]
    print(cmpdf.round(2).to_string())
    top_a, top_b = cmpdf[sa].idxmax(), cmpdf[sb].idxmax()
    print(f"\n  {sa}侧主导细胞类型 = {top_a} ({cmpdf.loc[top_a, sa]:.1f}%)")
    print(f"  {sb}侧主导细胞类型 = {top_b} ({cmpdf.loc[top_b, sb]:.1f}%)")
    if str(top_a) != str(top_b):
        print(f"  ⇒ 🔴 两侧主导类型不同：组织级 pseudobulk 在 {sa} 侧主要测 {top_a}，"
              f"在 {sb} 侧主要测 {top_b} —— 跨物种一致性被结构性压低。")
    else:
        print("  ⇒ 两侧主导类型相同，组成不匹配风险较低（仍需看次要类型偏移）")
    return True


def section_d(arrow_root, pattern, samples_a, samples_b, sa, sb):
    """D 资产可行性：计数矩阵覆盖率 + RNA 模态。"""
    print("\n" + "=" * 72)
    print("D. 资产可行性")
    print("=" * 72)
    arr = sorted(glob.glob(os.path.join(arrow_root, "**", pattern), recursive=True))
    print(f"  Arrow 文件合计（含重复路径）: {len(arr)}")
    if arr:
        uniq = sorted({os.path.basename(x) for x in arr})
        print(f"  唯一文件名: {len(uniq)}")
        for x in uniq[:15]:
            print(f"    {x}")
        if len(uniq) > 15:
            print(f"    ... 另 {len(uniq) - 15} 个")
    print(f"  {sa} 样本数={samples_a} | {sb} 样本数={samples_b}")
    print(f"  ⇒ 逐一核对每侧计数矩阵覆盖率：覆盖率低的侧「细胞类型分层 pseudobulk」本地不可行，须回集群")
    # RNA 模态
    rna = []
    for k in ("*rna*", "*RNA*", "*expr*", "*h5ad*", "*count*"):
        rna += glob.glob(os.path.join(arrow_root, "**", k), recursive=True)
    rna = [x for x in rna if os.path.isfile(x) and "node_modules" not in x]
    print(f"  RNA/表达矩阵文件: {len(rna)} 个")
    if not rna:
        print("  ⇒ 🔴 零 RNA → 程序层的 regulon（SCENIC 类）不可行，仅 chromVAR motif 可从 ATAC 做")
    else:
        for x in rna[:10]:
            print(f"    {x}")


def section_e(df, agecol, grpcol, indcol, species):
    """E 年龄轴分辨率：整数年龄 vs 年龄组 vs 退化组。"""
    print(f"\n--- E. {species}侧年龄轴 ---")
    try:
        per = df.groupby(indcol)[agecol].first()
    except Exception:
        per = df[agecol].dropna()
    print(f"  个体数={per.nunique() if hasattr(per, 'nunique') else '?'} | 样本数={df[indcol].nunique()}")
    print(f"  唯一整数年龄={per.nunique()} → {sorted(per.unique())}")
    if grpcol in df.columns:
        print(f"  年龄组={df[grpcol].nunique()} → {sorted(df[grpcol].astype(str).unique())}")
    # 退化组：组内零方差
    if grpcol in df.columns:
        for g, sub in df.groupby(grpcol):
            vals = sub[agecol].unique()
            if len(vals) == 1:
                n_ind = sub[indcol].nunique() if indcol in sub.columns else len(sub)
                print(f"  ⚠️ 退化组 '{g}': 全部为 {vals[0]} 岁（{n_ind} 个体）→ 该段组内零方差")
    print("  ⇒ 报告口径：写「N 个年龄组 + M 个整数年龄 / 有效分辨率≈组数」，不要写「df=组数」")


def make_figure(comp, comp_b, la, lb, per_a, per_b, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 3, figsize=(19, 6.2))

    if comp is not None and "Δ(Old-Young)" in comp.columns:
        cc = comp.reindex(comp["Δ(Old-Young)"].abs().sort_values(ascending=False).index).head(12)
        y = np.arange(len(cc))
        base = [c for c in comp.columns if c not in ("Δ(Old-Young)", "倍数")]
        gain, loss = base[-1], base[0]
        axes[0].barh(y - 0.2, cc[gain], height=0.4, label=gain, color="#4C9AF5")
        axes[0].barh(y + 0.2, cc[loss], height=0.4, label=loss, color="#E8613C")
        axes[0].set_yticks(y); axes[0].set_yticklabels(cc.index.astype(str), fontsize=9)
        axes[0].invert_yaxis(); axes[0].legend(fontsize=9)
        axes[0].set_title(f"A｜{la}：细胞类型组成随年龄偏移\n（组织级 pseudobulk 的衰老效应混入这一项）", fontsize=11, fontweight="bold")
        axes[0].grid(axis="x", alpha=0.3)

        cols = ["#E8613C" if v > 0 else "#4C9AF5" for v in cc["Δ(Old-Young)"]]
        axes[1].barh(y, cc["Δ(Old-Young)"], color=cols)
        axes[1].set_yticks(y); axes[1].set_yticklabels(cc.index.astype(str), fontsize=9)
        axes[1].invert_yaxis(); axes[1].axvline(0, color="black", lw=0.8)
        axes[1].set_title("B｜组成偏移幅度 Δ(Old−Young)\n（红=老年增多，蓝=老年减少）", fontsize=11, fontweight="bold")
        axes[1].grid(axis="x", alpha=0.3)

    rng = np.random.default_rng(0)
    if per_b is not None:
        axes[2].scatter(per_b.values, rng.normal(1, 0.055, len(per_b)), s=95,
                        color="#E8613C", alpha=0.85, edgecolor="black", linewidth=0.6,
                        label=f"{lb} (n={len(per_b)}, {per_b.nunique()} 个整数年龄)", zorder=3)
        for xv in sorted(np.unique(per_b.values)):
            axes[2].axvline(xv, color="#E8613C", alpha=0.14, lw=6, zorder=1)
    if per_a is not None:
        axes[2].scatter(per_a.values, rng.normal(0, 0.055, len(per_a)), s=95,
                        color="#4C9AF5", alpha=0.85, edgecolor="black", linewidth=0.6,
                        label=f"{la} (n={len(per_a)}, {per_a.nunique()} 个整数年龄)", zorder=3)
    axes[2].set_yticks([0, 1]); axes[2].set_yticklabels([la, lb], fontsize=11)
    axes[2].set_xlabel("年龄 (岁)", fontsize=10)
    axes[2].set_title("C｜年龄轴分辨率对比", fontsize=11, fontweight="bold")
    axes[2].legend(fontsize=9, loc="best"); axes[2].grid(axis="x", alpha=0.3)
    axes[2].set_ylim(-0.4, 1.4)

    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    plt.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"\n[图] saved: {out}")


def main():
    ap = argparse.ArgumentParser(description="观测单位审计：组成混杂 + 年龄轴分辨率 + 资产可行性")
    ap.add_argument("--meta", required=True, help="主体物种细胞元数据 CSV（每行一个细胞）")
    ap.add_argument("--species", default="主体")
    ap.add_argument("--meta-b", help="对照物种细胞元数据 CSV（可选）")
    ap.add_argument("--species-b", default="对照")
    ap.add_argument("--celltype", default="celltype")
    ap.add_argument("--age", default="Age")
    ap.add_argument("--group", default="age_group", help="年龄分组列名")
    ap.add_argument("--individual", default="individual")
    ap.add_argument("--group-young", default="Young")
    ap.add_argument("--group-old", default="Old")
    ap.add_argument("--arrow-root", default=".", help="计数矩阵搜索根目录")
    ap.add_argument("--arrow-pattern", default="*.arrow")
    ap.add_argument("--out", help="输出图路径（省略则不出图）")
    a = ap.parse_args()

    print("=" * 72)
    print(f"观测单位审计：{a.species}" + (f" vs {a.species_b}" if a.meta_b else ""))
    print("=" * 72)

    dfA, ctA, ageA, grpA, indA = load_meta(a.meta, a.celltype, a.age, a.group, a.individual)
    section_a(dfA, ctA, a.species)
    compA, _ = section_b(dfA, ctA, grpA, a.group_young, a.group_old)

    compB = None
    dfB = None
    if a.meta_b:
        dfB, ctB, ageB, grpB, indB = load_meta(a.meta_b, a.celltype, a.age, a.group, a.individual)
        section_a(dfB, ctB, a.species_b)
        compB, _ = section_b(dfB, ctB, grpB, a.group_young, a.group_old)

    ok = section_c(compA, compB, ctA, a.species, a.species_b)
    section_d(a.arrow_root, a.arrow_pattern,
              dfA[indA].nunique(), dfB[indB].nunique() if dfB is not None else "—",
              a.species, a.species_b)
    section_e(dfA, ageA, grpA, indA, a.species)
    if dfB is not None:
        section_e(dfB, ageB, grpB, indB, a.species_b)

    if a.out:
        perA = dfA.groupby(indA)[ageA].first()
        perB = dfB.groupby(indB)[ageB].first() if dfB is not None else None
        make_figure(compA, compB, a.species, a.species_b, perA, perB, a.out)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
