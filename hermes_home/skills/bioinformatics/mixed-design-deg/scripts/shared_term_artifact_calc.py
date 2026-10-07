#!/usr/bin/env python
"""共享项伪相关计算器（shared-term artifact calculator）

用途：判断「两个 DEG 对比的方向大部分相反」是生物学，还是设计矩阵的数学必然。

原理：Cov(c1'b, c2'b) = c1' (X'V⁻¹X)⁻¹ c2，V = ICC·ZZ' + (1−ICC)·I。
      两个对比只要在同一组均值上取相反符号，这一项就为负 —— 与生物学无关。

用法：
    1. 按自己的设计改 GROUPS（组名 -> (样本数, 供体组编号)）与 CONTRASTS（对比名 -> (正组, 负组)）
    2. python shared_term_artifact_calc.py
    3. 看输出：corr 越负 ⇒ 越不能用「方向相反」推断生物学；
       「纯伪影预期符号一致率」与实测一致率对比 ⇒ 实测落在区间内就只能判伪影
"""
import numpy as np
from numpy.linalg import inv

# ============ 按自己的设计修改 ============
# 组名 -> (样本数, 供体组编号)。同一供体组的 Pre/Post 共享随机效应。
# 例：3 组 × (Pre,Post)，Y 10 供体 / O 7 / OD 7
GROUPS = {
    "Y_Pre":  (10, 0), "Y_Post": (10, 0),
    "O_Pre":  (7, 1),  "O_Post": (7, 1),
    "OD_Pre": (7, 2),  "OD_Post": (7, 2),
}
# 对比名 -> (正组, 负组)
CONTRASTS = {
    "Aging":   ("O_Pre", "Y_Pre"),
    "Ex_Old":  ("O_Post", "O_Pre"),
    "Ex_Young": ("Y_Post", "Y_Pre"),
    "Ex_DM":   ("OD_Post", "OD_Pre"),
    "DM":      ("OD_Pre", "O_Pre"),
}
# 想考察「哪个对比显著基因的方向 vs 哪个对比」的伪影预期？
FOCUS_SELECTED = "Ex_Old"     # 在它上面按显著性选基因
FOCUS_OTHER = "Aging"         # 看它与它的符号一致率
OBSERVED_CONCORDANCE = 0.157  # 实测符号一致率（没有就设 None）
SIG_FRACTION = 1246 / 173950  # 入选比例（显著数 / 总检验数）
ICCS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.6]
# ========================================

names = list(GROUPS)
n_total = sum(n for n, _ in GROUPS.values())
n_donor = len({g for _, g in GROUPS.values()}) and sum(
    max(1, n // 2) if (g in [x for _, x in GROUPS.values()]) else 1
    for n, g in GROUPS.values())
# 供体数 = 每个 (供体组, 组内序号) 组合唯一；每组样本数为偶数时一半是供体
donor_ids = {}
d = 0
rows = []
for gi, (gname, (n, grp)) in enumerate(GROUPS.items()):
    for k in range(n):
        key = (grp, k if n % 2 == 0 else k // 2)
        if n % 2 == 0:                     # Pre/Post 各半 ⇒ 第 k 个样本属于第 k 个供体（若 k < n/2）
            key = (grp, k % (n // 2))
        if key not in donor_ids:
            donor_ids[key] = d; d += 1
        rows.append((gi, donor_ids[key]))

X = np.zeros((n_total, len(names)))
Z = np.zeros((n_total, d))
for i, (gi, di) in enumerate(rows):
    X[i, gi] = 1
    Z[i, di] = 1


def cvec(pos, neg):
    v = np.zeros(len(names)); v[names.index(pos)] = 1; v[names.index(neg)] = -1
    return v


print(f"样本数 {n_total} | 供体数 {d} | 组数 {len(names)}")
print("\n### 1) 全部对比两两相关（负值 = 共享项伪相关，不是生物学）")
cs = {k: cvec(*v) for k, v in CONTRASTS.items()}
for icc in [0.0, 0.3]:
    V = icc * (Z @ Z.T) + (1 - icc) * np.eye(n_total)
    C = inv(X.T @ inv(V) @ X)
    print(f"\n  ICC(donor)={icc}")
    print("  " + " " * 12 + "".join(f"{k:>11s}" for k in cs))
    for a, va in cs.items():
        line = f"  {a:12s}"
        for b, vb in cs.items():
            r = (va @ C @ vb) / np.sqrt((va @ C @ va) * (vb @ C @ vb))
            line += f"{r:11.3f}"
        print(line)

print(f"\n### 2) 纯伪影预期：在 {FOCUS_SELECTED} 显著基因上，与 {FOCUS_OTHER} 的符号一致率")
rng = np.random.default_rng(0)
a, b = cs[FOCUS_SELECTED], cs[FOCUS_OTHER]
for icc in ICCS:
    V = icc * (Z @ Z.T) + (1 - icc) * np.eye(n_total)
    C = inv(X.T @ inv(V) @ X)
    va, vb = a @ C @ a, b @ C @ b
    cov = a @ C @ b
    rho = cov / np.sqrt(va * vb)
    L = np.linalg.cholesky(np.array([[va, cov], [cov, vb]]))
    s = L @ rng.standard_normal((2, 400_000))
    x, y = s[0], s[1]
    thr = np.quantile(np.abs(x), 1 - SIG_FRACTION)   # 用实测显著比例反推选择阈值
    sel = np.abs(x) > thr
    print(f"  ICC={icc:.1f}  corr={rho:+.3f}  预期符号一致率 {(x[sel] > 0 == y[sel] > 0).mean() * 100:5.1f}%"
          if False else
          f"  ICC={icc:.1f}  corr={rho:+.3f}  预期符号一致率 {(((x[sel] > 0) == (y[sel] > 0)).mean() * 100):5.1f}%")

if OBSERVED_CONCORDANCE is not None:
    print(f"\n  实测符号一致率 = {OBSERVED_CONCORDANCE * 100:.1f}%")
    print("  实测落在预期区间内（或仅略高）⇒ 禁止把「方向相反」解释为生物学（如'逆转衰老'）")
    print("  实测显著高于预期上界 ⇒ 才可能存在真实同向共享信号，仍须独立验证")
print("\n### 3) 提示：DiD 不豁免共享项")
print("  DiD = (A_post-A_pre) - (B_post-B_pre) 与 'A_pre-B_pre' 共享 A_pre 与 B_pre 两组均值（都反号），")
print("  相关同样显著为负。要检验「处理把某组拉向另一组」，请改用距离分析：")
print("  逐样本算到目标组质心的距离 → 配对检验 post 是否比 pre 更近。")