import sys, importlib.util, re, json
from pathlib import Path
from collections import defaultdict

PROJECT = Path('E:/MemOmics-Agent')
spec = importlib.util.spec_from_file_location('hs', PROJECT / 'hermes-agent' / 'tools' / 'hybrid_search.py')
hs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hs)
m = hs.HybridMatcher(skills_dir=str(PROJECT / 'hermes_home' / 'skills' / 'bioinformatics'))

FULL_MAP = {
    'transcriptomics':'scRNA','scrna':'scRNA','single_cell':'scRNA',
    'decontamination':'scRNA','functional_analysis':'scRNA','aging':'scRNA',
    'integration':'scRNA','pathway_analysis':'scRNA','bioinformatics':'scRNA',
    'genomics':'GWAS/Genetics','genetics':'GWAS/Genetics','gwas':'GWAS/Genetics',
    'genomics_genetics':'GWAS/Genetics','functional_genomics':'GWAS/Genetics',
    'drug':'Drug','drug_discovery':'Drug',
    'clinical':'Clinical','survival':'Clinical',
    'proteomics':'Protein','proteomics_metabolomics':'Protein',
    'microbiome':'Microbiome','microbiology':'Microbiome','metagenomics':'Microbiome',
    'immunology':'Immunology',
    'literature':'Literature',
    'visualization':'Vis/Report','reporting':'Vis/Report',
    'data_retrieval':'Data Query','data_discovery':'Data Query',
    'general':'General','data_analysis':'General',
    'machine_learning':'ML','molecular_design':'Mol Bio',
    'experimental_design':'Experimental',
    'imaging':'Imaging','histology':'Imaging',
    'simulation':'Simulation','meta':'Meta','system':'Meta',
    'assay':'Assay','wet_lab':'Assay',
    'epigenomics':'scATAC','atac':'scATAC',
    'spatial':'Spatial','bulk':'Bulk RNA','bulk_rna':'Bulk RNA',
}

skills_dir = PROJECT / 'hermes_home' / 'skills' / 'bioinformatics'
by_cat = defaultdict(lambda: dict(total=0, miss=0, miss_names=[]))

for d in sorted(skills_dir.iterdir()):
    if not d.is_dir(): continue
    md = d / 'SKILL.md'
    if not md.exists(): continue
    try:
        content = md.read_text('utf-8')
        when_m = re.search(r'when_to_use:\s*"([^"]+)"', content)
        cat_m = re.search(r'category:\s*"?([^"\n]+)"?', content)
        wtu = when_m.group(1).strip() if when_m else ''
        raw_cat = cat_m.group(1).strip().lower() if cat_m else 'unknown'
        
        disp_cat = 'Other'
        for k, v in FULL_MAP.items():
            if k in raw_cat:
                disp_cat = v
                break
        
        query = wtu if wtu and len(wtu) >= 10 else d.name
        query = re.sub(r'\s+', ' ', query).strip()[:80]
        
        sr = m.search(query, top_k=10)
        ranked = sr.get('results', [])[:5] if isinstance(sr, dict) else []
        td = d.name.lower().replace('_', '-').replace(' ', '-')
        
        hit3 = any(
            td in rn.get('name', '').lower().replace('_', '-').replace(' ', '-') or
            rn.get('name', '').lower().replace('_', '-').replace(' ', '-') in td
            for rn in ranked[:3]
        )
        
        by_cat[disp_cat]['total'] += 1
        if not hit3:
            by_cat[disp_cat]['miss'] += 1
            by_cat[disp_cat]['miss_names'].append(d.name)
    except:
        pass

TARGETS = ['Clinical', 'Drug', 'Protein', 'Microbiome', 'Immunology', 'Data Query', 'General']

print("{:<16} {:>5} {:>5} {:>5} {:>6}".format("Category", "Total", "Hit", "Miss", "Hit%"))
print('-' * 50)
for cat in sorted(by_cat.keys()):
    d = by_cat[cat]
    total = d['total']
    miss = d['miss']
    hit = total - miss
    pct = hit / total * 100 if total else 0
    marker = ' <<<' if cat in TARGETS else ''
    print("{:<16} {:>5} {:>5} {:>5} {:>5.1f}%{}".format(cat, total, hit, miss, pct, marker))

total = sum(d['total'] for d in by_cat.values())
total_hit = total - sum(d['miss'] for d in by_cat.values())
print('-' * 50)
print("TOTAL           {:>5} {:>5} {:>5} {:>5.1f}%".format(total, total_hit, total - total_hit, total_hit / total * 100))

for cat in TARGETS:
    d = by_cat.get(cat)
    if d and d['miss_names']:
        print("\n--- {} misses ({}) ---".format(cat, d['miss']))
        for n in d['miss_names'][:8]:
            print("  {}".format(n))
