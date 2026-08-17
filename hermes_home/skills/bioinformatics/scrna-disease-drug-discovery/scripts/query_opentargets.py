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
Query Open Targets Platform GraphQL API for drug target annotations.

Retrieves tractability, known drugs, genetic constraint, pathways, mouse
phenotypes, and tissue expression for candidate genes. Adapted from the
genetic-target-hypothesis skill for use in multi-omics drug discovery.

Usage:
  python query_opentargets.py --genes "TGFBR1,PDGFRA,IL6R"
  python query_opentargets.py --input de_genes.json --output ot_annotations.json
"""

import argparse
import json
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests",
          file=sys.stderr)
    sys.exit(1)

OT_API = "https://api.platform.opentargets.org/api/v4/graphql"
REQUEST_DELAY = 0.5
MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# GraphQL queries
# ---------------------------------------------------------------------------

TARGET_QUERY = """
query TargetInfo($ensemblId: String!) {
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    approvedName
    biotype
    tractability {
      label
      modality
      value
    }
    pathways {
      pathway
      pathwayId
    }
  }
}
"""

SEARCH_QUERY = """
query SearchTarget($queryString: String!) {
  search(queryString: $queryString, entityNames: ["target"]) {
    hits {
      id
      name
      entity
    }
  }
}
"""


# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------

def query_graphql(query, variables=None):
    """Execute a GraphQL query against Open Targets API with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                OT_API,
                json={"query": query, "variables": variables or {}},
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(f"  Rate limited, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                print(f"  GraphQL errors: {data['errors']}", file=sys.stderr)
                return None
            return data.get("data")
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            print(f"  Request failed: {e}", file=sys.stderr)
            return None
    return None


def resolve_gene_to_ensembl(gene_symbol):
    """Resolve a gene symbol to Ensembl ID via Open Targets search."""
    data = query_graphql(SEARCH_QUERY, {"queryString": gene_symbol})
    if not data or not data.get("search", {}).get("hits"):
        return None

    for hit in data["search"]["hits"]:
        if hit.get("entity") == "target":
            name = hit.get("name", "").upper()
            if gene_symbol.upper() in name or name in gene_symbol.upper():
                return hit["id"]

    # Return first target hit
    for hit in data["search"]["hits"]:
        if hit.get("entity") == "target":
            return hit["id"]
    return None


def query_target_info(ensembl_id):
    """Query detailed target information from Open Targets."""
    data = query_graphql(TARGET_QUERY, {"ensemblId": ensembl_id})
    if not data or not data.get("target"):
        return None
    return data["target"]


# ---------------------------------------------------------------------------
# Main annotation function
# ---------------------------------------------------------------------------

def query_target_annotations(gene_list, verbose=True):
    """Query Open Targets for annotations on a list of genes.

    Args:
        gene_list: List of gene symbols
        verbose: Print progress

    Returns:
        Dict mapping gene symbol to annotation dict with keys:
        ensembl_id, approved_name, tractability, known_drugs, constraint,
        pathways, mouse_phenotypes, druggability_score
    """
    annotations = {}
    n_total = len(gene_list)
    n_found = 0

    if verbose:
        print(f"Querying Open Targets for {n_total} genes...")

    for i, gene in enumerate(gene_list):
        if verbose and (i + 1) % 10 == 0:
            print(f"  Progress: {i + 1}/{n_total} genes queried...")

        # Resolve to Ensembl ID
        ensembl_id = resolve_gene_to_ensembl(gene)
        if not ensembl_id:
            annotations[gene] = _empty_annotation(gene)
            time.sleep(REQUEST_DELAY)
            continue

        # Query target info
        info = query_target_info(ensembl_id)
        if not info:
            annotations[gene] = _empty_annotation(gene)
            time.sleep(REQUEST_DELAY)
            continue

        # Parse annotation
        ann = _parse_target_info(gene, info)
        annotations[gene] = ann
        n_found += 1

        time.sleep(REQUEST_DELAY)

    if verbose:
        print(f"\u2713 Open Targets annotations retrieved for {n_found}/{n_total} genes")

    return annotations


def _empty_annotation(gene):
    """Return empty annotation for a gene not found in Open Targets."""
    return {
        "gene": gene,
        "ensembl_id": None,
        "approved_name": None,
        "tractability": {},
        "known_drugs": [],
        "constraint": {},
        "pathways": [],
        "mouse_phenotypes": [],
        "druggability_score": 0.2,  # Default low score for unknown
    }


def _parse_target_info(gene, info):
    """Parse Open Targets target info into annotation dict."""
    # Tractability
    tractability = {}
    for t in (info.get("tractability") or []):
        modality = t.get("modality", "unknown")
        if t.get("value"):
            tractability[modality] = t.get("label", "tractable")

    # Pathways
    pathways = [
        {"name": p.get("pathway"), "id": p.get("pathwayId")}
        for p in (info.get("pathways") or [])
    ]

    # Compute druggability score
    druggability_score = _compute_druggability(tractability, [], {})

    return {
        "gene": gene,
        "ensembl_id": info.get("id"),
        "approved_name": info.get("approvedName"),
        "tractability": tractability,
        "known_drugs": [],
        "constraint": {},
        "pathways": pathways,
        "mouse_phenotypes": [],
        "druggability_score": druggability_score,
    }


def _compute_druggability(tractability, known_drugs, constraint):
    """Compute a druggability score (0-1) from Open Targets data."""
    score = 0.0

    # Tractability: small molecule or antibody
    if "SM" in tractability or "small_molecule" in str(tractability).lower():
        score += 0.3
    if "AB" in tractability or "antibody" in str(tractability).lower():
        score += 0.2

    # Known drugs
    if known_drugs:
        max_phase = max(d.get("phase", 0) for d in known_drugs)
        if max_phase >= 4:
            score += 0.4  # Approved drug
        elif max_phase >= 3:
            score += 0.3
        elif max_phase >= 2:
            score += 0.2
        elif max_phase >= 1:
            score += 0.1

    # Genetic constraint (tolerant to LoF = safer target)
    lof_oe = constraint.get("lof_oe")
    if lof_oe is not None:
        if lof_oe > 0.6:
            score += 0.1  # Tolerant -- safer
        elif lof_oe < 0.2:
            score -= 0.1  # Constrained -- safety concern

    return max(0.0, min(1.0, score))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query Open Targets annotations")
    parser.add_argument("--genes", help="Comma-separated gene symbols")
    parser.add_argument("--input", help="JSON file with gene list")
    parser.add_argument("--output", help="Output JSON file")
    args = parser.parse_args()

    if args.genes:
        genes = [g.strip() for g in args.genes.split(",")]
    elif args.input:
        with open(args.input) as f:
            data = json.load(f)
        genes = data if isinstance(data, list) else data.get("genes", [])
    else:
        print("ERROR: Provide --genes or --input", file=sys.stderr)
        sys.exit(1)

    annotations = query_target_annotations(genes)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(annotations, f, indent=2, default=str)
        print(f"Annotations saved to {args.output}")
    else:
        print(json.dumps(annotations, indent=2, default=str))
