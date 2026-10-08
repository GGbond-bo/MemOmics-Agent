# Common Patterns

Example workflows for different use cases.

## Pattern 1: SSc Skin Fibroblast Discovery (Demo)

The primary demo use case. SSc skin biopsies with fibroblast subtypes, immune cells, and vascular cells.

**Key settings:** `reference="Healthy"`, `disease_name="systemic sclerosis"`, full genetic evidence enabled.

**Expected biology:** TGF-beta/ECM in fibroblasts, IFN signature in macrophages/pericytes, TGFB1-TGFBR1 L-R interactions between macrophages and fibroblasts.

**Known SSc targets to validate:** TGFBR1, PDGFRA, IL6R, JAK1/2, COL1A1, FN1, POSTN.

## Pattern 2: Chaining from scrnaseq-scanpy-core-analysis

When the user has already run the core scRNA-seq pipeline:

```python
from load_data import load_annotated_h5ad
adata = load_annotated_h5ad("adata_processed.h5ad",
                             celltype_key="cell_type",
                             condition_key="condition",
                             sample_key="donor_id")

# The h5ad from scanpy core has .X = log-normalized, .layers["counts"] = raw
# IMPORTANT: pass layer="counts" for DESeq2
de_results = run_pseudobulk_de(adata, reference="Control", layer="counts")
```

## Pattern 3: Inflammatory Disease (IBD, RA, Lupus)

For autoimmune/inflammatory diseases, adjust the disease context:

```python
from target_scoring import score_targets

# Custom disease context for IBD
ibd_context = {
    "name": "inflammatory bowel disease",
    "relevant_cell_types": [
        "macrophage", "monocyte", "T cell", "Th17", "Treg",
        "epithelial", "fibroblast", "B cell", "plasma cell",
    ],
    "relevant_pathways": [
        "TNF", "NFkB", "IL17", "IL23", "JAK", "STAT",
        "inflammatory", "immune", "interferon", "autophagy",
    ],
    "relevant_lr_pairs": [
        ("TNF", "TNFRSF1A"), ("IL17A", "IL17RA"),
        ("IL23A", "IL23R"), ("IL6", "IL6R"),
        ("CCL2", "CCR2"), ("CXCL8", "CXCR1"),
    ],
}

scores = score_targets(de_results, pathway_results, lr_results,
                        genetic_results, ot_annotations,
                        disease_context=ibd_context)
```

## Pattern 4: Raw Count Matrix Input

When starting from raw counts (no prior scRNA-seq processing):

```python
from load_data import load_raw_data
from preprocess import run_preprocessing_pipeline

adata = load_raw_data("path/to/filtered_feature_bc_matrix/")
adata = run_preprocessing_pipeline(adata, species="human")

# Verify preprocessing added required columns
assert "cell_type" in adata.obs.columns
assert "X_umap" in adata.obsm

# Then run the standard pipeline...
```

## Pattern 5: Transcriptomics-Only (No Genetic Evidence)

For rapid exploration without API queries:

```python
# Skip genetic evidence and OT queries
scores = score_targets(de_results, pathway_results, lr_results,
                        genetic_results=None, ot_annotations=None)
```

The scoring automatically reweights: genetic_evidence weight (0.25) is redistributed to DE, pathway, L-R, specificity, and druggability. Druggability defaults to 0.2 for all targets.
