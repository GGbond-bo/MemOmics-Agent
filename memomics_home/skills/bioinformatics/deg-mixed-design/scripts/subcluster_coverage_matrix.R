#!/usr/bin/env Rscript
# =============================================================================
# subcluster_coverage_matrix.R -- 逐亚群 × 逐组 的细胞/样本覆盖矩阵（只读）
#   → 开工前可行性核查：先知道哪些「亚群 × 比较组」能跑，再投 DEG 作业
#
# 用法:
#   Rscript subcluster_coverage_matrix.R <rds> <outdir> \
#       --subcluster annotation_L3 --sample samplename --group type \
#       --min-cells 10 \
#       --map "Young_normal=Y_Pre,Young_normal_Post=Y_Post,Old_normal=O_Pre,\
# Old_normal_Post=O_Post,Old_diabete=OD_Pre,Old_diabete_Post=OD_Post"
#
# 输出: stdout 打印四张表 + 4 个 csv（细胞数 / 原始样本数 / 达标样本数 / 比较组配对数）
#
# 口径（必须与你的 DEG 脚本的过滤逻辑逐字对齐）:
#   达标 = 该样本在该亚群内细胞数 >= min_cells
#   可跑 = 比较组两侧的达标样本数均 >= 2
#
# 实测教训（2026-10-09, MuSC 6 亚群 × 5 比较组 = 30 作业只出 15 个 csv，
#           缺口 100% 由数据决定，开工前 10 秒可算）:
#   1) 「原始样本数」够 ≠ 可跑 —— min_cells 过滤后可能凑不齐两组各 2
#   2) 分组列真实取值常 ≠ 脚本硬编码 levels → 先打印 unique() 再映射
#   3) dplyr::recode 对未命中值【原样保留】不产生 NA ⇒ 守卫必须用 %in% 集合判定
#   4) 过样本门 ≠ 能跑完：还会死在 ①残差 df 不足（配对+RE 样本对数太少）
#      ②design 秩亏 ③MAST 无结果 ⇒ 预测可差 ±1，汇报时主动解释
#   5) 纯统计任务也必须出图，否则 rail_review(post) 因 figure_count=0 判 failed
# =============================================================================

suppressPackageStartupMessages(library(Seurat))

args <- commandArgs(trailingOnly = TRUE)
getopt <- function(k, def = NULL) {
  i <- match(k, args)
  if (is.na(i)) return(def)
  args[i + 1]
}
if (length(args) < 2) {
  cat("用法: Rscript subcluster_coverage_matrix.R <rds> <outdir> [--subcluster col] [--sample col] [--group col] [--min-cells N] [--map 'A=X,B=Y']\n")
  quit(status = 1)
}
rds_path  <- args[1]
outdir    <- args[2]
sub_col   <- getopt("--subcluster", "annotation_L3")
samp_col  <- getopt("--sample",     "samplename")
grp_col   <- getopt("--group",      "type")
min_cells <- as.integer(getopt("--min-cells", "10"))
map_str   <- getopt("--map", NULL)

if (!file.exists(rds_path)) stop("rds 不存在: ", rds_path)
cat("[read]", rds_path, "\n")
m  <- readRDS(rds_path)
md <- m@meta.data

for (cl in c(sub_col, samp_col, grp_col))
  if (!cl %in% names(md))
    stop("meta.data 里没有列 '", cl, "'；现有列: ", paste(names(md), collapse = ", "))

md$Sample <- as.character(md[[samp_col]])
md$ct     <- as.character(md[[sub_col]])
raw_grp   <- as.character(md[[grp_col]])

cat("\n=== 分组列真实取值（先看这个再决定映射）===\n")
print(table(raw_grp))

if (!is.null(map_str)) {
  kv  <- strsplit(gsub("[\r\n ]", "", map_str), ",")[[1]]
  MAP <- stats::setNames(sub("^[^=]*=", "", kv), sub("=.*$", "", kv))
  md$grp <- unname(MAP[raw_grp])
  # recode 未命中原样保留 ⇒ 用 %in% 集合判定，不能用 anyNA()
  unmapped <- setdiff(unique(raw_grp), names(MAP))
  if (length(unmapped))
    stop("映射覆盖不全，未映射取值: ", paste(unmapped, collapse = ","))
  cat("\n[map] 映射后分布:\n"); print(table(md$grp))
  if (anyNA(md$grp)) stop("映射产生了 NA（检查映射表）")
} else {
  md$grp <- raw_grp
  cat("\n[map] 未给 --map，直接用原始取值。⚠️ 若 DEG 脚本用短码 levels，先补映射\n")
}

GRPS <- sort(unique(md$grp))
cts  <- sort(unique(md$ct))

mk <- function(v) matrix(v, nrow = length(cts), ncol = length(GRPS),
                        dimnames = list(cts, GRPS))
cell_n <- mk(0L)   # 细胞数
samp_n <- mk(0L)   # 原始样本数（该组在该亚群有 >=1 细胞）
ok_n   <- mk(0L)   # 达标样本数（该样本在该亚群内 >= min_cells）★唯一决定可跑性

for (ct in cts) for (g in GRPS) {
  rows <- md$ct == ct & md$grp == g
  cell_n[ct, g] <- sum(rows)
  tb <- table(md$Sample[rows])
  samp_n[ct, g] <- length(tb)
  ok_n[ct, g]   <- sum(tb >= min_cells)
}

cat(sprintf("\n[meta] 细胞 %d | 样本 %d | 亚群 %d | 组 %d | min_cells %d\n",
            nrow(md), length(unique(md$Sample)), length(cts), length(GRPS), min_cells))
cat("\n### 表1 细胞数 (亚群 x 组)\n");                    print(cell_n)
cat("\n### 表2 原始样本数(>=1 细胞)\n");                  print(samp_n)
cat(sprintf("\n### 表3 达标样本数(>=%d 细胞) <-- 唯一决定可跑性\n", min_cells)); print(ok_n)

prs <- combn(GRPS, 2)
cmp <- matrix("", nrow = ncol(prs), ncol = length(cts),
              dimnames = list(apply(prs, 2, paste, collapse = "_vs_"), cts))
for (k in seq_len(ncol(prs))) {
  a <- prs[1, k]; b <- prs[2, k]
  for (ct in cts) cmp[k, ct] <- sprintf("%d / %d", ok_n[ct, a], ok_n[ct, b])
}
cat("\n### 表4 比较组两侧达标样本对数 (侧1 / 侧2)，两侧均>=2 才可跑\n")
print(cmp)

ok_side <- vapply(strsplit(as.vector(cmp), " */ *"), function(x) sum(as.integer(x) >= 2), 0L)
run_n   <- stats::setNames(colSums(matrix(ok_side >= 2, nrow = nrow(cmp))), cts)
cat("\n### 每个亚群的可跑比较组数 (分母 =", nrow(cmp), ")\n")
print(run_n)
cat(sprintf("\n[plan] 样本门通过的可跑组合: %d / %d\n", sum(ok_side >= 2), length(ok_side)))
cat("⚠️ 过样本门 != 能跑完（残差 df 不足 / design 秩亏 / MAST 无结果），±1 误差属正常\n")

dir.create(outdir, showWarnings = FALSE, recursive = TRUE)
write.csv(cell_n, file.path(outdir, "stat_cells_by_subcluster_group.csv"))
write.csv(samp_n, file.path(outdir, "stat_samples_raw_by_subcluster_group.csv"))
write.csv(ok_n,   file.path(outdir, "stat_samples_valid_by_subcluster_group.csv"))
write.csv(cmp,    file.path(outdir, "stat_comparison_sample_pairs.csv"))
cat("\n[out] 4 个 csv ->", outdir, "\n")
cat("[next] 交付记得配一张覆盖率热图（纯统计任务也必须有图，否则 rail_review(post) 判 failed）\n")