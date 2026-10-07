#!/usr/bin/env python
# ============================================================
# axis_level_aggregation_perm_test.py
# 一键探针：回答「能不能直接用 p 值标注 / FDR 不显著是不是样本少」之后的正解路线
#
# 做四件事（全部只读，不改任何已有产物）：
#   ① π0（Storey）+ 期望假阳性 → 量化每个效应的 raw p 里到底有没有信号
#   ② 单格检验：按设计分流（独立 → Mann-Whitney，配对 → Wilcoxon 符号秩）
#   ③ 轴级 Stouffer Z 聚合 → 族从 (22 程序×10 亚群) 缩到 (5 轴×10 亚群) → BH
#   ④ 置换零分布验证（保持设计结构）→ 判定聚合是否膨胀
#
# 归属 skill: deg-mixed-design（混合设计：组间独立 + 组内配对）
# 用法：改下面 CONFIG 后 `python axis_level_aggregation_perm_test.py`
# ============================================================
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm

# ---------------------------- CONFIG ----------------------------
META = "E:/骨骼肌锻炼/MF_AUCell_meta.csv"   # 细胞级表：samplename / type / annotation_L3 / *_AUC
OUT_CSV = None            # 需要落盘时给个路径，如 "results/axis_level_stouffer.csv"
SCORE_SUFFIX = "_AUC"     # 打分列后缀（自动识别程序列）
SUBCL = "annotation_L3"   # 亚群列
SAMPLE = "samplename"     # 样本列（配对键 = 去掉 Pre/Post 后缀）
GROUP = "type"            # 组别列
N_PERM = 60               # 置换次数（60 够用；每组 <1 分钟量级）

# effect: (组A, 组B, 是否配对) —— 方向约定：eff 正值 = B 高于 A
EFF = {
    "Aging":   ("Y_Pre",  "O_Pre",  False),
    "T2D":     ("O_Pre",  "OD_Pre", False),
    "ExYoung": ("Y_Pre",  "Y_Post", True),
    "ExOld":   ("O_Pre",  "O_Post", True),
    "ExT2D":   ("OD_Pre", "OD_Post", True),
}

# 轴映射：程序名（去 _AUC 后缀）→ 生物学轴。⛔ 技术伪影轴与"身份 score"按需剔除
AXIS = {
    "②底物代谢": ["scoreOxPhos", "Glycolysis", "FattyAcidMetabolism", "Adipogenesis"],
    "③营养感应/蛋白稳态": ["scoreInsulin", "mTORC1", "AMPK_PGC1a", "Autophagy"],
    "④收缩装置/神经肌单元": ["scoreSarcomeric", "scoreRegMyon", "Denervation"],
    "⑤衰老-炎症-ROS环": ["scoreSenMayo", "scoreInflammatory", "scoreTNFA", "scoreROS"],
    "⑥终末失代偿重塑": ["scoreAtrophy", "Fibrosis"],
}
# 若要纳入这些轴，取消注释（族会变大 ⇒ 门槛更严）：
# AXIS["①技术伪影"] = ["scoreStress"]
# AXIS["⑦纤维型身份"] = ["scoreI", "scoreII", "scoreIIa", "scoreIIx"]
# -------------------------- /CONFIG ----------------------------

rng = np.random.default_rng(42)


def bh(p):
    """BH q-value，并列 p 取组内最大 rank（BH 原定义；argsort 会给并列值分配不同 rank）。"""
    p = np.asarray(p, float)
    n = len(p)
    if n == 0:
        return p
    o = np.argsort(p, kind="mergesort")
    r = np.empty(n, float)
    r[o] = np.arange(1, n + 1)
    r = np.maximum(r, np.searchsorted(np.sort(p, kind="mergesort"), p, side="right").astype(float))
    q = np.minimum.accumulate((p * n / r)[o][::-1])[::-1]
    out = np.empty(n)
    out[o] = q
    return np.clip(out, 0, 1)


def pi0_storey(p, lam=0.5):
    """Storey π0 估计（真零假设比例）。π0≈1 = 全是噪声。"""
    p = np.asarray(p, float)
    return (p > lam).sum() / (len(p) * (1 - lam)) if len(p) else np.nan


def stouffer(pv, sgn):
    """Stouffer Z 聚合：组合 p 连续，不受单格离散下界约束。"""
    pv = np.clip(np.asarray(pv, float), 1e-300, 1)
    z = norm.isf(pv / 2) * np.sign(np.asarray(sgn, float))
    return 2 * norm.sf(abs(z.sum() / np.sqrt(len(z))))


# ---------------- 载入 + donor 级聚合（消除伪重复） ----------------
meta = pd.read_csv(META)
SC = [c for c in meta.columns if c.endswith(SCORE_SUFFIX)]
assert SC, f"没找到以 {SCORE_SUFFIX} 结尾的打分列"
meta["donor"] = meta[SAMPLE].astype(str).str.replace(r"_(Pre|Post)$", "", regex=True)
gm = meta.groupby([GROUP, SUBCL, "donor"])[SC].mean()          # 推断单位 = donor
SUBS = sorted(meta[SUBCL].dropna().unique())
p2a = {p: a for a, ps in AXIS.items() for p in ps}
PROGS = [p for ps in AXIS.values() for p in ps]
K = {a: len(ps) for a, ps in AXIS.items()}
col = {f"{p}{SCORE_SUFFIX}": p for p in PROGS}                 # 实际列名 → 程序名

print(f"格点: {len(meta)} 细胞 | {len(SUBS)} 亚群 | {len(PROGS)} 程序 | {len(AXIS)} 轴")
print(f"单格数/效应 = {len(PROGS)}×{len(SUBS)} = {len(PROGS)*len(SUBS)} | "
      f"轴级格数/效应 ≈ {len(AXIS)}×{len(SUBS)} = {len(AXIS)*len(SUBS)}")


# ---------------- 单格 p（按设计分流） ----------------
def cell_p(sig, flip=False):
    """sig = (A, B, paired)。返回 DataFrame[prog, sub, p, eff]。flip=True 走置换。"""
    A, B, paired = sig
    rows = []
    for sub in SUBS:
        for cname, prog in col.items():
            ca = gm.loc[(A, sub), cname].dropna()
            cb = gm.loc[(B, sub), cname].dropna()
            if paired:
                common = ca.index.intersection(cb.index)
                if len(common) < 3:
                    continue
                pre, post = ca.loc[common].values.copy(), cb.loc[common].values.copy()
                if flip:                      # donor 内交换 Pre/Post（保持配对结构）
                    sw = rng.random(len(common)) < .5
                    pre[sw], post[sw] = post[sw], pre[sw]
                rows.append((prog, sub, stats.wilcoxon(post, pre).pvalue,
                             np.mean(post) - np.mean(pre)))
            else:
                if len(ca) < 3 or len(cb) < 3:
                    continue
                x, y = ca.values.copy(), cb.values.copy()
                if flip:                      # 打乱 donor 组标签，保持组大小
                    pool = np.concatenate([x, y])
                    idx = rng.permutation(len(pool))
                    x, y = pool[idx[:len(x)]], pool[idx[len(x):]]
                rows.append((prog, sub, stats.mannwhitneyu(y, x).pvalue,
                             np.mean(y) - np.mean(x)))
    return pd.DataFrame(rows, columns=["prog", "sub", "p", "eff"])


def axis_p(d):
    """单格表 → 轴级 Stouffer 表（只保留 k 与轴成员数一致的格）。"""
    rows = []
    for (ax, sub), g in d.groupby(["axis", "sub"]):
        if len(g) == K[ax]:
            rows.append((ax, sub, stouffer(g["p"].values, g["eff"].values), g["eff"].mean()))
    return pd.DataFrame(rows, columns=["axis", "sub", "p_axis", "eff_axis"])


# ---------------- ① π0 + 期望假阳性 ----------------
print("\n" + "=" * 78)
print("① π0（Storey）+ 期望假阳性 —— 量化 raw p 里到底有没有信号")
print("=" * 78)
print(f"{'效应':<9}{'π0(.5)':>8}{'π0(.8)':>8}{'raw p<.05':>10}{'期望假阳性':>11}{'真信号':>9}{'第一箱':>8}")
for e, sig in EFF.items():
    d = cell_p(sig)
    d["axis"] = d["prog"].map(p2a)
    p = d["p"].values
    p05, p08 = pi0_storey(p, .5), pi0_storey(p, .8)
    pi0 = min(p05, p08)
    obs = int((p < .05).sum())
    exp_fp = pi0 * len(p) * .05
    h, _ = np.histogram(p, bins=10)
    print(f"{e:<9}{p05:>8.3f}{p08:>8.3f}{obs:>10d}{exp_fp:>11.1f}{obs-exp_fp:>+9.1f}"
          f"{h[0]:>8d}   (第一箱期望 {len(p)/10:.0f})")

# ---------------- ② + ③ 单格 vs 轴级 ----------------
print("\n" + "=" * 78)
print("② 单格（程序级）vs ③ 轴级 Stouffer —— 同族 BH 下的显著格数")
print("=" * 78)
print(f"{'效应':<9}{'族大小':>7}{'raw p<.05':>11}{'BH q<.05':>10}{'族大小':>7}"
      f"{'raw p<.05':>11}{'BH q<.05':>10}{'BH q<.10':>10}")
store = {}
for e, sig in EFF.items():
    d = cell_p(sig)
    d["axis"] = d["prog"].map(p2a)
    qs = bh(d["p"].values)
    a = axis_p(d)
    qa = bh(a["p_axis"].values)
    a["q"] = qa
    store[e] = a
    print(f"{e:<9}{len(d):>7}{int((d['p']<.05).sum()):>11d}{int((qs<.05).sum()):>10d}"
          f"{len(a):>7}{int((a['p_axis']<.05).sum()):>11d}{int((qa<.05).sum()):>10d}"
          f"{int((qa<.10).sum()):>10d}")

print("\n轴级 q<0.05 明细：")
for e, a in store.items():
    sig = a[a.q < .05].sort_values("q")
    if not len(sig):
        print(f"  {e}: 无（与 π0 结论对照 —— 可能数据里就没有可检出效应）")
        continue
    print(f"  {e} ({len(sig)} 格): " + ", ".join(
        f"{r.axis[:6]}×{r['sub']}(q={r.q:.3f})" for _, r in sig.head(8).iterrows()))

# ---------------- ④ 置换零分布验证 ----------------
print("\n" + "=" * 78)
print(f"④ 置换零分布（{N_PERM} 次/效应）—— 零假设下 q<0.05 格数应 ≈ 0；均值>0.5 判为膨胀")
print("=" * 78)
print(f"{'效应':<9}{'真实 q<.05':>10}{'置换均值':>10}{'置换最大':>10}{'膨胀?':>8}")
for e, sig in EFF.items():
    cnt = []
    for _ in range(N_PERM):
        dp = cell_p(sig, flip=True)
        ap = axis_p(dp)
        cnt.append(int((bh(ap["p_axis"].values) < .05).sum()))
    cnt = np.array(cnt)
    real = int((store[e].q < .05).sum())
    print(f"{e:<9}{real:>10d}{cnt.mean():>10.2f}{cnt.max():>10d}"
          f"{('⚠️ 是' if cnt.mean() > .5 else '否'):>8}")

# ---------------- 落盘 ----------------
if OUT_CSV:
    allr = []
    for e, a in store.items():
        t = a.copy()
        t["effect"] = e
        allr.append(t)
    pd.concat(allr, ignore_index=True).to_csv(OUT_CSV, index=False)
    print(f"\n落盘: {OUT_CSV}")

print("""
—— 判读口诀 ——
· π0 ≈ 1 且 raw p 格数 ≤ 期望假阳性  → raw p 标注 = 造假发现，⛔ 绝不能标
· π0 低（<0.5）                      → raw p 里真信号浓，但仍优先报 FDR 结果
· 轴级置换均值 ≈ 0                    → 聚合无膨胀，可作正式 FDR 口径引用
· 置换均值 > 0.5                      → 聚合在膨胀，改用 Fisher/Brown 或退回单格
""")