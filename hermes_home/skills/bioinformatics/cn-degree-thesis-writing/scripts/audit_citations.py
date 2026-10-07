#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文献表 <-> 正文 双向一致性核查（引文-文献表对齐）

用法:
    python audit_citations.py <论文目录> [文献表文件] [正文件1 正文件2 ...]
默认:
    文献表 = part4_refs_appendix.md
    正文   = part1_front.md part2a_ch1.md part2b_ch2.md part3_ch3_ch4_ch5.md
退出码: 0 = 双向对齐; 1 = 存在孤立文献 / 超范围引用

核心设计（踩过的坑，别删）:
  1) 扫描正文前先剔除文献表定义行（^\\[N\\] ），否则文献表会被当成正文引用；
  2) 引用展开支持 区间 [28-31] / 逗号 [9,16,17] / 连排 [35][36]；
  3) 🔴 假阳性过滤: 方括号内任一分量 > 文献表最大编号 -> 判为数值区间(如目标区间 [30, 500])，
     整括跳过。实测未加此过滤时会数出 13 次幻影命中 + 凭空报出一个 "[500] 超范围引用"。
"""
import os
import re
import sys
import json
import collections

DEFAULT_REF = "part4_refs_appendix.md"
DEFAULT_BODY = ["part1_front.md", "part2a_ch1.md", "part2b_ch2.md", "part3_ch3_ch4_ch5.md"]

CITE_RE = re.compile(r"\[([\d,\-–—\s]+)\]")          # 半角引用
ANY_BRACKET = re.compile(r"[\[［][^\]］]{0,30}[\]］]")  # 兜底盘点（含全角）
DEF_RE = re.compile(r"^\[(\d+)\]\s+(.+)$")


def strip_ref_defs(text):
    """剔除文献表定义行，避免把文献表自身当成正文引用"""
    return "\n".join(l for l in text.split("\n") if not re.match(r"^\[\d+\]\s", l.strip()))


def load_refs(path):
    refs = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = DEF_RE.match(line.strip())
            if m:
                refs[int(m.group(1))] = m.group(2)[:70]
    return refs


def expand(token, ref_max):
    """展开一个方括号内的编号串；返回 (ids, is_interval)"""
    ids = set()
    for part in token.split(","):
        part = part.strip()
        if not part:
            continue
        rm = re.match(r"^(\d+)\s*[\-–—]\s*(\d+)$", part)
        if rm:
            a, b = int(rm.group(1)), int(rm.group(2))
            if a <= b and b - a < 60:      # 防区间跑飞
                ids.update(range(a, b + 1))
            else:
                ids.add(a)
        elif part.isdigit():
            ids.add(int(part))
    # 🔴 数值区间假阳性过滤
    if ids and max(ids) > ref_max:
        return set(), True
    return ids, False


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    ref_file = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_REF
    body_files = sys.argv[3:] or DEFAULT_BODY

    ref_path = os.path.join(base, ref_file)
    if not os.path.exists(ref_path):
        print("❌ 找不到文献表文件:", ref_path)
        return 2
    refs = load_refs(ref_path)
    if not refs:
        print("❌ 文献表未解析到任何条目（检查条目格式是否为 '[N] 内容'）")
        return 2
    ref_ids = sorted(refs)
    ref_max = ref_ids[-1]
    print("文献表条目数: %d  编号范围: %d-%d" % (len(ref_ids), ref_ids[0], ref_max))
    gaps = [i for i in range(ref_ids[0], ref_max + 1) if i not in refs]
    print("编号缺号:", gaps if gaps else "无")

    cites = collections.defaultdict(list)
    per_file = {}
    intervals = []
    for fn in body_files:
        p = os.path.join(base, fn)
        if not os.path.exists(p):
            continue
        text = strip_ref_defs(open(p, encoding="utf-8").read())
        hits = 0
        for line in text.split("\n"):
            for m in CITE_RE.finditer(line):
                ids, is_iv = expand(m.group(1), ref_max)
                if is_iv:
                    intervals.append((fn, m.group(0)))
                    continue
                for i in sorted(ids):
                    cites[i].append((fn, line.strip()[:110]))
                    hits += 1
        per_file[fn] = hits

    cited = set(cites)
    uncited = [i for i in ref_ids if i not in cited]
    out_of_range = sorted(i for i in cited if i not in refs)

    print("\n各分部引用命中数:", per_file)
    if intervals:
        print("判定为数值区间(非引用)的方括号: %d 个 -> %s"
              % (len(intervals), sorted(set(b for _, b in intervals))))
    print("正文被引用的文献编号数: %d" % len([i for i in cited if i in refs]))

    print("\n=== 未被正文引用（孤立文献）: %d 条 ===" % len(uncited))
    for i in uncited:
        print("  [%d] %s" % (i, refs[i]))

    print("\n=== 引用了但文献表没有（超范围）: %d 条 ===" % len(out_of_range))
    for i in out_of_range:
        print("  [%d] 出现于: %s | %s" % (i, cites[i][0][0], cites[i][0][1][:80]))

    print("\n=== 引用次数一览（核查'同一文献被复用于互不相干的论断'）===")
    for i in ref_ids:
        if i in cited:
            files = sorted(set(f for f, _ in cites[i]))
            print("  [%2d] x%-2d %s | %s" % (i, len(cites[i]), ",".join(files), cites[i][0][1][:55]))

    # 兜底盘点：确认没有正则漏掉的形式
    print("\n=== 兜底盘点（含全角括号的含数字方括号）===")
    for fn in body_files:
        p = os.path.join(base, fn)
        if not os.path.exists(p):
            continue
        cnt = collections.Counter(
            b for b in ANY_BRACKET.findall(strip_ref_defs(open(p, encoding="utf-8").read()))
            if re.search(r"\d", b))
        if cnt:
            print(" ", fn, dict(cnt))

    with open(os.path.join(base, "_cite_audit.json"), "w", encoding="utf-8") as f:
        json.dump({"refs": {str(k): v for k, v in refs.items()},
                   "uncited": uncited, "out_of_range": out_of_range,
                   "cite_counts": {str(k): len(v) for k, v in cites.items()}},
                  f, ensure_ascii=False, indent=1)
    print("\n审计结果已存 _cite_audit.json")

    ok = not uncited and not out_of_range
    print("\n结论:", "✅ 双向对齐" if ok else "❌ 存在问题，需处置后复跑")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
