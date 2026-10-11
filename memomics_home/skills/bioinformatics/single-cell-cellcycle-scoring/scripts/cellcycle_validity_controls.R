## ============================================================
##  cellcycle_validity_controls.R
##  细胞周期打分的「判读控制」一键探针
##
##  用法（bash，直调绝对路径；别套 cmd //c）:
##    "/c/Program Files/R/R-4.5.3/bin/x64/Rscript.exe" --vanilla \
##        scripts/cellcycle_validity_controls.R \
##        "E:/data/obj.rds" "type" "samplename" "results/<sid>"
##
##  参数: 1=Seurat .rds  2=分组列名(6 组或 3 组)  3=样本列名  4=输出目录(可选)
##  产出: results/celllevel_cellcycle.csv, samplelevel_cellcycle.csv,
##        prolif_marker_detection.csv, icc_design_effect.csv,
##        permutation_tests.csv, bootstrap_resampling.csv
##  并且在控制台末尾打印一行 VERDICT（是否可解读相位标签）
## ============================================================
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) stop("用法: Rscript cellcycle_validity_controls.R <rds> <group_col> <sample_col> [out_dir]")
RDS <- args[1]; GROUP <- args[2]; SAMPLE <- args[3]
OUT <- if (length(args) >= 4) args[4] else "results/cellcycle_validity"
dir.create(OUT, showWarnings = FALSE, recursive = TRUE)
dir.create(file.path(OUT, "log"), showWarnings = FALSE, recursive = TRUE)

## 日志（崩溃也保住结果）——持久内核里跑时尤其重要
con <- file(file.path(OUT, "log", "cellcycle_validity.log"), open = "wt", encoding = "UTF-8")
sink(con, split = TRUE)

suppressPackageStartupMessages({library(Seurat); library(Matrix)})
set.seed(1)
obj <- readRDS(RDS); DefaultAssay(obj) <- "RNA"
cat("input:", ncol(obj), "cells |", nrow(obj), "genes | group:", GROUP, "| sample:", SAMPLE, "\n")

## ---------- 1. 打分 ----------
s_g <- cc.genes.updated.2019$s.genes; g_g <- cc.genes.updated.2019$g2m.genes
cat(sprintf("cc gene coverage: S %d/%d | G2M %d/%d\n",
            sum(s_g %in% rownames(obj)), length(s_g), sum(g_g %in% rownames(obj)), length(g_g)))
obj <- CellCycleScoring(obj, s.features = s_g, g2m.features = g_g, set.ident = FALSE)
obj$Phase <- factor(obj$Phase, levels = c("G1", "S", "G2M"))
md <- obj@meta.data; md$Phase <- obj$Phase; md$isCycling <- md$Phase %in% c("S", "G2M")
print(table(md$Phase))
cat(sprintf("S.Score range %.4f | G2M.Score range %.4f  (范围极小 => 分类阈值落在噪声带)\n",
            diff(range(obj$S.Score)), diff(range(obj$G2M.Score))))

## ---------- 2. 阴性对照：真实增殖 marker 可检出率 ----------
genes <- intersect(c("MKI67","PCNA","TOP2A","HIST1H4C","CCNB1","CDK1","MCM2","PAX7","MYOD1"), rownames(obj))
ex <- as.matrix(LayerData(obj, assay = "RNA", layer = "data")[genes, , drop = FALSE])
det <- ex > 0
mk <- data.frame()
for (g in genes) {
  mk <- rbind(mk,
    data.frame(gene = g, level = "phase",  unit = as.character(md$Phase),    det = det[g, ]),
    data.frame(gene = g, level = "group",  unit = as.character(md[[GROUP]]), det = det[g, ]),
    data.frame(gene = g, level = "sample", unit = as.character(md[[SAMPLE]]), det = det[g, ]))
}
mk_s <- aggregate(det ~ gene + level + unit, data = mk, FUN = function(z) round(100 * mean(z), 2))
names(mk_s)[4] <- "pct_det"
write.csv(mk_s, file.path(OUT, "prolif_marker_detection.csv"), row.names = FALSE)
cat("\n== 检出率 (phase) ==\n");  print(mk_s[mk_s$level == "phase", ])
cat("\n== 检出率 (group) ==\n");  print(mk_s[mk_s$level == "group", ])

mki67_phase <- mk_s$pct_det[mk_s$gene == "MKI67" & mk_s$level == "phase"]
mki67_samp  <- mk_s$pct_det[mk_s$gene == "MKI67" & mk_s$level == "sample"]
pct_cyc     <- 100 * mean(md$isCycling)

## 特异性检查：cc 基因集基线表达是否失衡
mg <- Matrix::rowMeans(LayerData(obj, assay = "RNA", layer = "data"))
baseS <- mean(mg[s_g]); baseG <- mean(mg[g_g])
naive <- 100 * mean(Matrix::colMeans(LayerData(obj, assay = "RNA", layer = "data")[s_g, , drop = FALSE]) >
                    Matrix::colMeans(LayerData(obj, assay = "RNA", layer = "data")[g_g, , drop = FALSE]))
cat(sprintf("\n基线表达: S 集 %.4f vs G2M 集 %.4f | 朴素均值比较 %%S = %.1f%% (Seurat 打分 %%S = %.1f%%)\n",
            baseS, baseG, naive, 100 * mean(md$Phase == "S")))

## ---------- 3. 样本级汇总 + ICC / 设计效应 ----------
agg <- data.frame(sample = md[[SAMPLE]], group = md[[GROUP]], Phase = md$Phase, isCyc = md$isCycling)
aggL <- aggregate(cbind(isCyc, S = as.numeric(Phase == "S"), G2M = as.numeric(Phase == "G2M")) ~ sample + group,
                  data = agg, FUN = mean)
aggL$n <- as.numeric(table(md[[SAMPLE]])[as.character(aggL$sample)])
aggL$pct_Cyc <- 100 * aggL$isCyc; aggL$nCyc <- aggL$isCyc * aggL$n
write.csv(aggL, file.path(OUT, "samplelevel_cellcycle.csv"), row.names = FALSE)

x <- aggL$nCyc; n <- aggL$n; k <- nrow(aggL); N <- sum(n); m0 <- N / k; pbar <- sum(x) / N
MSB <- sum(n * (x / n - pbar)^2) / (k - 1); MSW <- sum(n * (x / n) * (1 - x / n)) / (N - k)
ICC <- (MSB - MSW) / (MSB + (m0 - 1) * MSW); DEFF <- 1 + (m0 - 1) * ICC
icc_df <- data.frame(samples = k, nuclei_per_sample = round(m0, 1), total_N = N,
                     ICC = round(ICC, 4), design_effect = round(DEFF, 2), effective_n = round(N / DEFF, 1))
write.csv(icc_df, file.path(OUT, "icc_design_effect.csv"), row.names = FALSE)
cat("\n== ICC / 设计效应 ==\n"); print(icc_df)

## ---------- 4. 供体级置换（打乱 样本->组 标签）----------
cnt  <- table(md[[SAMPLE]], md$Phase)
grp  <- as.character(md[[GROUP]][match(rownames(cnt), as.character(md[[SAMPLE]]))])
labs <- unique(grp)
sum_by <- function(g) { m <- matrix(0, length(labs), 3, dimnames = list(labs, c("G1","S","G2M")))
  for (i in seq_along(g)) m[match(g[i], labs), ] <- m[match(g[i], labs), ] + as.numeric(cnt[i, ]); m }
obs <- suppressWarnings(chisq.test(sum_by(grp))$statistic)
B <- 2000; set.seed(42); perm <- numeric(B)
for (b in 1:B) perm[b] <- suppressWarnings(chisq.test(sum_by(sample(grp)))$statistic)
p_cell <- (sum(perm >= obs) + 1) / (B + 1)
kw_obs <- kruskal.test(aggL$pct_Cyc ~ aggL$group)$statistic
set.seed(43); pk <- numeric(B); for (b in 1:B) pk[b] <- kruskal.test(aggL$pct_Cyc ~ sample(aggL$group))$statistic
p_kw <- (sum(pk >= kw_obs) + 1) / (B + 1)
perm_df <- data.frame(test = c("cell-level phase chi2", "sample-level KW pct_Cyc"),
                      asymptotic_p = c(signif(chisq.test(sum_by(grp))$p.value, 4),
                                       signif(kruskal.test(aggL$pct_Cyc ~ aggL$group)$p.value, 4)),
                      permutation_p = c(round(p_cell, 4), round(p_kw, 4)), permutations = B)
write.csv(perm_df, file.path(OUT, "permutation_tests.csv"), row.names = FALSE)
cat("\n== 供体级置换 ==\n"); print(perm_df)
cat("提醒: >=3 个指标必须 BH 校正后再看有无显著项\n")

## ---------- 5. n 核重抽样 bootstrap ----------
sp <- split(seq_len(nrow(md)), md[[SAMPLE]]); nn <- round(m0)
set.seed(99); Bs <- 500; bs <- numeric(Bs)
for (b in 1:Bs) {
  v <- sapply(sp, function(ii) 100 * mean(md$isCycling[sample(ii, nn, replace = TRUE)]))
  bs[b] <- kruskal.test(v ~ grp)$p.value
}
boot_df <- data.frame(median_p = round(median(bs), 3), lo95 = round(quantile(bs, .025), 3),
                      hi95 = round(quantile(bs, .975), 3), pct_below_0.05 = round(100 * mean(bs < 0.05), 1))
write.csv(boot_df, file.path(OUT, "bootstrap_resampling.csv"), row.names = FALSE)
cat("\n== n 核重抽样 bootstrap (pct_Cyc) ==\n"); print(boot_df)

## ---------- 6. 判定行 ----------
no_prolif <- length(mki67_phase) > 0 && max(mki67_phase) < 1 && pct_cyc > 30
cat(sprintf("\nVERDICT: MKI67 phase-detection max = %.2f%% (sample-level max %.2f%%) | S+G2M = %.1f%%\n",
            if (length(mki67_phase)) max(mki67_phase) else NA, if (length(mki67_samp)) max(mki67_samp) else NA, pct_cyc))
if (no_prolif) cat("VERDICT: ⛔ 无增殖细胞 —— 相位标签不可作生物学解读，不得用于组间比较\n") else
  cat("VERDICT: 存在可检出增殖细胞 —— 可做组间比较，但须 BH 校正 + 分层，并报效应量\n")
cat("产出目录:", normalizePath(OUT), "\n")
sink(); close(con)