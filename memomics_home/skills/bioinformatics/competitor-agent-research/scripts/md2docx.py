#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
md2docx.py — 通用 Markdown → DOCX 转换器（Phylo 风格金表头 + Arial）

场景：模式 D 交付组合的第 5 件（可编辑 DOCX）——把已写好的 `.md` 母本
（定位报告 / 分析报告 / 论文草稿）一键转成 .docx，保留标题层级、项目符号、
管道表格、代码块与内嵌图。先写 .md 再转，比直接拼 python-docx 快一个量级。

用法:
    python md2docx.py <input.md> <output.docx> ["报告标题"] ["副标题"]

支持语法:
    # ## ### ####       标题层级
    - / 1.              无序 / 有序列表（真列表样式，不要手打 •）
    |a|b|               管道表格（金表头 D4A04A + 隔行 F9F7F3 + 细边框）
    ```...```           代码块（浅底 F5F5F0 + Consolas）
    > 引用  |  --- 水平线  |  **粗体** `行内代码`
    ![caption](path)    图片（居中 + 斜体灰题注）

实测要点（2026-10-02）：
1. **必须用带 python-docx 的解释器**。本项目 `.venv` 可能没有，系统 python 常有：
       python -c "import docx; print('ok')"
   先探测再跑；探测到就用它跑，**不要盲目 pip install**（能不装就不装）。
2. **持久内核（execute_python）里不要 `import docx`**：该解释器常缺包。
   用 `terminal` 调系统 python 跑本脚本。
3. 用 `exec(open(path).read())` 方式跑本文件时，不会注入 `__file__`
   —— 故本文件对 `__file__` 做了 try/except 兜底（HERE）。同理，下游脚本
   若用了 `__file__` 定位 ROOT，也要加兜底。
4. 图片相对路径按 `md 所在目录/..` 解析，因此 `deliverables/x.md` 里的
   `figures/Fig1.png` 会正确落到会话根下的 `figures/`。
5. 退出时会打印 `bytes | paras | tables | embedded images`——
   **embedded images 必须 >0**，否则图没进文档（路径错会打印「[缺图: ...]」红色提示）。
"""
import sys
import os
import re

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

HEADING, BODY, GOLD, MUTED = "111111", "2C2A26", "D4A04A", "8A8378"
FONT = "Arial"

# 安全兜底：exec() 方式运行时不注入 __file__
try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = os.getcwd()

INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")


def _run(p, text, size=11, bold=False, italic=False, color=BODY, mono=False):
    r = p.add_run(text)
    r.font.name = "Consolas" if mono else FONT
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    r.font.color.rgb = RGBColor.from_string(color)
    return r


def rich(p, text, size=11, color=BODY):
    """处理 **粗体** 与 `行内代码`"""
    for seg in INLINE.split(text):
        if not seg:
            continue
        if seg.startswith("**") and seg.endswith("**") and len(seg) > 4:
            _run(p, seg[2:-2], size=size, bold=True, color=color)
        elif seg.startswith("`") and seg.endswith("`") and len(seg) > 2:
            _run(p, seg[1:-1], size=size - 1, color="8B4513", mono=True)
        else:
            _run(p, seg, size=size, color=color)


def shade(cell, fill):
    el = OxmlElement("w:shd")
    el.set(qn("w:val"), "clear")
    el.set(qn("w:fill"), fill)
    cell._element.get_or_add_tcPr().append(el)


def borders(table, color="D5CFC5", size="4"):
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for e in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{e}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:color"), color)
        el.set(qn("w:space"), "0")
        b.append(el)
    tblPr.append(b)


def pad(cell, t=70, b=70, l=110, r=110):
    tcPr = cell._element.get_or_add_tcPr()
    m = OxmlElement("w:tcMar")
    for e, v in (("top", t), ("bottom", b), ("start", l), ("end", r)):
        el = OxmlElement(f"w:{e}")
        el.set(qn("w:w"), str(v))
        el.set(qn("w:type"), "dxa")
        m.append(el)
    tcPr.append(m)


def hrule(doc, color=GOLD, sz="6", before=4, after=10):
    p = doc.add_paragraph()
    pPr = p._element.get_or_add_pPr()
    pb = OxmlElement("w:pBdr")
    bo = OxmlElement("w:bottom")
    bo.set(qn("w:val"), "single")
    bo.set(qn("w:sz"), sz)
    bo.set(qn("w:color"), color)
    bo.set(qn("w:space"), "1")
    pb.append(bo)
    pPr.append(pb)
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)


def make_table(doc, rows):
    if not rows:
        return
    headers, data = rows[0], rows[1:]
    t = doc.add_table(rows=1 + len(data), cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = True
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ""
        rich(c.paragraphs[0], h, size=9, color="FFFFFF")
        for r in c.paragraphs[0].runs:
            r.bold = True
        shade(c, GOLD)
        pad(c)
    for ri, row in enumerate(data):
        for ci in range(len(headers)):
            c = t.rows[ri + 1].cells[ci]
            c.text = ""
            rich(c.paragraphs[0], row[ci] if ci < len(row) else "", size=9)
            if ci == 0:
                for r in c.paragraphs[0].runs:
                    r.bold = True
            if ri % 2 == 1:
                shade(c, "F9F7F3")
            pad(c)
    borders(t)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def convert(md_path, out_path, title=None, subtitle=None):
    lines = open(md_path, encoding="utf-8").read().split("\n")
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(11)
    st.font.color.rgb = RGBColor.from_string(BODY)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    for m in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(sec, m, Inches(0.9))

    if title:
        p = doc.add_paragraph()
        _run(p, title, size=24, bold=True, color=HEADING)
        p.paragraph_format.space_after = Pt(4)
    if subtitle:
        p = doc.add_paragraph()
        _run(p, subtitle, size=11, color=GOLD)
        p.paragraph_format.space_after = Pt(10)
    hrule(doc)

    i, n = 0, len(lines)
    in_code, code_buf, tbl_buf = False, [], []

    def flush_tbl():
        nonlocal tbl_buf
        if tbl_buf:
            make_table(doc, tbl_buf)
            tbl_buf = []

    while i < n:
        s = lines[i].strip()

        if s.startswith("```"):
            if in_code:
                p = doc.add_paragraph()
                _run(p, "\n".join(code_buf), size=8.5, mono=True, color="333333")
                p.paragraph_format.space_after = Pt(8)
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:fill"), "F5F5F0")
                p._element.get_or_add_pPr().append(shd)
                code_buf, in_code = [], False
            else:
                flush_tbl()
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(lines[i])
            i += 1
            continue

        # 图片 ![caption](path)
        m = re.match(r"^!\[(.*?)\]\((.+?)\)\s*$", s)
        if m:
            flush_tbl()
            cap, pth = m.group(1), m.group(2)
            if not os.path.isabs(pth):
                # 🔴 同目录优先，再退 ../（2026-10-07 修）：
                # 只试 ../ 时，deliverables/x.md 里的 figures/Fig1.png 会解析到
                # <会话根>/figures/ 而**静默显示 [缺图: …]**（DOCX 照样生成、不报错）。
                d = os.path.dirname(os.path.abspath(md_path))
                cand = [os.path.join(d, pth), os.path.normpath(os.path.join(d, "..", pth))]
                pth = next((c for c in cand if os.path.exists(c)), cand[0])
            if os.path.exists(pth):
                ip = doc.add_paragraph()
                ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
                ip.add_run().add_picture(pth, width=Inches(6.4))
                cp = doc.add_paragraph()
                cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _run(cp, cap, size=9, italic=True, color=MUTED)
                cp.paragraph_format.space_after = Pt(12)
            else:
                p = doc.add_paragraph()
                _run(p, f"[缺图: {pth}]", size=10, italic=True, color="C0392B")
            i += 1
            continue

        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not re.fullmatch(r"[-: ]+", "".join(cells)):
                tbl_buf.append(cells)
            i += 1
            continue
        flush_tbl()

        m = re.match(r"^(#{1,4})\s+(.*)", s)
        if m:
            lvl, txt = len(m.group(1)), m.group(2).strip()
            if lvl == 1:
                p = doc.add_paragraph()
                _run(p, txt, size=17, bold=True, color=HEADING)
                p.paragraph_format.space_before = Pt(18)
                p.paragraph_format.space_after = Pt(6)
            else:
                size = {2: 13.5, 3: 11.5, 4: 11}[lvl]
                p = doc.add_paragraph()
                _run(p, txt, size=size, bold=True, color=HEADING)
                p.paragraph_format.space_before = Pt(13 if lvl == 2 else 10)
                p.paragraph_format.space_after = Pt(5)
            if lvl == 2:
                hrule(doc, color="E8DCC0", sz="4", before=2, after=6)
            i += 1
            continue

        if re.fullmatch(r"-{3,}", s):
            hrule(doc)
            i += 1
            continue

        if s.startswith(">"):
            flush_tbl()
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            rich(p, s.lstrip("> ").strip(), size=10.5, color="4A4A4A")
            i += 1
            continue

        m = re.match(r"^([-*]|\d+\.)\s+(.*)", s)
        if m:
            style = "List Number" if re.match(r"\d+\.", m.group(1)) else "List Bullet"
            p = doc.add_paragraph(style=style)
            rich(p, m.group(2), size=10.5)
            p.paragraph_format.space_after = Pt(2)
            i += 1
            continue

        if not s:
            i += 1
            continue

        p = doc.add_paragraph()
        rich(p, s)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = Pt(15)
        i += 1

    flush_tbl()
    doc.save(out_path)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    md, out = sys.argv[1], sys.argv[2]
    t = sys.argv[3] if len(sys.argv) > 3 else None
    sub = sys.argv[4] if len(sys.argv) > 4 else None
    convert(md, out, t, sub)

    from docx import Document as D
    d = D(out)
    imgs = sum(1 for r in d.part.rels.values() if "image" in r.reltype)
    print(f"OK: {os.path.getsize(out):,} bytes | {len(d.paragraphs)} paras | "
          f"{len(d.tables)} tables | {imgs} embedded images")