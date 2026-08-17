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
Visualize pySCENIC regulon activities and networks.

Always exports both PNG and SVG formats with graceful fallback.
"""

import os
import numpy as np
import pandas as pd
import scanpy as sc
import seaborn as sns
import matplotlib.pyplot as plt
import networkx as nx

# Set the theme to ticks
sns.set_style("ticks")

# Configure font to Helvetica
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica']


def _save_figure_dual_format(fig, base_path, dpi=300):
    """
    Save figure in both PNG and SVG formats with graceful fallback.

    Always tries both formats - PNG is primary, SVG with fallback.
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(base_path) if os.path.dirname(base_path) else ".", exist_ok=True)

    # Remove extension if present
    base_path = os.path.splitext(base_path)[0]

    # Always save PNG (primary format)
    png_path = f"{base_path}.png"
    try:
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', format='png')
        print(f"   Saved: {png_path}")
    except Exception as e:
        print(f"   Warning: PNG save failed: {e}")

    # Always try SVG (high-quality vector format)
    svg_path = f"{base_path}.svg"
    try:
        fig.savefig(svg_path, dpi=dpi, bbox_inches='tight', format='svg')
        print(f"   Saved: {svg_path}")
    except Exception as e:
        print(f"   (SVG export failed - PNG available)")


def plot_regulon_activity_umap(adata, regulon_name, output_file=None):
    """
    Plot regulon activity on UMAP.

    Parameters:
    -----------
    adata : AnnData
        AnnData object with regulon activities in .obsm['X_aucell']
    regulon_name : str
        Name of regulon to visualize
    output_file : str, optional
        Path to save plot (without extension - both PNG and SVG will be created)

    Examples:
    ---------
    >>> plot_regulon_activity_umap(adata, 'MYC(+)', output_file='myc_activity_umap')
    """
    # Ensure UMAP is computed
    if 'X_umap' not in adata.obsm:
        print("Computing UMAP...")
        sc.pp.neighbors(adata)
        sc.tl.umap(adata)

    # Get regulon index
    regulon_idx = adata.uns['regulon_names'].index(regulon_name)
    adata.obs['regulon_activity'] = adata.obsm['X_aucell'][:, regulon_idx]

    fig, ax = plt.subplots(figsize=(8, 6))
    sc.pl.umap(adata, color='regulon_activity', ax=ax, show=False,
               title=f'{regulon_name} Activity', cmap='viridis')

    if output_file:
        _save_figure_dual_format(fig, output_file)
    plt.close()


def plot_top_regulons_heatmap(auc_matrix, adata=None, top_n=20, output_file='regulon_heatmap'):
    """
    Create heatmap of top regulon activities across cell types.

    Uses seaborn.clustermap for publication-quality heatmap with clustering.
    Exports both PNG and SVG formats.

    Parameters:
    -----------
    auc_matrix : pd.DataFrame
        AUCell matrix (cells x regulons)
    adata : AnnData, optional
        AnnData object with cell type annotations
    top_n : int
        Number of top regulons to plot (default: 20)
    output_file : str
        Path to save plot (without extension)

    Examples:
    ---------
    >>> plot_top_regulons_heatmap(auc_matrix, adata, top_n=20, output_file='regulon_heatmap')
    """
    # Get top regulons by variance
    regulon_var = auc_matrix.var().sort_values(ascending=False)
    top_regulons = regulon_var.head(top_n).index.tolist()

    plot_data = auc_matrix[top_regulons].copy()

    # If cell type annotations exist, aggregate by cell type
    if adata is not None and 'cell_type' in adata.obs.columns:
        plot_data['cell_type'] = adata.obs['cell_type'].values
        plot_data = plot_data.groupby('cell_type').mean()
    else:
        # Subsample cells if dataset is too large (prevents memory/rendering issues)
        max_cells_to_plot = 1000
        if len(plot_data) > max_cells_to_plot:
            print(f"  Subsampling {max_cells_to_plot} cells from {len(plot_data)} for heatmap visualization")
            sample_idx = np.random.choice(len(plot_data), max_cells_to_plot, replace=False)
            sample_idx = np.sort(sample_idx)  # Keep order for better visualization
            plot_data = plot_data.iloc[sample_idx, :]

    # Create clustermap
    heatmap = sns.clustermap(
        plot_data.T,
        cmap='viridis',
        center=None,
        figsize=(12, max(6, len(plot_data) * 0.4)),
        cbar_kws={'label': 'AUCell Score'},
        xticklabels=True,
        yticklabels=True
    )

    heatmap.ax_heatmap.set_xlabel(
        'Cell Type' if (adata is not None and 'cell_type' in adata.obs.columns) else 'Cells',
        fontsize=10
    )
    heatmap.ax_heatmap.set_ylabel('Regulon', fontsize=10)
    heatmap.fig.suptitle('Top Regulon Activities', fontsize=12, y=0.98)

    plt.setp(heatmap.ax_heatmap.get_xticklabels(), rotation=45, ha='right', fontsize=8)

    _save_figure_dual_format(heatmap.fig, output_file)
    plt.close()


def plot_regulon_network(regulons, top_n=10, output_file='regulon_network'):
    """
    Create network visualization of top regulons.

    Parameters:
    -----------
    regulons : list
        List of Regulon objects
    top_n : int
        Number of top regulons to visualize (default: 10)
    output_file : str
        Path to save plot (without extension)

    Examples:
    ---------
    >>> plot_regulon_network(regulons, top_n=10, output_file='regulon_network')
    """
    # Get top regulons by number of targets
    regulon_sizes = [(r.name, len(r.genes)) for r in regulons]
    regulon_sizes = sorted(regulon_sizes, key=lambda x: x[1], reverse=True)[:top_n]
    top_regulon_names = [r[0] for r in regulon_sizes]

    # Build network
    G = nx.Graph()

    for reg in regulons:
        if reg.name in top_regulon_names:
            tf = reg.transcription_factor
            G.add_node(tf, node_type='TF', size=len(reg.genes))

            # Add top targets
            targets = list(reg.genes)[:10]
            for target in targets:
                G.add_node(target, node_type='target', size=1)
                G.add_edge(tf, target)

    # Layout
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

    # Node colors and sizes
    node_colors = ['#e74c3c' if G.nodes[n]['node_type'] == 'TF' else '#3498db' for n in G.nodes()]
    node_sizes = [G.nodes[n]['size'] * 50 + 100 for n in G.nodes()]

    fig, ax = plt.subplots(figsize=(14, 12))

    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes, alpha=0.8, ax=ax)
    nx.draw_networkx_edges(G, pos, alpha=0.3, ax=ax)

    # Label TFs
    tf_labels = {n: n for n in G.nodes() if G.nodes[n]['node_type'] == 'TF'}
    nx.draw_networkx_labels(G, pos, tf_labels, font_size=10, font_weight='bold', ax=ax)

    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#e74c3c', markersize=12, label='TF'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#3498db', markersize=8, label='Target Gene'),
    ]
    ax.legend(handles=legend_elements, loc='upper left', fontsize=10)

    ax.set_title('Gene Regulatory Network (Top Regulons)', fontsize=12)
    ax.axis('off')

    plt.tight_layout()
    _save_figure_dual_format(fig, output_file)
    plt.close()


def generate_all_visualizations(auc_matrix, regulons, adata=None, top_n=20, output_dir="."):
    """
    Generate all standard pySCENIC visualizations.

    Exports both PNG and SVG formats for all plots with graceful fallback.

    Parameters:
    -----------
    auc_matrix : pd.DataFrame
        AUCell matrix (cells x regulons)
    regulons : list
        List of Regulon objects
    adata : AnnData, optional
        AnnData object for UMAP and cell type information
    top_n : int
        Number of top regulons to visualize (default: 20)
    output_dir : str
        Directory to save plots (default: current directory)

    Examples:
    ---------
    >>> generate_all_visualizations(auc_matrix, regulons, adata, output_dir="scenic_plots")
    """
    os.makedirs(output_dir, exist_ok=True)

    print("Generating visualizations...")

    # Generate heatmap
    print("  Creating regulon heatmap...")
    plot_top_regulons_heatmap(
        auc_matrix, adata, top_n=top_n,
        output_file=os.path.join(output_dir, 'regulon_heatmap')
    )

    # Generate network
    print("  Creating regulon network...")
    plot_regulon_network(
        regulons, top_n=top_n,
        output_file=os.path.join(output_dir, 'regulon_network')
    )

    print(f"\n✓ All visualizations generated successfully!")
    print(f"  Output directory: {output_dir}")
    print(f"  Files: PNG + SVG formats for all plots")
