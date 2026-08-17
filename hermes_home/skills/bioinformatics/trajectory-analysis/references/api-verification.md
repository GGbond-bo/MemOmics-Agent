# scTour v1.0.0 API Verification

> Source: GitHub `LiQian-XC/sctour` — verified 2025-07-05

## Package Structure

`sctour/__init__.py` exports only three submodules:
- `sct.train` — Trainer class + model training
- `sct.predict` — cross-dataset prediction
- `sct.vf` — vector field visualization

**There are NO module-level convenience functions like `sct.get_pseudotime()`, `sct.get_latent_representation()`, or `sct.get_vector_field()`.**

## Trainer Methods (the actual API)

| Method | Signature | Returns |
|--------|-----------|---------|
| `get_time()` | `self -> np.ndarray` | Pseudotime per cell. Requires `adata.obs['n_genes_by_counts']`. |
| `get_latentsp()` | `self, alpha_z=0.5, alpha_predz=0.5, step_size=None, step_wise=False, batch_size=None -> tuple` | 3-tuple: `(mix_zs, zs, pred_zs)` — weighted combined, encoder-derived, ODE-derived |
| `get_vector_field()` | `self, T: np.ndarray, Z: np.ndarray -> np.ndarray` | Vector field in latent space. Takes pseudotime + latent representation. |

## Predict Module

| Function | Purpose |
|----------|---------|
| `sct.predict.load_model(path)` | Load saved model |
| `sct.predict.predict_time(adata)` | Predict pseudotime for query data |
| `sct.predict.predict_latentsp(adata)` | Predict latent space for query data |
| `sct.predict.predict_vector_field(adata)` | Predict vector field for query data |
| `sct.predict.predict_ltsp_from_time(t)` | Predict latent space for unobserved timepoints |

## Vector Field Visualization

| Function | Purpose |
|----------|---------|
| `sct.vf.plot_vector_field(adata, zs_key, vf_key, ...)` | Streamplot of vector field on UMAP |
| `sct.vf.vector_field_embedding(...)` | Embed vector field into 2D |
| `sct.vf.vector_field_embedding_grid(...)` | Grid-based vector field embedding |

## Common Mistake: Using Non-Existent Functions

```python
# ❌ WRONG — these functions do NOT exist in scTour v1.0.0:
sct.get_pseudotime(tnode, adata)
sct.get_latent_representation(tnode, adata)
sct.get_vector_field(tnode, adata)

# ✅ CORRECT — use Trainer methods:
adata.obs['pseudotime'] = tnode.get_time()
mix_zs, zs, pred_zs = tnode.get_latentsp(alpha_z=0.5, alpha_predz=0.5)
adata.obsm['X_VF'] = tnode.get_vector_field(adata.obs['pseudotime'].values, adata.obsm['X_TNODE'])
```

## Verification Method

When a package is not installed locally, verify API from GitHub source:

```bash
# Check __init__.py exports
curl -sL "https://api.github.com/repos/LiQian-XC/sctour/contents/sctour/__init__.py" \
  -H "Accept: application/vnd.github.v3.raw"

# Check Trainer methods
curl -sL "https://api.github.com/repos/LiQian-XC/sctour/contents/sctour/train.py" \
  -H "Accept: application/vnd.github.v3.raw" | grep "^    def "

# Check predict module
curl -sL "https://api.github.com/repos/LiQian-XC/sctour/contents/sctour/predict.py" \
  -H "Accept: application/vnd.github.v3.raw" | grep "^def "
```