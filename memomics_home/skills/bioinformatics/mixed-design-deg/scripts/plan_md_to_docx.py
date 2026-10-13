# -*- coding: utf-8 -*-
"""Markdown 方案/报告 -> 可编辑 DOCX（保留标题层级、表格、代码块、列表）

用法:
    python plan_md_to_docx.py <input.md> [output.docx]
    # output 省略时 = 同目录同名 .docx

依赖: python-docx。若 .venv 没有，不要安装 —— 先探系统 python:
    for P in ".venv/Scripts/python.exe" python python3; do
      printf '%s -> ' "$P"; $P -c "import docx,sys;print('HAS_DOCX',sys.executable)" 2>&1 | tail -1
    done

要点:
  - 中文必须同时设 font.name 与 rPr.rFonts 的 w:eastAsia（只设前者中文会回退成豆腐块）
  - 管道表格 -> Light Grid 表，首行加粗；表格前插空段避免与正文粘连
  - 表格分隔行（|---|）按正则跳过
"""
import os
import re
import sys

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor
except ImportError:
    print("MISSING:python-docx -> 先探其它解释器（见文件头），不要直接安装")
    sys.exit(3)


def md_to_docx(md_path, out_path, cjk_font="Microsoft YaHei", body_pt=10.5):
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = cjk_font
    st.font.size = Pt(body_pt)
    st._element.rPr.rFonts.set(qn("w:eastAsia"), cjk_font)  # 中文关键的一行

    lines = open(md_path, encoding="utf-8").read().split("\n")
    i, in_code, code_buf = 0, False, []

    def flush_code(buf):
        if not buf:
            return
        p = doc.add_paragraph()
        r = p.add_run("\n".join(buf))
        r.font.name = "Consolas"
        r.font.size = Pt(8.5)
        r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        p.paragraph_format.left_indent = Pt(12)
        p.paragraph_format.space_after = Pt(6)

    while i < len(lines):
        ln = lines[i].rstrip()

        if ln.startswith("```"):                       # 代码围栏开/关
            if in_code:
                flush_code(code_buf)
                code_buf, in_code = [], False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(ln)
            i += 1
            continue

        # 管道表格（下一行是分隔行才算表头）
        if ln.startswith("|") and i + 1 < len(lines) and re.match(
                r"^\|[\s:\-|]+\|$", lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not re.match(r"^[\s:\-]+$", "".join(cells)):
                    rows.append(cells)
                i += 1
            if rows:
                ncol = max(len(r) for r in rows)
                t = doc.add_table(rows=0, cols=ncol)
                t.style = "Light Grid Accent 1"
                for ri, r in enumerate(rows):
                    cells = t.add_row().cells
                    for ci in range(ncol):
                        txt = (r[ci] if ci < len(r) else "").replace("**", "").replace("`", "")
                        cells[ci].text = txt
                        for para in cells[ci].paragraphs:
                            for run in para.runs:
                                run.font.size = Pt(8.5)
                                if ri == 0:
                                    run.bold = True
                doc.add_paragraph()
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", ln)          # 标题（最多 4 级）
        if m:
            doc.add_heading(m.group(2).replace("**", ""), level=min(len(m.group(1)), 4))
            i += 1
            continue

        if ln.startswith(">"):                          # 引用 -> 斜体灰
            p = doc.add_paragraph()
            r = p.add_run(ln.lstrip("> ").replace("**", "").replace("`", ""))
            r.italic = True
            r.font.size = Pt(9.5)
            r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            i += 1
            continue

        if ln.strip() in ("---", "***"):                # 分隔线
            doc.add_paragraph("─" * 40).alignment = WD_ALIGN_PARAGRAPH.CENTER
            i += 1
            continue

        m = re.match(r"^(\s*)[-*]\s+(.*)$", ln)         # 无序列表
        if m:
            doc.add_paragraph(m.group(2).replace("**", "").replace("`", ""), style="List Bullet")
            i += 1
            continue
        m = re.match(r"^(\s*)(\d+)\.\s+(.*)$", ln)      # 有序列表
        if m:
            doc.add_paragraph(m.group(3).replace("**", "").replace("`", ""), style="List Number")
            i += 1
            continue

        if not ln.strip():
            i += 1
            continue

        p = doc.add_paragraph()                         # 正文 + 行内 **加粗**
        for seg in re.split(r"(\*\*.*?\*\*)", ln.replace("`", "")):
            if seg.startswith("**") and seg.endswith("**") and len(seg) > 4:
                p.add_run(seg[2:-2]).bold = True
            elif seg:
                p.add_run(seg)
        i += 1

    doc.save(out_path)
    return len(doc.paragraphs), len(doc.tables)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    md = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(md)[0] + ".docx"
    n_par, n_tab = md_to_docx(md, out)
    print(f"OK: {out} {os.path.getsize(out)} bytes, paragraphs: {n_par} tables: {n_tab}")