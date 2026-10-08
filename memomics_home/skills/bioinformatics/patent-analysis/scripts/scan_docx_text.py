# -*- coding: utf-8 -*-
"""
scan_docx_text.py — 交付件（.docx）正文关键词核查探针

用途：docx 是 zip 包，grep / search_files 都拿不到内容；核验「某句原文是否真在交付件里」
      「旧口径数字是否零残留」必须提段落 + 表格单元格后按关键词扫。

一次跑完全部检查，不要为每一项检查再写一个小脚本（触发系统循环检测）。

用法：
    python scan_docx_text.py <交付件.docx> --keys 24.3 单侧 双侧 10,000 200次 --show-all
    python scan_docx_text.py <交付件.docx>            # 只打印段数/表数/图数概况

依赖：python-docx
    ⚠️ 若持久内核（execute_python）报 ModuleNotFoundError: No module named 'docx'，
       改用系统 python 执行本脚本（terminal: "<系统python路径>" scan_docx_text.py ...），
       不要为此在项目里重复装包。

输出：
    - 段落数 / 表数 / 内嵌图数（word/media/*）
    - 每个关键词在【段落 P#】与【表格 T#R#】中的命中原文
    - 关键词汇总（命中数 0 = 该词零残留 / 该句不在交付件中）
"""
import argparse
import io
import os
import sys
import zipfile


def main():
    ap = argparse.ArgumentParser(description="docx 正文关键词核查")
    ap.add_argument("docx", help=".docx 路径")
    ap.add_argument("--keys", nargs="*", default=[], help="要核的关键词（空格分隔）")
    ap.add_argument("--width", type=int, default=300, help="每条命中截断宽度（默认 300）")
    ap.add_argument("--show-all", action="store_true", help="打印全部段落（无关键词过滤）")
    args = ap.parse_args()

    if not os.path.exists(args.docx):
        sys.exit("文件不存在: %s" % args.docx)

    try:
        from docx import Document
    except ImportError:
        sys.exit("缺少 python-docx。请在系统 python 下运行本脚本（持久内核可能未装 docx）。")

    doc = Document(args.docx)
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    tables = doc.tables

    # 内嵌图（word/media/*）—— 数量应与「附图说明」条数一致
    media = []
    try:
        with zipfile.ZipFile(args.docx) as z:
            media = [n for n in z.namelist() if n.startswith("word/media/")]
    except Exception as e:  # noqa: BLE001
        print("[warn] 读 word/media 失败: %s" % e)

    print("=" * 72)
    print("file      : %s" % args.docx)
    print("size      : %d bytes" % os.path.getsize(args.docx))
    print("段落数    : %d" % len(paras))
    print("表数      : %d" % len(tables))
    print("内嵌图数  : %d  (%s)" % (len(media), ", ".join(sorted(media)) or "-"))
    print("=" * 72)

    if args.show_all or not args.keys:
        for i, t in enumerate(paras):
            print("[P%d] %s" % (i, t[: args.width]))
        for ti, tb in enumerate(tables):
            print("\n--- 表 T%d（%d 行 × %d 列）---" % (ti, len(tb.rows), len(tb.columns)))
            for ri, row in enumerate(tb.rows):
                line = " | ".join(c.text.strip() for c in row.cells)
                print("[T%d R%d] %s" % (ti, ri, line[: args.width]))
        return

    summary = {}
    print("\n=== 段落命中 ===")
    for i, t in enumerate(paras):
        hit = [k for k in args.keys if k in t]
        if hit:
            for k in hit:
                summary[k] = summary.get(k, 0) + 1
            print("[P%d] (%s) %s" % (i, ",".join(hit), t[: args.width]))

    print("\n=== 表格命中 ===")
    for ti, tb in enumerate(tables):
        for ri, row in enumerate(tb.rows):
            line = " | ".join(c.text.strip() for c in row.cells)
            hit = [k for k in args.keys if k in line]
            if hit:
                for k in hit:
                    summary[k] = summary.get(k, 0) + 1
                print("[T%d R%d] (%s) %s" % (ti, ri, ",".join(hit), line[: args.width]))

    print("\n=== 关键词汇总（0 = 该词不在交付件 / 已零残留）===")
    for k in args.keys:
        print("  %-20s %d" % (k, summary.get(k, 0)))


if __name__ == "__main__":
    main()
