# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================
# Auto-saved proven script by MemOmics Self-Evolution Engine
# 参考官方文档: agent-generated
# Date: 2026-06-30 00:09
# Review score: 0.85
# Species: human | Tissue: blood
# Data quality: {}
# ============================================================

# GWAS analysis
library(data.table)
# ... real code ...