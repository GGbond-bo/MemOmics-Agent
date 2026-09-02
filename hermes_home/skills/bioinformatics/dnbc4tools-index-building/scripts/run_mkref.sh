#!/bin/bash
# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 此脚本由 MemOmics Agent 执行。原脚本永远不被修改。
#
# 执行前必须:
#   1. rail_review(action="pre")  — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs", script_name="本脚本名",
#      species="物种", tissue="组织", direction="方向")
#      → 查同类运行日志，有则参考已有参数和经验，无则按原脚本执行
#   3. debate_analysis(topic, context) — 参数不确定时多角色辩论
#
# 执行后必须:
#   1. rail_review(action="post") — 检查输出/质量/图表
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. ref.json 是否存在且非空？
#        b. RNA: Genome/SA/SAindex 是否生成（非 0KB）？
#        c. ATAC: genome.index/tss.bed/promoter.bed/chrom.sizes 是否生成？
#        d. 日志是否以 "Analysis Complete" / "finished successfully" 结尾？
#        e. 数值/文件名与知识库对应？
#   2. 如果通过 → skill_evolution(action="record_run", ...)
#   3. 如果失败 → skill_evolution(action="record_error", ...)
#
# ★ 参数和结论辩论铁律:
#   - 参数选择（--threads/--limitram/--chrM/--species/--prefix）
#     → 必须调 debate_analysis 辩论
#   - 最多3轮，3轮后选最优结果
# ============================================================

set -euo pipefail

# ========== 用户待填参数区 ==========
DNBC4TOOLS="/opt/software/dnbc4tools2.1.3/dnbc4tools"  # 可执行程序路径
GENOME_FA="genome.fa"          # 参考基因组 FASTA（primary 组装）
GENES_GTF="genes.gtf"          # 原始注释 GTF（必需，非 GFF）
SPECIES="Homo_sapiens"         # Homo_sapiens / Mus_musculus / 其他
CHRM="auto"                    # 线粒体染色体名，auto 识别 chrM/MT/chrMT/mt/Mt
OUTDIR="genomeDir"             # 输出数据库目录
THREADS=10                     # 线程数
LIMITRAM=125000000000          # mkref 最大 RAM（bytes），按机器调整
ASSAY="rna"                    # rna 或 atac
PREFIX="chr"                   # atac 专用：染色体名前缀
# ===================================

# ---- Step 1: GTF 过滤（可选但强烈推荐）----
"$DNBC4TOOLS" tools mkgtf --ingtf "$GENES_GTF" --output genes.filter.gtf --type gene_type
echo "[OK] GTF filter done"

# ---- Step 2a: scRNA 索引构建（STAR 2.7.2b）----
if [ "$ASSAY" = "rna" ]; then
  "$DNBC4TOOLS" rna mkref \
    --fasta "$GENOME_FA" \
    --ingtf genes.filter.gtf \
    --species "$SPECIES" \
    --chrM "$CHRM" \
    --genomeDir "$OUTDIR" \
    --limitram "$LIMITRAM" \
    --threads "$THREADS"
  # 验证
  test -s "$OUTDIR/ref.json" && echo "[OK] ref.json exists"
  test -s "$OUTDIR/Genome" && echo "[OK] STAR Genome exists"
  test -s "$OUTDIR/SAindex" && echo "[OK] STAR SAindex exists"
fi

# ---- Step 2b: scATAC 索引构建（chromap 0.2.6）----
if [ "$ASSAY" = "atac" ]; then
  "$DNBC4TOOLS" atac mkref \
    --fasta "$GENOME_FA" \
    --ingtf genes.filter.gtf \
    --species "$SPECIES" \
    --prefix "$PREFIX" \
    --genomeDir "$OUTDIR" \
    --threads "$THREADS"
  # 验证
  test -s "$OUTDIR/ref.json" && echo "[OK] ref.json exists"
  test -s "$OUTDIR/genome.index" && echo "[OK] chromap index exists"
  test -s "$OUTDIR/tss.bed" && echo "[OK] tss.bed exists"
  test -s "$OUTDIR/promoter.bed" && echo "[OK] promoter.bed exists"
fi

echo "=== Analysis Complete ==="
echo "ref.json 内容："
cat "$OUTDIR/ref.json"