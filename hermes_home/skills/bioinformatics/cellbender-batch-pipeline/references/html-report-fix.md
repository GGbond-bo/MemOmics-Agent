# CellBender HTML Report — Bug #4 Cross-Drive Fix

## Bug

`os.replace()` fails when temp directory and output directory are on different drives (Windows).

```
Error: [WinError 17] The system cannot move the file to a different disk drive
```

## Root Cause

CellBender's `report.py` generates HTML in `%TEMP%` (typically C: drive), then tries `os.replace()` to move it to the output directory (e.g., F: drive). `os.replace()` requires source and destination to be on the same filesystem on Windows.

## Fix

Replace `os.replace()` with `shutil.move()` in the following locations in CellBender's `report.py`:

```python
# Before (broken):
os.replace(temp_html_path, final_html_path)

# After (fixed):
import shutil
shutil.move(temp_html_path, final_html_path)
```

Alternatively, generate the HTML directly in a temp directory on the same drive as the output.

## Verification (2026-07-29, 6 brain samples)

Patched report.py, then manually generated 6-sample summary HTML with embedded base64 charts:
- `PROJECT_DATA_DIR/summary/CellBender_Report.html` (~500 KB, all images inline)

## Notes

- This is a known CellBender issue on Windows when using separate drives
- The PDF report is unaffected (uses different code path)
- If `--expected-cells` is not passed to CellBender, the built-in report may fail — use manual HTML generation as fallback
