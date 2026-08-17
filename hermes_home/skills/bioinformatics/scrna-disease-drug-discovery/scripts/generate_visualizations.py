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

#!/usr/bin/env python3
"""
Generate publication-quality visualizations for disease drug discovery.

All plots are saved in both PNG (300 DPI) and SVG formats.

Usage:
  from generate_visualizations import generate_all_plots
  generate_all_plots(adata, de_results, pathway_results, lr_results,
                      genetic_results, scores, output_dir="results")
"""

import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)


def _setup_matplotlib():
    """Configure matplotlib for publication-quality output."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns
    sns.set_style("ticks")
    plt.rcParams.update({
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "figure.figsize": (8, 6),
    })
    return plt, sns


def _save_plot(fig, output_dir, name):
    """Save a figure in both PNG and SVG formats."""
    os.makedirs(output_dir, exist_ok=True)
    png_path = os.path.join(output_dir, f"{name}.png")
    fig.savefig(png_path, dpi=300, bbox_inches="tight", facecolor="white")

    try:
        svg_path = os.path.join(output_dir, f"{name}.svg")
        fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
    except Exception:
        pass  # SVG export is optional

    import matplotlib.pyplot as plt
    plt.close(fig)
    return png_path


# ---------------------------------------------------------------------------
# Individual plot functions
# ---------------------------------------------------------------------------

def plot_umap_overview(adata, output_dir="results"):
    """Plot UMAP colored by cell type and condition."""
    plt, sns = _setup_matplotlib()
    import scanpy as sc

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Cell type UMAP
    if "X_umap" in adata.obsm:
        sc.pl.umap(adata, color="cell_type", ax=axes[0], show=False,
                    title="Cell Types", frameon=True)
        sc.pl.umap(adata, color="condition", ax=axes[1], show=False,
                    title="Condition", frameon=True)
    else:
        axes[0].text(0.5, 0.5, "UMAP not computed", ha="center", va="center",
                     transform=axes[0].transAxes)
        axes[1].text(0.5, 0.5, "UMAP not computed", ha="center", va="center",
                     transform=axes[1].transAxes)

    fig.suptitle("Dataset Overview", fontsize=14, y=1.02)
    fig.tight_layout()
    _save_plot(fig, output_dir, "umap_overview")


def plot_de_volcanos(de_results, output_dir="results", max_plots=6):
    """Plot volcano plots for top cell types by number of DEGs."""
    plt, sns = _setup_matplotlib()

    # Rank cell types by number of significant DEGs
    ct_ndeg = {}
    for ct, df in de_results.items():
        padj_col = "padj" if "padj" in df.columns else "pvals_adj"
        if padj_col in df.columns:
            ct_ndeg[ct] = (df[padj_col] < 0.05).sum()
    sorted_cts = sorted(ct_ndeg, key=ct_ndeg.get, reverse=True)[:max_plots]

    if not sorted_cts:
        return

    n_plots = len(sorted_cts)
    n_cols = min(3, n_plots)
    n_rows = (n_plots + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 5 * n_rows))
    if n_plots == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for i, ct in enumerate(sorted_cts):
        ax = axes[i]
        df = de_results[ct].copy()

        padj_col = "padj" if "padj" in df.columns else "pvals_adj"
        fc_col = "log2FoldChange" if "log2FoldChange" in df.columns else "logfoldchanges"

        if padj_col not in df.columns or fc_col not in df.columns:
            ax.set_visible(False)
            continue

        df["neg_log10_padj"] = -np.log10(df[padj_col].clip(lower=1e-300))
        df["significant"] = (df[padj_col] < 0.05) & (abs(df[fc_col]) > 0.5)

        colors = df["significant"].map({True: "#E74C3C", False: "#BDC3C7"})
        ax.scatter(df[fc_col], df["neg_log10_padj"], c=colors, s=3, alpha=0.5)
        ax.axhline(-np.log10(0.05), color="grey", linestyle="--", linewidth=0.5)
        ax.axvline(-0.5, color="grey", linestyle="--", linewidth=0.5)
        ax.axvline(0.5, color="grey", linestyle="--", linewidth=0.5)
        ax.set_xlabel("log2 Fold Change")
        ax.set_ylabel("-log10(padj)")
        n_sig = df["significant"].sum()
        ax.set_title(f"{ct} ({n_sig} DEGs)")

    # Hide unused axes
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("Differential Expression per Cell Type", fontsize=14, y=1.02)
    fig.tight_layout()
    _save_plot(fig, output_dir, "de_volcano_plots")


def plot_deg_heatmap(de_results, output_dir="results", top_n=30):
    """Plot heatmap of top DEGs across cell types."""
    plt, sns = _setup_matplotlib()

    # Normalize DE DataFrames: ensure gene names are the index
    de_indexed = {}
    for ct, df in de_results.items():
        df = df.copy()
        if "gene" in df.columns and not isinstance(df.index[0], str):
            df = df.set_index("gene")
        de_indexed[ct] = df

    # Collect top DEGs per cell type
    all_genes = set()
    fc_data = {}
    for ct, df in de_indexed.items():
        padj_col = "padj" if "padj" in df.columns else "pvals_adj"
        fc_col = "log2FoldChange" if "log2FoldChange" in df.columns else "logfoldchanges"
        if padj_col not in df.columns or fc_col not in df.columns:
            continue

        sig = df[df[padj_col] < 0.05].nlargest(top_n // len(de_indexed) + 1,
                                                  fc_col, keep="first")
        all_genes.update(sig.index[:10])
        fc_data[ct] = df[fc_col]

    if not all_genes or not fc_data:
        return

    # Build matrix
    genes = sorted(all_genes)[:top_n]
    matrix = pd.DataFrame(index=genes, columns=list(fc_data.keys()), dtype=float)
    for ct, fc_series in fc_data.items():
        for gene in genes:
            if gene in fc_series.index:
                matrix.loc[gene, ct] = fc_series[gene]

    matrix = matrix.fillna(0).astype(float)

    fig, ax = plt.subplots(figsize=(max(8, len(fc_data) * 1.2), max(8, len(genes) * 0.3)))
    sns.heatmap(matrix, cmap="RdBu_r", center=0, ax=ax,
                xticklabels=True, yticklabels=True,
                cbar_kws={"label": "log2 Fold Change"})
    ax.set_title("Top DEGs Across Cell Types")
    ax.set_xlabel("Cell Type")
    ax.set_ylabel("Gene")
    fig.tight_layout()
    _save_plot(fig, output_dir, "deg_heatmap")


def plot_pathway_heatmap(pathway_results, output_dir="results"):
    """Plot pathway activity heatmap across cell types."""
    plt, sns = _setup_matplotlib()

    gsea_results = pathway_results.get("gsea_results", {})
    if not gsea_results:
        return

    # Collect NES values per pathway per cell type
    all_terms = set()
    nes_data = {}
    for ct, df in gsea_results.items():
        if df is None or df.empty:
            continue
        term_col = "Term" if "Term" in df.columns else "term"
        nes_col = "NES" if "NES" in df.columns else "nes"
        fdr_col = next((c for c in ["FDR q-val", "FDR", "fdr", "padj"] if c in df.columns), None)
        if fdr_col is None:
            continue

        if term_col not in df.columns or nes_col not in df.columns:
            continue

        sig = df[df[fdr_col] < 0.25] if fdr_col in df.columns else df.head(0)
        for _, row in sig.iterrows():
            all_terms.add(row[term_col])
        nes_data[ct] = {row[term_col]: row[nes_col] for _, row in df.iterrows()}

    if not all_terms:
        return

    # Build matrix — sort by max |NES| across cell types (most significant first)
    term_max_nes = {}
    for ct, nes_dict in nes_data.items():
        for term, nes in nes_dict.items():
            if term in all_terms:
                term_max_nes[term] = max(term_max_nes.get(term, 0), abs(nes))
    terms = sorted(all_terms, key=lambda t: term_max_nes.get(t, 0), reverse=True)[:30]
    matrix = pd.DataFrame(index=terms, columns=list(nes_data.keys()), dtype=float)
    for ct, nes_dict in nes_data.items():
        for term in terms:
            if term in nes_dict:
                matrix.loc[term, ct] = nes_dict[term]

    matrix = matrix.fillna(0).astype(float)

    fig, ax = plt.subplots(figsize=(max(8, len(nes_data) * 1.2),
                                     max(8, len(terms) * 0.35)))
    sns.heatmap(matrix, cmap="RdBu_r", center=0, ax=ax,
                xticklabels=True, yticklabels=True,
                cbar_kws={"label": "Normalized Enrichment Score (NES)"})
    ax.set_title("Pathway Enrichment Across Cell Types (GSEA)")
    ax.set_xlabel("Cell Type")
    fig.tight_layout()
    _save_plot(fig, output_dir, "pathway_heatmap")


def plot_lr_dotplot(lr_results, output_dir="results", top_n=30):
    """Plot dot plot of top ligand-receptor interactions."""
    plt, sns = _setup_matplotlib()

    interactions = lr_results.get("interactions")
    if interactions is None or interactions.empty:
        return

    # Get top interactions
    rank_col = None
    for col in ["consensus_rank", "magnitude_rank", "specificity_rank", "rank"]:
        if col in interactions.columns:
            rank_col = col
            break

    if rank_col:
        top = interactions.nsmallest(top_n, rank_col)
    else:
        top = interactions.head(top_n)

    ligand_col = None
    for col in ["ligand", "ligand_complex"]:
        if col in top.columns:
            ligand_col = col
            break
    receptor_col = None
    for col in ["receptor", "receptor_complex"]:
        if col in top.columns:
            receptor_col = col
            break
    source_col = None
    for col in ["source", "sender", "cell_type_1"]:
        if col in top.columns:
            source_col = col
            break
    target_col = None
    for col in ["target", "receiver", "cell_type_2"]:
        if col in top.columns:
            target_col = col
            break

    if ligand_col is None or receptor_col is None:
        return

    # Create interaction labels
    top = top.copy()
    top["interaction"] = top[ligand_col].astype(str) + " - " + top[receptor_col].astype(str)
    if source_col and target_col:
        top["cell_pair"] = top[source_col].astype(str) + " -> " + top[target_col].astype(str)
    else:
        top["cell_pair"] = "Unknown"

    fig, ax = plt.subplots(figsize=(10, max(6, len(top) * 0.35)))

    unique_pairs = top["cell_pair"].unique()
    colors = sns.color_palette("husl", len(unique_pairs))
    color_map = dict(zip(unique_pairs, colors))

    y_positions = range(len(top))
    interaction_labels = top["interaction"].tolist()
    pair_colors = [color_map[p] for p in top["cell_pair"]]

    ax.scatter(
        range(len(top)),
        range(len(top)),
        c=pair_colors,
        s=100, alpha=0.8, zorder=3,
    )
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(interaction_labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Rank")
    ax.set_xticks(range(len(top)))
    ax.set_xticklabels(range(1, len(top) + 1), fontsize=7)
    ax.set_title(f"Top {len(top)} Ligand-Receptor Interactions")

    # Legend for cell pairs
    from matplotlib.lines import Line2D
    legend_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=color_map[p],
               markersize=8, label=p)
        for p in unique_pairs[:10]  # Limit legend entries
    ]
    if legend_handles:
        ax.legend(handles=legend_handles, loc="lower right", fontsize=7,
                  title="Cell Pair", title_fontsize=8)

    fig.tight_layout()
    _save_plot(fig, output_dir, "lr_dotplot")


def plot_convergence_heatmap(scores_df, output_dir="results", top_n=30):
    """Plot multi-omics convergence heatmap for top targets."""
    plt, sns = _setup_matplotlib()

    top = scores_df.head(top_n).copy()
    if top.empty:
        return

    # Build evidence matrix
    evidence_cols = ["de_score", "pathway_score", "lr_score",
                     "specificity_score", "genetic_score", "druggability_score"]
    col_labels = ["DE", "Pathway", "L-R", "Specificity", "Genetic", "Druggability"]

    available_cols = [c for c in evidence_cols if c in top.columns]
    available_labels = [col_labels[evidence_cols.index(c)] for c in available_cols]

    matrix = top.set_index("gene")[available_cols].astype(float)
    matrix.columns = available_labels

    fig, ax = plt.subplots(figsize=(8, max(6, len(top) * 0.35)))

    # Annotate convergence
    cmap = sns.color_palette("YlOrRd", as_cmap=True)
    sns.heatmap(matrix, cmap=cmap, vmin=0, vmax=1, ax=ax,
                xticklabels=True, yticklabels=True, annot=True, fmt=".2f",
                cbar_kws={"label": "Evidence Score"}, linewidths=0.5)

    # Mark convergent targets
    for i, (_, row) in enumerate(top.iterrows()):
        if row.get("has_convergence", False):
            ax.text(len(available_cols) + 0.3, i + 0.5, "\u2605",
                    fontsize=12, ha="center", va="center", color="#2ECC71")

    ax.set_title("Multi-Omics Target Evidence (\u2605 = convergent genetic + transcriptomic)")
    ax.set_xlabel("Evidence Type")
    ax.set_ylabel("Gene Target")
    fig.tight_layout()
    _save_plot(fig, output_dir, "convergence_heatmap")


def plot_target_ranking(scores_df, output_dir="results", top_n=25):
    """Plot horizontal bar chart of target composite scores."""
    plt, sns = _setup_matplotlib()

    top = scores_df.head(top_n).copy()
    if top.empty:
        return

    fig, ax = plt.subplots(figsize=(10, max(6, len(top) * 0.35)))

    colors = top["priority_tier"].map({
        "HIGH": "#E74C3C",
        "MEDIUM": "#F39C12",
        "LOW": "#95A5A6",
    })

    bars = ax.barh(range(len(top)), top["composite_score"], color=colors, alpha=0.8)

    # Labels
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(top["gene"])
    ax.invert_yaxis()
    ax.set_xlabel("Composite Score")
    ax.set_title("Drug Target Ranking (Multi-Omics Composite Score)")

    # Add convergence markers
    for i, (_, row) in enumerate(top.iterrows()):
        if row.get("has_convergence", False):
            ax.text(row["composite_score"] + 0.01, i, "\u2605",
                    fontsize=10, va="center", color="#2ECC71")

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#E74C3C", alpha=0.8, label="HIGH priority"),
        Patch(facecolor="#F39C12", alpha=0.8, label="MEDIUM priority"),
        Patch(facecolor="#95A5A6", alpha=0.8, label="LOW priority"),
    ]
    ax.legend(handles=legend_elements, loc="lower right")

    fig.tight_layout()
    _save_plot(fig, output_dir, "target_ranking")


def plot_celltype_composition(adata, output_dir="results"):
    """Stacked bar chart: % cells per cell type per condition."""
    plt, sns = _setup_matplotlib()

    ct_cond = adata.obs.groupby(["condition", "cell_type"]).size().unstack(fill_value=0)
    ct_pct = ct_cond.div(ct_cond.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(figsize=(12, 6))
    ct_pct.T.plot(kind="bar", stacked=False, ax=ax, width=0.7)
    ax.set_ylabel("% of cells")
    ax.set_xlabel("Cell Type")
    ax.set_title("Cell Type Composition by Condition")
    ax.legend(title="Condition", bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    _save_plot(fig, output_dir, "celltype_composition")


def plot_marker_dotplot(adata, de_results, output_dir="results", top_n=5):
    """Dot plot: top DE genes per cell type (expression + % expressing)."""
    plt, sns = _setup_matplotlib()
    import scanpy as sc

    # Normalize DE DataFrames and get top genes per cell type
    top_genes = {}
    for ct, df in de_results.items():
        df_work = df.copy()
        if "gene" in df_work.columns and not isinstance(df_work.index[0], str):
            df_work = df_work.set_index("gene")
        padj_col = "padj" if "padj" in df_work.columns else "pvals_adj"
        fc_col = "log2FoldChange" if "log2FoldChange" in df_work.columns else "logfoldchanges"
        if padj_col not in df_work.columns or fc_col not in df_work.columns:
            continue
        sig = df_work[df_work[padj_col] < 0.05].nlargest(top_n, fc_col)
        if len(sig) > 0:
            top_genes[ct] = sig.index.tolist()

    if not top_genes:
        return

    # Flatten to unique gene list
    all_markers = []
    for ct in sorted(top_genes.keys()):
        for g in top_genes[ct]:
            if g not in all_markers:
                all_markers.append(g)

    if len(all_markers) > 50:
        all_markers = all_markers[:50]

    try:
        sc.pl.dotplot(adata, var_names=all_markers, groupby="cell_type",
                      save=False, show=False)
        # scanpy dotplot saves via its own mechanism; save our own version
        fig = plt.gcf()
        fig.set_size_inches(max(10, len(all_markers) * 0.3), max(6, len(top_genes) * 0.5))
        _save_plot(fig, output_dir, "marker_dotplot")
    except Exception as e:
        print(f"  WARNING: scanpy dotplot failed: {e}. Skipping.", file=sys.stderr)


def plot_genetic_manhattan(genetic_results, output_dir="results"):
    """Manhattan-style plot: -log10(p) on y-axis, effect size as dot size."""
    plt, sns = _setup_matplotlib()

    l2g_df = genetic_results.get("l2g_scores")
    if l2g_df is None or l2g_df.empty:
        return

    # Filter to rows with p-values
    if "pvalue" not in l2g_df.columns:
        # Fall back to L2G score plot if no p-values available
        top = l2g_df.drop_duplicates("gene").nlargest(20, "l2g_score")
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.barh(range(len(top)), top["l2g_score"], color="#E74C3C", alpha=0.8)
        ax.set_yticks(range(len(top)))
        ax.set_yticklabels(top["gene"])
        ax.invert_yaxis()
        ax.set_xlabel("L2G Score (disease-specific)")
        ax.set_title("Genetic Evidence (Open Targets L2G)")
        fig.tight_layout()
        _save_plot(fig, output_dir, "genetic_evidence")
        return

    plot_df = l2g_df[l2g_df["pvalue"].notna() & (l2g_df["pvalue"] > 0)].copy()
    if plot_df.empty:
        return

    # Take best p-value per gene
    plot_df["neg_log10_p"] = -np.log10(plot_df["pvalue"].clip(lower=1e-300))
    best = plot_df.loc[plot_df.groupby("gene")["neg_log10_p"].idxmax()]
    best = best.nlargest(30, "neg_log10_p")

    fig, ax = plt.subplots(figsize=(10, 8))

    # Dot size from effect size (beta or odds ratio)
    sizes = 80
    if "beta" in best.columns:
        beta_vals = best["beta"].abs().fillna(0)
        if beta_vals.max() > 0:
            sizes = 30 + 150 * (beta_vals / beta_vals.max())
    elif "odds_ratio" in best.columns:
        or_vals = best["odds_ratio"].fillna(1).apply(lambda x: abs(np.log2(max(x, 0.01))))
        if or_vals.max() > 0:
            sizes = 30 + 150 * (or_vals / or_vals.max())

    # Color by datasource
    color_map = {"gwas_credible_sets": "#E74C3C", "eva": "#F39C12", "gene_burden": "#3498DB"}
    colors = best.get("datasource_id", pd.Series("gwas_credible_sets")).map(
        lambda x: color_map.get(x, "#95A5A6"))

    ax.scatter(range(len(best)), best["neg_log10_p"], s=sizes, c=colors, alpha=0.8, zorder=3)
    ax.set_xticks(range(len(best)))
    ax.set_xticklabels(best["gene"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("-log10(p-value)")
    ax.set_title("Genetic Evidence: GWAS/ClinVar P-values for SSc")
    ax.axhline(-np.log10(5e-8), color="red", linestyle="--", linewidth=0.8, label="Genome-wide (5e-8)")
    ax.axhline(-np.log10(1e-5), color="orange", linestyle="--", linewidth=0.8, label="Suggestive (1e-5)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    _save_plot(fig, output_dir, "genetic_evidence")


def plot_gwas_gene_expression(gwas_context_df, output_dir="results"):
    """Dot plot: GWAS genes mapped to cell types with DE status.

    Shows the top SSc GWAS genes, where they're expressed in the skin,
    and whether they're differentially expressed — bridging the
    immune-fibroblast disconnect.
    """
    plt, sns = _setup_matplotlib()

    if gwas_context_df is None or gwas_context_df.empty:
        return

    df = gwas_context_df.sort_values("genetic_score", ascending=True).copy()

    fig, ax = plt.subplots(figsize=(10, max(6, len(df) * 0.4)))

    # Color by DE status
    colors = df["is_de"].map({True: "#E74C3C", False: "#95A5A6"})

    # Size by expression level
    sizes = 30 + 120 * (df["mean_expression"] / max(df["mean_expression"].max(), 0.01))

    bars = ax.barh(range(len(df)), df["genetic_score"], color=colors, alpha=0.8)

    # Add cell type labels
    for i, (_, row) in enumerate(df.iterrows()):
        label = f"{row['top_celltype']}"
        if row["is_de"]:
            label += f" (LFC={row['de_log2fc']:+.1f})"
        ax.text(row["genetic_score"] + 0.01, i, label, va="center", fontsize=7)

    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df["gene"])
    ax.set_xlabel("GWAS Genetic Association Score (Open Targets)")
    ax.set_title("SSc GWAS Genes: Expression in Skin Cell Types")

    from matplotlib.patches import Patch
    legend = [
        Patch(facecolor="#E74C3C", alpha=0.8, label="DE in SSc (padj<0.05)"),
        Patch(facecolor="#95A5A6", alpha=0.8, label="Not DE"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=8)

    fig.tight_layout()
    _save_plot(fig, output_dir, "gwas_gene_landscape")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def generate_all_plots(adata, de_results, pathway_results, lr_results,
                       genetic_results, scores_df, output_dir="results",
                       gwas_context_df=None):
    """Generate all publication-quality visualizations.

    Args:
        adata: Annotated AnnData object
        de_results: Dict of {celltype: DE DataFrame}
        pathway_results: Dict with gsea_results, pathway_activity
        lr_results: Dict with interactions, disease_specific
        genetic_results: Dict from collect_genetic_evidence()
        scores_df: DataFrame from score_targets()
        output_dir: Output directory for plots

    Returns:
        List of generated plot paths
    """
    os.makedirs(output_dir, exist_ok=True)
    plots_generated = []
    n_plots = 0

    print("Generating visualizations...")

    plot_specs = [
        ("UMAP overview", plot_umap_overview, [adata, output_dir]),
        ("Cell type composition", plot_celltype_composition, [adata, output_dir]),
        ("Volcano plots", plot_de_volcanos, [de_results, output_dir]),
        ("DEG heatmap", plot_deg_heatmap, [de_results, output_dir]),
        ("Marker dot plot", plot_marker_dotplot, [adata, de_results, output_dir]),
        ("Pathway heatmap", plot_pathway_heatmap, [pathway_results, output_dir]),
        ("L-R dot plot", plot_lr_dotplot, [lr_results, output_dir]),
        ("Genetic evidence", plot_genetic_manhattan, [genetic_results, output_dir]),
        ("GWAS gene landscape", plot_gwas_gene_expression, [gwas_context_df, output_dir]),
        ("Convergence heatmap", plot_convergence_heatmap, [scores_df, output_dir]),
        ("Target ranking", plot_target_ranking, [scores_df, output_dir]),
    ]

    for name, func, args in plot_specs:
        try:
            func(*args)
            n_plots += 1
            plots_generated.append(name)
            print(f"  [{n_plots}] {name}")
        except Exception as e:
            print(f"  WARNING: {name} failed: {e}", file=sys.stderr)

    print(f"\u2713 All plots generated successfully! {n_plots} visualizations saved")
    return plots_generated


if __name__ == "__main__":
    print("Visualization generation requires pre-computed analysis results.")
    print("Use via Python import: from generate_visualizations import generate_all_plots")
