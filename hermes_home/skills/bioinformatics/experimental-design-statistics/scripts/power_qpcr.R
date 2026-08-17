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
#   2. 如果通过 → skill_evolution(action="record_run",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", params_used="参数JSON", result_summary="结果",
#      quality_score=8, notes="经验总结")
#      → 记录成功运行日志，供后续同类型分析参考
#   3. 如果失败 → skill_evolution(action="record_error",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", error_message="报错", root_cause="根因",
#      fix_applied="修复方案")
#      → 记录错误日志，修正后重跑
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================
# qPCR / Continuous-Readout Power Analysis (ΔCt / ΔΔCt)
# Power and sample size for qPCR experiments analysed on the ΔCt (delta-Ct) scale,
# where the effect is a difference in cycle threshold between groups and the test
# is a t-test (2 groups) or one-way ANOVA (3+ groups).
#
# UNIT OF REPLICATION: BIOLOGICAL replicates (independent samples/animals/donors).
# The SD supplied MUST be the BIOLOGICAL ΔCt standard deviation, NOT the technical
# (well-to-well / replicate-pipetting) SD. Technical SD is typically ~0.1-0.3 Ct and
# powering off it dramatically overstates power (a known failure mode that yields
# badly underpowered qPCR designs). Use assert_biological_replication() to guard this.
#
# Based on: Cohen J (1988) Statistical Power Analysis for the Behavioral Sciences;
#           pwr package (Champely 2020), pwr.t.test / pwr.anova.test.

#' Assert that the analysis unit and SD are biological, not technical
#'
#' Replication guard for power analysis. qPCR / ΔCt power MUST be computed on
#' BIOLOGICAL replicates using the BIOLOGICAL ΔCt SD. Technical replicates
#' (repeated wells of the same sample) measure pipetting/instrument noise, not
#' biological variability, and powering off them is pseudoreplication that
#' produces a badly underpowered design.
#'
#' @param n_unit The unit of replication: "biological" (required) or "technical".
#' @param sd_type The kind of SD supplied: "biological" (required) or "technical".
#' @param context Optional string naming the assay/context, used in messages.
#' @param strict If TRUE (default), stop() on a technical violation; if FALSE, warning() only.
#' @return Invisibly TRUE if the check passes (i.e. both are biological).
#' @export
#' @examples
#' # Passes silently
#' assert_biological_replication("biological", "biological", context = "qPCR ZBTB16")
#' # Errors: technical SD where biological is required
#' # assert_biological_replication("biological", "technical", context = "qPCR")
assert_biological_replication <- function(n_unit = c("biological", "technical"),
                                          sd_type = c("biological", "technical"),
                                          context = "",
                                          strict = TRUE) {

  n_unit <- match.arg(n_unit)
  sd_type <- match.arg(sd_type)
  ctx <- if (nzchar(context)) sprintf(" [%s]", context) else ""

  problems <- character()
  if (n_unit == "technical") {
    problems <- c(problems, sprintf(
      "Unit of replication is TECHNICAL%s. Power must be computed over BIOLOGICAL replicates (independent samples/donors/animals); technical replicates are pseudoreplication and do not generalise.",
      ctx))
  }
  if (sd_type == "technical") {
    problems <- c(problems, sprintf(
      "SD supplied is TECHNICAL%s (well-to-well / pipetting noise, typically ~0.1-0.3 Ct). qPCR/ΔCt power requires the BIOLOGICAL ΔCt SD (typically ~0.5-1.0 Ct). Powering off a technical SD overstates power and yields an underpowered design.",
      ctx))
  }

  if (length(problems) > 0) {
    msg <- paste0(
      "Biological-replication guard tripped:\n  - ",
      paste(problems, collapse = "\n  - "),
      "\n  Fix: supply the biological ΔCt SD (e.g. SD of per-sample ΔCt across donors) and count biological replicates as n."
    )
    if (strict) stop(msg, call. = FALSE) else warning(msg, call. = FALSE)
    return(invisible(FALSE))
  }

  invisible(TRUE)
}


#' Effective per-contrast alpha after a multiple-testing correction
#'
#' Returns the alpha to use for a SINGLE planned contrast's power calculation
#' given n_contrasts planned comparisons. Bonferroni divides alpha by the number
#' of contrasts. Holm is step-down and uniformly at least as powerful as
#' Bonferroni; its smallest (most stringent) per-step threshold equals alpha/m,
#' so for a single contrast's power we use that conservative bound (alpha/m) and
#' label it accordingly. "none" returns alpha unchanged.
#'
#' @param alpha Family-wise / nominal per-test alpha (default: 0.05)
#' @param n_contrasts Number of planned contrasts (default: 1)
#' @param correction One of "holm", "bonferroni", "none"
#' @return Numeric effective per-contrast alpha
#' @keywords internal
effective_alpha_qpcr <- function(alpha = 0.05, n_contrasts = 1,
                                 correction = c("holm", "bonferroni", "none")) {
  correction <- match.arg(correction)
  if (n_contrasts < 1) stop("n_contrasts must be >= 1")
  if (alpha <= 0 || alpha >= 1) stop("alpha must be between 0 and 1")

  switch(correction,
    none = alpha,
    bonferroni = alpha / n_contrasts,
    # Holm's first-step threshold is alpha/m; this is the conservative bound for a
    # single contrast (Holm is >= Bonferroni in power, equal at the most stringent step).
    holm = alpha / n_contrasts
  )
}


#' Calculate power for a qPCR / ΔCt experiment
#'
#' Computes statistical power to detect a ΔΔCt effect (a difference in ΔCt between
#' groups) using Cohen's d for a two-group t-test or Cohen's f for a one-way ANOVA.
#' The effect size is derived from the expected ΔCt difference and the BIOLOGICAL
#' ΔCt SD. A multiple-testing correction is applied to the per-contrast alpha.
#'
#' UNIT: n_biological is the number of BIOLOGICAL replicates per group. sd_biological
#' is the BIOLOGICAL ΔCt SD (NOT technical well-to-well SD). The function calls
#' assert_biological_replication() to enforce this.
#'
#' @param delta_ct Expected effect on the ΔCt scale (ΔΔCt): the difference in mean
#'   ΔCt between the two conditions (Ct units). One Ct ~ 2-fold expression change.
#' @param sd_biological BIOLOGICAL ΔCt standard deviation (Ct units). Prior: ~0.5-1.0 Ct
#'   for well-controlled qPCR on biological replicates. NOT the technical SD (~0.1-0.3 Ct).
#' @param n_biological Number of BIOLOGICAL replicates per group.
#' @param alpha Nominal significance threshold per contrast before correction (default: 0.05)
#' @param test "t" for a two-group t-test (default) or "anova" for one-way ANOVA.
#' @param n_groups Number of groups for the ANOVA case (default: 2; used only when test="anova").
#' @param n_contrasts Number of planned contrasts / comparisons for multiple-testing
#'   correction of alpha (default: 1).
#' @param correction Multiple-testing correction applied to per-contrast alpha:
#'   "holm" (default), "bonferroni", or "none".
#' @param sd_type Declared kind of SD: "biological" (default, required) or "technical".
#'   Supplying "technical" trips the replication guard.
#' @param n_unit Declared unit of replication: "biological" (default) or "technical".
#' @return List with power, effective_alpha, cohens_d (or cohens_f), n_biological,
#'   parameters, assumptions, and an interpretation string.
#' @export
#' @examples
#' # ZBTB16-style: ΔΔCt = 1.0 Ct, biological SD = 0.8 Ct, n = 5/group,
#' # 4 planned contrasts, Holm correction
#' calc_power_qpcr_ddct(delta_ct = 1.0, sd_biological = 0.8, n_biological = 5,
#'                      test = "t", n_contrasts = 4, correction = "holm")
calc_power_qpcr_ddct <- function(delta_ct,
                                 sd_biological,
                                 n_biological,
                                 alpha = 0.05,
                                 test = c("t", "anova"),
                                 n_groups = 2,
                                 n_contrasts = 1,
                                 correction = c("holm", "bonferroni", "none"),
                                 sd_type = c("biological", "technical"),
                                 n_unit = c("biological", "technical")) {

  if (!requireNamespace("pwr", quietly = TRUE)) {
    stop("Package 'pwr' is required. Install with install.packages('pwr')")
  }

  test <- match.arg(test)
  correction <- match.arg(correction)
  sd_type <- match.arg(sd_type)
  n_unit <- match.arg(n_unit)

  # --- Replication guard: qPCR/ΔCt power MUST use biological replicates + biological SD ---
  assert_biological_replication(n_unit = n_unit, sd_type = sd_type,
                                context = "qPCR ΔCt power")

  # Validate inputs
  if (delta_ct <= 0) stop("delta_ct (ΔΔCt effect) must be positive (Ct units)")
  if (sd_biological <= 0) stop("sd_biological must be positive (Ct units)")
  if (n_biological < 2) stop("n_biological must be >= 2 per group")
  if (test == "anova" && n_groups < 2) stop("n_groups must be >= 2 for ANOVA")

  # Effective per-contrast alpha after multiple-testing correction
  eff_alpha <- effective_alpha_qpcr(alpha = alpha, n_contrasts = n_contrasts,
                                    correction = correction)

  if (test == "t") {
    # Cohen's d = mean difference / SD (pooled). On the ΔCt scale this is ΔΔCt / SD_biological.
    cohens_d <- delta_ct / sd_biological
    res <- pwr::pwr.t.test(n = n_biological, d = cohens_d, sig.level = eff_alpha,
                           type = "two.sample", alternative = "two.sided")
    power_value <- res$power
    effect_label <- "cohens_d"
    effect_value <- cohens_d
  } else {
    # One-way ANOVA: Cohen's f. For a balanced design with the full ΔCt spread
    # across n_groups equal to delta_ct (max - min), a conservative f is derived
    # assuming two extreme groups separated by delta_ct and the rest at the midpoint.
    # f = sqrt( sum(p_i * (mu_i - grand_mean)^2) / k ) / sigma.
    # With two extremes at +/- delta_ct/2 and (k-2) groups at the mean, balanced:
    #   variance of means = (2 * (delta_ct/2)^2) / k = delta_ct^2 / (2k)
    #   f = sqrt(variance_of_means) / sigma = delta_ct / (sigma * sqrt(2k))
    cohens_f <- delta_ct / (sd_biological * sqrt(2 * n_groups))
    res <- pwr::pwr.anova.test(k = n_groups, n = n_biological, f = cohens_f,
                               sig.level = eff_alpha)
    power_value <- res$power
    effect_label <- "cohens_f"
    effect_value <- cohens_f
  }

  output <- list(
    power = power_value,
    effective_alpha = eff_alpha,
    n_biological = n_biological,
    parameters = list(
      delta_ct = delta_ct,
      sd_biological = sd_biological,
      n_biological = n_biological,
      test = test,
      n_groups = if (test == "anova") n_groups else 2,
      n_contrasts = n_contrasts,
      correction = correction,
      alpha_nominal = alpha
    ),
    assumptions = list(
      unit_of_replication = "BIOLOGICAL replicates (independent samples/donors/animals)",
      sd_interpretation = "BIOLOGICAL ΔCt SD (NOT technical well-to-well SD; technical ~0.1-0.3 Ct, biological ~0.5-1.0 Ct)",
      effect_scale = "ΔCt (Ct units); 1 Ct ≈ 2-fold expression change",
      test = if (test == "t") "Two-sample t-test (Cohen's d)" else sprintf("One-way ANOVA, k=%d groups (Cohen's f)", n_groups)
    ),
    method = if (test == "t") "pwr::pwr.t.test (two-sample, two-sided)" else "pwr::pwr.anova.test (one-way)",
    interpretation = interpret_power_qpcr(power_value, n_biological, correction, n_contrasts)
  )
  output[[effect_label]] <- effect_value

  cat("✓ qPCR ΔCt power analysis completed successfully!\n")
  if (test == "t") {
    cat(sprintf("  Power = %.3f | Cohen's d = %.3f (ΔΔCt=%.2f / SD_bio=%.2f)\n",
                power_value, effect_value, delta_ct, sd_biological))
  } else {
    cat(sprintf("  Power = %.3f | Cohen's f = %.3f (ΔΔCt=%.2f, k=%d, SD_bio=%.2f)\n",
                power_value, effect_value, delta_ct, n_groups, sd_biological))
  }
  cat(sprintf("  n = %d BIOLOGICAL replicates/group | effective alpha = %.4f (%s, %d contrasts)\n",
              n_biological, eff_alpha, correction, n_contrasts))
  cat("  UNIT = biological replicates; SD = biological ΔCt SD (NOT technical).\n")

  return(output)
}


#' Smallest number of biological replicates hitting a target power (qPCR / ΔCt)
#'
#' Searches for the smallest n_biological per group that achieves the target power
#' for a ΔΔCt effect, given the BIOLOGICAL ΔCt SD and the multiple-testing-corrected
#' per-contrast alpha.
#'
#' @param delta_ct Expected ΔΔCt effect (Ct units)
#' @param sd_biological BIOLOGICAL ΔCt SD (Ct units; ~0.5-1.0 prior). NOT technical.
#' @param power Target power (default: 0.9)
#' @param alpha Nominal per-contrast alpha before correction (default: 0.05)
#' @param test "t" (default) or "anova"
#' @param n_groups Number of groups for ANOVA (default: 2)
#' @param n_contrasts Number of planned contrasts (default: 1)
#' @param correction "holm" (default), "bonferroni", or "none"
#' @param max_n Maximum n to search (default: 1000)
#' @param sd_type "biological" (default, required) or "technical" (trips guard)
#' @param n_unit "biological" (default) or "technical"
#' @return List with required_n_biological, achieved_power, effective_alpha, effect size, parameters
#' @export
#' @examples
#' samplesize_qpcr_ddct(delta_ct = 1.0, sd_biological = 0.8, power = 0.9,
#'                      test = "t", n_contrasts = 4, correction = "holm")
samplesize_qpcr_ddct <- function(delta_ct,
                                 sd_biological,
                                 power = 0.9,
                                 alpha = 0.05,
                                 test = c("t", "anova"),
                                 n_groups = 2,
                                 n_contrasts = 1,
                                 correction = c("holm", "bonferroni", "none"),
                                 max_n = 1000,
                                 sd_type = c("biological", "technical"),
                                 n_unit = c("biological", "technical")) {

  if (!requireNamespace("pwr", quietly = TRUE)) {
    stop("Package 'pwr' is required. Install with install.packages('pwr')")
  }

  test <- match.arg(test)
  correction <- match.arg(correction)
  sd_type <- match.arg(sd_type)
  n_unit <- match.arg(n_unit)

  # Replication guard
  assert_biological_replication(n_unit = n_unit, sd_type = sd_type,
                                context = "qPCR ΔCt sample size")

  if (delta_ct <= 0) stop("delta_ct (ΔΔCt effect) must be positive (Ct units)")
  if (sd_biological <= 0) stop("sd_biological must be positive (Ct units)")
  if (power <= 0 || power >= 1) stop("power must be between 0 and 1")

  eff_alpha <- effective_alpha_qpcr(alpha = alpha, n_contrasts = n_contrasts,
                                    correction = correction)

  if (test == "t") {
    cohens_d <- delta_ct / sd_biological
    effect_label <- "cohens_d"
    effect_value <- cohens_d
    # pwr.t.test can solve for n directly
    res <- tryCatch(
      pwr::pwr.t.test(d = cohens_d, sig.level = eff_alpha, power = power,
                      type = "two.sample", alternative = "two.sided"),
      error = function(e) NULL)
    required_n <- if (!is.null(res)) ceiling(res$n) else NA_integer_
  } else {
    cohens_f <- delta_ct / (sd_biological * sqrt(2 * n_groups))
    effect_label <- "cohens_f"
    effect_value <- cohens_f
    res <- tryCatch(
      pwr::pwr.anova.test(k = n_groups, f = cohens_f, sig.level = eff_alpha, power = power),
      error = function(e) NULL)
    required_n <- if (!is.null(res)) ceiling(res$n) else NA_integer_
  }

  # Guard against pathological solver output
  if (!is.na(required_n) && required_n > max_n) required_n <- NA_integer_
  if (!is.na(required_n) && required_n < 2) required_n <- 2L

  # Re-evaluate achieved power at the integer n
  achieved_power <- NA_real_
  if (!is.na(required_n)) {
    achieved_power <- if (test == "t") {
      pwr::pwr.t.test(n = required_n, d = effect_value, sig.level = eff_alpha,
                      type = "two.sample", alternative = "two.sided")$power
    } else {
      pwr::pwr.anova.test(k = n_groups, n = required_n, f = effect_value,
                          sig.level = eff_alpha)$power
    }
  }

  output <- list(
    required_n_biological = required_n,
    total_biological_samples = if (!is.na(required_n)) {
      required_n * (if (test == "anova") n_groups else 2)
    } else NA_integer_,
    target_power = power,
    achieved_power = achieved_power,
    effective_alpha = eff_alpha,
    parameters = list(
      delta_ct = delta_ct,
      sd_biological = sd_biological,
      test = test,
      n_groups = if (test == "anova") n_groups else 2,
      n_contrasts = n_contrasts,
      correction = correction,
      alpha_nominal = alpha
    ),
    assumptions = list(
      unit_of_replication = "BIOLOGICAL replicates (independent samples/donors/animals)",
      sd_interpretation = "BIOLOGICAL ΔCt SD (NOT technical)"
    ),
    method = if (test == "t") "pwr::pwr.t.test (solve n)" else "pwr::pwr.anova.test (solve n)",
    recommendation = recommend_qpcr_samplesize(required_n, delta_ct, sd_biological, correction, n_contrasts)
  )
  output[[effect_label]] <- effect_value

  cat("✓ qPCR ΔCt sample size estimation completed successfully!\n")
  if (!is.na(required_n)) {
    cat(sprintf("  Required n = %d BIOLOGICAL replicates/group for %.0f%% power\n",
                required_n, power * 100))
    cat(sprintf("  ΔΔCt=%.2f, SD_bio=%.2f, %s = %.3f, effective alpha = %.4f (%s, %d contrasts)\n",
                delta_ct, sd_biological, effect_label, effect_value, eff_alpha, correction, n_contrasts))
  } else {
    cat(sprintf("  Target power not reached within n <= %d. Increase effect, reduce SD, or relax power.\n", max_n))
  }

  return(output)
}


#' Sensitivity of qPCR power to the assumed biological ΔCt SD
#'
#' Because the biological ΔCt SD prior is uncertain (~0.5-1.0 Ct), this tabulates
#' power and Cohen's d across a range of biological SD values at a fixed n.
#'
#' @param delta_ct Expected ΔΔCt effect (Ct units)
#' @param n_biological Number of BIOLOGICAL replicates per group
#' @param sd_range Vector of biological ΔCt SD values to test (default: c(0.4, 0.6, 0.8, 1.0))
#' @param alpha Nominal per-contrast alpha before correction (default: 0.05)
#' @param test "t" (default) or "anova"
#' @param n_groups Number of groups for ANOVA (default: 2)
#' @param n_contrasts Number of planned contrasts (default: 1)
#' @param correction "holm" (default), "bonferroni", or "none"
#' @return Data frame with sd_biological, cohens_d (or cohens_f), effective_alpha, power, and an interpretation column
#' @export
#' @examples
#' sensitivity_qpcr_over_sd(delta_ct = 1.0, n_biological = 5,
#'                          sd_range = c(0.4, 0.6, 0.8, 1.0),
#'                          test = "t", n_contrasts = 4, correction = "holm")
sensitivity_qpcr_over_sd <- function(delta_ct,
                                     n_biological,
                                     sd_range = c(0.4, 0.6, 0.8, 1.0),
                                     alpha = 0.05,
                                     test = c("t", "anova"),
                                     n_groups = 2,
                                     n_contrasts = 1,
                                     correction = c("holm", "bonferroni", "none")) {

  if (!requireNamespace("pwr", quietly = TRUE)) {
    stop("Package 'pwr' is required. Install with install.packages('pwr')")
  }

  test <- match.arg(test)
  correction <- match.arg(correction)

  if (delta_ct <= 0) stop("delta_ct (ΔΔCt effect) must be positive (Ct units)")
  if (any(sd_range <= 0)) stop("all sd_range values must be positive (Ct units)")
  if (n_biological < 2) stop("n_biological must be >= 2 per group")

  eff_alpha <- effective_alpha_qpcr(alpha = alpha, n_contrasts = n_contrasts,
                                    correction = correction)

  effect_values <- numeric(length(sd_range))
  power_values <- numeric(length(sd_range))

  for (i in seq_along(sd_range)) {
    if (test == "t") {
      effect_values[i] <- delta_ct / sd_range[i]
      power_values[i] <- pwr::pwr.t.test(
        n = n_biological, d = effect_values[i], sig.level = eff_alpha,
        type = "two.sample", alternative = "two.sided")$power
    } else {
      effect_values[i] <- delta_ct / (sd_range[i] * sqrt(2 * n_groups))
      power_values[i] <- pwr::pwr.anova.test(
        k = n_groups, n = n_biological, f = effect_values[i], sig.level = eff_alpha)$power
    }
  }

  effect_col <- if (test == "t") "cohens_d" else "cohens_f"
  result <- data.frame(
    sd_biological = sd_range,
    effect_size = round(effect_values, 3),
    effective_alpha = round(eff_alpha, 4),
    power = round(power_values, 3),
    adequacy = ifelse(power_values >= 0.9, "adequate (>=0.90)",
               ifelse(power_values >= 0.8, "marginal (0.80-0.90)", "underpowered (<0.80)")),
    stringsAsFactors = FALSE
  )
  names(result)[names(result) == "effect_size"] <- effect_col

  cat("✓ qPCR ΔCt SD-sensitivity table computed successfully!\n")
  cat(sprintf("  ΔΔCt=%.2f, n=%d BIOLOGICAL/group, %s correction (%d contrasts), effective alpha=%.4f\n",
              delta_ct, n_biological, correction, n_contrasts, eff_alpha))
  cat("  Power vs BIOLOGICAL ΔCt SD (NOT technical):\n")
  print(result, row.names = FALSE)

  return(result)
}


#' Interpret qPCR power value
#' @keywords internal
interpret_power_qpcr <- function(power, n, correction, n_contrasts) {
  base <- sprintf("Power = %.3f with n = %d biological replicates/group (%s correction over %d contrasts). ",
                  power, n, correction, n_contrasts)
  if (power >= 0.9) {
    paste0(base, "Excellent: high power on biological replicates.")
  } else if (power >= 0.8) {
    paste0(base, "Good: adequate power for most qPCR applications.")
  } else if (power >= 0.7) {
    paste0(base, "Moderate: consider more biological replicates.")
  } else {
    paste0(base, "Low: increase biological replicates or accept a larger detectable ΔΔCt. Do NOT substitute technical replicates.")
  }
}


#' Recommend qPCR sample size
#' @keywords internal
recommend_qpcr_samplesize <- function(n, delta_ct, sd_biological, correction, n_contrasts) {
  if (is.na(n)) {
    return(paste0(
      "Target power not reached within the search range.\n",
      "  Options: detect a larger ΔΔCt, reduce biological SD (better-controlled sampling),\n",
      "  use fewer contrasts, or relax the target power. Do NOT power off technical SD."
    ))
  }
  rec <- paste0(
    "Recommended: ", n, " BIOLOGICAL replicates per group.\n",
    "  Effect: ΔΔCt = ", round(delta_ct, 2), " Ct, biological SD = ", round(sd_biological, 2), " Ct.\n",
    "  Correction: ", correction, " over ", n_contrasts, " contrast(s).\n"
  )
  if (n < 3) {
    rec <- paste0(rec, "Warning: n < 3 biological replicates is too low for reliable inference even at high effect sizes.\n")
  } else if (n <= 6) {
    rec <- paste0(rec, "This is a standard, feasible qPCR design.\n")
  } else if (n > 12) {
    rec <- paste0(rec, "Note: large n required. The biological ΔCt SD may be high — verify sampling/handling, or detect a larger ΔΔCt.\n")
  }
  rec
}
