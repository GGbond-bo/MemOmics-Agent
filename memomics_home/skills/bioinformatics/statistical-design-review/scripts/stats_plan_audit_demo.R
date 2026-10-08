# stats_plan_audit_demo.R — 统计方案审查探针（2026-09-25 实测通过）
#
# 用途：审查"多层测量 + 多组比较"的统计方案时，用同一份模拟数据把
#       ① 伪重复（子样本当 n）+ 未校正多重比较的后果
#       ② 个体均值 + ANOVA + Tukey
#       ③ LMM（个体随机截距）+ ICC
#       ④ 各效应量下的功效
#       并排跑出来，同时出四联诊断图。改下方 PARAMS 即可套用到其它设计。
#
# 跑法（execute_r 持久内核，推荐）：source('<abs path>', encoding='utf-8')
# 跑法（terminal）：Rscript stats_plan_audit_demo.R
# 依赖：base R + lme4/lmerTest（仅 ICC 一节需要；未装会自动跳过并提示）

## ---- PARAMS ------------------------------------------------------------
OUT_DIR   <- "E:/MemOmics-Agent/results"      # 图输出目录（自动拼 /stats_plan_audit/）
N_GROUP   <- 3                                # 组数
N_IND     <- 6                                # 每组个体数（= 统计 n）
N_SUB     <- 16                               # 每个体子样本数（纤维/细胞/视野…）
EFFECT    <- 0.5                              # 相邻组真实效应（以 SD 为单位）
SD_IND    <- 0.6                              # 个体间 SD
SD_SUB    <- 1.0                              # 个体内 SD
SEED      <- 42

set.seed(SEED)
dir.create(file.path(OUT_DIR, "stats_plan_audit"), showWarnings = FALSE, recursive = TRUE)

## ---- 0. 模拟数据 -------------------------------------------------------
gname <- LETTERS[seq_len(N_GROUP)]
mk <- function() {
  out <- list()
  for (g in seq_len(N_GROUP)) {
    for (m in seq_len(N_IND)) {
      mu <- EFFECT * (g - 1) + rnorm(1, 0, SD_IND)
      out[[length(out) + 1]] <- data.frame(
        Group = gname[g],
        Ind   = sprintf("%s%02d", gname[g], m),
        Y     = rnorm(N_SUB, mu, SD_SUB))
    }
  }
  do.call(rbind, out)
}
d <- mk()
d$Group <- factor(d$Group, levels = gname)
cat(sprintf("[数据] 个体 %d 个，子样本 %d 条（每个体 %d 条）\n",
            length(unique(d$Ind)), nrow(d), N_SUB))

## ---- 1. 错误口径：子样本当 n 的两两 t 检验（未校正） -------------------
prs <- combn(gname, 2, simplify = FALSE)
p_bad <- sapply(prs, function(pr)
  t.test(Y ~ Group, data = subset(d, Group %in% pr))$p.value)
names(p_bad) <- sapply(prs, paste, collapse = "-")
k <- length(prs)
cat(sprintf("\n[错误口径] 子样本当 n（n=%d）两两 t 检验，未校正：\n", nrow(d)))
print(round(p_bad, 5))
cat(sprintf("  FWER = 1-(1-0.05)^%d = %.3f（名义 5%%）\n", k, 1 - 0.95^k))

## ---- 2. 正确口径 A：个体均值 + ANOVA + Tukey ---------------------------
mu  <- tapply(d$Y, d$Ind, mean)
grp <- tapply(as.character(d$Group), d$Ind, function(x) x[1])
dm  <- data.frame(Ind = names(mu), Group = factor(grp, levels = gname), Y = as.numeric(mu))
fit <- aov(Y ~ Group, data = dm)
cat(sprintf("\n[正确 A] 个体均值（n=%d/组）ANOVA + Tukey HSD：\n", N_IND))
print(round(TukeyHSD(fit)$Group[, c("diff", "lwr", "upr", "p adj")], 4))
cat(sprintf("  前提：残差 Shapiro p=%.3f | Levene p=%.3f\n",
            shapiro.test(resid(fit))$p.value,
            tryCatch(car::leveneTest(Y ~ Group, dm)[1, 3], error = function(e) NA)))

## ---- 3. 正确口径 B：LMM（子样本嵌套于个体）+ ICC -----------------------
icc <- NA
cat("\n[正确 B] LMM: Y ~ Group + (1|Ind)\n")
if (requireNamespace("lme4", quietly = TRUE) &&
    requireNamespace("lmerTest", quietly = TRUE)) {
  suppressMessages({library(lme4); library(lmerTest)})
  m <- lmer(Y ~ Group + (1 | Ind), data = d)
  print(round(summary(m)$coefficients, 4))
  vc  <- as.data.frame(VarCorr(m))
  icc <- vc$vcov[1] / sum(vc$vcov)
  cat(sprintf("  方差分量：个体=%.3f 残差=%.3f → ICC=%.3f（子样本远非独立）\n",
              vc$vcov[1], vc$vcov[2], icc))
} else {
  cat("  (lme4/lmerTest 未装，跳过；可先征得用户同意再装)\n")
}

## ---- 4. 功效：这个 n 到底能检出多大效应 --------------------------------
cat(sprintf("\n[功效] n=%d/组、α=0.05：\n", N_IND))
pw_tab <- sapply(c(0.5, 0.8, 1.2, 1.5), function(dd)
  power.t.test(n = N_IND, delta = dd, sd = 1, sig.level = 0.05)$power)
print(data.frame(d = c(0.5, 0.8, 1.2, 1.5), power = round(pw_tab, 2)), row.names = FALSE)
cat(sprintf("  %d 组 ANOVA（between.var=%.2f, within.var=1）→ power=%.2f\n",
            N_GROUP, (EFFECT / 2)^2,
            power.anova.test(groups = N_GROUP, n = N_IND,
                             between.var = (EFFECT / 2)^2, within.var = 1,
                             sig.level = 0.05)$power))

## ---- 5. 四联诊断图（base graphics，零依赖；中文用 cairo + YaHei） ------
FIG <- file.path(OUT_DIR, "stats_plan_audit", "stats_plan_audit_diagnostics.png")
COL <- c(bad = "#D9534F", ok = "#4C72B0", g3 = "#55A868")
png(FIG, width = 2600, height = 2100, res = 200, type = "cairo")
par(mfrow = c(2, 2), mar = c(4.6, 4.8, 3.2, 1.2), family = "Microsoft YaHei",
    cex.main = 1.12, cex.lab = 1.0, cex.axis = 0.92)

# A 伪重复的代价
mA <- rbind(-log10(p_bad), -log10(TukeyHSD(fit)$Group[, "p adj"]))
barplot(mA, beside = TRUE, names.arg = names(p_bad), ylim = c(0, max(mA) * 1.5),
        col = c(COL["bad"], COL["ok"]), ylab = expression(-log[10](P)),
        xlab = "组间比较", main = "A  伪重复的代价（同一份数据）")
abline(h = -log10(0.05), lty = 2, lwd = 1.4, col = "grey30")
legend("topright", bty = "n", cex = 0.78, fill = c(COL["bad"], COL["ok"]),
       border = NA, legend = c(sprintf("错误：子样本当 n=%d，两两 t 检验", nrow(d)),
                               sprintf("正确：个体均值 n=%d/组，Tukey", N_IND)))

# B 嵌套结构
boxplot(Y ~ Ind, data = d, las = 2, cex.axis = 0.58,
        col = rep(rep(c("#A8C6E8", "#F3CBA6", "#B9DDB4"), each = N_IND)[seq_len(N_GROUP)],
                  each = N_IND),
        ylab = "测量值（任意单位）", xlab = sprintf("个体（每个体 %d 个子样本）", N_SUB),
        main = "B  嵌套结构：个体内散布 >> 个体间差异")
points(seq_along(mu), as.numeric(mu), pch = 18, col = COL["bad"], cex = 1.15)
legend("topleft", bty = "n", cex = 0.78, pch = c(1, 18),
       col = c("grey25", COL["bad"]), legend = c("单个子样本", "个体均值"))

# C 功效缺口
ns <- 2:20
pw <- sapply(c(0.5, 0.8, 1.2), function(dd)
  sapply(ns, function(nn) power.t.test(n = nn, delta = dd, sd = 1, sig.level = 0.05)$power))
matplot(ns, pw, type = "l", lty = 1, lwd = 2.2, ylim = c(0, 1),
        col = c(COL["bad"], COL["ok"], COL["g3"]),
        xlab = "每组个体数 n", ylab = "功效（power）", main = "C  n 的功效缺口")
abline(h = 0.8, lty = 2, col = "grey30")
abline(v = N_IND, lty = 3, col = "grey40")
text(N_IND + 0.4, 0.06, sprintf("n = %d", N_IND), cex = 0.8)
legend("bottomright", bty = "n", cex = 0.82, lty = 1, lwd = 2.2,
       col = c(COL["bad"], COL["ok"], COL["g3"]), legend = c("d = 0.5", "d = 0.8", "d = 1.2"))

# D 比例-表型（演示口径差异：原始 Pearson / logit Spearman / 控制组别偏相关）
set.seed(SEED + 1)
n  <- N_GROUP * N_IND
gp <- factor(rep(gname, each = N_IND))
prop <- plogis(rnorm(n, -1.2, 0.6) + 0.3 * as.numeric(gp))
pheno <- 1.5 * qlogis(prop) + rnorm(n, 0, 0.7) + 0.8 * as.numeric(gp)
d2 <- data.frame(Group = gp, prop = prop, lg = qlogis(prop), pheno = pheno)
r_raw <- cor(d2$prop, d2$pheno)
rho   <- cor(d2$lg, d2$pheno, method = "spearman")
rx <- resid(lm(prop ~ Group, d2)); ry <- resid(lm(pheno ~ Group, d2))
r_par <- cor(rx, ry)
cg <- c("#4C72B0", "#DD8452", "#55A868")[as.numeric(d2$Group)]
plot(d2$prop, d2$pheno, pch = 19, col = cg, cex = 1.5,
     xlab = "比例（每个体一个值）", ylab = "表型（每个体一个值）",
     main = sprintf("D  比例-表型：分析单位是个体（n = %d）", n))
abline(lm(pheno ~ prop, data = d2), lwd = 2.2, col = "grey20")
legend("topleft", bty = "n", cex = 0.8, pch = 19, col = cg[seq_len(N_GROUP)],
       legend = paste("组", levels(d2$Group)))
mtext(sprintf("Pearson r = %.2f（原始比例） | Spearman rho = %.2f（logit） | 偏相关 r = %.2f（控制组别）",
              r_raw, rho, r_par), side = 1, line = 3.1, cex = 0.74)
dev.off()

cat(sprintf("\n[图] %s\n", FIG))
cat(sprintf("[比例-表型] r=%.2f (raw) | rho=%.2f (logit) | r=%.2f (partial)\n", r_raw, rho, r_par))
cat(sprintf("[ICC] %s\n", ifelse(is.na(icc), "NA（lme4 未装）", sprintf("%.3f", icc))))
cat("== 提醒：本脚本用模拟数据演示统计口径差异，不是用户真实数据的分析结果 ==\n")