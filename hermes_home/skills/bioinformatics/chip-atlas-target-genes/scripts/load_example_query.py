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
"""
Example query data for ChIP-Atlas Target Genes skill.

Provides pre-defined TF queries for testing and demonstration.
"""


def load_example_query(query="tp53"):
    """
    Load a pre-defined example query for target genes analysis.

    Args:
        query: Query name - "tp53" (default), "e2f1", or "myc"

    Returns:
        dict: Query parameters with keys: protein, genome, distance, description
    """
    queries = {
        "tp53": {
            "protein": "TP53",
            "genome": "hg38",
            "distance": 5,
            "description": (
                "TP53 (tumor protein p53) - Master tumor suppressor and transcription factor. "
                "Well-characterized targets include CDKN1A, BAX, MDM2. "
                "Large dataset (~395 experiments, ~16K target genes). "
                "Expected runtime: ~10-30 seconds (large download ~13MB)."
            ),
        },
        "e2f1": {
            "protein": "E2F1",
            "genome": "hg38",
            "distance": 5,
            "description": (
                "E2F1 (E2F transcription factor 1) - Key cell cycle regulator. "
                "Targets include genes involved in DNA replication and cell division. "
                "Moderate dataset size. "
                "Expected runtime: ~5-15 seconds."
            ),
        },
        "myc": {
            "protein": "MYC",
            "genome": "hg38",
            "distance": 5,
            "description": (
                "MYC (MYC proto-oncogene) - Key transcription factor in cell growth. "
                "Broad binding profile with many target genes. "
                "Expected runtime: ~5-15 seconds."
            ),
        },
    }

    key = query.lower().strip()
    if key not in queries:
        available = ", ".join(f'"{k}"' for k in queries)
        raise ValueError(f"Unknown example query '{query}'. Available: {available}")

    result = queries[key]
    print(f"  ✓ Query loaded: {result['protein']} target genes ({result['genome']}, ±{result['distance']}kb)")
    print(f"    {result['description']}")
    return result
