---
name: secretome-classification
description: >
  Classify proteins from conditioned medium / secretome proteomics into existence forms:
  Class I (Free Soluble), Class II (Dual Free+EV), Class III (EV/Exosome Cargo),
  Class IV (Background/Contamination). Uses UniProt batch query (signal peptide + 
  subcellular location + secretion status) combined with literature-curated EV
  database (ExoCarta/Vesiclepedia). Designed for stem cell / organoid / EB 
  conditioned medium proteomics.
when_to_use: >
  [secretome-classification] 分泌蛋白组分类 / 蛋白存在形式推断 / secretome / 
  conditioned medium / 外泌体蛋白分类 / EV cargo / 上清蛋白组 / 条件培养基蛋白组 /
  "游离可溶蛋白 vs 外泌体相关蛋白" / protein existence form classification
tags: [proteomics, secretome, exosome, EV, conditioned-medium, stem-cell]
---

# Secretome Protein Classification

Classify proteins detected in conditioned medium (secretome proteomics) by their
most likely existence form: free soluble, EV/exosome-associated, dual, or background.

## When to Use

- ✅ Conditioned medium / supernatant proteomics (LC-MS/MS, label-free, TMT)
- ✅ Need to distinguish free secreted proteins from EV cargo
- ✅ Stem cell / organoid / EB secretome characterization
- ✅ Input: Excel/CSV with Protein ID column + intensity columns
- ✅ Output: 4-class annotation + publication figures

## Classification Framework (4 Classes)

| Class | Meaning | Criteria | Mechanism | Validation |
|-------|---------|----------|-----------|------------|
| **I: Free Soluble** | Classic secreted, signal peptide, no EV evidence | Signal=Yes + Secreted=Yes + not in EV_DB | Receptor binding → signaling | ELISA + recombinant add-back |
| **II: Dual (Free+EV)** | Both soluble and EV-associated | Signal=Yes + Secreted=Yes + in EV_DB | Both direct & EV-mediated | EV separation then quantify |
| **III: EV/Exosome Cargo** | Intracellular, packaged into EVs | Signal=No + Secreted=No + in EV_DB | EV uptake → cargo release | EV add-back + cargo block |
| **IV: Background** | Pseudogenes, histones, keratins, ribosomal, intracellular leakage | Various (see subclasses) | EXCLUDE from candidates | N/A |

### Class IV Subclasses

- **IV-A**: Pseudogenes / Histones (H2BC12, H2AC4, H4C1, HNRNPA1L3, ANXA2P2)
- **IV-B**: Keratins (KRT1-18) — possible handling contamination
- **IV-C**: Ribosomal proteins (RPS/RPL) — cell debris from turnover
- **IV-D**: Other intracellular (no signal, not in EV_DB) — stress-induced leakage

## Pipeline

```
Excel/CSV input
    ↓
Extract UniProt IDs + Gene names
    ↓
UniProt batch query (REST API, batch_size=100)
  → signal_peptide (FT SIGNAL)
  → subcellular_locations (CC SUBCELLULAR LOCATION)
  → keywords (KW)
  → is_secreted = "Secreted" in sub_locs or keywords
    ↓
Cross-reference with EV_KNOWN database
  → ExoCarta Top 100 + Vesiclepedia + literature
    ↓
Classify: Class I / II / III / IV
    ↓
Generate Figures:
  Fig1: Pie chart (4 main classes)
  Fig2: Volcano plot (test1 vs test2, color by class)
  Fig3: Priority candidate bar chart (Group A/B)
  Fig4: Classification bar chart with mechanism annotations
    ↓
Export: classified_proteins.csv + figures/
```

## EV_KNOWN Database

See [references/ev-database.md](references/ev-database.md) for the full curated set
of 100+ EV-associated human proteins. Key categories:
- Heat shock proteins (HSP90, HSPA8, HSPD1, HSPE1)
- Glycolytic enzymes (GAPDH, PKM, ENO1, ALDOA, LDHA/B, TPI1, GPI)
- Cytoskeletal (ACTB/G/L, TUBB, TUBA1B/C)
- ECM with EV evidence (COL1A1/2, COL3A1, COL6A1, FN1, SPARC, LUM)
- Dual-localization proteins (APOE, CLU, CST3)
- Redox (PRDX1/6, TXN), 14-3-3 (YWHAE/Q/Z)
- RNA-binding (HNRNPA2B1/K, PTBP1, YBX1)
- Prohibitins (PHB1/2), Annexins

## Key Pitfalls

1. **COL1A1/SPARC/LUM may appear as Class I** — they have signal peptide and are
   secreted, but extensive literature shows EV association. Must be in EV_KNOWN.
2. **CST3 is dual** — secreted via signal peptide but also abundant in EVs.
3. **Keratins are not functional secretome** — classify as IV-B, exclude from candidates.
4. **Serum proteins (ALB, TF, INS)** may come from culture medium supplementation,
   not cellular secretion. Flag but don't exclude if medium was serum-free.
5. **Uncharacterized proteins** (~20/157 in test case) may need manual review.
6. **Pseudogenes** (HNRNPA1L3, ANXA2P2) may be detected but are not functional.

## Reusable Scripts

- `scripts/classify_secretome.py` — Full pipeline: read Excel → UniProt batch query → classify → figures → export

## References

- ExoCarta: http://exocarta.org (Keerthikumar et al. 2016, J Mol Biol)
- Vesiclepedia: http://microvesicles.org (Kalra et al. 2012, PLoS Biol)
- Sarkar et al. 2012, PMID:22984290 — hESC secretome characterization
- Wolling et al. 2018, PMID:29905012 — hPSC differentiation secretome (SILAC)
- [references/ev-database.md](references/ev-database.md) — Full EV_KNOWN gene set


---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="{当前分析} 参数与结果 —— {样本}",
     context="参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<预查的 KB 内容>,
   )
   辩论维度：参数合理性、方法选择正确性、与KB生物学知识一致性、统计方法正确性
3. save_conclusions(module="{模块}", topic="{分析名}", debate_json=<debate返回JSON>, output_dir=<session results_dir>)
   → 写入 {module}/conclusions.md + conclusions.json
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。
⛔ debate confidence=low → 调整参数重跑。
