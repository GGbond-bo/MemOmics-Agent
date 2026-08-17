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
# DESeq2 with multiple conditions

library(DESeq2)

# Example with three conditions
set.seed(42)
n_genes <- 1000
n_samples <- 9

counts <- matrix(rnbinom(n_genes * n_samples, mu = 100, size = 10),
                 nrow = n_genes,
                 dimnames = list(paste0('gene', 1:n_genes),
                                paste0('sample', 1:n_samples)))

coldata <- data.frame(
    condition = factor(rep(c('control', 'treatmentA', 'treatmentB'), each = 3)),
    row.names = colnames(counts)
)

# Create DESeqDataSet
dds <- DESeqDataSetFromMatrix(countData = counts,
                               colData = coldata,
                               design = ~ condition)

# Pre-filter and set reference
keep <- rowSums(counts(dds)) >= 10
dds <- dds[keep,]
dds$condition <- relevel(dds$condition, ref = 'control')

# Run DESeq2
dds <- DESeq(dds)

# Check available coefficients
cat('Available coefficients:\n')
print(resultsNames(dds))

# Compare treatmentA vs control (with log2FC shrinkage)
res_A <- lfcShrink(dds, coef = 'condition_treatmentA_vs_control', type = 'apeglm')
cat('\nTreatmentA vs Control:\n')
summary(res_A)

# Compare treatmentB vs control (with log2FC shrinkage)
res_B <- lfcShrink(dds, coef = 'condition_treatmentB_vs_control', type = 'apeglm')
cat('\nTreatmentB vs Control:\n')
summary(res_B)

# Compare treatmentA vs treatmentB (using contrast, ashr for non-coefficient comparisons)
res_AB <- lfcShrink(dds, contrast = c('condition', 'treatmentA', 'treatmentB'), type = 'ashr')
cat('\nTreatmentA vs TreatmentB:\n')
summary(res_AB)
