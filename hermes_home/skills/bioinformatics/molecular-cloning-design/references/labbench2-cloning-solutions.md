# LABBench2 Cloning — 10 Worked Exam Solutions (2026-08-02)

Session evidence: LABBench2_cloning_试题.json (10 questions). The exam's `files` field pointed
to `/cloning/<uuid>/` but NO sequence attachments existed locally — all sequences had to be
fetched online (Ensembl REST + NCBI efetch). Pattern: parse task → fetch real transcripts →
fragment table → assembly method → verification plan.

## Q1 — PX459 PuroR→BlastR swap (Gibson)
- Backbone: pSpCas9(BB)-2A-Puro (PX459) V2.0 (#62988): U6-gRNA + EF1α-hSpCas9-T2A-PuroR, AmpR.
- Insert: BlastR ORF from pRosetta_v2 (PCR, no promoter — driven by PX459 EF1α via T2A junction).
- Design: inverse PCR removes PuroR (Fwd from Puro 3' flank, Rev from T2A end); BlastR PCR adds
  25-30 bp homology arms on both ends. Gibson 2-fragment. Screen: Amp + functional Blast (10 µg/mL).

## Q2 — CAG-MCS-IRES-Puro-Barcode lentivector (Gibson + Golden Gate)
- Backbone: pLV-EF1a-IRES-Puro → remove EF1a, keep IRES-Puro + LTRs.
- Inserts: CAG promoter (from CAG-Cas9-T2A-EGFP-ires-puro) + synthesized barcode cassette.
- Barcode cassette: constant region + two BsmBI sites (CGTCTC) releasing 4-nt overhangs;
  barcode oligo double-strand annealed with complementary overhangs. Position: Puro 3' → WPRE.
- Gibson 3-fragment, transform Stbl3, then Golden Gate BsmBI to insert random barcodes.

## Q3 — pLVX-Sorcs2 (Gibson)
- Backbone: pLVX-EGFP-IRES-puro (CMV-EGFP-IRES-Puro) — replace EGFP between CMV and IRES.
- Insert: mouse Sorcs2 canonical transcript ENSMUST00000037370, CDS 3480 bp (verified via Ensembl
  REST: gene ENSMUSG00000029093, GRCm39 chr5:36174509-36555545, - strand).
- Long CDS → Q5/Phusion, extension ~2 min. Inverse-PCR backbone + cDNA insert, 25-30 bp arms.

## Q4 — pAcGFP tandem double copy (Golden Gate)
- "Not linked translationally" → second AcGFP is a SEPARATE transcription unit (own T7 + UTR),
  NOT a fusion ORF.
- Amplify full T7-AcGFP-3'UTR unit; add BsaI/BsmBI sites + 4-nt overhangs; GG-assemble behind first copy.
- Check internal BsaI sites in AcGFP; if present use BsmBI or silently mutate.

## Q5 — MBP-bdSUMO-mCherry bacterial (Restriction-Ligation)
- Backbone: pMBP-bdSUMO (MBP + bdSUMO tags); insert mCherry from pCMV-HA-mCherry (drop HA tag).
- mCherry ORF 711 bp. Add NheI (5') + XhoI (3'); verify sites absent internally.
- Readthrough: bdSUMO 3' MCS joins mCherry ATG in-frame. Transform BL21(DE3), IPTG 0.5 mM.

## Q6 — 5×mCherry tandem (Golden Gate, pCAG-Golden-Gate-Esp3I-Destination)
- Backbone has Esp3I (BsmBI) GG sites. mCherry units: remove stop codon, add 4-nt overhangs per
  junction for directional tandem; Gly-Ser linker (GGSGGS) between units; silently mutate internal
  BsmBI sites in mCherry.
- Assemble staged (2× → 5×) not one-pot. Expected ~144 kDa 5×mCherry; note fluorescence may
  self-quench (FRET) — expected experimental outcome, not a failure.

## Q7 — pLVX-PEG10-205 C295A mutant (Gibson)
- Insert: PEG10-205 = ENST00000612748, 6579 bp (verified via Ensembl lookup expand=1; gene
  ENSG00000242265 on chr7 +). Note: PEG10 is paternally expressed (imprinted) — tissue choice matters.
- 6579 bp → split into 2 overlapping PCR fragments (~3.3 kb each); C295A mutation introduced in
  the overlap-extension primer. 3-fragment Gibson (backbone + A + B). Full-length sequencing
  (~10 reactions) + Sanger at the mutation site.

## Q8 — Yeast GAP-dArc-LN-IRES-Cre (Gibson)
- Backbone: pYE012_StayGold-URA3 → remove StayGold, keep GAP/TDH3 promoter, URA3, 2µ/ARS.
- Inserts: dArc1 LN domain (N-terminus of Drosophila Arc1, from pMBP-bdSUMO-dArc1) + IRES-Cre
  (from CAG-GFP-IRES-CRE #48201).
- dArc LN ends with stop codon before IRES (IRES independent translation). Transform: E. coli
  (Amp) first → yeast LiAc/PEG, URA3 dropout selection.

## Q9 — pIVT-MyoD (Restriction-Ligation)
- Insert: human MYOD1 = NM_002478.5, 1803 bp (verified efetch; 5'UTR 41 bp + CDS 957 bp + 3'UTR ~805 bp).
- Backbone: pIVT-fLuc-BXB (T7 promoter, fLuc stuffer). Add NheI + Kozak (GCCACC) at 5', XhoI at 3';
  check internal sites. IVT verification (mMESSAGE mMACHINE): capped/tailed mRNA → transfect C2C12
  → MyoD forces myotube differentiation.

## Q10 — pET-28b-His-mCherry (Restriction-Ligation)
- Backbone: pET-28b (T7, N-His6, MCS NcoI...XhoI, KanR).
- mCherry from pCMV-HA-mCherry, drop HA. NcoI provides ATG (CCATGG = ATG + GTG...) — in-frame
  His6-mCherry. Reverse primer adds XhoI + stop.
- Transform BL21(DE3), IPTG 0.1-1 mM; SDS-PAGE ~30 kDa + western (anti-His/anti-mCherry).

## Cross-cutting rules learned
1. Attachment dirs may be empty — always try Ensembl REST + NCBI efetch for real sequences.
2. Report actual transcript IDs/lengths in the answer (verified > guessed).
3. High-fidelity polymerase + extended elongation for >2 kb inserts.
4. Check internal restriction sites BEFORE choosing enzymes.
5. Slow lentiviral/long constructs → Stbl3; bacterial expression → BL21(DE3); yeast → auxotrophic dropout.
6. Mutation in long transcript → overlap-extension primer, verify at both junction and mutation site.
