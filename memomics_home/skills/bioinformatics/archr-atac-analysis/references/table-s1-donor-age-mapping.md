# Table_S1 样本→年龄映射（GSE278576 人海马 40 donor）铁律

## 事故记录（2026-08-29，用户当场抓错）

曾"凭印象"手排 40 个样本的 age_map（hc78 写成 25，Table_S1 实际 20），
被用户揭穿："你是ai,怎么还错这么离谱呢？" / "78不是20岁吗？"
上一版从第二个样本开始整体错位（hc5579=26 实际 25，一路错到尾）。

**根因**：Table_S1 的 Donor ID 行序与年龄**不是单调对应**。按年龄从小到大
"顺排"会对齐错位；同一年龄组内 Donor ID 乱序（80-100 组 5 个 donor 都是
89+，靠"看起来像"必错）。

## 铁律：映射只准代码匹配，禁止手写占位

```r
# 1. 从 Table_S1.tsv 读出权威映射（Donor ID → Age / Age_group / Sex / Assays）
# 2. 从 RDS 的 Sample 列提取 hc 编号（Sample 形如 GSM8549615_hc77）
donor <- sub(".*hc([0-9]+)$", "\\1", proj$Sample)
# 3. match 合并，零缺失校验（40/40 不匹配就报错，不允许放行）
stopifnot(all(donor %in% donor_map$Donor))
proj$Age       <- donor_map$Age[match(donor, donor_map$Donor)]
proj$Age_group <- donor_map$Age_group[match(donor, donor_map$Donor)]
proj$Sex       <- donor_map$Sex[match(donor, donor_map$Donor)]
```

交付前必跑 `table(proj$Age_group, useNA="always")` + 抽查 head。

## Table_S1 结构要点（避免后续再踩）

- **48 行 ≠ 40 个 ATAC 样本**。只有 Assays 列含 `10x multiome` 的 40 个 donor
  在人脑 ATAC 队列；其余 7 个纯 confocal fluorescence、1 个（Donor 5276, 22 岁, M）
  纯 `snm3C-seq`——**5276 不在 40 multiome 内，不是漏样本**。
  判别看 Assays 列，不要凭 Donor 编号"像不像"。
- **Age_group 四组平均**：20-40 ×10 人 / 40-60 ×10 / 60-80 ×10 / 80-100 ×10，
  细胞数 ~61.8K / 70.1K / 70.3K / 63.7K（265,909 细胞全匹配）。
- **80-100 组 5 个 donor（hc26/hc40/hc212191/hc35/hc9）Table_S1 标 `89+`**：
  代码按 89 写入，Age_group 仍 80-100，报告注释"≥89 未确认精确值"。
- 完整 40 行映射表：`results/memomics-cd677556/task2/human_donor_age_map_exact.csv`
  集群可跑脚本：`results/memomics-cd677556/scripts/write_human_age_group.R`
  （含 Age_group + Sex 写回 + stopifnot 校验，直接复制到集群执行）。