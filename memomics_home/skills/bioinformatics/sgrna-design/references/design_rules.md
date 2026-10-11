# Option 3: De Novo sgRNA Design Rules (Last Resort)

Use only when the gene/organism is **not** covered by validated sequences (Option 1) or
CRISPick datasets (Option 2) — e.g. non-model organisms or fully custom designs. These are
the general rules from the source guide; they encode standard CRISPR design heuristics.

## Essential requirements

### 1. Length
- **SpCas9, SaCas9:** 20 bp protospacer.
- **Cas12a (AsCas12a, enAsCas12a):** 23–25 bp.

### 2. PAM (must be present in the genome, immediately flanking the target)
| Enzyme | PAM | Location |
|--------|-----|----------|
| SpCas9 | **NGG** | immediately 3' of the 20 bp target |
| SaCas9 | **NNGRRT** | immediately 3' of the target |
| AsCas12a (wild-type) | **TTTV** | immediately 5' of the target |
| enAsCas12a (enhanced) | **TTTV** | immediately 5' of the target |

**CRITICAL:** Guides designed for enAsCas12a may not work with wild-type AsCas12a (different
activity profiles). Always match the guide design to your exact enzyme variant.

### 3. GC content
- Target **40–60%** GC.

### 4. Avoid
- **TTTT** runs (Pol III terminator — truncates the guide transcript).
- Homopolymer runs > 4 of the same nucleotide.
- Known repetitive / low-complexity regions (off-target risk).

## Target location

| Goal | Where to target |
|------|-----------------|
| **Knockout (KO)** | early constitutive exons, first ~50% of the CDS |
| **Activation (CRISPRa)** | **−200 to +1 bp** relative to the TSS |
| **Inhibition (CRISPRi)** | **−50 to +300 bp** relative to the TSS |

## Best practices
- Design and **test 3–4 different sgRNAs** per target gene.
- Prefer guides with high predicted on-target efficiency (score > 0.5 where available) and
  minimal predicted off-targets.
- **Validate experimentally** (e.g., Sanger sequencing of the edited locus; T7E1/TIDE for
  indel quantification).

## Quick self-check helper
`scripts/check_design_rules.py` flags TTTT, homopolymer runs, out-of-range GC, and verifies the
PAM for a candidate protospacer + enzyme. It is a sanity check, not a genome-wide off-target
search — for real off-target assessment use a dedicated aligner (e.g., Cas-OFFinder, CRISPOR)
or the precomputed CRISPick off-target ranks when available.
