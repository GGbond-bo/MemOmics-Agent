#!/usr/bin/env python3
"""DeCS numeric-ID -> descriptor name resolver (pt/en/es) via decs.bvsalud.org.

Verified 2026-08-02 (MESINESP benchmark): the /ths/resource/?id=<id> page shows a
survey-feedback banner ("Queremos a sua opiniao...") as its h1/title, but the
descriptor table is in the BODY under "Descritor em <lang>:". Ignore h1/title;
parse the body table with the regex below.

Usage:
    python decs_id_to_name.py 20174 9562 21034
    echo "20174 9562" | python decs_id_to_name.py --stdin
"""
import json
import re
import sys
import time
import urllib.request

BASE = "https://decs.bvsalud.org/ths/resource/?id="
LANGS = [("pt", "português"), ("en", "inglês"), ("es", "espanhol"), ("fr", "francês")]


def get_html(did, retry=4, timeout=25):
    url = BASE + str(did)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for a in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception:
            time.sleep(4 * (a + 1))
    return ""


def parse_names(html):
    """Descriptor names by language from the body table."""
    names = {}
    for key, label in LANGS:
        idx = html.find(f"Descritor em {label}:")
        if idx >= 0:
            seg = html[idx:idx + 800]
            m = re.search(r"<td[^>]*>(.*?)</td>", seg, re.S) or \
                re.search(r"<div[^>]*>(.*?)</div>", seg, re.S)
            if m:
                names[key] = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return names


def parse_trees(html):
    return list(dict.fromkeys(re.findall(r"([A-Z]\d+(?:\.\d+)+)", html)))[:6]


def resolve(did):
    html = get_html(did)
    if not html:
        return {"id": str(did), "error": "fetch failed"}
    names = parse_names(html)
    return {
        "id": str(did),
        "name_pt": names.get("pt", ""),
        "name_en": names.get("en", ""),
        "name_es": names.get("es", ""),
        "trees": parse_trees(html),  # for identity verification ONLY - never submit as decsCodes
    }


def main():
    if "--stdin" in sys.argv:
        ids = [x.strip() for x in sys.stdin.read().split() if x.strip()]
    else:
        ids = sys.argv[1:]
    if not ids:
        print(__doc__)
        return
    out = []
    for did in ids:
        out.append(resolve(did))
        time.sleep(0.4)  # politeness / rate limit
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
