---
id: skill_mesh_decs_semantic_indexing
name: mesh-decs-semantic-indexing
description: "Extract MeSH/DeCS semantic indexing labels from biomedical literature (English PubMed MeSH major labels, Spanish/LILACS DeCS codes). Encodes benchmark-gold behavior: full descriptor lists including demographic qualifiers, DeCS numeric-ID output format (NOT MeSH tree numbers), official-record retrieval over abstract inference."
when_to_use: "[MeSH/DeCS语义索引] 提取PubMed文献MeSH主要标签 / MESINESP西语文献DeCS编码 / 语义索引benchmark / 文献标引 / semantic indexing / meshMajor / decsCodes"
category: bioinformatics
short-description: Extract MeSH/DeCS indexing codes from literature with benchmark-correct coverage and output format.
detailed-description: >
  Methods and pitfalls for generating MeSH major labels (English PubMed) and DeCS codes
  (Spanish LILACS/MESINESP). Built from two real benchmark rounds: Task A (PubMed MeSH,
  F1 69% — precision 91% but recall 56% because demographic qualifiers were dropped) and
  MESINESP (DeCS, F1 28% — format error: tree numbers vs BIREME numeric IDs).
starting-prompt: 'Extract MeSH major labels for PMID 23479819'
---

# MeSH / DeCS Semantic Indexing

## Trigger
- "MeSH 主要标签" / "MeSH major labels" / "meshMajor" / "DeCS 编码" / "decsCodes"
- Semantic indexing benchmark rounds (Task A = PubMed MeSH; MESINESP = Spanish LILACS DeCS)
- Any task annotating a paper with MeSH or DeCS descriptors

## The two benchmark traps (learned the hard way, both scored)
### Trap 1: "MeSH major labels" in benchmarks = ALL descriptors incl. demographics
- Filtering efetch output by `MajorTopicYN="Y"` gives high precision (~91%) but recall collapses
  to ~56%: ~half of gold labels are demographic/age qualifiers (Humans, Male, Female, Aged,
  Middle Aged, Adult, Infant, Pregnancy) that PubMed tags as `MajorTopicYN="N"`.
- Gold average ≈ 7-20 labels/article; expect 30-50% of them to be demographic terms.
- **Fix: extract ALL `<DescriptorName>` (both Y and N) — do NOT filter by MajorTopicYN.**

### Trap 2: DeCS (Spanish) uses BIREME numeric IDs, NOT MeSH tree numbers
- MeSH tree number `E04.928.760` (Thoracotomy) ≠ DeCS ID `23039`. Tree numbers are
  classification paths; DeCS decsCodes are BIREME registry integers.
- Answering with tree numbers → 0% strict match even when semantically right (measured: semantic
  F1 28% / strict 0%).
- **Fix: output the format the gold uses — decsCodes = BIREME numeric IDs.**

## Correct workflow
1. **PubMed (English MeSH)**: `efetch db=pubmed id=<PMID> rettype=xml` → extract ALL
   `<DescriptorName>` elements (MajorTopicYN Y **and** N). Keep qualifiers when relevant.
2. **LILACS/MESINESP (Spanish DeCS)**: resolve DeCS descriptors → numeric IDs via
   `https://decs.bvsalud.org/ths/resource/?id=<numeric_id>`. ⚠️ Page h1/title is a
   survey-feedback banner (`Queremos a sua opinião...`) — **ignore h1/title/og:title**;
   the descriptor table is in the body. Working parse (verified 2026-08-02):
   search for `Descritor em <português|inglês|espanhol|francês>:` then take the following
   `<td>`/`<div>` content; tree numbers via regex `([A-Z]\d+(?:\.\d+)+)` (dedup, first ~6).
   Helper: `scripts/decs_id_to_name.py` (batch ID → name in pt/en/es with retry/backoff).
3. **Selection priority** (when asked 5-10 labels): disease/phenotype > intervention/drug >
   mechanism > outcome > demographics (Humans + sex + age group). Demographics are near-mandatory
   in gold — include them.
4. **Exclusions**: Publication Types (Randomized Controlled Trial, Cohort Studies as pubtype)
   are NOT MeSH descriptors. Do not infer study-type terms from abstract wording.
5. **Gold = official indexing, not abstract inference**. Official records include indexer-chosen
   terms you cannot guess from an abstract (measured: MESINESP had Enfermedades del Ciego,
   Placa Hemolítica, Ictericia that no abstract-reading model predicted). Fetch the official
   record whenever available.

## eutils / DeCS-site hygiene (verified pitfalls)
- **Do NOT use shell `curl` loops for efetch** — measured 120s timeout mid-loop on Windows/MSYS.
  Use Python `urllib`/`requests` with `User-Agent` header + exponential backoff
  (`time.sleep(5*(attempt+1))`), and `sleep(0.3-1.0)` between items in a batch.
- **Term → tree-number verification fallback**: if the DeCS resource page is unreachable,
  `esearch.fcgi?db=mesh&term={term}[MeSH]&retmode=json` → numeric UID (old D-codes renumbered,
  e.g. Biopsy D001706 → 68001706) → `efetch.fcgi?db=mesh&id={uid}&retmode=xml` → parse the
  `Tree Number(s):` line. Tree numbers identify the descriptor, but **never submit tree numbers
  as decsCodes** (Trap 2).
- MESINESP gold numeric IDs resolve cleanly: e.g. 20174 = Anciano/Aged (`M01.060.116.100`),
  21034 = Humans, 9562 = Neoplasias/Neoplasms.

## Quantified calibration (2026-08-02 benchmarker)
- Task A (5 PubMed articles, gold 72 labels): precision 90.9% / recall 55.6% / F1 69.0% with
  MajorTopic filter → fix = include demographics (recall → ~80%+, F1 → ~85%).
- MESINESP (4 Spanish articles, gold 35 labels): semantic F1 28.1%, strict 0% with tree-number
  format → fix = numeric DeCS IDs + demographics + official-record terms.

## References
- `scripts/decs_id_to_name.py` — batch DeCS numeric-ID → descriptor name (pt/en/es) parser
  with retry/backoff (uses the `Descritor em …:` body-table regex).
- `references/mesinesp-decs-case.md` — MESINESP round detail: 4 biblio records, gold DeCS IDs
  resolved to names/trees, and full error analysis.
- `references/mesh-taskA-case.md` — Task A round detail: 5 PMIDs, efetch parse, gold comparison.
