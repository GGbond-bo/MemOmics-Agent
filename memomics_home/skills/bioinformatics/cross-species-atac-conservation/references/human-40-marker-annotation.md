# 人侧 40 样本 getMarkerFeatures 注释协议（C1-C30, 2026-08-17 初版 → 2026-08-27 8 大类终版 → 2026-08-27 噪声判定更正）

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

## 🔴 8 大类终版判定 + 证据级 marker 排名法（2026-08-27 用户铁律"一定要有依据，不然全是错的"）

### 方法论升级：不要用"词典命中数"，用"特异 marker 最佳排名"

第一版用宽泛 marker 词典（ExN 列表长达 50+ 基因）数命中数 → **ExN 词典长必赢**，C14-C16（真 InN）被误判 ExN。修正：**只比"教科书级特异 marker"在按 Log2FC 降序的全量列表里的最佳排名**。

| 证据等级 | 判定 |
|---------|------|
| strong | 特异 marker 排名 ≤30 |
| moderate | 31-100 |
| weak/none | >100 或无命中 |

```python
# 8 大类特异 marker（人海马 ATAC 验证版，2026-08-27）
specific = {
    'ExN':  ['SLC17A7','NEUROD2','NEUROD6','NRGN','CDK5R2','ICAM5','FEZF2','BCL11B',
             'CACNG4','SEZ6L','ELFN2','MYT1','CHAD','ASCL1','GSX1','TOX2','C1QL1',
             'TMEM132C','KCNQ2','SNCB','INA'],
    'InN':  ['DLX1','DLX6','GAD2','SLC32A1','LHX6','PVALB','SST','ADARB2','CALB2',
             'VIP','CNR1','LAMP5','NXPH1'],
    'Astro':['GFAP','AQP4','SLC1A2','EDNRB','WIF1','HSPB8','ALDH1L1','CRYAB','EMX2',
             'S1PR1','FABP7','FGFR3','CST3','GJA1'],
    'Micro':['CSF1R','CX3CR1','TMEM119','C1QA','C1QB','TYROBP','CD83','CXCL10','CD163',
             'GPNMB','SPI1','ITGAM','HEXB','AIF1'],
    'OPC':  ['PDGFRA','CSPG4','OLIG1','OLIG2','TSHZ2','GPC5','GPR17','COL20A1','LHFPL3','SOX1'],
    'ODC':  ['MBP','MOG','PLP1','OPALIN','MAL','CLDN11','MOBP','CNP','MYRF'],
    'VS':   ['PECAM1','CLDN5','FLT1','VWF','RGS5','PDGFRB','ACTA2','MYH11','TAGLN',
             'DCN','FOXC2','NOTCH3','LYVE1'],
    'ChP':  ['TTR','FOLR1','FOXJ1','CFAP126','CLIC6'],
}
```

判定实现（核心逻辑）：每 cluster 取各类型 marker 的最小排名 → 最小者胜出 → 证据分级。

### ⛔ 已知误判陷阱（2026-08-27 实测踩过）

1. **OPCML ≠ OPC marker！** OPCML（Opioid Binding Protein / Cell Adhesion Molecule Like）是**神经元** marker（海马 DG 高表达）。之前误放进 OPC 词典导致 C1-C6 误判"OPC 混合"。
2. **CSPG4 双身份**：CSPG4 同时是 OPC 经典 marker 和 DG 神经元 marker——以它在哪个 cluster 排名更前为准（人侧 C1-C6 中 CSPG4 排 8-52，不是主导）。
3. **ExN 词典不要贪长**：泛神经元基因（SYT1/SYN1/GRIN1 等）会把 InN/Astro cluster 的命中数也拉高。用强特异基因（SLC17A7/NEUROD2/FEZF2/BCL11B 等）。
4. **HOX 基因群 = 伪影/背景**：C13 的 top marker 全是 HOXD11/HOXB5/HOXA2/MNX1/TLX1（正常成人海马不表达 HOX 发育基因）→ 不是任何细胞类型，**过滤而非注释**。GRM6（视网膜双极细胞）混入更证实污染。
5. **"炎性小胶质"确认基因**：CSF1R/CX3CR1 可能只排 30+（moderate），但 **IRF8(rank12)/ABI3(rank9)/P2RY13(rank14)/C3AR1(rank6)/TNF/S100A8** 直接坐实 Micro 炎症型。
6. **存疑 cluster 必须复核 + L1 辩论**：C12/C13/C20 经 debate 裁决 modify 后逐 cluster 读 top30 编码 marker 才定论。

### ⛔⚠️ 噪声判定三重门（2026-08-27 推翻旧"C25-C29=噪声"结论——必须三查再定性！）

**旧判例把 C25/C26/C28/C29 直接判"噪声"（依据：OR 基因 / peak 数 <5）——被 2026-08-27 全量重分析推翻，尤其 C26 绝不是噪声：**

**推翻证据**：
- C26 有 1146 个 marker，其中 **825 个（72%）是 C26 特异**（只在 C26 出现，非共享背景）
- C26 特异 marker 含**真实神经元基因**：GAD2、SLC17A6、FOXP2、CALB1、EOMES + GPC5/CSMD3/NRG1/ROBO2/DCC/EPHA6/RIMS1/CNTN4
- 用户跑 `plotGroups(TSSEnrichment, plotAs="violin")` → **TSS 很高** → 与"低质量垃圾群"矛盾

**正确三重门（不满足不得判噪声/剔除）**：
1. **QC 三指标**：TSSEnrichment + log10(nFrags) + DoubletScore。**TSS 高 = 不是低质量**，先别定性
2. **marker 特异性**：每个 marker 出现在几个 cluster（特异 vs 共享背景）。特异占比高（C26=72%）→ 有真实身份信号
3. **特异 marker 生物学构成**：是否真实细胞类型基因（GAD2/SLC17A6/NRGN 等神经元基因），不能只看 OR/非编码 RNA

**正确处理（大细胞量 + 高 TSS + 高特异占比 = 亚分离真实 cluster，不是垃圾）**：
- ① subset 出来提高分辨率重聚类（addIterativeLSI iterations=2, resolution=1.5）看能否拆出真实群
- ② 专利最稳 = cellColData 标 "Ambig" + 下游 DA/保守性分析排除（不冤枉也不带病）
- ③ 仅当 QC 明确差（低 TSS + 低 Frags + 高 DoubletScore）才剔除

**教训**：OR/味觉基因 + marker 数量少 ≠ 噪声。OR 基因是 mappability 假 peak 的背景信号，特异 marker 占比和 QC 才是决定性证据。

### 终版 8 大类判例（2026-08-27，已过 L1 辩论 + 逐 cluster 复核）

| Cluster | 终版注释 | 依据（特异 marker 排名） | 证据 |
|---------|---------|--------------------------|------|
| C1-C6 | **ExN（DG 颗粒神经元）** | CACNG4/SEZ6L/ELFN2/MYT1/BCL11B rank 1-3 | strong |
| C7-C12 | Astro（C12 标注异质性） | GFAP/AQP4/SLC1A2/EDNRB/HSPB8 rank 1-6；C12 GFAP rank10+SLC1A2 rank18+EMX2 rank20 混 ZIC5/OTX1/FOXG1 | strong |
| C14-C16 | **InN** | **DLX1 rank1 / DLX6 rank1-2**（最硬证据）+ SLC32A1/GAD2/LHX6 | strong |
| C17-C19 | ExN（深层为主） | SLC17A7/NEUROD2/NEUROD6/NRGN/CDK5R2 rank 2-10 | strong |
| C20 | Micro（炎性型） | IRF8 rank12 / ABI3 rank9 / P2RY13 rank14 / C3AR1 rank6 / TNF / S100A8 | strong（复核确认） |
| C21 | VS | CLDN5 rank4 / FOXC2 | strong |
| C22-C23 | Micro（激活/炎症） | CSF1R/CX3CR1/C1QA/C1QB/TYROBP rank 1-6 | strong |
| C30 | ODC | OPALIN rank1 | strong |
| **C13** | ❌ 过滤（HOX 伪影） | HOXD11/HOXB5/HOXA2/MNX1 top | 无任何 8 类 marker |
| C25/C28/C29 | ⚠️ 待定（低 marker 数） | 仅 1-5 个 marker，OR/味觉基因 | **需 QC + 特异 marker 复核**，未过三重门不得判死 |
| **C26** | ⚠️ **神经元富集（非噪声）** | 825/1146 特异 marker（72%），含 GAD2/SLC17A6/FOXP2/CALB1/EOMES | **重聚类 / 标 Ambig，不剔除** |

### 🔴 C1-C6 判定修正：NPC → ExN（DG 颗粒神经元）——与 2026-08-17 不同

08-17 曾判 C1-C6 为"❓ 神经祖 NPC"（因 MYT1/DLL3/ASCL1/SOX1/GSX1 签名，见下方旧判例）。
08-27 用 8 大类特异 marker 排名法复核：**CACNG4(#1-7)/SEZ6L/ELFN2/MYT1/CHAD/GSX1/C1QL1 全部排进前 20，ExN 命中 22-24 个且均 Log2FC 2.0-2.3 强度远超 OPC** → **定为 ExN（DG 颗粒神经元）**。CHAD 是 DG 颗粒细胞 marker（Allen Brain Atlas 支持），GSX1 是 DG 特异转录因子——两者同时出现是 DG 实锤。
**误区解释**：08-17 把 DLL3/ASCL1/SOX1 当"神经祖签名"，实际这些基因在 DG 颗粒神经元也有表达；且当时没意识到 OPCML 是神经元 marker、CSPG4 是双身份。若想最终确认 NPC vs DG Ex，用 UMAP 核对 `plotEmbedding(proj, colorBy="GeneScoreMatrix", name="CHAD"/"GSX1"/"PROX1")` + 对照 Table_S7 官方 18 亚类。

## 28 群注释地图（2026-08-17 初版判例，保留供对照）

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
| **C1-C6** | MYT1(#1-3), DLL3(#4-46), ASCL1(#11-58), SOX1(#9-36), GSX1, CACNG4(#3-7), TMEM100(#7-35), SEZ6L, ELFN2, C1QL1, (CSPG4 #8-52) | **❓ 初判神经祖；08-27 修正为 ExN（DG 颗粒神经元）** | 🔴→🟢 |
| C13 | MNX1(#2), HOXB5(#3), HOXD11(#1), FOXF1, GRM6 | **❌ 异常群**（运动神经元/体轴 HOX 签名，非海马）→ 污染嫌疑，剔除 | 🔴 |

## 合并方案（28 群 → 8 类）—— 专利实施例采用

```
Inh   = C14+C15+C16
Ex    = C1-C6 + C17+C18+C19   ← 08-27 修正：C1-C6 并入 ExN（DG）
Astro = C7+C8+C9+C10+C11+C12
Micro = C20+C22+C23（C23 可单列反应性）
VS    = C21
ODC   = C30
剔除  = C13（HOX 伪影）          ← 08-27 修正：C25/C26/C28/C29 不再直接剔除！
待定  = C25/C26/C28/C29         ← 需 QC（TSS/nFrags/DoubletScore）+ 特异 marker 复核；
                                  C26 已被证明神经元富集（72% 特异 marker），标 Ambig + 下游排除
                                  或提高分辨率重聚类，不得凭 marker 数判死
```

> ⚠️ **8 大类对齐是专利注释的最优粒度**：权利要求写"细胞类型包括兴奋性/抑制性神经元、星形胶质、小胶质等"覆盖面比 59 亚型宽，且没有亚型分不开的漏洞（亚区级 DG/CA1/CA2-4/EC 在 ATAC 分辨率下分不开是公认局限，统一标 ExN 即可）。

## 与猴侧 8 大类对齐提示

猴侧已注释 8 大类（Ex/Inh/Astro/Micro/OPC/ODC/VS/ChP）。人侧 C1-C6 定为 ExN(DG) 后，与猴侧 DG Ex 直接对应（猴侧 NHPABC 有 DG Ex 亚群）。跨物种对齐时 OPC 与 ExN 的边界用同一套 marker（CACNG4/CHAD/GSX1 vs PDGFRA/OLIG1）裁定。