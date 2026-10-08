# 跨物种海马 ATAC 比例分析 — 权威数据与映射（2026-08-29）

## 数据源
- 人脑：`E:\专利\human_meta.csv`（265,909 cells / 40 individuals）
- 猴脑：`E:\专利\monkey_meta.csv`（161,497 cells / 21 individuals）
- 人脑年龄权威源：`D:\我的下载\media-2\Supplemental Tables S1-S24\Table_S1.tsv`（Zemke GSE278576 官方补充表，Donor ID / Age / Age group / Sex / Assays）

## 人脑 40 个 multiome donor 精确映射（Table_S1 逐条代码提取，禁止手排）

Donor → Age → Age_group → Sex（40 行）：
```
77=20, 78=20, 5579=25, 76=26, 29=28, 6052=28, 5614=31, 13344=33, 935=38, 937=38      [20-40 组, M, M, F, F, M, M, M, F, F, F]
1134=41, 13414=41, 5021=43, 5087=44, 1745=46, 4781=46, 81=48, 5610=50, 5551=54, 6021=55  [40-60 组]
13394=65, 73787=66, 46426=68, 1265=69, 8=69, 1271=71, 1153=75, 1203=75, 69984=75, 1216=79  [60-80 组]
98=82, 12=83, 11=86, 73=86, 19=87, 26=89(89+), 40=89(89+), 212191=89(89+), 35=89(89+), 9=89(89+)  [80-100 组, F, M, M, M, F, M, F, F, M, F]
```
- RDS Sample 列 = `GSM8549615_hc77` 格式 → donor 号 = `sub(".*hc([0-9]+)$","\\1",Sample)` → `stopifnot(all(donor %in% donor_map$Donor))` 零容忍校验
- 80-100 组有 5 个 donor 原文标 89+（未确认精确年龄）→ 写 89 保 Age_group=80-100
- ⚠️ **Donor 5276（22 岁）不在队列**：Table_S1 有它但 Assays = `snm3C-seq`（无 10x multiome）→ 不产生 ATAC 数据。判断是否应在队列 = 查 Assays 列，不是看它有没有出现在 Table_S1
- ⚠️ **手排陷阱**：把 Donor ID 按年龄人为排序会整体错位（hc78 实为 20 不是 25，2026-08-29 用户当场抓错）——任何映射必须从 Table_S1 用代码逐条提取

## 猴脑 63 文库 → 21 个体
Sample 名 `M1_Hip_1` / `O2_Hip_3` / `V1_Hip_1` / `Y3_Hip_2` → individual = 前缀（M1/O2/V1/Y3），`sub("_Hip_.*","",Sample)`。
- 每文库 `_Hip_N` 后缀是同一大脑的重复文库，不是独立个体
- 前缀字母 = 年龄组：M=Middle, O=Old, V=Exceptionally old(very old), Y=Young
- 各年龄组个体数（2026-08-29 实测）：Young=4（Y3/Y4/Y5/Y7）、Middle=5（M1-M5）、Old=6（O1-O6）、EO=6（V1-V6）——⚠️ Young 只有 4 个体（张潇原文 23 只里可能覆盖更全），报告时注明

## 年龄组统一（跨物种按生命阶段，不是数值）
| 统一阶段 | 猴脑（张潇原稿） | 人脑 |
|---------|----------------|------|
| Young | 5-6 岁 | 20-40 岁 |
| Middle | 10-12 岁 | 40-60 岁 |
| Old | 22-23 岁 | 60-80 岁 |
| Exceptionally old | 28-31 岁 | 80-100 岁 |
- 依据：张潇原稿（young adult 5-6y / middle-aged 10-12y / old 22-23y / exceptionally old 28-31y，EO 接近圈养寿命上限）+ Zemke Table_S1 的 4 年龄组
- 实现：人脑加 `age_stage` 列（20-40→Young 等），猴脑 Age_group 直接用；两侧统一后再合并比较

## 细胞类型注释（2026-08-29 用户最终定稿，覆盖之前所有存档注释）
- 人脑（30 cluster → 7 类）：ExN=C17,C18,C19 / InN=C14,C15,C16 / Astro=C7-C12 / Micro=C20-C23 / OPC=C1-C6 / ODC=C24-C30（含 C26！）/ Unknown=C13
- 猴脑（18 亚群 predictedAnno → 8 类）：ExN=2,3,4,8,9,10,11 / InN=5,6,13,14 / Astro=1,12 / Micro=15 / OPC=17 / ODC=16 / VS=18 / ChP=7（数字 = predictedAnno 亚群编号，不是 Clusters）
- 有机生命沙箱（E:/专利/patent/monkey_Hf_ATAC_final.rds）可读 predictedAnno 真实亚群名：CA1_SUB s_f_Ex / CAE_SUB deep Ex / Microglia / EC L6 EX / MGE SST lnh / CGE LAMP5 lnh / Astrocyte / MGE PVALB lnh / EC L3_5 EX / DG Ex / CGE CNR1 lnh / OPC / CA2_4 EX / Ependymal / ODC / VS / Choroid Plexus / EC L2 EX

## 已交付结果（2026-08-29）
- `celltype_pct_individual.csv`（425 行，61 个体，个体水平比例）
- `figures/celltype_stacked_agegroup.png`（物种×年龄组×细胞构成堆叠柱）
- `figures/celltype_boxplot_agegroup.png`（6 共有类型箱线 + Young vs EO Wilcoxon）
- 核心发现：人/猴 Astro 同向下调（人 p=0.002）、OPC 同向下调（猴 p=0.010）、ODC 同向上调 → 跨物种一致性 = 专利"物种可代替性"第一证据