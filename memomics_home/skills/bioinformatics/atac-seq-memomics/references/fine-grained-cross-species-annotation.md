# Fine-Grained Cross-Species Subcluster Annotation Alignment

## When to Use

User has:
1. **Reference species** (e.g., monkey/Zhang Xiao 2026) with already-annotated subclusters (predictedAnno: 18 subtypes)
2. **Target species** (e.g., human 40 samples) with ArchR `getMarkerFeatures` output CSV (cluster × marker genes)
3. Wants: **matching subtypes share the same name, non-matching ones keep their original names**

This is the correct approach for cross-species comparison — NOT forcing everything into 8 broad classes.

## Method: Marker Intersection + Coding Gene Filtering

### Step 1: Filter Non-Coding Genes from getMarkerFeatures Output

ATAC GeneScoreMatrix marker lists are polluted by non-coding genes at top positions. **Must filter before annotation.**

```python
def is_coding(gene):
    """Filter miRNA, lncRNA, snoRNA, OR genes, pseudogenes"""
    g = gene.upper()
    if g.startswith('MIR') or g.startswith('MIRN'): return False
    if g.startswith('SNORD') or g.startswith('SNORA'): return False
    if g.startswith('LINC') or g.startswith('LOC'): return False
    if g.startswith('OR') and re.match(r'OR\d', g): return False  # olfactory receptors
    if g.startswith('TAS2R'): return False  # taste receptors
    if '-AS' in g or '-IT' in g: return False  # antisense/intronic transcripts
    if g.startswith('LCE'): return False
    if g.startswith('KRTAP'): return False
    if g.startswith('CT47') or g.startswith('CT45'): return False
    return True
```

### Step 2: Build Reference Marker Dictionary

From the reference species' annotation (e.g., Zhang Xiao 2026 Methods section):

```python
monkey_markers = {
    'DG Ex': ['NEUROD1','PROX1','GABRA4','SLC17A7','C1QL2','EBF1'],
    'CA1_SUB s.f. Ex': ['CAMK2A','SORL1','RELN','SLC17A7','NRGN','RASGRF2'],
    'CA2_4 Ex': ['CAMK2A','EGR1','NPY1R','SLC17A7','OPCML','STK32B'],
    'EC L2 Ex': ['CUX2','RELN','SLC17A7','RORB','LAMP5'],
    'EC L3_5 Ex': ['TLE4','THEMIS','SLC17A7','FEZF2','BCL11B'],
    'EC L6 Ex': ['ADRA1A','TLE4','SLC17A7','FOXP2','TBR1'],
    'CAE_SUB deep Ex': ['CRYM','FOXG1','SLC17A7','MEIS2','ETNPPL'],
    'MGE SST Inh': ['GAD2','LHX6','SST','SLC32A1','NXPH1','NPY'],
    'MGE PVALB Inh': ['GAD2','LHX6','PVALB','SLC32A1','GAD1','ERBB4'],
    'CGE CNR1 Inh': ['GAD2','ADARB2','CNR1','SLC32A1','VIP','CALB2'],
    'CGE LAMP5 Inh': ['GAD2','ADARB2','LAMP5','SLC32A1','NDNF','ID2'],
    'Astrocyte': ['GFAP','SLC1A2','AQP4','ALDH1L1','EDNRB','GJA1','FGFR3','SLC1A3'],
    'ODC': ['MBP','OPALIN','PLP1','MOG','MAG','MYRF','KLK6'],
    'OPC': ['PDGFRA','CSPG4','SOX10','OLIG2','OLIG1','VCAN','PCDH15'],
    'Microglia': ['CSF1R','CX3CR1','TMEM119','P2RY12','AIF1','HEXB','C1QA','C1QB'],
    'VS': ['PECAM1','CLDN5','RGS5','PDGFRB','ACTA2','FLT1','FOXC2','DCN'],
    'Choroid Plexus': ['TTR','FOLR1','CLIC6','OTOF','SLC13A4'],
    'Ependymal': ['FOXJ1','CFAP126','PIFO','DNAH5'],
}
```

### Step 3: Match Each Cluster to Best Reference Subtype

```python
for cluster_id, cluster_genes in clusters.items():
    scores = {}
    for anno, markers in monkey_markers.items():
        hits = [m for m in markers if m.upper() in cluster_genes]
        scores[anno] = (len(hits), hits)
    
    sorted_scores = sorted(scores.items(), key=lambda x: -x[1][0])
    best_anno, (best_hits, best_hit_genes) = sorted_scores[0]
    
    # Decision logic
    if best_hits >= 3:
        annotation = best_anno      # high confidence: use reference name
        confidence = 'high'
    elif best_hits == 2:
        annotation = best_anno      # medium confidence
        confidence = 'medium'
    elif best_hits == 1:
        annotation = best_anno      # low confidence
        confidence = 'low'
    else:
        annotation = f'C{cluster_num}'  # no match: keep original name
        confidence = 'none'
```

### Step 4: Output Alignment Table

| Cluster | Annotation | Monkey Match | Hits | Hit Genes | Confidence | Top5 Coding Genes |
|---------|-----------|-------------|------|-----------|------------|-------------------|
| C10 | Astrocyte | Astrocyte | 3 | GFAP,SLC1A2,AQP4 | high | EMX2,GJB6,... |
| C14 | MGE PVALB Inh | MGE PVALB Inh | 3 | GAD2,SLC32A1,GAD1 | high | DLX1,DLX6,... |
| C17 | EC L3_5 Ex | EC L3_5 Ex | 3 | SLC17A7,FEZF2,BCL11B | high | EGR4,UBXN10,... |
| C13 | C13 | none | 0 | — | none | HOXD11,MNX1,... |

## Key Findings (2026-08-27 Human 40 Samples)

### High Confidence (≥3 markers): 6 clusters
- C10/C11: Astrocyte (GFAP, SLC1A2, AQP4)
- C14/C15: MGE PVALB Inh (GAD2, SLC32A1, GAD1 / LHX6, SLC32A1, GAD1)
- C17: EC L3_5 Ex (SLC17A7, FEZF2, BCL11B)
- C30: ODC (OPALIN, MAG, KLK6)

### Medium Confidence (2 markers): 7 clusters
- C7: CAE_SUB deep Ex (FOXG1, ETNPPL)
- C8/C9/C12: Astrocyte (various 2-marker combos)
- C16: MGE PVALB Inh (SLC32A1, GAD1) — actually more like "泛MGE Inh"
- C21: VS (CLDN5, FOXC2)
- C22: Microglia (CX3CR1, C1QA)

### Low Confidence (1 marker): 9 clusters
- C1/C6: OPC (CSPG4 only)
- C2/C3: EC L3_5 Ex (BCL11B only)
- C4/C5: CAE_SUB deep Ex (FOXG1 only)
- C18/C19: CA1_SUB s.f. Ex (NRGN only)
- C20: Microglia (CX3CR1 only)

### No Match (0 markers): 5 clusters
- C13: HOX developmental genes (artifact)
- C23: Inflammatory microglia markers (CXCL10, CLEC5A, CASP1, SIGLEC7) — but no standard Microglia markers
- C25/C26/C28: Previously identified as batch artifacts / ambiguous

## Pitfalls

1. **Non-coding gene pollution**: Without filtering, top30 markers are 50%+ miRNA/lncRNA/OR genes. Always filter first.
2. **Single-marker matches are unreliable**: CSPG4 appears in both OPC and VS; FOXG1 in CAE_SUB deep Ex and some ExN clusters. Use ≥2 markers for medium confidence.
3. **C23 inflammatory microglia**: Has CXCL10/CLEC5A/CASP1 (inflammatory markers) but lacks CSF1R/CX3CR1/TMEM119 (standard microglia). Consider labeling as `Microglia_inflammatory` rather than forcing into standard Microglia.
4. **Excitatory neuron subtypes are hard to distinguish in ATAC**: DG/CA1/CA2-4/EC all share SLC17A7/CAMK2A. The ATAC resolution limit means some clusters can only be labeled at the broad ExN level.
5. **Reference species marker list must come from the paper's Methods section**, not from memory or generic databases.

## Output Files

- `task4/human_subcluster_annotation.csv` — full alignment table
- `task4/zx_vs_human40_annotation_heatmap.png` — heatmap of marker hits
- `scripts/zx_vs_human40_annotation.py` — reusable Python script

## User Preference

User explicitly said: "不一定注释8个大群，而是细分亚群注释上，保证注释相同，其他的就正常按照人和猴脑自己的注释" — meaning:
- Matching subtypes → same name (e.g., both call it "Astrocyte" not "Ast" or "Astro")
- Non-matching subtypes → keep original names (e.g., human C13 stays "C13", not forced into a category)
- This is the correct cross-species annotation strategy for patent/conservation analysis
