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

        # 问题5: 4 面板必填检查——传空直接报错，防止偷懒
        _missing = []
        if not method_zh or not str(method_zh).strip():
            _missing.append("method_zh")
        if not result_zh or not str(result_zh).strip():
            _missing.append("result_zh")
        if not bio_zh or not str(bio_zh).strip():
            _missing.append("bio_zh")
        if not param_source_zh or not str(param_source_zh).strip():
            _missing.append("param_source_zh")
        if _missing:
            raise ValueError(
                f"add_figure 面板必填检查失败: {', '.join(_missing)} 不能为空。"
                f"图片 {fig_path} 的 4 个面板全部必填，禁止偷懒。"
            )

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

    # ══════════════════════════════════════════════════════════════════════════
    # AUTO-FILL FROM LOGS — 从日志自动填充报告内容
    # ══════════════════════════════════════════════════════════════════════════

    def auto_fill_from_logs(self, session_data: dict):
        """从 collect_session_data() 返回的数据自动填充报告。

        会自动添加以下 section（如果数据存在）：
        1. "日志溯源" — 展示数据来源和统计
        2. "工具调用记录" — 列出本次会话所有工具调用
        3. "Skill 经验日志" — 列出遇到的错误和修复方案
        4. "运行归档" — 从 results/log/ 加载运行记录
        5. "辩论归档" — 从 results/log/ 加载辩论 JSON

        Parameters
        ----------
        session_data : dict
            collect_session_data() 返回的完整数据结构
        """
        meta = session_data.get("meta", {})
        session_id = session_data.get("session_id", "unknown")

        # 1. 日志溯源 section
        with self.section("log_trace", "Log Trace", "日志溯源", nav_group="日志"):
            self.add_log_trace(session_data)

        # 2. 工具调用记录
        tool_calls = session_data.get("state_db", {}).get("tool_calls", [])
        if tool_calls:
            with self.section("tool_log", "Tool Call History", "工具调用记录", nav_group="日志"):
                self.add_tool_call_log(tool_calls)

        # 3. Skill 经验日志（错误记录）
        error_logs = session_data.get("skill_logs", {}).get("error_logs", [])
        if error_logs:
            with self.section("skill_errors", "Skill Error Log", "Skill经验日志", nav_group="日志"):
                self.add_skill_error_log(error_logs)

        # 4. 运行归档记录
        run_records = session_data.get("results_log", {}).get("run_records", [])
        if run_records:
            with self.section("run_archive", "Run Archive", "运行归档", nav_group="日志"):
                self.add_run_archive(run_records)

        # 5. 辩论记录归档
        debate_records = session_data.get("results_log", {}).get("debate_records", [])
        if debate_records:
            with self.section("debate_archive", "Debate Archive", "辩论归档", nav_group="日志"):
                self.add_debate_archive(debate_records)

        print(f"[ReportBuilder] auto_fill_from_logs: "
              f"{meta.get('message_count', 0)} messages, "
              f"{meta.get('tool_call_count', 0)} tool calls, "
              f"{meta.get('error_log_count', 0)} errors, "
              f"{meta.get('run_record_count', 0)} run records, "
              f"{meta.get('debate_record_count', 0)} debates")

        # 6. 从工具调用记录中提取 add_figure 图解读和 debate_analysis 辩论
        self._auto_fill_figures_and_debates_from_tool_calls(tool_calls)

    # ── Auto-extract figures and debates from tool calls ─────────────────────

    def _auto_fill_figures_and_debates_from_tool_calls(self, tool_calls: list):
        """从结构化工具调用记录中提取 add_figure 和 debate_analysis 的参数，
        自动生成图解读面板和辩论记录面板。

        这解决了"LLM 上下文丢失导致报告缺图缺辩论"的问题——
        直接从持久化的工具调用记录中恢复，不依赖 LLM 记忆。

        add_figure 工具调用参数中的 fig_path/caption_en/method_zh/result_zh/bio_zh/param_source_zh
        会被提取并自动调用 self.add_figure()。

        debate_analysis 工具调用参数中的 topic/rounds 会被提取并自动调用 self.add_debate()。
        """
        figures_added = 0
        debates_added = 0

        for tc in tool_calls:
            tool_name = tc.get("tool_name", "")
            args = tc.get("args") or {}

            # 提取 add_figure 调用
            if tool_name == "add_figure" and isinstance(args, dict):
                fig_path = args.get("fig_path", "")
                if not fig_path:
                    continue
                try:
                    with self.section(
                        f"fig_{figures_added+1}",
                        args.get("title_en") or args.get("caption_en", "")[:70],
                        args.get("title_zh") or "图解读",
                        nav_group="图表",
                    ):
                        try:
                            self.add_figure(
                                fig_path=fig_path,
                                caption_en=args.get("caption_en", ""),
                                method_zh=args.get("method_zh", ""),
                                result_zh=args.get("result_zh", ""),
                                bio_zh=args.get("bio_zh", ""),
                                param_source_zh=args.get("param_source_zh", ""),
                                title_en=args.get("title_en", ""),
                                title_zh=args.get("title_zh", ""),
                                full_width=args.get("full_width", False),
                            )
                            figures_added += 1
                        except Exception as e:
                            # 图片文件可能不存在，在 section 内部添加警告
                            self.add_html(f"<div class='callout callout-warning'>"
                                          f"<strong>⚠️ 图片缺失</strong>: {fig_path} — {e}</div>")
                except Exception:
                    pass  # section 创建失败，跳过

            # 提取 debate_analysis 调用
            # debate_analysis 工具参数是 topic+context，返回的是辩论 prompt/instructions
            # 辩论的 rounds 在 LLM 后续回复中，不在工具调用参数里
            # 所以这里从 result_text 中尝试解析 JSON 辩论结果
            elif tool_name == "debate_analysis" and isinstance(args, dict):
                topic = args.get("topic", "")
                if not topic:
                    continue
                # 尝试从 result_text 中解析辩论结果
                result_text = tc.get("result_text", "")
                rounds = []
                try:
                    import json as _dj
                    result_obj = _dj.loads(result_text) if result_text.strip().startswith("{") else None
                    if result_obj and isinstance(result_obj, dict):
                        rounds = result_obj.get("rounds") or result_obj.get("debate_rounds") or []
                except Exception:
                    pass
                # 如果没有 rounds，用 context 构造一个简化辩论记录
                if not rounds:
                    context = args.get("context", "")
                    rounds = [{
                        "round": 1,
                        "pro": "(辩论详情见会话记录)",
                        "con": "(辩论详情见会话记录)",
                        "verdict": result_text[:200] if result_text else "(见辩论结果)",
                        "pro_score": 0,
                        "con_score": 0,
                        "action": "",
                    }]
                try:
                    with self.section(
                        f"debate_{debates_added+1}",
                        f"Debate: {topic[:50]}",
                        f"辩论: {topic[:30]}",
                        nav_group="辩论",
                    ):
                        self.add_debate(
                            topic=topic,
                            rounds=rounds,
                            title_en=f"Debate: {topic[:50]}",
                            title_zh=f"辩论: {topic[:30]}",
                        )
                    debates_added += 1
                except Exception:
                    pass

            # 提取 generate_report 调用中的 add_conclusion_debate 参数
            # generate_report 工具的参数中可能包含 conclusion_debate 字段
            elif tool_name == "generate_report" and isinstance(args, dict):
                conc = args.get("conclusion_debate") or args.get("conclusion") or {}
                if isinstance(conc, dict) and conc.get("conclusion"):
                    try:
                        with self.section(
                            f"conclusion_debate",
                            "Conclusion Debate",
                            "结论辩论",
                            nav_group="辩论",
                        ):
                            self.add_conclusion_debate(
                                conclusion=conc.get("conclusion", ""),
                                pro_argument=conc.get("pro_argument", ""),
                                con_argument=conc.get("con_argument", ""),
                                verdict=conc.get("verdict", ""),
                                confidence=conc.get("confidence", ""),
                            )
                        debates_added += 1
                    except Exception:
                        pass

        if figures_added or debates_added:
            print(f"[ReportBuilder] _auto_fill_figures_and_debates: "
                  f"{figures_added} figures, {debates_added} debates extracted from tool calls")

    # ── Log trace component ──────────────────────────────────────────────────

    def add_log_trace(self, session_data: dict):
        """添加日志溯源面板——展示数据来源和统计。"""
        meta = session_data.get("meta", {})
        session_id = session_data.get("session_id", "unknown")

        # 统计卡片
        stats = [
            (str(meta.get("message_count", 0)), "会话消息"),
            (str(meta.get("tool_call_count", 0)), "工具调用"),
            (str(meta.get("error_log_count", 0)), "错误记录"),
            (str(meta.get("run_record_count", 0)), "运行归档"),
            (str(meta.get("debate_record_count", 0)), "辩论记录"),
            (str(meta.get("log_line_count", 0)), "日志行数"),
        ]
        self.add_stat_cards(stats)

        # 数据来源
        sources_html = "<div class='subsection'><h3>数据来源 / Data Sources</h3>"
        sources = [
            ("hermes_home/logs/agent.log", "系统运行日志", meta.get("log_line_count", 0) > 0),
            ("hermes_home/state.db", "会话消息+工具调用", meta.get("message_count", 0) > 0),
            ("hermes_home/skills/.../logs/", "Skill经验日志", meta.get("error_log_count", 0) > 0),
            ("work/results/&lt;sid&gt;/log/", "运行归档", meta.get("run_record_count", 0) > 0),
        ]
        for path, desc, ok in sources:
            status = "✅" if ok else "❌"
            sources_html += (
                f"<div class='param-source'>"
                f"<span class='param-source-label'>{status} {path}</span>"
                f"<p class='param-source-body'>{desc}</p></div>"
            )
        sources_html += "</div>"
        self.add_html(sources_html)

        # 会话元数据
        session_meta = session_data.get("state_db", {}).get("session_meta", {})
        if session_meta:
            meta_html = "<div class='subsection'><h3>会话元数据 / Session Metadata</h3>"
            meta_html += "<table class='display compact dt-table' style='width:100%'><tbody>"
            for k, v in session_meta.items():
                if v is not None and str(v).strip():
                    meta_html += f"<tr><td style='font-weight:700;width:200px'>{k}</td><td>{v}</td></tr>"
            meta_html += "</tbody></table></div>"
            self.add_html(meta_html)

    # ── Tool call log component ──────────────────────────────────────────────

    def add_tool_call_log(self, tool_calls: list):
        """添加工具调用记录表。

        支持两种数据格式：
        1. 结构化（来自 tool_calls_log 表）：有 tool_name, args, result_text 字段
        2. 旧格式（从 content 识别）：有 tool_name, content 字段
        """
        rows_html = ""
        for i, tc in enumerate(tool_calls):
            tool_name = tc.get("tool_name") or "—"
            timestamp = tc.get("timestamp") or ""
            # 优先用 result_text（结构化），降级用 content（旧格式）
            summary = tc.get("result_text") or tc.get("content") or ""
            # 如果有 args，展示参数摘要
            args = tc.get("args")
            if args and isinstance(args, dict):
                args_summary = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(args.items())[:4])
                if args_summary:
                    summary = f"[{args_summary}] {summary}"
            if len(summary) > 250:
                summary = summary[:250] + "..."
            summary = summary.replace("<", "&lt;").replace(">", "&gt;")
            # 格式化时间戳
            if isinstance(timestamp, (int, float)):
                import datetime as _dt
                timestamp = _dt.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
            rows_html += (
                f"<tr>"
                f"<td>{i+1}</td>"
                f"<td><strong>{tool_name}</strong></td>"
                f"<td style='font-size:.82em'>{timestamp}</td>"
                f"<td style='font-size:.82em;color:var(--muted)'>{summary}</td>"
                f"</tr>"
            )

        table_html = f"""
<table class="display compact dt-table" style="width:100%">
  <thead><tr><th>#</th><th>工具</th><th>时间</th><th>参数+结果摘要</th></tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""
        self.add_html(f"<div class='table-wrapper'>{table_html}</div>")

    # ── Skill error log component ────────────────────────────────────────────

    def add_skill_error_log(self, error_logs: list):
        """添加 Skill 经验日志——错误和修复方案。"""
        self.add_callout(
            "warning",
            "经验日志",
            f"本次分析（或历史分析）共记录了 {len(error_logs)} 条错误经验，"
            f"这些错误已自动修复并记录到 skill 经验库中，后续分析可避免重复踩坑。",
        )

        rows_html = ""
        for err in error_logs:
            severity = err.get("severity", "")
            sev_color = {"high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"}.get(severity, "#636e72")
            sev_badge = f'<span style="background:{sev_color};color:#fff;padding:2px 8px;border-radius:10px;font-size:.8em">{severity}</span>' if severity else ""
            rows_html += f"""
<tr>
  <td style='font-size:.82em'>{err.get('date', '')}</td>
  <td><strong>{err.get('skill', '')}</strong></td>
  <td style='font-size:.82em'>{err.get('error', '')[:100]}</td>
  <td style='font-size:.82em'>{err.get('root_cause', '')[:80]}</td>
  <td style='font-size:.82em'>{err.get('fix', '')[:100]}</td>
  <td>{err.get('species', '')} / {err.get('tissue', '')}</td>
  <td>{sev_badge}</td>
</tr>"""

        table_html = f"""
<table class="display compact dt-table" style="width:100%">
  <thead><tr>
    <th>日期</th><th>Skill</th><th>错误</th><th>根因</th><th>修复方案</th><th>物种/组织</th><th>严重度</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>"""
        self.add_html(f"<div class='table-wrapper'>{table_html}</div>")

    # ── Run archive component ────────────────────────────────────────────────

    def add_run_archive(self, run_records: list):
        """添加运行归档记录。"""
        for i, rec in enumerate(run_records):
            title = rec.get("title") or rec.get("module") or f"Run #{i+1}"
            timestamp = rec.get("timestamp") or rec.get("date") or ""
            params = rec.get("params") or rec.get("parameters") or {}
            result_summary = rec.get("result_summary") or rec.get("result") or ""
            success = rec.get("success", True)
            file_path = rec.get("_file", "")

            status_badge = (
                '<span style="background:#27ae60;color:#fff;padding:2px 10px;border-radius:10px;font-size:.8em">成功</span>'
                if success else
                '<span style="background:#e74c3c;color:#fff;padding:2px 10px;border-radius:10px;font-size:.8em">失败</span>'
            )

            block = f"""
<div class="subsection">
  <h3>{title} {status_badge} <span style="font-size:.78em;color:var(--muted)">{timestamp}</span></h3>"""

            if params and isinstance(params, dict):
                param_rows = "".join(
                    f"<tr><td style='font-weight:700;width:200px'>{k}</td><td><code>{v}</code></td></tr>"
                    for k, v in params.items()
                )
                block += f"""
  <table class="display compact dt-table" style="width:100%">
    <thead><tr><th>参数</th><th>值</th></tr></thead>
    <tbody>{param_rows}</tbody>
  </table>"""

            if result_summary:
                result_text = str(result_summary)[:500].replace("<", "&lt;").replace(">", "&gt;")
                block += f"""
  <div class="callout callout-info">
    <strong>📊 结果摘要</strong>{result_text}
  </div>"""

            block += f"""
  <div style="font-size:.78em;color:var(--muted);margin-top:8px">来源: {file_path}</div>
</div>"""
            self.add_html(block)

    # ── Debate archive component ─────────────────────────────────────────────

    def add_debate_archive(self, debate_records: list):
        """添加辩论记录归档。"""
        for i, rec in enumerate(debate_records):
            topic = rec.get("topic") or rec.get("title") or f"Debate #{i+1}"
            rounds = rec.get("rounds") or rec.get("debate_rounds") or []
            timestamp = rec.get("timestamp") or rec.get("date") or ""
            file_path = rec.get("_file", "")

            if rounds and isinstance(rounds, list):
                self.add_debate(
                    topic=topic,
                    rounds=rounds,
                    title_en=f"Archived Debate: {topic[:50]}",
                    title_zh=f"辩论归档: {topic[:30]}",
                )
            else:
                conclusion = rec.get("conclusion") or rec.get("verdict") or ""
                block = f"""
<div class="subsection">
  <h3>🗣️ {topic} <span style="font-size:.78em;color:var(--muted)">{timestamp}</span></h3>
  <div class="callout callout-info"><strong>结论:</strong> {conclusion}</div>
  <div style="font-size:.78em;color:var(--muted);margin-top:8px">来源: {file_path}</div>
</div>"""
                self.add_html(block)


# ══════════════════════════════════════════════════════════════════════════════
# SESSION LOG COLLECTOR — 从五层日志源收集会话数据
# ══════════════════════════════════════════════════════════════════════════════

def _find_project_root() -> str:
    """动态查找 MemOmics-Agent 项目根目录。"""
    # 1. 从环境变量
    root = os.environ.get("MEMOMICS_PROJECT_ROOT", "")
    if root and os.path.isdir(root):
        return root
    # 2. 从本文件向上查找
    p = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.isdir(os.path.join(p, "hermes_home")) and os.path.isdir(os.path.join(p, "memomics")):
            return p
        p = os.path.dirname(p)
    # 3. 回退到默认
    return "MEMOMICS_HOME"


def _collect_from_state_db(project_root: str, session_id: str) -> dict:
    """从 state.db 收集会话消息和工具调用记录（第二层日志）。"""
    result = {"messages": [], "tool_calls": [], "session_meta": {}}
    db_path = os.path.join(project_root, "hermes_home", "state.db")
    if not os.path.exists(db_path):
        return result
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 会话元数据
        try:
            cur.execute(
                "SELECT id, model, started_at, message_count, tool_call_count, "
                "input_tokens, output_tokens, title, cwd FROM sessions WHERE id=?",
                (session_id,),
            )
            row = cur.fetchone()
            if row:
                result["session_meta"] = dict(row)
        except Exception:
            pass

        # 消息记录
        try:
            cur.execute(
                "SELECT id, session_id, role, content, tool_name, tool_calls, "
                "timestamp, token_count FROM messages "
                "WHERE session_id=? ORDER BY id ASC",
                (session_id,),
            )
            for row in cur.fetchall():
                msg = dict(row)
                result["messages"].append(msg)
        except Exception:
            pass

        # 结构化工具调用记录（从 tool_calls_log 表读取——server.py 持久化的）
        structured_tool_calls = []
        try:
            cur.execute(
                "SELECT id, session_id, tool_name, tool_id, args_json, "
                "result_text, timestamp FROM tool_calls_log "
                "WHERE session_id=? ORDER BY id ASC",
                (session_id,),
            )
            for row in cur.fetchall():
                tc = dict(row)
                # 解析 args_json
                if tc.get("args_json"):
                    try:
                        import json as _json
                        tc["args"] = _json.loads(tc["args_json"])
                    except Exception:
                        tc["args"] = {}
                else:
                    tc["args"] = {}
                structured_tool_calls.append(tc)
        except Exception:
            pass  # tool_calls_log 表可能不存在（旧版本 state.db）

        # 如果有结构化工具调用记录，用它替代从 content 中推测的
        if structured_tool_calls:
            result["tool_calls"] = structured_tool_calls
        else:
            # 降级：从 content 中识别工具调用痕迹（旧版本兼容）
            tool_keywords = [
                "scan_data", "search_knowledge", "guide_analysis", "check_env",
                "rail_review", "skill_evolution", "skill_view", "terminal",
                "debate_analysis", "download_pdf", "search_papers",
                "todo_manage", "memomics_pipeline", "update_results_dir",
                "generate_report",
            ]
            for msg in result["messages"]:
                if msg.get("content"):
                    content_lower = msg["content"].lower()
                    for kw in tool_keywords:
                        if kw in content_lower:
                            result["tool_calls"].append(msg)
                            break

        conn.close()
    except Exception as e:
        result["_error"] = f"state.db: {e}"
    return result


def _collect_from_skill_logs(project_root: str, skill_names: list = None) -> dict:
    """从 skill 经验日志收集错误记录和成功参数（第四层日志）。

    如果 skill_names 为 None，则扫描所有 bioinformatics skill。
    """
    result = {"error_logs": [], "proven_params": {}, "skills_scanned": []}
    skills_dir = os.path.join(project_root, "hermes_home", "skills", "bioinformatics")
    if not os.path.isdir(skills_dir):
        return result

    if skill_names is None:
        skill_names = [
            d for d in os.listdir(skills_dir)
            if os.path.isdir(os.path.join(skills_dir, d))
        ]

    for skill_name in skill_names:
        skill_path = os.path.join(skills_dir, skill_name)
        result["skills_scanned"].append(skill_name)

        # error_log.md
        error_log_path = os.path.join(skill_path, "logs", "error_log.md")
        if os.path.exists(error_log_path):
            try:
                with open(error_log_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # 解析 markdown 表格行
                lines = content.split("\n")
                for line in lines:
                    line = line.strip()
                    if line.startswith("|") and not line.startswith("|---") and not line.startswith("| ---"):
                        cells = [c.strip() for c in line.split("|")[1:-1]]
                        if len(cells) >= 3 and cells[0] != "日期":
                            result["error_logs"].append({
                                "skill": skill_name,
                                "date": cells[0] if len(cells) > 0 else "",
                                "error": cells[1] if len(cells) > 1 else "",
                                "type": cells[2] if len(cells) > 2 else "",
                                "root_cause": cells[3] if len(cells) > 3 else "",
                                "fix": cells[4] if len(cells) > 4 else "",
                                "species": cells[5] if len(cells) > 5 else "",
                                "tissue": cells[6] if len(cells) > 6 else "",
                                "severity": cells[7] if len(cells) > 7 else "",
                            })
            except Exception:
                pass

        # skill.json proven_params
        skill_json_path = os.path.join(skill_path, "skill.json")
        if os.path.exists(skill_json_path):
            try:
                import json
                with open(skill_json_path, "r", encoding="utf-8") as f:
                    sj = json.load(f)
                if sj.get("proven_params"):
                    result["proven_params"][skill_name] = sj["proven_params"]
            except Exception:
                pass

    return result


def _collect_from_results_log(project_root: str, session_id: str) -> dict:
    """从 results/<session>/log/ 收集运行归档记录（第五层日志）。"""
    result = {"run_records": [], "debate_records": [], "results_dir": ""}
    # 查找 results 目录
    results_base = os.path.join(project_root, "work", "results")
    if not os.path.isdir(results_base):
        # 也可能在 hermes_home/results
        results_base = os.path.join(project_root, "hermes_home", "results")
    if not os.path.isdir(results_base):
        return result

    # 查找会话对应的 results 目录
    session_results = None
    # 精确匹配
    for d in os.listdir(results_base):
        if session_id in d or d in session_id:
            session_results = os.path.join(results_base, d)
            break
    # 如果没找到，用最新的目录
    if session_results is None:
        dirs = sorted(
            [d for d in os.listdir(results_base) if os.path.isdir(os.path.join(results_base, d))],
            reverse=True,
        )
        if dirs:
            session_results = os.path.join(results_base, dirs[0])

    if session_results is None:
        return result
    result["results_dir"] = session_results

    # 递归查找 log/ 子目录
    for root, dirs, files in os.walk(session_results):
        for fname in files:
            fpath = os.path.join(root, fname)
            if fname.startswith("run_record_") and fname.endswith(".json"):
                try:
                    import json
                    with open(fpath, "r", encoding="utf-8") as f:
                        record = json.load(f)
                    record["_file"] = fpath
                    result["run_records"].append(record)
                except Exception:
                    pass
            elif fname.startswith("debate_") and fname.endswith(".json"):
                try:
                    import json
                    with open(fpath, "r", encoding="utf-8") as f:
                        record = json.load(f)
                    record["_file"] = fpath
                    result["debate_records"].append(record)
                except Exception:
                    pass

    return result


def _collect_from_agent_log(project_root: str, session_id: str, max_lines: int = 500) -> dict:
    """从 agent.log 收集系统运行日志（第一层日志）。"""
    result = {"log_lines": [], "log_file": ""}
    log_path = os.path.join(project_root, "hermes_home", "logs", "agent.log")
    if not os.path.exists(log_path):
        return result
    result["log_file"] = log_path

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # 过滤出包含 session_id 的行
        session_lines = [l.strip() for l in lines if session_id in l]
        if session_lines:
            result["log_lines"] = session_lines[-max_lines:]
        else:
            # 如果没有精确匹配，取最后 max_lines 行
            result["log_lines"] = [l.strip() for l in lines[-max_lines:]]

    except Exception as e:
        result["_error"] = f"agent.log: {e}"

    return result


def collect_session_data(session_id: str, project_root: str = "", skill_names: list = None) -> dict:
    """从五层日志源收集指定会话的全部记录。

    这是报告自动填充的核心函数。它从以下来源收集数据：

    1. hermes_home/logs/agent.log     — 系统运行日志（API调用、工具执行）
    2. hermes_home/state.db           — 会话消息+工具调用记录
    3. hermes_home/skills/.../logs/   — Skill 经验日志（错误+成功参数）
    4. work/results/<sid>/log/       — 运行归档（参数+结果+辩论）

    Parameters
    ----------
    session_id : str
        会话 ID（如 'memomics-9461f043'）
    project_root : str
        MemOmics-Agent 项目根目录（默认自动检测）
    skill_names : list, optional
        要扫描的 skill 名称列表（默认扫描全部 bioinformatics skill）

    Returns
    -------
    dict
        包含五个 key：agent_log, state_db, skill_logs, results_log, meta
    """
    if not project_root:
        project_root = _find_project_root()

    data = {
        "session_id": session_id,
        "project_root": project_root,
        "agent_log": {},
        "state_db": {},
        "skill_logs": {},
        "results_log": {},
        "meta": {"collected_at": datetime.now().isoformat()},
    }

    # 第一层：系统运行日志
    data["agent_log"] = _collect_from_agent_log(project_root, session_id)

    # 第二层：会话消息持久化
    data["state_db"] = _collect_from_state_db(project_root, session_id)

    # 第四层：Skill 经验日志
    data["skill_logs"] = _collect_from_skill_logs(project_root, skill_names)

    # 第五层：结果目录归档
    data["results_log"] = _collect_from_results_log(project_root, session_id)

    # 统计摘要
    data["meta"]["message_count"] = len(data["state_db"].get("messages", []))
    data["meta"]["tool_call_count"] = len(data["state_db"].get("tool_calls", []))
    data["meta"]["error_log_count"] = len(data["skill_logs"].get("error_logs", []))
    data["meta"]["run_record_count"] = len(data["results_log"].get("run_records", []))
    data["meta"]["debate_record_count"] = len(data["results_log"].get("debate_records", []))
    data["meta"]["log_line_count"] = len(data["agent_log"].get("log_lines", []))

    return data
