# 猴侧 RDS 注释全流程 — 远端 Arrow / 本机仅 RDS 场景（2026-08-27 monkey_Hf_ATAC_final.rds 实证）

## 场景
- 数据：`E:/专利/patent/monkey_Hf_ATAC_final.rds`（ArchRProject, 161,497 cells, 63 samples, 30 clusters C1-C30, 4 年龄组 Young/Middle/Old/Exceptionally old）
- Arrow 全部指向远端 `/hwfssz3/PS_JLU/zhangxiao6/ArchR/input/Hf/saveProj20250710/ArrowFiles/`（本机不存在）
- → 无法 getMarkerFeatures / plotMarkerHeatmap / imputeWeights；注释只能靠 RDS 内资产

## RDS 内可用资产（检查顺序）
```r
x <- readRDS("monkey_Hf_ATAC_final.rds")
colnames(x@cellColData)
# 本会话实测列：Sample, TSSEnrichment, ReadsInTSS, ReadsInPromoter, ReadsInBlacklist,
# PromoterRatio, PassQC, NucleosomeRatio, nMultiFrags, nMonoFrags, nFrags, nDiFrags,
# DoubletScore, DoubletEnrichment, BlacklistRatio, Clusters, Individual, Age, Age_group, predictedAnno
getArrowFiles(x)                    # ⚠️ 不是 x@arrowFiles（v1.0.3 无此 slot）
names(x@reducedDims)                # IterativeLSI, Harmony
names(x@embeddings)                 # UMAPHarmony
umap <- getEmbedding(x, embedding="UMAPHarmony")   # ✅ 可用，坐标随 RDS 保存
getOutputDirectory(x)               # 远端输出目录
```

## 🔴 R 命名向量索引坑（关键教训）
`map8[cc$predictedAnno]` 当 predictedAnno 是 **factor** 时按整数索引而非名字匹配
→ 结果分布整体错乱且难察觉：本会话 Micro 列显示 28,854（实际 = DG Ex 的数量），Anno8 分布全错。
修复：`map8[as.character(cc$predictedAnno)]` → 分布正确（ExN 69,047 / ODC 44,021 / Astro 23,548 / Micro 9,388 / InN 6,714 / OPC 6,574 / Epend 879 / CP 702 / VS 624，总和 = 161,497 对账通过）。
已 record_error 到 annotate_celltype_scRNA。

## 流程
1. **每簇纯度**：`table(predictedAnno)` → 主注释占比
2. **18 亚类 → 8 大类映射**（map8 见 SKILL.md）
3. **低纯度簇诊断**：top5 注释组成（哪些亚类混在一起）
4. **Ambig 判定**：second>20% 且不同大类 → Ambig；或跨大类比值差距 <10pp
5. **Ambig 裁决**：C14/C26/C3 → Ambig_requery（保守）：
   - C14（77 cells, 0.05%）：ExN 72.7 × Astro 27.3 → 极小簇
   - C26（1316 cells）：CP 47.4 × VS 41.1（差 6.3pp）→ ATAC 共可及性混杂，不硬归
   - C3（568 cells）：Micro 56.2 × ExN 31.3 → 主类过半但混入明显
6. **出图 4 张**：Clusters / predictedAnno(18) / Anno8(8) / 低纯度簇高亮
7. **落表 + 写回**：CSV（含 human_Anno 对比列）+ cellColData 存 RDS

## 关键洞察
- 30 簇中 27 簇 8 大类下纯度 95-99.9% —— "低纯度"主要来自大类内亚型混合（CA1/DG/EC 都是 ExN），粗粒度映射后自动解决
- 人猴簇号不对应（各自独立聚类）→ 跨物种比较按注释类型而非簇号
- L1 辩论连续 2 次 need_more_info → 停止重试，按反方共识 + KB 惯例保守裁决

## 产物（本会话）
- `results/memomics-cd677556/task2/results/monkey_cluster_annotation_final.csv`（30 簇裁决 + 人侧对比）
- `results/memomics-cd677556/task2/results/monkey_Hf_ATAC_annotated_cellColData.rds`
- `results/memomics-cd677556/task2/results/monkey_lowpurity_composition.csv` / `monkey_anno8_age.csv`
- `results/memomics-cd677556/task2/figures/monkey_umap_{clusters,predictedAnno,anno8,lowpurity}.png`
- `results/memomics-cd677556/task2/scripts/monkey_annotation_full.R`（可复用模板）