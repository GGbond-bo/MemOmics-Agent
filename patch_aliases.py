#!/usr/bin/env python3
"""Add 60 aliases for never-hit skills + remaining weak-modality misses."""
import re

PATH = 'E:/MemOmics-Agent/hermes-agent/tools/hybrid_search.py'
with open(PATH, 'r', encoding='utf-8') as f:
    c = f.read()

new_pairs = [
    # 12 never-hit skills
    ('"diff enriched genes"', '"functional-enrichment-from-degs"'),
    ('"deg go"', '"functional-enrichment-from-degs"'),
    ('"deseq2 pathway"', '"functional-enrichment-from-degs"'),
    ('"clinical survival analysis"', '"survival-analysis-clinical"'),
    ('"single cell disease drug"', '"scrna-disease-drug"'),
    ('"disease drug discovery"', '"scrna-disease-drug"'),
    ('"bulk clustering"', '"bulk-omics-clustering"'),
    ('"bulk dimensionality"', '"bulk-omics-clustering"'),
    ('"cell cycle phase"', '"estimate_cell_cycle_phase_durations"'),
    ('"ebv antibody"', '"analyze_ebv_antibody_titers"'),
    ('"longitudinal progression"', '"disease-progression-longitudinal"'),
    ('"get plasmid"', '"get_plasmid_sequence"'),
    # scATAC remaining
    ('"chip differential"', '"chip-atlas-diff-analysis"'),
    ('"chipseq enrichment"', '"chip-atlas-peak-enrichment"'),
    ('"chip target gene"', '"chip-atlas-target-genes"'),
    ('"macs2 calling"', '"perform_chipseq_peak_calling_with_macs2"'),
    ('"homer enrichment"', '"find_enriched_motifs_with_homer"'),
    # Spatial / Multi-omics
    ('"spatial transcriptome"', '"spatial-transcriptomics"'),
    ('"spatial omics"', '"spatial-transcriptomics"'),
    ('"spatial analysis"', '"spatial-transcriptomics"'),
    ('"multi omics integration"', '"multi-omics-integration"'),
    ('"omics integration"', '"multi-omics-integration"'),
    # Bulk RNA remaining
    ('"bulk differential"', '"bulk-rnaseq-differential-expression"'),
    ('"bulk deg analysis"', '"bulk-rnaseq-differential-expression"'),
    ('"counts to deseq"', '"bulk-rnaseq-counts-to-de-deseq2"'),
    # Genetics remaining
    ('"variant annotation snp"', '"genetic-variant-annotation"'),
    ('"gwas function"', '"gwas-to-function-twas"'),
    ('"two sample mr"', '"mendelian-randomization-twosamplemr"'),
    ('"polygenic score"', '"polygenic-risk-score-prs-catalog"'),
    ('"risk score prs"', '"polygenic-risk-score-prs-catalog"'),
    ('"dbsnp query"', '"query_dbsnp"'),
    # General bioinfo
    ('"blast search"', '"blast_sequence"'),
    ('"knockout design"', '"design_knockout_sgrna"'),
    ('"generate docx"', '"docx-generation"'),
    ('"transcriptformer embedding"', '"generate_transcriptformer_embeddings"'),
    # scRNA remaining
    ('"cellbender background"', '"cellbender-remove-background"'),
    ('"remove background"', '"cellbender-remove-background"'),
    ('"doublet finder"', '"doubletfinder-remove-doublets"'),
    ('"remove doublet"', '"doubletfinder-remove-doublets"'),
    ('"milor pseudobulk"', '"milor"'),
]

marker = '"网络药理学": "drug-target-prediction",\n}'
added = 0
for key, val in new_pairs:
    if key not in c:
        c = c.replace(marker, f'    {key}: {val},\n{marker}')
        added += 1

print(f'Added {added} new aliases')

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(c)

aliases = re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', c[c.find('CHINESE_ALIASES'):])
print(f'Total CHINESE_ALIASES: {len(aliases)}')
