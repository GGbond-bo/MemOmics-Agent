# Nature Journal HTML Extraction (PDF Fallback)

When `download_pdf` fails for Nature/Science/Cell series papers (no PMC full text, Unpaywall fails), extract content directly from the publisher HTML page.

## Verified Command (Nature Medicine 2026-08-27)

```bash
curl -sL -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  "https://www.nature.com/articles/<DOI>" | python3 -c "
import sys, re, html
content = sys.stdin.read()
content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
text = re.sub(r'<[^>]+>', ' ', content)
text = html.unescape(text)
text = re.sub(r'\s+', ' ', text).strip()
methods_idx = text.find('Methods')
if methods_idx > 0:
    print(text[methods_idx:methods_idx+8000])
else:
    print(text[:15000])
"
```

## Key Facts

- User-Agent header is mandatory — Nature blocks curl without it
- No JavaScript needed — Nature serves static HTML with full article text
- Content location: Abstract ~0-3000 chars, Methods/Results ~6000-15000 chars, References ~60000+ chars
- Figure descriptions are embedded in the HTML text (not just images)
- Supplementary Information is on separate pages (not in main article HTML)
- Zenodo/GEO links are in the references section or Data Availability statement
- Open Access articles have full text accessible

## Limitations

- Extended Data Figures: image URLs need separate parsing from img tags
- Supplementary tables: separate page, same curl technique works
- Some articles behind paywall: only abstract + methods summary visible

## Use Case: Quick Paper Investigation

When user asks to investigate a paper for specific data (ATAC/RNA/cell types):
1. Try download_pdf first
2. If fails → curl HTML fallback
3. Extract relevant sections (Methods for data types, Results for cell types/markers)
4. Return structured fact list, not full translation
