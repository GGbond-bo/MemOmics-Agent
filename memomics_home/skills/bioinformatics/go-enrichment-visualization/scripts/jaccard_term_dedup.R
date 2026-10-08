# ============================================================
# jaccard_term_dedup.R —— 富集词条冗余合并（替代 simplify/GOSemSim）
# 纯 base R 集合运算，秒级；无 clusterProfiler / GOSemSim 依赖
#
# 用法:
#   source("jaccard_term_dedup.R")
#   red_up <- jaccard_term_dedup(go_bp_sig_up, top_n = 15, tag = "up",
#                                ont = "BP", outdir = "results", thresh = 0.7)
#
# 输入 x: as.data.frame(enrichResult)，须含
#   Description (chr) | geneID ("/"分隔) | Count | GeneRatio | pvalue | p.adjust
# 输出:
#   <outdir>/go_<ont>_top<N>_jaccard_<tag>.csv         相似度矩阵
#   <outdir>/go_<ont>_redundancy_merged_<tag>.csv      簇代表词条 + Members 列
# 返回: 簇代表词条 data.frame（可直接用于出图）
#
# ⛔ 全量 enrichResult（数千词条）上不要调 simplify()/GOSemSim —— 假死。
#    见 references/go-ora-simplify-hang-and-jaccard-dedup.md
# ============================================================
jaccard_term_dedup <- function(x, top_n = 15, tag = "", ont = "BP",
                               outdir = "results", thresh = 0.7) {
  if (is.null(x) || nrow(x) == 0) return(NULL)
  if (!dir.exists(outdir)) dir.create(outdir, recursive = TRUE)

  top <- head(x[order(x$p.adjust, x$pvalue), ], top_n)
  gl  <- strsplit(top$geneID, "/")
  names(gl) <- make.unique(top$Description)

  ## ---- n x n Jaccard 矩阵 ----
  n <- length(gl)
  m <- matrix(0, n, n, dimnames = list(names(gl), names(gl)))
  for (i in seq_len(n)) for (j in seq_len(n)) if (i != j) {
    u <- length(union(gl[[i]], gl[[j]]))
    m[i, j] <- if (u > 0) length(intersect(gl[[i]], gl[[j]])) / u else 0
  }
  diag(m) <- 1
  write.csv(m, file.path(outdir, sprintf("go_%s_top%d_jaccard_%s.csv", ont, top_n, tag)))

  off <- m[row(m) != col(m)]
  cat(sprintf("%s_%s top%d Jaccard: 中位 %.3f / 最大 %.3f (>%.1f 即高度冗余)\n",
              ont, tag, top_n, median(off), max(off), thresh))

  ## ---- 贪心单趟归簇：按 p.adjust 升序，未被归簇者为簇代表 ----
  keep <- integer(0); assigned <- logical(n)
  for (i in order(top$p.adjust, top$pvalue)) {
    if (!assigned[i]) {
      keep <- c(keep, i)
      assigned[which(m[i, ] > thresh)] <- TRUE
    }
  }
  merged <- top[keep, c("Description", "Count", "GeneRatio", "pvalue", "p.adjust")]
  merged$Members <- vapply(keep, function(i)
    paste(names(gl)[m[i, ] > thresh], collapse = " ; "), character(1))
  merged <- merged[order(merged$p.adjust), ]
  write.csv(merged, file.path(outdir,
            sprintf("go_%s_redundancy_merged_%s.csv", ont, tag)), row.names = FALSE)
  cat(sprintf("  -> 去冗余后保留 %d 个代表词条 (原 %d)\n", nrow(merged), top_n))
  merged
}

# ============================================================
# 守门：只有显著子集 + 词条数 <= 200 才允许调 simplify()
# 全量 enrichResult（数千词条）上调 simplify = 假死
# ============================================================
safe_simplify <- function(sig, cutoff = 0.7, max_terms = 200) {
  if (is.null(sig) || nrow(sig) < 5) { cat("显著词条过少，跳过 simplify\n"); return(NULL) }
  if (nrow(sig) > max_terms) {
    cat(sprintf("显著词条 %d > %d，跳过 simplify（改用 Jaccard 去冗余）\n",
                nrow(sig), max_terms))
    return(NULL)
  }
  tryCatch(
    as.data.frame(simplify(sig, cutoff = cutoff, by = "p.adjust", measure = "Wang")),
    error = function(e) { cat("simplify 失败:", conditionMessage(e), "\n"); NULL })
}