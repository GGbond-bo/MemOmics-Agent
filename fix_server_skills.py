#!/usr/bin/env python3
"""Update server.py list_skills to use SKILL.md category field (18-class system)."""
import re

with open('webui/server.py', 'r', encoding='utf-8') as f:
    c = f.read()

# 1. Replace JSON_CATEGORY_MAP
old_map = '''    JSON_CATEGORY_MAP = {
        "scrna": "scRNA-seq", "scrna-seq": "scRNA-seq", "single-cell": "scRNA-seq",
        "atac": "scATAC-seq", "scatac": "scATAC-seq", "epigenomics": "scATAC-seq",
        "spatial": "空间转录组", "spatial-omics": "空间转录组",
        "bulk": "Bulk RNA-seq", "bulk-rnaseq": "Bulk RNA-seq",
        "methylation": "表观/甲基化", "epigenome": "表观/甲基化", "chipseq": "表观/甲基化",
        "proteomics": "蛋白/代谢", "metabolomics": "蛋白/代谢", "lipidomics": "蛋白/代谢",
        "microbial": "微生物/基因组", "genomics": "微生物/基因组", "variant": "微生物/基因组",
        "integration": "多组学整合", "multiome": "多组学整合",
        "report": "报告/工具", "tool": "报告/工具", "visualization": "报告/工具",
    }'''

new_map = '''    JSON_CATEGORY_MAP = {
        "scrna": "scRNA", "scRNA": "scRNA",
        "scatac": "scATAC", "scATAC": "scATAC",
        "Spatial": "Spatial", "spatial": "Spatial",
        "Bulk RNA": "Bulk RNA", "bulk rna": "Bulk RNA",
        "Proteomics": "Proteomics", "proteomics": "Proteomics",
        "Drug Discovery": "Drug Discovery", "drug discovery": "Drug Discovery",
        "Microbiome": "Microbiome", "microbiome": "Microbiome",
        "Multi-omics": "Multi-omics", "multi-omics": "Multi-omics",
        "Clinical": "Clinical", "clinical": "Clinical",
        "GWAS/Genetics": "GWAS/Genetics", "gwas/genetics": "GWAS/Genetics",
        "Data Query": "Data Query", "data query": "Data Query",
        "Literature": "Literature", "literature": "Literature",
        "Visualization": "Visualization", "visualization": "Visualization",
        "General Utility": "General Utility", "general utility": "General Utility",
        "Immunology": "Immunology", "immunology": "Immunology",
        "Mol Bio": "Mol Bio", "mol bio": "Mol Bio",
        "Assay/Wet Lab": "Assay/Wet Lab", "assay/wet lab": "Assay/Wet Lab",
        "Imaging": "Imaging", "imaging": "Imaging",
        "Structural Biology": "Structural Biology", "structural biology": "Structural Biology",
        "Histology/Pathology": "Histology/Pathology", "histology/pathology": "Histology/Pathology",
        "Bioimaging": "Bioimaging", "bioimaging": "Bioimaging",
    }'''

c = c.replace(old_map, new_map)

# 2. Add SKILL.md category check at the TOP of _categorize function
old_fn_start = '''    def _categorize(name, skill_json_data, skill_md_content="", desc=""):
        nl = name.lower()
        combined = (nl + " " + desc.lower())
        # 0. 名字优先: 如果名字明确包含 scrna/seurat/scanpy, 直接分到 scRNA-seq'''

new_fn_start = '''    def _categorize(name, skill_json_data, skill_md_content="", desc=""):
        nl = name.lower()
        # 0. SKILL.md category 字段优先 (对齐 SOUL.md 18 类系统)
        if skill_md_content:
            cat_match = re.search(r'category:\\s*"?([^"\\n]+)"?', skill_md_content)
            if cat_match:
                cat_val = cat_match.group(1).strip()
                if cat_val in JSON_CATEGORY_MAP:
                    return JSON_CATEGORY_MAP[cat_val]
                if cat_val.lower() in JSON_CATEGORY_MAP:
                    return JSON_CATEGORY_MAP[cat_val.lower()]
        combined = (nl + " " + desc.lower())
        # 1. 名字关键词匹配'''

c = c.replace(old_fn_start, new_fn_start)

with open('webui/server.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("Done. JSON_CATEGORY_MAP updated + SKILL.md category priority added.")
