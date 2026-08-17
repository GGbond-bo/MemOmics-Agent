# No-Replicate / Low-Replicate Proteomics Workflow

## ⛔ MANDATORY: Replicate Detection (Step ZERO — do this FIRST before ANY analysis)

**Before computing fold changes or any differential metrics, determine whether columns represent conditions or replicates.**

```python
import pandas as pd
import numpy as np
from scipy.stats import pearsonr

df = pd.read_excel("protein_report.xlsx")
cols = [c for c in df.columns if c not in ['Protein.Group','Protein.Ids','Protein names','Genes']]

if len(cols) == 2:
    log2_c1 = np.log2(df[cols[0]] + 1)
    log2_c2 = np.log2(df[cols[1]] + 1)
    r, p = pearsonr(log2_c1, log2_c2)

    if r > 0.9:
        print(f"⚠️ REPLICATES DETECTED (r={r:.4f}) — use Path A: Abundance-Based Analysis")
        # → Go to "Path A" section below
    elif r < 0.7:
        print(f"Conditions with no replicates (r={r:.4f}) — use Path B: Fold-Change Only")
        # → Go to "Path B" section below
    else:
        print(f"AMBIGUOUS (r={r:.4f}) — ASK USER: replicates or conditions?")
        # → STOP and ask the user to clarify
```

| r value | Interpretation | Analysis path |
|---------|---------------|----------------|
| r > 0.90 | **Technical replicates** | Mean abundance → rank by abundance → functional enrichment |
| r 0.70–0.90 | **Ambiguous** | **ASK USER**: replicates or conditions? |
| r < 0.70 | **Likely different conditions** (no reps) | Fold-change only (no p-values, no stats) |

> ⛔ **PITFALL (CRITICAL)**: The single most common and destructive error in low-N proteomics is **treating replicate columns as conditions**. If you compute log2FC on replicate data (r > 0.9), ALL fold changes are technical noise. This session was corrected mid-analysis: test1/test2 (r=0.94) were replicates, not conditions. The entire differential expression analysis was invalidated and redone.

---

## When to Use

When you have **1–2 samples with no biological replicates** (e.g., single-run LFQ). limma+DEqMS cannot be used because there is no residual variance to estimate. **Always run Step 0 first.**

---

## Path A: Abundance-Based Analysis (columns are replicates, r > 0.9)

Use when test1/test2 are **technical replicates** → compute mean abundance, rank by signal strength.

### Step A1: Compute Mean Abundance
```python
df['mean_abundance'] = (df['test1'] + df['test2']) / 2
df['log10_mean'] = np.log10(df['mean_abundance'] + 1)
df['CV'] = np.abs(df['test1'] - df['test2']) / (df['mean_abundance'] + 1)
df = df.sort_values('mean_abundance', ascending=False).reset_index(drop=True)
df['abundance_rank'] = range(1, len(df)+1)
```

### Step A2: Replicate QC Visualization
- **Replicate correlation scatter**: log2(test1) vs log2(test2), color by protein classification
- **Abundance histogram**: log10(mean_abundance) faceted by classification
- **CV histogram/boxplot**: CV distribution by classification (CV > 0.3 = caution)
- **Top-N bar chart**: Horizontal bar of top 40–50 proteins by mean abundance, color-coded by class

### Step A3: Protein Classification
See `references/secretome-classification.md` for the 4-class system:
- **Class I (Free Soluble)**: Signal peptide + secreted/extracellular
- **Class II (Dual: Free + EV)**: Signal peptide + EV database evidence
- **Class III (EV/Exosome Cargo)**: Intracellular + no signal peptide
- **Class IV (Background)**: Keratins, histones, ribosomal, media additives

### Step A4: Anti-Aging / Functional Protein Identification (if applicable)
1. Cross-reference against UniProt annotations for aging-related terms
2. Check against KB gene sets (e.g., `liver_aging_up/down`)
3. Literature search for stem cell secretome anti-aging proteins
4. Tier proteins by evidence strength: Tier 1 (strong) / Tier 2 (good) / Tier 3 (potential)

### Step A5: Downstream Analysis
- **Functional enrichment**: GO + KEGG via `clusterProfiler` (R), using ALL functional proteins (Class I+II+III)
- **PPI network**: STRING API → high-confidence edges (score ≥ 700)
- DO NOT do differential expression analysis — there is no biological contrast
- DO split enrichment by classification if biologically meaningful

### Key Parameters (Path A)

| Parameter | Default | Notes |
|-----------|---------|-------|
| CV warning threshold | 0.3 | Proteins with CV > 0.3 have poor replicate agreement |
| Top-N for bar chart | 40 | Adjust based on total protein count |
| Media contaminant list | ALB, INS, TF, IGF1, FGF2, EGF | Flag as Class IV |

---

## Path B: Fold-Change Only (columns are different conditions, r < 0.7)

Use when columns represent **different biological conditions** with no replicates.

### Step B1: Data Loading
```python
import pandas as pd, numpy as np

df = pd.read_excel("protein_report.xlsx")
df_clean = df.dropna(subset=['test1','test2']).copy()
```

### Step B2: Log2 Transform + Fold Change
```python
df_clean['log2_test1'] = np.log2(df_clean['test1'])
df_clean['log2_test2'] = np.log2(df_clean['test2'])
df_clean['log2FC'] = df_clean['log2_test1'] - df_clean['log2_test2']
df_clean['mean_log2'] = (df_clean['log2_test1'] + df_clean['log2_test2']) / 2
```

### Step B3: Differential Classification (no p-values!)
```python
fc_threshold = 0.58  # ~1.5-fold
df_clean['change'] = 'Unchanged'
df_clean.loc[df_clean['log2FC'] > fc_threshold, 'change'] = 'Up'
df_clean.loc[df_clean['log2FC'] < -fc_threshold, 'change'] = 'Down'
```

⚠️ **CRITICAL**: No p-values, no FDR. All differential calls are fold-change based. Every hit MUST be confirmed by orthogonal methods (ELISA, Western blot, PRM).

### Step B4: Visualization
- Volcano plot: log2FC vs mean_log2, colored by change direction
- MA plot: log2FC (M) vs mean_log2 (A)
- Intensity distribution histograms
- Bar charts for top candidates

### Step B5: Downstream Analysis
- **Enrichment**: Use `clusterProfiler` (R) with ENTREZID mapping from gene symbols
- **PPI**: Use `query_string` + literature-curated interactions
- **Classification**: For conditioned medium / secretome, see `references/secretome-classification.md`

### Key Parameters (Path B)

| Parameter | Default | Notes |
|-----------|---------|-------|
| log2FC threshold | 0.58 | ~1.5-fold change |
| Missing value handling | drop (require both present) | Small datasets can't impute reliably |
| Normalization | log2 transform only | No quantile/median normalization without replicates |

---

## Pitfalls

1. **⛔ Replicates mistaken for conditions**: Compute r FIRST. r > 0.9 → REPLICATES, not conditions. Do NOT compute log2FC.
2. **No statistical significance**: Cannot compute p-values without replicates. Report as "exploratory" or "discovery-phase".
3. **Fold-change inflation**: Low-intensity proteins have inflated log2FC due to noise. Use MA plot to assess.
4. **Batch effects**: Keratin/histone/ribosomal changes may reflect sample handling, not biology. Cross-reference with known contaminant lists.
5. **Media contaminants**: ALB, INS, TF, IGF1, FGF2, EGF, TGFB1 are common serum/media additives — flag as Class IV (Background).
6. **CV as quality filter**: In Path A, proteins with CV > 0.3 across replicates should be interpreted cautiously.

---

## Proven Runs

| Date | Dataset | Path | r | Species | Tissue | Proteins | Key Finding |
|------|---------|------|---|---------|--------|----------|-------------|
| 2026-07-20 | hES-4CL-EB CM | **A** (replicates) | 0.94 | Human | Embryoid body CM | 142 | HSPD1 top functional protein (1.56×10⁸); 31 anti-aging candidates; blood microparticle GO (p=7.9×10⁻³¹); Integrin signaling KEGG (p=1.4×10⁻⁷) |

> ⚠️ The 2026-07-20 run was initially misclassified as Path B (log2FC computed on replicates). This error was caught mid-session by the user and corrected to Path A. The Proven Run table above reflects the CORRECTED analysis.
