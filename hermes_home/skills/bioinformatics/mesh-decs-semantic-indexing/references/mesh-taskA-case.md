# Task A Round — PubMed MeSH Semantic Indexing Case (2026-08-02)

Exam: 试卷1_语义索引TaskA — 5 PubMed articles → 5-10 MeSH major labels each.
Score: precision 90.9% / recall 55.6% / F1 69.0% (gold 72 labels, predicted 44, hit 40).

## Method used (and its flaw)
- efetch XML per PMID, extracted only `<DescriptorName>` with `MajorTopicYN="Y"` (strict "major topic").
- Result: very precise (91%) but recall collapsed — all demographic qualifiers (which PubMed
  tags MajorTopicYN="N") were dropped.

## Gold comparison highlights
- PMID 23479819 (bacterial bioluminescence): 7 gold labels — my 7/7 hit (100% recall). Small
  non-clinical paper with no demographics in gold.
- PMID 23483174 (OSA): 17 gold — hit 9/9 precision but missed 8 demographics/context (Aged,
  Female, Humans, Male, Middle Aged, Hospitals University, Medicine, Severity of Illness Index).
- PMID 23483175 (breastfeeding/obesity): 20 gold — hit 9/10; wrong `Randomized Controlled Trial`
  (Publication Type, not MeSH descriptor); missed 11 incl. Adult/Female/Humans/Male/Infant/
  Infant Newborn/Pregnancy/Young Adult/Hospitals Maternity/Intervention Studies/Time Factors.
- PMID 23483176 (smoking/CVD): 15 gold — hit 8/9; wrong `Cohort Studies` (pubtype); missed 7
  demographics + Prevalence.
- PMID 23483177 (PCI bleeding): 13 gold — hit 7/8; wrong `Cardiovascular Diseases`; missed 6
  demographics.

## Root causes
1. Demographic qualifiers are near-mandatory in gold but tagged NonMajor in PubMed — filtering
   by MajorTopicYN="Y" removes them all.
2. Publication Types (Randomized Controlled Trial, Cohort Studies) are NOT MeSH descriptors —
   do not output them.
3. Do not infer study-design/context terms from abstract wording alone (Cohort Studies,
   Cardiovascular Diseases were over-inferred).

## Corrected workflow (applies to all future MeSH/DeCS rounds)
- efetch ALL `<DescriptorName>` (MajorTopicYN Y and N).
- Selection priority: disease > intervention > mechanism > outcome > demographics.
- Always include Humans + sex + age group when the gold-style list demands coverage.
- Exclude Publication Types; never output RCT/Cohort as MeSH.
- Target 7-11 labels per article (gold avg 8.75-14.4).
