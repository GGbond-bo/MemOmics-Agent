# -*- coding: utf-8 -*-
"""
学位论文 Markdown 母本 → 规范合规 DOCX 渲染器（模板，2026-09-16 实测版）

适用：高校学位论文规范（吉大硕士版实测；换学校改 CONFIG 与 SPEC 字体字号即可）
用法：改 CONFIG → 确认 python-docx 可用 → 运行

  # 分析内核常无 python-docx，用系统 Python 跑（先确认）：
  python -c "import docx; print(docx.__version__)"
  python thesis_docx_builder.py

⛔ 本脚本刻意不使用 __file__ —— 用 exec(open(p).read()) 在持久内核里跑时 __file__ 未定义会 NameError。

母本 Markdown 约定（渲染器按这些标记解析）：
  # 第N章　标题 / # 参考文献 / # 附录A　…   → 章级：另起节 + 该节页眉 = 本章标题
  ## 1.1　…                                → 一级节标题（黑体四号）
  ### 1.1.1　…                             → 二级节标题（黑体小四）
  **表 3.1　表题**                          → 表题（表上方、黑体居中）
  **图 3.1　图题**                          → 图题（图下方、黑体居中）
  ![alt](figures/x.png)                    → 居中插图（宽度 FIG_WIDTH_CM）
  图注：…                                   → 图注段落（宋体五号）
  > 引文                                    → 楷体缩进块
  ---                                      → 前置部分内分页（正文用分节符分页）
  4 空格缩进 + 行尾（2-1）                    → 公式行（居中）
  | a | b |  标准 Markdown 表格             → 带边框表（表头加粗）
"""
import os
import re
import shutil

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ─────────────────────────── CONFIG（改这里） ───────────────────────────
BASE = r"E:/path/to/thesis"                  # 工作目录（母本分片、figures/ 都在这里）
PARTS = [                                    # Markdown 分片，按顺序合并
    "part1_front.md",
    "part2_ch1_ch2.md",
    "part3_ch3_ch4_ch5.md",
    "part4_refs_appendix.md",
]
SRC_FIG = r""                                # 图件源目录（可为空字符串 = 不拷贝）；figures/ 已就位则留空
FIG_DIR_NAME = "figures"
OUT_MD_NAME = "学位论文_母本合并.md"
OUT_DOCX_NAME = "学位论文.docx"

SONG, HEI, KAI = "宋体", "黑体", "楷体"        # 吉大规范：正文宋体、标题与题注黑体、页眉楷体
BODY_PT = 12                                  # 正文小四
CHAPTER_PT = 16                               # 章标题 黑体三号
H1_PT, H2_PT = 14, 12                         # 一级/二级节标题
CAPTION_PT = 12                               # 图表题注（规范：字号＝正文）
HEADER_PT = 9                                 # 页眉 楷体小5号
TABLE_PT = 10.5                               # 表格 五号
FIG_WIDTH_CM = 14.5
MARGIN = dict(top=2.7, bottom=2.5, left=3.0, right=2.5)   # 规范：上左 ≥25mm、下右 ≥20mm
# 章级标题识别：第N章 / 参考文献 / 附录X / 作者简介 / 致谢
CHAPTER_RE = re.compile(r"^(第\d+章|参考文献|附录[A-Z]?|作者简介.*|后记和致谢).*")
# ────────────────────────────────────────────────────────────────────────

FIG_DIR = os.path.join(BASE, FIG_DIR_NAME)
OUT_MD = os.path.join(BASE, OUT_MD_NAME)
OUT_DOCX = os.path.join(BASE, OUT_DOCX_NAME)
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


# ───────────────────────── 基础排版工具（已验证） ─────────────────────────
def set_run(run, cn=SONG, size=BODY_PT, bold=False):
    """字体三属性齐写：只设 font.name 中文会回落默认字体。"""
    run.font.name = cn
    run.font.size = Pt(size)
    run.bold = bold
    rPr = run._element.get_or_add_rPr()
    rf = rPr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rPr.insert(0, rf)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia"):
        rf.set(qn(attr), cn)


def set_para(p, align=None, indent_chars=0, before=0, after=0,
             line=1.5, size_for_indent=BODY_PT):
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    if indent_chars:                      # 首行缩进 2 字符
        pf.first_line_indent = Pt(size_for_indent * indent_chars)
    return p


def add_rich(p, text, cn=SONG, size=BODY_PT, base_bold=False):
    """行内 **加粗** 解析"""
    pos = 0
    for m in BOLD_RE.finditer(text):
        if m.start() > pos:
            set_run(p.add_run(text[pos:m.start()]), cn, size, base_bold)
        set_run(p.add_run(m.group(1)), cn, size, True)
        pos = m.end()
    if pos < len(text):
        set_run(p.add_run(text[pos:]), cn, size, base_bold)
    if not text:
        set_run(p.add_run(""), cn, size, base_bold)
    return p


def add_header_border(paragraph, sz="6"):
    """页眉下方普通单划线"""
    pPr = paragraph._element.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    b.set(qn("w:val"), "single")
    b.set(qn("w:sz"), sz)
    b.set(qn("w:color"), "000000")
    b.set(qn("w:space"), "1")
    pBdr.append(b)
    pPr.append(pBdr)


def add_page_field(paragraph):
    """PAGE 域（不要硬编码页码）"""
    r = paragraph.add_run()
    set_run(r, SONG, TABLE_PT)
    f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = " PAGE "
    f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "end")
    for el in (f1, it, f2):
        r._element.append(el)


def set_pgnum(section, fmt, start=None):
    """分节页码格式：fmt='upperRoman'(前置) / 'decimal'(主体)；start 只在主体第一节给。"""
    sectPr = section._sectPr
    for old in sectPr.findall(qn("w:pgNumType")):
        sectPr.remove(old)
    el = OxmlElement("w:pgNumType")
    el.set(qn("w:fmt"), fmt)
    if start is not None:
        el.set(qn("w:start"), str(start))
    sectPr.append(el)


def setup_section(section, header_text=None):
    """页边距 + 页眉 + 页脚。🔴 header_text 必须传章标题——漏传 = 页眉空（脚本不报错！）"""
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(MARGIN["top"]), Cm(MARGIN["bottom"])
    section.left_margin, section.right_margin = Cm(MARGIN["left"]), Cm(MARGIN["right"])
    section.header_distance = section.footer_distance = Cm(1.5)

    hdr = section.header
    hdr.is_linked_to_previous = False          # 每节独立页眉
    hp = hdr.paragraphs[0]
    for r in list(hp.runs):
        r._element.getparent().remove(r._element)
    hp.text = ""
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if header_text:                            # 🔴 关键：不传就是空页眉
        set_run(hp.add_run(header_text), KAI, HEADER_PT)
        add_header_border(hp)

    ftr = section.footer
    ftr.is_linked_to_previous = False
    fp = ftr.paragraphs[0]
    for r in list(fp.runs):
        r._element.getparent().remove(r._element)
    fp.text = ""
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT   # 单面印刷：页码右下角
    add_page_field(fp)


# ───────────────────────── Markdown 解析工具 ─────────────────────────
def split_md_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_sep_row(line):
    s = line.strip().strip("|")
    return bool(s) and set(s.replace("|", "").replace(" ", "")) <= set("-:")


def add_md_table(doc, rows, size=TABLE_PT):
    ncol = max(len(r) for r in rows)
    t = doc.add_table(rows=len(rows), cols=ncol)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = True
    for i, row in enumerate(rows):
        for j in range(ncol):
            cell = t.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            set_para(p, WD_ALIGN_PARAGRAPH.LEFT, 0, 0, 0, 1.0)
            add_rich(p, (row[j] if j < len(row) else "").replace("<br/>", " "),
                     SONG, size, base_bold=(i == 0))
    return t


# ───────────────────────── 主流程 ─────────────────────────
def merge_md():
    buf = []
    for p in PARTS:
        with open(os.path.join(BASE, p), encoding="utf-8") as f:
            buf.append(f.read().strip())
    txt = "\n\n".join(buf)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(txt)
    return txt


def copy_figs():
    if not SRC_FIG:
        return 0
    os.makedirs(FIG_DIR, exist_ok=True)
    n = 0
    for fn in os.listdir(SRC_FIG):
        if fn.lower().endswith(".png"):
            shutil.copy2(os.path.join(SRC_FIG, fn), os.path.join(FIG_DIR, fn))
            n += 1
    return n


def build(txt):
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name, st.font.size = SONG, Pt(BODY_PT)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), SONG)

    setup_section(doc.sections[0], header_text=None)   # 前置部分不设页眉
    set_pgnum(doc.sections[0], "upperRoman", 1)        # 前置：罗马数字

    lines = txt.split("\n")
    i, in_body, in_code, body_started = 0, False, False, False

    while i < len(lines):
        raw, line = lines[i].rstrip(), lines[i].rstrip()
        s = line.strip()

        if s.startswith("```"):                        # 代码围栏
            in_code = not in_code
            i += 1
            continue
        if in_code:
            p = doc.add_paragraph()
            set_para(p, WD_ALIGN_PARAGRAPH.LEFT, 0, 0, 0, 1.2)
            set_run(p.add_run(line.replace("　", "  ")), SONG, TABLE_PT)
            i += 1
            continue

        if s.startswith("|") and i + 1 < len(lines) and is_sep_row(lines[i + 1]):
            rows = [split_md_row(s)]
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(split_md_row(lines[j]))
                j += 1
            add_md_table(doc, rows)
            doc.add_paragraph()
            i = j
            continue

        m = re.match(r"!\[(.*?)\]\((.*?)\)", s)        # 图片
        if m:
            path = os.path.join(BASE, m.group(2).replace("/", os.sep))
            if os.path.exists(path):
                p = doc.add_paragraph()
                set_para(p, WD_ALIGN_PARAGRAPH.CENTER, 0, 6, 2, 1.0)
                p.add_run().add_picture(path, width=Cm(FIG_WIDTH_CM))
            else:
                p = doc.add_paragraph()
                set_para(p, WD_ALIGN_PARAGRAPH.CENTER, 0, 0, 0, 1.0)
                set_run(p.add_run(f"[缺图件文件：{os.path.basename(m.group(2))}]"), SONG, TABLE_PT)
            i += 1
            continue

        if not s:
            i += 1
            continue

        if s == "---":                                  # 前置内分页
            if not in_body:
                p = doc.add_paragraph()
                p.add_run().add_break(WD_BREAK.PAGE)
            i += 1
            continue

        # 章级标题 → 新节 + 页眉 = 本章标题
        if s.startswith("# ") and not s.startswith("## "):
            title = s[2:].strip()
            if CHAPTER_RE.match(title):
                in_body = True
                sec = doc.add_section(WD_SECTION.NEW_PAGE)
                setup_section(sec, header_text=title)   # 🔴 传标题，否则页眉空
                set_pgnum(sec, "decimal", 1 if not body_started else None)
                body_started = True
                p = doc.add_paragraph()
                set_para(p, WD_ALIGN_PARAGRAPH.LEFT, 0, 12, 18, 1.5)
                set_run(p.add_run(title), HEI, CHAPTER_PT)
            else:
                p = doc.add_paragraph()
                set_para(p, WD_ALIGN_PARAGRAPH.CENTER, 0, 12, 10, 1.5)
                set_run(p.add_run(title), HEI, H1_PT + 1)
            i += 1
            continue

        if s.startswith("### "):
            p = doc.add_paragraph()
            set_para(p, WD_ALIGN_PARAGRAPH.LEFT, 0, 10, 6, 1.5)
            set_run(p.add_run(s[4:].strip()), HEI, H2_PT)
            i += 1
            continue
        if s.startswith("## "):
            p = doc.add_paragraph()
            set_para(p, WD_ALIGN_PARAGRAPH.LEFT, 0, 12, 8, 1.5)
            set_run(p.add_run(s[3:].strip()), HEI, H1_PT)
            i += 1
            continue

        # 图题 / 表题（黑体居中；表题 keep_with_next 防与表拆页）
        if re.match(r"^\*\*表\s*[A-Z]?\d", s):
            p = doc.add_paragraph()
            set_para(p, WD_ALIGN_PARAGRAPH.CENTER, 0, 8, 4, 1.3)
            set_run(p.add_run(BOLD_RE.sub(r"\1", s)), HEI, CAPTION_PT)
            p.paragraph_format.keep_with_next = True
            i += 1
            continue
        if re.match(r"^\*\*图\s*\d", s):
            p = doc.add_paragraph()
            set_para(p, WD_ALIGN_PARAGRAPH.CENTER, 0, 4, 8, 1.3)
            set_run(p.add_run(BOLD_RE.sub(r"\1", s)), HEI, CAPTION_PT)
            i += 1
            continue

        if s.startswith(">"):                            # 引文块
            t = s.lstrip(">").strip()
            if t:
                p = doc.add_paragraph()
                set_para(p, WD_ALIGN_PARAGRAPH.LEFT, 0, 2, 6, 1.3)
                p.paragraph_format.left_indent = Cm(1.0)
                add_rich(p, t, KAI, TABLE_PT)
            i += 1
            continue

        if s.startswith("图注："):
            p = doc.add_paragraph()
            set_para(p, WD_ALIGN_PARAGRAPH.LEFT, 0, 0, 10, 1.3)
            p.paragraph_format.left_indent = Cm(0.5)
            add_rich(p, s, SONG, TABLE_PT)
            i += 1
            continue

        lm = re.match(r"^([-*]|\d+\.)\s+(.*)$", s)       # 列表
        if lm:
            p = doc.add_paragraph(style="List Bullet" if lm.group(1) in "-*" else "List Number")
            set_para(p, WD_ALIGN_PARAGRAPH.LEFT, 0, 0, 4, 1.4)
            add_rich(p, lm.group(2), SONG, BODY_PT)
            i += 1
            continue

        if raw.startswith("    ") and re.search(r"（\d-\d+）\s*$", raw):   # 公式（带编号）
            p = doc.add_paragraph()
            set_para(p, WD_ALIGN_PARAGRAPH.CENTER, 0, 6, 6, 1.5)
            set_run(p.add_run(s), SONG, BODY_PT)
            i += 1
            continue
        if raw.startswith("    "):
            p = doc.add_paragraph()
            set_para(p, WD_ALIGN_PARAGRAPH.LEFT, 0, 0, 4, 1.4)
            p.paragraph_format.left_indent = Cm(0.8)
            add_rich(p, s, SONG, BODY_PT)
            i += 1
            continue

        p = doc.add_paragraph()                          # 正文：首行缩进 2 字符
        set_para(p, WD_ALIGN_PARAGRAPH.LEFT, 2, 0, 6, 1.5)
        add_rich(p, s, SONG, BODY_PT)
        i += 1

    doc.save(OUT_DOCX)
    return doc


def verify():
    """交付前必跑：页眉逐节非空 + 字体 + 单划线 + 页码格式 + 图片张数"""
    import zipfile
    z = zipfile.ZipFile(OUT_DOCX)
    media = [n for n in z.namelist() if n.startswith("word/media/")]
    print(f"DOCX {os.path.getsize(OUT_DOCX):,} B | 内嵌图 {len(media)} 张")
    bad = []
    for k in range(1, 30):
        n = f"word/header{k}.xml"
        if n not in z.namelist():
            continue
        x = z.read(n).decode("utf-8")
        txt = re.sub(r"<[^>]+>", "", x).strip()
        if txt:
            ok_font, ok_rule = (KAI in x), ("pBdr" in x)
            print(f"  header{k}: 「{txt}」 字体={ok_font} 单划线={ok_rule}")
            if not (ok_font and ok_rule):
                bad.append(k)
    x = z.read("word/document.xml").decode("utf-8")
    print("页码格式 upperRoman/decimal:", "upperRoman" in x, "/", "decimal" in x)
    assert not bad, f"⚠️ header {bad} 字体或单划线缺失"
    assert len(media) > 0, "⚠️ 没有内嵌图片"
    print("verify OK")


if __name__ == "__main__":
    txt = merge_md()
    n = copy_figs()
    doc = build(txt)
    print(f"merged: {OUT_MD}\nfigs: {n}\nDOCX: {OUT_DOCX}")
    print(f"  paragraphs={len(doc.paragraphs)} tables={len(doc.tables)} sections={len(doc.sections)}")
    verify()
