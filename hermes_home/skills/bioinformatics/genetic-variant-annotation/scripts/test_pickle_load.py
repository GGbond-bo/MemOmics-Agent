
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
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. 图片是否生成？无图 → 重新执行
#        b. 图片是否空白（全白/全黑/全单一色）？空白 → 强制重新出图
#        c. 图片是否有 NA/缺失值（>10%像素是NA）？有NA → 强制重新出图
#        d. 图片大小是否过小（<5KB）？过小 → 强制重新出图
#        e. 图片数量是否足够？（每步至少1张图，关键步骤至少2-3张）
#        f. 代码行数是否合理？是否分段执行（禁止&&连接）？
#        g. 数值范围是否合理？跟知识库对应吗？
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
# ★ 参数和结论辩论铁律:
#   - 有参数选择 → 必须调 debate_analysis 辩论
#   - 有结论输出 → 必须调 debate_analysis 辩论
#   - 辩论格式：正方(支持) vs 反方(质疑+替代) → 裁判决断
#   - 最多3轮，3轮后选最优结果
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
#   ★ 强制: 图片空白/NA/过小 → 重新出图 | 图片不够 → 补图 | 代码未分段 → 重写
#   ★ 强制: 有参数有结论 → debate_analysis 辩论
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================


"""
Test Pickle Loading

Simple script to verify that analysis_object.pkl can be loaded correctly.
This demonstrates downstream skill compatibility.
"""

import sys
import pickle
from pathlib import Path


def test_pickle_load(pickle_path="results/analysis_object.pkl"):
    """
    Test loading pickled analysis object.

    Parameters
    ----------
    pickle_path : str
        Path to pickled analysis object (default: "results/analysis_object.pkl")

    Returns
    -------
    dict
        Loaded analysis object with variants, genes, and metadata
    """
    pickle_file = Path(pickle_path)

    if not pickle_file.exists():
        print(f"Error: Pickle file not found: {pickle_path}")
        print("Run the Standard Workflow first to generate analysis_object.pkl")
        return None

    print("="*70)
    print("TESTING PICKLE LOAD")
    print("="*70)
    print()

    # Load pickle
    print(f"Loading: {pickle_path}")
    try:
        with open(pickle_file, 'rb') as f:
            obj = pickle.load(f)
        print("✓ Pickle loaded successfully!")
    except Exception as e:
        print(f"✗ Failed to load pickle: {e}")
        return None

    print()
    print("Analysis Object Contents:")
    print("-"*70)

    # Check structure
    if isinstance(obj, dict):
        print(f"  Type: Dictionary with {len(obj)} keys")
        print(f"  Keys: {list(obj.keys())}")

        # Check variants
        if 'variants' in obj:
            variants_df = obj['variants']
            print(f"\n  Variants DataFrame:")
            print(f"    Shape: {variants_df.shape}")
            print(f"    Columns: {len(variants_df.columns)}")
            if len(variants_df) > 0:
                print(f"    Sample columns: {list(variants_df.columns[:5])}")

        # Check genes
        if 'genes' in obj:
            genes_df = obj['genes']
            if genes_df is not None:
                print(f"\n  Genes DataFrame:")
                print(f"    Shape: {genes_df.shape}")
                print(f"    Columns: {list(genes_df.columns)}")

        # Check metadata
        if 'tool' in obj:
            print(f"\n  Tool: {obj['tool']}")
        if 'n_variants' in obj:
            print(f"  Total variants: {obj['n_variants']}")
        if 'n_genes' in obj:
            print(f"  Total genes: {obj['n_genes']}")

    else:
        print(f"  Type: {type(obj)}")
        print("  Warning: Expected dictionary structure")

    print()
    print("="*70)
    print("✓ Pickle load test completed successfully!")
    print("="*70)
    print()
    print("Downstream skills can load this object with:")
    print("  import pickle")
    print(f"  obj = pickle.load(open('{pickle_path}', 'rb'))")
    print()

    return obj


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Test pickle loading')
    parser.add_argument(
        '--pickle',
        default='results/analysis_object.pkl',
        help='Path to pickle file (default: results/analysis_object.pkl)'
    )

    args = parser.parse_args()

    # Run test
    obj = test_pickle_load(args.pickle)

    if obj is None:
        sys.exit(1)
    else:
        sys.exit(0)
