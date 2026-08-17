# 铁律：运行记录(query_logs)只是参考，不能跳过 rail_review/debate_analysis 审查
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
# 修复成功:   skill_evolution(action="record_run") — 记录成功
# ============================================================

"""
scTour Trajectory Inference — Main Entry Point

This script is the main entry point for the scTour skill.
It orchestrates both inference and visualization in one run.

Usage:
    python run.py --input data.h5ad --output_dir sctour_results
"""

import os
import sys
import argparse

# Add the scripts directory to the path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from run_sctour_inference import run_sctour_inference
from run_sctour_visualization import run_sctour_visualization


def main():
    parser = argparse.ArgumentParser(
        description="scTour — Complete Trajectory Inference Pipeline"
    )
    parser.add_argument("--input", required=True, help="Path to input AnnData (.h5ad)")
    parser.add_argument("--output_dir", default="sctour_results", help="Output directory")

    # Inference parameters
    parser.add_argument("--n_top_genes", type=int, default=2000, help="Number of HVGs")
    parser.add_argument("--loss_mode", default="nb", choices=["mse", "nb", "zinb"])
    parser.add_argument("--alpha_recon_lec", type=float, default=0.5)
    parser.add_argument("--alpha_recon_lode", type=float, default=0.5)
    parser.add_argument("--alpha_z", type=float, default=0.5)
    parser.add_argument("--alpha_predz", type=float, default=0.5)
    parser.add_argument("--n_latent", type=int, default=5)
    parser.add_argument("--percent", type=float, default=None)
    parser.add_argument("--nepoch", type=int, default=None)
    parser.add_argument("--batch_size", type=int, default=1024)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--random_state", type=int, default=0)
    parser.add_argument("--no_gpu", action="store_true")

    # Visualization parameters
    parser.add_argument("--no_sort", action="store_true")
    parser.add_argument("--n_neighbors", type=int, default=15)
    parser.add_argument("--min_dist", type=float, default=0.1)
    parser.add_argument("--color_by", nargs="*", default=["celltype"])
    parser.add_argument("--format", default="png", choices=["png", "pdf", "svg", "all"])

    # Skip options
    parser.add_argument("--viz_only", action="store_true", help="Skip inference, only visualize")
    parser.add_argument("--infer_only", action="store_true", help="Only inference, skip visualization")

    args = parser.parse_args()

    adata_path = args.input

    if not args.viz_only:
        print("\n" + "=" * 60)
        print("PHASE 1: scTour Inference")
        print("=" * 60)

        result = run_sctour_inference(
            input_h5ad=args.input,
            output_dir=args.output_dir,
            n_top_genes=args.n_top_genes,
            loss_mode=args.loss_mode,
            alpha_recon_lec=args.alpha_recon_lec,
            alpha_recon_lode=args.alpha_recon_lode,
            alpha_z=args.alpha_z,
            alpha_predz=args.alpha_predz,
            n_latent=args.n_latent,
            percent=args.percent,
            nepoch=args.nepoch,
            batch_size=args.batch_size,
            lr=args.lr,
            random_state=args.random_state,
            use_gpu=not args.no_gpu,
        )

        # Use the output AnnData for visualization
        adata_path = os.path.join(args.output_dir, "data", "adata_with_sctour.h5ad")

    if not args.infer_only:
        print("\n" + "=" * 60)
        print("PHASE 2: scTour Visualization")
        print("=" * 60)

        run_sctour_visualization(
            input_h5ad=adata_path,
            output_dir=args.output_dir,
            sort_by_ptime=not args.no_sort,
            n_neighbors=args.n_neighbors,
            min_dist=args.min_dist,
            color_by=args.color_by,
            save_format=args.format,
        )

    print("\n" + "=" * 60)
    print("scTour Pipeline — ALL DONE")
    print(f"Results: {os.path.abspath(args.output_dir)}")
    print("=" * 60)


if __name__ == "__main__":
    main()