# Cross-Species Brain Tissue Replaceability Assessment — S100-S600 Framework

## Full S-Sequence

```
S100  数据获取
  ├─ Species A sc/snRNA-seq: >=4 age groups, >=4 individuals/group
  └─ Species B sc/snRNA-seq: matching age gradient

S200  细胞类型锚定与基因对齐
  ├─ marker genes + label transfer -> shared cell types (6-10 classes)
  └─ Gene alignment: 1:1 ortholog (独立权利要求)
      └─ Alternative: ESM-2 protein embedding (从属权利要求+实施例)

S205  KEY 跨物种技术批次效应校正
  └─ Harmony/scVI residualization -> UMAP mixing verification
     Cell types that fail to mix -> flagged as "评估仅供参考"

S300  分层可代替性评估 (per cell type)

  S310 细胞组成层
  └─ Dirichlet-multinomial: proportion ~ species + age

  S320 KEY 基因表达层 — pseudobulk individual aggregation
  └─ Triple correlation: r_cross vs r_within
     If r_cross >= lower CI of r_within -> species diff <= individual diff

  S330 衰老轨迹层
  └─ cos(theta) = (V_speciesA · V_speciesB) / (|V_speciesA| * |V_speciesB|)
     Gene sets: Hallmarks of Aging, SenMayo, SASP (NOT disease-specific)

  S335 KEY 年龄等效变换
  └─ age_scaled = (age - mean)/sd per species
     OR: biological equivalent age (e.g., monkey age * 3.5 -> human-equivalent)

  S340 KEY 方差分解层 — mixed effects model
  └─ expression ~ species + age_scaled + species:age_scaled + (1|individual)
     Extract: beta_species, beta_age, beta_interaction, sigma2_individual
     SDI = |beta_species|^2 / sigma2_individual
     (Statistic in independent claims; thresholds in dependent claims)

  S350 功能层
  └─ Aging gene sets * per-layer判定 -> pathway-specific replaceability heatmap

S400 KEY A/B/C/D Four-Level Gene Classification
  A级: SDI < threshold AND cos(theta) > high -> fully replaceable
  B级: SDI < threshold BUT cos(theta) moderate -> quantitatively replaceable
  C级: SDI moderate BUT cos(theta) > high -> directionally replaceable
  D级: SDI > high threshold -> NOT replaceable

  This classification is the ROUTING TABLE for all downstream applications.

S500  综合可代替性指数 (IRS)
  IRS = alpha*S_comp + beta*S_expr + gamma*S_trajectory + delta*(1-P_D_class)
  Weights determined by grid search sensitivity analysis

S600  方法验证体系
  S610 进化锚点: Human > Monkey > Mouse IRS ordering
  S620 阴性对照: Species label permutation test (>=1000 iterations)
  S630 文献交叉验证: D-class gene literature divergence rate vs A-class
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Pseudobulk at individual level | Single-cell-level cross-species comparison = pseudoreplication. n=5 vs n=5 is real biological replication. |
| species*age interaction | "Replaceability" is NOT "how similar are monkey and human at baseline" but "do they age in the same way?" |
| SDI statistic in independent claims | Objectively defined, computable. Thresholds go in dependent claims (empirically chosen). |
| ESM-2 NOT in independent claims | Black-box -> 充分公开 rejection risk. Goes in dependent claims + alternative embodiments. |
| 1:1 ortholog in independent claims | Verifiable, transparent, reproducible. Examiner can understand it. |
| Batch correction (S205) | Uncontrolled technical confounders = reviewer's first attack. Must be explicit step. |
| Age scaling (S335) | Raw ages differ across species (monkey 5yr != human 20yr). Must normalize before mixed model. |

## Key Pitfalls

1. **Without S335**: species*age interaction is uninterpretable when raw ages differ across species
2. **Without S205**: detected "species differences" may be batch effects from different labs/platforms
3. **S320 at cell level instead of individual level**: pseudoreplication -> inflated significance -> false positives
4. **ESM-2 in independent claims**: examiner can't verify -> 充分公开驳回
5. **Hard SDI thresholds in independent claims**: examiner asks "where did these numbers come from?" -> put in dependent
