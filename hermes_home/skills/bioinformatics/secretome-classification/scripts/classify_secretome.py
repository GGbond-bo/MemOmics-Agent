"""
Secretome Protein Classification Pipeline

Classifies proteins from conditioned medium proteomics into:
  Class I: Free Soluble | Class II: Dual (Free+EV) | Class III: EV Cargo | Class IV: Background

Usage:
  python classify_secretome.py <input.xlsx> [--sheet report.pg_matrix]
                                [--id_col Protein.Ids] [--gene_col Genes]
                                [--sample_cols test1,test2]
                                [--output_dir results/secretome/]
"""
import pandas as pd
import numpy as np
import urllib.request, urllib.parse
import json, time, os, sys

# ========== EV KNOWN DATABASE ==========
EV_KNOWN = {
    'HSP90AA1','HSP90AB1','HSPA8','HSPA5','HSPA1A','HSPD1','HSPA9','HSPE1',
    'GAPDH','PKM','PGK1','ENO1','ALDOA','LDHA','LDHB','TPI1','GPI',
    'ACTB','ACTG1','ACTA2','TUBB','TUBA1B','TUBA1C',
    'ANXA2P2','PHB1','PHB2',
    'APOE','CLU','FN1',
    'COL1A1','COL1A2','COL3A1','COL6A1','SPARC','LUM','CST3',
    'PRDX1','PRDX6','TXN',
    'YWHAE','YWHAQ','YWHAZ',
    'CFL1','PFN1','EZR',
    'HNRNPA2B1','HNRNPK','PTBP1','YBX1',
    'RPS2','RPS12','RPS28','RPL3','RPL6','RPL17',
    'EEF1A1','FLNA','PLEC','FSCN1','IQGAP1',
    'CD9','CD63','CD81','TSG101','PDCD6IP','FLOT1','FLOT2','ANXA5','GANAB',
}

PSEUDOGENES = {'HNRNPA1L3', 'ANXA2P2'}
HISTONES = {'H2BC12', 'H2AC4', 'H4C1'}
KERATINS = {'KRT1','KRT2','KRT5','KRT6A','KRT8','KRT9','KRT10','KRT14','KRT15','KRT18'}
RIBOSOMAL = {'RPS2','RPS12','RPS28','RPL3','RPL6','RPL17'}


def query_uniprot_batch(uniprot_ids, cache_path=None):
    """Batch query UniProt REST API for signal peptide, subcellular location, secreted status."""
    if cache_path and os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)
    
    results = {}
    batch_size = 100
    for i in range(0, len(uniprot_ids), batch_size):
        batch = uniprot_ids[i:i+batch_size]
        query_str = ' OR '.join([f'accession:{uid}' for uid in batch])
        url = 'https://rest.uniprot.org/uniprotkb/search'
        params = {
            'query': query_str, 'format': 'json', 'size': batch_size,
            'fields': 'accession,gene_names,cc_subcellular_location,ft_signal,keyword'
        }
        try:
            req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            for entry in data.get('results', []):
                acc = entry['primaryAccession']
                genes = ';'.join([g.get('geneName',{}).get('value','') 
                                  for g in entry.get('genes',[])]) if entry.get('genes') else ''
                has_signal = False
                for feat in entry.get('features', []):
                    if feat.get('type') == 'Signal':
                        has_signal = True; break
                sub_locs = []
                for comment in entry.get('comments', []):
                    if comment.get('commentType') == 'SUBCELLULAR LOCATION':
                        for loc in comment.get('subcellularLocations', []):
                            v = loc.get('location', {}).get('value', '')
                            if v: sub_locs.append(v)
                keywords = [kw.get('name','') for kw in entry.get('keywords', [])]
                is_secreted = ('Secreted' in sub_locs or 
                               'secreted' in ' '.join(keywords).lower() or
                               'Secreted' in keywords)
                results[acc] = {
                    'gene': genes, 'signal_peptide': has_signal,
                    'subcellular_locations': '; '.join(sub_locs),
                    'keywords': '; '.join(keywords[:10]), 'is_secreted': is_secreted,
                }
            time.sleep(0.5)
        except Exception as e:
            print(f"Error batch {i//batch_size}: {e}")
    
    if cache_path:
        with open(cache_path, 'w') as f:
            json.dump(results, f, indent=2)
    return results


def classify_protein(row, uniprot_annotations):
    """Classify a single protein row."""
    uid = row.get('Protein.Ids', '')
    gene = str(row.get('Genes', ''))
    up_info = uniprot_annotations.get(uid, {})
    has_signal = up_info.get('signal_peptide', False)
    is_secreted = up_info.get('is_secreted', False)
    keywords = up_info.get('keywords', '').lower()
    
    if gene in PSEUDOGENES or gene in HISTONES:
        return 'IV-A: Pseudogene/Histone'
    if gene in KERATINS:
        return 'IV-B: Keratin (possible contamination)'
    if gene in RIBOSOMAL:
        return 'IV-C: Ribosomal (cell debris)'
    
    in_ev_db = gene in EV_KNOWN
    ev_keyword = any(kw in keywords for kw in ['extracellular vesicle','exosome','microvesicle'])
    
    if not has_signal and not is_secreted and (in_ev_db or ev_keyword):
        return 'III: EV/Exosome Cargo'
    if has_signal and is_secreted and (in_ev_db or ev_keyword):
        return 'II: Dual (Free + EV)'
    if has_signal and is_secreted:
        return 'I: Free Soluble'
    if not has_signal and not is_secreted:
        return 'IV-D: Intracellular (stress/leakage)'
    return 'Unclassified'


def run_pipeline(input_path, sheet='report.pg_matrix', output_dir='results/secretome/'):
    """Main pipeline: read data → query UniProt → classify → export."""
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Read data
    df = pd.read_excel(input_path, sheet_name=sheet)
    uniprot_ids = df['Protein.Ids'].dropna().unique().tolist()
    print(f"Loaded {len(df)} proteins, {len(uniprot_ids)} unique UniProt IDs")
    
    # 2. Query UniProt
    cache = os.path.join(output_dir, 'uniprot_cache.json')
    annotations = query_uniprot_batch(uniprot_ids, cache)
    print(f"Fetched {len(annotations)} UniProt annotations")
    
    # 3. Classify
    df['classification'] = df.apply(lambda r: classify_protein(r, annotations), axis=1)
    
    # 4. Compute derived columns
    for col in ['test1', 'test2']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'test1' in df.columns and 'test2' in df.columns:
        df['log2FC'] = np.log2((df['test1'] + 1) / (df['test2'] + 1))
        df['avg_intensity'] = np.log10((df['test1'] + df['test2']) / 2 + 1)
    
    # 5. Summary
    print("\n" + "="*60)
    for cls in sorted(df['classification'].unique()):
        n = (df['classification'] == cls).sum()
        print(f"  {cls}: {n} proteins")
    print("="*60)
    
    # 6. Export
    out = os.path.join(output_dir, 'classified_proteins.csv')
    cols = ['Genes', 'Protein names', 'classification'] + \
           [c for c in ['test1', 'test2', 'log2FC', 'avg_intensity'] if c in df.columns]
    df[cols].to_csv(out, index=False)
    print(f"\nExported: {out}")
    return df, annotations


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python classify_secretome.py <input.xlsx> [output_dir]")
        sys.exit(1)
    run_pipeline(sys.argv[1], output_dir=sys.argv[2] if len(sys.argv)>2 else 'results/secretome/')
