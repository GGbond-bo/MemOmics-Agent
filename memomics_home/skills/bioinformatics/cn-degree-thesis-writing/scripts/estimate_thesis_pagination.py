#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""学位论文页码「版心实算」估算器 + 图表序号倒置探针（只诊断，不改稿）

用法:
    python estimate_thesis_pagination.py <论文.docx> [--line-spacing 1.5] [--quiet]

设计前提（务必先读）:
    本脚本**不是** Word 分页。当本机没有 Word / WPS / LibreOffice / pandoc 时拿不到真实分页，
    只能按版心尺寸、docGrid 行距基准、实际字号与字符宽度逐段累计估算。
    结果精度约 ±(10~15)%，行距口径不同会给出不同单点值 —— 必须把区间与不确定度一并报给用户，
    交付话术固定为「按版心实算的估算值，不是 Word 实测；终稿请在 Word 中 Ctrl+A→F9 后据实校对」。
    详见 references/thesis-figure-authoring-and-pagination.md Part B。

输出:
    ① 版心/行高基准（读自 docx，不是猜的） ② 分量拆解（文字/图片/表格各占几页）
    ③ 每个图题/表题的估算页码（前置罗马数字、主体阿拉伯数字重新起算）
    ④ 图表序号倒置告警（图 3.3 出现在 图 3.2 之前 这类）
退出码: 0 = 无告警；1 = 发现序号倒置或读取失败
"""
import argparse
import math
import os
import re
import sys

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

CAP_RE = re.compile(r"^([图表])\s*(\d+)\s*\.\s*(\d+)")
CHAP_RE = re.compile(r"^第\s*\d+\s*章")


def char_w(ch, size):
    """单字符渲染宽度(pt)的工程近似：CJK=字号，ASCII=0.5×字号，其余=0.75×字号。"""
    o = ord(ch)
    if o >= 0x2E80:
        return size
    if o < 128:
        return size * 0.5
    return size * 0.75


def text_w(s, size):
    return sum(char_w(c, size) for c in s)


def read_layout(doc):
    """版心与行距基准 —— 全部读自 docx 自身，不猜。"""
    sec = doc.sections[0]
    pw = sec.page_width.pt
    ph = sec.page_height.pt
    mt = (sec.top_margin.pt if sec.top_margin else 72.0)
    mb = (sec.bottom_margin.pt if sec.bottom_margin else 72.0)
    ml = (sec.left_margin.pt if sec.left_margin else 72.0)
    mr = (sec.right_margin.pt if sec.right_margin else 72.0)
    grid = sec._sectPr.find(qn("w:docGrid"))
    pitch = None
    if grid is not None and grid.get(qn("w:linePitch")):
        pitch = int(grid.get(qn("w:linePitch"))) / 20.0    # twip → pt
    return dict(page_w=pw, page_h=ph, text_w=pw - ml - mr, text_h=ph - mt - mb,
                margins=(mt, mb, ml, mr), line_pitch=pitch)


def para_metrics(p, default_ls, single_line_pt):
    sizes = [r.font.size.pt for r in p.runs if r.font.size]
    size = max(sizes) if sizes else 12.0
    pf = p.paragraph_format
    ls = pf.line_spacing if pf.line_spacing else default_ls
    single = single_line_pt if single_line_pt else 1.3 * size
    line_h = ls * single
    sb = pf.space_before.pt if pf.space_before else 0.0
    sa = pf.space_after.pt if pf.space_after else 0.0
    ind = pf.first_line_indent.pt if pf.first_line_indent else 0.0
    img_h = 0.0
    for run in p.runs:
        for ext in run._element.findall(".//" + qn("wp:extent")):
            img_h += int(ext.get("cy")) / 12700.0          # EMU → pt
    xml = p._element.xml.replace(" ", "")
    pgbreak = 'w:type="page"' in xml
    ppr = p._element.find(qn("w:pPr"))
    sect = ppr is not None and ppr.find(qn("w:sectPr")) is not None
    return dict(text=p.text, size=size, line_h=line_h, sb=sb, sa=sa,
                ind=ind, img_h=img_h, pgbreak=pgbreak, sect=sect)


def table_height(tbl, text_w_pt, default_ls):
    h = 0.0
    for row in tbl.rows:
        ncol = max(1, len(row.cells))
        avail = text_w_pt / ncol
        mx = 1
        for c in row.cells:
            sz = 10.5
            for pp in c.paragraphs:
                ss = [r.font.size.pt for r in pp.runs if r.font.size]
                if ss:
                    sz = max(ss)
                break
            w = text_w(c.text, sz)
            mx = max(mx, max(1, math.ceil(w / max(1.0, avail))))
        h += mx * 1.3 * 12.0 * default_ls / 1.5 + 3.0
    return h


def roman(n):
    out = ""
    for k, r in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                 (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= k:
            out += r
            n -= k
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docx")
    ap.add_argument("--line-spacing", type=float, default=1.5,
                    help="段落未显式设 line_spacing 时的默认倍数（生成器约定，默认 1.5）")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.docx):
        print("找不到文件:", a.docx); return 1
    doc = Document(a.docx)
    L = read_layout(doc)

    print("=" * 68)
    print("版心: %.1f × %.1f pt (%.2f × %.2f cm) | 页边距 上%.2f 下%.2f 左%.2f 右%.2f cm"
          % (L["text_w"], L["text_h"], L["text_w"] / 28.3465, L["text_h"] / 28.3465,
             L["margins"][0] / 28.3465, L["margins"][1] / 28.3465,
             L["margins"][2] / 28.3465, L["margins"][3] / 28.3465))
    if L["line_pitch"]:
        print("行距基准(docGrid linePitch): %.1f pt/行 → 每页约 %.1f 行（×%.2f 倍行距）"
              % (L["line_pitch"], L["text_h"] / (L["line_pitch"] * a.line_spacing), a.line_spacing))
    else:
        print("⚠️ docx 内无 w:docGrid linePitch → 行高按 1.3×字号 估算（不确定度更大）")
    print("=" * 68)

    page, used = 1, 0.0
    n_lines = n_img = n_pages_img = 0
    tbl_h_total = 0.0
    n_tbl = n_tbl_rows = 0
    para_h_total = 0.0
    caps, order_issues = [], []

    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:tbl"):
            t = Table(child, doc)
            h = table_height(t, L["text_w"], a.line_spacing)
            if used + h > L["text_h"]:
                page += 1; used = 0.0
            used += h
            tbl_h_total += h; n_tbl += 1; n_tbl_rows += len(t.rows)
            continue
        if child.tag != qn("w:p"):        # 末尾的 w:sectPr 不是段落，必须跳过
            continue
        p = Paragraph(child, doc)
        m = para_metrics(p, a.line_spacing, L["line_pitch"])
        if m["pgbreak"]:
            page += 1; used = 0.0
        lines = 1
        if m["text"].strip():
            lines = max(1, math.ceil((text_w(m["text"], m["size"]) + m["ind"] * 0.6) / L["text_w"]))
        h = m["sb"] + m["sa"] + lines * m["line_h"] + m["img_h"]
        n_lines += lines
        if m["img_h"]:
            n_img += 1; n_pages_img += m["img_h"]
        para_h_total += m["sb"] + m["sa"] + lines * m["line_h"]
        if h > 0 and used + min(h, L["text_h"]) > L["text_h"]:
            page += 1; used = 0.0
        used += h
        cm = CAP_RE.match(m["text"].strip())
        if cm:
            caps.append((cm.group(1), int(cm.group(2)), int(cm.group(3)), page, m["text"].strip()))
        if m["sect"]:
            page += 1; used = 0.0

    # ── 前置/主体页码起点：重扫一次、找到「第一个 第N章 段落」即停（成本很低） ──
    body_start = None
    pg = 1; used2 = 0.0
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:tbl"):
            t = Table(child, doc)
            h = table_height(t, L["text_w"], a.line_spacing)
            if used2 + h > L["text_h"]:
                pg += 1; used2 = 0.0
            used2 += h
            continue
        if child.tag != qn("w:p"):
            continue
        p = Paragraph(child, doc)
        m = para_metrics(p, a.line_spacing, L["line_pitch"])
        if m["pgbreak"]:
            pg += 1; used2 = 0.0
        lines = 1
        if m["text"].strip():
            lines = max(1, math.ceil((text_w(m["text"], m["size"]) + m["ind"] * 0.6) / L["text_w"]))
        h = m["sb"] + m["sa"] + lines * m["line_h"] + m["img_h"]
        if h > 0 and used2 + min(h, L["text_h"]) > L["text_h"]:
            pg += 1; used2 = 0.0
        used2 += h
        if body_start is None and CHAP_RE.match(m["text"].strip()):
            body_start = pg
        if m["sect"]:
            pg += 1; used2 = 0.0
        if body_start:
            break

    def label(p):
        if body_start and p >= body_start:
            return str(p - body_start + 1)
        return roman(p) if p >= 1 else "—"

    # ── 分量拆解 ──
    print("\n【分量拆解】")
    print("  纯文字  %6d 字 → %5d 行 → 约 %5.1f 页" % (sum(len(c[4]) for c in caps), n_lines,
                                                    para_h_total / L["text_h"]))
    print("  图片    %6d 张            → 约 %5.1f 页" % (n_img, n_pages_img / L["text_h"]))
    print("  表格    %6d 个 / %d 行    → 约 %5.1f 页" % (n_tbl, n_tbl_rows, tbl_h_total / L["text_h"]))
    print("  合计（含分页浪费）        → 约 %5d 页" % page)
    print("  ⚠️ 这是按版心实算的**估算值**，不是 Word 实测；行距口径不同会落在更宽区间。")

    figs = [c for c in caps if c[0] == "图"]
    tabs = [c for c in caps if c[0] == "表"]
    for name, arr in (("图", figs), ("表", tabs)):
        print("\n【%s 估算页码】" % name)
        prev = None
        for _, maj, mnr, p, txt in arr:
            flag = ""
            if prev is not None and (maj, mnr) < prev:
                flag = "  ← ⚠️ 序号倒置（出现在前一个同章序号之前）"
                order_issues.append("%s%d.%d 出现在更小编号之后" % (name, maj, mnr))
            prev = (maj, mnr)
            print("  %s%-6s p%-5s %s%s" % (name, "%d.%d" % (maj, mnr), label(p), txt[:34], flag))

    if order_issues:
        print("\n❌ 序号倒置 %d 处：%s" % (len(order_issues), "; ".join(order_issues)))
        print("   → 图表号必须按正文出现顺序连续编号；修完同步：插图附表清单 / 目录页码 / 正文交叉引用 / 图注 / 图片 alt")
        return 1
    if not a.quiet:
        print("\n✅ 未发现图表序号倒置。等第 3~4 位小数页码不作检查，请与 Word 中 F9 结果比对后校准。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
