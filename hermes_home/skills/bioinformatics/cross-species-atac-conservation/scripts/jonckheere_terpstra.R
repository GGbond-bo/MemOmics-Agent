# =============================================================================
# jonckheere_terpstra.R — 有序阶段趋势检验的可运行实现（base R，无包依赖）
# -----------------------------------------------------------------------------
# 配套文档：references/staged-design-vs-continuous-age.md
#   · §五之一 —— mid-rank ties 修正的必要性与自检三条
#   · §六     —— JT 的「最小可能 p」小 n 天花板（先算再许诺）
#   · §十四   —— 猴侧实测判决结果（连续 vs 阶段）
#   · §十五   —— 显著数 << 5% = 检验保守 的诊断模式
#
# 用途：有序分组设计（Young/Middle/Old/Exceptionally old 等）的单调趋势检验，
#       替代「把 K 个离散平台当连续轴」的 cor(x, age) 回归。
#
# 约定：Z   = 矩阵 [单元 × 个体]（行 = tile/peak/gene，列 = 个体）
#       grp = 整数有序编码向量（★ 必须显式映射，见文件末尾 NOTE）
# 运行：source() 后用；或 `Rscript jonckheere_terpstra.R` 跑自检（约 10 秒）
#
# ★ 与文档 §五之一 的 jt_mid() 数学等价：本实现按【组对】循环（6 组对），
#   文档版按【个体对】循环（190 对）。538k 单元 × 20 个体实测 1–3 秒，二者可互校验。
# =============================================================================

## ---------------------------------------------------------------------------
## 1. 核心：JT 统计量（★ mid-rank ties 修正）
## ---------------------------------------------------------------------------
jt_mid <- function(Z, grp) {
  grp <- as.integer(grp); ni <- table(grp); N <- length(grp); J <- 0
  for (pr in combn(length(ni), 2, simplify = FALSE)) {
    A <- Z[, grp == pr[1], drop = FALSE]
    B <- Z[, grp == pr[2], drop = FALSE]
    J <- J + rowSums(sapply(seq_len(ncol(B)), function(q)
      rowSums((B[, q] > A) + 0.5 * (B[, q] == A))))   # ★ 0.5 项 = mid-rank，不可省
  }                                                   #   省掉 → 全等单元得 z=-5 假显著
  list(J = J, EJ = (N^2 - sum(ni^2)) / 4,
       sd = sqrt((N^2 * (2*N + 3) - sum(ni^2 * (2*ni + 3))) / 72))
}

jt_z <- function(Z, grp) { r <- jt_mid(Z, grp); (r$J - r$EJ) / r$sd }

## 双侧 p 值（JT 渐近正态；渐近性由总对数驱动，n≈20 / 4 组已够好）
jt_p <- function(Z, grp) 2 * pnorm(-abs(jt_z(Z, grp)))

## 小 n 天花板：单单元理论上能达到的最小 p（组大小一确定就固定，与数据无关）
jt_p_floor <- function(ni) {
  N <- sum(ni)
  Umax <- sum(combn(rev(ni), 2, prod))                 # = (N² − Σnᵢ²)/2
  Ez <- (N^2 - sum(ni^2)) / 4
  sdv <- sqrt((N^2 * (2*N + 3) - sum(ni^2 * (2*ni + 3))) / 72)
  2 * pnorm(-abs((Umax - Ez) / sdv))
}
## 猴 n=(4,4,6,6) → 5.7e-7（比 T≈3e5 时的 BH 门槛 3.3e-7 还大 → 猴侧 0 显著是可预期的）
## 人 n=(10,10,10,10) → 4.4e-13

## ---------------------------------------------------------------------------
## 2. 连续对照口径：向量化逐行 Pearson（比 apply + cor 快 100×+）
## ---------------------------------------------------------------------------
row_pearson <- function(Z, v) {
  Zc <- Z - rowMeans(Z); vc <- v - mean(v)
  as.vector((Zc %*% vc) / (sqrt(rowSums(Zc^2)) * sqrt(sum(vc^2))))
}

## ---------------------------------------------------------------------------
## 3. ★ 必跑自检（四条全 ✔ 才可信；③ 专抓 ties bug）
## ---------------------------------------------------------------------------
jt_selftest <- function(verbose = TRUE) {
  grp <- rep(1:4, c(4, 4, 6, 6)); ni <- table(grp); N <- length(grp)
  Jmax <- sum(combn(rev(ni), 2, prod))                # 完全单调 = 148
  EJ   <- (N^2 - sum(ni^2)) / 4                       # = 74
  # 构造：每行都等于 vals
  # ★ 勿用 matrix(rep(1:20, 5), nrow = 5, byrow = FALSE) —— 那些行并不单调（会得到假失败 J=62）
  mk <- function(vals, nrow = 2000) matrix(rep(vals, each = nrow), nrow = nrow)

  z1 <- jt_z(mk(1:20), grp)                           # ① 完美单调递增
  z2 <- jt_z(mk(20:1), grp)                           # ② 完美单调递减
  r3 <- jt_mid(mk(rep(1, 20)), grp)                   # ③ 全等（无信息）
  z3 <- (r3$J - r3$EJ) / r3$sd
  r4 <- jt_mid(matrix(rnorm(2000 * 20), 2000, 20), grp)  # ④ 随机

  chk <- c(
    mono_up   = abs(z1[1] - 5) < 1e-6,
    mono_down = abs(z2[1] + 5) < 1e-6,
    all_equal = abs(r3$J[1] - EJ) < 1e-6 && abs(z3[1]) < 1e-6,   # ★ 必须 z=0
    random_EJ = abs(mean(r4$J) - r4$EJ) < 1
  )
  if (verbose) {
    cat(sprintf("① 完美单调递增  J=%7.1f  z=%7.3f   (期望 J=%g, z=+5)\n", r3$EJ * 0 + jt_mid(mk(1:20), grp)$J[1], z1[1], Jmax))
    cat(sprintf("② 完美单调递减  z=%7.3f               (期望 z=-5)\n", z2[1]))
    cat(sprintf("③ 全等(无信息)  J=%7.1f  z=%7.3f   (期望 J=%g, z=0 ★必须为0)\n", r3$J[1], z3[1], EJ))
    cat(sprintf("④ 随机          mean(J)=%7.2f          (期望 EJ=%g)\n", mean(r4$J), r4$EJ))
    cat(if (all(chk)) "✅ 自检通过（mid-rank 修正已生效）\n"
        else paste0("❌ 自检失败: ", paste(names(chk)[!chk], collapse = ", "), "\n"))
  }
  invisible(all(chk))
}

## ---------------------------------------------------------------------------
## 4. 端到端用法
## ---------------------------------------------------------------------------
## ORD <- c(Young = 1, Middle = 2, Old = 3, "Exceptionally old" = 4)   # ★ 显式有序
## grp <- ORD[as.character(map$Age_group)]
## stopifnot(!anyNA(grp))                 # 标签不符立刻停，不静默丢样本
## z   <- jt_z(lcpm, grp)                 # lcpm = log2(CPM+1)，行 = tile，列 = 个体
## p   <- 2 * pnorm(-abs(z)); q <- p.adjust(p, "fdr")
## rc  <- row_pearson(lcpm, age_num)      # 连续对照口径
## jt_p_floor(table(grp))                 # ★ 先算 p 下限，再许诺显著性
##
## ★ 交付契约：chr, start, end, r, p, q —— 前 6 列位置与名字不能动，新增列追加在后
##   分阶段下 r = 与阶段序号 1..4 的相关 = 有序趋势强度，不再是连续年龄回归
##   → 交付说明必须显式声明口径已变，否则会被当成同口径跨代次比较

if (sys.nframe() == 0) jt_selftest()

## ---------------------------------------------------------------------------
## NOTE · 有序编码（唯一正确写法）
## ---------------------------------------------------------------------------
## 猴: Age_group (大写A)   人: age_group (小写) + Age_label ('20-40'…)
## ✗ cor(x, Age_group)                → Error: 'y'必需是数值
## ✗ as.numeric(factor(Age_group))    → 字母序 E<M<O<Y → 方向 100% 反转且不报错
## ✓ ORD <- c(Young=1, Middle=2, Old=3, "Exceptionally old"=4); grp <- ORD[as.character(x)]
## ✓ stopifnot(!anyNA(grp))
