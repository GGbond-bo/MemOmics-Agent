# CAJ/KDH Format Conversion Recipe

> CNKI (中国知网) proprietary format → readable text. No CAJViewer needed.

## Problem

CNKI thesis/patent files come in `.caj` extension but internally may be **KDH format** (encrypted PDF-like). Neither pymupdf nor standard PDF tools can open them directly.

## Solution: caj2pdf + skip mutool

### Setup (one-time)

```bash
git clone https://github.com/caj2pdf/caj2pdf.git
cd caj2pdf
pip install PyPDF2
```

**Location on this machine:** `E:/tmp/caj2pdf/`

### Conversion Recipe

The key insight: `caj2pdf` writes a valid intermediate `.tmp` file **before** calling `mutool` for xref repair. The `.tmp` file is already readable by pymupdf — skip the mutool step entirely.

```python
import sys, os
sys.path.insert(0, 'E:/tmp/caj2pdf')
from cajparser import KDH_PASSPHRASE
import fitz  # pymupdf

def kdh_to_text(filepath):
    """Convert a KDH-format .caj file to readable text."""
    with open(filepath, 'rb') as f:
        origin = f.read()
    
    # Decrypt KDH (XOR with passphrase, skip 254-byte header)
    origin = origin[254:]
    output = []
    keycursor = 0
    for b in origin:
        output.append(b ^ KDH_PASSPHRASE[keycursor])
        keycursor += 1
        if keycursor >= len(KDH_PASSPHRASE):
            keycursor = 0
    output = bytes(output)
    
    # Trim after %%EOF marker
    eofpos = output.rfind(b'%%EOF')
    if eofpos < 0:
        raise Exception('%%EOF not found — not a valid KDH file')
    output = output[:eofpos + 5]
    
    # Write temp PDF and read with pymupdf
    tmp = filepath + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(output)
    
    doc = fitz.open(tmp)
    text = '\n'.join([doc[i].get_text() for i in range(doc.page_count)])
    doc.close()
    os.remove(tmp)
    return text
```

### Bulk Conversion

```python
import os, fitz

for fname in os.listdir('E:/专利'):
    if not fname.endswith('.caj'):
        continue
    full_text = kdh_to_text(os.path.join('E:/专利', fname))
    out = fname.replace('.caj', '.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(full_text)
```

### File Type Detection

```bash
cd E:/tmp/caj2pdf
python caj2pdf show "file.caj"
# Output: "Type: KDH" or "Type: CAJ" or "Type: HN"
```

- **KDH**: Use the recipe above (decrypt→read with pymupdf)
- **CAJ**: `caj2pdf convert file.caj -o output.pdf` (no mutool needed)
- **HN**: Needs compiled C libraries (`libjbigdec.so`, `libjbig2codec.so`) — not supported on Windows without Docker/WSL

### Pitfalls

| Pitfall | Fix |
|---------|-----|
| FileNotFoundError for mutool | Skip mutool — rename `.tmp` directly or just read `.tmp` with pymupdf |
| `%%EOF` not found | File may be HN format or corrupted — try `caj2pdf show` first |
| execute_code sandbox doesn't have pymupdf | Use `execute_python` instead (has full conda env) |
| Chinese text garbled | The decrypt+read method preserves GBK encoding correctly |
