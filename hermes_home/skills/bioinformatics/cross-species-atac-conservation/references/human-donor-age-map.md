# GSE278576 人海马 40 donor → Age 精确映射（2026-08-27 代码级核验）

> ⚠️ 本文是唯一可信的 donor→age 映射。**禁止手排占位符 age_map**——曾因手排把
> hc78 错写为 25（实际 20）被用户当场抓出（"你是 AI 怎么还错这么离谱"）。
> 任何写回 RDS 的 Age/Age_group 必须走下方"代码级匹配流程"。

## 数据源（已确认，替代旧的 metadata.tsv.gz 说法）

| 项 | 值 |
|----|----|
| 摘要表 | `D:/我的下载/media-2/Supplemental Tables S1-S24/Table_S1.tsv`（49 行 = 表头 + 48 donor × 11 列） |
| 列结构 | Donor ID / Age / Age group / Sex / Source / Brain bank id / Assays / Cause of death / PMI / Braak Stage / Race |
| GEO | GSE278576，**80 samples = 40 donors × (10x Multiome + snm3C-seq)** |
| RDS Sample 列 | 40 个，格式 `GSM8549615_hc77` … `GSM8549654_hc9`（GSM 连续 40 个） |
| 文章年龄分组 | 20-40 / 40-60 / 60-80 / 80-100 四组，每组恰好 10 donor |
| 细胞数 | 265,909（20-40 组 61,798 / 40-60 组 70,124 / 60-80 组 70,335 / 80-100 组 63,652） |

- ✅ **Table_S1.tsv 就是 donor 级年龄的权威来源**（GEO series matrix 只有按细胞类型/年龄组的
  伪 bulk `.bw`，不含每个 donor 的年龄）。
- ❌ 旧记录"必须下载 `GSE278576_hippocampus_RNA_seurat_object_filtered_cells_metadata.tsv.gz`
  （12MB）按 orig.ident 分组提取" → **不可用**（该 GEO 文件 404），且没必要——Tabel_S1 已在本地。

## 40 donor 精确映射（40/40 校验通过，零 NA）

| # | GSM | hc | Donor | Age | Age_group | Sex |
|----|-----|----|-------|-----|-----------|-----|
| 1 | GSM8549615 | hc77 | 77 | 20 | 20-40 | M |
| 2 | GSM8549616 | hc78 | 78 | 20 | 20-40 | M |
| 3 | GSM8549617 | hc5579 | 5579 | 25 | 20-40 | F |
| 4 | GSM8549618 | hc76 | 76 | 26 | 20-40 | F |
| 5 | GSM8549619 | hc29 | 29 | 28 | 20-40 | M |
| 6 | GSM8549620 | hc6052 | 6052 | 28 | 20-40 | M |
| 7 | GSM8549621 | hc5614 | 5614 | 31 | 20-40 | M |
| 8 | GSM8549622 | hc13344 | 13344 | 33 | 20-40 | F |
| 9 | GSM8549623 | hc935 | 935 | 38 | 20-40 | F |
| 10 | GSM8549624 | hc937 | 937 | 38 | 20-40 | F |
| 11 | GSM8549625 | hc1134 | 1134 | 41 | 40-60 | M |
| 12 | GSM8549626 | hc13414 | 13414 | 41 | 40-60 | M |
| 13 | GSM8549627 | hc5021 | 5021 | 43 | 40-60 | F |
| 14 | GSM8549628 | hc5087 | 5087 | 44 | 40-60 | M |
| 15 | GSM8549629 | hc1745 | 1745 | 46 | 40-60 | F |
| 16 | GSM8549630 | hc4781 | 4781 | 46 | 40-60 | M |
| 17 | GSM8549631 | hc81 | 81 | 48 | 40-60 | F |
| 18 | GSM8549632 | hc5610 | 5610 | 50 | 40-60 | F |
| 19 | GSM8549633 | hc5551 | 5551 | 54 | 40-60 | M |
| 20 | GSM8549634 | hc6021 | 6021 | 55 | 40-60 | F |
| 21 | GSM8549635 | hc13394 | 13394 | 65 | 60-80 | F |
| 22 | GSM8549636 | hc73787 | 73787 | 66 | 60-80 | M |
| 23 | GSM8549637 | hc46426 | 46426 | 68 | 60-80 | M |
| 24 | GSM8549638 | hc1265 | 1265 | 69 | 60-80 | F |
| 25 | GSM8549639 | hc8 | 8 | 69 | 60-80 | M |
| 26 | GSM8549640 | hc1271 | 1271 | 71 | 60-80 | M |
| 27 | GSM8549641 | hc1153 | 1153 | 75 | 60-80 | F |
| 28 | GSM8549642 | hc1203 | 1203 | 75 | 60-80 | F |
| 29 | GSM8549643 | hc69984 | 69984 | 75 | 60-80 | M |
| 30 | GSM8549644 | hc1216 | 1216 | 79 | 60-80 | F |
| 31 | GSM8549645 | hc98 | 98 | 82 | 80-100 | F |
| 32 | GSM8549646 | hc12 | 12 | 83 | 80-100 | M |
| 33 | GSM8549647 | hc11 | 11 | 86 | 80-100 | M |
| 34 | GSM8549648 | hc73 | 73 | 86 | 80-100 | M |
| 35 | GSM8549649 | hc19 | 19 | 87 | 80-100 | F |
| 36 | GSM8549650 | hc26 | 26 | 89+ | 80-100 | M |
| 37 | GSM8549651 | hc40 | 40 | 89+ | 80-100 | F |
| 38 | GSM8549652 | hc212191 | 212191 | 89+ | 80-100 | F |
| 39 | GSM8549653 | hc35 | 35 | 89+ | 80-100 | M |
| 40 | GSM8549654 | hc9 | 9 | 89+ | 80-100 | F |

**89+ 处理**：Table_S1 原文标 `89+`（≥89 未确认），写入数值列用 89，Age_group 仍为 80-100；
连续年龄模型注意这 5 个是右删失。

## 5276 为什么不在 RDS（常见疑问，2026-08-27 用户问"漏了？"）

- Table_S1 里 **Donor 5276 = 22 岁, M, 20-40 组**，但 `Assays` = **仅 `snm3C-seq`**（无 `10x multiome`）。
- GSE278576 的 **80 samples = 40 donors × 2 assays**；人脑 ATAC RDS 只含 **40 个 10x multiome donor**。
- 所以 5276 **本来就不该出现在 ATAC RDS**（不是遗漏）。Table_S1 全部 48 donor 里含
  "10x multiome" 的恰好 40 个 = RDS 的 40 个，无缺无多。同理解释 "80 samples vs 40 donors"。

## 代码级匹配流程（禁止手排，必须走这段）

```r
library(ArchR)
proj <- readRDS("E:/专利/patent/human_Hf_ATAC_40_clustered.rds")  # 用户路径

donor_map <- data.frame(
  Donor = c("77","78","5579","76","29","6052","5614","13344","935","937",
            "1134","13414","5021","5087","1745","4781","81","5610","5551","6021",
            "13394","73787","46426","1265","8","1271","1153","1203","69984","1216",
            "98","12","11","73","19","26","40","212191","35","9"),
  Age = c(20,20,25,26,28,28,31,33,38,38,
          41,41,43,44,46,46,48,50,54,55,
          65,66,68,69,69,71,75,75,75,79,
          82,83,86,86,87,89,89,89,89,89),
  Age_group = c(rep("20-40",10), rep("40-60",10), rep("60-80",10), rep("80-100",10)),
  Sex = c("M","M","F","F","M","M","M","F","F","F",
          "M","M","F","M","F","M","F","F","M","F",
          "F","M","M","F","M","M","F","F","M","F",
          "F","M","M","M","F","M","F","F","M","F")
)

donor <- sub(".*hc([0-9]+)$", "\\1", proj$Sample)
stopifnot(all(donor %in% donor_map$Donor))   # 40/40 必须全匹配，否则报错

proj$Age       <- donor_map$Age[match(donor, donor_map$Donor)]
proj$Age_group <- donor_map$Age_group[match(donor, donor_map$Donor)]
proj$Sex       <- donor_map$Sex[match(donor, donor_map$Donor)]

stopifnot(sum(is.na(proj$Age)) == 0, sum(is.na(proj$Sex)) == 0)
print(table(proj$Age_group, useNA="always"))
```

完整可跑脚本（2026-08-27 本机跑通）：
- `results/memomics-cd677556/scripts/write_human_age_group.R`
- 产出：`results/memomics-cd677556/task2/human_Hf_ATAC_40_withAge_exact.rds`
- 映射 CSV：`results/memomics-cd677556/task2/human_donor_age_map_exact.csv`

## 教训（用户 2026-08-27 明确纠正）

1. **绝不给"占位示例"让用户自己核对**。给用户数字映射 = 必须一次性精确。
2. **sample→metadata 映射必须以数据源为准**（RDS Sample 列 ↔ Table_S1 Donor ID），
   不许凭记忆/推断/手排。
3. 交付前自检：40/40、零 NA、无重复、Age_group 四组 10/10/10/10。
4. 用户会拿记忆里的真实值抽查（如"78 不是 20 岁吗"）；错一位 = 失去信任。
5. 手排 age_map 的典型错误是**整表错位**（hc78 应为 20 却被写成 25，后面全部顺延错位）——
   这正是"逐条代码匹配 + stopifnot"能拦住的错误类型。