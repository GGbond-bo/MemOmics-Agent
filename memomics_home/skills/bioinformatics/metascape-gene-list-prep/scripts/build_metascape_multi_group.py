# -*- coding: utf-8 -*-
"""
build_metascape_multi_group.py — 多比较组工作簿 → 每组一张 Metascape 输入表

适用：一个 xlsx 里有 N 个 sheet（每 sheet 一个比较组），列为
      gene / celltype / regulation(Up|Down) / coef / se / z / p / fdr / direction / comparison / ...
输出：每个 sheet 一张表，表内「每列 = 一个亚群的一个方向」
      - 列名 up_<celltype> / down_<celltype>，列序 = 亚群字母序，每亚群 up 在前 down 在后
      - 列内按 |coef| 降序（并列按 fdr 升序）取 top-N，不足全取
      - 空列（该亚群该方向无显著基因）不出这一列（只有表头的列会让 Metascape 报噪声）
      - 交付两份：<前缀>.txt（tab、utf-8-sig，直接上传）+ 同名 .xlsx（便于肉眼检查）
      - 外加 列基因数汇总.csv + _自检报告.csv

用法：改下面「配置区」4 个常量即可复用（可选：EXAMPLE_SHEET/EXAMPLE 用于反查用户样板）
"""
import os, csv
import pandas as pd

# ===== 配置区 =====
F     = r"D:/我的下载/DEG_fdr05_coef025_5contrasts_formatted.xlsx"   # 输入工作簿
OUT   = r"D:/肌肉锻炼/DEG_metascape"                                  # 输出目录（用户指定）
TOP_N = 100                                                           # 每列取前 N（不足全取）
PREFIX = "Metascape"                                                  # 文件名前缀
# 可选：把用户贴的样板放进来，自动反查排序口径（键 = "up_<celltype>" / "down_<celltype>"）
EXAMPLE_SHEET = "Aging"
EXAMPLE = {
    # "up_LRP1B+(I)": ["UNC13C", "MCU", ...],
    # "down_LRP1B+(I)": ["FKBP5", "MT-RNR1", ...],
}
# ==================

os.makedirs(OUT, exist_ok=True)
xl = pd.ExcelFile(F)
SHEETS = xl.sheet_names
summary_rows, checks = [], []

for sheet in SHEETS:
    d = pd.read_excel(F, sheet_name=sheet)
    celltypes = sorted(d["celltype"].unique())        # 亚群字母序（文件出现顺序各组不同，必须自己排）
    cmp_name = d["comparison"].iloc[0] if "comparison" in d.columns else ""
    cols = []
    for ct in celltypes:
        for reg, tag in [("Up", "up"), ("Down", "down")]:
            sub = d[(d["celltype"] == ct) & (d["regulation"] == reg)].copy()
            sub["_abs"] = sub["coef"].abs()
            sub = sub.sort_values(["_abs", "fdr"], ascending=[False, True])   # |coef| 降序，并列 fdr 升序
            genes, seen = [], set()
            for g in sub["gene"].astype(str).str.strip():
                if g and g not in seen:                # 保序去重
                    seen.add(g); genes.append(g)
            genes = genes[:TOP_N]
            rec = dict(group=sheet, comparison=cmp_name, column=f"{tag}_{ct}",
                       n_genes=len(genes), n_available=len(sub), capped=len(genes) == TOP_N,
                       top_abs_coef=round(float(sub["_abs"].iloc[0]), 4) if len(sub) else None,
                       min_abs_coef=round(float(sub["_abs"].iloc[-1]), 4) if len(sub) else None)
            if not genes:                              # 空列 → 不出这一列
                rec["note"] = "empty_skipped"; summary_rows.append(rec); continue
            cols.append((f"{tag}_{ct}", genes)); summary_rows.append(rec)

    if not cols:
        print(f"[{sheet}] 无任何可用列，跳过"); continue
    nrow = max(len(g) for _, g in cols)
    matrix = [[g[i] if i < len(g) else "" for _, g in cols] for i in range(nrow)]   # 手工补空对齐

    txt = os.path.join(OUT, f"{PREFIX}_{sheet}_top{TOP_N}.txt")
    with open(txt, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow([c for c, _ in cols]); w.writerows(matrix)

    pd.DataFrame({c: pd.Series(g) for c, g in cols}).to_excel(
        os.path.join(OUT, f"{PREFIX}_{sheet}_top{TOP_N}.xlsx"), index=False)

    # 读回磁盘文件自检（不信内存对象）
    back = pd.read_csv(txt, sep="\t", encoding="utf-8-sig", dtype=str).fillna("")
    ok_head = list(back.columns) == [c for c, _ in cols]
    ok_row2 = not any(v in celltypes for v in back.iloc[0].tolist())      # 第 2 行必须是基因不是表头
    ne = {c: int((back[c].astype(str).str.strip() != "").sum()) for c in back.columns}
    ok_cnt = all(ne[c] == len(g) for c, g in cols)
    checks.append(dict(sheet=sheet, n_cols=len(cols), nrow_back=nrow, header_ok=ok_head,
                       row2_is_genes=ok_row2, counts_match=ok_cnt,
                       empty_cols=[c for c, v in ne.items() if v == 0],
                       dup_cols=[c for c in back.columns
                                 if len(back[c][back[c] != ""]) - back[c][back[c] != ""].nunique() > 0]))
    print(f"[{sheet}] 列={len(cols)} 最长列={nrow} 表头OK={ok_head} 第2行是基因={ok_row2} 基因数吻合={ok_cnt}")

    # 可选：反查用户样板，逐位比对（判定样板是规格还是示意）
    if sheet == EXAMPLE_SHEET and EXAMPLE:
        dd = dict(cols)
        for cname, expect in EXAMPLE.items():
            got = dd.get(cname, [])[:len(expect)]
            hit = sum(1 for a, b in zip(got, expect) if a == b)
            print(f"   反查 {cname}: {hit}/{len(expect)} 逐位一致")
            if hit < len(expect):
                print("      样板:", expect); print("      本次:", got)

pd.DataFrame(summary_rows).to_csv(os.path.join(OUT, f"{PREFIX}_列基因数汇总.csv"),
                                  index=False, encoding="utf-8-sig")
pd.DataFrame(checks).to_csv(os.path.join(OUT, "_自检报告.csv"), index=False, encoding="utf-8-sig")

print(f"\n输出目录 {OUT} | 总列数 {sum(c['n_cols'] for c in checks)}")
for fn in sorted(os.listdir(OUT)):
    print(f"  {fn}  ({os.path.getsize(os.path.join(OUT, fn))} B)")