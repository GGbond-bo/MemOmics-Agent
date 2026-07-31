---
name: scrna-cns-figure-design
category: bioinformatics
description: >-
  CNS-level single-cell RNA-seq figure architecture and implementation.
  Covers condition-resolved UMAP with density contours, continuum scoring,
  multi-condition perturbation vector fields, NMF gene programs, and the
  anti-pattern of forcing hierarchical nesting on continuum cell states.
  Use when user is designing main figures (F2-F7) for a multi-condition
  single-cell paper targeting Nature/Science/Cell.
trigger:
  when:
    - User asks about figure design/architecture for single-cell paper
    - User says "F2"/"Figure 2" in context of scRNA-seq manuscript
    - User wants condition-resolved visualization beyond basic UMAP
    - User corrects hierarchical clustering or shallow annotation-only figures
---

# scRNA-seq CNS Figure Design

## Anti-Patterns That Kill CNS Figures (2026 standard)

| Don't | Why | Do Instead |
|-------|-----|------------|
| Force hierarchical nesting of continuum cell states | Transition ≠ container. Reviewers reject artificial layers. | "Continuous transcriptional landscape" language |
| Single UMAP colored by cluster as F2 | 2019-level catalog, not a 2026 argument | Split UMAP by condition with density contours |
| Bar chart of cluster proportions as sole quantitative panel | Discrete; hides distribution shifts within clusters | Split-violin of continuous scores |
| GO/KEGG for novel subtypes with <20 markers | Generic terms, non-discriminatory | Gene set scoring matrix + NMF programs |
| hdWGCNA for terminally differentiated cells | Co-expression networks often flat; memory-intensive | NMF (gene program decomposition) |

## The F1-F7 Architecture Pattern

| Figure | Content | Unique value |
|--------|---------|-------------|
| F1 | Pipeline, clinical data, L1+L2 multi-omics UMAP, proportions | Atlas landscape |
| F2 | Deep dive into ONE cell type (multi-dimensional, multi-condition, quantitative) | The "stop and look" figure |
| F3 | Other major cell types | Completeness |
| F4 | DEG across all subtypes × all conditions | Gene-level validation |
| F5 | Cell-cell communication | Intercellular logic |
| F6 | GRN | Transcriptional drivers |
| F7 | Exercise/individual response | Translational axis |

## F2 Deep-Dive Panel Checklist

Each panel must answer a non-trivial question:

| Panel | Question Answered | Implementation |
|-------|------------------|----------------|
| 2a | How does each condition reshape the transcriptional space? | Split UMAP + density contours per condition |
| 2b | Does fiber type identity blur or shift with condition? | Split-violin of continuum score (e.g. fast-slow index) |
| 2c | Are novel populations real? | Evidence chain: UMAP highlight + marker violin + literature + proportion |
| 2d | Which populations are most sensitive to aging? To exercise? | PCA perturbation vector field + reversibility index |
| 2e | What gene programs drive condition differences? | NMF decomposition → program × cluster heatmap + program × condition line plot |

## Condition-Resolved UMAP with Density Contours

Recipe for Python/scanpy:

```python
from scipy.stats import gaussian_kde
import numpy as np

def plot_condition_umap(adata, condition_col, umap_key='X_umap', conditions=None):
    """Split UMAP by condition with density contours."""
    umap_coords = adata.obsm[umap_key]
    if conditions is None:
        conditions = sorted(adata.obs[condition_col].unique())
    
    fig, axes = plt.subplots(1, len(conditions), figsize=(6*len(conditions), 5.5),
                             sharex=True, sharey=True)
    
    for ax, cond in zip(axes, conditions):
        mask = adata.obs[condition_col] == cond
        coords = umap_coords[mask]
        
        # Background: all cells in light gray
        ax.scatter(umap_coords[:,0], umap_coords[:,1],
                   c='#e0e0e0', s=0.3, alpha=0.4, rasterized=True)
        # Foreground: this condition
        ax.scatter(coords[:,0], coords[:,1],
                   c=color, s=1.5, alpha=0.7, rasterized=True)
        
        # Density contours at 25%, 50%, 75% max
        if coords.shape[0] > 30:
            k = gaussian_kde(np.vstack([coords[:,0], coords[:,1]]))
            xi = np.linspace(coords[:,0].min()-0.5, coords[:,0].max()+0.5, 80)
            yi = np.linspace(coords[:,1].min()-0.5, coords[:,1].max()+0.5, 80)
            Xi, Yi = np.meshgrid(xi, yi)
            Zi = k(np.vstack([Xi.ravel(), Yi.ravel()])).reshape(Xi.shape)
            levels = [np.max(Zi)*p for p in [0.25, 0.50, 0.75]]
            ax.contour(Xi, Yi, Zi, levels=levels, colors=color,
                      linewidths=[0.6, 0.9, 1.3], alpha=0.9)
        
        ax.set_title(f'{cond}\n({coords.shape[0]:,} cells)')
        ax.set_xticks([]); ax.set_yticks([])
    
    return fig
```

## Multi-Group Function Score Mini-Heatmaps (Scheme A)

When per-function differences are subtle across clusters, use independent
mini-heatmaps instead of a single global-Z-score heatmap:

```
[Module1]  [Module2]  [Module3]  [Module4]  [Module5]
 10cl×5c    10cl×5c    10cl×5c    10cl×5c    10cl×5c
```

Each module gets its own color scale → subtle condition differences visible.

## Core Principle

> Every panel must answer a question that cannot be answered by a simpler display.
> If a bar chart would convey the same information, the panel is redundant.
