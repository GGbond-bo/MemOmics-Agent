#!/usr/bin/env python3
"""
GO enrichment heatmap — reference-figure style (matplotlib)
Template from 2026-09 session: user wanted CNS-level heatmap matching a specific reference image.

Key design choices (verified working):
- Row labels on RIGHT side, two-line: "Pathway name\n(key genes)"
- Warm color gradient: gray → light blue → medium blue → orange → dark red
- Compact near-square aspect ratio (10×12 for ~56 terms × 17 clusters)
- Value annotations in cells (white text for high values)
- Thin grid lines (#CCCCCC)
- Horizontal colorbar at bottom

Input: Excel with columns Cluster | Path | Genes | Log(q-value)
Output: SVG + PDF + PNG (300 DPI)
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from pathlib import Path


def make_go_heatmap(
    xlsx_path: str,
    sheet_name: str = "Hoja1",
    output_dir: str = "figures",
    output_prefix: str = "GO_heatmap",
    max_pathway_chars: int = 35,
    max_genes_chars: int = 28,
    vmax: float = 50.0,
):
    # ── Read data ──
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
    
    # Filter header rows (Cluster == "Cluster" or Path is NaN)
    df = df[df['Path'].notna() & (df['Cluster'] != 'Cluster')]
    df['Log(q-value)'] = pd.to_numeric(df['Log(q-value)'], errors='coerce')
    df = df[df['Log(q-value)'].notna()]
    
    # Deduplicate terms (keep first occurrence)
    df_dedup = df.drop_duplicates(subset='Path', keep='first')
    paths = df_dedup['Path'].tolist()
    genes_list = df_dedup['Genes'].fillna('').tolist()
    clusters = df['Cluster'].unique().tolist()
    
    # ── Build matrix ──
    n_paths = len(paths)
    n_clusters = len(clusters)
    mat = np.zeros((n_paths, n_clusters))
    
    for i, path in enumerate(paths):
        for j, clu in enumerate(clusters):
            sub = df[(df['Cluster'] == clu) & (df['Path'] == path)]
            if len(sub) > 0:
                mat[i, j] = sub['Log(q-value)'].values[0]
    
    mat_cap = np.clip(mat, 0, vmax)
    
    # ── Row labels (two-line, truncated) ──
    def truncate(s, maxlen):
        s = str(s).strip()
        return s[:maxlen-3] + "..." if len(s) > maxlen else s
    
    short_paths = [truncate(p, max_pathway_chars) for p in paths]
    short_genes = [truncate(str(g), max_genes_chars) for g in genes_list]
    
    # ── Color scheme (warm gradient, reference-figure style) ──
    colors_ref = ["#E8E8E8", "#A8C8E0", "#6090B8", "#D6604D", "#B2182B"]
    cmap = mcolors.LinearSegmentedColormap.from_list("ref_style", colors_ref)
    norm = mcolors.Normalize(vmin=0, vmax=vmax)
    
    # ── Plot (compact, near-square) ──
    fig, ax = plt.subplots(figsize=(10, 12))
    im = ax.imshow(mat_cap, aspect='auto', cmap=cmap, norm=norm, interpolation='nearest')
    
    # Column labels (top, rotated)
    ax.set_xticks(range(n_clusters))
    ax.set_xticklabels(clusters, rotation=45, ha='left', fontsize=7, fontweight='normal')
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position('top')
    
    # Hide left y-axis
    ax.set_yticks([])
    
    # Value annotations in cells
    for i in range(n_paths):
        for j in range(n_clusters):
            val = mat[i, j]
            if val > 0:
                color = 'white' if val > 30 else '#333333'
                fontsize = 5 if val < 10 else 5.5
                ax.text(j, i, f"{val:.0f}", ha='center', va='center',
                        fontsize=fontsize, color=color)
    
    # Thin grid lines
    for i in range(n_paths + 1):
        ax.axhline(i - 0.5, color='#CCCCCC', linewidth=0.5)
    for j in range(n_clusters + 1):
        ax.axvline(j - 0.5, color='#CCCCCC', linewidth=0.5)
    
    # Border
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
        spine.set_color('#666666')
    
    # ── Right-side row labels (two-line) ──
    right_ax = ax.twinx()
    right_ax.set_ylim(ax.get_ylim())
    right_ax.set_yticks(range(n_paths))
    right_ax.set_yticklabels(
        [f"{sp}\n({sg})" for sp, sg in zip(short_paths, short_genes)],
        fontsize=5.5, va='center'
    )
    right_ax.tick_params(axis='y', which='both', length=0)
    for spine in right_ax.spines.values():
        spine.set_visible(False)
    
    # ── Horizontal colorbar at bottom ──
    cbar_ax = fig.add_axes([0.15, 0.02, 0.15, 0.015])
    cbar = fig.colorbar(im, cax=cbar_ax, orientation='horizontal')
    cbar.set_label('-log₁₀(q-value)', fontsize=9, labelpad=8)
    cbar.set_ticks([0, 10, 20, 30, 40, 50])
    cbar.set_ticklabels(['0', '10', '20', '30', '40', '50+'])
    cbar.ax.tick_params(labelsize=7)
    
    plt.subplots_adjust(left=0.02, right=0.42, top=0.88, bottom=0.06)
    
    # ── Export ──
    outdir = Path(output_dir)
    outdir.mkdir(exist_ok=True, parents=True)
    
    for ext in ['svg', 'pdf', 'png']:
        fig.savefig(outdir / f"{output_prefix}.{ext}", dpi=300,
                    bbox_inches='tight', facecolor='white')
    
    print(f"Done! {n_paths} terms x {n_clusters} clusters")
    print(f"Output: {outdir}/{output_prefix}.{{svg,pdf,png}}")
    return fig


if __name__ == "__main__":
    import sys
    xlsx = sys.argv[1] if len(sys.argv) > 1 else "input.xlsx"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "figures"
    make_go_heatmap(xlsx, output_dir=outdir)
