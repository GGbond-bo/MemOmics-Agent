#!/usr/bin/env python3
"""Fetch official PubMed MeSH headings for PMIDs and verify answers files.

Reusable for BioASQ Task A-style MeSH labeling benchmarks (and MESINESP DeCS
conversion via the mesh db route). Validated 2026-08-02.

Usage:
  python fetch_mesh_major_topics.py --pmids 23479819,23483174          # print clean MH headings
  python fetch_mesh_major_topics.py --verify answers_mesh_taskA.json   # validate answers file

Answers file format (matches what the benchmark expects):
  {"exam": "...", "answers": [{"pmid": "23479819", "title": "...",
                               "mesh_major_topics": ["Luminescence", ...]}, ...]}
"""
import argparse
import json
import re
import ssl
import sys
import time
import urllib.request

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_medline(pmids, timeout=60):
    """Fetch MEDLINE records for a list of PMIDs (one batched efetch call)."""
    url = EUTILS + "?db=pubmed&id=" + ",".join(pmids) + "&rettype=medline&retmode=text"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, context=_ctx(), timeout=timeout).read().decode("utf-8", "replace")
    return data


def parse_mh_blocks(medline):
    """Return {pmid: [raw MH lines]}."""
    blocks = re.split(r"\n\n(?=PMID- )", medline)
    out = {}
    for blk in blocks:
        m = re.search(r"PMID- (\d+)", blk)
        if not m:
            continue
        pmid = m.group(1)
        mh = [ln[6:] for ln in blk.splitlines() if ln.startswith("MH  - ")]
        out[pmid] = mh
    return out


def clean_mh(mh_lines):
    """Strip leading '*' (major-topic flag) and '/qualifier' suffix."""
    return {re.sub(r"^[*]", "", t).split("/")[0] for t in mh_lines}


def verify_answers(path):
    with open(path, encoding="utf-8") as f:
        ans = json.load(f)
    answers = ans["answers"]
    assert len(answers) == 5, f"expected 5 answers, got {len(answers)}"  # typical exam size

    # 1) structural check
    for a in answers:
        n = len(a["mesh_major_topics"])
        assert 5 <= n <= 10, f"PMID {a['pmid']}: {n} tags (must be 5-10)"
        assert all(isinstance(t, str) and t.strip() for t in a["mesh_major_topics"]), \
            f"PMID {a['pmid']}: non-string tag"
    print(f"[OK] structure: {len(answers)} answers, all tag counts 5-10")

    # 2) cross-check against official PubMed MH set
    pmids = [a["pmid"] for a in answers]
    official = parse_mh_blocks(fetch_medline(pmids))
    ok = True
    for a in answers:
        pmid = a["pmid"]
        if pmid not in official:
            print(f"[FAIL] PMID {pmid}: no MH found from NCBI")
            ok = False
            continue
        mh_set = clean_mh(official[pmid])
        missing = [t for t in a["mesh_major_topics"] if t.split("/")[0] not in mh_set]
        if missing:
            print(f"[FAIL] PMID {pmid}: tags NOT in official MH: {missing}")
            ok = False
        else:
            print(f"[OK] PMID {pmid}: all {len(a['mesh_major_topics'])} tags confirmed "
                  f"in PubMed MH ({len(official[pmid])} official MH lines)")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Fetch/verify PubMed MeSH headings")
    ap.add_argument("--pmids", help="comma-separated PMIDs to print clean MH headings")
    ap.add_argument("--verify", help="path to answers JSON file to validate")
    args = ap.parse_args()

    if args.verify:
        sys.exit(verify_answers(args.verify))

    if args.pmids:
        pmids = [p.strip() for p in args.pmids.split(",")]
        data = fetch_medline(pmids)
        for pmid, mh in parse_mh_blocks(data).items():
            print(f"===== PMID {pmid} =====")
            print("Raw MH:", mh)
            print("Clean :", sorted(clean_mh(mh)))
        return

    ap.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
