---
id: skill_molecular_cloning_design
name: molecular-cloning-design
description: Design complete cloning strategies for plasmid engineering (Gibson, Golden Gate, restriction-ligation) including backbone linearization, primer/overhang design, long-insert splitting, mutation introduction, and verification. Covers lentiviral, bacterial, yeast, and IVT expression backbones and Addgene plasmid swaps. Also the playbook for LABBench2 cloning-style exam questions.
when_to_use: "[molecular cloning] 克隆策略设计：Gibson Assembly / Golden Gate / Restriction-Ligation / Addgene质粒改造 / 慢病毒·细菌·酵母·IVT载体构建 / LABBench2 cloning考试"
category: Mol Bio
short-description: Design complete cloning strategies for plasmid engineering (Gibson, Golden Gate, restriction-ligation).
detailed-description: >
  End-to-end cloning strategy design: identify fragments from Addgene/Ensembl/NCBI sources,
  design primers with assembly overhangs or restriction sites, choose backbone linearization
  method, handle long inserts (>4kb) and point mutations, and specify verification steps.
  Covers lentiviral, bacterial, yeast, and IVT expression backbones. Also the playbook for
  LABBench2 cloning-style exam questions where attachments are absent and sequences must be
  fetched online.
starting-prompt: "Design a Gibson assembly strategy to swap PuroR for BlastR in PX459 using pRosetta_v2 as BlastR source."
---

# Molecular Cloning Design

## Trigger
- "clone X into Y" / "设计克隆策略" / Gibson / Golden Gate / restriction-ligation / backbone swap / Addgene plasmid
- LABBench2 cloning exam questions (design questions referencing Addgene plasmids + Ensembl/NCBI transcripts)

## Core workflow (design answers, no wet lab required)
1. **Parse the task**: backbone (Addgene #), insert source (which plasmid/gene), fusion vs independent expression, mutation requirements.
2. **Get real sequences online when attachments are missing**:
   - Ensembl REST: `https://rest.ensembl.org/lookup/id/ENSG...?expand=1` for transcript lists; `/sequence/id/<ENST>?type=cds` for CDS; `display_name` reveals isoform (e.g. PEG10-205 = ENST00000612748, 6579 bp).
   - NCBI: `efetch db=nuccore` for RefSeq mRNA (e.g. MYOD1 NM_002478.5 = 1803 bp).
   - Record: transcript ID, length, CDS length, UTR presence — report them in the answer.
3. **Design fragments table**: backbone (how linearized), inserts (PCR from what), each with 25-30 bp Gibson homology arms / Golden Gate 4-nt overhangs / restriction sites.
4. **Choose assembly method**: Gibson (2-3 fragments, any junction), Golden Gate (directional, scarless, multimerization), restriction-ligation (cheap, needs unique sites).
5. **Check internal restriction sites** — a site used for cloning must not occur inside insert or backbone (NEBcutter mental check / in-silico).
6. **Mutation introduction**: C295A-style point mutations → put mutant base in overlap-extension PCR primers or a dedicated mutation primer; verify by Sanger.
7. **Verification plan**: colony PCR → junction Sanger → full-length sequencing (long inserts need N reactions) → functional assay (transfection, IPTG induction, IVT).

## Method-specific rules
### Gibson Assembly
- Homology arms 25-30 bp each side; terminal 20 bp Tm ≥ 50°C; total overlap ≥ 40 bp.
- Backbone linearized by inverse PCR + DpnI digest (destroys template).
- >2 fragments OK; long inserts (>4 kb) → split into 2 PCR fragments sharing an overlap, or 3-fragment Gibson.
- High-fidelity polymerase (Q5/Phusion) with extended elongation (~1 kb/30 s).

### Golden Gate
- Type IIS enzymes: BsaI (GGTCTC), BsmBI/Esp3I (CGTCTC) — cut outside recognition, leaving 4-nt overhangs.
- Overhang design: different 4-nt overhangs per junction enforce directional assembly; avoid self-ligating overhangs.
- **Internal type IIS sites in insert/backbone MUST be silently mutated** (check mCherry, AcGFP etc.).
- Thermal cycling: 37°C 5 min / 16°C 10 min × 30, then 65°C 20 min heat-kill. T4 ligase + enzyme in same reaction.
- Tandem repeats (e.g. 5×mCherry): assemble in stages (2× → 5×) rather than one pot; include flexible Gly-Ser linker between units if fused protein.
- "Not linked translationally" = separate transcription units (each own promoter+UTR) or IRES — NOT a fusion ORF.

### Restriction-Ligation
- Pick sites flanking the stuffer in backbone MCS; ensure sites absent internally.
- NcoI trick: NcoI site CCATGG provides the ATG → use for N-terminal fusion right after His6 (pET-28b MCS: NcoI...XhoI).
- Kozak context GCCACC before ATG for mammalian expression.
- Ligate 3:1 insert:vector molar ratio; 16°C overnight; heat-inactivate.

## Backbone quick facts
- **pSpCas9(BB)-2A-Puro (PX459) V2.0** (#62988): U6-gRNA + EF1α-hSpCas9-T2A-PuroR; AmpR; swap marker at the T2A junction.
- **pLVX-EGFP-IRES-puro** (Clontech): CMV-EGFP-IRES-Puro, AmpR, lentiviral; replace EGFP ORF between CMV and IRES.
- **pLV-EF1a-IRES-Puro** (#85132): EF1a-IRES-Puro lentiviral.
- **pET-28b**: T7, N-His6, MCS NcoI...XhoI, KanR; transform BL21(DE3) for expression.
- **pIVT-fLuc-BXB**: T7-driven IVT template; fLuc stuffer; replace with gene ORF for mRNA production.
- **pMBP-bdSUMO**: bacterial MBP+bdSUMO tags; fuse ORF downstream of bdSUMO (frame matters).
- **pCAG-Golden-Gate-Esp3I-Destination**: CAG promoter + Esp3I GG sites for mammalian expression.
- **CAG-GFP-IRES-CRE** (#48201): source of IRES-Cre cassette (useful in many builds).
- Yeast backbones (pYE012_StayGold-URA3): use yeast promoters (GAP/TDH3) — mammalian CAG/CMV don't work in yeast; select on URA3 dropout.

## Strain / screening notes
- Lentiviral vectors + long inserts → transform Stbl3 (or Stbl4), 30°C.
- Bacterial expression → BL21(DE3), IPTG 0.1-1 mM, 37°C 3h or 16°C overnight.
- Yeast → LiAc/PEG transformation, auxotrophic dropout selection.

## Pitfalls
- Forgetting biology constraints (e.g. PEG10 is imprinted — paternal allele expression; tissue choice for cDNA).
- Assuming a fused ORF when the question says "not linked translationally".
- Single-piece PCR for >4 kb inserts → split into overlapping fragments.
- Skipping internal-site check → failed digest later.
- For IVT: keep UTRs + add Kozak; verify with in vitro transcription before transfection.

## References
- `references/labbench2-cloning-solutions.md` — 10 worked LABBench2 cloning exam solutions (Q1-Q10: fragment tables + steps + verification).
- See also `pcr-primer-design` for primer Tm/GC validation scripts.
