#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""xlsx 兜底读取器 —— 绕开 openpyxl 的图片/关系表检查，直接解 xlsx 的 zip/XML。

用途：openpyxl 报 KeyError: "There is no item named 'xl/drawings/drawing1.xml'"（关系表损坏），
      或 read_only=True 静默返回空表（max_row=1）时，用本脚本仍能读到全部单元格数据。

用法：
    python read_xlsx_manual.py <文件路径> [sheet序号(默认1)] [起始行(默认1)] [打印行数(默认20)]
    python read_xlsx_manual.py "E:/骨骼肌锻炼/pathway_score.xlsx" 1 1 25
    python read_xlsx_manual.py <文件路径> --summary        # 只打印结构概览（不做行内容打印）

输出：每个 sheet 的维度概览 + 指定行号区间的单元格内容。
     行号为 Excel 原生行号（可能不连续，空行不写进 XML）。
"""
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def colidx(ref):
    """列字母 -> 序号: A->1, B->2, Z->26, AA->27"""
    s = ''.join(ch for ch in ref if ch.isalpha())
    n = 0
    for ch in s:
        n = n * 26 + ord(ch) - 64
    return n


def read_xlsx_manual(path):
    """返回 {sheet_xml_name: {row_idx: {col_letter: value}}}"""
    z = zipfile.ZipFile(path)
    ss = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(NS + 'si'):
            ss.append(''.join(t.text or '' for t in si.iter(NS + 't')))
    out = {}
    for sh in sorted(n for n in z.namelist() if n.startswith('xl/worksheets/sheet')):
        rows = {}
        for row in ET.fromstring(z.read(sh)).iter(NS + 'row'):
            ri = int(row.get('r'))
            cells = {}
            for c in row.findall(NS + 'c'):
                col = ''.join(ch for ch in c.get('r') if ch.isalpha())
                t = c.get('t')
                v = c.find(NS + 'v')
                isel = c.find(NS + 'is')
                if t == 's' and v is not None:
                    val = ss[int(v.text)]
                elif t == 'inlineStr' and isel is not None:
                    val = ''.join(x.text or '' for x in isel.iter(NS + 't'))
                elif v is not None:
                    val = v.text
                else:
                    val = None
                cells[col] = val
            rows[ri] = cells
        out[sh] = rows
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    summary_only = '--summary' in sys.argv
    nums = [a for a in sys.argv[2:] if not a.startswith('--')]
    sheet_no = int(nums[0]) if len(nums) > 0 else 1
    start = int(nums[1]) if len(nums) > 1 else 1
    nlines = int(nums[2]) if len(nums) > 2 else 20

    sheets = read_xlsx_manual(path)
    print('sheets(内部XML名): %s' % list(sheets.keys()))
    for name, rows in sheets.items():
        occupied = sorted(rows.keys())
        maxcol = 0
        for r in rows.values():
            for col in r:
                maxcol = max(maxcol, colidx(col))
        print('\n=== %s ===' % name)
        print(' 有数据的行号: %d 个, 范围 %s .. %s' % (
            len(occupied), occupied[0] if occupied else None, occupied[-1] if occupied else None))
        print(' 最大列序号: %d' % maxcol)
        if summary_only:
            continue
        for ri in occupied:
            if ri < start or ri >= start + nlines:
                continue
            cells = rows[ri]
            vals = ['%s=%s' % (k, str(v)[:60]) for k, v in sorted(cells.items(), key=lambda kv: colidx(kv[0]))
                    if v not in (None, '')]
            print(' r%-4d %s' % (ri, vals[:8]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
