# ECM Pathway Contamination Validation Protocol

## Background
CellChat analysis of skeletal muscle (and other ECM-rich tissues) frequently identifies LAMININ, COLLAGEN, FN1, and TENASCIN among top pathways. Debate analysis will flag these as potential fibroblast (FAP) contamination artifacts.

## Validation Protocol

### Step 1: Check canonical FAP markers
```r
markers <- c("PDGFRA", "PDGFRB", "LUM", "DCN", "LOX", "TGFBI", "COL1A2")
DotPlot(seurat_obj, features = markers, group.by = "subcluster")
```

### Step 2: Decision thresholds
| Marker | Fibroblast threshold | Muscle threshold | Interpretation |
|--------|---------------------|------------------|----------------|
| PDGFRA | >20% | ≤5% | Canonical FAP marker — if ≤5%, FAP contamination ruled out |
| LUM | >30% | ≤10% | Lumican — proteoglycan specific to fibroblasts |
| DCN | >40% | ≤25% | Decorin — also expressed by muscle; use with PDGFRA |
| PDGFRB | >15% | ≤10% | Secondary FAP marker |
| LOX | >5% | ≤3% | Lysyl oxidase — fibrosis-specific |

### Step 3: CASE STUDY — human skeletal muscle SMF (2026-07-14)
- PDGFRA: NMJ=12%, zone1-6 ≤1% → **NOT contamination**
- LUM: zone1=8% → below threshold
- DCN: zone1=23% → ambiguous, but PDGFRA=1% confirms muscle source
- PDGFRB: zone1=9% → below threshold
- LOX: ≤2% everywhere → not fibrosis
- **Verdict**: COL1A1 is genuinely from muscle fiber ECM remodeling during denervation

### Step 4: If contamination IS found
- Re-cluster with higher resolution to separate FAPs
- Or filter PDGFRA+ cells before CellChat
- Or use only muscle-specific markers for identity
