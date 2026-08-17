# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 此脚本由 MemOmics Agent 执行。原脚本永远不被修改。
#
# 执行前必须:
#   1. rail_review(action="pre")  — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs", script_name="本脚本名",
#      species="物种", tissue="组织", direction="方向")
#      → 查同类运行日志，有则参考已有参数和经验，无则按原脚本执行
#   3. debate_analysis(topic, context) — 参数不确定时多角色辩论
#
# 执行后必须:
#   1. rail_review(action="post") — 检查输出/质量/图表
#   2. 如果通过 → skill_evolution(action="record_run",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", params_used="参数JSON", result_summary="结果",
#      quality_score=8, notes="经验总结")
#      → 记录成功运行日志，供后续同类型分析参考
#   3. 如果失败 → skill_evolution(action="record_error",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", error_message="报错", root_cause="根因",
#      fix_applied="修复方案")
#      → 记录错误日志，修正后重跑
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

#!/usr/bin/env python3
"""
Integrate genetic evidence from multiple sources for disease-gene prioritization.

Queries four complementary genetic evidence databases and integrates results
into a unified per-gene genetic evidence summary:

  1. GeneBass — rare variant burden test results (pLoF, missense)
  2. TWAS Atlas (CNCB-NGDC) — published TWAS associations across traits/tissues
  3. EBI eQTL Catalogue — tissue-specific eQTL associations
  4. Open Targets L2G — locus-to-gene GWAS prioritization scores

The combined evidence feeds into a genetic sub-score used for target
prioritization in the scRNA-seq disease-drug discovery workflow.

Usage:
  python genetic_evidence.py --genes "IRF4,STAT4,BLK,TNFAIP3" --disease "systemic sclerosis"
  python genetic_evidence.py --genes "IRF4,STAT4" --disease "systemic sclerosis" --output genetic_evidence.json
  python genetic_evidence.py --gene-file gene_list.txt --disease "scleroderma" --no-genebass
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests",
          file=sys.stderr)
    sys.exit(1)

import urllib.parse
import urllib.request


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TWAS_ATLAS_BASE = "https://ngdc.cncb.ac.cn/twas"
EQTL_API_BASE = "https://www.ebi.ac.uk/eqtl/api/v2"
OT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"

REQUEST_DELAY = 0.5
MAX_RETRIES = 3

# Tissues relevant to SSc / autoimmune / fibrotic disease
EQTL_SKIN_IMMUNE_TISSUES = {
    "skin", "skin - sun exposed (lower leg)", "skin - not sun exposed (suprapubic)",
    "whole blood", "blood", "lymphocytes", "monocytes", "neutrophils",
    "T cells", "CD4+ T cells", "CD8+ T cells", "B cells", "NK cells",
    "macrophages", "dendritic cells", "LCL", "lymphoblastoid cell line",
    "PBMC", "spleen", "lung", "fibroblast", "fibroblasts",
}

# TWAS trait search terms — disease-specific only, no proxy diseases
SSC_RELATED_TRAITS = [
    "systemic sclerosis",
    "scleroderma",
    "pulmonary fibrosis",
    "interstitial lung disease",
    "Raynaud",
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _retry_request(func, *args, retries=MAX_RETRIES, delay=REQUEST_DELAY, **kwargs):
    """Execute a callable with exponential-backoff retry logic."""
    for attempt in range(retries):
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Retry {attempt + 1}/{retries} in {wait}s: {e}",
                      file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"  Request failed after {retries} attempts: {e}",
                      file=sys.stderr)
                return None


def _post_twas(endpoint, params):
    """POST to TWAS Atlas and return parsed JSON."""
    url = f"{TWAS_ATLAS_BASE}/{endpoint}"
    data = urllib.parse.urlencode(params).encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "scRNA-Disease-DrugDiscovery/1.0",
        "Accept": "application/json",
    }

    def _do_post():
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    return _retry_request(_do_post)


def _get_json(url, params=None):
    """GET request with retry logic using requests library."""
    def _do_get():
        resp = requests.get(
            url,
            params=params,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code == 429:
            raise Exception("Rate limited (429)")
        if resp.status_code in (404, 400, 422):
            return None
        resp.raise_for_status()
        return resp.json()

    return _retry_request(_do_get)


def _graphql_query(query, variables=None):
    """Execute a GraphQL query against Open Targets API with retry logic."""
    def _do_query():
        resp = requests.post(
            OT_GRAPHQL,
            json={"query": query, "variables": variables or {}},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code == 429:
            raise Exception("Rate limited (429)")
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            print(f"  GraphQL errors: {data['errors']}", file=sys.stderr)
            return None
        return data.get("data")

    return _retry_request(_do_query)


def _resolve_ensembl_id(symbol):
    """Look up Ensembl gene ID from gene symbol via Open Targets search."""
    query = """
    query SearchGene($symbol: String!) {
      search(queryString: $symbol, entityNames: ["target"], page: {index: 0, size: 5}) {
        hits {
          object {
            ... on Target {
              id
              approvedSymbol
            }
          }
        }
      }
    }
    """
    data = _graphql_query(query, {"symbol": symbol})
    if not data or not data.get("search", {}).get("hits"):
        return None

    for hit in data["search"]["hits"]:
        obj = hit.get("object", {})
        if obj and obj.get("approvedSymbol", "").upper() == symbol.upper():
            return obj["id"]

    # Fall back to first hit
    first = data["search"]["hits"][0]
    obj = first.get("object", {})
    return obj.get("id") if obj else None


# ---------------------------------------------------------------------------
# 1. GeneBass query
# ---------------------------------------------------------------------------

def query_genebass(gene_list, disease_name):
    """Search GeneBass filtered data for disease-related phenotype burden results.

    Checks data locations:
      1. /mnt/datalake/genebass/ (Biomni)
      2. ./genebass_output/ (local)

    Returns DataFrame of significant hits with columns:
      gene, phenotype, annotation, pvalue, beta, direction, tier

    Returns empty DataFrame if GeneBass data is unavailable.
    """
    gene_set = set(g.upper() for g in gene_list)
    data_dirs = [
        "/mnt/datalake/genebass",
        os.path.join(os.getcwd(), "genebass_output"),
        os.path.expanduser("~/Documents/GitHub/manny-rivas-stanford/genebass/genebass_output"),
    ]

    data_dir = None
    for d in data_dirs:
        if os.path.isdir(d):
            data_dir = d
            break

    if data_dir is None:
        print("  GeneBass data not found at any known location", file=sys.stderr)
        return pd.DataFrame(columns=["gene", "phenotype", "annotation",
                                      "pvalue", "beta", "direction", "tier"])

    print(f"  GeneBass data directory: {data_dir}", file=sys.stderr)

    # Try loading filtered pickle files
    hits = []
    for annotation in ["pLoF", "missense|LC"]:
        # Standard pickle naming conventions
        for suffix in [f"_filtered_{annotation.replace('|', '_')}.pkl",
                       f"_{annotation.replace('|', '_')}_filtered.pkl"]:
            pkl_path = None
            for fname in os.listdir(data_dir):
                if fname.endswith(".pkl") and annotation.replace("|", "_") in fname:
                    pkl_path = os.path.join(data_dir, fname)
                    break

            if pkl_path and os.path.exists(pkl_path):
                try:
                    df = pd.read_pickle(pkl_path)
                    print(f"    Loaded {annotation}: {len(df)} rows from {os.path.basename(pkl_path)}",
                          file=sys.stderr)

                    # Filter to disease-related phenotypes
                    disease_lower = disease_name.lower()
                    disease_terms = [disease_lower]
                    if "sclerosis" in disease_lower or "scleroderma" in disease_lower:
                        disease_terms.extend(["sclerosis", "scleroderma", "fibrosis",
                                              "raynaud", "interstitial lung"])

                    pheno_col = None
                    for col in ["pheno_description", "phenotype", "description"]:
                        if col in df.columns:
                            pheno_col = col
                            break

                    if pheno_col is None:
                        continue

                    mask = pd.Series(False, index=df.index)
                    for term in disease_terms:
                        mask |= df[pheno_col].str.contains(term, case=False, na=False)

                    # Filter to target genes
                    gene_col = None
                    for col in ["gene_symbol", "gene", "markerName"]:
                        if col in df.columns:
                            gene_col = col
                            break

                    if gene_col is None:
                        continue

                    mask &= df[gene_col].str.upper().isin(gene_set)
                    filtered = df.loc[mask].copy()

                    if len(filtered) == 0:
                        continue

                    # Extract relevant columns
                    pval_col = None
                    for col in ["Pvalue", "pvalue", "p_value", "Pvalue_Burden"]:
                        if col in filtered.columns:
                            pval_col = col
                            break

                    beta_col = None
                    for col in ["BETA_Burden", "beta", "BETA"]:
                        if col in filtered.columns:
                            beta_col = col
                            break

                    for _, row in filtered.iterrows():
                        pval = float(row[pval_col]) if pval_col else None
                        beta = float(row[beta_col]) if beta_col else None

                        # Assign tier
                        if pval is not None:
                            if pval < 2.5e-6:
                                tier = "bonferroni_significant"
                            elif pval < 1e-4:
                                tier = "fdr_supported"
                            else:
                                tier = "discovery_only"
                        else:
                            tier = "discovery_only"

                        # Direction from BETA sign
                        direction = "unknown"
                        if beta is not None:
                            direction = "inhibit" if beta < 0 else "activate"

                        hits.append({
                            "gene": row[gene_col],
                            "phenotype": row[pheno_col],
                            "annotation": annotation,
                            "pvalue": pval,
                            "beta": beta,
                            "direction": direction,
                            "tier": tier,
                        })
                    break  # Found the pickle for this annotation
                except Exception as e:
                    print(f"    Error loading {pkl_path}: {e}", file=sys.stderr)
                    continue

    result = pd.DataFrame(hits, columns=["gene", "phenotype", "annotation",
                                          "pvalue", "beta", "direction", "tier"])
    print(f"  GeneBass: {len(result)} hits for {len(result['gene'].unique()) if len(result) > 0 else 0} genes",
          file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# 2. TWAS Atlas query
# ---------------------------------------------------------------------------

def query_twas_atlas(gene_list, disease_name):
    """Query CNCB-NGDC TWAS Atlas POST API for disease-related TWAS associations.

    Searches for the disease directly plus related traits (fibrosis, autoimmune).

    Returns DataFrame with columns:
      gene, trait, tissue, zscore, pvalue, method
    """
    gene_set = set(g.upper() for g in gene_list)

    # Build search terms
    search_terms = [disease_name]
    disease_lower = disease_name.lower()
    if "sclerosis" in disease_lower or "scleroderma" in disease_lower:
        search_terms = SSC_RELATED_TRAITS
    elif any(term in disease_lower for term in ["fibrosis", "lung"]):
        search_terms.extend(["pulmonary fibrosis", "interstitial lung disease"])
    elif any(term in disease_lower for term in ["arthritis", "lupus", "autoimmune"]):
        search_terms.extend(["rheumatoid arthritis", "systemic lupus erythematosus",
                              "autoimmune"])

    # Deduplicate search terms
    seen = set()
    unique_terms = []
    for t in search_terms:
        t_lower = t.lower()
        if t_lower not in seen:
            seen.add(t_lower)
            unique_terms.append(t)

    all_associations = []

    for trait_term in unique_terms:
        print(f"  TWAS Atlas: searching '{trait_term}'...", file=sys.stderr, end="")

        # Step 1: Get studies for trait
        studies = _post_twas("traitpub", {"item": trait_term})
        if not studies:
            print(" no studies", file=sys.stderr)
            time.sleep(REQUEST_DELAY)
            continue

        print(f" {len(studies)} studies", file=sys.stderr)

        # Sort by association count, take top 5 per trait
        for s in studies:
            try:
                s["_n_assoc"] = int(s.get("assoc", 0))
            except (ValueError, TypeError):
                s["_n_assoc"] = 0
        studies.sort(key=lambda s: -s["_n_assoc"])
        studies = studies[:5]

        # Step 2: Get associations per study
        for s in studies:
            study_id = s.get("stuId", "")
            mapped_trait = s.get("mapTra", trait_term)
            method = s.get("method", "Unknown")

            assocs = _post_twas("traitassoc", {
                "item": study_id,
                "item1": mapped_trait,
                "item2": "0",  # all associations
            })
            time.sleep(REQUEST_DELAY)

            if not assocs:
                continue

            # Filter to target genes
            for a in assocs:
                gene_sym = a.get("geneSym", "")
                if gene_sym.upper() in gene_set:
                    try:
                        pval = float(a.get("pvalue", 1))
                    except (ValueError, TypeError):
                        pval = 1.0
                    try:
                        zscore = float(a.get("zscore", 0))
                    except (ValueError, TypeError):
                        zscore = None

                    all_associations.append({
                        "gene": gene_sym,
                        "trait": mapped_trait,
                        "tissue": a.get("tissue", "Unknown"),
                        "zscore": zscore,
                        "pvalue": pval,
                        "method": method,
                    })

    result = pd.DataFrame(all_associations,
                          columns=["gene", "trait", "tissue", "zscore", "pvalue", "method"])
    n_genes = result["gene"].nunique() if len(result) > 0 else 0
    print(f"  TWAS Atlas: {len(result)} associations for {n_genes} genes",
          file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# 3. eQTL Catalogue query
# ---------------------------------------------------------------------------

def query_eqtl_catalogue(gene_list, max_genes=30, max_tissues=5):
    """Query EBI eQTL Catalogue REST API for skin and immune tissue eQTLs.

    Optimized for Biomni execution timeouts:
    - Limited to max_genes (default 30) to keep API calls tractable
    - Limited to max_tissues (default 5) most disease-relevant tissues
    - Ensembl ID cache shared across queries

    Total API calls: ~max_genes × (1 resolve + max_tissues queries)
    At 0.5s rate limit: 30 × 6 = 180 calls × 0.5s = ~90 seconds

    Returns DataFrame with columns:
      gene, tissue, beta, pvalue, variant
    """
    # Limit gene list to avoid timeout (eQTL is supplementary evidence)
    if len(gene_list) > max_genes:
        print(f"  eQTL Catalogue: limiting to top {max_genes} genes "
              f"(of {len(gene_list)}) to avoid timeout", file=sys.stderr)
        gene_list = gene_list[:max_genes]

    # Pre-load datasets and filter to most relevant tissues only
    print("  eQTL Catalogue: loading datasets...", file=sys.stderr)
    datasets = _get_json(f"{EQTL_API_BASE}/datasets", params={"size": 500})
    if not datasets or not isinstance(datasets, list):
        print("  eQTL Catalogue: could not load datasets", file=sys.stderr)
        return pd.DataFrame(columns=["gene", "tissue", "beta", "pvalue", "variant"])

    # Priority tissues for SSc: skin and fibroblast first, then blood/immune
    PRIORITY_TISSUES = [
        "skin",         # Most relevant for SSc
        "fibroblast",   # Disease effector cell type
        "blood",        # Accessible tissue
        "pbmc",         # Immune cells
        "lung",         # SSc-ILD relevant
    ]

    relevant_datasets = []
    for d in datasets:
        if d.get("quant_method") != "ge":
            continue
        tissue = (d.get("tissue_label") or "").lower()
        for priority_term in PRIORITY_TISSUES:
            if priority_term in tissue:
                relevant_datasets.append((d, priority_term))
                break

    # Deduplicate: one dataset per priority tissue, take first match
    seen_priorities = set()
    representative = []
    for d, priority in relevant_datasets:
        if priority not in seen_priorities:
            seen_priorities.add(priority)
            representative.append(d)
        if len(representative) >= max_tissues:
            break

    print(f"  eQTL Catalogue: {len(representative)} tissue datasets "
          f"(limited to {max_tissues} most relevant)", file=sys.stderr)

    # Resolve Ensembl IDs (with caching — _resolve_ensembl_id may be called
    # from multiple functions, so cache at module level)
    ensembl_map = {}
    for gene in gene_list:
        eid = _resolve_ensembl_id(gene)
        if eid:
            ensembl_map[gene] = eid
        time.sleep(REQUEST_DELAY)

    print(f"  eQTL Catalogue: resolved {len(ensembl_map)}/{len(gene_list)} "
          f"Ensembl IDs", file=sys.stderr)

    all_eqtls = []
    n_total_queries = 0

    for gene, ensembl_id in ensembl_map.items():
        for ds in representative:
            ds_id = ds.get("dataset_id")
            tissue = ds.get("tissue_label", "unknown")
            if not ds_id:
                continue

            url = f"{EQTL_API_BASE}/datasets/{ds_id}/associations"
            data = _get_json(url, params={"gene_id": ensembl_id, "size": 10})
            n_total_queries += 1

            if data and isinstance(data, list):
                for assoc in data:
                    if assoc.get("gene_id") == ensembl_id:
                        beta = assoc.get("beta") or assoc.get("effect_size")
                        pval = assoc.get("pvalue") or assoc.get("p_value")
                        variant = (assoc.get("variant") or assoc.get("rsid")
                                   or assoc.get("variant_id"))
                        all_eqtls.append({
                            "gene": gene,
                            "tissue": tissue,
                            "beta": float(beta) if beta is not None else None,
                            "pvalue": float(pval) if pval is not None else None,
                            "variant": str(variant) if variant else None,
                        })

            if n_total_queries % 10 == 0:
                time.sleep(REQUEST_DELAY)

    result = pd.DataFrame(all_eqtls,
                          columns=["gene", "tissue", "beta", "pvalue", "variant"])

    # Filter by significance (p < 0.05)
    n_raw = len(result)
    if len(result) > 0 and "pvalue" in result.columns:
        result = result[result["pvalue"].notna() & (result["pvalue"] < 0.05)]

    n_genes = result["gene"].nunique() if len(result) > 0 else 0
    print(f"  eQTL Catalogue: {len(result)} significant associations "
          f"(of {n_raw} raw) for {n_genes} genes "
          f"({n_total_queries} API calls)", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# 3b. Open Targets Disease Genetics (GWAS + ClinVar + gene_burden)
# ---------------------------------------------------------------------------

# EFO IDs for SSc and related terms
SSC_EFO_IDS = [
    "EFO_0000717",   # systemic scleroderma (main)
    "MONDO_0016358",  # limited cutaneous SSc
    "EFO_0000404",    # diffuse scleroderma
]

OT_DISEASE_GENETICS_QUERY = """
query DiseaseGenetics($diseaseId: String!, $page: Int!) {
  disease(efoId: $diseaseId) {
    associatedTargets(page: { index: $page, size: 500 }) {
      count
      rows {
        target { id approvedSymbol }
        score
        datatypeScores { id score }
      }
    }
  }
}
"""


def query_ot_disease_genetics(gene_list, disease_name="systemic sclerosis",
                               disease_efo_ids=None):
    """Query Open Targets for disease-specific genetic association evidence.

    Retrieves GWAS, ClinVar, and gene burden evidence aggregated by Open Targets
    for the specified disease. This is the primary genetic evidence source when
    GeneBass has no hits for the disease.

    Args:
        gene_list: List of gene symbols to check
        disease_name: Disease name for EFO ID resolution
        disease_efo_ids: Explicit EFO IDs (overrides disease_name lookup)

    Returns:
        DataFrame with columns: gene, ensembl_id, ot_genetic_score,
        has_gwas_clinvar
    """
    if disease_efo_ids is None:
        disease_efo_ids = _resolve_disease_efo(disease_name)

    if not disease_efo_ids:
        print("  WARNING: Could not resolve disease EFO ID. "
              "Skipping OT disease genetics.", file=sys.stderr)
        return pd.DataFrame(columns=["gene", "ensembl_id", "ot_genetic_score",
                                      "has_gwas_clinvar"])

    gene_set = {g.upper() for g in gene_list}

    # Query all disease-associated targets and filter to our gene list
    all_results = []
    for efo_id in disease_efo_ids:
        print(f"  OT Disease Genetics: querying {efo_id}...", file=sys.stderr)
        for page in range(8):  # Max ~4000 targets
            data = _graphql_query(OT_DISEASE_GENETICS_QUERY,
                                   {"diseaseId": efo_id, "page": page})
            if not data or not data.get("disease"):
                break
            rows = data["disease"]["associatedTargets"].get("rows", [])
            if not rows:
                break

            for row in rows:
                gene = row["target"]["approvedSymbol"]
                if gene.upper() not in gene_set:
                    continue

                dtypes = {d["id"]: d["score"]
                          for d in row.get("datatypeScores", [])}
                gen_score = dtypes.get("genetic_association", 0)
                if gen_score > 0:
                    all_results.append({
                        "gene": gene,
                        "ensembl_id": row["target"]["id"],
                        "ot_genetic_score": gen_score,
                        "has_gwas_clinvar": True,
                    })

            time.sleep(REQUEST_DELAY)

    # Deduplicate: keep highest score per gene
    result = pd.DataFrame(all_results,
                           columns=["gene", "ensembl_id", "ot_genetic_score",
                                    "has_gwas_clinvar"])
    if len(result) > 0:
        result = result.sort_values("ot_genetic_score", ascending=False)
        result = result.drop_duplicates(subset="gene", keep="first")

    n_genes = len(result)
    print(f"  OT Disease Genetics: {n_genes} genes with GWAS/ClinVar/burden "
          f"evidence for {disease_name}", file=sys.stderr)

    return result


def _resolve_disease_efo(disease_name):
    """Resolve disease name to EFO IDs via Open Targets search."""
    # Check common SSc terms first
    name_lower = disease_name.lower()
    if any(kw in name_lower for kw in ["sclerosis", "scleroderma", "ssc"]):
        return SSC_EFO_IDS

    # Search Open Targets
    search_q = """
    query SearchDisease($q: String!) {
      search(queryString: $q, entityNames: ["disease"]) {
        hits { id name entity }
      }
    }
    """
    data = _graphql_query(search_q, {"q": disease_name})
    if not data or not data.get("search", {}).get("hits"):
        return []

    efo_ids = []
    for hit in data["search"]["hits"]:
        if hit.get("entity") == "disease":
            efo_ids.append(hit["id"])
            if len(efo_ids) >= 3:
                break
    return efo_ids


# ---------------------------------------------------------------------------
# 4. Open Targets L2G query
# ---------------------------------------------------------------------------

def query_ot_l2g(gene_list, disease_efo_ids=None, max_genes=50):
    """Query Open Targets L2G (locus-to-gene) scores via GraphQL.

    Limited to max_genes to avoid timeout (each gene requires 2-3 API calls).

    Returns DataFrame with columns:
      gene, study, l2g_score, pvalue, beta, odds_ratio, variant_rsid, etc.
    """
    if len(gene_list) > max_genes:
        print(f"  L2G: limiting to top {max_genes} genes (of {len(gene_list)})",
              file=sys.stderr)
        gene_list = gene_list[:max_genes]

    # Resolve Ensembl IDs
    ensembl_map = {}
    for gene in gene_list:
        eid = _resolve_ensembl_id(gene)
        if eid:
            ensembl_map[gene] = eid
        time.sleep(REQUEST_DELAY)

    all_l2g = []

    for gene, ensembl_id in ensembl_map.items():
        print(f"    L2G: querying {gene} ({ensembl_id})...", file=sys.stderr)

        # Get associated diseases with L2G evidence
        assoc_query = """
        query AssociatedDiseases($id: String!) {
          target(ensemblId: $id) {
            associatedDiseases(page: {index: 0, size: 20}) {
              rows {
                disease {
                  id
                  name
                }
                score
              }
            }
          }
        }
        """
        data = _graphql_query(assoc_query, {"id": ensembl_id})
        if not data or not data.get("target"):
            time.sleep(REQUEST_DELAY)
            continue

        diseases = data["target"].get("associatedDiseases", {}) or {}
        rows = diseases.get("rows", []) or []

        # Filter to disease EFO IDs if provided, otherwise use all
        efo_ids = []
        for r in rows:
            d = r.get("disease", {})
            if d.get("id"):
                if disease_efo_ids is None or d["id"] in disease_efo_ids:
                    efo_ids.append(d["id"])

        if not efo_ids:
            time.sleep(REQUEST_DELAY)
            continue

        time.sleep(REQUEST_DELAY)

        # Query evidence with full statistics (L2G + p-values + effect sizes)
        evidence_query = """
        query GeneticEvidence($id: String!, $efoIds: [String!]!) {
          target(ensemblId: $id) {
            evidences(
              efoIds: $efoIds
              datasourceIds: ["gwas_credible_sets", "eva", "gene_burden"]
              size: 100
            ) {
              rows {
                score
                resourceScore
                pValueMantissa
                pValueExponent
                beta
                oddsRatio
                variantRsId
                variantFunctionalConsequence { label }
                studyId
                datasourceId
                disease {
                  id
                  name
                }
              }
            }
          }
        }
        """
        ev_data = _graphql_query(evidence_query, {"id": ensembl_id, "efoIds": efo_ids})
        time.sleep(REQUEST_DELAY)

        if ev_data and ev_data.get("target"):
            ev_rows = (ev_data["target"].get("evidences", {}) or {}).get("rows", []) or []
            for r in ev_rows:
                disease = r.get("disease", {}) or {}
                score = r.get("score") or r.get("resourceScore")
                if score is None:
                    continue

                # Compute p-value from mantissa and exponent
                mantissa = r.get("pValueMantissa")
                exponent = r.get("pValueExponent")
                pvalue = None
                if mantissa is not None and exponent is not None:
                    try:
                        pvalue = float(mantissa) * (10 ** float(exponent))
                    except (TypeError, ValueError):
                        pvalue = None

                # Variant consequence
                vc = r.get("variantFunctionalConsequence", {}) or {}
                vc_label = vc.get("label") if isinstance(vc, dict) else None

                all_l2g.append({
                    "gene": gene,
                    "study": disease.get("name", disease.get("id", "")),
                    "l2g_score": round(float(score), 4),
                    "pvalue": pvalue,
                    "p_mantissa": mantissa,
                    "p_exponent": exponent,
                    "beta": r.get("beta"),
                    "odds_ratio": r.get("oddsRatio"),
                    "variant_rsid": r.get("variantRsId"),
                    "variant_consequence": vc_label,
                    "study_id": r.get("studyId"),
                    "datasource_id": r.get("datasourceId"),
                })

    result = pd.DataFrame(all_l2g, columns=[
        "gene", "study", "l2g_score", "pvalue", "p_mantissa", "p_exponent",
        "beta", "odds_ratio", "variant_rsid", "variant_consequence",
        "study_id", "datasource_id",
    ])
    n_genes = result["gene"].nunique() if len(result) > 0 else 0
    print(f"  Open Targets L2G: {len(result)} evidence rows for {n_genes} genes "
          f"(with p-values, betas, variant annotations)", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# GWAS Gene Landscape (independent of scRNAseq candidate list)
# ---------------------------------------------------------------------------

def get_top_gwas_genes(disease_name="systemic sclerosis", n=20):
    """Query Open Targets for top GWAS-associated genes for a disease.

    This is independent of the scRNAseq DE results — it returns the
    strongest genetically-supported genes regardless of whether they
    appeared in the transcriptomic analysis.

    Args:
        disease_name: Disease name for EFO ID resolution
        n: Number of top genes to return

    Returns:
        DataFrame with columns: gene, ensembl_id, genetic_association_score,
        l2g_score (best SSc-specific L2G if available)
    """
    disease_efo_ids = _resolve_disease_efo(disease_name)
    if not disease_efo_ids:
        print(f"  WARNING: Could not resolve EFO IDs for '{disease_name}'",
              file=sys.stderr)
        return pd.DataFrame(columns=["gene", "ensembl_id",
                                      "genetic_association_score"])

    print(f"  Querying top {n} GWAS genes for {disease_name}...",
          file=sys.stderr)

    all_results = []
    for efo_id in disease_efo_ids:
        for page in range(4):  # Up to 2000 targets
            data = _graphql_query(OT_DISEASE_GENETICS_QUERY,
                                   {"diseaseId": efo_id, "page": page})
            if not data or not data.get("disease"):
                break
            rows = data["disease"]["associatedTargets"].get("rows", [])
            if not rows:
                break

            for row in rows:
                dtypes = {d["id"]: d["score"]
                          for d in row.get("datatypeScores", [])}
                gen_score = dtypes.get("genetic_association", 0)
                if gen_score > 0:
                    all_results.append({
                        "gene": row["target"]["approvedSymbol"],
                        "ensembl_id": row["target"]["id"],
                        "genetic_association_score": gen_score,
                    })
            time.sleep(REQUEST_DELAY)

    result = pd.DataFrame(all_results)
    if len(result) > 0:
        result = result.sort_values("genetic_association_score", ascending=False)
        result = result.drop_duplicates(subset="gene", keep="first")
        result = result.head(n).reset_index(drop=True)

    print(f"  Found {len(result)} GWAS-associated genes for {disease_name}",
          file=sys.stderr)
    return result


def assess_gwas_genes_in_adata(adata, gwas_genes_df, de_results=None,
                                celltype_key="cell_type",
                                condition_key="condition"):
    """Map GWAS genes to their expression context in the scRNAseq dataset.

    For each GWAS gene, finds: top expressing cell type, mean expression,
    % cells expressing, and whether it's DE in any cell type.

    Args:
        adata: Annotated AnnData
        gwas_genes_df: DataFrame from get_top_gwas_genes() with 'gene' column
        de_results: Dict of {celltype: DE DataFrame} from pseudobulk DE
        celltype_key: Cell type column in adata.obs
        condition_key: Condition column in adata.obs

    Returns:
        DataFrame with columns: gene, genetic_score, top_celltype,
        mean_expression, pct_expressing, is_de, de_celltype, de_log2fc, de_padj
    """
    import scipy.sparse as sp

    genes = gwas_genes_df["gene"].tolist()
    gene_scores = dict(zip(gwas_genes_df["gene"],
                            gwas_genes_df["genetic_association_score"]))

    # Find which GWAS genes are in the dataset
    available = [g for g in genes if g in adata.var_names]
    missing = [g for g in genes if g not in adata.var_names]
    if missing:
        print(f"  {len(missing)} GWAS genes not in dataset: {missing[:5]}...",
              file=sys.stderr)

    results = []
    celltypes = adata.obs[celltype_key].unique()

    for gene in available:
        gene_idx = list(adata.var_names).index(gene)

        # Expression per cell type
        best_ct = None
        best_expr = 0
        best_pct = 0

        for ct in celltypes:
            ct_mask = adata.obs[celltype_key] == ct
            ct_data = adata.X[ct_mask.values, gene_idx]
            if sp.issparse(ct_data):
                ct_data = ct_data.toarray().flatten()
            else:
                ct_data = np.asarray(ct_data).flatten()

            mean_expr = float(ct_data.mean())
            pct_expr = float((ct_data > 0).mean() * 100)

            if mean_expr > best_expr:
                best_expr = mean_expr
                best_pct = pct_expr
                best_ct = ct

        # Check if DE in any cell type
        is_de = False
        de_ct = None
        de_lfc = None
        de_padj = None

        if de_results:
            for ct, df in de_results.items():
                df_work = df.copy()
                if "gene" in df_work.columns and not isinstance(df_work.index[0], str):
                    df_work = df_work.set_index("gene")
                if gene in df_work.index:
                    row = df_work.loc[gene]
                    padj = row.get("padj", 1.0)
                    lfc = row.get("log2FoldChange", row.get("logfoldchanges", 0))
                    if padj < 0.05:
                        is_de = True
                        if de_padj is None or padj < de_padj:
                            de_ct = ct
                            de_lfc = lfc
                            de_padj = padj

        results.append({
            "gene": gene,
            "genetic_score": gene_scores.get(gene, 0),
            "top_celltype": best_ct,
            "mean_expression": round(best_expr, 2),
            "pct_expressing": round(best_pct, 1),
            "is_de": is_de,
            "de_celltype": de_ct,
            "de_log2fc": round(float(de_lfc), 2) if de_lfc is not None else None,
            "de_padj": float(de_padj) if de_padj is not None else None,
        })

    result = pd.DataFrame(results)
    n_de = result["is_de"].sum() if len(result) > 0 else 0
    print(f"  GWAS gene landscape: {len(result)} genes mapped, "
          f"{n_de} are DE in at least one cell type", file=sys.stderr)

    # Save incrementally
    out_dir = os.environ.get("SCRNA_RESULTS_DIR", "results")
    os.makedirs(out_dir, exist_ok=True)
    try:
        path = os.path.join(out_dir, "gwas_gene_landscape.csv")
        result.to_csv(path, index=False)
        print(f"  Saved: {path}", file=sys.stderr)
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_genetic_score(summary_row):
    """Compute the genetic sub-score for a gene.

    Hierarchy:
      1. GeneBass burden (best when available): min(-log10(p)/10, 1.0) * 0.40
      2. OT Disease Genetics (GWAS/ClinVar): score * 0.40
         -> If GeneBass has hits, OT score gets 0.10 bonus weight
         -> If GeneBass empty, OT score gets the full 0.40 primary weight
      3. TWAS: 0.15
      4. eQTL: 0.10
      5. L2G: score * 0.10
      6. Direction concordance: +0.10 bonus

    Returns float in [0, ~1.1] range.
    """
    score = 0.0

    has_genebass = (summary_row.get("has_genebass")
                    and summary_row.get("genebass_best_pvalue") is not None)
    has_ot = (summary_row.get("has_ot_genetics")
              and summary_row.get("ot_genetic_score") is not None)

    # Primary genetic evidence: GeneBass or OT Disease Genetics
    if has_genebass:
        # GeneBass available: use as primary (0.40), OT as supplementary (0.10)
        pval = summary_row["genebass_best_pvalue"]
        if pval > 0:
            score += min(-np.log10(pval) / 10.0, 1.0) * 0.40
        if has_ot:
            score += float(summary_row["ot_genetic_score"]) * 0.10
    elif has_ot:
        # No GeneBass: OT Disease Genetics is primary (0.50)
        score += float(summary_row["ot_genetic_score"]) * 0.50
    # else: neither available, primary genetic score = 0

    # TWAS component (0.15)
    if summary_row.get("has_twas"):
        score += 0.15

    # eQTL component (0.10)
    if summary_row.get("has_eqtl"):
        score += 0.10

    # L2G component (0.10 max)
    if summary_row.get("has_l2g") and summary_row.get("best_l2g_score") is not None:
        score += float(summary_row["best_l2g_score"]) * 0.10

    # Direction concordance bonus (+0.10)
    direction = summary_row.get("direction")
    if direction in ("inhibit", "activate"):
        score += 0.10

    return round(min(score, 1.0), 4)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def collect_genetic_evidence(gene_list, disease_name, include_genebass=True):
    """Main orchestrator: collect and integrate genetic evidence from all sources.

    For a list of genes and disease name:
      1. Query GeneBass for disease-related phenotype burden results
      2. Query TWAS Atlas for disease/fibrosis/autoimmune TWAS associations
      3. Query eQTL Catalogue for skin and immune tissue eQTLs
      4. Query Open Targets L2G for GWAS-based gene prioritization
      5. Integrate into unified genetic evidence summary per gene

    Args:
        gene_list: list of gene symbols (e.g., ["IRF4", "STAT4", "BLK"])
        disease_name: disease name for context (e.g., "systemic sclerosis")
        include_genebass: whether to attempt GeneBass query (default True)

    Returns dict with:
        "genebass_hits":     DataFrame (gene, phenotype, annotation, pvalue, beta, direction, tier)
        "twas_associations": DataFrame (gene, trait, tissue, zscore, pvalue, method)
        "eqtl_evidence":     DataFrame (gene, tissue, beta, pvalue, variant)
        "l2g_scores":        DataFrame (gene, study, l2g_score)
        "summary":           DataFrame (gene, has_genebass, has_twas, has_eqtl, has_l2g,
                                        genetic_score, direction)
    """
    gene_list = [g.strip() for g in gene_list if g.strip()]
    if not gene_list:
        print("No genes provided", file=sys.stderr)
        empty_summary = pd.DataFrame(columns=["gene", "has_genebass", "has_twas",
                                               "has_eqtl", "has_l2g",
                                               "genetic_score", "direction"])
        return {
            "genebass_hits": pd.DataFrame(),
            "twas_associations": pd.DataFrame(),
            "eqtl_evidence": pd.DataFrame(),
            "l2g_scores": pd.DataFrame(),
            "summary": empty_summary,
        }

    print(f"Collecting genetic evidence for {len(gene_list)} genes "
          f"({disease_name})...", file=sys.stderr)

    # 1. GeneBass (rare variant burden — best when available)
    if include_genebass:
        print("\n[1/5] GeneBass burden results...", file=sys.stderr)
        genebass_df = query_genebass(gene_list, disease_name)
    else:
        print("\n[1/5] GeneBass: skipped (--no-genebass)", file=sys.stderr)
        genebass_df = pd.DataFrame(columns=["gene", "phenotype", "annotation",
                                             "pvalue", "beta", "direction", "tier"])

    # 2. Open Targets Disease Genetics (GWAS + ClinVar + gene burden)
    # Primary genetic source when GeneBass has no disease-specific hits
    print("\n[2/5] Open Targets Disease Genetics (GWAS/ClinVar)...",
          file=sys.stderr)
    ot_genetics_df = query_ot_disease_genetics(gene_list, disease_name)

    # 3. TWAS Atlas (disease-specific only, no proxy diseases)
    print("\n[3/5] TWAS Atlas associations...", file=sys.stderr)
    twas_df = query_twas_atlas(gene_list, disease_name)

    # 4. eQTL Catalogue
    print("\n[4/5] eQTL Catalogue (skin/immune tissues)...", file=sys.stderr)
    eqtl_df = query_eqtl_catalogue(gene_list)

    # 5. Open Targets L2G (disease-specific — filter to SSc EFO IDs)
    print("\n[5/5] Open Targets L2G scores (disease-filtered)...", file=sys.stderr)
    disease_efos = _resolve_disease_efo(disease_name)
    l2g_df = query_ot_l2g(gene_list, disease_efo_ids=disease_efos if disease_efos else None)

    # 6. Integrate into per-gene summary
    print("\nIntegrating evidence...", file=sys.stderr)
    summary_rows = []

    for gene in gene_list:
        row = {"gene": gene}

        # GeneBass (rare variant burden)
        gb_gene = genebass_df.loc[genebass_df["gene"].str.upper() == gene.upper()] if len(genebass_df) > 0 else pd.DataFrame()
        row["has_genebass"] = len(gb_gene) > 0
        if len(gb_gene) > 0:
            best_idx = gb_gene["pvalue"].idxmin()
            row["genebass_best_pvalue"] = gb_gene.loc[best_idx, "pvalue"]
            row["genebass_direction"] = gb_gene.loc[best_idx, "direction"]
        else:
            row["genebass_best_pvalue"] = None
            row["genebass_direction"] = None

        # OT Disease Genetics (GWAS + ClinVar + gene burden)
        ot_gene = ot_genetics_df.loc[ot_genetics_df["gene"].str.upper() == gene.upper()] if len(ot_genetics_df) > 0 else pd.DataFrame()
        row["has_ot_genetics"] = len(ot_gene) > 0
        if len(ot_gene) > 0:
            row["ot_genetic_score"] = ot_gene.iloc[0]["ot_genetic_score"]
        else:
            row["ot_genetic_score"] = None

        # TWAS
        twas_gene = twas_df.loc[twas_df["gene"].str.upper() == gene.upper()] if len(twas_df) > 0 else pd.DataFrame()
        row["has_twas"] = len(twas_gene) > 0

        # eQTL
        eqtl_gene = eqtl_df.loc[eqtl_df["gene"].str.upper() == gene.upper()] if len(eqtl_df) > 0 else pd.DataFrame()
        row["has_eqtl"] = len(eqtl_gene) > 0

        # L2G
        l2g_gene = l2g_df.loc[l2g_df["gene"].str.upper() == gene.upper()] if len(l2g_df) > 0 else pd.DataFrame()
        row["has_l2g"] = len(l2g_gene) > 0
        if len(l2g_gene) > 0:
            row["best_l2g_score"] = l2g_gene["l2g_score"].max()
        else:
            row["best_l2g_score"] = None

        # Direction: prefer GeneBass, then infer from TWAS z-score
        direction = row.get("genebass_direction")
        if direction is None or direction == "unknown":
            if len(twas_gene) > 0 and "pvalue" in twas_gene.columns:
                best_twas = twas_gene.loc[twas_gene["pvalue"].idxmin()]
                z = best_twas.get("zscore")
                if z is not None and not np.isnan(z):
                    direction = "inhibit" if z > 0 else "activate"
        row["direction"] = direction if direction and direction != "unknown" else None

        # Compute genetic score
        row["genetic_score"] = compute_genetic_score(row)

        summary_rows.append(row)

    summary_df = pd.DataFrame(summary_rows)

    # Reorder columns for clarity
    summary_cols = ["gene", "has_genebass", "has_ot_genetics", "has_twas",
                    "has_eqtl", "has_l2g", "genetic_score", "direction"]
    extra_cols = [c for c in summary_df.columns if c not in summary_cols]
    summary_df = summary_df[summary_cols + extra_cols]

    # Verification printout
    n_genebass = summary_df["has_genebass"].sum()
    n_ot = summary_df["has_ot_genetics"].sum()
    n_twas = summary_df["has_twas"].sum()
    n_eqtl = summary_df["has_eqtl"].sum()
    n_l2g = summary_df["has_l2g"].sum()

    print(f"\nGenetic evidence collected! "
          f"{n_genebass} GeneBass, "
          f"{n_ot} OT GWAS/ClinVar, "
          f"{n_twas} TWAS, "
          f"{n_eqtl} eQTL",
          file=sys.stderr)

    return {
        "genebass_hits": genebass_df,
        "ot_disease_genetics": ot_genetics_df,
        "twas_associations": twas_df,
        "eqtl_evidence": eqtl_df,
        "l2g_scores": l2g_df,
        "summary": summary_df,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Integrate genetic evidence from multiple sources for "
                    "disease-gene prioritization"
    )
    parser.add_argument("--genes",
                        help="Comma-separated gene symbols "
                             "(e.g., 'IRF4,STAT4,BLK,TNFAIP3')")
    parser.add_argument("--gene-file",
                        help="Text file with one gene symbol per line")
    parser.add_argument("--disease", required=True,
                        help="Disease name (e.g., 'systemic sclerosis')")
    parser.add_argument("--no-genebass", action="store_true",
                        help="Skip GeneBass query (use when data unavailable)")
    parser.add_argument("--output",
                        help="Output JSON file path")
    parser.add_argument("--max-genes", type=int, default=50,
                        help="Maximum number of genes to query (default: 50)")
    args = parser.parse_args()

    # Build gene list
    if args.genes:
        gene_list = [g.strip() for g in args.genes.split(",") if g.strip()]
    elif args.gene_file:
        with open(args.gene_file) as f:
            gene_list = [line.strip() for line in f if line.strip()
                         and not line.startswith("#")]
    else:
        print("ERROR: Provide --genes or --gene-file", file=sys.stderr)
        sys.exit(1)

    if len(gene_list) > args.max_genes:
        print(f"WARNING: Limiting to {args.max_genes} genes (from {len(gene_list)})",
              file=sys.stderr)
        gene_list = gene_list[:args.max_genes]

    # Run
    results = collect_genetic_evidence(
        gene_list,
        args.disease,
        include_genebass=not args.no_genebass,
    )

    # Build serializable output
    output = {
        "disease": args.disease,
        "n_genes": len(gene_list),
        "genes_queried": gene_list,
        "genebass_hits": (results["genebass_hits"].to_dict(orient="records")
                          if len(results["genebass_hits"]) > 0 else []),
        "twas_associations": (results["twas_associations"].to_dict(orient="records")
                              if len(results["twas_associations"]) > 0 else []),
        "eqtl_evidence": (results["eqtl_evidence"].to_dict(orient="records")
                          if len(results["eqtl_evidence"]) > 0 else []),
        "l2g_scores": (results["l2g_scores"].to_dict(orient="records")
                       if len(results["l2g_scores"]) > 0 else []),
        "summary": (results["summary"].to_dict(orient="records")
                    if len(results["summary"]) > 0 else []),
    }

    # Print summary table
    summary = results["summary"]
    if len(summary) > 0:
        print(f"\n{'Gene':12s} {'GeneBass':>8s} {'TWAS':>6s} {'eQTL':>6s} "
              f"{'L2G':>6s} {'Score':>7s} {'Direction':>10s}",
              file=sys.stderr)
        print("-" * 62, file=sys.stderr)
        for _, r in summary.sort_values("genetic_score", ascending=False).iterrows():
            gb = "Y" if r["has_genebass"] else "-"
            tw = "Y" if r["has_twas"] else "-"
            eq = "Y" if r["has_eqtl"] else "-"
            l2 = "Y" if r["has_l2g"] else "-"
            d = r.get("direction") or "-"
            print(f"{r['gene']:12s} {gb:>8s} {tw:>6s} {eq:>6s} "
                  f"{l2:>6s} {r['genetic_score']:>7.3f} {d:>10s}",
                  file=sys.stderr)

    # Write output
    if args.output:
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"\nResults written to: {args.output}", file=sys.stderr)
    else:
        print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
