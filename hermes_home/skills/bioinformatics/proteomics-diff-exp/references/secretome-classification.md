# Secretome / Conditioned Medium Protein Classification

## When to Use

When you have **supernatant/conditioned medium (CM) proteomics** data — the sample is not cell lysate but the extracellular fluid. CM contains a mixture of:
- Classical secreted proteins (signal peptide → ER/Golgi → exocytosis)
- EV/exosome cargo proteins (intracellular proteins packaged into vesicles)
- Cell debris / leakage proteins (from dead/dying cells)
- Media additives (serum proteins like ALB, INS, TF)

**The total CM proteome ≠ secretome.** You must classify proteins by existence form before interpreting function.

## Four-Class Classification System

| Class | Name | Criteria | Mechanism | Validation Strategy |
|-------|------|----------|-----------|---------------------|
| **I** | Free Soluble | Signal peptide + extracellular/secreted localization | Receptor binding → signal activation | ELISA/WB + recombinant protein add-back |
| **II** | Dual (Free + EV) | Signal peptide + EV/exosome evidence | Direct binding + EV delivery | EV separation then quantify both fractions |
| **III** | EV/Exosome Cargo | Intracellular localization + no signal peptide | EV uptake → cargo release | EV isolation + EV add-back + cargo blockade |
| **IV** | Background | Keratins, histones, ribosomal, media additives | Contamination / cell debris | Exclude from functional analysis |

## Step-by-Step Workflow

### Step 1: UniProt Batch Query
Query all gene symbols against UniProt REST API to get:
- Signal peptide (feature type: "Signal")
- Subcellular localization (comment type: "SUBCELLULAR LOCATION")
- Transmembrane domains

```python
import requests, time

def query_uniprot_batch(gene_names):
    results = {}
    for gene in gene_names:
        url = f"https://rest.uniprot.org/uniprotkb/search?query=gene:{gene}+AND+organism_id:9606&fields=accession,cc_subcellular_location,ft_signal&size=3"
        r = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
        if r.status_code == 200:
            results[gene] = r.json().get('results', [])
        time.sleep(0.15)  # rate limit
    return results
```

### Step 2: Feature Extraction
```python
def has_signal_peptide(entries):
    for entry in entries:
        for feat in entry.get('features', []):
            if feat.get('type') == 'Signal':
                return True
    return False

def get_subcellular_locations(entries):
    locs = []
    for entry in entries:
        for c in entry.get('comments', []):
            if c.get('commentType') == 'SUBCELLULAR LOCATION':
                for loc in c.get('subcellularLocations', []):
                    locs.append(loc.get('location', {}).get('value', ''))
    return locs
```

### Step 3: EV Database Cross-Reference
Check against Vesiclepedia / ExoCarta high-frequency EV markers:
- EV markers: CD9, CD63, CD81, TSG101, ALIX/PDCD6IP, FLOT1, FLOT2, ANXA5, RAB5A, RAB7A
- EV-associated keywords in subcellular localization: "extracellular exosome", "extracellular vesicle"

### Step 4: Classification Logic
```
if gene in MEDIA_CONTAMINANTS or is_keratin/histone/ribosomal:
    → Class IV (Background)

if has_signal_peptide AND is_extracellular/secreted:
    → Class I (Free Soluble)

if is_intracellular AND NOT has_signal_peptide:
    → Class III (EV/Exosome Cargo)

if has_signal_peptide AND has_EV_evidence:
    → Class II (Dual: Free + EV)
```

### Step 5: Literature Curation Correction
Override automated classification for well-studied proteins using literature. Key references:
- Sarkar et al. 2012 (PMID:22984290) — hESC secretome atlas
- Wolling et al. 2018 (PMID:29905012) — hPSC differentiation secretome
- Vesiclepedia: http://microvesicles.org/
- ExoCarta: http://exocarta.org/

## Known Classification Examples

### Class I (Free Soluble) — confirmed
AFP, HPX, IGFBP2, APOA4, APOC3, TTR, RBP4, CFI, SERPINA1, AHSG, SERPINC1, FGA, FGG, C3

### Class II (Dual) — confirmed
APOE, CLU, FN1, SPARC, CST3, COL6A1, COL1A1, LUM

### Class III (EV Cargo) — confirmed
HSPD1 (HSP60), PRDX1, HSPA8, HSP90AA1, PHB1, PHB2, GAPDH, ACTB, TUBB

### Class IV (Background) — always flag
KRT1, KRT5, KRT9, KRT10, KRT14, KRT15 (keratins)
Histone family proteins
RPS/RPL ribosomal proteins
ALB, INS, TF (media additives)
HNRNP proteins, putative/uncharacterized proteins

### Step 6: Anti-Aging / Functional Protein Identification
When the research context involves aging/senescence/rejuvenation, cross-reference classified proteins against aging databases after classification.

**Data sources for anti-aging annotation:**
1. **UniProt**: Search function descriptions for "aging", "senescence", "longevity"
2. **KB gene sets**: Check tissue-specific aging gene sets (e.g., `liver_aging_up`, `liver_aging_down` in MemOmics knowledge base)
3. **Literature**: PubMed search for "(gene) aging stem cell secretome extracellular vesicle"
4. **Key references**:
   - Yu et al. 2023 (PMID:37449253): ESC-EV rejuvenate senescent cells via miR-15b/290a → Ccn2-AKT/mTOR
   - Enomoto et al. 2025 (PMID:41101499): ESC-EV delay senescence by inhibiting oxidative stress

**Evidence tiers for anti-aging proteins:**
| Tier | Criteria | Example proteins |
|------|----------|------------------|
| Tier 1 (Strong) | UniProt aging annotation + KB gene set match + literature support | HSPD1, HSPA8, PRDX1, CLU, APOE, FSTL1, IGFBP2 |
| Tier 2 (Good) | KB gene set match or single literature source | C3, CAT, SOD1, TXN, PRDX6, HSP90AA1, MIF |
| Tier 3 (Potential) | Plausible mechanism + indirect evidence | FN1, SPARC, COL1A1, COL6A1, CST3, TTR, AFP |

**Visualization**: Horizontal bar chart of Tier 1–3 proteins sorted by mean abundance, color-coded by evidence tier.

## Pitfalls

1. **UniProt annotation gaps**: Some proteins lack subcellular localization data → fall back to literature
2. **Dual-class proteins**: APOE and CLU appear in both free and EV fractions — classify as Class II, validate with fraction separation
3. **Cell death artifacts**: HSP/chaperone proteins in CM may come from dying cells, not active EV secretion — use viability assays to confirm
4. **Protease degradation**: Free soluble proteins in CM may be degraded over time — consider protease inhibitors during collection
5. **Replicates vs. conditions confusion**: When CM proteomics has two columns (like test1/test2), ALWAYS check correlation first (r > 0.9 → replicates). See `references/no-replicate-proteomics.md` Step 0.

## Proven Run

| Date | Dataset | Proteins | Class I | Class II | Class III | Class IV | Unclassified |
|------|---------|----------|---------|----------|-----------|----------|--------------|
| 2026-07-20 | hES-4CL-EB CM | 142 | 32 | 12 | 60 | 31 | 7 |
