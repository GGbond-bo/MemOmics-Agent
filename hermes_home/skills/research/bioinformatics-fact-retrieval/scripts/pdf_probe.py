#!/usr/bin/env python
"""pdf_probe.py — PDF 全文抽取 + 关键词命中探针（一次调用看清「哪些说法有原文支撑」）

用途：用户带着一个前提/术语来求确认（「是不是就是 X？」）时，不要凭印象表态 ——
先把全文抽成 txt，再对「用户前提里的词 + 论文自己的核心词」逐个做命中探针。
⛔ 命中次数本身就是证据：某术语全文只出现 1 次、且落在讨论区的无关短语里，
就说明它根本不是论文的架构概念。这是把「不完全是」说到可复核的关键一步。

用法
----
  # 1) 只抽取全文（落盘，后续反复 grep 不必重抽）
  python pdf_probe.py "E:/文献/AI/agent/literature/Biomni.pdf" \
      --out results/<sid>/data/Biomni_fulltext.txt

  # 2) 抽取 + 命中探针（计数按降序打印，每个词给 n 个上下文窗口）
  python pdf_probe.py "E:/文献/AI/agent/literature/Biomni.pdf" \
      --out results/<sid>/data/Biomni_fulltext.txt \
      --kw "2,500" "knowledge base" "skill" "action space" "retrieval" \
      --w 1200 --n 2

输出
----
  页数 / 字符数 / 全文落盘路径
  ---- 命中计数（降序）----
  'skill' 1 · 'retrieval' 27 · ...
  ---- 命中上下文（逐字引用用）----
  [skill] @33045 --- ...原文...
  [skill] @33045 --- ...原文...
  [=] 'knowledge base' 在文件中不存在...

实现说明
--------
- 抽取优先 PyMuPDF(fitz)，缺失时自动退 pypdf；两者都无则报错并提示
  `pip install pymupdf`。
- 只打印**有限个**上下文窗口（默认每词 2 个、每个 1200 字符），避免把整篇正文
  灌进上下文浪费 token —— 需要更多时调 --n / --w，或直接 read_file 落盘的 txt。
- `--out` 目录自动创建。
"""
from __future__ import annotations

import argparse
import os
import re
import sys


def extract_text(pdf_path: str) -> str:
    """PDF -> 全文文本。优先 pymupdf，退 pypdf。"""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        parts = [f"=== PAGE {i + 1} ===\n" + pg.get_text() for i, pg in enumerate(doc)]
        print(f"[ok] pymupdf 抽取 {len(doc)} 页")
        return "\n".join(parts)
    except ImportError:
        pass
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        parts = [pg.extract_text() or "" for pg in reader.pages]
        print(f"[ok] pypdf 抽取 {len(reader.pages)} 页")
        return "\n".join(parts)
    except ImportError:
        sys.exit(
            "[err] 需要 PDF 解析库：pip install pymupdf   （或 pip install pypdf）\n"
            "      装到项目内 venv，别装系统 Python。"
        )


def probe(txt: str, keywords: list[str], window: int, n: int) -> None:
    counts: list[tuple[str, int]] = []
    hits: dict[str, list[re.Match]] = {}
    for kw in keywords:
        found = list(re.finditer(re.escape(kw), txt))
        counts.append((kw, len(found)))
        hits[kw] = found

    print("\n---- 命中计数（降序；命中次数本身就是证据）----")
    for kw, c in sorted(counts, key=lambda x: -x[1]):
        flag = "  <-- 全文未出现" if c == 0 else ""
        print(f"  {kw!r}: {c}{flag}")

    print("\n---- 命中上下文（逐字引用用）----")
    for kw, _ in sorted(counts, key=lambda x: -x[1]):
        found = hits[kw]
        if not found:
            print(f"[=] {kw!r} 在文件中不存在 —— 用户前提里的这个词没有原文支撑\n")
            continue
        for m in found[:n]:
            s = max(0, m.start() - window)
            e = min(len(txt), m.end() + window)
            snippet = txt[s:e].replace("\n", " ")
            print(f"[{kw}] @{m.start()} --- {snippet}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="PDF 全文抽取 + 关键词命中探针")
    ap.add_argument("pdf", help="PDF 路径")
    ap.add_argument("--out", default="", help="全文落盘路径（强烈建议给，后续反复 grep 免重抽）")
    ap.add_argument("--kw", nargs="*", default=[], help="要探针的关键词（用户前提里的词 + 论文核心词）")
    ap.add_argument("--w", type=int, default=1200, help="上下文窗口字符数（默认 1200）")
    ap.add_argument("--n", type=int, default=2, help="每个关键词打印几个窗口（默认 2）")
    args = ap.parse_args()

    if not os.path.exists(args.pdf):
        sys.exit(f"[err] 文件不存在：{args.pdf}")

    txt = extract_text(args.pdf)
    print(f"[ok] 字符数 {len(txt)}")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(txt)
        print(f"[ok] 全文已落盘：{args.out}")

    if args.kw:
        probe(txt, args.kw, args.w, args.n)
    else:
        print("[i] 未给 --kw，只做了抽取。建议至少探针用户前提里的词。")

    print(
        "\n[i] 引用时标明层级：本脚本产出属全文层（正文明文），可引数字/图注；\n"
        "    若只用本脚本的计数而未读正文明文，则仍属检索层，需自报「未读正文」。"
    )


if __name__ == "__main__":
    main()