---
id: "skill_89a81caf3c33403c8707b27722481796"
name: "pdf-report-generation"
display-name: "PDF Report Generation"
short-description: "Generate professional, Phylo-branded PDF reports from scientific analysis results using ReportLab."
category: Visualization
visibility: "internal"
keywords: "PDF, report, ReportLab, scientific, figures, tables, charts"
version: "1.0"
last-updated: "April 2026"
description: >
when_to_use: "[pdf-report-generation] PDF报告生成：分析结果/图表/表格→LaTeX/HTML→PDF报告→自动排版→可重复生成"
  Generate professional, Phylo-branded PDF reports from scientific analysis results
  using ReportLab. Use this skill whenever the agent needs to produce a PDF report,
  analysis summary, or any standalone PDF deliverable. Triggers include: user requests
  a "PDF report", "generate a report as PDF", "create a PDF summary", or when the
  analysis is complex enough that a structured multi-page document with embedded
  charts and tables is the right deliverable format. Also use when the task involves
  generating publication-quality figures embedded in a report, or when results need
  to be shared outside the Biomni platform in a polished, self-contained format.
  Do NOT use for: simple markdown reports viewed in-app, extracting text from existing
  PDFs (use pdfplumber directly), or merging/splitting existing PDFs (use pypdf).
compatibility:
  pre_installed:
    - reportlab
    - pypdf
---
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。以下规则覆盖所有 Biomni 默认行为。

### 规则1: 拿到数据 → 必须调 search_knowledge
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 7步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. check_env 检查环境
3. rail_review(pre) 前置审查
4. source/import 预写脚本（禁止 inline 代码）
5. terminal 执行（分步执行，禁止 && 连接多步骤）
6. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
7. rail_review(post) 后置审查
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 resolution, n_pcs, min_features, FDR threshold等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式（多角色对抗 v3）：
  - 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
  - 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
  - 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
  - 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
  - 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
  - 辩论结果自动归档到 results/.../log/debate_*.json
- **不确定的参数就辩论**，不要自己拍脑袋

### 规则5: 执行后审查

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

  - **图片检查**：
    - 图有没有生成？没生成 → **强制重新执行**
    - 图片是否空白（全白/全黑/全单一色）？空白 → **强制重新出图**
    - 图片是否有 NA/缺失值（>10% 像素是 NA）？有 NA → **强制重新出图**
    - 图片大小是否过小（<5KB）？过小 → **强制重新出图**
    - 图片数量是否足够？（每步至少 1 张图，关键步骤至少 2-3 张）
  - **代码质量检查**：
    - 代码行数是否合理？（过短可能偷懒，过长可能未分段）
    - 代码是否有注释？
    - 代码是否分段执行（禁止 && 连接多步骤）？
  - **结果合理性**：
    - 数值范围是否合理？
    - 跟知识库对应吗？
  - **参数和结论辩论**：
    - 有参数的选择 → **必须调 debate_analysis 辩论**
    - 有结论输出 → **必须调 debate_analysis 辩论**
    - 不通过 → 修复重跑
    - 通过 → **必须调 skill_evolution(action="record_run")** 记录成功经验（skill_name/script_name/species/tissue/direction/params_used/result_summary/quality_score/notes） → 创建目录存储(figures/results/scripts/data) → 下一步
    - **不通过 → 修复后重跑 → 成功后调 skill_evolution(action="record_run")**；如果是脚本报错 → **调 skill_evolution(action="record_error")** 记录根因+修复方案

### 规则6: 结果存储结构
```
results/<模块>/<方法>/
  ├── scripts/     # 分析脚本
  ├── figures/     # PNG + SVG 图表
  ├── data/        # RDS/H5AD 中间数据
  └── results/     # CSV/TSV 结果表
```


### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

| 时机 | action | 调 | 不调 |
|------|--------|----|------|
| 脚本报错+你分析根因+修复后 | record_error | ✅ R/Python 脚本报错，你找到根因并修复 | ❌ trivial 错误（打字错误、路径不存在） |
| 脚本成功+结果通过 rail_review | record_success | ✅ 分析步骤完成，图生成，审查通过 | ❌ 闲聊/方法咨询/非分析任务 |
| 修复后脚本验证稳定有效 | update_script | ✅ 同一错误修复了，重跑成功 | ❌ 只改参数没改脚本；未验证就更新 |

---



# Biomni PDF Report Generation

## When to generate a PDF (vs. markdown)

Markdown is fine when the user will read results inside the Biomni UI. But markdown
falls apart the moment someone downloads it or shares it — figures are decoupled,
there's no page layout, no branding. Generate a PDF when:

- The user explicitly asks for a PDF or "report"
- Results need to be shared with collaborators, PIs, or stakeholders outside Biomni
- The analysis has multiple sections with embedded figures and tables
- The deliverable needs to look polished and self-contained (grant supplements, publications)

## Phylo Brand Identity

These colors and fonts define the Phylo visual language. Use them consistently
across all PDF reports so outputs feel like they come from a coherent product,
not a random script.

### Color Palette

The Phylo visual identity uses a restrained, scientific palette. Gold is the
primary accent — used for table headers, dividers, and subtle highlights.
The overall feel should be clean white pages with minimal color.

```python
from reportlab.lib.colors import HexColor

# Brand colors (full palette, available when needed)
PHYLO_BLACK     = HexColor("#000000")     # Headings, primary text
PHYLO_WARM_GRAY = HexColor("#ECE9E2")     # Backgrounds, alternating table rows
PHYLO_OFF_WHITE = HexColor("#FAF9F3")     # Page background, light sections
PHYLO_LIME      = HexColor("#E9ED4C")     # Chart color (use sparingly)
PHYLO_ORANGE    = HexColor("#FF9400")     # Warnings, secondary chart color
PHYLO_GREEN     = HexColor("#75A025")     # Success states, positive indicators
PHYLO_PINK      = HexColor("#FD9BED")     # Tertiary accent (use sparingly)
PHYLO_BLUE      = HexColor("#0279EE")     # Links, chart color

# Derived / functional — these drive the report styling
PHYLO_GOLD       = HexColor("#D4A04A")    # PRIMARY ACCENT: table headers, dividers, highlights
HEADING_COLOR    = HexColor("#111111")    # Headings (near-black)
BODY_TEXT         = HexColor("#2C2A26")    # Body text (warm dark)
MUTED_TEXT        = HexColor("#8A8378")    # Captions, footnotes, secondary text
CAPTION_TEXT      = MUTED_TEXT             # Alias
TABLE_HEADER_BG  = PHYLO_GOLD            # Table header background (gold)
TABLE_HEADER_FG  = HexColor("#FFFFFF")    # Table header text (white)
TABLE_ALT_ROW    = HexColor("#F9F7F3")   # Alternating row shading (very light warm)
TABLE_BORDER     = HexColor("#D5CFC5")   # Table grid lines (warm gray)
DIVIDER_COLOR    = PHYLO_GOLD            # Section dividers (gold)
CALLOUT_BG       = PHYLO_OFF_WHITE       # Callout box background (warm off-white)
CALLOUT_BORDER   = PHYLO_GOLD            # Callout box border (gold)
LINK_COLOR       = HexColor("#0563C1")   # Hyperlinks
```

### Chart Color Sequence

When plotting multiple series, cycle through these in order. They are chosen
to be distinguishable, colorblind-friendly in most combinations, and consistent
with the Phylo palette:

```python
CHART_COLORS = [
    PHYLO_GOLD,       # #D4A04A  — primary accent
    PHYLO_BLUE,       # #0279EE
    PHYLO_GREEN,      # #75A025
    PHYLO_ORANGE,     # #FF9400
    PHYLO_PINK,       # #FD9BED
    PHYLO_BLACK,      # #000000
]
```

### Typography

ReportLab's built-in fonts are limited. Use Helvetica as the base (clean,
universally available in PDF readers). Never rely on system fonts — they
won't embed and will render differently on other machines.

```python
FONT_HEADING  = "Helvetica-Bold"
FONT_BODY     = "Helvetica"
FONT_ITALIC   = "Helvetica-Oblique"
FONT_MONO     = "Courier"        # Code snippets, gene names, file paths
```

## Architecture: How ReportLab Platypus Works

ReportLab has two levels:
1. **Canvas** — low-level: you position every element with x,y coordinates.
   Use for page backgrounds, headers, footers, and decorative elements.
2. **Platypus** — high-level: you build a list of "flowable" objects (paragraphs,
   tables, charts, spacers) and the engine handles pagination, text reflow,
   and page breaks automatically.

The pattern is: use Platypus for content, canvas callbacks for chrome.

```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

doc = SimpleDocTemplate(output_path, pagesize=letter,
                        topMargin=52, bottomMargin=52,
                        leftMargin=60, rightMargin=60)
story = []   # list of flowables — this IS the report

# Add content as flowables
story.append(Paragraph("Title", styles["Title"]))
story.append(Table(data, colWidths=[...]))
story.append(PageBreak())

# Canvas callback for page chrome (same for all pages)
doc.build(story, onFirstPage=page_header_footer, onLaterPages=page_header_footer)
```

## Standard Report Template

Every Biomni PDF report should follow this structure. Not every section is
required — adapt to the analysis, but maintain the ordering.

### Page 1: Title Page (No Cover)

Reports open directly with content — no full-bleed colored cover page. The first
page uses the same header/footer as all other pages. Title content is added as
flowables at the top of the story:

```python
# Title block — large bold heading, gold subtitle, muted attribution
story.append(Spacer(1, 40))
story.append(Paragraph("Report Title Here", styles["ReportTitle"]))
story.append(Paragraph("Subtitle or Analysis Type", styles["Subtitle"]))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "<i>Generated by Biomni  |  " + date_str + "</i>", styles["Attribution"]))
story.append(Spacer(1, 24))
```

Title styles:
```python
styles.add(ParagraphStyle(name="ReportTitle", fontName="Helvetica-Bold",
    fontSize=26, textColor=HEADING_COLOR, spaceBefore=0, spaceAfter=6,
    leading=32))

styles.add(ParagraphStyle(name="Subtitle", fontName="Helvetica",
    fontSize=11, textColor=PHYLO_GOLD, spaceAfter=4))

styles.add(ParagraphStyle(name="Attribution", fontName="Helvetica-Oblique",
    fontSize=10, textColor=MUTED_TEXT, spaceAfter=8))
```

This keeps the first page clean and scientific. The report title is large but
black-on-white. The gold subtitle provides brand color without being flashy.

### All Pages: Header & Footer

Every page (including the first) gets a consistent header and footer via
canvas callback. The header shows the report title in muted text with a
gold underline. The footer has a thin warm-gray line and centered muted text.

**Do not put "PHYLO" or any explicit branding in the header.** These reports
are meant to be used by users directly, so the header should be the report
title only — clean and professional.

```python
def page_header_footer(canvas, doc):
    """Canvas callback for all pages. Clean scientific header/footer."""
    canvas.saveState()
    w, h = letter

    # ── Header ──
    # Report title in muted text, left-aligned
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(MUTED_TEXT)
    canvas.drawString(60, h - 40, "Report Title Here")
    # Gold underline beneath header
    canvas.setStrokeColor(PHYLO_GOLD)
    canvas.setLineWidth(1)
    canvas.line(60, h - 48, w - 60, h - 48)

    # ── Footer ──
    # Thin warm-gray line + centered muted text
    canvas.setStrokeColor(TABLE_BORDER)  # #D5CFC5
    canvas.setLineWidth(0.75)
    canvas.line(60, 40, w - 60, 40)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED_TEXT)
    canvas.drawCentredString(w / 2, 26, f"Page {doc.page}")

    canvas.restoreState()
```

Use the same callback for first and later pages:
```python
doc.build(story, onFirstPage=page_header_footer, onLaterPages=page_header_footer)
```

### Report Sections (in order)

1. **Executive Summary** — 2-3 paragraphs: what was done, key finding, implication
2. **Methods** — Brief: input data, tools used, key parameters
3. **Results** — Tables and figures with captions. This is the bulk of the report.
4. **Discussion / Interpretation** — What the results mean biologically
5. **Appendix** (optional) — Full gene lists, parameter tables, supplementary figures

## Building Blocks

### Styled Paragraphs

Define a style system once, reuse everywhere:

```python
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

styles = getSampleStyleSheet()

styles.add(ParagraphStyle(name="SectionHead", fontName="Helvetica-Bold",
    fontSize=18, textColor=HEADING_COLOR, spaceBefore=24, spaceAfter=10))

styles.add(ParagraphStyle(name="Body", fontName="Helvetica",
    fontSize=10.5, textColor=BODY_TEXT, alignment=TA_JUSTIFY,
    spaceAfter=8, leading=15))

styles.add(ParagraphStyle(name="Caption", fontName="Helvetica-Oblique",
    fontSize=9, textColor=CAPTION_TEXT, alignment=TA_CENTER, spaceAfter=14))
```

Rich text in paragraphs uses XML tags — **not** markdown, not Unicode:
```python
Paragraph("Gene <b>TP53</b> (p-value: 1.2×10<super>-8</super>)", styles["Body"])
```

**Important**: Never use Unicode subscript/superscript characters (₀₁₂₃ etc.)
in ReportLab. They render as black boxes. Always use `<sub>` and `<super>` tags.

### Tables

Tables are the workhorse of scientific reports. The pattern:

```python
from reportlab.platypus import Table, TableStyle
from reportlab.lib.colors import HexColor

# Header row + data rows
data = [
    [Paragraph(f'<b>{h}</b>', header_style) for h in headers],
    *[[Paragraph(str(c), cell_style) for c in row] for row in rows]
]

table = Table(data, colWidths=[...])  # Always set explicit widths
table.setStyle(TableStyle([
    # Header — gold background, white bold text
    ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),   # #D4A04A gold
    ("TEXTCOLOR", (0, 0), (-1, 0), TABLE_HEADER_FG),    # white
    # Alternating rows — very light warm gray
    *[("BACKGROUND", (0, i), (-1, i), TABLE_ALT_ROW)    # #F9F7F3
      for i in range(2, len(data), 2)],
    # Grid — thin warm borders (not heavy black)
    ("GRID", (0, 0), (-1, -1), 0.5, TABLE_BORDER),      # #D5CFC5
    ("BOX", (0, 0), (-1, -1), 0.75, TABLE_BORDER),      # outer border same warm gray
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
]))
```

For large result tables (100+ rows), show top 20 in the report body and note
"Full results in results.csv". Don't try to fit everything — PDFs aren't spreadsheets.

### Charts (Native ReportLab Graphics)

ReportLab can draw bar charts, pie charts, and line plots as vector graphics
directly in the PDF — no matplotlib, no image files, no dependencies.

```python
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.barcharts import VerticalBarChart

def make_bar_chart(categories, data_series, series_labels, width=460, height=220):
    d = Drawing(width, height)
    # Background card
    d.add(Rect(0, 0, width, height, fillColor=PHYLO_OFF_WHITE,
               strokeColor=TABLE_BORDER, strokeWidth=0.5, rx=6))
    bc = VerticalBarChart()
    bc.x, bc.y = 60, 40
    bc.width, bc.height = width - 100, height - 70
    bc.data = data_series
    bc.categoryAxis.categoryNames = categories
    # Apply Phylo chart colors
    for i, color in enumerate(CHART_COLORS[:len(data_series)]):
        bc.bars[i].fillColor = color
        bc.bars[i].strokeWidth = 0
    d.add(bc)
    return d
```

### Centering Charts, Images, and Tables

**IMPORTANT**: All charts, images, and tables should be horizontally centered
on the page. Left-aligned figures look unpolished in a scientific report.

For **Drawing objects** (charts), set `hAlign` on the Drawing:
```python
d = Drawing(width, height)
d.hAlign = "CENTER"   # ← always set this
# ... add chart elements ...
return d
```

For **embedded images**, wrap in a centered paragraph or set `hAlign`:
```python
from reportlab.platypus import Image

img = Image("/mnt/results/volcano_plot.png", width=400, height=300)
img.hAlign = "CENTER"
story.append(img)
story.append(Paragraph("Figure 1: Volcano plot of DEGs", styles["Caption"]))
```

For **tables**, set `hAlign` on the Table object:
```python
table = Table(data, colWidths=[...])
table.hAlign = "CENTER"   # ← always set this
table.setStyle(TableStyle([...]))
```

**When to use ReportLab charts vs. matplotlib images:**
- ReportLab charts: simple bar/pie/line, small datasets, when you want vector quality
- Matplotlib/seaborn images: complex scientific plots (volcano, heatmap, UMAP),
  already generated during analysis. Save as PNG, then embed (see above)

### Callout Boxes

For highlighting key findings or warnings. Uses warm off-white background
with a gold left border — subtle, not flashy:

```python
def callout_box(text, style, width=440):
    data = [[Paragraph(text, style)]]
    t = Table(data, colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CALLOUT_BG),     # #FAF9F3 warm off-white
        ("BOX", (0, 0), (-1, -1), 0.5, TABLE_BORDER),     # thin warm gray border
        ("LINEBEFOREDECOR", (0, 0), (0, -1)),              # optional: see note below
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    return t
```

For a gold left-accent border (like a scientific aside), add:
```python
("LINEBEFORE", (0, 0), (0, -1), 3, PHYLO_GOLD),
```

### Section Dividers

Use gold divider lines to separate major sections — matching the gold header underline:

```python
from reportlab.platypus import HRFlowable

def divider(color=DIVIDER_COLOR, width=480):
    return HRFlowable(width=width, thickness=1, color=color,  # gold #D4A04A
                      spaceAfter=10, spaceBefore=4)
```

## File Handling for Biomni

ReportLab writes PDFs sequentially (no random-access seeks), so PDFs can be
written **directly to `/mnt/results/`** — no staging needed.

```python
import os

output_path = "/mnt/results/report_analysis.pdf"

doc = SimpleDocTemplate(output_path, pagesize=letter, ...)
doc.build(story, ...)
```

Naming convention: `report_<descriptive_title>.pdf`
Examples: `report_differential_expression.pdf`, `report_survival_analysis.pdf`

## Validation

After generating any PDF, validate it before telling the user it's ready.
Validation catches blank pages, missing content, rendering failures, and
corrupted files. See `references/validation.md` for the full validation
guide and helper function.

### Quick validation (always do this)

```python
from pypdf import PdfReader

reader = PdfReader(output_path)
page_count = len(reader.pages)
file_size = os.path.getsize(output_path)

# Sanity checks
assert page_count >= 2, f"Report has only {page_count} page(s) — likely missing content"
assert file_size > 5000, f"Report is only {file_size} bytes — likely blank or corrupt"

# Verify text is extractable (not just images)
first_page_text = reader.pages[0].extract_text()
assert len(first_page_text.strip()) > 0, "First page has no extractable text"
```

### Visual validation (recommended)

Use the Read tool with `mode="media_output_check"` after generation:
```
Read(path="/mnt/results/report_analysis.pdf", mode="media_output_check")
```

This runs a lightweight visual check without consuming context. If it reports
blank pages, clipped content, or rendering issues, regenerate and re-check.

### Alignment and layout review (always do this)

After generating the PDF, visually review each page for layout issues.
Common problems to check:

1. **Charts/images not centered.** Every Drawing, Image, and Table should have
   `hAlign = "CENTER"`. Left-aligned figures in an otherwise justified report
   look unprofessional.
2. **Tables wider than the content area.** Sum of `colWidths` must not exceed
   the page content width (letter with 60pt margins = ~492pt usable).
3. **Orphaned captions.** A figure caption should not appear on a different page
   from its figure. Use `KeepTogether` to bind them:
   ```python
   from reportlab.platypus import KeepTogether
   story.append(KeepTogether([chart, Spacer(1, 4), caption_paragraph]))
   ```
4. **Uneven spacing.** Sections should have consistent `spaceBefore`/`spaceAfter`.
   Don't mix manual `Spacer()` calls with paragraph spacing — pick one approach.
5. **Page breaks mid-table.** For tables with many rows, use `repeatRows=1` to
   repeat the header row on continuation pages:
   ```python
   table = Table(data, colWidths=[...], repeatRows=1)
   ```

## Common Pitfalls

1. **Unicode subscripts render as black boxes.** Use `<sub>` and `<super>` tags instead.
2. **Forgetting explicit colWidths on tables.** Without them, ReportLab guesses
   poorly and columns overflow or collapse.
3. **Using `/tmp/results-staging/` for PDFs.** ReportLab writes sequentially —
   write directly to `/mnt/results/`. Staging is only needed for ZIP-based
   formats (.docx, .pptx, .xlsx).
4. **Enormous tables.** Show top N rows + summary. Full data belongs in CSV.
5. **Missing `canvas.saveState()` / `restoreState()`.** In page callbacks, always
   wrap your drawing code. Without this, style changes leak into the content layer.
6. **Embedding huge images.** Resize to reasonable dimensions (width ≤ 500pt)
   before embedding. Large images bloat the PDF and slow rendering.
7. **Left-aligned charts and images.** ReportLab defaults to left alignment.
   Always set `hAlign = "CENTER"` on Drawing, Image, and Table objects.
8. **Orphaned captions.** Wrap figure + caption in `KeepTogether([...])` so
   they don't split across pages.
