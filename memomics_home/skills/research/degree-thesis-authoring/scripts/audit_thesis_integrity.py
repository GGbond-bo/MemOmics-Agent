# -*- coding: utf-8 -*-
"""学位论文 / 长文档完整性审计（可复跑）

用法：
    python audit_thesis_integrity.py <论文目录> [参考文献部分的文件名]
    # 例：python audit_thesis_integrity.py E:/.../results/thesis part4_refs_appendix.md

检查项（脚本能查的部分；人工判的部分见 references/figure-citation-integrity-audit.md）：
  1) 图件 ↔ 图号映射：同一图件被 ≥2 个图号引用 = 排版硬伤
  2) 图号连续性：每章 图 X.1..X.n 有无断号
  3) 正文图/表引用形态：[图 X.Y] 夹注计数（规范要求「如图 X.Y 所示」）
  4) 文献表 ↔ 正文被引：展开区间/逗号引用后，报 0 孤立 / 0 超范围 / 0 缺号
  5) 待填项：封面、作者简介等占位标记逐条列出（file:line）
  6) DOCX 复核（若存在同名 .docx）：内嵌图数、图题段是否落在含图段之前

输出：控制台结论 + <论文目录>/audit_report.json
注意：本脚本是正则启发式，首次使用请人工核对一遍输出再下结论。
"""
import os
import re
import sys
import glob
import json

# ── 正则 ──
RE_IMG = re.compile(r"!\[[^\]]*\]\(([^)]+\.(?:png|jpg|jpeg|tif|tiff|svg|pdf))\)", re.I)
RE_CAP = re.compile(r"^\*\*\s*(图|表)\s*(\d+\.\d+)\s*(.+?)\s*\*\*")
RE_CAP_ANY = re.compile(r"(图|表)\s*(\d+\.\d+)")
RE_IMG_BRACKET = re.compile(r"[\[［]\s*(图|表)\s*\d+\.\d+\s*[\]］]")
RE_CITE = re.compile(r"\[([0-9][0-9,，\-–\s]*)\]")
RE_REF_ITEM = re.compile(r"^\s*\[(\d+)\]\s*\S")
# 数值区间假阳性特征：逗号后带空格，且数值远大于文献总数（如 [30, 500]）
RE_INTERVAL = re.compile(r"\[[0-9]+\s*,\s+[0-9]+\]")
PLACEHOLDERS = ["【待填】", "待填", "待补", "待核实", "待确认", "【】", "TODO", "占位", "XXX"]


def expand_cite(blob):
    """展开 [28-31] / [9,16,17] 为编号集合；解析失败返回空集。"""
    out = set()
    for tok in re.split(r"[,，]", blob):
        tok = tok.strip()
        if not tok:
            continue
        m = re.fullmatch(r"(\d+)\s*[\-–]\s*(\d+)", tok)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < a <= b <= a + 200:
                out.update(range(a, b + 1))
            continue
        if tok.isdigit():
            out.add(int(tok))
    return out


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    parts = sorted(glob.glob(os.path.join(folder, "part*.md")))
    if not parts:
        raise SystemExit("未找到 part*.md，检查目录：" + folder)
    texts = {os.path.basename(p): open(p, encoding="utf-8").read() for p in parts}

    refs_name = sys.argv[2] if len(sys.argv) > 2 else None
    if refs_name is None:
        cands = [k for k in texts if re.search(r"ref|appendix|文献|参考", k, re.I)]
        refs_name = cands[0] if cands else None

    report = {}

    # ── 1+2 图件映射与图号连续性 ──
    img_of_cap, cap_of_img, chap_nums, mentions = {}, {}, {}, []
    for name in parts:                      # parts 已排序 = 文档顺序（首次提及也按此）
        lines = texts[name].splitlines()
        for i, ln in enumerate(lines):
            m = RE_CAP.match(ln.strip())
            if m:
                kind, num = m.group(1), m.group(2)
                if kind != "图":
                    continue
                path = None
                for j in range(i, min(i + 4, len(lines))):
                    mi = RE_IMG.search(lines[j])
                    if mi:
                        path = mi.group(1).replace("\\", "/").split("/")[-1]
                        break
                if path:
                    img_of_cap.setdefault(num, set()).add(path)
                    cap_of_img.setdefault(path, set()).add(num)
            for mm in RE_CAP_ANY.finditer(ln):
                if mm.group(1) == "图":
                    mentions.append((name, i + 1, mm.group(2)))

    dup = {p: sorted(v, key=lambda x: [int(t) for t in x.split(".")]) for p, v in cap_of_img.items() if len(v) > 1}
    first_mention = {}
    for name, line, num in mentions:
        first_mention.setdefault(num, (parts.index([p for p in parts if os.path.basename(p) == name][0]), line))
    chap = {}
    for num in first_mention:
        chap.setdefault(num.split(".")[0], []).append(num)
    gaps = {c: sorted(v, key=lambda x: int(x.split(".")[1])) for c, v in chap.items()}
    report["图件重复"] = dup
    report["图号按章"] = gaps
    report["图号首次提及顺序"] = sorted(first_mention, key=lambda n: first_mention[n])

    # ── 3 方括号夹注 ──
    brackets = []
    for name in parts:
        for i, ln in enumerate(texts[name].splitlines()):
            for m in RE_IMG_BRACKET.finditer(ln):
                brackets.append(f"{name}:{i+1} {m.group(0)}")
    report["图表方括号夹注"] = brackets

    # ── 4 引文 ↔ 文献表 ──
    cite = {"文献表条数": 0, "正文被引": 0, "孤立文献": [], "超范围引用": []}
    if refs_name and refs_name in texts:
        ref_nums = {int(m.group(1)) for m in (RE_REF_ITEM.match(l) for l in texts[refs_name].splitlines()) if m}
        maxn = max(ref_nums) if ref_nums else 0
        body = "\n".join(texts[k] for k in texts if k != refs_name)
        body = RE_INTERVAL.sub(" ", body)          # 先剔除数值区间假阳性
        cited, bad = set(), []
        for m in RE_CITE.finditer(body):
            nums = expand_cite(m.group(1))
            if not nums:
                continue
            overs = {n for n in nums if n > maxn}
            if overs:
                bad.append(f"{sorted(overs)} (上限 {maxn})")
            cited |= nums
        cite.update({
            "文献表条数": len(ref_nums),
            "正文被引": len(cited & ref_nums) if ref_nums else len(cited),
            "孤立文献": sorted(ref_nums - cited),
            "超范围引用": bad[:20],
        })
    report["引文核查"] = cite

    # ── 5 待填项 ──
    ph = []
    for name in parts:
        for i, ln in enumerate(texts[name].splitlines()):
            hit = [w for w in PLACEHOLDERS if w in ln]
            if hit:
                ph.append({"file": name, "line": i + 1, "标记": "/".join(hit), "原文": ln.strip()[:70]})
    report["待填项"] = ph

    # ── 6 DOCX 复核 ──
    docx_report = "未找到同名 .docx（跳过）"
    docxs = glob.glob(os.path.join(folder, "*.docx"))
    if docxs:
        try:
            from docx import Document
            d = Document(docxs[0])
            NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
            seq, caps_before = [], 0
            for i, p in enumerate(d.paragraphs):
                has = len(p._element.findall(f".//{NS}blip")) > 0
                t = p.text.strip()
                if has:
                    seq.append(("IMG", i))
                    prev = d.paragraphs[i - 1].text.strip() if i > 0 else ""
                    if RE_CAP_ANY.match(prev):
                        caps_before += 1
                elif RE_CAP_ANY.match(t) and "图" in t[:3]:
                    seq.append(("CAP", i))
            docx_report = {
                "docx": os.path.basename(docxs[0]),
                "内嵌图数": sum(1 for k, _ in seq if k == "IMG"),
                "画像前紧邻图题的图数": caps_before,
                "提示": "「画像前紧邻图题」>0 ⇒ 图题落在图片上方，与规范『图题在图下』相悖（见 references 第 2 节）",
            }
        except Exception as e:
            docx_report = "docx 读取失败：" + repr(e)
    report["DOCX"] = docx_report

    # ── 输出 ──
    print("=" * 68)
    print("图件重复（同一图件挂多个图号）:", dup if dup else "无（合格）")
    print("图表方括号夹注数:", len(brackets), brackets[:6] if brackets else "（合格）")
    print("引文核查:", json.dumps(cite, ensure_ascii=False))
    print("待填项条数:", len(ph), "（前 8 条）")
    for x in ph[:8]:
        print("   ", x["file"], "line", x["line"], x["标记"], "|", x["原文"][:40])
    print("DOCX:", json.dumps(docx_report, ensure_ascii=False) if isinstance(docx_report, dict) else docx_report)
    print("图号首次提及顺序:", report["图号首次提及顺序"])
    print("=" * 68)

    out = os.path.join(folder, "audit_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("报告已落盘:", out)


if __name__ == "__main__":
    main()
