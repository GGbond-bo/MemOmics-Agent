# Motif Enrichment for Non-UCSC Genomes with Small DA Tile Sets

## Problem

When running motif enrichment on DA tiles from T2T/non-UCSC genomes:
1. **JASPAR2024 broken API** — `getMatrixSet(JASPAR2024)` fails. Use **JASPAR2020**.
2. **NCBI→UCSC chr mapping** — T2T assemblies use NC_088xxx.1, BSgenome uses chr1
3. **T2T coords exceed BSgenome bounds** — older BSgenome (rheMac10) shorter than T2T → `getSeq` fails "beyond boundaries"
4. **48-60 tiles too few for Fisher test** — 633 motifs × Bonferroni → all FDR=1

## Verified Workflow (2026-07-29, macaque hippocampus T2T)

### 1. NCBI→UCSC mapping + bounds check
```r
nc2chr <- c("NC_088375.1"="chr1", ..., "NC_088395.1"="chrX")
make_gr <- function(df, genome) {
  df$chr <- nc2chr[df$seqnames]
  df <- df[!is.na(df$chr), ]
  df$end <- df$start + 499
  clen <- seqlengths(genome)
  df <- df[df$end <= clen[df$chr], ]  # bounds check
  GRanges(seqnames=df$chr, ranges=IRanges(start=df$start, end=df$end))
}
```

### 2. JASPAR2020 + score-based ranking
```r
library(JASPAR2020)  # NOT JASPAR2024
motifs <- getMatrixSet(JASPAR2020, list(species=9606, collection="CORE"))
scores <- matchMotifs(motifs, seqs, genome=genome, out="scores")
# Rank by mean score fold-change (not p-value — 48 tiles too few)
results <- data.frame(
  motif = colnames(scores),
  fc = colMeans(assay(fg_scores)) / pmax(colMeans(assay(bg_scores)), 0.001)
)[order(-fc), ]
```

### 3. Annotate IDs → TF names
```r
sapply(head(results$motif, 10), function(id) name(motifs[[id]]))
```

## Key Results (Macaque Hippocampus Aging)
| Group | Top TF | FC | Relevance |
|-------|--------|:--:|-----------|
| OLD | CEBPB | 5.28 | Inflammation/senescence pioneer TF |
| OLD | ZFP57 | 6.14 | Imprinting maintenance |
| YOUNG | HOXB8 | 8.38 | Adult neurogenesis |
| YOUNG | FOSL1::JUND | 3.40 | AP-1, synaptic plasticity |

## Common Pitfalls
- `names(gr)` returns empty — use `as.character(seqnames(gr))`
- `assay(fg_scores)` is a matrix, NOT `assay(fg_scores)[[1]]`
- Always filter tiles beyond BSgenome boundaries before `getSeq`

## Visualization + HTML Report Integration (2026-08-02 验证)

motif 分析跑完**不算收尾** — 必须出图 + 整合进报告 + 更新 task_plan + record_run。

### 1. TF 名映射 + Top-TF 柱状图 (run_motif_figs.R)

```r
# ID → TF 名映射 (JASPAR2020)
id2name <- sapply(motifs, function(m) { n <- name(m); if(length(n)==0) NA else gsub("::.*$","::…", n[1]) })
# 注意: 同一 TF 可能同时富集在 Old/Young 两侧 (如 PITX1/ZFP57/GBX1) → duplicated 加 * 标注

# Top-12 barplot (Old 红 #E64B35 / Young 蓝 #4DBBD5)
df$tf <- factor(df$tf, levels=rev(df$tf))
ggplot(df, aes(x=tf, y=fc)) + geom_bar(stat="identity", fill=color, alpha=0.85) +
  geom_text(aes(label=sprintf("%.2f", fc)), hjust=-0.15) + coord_flip() +
  labs(title=paste0("Top ", label, "-enriched TF motifs (score FC vs background)"))
```

### 2. 向已有 HTML 报告追加 Phase section (23_add_motif_to_report.py)

**不要重新生成整个报告** — 用 anchor 插入法保持原有结构完整：

```python
# ① timeline 追加新 phase
html = html.replace(
  '<div class="phase done">…Phase 5…</div>',
  '<div class="phase done">…Phase 5…</div>\n    <div class="phase done">…Phase 6…</div>')
# ② 在新 section 的 anchor 注释前插入 (找唯一 anchor, 如 '<!-- Pipeline Details -->')
assert '<!-- Pipeline Details -->' in html   # anchor 必须唯一, 否则双插
html = html.replace('<!-- Pipeline Details -->', motif_section + "\n" + anchor)
# ③ base64 嵌入图 + CSV 排名表转 HTML table (含 old-enriched/young-enriched 行着色)
# ④ 验证: anchor 只出现 1 次 (html.count(section_title) == 1), base64 图数只增不减
```

关键发现框 (finding div) 应写**两侧对比结论** + 共享 TF 提示，不写文件清单。

### 3. 收尾协议 (系统唤醒发现"跑完未收尾"时补做)

```
Phase 分析完成 → 立即:
  1. 可视化图 (PNG/PDF)   ← 本次缺: Motif_Top_Old/Young.png
  2. 整合进 HTML 报告      ← 本次缺: Phase 6 section + 表格
  3. task_plan.md 补记 Phase + Status: complete + Key findings + Issues
  4. skill_evolution(action="record_run")
  5. 临时验证脚本 (22/22 checks, 跑完清理)
```

### 4. Key Results (Macaque Hippocampus Aging) — 补充

| Group | Top TF | FC | 说明 |
|-------|--------|:--:|------|
| OLD | ZFP57 | 6.14 | imprinting maintenance |
| OLD | CEBPB | 5.28 | inflammation pioneer |
| OLD | MLX/MLXIPL | 4.41/3.94 | metabolism |
| OLD | VENTX | 4.39 | homeobox |
| YOUNG | HOXB8 | 8.38 | adult neurogenesis |
| YOUNG | BHLHE41 | 3.63 | clock |
| YOUNG | FOSL1::JUND | 3.40 | AP-1 |
| 共享 | PITX1/ZFP57/GBX1 | — | 两侧均富集 → 年龄重塑共享+方向特异模块 |
