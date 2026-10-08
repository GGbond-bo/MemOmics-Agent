# 亚群 top1 基因集小提琴图（Subcluster Top-1 Score Violin）

案例日期：2026-08-16（human / skeletal_muscle / aging，MF_AUCell_meta.csv 508,661 细胞）

## 触发场景
用户从 18 程序 × 亚群 z-score 热图（FigA3）里看到各亚群有对应高表达基因集
（"RSS 就非常高表达 Fibrosis，你先挑选出来"），随后要求：
"LRP1B+(I)、OTUD1+(I)、OTUD1+(II)、RP_high(I)、RP_high(II) 这几个亚群，
每个亚群都画自己 top1 的基因打分的小提琴图，横坐标是亚群"。
本质 = 验证各亚群 signature 打分的分布。

## 数据准备（50 万细胞级 CSV 高效路径）
```python
import pandas as pd, numpy as np
from scipy.stats import zscore

# 1) top1 挑选：样本级聚合表 → 行内 z-score → argmax
agg = pd.read_csv('agg_sample_v2.csv')          # annotation_L3 分组，479 行
score_cols = [c for c in agg.columns if c.endswith('_AUC')]
identity = ['scoreI_AUC','scoreII_AUC','scoreIIa_AUC','scoreIIx_AUC']
prog_cols = [c for c in score_cols if c not in identity]   # 18 程序
sub_means = agg.groupby('annotation_L3')[prog_cols].mean()
Z = sub_means.apply(zscore, axis=0, result_type='expand')
Z.columns = [c.replace('_AUC','') for c in Z.columns]
top1_map = {s: Z.loc[s].sort_values(ascending=False).index[0] for s in targets}
```
已验证签名：RSS→Fibrosis、Specialized MF→Denervation、RP_high(II)→Glycolysis、
LRP1B+(I)→AMPK_PGC1a、RP_high(I)→scoreSarcomeric、OTUD1+(I)→scoreInflammatory、
OTUD1+(II)→scoreAtrophy（z=0.58 弱，无突出程序）。

⚠️ 口径坑：OTUD1+(II) 在 22 打分（含身份）里 top1=scoreII，在 18 程序里
top1=scoreAtrophy——用户看的图是哪个口径就用哪个，先确认再算。

## 细胞级分布读取 + 抽样
```python
need = ['annotation_L3'] + [top1_map[s]+'_AUC' for s in targets]
df = pd.read_csv('MF_AUCell_meta.csv', usecols=need)   # 382MB 只读 6 列秒读
df = df[df['annotation_L3'].isin(targets)]
sub = df.groupby('annotation_L3', group_keys=False).apply(
    lambda x: x.sample(n=min(3000,len(x)), random_state=42))  # 每亚群 ≤3000
sub['score'] = sub.apply(lambda r: r[top1_map[r['annotation_L3']]+'_AUC'], axis=1)
```

## y 轴决策：raw AUCell，不是 z-score
- 小提琴展示分布形状 → raw（0-1）直接反映真实水平分布
- z-score 把每个基因集自己的分布拉平到 0 附近 → 形状失真
- 热图比较跨亚群相对高低 → z-score；分布图展示绝对水平 → raw
- ⚠️ 每个亚群 top1 基因集不同 → 横轴间高度不可直接比较
  （实测 Inflammatory 中位 0.040 vs Sarcomeric 0.511 天生量级差）
  → x 轴标签下加小字标注基因集名，避免误读

## 绘图（nature-figure 规范）
```python
import matplotlib as mpl; mpl.use('Agg')
import matplotlib.pyplot as plt
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial","Helvetica","DejaVu Sans"],
    "pdf.fonttype": 42, "svg.fonttype": "none",
    "font.size": 7, "axes.spines.right": False, "axes.spines.top": False,
    "axes.linewidth": 0.8, "legend.frameon": False,
})
fig, ax = plt.subplots(figsize=(3.6, 2.9), dpi=300)
vp = ax.violinplot([sub[sub['annotation_L3']==s]['score'].values for s in order],
                   positions=range(len(order)), widths=0.72,
                   showmeans=False, showmedians=False, showextrema=False)
for i, body in enumerate(vp['bodies']):
    body.set_facecolor(colors[order[i]]); body.set_alpha(0.75); body.set_edgecolor('none')
# 中位数黑短线 + jitter 散点（每亚群 ≤800 点）
for i, s in enumerate(order):
    vals = sub[sub['annotation_L3']==s]['score'].values
    med = np.median(vals)
    ax.scatter(i+1, med, color='black', s=14, zorder=5, marker='_', linewidth=1.4)
    rng = np.random.default_rng(i)
    ax.scatter(i+1+rng.normal(0,0.12,min(len(vals),800)),
               rng.choice(vals,min(len(vals),800),replace=False),
               s=2.5, color=colors[order[i]], alpha=0.45, linewidths=0, zorder=3)
ax.set_xticks(range(1,len(order)+1))
ax.set_xticklabels([f"{s}\n{top1_map[s]}" for s in order], fontsize=6.5)
ax.set_ylabel('AUCell score (raw)', fontsize=7)
fig.savefig(out+'.png', bbox_inches='tight'); fig.savefig(out+'.svg', bbox_inches='tight')
fig.savefig(out+'.pdf', bbox_inches='tight')
```
用户配色（muscle_fiber_final_colors）：LRP1B+(I)=#A8D8EA、OTUD1+(I)=#2E86C1、
OTUD1+(II)=#D4A5A5、RP_high(I)=#B39DDB、RP_high(II)=#80CBC4、RSS=#009E73、
Specialized MF=#CC79A7、Pure Type I=#5DADE2、Pure Type IIA=#FFB347、Pure Type IIX=#CC7A00。

## 实测中位数（5 亚群，n=3000/亚群）
LRP1B+(I) [AMPK_PGC1a]=0.1951 / OTUD1+(I) [scoreInflammatory]=0.0401 /
OTUD1+(II) [scoreAtrophy]=0.1773 / RP_high(I) [scoreSarcomeric]=0.5108 /
RP_high(II) [Glycolysis]=0.0677

## 后续可选增强
- 每亚群按 type 分面（6 个小提琴/亚群）
- Wilcoxon 组间检验 + 星号
- 全部 10 亚群都画
- 出图后用 vision_describe 验证（OCR 查标签完整性 + ASCII 查小提琴形状非空白）
