#!/usr/bin/env python3
"""Fix all 276 SKILL.md category fields to align with SOUL.md 15-category system."""
from pathlib import Path
import re

OLD_TO_NEW = {
    'transcriptomics': 'scRNA', 'decontamination': 'scRNA', 'functional_analysis': 'scRNA',
    'pathway_analysis': 'scRNA', 'bioinformatics': 'scRNA', 'aging': 'scRNA',
    'epigenomics': 'scATAC', 'spatial': 'Spatial', 'spatial_transcriptomics': 'Spatial',
    'bulk_rna': 'Bulk RNA', 'bulk': 'Bulk RNA',
    'proteomics': 'Proteomics', 'proteomics_metabolomics': 'Proteomics',
    'drug_discovery': 'Drug Discovery', 'drug': 'Drug Discovery',
    'microbiome': 'Microbiome', 'microbiology': 'Microbiome', 'metagenomics': 'Microbiome',
    'multi_omics': 'Multi-omics', 'integration': 'Multi-omics',
    'clinical': 'Clinical', 'survival': 'Clinical',
    'genomics': 'GWAS/Genetics', 'genomics_genetics': 'GWAS/Genetics',
    'genetics': 'GWAS/Genetics', 'functional_genomics': 'GWAS/Genetics', 'gwas': 'GWAS/Genetics',
    'data_retrieval': 'Data Query', 'data_discovery': 'Data Query',
    'literature': 'Literature', 'literature_search': 'Literature',
    'visualization': 'Visualization', 'reporting': 'Visualization',
    'general': 'General Utility', 'system': 'General Utility', 'meta': 'General Utility',
    'data_analysis': 'General Utility', 'experimental_design': 'General Utility',
    'machine_learning': 'General Utility',
    'immunology': 'Immunology',
    'mol_bio': 'Mol Bio', 'molecular_biology': 'Mol Bio', 'molecular_design': 'Mol Bio',
    'assay': 'Assay/Wet Lab', 'wet_lab': 'Assay/Wet Lab', 'lab': 'Assay/Wet Lab',
    'imaging': 'Imaging', 'histology': 'Imaging',
    'simulation': 'Simulation',
}

INDIVIDUAL = {
    'align_sequences': 'Mol Bio', 'analyze_protein_conservation': 'Mol Bio',
    'analyze_rna_secondary_structure_features': 'Mol Bio', 'annotate_open_reading_frames': 'Mol Bio',
    'annotate_plasmid': 'Mol Bio', 'design_golden_gate_oligos': 'Mol Bio',
    'design_knockout_sgrna': 'Mol Bio', 'design_primer': 'Mol Bio',
    'design_verification_primers': 'Mol Bio', 'digest_sequence': 'Mol Bio',
    'find_restriction_enzymes': 'Mol Bio', 'find_restriction_sites': 'Mol Bio',
    'find_sequence_mutations': 'Mol Bio', 'get_golden_gate_assembly_protocol': 'Mol Bio',
    'get_oligo_annealing_protocol': 'Mol Bio', 'golden_gate_assembly': 'Mol Bio',
    'pcr_simple': 'Mol Bio', 'sgrna-design': 'Mol Bio',
    'analyze_circular_dichroism_spectra': 'Proteomics', 'analyze_itc_binding_thermodynamics': 'Proteomics',
    'analyze_protease_kinetics': 'Proteomics', 'compare_protein_structures': 'Proteomics',
    'model_protein_dimerization_network': 'Proteomics', 'simulate_protein_signaling_network': 'Proteomics',
    'proteomics-diff-exp': 'Proteomics',
    'analyze_enzyme_kinetics_assay': 'Assay/Wet Lab', 'get_bacterial_transformation_protocol': 'Assay/Wet Lab',
    'multi-omics-integration': 'Multi-omics', 'rgcca-multiblock': 'Multi-omics',
    'disease-progression-longitudinal': 'Clinical', 'survival-analysis-clinical': 'Clinical',
    'perform_flux_balance_analysis': 'Drug Discovery', 'simulate_metabolic_network_perturbation': 'Drug Discovery',
    'simulate_renin_angiotensin_system_dynamics': 'Drug Discovery', 'lipidomics-summary-stats': 'Drug Discovery',
    'get_gene_coding_sequence': 'Data Query', 'get_plasmid_sequence': 'Data Query', 'query_chatnt': 'Data Query',
    'lasso-biomarker-panel': 'scRNA', 'upstream-regulator-analysis': 'scRNA',
    'scrna-disease-drug-discovery': 'scRNA', 'senescence-detection': 'scRNA', 'sasp-scoring': 'scRNA',
    'stratified-subsampling': 'scRNA', 'pooled-crispr-screens': 'scRNA',
    'doubletfinder-remove-doublets': 'scRNA', 'cellbender-remove-background': 'scRNA', 'soupx-remove-background': 'scRNA',
    'bulk-omics-clustering': 'Bulk RNA', 'functional-enrichment-from-degs': 'Bulk RNA',
    'bioinformatics-html-report': 'Visualization', 'knowledge-base-curation': 'General Utility',
    'literature-param-extraction': 'Literature', 'literature-preclinical': 'Literature',
    'literature-review': 'Literature', 'phylo-create-skill': 'General Utility',
    'immune-deconvolution': 'Immunology', 'analyze_ebv_antibody_titers': 'Immunology',
    'html-report': 'Visualization', 'data-viz': 'Visualization', 'ppt-generator': 'Visualization',
    'ppt-html': 'Visualization', 'ppt-master': 'Visualization', 'pptx-generation': 'Visualization',
    'pdf-report-generation': 'Visualization', 'analysis-summary-report': 'General Utility',
    'heart-conference-monitor': 'General Utility',
    'code-writer': 'General Utility', 'paper-translate': 'General Utility',
    'file-convert': 'General Utility', 'web-research': 'General Utility',
    'academic-paper-writing': 'General Utility', 'pdf_reader': 'General Utility',
    'extract_pdf_content': 'General Utility', 'pdf-translate': 'General Utility',
    'pcr-primer-design': 'Mol Bio', 'phylogenetics-toolkit': 'GWAS/Genetics',
    'analyze_cns_lesion_histology': 'Immunology', 'analyze_cfse_cell_proliferation': 'Immunology',
    'isolate_purify_immune_cells': 'Immunology', 'analyze_immunohistochemistry_image': 'Assay/Wet Lab',
    'perform_facs_cell_sorting': 'Assay/Wet Lab', 'perform_pcr_and_gel_electrophoresis': 'Assay/Wet Lab',
    'batch_register_images': 'Imaging', 'analyze_radiolabeled_antibody_biodistribution': 'Imaging',
    'segment_and_quantify_cells_in_multiplexed_images': 'Clinical',
    'analyze_aortic_diameter_and_geometry': 'Clinical', 'analyze_bone_microct_morphometry': 'Clinical',
    'analyze_thrombus_histology': 'Clinical', 'perform_cosinor_analysis': 'Clinical',
    'quantify_amyloid_beta_plaques': 'Clinical', 'quantify_corneal_nerve_fibers': 'Clinical',
    'simulate_thyroid_hormone_pharmacokinetics': 'Clinical', 'analyze_abr_waveform_p1_metrics': 'Clinical',
    'step4-generate-final-report': 'Visualization',
}

skills_dir = Path('hermes_home/skills/bioinformatics')
fixed = 0
skipped = 0
new_dist = {}

for d in sorted(skills_dir.iterdir()):
    if not d.is_dir(): continue
    md = d / 'SKILL.md'
    if not md.exists(): continue

    content = md.read_text('utf-8')
    cat_m = re.search(r'category:\s*"?([^"\n]+)"?', content)

    if not cat_m:
        new_cat = INDIVIDUAL.get(d.name, 'General Utility')
        content = re.sub(r'(tags:\s*\[.*?\])\n', f'category: {new_cat}\n\\1\n', content)
        md.write_text(content, 'utf-8')
        fixed += 1
        new_dist[new_cat] = new_dist.get(new_cat, 0) + 1
        continue

    old_cat = cat_m.group(1).strip()
    old_cat_lower = old_cat.lower()

    if d.name in INDIVIDUAL:
        new_cat = INDIVIDUAL[d.name]
    elif old_cat_lower in OLD_TO_NEW:
        new_cat = OLD_TO_NEW[old_cat_lower]
    else:
        new_cat = old_cat

    if new_cat != old_cat:
        content = re.sub(rf'category:\s*"?{re.escape(old_cat)}"?', f'category: {new_cat}', content)
        md.write_text(content, 'utf-8')
        fixed += 1
    else:
        skipped += 1

    new_dist[new_cat] = new_dist.get(new_cat, 0) + 1

print(f"Fixed: {fixed}, Unchanged: {skipped}")
print("\nNew distribution:")
for cat, cnt in sorted(new_dist.items(), key=lambda x: -x[1]):
    print(f"  {cat:<20} {cnt:>3}")
print(f"\nTotal: {sum(new_dist.values())}")
print(f"Categories: {len(new_dist)}")
