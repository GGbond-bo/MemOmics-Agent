#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verify_output_validity.py — 产出有效性四问校验器（可反复直接跑，不依赖具体项目代码）

用法
----
# 1) SCENIC 产出预设（regulon 基因命中率 + AUCell 非零占比）
python verify_output_validity.py --mode scenic --scenic-dir results/<sid>/data/scenic

# 2) 通用矩阵/结果表预设（非零占比 / 唯一值 / 维度 / ID 命中率）
python verify_output_validity.py --mode table --table results/x.csv \
       --id-col target --ref-ids data/genes.txt

# 3) 纯 ID 交集
python verify_output_validity.py --mode ids --id-col TF --ref-ids input_ids.txt --table out.csv

退出码：0 = 全部通过；1 = 有断言失败（不要继续下游，不要汇报"分析完成"）。
设计原则：每条检查都必须**算出一个数字**并打印，失败即 raise —— 不要用肉眼"看起来还行"放过。
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys

import numpy as np
import pandas as pd


def _ok(msg):
    print(f"  ✅ {msg}")


def _bad(msg):
    print(f"  ❌ {msg}")


# ---------------------------------------------------------------- 通用检查

def check_id_overlap(result_ids, input_ids, threshold=0.9, label="ID 命中率"):
    """结果的 ID 命名体系是否与输入同源（HGNC vs ENSEMBL / 版本号后缀 / 大小写）"""
    r, i = set(map(str, result_ids)), set(map(str, input_ids))
    hit = len(r & i) / max(1, len(r))
    ( _ok if hit >= threshold else _bad )(
        f"{label} = {hit:.3f}（{len(r & i)}/{len(r)}，阈值 {threshold}）")
    return hit >= threshold, hit


def check_matrix_numeric(values, label="数值分布", min_nonzero=0.5, max_na_frac=0.1):
    """是不是全 0 / 全 NA / 全同一个值 —— 「算得低」和「根本没算」是两回事"""
    a = np.asarray(values, dtype=float)
    nz = float((a > 0).mean())
    na = float(np.isnan(a).mean())
    nuniq = int(pd.Series(a.ravel()).nunique(dropna=True))
    good = (nz >= min_nonzero) and (na <= max_na_frac) and (nuniq > 1)
    ( _ok if good else _bad )(
        f"{label}: 非零占比={nz*100:.1f}%（阈值 {min_nonzero*100:.0f}%）| NA={na*100:.1f}%"
        f"（上限 {max_na_frac*100:.0f}%）| 唯一值={nuniq} | min/max={np.nanmin(a):.4g}/{np.nanmax(a):.4g}")
    return good


def check_single_char_contamination(series, label="单字符污染"):
    """静默 bug 的招牌症状：字符串被逐字符迭代 → 结果里出现 '['、'('、\"'\" 这类单字符条目"""
    s = pd.Series(series).astype(str)
    bad = s.str.len().le(1) & s.ne("")
    frac = float(bad.mean())
    ( _ok if frac == 0 else _bad )(
        f"{label}: 长度≤1 的条目 {int(bad.sum())}/{len(s)}（{frac*100:.1f}%）"
        + (f"，示例={list(s[bad].unique()[:8])}" if frac else ""))
    return frac == 0


def check_shape(df, expect_rows=None, expect_cols=None, label="维度"):
    ok = True
    msgs = [f"shape={df.shape}"]
    if expect_rows is not None and df.shape[0] != expect_rows:
        ok = False; msgs.append(f"行数应为 {expect_rows}")
    if expect_cols is not None and df.shape[1] != expect_cols:
        ok = False; msgs.append(f"列数应为 {expect_cols}")
    if not df.index.is_unique:
        ok = False; msgs.append("索引有重复")
    ( _ok if ok else _bad )(f"{label}: " + " | ".join(msgs))
    return ok


# ---------------------------------------------------------------- SCENIC 预设

def check_scenic(scenic_dir, expr_genes_file=None, min_hit=0.9, min_nonzero=0.5):
    """pySCENIC 产出有效性：
       ① regulons 的基因是不是真 HGNC（不是字符串被逐字符拆开的产物）
       ② AUCell 矩阵非零占比
       ③ regulons.csv 的 target 列无单字符污染
    """
    results = []
    reg_pkl = os.path.join(scenic_dir, "regulons.pkl")
    if os.path.exists(reg_pkl):
        print(f"[1/3] regulons.pkl（{reg_pkl}）")
        with open(reg_pkl, "rb") as f:
            regulons = pickle.load(f)
        print(f"  regulon 数 = {len(regulons)}")
        r0 = regulons[0]
        print(f"  示例 {r0.name}: genes[:8]={list(r0.genes)[:8]}")
        results.append(check_single_char_contamination(
            [g for r in regulons for g in r.genes], "regulon 基因"))
        if expr_genes_file is None:
            cand = os.path.join(scenic_dir, "gene_subset_hvg_tf.txt")
            expr_genes_file = cand if os.path.exists(cand) else None
        if expr_genes_file:
            ref = [l.strip() for l in open(expr_genes_file, encoding="utf-8") if l.strip()]
            r, i = set(g for reg in regulons for g in reg.genes), set(ref)
            hit = len(r & i) / max(1, len(r))
            ( _ok if hit >= min_hit else _bad )(
                f"regulon 基因 ∩ 表达矩阵 = {hit:.3f}（阈值 {min_hit}）—— "
                "低于阈值说明 TargetGenes 被字符串化，见 references/prune2df-targetgenes-stringification.md")
            results.append(hit >= min_hit)
        else:
            print("  ⚠️ 未找到 gene_subset_hvg_tf.txt，跳过命中率检查（请用 --expr-genes 指定）")
    else:
        _bad(f"缺少 {reg_pkl}")

    auc_path = os.path.join(scenic_dir, "aucell_matrix.csv")
    if os.path.exists(auc_path):
        print(f"[2/3] aucell_matrix.csv")
        auc = pd.read_csv(auc_path, index_col=0)
        results.append(check_matrix_numeric(auc.values, "AUCell 活性矩阵",
                                            min_nonzero=min_nonzero))
    else:
        _bad(f"缺少 {auc_path}")

    reg_csv = os.path.join(scenic_dir, "regulons.csv")
    if os.path.exists(reg_csv):
        print("[3/3] regulons.csv")
        rc = pd.read_csv(reg_csv)
        tcol = "target" if "target" in rc.columns else rc.columns[-2]
        results.append(check_single_char_contamination(rc[tcol], f"{tcol} 列"))
    return all(results)


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["scenic", "table", "ids"], required=True)
    ap.add_argument("--scenic-dir")
    ap.add_argument("--table")
    ap.add_argument("--id-col")
    ap.add_argument("--ref-ids")
    ap.add_argument("--expr-genes")
    ap.add_argument("--min-hit", type=float, default=0.9)
    ap.add_argument("--min-nonzero", type=float, default=0.5)
    a = ap.parse_args()

    print("=" * 62)
    print(f"产出有效性校验 mode={a.mode}")
    print("=" * 62)
    if a.mode == "scenic":
        ok = check_scenic(a.scenic_dir, a.expr_genes, a.min_hit, a.min_nonzero)
    else:
        df = pd.read_csv(a.table)
        checks = [check_shape(df)]
        if a.id_col and a.ref_ids:
            ref = [l.strip() for l in open(a.ref_ids, encoding="utf-8") if l.strip()]
            checks.append(check_id_overlap(df[a.id_col], ref, a.min_hit)[0])
            checks.append(check_single_char_contamination(df[a.id_col], f"{a.id_col} 列"))
        if a.mode == "table":
            num = df.select_dtypes(include=[np.number])
            if num.shape[1]:
                checks.append(check_matrix_numeric(num.values, "数值列",
                                                   min_nonzero=a.min_nonzero))
        ok = all(checks)

    print("=" * 62)
    print("结论:", "✅ 产出有效，可进下游" if ok else
          "❌ 产出无效/可疑 —— 不许进下游、不许汇报分析完成（先按归因决策树定位）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())