# GSE278576 人海马 ATAC 全量注释与年龄元数据（2026-08-28/29 定稿，取代旧的 9 样本 pilot 假设）

> ⚠️ gse278576-atac-aging-comparison skill 是 manual skill 不可写，本文件挂在本 skill（cross-species-atac-annotation）下，两者内容交叉引用。

## 1. 数据全量状态（用户已提供，非 pilot）

| 物种 | RDS | 细胞 | cluster | 注释列 | 年龄 |
|------|-----|------|---------|--------|------|
| 人 | `E:/专利/patent/human_Hf_ATAC_40_clustered.rds` | 265,909 | C1-C30 连续 30 群 | 用户定稿 `cellType8`（8 大类） | 40 donors，4 组各 10：20-40/40-60/60-80/80-100 |
| 猴 | `E:/专利/patent/monkey_Hf_ATAC_final.rds` | 161,497 | 63 文库 / predictedAnno 18 亚类 | 用户定稿（8 大类） | rds 自带 Age(5-31) + Age_group(4 组) |

⚠️ markerList CSV 只有 28 行≠30 群（C24/C27 无显著 marker 被 getMarkerFeatures 省略，但群真实存在）——群数一律以 `length(unique(proj@cellColData$Clusters))` 为准（见本 skill P7）。

## 2. 用户定稿注释（勿覆盖，2026-08-28 用户说"全部注释成功"）

- **人脑**（keyed on `Clusters` C1..C30）：OPC=C1-6, Astro=C7-12, Unknown=C13, InN=C14-16, ExN=C17-19, Micro=C20-23, ODC=C24-30
- **猴脑**（keyed on **`predictedAnno` manuscript codes** 1-18，不是 `Clusters`）：ExN=2,3,4,8,9,10,11；InN=5,6,13,14；Astro=1,12；Micro=15；OPC=17；ODC=16；VS=18；ChP=7
- predictedAnno 编号→名称映射：1=Astrocyte, 2=CA1_SUB s_f_Ex, 3=CA2_4 EX, 4=CGE CNR1 lnh, 5=CGE LAMP5 lnh, 6=Choroid Plexus, 7=DG Ex, 8=EC L2 EX, 9=EC L3_5 EX, 10=EC L6 EX, 11=CAE_SUB deep Ex, 12=MGE SST lnh, 13=MGE PVALB lnh, 14=Microglia, 15=ODC, 16=OPC, 17=Ependymal, 18=VS
- R 写回必须 `as.character()` 目标列再 index（factor 按整数索引 bug，见本 skill P1）

## 3. 年龄元数据

- 人脑：GEO series matrix 无 age 字段；donor→age 在用户提供 `D:/我的下载/media-2/Supplemental Tables S1-S24/Table_S1.tsv`（48 行；筛 `Assays` 含 "10x multiome" = 恰好 40 donors）
- **必须程序化生成映射**（pandas 读 TSV 再吐 R vector），严禁手写——曾手写串位被用户抓包（hc78 实际 20 岁非 25；见 P23）
- 猴脑：rds 自带。4 组：Young(5-6, n=6)/Middle(10-12, n=5)/Old(22-23, n=6)/EO(28-31, n=6)（张潇原稿正文 + Fig1 legend）
- 跨物种对齐 = **life stage（非绝对年龄）**：hum 20-40→Young, 40-60→Middle, 60-80→Old, 80-100→EO（详见 references/life_stage_alignment_and_celltype_proportion_stats.md）

## 4. 细胞比例物种×年龄分析（毕业论文交付，2026-08-29 定稿）

- 统计单位 = **个体**（human 40 / monkey 21），禁止拿细胞数当 n（伪重复）
- 年龄组 ordinal → **Spearman ρ**（非 Pearson）；方向（±）、强度（|ρ|）、显著性（p）分开读
- "双不显著（ρ≈0, 均 ns）"也是同向一致证据（InN 案例），可支撑可替代性；只有物种分歧才是反证
- 仅 shared celltype（ExN/InN/Astro/Micro/OPC/ODC）做跨物种统计；人 Unknown、猴 VS/ChP 不共用
- 产出图型：concordance per-celltype（mean±SEM 轨迹 + 个体点 + ρ[Bootstrap CI] p 图例）——复用 `scripts/concordance_astro_opc.py` 改 celltype 循环
- 配色需用户批准后统一复用（Okabe-Ito 色盲安全提案）

## 5. Peak calling / 下游管线（2026-08-29/30 实测）

- 人脑 peak 已出：525,137 个 501bp fixed-width（正常；ArchR resize 501 是默认标志非 bug）；猴脑在集群 addGroupCoverages → addReproduciblePeakSet 阶段
- 张潇 NHPABC cCRE 官方参数：addGroupCoverages(minCells=40, maxCells=5000, minReplicates=2, maxReplicates=10)；addReproduciblePeakSet(maxPeaks=500000, cutOff=0.01)；501-bp peaks
- **先决条件**：loadArchRProject 的 Project outputDirectory 必须本人可写，否则 HDF5 H5Fcreate 报错（copyArchRProject 到自己目录）；call peak 后必须 addPeakMatrix 再 getMatrixFromProject
- 猴脑（T2T-MFA8v1.1, RefSeq NC_088375.1）绝不能用 hg38 BSgenome；chromSizes 以 NC_ 开头 = 猴，chr = 人
- L1 序列保守：Windows 本地读 bigWig 工具链全灭（pyBigWig 无 win wheel / rtracklayer UCSC 库失败 / conda 无 win 包）→ phyloP 批量打分必须在 Linux 集群 `pip install pyBigWig`；UCSC 无 T2T-MFA8 chain → 基因 ortholog 锚定（详见 atac-seq-memomics references/peak-calling-production-pitfalls.md）
- 人猴 Y 染色体：猴全雌无 Y；人含男→人侧 peak 文件应无 chrY（call peak 前排除或未通过 reproducible 门槛），跨物种比较限定常染色体+X；方法学写明人猴性别构成差异