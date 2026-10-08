# -*- coding: utf-8 -*-
"""通用 ORA 富集：Enrichr 基因集实下载 + 超几何检验 + BH-FDR（可独立重跑）

用途：本地/知识库没有目标基因集时，从 Enrichr 公开 API 实下载，对「前景基因集 vs 背景基因集」
做单侧超几何富集 + Benjamini-Hochberg FDR。**严禁凭记忆手写基因集**（违反不编造铁律）。

用法：
  python enrichr_ora_hypergeom.py \
      --foreground results/v21_core_elements.csv --fg-col symbol \
      --background results/v21_gene_three_pillar.csv --bg-col symbol \
      --libraries Reactome_2022 KEGG_2021_Human Aging_Perturbations_from_GEO_up \
      --out results/enrichment.csv --stats results/enrichment_stats.json

可选：
  --within-lib LIB        对单个库单独做 BH-FDR（预限定子库口径，见下）
  --within-libs L1 L2 L3  对指定的语义子库合并做 BH-FDR

⚠️ 校正口径（2026-09-15 实测教训）：
  同一份前景/背景，BH-FDR 结果强依赖检验集合大小——
    全库 3794 条 → 最小 FDR 0.0082（1 条过）
    预限定 842 条子库 → 最小 FDR 0.0506（0 条过）
    单库 286 条 → 最小 FDR 0.0219（过）
  若分析前就限定了语义子库，可做库内 FDR，但**必须在报告中显式标注口径**，不可悄悄换。
"""
import argparse, json, os, sys
import urllib.request

import numpy as np
import pandas as pd
from scipy.stats import hypergeom

ENRICHR = 'https://maayanlab.cloud/Enrichr/geneSetLibrary?mode=text&libraryName='
UA = {'User-Agent': 'Mozilla/5.0'}          # 必带 UA


def download_library(name, cache_dir='.'):
    """下载 Enrichr 库；不存在时返回 None（不抛异常，见坑 2）"""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f'{name}.txt')
    if not os.path.exists(path):
        url = ENRICHR + name
        raw = urllib.request.urlopen(
            urllib.request.Request(url, headers=UA), timeout=60).read()
        # 坑 2：库名拼错 → 返回 404 HTML 且 urlopen 不抛异常
        if raw[:4] == b'<!do':
            print(f'[ERR] {name}: 404（库名不存在）', file=sys.stderr)
            return None
        with open(path, 'wb') as f:
            f.write(raw)
    sets = {}
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        if not line:
            continue
        parts = line.split('\t')                 # Term \t \t GENE1 \t GENE2 ...
        term = parts[0].strip()
        genes = {g.strip().upper() for g in parts[1:] if g.strip()}   # 坑 1：统一大写
        if term and genes:
            sets[term] = genes
    if not sets:
        print(f'[ERR] {name}: 解析出 0 个基因集', file=sys.stderr)
        return None
    return sets


def bh_fdr(p):
    p = np.asarray(p, dtype=float)
    o = np.argsort(p)
    m = len(p)
    q = np.empty(m)
    prev = 1.0
    for i in range(m - 1, -1, -1):
        idx = o[i]
        prev = min(prev, p[idx] * m / (i + 1))
        q[idx] = min(prev, 1.0)
    return q


def read_set(path, col=None):
    """读基因列表：CSV（取 col 列）或每行一个基因的纯文本"""
    if path.endswith('.csv') or path.endswith('.tsv'):
        sep = ',' if path.endswith('.csv') else '\t'
        df = pd.read_csv(path, sep=sep)
        ser = df[col] if col and col in df.columns else df.iloc[:, 0]
    else:
        ser = pd.read_csv(path, header=None).iloc[:, 0]
    return {str(s).strip().upper() for s in ser.dropna() if str(s).strip()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--foreground', required=True)
    ap.add_argument('--fg-col', default=None)
    ap.add_argument('--background', required=True)
    ap.add_argument('--bg-col', default=None)
    ap.add_argument('--libraries', nargs='+', required=True)
    ap.add_argument('--out', default='enrichment.csv')
    ap.add_argument('--stats', default='enrichment_stats.json')
    ap.add_argument('--cache-dir', default='.')
    ap.add_argument('--within-lib', default=None, help='对该库单独做 BH-FDR（预限定口径）')
    ap.add_argument('--within-libs', nargs='*', default=None, help='对这些库合并做 BH-FDR')
    ap.add_argument('--min-set-size', type=int, default=5)
    a = ap.parse_args()

    fg = read_set(a.foreground, a.fg_col)
    bg = read_set(a.background, a.bg_col)
    N = len(bg)
    K = len(fg & bg)
    print(f'[输入] 前景 {len(fg)} | 背景 {N} | 前景∩背景 K={K}')
    if K == 0:
        sys.exit('[FATAL] 前景与背景交集为 0 —— 检查基因名大小写/列名（坑 1）')

    rows = []
    for lib in a.libraries:
        sets = download_library(lib, a.cache_dir)
        if sets is None:
            continue
        print(f'[库] {lib}: {len(sets)} 个基因集')
        for term, genes in sets.items():
            g = genes & bg
            n = len(g)
            if n < a.min_set_size:
                continue
            k = len(g & fg)
            p = 1.0 if k == 0 else hypergeom.sf(k - 1, N, n, K)
            exp = K * n / N
            rows.append(dict(library=lib, term=term, set_n=n, hits=k,
                             expected=round(exp, 4),
                             fold=(k / exp if exp > 0 else np.nan), p=p))
    E = pd.DataFrame(rows)
    if E.empty:
        sys.exit('[FATAL] 无有效检验（检查库名/最小集大小）')

    E['fdr'] = np.nan
    if a.within_lib:
        sub = E.library == a.within_lib
        E.loc[sub, 'fdr'] = bh_fdr(E.loc[sub, 'p'].values)
    elif a.within_libs:
        sub = E.library.isin(a.within_libs)
        E.loc[sub, 'fdr'] = bh_fdr(E.loc[sub, 'p'].values)
    else:
        E['fdr'] = bh_fdr(E.p.values)

    E = E.sort_values(['fdr', 'p'])
    E.to_csv(a.out, index=False)
    print(f'\n→ {a.out}（{len(E)} 条，口径={"库内:"+a.within_lib if a.within_lib else "全库"}）')
    print(E.head(15).to_string(index=False))

    stats = dict(n_fg=len(fg), n_bg=N, K=K, n_tested=int(len(E)),
                 n_p05=int((E.p < 0.05).sum()), n_fdr05=int((E.fdr < 0.05).sum()),
                 min_p=float(E.p.min()), min_fdr=float(E.fdr.min()),
                 top=E.head(5)[['library', 'term', 'hits', 'fold', 'p', 'fdr']].to_dict('records'))
    with open(a.stats, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)
    print('\n' + json.dumps(stats, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
