#!/usr/bin/env python
"""
overlap_decomposition.py —— 两个基因模型的重叠拆解（gene span 级 vs exon 级）

为什么需要它：UMI 计数只落在外显子上，而合作者/审稿人质疑的「重叠区」通常是
GTF 里两行 start-end 相交的 **gene span**（含大量内含子）。把两层拆开量化，
就能用一个百分比把「会不会把两个基因混在一起」这个质疑关掉。

用法:
    python overlap_decomposition.py <gtf|gtf.gz> GENE_A GENE_B [--out 前缀]

示例:
    python overlap_decomposition.py gencode.v32.primary_assembly.annotation.gtf.gz MEF2C MEF2C-AS1 --out 44b

输出（stdout，同时可写 CSV）:
    每个基因：chrom / strand / biotype / gene_id / span / 外显子记录数 / 合并外显子块数 / 合并外显子 bp
    两基因：  span 重叠区与 bp / exon 级重叠段（合并后）与 bp / exon 占 span 重叠的百分比

只依赖标准库。GTF 需含 gene_name（GENCODE 风格属性，形如 gene_id "X"; gene_name "Y";）。
"""
import argparse
import csv
import gzip
import os
import sys
from collections import defaultdict


def open_maybe_gz(path):
    if path.lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def parse_attrs(field):
    """解析 GTF 第 9 列属性字段 -> dict（去引号）。"""
    d = {}
    for kv in field.strip().split(";"):
        kv = kv.strip()
        if not kv or " " not in kv:
            continue
        k, v = kv.split(" ", 1)
        d[k.strip()] = v.strip().strip('"')
    return d


def merge_iv(iv):
    """合并区间（相邻/相接也合并），返回 [[s, e], ...]。"""
    if not iv:
        return []
    iv = sorted(iv)
    out = [list(iv[0])]
    for s, e in iv[1:]:
        if s <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def intersect_iv(a, b):
    """两个已合并区间列表求交，返回 [(s, e), ...]。"""
    res, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        s, e = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if s <= e:
            res.append((s, e))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return res


def bp(iv):
    return sum(e - s + 1 for s, e in iv)


def load_genes(path, wanted):
    """扫描 GTF，收集目标基因的 gene 行与 exon 行。"""
    up = {w.upper(): w for w in wanted}
    g = {w: {"exons": [], "tx": set(), "chrom": "", "strand": "", "biotype": "",
             "gene_id": "", "start": None, "end": None, "n_exon_records": 0} for w in wanted}
    with open_maybe_gz(path) as fh:
        for line in fh:
            if not line or line[0] == "#":
                continue
            f = line.rstrip("\n").split("\t")
            if len(f) < 9:
                continue
            feat = f[2]
            if feat not in ("gene", "exon"):
                continue
            name = parse_attrs(f[8]).get("gene_name", "")
            key = up.get(name.upper())
            if key is None:
                continue
            rec = g[key]
            at = parse_attrs(f[8])
            rec["chrom"], rec["strand"] = f[0], f[6]
            rec["biotype"] = at.get("gene_type", at.get("gene_biotype", rec["biotype"]))
            rec["gene_id"] = at.get("gene_id", rec["gene_id"])
            s, e = int(f[3]), int(f[4])
            if feat == "gene":
                rec["start"], rec["end"] = s, e
            else:
                rec["exons"].append((s, e))
                rec["n_exon_records"] += 1
                if at.get("transcript_id"):
                    rec["tx"].add(at["transcript_id"])
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtf")
    ap.add_argument("gene_a")
    ap.add_argument("gene_b")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if not os.path.exists(args.gtf):
        sys.exit("GTF not found: %s" % args.gtf)

    names = [args.gene_a, args.gene_b]
    G = load_genes(args.gtf, names)

    stats_rows, ov_rows = [], []
    merged = {}
    for nm in names:
        r = G[nm]
        if not r["exons"] and r["start"] is None:
            sys.exit("gene not found in GTF (check gene_name spelling): %s" % nm)
        span = [[r["start"], r["end"]]] if r["start"] is not None else []
        if not span and r["exons"]:
            span = [[min(s for s, _ in r["exons"]), max(e for _, e in r["exons"])]]
        me = merge_iv(r["exons"])
        merged[nm] = me
        stats_rows.append({
            "gene": nm, "chrom": r["chrom"], "strand": r["strand"], "biotype": r["biotype"],
            "gene_id": r["gene_id"], "n_transcripts": len(r["tx"]),
            "n_exon_records": r["n_exon_records"], "n_merged_exon_blocks": len(me),
            "merged_exon_bp": bp(me), "gene_span_bp": span[0][1] - span[0][0] + 1 if span else 0,
            "start": span[0][0] if span else "", "end": span[0][1] if span else "",
        })
        print("[%s] %s:%s-%s (%s) %s | span=%s bp | merged exons=%d blocks / %s bp | %d exon records / %d tx"
              % (nm, r["chrom"], span[0][0] if span else "?", span[0][1] if span else "?", r["strand"],
                 r["biotype"], stats_rows[-1]["gene_span_bp"], len(me), bp(me),
                 r["n_exon_records"], len(r["tx"])))

    a, b = names
    span_a = [[stats_rows[0]["start"], stats_rows[0]["end"]]] if stats_rows[0]["start"] != "" else []
    span_b = [[stats_rows[1]["start"], stats_rows[1]["end"]]] if stats_rows[1]["start"] != "" else []
    sp = intersect_iv(span_a, span_b)
    ex = intersect_iv(merged[a], merged[b])

    print("\n=== span-level overlap (对方看到的“重叠区”) ===")
    print("  %s bp in %d segment(s): %s" % (bp(sp), len(sp),
          "; ".join("%d-%d" % (s, e) for s, e in sp) if sp else "-"))

    print("=== exon-level overlap (UMI 真正能计数的重叠) ===")
    print("  %s bp in %d segment(s): %s" % (bp(ex), len(ex),
          "; ".join("%d-%d" % (s, e) for s, e in ex) if ex else "-"))
    pct = (bp(ex) / bp(sp) * 100) if bp(sp) else 0.0
    print("  exon overlap = %.2f%% of span overlap" % pct)
    print("  intronic / intergenic remainder (never counted by UMI): %s bp" % (bp(sp) - bp(ex)))

    for s, e in sp:
        ov_rows.append({"item": "gene_span_overlap", "value_bp": bp(sp), "n_segments": len(sp),
                        "note": "; ".join("%d-%d" % (x, y) for x, y in sp)})
        break
    ov_rows.append({"item": "exon_level_overlap", "value_bp": bp(ex), "n_segments": len(ex),
                    "note": "; ".join("%d-%d" % (x, y) for x, y in ex)})
    ov_rows.append({"item": "exon_overlap_pct_of_span", "value_bp": "%.2f" % pct, "n_segments": "",
                    "note": "UMI counting only sees exons"})
    ov_rows.append({"item": "intronic_or_between", "value_bp": bp(sp) - bp(ex), "n_segments": "",
                    "note": "not counted by standard UMI pipelines"})

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out + "_stats.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(stats_rows[0].keys()))
            w.writeheader()
            w.writerows(stats_rows)
        with open(args.out + "_overlap.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["item", "value_bp", "n_segments", "note"])
            w.writeheader()
            w.writerows(ov_rows)
        print("\nwritten: %s_stats.csv , %s_overlap.csv" % (args.out, args.out))


if __name__ == "__main__":
    main()