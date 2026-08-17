# Protein Classification Logic — 分泌蛋白四类分类详解

## 分类决策树

```
For each protein:
│
├─ gene in {ALB, INS, TF, BSA}?
│   → Class IV: Background/Media
│
├─ gene matches KRT* / Histone / RPS* / RPL*?
│   → Class IV: Background/Contamination
│
├─ has_signal_peptide AND is_extracellular AND NOT is_cytoplasmic?
│   ├─ gene in EV_DB (ExoCarta/Vesiclepedia)?
│   │   → Class II: Dual (Free + EV)
│   └─ else
│       → Class I: Free Soluble
│
├─ (is_cytoplasmic OR is_mitochondrial) AND NOT has_signal_peptide?
│   → Class III: EV/Exosome Cargo
│
├─ gene in EV_DB AND NOT has_signal_peptide?
│   → Class III: EV/Exosome Cargo
│
└─ fallback: has_signal_peptide?
    → Class I: Free Soluble
    → else: Unclassified
```

## UniProt 查询字段

```
GET https://rest.uniprot.org/uniprotkb/search
  ?query=gene:{GENE}+AND+organism_id:9606
  &fields=accession,gene_names,ft_signal,cc_subcellular_location
  &format=json&size=3
```

关键判断依据：
- `features[].type == "Signal"` → has_signal_peptide
- `comments[].subcellularLocations[].location.value` 含 "Secreted"/"Extracellular" → is_extracellular
- 含 "Cytoplasm" → is_cytoplasmic
- 含 "Mitochondrion" → is_mitochondrial

## EV 数据库参考基因集（人，部分）

```
HSPD1, PRDX1, HSPA8, HSP90AA1, HSP90AB1, GAPDH, ACTB, ACTG1,
TUBB, TUBA1B, TUBA1C, PKM, LDHA, LDHB, ENO1, ALDOA, PGK1, TPI1,
CLU, FN1, FLNA, ANXA2, YWHAZ, YWHAE, YWHAQ, PPIA, CFL1, PFN1,
EZR, GSTP1, PRDX6, PHB1, PHB2, AHCY, EEF1A1, NPM1, PTMA,
HNRNPA2B1, VAPA, SOD1, CAT, SLC25A5, SLC25A6, ATP6V0C, TXN
```

## 显式校正规则

分类完成后必须强制执行以下规则（覆盖 API 查询结果）：

```
gene ~ KRT  → Class IV: Background/Contamination
gene ~ ^H[2-4]|Histone|H2A|H2B|H4 → Class IV: Background/Contamination
gene ~ ^RP[SL] → Class IV: Background/Contamination
gene in {ALB, INS, TF} → Class IV: Background/Media
```

## 四类蛋白的生物学含义

| 分类 | 机制 | 验证方法 |
|------|------|----------|
| Free Soluble | 经典分泌 → 表面受体结合 → 信号激活 | ELISA + 重组蛋白 add-back |
| Dual (Free+EV) | 双重存在形式，需组分分离后分别验证 | EV分离后游离/EV组分分别定量 |
| EV/Exosome Cargo | 包装入EV → 囊泡摄取 → cargo释放 | EV add-back + cargo阻断 |
| Background | 污染/培养基添加/细胞裂解假象 | 排除 |
