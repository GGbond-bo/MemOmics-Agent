#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两组比较（小样本）→ 固定表头 CSV：Welch 双侧 t + Hedges' g + BH-FDR。

零第三方依赖（只用 stdlib：csv/math/statistics/argparse），可在任何 R/Python 环境直接跑，
不需要 scipy（Welch 的 t 分布 p 值用不完全 beta 函数自实现）。

输入：长表 CSV，默认列名 sample,group,gene,expr（每组若干例，组名由 --groups 指定）。
输出：每基因一行的 CSV，表头固定
      gene,mean_<A>,mean_<B>,pvalue,effect_size,qvalue,test_method,differential
      数值默认 6 位小数；effect_size = Hedges' g（正 = B 组高）；differential 判据由 --flag 决定。

用法：
  python two_group_compare.py --input expr.csv --output out.csv --groups Aging,T2D
  python two_group_compare.py --selftest        # 自证：与 2026-10-18 实测产物逐位核对

口径要点（详见 SKILL.md「小样本两组比较的执行口径」）：
  * 独立两组 + 方差不齐风险 → Welch（n≤10 时查不了方差齐性，Student 会高估精度）
  * 效应量 Hedges' g = d·J，J = 1 − 3/(4·df − 1)；等 n 时 SD_pooled 与 Welch 分母同式 ⇒ 不冲突
  * BH 带单调化（从最大 p 往小累进取 min），否则 q 会倒挂
  * ⚠️ differential 只是便利列：回复里必须声明判据（--flag p|q），并主动点出 p<0.05 但 q≥0.05 的边界行
"""
import argparse
import csv
import math
import statistics
import sys

# ---------------- 统计原语（零依赖） ----------------


def _betacf(a, b, x):
    MAXIT, EPS, FPMIN = 300, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def _betai(a, b, x):
    """正则化不完全 beta 函数 I_x(a, b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def welch_ttest(x1, x2):
    """返回 (t, df, 双侧 p)。x1/x2 为两组原始观测值。"""
    n1, n2 = len(x1), len(x2)
    if n1 < 2 or n2 < 2:
        raise ValueError("每组至少需要 2 个观测")
    m1, m2 = statistics.fmean(x1), statistics.fmean(x2)
    v1, v2 = statistics.variance(x1), statistics.variance(x2)   # ddof=1
    se2 = v1 / n1 + v2 / n2
    t = (m1 - m2) / math.sqrt(se2)
    df = se2 ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    p = _betai(df / 2.0, 0.5, df / (df + t * t))                # 双侧
    return t, df, p


def hedges_g(x1, x2):
    """Hedges' g（合并 SD + 小样本校正 J）；正 = 第二组均值更高。"""
    n1, n2 = len(x1), len(x2)
    df = n1 + n2 - 2
    s1, s2 = statistics.stdev(x1), statistics.stdev(x2)
    sp = math.sqrt(((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / df)
    if sp == 0:
        return float("nan")
    d = (statistics.fmean(x2) - statistics.fmean(x1)) / sp
    j = 1.0 - 3.0 / (4.0 * df - 1.0)
    return d * j


def bh_fdr(pvals):
    """Benjamini-Hochberg，带单调化（从最大 p 往小累进取 min）。"""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    q = [1.0] * m
    prev = 1.0
    for rank in range(m - 1, -1, -1):          # rank: 0-based 升序名次
        idx = order[rank]
        prev = min(prev, pvals[idx] * m / (rank + 1))
        q[idx] = prev
    return q


def mde_two_sample(n, alpha=0.05, power=0.80):
    """近似 MDE（最小可检测效应，单位 = Hedges' g）：
       MDE ≈ (t_{1−α/2,df} + t_{power,df}) · √(2/n)，df = 2n − 2。
       n=6 → df=10 → ≈ (2.228 + 0.879)·0.5774 ≈ 1.79
       （与 R power.t.test 一致：n=6/组、d=1.5 的功效 0.65 < 0.8 ⇒ 要 d≈1.8 才够 80% 功效；
        也解释了两组小样本里 d=0.5 的功效为何只有 0.12。）"""
    df = 2 * n - 2
    return (_t_ppf(1 - alpha / 2.0, df) + _t_ppf(power, df)) * math.sqrt(2.0 / n)


def _t_ppf(p, df):
    """t 分位数的二分求逆（够用，避免依赖 scipy）。"""
    lo, hi = -100.0, 100.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        cdf = 1.0 - 0.5 * _betai(df / 2.0, 0.5, df / (df + mid * mid))
        if cdf < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ---------------- 主流程 ----------------


def load_long(path, gene_col, group_col, value_col, groups):
    """长表 → {gene: {group: [values]}}，保持首次出现顺序。"""
    data, order = {}, []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            g = (row.get(gene_col) or "").strip()
            grp = (row.get(group_col) or "").strip()
            if not g or grp not in groups:
                continue
            val = float((row.get(value_col) or "").strip())
            data.setdefault(g, {}).setdefault(grp, []).append(val)
            if g not in order:
                order.append(g)
    return data, order


def compare(data, order, groups, alpha=0.05, flag="p", digits=6):
    rows, pvals = [], []
    for g in order:
        x1, x2 = data[g].get(groups[0], []), data[g].get(groups[1], [])
        if len(x1) < 2 or len(x2) < 2:
            print(f"[warn] {g}: 某组观测不足 2 个，跳过", file=sys.stderr)
            continue
        _, _, p = welch_ttest(x1, x2)
        rows.append({"gene": g,
                     f"mean_{groups[0]}": statistics.fmean(x1),
                     f"mean_{groups[1]}": statistics.fmean(x2),
                     "pvalue": p,
                     "effect_size": hedges_g(x1, x2),
                     "n1": len(x1), "n2": len(x2)})
        pvals.append(p)
    qs = bh_fdr(pvals) if pvals else []
    for r, q in zip(rows, qs):
        r["qvalue"] = q
        crit = r["pvalue"] if flag == "p" else q
        r["differential"] = "yes" if crit < alpha else "no"
        r["test_method"] = f"Welch t-test (two-sided)"
    return rows


def write_csv(rows, groups, path, digits=6):
    header = ["gene", f"mean_{groups[0]}", f"mean_{groups[1]}",
              "pvalue", "effect_size", "qvalue", "test_method", "differential"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([r["gene"],
                        f"{r[header[1]]:.{digits}f}",
                        f"{r[header[2]]:.{digits}f}",
                        f"{r['pvalue']:.{digits}f}",
                        f"{r['effect_size']:.4f}",
                        f"{r['qvalue']:.{digits}f}",
                        r["test_method"],
                        r["differential"]])
    return path


def report(rows, groups, flag):
    """打印表格 + 自动点出边界行（p<α 但 q≥α）。"""
    print(f"{'gene':8s}{'mean_' + groups[0]:>12s}{'mean_' + groups[1]:>12s}"
          f"{'pvalue':>12s}{'g':>10s}{'qvalue':>12s}  diff")
    for r in rows:
        print(f"{r['gene']:8s}{r[f'mean_{groups[0]}']:12.4f}{r[f'mean_{groups[1]}']:12.4f}"
              f"{r['pvalue']:12.6f}{r['effect_size']:10.4f}{r['qvalue']:12.6f}  {r['differential']}")
    print(f"\n[flag] differential 判据 = {flag} < 0.05；另一口径的结果可能不同，回复里必须声明")
    border = [r["gene"] for r in rows if r["pvalue"] < 0.05 <= r["qvalue"]]
    if border:
        print(f"[边界行] p<0.05 但 q>=0.05（校正后不再显著，务必在回复里点出）: {', '.join(border)}")
    n = rows[0]["n1"] if rows else 0
    print(f"[局限] 每组 n={n}；80% 功效只能检出 |g| ≳ {mde_two_sample(n):.2f} 的大效应"
          f"（参考：n=6/组时 d=0.5 功效 0.12、0.8→0.24、1.2→0.47、1.5→0.65）；"
          f"不显著 ≠ 无差异；正态性/方差齐性在此 n 下几乎无法检验，前提只能说「未发现明显违背」")


# ---------------- 自证（与 2026-10-18 实测产物核对） ----------------

SELFTEST_X1 = [11.204, 10.136, 11.745, 10.403, 9.844, 10.396]          # Aging / GENE1
SELFTEST_X2 = [12.931, 13.032, 11.965, 13.947, 12.205, 12.495]          # T2D   / GENE1
SELFTEST_P = [0.00039433936510108435, 0.77589731051136, 0.027086822406778018,
              0.12494514746328732, 0.700847977551006, 0.11897473902969302]
SELFTEST_Q = [0.002366036190606506, 0.7758973105113599, 0.08126046722033406,
              0.18741772119493097, 0.7758973105113599, 0.18741772119493097]


def selftest():
    ok = True
    t, df, p = welch_ttest(SELFTEST_X1, SELFTEST_X2)
    g = hedges_g(SELFTEST_X1, SELFTEST_X2)
    checks = [("Welch df ≈ n1+n2−2 = 10", abs(df - 10.0) < 1e-3, df),
              ("Welch p = 0.000394", abs(p - 0.000394) < 5e-7, p),
              ("Hedges' g = 2.7777", abs(g - 2.7777) < 1e-3, g),
              ("t 符号（负 = 第一组低）", t < 0, t)]
    for name, good, val in checks:
        ok &= good
        tag = "  ok  " if good else "  FAIL"
        det = f"  (got {val:.6f})" if isinstance(val, float) else ""
        print(f"{tag} {name}{det}")
    q = bh_fdr(SELFTEST_P)
    for i, (got, want) in enumerate(zip(q, SELFTEST_Q)):
        good = abs(got - want) < 1e-9
        ok &= good
        print(("  ok  " if good else "  FAIL") + f" BH q[{i}] = {want:.6f} (got {got:.6f})")
    print("\nSELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="两组比较 → 固定表头 CSV（Welch + Hedges' g + BH）")
    ap.add_argument("--input", help="长表 CSV")
    ap.add_argument("--output", help="输出 CSV 路径")
    ap.add_argument("--groups", help="两组名，逗号分隔，如 Aging,T2D（顺序 = 输出列顺序）")
    ap.add_argument("--gene-col", default="gene")
    ap.add_argument("--group-col", default="group")
    ap.add_argument("--value-col", default="expr")
    ap.add_argument("--flag", choices=["p", "q"], default="p",
                    help="differential 判据：原始 p（默认）或校正 q")
    ap.add_argument("--digits", type=int, default=6)
    ap.add_argument("--selftest", action="store_true", help="跑内置自证（不需输入文件）")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not (a.input and a.output and a.groups):
        ap.error("需要 --input / --output / --groups（或 --selftest）")
    groups = [s.strip() for s in a.groups.split(",") if s.strip()]
    if len(groups) != 2:
        ap.error("--groups 必须是两个组名")

    data, order = load_long(a.input, a.gene_col, a.group_col, a.value_col, groups)
    if not order:
        print("[error] 没读到任何基因（检查列名/组名是否匹配）", file=sys.stderr)
        return 2
    rows = compare(data, order, groups, flag=a.flag, digits=a.digits)
    write_csv(rows, groups, a.output, digits=a.digits)
    report(rows, groups, a.flag)
    print(f"\n[out] {a.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())