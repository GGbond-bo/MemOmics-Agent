#!/usr/bin/env python
# ============================================================
# audit_group_effects.py —— 混合设计（组间独立 + 组内配对）效应量六合一审计
#
# 用途：返工前判断既有口径对不对 / 返工后证明新口径站得住。
# 顺序：A 数据完整性 → B 配对 QC(r 分布) → C FDR 检验族敏感性
#       → D 效应量 95% CI → E 功效模拟 → F 实现校验(合成数据)
#
# 用法：改下方 CONFIG（其余不用动），然后
#       execute_python: exec(open('<本脚本路径>', encoding='utf-8').read())
# 依赖：pandas numpy scipy（statsmodels 可选，仅用于 BH 交叉校验）
# ============================================================
import numpy as np
import pandas as pd
from scipy import stats

# ---------------- CONFIG（按项目改这里） ----------------
META_CSV = "E:/骨骼肌锻炼/MF_AUCell_meta.csv"   # 细胞级长表
GROUP_COL = "type"                                # 组别列
SUBJ_COL = None                                   # 个体列；None = 从 sample 名剥离 _Pre/_Post
SAMPLE_COL = "samplename"
SUBCLUSTER_COL = "annotation_L3"                  # 亚群列（无则设 None）
SCORE_SUFFIX = "_AUC"                             # 打分列后缀；None = 全部数值列
TIME_SUFFIX = ("_Pre", "_Post")                   # 时间点后缀
LOW_CELL = 50                                     # 「低细胞数」阈值
PAIR_R = 0.32                                     # 功效模拟用的个体内相关（取自本项目实测）
# 效应定义: 名称 -> (组A, 组B, paired?)   方向 = B − A
EFFECTS = {
    "Aging":   ("Y_Pre",  "O_Pre",   False),   # 独立
    "T2D":     ("O_Pre",  "OD_Pre",  False),   # 独立
    "ExYoung": ("Y_Pre",  "Y_Post",  True),    # 配对
    "ExOld":   ("O_Pre",  "O_Post",  True),    # 配对
    "ExT2D":   ("OD_Pre", "OD_Post", True),    # 配对
}
FDR_FAMILIES = ["global", "per_effect", "per_score", "per_effect_x_axis"]
POWER_DS = [0.2, 0.4, 0.6, 0.8]
N_SIM = 2000
RNG_SEED = 7
# --------------------------------------------------------


def bh(p):
    """Benjamini-Hochberg。"""
    p = np.asarray(p, float)
    n = len(p)
    o = np.argsort(p)
    r = np.empty(n)
    r[o] = np.arange(1, n + 1)
    q = np.minimum.accumulate((p * n / r)[o][::-1])[::-1]
    out = np.empty(n)
    out[o] = q
    return np.clip(out, 0, 1)


def hedges_g(x, y):
    """独立比较，方向 = y − x。返回 g(J 校正), J, SE(g)。"""
    n1, n2 = len(x), len(y)
    df = n1 + n2 - 2
    sp = np.sqrt(((n1 - 1) * x.var(ddof=1) + (n2 - 1) * y.var(ddof=1)) / df)
    d = (y.mean() - x.mean()) / sp
    J = 1 - 3 / (4 * df - 1)                      # 小样本校正（Hedges 1981）
    g = d * J
    se = np.sqrt((n1 + n2) / (n1 * n2) + g ** 2 / (2 * (n1 + n2)))
    return g, J, se


def d_av(pre, post):
    """配对比较，方向 = post − pre。返回 d_av, d_z, r(pre,post)。

    d_av 与独立 d 同尺度，共用色标时必须用它；
    d_z 受个体内相关影响（d_z/d_av = 1/sqrt(2(1-r))），只入表审计、不入图。
    """
    diff = post - pre
    s_av = np.sqrt((pre.var(ddof=1) + post.var(ddof=1)) / 2)
    return diff.mean() / s_av, diff.mean() / diff.std(ddof=1), np.corrcoef(pre, post)[0, 1]


def build_donor_table():
    meta = pd.read_csv(META_CSV)
    tags = "|".join(s.strip("_") for s in TIME_SUFFIX)
    meta["donor"] = (meta[SUBJ_COL] if SUBJ_COL
                     else meta[SAMPLE_COL].str.replace(r"_(%s)$" % tags, "", regex=True))
    meta["tp"] = meta[SAMPLE_COL].str.extract(r"_(%s)$" % tags)[0]
    scores = ([c for c in meta.columns if c.endswith(SCORE_SUFFIX)]
              if SCORE_SUFFIX else
              [c for c in meta.columns if pd.api.types.is_numeric_dtype(meta[c])])
    subs = sorted(meta[SUBCLUSTER_COL].dropna().unique()) if SUBCLUSTER_COL else [None]
    keys = [GROUP_COL] + ([SUBCLUSTER_COL] if SUBCLUSTER_COL else []) + ["donor"]
    gm = meta.groupby(keys)[scores].mean()        # donor 级（先细胞内均值，再 donor 均值）
    ncells = meta.groupby(keys).size().rename("ncells")
    return meta, gm, ncells, scores, subs


def main():
    meta, gm, ncells, scores, subs = build_donor_table()
    lv = gm.index.get_level_values
    donors = lv("donor")

    def unit(g, s, d):
        """(组, 亚群, donor) 索引键。"""
        return (g, s, d) if SUBCLUSTER_COL else (g, d)

    # ================= A. 数据完整性 =================
    print("=" * 78, "\n[A] 数据完整性")
    print(f"  细胞级行数={len(meta)} | donor 数={meta['donor'].nunique()} | "
          f"score 列数={len(scores)} | 亚群数={len(subs)}")
    ntp = meta.groupby("donor")["tp"].nunique()
    print(f"  单时间点孤儿 donor = {int((ntp < 2).sum())}  （应为 0，非 0 则配对编号有错）")
    print(f"  组别 × donor 数 = {meta.groupby(GROUP_COL)['donor'].nunique().to_dict()}")
    print(f"  每格细胞数: min={ncells.min()} 中位={int(ncells.median())} max={ncells.max()} "
          f"| <{LOW_CELL} 格数={int((ncells < LOW_CELL).sum())}")

    # ================= 逐格效应量（B/C/D 的公共输入） =================
    rows = []
    for eff, (A, B, paired) in EFFECTS.items():
        for s in subs:
            for sc in scores:
                sel_a = (lv(GROUP_COL) == A)
                sel_b = (lv(GROUP_COL) == B)
                if SUBCLUSTER_COL:
                    sel_a = sel_a & (lv(SUBCLUSTER_COL) == s)
                    sel_b = sel_b & (lv(SUBCLUSTER_COL) == s)
                ca = pd.Series(gm.loc[sel_a, sc].to_numpy(), index=donors[sel_a]).dropna()
                cb = pd.Series(gm.loc[sel_b, sc].to_numpy(), index=donors[sel_b]).dropna()
                if paired:
                    common = ca.index.intersection(cb.index)   # 按 donor 对齐
                    if len(common) < 3:
                        continue
                    pre, post = ca.loc[common].to_numpy(), cb.loc[common].to_numpy()
                    est, dz, r = d_av(pre, post)
                    p_np = stats.wilcoxon(post, pre).pvalue            # 配对主检验
                    p_pa = stats.ttest_rel(post, pre).pvalue
                    typ, aux1, aux2 = "d_av", dz, r
                    cells = [ncells.get(unit(g, s, d), 0)
                             for g in (A, B) for d in common]
                else:
                    if len(ca) < 3 or len(cb) < 3:
                        continue
                    est, aux1, _ = hedges_g(ca.to_numpy(), cb.to_numpy())
                    p_np = stats.mannwhitneyu(cb.to_numpy(), ca.to_numpy()).pvalue  # 独立主检验
                    p_pa = stats.ttest_ind(cb.to_numpy(), ca.to_numpy(), equal_var=False).pvalue
                    typ, aux2 = "g", np.nan
                    cells = [ncells.get(unit(g, s, d), 0)
                             for g in (A, B) for d in list(ca.index) + list(cb.index)]
                rows.append(dict(score=sc, sub=s, effect=eff, est=est, eff_type=typ,
                                 p_np=p_np, p_param=p_pa, aux1=aux1, aux2=aux2,
                                 n1=len(ca), n2=len(cb), ncells_min=int(min(cells))))
    df = pd.DataFrame(rows)
    df["axis"] = (df["score"].str.replace(SCORE_SUFFIX, "", regex=True)
                  if SCORE_SUFFIX else df["score"])

    # ================= B. 配对 QC =================
    print("\n" + "=" * 78, "\n[B] 配对 QC —— donor 级 r(Pre,Post)")
    pc = df[df.eff_type == "d_av"]
    if pc.empty:
        print("  （无配对比较，跳过）")
    else:
        for e in pc.effect.unique():
            x = pc.loc[pc.effect == e, "aux2"]
            print(f"  {e:10s} n={x.size:4d} min={x.min():+.3f} Q1={x.quantile(.25):+.3f} "
                  f"中位={x.median():+.3f} Q3={x.quantile(.75):+.3f} max={x.max():+.3f}")
        for e, v in pc.groupby("effect")["aux2"].median().items():
            if v < 0:
                print(f"  ⛔ {e} r 中位为负 ({v:+.3f}) → 该组配对检验效率**低于**独立检验。"
                      f"如实报告 + 另出独立口径敏感性表，不许偷偷切口径掩盖")
        lc = pc.assign(low=pc.ncells_min < LOW_CELL)
        print(f"  低细胞分层复核（异常 r 是否只来自低细胞格，<{LOW_CELL} 细胞）:")
        for e in pc.effect.unique():
            s = lc[lc.effect == e]
            hi = s[~s.low]
            print(f"    {e:10s} <{LOW_CELL}格(n={int(s.low.sum()):3d}) r中位={s[s.low].aux2.median():+.3f}"
                  f" | >={LOW_CELL}格(n={len(hi):3d}) r中位={hi.aux2.median():+.3f}"
                  f"  ← 后者若仍异常 ⇒ 非噪声，是数据稳健特征")

    # ================= C. FDR 检验族敏感性 =================
    fam_groups = {"global": None, "per_effect": ["effect"], "per_score": ["axis"],
                  "per_effect_x_axis": ["effect", "axis"]}
    for fam in FDR_FAMILIES:
        g = fam_groups[fam]
        df["q_" + fam] = (bh(df["p_np"]) if g is None
                          else df.groupby(g)["p_np"].transform(bh))
    print("\n" + "=" * 78, "\n[C] FDR 检验族敏感性 —— 显著格数 (q<0.05)")
    out = pd.DataFrame({
        fam: df.groupby("effect")["q_" + fam].apply(lambda x: int((x < .05).sum()))
        for fam in FDR_FAMILIES}).T
    out["合计"] = out.sum(axis=1)
    print(out.to_string())
    print("  ⇒ 族越细越不保守，实质改变谁带星号；默认取 per_effect（与面板结构一致），"
          "但要把族选择摆给用户拍板")

    # ================= D. 效应量 95% CI =================
    def ci(est, typ, n1, n2):
        se = (np.sqrt((n1 + n2) / (n1 * n2) + est ** 2 / (2 * (n1 + n2))) if typ == "g"
              else np.sqrt(1 / n1 + est ** 2 / (2 * n1)))
        return est - 1.96 * se, est + 1.96 * se

    df[["lo", "hi"]] = [ci(r.est, r.eff_type, r.n1, r.n2) for r in df.itertuples()]
    df["covers0"] = (df.lo <= 0) & (df.hi >= 0)
    print("\n" + "=" * 78, "\n[D] 效应量 95% CI（含 0 = 不排除无效）")
    for e in df.effect.unique():
        s = df[df.effect == e]
        print(f"  {e:10s} 中位est={s.est.median():+.3f} 中位CI宽={(s.hi - s.lo).median():.3f} "
              f"含0={int(s.covers0.sum())}/{len(s)}")

    # ================= E. 功效模拟 =================
    rng = np.random.default_rng(RNG_SEED)
    print("\n" + "=" * 78, f"\n[E] 功效模拟 (α=0.05, {N_SIM} 次)")
    ns = sorted({int(v) for v in pd.concat([df.n1, df.n2]).unique() if v >= 3})
    pa = ns[:2]
    print(f"{'d':>5}" + "".join(f"{f'n={n}配对(r={PAIR_R})':>20}{f'n={n}独立MWU':>14}" for n in pa))
    for d in POWER_DS:
        line = f"{d:>5.1f}"
        for n in pa:
            sig = 0
            for _ in range(N_SIM):
                pre = rng.normal(0, 1, n)
                # ⚠️ 必须带噪声项，使 corr(pre,post)=PAIR_R 且 sd(diff)=√(2(1−r))
                #    写成 post = pre + d（零噪声）→ Wilcoxon 恒显著 → 功效假象 1.0
                post = PAIR_R * pre + np.sqrt(1 - PAIR_R ** 2) * rng.normal(0, 1, n) + d
                sig += stats.wilcoxon(post, pre).pvalue < .05
            p_pair = sig / N_SIM
            sig = 0
            for _ in range(N_SIM):
                x_, y_ = rng.normal(0, 1, n), rng.normal(d, 1, n)
                sig += stats.mannwhitneyu(y_, x_).pvalue < .05
            line += f"{p_pair:>20.3f}{sig / N_SIM:>14.3f}"
        print(line)
    print("  ⇒ 若 d<0.8 处功效 <0.5：0 显著只能写「未检出显著证据（功效不足）」，"
          "禁写「无效/没有效应」")

    # ================= F. 实现校验（合成数据） =================
    print("\n" + "=" * 78, "\n[F] 实现校验（合成数据，改公式后必跑）")
    r2 = np.random.default_rng(1)
    x, y = r2.normal(0, 1, 9), r2.normal(.6, 1.4, 8)
    n1, n2 = len(x), len(y)
    dfo = n1 + n2 - 2
    manual = ((y.mean() - x.mean()) /
              np.sqrt(((n1 - 1) * x.var(ddof=1) + (n2 - 1) * y.var(ddof=1)) / dfo) *
              (1 - 3 / (4 * dfo - 1)))
    print(f"  Hedges g  手算 vs 函数 差 = {abs(manual - hedges_g(x, y)[0]):.2e}  （应为 0.00e+00）")
    pre, post = r2.normal(1, 1, 12), r2.normal(1.4, 1.3, 12)
    dm = (post - pre).mean() / np.sqrt((pre.var(ddof=1) + post.var(ddof=1)) / 2)
    print(f"  d_av      手算 vs 函数 差 = {abs(dm - d_av(pre, post)[0]):.2e}  （应为 0.00e+00）")
    pv = np.array([.001, .008, .039, .041, .30, .62, .90])
    try:
        from statsmodels.stats.multitest import multipletests
        print(f"  BH        自实现 vs statsmodels 差 = "
              f"{np.abs(bh(pv) - multipletests(pv, method='fdr_bh')[1]).max():.2e}  （应 ≤1e-16）")
    except ImportError:
        print(f"  BH        自实现 q = {np.round(bh(pv), 5)}（statsmodels 未装，跳过交叉校验）")
    if not pc.empty:
        r_med = pc.aux2.median()
        if not np.isnan(r_med) and abs(r_med) < 1:
            ob = (pc.aux1 / pc.est).median()
            th = 1 / np.sqrt(2 * (1 - r_med))
            print(f"  公式自洽  实测 d_z/d_av={ob:.3f} vs 理论 1/√(2(1−r))={th:.3f}"
                  f"  (r 中位={r_med:.3f})")

    df.to_csv("group_effects_audit.csv", index=False)
    print("\n已写: group_effects_audit.csv（逐格 est/p/q/CI/r/ncells 全量留档）")


if __name__ == "__main__":
    main()