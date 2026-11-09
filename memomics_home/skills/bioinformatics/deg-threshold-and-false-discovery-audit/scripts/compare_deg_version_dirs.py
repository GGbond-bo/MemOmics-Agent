#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""compare_deg_version_dirs.py — 对比两版 DEG 结果目录，并做「参数未变子集」隔离归因。

用途（铁律 1.8）：用户问「我按旧版跑过了，换新版结果会不会变」/「跑个新版看看区别」时，
两版都跑完后用本脚本逐对量化差异，并自动按元信息列（如 k、batch_used）分层。

用法
  python compare_deg_version_dirs.py OLD_DIR NEW_DIR OUT_DIR \
      [--old-suffix _sDEG] [--new-suffix _v8] [--prefix immune_] \
      [--key-cols k_actual batch_used] [--fdr 0.05]

文件命名约定：<prefix><celltype>_<comparison><suffix>.csv
  例：immune_CD14__Mono_Y_Pre_vs_O_Pre_sDEG.csv
comparison 由「最后一个 _ 之前 / 之后」切不出来时，会用 --comparisons 里最长后缀匹配。

输出
  OUT_DIR/deg_version_comparison.csv    逐对明细
  OUT_DIR/deg_version_comparison.md     同上（markdown，可直接贴报告）
  终端打印：总体指标 + 按 key-cols 分层的归因表 + 「逐位相同」子集验证结果

关键判据（脚本会自动打印）
  若「主参数未变」的子集 jaccard == 1.0 且 coef_spearman == 1.0
    ⇒ 该参数被证明是唯一驱动因素（其余改动对统计量零影响）
"""
import argparse
import glob
import os
import re
import sys

import numpy as np
import pandas as pd
from scipy import stats

DEFAULT_COMPARISONS = [
    "Y_Pre_vs_Y_Post", "O_Pre_vs_O_Post", "OD_Pre_vs_OD_Post",
    "Y_Pre_vs_O_Pre", "O_Pre_vs_OD_Pre",
]
COEF_CANDIDATES = ("coef", "logFC", "avg_log2FC", "log2FoldChange")
P_CANDIDATES = ("p", "pvalue", "p_val")
FDR_CANDIDATES = ("fdr", "padj", "p_val_adj")


def _pick(df, candidates, target):
    """把各版本可能不同的列名统一成 target。"""
    for c in candidates:
        for col in df.columns:
            if col.lower() == c.lower():
                if col != target:
                    df = df.rename(columns={col: target})
                return df
    return df


def load(path):
    df = pd.read_csv(path)
    df = _pick(df, COEF_CANDIDATES, "coef")
    df = _pick(df, P_CANDIDATES, "p")
    df = _pick(df, FDR_CANDIDATES, "fdr")
    missing = [c for c in ("gene", "coef", "p", "fdr") if c not in df.columns]
    if missing:
        raise ValueError(f"{os.path.basename(path)} 缺列: {missing}（现有 {list(df.columns)[:12]}）")
    return df


def split_key(fname, prefix, suffix, comparisons):
    base = os.path.basename(fname)
    base = re.sub(r"\.csv$", "", base)
    if prefix and base.startswith(prefix):
        base = base[len(prefix):]
    if suffix and base.endswith(suffix):
        base = base[: -len(suffix)]
    for c in sorted(comparisons, key=len, reverse=True):
        if base.endswith("_" + c):
            return base[: -(len(c) + 1)], c
    parts = base.rsplit("_", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (base, "NA")


def compare_pair(p_old, p_new, fdr_cut):
    do, dn = load(p_old), load(p_new)
    do = do.dropna(subset=["coef"]).drop_duplicates("gene")
    dn = dn.dropna(subset=["coef"]).drop_duplicates("gene")
    do["gene"] = do["gene"].astype(str)
    dn["gene"] = dn["gene"].astype(str)
    do = do.set_index("gene")
    dn = dn.set_index("gene")

    s_old = set(do.index[(do["fdr"] < fdr_cut) & do["fdr"].notna()])
    s_new = set(dn.index[(dn["fdr"] < fdr_cut) & dn["fdr"].notna()])
    inter, union = s_old & s_new, s_old | s_new

    common = do.index.intersection(dn.index)
    out = dict(
        n_genes_old=len(do), n_genes_new=len(dn), n_common_genes=len(common),
        sig_old=len(s_old), sig_new=len(s_new), sig_inter=len(inter),
        jaccard=round(len(inter) / len(union), 4) if union else np.nan,
        sig_only_new=len(s_new - s_old), sig_only_old=len(s_old - s_new),
    )

    if inter:
        gi = list(inter)
        out["dir_agree_among_shared_sig"] = round(
            float((np.sign(do.loc[gi, "coef"]) == np.sign(dn.loc[gi, "coef"])).mean()), 4)

    if len(common) > 2:
        c_o = do.loc[common, "coef"].astype(float)
        c_n = dn.loc[common, "coef"].astype(float)
        ok = np.isfinite(c_o) & np.isfinite(c_n)
        if ok.sum() > 2:
            out["coef_pearson"] = round(float(stats.pearsonr(c_o[ok], c_n[ok])[0]), 4)
            out["coef_spearman"] = round(float(stats.spearmanr(c_o[ok], c_n[ok])[0]), 4)
        p_o = do.loc[common, "p"].astype(float).clip(lower=1e-300)
        p_n = dn.loc[common, "p"].astype(float).clip(lower=1e-300)
        ok = np.isfinite(p_o) & np.isfinite(p_n)
        if ok.sum() > 2:
            out["neglogp_spearman"] = round(float(
                stats.spearmanr(-np.log10(p_o[ok]), -np.log10(p_n[ok]))[0]), 4)

    # 元信息：两版各取常数列（用于分层归因）
    for tag, d in (("old", do), ("new", dn)):
        for col in ("k_actual", "nRUV_used", "df_resid", "batch_used", "n_samples", "n_cells"):
            if col in d.columns:
                vals = pd.unique(d[col].dropna())
                if len(vals) == 1:
                    out[f"{tag}_{col}"] = vals[0]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old_dir")
    ap.add_argument("new_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--old-suffix", default="_sDEG")
    ap.add_argument("--new-suffix", default="_v8")
    ap.add_argument("--prefix", default="immune_")
    ap.add_argument("--fdr", type=float, default=0.05)
    ap.add_argument("--comparisons", nargs="*", default=DEFAULT_COMPARISONS)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    cmp_list = args.comparisons

    f_old, f_new = {}, {}
    for p in glob.glob(os.path.join(args.old_dir, "*.csv")):
        if args.prefix and not os.path.basename(p).startswith(args.prefix):
            continue
        f_old[split_key(p, args.prefix, args.old_suffix, cmp_list)] = p
    for p in glob.glob(os.path.join(args.new_dir, "*.csv")):
        if args.prefix and not os.path.basename(p).startswith(args.prefix):
            continue
        f_new[split_key(p, args.prefix, args.new_suffix, cmp_list)] = p

    shared = sorted(set(f_old) & set(f_new))
    print(f"old 目录 {len(f_old)} 表 | new 目录 {len(f_new)} 表 | 成对可比 {len(shared)}")
    only_old = sorted(set(f_old) - set(f_new))
    only_new = sorted(set(f_new) - set(f_old))
    print(f"仅 old 有 {len(only_old)} 个 | 仅 new 有 {len(only_new)} 个")
    for k in only_old:
        print("  仅 old:", " / ".join(k))
    for k in only_new:
        print("  仅 new:", " / ".join(k))
    if only_old or only_new:
        print("  ⚠️ 覆盖率不一致必须在报告里逐个交代跳过原因，不能默认当噪声")

    rows = []
    for tag, comp in shared:
        try:
            r = compare_pair(f_old[(tag, comp)], f_new[(tag, comp)], args.fdr)
        except Exception as e:  # noqa: BLE001
            print(f"  !! {tag} / {comp} 比对失败: {e}")
            continue
        r.update(celltype=tag, comparison=comp)
        rows.append(r)

    if not rows:
        print("没有可比对的组合"); sys.exit(1)

    res = pd.DataFrame(rows).sort_values(["celltype", "comparison"])
    fp = os.path.join(args.out_dir, "deg_version_comparison.csv")
    res.to_csv(fp, index=False)
    with open(os.path.join(args.out_dir, "deg_version_comparison.md"), "w", encoding="utf-8") as fh:
        fh.write("# DEG 两版结果对比\n\n")
        fh.write(f"成对可比组合：{len(res)}\n\n")
        try:
            fh.write(res.to_markdown(index=False))
        except Exception:  # tabulate 缺失
            fh.write(res.to_string(index=False))
        fh.write("\n")
    print("写出:", fp)

    print("\n=== 总体 ===")
    for c in ("sig_old", "sig_new", "sig_inter"):
        print(f"  {c}: 中位 {res[c].median():.0f}  合计 {res[c].sum():.0f}")
    for c in ("jaccard", "dir_agree_among_shared_sig", "coef_spearman", "neglogp_spearman"):
        if c in res.columns:
            print(f"  {c}: 中位 {res[c].median():.4f}  范围 {res[c].min():.4f} ~ {res[c].max():.4f}")

    # ---- 自动归因：找出主参数（old_nRUV_used vs new_k_actual / nRUV_used）是否变化 ----
    k_old = next((c for c in ("old_nRUV_used", "old_k_actual") if c in res.columns), None)
    k_new = next((c for c in ("new_k_actual", "new_nRUV_used") if c in res.columns), None)
    if k_old and k_new:
        res["dparam"] = res[k_new] - res[k_old]
        changed = res["dparam"] != 0
        print(f"\n=== 归因：主参数({k_new} vs {k_old})变化的组合 {int(changed.sum())}/{len(res)} ===")
        same = res[~changed]
        if len(same):
            bit_identical = same[(same["jaccard"] == 1.0) & (same["coef_spearman"] == 1.0)]
            print(f"  参数未变子集 n={len(same)}；其中 jaccard==1 且 coef_spearman==1 的 {len(bit_identical)} 个")
            if len(bit_identical) == len(same):
                print("  ✅ 证明：参数未变时结果逐位相同 ⇒ 该参数是唯一驱动因素，其余改动对统计量零影响")
        if "batch_used" in res.columns:
            sub = res[changed]
            print("\n  按 batch_used 分层（仅参数已变化的组合）：")
            for val, g in sub.groupby("new_batch_used" if "new_batch_used" in sub.columns else "batch_used"):
                print(f"    batch_used={val}: n={len(g)}  jaccard中位={g['jaccard'].median():.4f}  "
                      f"coef_spearman中位={g['coef_spearman'].median():.4f}")
        if (res["dparam"] != 0).any():
            ratio = (res.loc[changed, k_new] / res.loc[changed, k_old]).astype(float)
            bins = pd.cut(ratio, [-0.01, 0.3, 0.5, 0.8, 1.01])
            print("\n  压缩幅度 vs 差异：")
            print(res.loc[changed].groupby(bins, observed=True)["jaccard"]
                  .agg(["size", "median"]).to_string())
    else:
        print("\n（两版都没有 k_actual/nRUV_used 列，跳过自动归因；可手动按 --key-cols 分层）")


if __name__ == "__main__":
    main()