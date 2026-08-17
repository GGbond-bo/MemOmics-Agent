#!/usr/bin/env python3
"""Resolve DeCS numeric IDs (BIREME registration numbers) to descriptor names + tree numbers.

Usage:
    python decs_id_lookup.py 20174 9562 24375

Output: per-ID Spanish/English descriptor name + first tree numbers; JSON dump to decs_id_map.json.

Background (2026-08, TaskC MESINESP): DeCS (Descriptores en Ciencias de la Salud)
has its OWN numeric ID system (e.g. 23039=Toracotomía, 9562=Neoplasias, 21034=Humans).
These are NOT MeSH tree numbers. Benchmarks that ask for decsCodes want these numeric
IDs — never answer with MeSH tree numbers (strict format scoring = 0).

Working URL pattern: https://decs.bvsalud.org/ths/resource/?id=<ID>
The ?filter=ths_regid&q= form returns a generic search page (no descriptor).
The h1 title is a site banner ("Queremos a sua opinião..."); real names live in
"Descritor em espanhol:" / "Descritor em inglês:" table cells.
"""
import sys, time, json, re, urllib.request

BASE = "https://decs.bvsalud.org/ths/resource/?id="

def lookup(did):
    req = urllib.request.Request(BASE + did, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        txt = r.read().decode("utf-8", "replace")
    fields = {}
    for lang, label in (("pt", "português"), ("en", "inglês"), ("es", "espanhol"), ("fr", "francês")):
        idx = txt.find(f"Descritor em {label}:")
        if idx < 0:
            continue
        seg = txt[idx:idx + 700]
        m = re.search(r"<td[^>]*>(.*?)</td>", seg, re.S)
        if m:
            fields[lang] = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    trees = list(dict.fromkeys(re.findall(r"([A-Z]\d+(?:\.\d+)+)", txt)))
    return {"id": did, "names": fields, "tree_numbers": trees[:6]}

def main():
    ids = [a for a in sys.argv[1:] if a.isdigit()]
    if not ids:
        print("Usage: python decs_id_lookup.py <DeCS-ID> [DeCS-ID...]")
        sys.exit(1)
    out = {}
    for did in ids:
        rec = lookup(did)
        out[did] = rec
        es = rec["names"].get("es", "?")
        en = rec["names"].get("en", "?")
        print(f"{did}: ES={es} | EN={en} | trees={rec['tree_numbers']}")
        time.sleep(0.4)
    with open("decs_id_map.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nSaved decs_id_map.json")

if __name__ == "__main__":
    main()
