# Pre-QC'd Seurat 对象的 verify-not-re-run 工作流

场景：用户给的 .rds 是**已预处理**对象（已过滤/已标准化/已有降维/已有注释），却要求"做基础 QC、标准化、降维聚类、识别亚型"。

## 第一步：探测是否 pre-processed（写任何代码前）

看 meta.data 与 reductions：
- `percent.mt` max 恰好落在整阈值（如 4.99 → 上游用过 5% 截断）
- `nFeature_RNA`/`nCount_RNA` 范围已是健康窗口（如 501-7807 / 1001-24847）
- 已存在 `pca`/`harmony`/`umap` reductions + `annotation_L3` 等注释列
- 已有 `SCT` assay（3000 HVG + scale.data）→ 标准化已完成

命中 ≥3 条 → **不要重复硬过滤、不要重跑 SCT/PCA/Harmony、不要覆盖已有 embedding**。重跑 883MB 对象既浪费又可能破坏已有注释结构。

## 第二步：按 L1 辩论裁决走 report-only

2026-08-14 实测裁决（MF_subset_2000.rds）：
```
verdict=modify, confidence=high
qc_thresholds: percent.mt/nFeature_RNA/nCount_RNA → report_only（不设硬阈值）
outlier_handling: flag_only_no_exclusion
normalization: SCTransform（已有则确认即可）
use_existing: [harmony, umap, annotation_L3]
clustering: map_to_existing_annotation
```
执行内容 = QC 分布图（VlnPlot×3 + scatter）+ 按 type/sample 的 QC 统计表，不 subset。

## 第三步：注释可靠性统计闭环（L2 "need_more_info" 裁决的标准应答）

当 L2 辩论对注释裁决 need_more_info（反方：缺效应量/阳性率/FDR）时，不要只靠 mean expression 辩护，跑两个数值证据：

1. **阳性率矩阵**：每 marker × 每亚群 `expr>0` 的细胞百分比 → `marker_pct_by_subtype.csv`
2. **每亚群代表 marker Wilcoxon**：`FindMarkers(ident.1=亚群, features=marker, only.pos=TRUE, logfc.threshold=0)` → 报 avg_log2FC + pct.1/pct.2 + p_val_adj → `marker_DE_by_subtype.csv`

通过标准（实测）：主 marker `avg_log2FC>1.5`、阳性率差大（如 98% vs 44%）、`p_val_adj < 1e-100` → 注释可靠结论有统计支撑。

## MF_subset_2000.rds 实测数据（人骨骼肌纤维）

- 20,000 cells × 51,227 genes；RNA+SCT；pca/harmony(30d)/umap
- QC: nFeature med 2491 (501-7807), nCount med 5165 (1001-24847), MT med 0.35% (max 4.99), ribo med 0.35%
- 6 组: Y_Pre 3767 / Y_Post 2930 / O_Pre 2923 / O_Post 2901 / OD_Pre 3636 / OD_Post 3843；48 samples
- annotation_L3 10 亚群各 2000 cells：LRP1B+(I), OTUD1+(I), OTUD1+(II), Pure Type I, Pure Type IIA, Pure Type IIX, RP_high(I), RP_high(II), RSS, Specialized MF
- 验证亮点: Pure Type IIX MYH1 avg_log2FC=3.65 (98.3% vs 44.4%, p=0); RP_high(I) MYH7 1.75; RP_high(II) MYH2 1.83
- marker 规范：Type I=MYH7/TNNI1/TNNT1, IIA=MYH2/TNNI2, IIX=MYH1 (Schiaffino & Reggiani 2011)
