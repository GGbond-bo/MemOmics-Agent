# GSE278576 人海马衰老 ATAC — 案例细节（2026-08-04 实测）

## 论文识别（用户确认过的原文）
| 项目 | 内容 |
|------|------|
| 标题 | Epigenetic and 3D genome reprogramming during the aging of the human hippocampus |
| 正式版 | Science 2026-07-23, PMID 42490474, DOI 10.1126/science.adt8307 |
| 预印本 | bioRxiv 2024-10-17, PMID 39463924, DOI 10.1101/2024.10.14.618338 |
| 通讯作者 | Bing Ren（任兵, UCSD）+ Xiangmin Xu (UCI) |
| 数据 | GSE278576：40 供体 × 2 平台 = 80 samples（10x Multiome snRNA+snATAC 295,033 nuclei；snm3C-seq 22,240 nuclei） |
| 队列 | 4 年龄组：20-40 / 40-60 / 60-80 / 80-100 |
| 可视化 | https://epigenome.wustl.edu/seahorse/ |

## 官方路径（本地已存）
- 官方代码仓库：`github.com/nrzemke/aging_human_hippocampus`（第一作者 Nathan Zemke 官方，Zenodo DOI 10.5281/zenodo.19391232）→ 本地 `E:\专利\Human_Hippocampus_ATAC\official_scripts\aging_human_hippocampus-main\`
- 补充材料：`papers\suppl_media1.pdf`（M&M 全文）+ `papers\suppl_media2\`（Tables S1-S24）
- **Table_S7.tsv（20.8MB）= 472,859 个官方 cCRE 全集**（坐标 + 18 亚类归属）→ 本机首选复用路径
- **Table_S1.tsv = donor→age 映射**（供体年龄分组核对用）
- 本地 fragments：`E:\专利\Human_Hippocampus_ATAC\fragments\`（9 样本 tsv.gz + tbi）

## donor→age 提取（2026-08-08 实测：series matrix 不含 age！）
- ⚠️ `GSE278576_series_matrix.txt.gz` 的 `!Sample_characteristics` 只有 `tissue: hippocampus` + `donor id: hcXX` 两列，**没有 age/sex**
- 正确来源：`GSE278576_hippocampus_RNA_seurat_object_filtered_cells_metadata.tsv.gz`（GSE suppl 页，12MB，295,034 细胞级行）列含 `orig.ident` / `Age` / `Gender` / `age_group` / `subclass`
- 提取法：按 `orig.ident` 分组取 `Age` 唯一值 → donor→age 映射（40 donor，age 20-95，4 年龄组全）
- 完整映射已存：`results/memomics-1c1890da/donor_age_map.json`（挑测试样本/分组核对直接读，不用再下 metadata）
- 挑测试样本规则（跨物种 pilot）：2 年轻 + 2 老年，年龄跨 ≥60 年（如 hc78=20 + hc5579=25 vs hc98=82 + hc9=95），QC 后细胞数 5,800-9,000 稳健优先

## 官方流程参数速查
1. **QC/聚类**：cellranger-arc v2.0.0 → SnapATAC2 (min_num_fragments=500, min_counts=500, min_tsse=5) → tile matrix + select_features n=250000 → scrublet → spectral → umap → leiden；RNA 侧 Seurat SCTransform → rPCA → Leiden res 0.3 → marker+reference 注释 18 亚类
2. **Peak calling（官方代码用 MACS3，论文写 MACS2）**：`macs3 callpeak --ext 150 --shift -75 --nomodel -g hs -q 0.1 --call-summits -f BED` → summit 过滤 `_alt` → iterative_overlap_peak_merging → union 500bp（summit ±250bp）
3. **年龄相关（correlation_ATAC.ipynb）**：每细胞类型 pseudobulk log2CPM vs donor age → Pearson cor.test → shuffle 零分布 ×5000 → FDR<0.1 → Up/Down/No
4. **TF motif**：TF_motif_chrom_access_age_correlation.R，proximal/distal 平衡采样 + Wilcoxon vs 背景

## 9 样本 pilot 实测结果（2026-08-04 跑通）
- 样本：hc77(20)/hc78(20)/hc5579(25)/hc76(26)/hc29(28)/hc6052(28)/hc5614(31)/hc13344(33)/hc935(38) —— **全部 20-40 岁组**
- 总 fragments 15.5 亿（每样本 8,700 万–2.96 亿）；落入官方 cCRE 6.96 亿（45.4%）
- Pearson cor 分布 -0.97~0.94；最小 pval 8.2e-6；**FDR 全 >0.7 → 0 个显著 cCRE**（年龄跨度不足，数据覆盖问题非方法问题）
- 产出：`results/memomics-8857f1c1/gse278576_comparison/` → age_correlation/all_celltypes_pcc_full.tsv (68MB) + cpm_matrix.tsv (90MB) + all_celltypes_pcc_fdr_0.1.tsv (73B 仅表头) + figures/ 5 张图 + log/full_run.log

## 核心脚本（已存于 gse278576-atac-aging-comparison skill）
- `scripts/core_age_correlation.py` —— 官方 cCRE → fragments 计数 → log2CPM → Pearson+FDR 一步完成（pilot 已跑通，9 样本 ~15min 并行）
- 后续 40 样本下齐：同一脚本直接全量重跑即可

## 可视化脚本（2026-08-11 定位）
- **脚本**：`results/memomics-8857f1c1/gse278576_comparison/scripts/visualize_results.py`（纯 matplotlib，无 R）
- **输入**：`age_correlation/cpm_matrix.tsv`（92MB，行=cCRE 列=donor）+ `all_celltypes_pcc_full.tsv`（71MB）
- **输出**：`figures/` 共 5 张（pcc_density / volcano / heatmap_top2000 / cor_by_celltype_boxplot / sample_fragments）
- **热图配方（heatmap_top2000.png）**：按行方差取 Top 2000 变异性 cCRE → 行 z-score（`scipy.stats.zscore(axis=1)`）→ donor 列按年龄升序排序（age_lut 硬编码 9 供体年龄）→ `imshow(aspect="auto", cmap=..., vmin=-2, vmax=2)` → 200dpi
- **配色偏好**：用户 2026-08-11 要求蓝白色 → `cmap="Blues"`（白→蓝渐变），此前默认 `RdBu_r`。改配色只需 patch 脚本第 ~68 行 cmap 后重跑，无需重算数据（TSV 现成，单脚本重跑 <2min）

## 陷阱回顾（本案例实测）
1. snapatac2 全版本无 Windows wheel（macOS/Linux only）→ 2.10.0 源码编译缺 MSVC 必失败；2.9.0 也仅有 mac/linux wheel。**结论：Windows 上不要尝试装 snapatac2，直接官方 cCRE 复用路径**
2. git clone 被墙 → `https://codeload.github.com/nrzemke/aging_human_hippocampus/zip/refs/heads/main` 或 Python requests 下载 zip（20.3MB）
3. Science 官网 403 付费墙 → bioRxiv 预印本免费全文
4. fragments 头部 ~51 行注释需跳过（`#` 开头），数据 5 列 `chr start end barcode count`
5. 单样本计数 456s（纯 Python 逐行 gzip）→ multiprocessing 4 workers 并行 9 样本 ~15min
