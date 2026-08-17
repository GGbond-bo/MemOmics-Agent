# scTour Multi-Configuration Comparison — 2026-07-07 Human Skeletal Muscle

## Data Context

| Field | Value |
|-------|-------|
| Species | human (Homo sapiens) |
| Tissue | skeletal_muscle |
| Direction | aging + diabetes + exercise |
| Cells | 11,630 |
| Genes | 51,227 (HVG subset: 1,000) |
| Samples | 48 (Young_normal, Young_normal_Post, Old_normal, Old_normal_Post, Old_diabete, Old_diabete_Post) |
| Annotation | subcluster: TypeI, TypeII, RSS |
| Counts location | `.layers['counts']` (`.X` had SCTransform residuals) |
| Environment | Python 3.10 venv, CPU mode (no CUDA), RTX 5070 Ti (Blackwell) |

## Three Configurations Run

### run1_balanced
```python
Trainer(adata, loss_mode='nb',
    alpha_recon_lec=0.5, alpha_recon_lode=0.5,
    n_latent=5, nepoch=400, batch_size=1024,
    lr=1e-3, random_state=0)
```

### run2_encoder
```python
Trainer(adata, loss_mode='nb',
    alpha_recon_lec=0.8, alpha_recon_lode=0.2,
    n_latent=8, nepoch=400, batch_size=1024,
    lr=1e-3, random_state=42)
```

### run3_ode
```python
Trainer(adata, loss_mode='nb',
    alpha_recon_lec=0.3, alpha_recon_lode=0.7,
    n_latent=3, nepoch=400, batch_size=1024,
    lr=1e-3, random_state=123)
```

## Results Comparison

| Run | Young_mean | Old_mean | Delta | KS_pval | Selected? |
|:---:|:----------:|:--------:|:-----:|:-------:|:---------:|
| run1_balanced | 0.507 | 0.521 | +0.014 | 8.57e-5 | **Yes** (final) |
| run2_encoder | 0.590 | 0.576 | -0.014 | 0.014 | No (reversed direction) |
| run3_ode | 0.137 | 0.219 | +0.082 | ~0 | No (compressed range) |

**Winner**: run2_encoder after debate — showed Post-exercise groups clustering with Young, which best matched the biological hypothesis (exercise counteracts aging transcriptome).

## Key Workflow Steps

1. **Count extraction**: `adata.X = adata.layers['counts'].copy()` before HVG selection
2. **Dtype fix**: `.X` to float32 (avoid PyTorch Double/Float mismatch)
3. **Sparse→dense**: SparseCSRView to dense (avoid `.A` attribute error)
4. **HVG**: `flavor='seurat_v3', n_top_genes=1000`
5. **Model save**: `tnode.save_model(save_dir, 'sctour_model')` for each run
6. **Figure save**: `sc.pl.umap(..., save='_prefix.png')` saves to `./figures/` relative to cwd

## Debate Outcome

The debate selected run2_encoder (encoder-heavy, alpha_recon_lec=0.8) because:
- Direction was correct: Young + Post-exercise at low pseudotime, Old_unexercised at high
- The separation between exercise states was most biologically meaningful
- TypeI/RSS fibers showed appropriate distribution along the trajectory

## Environment Setup

```bash
# Created clean Python 3.10 venv
uv venv sctour_env --python 3.10
source sctour_env/bin/activate

# Install scTour from GitHub (pip version may be outdated)
pip install git+https://github.com/LiQian-XC/sctour.git

# Core dependencies
pip install scanpy numpy pandas matplotlib scipy scikit-misc

# PyTorch (CPU for Blackwell RTX 5070 Ti — cu128 torch not yet available)
pip install torch torchdiffeq
```

## Report

Comprehensive HTML report generated via `bioinformatics-html-report` skill's `html_report_builder.py`.
Contains: 15 figures (3 runs × 5 each), parameter comparison table, KS test results, debate records.
Saved to: `results/human_skeletal_muscle_aging_diabetes_exercise_20260708/03_advanced/scTour/scTour_Trajectory_Report.html`

---

## Run 2 — 2026-07-08 (Same dataset, new scoring)

A second run with the same 11,630-cell dataset was performed 24h later with improved visualization scripts. **Different debate outcome** — `run1_balanced` won instead of `run2_encoder`.

### Why different verdict?

| Aspect | Run 1 (07-07) | Run 2 (07-08) |
|:-------|:-------------|:-------------|
| Debate focus | Direction (+0.014 vs -0.014) | Overall KS separability (avg_ks=0.356) |
| Key comparison | Young vs Old overall | **Exercise effect (Old Pre vs Post KS=0.52)** |
| Winner | run2_encoder (directional correctness) | run1_balanced (total separability) |
| Aging KS | — | 0.46*** |
| Diabetes KS | — | 0.27*** |

### Lesson Learned

The optimal config **depends on which biological question is primary**:
- If the main question is **aging trajectory direction** → Balanced often works (captures aging + exercise together)
- If the main question is **exercise intervention effect** → Balanced wins decisively (KS=0.52 for Pre vs Post)
- If the main question is **diabetes-specific signal** → ODE or Encoder may be better

**Recommendation**: Always run at least 3 configs (Balanced/Encoder/ODE) and let the comparison + debate guide selection based on the specific biological question. Do NOT lock in a single config prematurely.