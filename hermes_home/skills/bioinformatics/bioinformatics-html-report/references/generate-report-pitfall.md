# Pitfall: generate_report Tool vs Rich Embedded Reports

**Problem**: The MemOmics `generate_report` tool outputs ~40KB framework-only HTML with
external image links. It does NOT embed images or data tables. Multi-figure bioinformatics
reports for secretome, multi-omics, or any multi-phase analysis should be 2-8 MB
self-contained HTML files with base64-embedded figures.

**Observed behavior** (hES-4CL-EB session, 2026-07-20):
- `generate_report` → 39KB file with text framework + external image links
- User complained "为什么只有39kb?"
- Manual construction with `write_file` + base64-encoded PNGs → 2.2MB complete report

**Fix**: For reports with 10+ figures:
1. Build HTML manually using `write_file`
2. Base64-encode all PNG figures (`encode_image()` from ReportBuilder)
3. Embed all data tables inline
4. Include full analysis scripts in collapsible `<details>` blocks
5. Use the dark-theme template from `proteomics-secretome-analysis` skill

**Validation**: Check file size after write — if <100KB, images are not embedded.
A proper secretome report with 10+ figures MUST be >1MB.

**When to use `generate_report`**: Only for simple single-figure summaries.
Any multi-phase bioinformatics analysis with figure panels MUST use manual HTML construction.
