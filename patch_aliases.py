#!/usr/bin/env python3
"""Fix incorrect aliases + add missing ones for weak modalities."""
import re

PATH = 'E:/MemOmics-Agent/hermes-agent/tools/hybrid_search.py'
with open(PATH, 'r', encoding='utf-8') as f:
    c = f.read()

fixes = {
    # Fix wrong skill names
    '"gwas": "gwas-analysis"': '"gwas": "gwas-phewas"',
    '"孟德尔": "mendelian-randomization"': '"孟德尔": "mendelian-randomization-twosamplemr"',
    '"mendel": "mendelian-randomization"': '"mendel": "mendelian-randomization-twosamplemr"',
    '"chip": "perform_chipseq_peak_calling_with_macs2"': '"chip": "chip-atlas-target-genes"',
    '"chipseq": "perform_chipseq_peak_calling_with_macs2"': '"chipseq": "chip-atlas-target-genes"',
}

for old, new in fixes.items():
    if old in c:
        c = c.replace(old, new)
        print(f'Fixed: {old[:50]}... -> {new[:50]}...')
    else:
        print(f'NOT FOUND: {old[:50]}...')

# Add new aliases before the closing brace
new_aliases = [
    # Bulk RNA
    ('"bulk rna"', '"bulk-rnaseq-differential-expression"'),
    ('"bulk rnaseq"', '"bulk-rnaseq-differential-expression"'),
    ('"deseq"', '"bulk-rnaseq-differential-expression"'),
    ('"rna-seq差异"', '"bulk-rnaseq-differential-expression"'),
    ('"转录组差异"', '"bulk-rnaseq-differential-expression"'),
    ('"hdwgcna"', '"hdwgcna"'),
    ('"高维wgcna"', '"hdwgcna"'),
    ('"bulk聚类"', '"bulk-omics-clustering"'),
    ('"counts to de"', '"bulk-rnaseq-counts-to-de-deseq2"'),
    # ATAC
    ('"atac全流程"', '"atac-seq-memomics"'),
    ('"atac-seq"', '"atac-seq-memomics"'),
    ('"chip atlas"', '"chip-atlas-target-genes"'),
    ('"chip-atlas"', '"chip-atlas-target-genes"'),
    ('"homer motif"', '"find_enriched_motifs_with_homer"'),
    ('"chip diff"', '"chip-atlas-diff-analysis"'),
    # Drug
    ('"fda安全"', '"analyze_fda_safety_signals"'),
    ('"药物安全"', '"analyze_fda_safety_signals"'),
    ('"fda safety"', '"analyze_fda_safety_signals"'),
    ('"药物联用"', '"check_drug_combination_safety"'),
    ('"drug combination"', '"check_drug_combination_safety"'),
    ('"fda召回"', '"check_fda_drug_recalls"'),
    ('"临床试验"', '"clinicaltrials-landscape"'),
    ('"clinical trial"', '"clinicaltrials-landscape"'),
    ('"药物反应"', '"drug-response"'),
    ('"drug response"', '"drug-response"'),
    ('"药物标签"', '"get_fda_drug_label_info"'),
    # Genetics
    ('"crispr编辑"', '"analyze_crispr_genome_editing"'),
    ('"变异注释"', '"genetic-variant-annotation"'),
    ('"twas"', '"gwas-to-function-twas"'),
    ('"孟德尔随机化"', '"mendelian-randomization-twosamplemr"'),
    ('"mendelian randomization"', '"mendelian-randomization-twosamplemr"'),
    ('"prs"', '"polygenic-risk-score-prs-catalog"'),
    ('"多基因风险"', '"polygenic-risk-score-prs-catalog"'),
    ('"基因必需"', '"gene-essentiality"'),
    ('"gene essential"', '"gene-essentiality"'),
    # Lab
    ('"质粒注释"', '"annotate_plasmid"'),
    ('"引物设计"', '"design_primer"'),
    ('"primer design"', '"design_primer"'),
    ('"验证引物"', '"design_verification_primers"'),
    ('"限制酶"', '"find_restriction_enzymes"'),
    ('"酶切位点"', '"find_restriction_sites"'),
    ('"enzyme cut"', '"find_restriction_sites"'),
    ('"酶切"', '"find_restriction_enzymes"'),
    ('"gwas catalog"', '"query_gwas_catalog"'),
    ('"ppt生成"', '"ppt-html"'),
    ('"生存临床"', '"survival-analysis-clinical"'),
    # Spatial / Multi-omics
    ('"spatial"', '"spatial-transcriptomics"'),
    ('"多组学"', '"multi-omics-integration"'),
    ('"多组学整合"', '"multi-omics-integration"'),
    ('"multi omics"', '"multi-omics-integration"'),
    ('"整合分析"', '"multi-omics-integration"'),
]

added = 0
for key, val in new_aliases:
    if key not in c:
        # Insert before closing brace of CHINESE_ALIASES
        marker = '"网络药理学": "drug-target-prediction",\n}'
        insert_line = f'    {key}: {val},\n'
        if marker in c:
            c = c.replace(marker, f'    {key}: {val},\n{marker}')
            added += 1

print(f'Added {added} new aliases')

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(c)

aliases = re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', c[c.find('CHINESE_ALIASES'):])
print(f'Total CHINESE_ALIASES: {len(aliases)}')
