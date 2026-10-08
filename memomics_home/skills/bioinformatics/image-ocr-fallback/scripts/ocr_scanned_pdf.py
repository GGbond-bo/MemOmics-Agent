# -*- coding: utf-8 -*-
"""整册扫描版 PDF → 文本（RapidOCR + PyMuPDF，离线，无需 tesseract 二进制）

用法（在 MemOmics 里优先走持久内核，避免冷启动）：
    execute_python(code="exec(open(r'<此文件路径>', encoding='utf-8').read())")
或改 SRC/OUT 后由 skills/image-ocr-fallback 直接调用。

要点：
- 先判文字层：有文字层就不必 OCR（省时且更准）。
- 200 dpi 足够；实测 ≈10 s/页（26 页 263 s）。
- 逐页 print 进度，便于判断是否还在跑 / 估算剩余时间。
- 结果落盘 txt，再 read_file 分段读，别把整册文本灌进上下文。
- ⚠️ 表格/多栏页 OCR 后会串行错位，格式类细节须回原件核对。
"""
import os
import time

import pymupdf
from rapidocr_onnxruntime import RapidOCR

SRC = r"D:\path\to\scanned.pdf"
OUT = r"E:\MemOmics-Agent\results\<sid>\data\scanned_ocr.txt"
DPI = 200

doc = pymupdf.open(SRC)

# 1) 文字层探测：任取前 5 页，全为空才判定为扫描版
probe = [len(doc[i].get_text().strip()) for i in range(min(5, doc.page_count))]
print(f"pages={doc.page_count} text_layer_chars(first5)={probe}", flush=True)
if any(probe):
    print("检测到文字层 → 直接抽文本，无需 OCR", flush=True)
    txt = "\n".join(f"\n===== PAGE {i+1} =====\n{pg.get_text()}" for i, pg in enumerate(doc))
    open(OUT, "w", encoding="utf-8").write(txt)
    print("SAVED:", OUT, os.path.getsize(OUT), "bytes")
    raise SystemExit(0)

# 2) 扫描版：逐页渲染 + OCR
ocr = RapidOCR()
parts, t0 = [], time.time()
for i, page in enumerate(doc):
    pix = page.get_pixmap(dpi=DPI)
    res, _ = ocr(pix.tobytes("png"))
    page_txt = "\n".join(r[1] for r in (res or []))   # r = [box, text, conf]
    parts.append(f"\n===== PAGE {i+1} =====\n{page_txt}")
    print(f"page {i+1}/{doc.page_count} lines={len(res or [])} chars={len(page_txt)} "
          f"elapsed={time.time()-t0:.0f}s", flush=True)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write("".join(parts))
print("SAVED:", OUT, os.path.getsize(OUT), "bytes; total", round(time.time() - t0), "s")
