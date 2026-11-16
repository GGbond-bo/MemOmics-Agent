# -*- coding: utf-8 -*-
"""多篇论文语料 Step 1：批量 PDF → 纯文本 + 解析健康检查。

用法:
    python pdf_corpus_extract.py <src_dir> <out_dir> [--glob "*.pdf"]

输出:
    <out_dir>/<key>.txt          每篇一个纯文本（逐页 join，页间插 ===PAGE_BREAK===）
    <out_dir>/_extract_report.json  页数 / 非空页数 / 字符数 / 首屏标题线索

    非空页数 ≈ 页数        -> 原生数字排版，解析正常
    非空页数明显 < 页数    -> 有解析残页，换 get_text("blocks") 或 pdftotext 复核
    字符数/页 < 500        -> 扫描件，改走 OCR
"""
import argparse
import glob
import json
import os
import re

import fitz  # PyMuPDF


def slug(name: str) -> str:
    """从文件名生成稳定短 key（去扩展名、非法字符转下划线、截断）。"""
    base = os.path.splitext(os.path.basename(name))[0]
    base = re.sub(r"[^\w\u4e00-\u9fff]+", "_", base).strip("_")
    return base[:80] or "doc"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--glob", default="*.pdf")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    paths = sorted(glob.glob(os.path.join(args.src_dir, args.glob)))
    if not paths:
        print(f"[ERR] no file matched: {args.src_dir}/{args.glob}")
        return

    report = {}
    for path in paths:
        key = slug(path)
        doc = fitz.open(path)
        pages = [pg.get_text("text") for pg in doc]
        doc.close()

        full = "\n\n===PAGE_BREAK===\n\n".join(pages)
        outp = os.path.join(args.out_dir, key + ".txt")
        with open(outp, "w", encoding="utf-8") as fh:
            fh.write(full)

        nonempty = sum(1 for p in pages if len(p.strip()) > 50)
        chars = len(full)
        per_page = chars / max(len(pages), 1)
        if nonempty < len(pages) * 0.9 or per_page < 500:
            flag = "  <-- CHECK (残页/扫描件嫌疑)"
        else:
            flag = ""

        report[key] = {
            "file": os.path.basename(path),
            "bytes": os.path.getsize(path),
            "pages": len(pages),
            "pages_nonempty": nonempty,
            "chars": chars,
            "chars_per_page": round(per_page),
            "txt": outp,
            "head": re.sub(r"\s+", " ", pages[0][:400]) if pages else "",
        }
        print(
            f"[OK] {key}: {len(pages)} pages, {nonempty} nonempty, "
            f"{chars} chars ({round(per_page)}/page){flag}"
        )

    with open(os.path.join(args.out_dir, "_extract_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"\nOUT: {args.out_dir}")


if __name__ == "__main__":
    main()