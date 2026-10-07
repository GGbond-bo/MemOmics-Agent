# -*- coding: utf-8 -*-
"""图表正文引用探针（只诊断，不改文件）。

配套 cn-degree-thesis-writing 铁律 8 / references/figure-table-intext-citation.md。

用法:
    python check_intext_citations.py <论文目录> [--docx 论文.docx] [--keyword 词 ...]

检查项（论文目录下 part*.md / *.md）:
    ① 括注式图表引用      （图 3.2） / （表 3.4）        → 应写「如图 3.2 所示」
    ② 方括号夹注          [图 3.2 三柱分布]             → 中文校内规范不允许
    ③ 图片 alt 简称       ![图 3.2 三柱分布](x.png)     → alt 应写「完整图题」
DOCX（--docx）: 解 zip → 剥标签 → ①② + --keyword 关键词命中统计。
                      （⚠️ 必须先剥标签：Word 跨 run 拆字，直接 grep 内部 XML 会漏检）

退出码: 0 = 未发现问题 / 1 = 存在问题 / 2 = 用法错误
"""
import os
import re
import sys
import glob

BRACKET = re.compile(r"\[([图表])\s?\d+\.[0-9]+[^\]]*\]")
PAREN = re.compile(r"[（(]([^）)\n]{0,40}?)([图表])\s?\d+\.[0-9]+")
IMG = re.compile(r"^!\[(.*?)\]\(([^)]+)\)\s*$")
CAP = re.compile(r"^\*\*([图表])\s?(\d+\.\d+)\s*[　 ]\s*(.+?)\*\*\s*$")
# 这些行里的图表提及属正常用法，跳过
SKIP_PREFIX = ("图注", "表注", ">", "| 图 ", "| 表 ", "**图 ", "**表 ")


def norm_title(s):
    return re.sub(r"\s+", "", s.replace("　", "")).strip()


def check_md(path):
    """返回 (problems, stats)；problems 为 (行号, 类型, 内容) 列表。"""
    problems = []
    lines = open(path, encoding="utf-8").read().split("\n")
    caps = {}
    for ln in lines:
        m = CAP.match(ln.strip())
        if m:
            caps.setdefault(f"{m.group(1)}{m.group(2)}", m.group(3).strip())

    n_alt, n_paren, n_bracket = 0, 0, 0
    for i, ln in enumerate(lines, 1):
        st = ln.strip()
        if not st:
            continue
        # ③ 图片 alt 简称：alt 与就近图题不一致
        m = IMG.match(st)
        if m:
            n_alt += 1
            alt, src = m.group(1), m.group(2)
            num = re.match(r"^([图表])\s?(\d+\.\d+)", alt)
            if num:
                title = caps.get(f"{num.group(1)}{num.group(2)}")
                if title and norm_title(title) not in norm_title(alt):
                    problems.append((i, "alt 简称", f"{alt}  ->  应为「{num.group(1)} {num.group(2)}　{title}」"))
            continue
        if st.startswith(SKIP_PREFIX):
            continue
        # ② 方括号夹注（排除上一条图注正文里的正常引用如「本图与图 3.7」）
        for bm in BRACKET.finditer(st):
            n_bracket += 1
            problems.append((i, "方括号夹注", bm.group(0)))
        # ① 括注式（排除已写成「如图…所示」的）
        for pm in PAREN.finditer(st):
            seg = st[max(0, pm.start() - 2):pm.end()]
            if "如" in seg:
                continue
            n_paren += 1
            problems.append((i, "括注式", pm.group(0)))
    return problems, {"alt": n_alt, "括注": n_paren, "夹注": n_bracket}


def check_docx(path, keywords):
    import zipfile
    z = zipfile.ZipFile(path)
    raw = z.read("word/document.xml").decode("utf-8")
    t = re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", raw))
    out = []
    for bm in BRACKET.finditer(t):
        out.append(("方括号夹注", bm.group(0)))
    for pm in PAREN.finditer(t):
        seg = t[max(0, pm.start() - 2):pm.end()]
        if "如" not in seg:
            out.append(("括注式", pm.group(0)))
    print(f"  DOCX 图片数(word/media): {len([n for n in z.namelist() if n.startswith('word/media/')])}")
    for kw in keywords:
        print(f"  DOCX 关键词「{kw}」命中: {t.count(kw)}")
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    d = argv[1]
    docx = None
    kws = []
    rest = argv[2:]
    i = 0
    while i < len(rest):
        if rest[i] == "--docx" and i + 1 < len(rest):
            docx = rest[i + 1]
            i += 2
        elif rest[i] == "--keyword" and i + 1 < len(rest):
            kws.append(rest[i + 1])
            i += 2
        else:
            i += 1

    files = sorted(glob.glob(os.path.join(d, "*.md")))
    if not files:
        print(f"⚠ 目录下没有 .md 母本: {d}")
    bad = 0
    for f in files:
        problems, stats = check_md(f)
        name = os.path.basename(f)
        print(f"\n== {name}  (图片 {stats['alt']} / 括注 {stats['括注']} / 夹注 {stats['夹注']})")
        for ln, kind, txt in problems:
            print(f"   🔴 {name}:{ln}  [{kind}] {txt[:110]}")
        bad += len(problems)

    if docx and os.path.exists(docx):
        print(f"\n== DOCX: {os.path.basename(docx)}")
        for kind, txt in check_docx(docx, kws):
            print(f"   🔴 [{kind}] {txt[:110]}")
            bad += 1

    print("\n结论:", "✅ 未发现图表引用格式问题" if bad == 0 else f"🔴 共 {bad} 处问题（见上）")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
