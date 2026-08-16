# Specialized MF 比例显著性案例（2026-08-17）

## 数据
- `E:/骨骼肌锻炼/special_MF_annotation_umap.rds`（原文件，中文路径）→ 英文副本 `results/<sid>/data/special_MF_annotation_umap.rds`
- Seurat 对象 **11,630 细胞 × 51,227 基因**（⚠️ 曾误报"51,227 细胞"——`dim()` 返回 (genes, cells)，ncol=细胞数）
- meta.data 列：`samplename`(48 样本) + `type`(6 组: Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post) + `subcluster`(7 亚群: NMJ + zone1-6)
- 细胞数：NMJ 59 / zone1 3022 / zone2 822 / zone3 808 / zone4 1254 / zone5 4912 / zone6 753（求和=11,630 ✓）
- 另有打分列：scoreI_AUC/scoreII_AUC/Denervation_AUC/scoreRegMyon_AUC/scoreAtrophy_AUC/scoreExercise_AUC/scoreSenMayo_AUC/Score_Remodeling/Score_PathoLock/Pathology_Index

## 流程
1. **R 提取 meta 落盘 CSV**（01_extract_meta.R）：`.libPaths('E:/R-libs/R-4.5.3')` + R-4.5.3 全路径 terminal Rscript；容错取列 `get_col(c('samplename','sample'))`；只取 3 列存 CSV 避免后续重读 528MB RDS
2. **Python 算显著性 + 比例表**（02_significance.py，见下方核心代码）

## 02_significance.py 核心（可直接复用）
```python
import pandas as pd, numpy as np
from scipy.stats import wilcoxon, mannwhitneyu
from statsmodels.stats.multitest import multipletests

# per-sample 比例: 亚群细胞数/样本总细胞数
cell_counts = meta.groupby(['samplename','type','subcluster']).size().reset_index(name='n_cells')
sample_totals = cell_counts.groupby('samplename')['n_cells'].sum().rename('total')
cell_counts = cell_counts.merge(sample_totals, on='samplename')
cell_counts['proportion'] = cell_counts['n_cells']/cell_counts['total']

# 补零（0 细胞样本）: full_idx MultiIndex 全组合 → merge → fillna(0)

# base_id 配对键
full['base_id'] = full['samplename'].str.replace(r'_(Pre|Post)$', '', regex=True)

# Cliff's delta 方向翻转（正值=后者组高，用户约定）
def cliffs_delta(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    gt=0; lt=0
    for x in a:
        gt += np.sum(b > x); lt += np.sum(b < x)
    return (gt-lt)/(len(a)*len(b))

# 配对比较: base_id inner_join 后 wilcoxon(proportion_2, proportion_1)
# 独立比较: mannwhitneyu(v2, v1) + cliffs_delta(v1, v2)
# 双 FDR: multipletests(p, method='fdr_bh') per_celltype + 全局
```

## 9 比较对定义
```python
COMPARISONS = [
    ('Y_pre_post',  'Y_Pre',  'Y_Post',  True),   # 年轻运动
    ('O_pre_post',  'O_Pre',  'O_Post',  True),   # 老年运动
    ('OD_pre_post', 'OD_Pre', 'OD_Post', True),   # 糖尿病运动
    ('YvsO',        'Y_Pre',  'O_Pre',   False),  # 衰老
    ('OvsOD',       'O_Pre',  'OD_Pre',  False),  # 糖尿病
    ('YvsOD',       'Y_Pre',  'OD_Pre',  False),  # 年轻 vs 老年糖尿病
    ('Ypost_vs_Opost',  'Y_Post','O_Post', False),
    ('Opost_vs_ODpost', 'O_Post','OD_Post', False),
    ('Ypost_vs_ODpost', 'Y_Post','OD_Post', False),
]
```

## 结果（六组比例中位数）
```text
亚群     Y_Pre   Y_Post   O_Pre   O_Post   OD_Pre  OD_Post
NMJ     0.0000  0.0000  0.0000  0.0000  0.0000   0.0035
zone1   0.0154  0.0288  0.1047  0.2151  0.0556   0.1864
zone2   0.0000  0.0182  0.0542  0.0239  0.0986   0.0674
zone3   0.0000  0.0000  0.0159  0.0660  0.0268   0.0622
zone4   0.0000  0.0000  0.0049  0.1043  0.0625   0.0356
zone5   0.8133  0.7849  0.5952  0.2351  0.5303   0.5000
zone6   0.1442  0.1179  0.1079  0.0922  0.0592   0.0241
```

## 显著性要点
- **衰老效应（Y_Pre→O_Pre）**：zone5 显著↓（p=0.0046, FDR_per=0.0139, FDR_global=0.0485, delta=-0.80）；zone3↑（p=0.0234, FDR_per=0.0421）+ zone1↑（p=0.0271）为趋势
- **糖尿病效应（O_Pre→OD_Pre）**：7 亚群全不显著（p 均 >0.12）
- **老年运动（O_Pre→O_Post 配对）**：zone3↑（p=0.0156, FDR_per=0.0352）+ zone5↓（p=0.0156 同）
- **糖尿病运动（OD_Pre→OD_Post 配对）**：仅 zone6 p=0.0469（FDR_global=0.123），其余不显著
- 解读：zone5=核心衰老下降群（年轻 81%→老年 60%），糖尿病轴整体无信号

## 产出文件
- `data/special_MF_meta.csv`（meta 3 列，11630 行）
- `data/special_MF_significance.csv`（63 行：9 比较 × 7 亚群，含 p/FDR_per_celltype/FDR_global/eff）
- `data/special_MF_proportion_by_group.csv` + `data/special_MF_proportion_median_pivot.csv`

## 探索箱线图（03_boxplot_6grp_cluster1.R，2026-08-17 追加）

**触发**：用户"先做第一组，6个柱子的箱线图，我先看看效果"——按逐亚群门禁先出第一个亚群（zone1/cluster1）的 6 组探索图。

**模板要点**（可复用为后续亚群画图脚本）：
- 读 `special_MF_meta.csv` → 每样本每亚群比例（`n / sample_total`）→ 6 组 factor 顺序 `Y_Pre..OD_Post`
- 亚群显示名映射：`zone1-6 -> cluster1-6`（用户拍板改名），NMJ 不变；`label_map <- c(NMJ='NMJ', zone1='cluster1', ...)`
- 画图：`ggplot + geom_boxplot(outlier.shape=NA, fill='#f0f0f0') + geom_jitter(width=0.14, color='#3b6fb5') + theme_bw(base_size=11)`；标题 `Specialized MF: cluster1 (6 groups)`
- **显著性标注从 CSV 读，不重算**：`comp_sig <- sig_ct[sig_ct$paired != 'True' & sig_ct$p < 0.05, ]`——⚠️ paired 是字符型，`== FALSE` 永远匹配不到（2026-08-17 实测踩坑，图上 0 标注不报错）
- 手动括号：`annotate('segment'/'text', y = base_h + (i-1)*step, label=paste0('p=', formatC(p, format='f', digits=3)))`，括号高度随比较数递增（`base_h <- ymax*1.08; step <- ymax*0.08`），`coord_cartesian(ylim=c(0, ymax*1.30))` 预留标注空间
- 探索图尺寸 **140×110mm, 300dpi, bg='white'**（定稿才用 egg::set_panel_size 柱数规则）

**cluster1 实测标注**（raw p 探索版，4 个独立比较显著）：
| 比较 | p |
|------|-----|
| Y_Pre vs OD_Pre | 0.0054 |
| Y_Pre vs OD_Pre（YvsOD） | 0.0161 |
| Y_Post vs O_Post | 0.0217 |
| Y_Pre vs O_Pre（YvsO） | 0.0271 |

**⚠️ 生物学解读警示（L1 辩论 verdict=modify, high）**：cluster1 比例年轻组极低（Y_Pre 1.5%）→ 老年升高（O_Pre 10.5%）→ **老年运动后继续升（O_Post 21.5%）**，糖尿病运动组也保持高位（OD_Post 18.6%）。方向与"运动逆转去神经"知识库预期**相反**——运动后 Specialized MF 比例反而升。定稿前必须补 **pseudobulk（DESeq2, FDR<0.1）验证**，防止 10 vs 7 小样本个体异质性带偏；raw p 探索标注须注明未校正。产出 `explore_6grp_cluster1_boxplot.png`、脚本 `03_boxplot_6grp_cluster1.R`。