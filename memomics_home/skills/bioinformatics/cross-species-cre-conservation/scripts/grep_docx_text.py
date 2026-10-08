#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
docx 正文/表格取文本 + 关键词计数与上下文打印。

用途：回答"交付件里到底有没有这句话/这个方法/这个数字"——交付件三层扫描
      （正文 md / docx 表格单元格 / 内嵌图像素）中负责 docx 这一层。
      比只 grep md 强的是：docx 的表格单元格文字段落扫描常常拿不到。

用法：
    python grep_docx_text.py <docx或目录> 关键词1 关键词2 ...
    python grep_docx_text.py 交底书_v12.docx 经验贝叶斯 lfdr 五态
    python grep_docx_text.py E:/专利/ --latest 经验贝叶斯      # 只看目录里最新一份 docx

要点（两个必踩的坑，本脚本已内置）：
  ① `~$xxx.docx` 是 Word 打开文件时的锁文件（100+ 字节，不是 zip），
     且它的 mtime 永远最新 ⇒ `sorted(glob("*.docx"))[-1]` 必中它，报
     `zipfile.BadZipFile: File is not a zip file`。必须过滤 `~$` 前缀。
  ② docx 是 zip：正文在 `word/document.xml`，去标签后才能检索。
"""
import os
import re
import sys
import glob
import zipfile


def docx_text(path):
    """返回 docx 全文（含表格单元格），失败返回 None。"""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except zipfile.BadZipFile:
        return None
    xml = re.sub(r"</w:p>", "\n", xml)          # 段落边界换行，保住排版
    txt = re.sub(r"<[^>]+>", "", xml)
    return re.sub(r"\n{3,}", "\n\n", txt)


def pick_docx(target, latest_only=True):
    if os.path.isdir(target):
        cands = [f for f in glob.glob(os.path.join(target, "**", "*.docx"), recursive=True)
                 if not os.path.basename(f).startswith("~$")]   # ← 坑①
        cands.sort(key=os.path.getmtime)
        return cands[-1:] if (latest_only and cands) else cands
    return [target]


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    target, keywords = sys.argv[1], sys.argv[2:]
    ctx = 90
    found_any = False
    for f in pick_docx(target):
        txt = docx_text(f)
        if txt is None:
            print(f"[skip] {os.path.basename(f)} —— 不是有效 zip（Word 锁文件或损坏）")
            continue
        print(f"\n=== {os.path.basename(f)}  (正文字数 {len(txt):,}) ===")
        for kw in keywords:
            c = txt.count(kw)
            flag = "命中" if c else "【零命中】"
            print(f"--- {kw}: {flag} x{c}")
            if c:
                found_any = True
                for i, m in enumerate(re.finditer(re.escape(kw), txt)):
                    if i >= 3:                       # 每词最多 3 处上下文
                        break
                    s, e = max(0, m.start() - ctx), min(len(txt), m.end() + ctx)
                    print(f"    …{txt[s:e]}…")
    print("\n[summary] " + ("至少一个关键词命中" if found_any else "全部零命中"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
