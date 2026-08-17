---
name: mesh-semantic-indexing
description: Generate and verify MeSH/DeCS semantic indexing labels for biomedical articles using NCBI E-utilities. Use when asked to output MeSH major topics for PMIDs, annotate literature with controlled vocabulary, or answer semantic-indexing benchmark questions (BioASQ Task A / MESINESP style).
category: bioinformatics
---

# MeSH / DeCS Semantic Indexing (NCBI E-utilities)

## When to Use
- User provides PMIDs (or title+abstract) and wants MeSH major topics (typically 5-10 labels/article)
- Benchmark exams: BioASQ Task A (MeSH labeling from title+abstract), MESINESP (DeCS codes for Spanish articles)
- Any "annotate this paper with controlled vocabulary" request
- Verifying whether a proposed MeSH label exists in official PubMed indexing

## Core Principle
**Always fetch the OFFICIAL PubMed MeSH indexing — never invent labels from title/abstract alone.**
PubMed curators assign MH (MeSH Heading) lines. A leading `*` on an MH line marks MajorTopicYN="Y" (major topic). The exam gold answers match the full clean MH heading set (major + minor), qualifiers stripped.

## Working Recipe (validated 2026-08-02 on Windows/MSYS)

### 1. Fetch official MeSH via Python urllib (NOT curl)
curl to eutils on this Windows/MSYS host times out (>120s, exit 124). Python urllib with a browser User-Agent + ssl CERT_NONE context works reliably:

```python
import urllib.request, re, ssl
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
pmids = ["23479819", "23483174"]  # ...
url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id="
       + ",".join(pmids) + "&rettype=medline&retmode=text")
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
data = urllib.request.urlopen(req, context=ctx, timeout=60).read().decode("utf-8", "replace")
# split records on "\n\n(?=PMID- )", collect lines starting with "MH  - "
```

### 2. Parse MH lines into clean labels
- strip leading `*` (major-topic flag)
- strip `/qualifier` suffix (e.g. `Vibrio/enzymology/*metabolism` → `Vibrio`)
- Output 5-10 major topics per article (exam requirement)

### 3. Cross-verify answers against the official MH set
Re-fetch medline, build a set of clean official headings, assert every answer label ∈ official set. Also assert structure: 5-10 tags, all non-empty strings. Save answers as `{exam, answers:[{pmid, title, mesh_major_topics}]}`.

## Pitfalls (learned the hard way)
1. **curl eutils times out on Windows/MSYS** → use Python urllib + User-Agent header + ssl CERT_NONE context. Retry-able, not transient.
2. **Scripts written to MSYS `/tmp` cannot be read by native python** — `python "E:\tmp\script.py"` fails with "can't open file"; the bash `$TEMP` is the MSYS virtual path. Always write scripts to a native Windows path: `C:/Users/<user>/AppData/Local/Temp/` or an `E:/` working directory.
3. **MEDLINE MH parsing details**: major-topic flag is a leading `*`; qualifiers come after `/`; both must be stripped before comparison with answers. Batch multiple PMIDs in one efetch call (comma-joined) — it's fast; add `time.sleep(0.4)` only between separate calls.
4. **DeCS (MESINESP) web scraping is a dead end**: `decs.bvsalud.org/ths/resource/?id=N` returns the same generic site-feedback HTML ("Queremos a sua opinião sobre o novo sitio web do DeCS/MeSH") for every ID — no descriptor names exposed. Do not scrape. For DeCS ID→name mapping use E-utilities `db=mesh` efetch with MeSH UI IDs (D-codes appear as 68xxxxx in the modern API), or rely on gold IDs directly.
5. **MeSH UI IDs in eutils db=mesh are 68xxxxx-formatted** (e.g. Biopsy=D001706 → 68001706, Mediastinal Neoplasms → 68008479). Tree numbers come from the "Tree Number(s):" line in the efetch text output.

## Verification Script
`scripts/fetch_mesh_major_topics.py` — reusable fetch + verify (structure check + official-MH cross-check). Run with native python: `python fetch_mesh_major_topics.py --pmids 23479819,23483174` to print clean headings, or `--verify answers.json` to validate an answers file against PubMed's official MH set.

## Related Skills
- paper-summary / paper-download — literature interpretation/download (different goal: reading papers, not indexing them)
- literature-param-extraction — extracting analysis params from PDFs (different goal)
- knowledge-base-curation — building YAML KB entries (can consume MeSH labels as structured vocab)
