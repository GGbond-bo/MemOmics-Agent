# =============================================================================
# 组成校正的决定性检验（individual-level pseudobulk）—— 可跑模板
# -----------------------------------------------------------------------------
# 用途：把组织级 pseudobulk 的"衰老效应"分解为【组成项】与【细胞内在项】。
#       同一批数据、同一个矩阵，只改模型（不换口径、不换输入）。
# 配套：<skill>/references/composition-adjusted-pseudobulk-da.md（判据/解读/坑）
#
# 用法：改下面 CONFIG 五处 → 在 R 持久内核里 source() 本文件
#       一次跑完 4 项判据 + 落盘 4 个产物 + 出 1 张四面板图
#
# 输入要求：
#   - Y: 个体级 pseudobulk 矩阵（ArchR getGroupSE(groupBy="Sample")），peak × 个体
#   - meta: 细胞级元数据 CSV，至少含 celltype / individual / Age 三列
#   - 🔴 colnames(Y) 与 meta 的 individual 必须是同一集合（脚本内含 stopifnot 断言）
# 输出：
#   results/组成校正_<标签>_摘要.csv / _逐peak.csv.gz / _组成vs年龄.csv / _分层.csv
#   figures/<标签>组成校正决定性检验.png
# =============================================================================

## ---------------- CONFIG（只改这里） ----------------
SE_RDS   <- "path/to/GroupSE_byindividual.rds"   # 个体级 pseudobulk, assay="PeakMatrix"
META_CSV <- "path/to/cell_level_meta.csv"        # 细胞级：celltype + individual + Age
OUT      <- "path/to/results_dir"
TAG      <- "人侧"                                # 产物前缀（如 人侧 / 猴侧）
DROP_CT  <- "Unknown"                            # 排除的细胞类型
# ----------------------------------------------------

suppressMessages(library(SummarizedExperiment))
dir.create(file.path(OUT, "results"), showWarnings = FALSE, recursive = TRUE)
dir.create(file.path(OUT, "figures"), showWarnings = FALSE, recursive = TRUE)

## ---------- 1. 载入 + 对齐（❌ 不靠顺序，靠 match） ----------
x  <- readRDS(SE_RDS)
Y  <- as.matrix(assay(x, "PeakMatrix"))
cd <- as.data.frame(colData(x))
h  <- read.csv(META_CSV, stringsAsFactors = FALSE)

ind <- colnames(Y)                                   # 矩阵列 = 个体
Age <- cd$Age[match(ind, rownames(cd))]              # 🔴 按名字对齐
stopifnot(!any(is.na(Age)))
stopifnot(!any(is.na(match(ind, unique(h$individual)))))   # 列↔元数据同集合

## ---------- 2. 组成矩阵 + CLR（🔴 0.5 零替换，否则 -Inf → 全 NaN） ----------
W <- table(h$individual, h$celltype)
cts <- setdiff(colnames(W), DROP_CT)
W <- W[ind, cts, drop = FALSE]
P <- W / rowSums(W)                                   # 原始占比：报告/作图用
nzero <- sum(W == 0)
cat(sprintf("[2b] 零细胞格: %d / %d → CLR 前 0.5 零替换\n", nzero, length(W)))
Wp  <- W + 0.5
Pp  <- Wp / rowSums(Wp)
clr <- log(Pp) - rowMeans(log(Pp))
Z   <- clr[, -ncol(clr), drop = FALSE]                # 🔴 丢 1 列，避免与截距共线
stopifnot(!anyNA(Z), is.finite(det(crossprod(cbind(1, Z)))))   # 断言前置

## ---------- 3. 归一化 + 向量化 OLS（❌ 不要逐行 lm） ----------
Ylog <- log2(t(t(Y) / colSums(Y) * 1e6) + 1)
fit <- function(X) {
  XtX_inv <- solve(crossprod(X))
  B   <- Ylog %*% X %*% XtX_inv
  R   <- Ylog - Ylog %*% X %*% XtX_inv %*% t(X)
  RSS <- rowSums(R^2); TSS <- rowSums((Ylog - rowMeans(Ylog))^2)
  df  <- ncol(Ylog) - ncol(X); s2 <- RSS / df
  list(B = B, se = sqrt(outer(s2, diag(XtX_inv))), R2 = 1 - RSS / TSS, df = df)
}
Xa <- cbind(int = 1, Age = Age)                        # A 现行组织级口径
Xb <- cbind(int = 1, Age = Age, Z)                     # B 组成校正
Xc <- cbind(int = 1, Z)                                # C 纯组成
fa <- fit(Xa); fb <- fit(Xb); fc <- fit(Xc)

pa <- 2 * pt(-abs(fa$B[, "Age"] / fa$se[, 2]), fa$df)
pb <- 2 * pt(-abs(fb$B[, "Age"] / fb$se[, 2]), fb$df)
fdr_a <- p.adjust(pa, "BH"); fdr_b <- p.adjust(pb, "BH")
sig_a <- fdr_a < 0.05; sig_b <- fdr_b < 0.05

## ---------- 4. 四项判据 ----------
# ① 组成-年龄关联
sp <- sapply(cts, function(ct) {
  r <- suppressWarnings(cor.test(P[, ct], Age, method = "spearman"))
  c(rho = unname(r$estimate), p = r$p.value)
})
spdf <- data.frame(celltype = cts, rho = sp["rho", ], p = sp["p", ], row.names = NULL)

# ② 方差分解
r2_age <- median(fa$R2); r2_comp <- median(fc$R2); r2_full <- median(fb$R2)
uniq_age <- r2_full - r2_comp; uniq_comp <- r2_full - r2_age
shared <- r2_age + r2_comp - r2_full

# ③ 显著数存留
retention <- mean(sig_b[sig_a])
flip <- mean(sign(fa$B[sig_a, "Age"]) != sign(fb$B[sig_a, "Age"]))
shrink <- median(abs(fb$B[, "Age"])) / median(abs(fa$B[, "Age"]))

# ④ 组成载荷四分位分层
qs <- cut(fc$R2, breaks = quantile(fc$R2, 0:4 / 4), labels = paste0("Q", 1:4), include.lowest = TRUE)
tab <- data.frame(                                     # 🔴 列名一律 ASCII（含 % 会解析期报错）
  Q              = levels(qs),
  n              = as.integer(table(qs)),
  R2_comp_median = as.numeric(tapply(fc$R2, qs, median)),
  A_sig_pct      = 100 * as.numeric(tapply(sig_a, qs, mean)),
  B_sig_pct      = 100 * as.numeric(tapply(sig_b, qs, mean)),
  retention_pct  = sapply(levels(qs), function(q) {
    i <- qs == q & sig_a; if (!sum(i)) return(NA_real_); 100 * mean(sig_b[i]) }),
  betaA_median   = as.numeric(tapply(abs(fa$B[, "Age"]), qs, median)),
  betaB_median   = as.numeric(tapply(abs(fb$B[, "Age"]), qs, median)),
  row.names = NULL)

cat("\n==== ① 组成 vs 年龄 ====\n"); print(spdf[order(-abs(spdf$rho)), ], row.names = FALSE, digits = 4)
cat(sprintf("\n==== ② 方差分解 ====\n  R2(Age)=%.5f  R2(Comp)=%.5f  R2(Full)=%.5f\n  唯一Age=%.5f (%.1f%%)  唯一组成=%.5f (%.1f%%)  共享=%.5f (%.1f%%)\n",
            r2_age, r2_comp, r2_full,
            uniq_age,  100 * uniq_age  / (uniq_age + uniq_comp + shared),
            uniq_comp, 100 * uniq_comp / (uniq_age + uniq_comp + shared),
            shared,    100 * shared    / (uniq_age + uniq_comp + shared)))
cat(sprintf("\n==== ③ 显著数 ====\n  A=%d/%d  B=%d/%d  存留率=%.2f%%  翻转=%.2f%%  收缩比=%.3f\n",
            sum(sig_a), length(sig_a), sum(sig_b), length(sig_b),
            100 * retention, 100 * flip, shrink))
cat("\n==== ④ 组成载荷分层 ====\n"); print(tab, row.names = FALSE, digits = 5)

## ---------- 5. 落盘 ----------
write.csv(data.frame(peak = seq_len(nrow(Y)), beta_A = fa$B[, "Age"], p_A = pa, fdr_A = fdr_a,
                     beta_B = fb$B[, "Age"], p_B = pb, fdr_B = fdr_b,
                     R2_age = fa$R2, R2_comp = fc$R2, R2_full = fb$R2, sig_A = sig_a, sig_B = sig_b),
          gzfile(file.path(OUT, "results", sprintf("组成校正_%s_逐peak.csv.gz", TAG))), row.names = FALSE)
write.csv(spdf, file.path(OUT, "results", sprintf("组成校正_%s_组成vs年龄.csv", TAG)), row.names = FALSE)
write.csv(tab,  file.path(OUT, "results", sprintf("组成校正_%s_分层.csv", TAG)), row.names = FALSE)
write.csv(data.frame(
  指标 = c("n_peak", "n_individual", "唯一Age份额_pct", "唯一组成份额_pct", "共享份额_pct",
           "A显著数", "B显著数", "存留率_pct", "方向翻转率_pct", "收缩比"),
  值   = c(nrow(Y), ncol(Y), round(100 * uniq_age / (uniq_age + uniq_comp + shared), 2),
           round(100 * uniq_comp / (uniq_age + uniq_comp + shared), 2),
           round(100 * shared   / (uniq_age + uniq_comp + shared), 2),
           sum(sig_a), sum(sig_b), round(100 * retention, 2), round(100 * flip, 2), round(shrink, 4))),
  file.path(OUT, "results", sprintf("组成校正_%s_摘要.csv", TAG)), row.names = FALSE)

## ---------- 6. 四面板图（中文用 ASCII + mathtext，避免豆腐块） ----------
suppressMessages({library(ggplot2); library(patchwork)})
theme_set(theme_bw(base_size = 11) + theme(panel.grid.minor = element_blank(),
                                           plot.title = element_text(face = "bold", size = 11)))
top <- spdf$celltype[which.max(abs(spdf$rho))]
p1 <- ggplot(data.frame(Age = Age, v = P[, top])) +
  geom_point(aes(Age, v * 100), color = "#E8613C", size = 2.4, alpha = .85) +
  geom_smooth(aes(Age, v * 100), method = "lm", se = TRUE, color = "#E8613C", fill = "#E8613C", alpha = .15) +
  labs(x = "年龄 (岁)", y = sprintf("%s 占该个体细胞比例 (%%)", top),
       title = "A｜组成随年龄偏移",
       subtitle = sprintf("%s: rho=%.3f, p=%.2g", top, spdf$rho[spdf$celltype == top], spdf$p[spdf$celltype == top]))
vd <- data.frame(part = factor(c("唯一 Age", "共享", "唯一 组成"), levels = c("唯一 组成", "共享", "唯一 Age")),
                 share = c(uniq_age, shared, uniq_comp) * 100)
p2 <- ggplot(vd, aes(part, share, fill = part)) + geom_col(width = .62, color = "grey25") +
  geom_text(aes(label = sprintf("%.1f%%", share)), vjust = -0.35, size = 3.4) +
  scale_fill_manual(values = c("#E8613C", "#B9A44C", "#4C9AF5"), guide = "none") +
  labs(x = NULL, y = "解释份额 (%)", title = "B｜方差分解",
       subtitle = sprintf("$R^2$(Age)=%.4f  $R^2$(组成)=%.4f", r2_age, r2_comp)) +
  expand_limits(y = max(vd$share) * 1.18)
cmp <- data.frame(m = factor(c("A: Age only", "B: Age + 组成"), levels = c("A: Age only", "B: Age + 组成")),
                  n = c(sum(sig_a), sum(sig_b)))
p3 <- ggplot(cmp, aes(m, n, fill = m)) + geom_col(width = .55, color = "grey25") +
  geom_text(aes(label = format(n, big.mark = ",")), vjust = -0.4, size = 3.4) +
  scale_fill_manual(values = c("#4C9AF5", "#E8613C"), guide = "none") +
  labs(x = NULL, y = "FDR<0.05 的 peak 数", title = "C｜校正后的显著数",
       subtitle = sprintf("存留率 %.1f%% | 翻转 %.1f%% | 收缩比 %.2f", 100 * retention, 100 * flip, shrink)) +
  expand_limits(y = max(cmp$n) * 1.2)
p4 <- ggplot(data.frame(Q = factor(tab$Q), ret = tab$retention_pct, r2 = tab$R2_comp_median), aes(Q, ret, group = 1)) +
  geom_line(color = "#7A7A7A") + geom_point(aes(size = r2), color = "#E8613C") +
  geom_text(aes(label = sprintf("%.0f%%", ret)), vjust = -1.1, size = 3.2) +
  labs(x = "组成载荷四分位", y = "A 显著 peak 在 B 中的存留率 (%)", title = "D｜组成敏感度分层", size = "$R^2$comp") +
  expand_limits(y = c(0, 105))
fig <- (p1 | p2) / (p3 | p4) +
  plot_annotation(title = sprintf("%s组成校正的决定性检验（%d peak × %d 个体，同一批数据仅改模型）", TAG, nrow(Y), ncol(Y)),
                  subtitle = "模型 A: log2CPM ~ Age ｜ 模型 B: log2CPM ~ Age + CLR(细胞类型组成)")
ggsave(file.path(OUT, "figures", sprintf("%s组成校正决定性检验.png", TAG)), fig,
       width = 13.6, height = 10.2, dpi = 200, bg = "white")
cat("\n[完成]\n")
