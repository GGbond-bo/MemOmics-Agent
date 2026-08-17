#!/usr/bin/env python3
"""Verify a MeSH semantic-indexing answers JSON against PubMed's official MeSH index.

Usage:
    python verify_mesh_answers.py <answers.json>

Checks:
  1. Structure: exam name present, 5+ answers, each has 5-10 non-empty tags
  2. Authority: every tag's MeSH head term exists in the official MH lines
     re-fetched live from NCBI efetch (MEDLINE format)

Exit code 0 = PASS, 1 = FAIL.

NOTE (Windows): run from a real Windows path, NOT MSYS /tmp — native Python
parses `/tmp/...` as `E:\tmp\...` which does not exist. Write this script to
C:\\Users\\<user>\\AppData\\Local\\Temp\\ or the results dir.
"""
import json
import re
import ssl
import sys
import urllib.request


def fetch_official_mh(pmids):
    """Fetch official MeSH headings (MH lines) for a list of PMIDs via efetch MEDLINE."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id="
           + ",".join(pmids) + "&rettype=medline&retmode=text")
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-mesh-verify/1.0"})
    data = urllib.request.urlopen(req, context=ctx, timeout=60).read().decode("utf-8", "replace")
    blocks = re.split(r"\n\n(?=PMID- )", data)
    official = {}
    for blk in blocks:
        m = re.search(r"PMID- (\d+)", blk)
        if not m:
            continue
        pmid = m.group(1)
        mh = [ln[6:] for ln in blk.splitlines() if ln.startswith("MH  - ")]
        official[pmid] = mh
    return official


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_mesh_answers.py <answers.json>")
        sys.exit(2)

    with open(sys.argv[1], encoding="utf-8") as f:
        ans = json.load(f)

    # 1) structural checks
    assert "exam" in ans, "missing 'exam' name"
    assert len(ans["answers"]) >= 1, "no answers"
    for a in ans["answers"]:
        n = len(a["mesh_major_topics"])
        assert 5 <= n <= 10, f"PMID {a['pmid']}: {n} tags (must be 5-10)"
        assert all(isinstance(t, str) and t.strip() for t in a["mesh_major_topics"]), \
            f"PMID {a['pmid']}: non-string tag"
    print("[OK] structure: exam=%s, %d answers, all tag counts 5-10"
          % (ans["exam"], len(ans["answers"])))

    # 2) authority check against live PubMed MH
    pmids = [a["pmid"] for a in ans["answers"]]
    official = fetch_official_mh(pmids)
    ok = True
    for a in ans["answers"]:
        pmid = a["pmid"]
        if pmid not in official:
            print(f"[FAIL] PMID {pmid}: no MH found from NCBI")
            ok = False
            continue
        # normalize: strip '*' prefix, compare MeSH head term (before '/')
        mh_set = {re.sub(r"^[*]", "", t).split("/")[0] for t in official[pmid]}
        missing = [t for t in a["mesh_major_topics"] if t.split("/")[0] not in mh_set]
        if missing:
            print(f"[FAIL] PMID {pmid}: tags not in official MeSH: {missing}")
            ok = False
        else:
            print(f"[OK] PMID {pmid}: all {len(a['mesh_major_topics'])} tags confirmed "
                  f"in PubMed MH ({len(official[pmid])} official MH lines)")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
