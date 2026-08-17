---
id: "skill_a0ffd6a768fa4c1f9ed4ce21bceb41d3"
name: "pptx-generation"
display-name: "Best practices for presentation generation"
short-description: "Generate professional, Phylo-branded PowerPoint presentations from scientific analysis results using python-pptx."
category: Visualization
visibility: "internal"
keywords: "PowerPoint, pptx, slides, presentation, python-pptx, Phylo, scientific, figures, charts"
version: "1.0"
last-updated: "April 2026"
description: >
when_to_use: "[pptx-generation] PPTX文件生成：内容/图表→python-pptx→专业排版→图表嵌入→PowerPoint文件"
  Generate professional, Phylo-branded PowerPoint presentations from scientific
  analysis results using python-pptx. Use this skill whenever the agent needs to
  produce a .pptx slide deck. Only create when the user explicitly requests slides,
  a presentation, or a PowerPoint. Do NOT use for: simple markdown reports,
  Word documents (use docx_generation), or PDF reports (use pdf_report_generation).
compatibility:
  pre_installed:
    - python-pptx
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



# Best Practices for Presentation Generation

## When to create a presentation

**Only create when the user explicitly requests** slides, a presentation, or
a PowerPoint.

Slide content guidelines:

- Keep text concise — use bullet points, not paragraphs
- Include key figures/charts as images when relevant (save figure first, then add to slide)
- Limit to essential slides; prefer quality over quantity
- Use a clean, professional layout with consistent formatting

## Phylo Brand Identity for Slides

Scientific presentations should be clean, authoritative, and restrained.
The Phylo slide palette uses warm neutrals with gold accents — matching
the docx and PDF report styles.

### Slide Color Palette

```python
# Slide backgrounds — consistent white throughout
LIGHT_BG         = "FFFFFF"    # All slides (white)
WARM_GRAY_BG     = "FAF9F3"   # Callout boxes, alternate table rows

# Text
HEADING          = "111111"    # Headings (dark on white)
BODY             = "2C2A26"    # Body text
MUTED            = "8A8378"   # Captions, footnotes, secondary text

# Accents
GOLD             = "D4A04A"   # PRIMARY ACCENT: borders, highlights, dividers
GOLD_LIGHT       = "E8CC8A"   # Lighter gold for fills, backgrounds

# Full Phylo brand colors (for charts and diagrams)
PHYLO_BLUE       = "0279EE"
PHYLO_ORANGE     = "FF9400"
PHYLO_GREEN      = "75A025"
PHYLO_PINK       = "FD9BED"
PHYLO_LIME       = "E9ED4C"
```

### Chart Colors

When adding charts or data visualizations to slides, use this sequence:

```python
CHART_COLORS = ["D4A04A", "0279EE", "75A025", "FF9400", "FD9BED", "111111"]
```

### Typography

Use Arial — universally available across platforms.

| Element        | Font   | Size   | Weight | Color         |
|----------------|--------|--------|--------|---------------|
| Slide title    | Arial  | 36-40pt| Bold   | HEADING       |
| Subtitle       | Arial  | 18-20pt| Normal | GOLD or MUTED |
| Section header | Arial  | 24-28pt| Bold   | HEADING       |
| Body text      | Arial  | 16-18pt| Normal | BODY          |
| Bullet points  | Arial  | 14-16pt| Normal | BODY          |
| Captions       | Arial  | 10-12pt| Italic | MUTED         |
| Data labels    | Arial  | 11-12pt| Normal | BODY          |

## Architecture: How python-pptx Works

python-pptx creates .pptx files by building slides with positioned elements.
Every element has x, y, width, height in inches (via `Inches()`) or points
(via `Pt()`).

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

prs = Presentation()
prs.slide_width = Inches(13.333)   # 16:9 widescreen
prs.slide_height = Inches(7.5)

# Blank layout (most flexible)
blank_layout = prs.slide_layouts[6]
slide = prs.slides.add_slide(blank_layout)

# Add elements with absolute positioning
txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1))
tf = txBox.text_frame
tf.text = "Hello World"

prs.save(output_path)
```

**Key concept**: Unlike Word/PDF, slides use absolute positioning. Every
element needs explicit x, y, w, h coordinates. Plan your layout grid before
coding.

## Standard Slide Deck Structure

### Slide Dimensions

Use widescreen 16:9 (standard for scientific presentations):

```python
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
```

Layout grid: 0.5" margins on all sides gives a content area of 12.333" × 6.5".

### Slide Types

A scientific presentation typically follows this structure:

1. **Title Slide** — white background, gold accent, report title, subtitle, date
2. **Overview / Key Findings** — 3-4 bullet points or stat callouts
3. **Methods** — brief pipeline/approach description
4. **Results Slides** — tables, charts, key figures (1 topic per slide)
5. **Discussion** — interpretation, implications
6. **Next Steps / Conclusions** — white background, closing slide

All slides use a **consistent white background** with gold accent lines for
visual hierarchy. This maintains a clean, scientific look throughout.

### Title Slide

```python
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout

# White background
fill = slide.background.fill
fill.solid()
fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

# Gold accent line at top
line = slide.shapes.add_shape(
    1, Inches(0.5), Inches(0.5),
    Inches(12.333), Inches(0))
line.fill.background()
line.line.color.rgb = RGBColor(0xD4, 0xA0, 0x4A)
line.line.width = Pt(2)

# Title text
txBox = slide.shapes.add_textbox(
    Inches(1), Inches(1.5), Inches(11), Inches(2))
tf = txBox.text_frame
tf.word_wrap = True
p = tf.paragraphs[0]
p.text = "Differential Expression Analysis"
p.font.name = "Arial"
p.font.size = Pt(40)
p.font.bold = True
p.font.color.rgb = RGBColor(0x11, 0x11, 0x11)

# Subtitle in gold
p2 = tf.add_paragraph()
p2.text = "RNA-seq  |  Treatment vs. Control"
p2.font.name = "Arial"
p2.font.size = Pt(18)
p2.font.color.rgb = RGBColor(0xD4, 0xA0, 0x4A)
p2.space_before = Pt(12)

# Attribution (bottom, muted)
attr_box = slide.shapes.add_textbox(
    Inches(1), Inches(6.2), Inches(11), Inches(0.8))
attr_tf = attr_box.text_frame
attr_p = attr_tf.paragraphs[0]
attr_p.text = "Generated by Biomni  |  April 2026"
attr_p.font.name = "Arial"
attr_p.font.size = Pt(12)
attr_p.font.color.rgb = RGBColor(0x8A, 0x83, 0x78)
```

### Content Slides

```python
slide = prs.slides.add_slide(prs.slide_layouts[6])

# White background (default, but be explicit)
fill = slide.background.fill
fill.solid()
fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

# Gold accent line at top
line = slide.shapes.add_shape(
    1, Inches(0.5), Inches(0.5),
    Inches(12.333), Inches(0))
line.fill.background()
line.line.color.rgb = RGBColor(0xD4, 0xA0, 0x4A)
line.line.width = Pt(1.5)

# Slide title
title_box = slide.shapes.add_textbox(
    Inches(0.5), Inches(0.6), Inches(12), Inches(0.8))
tf = title_box.text_frame
p = tf.paragraphs[0]
p.text = "Key Findings"
p.font.name = "Arial"
p.font.size = Pt(28)
p.font.bold = True
p.font.color.rgb = RGBColor(0x11, 0x11, 0x11)

# Muted footer
footer_box = slide.shapes.add_textbox(
    Inches(0.5), Inches(7.0), Inches(12), Inches(0.4))
ft = footer_box.text_frame
fp = ft.paragraphs[0]
fp.text = "RNA-seq Differential Expression Analysis"
fp.font.name = "Arial"
fp.font.size = Pt(9)
fp.font.color.rgb = RGBColor(0x8A, 0x83, 0x78)
fp.alignment = PP_ALIGN.RIGHT
```

## Building Blocks

### Text Boxes with Bullets

```python
def add_bullets(slide, items, x, y, w, h, font_size=16):
    """Add a bulleted list to a slide."""
    txBox = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = txBox.text_frame
    tf.word_wrap = True

    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = item
        p.font.name = "Arial"
        p.font.size = Pt(font_size)
        p.font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)
        p.space_after = Pt(8)
        # Bullet
        p.level = 0
        pPr = p._pPr
        if pPr is None:
            from pptx.oxml.ns import qn
            pPr = p._p.get_or_add_pPr()
        buChar = pPr.makeelement('{http://schemas.openxmlformats.org/drawingml/2006/main}buChar', {})
        buChar.set('char', '•')
        pPr.append(buChar)
    return txBox
```

### Tables

Gold header, warm alternating rows — matching the Word/PDF table style:

```python
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

def add_styled_table(slide, headers, rows, x, y, w, h, col_widths=None):
    """Add a Phylo-styled table to a slide."""
    n_rows = len(rows) + 1
    n_cols = len(headers)
    table_shape = slide.shapes.add_table(n_rows, n_cols,
        Inches(x), Inches(y), Inches(w), Inches(h))
    table = table_shape.table

    # Set column widths
    if col_widths:
        for i, cw in enumerate(col_widths):
            table.columns[i].width = Inches(cw)

    # Header row — gold background, white bold text
    for i, header_text in enumerate(headers):
        cell = table.cell(0, i)
        cell.text = header_text
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(0xD4, 0xA0, 0x4A)
        for paragraph in cell.text_frame.paragraphs:
            paragraph.font.name = "Arial"
            paragraph.font.size = Pt(12)
            paragraph.font.bold = True
            paragraph.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    # Data rows — alternating warm gray
    for ri, row_data in enumerate(rows):
        for ci, cell_text in enumerate(row_data):
            cell = table.cell(ri + 1, ci)
            cell.text = str(cell_text)
            # Alternating row fill
            if ri % 2 == 1:
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(0xF9, 0xF7, 0xF3)
            else:
                cell.fill.background()
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.name = "Arial"
                paragraph.font.size = Pt(11)
                paragraph.font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)
                if ci == 0:
                    paragraph.font.bold = True

    return table_shape
```

### Embedding Figures

Scientific presentations often include pre-generated figures. Save the
figure first during analysis, then add to slides:

```python
# During analysis (in a previous ExecuteCode cell)
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
# ... create plot ...
fig.savefig("/tmp/results-staging/volcano_plot.png", dpi=200, bbox_inches="tight")

# In the presentation-building cell (read from /mnt/results/)
slide.shapes.add_picture(
    "/mnt/results/volcano_plot.png",
    Inches(1), Inches(1.5),
    width=Inches(5), height=Inches(4)
)
```

**Always save figures as PNG at 200 dpi** for crisp rendering on projectors.
Center images by calculating x position: `x = (13.333 - image_width) / 2`.

### Stat Callouts

For highlighting key numbers (e.g., "1,247 DEGs identified"):

```python
def add_stat_callout(slide, number, label, x, y, w=3.0, h=1.5):
    """Large number with small label below — for key metrics."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True

    # Big number
    p = tf.paragraphs[0]
    p.text = str(number)
    p.font.name = "Arial"
    p.font.size = Pt(48)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0xD4, 0xA0, 0x4A)  # gold
    p.alignment = PP_ALIGN.CENTER

    # Label below
    p2 = tf.add_paragraph()
    p2.text = label
    p2.font.name = "Arial"
    p2.font.size = Pt(14)
    p2.font.color.rgb = RGBColor(0x8A, 0x83, 0x78)  # muted
    p2.alignment = PP_ALIGN.CENTER

    return box
```

### Callout Boxes

For highlighting key findings on a slide. Off-white background with gold
left accent — consistent with the Word/PDF callout style:

```python
def add_callout(slide, text, x, y, w, h):
    """Callout box with gold left accent."""
    # Background rectangle (off-white)
    bg = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(0xFA, 0xF9, 0xF3)
    bg.line.color.rgb = RGBColor(0xD5, 0xCF, 0xC5)
    bg.line.width = Pt(0.5)

    # Gold left accent bar
    bar = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(0.06), Inches(h))
    bar.fill.solid()
    bar.fill.fore_color.rgb = RGBColor(0xD4, 0xA0, 0x4A)
    bar.line.fill.background()

    # Text
    txBox = slide.shapes.add_textbox(
        Inches(x + 0.2), Inches(y + 0.15),
        Inches(w - 0.4), Inches(h - 0.3))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.name = "Arial"
    p.font.size = Pt(14)
    p.font.color.rgb = RGBColor(0x2C, 0x2A, 0x26)

    return txBox
```

## Layout Guidelines

### Spacing

- **Margins**: 0.5" minimum from slide edges
- **Between elements**: 0.3-0.5" gaps
- **Don't fill every inch** — whitespace makes content easier to read

### Layout Patterns for Scientific Slides

- **Title + bullets**: Title at top (y=0.6"), bullets below (y=1.5")
- **Two-column**: Text left (x=0.5, w=5.5), figure right (x=6.5, w=6)
- **Figure + caption**: Centered image with italic caption below
- **Stat callouts**: 3-4 large numbers in a row for key metrics
- **Table slide**: Title + centered table filling most of the slide

### Slide Count Guidelines

Scientific presentations should be concise:

- **Short analysis summary**: 4-6 slides
- **Full analysis report**: 8-12 slides
- **Literature review**: 6-10 slides
- **Never exceed 15 slides** unless the user specifically requests more

## File Handling for Biomni

PowerPoint (.pptx) is a ZIP-based format. **Write to `/tmp/results-staging/`** —
files auto-sync to `/mnt/results/` after each ExecuteCode cell.

```python
import os

os.makedirs("/tmp/results-staging", exist_ok=True)
output_path = "/tmp/results-staging/presentation_analysis.pptx"

prs.save(output_path)

# After ExecuteCode finishes, auto-syncs to /mnt/results/presentation_analysis.pptx
# In subsequent cells, read from /mnt/results/
```

**Naming convention**: `presentation_<descriptive_title>.pptx`
Examples: `presentation_rnaseq_results.pptx`, `presentation_target_discovery.pptx`

**IMPORTANT**: Do not mention internal paths in user-facing outputs. Use filenames only.

## Validation

After saving the .pptx file, always run a structural validation:

```python
from pptx import Presentation
import os

prs_check = Presentation(output_path)
file_size = os.path.getsize(output_path)
slide_count = len(prs_check.slides)

assert file_size > 10000, f"Presentation is only {file_size} bytes — likely empty"
assert slide_count >= 2, f"Only {slide_count} slide(s) — likely missing content"

# Check each slide has content
for i, slide in enumerate(prs_check.slides):
    shapes = len(slide.shapes)
    assert shapes >= 1, f"Slide {i+1} has no shapes — likely blank"

# Verify key formatting on each slide
for i, slide in enumerate(prs_check.slides):
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                if para.font.name:
                    assert para.font.name == "Arial", \
                        f"Slide {i+1}: unexpected font '{para.font.name}'"

print(f"OK: {file_size:,} bytes, {slide_count} slides")
```

### QA Checklist

Review the code for these common layout issues before saving:

1. **Overlapping elements** — verify x/y/w/h don't cause shapes to stack
2. **Text overflow** — ensure text boxes are large enough for content
3. **Uneven spacing** — consistent gaps between elements (0.3-0.5")
4. **Low-contrast text** — dark text on white backgrounds, gold for accents only
5. **Images not centered** — calculate x: `(13.333 - width) / 2`
6. **Inconsistent fonts** — every paragraph must set `font.name = "Arial"`
7. **Table formatting** — gold headers, warm alternating rows
8. **Missing line.fill.background()** — shapes get unwanted outlines without it

## Common Pitfalls

1. **Font not set on every paragraph.** python-pptx does not inherit fonts
   reliably. Set `font.name = "Arial"` on every paragraph explicitly.
2. **Shapes missing `.line.fill.background()`**. Without this, shapes get
   a visible outline. Call it to remove the border.
3. **Images not centered.** Calculate x position: `(13.333 - width) / 2`.
4. **Writing directly to `/mnt/results/`.** .pptx is ZIP-based — always
   stage in `/tmp/results-staging/`.
5. **Too many slides.** Scientific presentations should be concise (4-12 slides).
   Limit to essential content; quality over quantity.
6. **Text-heavy slides.** Use bullet points, not paragraphs. If a slide has
   more than 6 bullet points, split into two slides.
7. **Forgetting figure attribution.** When embedding analysis figures, add
   a caption below with figure number and brief description.
8. **Low-resolution images.** Save figures at 200 dpi minimum. 72 dpi looks
   blurry on projectors.
9. **Inconsistent backgrounds.** Use white backgrounds on ALL slides.
   Gold accents and typography provide visual hierarchy — no dark slides.
10. **Mixing colors randomly.** Stick to the Phylo palette. Gold is the accent,
    near-black for headings, warm gray for secondary elements.
