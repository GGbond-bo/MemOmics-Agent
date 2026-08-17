#!/usr/bin/env python3
"""Retrieve MeSH tree numbers (= DeCS codes) for descriptors via NCBI E-utilities.
Verified 2026-08-02 on MESINESP benchmark (DeCS coding). DeCS codes == MeSH tree numbers.

Usage:
    python mesh_tree_numbers.py "Mediastinal Neoplasms" "Tongue Neoplasms"
    python mesh_tree_numbers.py 68001706            # pass a known UI (68+D-code digits) directly

Known-meaning UI shortcut: 68 + MeSH D-code digits, e.g. Biopsy=D001706 -> 68001706.
Beware: UIDs starting with 81 are WRONG records (supplementary/other) returning Y-codes
(Y02.050, Y09.010.020) — Y-codes are NOT standard MeSH tree numbers, never use them.
"""
import json, re, sys, time
import urllib.request, urllib.parse

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def esearch_mesh(term, retry=5):
    """Return UID list. Plain term (no [MeSH] tag) is more robust under rate limiting."""
    url = BASE + "esearch.fcgi?" + urllib.parse.urlencode({
        "db": "mesh", "term": term, "retmode": "json", "retmax": 5})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for a in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode()).get("esearchresult", {}).get("idlist", [])
        except Exception:
            time.sleep(5 * (a + 1))
    return []


def fetch_trees(uid):
    """efetch returns PLAIN TEXT even with retmode=xml; tree numbers live in 'Tree Number(s):'."""
    url = BASE + "efetch.fcgi?" + urllib.parse.urlencode({"db": "mesh", "id": uid, "retmode": "xml"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for a in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                txt = r.read().decode()
            m = re.search(r"Tree Number\(s\):\s*(.+)", txt)
            return [t.strip() for t in m.group(1).split(",")] if m else []
        except Exception:
            time.sleep(3)
    return []


def mesh_trees(term_or_ui):
    """Return (uid, [tree_numbers]). Verify the returned record matches expectations —
    esearch uids[0] can be a DIFFERENT descriptor (e.g. 'Blood Transfusion' -> 'Transfusion Reaction')."""
    if re.fullmatch(r"\d{8}", term_or_ui):
        uid = term_or_ui
    else:
        uids = esearch_mesh(term_or_ui)
        if not uids:
            return None, []
        uid = uids[0]
    return uid, fetch_trees(uid)


if __name__ == "__main__":
    for t in sys.argv[1:]:
        uid, trees = mesh_trees(t)
        print(f"{t}: UI={uid} | {trees}")
        time.sleep(1.0)
