"""
html_report_builder.py
======================
A zero-dependency Python library for building beautiful, interactive,
single-file HTML reports for bioinformatics analyses.

Core idea
---------
Everything is plain Python string manipulation + f-strings.
No Jinja2, no React, no webpack. Just:
  - PNG figures  → base64-encoded <img> tags
  - CSV tables   → DataTables HTML (sortable, searchable)
  - Text content → styled HTML components (sections, callouts, fig-blocks)
  - CSS/JS       → inlined strings (Phylo color palette)
  - CDN deps     → jQuery + DataTables (online) or omit for offline

Usage
-----
    from html_report_builder import ReportBuilder

    rb = ReportBuilder(
        title="My Analysis Report",
        subtitle="Dataset · Method · Date",
        author="Your Name",
    )

    # Add a section
    with rb.section("network", "1. Network Analysis", "网络分析"):
        rb.add_figure(
            fig_path="figures/network.png",
            caption_en="Figure 1. Co-expression network.",
            method_zh="使用 WGCNA 构建加权共表达网络。",
            result_zh="识别出 10 个模块。",
            bio_zh="模块代表不同的生物学功能程序。",
        )
        rb.add_table(
            table_id="tbl_modules",
            csv_path="tables/modules.csv",
            title_en="Module Summary",
            title_zh="模块汇总表",
            columns=None,   # None = use all CSV columns
        )

    rb.save("report.html")

Author: Biomni (Phylo) — generated for zhangbo11
"""

import base64
import csv
import os
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ══════════════════════════════════════════════════════════════════════════════
# COLOR PALETTE  (Phylo brand)
# ══════════════════════════════════════════════════════════════════════════════
PALETTE = {
    "blue":   "#0279EE",
    "yellow": "#E9ED4C",
    "orange": "#FF9400",
    "green":  "#75A025",
    "pink":   "#FD9BED",
    "red":    "#E05C5C",
    "dark":   "#1a1a2e",
    "mid":    "#16213e",
    "light":  "#f8f9fa",
    "text":   "#2d3436",
    "muted":  "#636e72",
    "border": "#dee2e6",
}


# ══════════════════════════════════════════════════════════════════════════════
# LOW-LEVEL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def encode_image(path: str) -> str:
    """Return base64-encoded data URI for a PNG/JPG/SVG image."""
    ext = os.path.splitext(path)[1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg",
            "jpeg": "image/jpeg", "svg": "image/svg+xml",
            "gif": "image/gif"}.get(ext.lstrip("."), "image/png")
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode()
    return f"data:{mime};base64,{data}"


def read_csv(path: str) -> Tuple[List[str], List[Dict]]:
    """Return (headers, rows) from a CSV file."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        rows = [dict(r) for r in reader]
    return list(headers), rows


def fmt_number(v: str, decimals: int = 4) -> str:
    """Format a string as a float with given decimal places."""
    try:
        f = float(v)
        if abs(f) < 0.001 and f != 0:
            return f"{f:.2e}"
        return f"{f:.{decimals}f}"
    except (ValueError, TypeError):
        return str(v)


def color_badge(text: str, bg: str, text_color: str = "#fff") -> str:
    """Return a colored pill badge span."""
    return (
        f'<span style="background:{bg};color:{text_color};'
        f'padding:2px 10px;border-radius:12px;font-weight:700;'
        f'font-size:0.82em;white-space:nowrap">{text}</span>'
    )


# ══════════════════════════════════════════════════════════════════════════════
# CSS TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════

def _build_css(p: Dict = PALETTE) -> str:
    return f"""
:root {{
  --blue:{p['blue']}; --yellow:{p['yellow']}; --orange:{p['orange']};
  --green:{p['green']}; --pink:{p['pink']}; --red:{p['red']};
  --dark:{p['dark']}; --mid:{p['mid']}; --light:{p['light']};
  --text:{p['text']}; --muted:{p['muted']}; --border:{p['border']};
  --sidebar-w:240px;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#f0f2f5;
      color:var(--text);line-height:1.65;font-size:15px}}

/* ── Progress bar ── */
#progress-bar{{position:fixed;top:0;left:0;height:3px;z-index:9999;width:0%;
  background:linear-gradient(90deg,var(--blue),var(--yellow));transition:width .1s}}

/* ── Sidebar ── */
#sidebar{{position:fixed;left:0;top:0;width:var(--sidebar-w);height:100vh;
  background:var(--dark);color:#fff;overflow-y:auto;z-index:100;
  padding-bottom:24px;transition:transform .3s}}
#sidebar-logo{{padding:20px 16px 14px;border-bottom:1px solid rgba(255,255,255,.1);
  font-size:1.05em;font-weight:700;color:var(--yellow);line-height:1.3}}
#sidebar-logo span{{display:block;font-size:.7em;color:rgba(255,255,255,.45);
  font-weight:400;margin-top:4px}}
.nav-group{{padding:12px 16px 4px;font-size:.68em;text-transform:uppercase;
  letter-spacing:1px;color:rgba(255,255,255,.35)}}
.nav-item{{display:block;padding:8px 16px;color:rgba(255,255,255,.72);
  text-decoration:none;font-size:.84em;border-left:3px solid transparent;
  transition:all .18s}}
.nav-item:hover,.nav-item.active{{background:rgba(255,255,255,.08);
  color:#fff;border-left-color:var(--yellow)}}
.nav-num{{display:inline-block;width:20px;height:20px;background:rgba(255,255,255,.1);
  border-radius:50%;text-align:center;line-height:20px;font-size:.72em;margin-right:6px}}

/* ── Main ── */
#main{{margin-left:var(--sidebar-w);padding:0}}

/* ── Hero ── */
#hero{{background:linear-gradient(135deg,var(--dark) 0%,var(--mid) 60%,#0f3460 100%);
  color:#fff;padding:56px 48px 44px;position:relative;overflow:hidden}}
#hero::before{{content:'';position:absolute;top:-40%;right:-8%;width:480px;height:480px;
  background:radial-gradient(circle,rgba(2,121,238,.15) 0%,transparent 70%);
  pointer-events:none}}
#hero h1{{font-size:2em;font-weight:800;line-height:1.25;margin-bottom:6px}}
#hero h1 span{{color:var(--yellow)}}
#hero .hero-sub{{font-size:.92em;color:rgba(255,255,255,.6);margin-bottom:28px}}
.hero-stats{{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:28px}}
.stat-card{{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);
  border-radius:10px;padding:14px 20px;min-width:110px}}
.stat-num{{font-size:1.75em;font-weight:800;color:var(--yellow);line-height:1}}
.stat-label{{font-size:.72em;color:rgba(255,255,255,.5);margin-top:4px}}
.key-findings{{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);
  border-radius:10px;padding:18px 22px;margin-top:8px}}
.key-findings h3{{color:var(--yellow);margin-bottom:10px;font-size:.88em;
  text-transform:uppercase;letter-spacing:1px}}
.key-findings ul{{list-style:none;padding:0}}
.key-findings li{{padding:4px 0 4px 20px;position:relative;font-size:.88em;
  color:rgba(255,255,255,.8)}}
.key-findings li::before{{content:'→';position:absolute;left:0;color:var(--yellow)}}

/* ── Sections ── */
.report-section{{background:#fff;margin:24px 32px;border-radius:12px;
  box-shadow:0 2px 12px rgba(0,0,0,.06);overflow:hidden}}
.section-header{{background:linear-gradient(135deg,var(--dark),var(--mid));
  color:#fff;padding:22px 32px}}
.section-header h2{{font-size:1.3em;font-weight:700;margin-bottom:3px}}
.section-subtitle{{color:rgba(255,255,255,.55);font-size:.88em}}
.section-body{{padding:28px 32px}}

/* ── Subsections ── */
.subsection{{margin-bottom:32px}}
.subsection h3{{font-size:1.05em;font-weight:700;color:var(--dark);
  margin-bottom:14px;padding-bottom:7px;border-bottom:2px solid var(--yellow)}}
.zh-sub{{font-size:.78em;color:var(--muted);font-weight:400;margin-left:8px}}
details.subsection>summary{{cursor:pointer;list-style:none;padding:10px 0}}
details.subsection>summary::-webkit-details-marker{{display:none}}
details.subsection>summary h3{{display:inline-flex;align-items:center;gap:8px}}
details.subsection>summary h3::after{{content:'▼';font-size:.68em;
  color:var(--muted);transition:transform .2s}}
details.subsection[open]>summary h3::after{{transform:rotate(180deg)}}

/* ── Figure blocks ── */
.fig-block{{display:grid;grid-template-columns:1fr 1fr;gap:24px;
  margin-bottom:24px;align-items:start}}
.fig-block.full-width{{grid-template-columns:1fr}}
.fig-container{{text-align:center}}
.report-img{{max-width:100%;border-radius:8px;cursor:zoom-in;
  transition:transform .2s,box-shadow .2s;
  box-shadow:0 2px 8px rgba(0,0,0,.1)}}
.report-img:hover{{transform:scale(1.01);box-shadow:0 4px 16px rgba(0,0,0,.15)}}
.fig-caption{{font-size:.78em;color:var(--muted);margin-top:8px;font-style:italic}}
.fig-interp{{display:flex;flex-direction:column;gap:10px}}
.interp-block{{border-radius:8px;padding:11px 14px}}
.method-block{{background:#e3f2fd;border-left:3px solid #1976d2}}
.result-block{{background:#e8f5e9;border-left:3px solid #388e3c}}
.bio-block{{background:#fff8e1;border-left:3px solid #f9a825}}
.interp-label{{font-size:.72em;font-weight:700;text-transform:uppercase;
  letter-spacing:.5px;display:block;margin-bottom:4px;color:var(--muted)}}
.interp-block p{{font-size:.87em;line-height:1.6;color:var(--text)}}

/* ── Callout boxes ── */
.callout{{border-radius:6px;padding:12px 16px;margin:12px 0;font-size:.87em;line-height:1.6}}
.callout strong{{display:block;margin-bottom:3px}}
.callout-info{{background:#e3f2fd;border-left:4px solid #1976d2}}
.callout-warning{{background:#fff8e1;border-left:4px solid #f9a825}}
.callout-success{{background:#e8f5e9;border-left:4px solid #388e3c}}
.callout-tip{{background:#f3e5f5;border-left:4px solid #7b1fa2}}

/* ── Debate panel ── */
.debate-panel{{background:#faf5ff;border:1px solid #d8b4fe;border-radius:10px;
  padding:18px;margin:16px 0}}
.debate-header{{font-size:.9em;font-weight:700;color:#7b1fa2;
  margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #e9d5ff}}
.debate-round{{margin-bottom:14px;padding:10px 14px;border-radius:8px;
  background:#fff;border:1px solid #e9d5ff}}
.debate-round-title{{font-size:.82em;font-weight:700;color:#7b1fa2;margin-bottom:6px}}
.debate-args{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:8px}}
.debate-pro{{background:#e8f5e9;border-left:3px solid #388e3c;border-radius:6px;
  padding:10px 12px}}
.debate-con{{background:#ffebee;border-left:3px solid #c62828;border-radius:6px;
  padding:10px 12px}}
.debate-arg-label{{font-size:.72em;font-weight:700;text-transform:uppercase;
  letter-spacing:.5px;display:block;margin-bottom:4px}}
.debate-pro .debate-arg-label{{color:#2e7d32}}
.debate-con .debate-arg-label{{color:#c62828}}
.debate-arg-body{{font-size:.84em;line-height:1.55;color:var(--text)}}
.debate-verdict{{background:#fff3e0;border:1px solid #ffb74d;border-radius:6px;
  padding:10px 14px;margin-top:10px;font-size:.85em}}
.debate-verdict-label{{font-weight:700;color:#e65100;margin-bottom:4px}}
.debate-score{{display:inline-block;padding:2px 10px;border-radius:10px;
  font-weight:700;font-size:.8em;margin-left:8px}}
.debate-score.pro{{background:#e8f5e9;color:#2e7d32}}
.debate-score.con{{background:#ffebee;color:#c62828}}

/* ── Param source panel ── */
.param-source{{background:#f3f4f6;border-left:3px solid #6b7280;border-radius:6px;
  padding:10px 14px;margin:8px 0}}
.param-source-label{{font-size:.72em;font-weight:700;text-transform:uppercase;
  letter-spacing:.5px;color:#6b7280;display:block;margin-bottom:4px}}
.param-source-body{{font-size:.84em;line-height:1.55;color:var(--text)}}
.param-tag{{display:inline-block;padding:1px 8px;border-radius:8px;
  font-size:.72em;font-weight:600;margin:2px}}
.param-tag-kb{{background:#dbeafe;color:#1e40af}}
.param-tag-paper{{background:#d1fae5;color:#065f46}}
.param-tag-debate{{background:#f3e5f5;color:#7b1fa2}}
.param-tag-skill{{background:#fef3c7;color:#92400e}}

/* ── Conclusion debate ── */
.conclusion-debate{{background:linear-gradient(135deg,#faf5ff,#fff8e1);
  border:2px solid #d8b4fe;border-radius:12px;padding:24px;margin:20px 0}}
.conclusion-debate h3{{color:#7b1fa2;font-size:1.1em;margin-bottom:14px}}

/* ── Pipeline flow ── */
.pipeline-flow{{display:flex;flex-direction:column;align-items:center;padding:16px 0}}
.pipeline-step{{display:flex;align-items:flex-start;gap:14px;background:#f8f9fa;
  border:1px solid var(--border);border-radius:10px;padding:14px 18px;
  width:100%;max-width:680px;transition:box-shadow .2s}}
.pipeline-step:hover{{box-shadow:0 4px 12px rgba(0,0,0,.08)}}
.step-icon{{font-size:1.7em;min-width:38px;text-align:center}}
.step-title{{font-weight:700;font-size:.97em;color:var(--dark)}}
.step-subtitle{{font-size:.78em;color:var(--blue);font-weight:600;margin:2px 0}}
.step-params{{font-size:.76em;color:var(--muted);font-family:monospace;
  background:#fff;padding:2px 8px;border-radius:4px;display:inline-block;margin:3px 0}}
.step-desc{{font-size:.82em;color:var(--text);margin-top:5px;line-height:1.5}}
.pipeline-arrow{{font-size:1.1em;color:var(--muted);margin:3px 0}}

/* ── Tables ── */
.table-wrapper{{margin:14px 0;overflow-x:auto}}
table.dataTable{{font-size:.84em}}
.dataTables_wrapper .dataTables_filter input{{
  border:1px solid var(--border);border-radius:6px;padding:4px 10px}}
.dataTables_wrapper .dataTables_length select{{
  border:1px solid var(--border);border-radius:6px;padding:2px 6px}}

/* ── Lightbox ── */
#lightbox{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);
  z-index:9998;cursor:zoom-out;align-items:center;justify-content:center}}
#lightbox.active{{display:flex}}
#lightbox img{{max-width:92vw;max-height:92vh;border-radius:8px;
  box-shadow:0 8px 40px rgba(0,0,0,.5)}}
#lb-close{{position:absolute;top:20px;right:28px;color:#fff;font-size:2em;
  cursor:pointer;line-height:1;opacity:.7}}
#lb-close:hover{{opacity:1}}

/* ── Misc ── */
hr.divider{{border:none;border-top:1px solid var(--border);margin:22px 0}}
.tag{{display:inline-block;padding:2px 8px;border-radius:10px;
  font-size:.74em;font-weight:600;margin:2px}}
.tag-blue{{background:#e3f2fd;color:#1565c0}}
.tag-green{{background:#e8f5e9;color:#2e7d32}}
.tag-orange{{background:#fff3e0;color:#e65100}}
.tag-red{{background:#ffebee;color:#c62828}}

/* ── Responsive ── */
@media(max-width:900px){{
  #sidebar{{transform:translateX(-100%)}}
  #main{{margin-left:0}}
  .fig-block{{grid-template-columns:1fr}}
  .report-section{{margin:12px}}
}}
"""


# ══════════════════════════════════════════════════════════════════════════════
# JS TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════

def _build_js() -> str:
    return """
// ── Progress bar ──────────────────────────────────────────────────────────
window.addEventListener('scroll', () => {
  const h = document.documentElement;
  const pct = (h.scrollTop / (h.scrollHeight - h.clientHeight)) * 100;
  document.getElementById('progress-bar').style.width = pct + '%';
});

// ── Active nav highlight ───────────────────────────────────────────────────
const _sections = document.querySelectorAll('section[id]');
const _navItems = document.querySelectorAll('.nav-item[href^="#"]');
const _observer = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      _navItems.forEach(n => n.classList.remove('active'));
      const a = document.querySelector(`.nav-item[href="#${e.target.id}"]`);
      if (a) a.classList.add('active');
    }
  });
}, { threshold: 0.25 });
_sections.forEach(s => _observer.observe(s));

// ── Lightbox ───────────────────────────────────────────────────────────────
function openLightbox(src) {
  document.getElementById('lb-img').src = src;
  document.getElementById('lightbox').classList.add('active');
}
document.getElementById('lightbox').addEventListener('click', () => {
  document.getElementById('lightbox').classList.remove('active');
});

// ── DataTables ─────────────────────────────────────────────────────────────
$(document).ready(function () {
  $('table.dt-table').DataTable({
    pageLength: 10,
    lengthMenu: [10, 25, 50, 100],
    order: [],
    responsive: true,
    language: {
      search: "🔍 搜索:",
      lengthMenu: "显示 _MENU_ 条",
      info: "第 _START_–_END_ 条，共 _TOTAL_ 条",
      paginate: { first: "«", last: "»", next: "›", previous: "‹" }
    }
  });
});
"""


# ══════════════════════════════════════════════════════════════════════════════
# REPORT BUILDER CLASS
# ══════════════════════════════════════════════════════════════════════════════

class ReportBuilder:
    """
    Fluent builder for single-file interactive HTML reports.

    Parameters
    ----------
    title : str
        Main title shown in the hero section (English recommended).
    subtitle : str
        Subtitle line below the title (dataset · method · date).
    author : str, optional
        Author name shown in the footer.
    logo_text : str, optional
        Short text shown at the top of the sidebar (default: title).
    logo_sub : str, optional
        Sub-text below the sidebar logo.
    stats : list of (value, label) tuples, optional
        Key statistics shown as cards in the hero section.
    key_findings : list of str, optional
        Bullet points shown in the hero "Key Findings" box.
    palette : dict, optional
        Override color palette (see PALETTE constant).
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        author: str = "Biomni (Phylo)",
        logo_text: str = "",
        logo_sub: str = "",
        stats: Optional[List[Tuple[str, str]]] = None,
        key_findings: Optional[List[str]] = None,
        palette: Optional[Dict] = None,
    ):
        self.title = title
        self.subtitle = subtitle
        self.author = author
        self.logo_text = logo_text or title
        self.logo_sub = logo_sub
        self.stats = stats or []
        self.key_findings = key_findings or []
        self.palette = palette or PALETTE

        self._sections: List[Dict] = []          # list of {id, title_en, title_zh, nav_group, blocks}
        self._current_section: Optional[Dict] = None
        self._nav_groups: List[Tuple[str, List]] = []  # [(group_label, [section_ids])]
        self._current_nav_group: Optional[str] = None

    # ── Context manager for sections ──────────────────────────────────────────

    @contextmanager
    def section(
        self,
        sec_id: str,
        title_en: str,
        title_zh: str = "",
        nav_group: str = "",
    ):
        """
        Context manager that opens a new report section.

        Usage::

            with rb.section("network", "1. Network Analysis", "网络分析"):
                rb.add_figure(...)
                rb.add_table(...)
        """
        sec = {
            "id": sec_id,
            "title_en": title_en,
            "title_zh": title_zh,
            "nav_group": nav_group,
            "blocks": [],
        }
        self._sections.append(sec)
        self._current_section = sec
        try:
            yield self
        finally:
            self._current_section = None

    def _add_block(self, html: str):
        if self._current_section is None:
            raise RuntimeError("add_* methods must be called inside a `with rb.section(...)` block.")
        self._current_section["blocks"].append(html)

    # ── Figure block ──────────────────────────────────────────────────────────

    def add_figure(
        self,
        fig_path: str,
        caption_en: str,
        method_zh: str = "",
        result_zh: str = "",
        bio_zh: str = "",
        param_source_zh: str = "",
        title_en: str = "",
        title_zh: str = "",
        full_width: bool = False,
        collapsible: bool = True,
    ):
        """
        Add a figure with bilingual interpretation panels.

        Parameters
        ----------
        fig_path : str
            Path to the image file (PNG/JPG/SVG).
        caption_en : str
            English figure caption shown below the image.
        method_zh : str
            Chinese text for the "📐 方法" panel (blue).
        result_zh : str
            Chinese text for the "📊 结果" panel (green).
        bio_zh : str
            Chinese text for the "🧬 生物学意义" panel (yellow).
        title_en : str
            Subsection title (English). Defaults to caption_en[:60].
        title_zh : str
            Subsection title (Chinese).
        full_width : bool
            If True, figure takes full width (no side-by-side layout).
        collapsible : bool
            If True, wrap in a <details> collapsible block.
        """
        title_en = title_en or caption_en[:70]
        b64_src = encode_image(fig_path)

        interp_panels = ""
        if param_source_zh:
            interp_panels += f"""<div class="param-source">
  <span class="param-source-label">📚 参数来源</span><p class="param-source-body">{param_source_zh}</p></div>"""
        if method_zh:
            interp_panels += f"""<div class="interp-block method-block">
  <span class="interp-label">📐 方法</span><p>{method_zh}</p></div>"""
        if result_zh:
            interp_panels += f"""<div class="interp-block result-block">
  <span class="interp-label">📊 结果</span><p>{result_zh}</p></div>"""
        if bio_zh:
            interp_panels += f"""<div class="interp-block bio-block">
  <span class="interp-label">🧬 生物学意义</span><p>{bio_zh}</p></div>"""

        fw_cls = " full-width" if full_width else ""
        fig_html = f"""
<div class="fig-block{fw_cls}">
  <div class="fig-container">
    <img src="{b64_src}" alt="{caption_en}" class="report-img"
         onclick="openLightbox(this.src)">
    <p class="fig-caption"><em>{caption_en}</em></p>
  </div>
  <div class="fig-interp">{interp_panels}</div>
</div>"""

        zh_span = f'<span class="zh-sub">{title_zh}</span>' if title_zh else ""
        if collapsible:
            block = f"""<details class="subsection" open>
  <summary><h3>{title_en} {zh_span}</h3></summary>
  {fig_html}
</details>"""
        else:
            block = f"""<div class="subsection">
  <h3>{title_en} {zh_span}</h3>
  {fig_html}
</div>"""

        self._add_block(block)

    # ── Table block ───────────────────────────────────────────────────────────

    def add_table(
        self,
        table_id: str,
        csv_path: str,
        title_en: str = "Data Table",
        title_zh: str = "",
        columns: Optional[List[Tuple[str, str]]] = None,
        fmt: Optional[Dict] = None,
        tip: str = "",
        max_rows: int = 500,
    ):
        """
        Add an interactive DataTable from a CSV file.

        Parameters
        ----------
        table_id : str
            Unique HTML id for the <table> element.
        csv_path : str
            Path to the CSV file.
        title_en : str
            Subsection title (English).
        title_zh : str
            Subsection title (Chinese).
        columns : list of (csv_key, display_label), optional
            Subset and rename columns. None = use all columns.
        fmt : dict, optional
            {csv_key: callable} for custom cell formatting.
        tip : str, optional
            Tip text shown in a callout above the table.
        max_rows : int
            Maximum rows to include (default 500).
        """
        headers, rows = read_csv(csv_path)
        fmt = fmt or {}

        if columns is None:
            columns = [(h, h) for h in headers]

        thead = "".join(f"<th>{label}</th>" for _, label in columns)
        tbody_rows = []
        for row in rows[:max_rows]:
            cells = []
            for key, _ in columns:
                val = row.get(key, "")
                if key in fmt:
                    val = fmt[key](val)
                cells.append(f"<td>{val}</td>")
            tbody_rows.append("<tr>" + "".join(cells) + "</tr>")
        tbody = "\n".join(tbody_rows)

        table_html = f"""
<table id="{table_id}" class="display compact dt-table" style="width:100%">
  <thead><tr>{thead}</tr></thead>
  <tbody>{tbody}</tbody>
</table>"""

        tip_html = ""
        if tip:
            tip_html = f'<div class="callout callout-tip"><strong>💡 使用提示</strong>{tip}</div>'

        zh_span = f'<span class="zh-sub">{title_zh}</span>' if title_zh else ""
        block = f"""<div class="subsection">
  <h3>{title_en} {zh_span}</h3>
  {tip_html}
  <div class="table-wrapper">{table_html}</div>
</div>"""
        self._add_block(block)

    # ── Debate record block ──────────────────────────────────────────────────

    def add_debate(
        self,
        topic: str,
        rounds: List[Dict],
        title_en: str = "Parameter Debate",
        title_zh: str = "参数辩论记录",
    ):
        """
        Add a debate record panel showing pro/con arguments and verdict.

        Parameters
        ----------
        topic : str
            The debated topic/parameter.
        rounds : list of dicts, each with keys:
            round (int)       : round number (1, 2, 3...)
            pro (str)          : proponent argument
            con (str)          : opponent argument
            verdict (str)      : judge's verdict
            pro_score (int)    : proponent score (0-10)
            con_score (int)    : opponent score (0-10)
            action (str)       : action taken after this round
        title_en : str
            Section title (English).
        title_zh : str
            Section title (Chinese).
        """
        rounds_html = ""
        for r in rounds:
            pro_score = r.get("pro_score", 0)
            con_score = r.get("con_score", 0)
            action_html = ""
            if r.get("action"):
                action_html = f'<div class="debate-verdict"><span class="debate-verdict-label">裁决后行动:</span> {r["action"]}</div>'
            rounds_html += f"""
<div class="debate-round">
  <div class="debate-round-title">第 {r.get('round', 1)} 轮辩论
    <span class="debate-score pro">正方 {pro_score}</span>
    <span class="debate-score con">反方 {con_score}</span>
  </div>
  <div class="debate-args">
    <div class="debate-pro">
      <span class="debate-arg-label">✅ 正方 (支持)</span>
      <p class="debate-arg-body">{r.get('pro', '')}</p>
    </div>
    <div class="debate-con">
      <span class="debate-arg-label">❌ 反方 (质疑)</span>
      <p class="debate-arg-body">{r.get('con', '')}</p>
    </div>
  </div>
  <div class="debate-verdict">
    <span class="debate-verdict-label">⚖️ 裁判决断:</span> {r.get('verdict', '')}
  </div>
  {action_html}
</div>"""

        block = f"""
<div class="debate-panel">
  <div class="debate-header">🗣️ {title_en} <span style="font-size:.8em;color:#636e72">/ {title_zh}</span></div>
  <div style="font-size:.85em;color:var(--muted);margin-bottom:10px">辩论主题: {topic}</div>
  {rounds_html}
</div>"""
        self._add_block(block)

    # ── Param source block ───────────────────────────────────────────────────

    def add_param_source(
        self,
        sources: List[Dict],
        title_en: str = "Parameter Sources",
        title_zh: str = "参数来源",
    ):
        """
        Add a parameter source traceability panel.

        Parameters
        ----------
        sources : list of dicts with keys:
            param (str)      : parameter name
            value (str)      : parameter value used
            source (str)     : 'knowledge_base', 'literature', 'debate', 'skill', 'default'
            citation (str)   : citation or reference
            note (str)       : optional note
        """
        source_tags = {
            "knowledge_base": '<span class="param-tag param-tag-kb">知识库</span>',
            "literature": '<span class="param-tag param-tag-paper">文献</span>',
            "debate": '<span class="param-tag param-tag-debate">辩论</span>',
            "skill": '<span class="param-tag param-tag-skill">Skill</span>',
            "default": '<span class="param-tag" style="background:#f3f4f6;color:#6b7280">默认</span>',
        }
        rows_html = ""
        for s in sources:
            tag = source_tags.get(s.get("source", "default"), source_tags["default"])
            citation = f' — <em>{s.get("citation", "")}</em>' if s.get("citation") else ""
            note = f' <span style="color:var(--muted);font-size:.85em">({s.get("note")})</span>' if s.get("note") else ""
            rows_html += f"""
<div class="param-source">
  <span class="param-source-label">{s.get('param', '')} = {s.get('value', '')}</span>
  <p class="param-source-body">{tag}{citation}{note}</p>
</div>"""

        zh_span = f'<span class="zh-sub">{title_zh}</span>' if title_zh else ""
        block = f"""
<div class="subsection">
  <h3>{title_en} {zh_span}</h3>
  {rows_html}
</div>"""
        self._add_block(block)

    # ── Conclusion debate block ───────────────────────────────────────────────

    def add_conclusion_debate(
        self,
        conclusion: str,
        pro_argument: str,
        con_argument: str,
        verdict: str,
        confidence: str = "",
    ):
        """
        Add a conclusion debate panel — debate the final conclusion itself.

        Parameters
        ----------
        conclusion : str
            The final conclusion being debated.
        pro_argument : str
            Arguments supporting the conclusion.
        con_argument : str
            Arguments questioning the conclusion.
        verdict : str
            Final verdict after debate.
        confidence : str
            Confidence level (high/medium/low) with reasoning.
        """
        confidence_html = ""
        if confidence:
            confidence_html = f'<div class="debate-verdict"><span class="debate-verdict-label">置信度:</span> {confidence}</div>'

        block = f"""
<div class="conclusion-debate">
  <h3>🔍 结论辩论 / Conclusion Debate</h3>
  <div style="font-size:.9em;margin-bottom:14px;padding:10px 14px;background:#fff;border-radius:6px">
    <strong>结论:</strong> {conclusion}
  </div>
  <div class="debate-args">
    <div class="debate-pro">
      <span class="debate-arg-label">✅ 支持论据</span>
      <p class="debate-arg-body">{pro_argument}</p>
    </div>
    <div class="debate-con">
      <span class="debate-arg-label">❌ 质疑论据</span>
      <p class="debate-arg-body">{con_argument}</p>
    </div>
  </div>
  <div class="debate-verdict">
    <span class="debate-verdict-label">⚖️ 最终裁决:</span> {verdict}
  </div>
  {confidence_html}
</div>"""
        self._add_block(block)

    # ── Raw HTML block ────────────────────────────────────────────────────────

    def add_html(self, html: str):
        """Add arbitrary HTML directly into the current section."""
        self._add_block(html)

    # ── Callout block ─────────────────────────────────────────────────────────

    def add_callout(
        self,
        kind: str,
        title: str,
        body: str,
    ):
        """
        Add a callout box.

        Parameters
        ----------
        kind : str
            One of: 'info', 'warning', 'success', 'tip'
        title : str
            Bold title line.
        body : str
            Body text (HTML allowed).
        """
        icons = {"info": "ℹ️", "warning": "⚠️", "success": "✅", "tip": "💡"}
        icon = icons.get(kind, "ℹ️")
        block = f"""<div class="callout callout-{kind}">
  <strong>{icon} {title}</strong>{body}
</div>"""
        self._add_block(block)

    # ── Pipeline flowchart ────────────────────────────────────────────────────

    def add_pipeline(
        self,
        steps: List[Dict],
    ):
        """
        Add a vertical pipeline flowchart.

        Parameters
        ----------
        steps : list of dicts with keys:
            icon (str)       : emoji icon
            title (str)      : step name
            subtitle (str)   : short subtitle
            params (str)     : key parameters (shown in monospace)
            desc (str)       : longer description (optional)
        """
        html = '<div class="pipeline-flow">'
        for i, s in enumerate(steps):
            desc_html = f'<div class="step-desc">{s["desc"]}</div>' if s.get("desc") else ""
            param_src_html = ""
            if s.get("param_source"):
                param_src_html = f'<div class="param-source" style="margin:6px 0"><span class="param-source-label">📚 参数来源</span><p class="param-source-body">{s["param_source"]}</p></div>'
            html += f"""<div class="pipeline-step">
  <div class="step-icon">{s.get('icon','⚙️')}</div>
  <div class="step-content">
    <div class="step-title">{s['title']}</div>
    <div class="step-subtitle">{s.get('subtitle','')}</div>
    <div class="step-params">{s.get('params','')}</div>
    {param_src_html}
    {desc_html}
  </div>
</div>"""
            if i < len(steps) - 1:
                html += '<div class="pipeline-arrow">▼</div>'
        html += "</div>"
        self._add_block(html)

    # ── Stat cards (can also be added inside sections) ────────────────────────

    def add_stat_cards(self, stats: List[Tuple[str, str]]):
        """Add a row of stat cards (value, label) inside a section."""
        cards = "".join(
            f'<div class="stat-card" style="background:#f8f9fa;border:1px solid var(--border);'
            f'border-radius:10px;padding:12px 18px;display:inline-block;margin:6px">'
            f'<div class="stat-num" style="color:var(--blue)">{v}</div>'
            f'<div class="stat-label" style="color:var(--muted)">{l}</div></div>'
            for v, l in stats
        )
        self._add_block(f'<div style="margin:12px 0">{cards}</div>')

    # ══════════════════════════════════════════════════════════════════════════
    # RENDER
    # ══════════════════════════════════════════════════════════════════════════

    def _render_hero(self) -> str:
        stats_html = "".join(
            f'<div class="stat-card"><div class="stat-num">{v}</div>'
            f'<div class="stat-label">{l}</div></div>'
            for v, l in self.stats
        )
        findings_html = ""
        if self.key_findings:
            items = "".join(f"<li>{f}</li>" for f in self.key_findings)
            findings_html = f"""<div class="key-findings">
  <h3>🔑 Key Findings</h3>
  <ul>{items}</ul>
</div>"""

        # Split title at first newline or <br> for yellow span
        title_parts = re.split(r"\n|<br\s*/?>", self.title, maxsplit=1)
        title_html = title_parts[0]
        if len(title_parts) > 1:
            title_html += f"<br><span>{title_parts[1]}</span>"

        return f"""<section id="hero">
  <h1>{title_html}</h1>
  <p class="hero-sub">{self.subtitle}</p>
  <div class="hero-stats">{stats_html}</div>
  {findings_html}
</section>"""

    def _render_sidebar(self) -> str:
        # Auto-build nav from sections
        nav_html = ""
        # Group sections by nav_group
        groups: Dict[str, List] = {}
        for sec in self._sections:
            g = sec.get("nav_group", "") or ""
            groups.setdefault(g, []).append(sec)

        nav_html += f'<a class="nav-item" href="#hero"><span class="nav-num">0</span>Summary</a>'
        num = 1
        for group, secs in groups.items():
            if group:
                nav_html += f'<div class="nav-group">{group}</div>'
            for sec in secs:
                label = sec["title_en"]
                # Shorten label for sidebar
                short = label.split(".")[-1].strip() if "." in label else label
                short = short[:28]
                nav_html += (
                    f'<a class="nav-item" href="#{sec["id"]}">'
                    f'<span class="nav-num">{num}</span>{short}</a>'
                )
                num += 1

        return f"""<div id="sidebar">
  <div id="sidebar-logo">{self.logo_text}<span>{self.logo_sub}</span></div>
  {nav_html}
</div>"""

    def _render_sections(self) -> str:
        html = ""
        for sec in self._sections:
            body = "\n".join(sec["blocks"])
            zh_sub = (
                f'<p class="section-subtitle">{sec["title_zh"]}</p>'
                if sec["title_zh"] else ""
            )
            html += f"""
<section id="{sec['id']}" class="report-section">
  <div class="section-header">
    <h2>{sec['title_en']}</h2>
    {zh_sub}
  </div>
  <div class="section-body">
    {body}
  </div>
</section>"""
        return html

    def _render_footer(self) -> str:
        date = datetime.now().strftime("%Y-%m-%d")
        return f"""<footer style="background:var(--dark);color:rgba(255,255,255,.45);
  text-align:center;padding:28px;margin-top:36px;font-size:.8em">
  <p>{self.title} &nbsp;|&nbsp; {self.author} &nbsp;|&nbsp; {date}</p>
</footer>"""

    def render(self) -> str:
        """Render the complete HTML as a string."""
        css = _build_css(self.palette)
        js = _build_js()
        hero = self._render_hero()
        sidebar = self._render_sidebar()
        sections = self._render_sections()
        footer = self._render_footer()

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{self.title}</title>
  <link rel="stylesheet"
    href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
  <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
  <style>{css}</style>
</head>
<body>

<div id="progress-bar"></div>

<!-- Lightbox -->
<div id="lightbox">
  <span id="lb-close"
    onclick="document.getElementById('lightbox').classList.remove('active')">✕</span>
  <img id="lb-img" src="" alt="enlarged figure">
</div>

{sidebar}

<div id="main">
  {hero}
  {sections}
  {footer}
</div>

<script>{js}</script>
</body>
</html>"""

    def save(self, output_path: str) -> str:
        """
        Render and save the HTML report to a file.

        Returns the output path.
        """
        html = self.render()
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        size_kb = os.path.getsize(output_path) / 1024
        print(f"[ReportBuilder] Saved: {output_path}  ({size_kb:.0f} KB)")
        return output_path
