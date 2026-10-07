# -*- coding: utf-8 -*-
"""把 WPS/Word 实测页码（wps_pages.py 产出的 json）回写进母本 part1_front.md 的
目录 / 插图清单 / 附表清单，并顺带做去重与条数核对。

用法：
    python wps_writeback.py <thesis_dir> [页码json]

前置：先跑 wps_pages.py 拿到 _wps_pages.json
改完必须**重渲染** DOCX（页码只改数字，版式不变，实测页码继续有效）。
"""
import io
import json
import os
import re
import sys

BASE = sys.argv[1] if len(sys.argv) > 1 else r"E:/path/to/results/thesis"
J = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, "_wps_pages.json")
P1 = os.path.join(BASE, "part1_front.md")

r = json.load(open(J, encoding="utf-8"))
fig, tab, sec, head = r["fig"], r["tab"], r["sec"], r["head"]
print(f"[输入] 实测总页 {r['total_pages']} | 摘要 p{r['front_page']} | 第1章 p{r['body_page']}")

s = io.open(P1, encoding="utf-8").read()
cnt = {"fig": 0, "tab": 0, "toc": 0}


def fix_list(name, mapping, key_char):
    """回写一个清单块：换页码 + 按号去重 + 保持原行序"""
    global s
    m = re.search(r"(### " + name + r"\n\n\|.*?\n\|[-|\s]+\n)((?:\|.*\n)+)", s)
    assert m, name + " 未找到"
    rows, seen, out, missing = m.group(2).strip("\n").split("\n"), set(), [], []
    for line in rows:
        mm = re.match(r"\| " + key_char + r"(\d+(?:\.\d+)+) \| (.*?) \| (.*?) \|", line)
        if mm:
            num = mm.group(1)
            if num in seen:                      # ★ 同号重复行 → 丢弃
                print(f"  [{name}] 丢弃重复行 {key_char}{num}")
                continue
            seen.add(num)
            if num in mapping:
                out.append(f"| {key_char}{num} | {mm.group(2)} | {mapping[num]} |")
                cnt["fig" if key_char == "图" else "tab"] += 1
                continue
        out.append(line)
    for num in mapping:                          # ★ 正文有、清单漏登记 → 补行（页码待填）
        if num not in seen:
            missing.append(num)
            out.append(f"| {key_char}{num} | （待补题名） | {mapping[num]} |")
    if missing:
        print(f"  [{name}] ⚠ 清单漏登记，已补：{missing}")
    s = s[:m.start(2)] + "\n".join(out) + "\n" + s[m.end(2):]


fix_list("插图清单", fig, "图")
fix_list("附表清单", tab, "表")
print(f"[回写] 插图清单 {cnt['fig']} 行 / 附表清单 {cnt['tab']} 行")

# 目录：块前常有一行格式说明 → 正则必须放宽（不要用 ## 目　录\n\n```）
tm = re.search(r"## 目\u3000录[\s\S]*?```\n([\s\S]*?)\n```", s)
assert tm, "目录块未找到"
new = []
for line in tm.group(1).split("\n"):
    mm = re.match(r"^(.*?)(…+)\s*(\S+)\s*$", line)
    if mm:
        ttl, dots = mm.group(1).rstrip(), mm.group(2)
        core = re.sub(r"[\s\u3000]+", "", ttl)
        pg = None
        m2 = re.match(r"^(\d+\.\d+(?:\.\d+)?)", core)
        if m2 and m2.group(1) in sec:
            pg = sec[m2.group(1)]
        elif core in head:
            pg = head[core]
        if pg:
            new.append(f"{ttl} {dots} {pg}")
            cnt["toc"] += 1
            continue
    new.append(line)
s = s[:tm.start(1)] + "\n".join(new) + s[tm.end(1):]
print(f"[回写] 目录 {cnt['toc']} 行")

s = s.replace("> ⚠️ 页码为版面示意，Word 生成后须更新域（Ctrl+A → F9）并据实校对。",
              f"> 页码取自办公套件（WPS/Word）实测分页：全文 {r['total_pages']} 页；"
              f"前置罗马数字自摘要起，主体阿拉伯数字自第1章起。")

io.open(P1, "w", encoding="utf-8").write(s)
print("[完成] part1_front.md 已按实测页码更新 —— 记得重渲染 DOCX")
