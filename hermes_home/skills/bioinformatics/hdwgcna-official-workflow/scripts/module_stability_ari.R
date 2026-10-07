# =====================================================================
# 模块稳定性 / 可重复性评估（hdWGCNA 建网后必做，出性状结论前强制）
# ---------------------------------------------------------------------
# 用途: 判定 "N 个模块" 是真结构还是小样本过分割噪声
#
# 🔴 2026-09-24 修复（本脚本 v1 自带两个静默 bug，务必读这段）:
#   bug-1 split-half 用了 ncol(datExpr)（=基因数）分半 + datExpr[, idx]（取列）
#         => 实际切成「基因对半分」，根本不是「metacell 对半分」，结果全无效。
#         指纹: 日志打出 "半样本 odd: 5558 samples" 而 5558 = 11116/2（基因数一半）。
#         修: nrow(datExpr)（=样本/metacell）+ datExpr[idx, , drop=FALSE]（取行）。
#   bug-2 permuted 注释写「逐基因打乱」，实现是 apply(datExpr, 1, sample)（逐样本打乱）。
#         两者都破坏共表达，但只有 per-gene 版保持每个基因的表达分布 = 标准零模型。
#         修: t(apply(datExpr, 2, sample))。
#   教训: 凡「日志里的数字与它的文本标签对不上」= 维度/索引方向的 bug 指纹，
#         立刻回查 nrow/ncol 与 [i,] / [,j]。本脚本已加 stopifnot 朝向断言防复发。
#
# 变体（次序即优先级）:
#   [0] reproduce  : 同 datExpr 重跑（参数与 hdWGCNA::ConstructNetwork 对齐）
#                    -> ARI 必须 ≈1，这一条是变体可比性的前提
#                    ⚠️ 实测常得 0.95 而非 1.0 —— ConstructNetwork 有固有随机性
#   [1] permuted   : 严格零模型，逐基因在样本间打乱（保持基因分布，只破坏共表达）
#                    -> 判据不是「模块数变少」，而是**看 grey 占比**（见文件尾判读段）
#   [2] split-half : metacell 奇/偶各半独立建网 -> 直接可重复性（按行分半！）
#   [3] variants   : k=3/type、k=3|k=5 annotation_L3、单细胞直接建网
#   [4] seed       : 同 datExpr 仅改 randomSeed -> 区分「实现差异」vs「建网固有随机性」
# 每变体独立 tryCatch + 结果增量落盘 CSV + 全程 trace 写日志（execute_r 吞 stdout 时唯一可靠证据）
# ---------------------------------------------------------------------
# 用法（Windows/R 4.4.2）:
#   setwd("<session_dir>")   # 或改下方 BASE
#   Rscript --vanilla scripts/module_stability_ari.R
# 前置: BASE/results/hdwgcna/ 下已有 primary 建网对象（含 misc[[WN]]$datExpr + wgcna_modules）
# =====================================================================
options(error = function() { cat("\n=== TRACEBACK ===\n"); traceback(2, max.lines=3); quit(status=1) })
suppressPackageStartupMessages({ library(Seurat); library(WGCNA) })
loadNamespace("hdWGCNA"); .h <- asNamespace("hdWGCNA"); GETFN <- function(f) get(f, envir = .h)
set.seed(123)

## ---------------- 改这里 ----------------
BASE      <- "E:/MemOmics-Agent/results/<session_dir>"
PRIMARY   <- "phase2_network_k5type_f005_pow9.rds"   # 已建网对象（data/ 下）
WN        <- "MF_wgcna"
POW       <- 9
DATASET   <- "E:/path/to/original.rds"               # 仅 [3] 的 metacell 变体需要
RUN_SEED  <- TRUE                                    # [4] seed 变体（+8 分钟；只验可比性时可关）
VARIANTS  <- list(                                   # group.by, k
  list(gb = "type", k = 3L),
  list(gb = "annotation_L3", k = 3L),
  list(gb = "annotation_L3", k = 5L)
)
## ---------------------------------------

DATDIR <- file.path(BASE, "data"); RESDIR <- file.path(BASE, "results", "hdwgcna")
con <- file(file.path(BASE, "log", "stability_ari.log"), open = "wt")
TR <- function(...) { cat(..., "\n", file = con, sep = ""); flush(con) }
TR("=== 模块稳定性评估 | ", format(Sys.time()), " ===")

## ---- 判据工具（手写，不依赖 mclust）----
ari <- function(x, y) {
  x <- as.character(x); y <- as.character(y)
  tab <- table(x, y); n <- sum(tab)
  if (n < 2) return(NA_real_)
  a <- rowSums(tab); b <- colSums(tab)
  s_ij <- sum(choose(tab, 2)); s_a <- sum(choose(a, 2)); s_b <- sum(choose(b, 2))
  e <- s_a * s_b / choose(n, 2); mx <- (s_a + s_b) / 2
  if (mx == e) 1 else (s_ij - e) / (mx - e)
}
jac_stats <- function(p1, p2, lab1, lab2) {
  out <- numeric(0)
  for (m in setdiff(unique(p1), "grey")) {
    g1 <- lab1[p1 == m]; best <- 0
    for (m2 in setdiff(unique(p2), "grey")) {
      g2 <- lab2[p2 == m2]
      j <- length(intersect(g1, g2)) / length(union(g1, g2))
      if (j > best) best <- j
    }
    out <- c(out, best)
  }
  list(mean_jac = mean(out), median_jac = median(out),
       n_jac_ge50 = sum(out >= 0.5), n_modules = length(out))
}

## ---- 建网（参数逐项对齐 hdWGCNA::ConstructNetwork，见 SKILL.md 实测 formals）----
runBlock <- function(datExpr, tag, seed = 12345) {
  t0 <- Sys.time()
  # 防呆: WGCNA 要求 行=样本 列=基因; 样本数一定远小于基因数（小样本场景）
  stopifnot(nrow(datExpr) < ncol(datExpr))
  m <- blockwiseModules(datExpr, power = POW, networkType = "signed", TOMType = "signed",
                        TOMDenom = "min", minModuleSize = 50, mergeCutHeight = 0.2,
                        deepSplit = 4, pamStage = FALSE, randomSeed = seed,
                        maxBlockSize = 30000, verbose = 0, saveTOMs = FALSE)
  TR(sprintf("  [%s] %.1f min | 输入 %d samples x %d genes | 唯一色=%d | 非grey=%d | grey 基因=%d (%.0f%%)",
             tag, as.numeric(difftime(Sys.time(), t0, units = "mins")),
             nrow(datExpr), ncol(datExpr),
             length(unique(m$colors)), length(setdiff(unique(m$colors), "grey")),
             sum(m$colors == "grey"), 100 * sum(m$colors == "grey") / ncol(datExpr)))
  m$colors
}

## ---- 载入 primary ----（datExpr 朝向必须 样本×基因；WGCNA 要求行=样本）
o <- readRDS(file.path(DATDIR, PRIMARY))
mods <- GETFN("GetModules")(o, wgcna_name = WN)
primary_lab <- setNames(mods$module, mods$gene_name)
datExpr <- o@misc[[WN]][["datExpr"]]
if (is.null(datExpr)) datExpr <- as.matrix(GETFN("GetMetacellExpression")(o, wgcna_name = WN))
if (nrow(datExpr) > ncol(datExpr)) { datExpr <- t(datExpr); TR("  datExpr 已转置 -> samples x genes") }

# 🔴 显式朝向断言（防 bug-1 那类 nrow/ncol 混用复发）：列数必须等于模块标签数
stopifnot(ncol(datExpr) == length(primary_lab), nrow(datExpr) < ncol(datExpr))
genes <- colnames(datExpr)
n_samp <- nrow(datExpr)                       # 样本/metacell 数（split-half 分的是这个）
TR("primary datExpr: ", n_samp, " samples x ", ncol(datExpr), " genes | 非grey 模块 ",
   length(setdiff(unique(primary_lab), "grey")))
TR("  （朝向断言通过: ncol == 模块标签数, nrow < ncol）")

res <- list()
add <- function(tag, desc, cols, cmp_genes = NULL) {
  lab <- as.character(cols); names(lab) <- names(cols)      # colors 以基因名为 names
  if (is.null(cmp_genes)) cmp_genes <- intersect(genes, names(primary_lab))
  p1 <- primary_lab[cmp_genes]; p2 <- lab[cmp_genes]
  keep <- !is.na(p1) & !is.na(p2); p1 <- p1[keep]; p2 <- p2[keep]
  js <- jac_stats(p1, p2, names(p1), names(p2))
  av <- ari(p1, p2)
  res[[tag]] <<- data.frame(
    variant = tag, desc = desc, n_genes = length(p1),
    n_modules = length(setdiff(unique(p2), "grey")), grey_n = sum(p2 == "grey"),
    ARI_vs_primary = round(av, 4), mean_jaccard = round(js$mean_jac, 4),
    median_jaccard = round(js$median_jac, 4), n_jac_ge0.5 = js$n_jac_ge50,
    pct_jac_ge0.5 = round(100 * js$n_jac_ge50 / max(js$n_modules, 1), 1),
    stringsAsFactors = FALSE)
  write.csv(do.call(rbind, res), file.path(RESDIR, "stability_ari.csv"), row.names = FALSE)
  TR(sprintf("  -> ARI=%.4f | mean Jaccard=%.4f | %d/%d 模块 Jaccard>=0.5",
             av, js$mean_jac, js$n_jac_ge50, js$n_modules))
}

## ---- [0] reproduce 对照（ARI 必须 ≈1）----
TR("\n[0] reproduce 对照")
c0 <- tryCatch(runBlock(datExpr, "reproduce"), error = function(e) { TR("  FAIL: ", conditionMessage(e)); NULL })
if (!is.null(c0)) add("reproduce", "同 datExpr 重跑(参数对齐校验)", c0)

## ---- [1] permuted 严格零模型（关键判据）----
TR("\n[1] permuted 零模型（逐基因在样本间打乱，保持基因分布）")
cP <- tryCatch({
  dp <- t(apply(datExpr, 2, sample))       # 按【列=基因】打乱 -> genes x samples -> 转回
  dimnames(dp) <- dimnames(datExpr)
  ok <- isTRUE(all.equal(sort(dp[, 1]), sort(datExpr[, 1])))
  TR("  打乱后列分布一致性校验: ", ifelse(ok, "PASS（仅破坏共表达，分布不变）", "FAIL"))
  runBlock(dp, "permuted")
}, error = function(e) { TR("  FAIL: ", conditionMessage(e)); NULL })
if (!is.null(cP)) add("permuted", "严格零模型: 逐基因在样本间打乱", cP)

## ---- [2] split-half（🔴 按【行=样本/metacell】分半，不是按基因）----
TR("\n[2] split-half（metacell 奇/偶对半分）")
for (half in c("odd", "even")) {
  idx <- if (half == "odd") seq(1, n_samp, by = 2) else seq(2, n_samp, by = 2)
  TR("  半样本 ", half, ": 取第 ", min(idx), "-", max(idx), " 个 metacell, 共 ", length(idx),
     " 个 | 子矩阵 ", length(idx), " samples x ", ncol(datExpr), " genes")
  cH <- tryCatch(runBlock(datExpr[idx, , drop = FALSE], paste0("split_", half)),
                 error = function(e) { TR("  FAIL: ", conditionMessage(e)); NULL })
  if (!is.null(cH)) add(paste0("split_", half),
                        sprintf("%s 半(%d metacells)按行分半独立建网", half, length(idx)), cH)
}

## ---- [3] 参数变体（metacell 重建 + 单细胞直接建网）----
TR("\n[3] 参数变体")
obj0 <- readRDS(DATASET); DefaultAssay(obj0) <- "RNA"
mkdat <- function(gb, k, frac = 0.05) {
  oo <- GETFN("SetupForWGCNA")(obj0, gene_select = "fraction", fraction = frac, wgcna_name = WN)
  oo <- GETFN("MetacellsByGroups")(oo, group.by = gb, k = k, max_shared = 2L, min_cells = 5L,
                                   reduction = "pca", ident.group = gb, wgcna_name = WN)
  oo <- GETFN("NormalizeMetacells")(oo, wgcna_name = WN)     # 漏这两步 -> Layer 'data' is empty
  oo <- GETFN("ScaleMetacells")(oo, wgcna_name = WN)
  m <- oo@misc[[WN]][["wgcna_metacell_obj"]]                 # 键名实证 = wgcna_metacell_obj
  gcol <- intersect(c(gb, "group", "groups"), colnames(m@meta.data))[1]
  oo <- GETFN("SetDatExpr")(oo, group_name = sort(unique(as.character(m@meta.data[[gcol]]))),
                            group.by = gcol, use_metacells = TRUE, assay = "RNA",
                            layer = "data", wgcna_name = WN)
  de <- oo@misc[[WN]][["datExpr"]]
  if (is.null(de)) de <- as.matrix(GETFN("GetMetacellExpression")(oo, wgcna_name = WN))
  if (nrow(de) > ncol(de)) de <- t(de)
  list(de = de, n_mc = ncol(m))
}
for (v in VARIANTS) {
  tag <- paste0("k", v$k, "_", v$gb)
  cc <- tryCatch({
    r <- mkdat(v$gb, v$k)
    # 标签写「samples」（=行数）——v1 这里曾把行数打成 "genes"，误导排查
    TR("  ", tag, ": ", nrow(r$de), " samples x ", ncol(r$de), " genes | mc=", r$n_mc)
    runBlock(r$de, tag)
  }, error = function(e) { TR("  FAIL(build ", tag, "): ", conditionMessage(e)); NULL })
  if (!is.null(cc)) add(tag, sprintf("metacell k=%d/%s", v$k, v$gb), cc)
}
cS <- tryCatch({                                              # 单细胞直接建网（不经 metacell）
  o1 <- NormalizeData(obj0, verbose = FALSE)
  m1 <- as.matrix(LayerData(o1, assay = "RNA", layer = "data"))
  gs <- intersect(genes, rownames(m1))
  TR("  单细胞矩阵: ", length(gs), " genes x ", ncol(m1), " cells")
  runBlock(t(m1[gs, , drop = FALSE]), "single_cell")
}, error = function(e) { TR("  FAIL: ", conditionMessage(e)); NULL })
if (!is.null(cS)) add("single_cell", "原始细胞直接建网", cS)

## ---- [4] seed 对照（同 datExpr 仅改 randomSeed）----
if (RUN_SEED) {
  TR("\n[4] seed 对照（randomSeed=999）")
  cSd <- tryCatch(runBlock(datExpr, "seed999", seed = 999),
                  error = function(e) { TR("  FAIL: ", conditionMessage(e)); NULL })
  if (!is.null(cSd)) add("seed999", "同 datExpr 仅改 randomSeed=999", cSd)
}

## ---- 总表 ----（混合两批结果时按 ARI 降序排列，reproduce 应在最上）
TR("\n=========== 稳定性总表 ===========")
tab <- do.call(rbind, res); rownames(tab) <- NULL
tab <- tab[order(-tab$ARI_vs_primary), ]
capture.output(print(tab, row.names = FALSE), file = con, append = TRUE)
write.csv(tab, file.path(RESDIR, "stability_ari.csv"), row.names = FALSE)

## ---- 判读（2026-09-24 实测校准过的阈值，不要只看「模块数」）----
TR("\n判读:")
TR("  [0] ARI 必须 >=0.9（否则复现管线不等价, 变体比较无意义）。")
TR("      ⚠️ 实测同 datExpr 同参数重跑常得 ~0.95 而非 1.0 = ConstructNetwork 固有随机性；")
TR("         此时别急着判失败 —— 先跑 [4] seed 对照，若换 seed 也掉到同一量级，")
TR("         说明是随机性而非「你的复现管线写错了」。")
TR("  [1] 🔴 判据不是「permuted 模块数变少」，而是 grey 占比：")
TR("      实测(11116 基因/37 metacell)打乱后仍产出 37 个非 grey 模块，但 grey 从 4651 掉到 524；")
TR("      primary 也只在 grey 里留 4651 —— 说明在 300:1 基因:样本比下，")
TR("      『模块数多』本身不构成信号证据。真正能定论的是 [2][3][4] 的一致性。")
TR("  [2] split-half 两半 ARI 低 => 模块不可重复（实测 ARI 0.15-0.21 / Jaccard>=0.5 仅 1/57）。")
TR("  [3] 变体 ARI 低 => 参数敏感/过分割（实测 k3_type 0.08 / k3_L3 0.04 / single_cell 0.02）。")
TR("  🔑 合判断：除 [0] 外全部变体 ARI<=0.21 且 Jaccard>=0.5 的模块仅 0-1/57")
TR("      => 模块划分对参数极度敏感，禁止据此输出性状关联结论（降级为探索性描述）。")
TR("[稳定性评估完成]")
close(con)