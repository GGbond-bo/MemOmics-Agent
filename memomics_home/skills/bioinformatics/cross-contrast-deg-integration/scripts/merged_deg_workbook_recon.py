#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
陌生 DEG 工作簿「结构侦察」探针（只读，不改数据、不出图）。

用途：用户丢来一张已算好的 DEG 工作簿（xlsx / 多 sheet），说「看看这表里有什么」时，
先跑本脚本 → 一次拿到结构 / 规模 / 显著性 / 口径一致率 / 跨亚群交集 / TOP10，

用法：
    python merged_deg_workbook_recon.py <DEG工作簿.xlsx> [--summary-sheet ALL_merged] [--celltype-col celltype]
"""
import argparse
import sys

import numpy as np
import pandas as pd


def load(path, summary_name="all_merged"):
    xl = pd.ExcelFile(path)
    sheets = list(xl.sheet_names)
    summary = [s for s in sheets if s.strip().lower() == summary_name.lower()]
    subs = [s for s in sheets if s not in summary]
    frames = {s: xl.parse(s) for s in sheets}
    return frames, sheets, subs, (summary[0] if summary else None)


def main(path, summary_name="all_merged", ct_col="celltype"):
    frames, sheets, subs, summary = load(path, summary_name)

    print(f"FILE   : {path}")
    print(f"SHEETS : {len(sheets)} → {sheets}")
    print(f"汇总表 : {summary}   亚群表({len(subs)}): {subs}")

    # ---- 1) 元信息：列 / 对比 / 方向约定 / 方法 / 校正因子 --------------------
    ref = frames[summary or sheets[0]]
    print(f"\nCOLS ({len(ref.columns)}): {list(ref.columns)}")
    for c in ["comparison", "direction", "method", "nRUV_used", ct_col]:
        if c in ref.columns:
            u = list(pd.Series(ref[c].dropna().unique())[:10])
            print(f"  {c:12s} nunique={ref[c].nunique():>4}  unique[:10]={u}")

    # ---- 2) 每 sheet 规模 + 显著性（C 与 D 两套口径都要看） -------------------
    rows = []
    for s in sheets:
        d = frames[s]
        sig = d["fdr"] < 0.05
        rows.append(dict(
            sheet=s, rows=len(d), genes=d["gene"].nunique(),
            n_cells=int(d["n_cells"].max()) if "n_cells" in d else np.nan,
            sig_fdr05=int(sig.sum()),
            up=int((sig & (d["coef"] > 0)).sum()),
            dn=int((sig & (d["coef"] < 0)).sum()),
            sig_fdrD05=int((d["fdr_D"] < 0.05).sum()) if "fdr_D" in d else -1,
        ))
    t = pd.DataFrame(rows)
    print("\n== 规模与显著性 ==")
    print(t.to_string(index=False))

    # 陷阱① 汇总表 = 各亚群拼接？排除汇总表再求和！
    if summary:
        ssum = int(t.loc[t["sheet"] != summary, "rows"].sum())
        same = ssum == int(t.loc[t["sheet"] == summary, "rows"].iloc[0])
        print(f"\n[陷阱①] 各亚群行数之和={ssum}  vs  {summary} 行数={int(t.loc[t['sheet']==summary,'rows'].iloc[0])}"
              f"  → {'拼接关系成立 ✅' if same else '不成立，需人工核 ⚠️'}")
    # 陷阱② 行数 ≠ 基因数
    if summary:
        print(f"[陷阱②] {summary}: {len(ref)} 行只对应 {ref['gene'].nunique()} 个唯一基因"
              f" → 各亚群基因集不同，行数不能读成基因数")
    # 陷阱③ n_cells 是否常量列
    if "n_cells" in ref.columns and ct_col in ref.columns:
        g = ref.groupby(ct_col)["n_cells"].nunique()
        print(f"[陷阱③] n_cells 在每个 {ct_col} 内的唯一值数 = {sorted(set(g.tolist()))}"
              f" → {'每亚群一个常量（细胞类型总细胞数，非分组细胞数）' if set(g.tolist())=={1} else '组内有变化，需细看'}")

    # ---- 3) 口径陷阱：C vs D 组件符号一致率 --------------------------------
    if "coef_D" in ref.columns:
        sgn = {}
        for s in sheets:
            d = frames[s]
            sgn[s] = round(float(((d["coef"] * d["coef_D"]) > 0).mean()), 3)
        print("\n== [口径陷阱] coef(C 表达量) vs coef_D(D 检出率) 符号一致率 ==")
        print("  " + "  ".join(f"{k}={v}" for k, v in sgn.items()))
        print("  ⚠️ 一致率显著<1（本例全表 0.363、亚群 0.15~0.65）→ 两套口径方向不同；")
        print("     确认「报告口径是哪一套」之前，不得用未确认的那套写上调/下调结论。")
        print(f"  C 极差: [{ref['coef'].min():.2f}, {ref['coef'].max():.2f}]   "
              f"D 极差: [{ref['coef_D'].min():.2f}, {ref['coef_D'].max():.2f}]  (尺度不同属正常)")

    # ---- 4) 跨亚群交集（必须用原始基因集，不能用行数） ----------------------
    sig_sets = {s: set(frames[s].query("fdr<0.05")["gene"]) for s in subs}
    if sig_sets:
        common = set.intersection(*sig_sets.values())
        print(f"\n== 跨 {len(subs)} 个亚群共同显著（FDR<0.05，集合交集）: {len(common)} 个 ==")
        print("  前40:", sorted(common)[:40])
        uniq = {s: len(v - set().union(*[x for k, x in sig_sets.items() if k != s]))
                for s, v in sig_sets.items()}
        print("  各亚群独有显著基因数（悬殊=功效/混杂差异，需核）:", uniq)

    # ---- 5) 每亚群 TOP10（按主口径 fdr，显式标注口径） ---------------------
    print("\n== TOP10（主口径 C：fdr 升序；括号内 coef，+ = 后一组高） ==")
    for s in subs:
        d = frames[s].sort_values("fdr").head(10)
        print(f"  {s}: " + ", ".join(f"{g}({c:+.2f})" for g, c in zip(d["gene"], d["coef"])))

    return t


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--summary-sheet", default="ALL_merged")
    ap.add_argument("--celltype-col", default="celltype")
    a = ap.parse_args()
    main(a.path, a.summary_sheet, a.celltype_col)
    sys.exit(0)