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
scTour Visualization — UMAP + Pseudotime + Vector Field

Generates publication-quality visualizations from scTour inference results.
Requires an AnnData with scTour outputs (ptime, X_TNODE, X_VF).

Based on scTour v1.0.0 API.
Reference: Li Q. (2023) Genome Biology. https://doi.org/10.1186/s13059-023-02988-9
"""

import os
import sys
import argparse
import warnings
import numpy as np
import scanpy as sc
import sctour as sct
import matplotlib.pyplot as plt
from datetime import datetime

warnings.filterwarnings('ignore')

# Set matplotlib defaults for publication quality
plt.rcParams.update({
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.labelsize': 11,
})


def run_sctour_visualization(
    input_h5ad: str,
    output_dir: str = "sctour_results",
    # UMAP parameters
    sort_by_ptime: bool = True,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    # Color categories
    color_by: list = None,
    # Vector field parameters
    vf_reverse: bool = False,
    vf_stream: bool = True,
    vf_stream_density: int = 2,
    vf_grid: bool = False,
    vf_n_neigh: int = 20,
    vf_use_t_key: bool = True,
    # Output
    figsize: tuple = (10, 10),
    save_format: str = "png",
    show_plots: bool = False,
):
    """
    Generate scTour visualizations: UMAP of pseudotime + vector field.

    Parameters
    ----------
    input_h5ad : str
        Path to AnnData with scTour outputs.
    output_dir : str
        Directory to save figures.
    sort_by_ptime : bool
        Whether to sort cells by pseudotime before UMAP.
    n_neighbors : int
        Number of neighbors for UMAP.
    min_dist : float
        min_dist for UMAP.
    color_by : list or None
        Additional .obs columns to color UMAP by.
    vf_reverse : bool
        Whether to reverse vector field direction.
    vf_stream : bool
        Whether to use streamplot for vector field.
    vf_stream_density : int
        Stream density for vector field.
    vf_grid : bool
        Whether to show grid arrows.
    vf_n_neigh : int
        Number of neighbors for vector field.
    vf_use_t_key : bool
        Whether to incorporate pseudotime in neighbor detection.
    figsize : tuple
        Figure size (width, height).
    save_format : str
        Output format: 'png', 'pdf', 'svg', or 'all'.
    show_plots : bool
        Whether to display plots interactively.

    Returns
    -------
    dict with keys:
        - 'figures': list of saved figure paths
        - 'output_dir': output directory path
    """
    # ================================================================
    # Create output directories
    # ================================================================
    os.makedirs(output_dir, exist_ok=True)
    figures_dir = os.path.join(output_dir, "figures")
    os.makedirs(figures_dir, exist_ok=True)

    print("=" * 60)
    print(f"scTour Visualization — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ================================================================
    # Step 1: Load data
    # ================================================================
    print("\n=== Step 1: Load Data ===")
    print(f"  Loading: {input_h5ad}")
    adata = sc.read(input_h5ad)
    print(f"  ✓ Loaded: {adata.n_obs} cells, {adata.n_vars} genes")

    # Validate required fields
    required_fields = {
        'obs': ['ptime'],
        'obsm': ['X_TNODE', 'X_VF'],
    }
    for where, fields in required_fields.items():
        container = adata.obs if where == 'obs' else adata.obsm
        for field in fields:
            if field not in container:
                raise KeyError(
                    f"'{field}' not found in adata.{where}. "
                    f"Please run scTour inference first."
                )
    print(f"  ✓ All required fields present: ptime, X_TNODE, X_VF")

    # ================================================================
    # Step 2: Sort cells by pseudotime (optional)
    # ================================================================
    if sort_by_ptime:
        print("\n=== Step 2: Sort Cells by Pseudotime ===")
        adata = adata[np.argsort(adata.obs['ptime'].values), :]
        print(f"  ✓ Cells sorted by pseudotime")

    # ================================================================
    # Step 3: Compute UMAP on latent space
    # ================================================================
    print("\n=== Step 3: Compute UMAP ===")
    print(f"  Using X_TNODE latent space, n_neighbors={n_neighbors}, min_dist={min_dist}")
    sc.pp.neighbors(adata, use_rep='X_TNODE', n_neighbors=n_neighbors)
    sc.tl.umap(adata, min_dist=min_dist)
    print(f"  ✓ UMAP computed")

    # Store UMAP coordinates
    adata.obsm['X_umap_sctour'] = adata.obsm['X_umap']

    # ================================================================
    # Step 4: Generate Pseudotime UMAP
    # ================================================================
    print("\n=== Step 4: Generate Pseudotime UMAP ===")
    saved_figures = []

    formats = [save_format] if save_format != 'all' else ['png', 'pdf', 'svg']

    for fmt in formats:
        fig_path = os.path.join(figures_dir, f"sctour_ptime_umap.{fmt}")
        sc.pl.umap(
            adata,
            color='ptime',
            cmap='viridis',
            title='scTour Developmental Pseudotime',
            show=show_plots,
            save=False,
            frameon=False,
        )
        plt.savefig(fig_path, dpi=300, bbox_inches='tight')
        plt.close()
        saved_figures.append(fig_path)
        print(f"  ✓ Saved: {fig_path}")

    # ================================================================
    # Step 5: Generate additional color-by UMAPs
    # ================================================================
    if color_by:
        print("\n=== Step 5: Generate Color-by UMAPs ===")
        for color_col in color_by:
            if color_col in adata.obs.columns:
                for fmt in formats:
                    fig_path = os.path.join(figures_dir, f"sctour_umap_{color_col}.{fmt}")
                    sc.pl.umap(
                        adata,
                        color=color_col,
                        title=f'scTour — {color_col}',
                        show=show_plots,
                        save=False,
                        frameon=False,
                    )
                    plt.savefig(fig_path, dpi=300, bbox_inches='tight')
                    plt.close()
                    saved_figures.append(fig_path)
                print(f"  ✓ Saved: sctour_umap_{color_col}.*")
            else:
                print(f"  ⚠ Column '{color_col}' not found in adata.obs, skipping")

    # ================================================================
    # Step 6: Generate Vector Field Visualization
    # ================================================================
    print("\n=== Step 6: Generate Vector Field ===")

    t_key = 'ptime' if vf_use_t_key else None

    for fmt in formats:
        vf_path = os.path.join(figures_dir, f"sctour_vector_field.{fmt}")

        sct.vf.plot_vector_field(
            adata,
            zs_key='X_TNODE',
            vf_key='X_VF',
            reverse=vf_reverse,
            use_rep_neigh='X_TNODE',
            t_key=t_key,
            n_neigh=vf_n_neigh,
            stream=vf_stream,
            stream_density=vf_stream_density,
            grid=vf_grid,
            color='ptime',
            show=show_plots,
            save=vf_path,
            frameon=False,
            title='scTour Transcriptomic Vector Field',
        )
        plt.close()
        saved_figures.append(vf_path)
        print(f"  ✓ Saved: {vf_path}")

    # ================================================================
    # Step 7: Generate Multi-panel Figure
    # ================================================================
    print("\n=== Step 7: Generate Multi-panel Figure ===")

    n_panels = 2 + (1 if color_by and len(color_by) > 0 else 0)
    n_cols = min(n_panels, 3)
    n_rows = (n_panels + n_cols - 1) // n_cols

    for fmt in formats:
        fig, axs = plt.subplots(n_rows, n_cols, figsize=figsize)
        if n_panels == 1:
            axs = [axs]
        else:
            axs = axs.flatten()

        # Panel 1: Pseudotime
        sc.pl.umap(
            adata, color='ptime', cmap='viridis',
            title='Pseudotime', ax=axs[0],
            show=False, frameon=False
        )

        # Panel 2: Vector field
        sct.vf.plot_vector_field(
            adata, zs_key='X_TNODE', vf_key='X_VF',
            reverse=vf_reverse, use_rep_neigh='X_TNODE',
            t_key=t_key, n_neigh=vf_n_neigh,
            stream=vf_stream, stream_density=vf_stream_density,
            grid=vf_grid, color='ptime',
            show=False, ax=axs[1],
            legend_loc='none', frameon=False,
            title='Vector Field',
        )

        # Panel 3+: Additional color-by
        panel_idx = 2
        if color_by:
            for color_col in color_by[:n_panels - 2]:
                if color_col in adata.obs.columns:
                    sc.pl.umap(
                        adata, color=color_col,
                        title=color_col, ax=axs[panel_idx],
                        show=False, frameon=False
                    )
                    panel_idx += 1

        # Hide unused axes
        for i in range(panel_idx, len(axs)):
            axs[i].set_visible(False)

        plt.suptitle('scTour Cellular Dynamics Inference', fontsize=14, fontweight='bold')
        plt.tight_layout()

        multi_path = os.path.join(figures_dir, f"sctour_multipanel.{fmt}")
        plt.savefig(multi_path, dpi=300, bbox_inches='tight')
        plt.close()
        saved_figures.append(multi_path)
        print(f"  ✓ Saved: {multi_path}")

    # ================================================================
    # Summary
    # ================================================================
    print("\n" + "=" * 60)
    print("scTour Visualization — COMPLETE")
    print(f"  Figures saved to: {figures_dir}")
    print(f"  Total figures: {len(saved_figures)}")
    for f in saved_figures:
        print(f"    - {os.path.basename(f)}")
    print("=" * 60)

    return {
        'figures': saved_figures,
        'output_dir': output_dir,
    }


def main():
    parser = argparse.ArgumentParser(
        description="scTour Visualization — UMAP + Pseudotime + Vector Field"
    )
    parser.add_argument("--input", required=True, help="Path to AnnData with scTour outputs (.h5ad)")
    parser.add_argument("--output_dir", default="sctour_results", help="Output directory")
    parser.add_argument("--no_sort", action="store_true", help="Don't sort cells by pseudotime")
    parser.add_argument("--n_neighbors", type=int, default=15, help="UMAP n_neighbors")
    parser.add_argument("--min_dist", type=float, default=0.1, help="UMAP min_dist")
    parser.add_argument("--color_by", nargs="*", default=None, help="Additional .obs columns to color by")
    parser.add_argument("--vf_reverse", action="store_true", help="Reverse vector field direction")
    parser.add_argument("--vf_no_stream", action="store_true", help="Use grid arrows instead of streamplot")
    parser.add_argument("--vf_stream_density", type=int, default=2, help="Stream density")
    parser.add_argument("--vf_n_neigh", type=int, default=20, help="Vector field n_neighbors")
    parser.add_argument("--format", default="png", choices=["png", "pdf", "svg", "all"])
    parser.add_argument("--show", action="store_true", help="Show plots interactively")

    args = parser.parse_args()

    run_sctour_visualization(
        input_h5ad=args.input,
        output_dir=args.output_dir,
        sort_by_ptime=not args.no_sort,
        n_neighbors=args.n_neighbors,
        min_dist=args.min_dist,
        color_by=args.color_by,
        vf_reverse=args.vf_reverse,
        vf_stream=not args.vf_no_stream,
        vf_stream_density=args.vf_stream_density,
        vf_n_neigh=args.vf_n_neigh,
        save_format=args.format,
        show_plots=args.show,
    )


if __name__ == "__main__":
    main()