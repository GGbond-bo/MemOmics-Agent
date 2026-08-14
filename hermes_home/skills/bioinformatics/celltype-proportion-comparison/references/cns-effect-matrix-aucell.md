# CNS 级"效应矩阵"图组 — AUCell/多打分 meta CSV 可视化配方（2026-08-14 实测）

场景：细胞级 meta CSV（每行=细胞），含 `samplename` / `type`（6组：Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post，个体配对）/ `annotation_L3`（10 亚群）+ 22 个 AUCell 打分列（`score*_AUC` + 基因集打分，全 0-1 无缺失）。目标：CNS 主刊审美，一图回答"哪些打分被衰老/运动/糖尿病改变"。

实测数据：`E:\骨骼肌锻炼\MF_AUCell_meta.csv`（508,661 细胞 × 58 列）。产出 `figures/Fig1_effect_matrix.png/pdf` + `Fig2_paired_response` + `Fig3_aging_vs_exercise`。

## 统计设计（防伪重复，样本级聚合）

1. **样本×亚群聚合**：50 万细胞直接算 = 伪重复。`fread`/`pd.read_csv` 后按 `samplename × annotation_L3` 取打分均值 → 48样本×10亚群≈479 行。落盘 `agg_sample.csv`。
2. **效应**（每 打分×亚群×效应 组合）：Cohen's d = `(mean(B)-mean(A))/sqrt((var(A)+var(B))/2)` + Wilcoxon 秩和 p，BH 校正（按效应分组校正）。三效应：Aging(Y_Pre→O_Pre) / Exercise_O(O_Pre→O_Post) / T2D(O_Pre→OD_Pre)。落盘 `effect_table.csv`。
3. **逆转率**（仅对 Aging 显著 p<0.05 组合）：`reversal = 1 - (O_Post − Y_Pre)/(O_Pre − Y_Pre)`；>0=向年轻回拉，<0=恶化。实测中位数：Metabolic +0.21 / Identity +0.36 / Senescence −0.07 → "运动是衰老的镜子，只照见代谢-结构这一半"。

## 打分排序与功能轴分组（22 打分实测）

```python
score_order = ['scoreOxPhos_AUC','Glycolysis_AUC','FattyAcidMetabolism_AUC','AMPK_PGC1a_AUC',
 'scoreSarcomeric_AUC','scoreRegMyon_AUC','Autophagy_AUC','Adipogenesis_AUC','mTORC1_AUC','scoreInsulin_AUC','scoreROS_AUC',
 'scoreI_AUC','scoreII_AUC','scoreIIa_AUC','scoreIIx_AUC',
 'scoreSenMayo_AUC','scoreStress_AUC','scoreTNFA_AUC','scoreInflammatory_AUC','Denervation_AUC','scoreAtrophy_AUC','Fibrosis_AUC']
grp = ['Metabolic']*11 + ['Identity']*4 + ['Senescence']*7
grp_col = {'Metabolic':'#2E86AB','Identity':'#F6AE2D','Senescence':'#F25F5C'}
```

## 核心代码（Python 一次性成功；matplotlib 需 `matplotlib.use('Agg')`）

### pivot 效应矩阵
```python
def pivot(eff, val):
    d = res[res['effect']==eff].pivot(index='score', columns='sub', values=val)
    return d.reindex(score_order).reindex(columns=subs)
mA, mE, mT = pivot('Aging','d'), pivot('Ex_O','d'), pivot('T2D','d')
pA = pivot('Aging','p')
```

### Fig1 Hero：3 面板效应热图 + 逆转率条
```python
from matplotlib.colors import TwoSlopeNorm
cmap = LinearSegmentedColormap.from_list('cns', ['#2166AC','#F7F7F7','#B2182B'])
norm = TwoSlopeNorm(vmin=-3, vcenter=0, vmax=3)   # ±3 截断
ax.imshow(X, cmap=cmap, norm=norm, aspect='auto')
# 星号：双层循环
if not np.isnan(Pv[i,j]) and Pv[i,j] < 0.05: ax.text(j, i, '*', ha='center', va='center', fontsize=5)
# 行分组分隔线
for c in np.cumsum([11,4,7])[:-1]: ax.axhline(c-0.5, color='white', lw=1.2)
# 布局：gridspec 1行5列 width_ratios=[0.35,1,1,1,0.12]（轴色条/热图×3/逆转率条）
# 逆转率条 norm=TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1)，配色 #B2182B→白→#2166AC
```

### Fig2 配对个体响应（老年 Pre→Post 连线）
```python
agg['ind'] = agg['samplename'].str.rsplit('_',1).str[0]   # Old_5_Pre → Old_5
w = d.pivot(index='ind', columns='type', values=sc).dropna()  # 只留 O_Pre/O_Post
from scipy.stats import wilcoxon
_, pv = wilcoxon(w['O_Post'], w['O_Pre'])
# 每个体画连线 + Pre/Post 散点，标题带 p
```

### Fig3 Aging vs Exercise 效应散点
```python
# x=mA 展平, y=mE 展平, 按 grp 分色; axhline(0)/axvline(0) 参考线 + 对角线 ax.plot([-5,5],[-5,5], ls=':')
# 标注 top-6 |d| 组合的 (亚群, 打分)
```

## 关键踩坑（本配方实测）
- `pivot` 后必须 `.reindex(score_order).reindex(columns=subs)` 对齐行/列序（ComplexHeatmap 在 R 端自动对齐，matplotlib 不会）
- 大 CSV 用 `pd.read_csv` 读 50 万行几秒，R `fread` 也快——但**当 R 端 DLL 损坏时直接 Python 读 CSV 是逃生通道**（中间表已落盘）
- 配对 wilcoxon 需要 Pre/Post 都有的个体（`.dropna()` 过滤），个体数不足会抛错 → `try/except` 返回 NaN
- 图内标签用英文（CNS 惯例），避免中文字体配置；汇报用中文结论先行
- 三图一次 `execute_code` 跑完，每图独立 tryCatch 式分段，单图失败不影响其他
