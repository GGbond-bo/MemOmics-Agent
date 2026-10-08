# -*- coding: utf-8 -*-
"""学位论文 图/表编号体检 + 按「出现顺序」重编号（幂等）。

三类高频缺陷（都是实测撞过的）：
  ① 题注出现顺序与编号顺序不一致（例：图2.2 排在 图2.1 之前 / 表3.3 排在 表3.2 之前）
     → 规范要求按在文中出现的先后顺序连续编码
  ② 插图清单 / 附表清单 与正文题注**对不上**：漏登记、同号重复行
  ③ 某张图/表只有图题、正文里**完全没有**叙述式引用（"如图X 所示"）→ 审稿人必问

用法：
    python audit_and_renumber_figures_tables.py --dir <thesis目录> [--parts a.md,b.md,...] [--apply]

--apply 时：按出现顺序做**双射置换**（编号互换），正文引用、目录、清单自动跟随；
            清单按号去重并按出现序重排；页码列留待 wps_writeback.py 重填。
"""
import argparse
import io
import os
import re
import sys

DEFAULT_PARTS = ["part1_front.md", "part2a_ch1.md", "part2b_ch2.md",
                 "part3_ch3_ch4_ch5.md", "part4_refs_appendix.md"]
CAP = re.compile(r"^\*\*(图|表)(\d+)\.(\d+)　(.+?)\*\*\s*$")
LIST_ROW = re.compile(r"^\| (图|表)(\d+(?:\.\d+)+) \| (.*?) \| (.*?) \|\s*$")


def read_parts(d):
    parts = os.environ.get("THESIS_PARTS")
    names = parts.split(",") if parts else DEFAULT_PARTS
    out = []
    for f in names:
        p = os.path.join(d, f)
        if os.path.exists(p):
            out.append((f, io.open(p, encoding="utf-8").read()))
    return out


def scan(files):
    """收集题注（按出现顺序）与清单行"""
    caps, rows = [], []
    for f, s in files:
        for i, l in enumerate(s.split("\n"), 1):
            t = l.strip()
            m = CAP.match(t)
            if m:
                caps.append({"kind": m.group(1), "num": f"{m.group(2)}.{m.group(3)}",
                             "title": m.group(4), "file": f, "line": i})
            m2 = LIST_ROW.match(t)
            if m2:
                rows.append({"kind": m2.group(1), "num": m2.group(2),
                             "title": m2.group(3), "file": f})
    return caps, rows


def desired_mapping(caps):
    """按出现顺序算每个前缀组（章）内的期望编号：同章第 k 次出现 → k+1"""
    seen = {}
    mp = {}
    for c in caps:
        pre = c["num"].split(".")[0]
        seen[pre] = seen.get(pre, 0) + 1
        want = f"{pre}.{seen[pre]}"
        if want != c["num"]:
            mp[c["num"]] = want
    return mp


def renumber(files, mapping, d):
    """双射置换：先用占位符，避免 1↔2 互换时互相覆盖"""
    changed = 0
    for f, s in files:
        orig = s
        for old, new in mapping.items():
            s = re.sub(rf"([图表]){re.escape(old)}(?![0-9])", rf"\1\u0001{new}\u0001", s)
        s = s.replace("\u0001", "")
        if s != orig:
            io.open(os.path.join(d, f), "w", encoding="utf-8").write(s)
            changed += 1
            print(f"  [renumber] {f} 已更新")
    return changed


def fix_lists(files, d):
    """清单：按号去重 + 按数值序重排（页码列原样保留，随后由 wps_writeback 重填）"""
    for name, key in (("插图清单", "图"), ("附表清单", "表")):
        f, s = next(((f, s) for f, s in files if name in s), (None, None))
        if not s:
            print(f"  [{name}] 未找到")
            continue
        m = re.search(r"(### " + name + r"\n\n\|.*?\n\|[-|\s]+\n)((?:\|.*\n)+)", s)
        rows = m.group(2).strip("\n").split("\n")
        seen, out = set(), []
        for r in rows:
            mm = LIST_ROW.match(r.strip())
            if not mm:
                out.append(r)
                continue
            if mm.group(2) in seen:
                print(f"  [{name}] 去重 {key}{mm.group(2)}")
                continue
            seen.add(mm.group(2))
            out.append(r)
        out.sort(key=lambda r: tuple(int(x) for x in (LIST_ROW.match(r.strip()).group(2).split(".")
                                                      if LIST_ROW.match(r.strip()) else ["9999"])))
        s = s[:m.start(2)] + "\n".join(out) + "\n" + s[m.end(2):]
        io.open(os.path.join(d, f), "w", encoding="utf-8").write(s)
        print(f"  [{name}] 去重+重排 → {len(out)} 行")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--parts", default="")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.parts:
        os.environ["THESIS_PARTS"] = a.parts
    d = a.dir

    files = read_parts(d)
    caps, rows = scan(files)
    print(f"[扫描] 题注 {len(caps)} 条 | 清单行 {len(rows)} 条")

    # ① 顺序体检
    bad = {}
    for kind in ("图", "表"):
        seq = [c["num"] for c in caps if c["kind"] == kind]
        for pre in sorted({n.split(".")[0] for n in seq}):
            g = [n for n in seq if n.startswith(pre + ".")]
            if g != sorted(g, key=lambda x: int(x.split(".")[1])):
                bad[pre + kind] = g
    print("[① 顺序]", "全部一致 ✓" if not bad else f"✗ 不一致：{bad}")

    # ② 清单元数据核对
    for kind in ("图", "表"):
        cset = {c["num"] for c in caps if c["kind"] == kind}
        rset = {r["num"] for r in rows if r["kind"] == kind}
        dup = [r["num"] for r in rows if r["kind"] == kind and
               [x["num"] for x in rows if x["kind"] == kind].count(r["num"]) > 1]
        print(f"[② 清单 {kind}] 题注 {len(cset)} / 清单 {len(rset)} | 漏登记 {sorted(cset - rset)} | "
              f"多余 {sorted(rset - cset)} | 重复 {sorted(set(dup))}")

    # ③ 正文引用体检
    allt = "\n".join(s for _, s in files)
    nocite = []
    for c in caps:
        n = c["num"]
        hits = len(re.findall(rf"[如见][^。\n]{{0,8}}{c['kind']}{re.escape(n)}(?![0-9])", allt))
        if hits == 0:
            nocite.append(c["kind"] + n)
    print("[③ 正文引用]", "每张图/表都有引用 ✓" if not nocite else f"✗ 无正文引用：{nocite}")

    if not a.apply:
        print("\n（仅体检；加 --apply 执行按出现顺序重编号 + 清单去重重排）")
        return

    mp = desired_mapping(caps)
    if mp:
        print("[重编号] 映射:", mp)
        renumber(files, mp, d)
    files = read_parts(d)
    fix_lists(files, d)
    print("\n[完成] 记得重跑渲染脚本，并重跑 wps_pages.py + wps_writeback.py 校正页码")


if __name__ == "__main__":
    sys.exit(main())
