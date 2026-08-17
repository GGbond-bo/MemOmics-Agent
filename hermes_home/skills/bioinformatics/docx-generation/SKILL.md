---
id: "skill_49bf9e9135264577947c33033a39160c"
name: "docx-generation"
display-name: "Best practices for Word document generation"
short-description: "Generate professional, Phylo-branded Word documents (.docx) using python-docx."
category: Visualization
visibility: "internal"
keywords: "Word, docx, document, python-docx, Phylo, scientific, tables, figures, editable"
version: "1.0"
last-updated: "April 2026"
description: >
when_to_use: "[docx-generation] 需使用docx generation功能，适用于相关生信分析场景"
  Generate professional, Phylo-branded Word documents from scientific analysis
  results using python-docx. Use this skill whenever the agent needs to produce
  a .docx deliverable. Only create when the user explicitly requests a Word
  document, .docx, or editable report. Do NOT use for: simple markdown reports
  viewed in-app, PDF deliverables (use pdf_report_generation), or spreadsheet
  data (use CSV or xlsx).
compatibility:
  pre_installed:
    - python-docx
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



# Best Practices for Word Document Generation

## When to create a Word doc

**Only create when the user explicitly requests** a Word document, .docx,
or editable report.

Choose the right format for the situation:

- **Word (.docx)** — when collaborators need to edit, comment, or track changes.
  Preferred for drafts, manuscripts, and documents going through review cycles.
- **PDF** — when the document is final and should not be edited. Use the
  `pdf_report_generation` skill instead.
- **Markdown** (`report_<title>.md`) — default for in-app reports. Only create
  when the task involves multiple complex analyses needing structured documentation.
- **Direct chat response** — default for simple queries and single analyses.

Generate a Word doc specifically when:

- The user explicitly asks for a Word doc, .docx, or "editable report"
- The deliverable will be reviewed, annotated, or revised by others
- The report needs to be imported into Word-based workflows (journals, grants)
- The user wants to add their own content or figures after generation

## Phylo Brand Identity

These colors and fonts match the Phylo visual language. The style is clean and
scientific — gold as the primary accent, white backgrounds, minimal color.

### Color Tokens

```python
# Brand colors (for reference — used as hex strings in python-docx)
HEADING_COLOR    = "111111"    # Headings (near-black)
BODY_COLOR       = "2C2A26"    # Body text (warm dark)
GOLD             = "D4A04A"    # PRIMARY ACCENT: table headers, dividers, highlights
MUTED            = "8A8378"    # Captions, footnotes, secondary text
TABLE_HEADER_FILL = "D4A04A"  # Table header background (gold)
TABLE_ALT_FILL   = "F9F7F3"   # Alternating row shading (very light warm)
TABLE_BORDER     = "D5CFC5"   # Table grid lines (warm gray)
LINK_COLOR       = "0563C1"   # Hyperlinks
WHITE            = "FFFFFF"   # Table header text, backgrounds
```

### Typography

Use Arial as the default font — universally available across platforms.

```python
FONT = "Arial"
```

| Element        | Font   | Size | Weight | Color       |
|----------------|--------|------|--------|-------------|
| Report title   | Arial  | 26pt | Bold   | HEADING     |
| Subtitle       | Arial  | 11pt | Normal | GOLD        |
| Attribution    | Arial  | 10pt | Italic | MUTED       |
| Section head   | Arial  | 18pt | Bold   | HEADING     |
| Subheading     | Arial  | 14pt | Bold   | HEADING     |
| Body text      | Arial  | 11pt | Normal | BODY        |
| Caption        | Arial  | 9pt  | Italic | MUTED       |
| Table header   | Arial  | 10pt | Bold   | WHITE       |
| Table cell     | Arial  | 10pt | Normal | BODY        |

## Architecture: How python-docx Works

python-docx builds .docx files by constructing an object model of paragraphs,
runs, tables, and sections. Key concepts:

```python
from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT

doc = Document()

# Set default font
style = doc.styles["Normal"]
font = style.font
font.name = "Arial"
font.size = Pt(11)
font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)

# Add content
doc.add_heading("Title", level=1)
doc.add_paragraph("Body text here.")

# Save
doc.save(output_path)
```

Unlike ReportLab, python-docx does not use canvas callbacks. Headers, footers,
and page layout are set through section properties.

## Standard Report Template

Every Biomni Word document should follow this structure. Not every section is
required — adapt to the analysis, but maintain the ordering.

### Page Setup

```python
from docx.shared import Inches

section = doc.sections[0]
section.page_width = Inches(8.5)
section.page_height = Inches(11)
section.top_margin = Inches(1)
section.bottom_margin = Inches(1)
section.left_margin = Inches(1)
section.right_margin = Inches(1)
```

### Header and Footer

The header shows the report title in muted text with a gold underline.
The footer shows centered page number or muted text.

**Do not put "PHYLO" or explicit branding in the header.** These reports
are used by users directly — the header should be the report title only.

```python
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ── Header ──
header = section.header
header.is_linked_to_previous = False
hp = header.paragraphs[0]
hp.text = ""

# Report title in muted text
run = hp.add_run("RNA-seq Differential Expression Analysis")
run.font.name = "Arial"
run.font.size = Pt(9)
run.font.color.rgb = RGBColor(0x8A, 0x83, 0x78)

# Gold bottom border on header paragraph
pPr = hp._element.get_or_add_pPr()
pBdr = OxmlElement("w:pBdr")
bottom = OxmlElement("w:bottom")
bottom.set(qn("w:val"), "single")
bottom.set(qn("w:sz"), "6")        # border thickness
bottom.set(qn("w:color"), "D4A04A")  # gold
bottom.set(qn("w:space"), "4")
pBdr.append(bottom)
pPr.append(pBdr)

# ── Footer ──
footer = section.footer
footer.is_linked_to_previous = False
fp = footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

# Thin warm-gray top border
fpPr = fp._element.get_or_add_pPr()
fpBdr = OxmlElement("w:pBdr")
top = OxmlElement("w:top")
top.set(qn("w:val"), "single")
top.set(qn("w:sz"), "4")
top.set(qn("w:color"), "D5CFC5")
top.set(qn("w:space"), "4")
fpBdr.append(top)
fpPr.append(fpBdr)

run = fp.add_run("Page ")
run.font.name = "Arial"
run.font.size = Pt(8)
run.font.color.rgb = RGBColor(0x8A, 0x83, 0x78)

# Auto page number field
fldChar1 = OxmlElement("w:fldChar")
fldChar1.set(qn("w:fldCharType"), "begin")
run2 = fp.add_run()
run2._element.append(fldChar1)

instrText = OxmlElement("w:instrText")
instrText.set(qn("xml:space"), "preserve")
instrText.text = " PAGE "
run3 = fp.add_run()
run3._element.append(instrText)

fldChar2 = OxmlElement("w:fldChar")
fldChar2.set(qn("w:fldCharType"), "end")
run4 = fp.add_run()
run4._element.append(fldChar2)
```

### Title Block (Page 1)

No cover page — reports open directly with content. The title block is a
large heading + gold subtitle + muted attribution:

```python
# Title
title_para = doc.add_paragraph()
title_run = title_para.add_run("Differential Expression Analysis")
title_run.font.name = "Arial"
title_run.font.size = Pt(26)
title_run.bold = True
title_run.font.color.rgb = RGBColor(0x11, 0x11, 0x11)
title_para.space_before = Pt(20)
title_para.space_after = Pt(4)

# Subtitle in gold
sub_para = doc.add_paragraph()
sub_run = sub_para.add_run("RNA-seq  |  Treatment vs. Control  |  HeLa Cell Line")
sub_run.font.name = "Arial"
sub_run.font.size = Pt(11)
sub_run.font.color.rgb = RGBColor(0xD4, 0xA0, 0x4A)
sub_para.space_after = Pt(2)

# Attribution in muted italic
attr_para = doc.add_paragraph()
attr_run = attr_para.add_run("Generated by Biomni  |  April 14, 2026")
attr_run.font.name = "Arial"
attr_run.font.size = Pt(10)
attr_run.italic = True
attr_run.font.color.rgb = RGBColor(0x8A, 0x83, 0x78)
attr_para.space_after = Pt(16)
```

### Report Sections (in order)

1. **Executive Summary** — 2-3 paragraphs: what was done, key finding, implication
2. **Methods** — Brief: input data, tools used, key parameters
3. **Results** — Tables and figures with captions. This is the bulk of the report.
4. **Discussion / Interpretation** — What the results mean biologically
5. **Appendix** (optional) — Full gene lists, parameter tables, supplementary figures

## Building Blocks

### Section Headings

```python
def add_section_heading(doc, text, level=1):
    """Add a heading with Phylo styling."""
    heading = doc.add_heading(text, level=level)
    for run in heading.runs:
        run.font.name = "Arial"
        run.font.color.rgb = RGBColor(0x11, 0x11, 0x11)
    if level == 1:
        heading.space_before = Pt(24)
        heading.space_after = Pt(10)
    elif level == 2:
        heading.space_before = Pt(16)
        heading.space_after = Pt(8)
    return heading
```

### Body Paragraphs

```python
def add_body(doc, text):
    """Add a body paragraph with Phylo styling."""
    para = doc.add_paragraph()
    run = para.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)
    para.paragraph_format.space_after = Pt(8)
    para.paragraph_format.line_spacing = Pt(15)
    return para
```

For rich text (bold, italic) within a paragraph, use multiple runs:

```python
para = doc.add_paragraph()
run1 = para.add_run("Gene ")
run1.font.name = "Arial"
run1.font.size = Pt(11)
run1.font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)

run2 = para.add_run("TP53")
run2.font.name = "Arial"
run2.font.size = Pt(11)
run2.bold = True
run2.font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)

run3 = para.add_run(" is significantly upregulated.")
run3.font.name = "Arial"
run3.font.size = Pt(11)
run3.font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)
```

### Bullet and Numbered Lists

Use python-docx's built-in list styles. **Never insert bullet characters manually**
(e.g., "•" or "\u2022") — they won't be recognized as proper list items.

```python
# Bullet list
doc.add_paragraph("First item", style="List Bullet")
doc.add_paragraph("Second item", style="List Bullet")

# Numbered list
doc.add_paragraph("Step one", style="List Number")
doc.add_paragraph("Step two", style="List Number")
```

To style list items with Phylo fonts, set the font on each run after adding:

```python
para = doc.add_paragraph(style="List Bullet")
run = para.add_run("Loss-of-function variants reduce BMI")
run.font.name = "Arial"
run.font.size = Pt(11)
run.font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)
```

### Hyperlinks

For citations and references in scientific reports:

```python
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

def add_hyperlink(paragraph, url, text):
    """Add a clickable hyperlink to a paragraph."""
    part = paragraph.part
    r_id = part.relate_to(url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    rStyle = OxmlElement("w:rStyle")
    rStyle.set(qn("w:val"), "Hyperlink")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rPr.append(rStyle)
    rPr.append(color)
    rPr.append(u)
    run.append(rPr)
    run.text = text
    hyperlink.append(run)
    paragraph._element.append(hyperlink)
    return hyperlink
```

### Tables

Tables use gold headers with white text, warm gray alternating rows, and
thin warm borders. This matches the Phylo docx style exactly.

```python
from docx.shared import Pt, RGBColor, Inches
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.table import WD_TABLE_ALIGNMENT

def styled_table(doc, headers, rows, col_widths=None):
    """Create a Phylo-styled table with gold headers and alternating rows."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Set column widths if provided (in inches)
    if col_widths:
        for i, width in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = Inches(width)

    # Header row
    for i, header_text in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(header_text)
        run.font.name = "Arial"
        run.font.size = Pt(10)
        run.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        # Gold background
        shading = OxmlElement("w:shd")
        shading.set(qn("w:fill"), "D4A04A")
        shading.set(qn("w:val"), "clear")
        cell._element.get_or_add_tcPr().append(shading)

    # Data rows
    for ri, row_data in enumerate(rows):
        for ci, cell_text in enumerate(row_data):
            cell = table.rows[ri + 1].cells[ci]
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(cell_text))
            run.font.name = "Arial"
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)
            # Bold first column (gene names, labels)
            if ci == 0:
                run.bold = True
            # Alternating row shading
            if ri % 2 == 1:
                shading = OxmlElement("w:shd")
                shading.set(qn("w:fill"), "F9F7F3")
                shading.set(qn("w:val"), "clear")
                cell._element.get_or_add_tcPr().append(shading)

    # Set table borders (thin warm gray)
    set_table_borders(table, "D5CFC5")

    # Cell padding
    for row in table.rows:
        for cell in row.cells:
            set_cell_padding(cell, top=80, bottom=80, left=120, right=120)

    return table

def set_table_borders(table, color="D5CFC5", size="4"):
    """Set thin warm-gray borders on all table cells."""
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement("w:tblPr")
    borders = OxmlElement("w:tblBorders")
    for edge in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:color"), color)
        el.set(qn("w:space"), "0")
        borders.append(el)
    tblPr.append(borders)

def set_cell_padding(cell, top=80, bottom=80, left=120, right=120):
    """Set cell padding in twips (1/20 of a point)."""
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for edge, val in [("top", top), ("bottom", bottom),
                      ("start", left), ("end", right)]:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        tcMar.append(el)
    tcPr.append(tcMar)
```

### Images

Embed figures already generated during analysis. Center them and add a
caption below:

```python
from docx.shared import Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

def add_figure(doc, image_path, caption_text, width=5.0):
    """Add a centered image with an italic muted caption."""
    # Image paragraph (centered)
    img_para = doc.add_paragraph()
    img_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    img_para.add_run().add_picture(image_path, width=Inches(width))
    img_para.space_before = Pt(12)
    img_para.space_after = Pt(4)

    # Caption (centered, muted italic)
    cap_para = doc.add_paragraph()
    cap_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap_run = cap_para.add_run(caption_text)
    cap_run.font.name = "Arial"
    cap_run.font.size = Pt(9)
    cap_run.italic = True
    cap_run.font.color.rgb = RGBColor(0x8A, 0x83, 0x78)
    cap_para.space_after = Pt(14)

    return img_para
```

### Callout Boxes

For highlighting key findings. Uses a single-cell table with warm off-white
background and a gold left border:

```python
def callout_box(doc, text, bold_prefix=None):
    """Add a callout box with gold left accent."""
    table = doc.add_table(rows=1, cols=1)
    cell = table.rows[0].cells[0]
    cell.text = ""

    para = cell.paragraphs[0]
    if bold_prefix:
        bold_run = para.add_run(bold_prefix + " ")
        bold_run.font.name = "Arial"
        bold_run.font.size = Pt(10)
        bold_run.bold = True
        bold_run.font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)

    text_run = para.add_run(text)
    text_run.font.name = "Arial"
    text_run.font.size = Pt(10)
    text_run.font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)

    # Off-white background
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), "FAF9F3")
    shading.set(qn("w:val"), "clear")
    cell._element.get_or_add_tcPr().append(shading)

    # Gold left border, warm gray on other sides
    tcBorders = OxmlElement("w:tcBorders")
    for edge, color, size in [
        ("start", "D4A04A", "18"),   # thick gold left border
        ("top", "D5CFC5", "4"),
        ("bottom", "D5CFC5", "4"),
        ("end", "D5CFC5", "4"),
    ]:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:color"), color)
        el.set(qn("w:space"), "0")
        tcBorders.append(el)
    cell._element.get_or_add_tcPr().append(tcBorders)

    set_cell_padding(cell, top=120, bottom=120, left=160, right=160)

    return table
```

### Section Dividers

A gold horizontal rule to separate major sections:

```python
def add_divider(doc):
    """Add a gold divider line."""
    para = doc.add_paragraph()
    pPr = para._element.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:color"), "D4A04A")
    bottom.set(qn("w:space"), "1")
    pBdr.append(bottom)
    pPr.append(pBdr)
    para.space_before = Pt(4)
    para.space_after = Pt(10)
    return para
```

### Page Breaks

```python
from docx.enum.text import WD_BREAK

# Add a page break before a new section
para = doc.add_paragraph()
para.add_run().add_break(WD_BREAK.PAGE)
```

## File Handling for Biomni

Word documents (.docx) are ZIP-based formats that require random-access writes.
**Write to `/tmp/results-staging/`** — files are automatically copied to
`/mnt/results/` after each ExecuteCode cell finishes.

```python
import os

os.makedirs("/tmp/results-staging", exist_ok=True)
output_path = "/tmp/results-staging/document_analysis.docx"

doc.save(output_path)

# After ExecuteCode finishes, file auto-syncs to /mnt/results/document_analysis.docx
# In subsequent cells, read from /mnt/results/ (not /tmp/results-staging/)
```

**Naming convention**: `document_<descriptive_title>.docx`
Examples: `document_differential_expression.docx`, `document_literature_review.docx`

**IMPORTANT**: Do not mention internal paths like `/mnt/results/` or
`/tmp/results-staging/` in user-facing outputs. Use filenames only
(e.g., "See document_analysis.docx").

## Validation

After generating any Word document, validate it before telling the user it's ready.

### Quick validation (always do this)

```python
from docx import Document
import os

doc_check = Document(output_path)
file_size = os.path.getsize(output_path)
para_count = len(doc_check.paragraphs)
table_count = len(doc_check.tables)

# Sanity checks
assert file_size > 5000, f"Document is only {file_size} bytes — likely empty"
assert para_count >= 5, f"Document has only {para_count} paragraphs — likely missing content"

# Verify text content exists
all_text = "\n".join([p.text for p in doc_check.paragraphs])
assert len(all_text.strip()) > 100, "Document has very little text content"

print(f"OK: {file_size:,} bytes, {para_count} paragraphs, {table_count} tables")
```

### Alignment and layout review (always do this)

After generating the document, check for common layout issues:

1. **Tables not centered.** Every table should have `table.alignment = WD_TABLE_ALIGNMENT.CENTER`.
2. **Images not centered.** Image paragraphs should have `alignment = WD_ALIGN_PARAGRAPH.CENTER`.
3. **Missing column widths.** Always set explicit column widths on tables — without
   them, Word auto-sizes unpredictably.
4. **Font inconsistency.** Every run must have `font.name = "Arial"` set explicitly.
   python-docx does not always inherit from the Normal style.
5. **Orphaned captions.** A figure caption should appear on the same page as
   its figure. For critical figure+caption pairs, consider using a keep-with-next
   paragraph property.

### Visual validation (MANDATORY for embedded figures)

If the document contains embedded figures/images, you MUST validate them
using the Biomni media output check pattern. Convert to PDF first, then check:

```python
import subprocess
subprocess.run(["libreoffice", "--headless", "--convert-to", "pdf", output_path])
```

Then in a subsequent step:
```
Read(path="/mnt/results/document_analysis.pdf", mode="media_output_check")
```

This is MANDATORY per the system prompt: "After saving ANY figure, run Read
on the .png or .pdf with mode='media_output_check' to verify formatting and
rendering." If figures are blank, unreadable, or clipped, regenerate and re-check.

## Common Pitfalls

1. **Font not sticking.** python-docx requires setting `font.name` on every run
   explicitly. The Normal style font is not always inherited, especially in
   table cells and headers.
2. **Table shading using wrong XML.** Always use `w:shd` with `val="clear"`.
   Using `val="solid"` creates a black background.
3. **Missing cell padding.** Without explicit `tcMar`, table cells look cramped.
   Always call `set_cell_padding()` on every cell.
4. **Writing directly to `/mnt/results/`.** .docx is a ZIP-based format —
   always stage in `/tmp/results-staging/`. Files auto-sync to `/mnt/results/`
   after ExecuteCode finishes. In subsequent cells, read from `/mnt/results/`.
5. **Enormous tables.** Show top N rows + summary. Full data belongs in CSV.
6. **Left-aligned images.** Default paragraph alignment is left. Always set
   `alignment = WD_ALIGN_PARAGRAPH.CENTER` on image paragraphs.
7. **Hard-coded page numbers.** Use the PAGE field code (shown in header/footer
   section) instead of hard-coded numbers — they update automatically.
8. **Unicode issues.** python-docx handles Unicode well, but avoid combining
   characters that may not render in Arial. Stick to standard scientific
   notation (µ, ±, ×, °, α, β) which Arial supports.
9. **Never use tables as dividers.** Table cells have a minimum height and
   render as empty boxes. Use paragraph borders (see Section Dividers)
   for horizontal rules.
10. **Never use unicode bullets.** Use `style="List Bullet"` or `style="List Number"`.
    Manually inserted bullet characters (•, \u2022) are not recognized as
    proper list items and break numbering/indentation.
11. **Font inheritance is unreliable.** python-docx does not always inherit
    the Normal style font into headings, table cells, or list items. Always
    set `font.name = "Arial"` explicitly on every run.
