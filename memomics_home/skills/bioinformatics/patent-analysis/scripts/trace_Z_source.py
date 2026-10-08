#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""trace_Z_source.py —— 数值口径溯源探针（列级 provenance audit）

用途：已知一张「正本」基因级 Z 表（交底书/正文引用），判定它的 Z 到底来自哪个输入文件
（例如两份候选的 tile 级 ageDA 表），**只扫单条染色体**，1-2 分钟出定论，无需全量重跑。

用法示例：
  python trace_Z_source.py \
      --ref   E:/专利/P3_L1_data/v5_substitutability_all.csv \
      --candidate E:/专利/M2/monkey_ageDA_all.csv \
      --candidate E:/专利/monkey_ageDA_continuous.csv \
      --side monkey --ref-col Z_monkey

  自定义坐标/同源文件：
      --feature-table <GCF_xxx_feature_table.txt.gz>   # side=monkey 用
      --human-bed     <human_ortholog_hg38_full.csv>   # side=human 用
      --orthologs     <monkey_human_orthologs_full.csv>
      --chrom NC_088375.1        # 默认取坐标表里第 1 条染色体

判读：某候选文件的「与正本完全一致(round4)比例 = 1.000 且中位绝对差 = 0.0000」→ 它就是真来源；
      其余候选应显示 0.000 / 中位差明显 > 0。

依赖：numpy + 标准库（零 scipy）。
"""
import argparse, csv, gzip, math, os, sys
import numpy as np

# ───────────── 纯 numpy 正态分布（与正本管道一致，零 scipy） ─────────────
_erf_vec = np.frompyfunc(math.erf, 1, 1)


def _erf(x):
    xa = np.asarray(x, dtype=np.float64)
    return _erf_vec(np.atleast_1d(xa)).astype(np.float64)


def _erfinv(y):
    y = np.asarray(y, dtype=np.float64)
    y = np.clip(y, -1 + 1e-300, 1 - 1e-300)
    a = 0.147
    ln = np.log(1 - y * y)
    t = 2.0 / (np.pi * a) + ln / 2.0
    x = np.sign(y) * np.sqrt(np.sqrt(t * t - ln / a) - t)
    for _ in range(6):
        x = x - (_erf(x) - y) / (2.0 / np.sqrt(np.pi) * np.exp(-x * x))
    return x


def norm_ppf(p):
    return np.sqrt(2.0) * _erfinv(2.0 * np.asarray(p, dtype=np.float64) - 1.0)


def stouffer(rp_list):
    """Z_i = sign(r)*Phi^-1(1 - p/2)  →  Z = sum(Z_i)/sqrt(n)   （正本口径）"""
    Zs = np.array([np.sign(r) * norm_ppf(1.0 - max(p, 1e-300) / 2.0) for r, p in rp_list])
    Z = Zs.sum() / math.sqrt(len(Zs))
    return round(float(Z), 4)


# ───────────── 坐标加载 ─────────────
def load_monkey_coords(feature_table_gz):
    genes = {}
    with gzip.open(feature_table_gz, 'rt', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            p = line.rstrip('\n').split('\t')
            if len(p) < 16 or p[0] != 'gene':
                continue
            try:
                chrom, st, en = p[6], int(p[7]), int(p[8])
                gid = str(int(p[15]))
            except (ValueError, IndexError):
                continue
            genes.setdefault(chrom, []).append((st, en, gid))
    for c in genes:
        genes[c].sort()
    return genes


def load_human_coords(human_bed):
    genes = {}
    with open(human_bed, encoding='utf-8') as f:
        rd = csv.reader(f)
        next(rd, None)
        for row in rd:
            try:
                gid, chrom, st, en = row[0], row[1], int(float(row[2])), int(float(row[3]))
            except (ValueError, IndexError):
                continue
            if not chrom.startswith('chr'):
                chrom = 'chr' + chrom
            genes.setdefault(chrom, []).append((st, en, gid))
    for c in genes:
        genes[c].sort()
    return genes


def load_symbol_map(orthologs_csv, side):
    """macaque_gene_id -> human_symbol  /  human_gene_id -> human_symbol"""
    key = 'macaque_gene_id' if side == 'monkey' else 'human_gene_id'
    m = {}
    with open(orthologs_csv, encoding='utf-8') as f:
        rd = csv.DictReader(f)
        for row in rd:
            k = (row.get(key) or '').strip()
            s = (row.get('human_symbol') or '').strip()
            if k and s:
                m[k] = s
    return m


# ───────────── 单染色体扫描（廉价探针核心） ─────────────
def scan_chrom(path, target, cap=3_000_000):
    """只收集 target 染色体的行；chrom 一变立刻 break。坐标一律 int(float(x))。"""
    rows, started = [], False
    with open(path, encoding='utf-8') as f:
        rd = csv.reader(f)
        next(rd, None)
        for i, p in enumerate(rd):
            if i > cap:
                break
            if len(p) < 5:
                continue
            if p[0] == target:
                started = True
                try:
                    rows.append((int(float(p[1])), int(float(p[2])), float(p[3]), float(p[4])))
                except ValueError:
                    continue
            elif started:
                break
    return rows


def anchor(rows, coords, window):
    """tile 中点 ±window 落到基因体 → 归属该基因（与正本管道同判据）"""
    st_ = np.array([g[0] for g in coords])
    en_ = np.array([g[1] for g in coords])
    acc = {}
    for s, e, r, p in rows:
        mid = (s + e) // 2
        lo, hi = mid - window, mid + window
        idx = int(np.searchsorted(st_, hi, side='right') - 1)
        while idx >= 0:
            if en_[idx] < lo:
                break
            if st_[idx] <= hi and en_[idx] >= lo:
                acc.setdefault(coords[idx][2], []).append((r, p))
                break
            idx -= 1
    return acc


def read_ref(ref_csv, ref_col, symbol_col='symbol'):
    ref = {}
    with open(ref_csv, encoding='utf-8') as f:
        rd = csv.DictReader(f)
        if symbol_col not in rd.fieldnames or ref_col not in rd.fieldnames:
            sys.exit(f'!! {ref_csv} 缺少列 {symbol_col} / {ref_col}；实际列={rd.fieldnames}')
        for row in rd:
            ref[row[symbol_col].strip()] = float(row[ref_col])
    return ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ref', required=True, help='正本基因级 Z 表（如 v5_substitutability_all.csv）')
    ap.add_argument('--candidate', action='append', required=True, help='候选 tile 级输入，可多次传')
    ap.add_argument('--side', choices=['monkey', 'human'], default='monkey')
    ap.add_argument('--ref-col', default=None, help='默认 Z_monkey / Z_human（按 --side）')
    ap.add_argument('--symbol-col', default='symbol')
    ap.add_argument('--window', type=int, default=2000)
    ap.add_argument('--cap', type=int, default=3_000_000)
    ap.add_argument('--chrom', default=None)
    ap.add_argument('--feature-table', default=r'E:/专利/P3_L1_data/GCF_037993035.2_T2T-MFA8v1.1_feature_table.txt.gz')
    ap.add_argument('--human-bed', default=r'E:/专利/P3_L1_data/human_ortholog_hg38_full.csv')
    ap.add_argument('--orthologs', default=r'E:/专利/P3_L1_data/monkey_human_orthologs_full.csv')
    a = ap.parse_args()

    ref_col = a.ref_col or ('Z_monkey' if a.side == 'monkey' else 'Z_human')
    coords_all = load_monkey_coords(a.feature_table) if a.side == 'monkey' else load_human_coords(a.human_bed)
    chrom = a.chrom or list(coords_all)[0]
    if chrom not in coords_all:
        sys.exit(f'!! 坐标表里没有染色体 {chrom}；可选前几条={list(coords_all)[:5]}')
    coords = coords_all[chrom]
    print(f'[i] side={a.side} chrom={chrom} genes={len(coords)} window=±{a.window}')

    ref = read_ref(a.ref, ref_col, a.symbol_col)
    print(f'[i] 正本 {os.path.basename(a.ref)} 列={ref_col} n={len(ref)}')

    sym_map = load_symbol_map(a.orthologs, a.side)
    print(f'[i] 同源映射 {len(sym_map)} 条\n')

    print(f'{"候选文件":<52}{"锚定基因":>9}{"可比基因":>9}{"round4一致":>12}{"中位绝对差":>12}')
    print('-' * 96)
    for cand in a.candidate:
        if not os.path.isfile(cand):
            print(f'{os.path.basename(cand):<52}{"MISSING":>9}')
            continue
        rows = scan_chrom(cand, chrom, a.cap)
        acc = anchor(rows, coords, a.window)
        got, diffs = [], []
        for gid, rp in acc.items():
            sym = sym_map.get(gid)
            if sym is None or sym not in ref:
                continue
            got.append((sym, stouffer(rp)))
        for sym, z in got:
            diffs.append(abs(round(z, 4) - round(ref[sym], 4)))
        if not diffs:
            print(f'{os.path.basename(cand):<52}{len(acc):>9}{0:>9}{"—":>12}{"—":>12}')
            continue
        d = np.array(diffs)
        ratio = float((d < 1e-9).mean())
        flag = '  ← ★真来源' if ratio > 0.999 else ''
        print(f'{os.path.basename(cand):<52}{len(acc):>9}{len(d):>9}{ratio:>12.3f}{np.median(d):>12.4f}{flag}')
    print('\n[判读] 一致比例=1.000 且中位差=0.0000 的候选即正本数字的真来源（决定性证据）。')
    print('       全部候选都 <1 → 正本用了第三份输入；去查生成脚本的输入常量（文件名不可信）。')


if __name__ == '__main__':
    main()
