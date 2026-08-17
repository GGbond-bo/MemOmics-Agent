---
name: image-ocr-fallback
description: >-
  Extract text from uploaded images / screenshots / scanned PDF pages when the
  current model has no native vision. Verified offline pipeline: RapidOCR
  (rapidocr_onnxruntime, ONNX models bundled in the pip wheel). Covers the
  failure chain of pytesseract (needs tesseract binary) and easyocr (needs
  ~100MB network model download). Use when user uploads an image asking
  "能识图吗" / "read this image" / scanned-PDF text extraction returns empty.
category: General Utility
trigger:
  when:
    - User uploads image and asks "能识图吗" / "can you read this image" / "看看这个图"
    - PDF text extraction returns empty (scanned/image-based PDF)
    - Model lacks vision_analyze tool and has no native vision
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
/e/USER_MINICONDA/python.exe -m pip install rapidocr_onnxruntime -q
```

### 2. Run

```bash
/e/USER_MINICONDA/python.exe -c "
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
  `MEMOMICS_HOME/webui/uploads/<timestamp>_<name>.png` — find with
  `find MEMOMICS_HOME -name "<filename>"`.

## Failure Chain (do not re-try these)

| Tool | Why it fails here | Verdict |
|------|-------------------|:---:|
| `pytesseract` | Requires tesseract binary; `which tesseract` is empty on this machine | ❌ |
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
