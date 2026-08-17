# MESINESP Round — DeCS Semantic Indexing Case (2026-08-02)

Exam: 试卷3_多语言检索MESINESP — 4 Spanish-language medical abstracts, output DeCS codes.
Score: semantic F1 28.1%, strict 0%. Full error analysis.

## The fatal error
Assumed "DeCS = MeSH in Spanish, same tree numbers" and answered with MeSH tree numbers
(e.g. `E04.928.760` for Thoracotomy). Gold uses **BIREME numeric DeCS IDs** (e.g. `23039`).
Strict match = 0%. Even semantically-correct labels scored zero on format.

## Gold records (decsCodes resolved to names/trees for future calibration)
- biblio-1000005 (纵隔肿瘤): 11 labels — Anciano(20174), Neoplasias(9562), Adenocarcinoma,
  Mediana Edad(9062), Timo, Mediastino, Humanos(21034), Femenino(21030), Masculino(21044),
  Toracotomía(23039), Tomografía Computarizada.
- biblio-1000026 (中性粒细胞减少性小肠结肠炎/LLA): 7 labels — Enterocolitis Neutropénica,
  Leucemia-Linfoma Linfoblástico de Células Precursoras, Neoplasias(9562), Humanos(21034),
  Dolor Abdominal, Enfermedades del Ciego, Diarrea.
- biblio-1000027 (TAC凝集技术/抗红细胞抗体): 7 labels — Lab Clínico, Placa Hemolítica,
  Humanos(21034), Anticuerpos, Hemólisis, Ictericia, Tipificación Sanguínea y Pruebas Cruzadas.
- biblio-1000028 (活动舌癌): 10 labels — Quimioterapia Combinada, Glosectomía, Cirugía General,
  Neoplasias de la Lengua, ENT Neoplasms, Humanos(21034), Mediana Edad(9062), Femenino(21030),
  Masculino(21044), Lengua.

## What I got right / wrong
- Right: semantic core disease terms (Adenocarcinoma, Toracotomía, Enterocolitis Neutropénica).
- Wrong: format (tree numbers vs numeric IDs); systematically missed ALL demographics (Humans/
  Femenino/Masculino/age groups = 9 of 35 gold labels); guessed indexer-only terms incorrectly
  (Biopsia, Fiebre, Carcinoma Escamoso were NOT in gold); missed official-index terms
  (Enfermedades del Ciego, Placa Hemolítica, Ictericia, Glosectomía).

## Repeated pattern across rounds
Task A (PubMed MeSH) had the SAME demographic-blindness: filter `MajorTopicYN="Y"` dropped
Humans/Male/Female/Age from gold. Both rounds confirm: **benchmark gold includes demographic
qualifiers; do not filter them out.**

## DeCS resolution endpoint
`https://decs.bvsalud.org/ths/resource/?id=<numeric_id>` returns name + tree for a numeric ID.
Note: this endpoint was reached via urllib — the site may be slow; use retries.
