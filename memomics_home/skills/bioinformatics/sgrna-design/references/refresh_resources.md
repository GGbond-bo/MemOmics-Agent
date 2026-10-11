# Refreshing the bundled resource files

This skill bundles a snapshot of two files from `snap-stanford/Biomni`
(`biomni/know_how/resource/`):

- `addgene_grna_sequences.csv` — 321 validated sgRNA records (197 genes) from Addgene.
- `CRISPick_download_links.txt` — 238 CRISPick precomputed-dataset download URLs.

The snapshot is fixed at skill-creation time and does **not** auto-update. To pull the latest
versions from the upstream repository:

```bash
SKILL_DIR="$(dirname "$0")/.."   # or the absolute path to the skill folder
RES="$SKILL_DIR/references/resource"

BASE="https://raw.githubusercontent.com/snap-stanford/Biomni/main/biomni/know_how/resource"
wget -O "$RES/addgene_grna_sequences.csv"  "$BASE/addgene_grna_sequences.csv"
wget -O "$RES/CRISPick_download_links.txt" "$BASE/CRISPick_download_links.txt"
```

After refreshing, sanity-check structure:

```bash
head -1 "$RES/addgene_grna_sequences.csv"   # expect spaced column names
wc -l "$RES/addgene_grna_sequences.csv" "$RES/CRISPick_download_links.txt"
```

Notes:
- The Addgene CSV stores `Plasmid ID` and `PubMed ID` as HTML `<a>` tags; `search_addgene.py`
  strips these automatically — no manual cleaning needed.
- If upstream changes column names, update the loaders in `scripts/search_addgene.py`
  (Addgene) or the alias lists in `scripts/select_crispick_sgrnas.py` (CRISPick exports).
- Original source guide: `biomni/know_how/sgRNA_design_guide.md` in the same repo.
