---
name: image-ocr-fallback
description: >-
  从「读不了」的文档里取文字：上传的图片/截图、扫描版 PDF、旧版 Word 97-2003 二进制
  `.doc`（read_file 直接拒读）。图片/扫描页走 RapidOCR（rapidocr_onnxruntime，ONNX
  模型随 pip wheel 打包，零联网）；旧版 `.doc` 走 antiword；`.docx` 走 read_file。
  含整册扫描 PDF 的批量 OCR 循环（scripts/ocr_scanned_pdf.py）。
  用于：用户上传图问"能识图吗"/"read this image"、PDF 抽文字返回空、用户给一批
  学校/单位下发的 .doc 或扫描件原件要求整理标注。
category: General Utility
trigger:
  when:
    - User uploads image and asks "能识图吗" / "can you read this image" / "看看这个图"
    - PDF text extraction returns empty (scanned/image-based PDF)
    - Model lacks vision_analyze tool and has no native vision
    - read_file 报 "Cannot read binary file '...doc'"（旧版 .doc 原件）
    - 用户给一批下发的 .doc / 扫描版 PDF 原件，要求整理、标注、后续按格式产出
---

# Image OCR Fallback (No-Vision Models)

## When to Use

- User uploads a screenshot/table/figure-caption image and expects the text read back
- Current session model has no native vision (e.g. deepseek-v4-flash) and no
  `vision_analyze` tool is exposed
- PDF is scanned/image-based → pymupdf text extraction returns empty

## ⚠️ Honest Capability Boundary (tell the user)

OCR extracts **text only** (tables, captions, PPT text pages, code screenshots).
It CANNOT interpret figures, photos, heatmaps, UMAPs, or graphs.
- If the image is a chart/photo → suggest a vision-capable model session or ask
  the user to describe the content.
- If the image is text → RapidOCR below will restore most content.

## Verified Pipeline (2026-07, Windows + miniconda3)

### 1. Install

```bash
# CRITICAL: pip may install to a different python than the one you run.
# On this machine: `pip` → D:\Python (3.13), system python → Python312,
# but the package landed in miniconda3. Use the interpreter that has it:
/e/miniconda3/python.exe -m pip install rapidocr_onnxruntime -q
```

### 2. Run

```bash
/e/miniconda3/python.exe -c "
from rapidocr_onnxruntime import RapidOCR
ocr = RapidOCR()
result, elapse = ocr('E:/path/to/image.png')
if result:
    for item in result:
        box, text, conf = item[0], item[1], item[2]
        x = int(box[0][0]); y = int(box[0][1])
        print(f'[{x},{y}] conf={conf} text={text}')
else:
    print('NO TEXT FOUND - 可能是纯图形图')
"
```

Pitfalls:
- `conf` is a **str** — do NOT `%.2f` format it (ValueError). Use `conf={conf}` or str().
- Locate uploaded files first: webui uploads live under
  `E:/MemOmics-Agent/webui/uploads/<timestamp>_<name>.png` — find with
  `find E:/MemOmics-Agent -name "<filename>"`.

## 整册扫描 PDF 批量 OCR（实测 2026-09，26 页 / 263 s）

先判有没有文字层——**有文字层就不要 OCR**：

```python
import pymupdf
d = pymupdf.open(src)
print(d.page_count, [len(d[i].get_text().strip()) for i in range(min(5, d.page_count))])
# 全 0 → 扫描版，走下面的循环
```

批量循环（脚本见 `scripts/ocr_scanned_pdf.py`，可直接 `exec(open(...).read())`）：

```python
import pymupdf
from rapidocr_onnxruntime import RapidOCR

doc, ocr = pymupdf.open(src), RapidOCR()
parts = []
for i, page in enumerate(doc):
    pix = page.get_pixmap(dpi=200)              # 200 dpi 足够；再高只增耗时
    res, _ = ocr(pix.tobytes("png"))
    parts.append(f"\n===== PAGE {i+1} =====\n" + "\n".join(r[1] for r in (res or [])))
    print(f"page {i+1}/{doc.page_count} chars={len(parts[-1])}", flush=True)   # 逐页报进度
open(out_txt, "w", encoding="utf-8").write("".join(parts))
```

要点：
- **逐页 print 进度**：整册 OCR 要几分钟，没有进度输出看起来像卡死（也方便外部判断是否还在跑）。
- 实测节拍 **≈10 s/页**（26 页 263 s），可按页数预估时间再决定同步还是后台。
- 结果先**落盘 txt**，再 `read_file` 分段读——不要把整册 OCR 文本灌进上下文。
- **表格/多栏页会 OCR 串行错位**：标准、规范、附件表这类内容 OCR 后**结构不可信**，
  可以看大意，**不能当权威表格引用**；涉及格式/数值细节回原件核对，或在交付物里注明"待核原件"。

## 旧版 `.doc`（Word 97-2003 二进制）→ antiword

`read_file` 对 `.doc` 报 `Cannot read binary file '...doc'` 是**预期行为**（不是文件损坏），别重试，
换 antiword（git-bash 自带，`/mingw64/bin/antiword`，免安装）：

```bash
for f in *.doc; do
  antiword -w 0 -m UTF-8.txt "$f" > "${f%.doc}.txt"
done
```

- **`-w 0` 必须加**：否则按 79 字符自动折行，中文正文被拦腰断行，读回来无法引用。
- **`-m UTF-8.txt`**：中文映射表，保证 UTF-8 输出。
- 表格用 `|` 分隔，**合并单元格会错位**（封面版式表的竖排文字被拆到每行左侧）——看结构可以，数值需核对原件。
- 断言"文件不存在"之前先 `ls` 目录：用户给的路径常带多余引号，或实际文件名与所说不一致；
  顺带能发现配套附件（封面格式/声明页/国标/名称表），一并抽取。

## 抽取之后：整理成「标注版」

用户说"整理出来，并做好标记"时，交付物不是原始 OCR 文本，而是**带标记的速查**：
适用对象（`【硕】/【博】/【通】`）、约束强度（`🔴硬性` / `⚪可选`）、来源条款号 + 章节骨架 + 自查清单。
学位论文/校内规范这类场景 → `cn-degree-thesis-writing` skill。

## Failure Chain (do not re-try these)

| Tool | Why it fails here | Verdict |
|------|-------------------|:---:|
| `pytesseract` | 依赖 tesseract 二进制且要配 PATH/语言包；本机实装在 `C:\Program Files\Tesseract-OCR\`（不在 PATH）——能用但不免配置，中文识别还需 chi_sim 语言包 | ⚠️ 需配置 |
| `easyocr` | First run downloads ~100MB detection model; on slow networks hangs at "Downloading detection model..." then times out (400s) | ❌ |
| PowerShell WinRT OCR (`Windows.Media.Ocr`) | Async WinRT interop from bash/PowerShell is flaky; GetAwaiter calls fail on COM objects | ❌ skip |
| **RapidOCR** (`rapidocr_onnxruntime`) | ONNX models **bundled inside the pip wheel** — zero network download, works offline | ✅ |

## Output Convention

Return OCR text as a readable block, with coordinates/confidence when useful.
If the image is a screenshot of previous chat content (user testing ability),
state what the image contains and confirm whether it matches expected content.

## Common Issues

| Error | Cause | Fix |
|-------|-------|-----|
| ModuleNotFoundError: easyocr/rapidocr | installed under different python | find via `pip show <pkg> \| grep Location`, use that interpreter |
| ValueError: Unknown format code 'f' | conf is str | `conf={conf}` not `conf={conf:.2f}` |
| easyocr hangs at model download | slow network, ~100MB model | don't wait — switch to RapidOCR |
| OCR returns nothing | pure-graphics image (chart/photo) | tell user: text-only tool; need vision model or description |
