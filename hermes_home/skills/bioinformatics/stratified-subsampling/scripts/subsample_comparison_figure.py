"""
Subsampling comparison figure: 3-panel visualization for stratified subsampling QC.
Panel A: Celltype distribution bar chart (full vs subset, log scale)
Panel B: Age/group distribution bar chart (full vs subset)
Panel C: Proportionality scatter plot with diagonal reference line

Usage: modify the data paths and column names below, then run.
"""
import scanpy as sc
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

# === CONFIG ===
FULL_PATH = "path/to/full.h5ad"
SUBSET_PATH = "path/to/subset.h5ad"
OUTPUT_PATH = "figures/subsampling_comparison.png"
CELLTYPE_COL = "celltype"
GROUP_COL = "age"       # or "sample_id"
SEED = 42

# === Load ===
adata_full = sc.read_h5ad(FULL_PATH)
adata_sub = sc.read_h5ad(SUBSET_PATH)

np.random.seed(SEED)
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# --- Panel A: Celltype composition (log scale) ---
ax = axes[0]
cts = adata_full.obs[CELLTYPE_COL].value_counts()
cts_sub = adata_sub.obs[CELLTYPE_COL].value_counts()
order = cts.index
cts_sub = cts_sub.reindex(order, fill_value=0)

x = np.arange(len(order))
w = 0.35
ax.bar(x - w/2, cts.values, w, label=f'Full ({adata_full.n_obs:,})', color='#3B82F6', alpha=0.8)
ax.bar(x + w/2, cts_sub.values, w, label=f'Subset ({adata_sub.n_obs:,})', color='#EF4444', alpha=0.8)
ax.set_xticks(x)
ax.set_xticklabels(order, rotation=45, ha='right', fontsize=9)
ax.set_ylabel('Cell count', fontsize=11)
ax.set_title('A) Celltype distribution', fontsize=13, fontweight='bold')
ax.legend(fontsize=9)
ax.set_yscale('log')
ax.grid(axis='y', alpha=0.3)

# --- Panel B: Group distribution ---
ax = axes[1]
grp_full = adata_full.obs[GROUP_COL].value_counts().sort_index()
grp_sub = adata_sub.obs[GROUP_COL].value_counts().sort_index()
all_groups = sorted(set(grp_full.index) | set(grp_sub.index))
grp_full = grp_full.reindex(all_groups, fill_value=0)
grp_sub = grp_sub.reindex(all_groups, fill_value=0)

x = np.arange(len(all_groups))
ax.bar(x - w/2, grp_full.values, w, label='Full', color='#3B82F6', alpha=0.8)
ax.bar(x + w/2, grp_sub.values, w, label='Subset', color='#EF4444', alpha=0.8)
ax.set_xticks(x)
ax.set_xticklabels(all_groups, fontsize=9)
ax.set_xlabel(GROUP_COL, fontsize=11)
ax.set_ylabel('Cell count', fontsize=11)
ax.set_title(f'B) {GROUP_COL} distribution', fontsize=13, fontweight='bold')
ax.legend(fontsize=9)
ax.grid(axis='y', alpha=0.3)

# --- Panel C: Proportionality check ---
ax = axes[2]
full_pct = cts / cts.sum() * 100
sub_pct = cts_sub / cts_sub.sum() * 100
ax.scatter(full_pct, sub_pct, s=60, c='#8B5CF6', edgecolors='black', linewidth=0.5)
for ct in order:
    ax.annotate(ct, (full_pct[ct], sub_pct[ct]), fontsize=7,
                textcoords="offset points", xytext=(5, 5), ha='left')
lims = [-0.5, max(full_pct.max(), sub_pct.max()) + 5]
ax.plot(lims, lims, 'k--', alpha=0.3, linewidth=1)
ax.set_xlabel('Full dataset (%)', fontsize=11)
ax.set_ylabel('Subset (%)', fontsize=11)
ax.set_title('C) Proportionality check', fontsize=13, fontweight='bold')
ax.grid(alpha=0.3)

plt.tight_layout()
import os
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
fig.savefig(OUTPUT_PATH, dpi=150, bbox_inches='tight')
plt.close()
print(f"Figure saved → {OUTPUT_PATH}")
