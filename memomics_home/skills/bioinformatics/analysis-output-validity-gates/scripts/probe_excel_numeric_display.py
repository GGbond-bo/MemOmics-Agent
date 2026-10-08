#!/usr/bin/env python
"""探针：报告 xlsx 各 sheet 数值列「在 Excel 里会被显示成什么」。

用途：交付 DEG / 统计表**前**自检 —— 防止 number_format='0.0000' 把 1e-51 量级的 FDR
静默显示成 0（用户打开 Excel 就以为数据坏了）。同时给出精确 0 的格数与最小正值，
便于区分「格式隐藏」与「双精度下溢」（后者 abs(z) 通常 >= 37.5）。

用法:
    python probe_excel_numeric_display.py <xlsx路径> [列名 列名 ...]
    python probe_excel_numeric_display.py D:/我的下载/DEG_fdr05_coef025_5contrasts.xlsx fdr p
"""
import sys

import openpyxl
import pandas as pd


def decimals_of(fmt):
    """'0.0000' -> 4 ; 'General' / '0.00E+00' -> 0（不按定点截断）。"""
    if not isinstance(fmt, str) or not fmt.startswith("0."):
        return 0
    return fmt.split(".")[-1].count("0")


def probe(path, cols=None):
    wb = openpyxl.load_workbook(path, data_only=True)
    xf = pd.ExcelFile(path)
    for sn in xf.sheet_names:
        df = xf.parse(sn)
        ws = wb[sn]
        hdr = [c.value for c in ws[1]]
        print("=== %s (%d 行) ===" % (sn, len(df)))
        for name in (cols or list(df.columns)):
            if name not in df.columns:
                continue
            v = pd.to_numeric(df[name], errors="coerce")
            if v.notna().sum() == 0:
                continue
            fmt = "?"
            if name in hdr:
                c = ws.cell(row=2, column=hdr.index(name) + 1)
                if c.data_type == "n":
                    fmt = c.number_format
            dec = decimals_of(fmt)
            thr = 0.5 * 10 ** (-dec) if dec else None
            disp0 = int((v.abs() < thr).sum()) if thr else 0
            pos = v[v > 0]
            print("  [%s] fmt=%s | 显示成0=%d (%.1f%%) 精确0=%d | min_pos=%.3e med=%.3e max=%.3e"
                  % (name, fmt, disp0, disp0 / len(v) * 100, int((v == 0).sum()),
                     pos.min(), v.median(), v.max()))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    probe(sys.argv[1], sys.argv[2:] or None)