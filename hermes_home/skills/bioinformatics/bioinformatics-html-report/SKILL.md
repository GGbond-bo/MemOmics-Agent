# Bioinformatics HTML Report Builder

A zero-dependency Python toolkit for generating publication-quality interactive
HTML reports from bioinformatics analysis outputs (figures + tables).

---

## What This Skill Provides

Three files:

| File | Purpose |
|------|---------|
| `html_report_builder.py` | Core library — import this in your script |
| `example_usage.py` | Minimal template for any analysis (DEG, GSEA, etc.) |
| `hdwgcna_report_generator.py` | Full reference implementation for hdWGCNA |

---

## Core Concept

```
PNG figures  →  base64 <img> tags  (offline viewable)
CSV tables   →  DataTables HTML    (sortable, searchable)
Text content →  styled components  (sections, callouts, fig-blocks)
CSS/JS       →  inlined strings    (Phylo color palette)
CDN deps     →  jQuery + DataTables (online) or omit for offline
```

Everything is plain Python f-strings. No Jinja2, no React, no webpack.

---

## Quick Start

```python
from html_report_builder import ReportBuilder

rb = ReportBuilder(
    title="My Analysis\nDataset · Method · 2025",
    subtitle="RNA-seq | Condition A vs B | n=6 per group",
    stats=[("1,234", "DEGs"), ("48", "Samples")],
    key_findings=["Top gene: GENE_A (log2FC=+4.2)"],
)

with rb.section("results", "1. Results", "结果"):
    rb.add_figure(
        fig_path="figures/volcano.png",
        caption_en="Figure 1. Volcano plot.",
        method_zh="DESeq2 Wald 检验，BH-FDR 校正。",
        result_zh="共 1,234 个 DEGs (FDR<0.05)。",
        bio_zh="上调基因富集于代谢通路。",
    )
    rb.add_table(
        table_id="tbl_deg",
        csv_path="tables/deg_results.csv",
        title_en="DEG Results",
        title_zh="差异表达基因",
    )

rb.save("report.html")
```

---

## ReportBuilder API

### Constructor

```python
ReportBuilder(
    title: str,           # Main title (use \n or <br> for subtitle line in yellow)
    subtitle: str = "",   # Subtitle below title
    author: str = "",     # Footer author name
    logo_text: str = "",  # Sidebar logo text
    logo_sub: str = "",   # Sidebar logo subtitle
    stats: list = [],     # [(value, label), ...] hero stat cards
    key_findings: list = [],  # [str, ...] bullet points in hero
    palette: dict = None, # Override color palette
)
```

### Section context manager

```python
with rb.section(
    sec_id: str,       # HTML anchor id (e.g. "network")
    title_en: str,     # Section title (English)
    title_zh: str = "", # Section subtitle (Chinese)
    nav_group: str = "", # Sidebar group label
):
    # add content here
```

### add_figure()

```python
rb.add_figure(
    fig_path: str,        # Path to PNG/JPG/SVG
    caption_en: str,      # English caption below image
    method_zh: str = "",  # Blue panel: 📐 方法
    result_zh: str = "",  # Green panel: 📊 结果
    bio_zh: str = "",     # Yellow panel: 🧬 生物学意义
    param_source_zh: str = "",  # Gray panel: 📚 参数来源 (MemOmics 新增)
    title_en: str = "",   # Subsection title
    title_zh: str = "",   # Subsection title (Chinese)
    full_width: bool = False,   # Full-width layout
    collapsible: bool = True,   # Wrap in <details>
)
```

### add_debate() — MemOmics 新增

```python
rb.add_debate(
    topic: str,           # 辩论主题
    rounds: [             # 辩论轮次 (最多3轮)
        {
            "round": 1,           # 轮次
            "pro": "正方论据...",   # 支持当前参数的理由
            "con": "反方论据...",   # 质疑+替代方案
            "verdict": "裁决...",   # 裁判决断
            "pro_score": 8,        # 正方分数 0-10
            "con_score": 7,        # 反方分数 0-10
            "action": "修改参数...", # 裁决后采取的行动
        },
    ],
    title_en: str = "Parameter Debate",
    title_zh: str = "参数辩论记录",
)
```

### add_param_source() — MemOmics 新增

```python
rb.add_param_source(
    sources: [
        {
            "param": "resolution",       # 参数名
            "value": "0.5",              # 参数值
            "source": "debate",         # 来源: knowledge_base/literature/debate/skill/default
            "citation": "辩论第2轮裁决",  # 引用来源
            "note": "细胞数3万,骨骼肌",    # 备注
        },
    ],
)
```

### add_conclusion_debate() — MemOmics 新增

```python
rb.add_conclusion_debate(
    conclusion: str,       # 最终结论
    pro_argument: str,     # 支持结论的证据
    con_argument: str,     # 质疑结论的证据
    verdict: str,          # 最终裁决
    confidence: str = "",  # 置信度 (high/medium/low) + 理由
)
```

### add_table()

```python
rb.add_table(
    table_id: str,        # Unique HTML id
    csv_path: str,        # Path to CSV file
    title_en: str = "",   # Subsection title
    title_zh: str = "",   # Subsection title (Chinese)
    columns: list = None, # [(csv_key, display_label), ...] — None = all columns
    fmt: dict = None,     # {csv_key: callable} for cell formatting
    tip: str = "",        # Tip text in callout above table
    max_rows: int = 500,  # Max rows to include
)
```

### add_callout()

```python
rb.add_callout(
    kind: str,   # "info" | "warning" | "success" | "tip"
    title: str,  # Bold title
    body: str,   # Body text (HTML allowed)
)
```

### add_pipeline()

```python
rb.add_pipeline(steps=[
    {
        "icon": "⚙️",          # Emoji icon
        "title": "Step Name",   # Step title
        "subtitle": "...",      # Short subtitle
        "params": "key=val",    # Monospace params line
        "desc": "...",          # Longer description (optional)
    },
    ...
])
```

### add_html()

```python
rb.add_html("<p>Any raw HTML</p>")
```

### save()

```python
rb.save("output.html")  # Returns path, prints file size
```

---

## Helper Functions

```python
from html_report_builder import color_badge, fmt_number, encode_image

# Colored pill badge
color_badge("M1", bg="#4CAF50", text_color="#fff")
# → '<span style="background:#4CAF50;...">M1</span>'

# Smart number formatting (auto scientific notation for small values)
fmt_number("0.000123", decimals=4)  # → "1.23e-04"
fmt_number("3.14159",  decimals=2)  # → "3.14"

# Base64 encode an image
src = encode_image("figures/plot.png")  # → "data:image/png;base64,..."
```

---

## Color Palette (Phylo Brand)

```python
PALETTE = {
    "blue":   "#0279EE",   # Primary blue
    "yellow": "#E9ED4C",   # Accent yellow
    "orange": "#FF9400",   # Orange
    "green":  "#75A025",   # Green
    "pink":   "#FD9BED",   # Pink
    "red":    "#E05C5C",   # Red
    "dark":   "#1a1a2e",   # Sidebar / hero background
    "mid":    "#16213e",   # Section headers
    "light":  "#f8f9fa",   # Page background
}
```

Override any color by passing `palette={"blue": "#your_color", ...}` to `ReportBuilder`.

---

## Interpretation Panel Colors

| Panel | Color | Use for |
|-------|-------|---------|
| 📐 方法 (method_zh) | Blue `#e3f2fd` | How the analysis was done, key parameters |
| 📊 结果 (result_zh) | Green `#e8f5e9` | What the figure shows, key numbers |
| 🧬 生物学意义 (bio_zh) | Yellow `#fff8e1` | What it means biologically, implications |

---

## Interactive Features

| Feature | Implementation |
|---------|---------------|
| Image lightbox (click to zoom) | Pure JS `openLightbox()` |
| Collapsible subsections | HTML `<details>` + CSS |
| Sortable/searchable tables | DataTables 1.13.6 (CDN) |
| Fixed sidebar navigation | CSS `position:fixed` + IntersectionObserver |
| Scroll progress bar | JS scroll event |
| Callout boxes | CSS classes `.callout-{info,warning,success,tip}` |

**Offline mode**: All figures are base64-embedded. Tables are visible offline
but sorting/search requires CDN (jQuery + DataTables). To make fully offline,
download the CDN files and replace the `<script>` / `<link>` tags.

---

## Adapting for Different Analyses

| Analysis | Key figures | Key tables |
|----------|-------------|------------|
| Bulk DEG | PCA, volcano, heatmap | DEG results, GSEA |
| scRNA-seq | UMAP, dotplot, violin | Marker genes, cell counts |
| hdWGCNA | Dendrogram, module UMAP, trait heatmap | Hub genes, DME, preservation |
| Proteomics | Volcano, heatmap, PCA | Protein DE results |
| ATAC-seq | Peak heatmap, motif enrichment | DA peaks, TF motifs |
| Spatial | Spatial feature plots | SVG results |

---

## File Size Guide

| Content | Approx size |
|---------|-------------|
| 1 PNG figure (150 DPI) | +100–500 KB |
| 10 figures | +1–5 MB |
| 500-row DataTable | +50 KB |
| CSS + JS | +30 KB |
| **Typical report (10–15 figs)** | **2–8 MB** |

---

## Requirements

```
Python >= 3.8
Standard library only: base64, csv, os, re, contextlib, datetime, typing
```

No pip installs needed. The CDN dependencies (jQuery, DataTables) are loaded
from the internet when the HTML is opened in a browser.


---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用  工具进行多角色辩论。

### 辩论规则
- **正方 3 角色**（各自独立，互相看不到）：生物学 agent / 统计学 agent / 生信 agent
- **反方 4 角色**（各自独立，互相看不到，也看不到正方）：生物学 agent / 统计学 agent / 生信 agent / 历史经验 agent
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个角色是独立的 LLM API 调用，messages 只包含自己的 prompt

### 触发场景
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）


## 🔒 审查机制（rail_review）

本 skill 执行代码前**必须**调用  进行前置审查，执行后**必须**调用  进行后置审查。

### 审查内容
- **pre 审查**：环境检查（包是否安装）→ 参数校验（参数是否合理）→ 代码审查（语法/逻辑）→ 硬件检查（内存/GPU是否够）
- **post 审查**：结果质量评估（输出是否合理）→ 图表检查（图是否生成）→ 数值检查（细胞数/基因数是否异常）→ 错误检查（有无 warning/error）

### 审查不通过
- pre 不通过 → **阻断执行**，修正后重新审查
- post 不通过 → **阻断下一步**，修正后重跑，直到通过
- 失败时调用  记录错误
- 修复成功后调用  +  替换脚本
