# 人侧 40 样本 getMarkerFeatures 注释协议（C1-C30, 2026-08-17）

> 数据：`E:/专利/human_40_markerList.csv`（20,327 行，ArchR getMarkerFeatures 输出，28 群有 marker：C1-C23 + C25/C26/C28/C29/C30；**C24/C27 无 marker**）。
> 列：group, group_name, seqnames, start, end, strand, name, idx, Log2FC, FDR, MeanDiff

## 铁律 0：ATAC GeneScore 的 top marker 不能直接读

每群 Log2FC 最高的 22–45% 是假阳性家族：**MIR/SNORD/SNORA/OR/TAS2R/KRTAP/LOC/LINC/CT/PRAMEF/MAGEA/SSX/RPL/RPS/HIST/C\d+orf/*-AS1/*-DT/*-IT1/*-HG/UBE2Q2L/USP43/SPRY4**。
另有已知噪音基因：CHAD, LCE1D, LCE4A, LCE3B, RTP5, NGB, LCN9, NR0B1, SYCP3, SPRR2A, TAL1, SAGE1, NANOGNB, CT83, CPA5, KLK6, MCAM, HMX2, TCAF2, AMY2A, KLRC4, CLIC2, SERPINB4, FBXO40, GABRE, OOSP2, DCAF8L2, VAV3-AS1。

**正确流程（程序化）**：
1. csv.DictReader 读入（encoding utf-8-sig），按 group_name 分组
2. 每群按 Log2FC 降序排序，先按假阳性 regex 过滤
3. 输出过滤后 top10-12 真实基因
4. **金标准 marker 排名交叉核对**：对每个已知 marker 记录它在全量排序中的名次（`names.index(m)+1`），名次 ≤50 才算命中——高置信注释 = 金标准基因排进前 50
5. 金标准集按细胞类型分组（ExN/InN/Astro/Micro/ODC/OPC/VS/EPC/NPC）便于聚合展示

不能只看 top，不能直接下结论；top 里全是 MIR/SNORD/OR/KRTAP/LOC/LINC 不代表没注释出来——**金标准基因其实都在正确位置，只是被噪声压到 top 50 之外**。

## 28 群注释地图（2026-08-17 实测）

| 群 | 过滤后核心 marker（金标准排名） | 注释 | 置信度 |
|---|---|---|---|
| C14/C15/C16 | DLX1(#1-2), DLX6(#1-2), GAD1(#28-89), SLC32A1(#7-45), LHX6, SRRM4, GJD2, INA, SNCB | **Inh 抑制性神经元** | 🟢 极高 |
| C17/C18/C19 | SLC17A7(#21-471), NRGN(#2-94), NEUROD2(#14-49), NEUROD6(#12), CDK5R2(#4-32), ICAM5, EGR4, FEZF2(#7-15), BCL11B | **Ex 兴奋性神经元**（深层为主） | 🟢 极高 |
| C7-C12 | GFAP(#1-2), EMX2(#5-30), OTX1(#2-26), PAX6, AQP4(#11-105), SLC1A2(#25-144), GJB6, ATP1B2, ETNPPL(C7#2), FOXG1(C7#5) | **Astro 星形胶质**（多群=区域异质性；C7 为特异亚型） | 🟢 高 |
| C20 | C3AR1(#7), IRF8(#15), ABI3(#11), FPR3(#21), P2RY13, HLA-DQA1, ITGAX | **Micro 小胶质**（免疫样） | 🟢 高 |
| C22 | TYROBP(#10), ABI3(#7), FPR3(#8), CX3CR1(#27), SIGLEC7, HLA-DRB1 | **Micro 小胶质**（经典稳态） | 🟢 极高 |
| C23 | CXCL10(#1), CD163(#7), CASP1(#3), S100A8(#6), CLEC5A, MS4A7, FPR2 | **Micro/巨噬 反应性亚型** | 🟡 中 |
| C21 | CCL18(#1), FOXC2(#8), FOXC1(#19), FOXL1(#18), ICAM2(#20), CARMN(#24) | **VS/血管平滑肌/周细胞** | 🟢 高 |
| C30 | OPALIN(#3), MAG(#14), TMEM31(#7), KLK6(#6) | **ODC 少突胶质**（群小 marker 少） | 🟡 中 |
| **C1-C6** | MYT1(#1-3), DLL3(#4-46), ASCL1(#11-58), SOX1(#9-36), GSX1, CACNG4(#3-7), TMEM100(#7-35), SEZ6L, ELFN2, C1QL1, (CSPG4 #8-52) | **❓ 神经祖/未成熟神经元（含 OPC 特征）——不是 Ex！** | 🔴 需验证 |
| C13 | MNX1(#2), HOXB5(#3), HOXD11(#1), FOXF1, GRM6 | **❌ 异常群**（运动神经元/体轴 HOX 签名，非海马）→ 污染嫌疑，剔除 | 🔴 |
| C25/C28/C29 | 100% 假阳性（OR7A5/OR2T4/HMX2/CT47A7） | ❌ 噪声群 → 剔除 | 🔴 |
| C26 | 45% 假阳性（TAS2R9/OR5B2/IFNA10），过滤后无细胞类型 | ❌ 噪声群 → 剔除 | 🔴 |

## 重要修正记录（教训）

- **C1-C6 曾误判为 Ex**（只看 top marker 的 SEZ6L/CACNG4 等神经元基因）。过滤假阳性后真实签名是 **MYT1/DLL3/ASCL1/SOX1/GSX1 = 神经祖细胞（NPC）**，部分群带 CSPG4（OPC）。成熟 Ex marker（SLC17A7/CAMK2A）根本没进前 50 → **C17/C18/C19 才是 Ex**。判断神经元亚型必须看成熟 vs 祖细胞 marker 的区分，不能只看"像神经元基因"。
- **长基因偏倚警告**：MYT1、CSPG4 都是 >500kb 超长基因，ATAC GeneScore 天然虚高。C1-C6 到底是否真 NPC/OPC 不能只靠 marker 表，需两步验证：
  1. UMAP 核对：`plotEmbedding(proj, colorBy="GeneScoreMatrix", name="MYT1"/"SOX1"/"CSPG4"/"SLC17A7")`
  2. 对照 Table_S7 官方 18 亚类（本地 `E:/专利/Human_Hippocampus_ATAC/papers/suppl_media2/Supplemental Tables S1-S24/Table_S7.tsv`）
- 若确认 NPC → 海马神经发生与衰老相关（DG NPC 随龄锐减），是专利"衰老相关可及性变化"的新看点，价值高于纯 Ex。

## 合并方案（28 群 → 8 类）

```
Inh   = C14+C15+C16
Ex    = C17+C18+C19
Astro = C7+C8+C9+C10+C11+C12
Micro = C20+C22+C23（C23 可单列反应性）
VS    = C21
ODC   = C30
NPC   = C1-C6（需验证后并入）
剔除  = C13+C25+C26+C28+C29
```

## 与猴侧 8 大类对齐提示

猴侧已注释 8 大类（Ex/Inh/Astro/Micro/OPC/ODC/VS/ChP）。人侧本表 NPC 群（C1-C6）对应猴侧 OPC/神经祖类目——跨物种对齐时 NPC 与 OPC 的边界要在两侧用同一套 marker（MYT1/SOX1/CSPG4/PDGFRA）裁定，避免"一侧是 NPC、另一侧是 OPC"的粒度错位。
