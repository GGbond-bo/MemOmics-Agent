# 猴脑/人脑 年龄组划分与跨物种统一映射（2026-08-29 用户原文章核实）

## 权威依据：张潇《Multimodal brain cell atlas across the adult macaque lifespan》(Revised text-final.docx)

原文（Results 第 75 行 + Figure 1 legend 均写明，用户提供原稿 D:/学习文献/Revised text-final.docx）：

> "They spanned four age groups: **young adult (5-6 years, n = 6), middle-aged (10-12 years, n = 5), old (22-23 years, n = 6), and exceptionally old (28-31 years, n = 6)**. The exceptionally old group corresponds to the **upper end of the typical lifespan** for this species in captivity and is considered rare.

> Transitions from young to middle age, middle age to old, and old to exceptionally old ... were defined as the **early, late, and very late** stages of aging, respectively."

### 猴脑 4 组（23 只雌性食蟹猴，Macaca fascicularis）

| 官方分组 | 年龄(岁) | n | 阶段定义 |
|---------|---------|---|---------|
| Young（青年） | 5-6 | 6 | 性成熟后完全成年 |
| Middle-aged（中年） | 10-12 | 5 | early aging 起始 |
| Old（老年） | 22-23 | 6 | late aging |
| Exceptionally old（超高龄） | 28-31 | 6 | very late aging，接近圈养寿命上限（罕见） |

- **划分逻辑 = 生物学阶段，不是等间隔**：EO 组单独拎出代表"长寿/健康衰老"（接近寿命上限者）；三阶段递进描述衰老进程（early/late/very late）
- **用户猴脑样本年龄**（9 个）：5, 10, 11, 12, 22, 23, 28, 29, 31 → 映射：5→Young；10/11/12→Middle；22/23→Old；28/29/31→EO。**全部落在官方分组内，无需自定义**
- 猴脑 RDS 的 Age_group 列值 = 'Young' / 'Middle' / 'Old' / 'Exceptionally old'

## 人脑 4 组（GSE278576, 40 样本）

| 组 | 年龄(岁) |
|----|---------|
| 20-40 | 青年 |
| 40-60 | 中年 |
| 60-80 | 老年 |
| 80-100 | 超高龄 |

人脑 RDS 的 Age_group 列值 = '20-40' / '40-60' / '60-80' / '80-100'

## 🔴 跨物种统一铁律：按生命阶段对齐，不按数值对齐

用户问"是不是应该统一呢？"——**必须统一，但禁止按数值对齐**（20-40 ≠ Young！）。物种寿命不同（人 ~80+，食蟹猴圈养 ~25-30），跨物种比较必须用"生命阶段"而非绝对年龄。这是 species×age 混合效应模型、细胞比例跨组比较的前提。

### 统一映射（2026-08-29 用户确认方案）

| 生命阶段 | 猴脑（张潇原文） | 人脑 | stage 标签 |
|---------|----------------|------|-----------|
| Young 青年 | 5-6 岁 | 20-40 岁 | Young |
| Middle-aged 中年 | 10-12 岁 | 40-60 岁 | Middle |
| Old 老年 | 22-23 岁 | 60-80 岁 | Old |
| Exceptionally old 超高龄 | 28-31 岁 | 80-100 岁 | EO |

### 数据展示与建模规则

1. **表里两物种都保留原始区间（证据可追溯）+ 加一列统一 `stage` 标签**——不丢原文依据，跨物种比较用 stage
2. **比例表/建模用统一 stage**（celltype × stage 交叉表，两物种各一张 + 合并对比表）
3. 报告/专利里写明猴脑分组引自张潇 2026 原文（4 组 n=6/5/6/6），引用不自定义
4. 人脑 RDS 若 Age_group 是 '20-40' 字符串，写 stage 映射时用 match/ifelse 映射表，不许手工逐样本填（沿用人侧 donor age map 的代码级匹配铁律）

## 相关脚本

- 已有脚本：`scripts/celltype_agegroup_proportion.R`（人/猴通用：表 4. 交叉表 + 列百分比 + 行百分比 + 导出 CSV）
- RDS 路径确认：本机 `E:/专利/patent/` 只有原始 clustered rds；带 Age_group 注释的版本（human_Hf_ATAC_40_withAge_exact.rds / monkey rds）在集群或需用户确认位置