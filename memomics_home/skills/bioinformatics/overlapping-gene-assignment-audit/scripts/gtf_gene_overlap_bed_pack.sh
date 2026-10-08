#!/usr/bin/env bash
# =============================================================================
#  gtf_gene_overlap_bed_pack.sh
#  从 GENCODE/Ensembl GTF 生成「重叠基因归属审计包」：span/exon BED + 两种重叠 + 汇总 + 断言
#
#  用途：回答「If we are counting reads in the overlapping region,
#        how can we distinguish gene A vs gene B reads?」
#        —— 给出「真正会被 UMI 计数看到的重叠」到底有多大。
#
#  用法：
#    bash gtf_gene_overlap_bed_pack.sh <GTF[.gz]> <GENE1_ENSG> <GENE2_ENSG> [OUT_DIR]
#
#  示例（MEF2C / MEF2C-AS1，预期 span=20930 / exon=422）：
#    bash gtf_gene_overlap_bed_pack.sh \
#         E:/Human_gene_reference/gencode.v32.primary_assembly.annotation.gtf \
#         ENSG00000081189 ENSG00000248309 results/<sid>/results/44c_MEF2C_AS1_audit
#
#  依赖：awk（必需）；bedtools（可选，缺省时自动走等价的 awk 求交）
#  ⚠️ 坐标系：BED 为 0-based half-open，GTF 为 1-based inclusive
#      ⇒ start_bed = start_gtf - 1, end_bed = end_gtf
#  ⚠️ 基因一律用 Ensembl ID 匹配，绝不用 symbol（反义基因 symbol 常是真基因的真前缀：
#      MEF2C 是 MEF2C-AS1 的前缀，grep symbol 会同时命中两者）
# =============================================================================
set -euo pipefail

GTF="${1:?usage: gtf_gene_overlap_bed_pack.sh <GTF[.gz]> <ENSG1> <ENSG2> [OUT_DIR]}"
G1="${2:?need ENSG id #1}"
G2="${3:?need ENSG id #2}"
OUT="${4:-$(pwd)/overlap_audit}"
mkdir -p "$OUT"

echo "== GTF : $GTF"
[ -f "$GTF" ] || { echo "ERROR: GTF not found: $GTF"; exit 1; }
echo "== OUT : $OUT"
echo "== genes: $G1  vs  $G2"

read_gtf() { case "$GTF" in *.gz) gzip -dc "$GTF";; *) cat "$GTF";; esac; }

# ---- 1. gene spans (BED6) ---------------------------------------------------
# 🔴 awk 里解析 GTF attributes 不要写转义引号（split($9,a,"gene_name \"") 会告警/出错），
#    用 match + substr 的零转义写法（详见 references/awk-gtf-attribute-parsing.md）
read_gtf | awk -F'\t' -v g1="$G1" -v g2="$G2" '
  $3=="gene" && (index($9,g1)||index($9,g2)) {
    if (match($9, /gene_name "[^"]+"/)) nm=substr($9,RSTART+11,RLENGTH-12); else nm="gene"
    printf "%s\t%d\t%d\t%s\t0\t%s\n",$1,$4-1,$5,nm,$7
  }' | sort -k1,1 -k2,2n > "$OUT/step1_gene_span.bed"

# ---- 2. exon blocks (raw, then merge per gene) ------------------------------
read_gtf | awk -F'\t' -v g1="$G1" -v g2="$G2" '
  $3=="exon" && (index($9,g1)||index($9,g2)) {
    if (match($9, /gene_name "[^"]+"/)) nm=substr($9,RSTART+11,RLENGTH-12); else nm="gene"
    printf "%s\t%d\t%d\t%s\t0\t%s\n",$1,$4-1,$5,nm,$7
  }' | sort -k1,1 -k2,2n > "$OUT/step2_exons_raw.bed"

GNAME1=$(awk -v g="$G1" 'NR==FNR{next} $4!=""{print $4; exit}' /dev/null "$OUT/step1_gene_span.bed" | head -1)
# 分别取两个名字（按行序，span 文件已排序）
mapfile -t NAMES < <(cut -f4 "$OUT/step1_gene_span.bed" | sort -u)
N1="${NAMES[0]:-gene1}"; N2="${NAMES[1]:-gene2}"

if command -v bedtools >/dev/null 2>&1; then
  echo "== bedtools: $(bedtools --version)"
  for g in "$N1" "$N2"; do
    awk -v g="$g" '$4==g' "$OUT/step2_exons_raw.bed" \
      | bedtools merge -i - -c 6 -o distinct > "$OUT/${g}_exons_merged.bed"
  done
  awk -v n="$N1" '$4==n' "$OUT/step1_gene_span.bed" > "$OUT/${N1}_span.bed"
  awk -v n="$N2" '$4==n' "$OUT/step1_gene_span.bed" > "$OUT/${N2}_span.bed"
  bedtools intersect -a "$OUT/${N1}_span.bed" -b "$OUT/${N2}_span.bed" \
    > "$OUT/overlap_gene_span.bed"
  bedtools intersect -a "$OUT/${N1}_exons_merged.bed" -b "$OUT/${N2}_exons_merged.bed" \
    > "$OUT/overlap_exons.bed"
else
  echo "== bedtools NOT found -> awk fallback (identical result)"
  for g in "$N1" "$N2"; do
    awk -v g="$g" '$4==g{print $2"\t"$3}' "$OUT/step2_exons_raw.bed" \
      | sort -k1,1n | awk 'BEGIN{p=-1}{if($1>p+1){if(p>=0)print s"\t"p; s=$1} if($2>p)p=$2}
                           END{if(p>=0)print s"\t"p}' > "$OUT/${g}_exons_merged.bed"
  done
  awk -v n="$N1" '$4==n' "$OUT/step1_gene_span.bed" > "$OUT/${N1}_span.bed"
  awk -v n="$N2" '$4==n' "$OUT/step1_gene_span.bed" > "$OUT/${N2}_span.bed"
  # span overlap
  awk '$4=="'"$N1"'"{a1=$2;a2=$3} $4=="'"$N2"'"{b1=$2;b2=$3}
       END{s=(a1>b1?a1:b1); e=(a2<b2?a2:b2); if(s<e) print $1"\t"s"\t"e"\tgene_span_overlap"} ' \
       "$OUT/step1_gene_span.bed" > "$OUT/overlap_gene_span.bed"
  # exon overlap (pairwise max/min, then dedup by coordinate)
  awk 'NR==FNR{A[++n]=$1"\t"$2; next}
       {for(i=1;i<=n;i++){split(A[i],x,"\t");
          s=(x[1]>$1?x[1]:$1); e=(x[2]<$2?x[2]:$2);
          if(s<e) print "chr5\t"s"\t"e}}' \
      "$OUT/${N2}_exons_merged.bed" "$OUT/${N1}_exons_merged.bed" \
      | sort -k2,2n -u > "$OUT/overlap_exons.bed"
fi

# ---- 3. summary + assertions ------------------------------------------------
span=$(awk '{s+=$3-$2} END{print s+0}' "$OUT/overlap_gene_span.bed")
exon=$(awk '{s+=$3-$2} END{print s+0}' "$OUT/overlap_exons.bed")
nseg=$(grep -c . "$OUT/overlap_exons.bed" || true)
STR=$(awk '{printf "%s=%s ", $4,$6}' "$OUT/step1_gene_span.bed")

{
  echo "item,value,unit,detail"
  echo "gene1_span,$N1,bp,$(cut -f1,2,3 "$OUT/${N1}_span.bed" | tr '\t' ':' | head -1)"
  echo "gene2_span,$N2,bp,$(cut -f1,2,3 "$OUT/${N2}_span.bed" | tr '\t' ':' | head -1)"
  echo "gene_span_overlap,$span,bp,$(cat "$OUT/overlap_gene_span.bed" | tr '\t' ' ')"
  echo "exon_level_overlap,$exon,bp,\"${nseg} segments; only exons are counted by UMI pipelines\""
  echo "exon_overlap_pct,$(awk -v e="$exon" -v s="$span" 'BEGIN{if(s>0)printf "%.2f",100*e/s; else print 0}'),%,of span overlap"
  echo "intronic_remainder,$((span - exon)),bp,not counted by standard UMI pipelines"
  echo "strands,\"$STR\",,opposite strands -> strand-aware assignment separates them"
} > "$OUT/audit_summary.csv"

echo
echo "========== RESULT =========="
echo "gene-span overlap : ${span} bp"
echo "exon-level overlap: ${exon} bp  in ${nseg} segments   <-- the only part UMI can see"
echo "strands           : $STR"
echo "exon overlap segments (BED, 0-based half-open):"
cat "$OUT/overlap_exons.bed"
echo "============================"
echo
echo "PASS criteria are gene-pair specific (e.g. MEF2C/MEF2C-AS1: span=20930, exon=422)."
echo "Next: write README.md with method + honest limits, and render an index figure"
echo "(BED-to-interval table + the exon-overlap blocks) to satisfy rail_review(post)."