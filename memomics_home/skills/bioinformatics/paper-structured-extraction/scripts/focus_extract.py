# -*- coding: utf-8 -*-
"""多篇论文语料 Step 3：收敛式抽取（把「读全文」降级为「读命中句」）。

用法:
    python focus_extract.py <txt_dir> <out_dir> [--per-file 22]

思路:
    只保留「同一行里既有数字、又含质控/统计关键词」的句子，每篇压成 ~50 行、
    每行前缀 L<行号>| 锚回原 txt。之后才逐篇读这些小文件；需要上下文时
    用 read_file(offset=行号, limit=40~55) 定点回读原文核对。

⚠️ 本脚本是「定位器」不是「事实来源」：任何要写进交付的阈值都必须回原文核对，
   尤其线粒体阈值（<5% 保留 vs >10% 剔除）、min_gene/min_cells、MAPQ、bin 大小、
   参考基因组版本（hg19 vs hg38 可能同篇混用）。
"""
import argparse
import os
import re

# 行内必须同时命中：数字 + 下方 QC 关键词，才会被 QC_THRESHOLD 段收录
QC_KW = (
    r"(?i)(quality|filter|exclud|discard|doublet|ambient|mitochond|MT[- ]?%|\bUMI|"
    r"gene count|detected genes|features|threshold|criteria|criteri|cut-?off|retain|"
    r"passing|removed|decontam|clean)"
)
STAT_KW = (
    r"(?i)(Wilcoxon|MAST|DESeq2|edgeR|limma|pseudobulk|Mann-Whitney|Benjamini|Hochberg|"
    r"\bFDR\b|adjusted p|Bonferroni|permutation|log2|fold change|two-sided|Monocle|"
    r"Slingshot|Harmony|SCTransform|Seurat|Scanpy|Louvain|Leiden|resolution|UMAP|t-SNE|"
    r"Cell ?Ranger|STAR|Solo|SingleR|inferCNV|CellChat|GSEA|GO |KEGG|correlat|regress|"
    r"linear model|mixed model|t-test|ANOVA|chi-square|Fisher)"
)
PLAT_KW = (
    r"(?i)(Stereo-?seq|DNBelab|dnbc4tools|10[xX]|Visium|Smart-?seq|Drop-?seq|Slide-?seq|"
    r"seqFISH|MERFISH|Rhapsody|bin ?\d|sequencing depth|reads per|Q30|saturation|"
    r"GRCh|hg19|hg38|mm10|GENCODE|Ensembl|reference)"
)


def grab(lines, kw, need_num=True, cap=22, width=185):
    """收集命中行；need_num=True 时要求行内含数字（滤掉纯铺陈句）。"""
    rx = re.compile(kw)
    out, seen = [], set()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if len(s) < 25 or not rx.search(s):
            continue
        if need_num and not re.search(r"\d", s):
            continue
        item = f"L{i + 1}| {s[:width]}"
        # 去重键：行内容前 75 字符（跨篇重复的版权页/参考文献会被压掉）
        dedup = item[5:80]
        if dedup in seen:
            continue
        seen.add(dedup)
        out.append(item)
        if len(out) >= cap:
            break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("txt_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--per-file", type=int, default=22, help="每类最多保留行数")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    files = sorted(
        f for f in os.listdir(args.txt_dir)
        if f.endswith(".txt") and not f.startswith("_")
    )
    if not files:
        print(f"[ERR] no .txt in {args.txt_dir}")
        return

    for name in files:
        key = name[:-4]
        lines = open(os.path.join(args.txt_dir, name), encoding="utf-8").read().splitlines()
        # 摘要要点：前 200 行里够长的正文行
        abs_head = [l.strip()[:190] for l in lines[:200] if len(l.strip()) > 40][:16]

        parts = [f"### {key}  (total {len(lines)} lines)", "", "## ABSTRACT_HEAD"]
        parts += ["  " + x for x in abs_head]
        parts += ["", "## QC_THRESHOLD_SENTENCES"]
        parts += ["  " + x for x in grab(lines, QC_KW, True, args.per_file)]
        parts += ["", "## PLATFORM_REF_SENTENCES"]
        parts += ["  " + x for x in grab(lines, PLAT_KW, False, 12)]
        parts += ["", "## TOOLS_STATS_SENTENCES"]
        parts += ["  " + x for x in grab(lines, STAT_KW, False, 18)]

        outp = os.path.join(args.out_dir, f"focus_{key}.txt")
        with open(outp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(parts))
        print(f"{key}: {len(abs_head)} abs lines -> {outp} ({len(''.join(parts))} chars)")


if __name__ == "__main__":
    main()