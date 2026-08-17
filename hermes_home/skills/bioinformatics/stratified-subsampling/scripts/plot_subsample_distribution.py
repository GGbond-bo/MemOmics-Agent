"""Generate 3-panel subsample distribution figure for rail_review(post) compliance.

Usage: Called immediately after any subsample operation to satisfy figure_count>=1 requirement.
Output: figures/subsample_distribution.png (3-panel: age + celltype bar + proportion pie)
"""

import scanpy as sc
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import numpy as np
import os

def plot_subsample_distribution(
    adata,
    outdir: str,
    age_col: str = "age",
    ct_col: str = "celltype",
    age_threshold: int = 60,
    young_color: str = "#4CAF50",
    aged_color: str = "#FF5252",
    dpi: int = 150
):
    """Generate 3-panel subsample distribution figure.
    
    Panel 1: Age distribution (colored by young/aged split)
    Panel 2: Cell type horizontal bar chart with counts
    Panel 3: Cell type proportion pie chart (types >1%)
    """
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    
    # Panel 1: Age distribution (Young vs Aged coloring)
    age_order = sorted(adata.obs[age_col].unique())
    age_counts = adata.obs[age_col].value_counts().reindex(age_order)
    colors_age = [young_color if int(a) < age_threshold else aged_color for a in age_order]
    axes[0].bar(range(len(age_counts)), age_counts.values, color=colors_age)
    axes[0].set_xticks(range(len(age_counts)))
    axes[0].set_xticklabels(age_order, rotation=45, ha='right', fontsize=8)
    axes[0].set_title(f'Age Distribution\n({young_color}=Young <{age_threshold}, {aged_color}=Aged)', fontsize=12)
    axes[0].set_ylabel('Cell Count')
    axes[0].set_xlabel('Age')
    
    # Panel 2: Cell type horizontal bar chart
    ct_counts = adata.obs[ct_col].value_counts()
    colors_ct = plt.cm.tab20(np.linspace(0, 1, len(ct_counts)))
    axes[1].barh(range(len(ct_counts)), ct_counts.values, color=colors_ct)
    axes[1].set_yticks(range(len(ct_counts)))
    axes[1].set_yticklabels(ct_counts.index, fontsize=9)
    axes[1].set_title('Cell Type Distribution', fontsize=12)
    axes[1].set_xlabel('Cell Count')
    for i, v in enumerate(ct_counts.values):
        axes[1].text(v + max(ct_counts.values)*0.02, i, str(v), va='center', fontsize=8)
    
    # Panel 3: Proportion pie (merge <1% types into "Others")
    mask = ct_counts / ct_counts.sum() > 0.01
    pie_data = ct_counts[mask].copy()
    others = ct_counts[~mask].sum()
    if others > 0:
        pie_data['Others (<1%)'] = others
    axes[2].pie(pie_data.values, labels=pie_data.index, autopct='%1.1f%%',
                colors=plt.cm.Set3(np.linspace(0, 1, len(pie_data))),
                textprops={'fontsize': 8})
    axes[2].set_title('Cell Type Proportions', fontsize=12)
    
    plt.suptitle(f'Subset — {adata.n_obs} cells × {adata.n_vars} genes',
                 fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    fig_dir = os.path.join(outdir, 'figures')
    os.makedirs(fig_dir, exist_ok=True)
    figpath = os.path.join(fig_dir, 'subsample_distribution.png')
    plt.savefig(figpath, dpi=dpi, bbox_inches='tight')
    plt.close()
    print(f"✅ Distribution figure saved: {figpath}")
    return figpath
