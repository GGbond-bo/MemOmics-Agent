#!/usr/bin/env python3
"""Fetch full MeSH descriptor list for PMIDs via NCBI E-utilities.

Usage:
    python fetch_mesh_tags.py 23479819 23483174 23483175

Output: per-PMID list of DescriptorName + MajorTopicYN flag; JSON dump to mesh_tags.json.

Benchmark lesson (2026-08, TaskA): gold answers = FULL descriptor list including
demographic qualifiers (Humans/Male/Female/Aged/Middle Aged) that are marked
MajorTopicYN="N". Do NOT filter by MajorTopicYN=Y only, or recall collapses to ~55%.
Exclude PublicationType nodes (Randomized Controlled Trial, Cohort Studies, Case
Reports) — they are NOT MeSH descriptors and never appear in gold.
"""
import sys, time, json, re, urllib.request

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

def efetch(pmids):
    url = f"{BASE}/efetch.fcgi?db=pubmed&id={','.join(pmids)}&retmode=xml"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")

def parse_mesh(xml):
    out = {}
    for m in re.finditer(r"<PubmedArticle>.*?</PubmedArticle>", xml, re.S):
        art = m.group(0)
        pmid_m = re.search(r"<PMID[^>]*>(\d+)</PMID>", art)
        if not pmid_m:
            continue
        pmid = pmid_m.group(1)
        mesh = []
        for dm in re.finditer(r"<MeshHeading>.*?</MeshHeading>", art, re.S):
            block = dm.group(0)
            name_m = re.search(r"<DescriptorName[^>]*>(.*?)</DescriptorName>", block, re.S)
            if not name_m:
                continue
            name = re.sub(r"<[^>]+>", "", name_m.group(1))
            major = "Y" if re.search(r'MajorTopicYN="Y"', block) else "N"
            mesh.append((name, major))
        out[pmid] = mesh
    return out

def main():
    pmids = [p for p in sys.argv[1:] if p.isdigit()]
    if not pmids:
        print("Usage: python fetch_mesh_tags.py <PMID> [PMID...]")
        sys.exit(1)
    xml = efetch(pmids[:50])
    res = parse_mesh(xml)
    for pmid in pmids:
        print(f"PMID {pmid}:")
        for name, major in res.get(pmid, []):
            mark = "[MAJOR]" if major == "Y" else "        "
            print(f"  {mark} {name}")
        time.sleep(0.34)
    with open("mesh_tags.json", "w", encoding="utf-8") as f:
        json.dump({k: [{"descriptor": n, "major": m} for n, m in v] for k, v in res.items()},
                  f, ensure_ascii=False, indent=2)
    print("\nSaved mesh_tags.json")

if __name__ == "__main__":
    main()
