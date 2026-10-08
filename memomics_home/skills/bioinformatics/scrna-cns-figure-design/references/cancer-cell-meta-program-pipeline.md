# Reference-Grade NMF Meta-Program Pipeline — Zhuo et al. 2026 Cancer Cell

> Source: 2026-07 session. User asked to download+interpret "A conserved
> re-epithelialization program underlies malignancy in pancreatic ductal
> adenocarcinoma" (Cancer Cell 44:1270-1289.e11, PMID 42066759,
> DOI 10.1016/j.ccell.2026.03.021). This is the closest published analog to the
> user's F2f NMF plan — steal its pipeline verbatim.

## The Pipeline (validated, publication-grade)

```
1. Per-sample (or per-condition) NMF independently
   → e.g. 10 PDAC tumors → 227 robust programs total
2. Meta-program integration:
   - Jaccard similarity on top-50 genes of each program
   - UPGMA hierarchical clustering of the Jaccard matrix
   - RobustRankAggreg to extract core genes per meta-program
3. Filter: exclude mitochondrial / ribosomal contamination programs
4. Program marker definition: rank top-800 in own MP AND ≥10× lower rank in all
   other MPs
5. Result: 13 meta-programs (MP10 = invasive program, MP11 = intraductal program)
```

## Why This Matters for the User's F2f

- The user's F2f plan ("NMF gene program discovery") becomes publication-defensible
  if run as per-sample NMF → meta-program integration instead of single NMF on pooled data.
- Direct replication recipe for 骨骼肌 MF (10 clusters × 5 conditions):
  - NMF per condition (or per sample), then Jaccard(top50)+UPGMA+RobustRankAggreg
  - Expect ~5-8 meta-programs: fast contractile / slow oxidative / aging-degeneration /
    NMJ-denervation / ribosomal-translation / stress-ROS
- MP marker definition (top800 + 10×) is directly reusable for cNMF program genes.

## "Program Hijacking" Narrative (for Specialized MF dual-origin)

The paper's core concept: PDAC invasion is NOT classic EMT but a hijacked
"wound re-epithelialization" program (MP10 ≈ migrating keratinocyte program),
driven by wound-induced TF FOSL1, fed by CTHRC1^high myCAF via non-canonical
EGFR ligands (CTHRC1/CCN2/VCAN) — a self-reinforcing "wound-like vicious cycle."

Transferable to the user's Specialized MF (denervation-slow + developmental-fast
dual origin):

| Cancer Cell evidence style | User's MF analog |
|---------------------------|------------------|
| MP10 ≠ EMT: cells keep CDH1/EPCAM; EMT cells ~0.25% of tumors and mutually exclusive with MP10 | Check whether denervation-slow and developmental-fast components are mutually exclusive states (like MP10 vs EMT), not a single hybrid |
| ~50% of PanIN→PDAC open chromatin shared with wound EpdSC (ATAC-seq) | User has ATAC (multi-omics!): check whether denervated-MF open chromatin overlaps known denervation models — the Fig 5 logic |
| FOSL1 master regulator: binds ~75% of up-regulated genes; ChIP-seq validation | F6 GRN: ATAC + TOBIAS footprinting → candidate TF → validate (not just marker genes) |
| FOSL1 also binds Cdkn2a enhancer — explains why MP10 activation is always coupled to TSG expression | Check whether RSS ("pre-activated but suppressed" analog) co-expresses TSG / senescence-suppression programs |

## Key Literature Anchors (verified)

- Zhuo M et al. 2026, Cancer Cell. PMID 42066759. Stereo-seq (BGI) spatial
  transcriptomics, 10 untreated PDAC; GEO mouse GSE248586; code github.com/ycl0051/PDAC.
- Methods reused: Stereopy cell-cell communication, TOBIAS v0.16.1 footprinting,
  AUCell v1.16.0, clusterProfiler GSEA (10000 permutations).

## Download Status (this session)

- ScienceDirect = paywall + Cloudflare anti-bot; PMC not open-access; no preprint.
- User provided PDF via 科研通 (ablesci.com) — full text extractable with pymupdf.
- Lesson: for paywalled Cancer Cell/Nature-family papers, ask user for 科研通
  (ablesci) download or institutional access rather than burning time on curl.
