# ============================================================
# MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# 执行前: rail_review(pre) | 参数不确定 → debate_analysis
# 执行后: rail_review(post) | record_run / record_error
# ============================================================

import pandas as pd
import numpy as np
import os
import sys
from scipy import stats
from statsmodels.stats.multitest import multipletests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

def load_peak_table(path: str) -> pd.DataFrame:
    """读取峰表：第一列代谢物名，其余为样本。"""
    df = pd.read_csv(path, sep="\t" if path.endswith(".tsv") else ",", index_col=0)
    return df

def qc_filter(df: pd.DataFrame, min_fraction: float = 0.8, cv_threshold: float = 0.3) -> pd.DataFrame:
    """QC：过滤缺失率过高或 QC 样本 CV 过大的代谢物。"""
    non_missing = df.notna().mean(axis=1)
    df = df[non_missing >= min_fraction]
    return df

def normalize(df: pd.DataFrame, method: str = "total_area") -> pd.DataFrame:
    """归一化：总峰面积 / 中位数。"""
    if method == "total_area":
        factor = df.sum(axis=0) / df.sum(axis=0).mean()
    else:
        factor = df.median(axis=0) / df.median(axis=0).mean()
    return df / factor

def impute(df: pd.DataFrame, value: float = None) -> pd.DataFrame:
    """缺失值填充：默认用每列最小值的一半。"""
    if value is None:
        value = df.min(axis=0) / 2
    return df.fillna(value)

def differential(df: pd.DataFrame, group_a: list, group_b: list,
                 fdr_threshold: float = 0.05, log2fc_threshold: float = 1.0) -> pd.DataFrame:
    """两组差异分析：t 检验 + BH FDR。返回带 pvalue/fdr/log2fc 的表。"""
    a, b = df[group_a], df[group_b]
    pvals, log2fcs = [], []
    for idx in df.index:
        av, bv = a.loc[idx].dropna(), b.loc[idx].dropna()
        if len(av) < 2 or len(bv) < 2:
            pvals.append(np.nan); log2fcs.append(np.nan); continue
        t, p = stats.ttest_ind(av, bv, equal_var=False)
        pvals.append(p)
        log2fcs.append(np.log2(bv.mean() / max(av.mean(), 1e-9)))
    res = pd.DataFrame({"pvalue": pvals, "log2fc": log2fcs}, index=df.index)
    res["fdr"] = multipletests(res["pvalue"].dropna(), method="fdr_bh")[1] if res["pvalue"].notna().any() else np.nan
    res["significant"] = (res["fdr"] < fdr_threshold) & (res["log2fc"].abs() > log2fc_threshold)
    return res


def heatmap_plot(df: pd.DataFrame, res: pd.DataFrame, group_a: list, group_b: list, out_path: str, top_n: int = 25):
    """差异热图：取 top_n 显著代谢物，样本按组排序。"""
    sig = res[res["significant"] == True].sort_values("fdr")
    if len(sig) == 0:
        sig = res.sort_values("pvalue").head(top_n)
    top = sig.head(top_n).index.tolist()
    sub = df.loc[top, group_a + group_b]
    sub = sub.apply(lambda r: (r - r.mean()) / (r.std() + 1e-9), axis=1)  # z-score 每代谢物
    plt.figure(figsize=(max(6, len(sub.columns) * 0.4), max(4, len(sub) * 0.35)))
    sns.heatmap(sub, cmap="RdBu_r", center=0, cbar_kws={"label": "z-score"})
    plt.title(f"Top {len(sub)} Differential Metabolites (heatmap)")
    plt.tight_layout(); plt.savefig(out_path, dpi=150); plt.close()

def volcano_plot(res: pd.DataFrame, out_path: str):
    plt.figure(figsize=(7, 6))
    sns.scatterplot(x=res["log2fc"], y=-np.log10(res["pvalue"]), hue=res["significant"], palette={True: "red", False: "gray"})
    plt.axhline(-np.log10(0.05), ls="--", c="gray", lw=0.8)
    plt.axvline(0, ls="--", c="gray", lw=0.8)
    plt.xlabel("log2FC"); plt.ylabel("-log10(p)")
    plt.title("Volcano Plot")
    plt.tight_layout(); plt.savefig(out_path, dpi=150); plt.close()

if __name__ == "__main__":
    peak_path = sys.argv[1]
    grp_file = sys.argv[2]  # tsv: sample<TAB>group
    out_dir = sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    df = load_peak_table(peak_path)
    df = qc_filter(df)
    df = normalize(df)
    df = impute(df)
    grp = pd.read_csv(grp_file, sep="\t", index_col=0)["group"]
    a = grp[grp == "A"].index.tolist(); b = grp[grp == "B"].index.tolist()
    res = differential(df, a, b)
    res.to_csv(os.path.join(out_dir, "differential_results.tsv"), sep="\t")
    volcano_plot(res, os.path.join(out_dir, "volcano.png"))
    heatmap_plot(df, res, a, b, os.path.join(out_dir, "heatmap.png"))
    print(f"Done. {len(res)} metabolites, {int(res['significant'].sum())} significant.")
