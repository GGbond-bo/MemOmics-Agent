---
name: image-ocr-text-extraction
category: productivity
description: >-
  Extract text from uploaded images when the active LLM has no native vision
  (e.g. deepseek-v4-flash) or vision_analyze is unavailable. RapidOCR-based,
  fully offline, Chinese+English. Use when user uploads a screenshot/table/
  figure caption and asks "能识图吗" / "can you read this image".
trigger:
  when:
    - User uploads an image and the active model has no vision capability
    - User asks "能识图吗" / "能不能看这个图" / "read this screenshot"
    - vision_analyze is documented but NOT exposed in the session tool list
---

# Image OCR Text Extraction (Vision-Less Fallback)

## When to use

- Active model is text-only (e.g. deepseek-v4-flash) → cannot "see" images natively
- `vision_analyze` is mentioned in docs but NOT exposed in the current tool list
- User uploads a screenshot containing text: tables, figure captions, PPT pages,
  marker lists, code snippets

**Honesty rule**: state plainly that you cannot interpret graphics/heatmaps/photos —
OCR extracts text only. For image content (UMAP, dotplot, microscopy), suggest a
vision-capable model or ask the user to describe the content.

## Recipe (verified 2026-07-31, Windows / MemOmics)

1. **Locate the upload** — try in order:
   - `MEMOMICS_HOME/webui/uploads/` (verified location for this deployment)
   - The user message usually contains `/uploads/<timestamp>_<hash>.png`
   - Fall back to search_files for the filename / recent PNG
2. **Check image properties** (optional sanity check):
   ```python
   from PIL import Image
   im = Image.open(path); print(im.size, im.mode)
   ```
3. **OCR with RapidOCR** (preferred — ONNX models ship inside the wheel, ~15MB,
   no big model download, works offline, Chinese+English):
   ```python
   from rapidocr_onnxruntime import RapidOCR
   engine = RapidOCR()
   result, _ = engine(str(path))
   for box, text, score in result:
       print(text, float(score))
   ```
   - `score` may come back as a string → coerce with `float()`.
   - Install: `pip install rapidocr_onnxruntime` (pulls onnxruntime + opencv).
   - On machines with multiple Pythons (python3=3.12, pip→3.13 mismatch), locate the
     env that has it via `pip show rapidocr_onnxruntime` or search site-packages,
     then call that env's python explicitly.

## What NOT to do

- **Do NOT use easyocr on slow networks**: it downloads a ~100MB detection model on
  first run and hangs on limited bandwidth. RapidOCR avoids this entirely.
- **Do NOT fight Windows.Media.Ocr via PowerShell**: WinRT interop is painful and
  unreliable from MSYS bash; skip it.
- **Do NOT claim to have "seen" the image** — only claim OCR'd text.

## Output style

- If the image is a screenshot of your own earlier output, say so explicitly
  (e.g. "this is the 创新点 column of my previous answer") to build continuity.
- Present OCR'd text in a structured table matching the source layout.

## Pitfalls

- Uploads may live under `webui/uploads/` not `work/` — check both.
- RapidOCR can return None for non-image files — verify the file is an image first.
- OCR ≠ understanding: for figure interpretation you still need vision or a user description.
