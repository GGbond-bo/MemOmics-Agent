#!/usr/bin/env python
"""
GSE278576 人海马衰老 ATAC 对比流程 — 核心执行（官方 cCRE 复用版）
官方 cCRE (Table_S7, 472,859) + 自己 fragments 计数 → pseudobulk log2CPM → 连续年龄 Pearson 相关

完全复现官方 correlation_ATAC.ipynb 逻辑:
  1. 官方 472,859 个 cCRE 作为特征（跳过 MACS3 peak calling）
  2. 每样本统计落在每个 cCRE 的 fragment 计数
  3. 供体过滤（官方）: 供体平均 ≥1 count/cCRE
  4. pseudobulk log2CPM 归一化
  5. Pearson cor.test(log2CPM, donor_age) per cCRE
  6. FDR < 0.1 → Up (cor>0) / Down (cor<0)

用法:
  python3 core_age_correlation.py --out all_celltypes --n-procs 4

关键路径（按需修改）:
  FRAG_DIR = E:\\专利\\Human_Hippocampus_ATAC\\fragments
  TABLE_S7 = ...\\suppl_media2\\Supplemental Tables S1-S24\\Table_S7.tsv
  TABLE_S1 = ...\\Table_S1.tsv
"""
import os
import sys
import gzip
import time
import argparse
from collections import defaultdict
from multiprocessing import Pool, cpu_count

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

FRAG_DIR = r"E:\专利\Human_Hippocampus_ATAC\fragments"
OUT_DIR = r"MEMOMICS_HOME\results\memomics-8857f1c1\gse278576_comparison"
TABLE_S7 = r"E:\专利\Human_Hippocampus_ATAC\papers\suppl_media2\Supplemental Tables S1-S24\Table_S7.tsv"
TABLE_S1 = r"E:\专利\Human_Hippocampus_ATAC\papers\suppl_media2\Supplemental Tables S1-S24\Table_S1.tsv"

SAMPLE_MAP = {
    "GSM8549615_hc77": "hc77", "GSM8549616_hc78": "hc78", "GSM8549617_hc5579": "hc5579",
    "GSM8549618_hc76": "hc76", "GSM8549619_hc29": "hc29", "GSM8549620_hc6052": "hc6052",
    "GSM8549621_hc5614": "hc5614", "GSM8549622_hc13344": "hc13344", "GSM8549623_hc935": "hc935",
}

def load_ccre_from_table_s7():
    """Table_S7 → cCRE 列表 [(chr, start, end, celltypes)]"""
    ccres = []
    with open(TABLE_S7, encoding="utf-8") as f:
        next(f)  # header
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            coord, ct = parts[0], parts[1]
            chrom, s, e = coord.split("-")
            ccres.append((chrom, int(s), int(e), ct))
    return ccres

def build_interval_index(ccres):
    """按 chr 构建区间索引 → {chr: np.array([[start, end, idx], ...])}"""
    chr_dict = defaultdict(list)
    for i, (chrom, start, end, _) in enumerate(ccres):
        chr_dict[chrom].append((start, end, i))
    for chrom in chr_dict:
        chr_dict[chrom] = np.array(sorted(chr_dict[chrom], key=lambda x: (x[0], x[1])), dtype=np.int64)
    return chr_dict

def count_fragments(frag_path, chr_dict, n_ccres):
    """统计 fragments 落在 cCRE 的计数。fragments 格式: chr start end barcode count（数据从第 51 行起）"""
    counts = np.zeros(n_ccres, dtype=np.int64)
    n_frags = 0
    with gzip.open(frag_path, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            chrom, start, end = parts[0], int(parts[1]), int(parts[2])
            n_frags += 1
            if chrom not in chr_dict:
                continue
            arr = chr_dict[chrom]
            starts = arr[:, 0]
            idx = np.searchsorted(starts, start, side="left")
            j = idx - 1
            while j >= 0 and arr[j, 1] > start:
                counts[arr[j, 2]] += 1
                j -= 1
            j = idx
            while j < len(arr) and arr[j, 0] < end:
                counts[arr[j, 2]] += 1
                j += 1
    return counts, n_frags

def _count_worker(args):
    frag_path, chr_dict, n_ccres, sample = args
    t0 = time.time()
    counts, n_frags = count_fragments(frag_path, chr_dict, n_ccres)
    print(f"[{sample}] {n_frags:,} frags -> {int(counts.sum()):,} in cCREs ({time.time()-t0:.0f}s)", flush=True)
    return sample, counts, n_frags

def count_all_parallel(frag_files, chr_dict, n_ccres, n_procs=None):
    n_procs = n_procs or min(cpu_count(), len(frag_files))
    n_procs = min(n_procs, 6)
    tasks = [(frag_files[s], chr_dict, n_ccres, s) for s in sorted(frag_files)]
    with Pool(n_procs) as pool:
        results = pool.map(_count_worker, tasks)
    count_mat = np.zeros((n_ccres, len(results)), dtype=np.int64)
    samples = []
    sorted_samples = sorted(frag_files)
    for sample, counts, n_frags in results:
        idx = sorted_samples.index(sample)
        count_mat[:, idx] = counts
        samples.append(sample)
    return count_mat, samples

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="all_celltypes")
    parser.add_argument("--fdr-thresh", type=float, default=0.1)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--n-procs", type=int, default=None)
    args = parser.parse_args()

    os.makedirs(os.path.join(OUT_DIR, "age_correlation"), exist_ok=True)

    t0 = time.time()
    ccres = load_ccre_from_table_s7()
    print(f"加载 {len(ccres)} 官方 cCRE ({time.time()-t0:.1f}s)", flush=True)

    s1 = pd.read_csv(TABLE_S1, sep="\t")
    age_map = {}
    for _, row in s1.iterrows():
        donor = str(int(row["Donor ID"]))
        age_val = str(row["Age"]).strip()
        try:
            age_map[donor] = int(float(age_val.replace("+", "")))
        except (ValueError, TypeError):
            print(f"skip donor {donor}: {age_val}")
    print(f"供体年龄映射: {len(age_map)} donors", flush=True)

    frag_files = {}
    for fname in os.listdir(FRAG_DIR):
        if fname.endswith("_atac_fragments.tsv.gz") and not fname.endswith(".tbi.gz"):
            for gsm, name in SAMPLE_MAP.items():
                if fname.startswith(gsm):
                    frag_files[name] = os.path.join(FRAG_DIR, fname)
                    break
    samples = sorted(frag_files.keys())
    sample_ages = {}
    for s in samples:
        donor = s.replace("hc", "")
        if donor in age_map:
            sample_ages[s] = age_map[donor]
    samples = [s for s in samples if s in sample_ages]
    if args.max_samples:
        samples = samples[:args.max_samples]
    print(f"有效样本: {len(samples)} -> 年龄: {[(s, sample_ages[s]) for s in samples]}", flush=True)

    chr_dict = build_interval_index(ccres)
    count_mat, samples = count_all_parallel(
        {s: frag_files[s] for s in samples}, chr_dict, len(ccres), n_procs=args.n_procs)

    donor_total = count_mat.sum(axis=0)
    print(f"供体总计数: {donor_total}", flush=True)
    keep_donors = donor_total >= len(ccres) * 1.0
    if not all(keep_donors):
        print(f"donor filter: remove {sum(~keep_donors)} low-count donors", flush=True)
        count_mat = count_mat[:, keep_donors]
        samples = [s for s, k in zip(samples, keep_donors) if k]
    if len(samples) < 3:
        print(f"ERROR: {len(samples)} donors < 3, cannot do correlation", flush=True)
        return

    colsums = count_mat.sum(axis=0).astype(float)
    colsums[colsums == 0] = 1
    cpm = count_mat / colsums * 1e6
    log2cpm = np.log2(cpm + 1)

    ages = np.array([sample_ages[s] for s in samples], dtype=float)
    corrs = np.full(len(ccres), np.nan)
    pvals = np.full(len(ccres), np.nan)
    for i in range(len(ccres)):
        row = log2cpm[i]
        if np.std(row) == 0:
            continue
        r, p = stats.pearsonr(row, ages)
        corrs[i], pvals[i] = r, p

    valid = ~np.isnan(pvals)
    fdr = np.full(len(ccres), np.nan)
    if valid.sum() > 0:
        fdr[valid] = multipletests(pvals[valid], method="fdr_bh")[1]

    df = pd.DataFrame({
        "coordinates": [f"{c[0]}-{c[1]}-{c[2]}" for c in ccres],
        "chr": [c[0] for c in ccres], "start": [c[1] for c in ccres],
        "end": [c[2] for c in ccres], "celltype": [c[3] for c in ccres],
        "cor": corrs, "pval": pvals, "fdr": fdr,
    })
    df["log10fdr"] = -np.log10(df["fdr"] + 1e-300)
    df["Age_Correlated"] = "No"
    df.loc[(df["fdr"] < args.fdr_thresh) & (df["cor"] > 0), "Age_Correlated"] = "Up"
    df.loc[(df["fdr"] < args.fdr_thresh) & (df["cor"] < 0), "Age_Correlated"] = "Down"

    full_out = os.path.join(OUT_DIR, "age_correlation", f"{args.out}_pcc_full.tsv")
    sig_out = os.path.join(OUT_DIR, "age_correlation", f"{args.out}_pcc_fdr_{args.fdr_thresh}.tsv")
    cpm_out = os.path.join(OUT_DIR, "age_correlation", "cpm_matrix.tsv")
    df.to_csv(full_out, sep="\t", index=False)
    df[df["Age_Correlated"] != "No"].to_csv(sig_out, sep="\t", index=False)
    cpm_df = pd.DataFrame(log2cpm, columns=samples)
    cpm_df.insert(0, "coordinates", [f"{c[0]}-{c[1]}-{c[2]}" for c in ccres])
    cpm_df.to_csv(cpm_out, sep="\t", index=False)

    print(f"SAVED: {full_out}", flush=True)
    print(f"SAVED: {sig_out}", flush=True)
    print(f"SAVED: {cpm_out}", flush=True)
    print(df["Age_Correlated"].value_counts().to_string(), flush=True)
    if (df["Age_Correlated"] != "No").sum() > 0:
        print(df[df["Age_Correlated"] == "Up"].nlargest(5, "cor")[["coordinates", "celltype", "cor", "fdr"]].to_string(index=False))
        print(df[df["Age_Correlated"] == "Down"].nsmallest(5, "cor")[["coordinates", "celltype", "cor", "fdr"]].to_string(index=False))

if __name__ == "__main__":
    main()
