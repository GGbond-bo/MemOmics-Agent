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
Visualization functions for clustering results.

This module creates publication-quality plots using plotnine (with Prism theme)
for general plots and seaborn for heatmaps/dendrograms.
"""

import numpy as np
import pandas as pd
from typing import Optional, List
import warnings
import os

try:
    from adjustText import adjust_text
    HAS_ADJUSTTEXT = True
except ImportError:
    HAS_ADJUSTTEXT = False


def _save_plot(plot_obj, output_path: str, dpi: int = 300, **kwargs):
    """
    Save plot in both PNG and SVG formats with explicit fallback.

    Parameters
    ----------
    plot_obj : plotnine.ggplot or matplotlib figure
        Plot object to save
    output_path : str
        Base output path (without extension)
    dpi : int
        Resolution for raster format (PNG)
    **kwargs : additional save parameters
    """
    # Remove extension if provided
    base_path = os.path.splitext(output_path)[0]

    # Always save PNG (primary format)
    png_path = f"{base_path}.png"
    plot_obj.save(png_path, dpi=dpi, **kwargs)

    # Always try SVG with explicit fallback
    svg_path = f"{base_path}.svg"
    try:
        plot_obj.save(svg_path, dpi=dpi, **kwargs)
    except Exception as e:
        # SVG export failed, but PNG is still available
        print(f"   (SVG export failed: {e})")
        svg_path = None

    return png_path, svg_path


def _save_matplotlib_plot(fig_obj, output_path: str, dpi: int = 300, **kwargs):
    """
    Save matplotlib/seaborn plot in both PNG and SVG formats with explicit fallback.

    Parameters
    ----------
    fig_obj : matplotlib figure or seaborn object
        Figure object to save
    output_path : str
        Base output path (without extension)
    dpi : int
        Resolution for raster format (PNG)
    **kwargs : additional save parameters
    """
    # Remove extension if provided
    base_path = os.path.splitext(output_path)[0]

    # Always save PNG (primary format)
    png_path = f"{base_path}.png"
    fig_obj.savefig(png_path, dpi=dpi, bbox_inches='tight', **kwargs)

    # Always try SVG with explicit fallback
    svg_path = f"{base_path}.svg"
    try:
        fig_obj.savefig(svg_path, dpi=dpi, bbox_inches='tight', **kwargs)
    except Exception as e:
        # SVG export failed, but PNG is still available
        print(f"   (SVG export failed: {e})")
        svg_path = None

    return png_path, svg_path


def plot_all_results(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    sample_names: List[str],
    feature_names: List[str],
    pca_data: Optional[np.ndarray] = None,
    umap_embedding: Optional[np.ndarray] = None,
    linkage_matrix: Optional[np.ndarray] = None,
    metadata: Optional[pd.DataFrame] = None,
    output_dir: str = "clustering_visualizations/"
):
    """
    Generate comprehensive set of clustering visualization plots.

    Parameters
    ----------
    data : np.ndarray
        Original data matrix (samples × features)
    cluster_labels : np.ndarray
        Cluster assignments
    sample_names : List[str]
        Sample names
    feature_names : List[str]
        Feature names
    pca_data : np.ndarray, optional
        PCA-transformed data
    umap_embedding : np.ndarray, optional
        UMAP embedding
    linkage_matrix : np.ndarray, optional
        Hierarchical clustering linkage matrix
    metadata : pd.DataFrame, optional
        Sample metadata
    output_dir : str, default="clustering_visualizations/"
        Directory to save plots
    """

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    print(f"\nGenerating visualization plots in {output_dir}...")

    # 1. PCA scatter plot
    if pca_data is not None:
        plot_pca_scatter(
            pca_data, cluster_labels, sample_names,
            output_path=os.path.join(output_dir, "pca_scatter")
        )

    # 2. UMAP plot
    if umap_embedding is not None:
        plot_umap_scatter(
            umap_embedding, cluster_labels, sample_names,
            output_path=os.path.join(output_dir, "umap_scatter")
        )

    # 3. Dendrogram (if hierarchical)
    if linkage_matrix is not None:
        from scripts.hierarchical_clustering import _plot_dendrogram
        _plot_dendrogram(
            linkage_matrix,
            n_clusters=len(np.unique(cluster_labels[cluster_labels >= 0])),
            labels=sample_names,
            save_path=os.path.join(output_dir, "dendrogram")
        )

    # 4. Cluster sizes barplot
    plot_cluster_sizes(
        cluster_labels,
        output_path=os.path.join(output_dir, "cluster_sizes")
    )

    # 5. Silhouette plot
    from scripts.optimal_clusters import silhouette_analysis_per_sample
    silhouette_analysis_per_sample(
        data, cluster_labels, plot=True,
        output_path=os.path.join(output_dir, "silhouette_plot")
    )

    print(f"✓ Plots saved to {output_dir}")


def plot_pca_scatter(
    pca_data: np.ndarray,
    cluster_labels: np.ndarray,
    sample_names: List[str],
    output_path: Optional[str] = None,
    label_samples: bool = False
):
    """
    Create PCA scatter plot colored by cluster with optional sample labels.

    Parameters
    ----------
    pca_data : np.ndarray
        PCA-transformed data (samples × n_components)
    cluster_labels : np.ndarray
        Cluster assignments
    sample_names : List[str]
        Sample names
    output_path : str, optional
        Path to save plot
    label_samples : bool, optional
        Add sample name labels with adjustText (default: False)
    """

    from plotnine import ggplot, aes, geom_point, labs, theme_minimal, scale_color_brewer
    from plotnine_prism import theme_prism

    # Create dataframe
    df = pd.DataFrame({
        'PC1': pca_data[:, 0],
        'PC2': pca_data[:, 1],
        'Cluster': cluster_labels.astype(str),
        'Sample': sample_names
    })

    # Create plot
    plot = (ggplot(df, aes(x='PC1', y='PC2', color='Cluster'))
            + geom_point(size=3, alpha=0.7)
            + labs(title='PCA Clustering Results', x='PC1', y='PC2')
            + theme_prism()
            + scale_color_brewer(type='qual', palette='Set2'))

    if output_path:
        # Add labels with adjustText if requested and available
        if label_samples and HAS_ADJUSTTEXT:
            import matplotlib.pyplot as plt

            # Draw base plot
            fig = plot.draw()
            ax = fig.axes[0]

            # Add labels with adjustText for non-overlapping placement
            texts = [
                ax.text(row['PC1'], row['PC2'], row['Sample'],
                       fontsize=8, alpha=0.8)
                for _, row in df.iterrows()
            ]
            adjust_text(
                texts,
                arrowprops=dict(arrowstyle='->', color='gray', lw=0.5, alpha=0.6),
                expand_points=(1.5, 1.5),
                force_text=(0.3, 0.3)
            )

            # Save with labels
            base_path = os.path.splitext(output_path)[0]
            png_path = f"{base_path}.png"
            svg_path = f"{base_path}.svg"

            fig.savefig(png_path, dpi=300, bbox_inches='tight')
            print(f"PCA plot saved to {png_path}")

            try:
                fig.savefig(svg_path, bbox_inches='tight')
                print(f"PCA plot saved to {svg_path}")
            except Exception:
                pass

            plt.close(fig)
        else:
            # Save without labels
            png_path, svg_path = _save_plot(plot, output_path, dpi=300, width=8, height=6)
            if svg_path:
                print(f"PCA plot saved to {png_path} and {svg_path}")
            else:
                print(f"PCA plot saved to {png_path}")

    return plot


def plot_umap_scatter(
    umap_embedding: np.ndarray,
    cluster_labels: np.ndarray,
    sample_names: List[str],
    output_path: Optional[str] = None,
    label_samples: bool = False
):
    """
    Create UMAP scatter plot colored by cluster with optional sample labels.

    Parameters
    ----------
    umap_embedding : np.ndarray
        UMAP embedding (samples × 2)
    cluster_labels : np.ndarray
        Cluster assignments
    sample_names : List[str]
        Sample names
    output_path : str, optional
        Path to save plot
    label_samples : bool, optional
        Add sample name labels with adjustText (default: False)
    """

    from plotnine import ggplot, aes, geom_point, labs, scale_color_brewer
    from plotnine_prism import theme_prism

    df = pd.DataFrame({
        'UMAP1': umap_embedding[:, 0],
        'UMAP2': umap_embedding[:, 1],
        'Cluster': cluster_labels.astype(str),
        'Sample': sample_names
    })

    plot = (ggplot(df, aes(x='UMAP1', y='UMAP2', color='Cluster'))
            + geom_point(size=3, alpha=0.7)
            + labs(title='UMAP Clustering Results', x='UMAP 1', y='UMAP 2')
            + theme_prism()
            + scale_color_brewer(type='qual', palette='Set2'))

    if output_path:
        # Add labels with adjustText if requested and available
        if label_samples and HAS_ADJUSTTEXT:
            import matplotlib.pyplot as plt

            # Draw base plot
            fig = plot.draw()
            ax = fig.axes[0]

            # Add labels with adjustText for non-overlapping placement
            texts = [
                ax.text(row['UMAP1'], row['UMAP2'], row['Sample'],
                       fontsize=8, alpha=0.8)
                for _, row in df.iterrows()
            ]
            adjust_text(
                texts,
                arrowprops=dict(arrowstyle='->', color='gray', lw=0.5, alpha=0.6),
                expand_points=(1.5, 1.5),
                force_text=(0.3, 0.3)
            )

            # Save with labels
            base_path = os.path.splitext(output_path)[0]
            png_path = f"{base_path}.png"
            svg_path = f"{base_path}.svg"

            fig.savefig(png_path, dpi=300, bbox_inches='tight')
            print(f"UMAP plot saved to {png_path}")

            try:
                fig.savefig(svg_path, bbox_inches='tight')
                print(f"UMAP plot saved to {svg_path}")
            except Exception:
                pass

            plt.close(fig)
        else:
            # Save without labels
            png_path, svg_path = _save_plot(plot, output_path, dpi=300, width=8, height=6)
            if svg_path:
                print(f"UMAP plot saved to {png_path} and {svg_path}")
            else:
                print(f"UMAP plot saved to {png_path}")

    return plot


def plot_cluster_sizes(
    cluster_labels: np.ndarray,
    output_path: Optional[str] = None
):
    """Create barplot of cluster sizes."""

    from plotnine import ggplot, aes, geom_bar, labs, theme_minimal
    from plotnine_prism import theme_prism

    # Count clusters
    unique, counts = np.unique(cluster_labels[cluster_labels >= 0], return_counts=True)

    df = pd.DataFrame({
        'Cluster': unique.astype(str),
        'Count': counts
    })

    plot = (ggplot(df, aes(x='Cluster', y='Count', fill='Cluster'))
            + geom_bar(stat='identity', show_legend=False)
            + labs(title='Cluster Sizes', x='Cluster', y='Number of Samples')
            + theme_prism())

    if output_path:
        png_path, svg_path = _save_plot(plot, output_path, dpi=300, width=6, height=6)
        if svg_path:
            print(f"Cluster sizes plot saved to {png_path} and {svg_path}")
        else:
            print(f"Cluster sizes plot saved to {png_path}")

    return plot


def plot_cluster_heatmap(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    feature_names: List[str],
    sample_names: List[str],
    top_n_features: int = 50,
    output_path: Optional[str] = None
):
    """
    Create clustered heatmap using seaborn.

    Parameters
    ----------
    data : np.ndarray
        Data matrix
    cluster_labels : np.ndarray
        Cluster assignments
    feature_names : List[str]
        Feature names
    sample_names : List[str]
        Sample names
    top_n_features : int, default=50
        Number of top variable features to include
    output_path : str, optional
        Path to save plot
    """

    import seaborn as sns
    import matplotlib.pyplot as plt

    # Select top variable features
    variances = np.var(data, axis=0)
    top_indices = np.argsort(variances)[-top_n_features:]

    data_subset = data[:, top_indices]
    features_subset = [feature_names[i] for i in top_indices]

    # Create DataFrame
    df = pd.DataFrame(data_subset, columns=features_subset, index=sample_names)

    # Sort by cluster
    sort_idx = np.argsort(cluster_labels)
    df_sorted = df.iloc[sort_idx]

    # Create cluster color map
    cluster_colors = pd.Series(cluster_labels[sort_idx], index=df_sorted.index, name='Cluster')

    # Create heatmap
    heatmap = sns.clustermap(
        df_sorted,
        cmap='RdBu_r',
        center=0,
        standard_scale=1,
        row_cluster=False,
        col_cluster=True,
        row_colors=cluster_colors.map(sns.color_palette('Set2', len(np.unique(cluster_labels)))),
        figsize=(12, 10),
        dendrogram_ratio=0.1,
        cbar_kws={'label': 'Z-score'}
    )

    heatmap.ax_heatmap.set_xlabel('Features', fontsize=12)
    heatmap.ax_heatmap.set_ylabel('Samples', fontsize=12)

    if output_path:
        png_path, svg_path = _save_matplotlib_plot(heatmap, output_path, dpi=300)
        if svg_path:
            print(f"Heatmap saved to {png_path} and {svg_path}")
        else:
            print(f"Heatmap saved to {png_path}")

    plt.show()
    plt.close()

    return heatmap
