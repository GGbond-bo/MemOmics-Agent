"""
CNS GO Enrichment Heatmap — Final Version (2026-09-07)
Pure red gradient (white → pink → red → dark red), 0-10 clip
Sparse-filtered: pathways in ≥2 clusters AND clusters with ≥4 pathways
Template from: go-enrichment-visualization skill
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize

plt.rcParams['font.family'] = 'Arial'

# ── Load data ──
df = pd.read_csv(r'DATA_PATH_HERE')  # columns: cluster, path_id, path, genes, logq, val, ngene

# ── Build pivot (rows=pathway, cols=cluster) ──
pv = df.pivot_table(index='path', columns='cluster', values='val', fill_value=0, aggfunc='max')
pv = pv.clip(upper=10)

# ── Gene mapping ──
gene_map = df.drop_duplicates('path').set_index('path')['genes'].to_dict()

# ── Sparse filtering ──
row_nz = (pv > 0).sum(axis=1)
col_nz = (pv > 0).sum(axis=0)
dense_paths = row_nz[row_nz >= 2].index
dense_cols = col_nz[col_nz >= 4].index
pv_filtered = pv.loc[dense_paths, dense_cols].copy()

# ── Order by density ──
row_order = row_nz[dense_paths].sort_values(ascending=False).index
col_order = col_nz[dense_cols].sort_values(ascending=False).index
pv_filtered = pv_filtered.loc[row_order, col_order]

print(f"Filtered: {pv_filtered.shape[0]} pathways × {pv_filtered.shape[1]} clusters")
print(f"Non-zero: {(pv_filtered > 0).sum().sum()}/{pv_filtered.size} = {(pv_filtered > 0).sum().sum()/pv_filtered.size*100:.1f}%")

# ── Pure red gradient (NO blue, NO gray) ──
colors_red = ['#FFFFFF', '#FFD4D4', '#FF8888', '#FF4444', '#CC0000', '#800000']
cmap = LinearSegmentedColormap.from_list('cns_pure_red', colors_red, N=256)
norm = Normalize(vmin=0, vmax=10)

# ── Plot ──
fig_w = max(8, pv_filtered.shape[1] * 0.6)
fig_h = max(6, pv_filtered.shape[0] * 0.45)
fig, ax = plt.subplots(figsize=(fig_w, fig_h))

im = ax.imshow(pv_filtered.values, cmap=cmap, aspect='auto', vmin=0, vmax=10, interpolation='nearest')

# X labels (clusters)
ax.set_xticks(range(len(pv_filtered.columns)))
ax.set_xticklabels(pv_filtered.columns, rotation=45, ha='right', fontsize=8)

# Y labels (pathways)
ax.set_yticks(range(len(pv_filtered.index)))
def shorten(s, max_len=50):
    return s if len(s) <= max_len else s[:max_len-3] + '...'
ax.set_yticklabels([shorten(p) for p in pv_filtered.index], fontsize=7)

# Gene annotations on right
for i, path in enumerate(pv_filtered.index):
    genes = gene_map.get(path, '')
    if genes:
        gene_list = genes.split(';')[:3]
        ax.text(pv_filtered.shape[1] + 0.5, i, f"({', '.join(gene_list)})",
                fontsize=6, ha='left', va='center', color='#333333')

ax.set_xlim(-0.5, pv_filtered.shape[1] - 0.5)
ax.set_ylim(-0.5, pv_filtered.shape[0] - 0.5)

# Grid (thin white)
for i in range(pv_filtered.shape[0] + 1):
    ax.axhline(i - 0.5, color='white', linewidth=0.5)
for j in range(pv_filtered.shape[1] + 1):
    ax.axvline(j - 0.5, color='white', linewidth=0.5)

# Colorbar
cbar = plt.colorbar(im, ax=ax, shrink=0.8, pad=0.15)
cbar.set_label('GO Enrichment Strength (0-10)', fontsize=9, fontweight='bold')
cbar.ax.tick_params(labelsize=8)

ax.set_title('GO Enrichment Heatmap', fontsize=12, fontweight='bold', pad=20)
plt.tight_layout()

# ── Export ──
fig.savefig('GO_heatmap.png', dpi=300, bbox_inches='tight')
fig.savefig('GO_heatmap.pdf', bbox_inches='tight')
fig.savefig('GO_heatmap.svg', bbox_inches='tight')
