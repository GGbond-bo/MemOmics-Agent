# 「主角亚群 vs 3 纯纤维」4-sub 小提琴图 — 用户认可的模板脚本（2026-08-20）

用户明确要求"按我之前的代码 fig_C1_AMPK_violin_4sub.py 参考绘画"——这是一套用户认可、
可复用的**主角亚群 vs Pure Type I / IIA / IIX 的 4-sub 对比小提琴图**模板。与
`subtype-vs-fiber-violin.md` 的 raw-p-star 版本是**同一类的两套星号口径**，用哪套以用户
当次指定为准。

## 模板脚本位置
`results/memomics-2274ab75/scripts/fig_C1_AMPK_violin_4sub.py`
（本类重画通用版 `fig_C1_5sub_vs_pure_v2.py`，JOBS 列表批量出多图）

## 核心结构（4-sub = 主角 + 3 纯纤维）
- `order = [main_sub, 'Pure Type I', 'Pure Type IIA', 'Pure Type IIX']`
- 主角配色浅蓝 `#A8D8EA`；纯纤维标准配色 I `#5DADE2` / IIA `#FFB347` / IIX `#CC7A00`
- 打分列 = `{基因集名}_AUC`（如 `AMPK_PGC1a_AUC`、`scoreInflammatory_AUC`），
  读 `MF_AUCell_meta.csv` 只读 `usecols=['annotation_L3']+[score_col]`（50 万细胞级秒读）
- 数据分组：`data_by_group = [df[df['annotation_L3']==o][score_col].values for o in order]`

## ⛔ 星号按 Cohen's d 效应量分级（不是 p 值）——本模板的签名
细胞级 n 巨大（主角 8k-31k vs Pure IIA 171k）时 Mann-Whitney p 下溢/伪重复虚标小效应，
用户对效应量极其敏感 → **星号 = d 分级而非 p 判级**：
```python
def star_eff(d):
    ad = abs(d)
    if ad >= 0.8: return '***'
    if ad >= 0.5: return '**'
    if ad >= 0.3: return '*'
    return 'ns'
```
- Cohen's d = pooled SD（主角 vs 各纯纤维），主角自身格标空格
- 结论措辞分级：d≥0.5 说"富集/差异强"，d<0.3 说"统计显著但效应小（共性/趋势）"，
  用"富集"不用"特异"

## nature-figure 排版（rcParams）
- `font.family=sans-serif` + `Arial`、`svg.fonttype=none`、`pdf.fonttype=42`、`font.size=7`
- 仅保 left/bottom 脊柱；`figure.facecolor=white`；`legend.frameon=False`
- `figsize=(90/25.4, 62/25.4)` = 单栏 90×62 mm，dpi=600

## 小提琴绘制要点
- `violinplot(widths=0.70, showmeans/medians/extrema=False)` → body 设 facecolor + alpha=0.85 + edgecolor none
- 内部窄箱线（`boxplot(widths=0.12)`）只显示中位数 + IQR（medianprops/boxprops/whisker/cap 深灰 #111111），`showfliers=False`
- **不截断 Y 轴**：`ylim(0, data_max*1.28)`（1.28 只留 bracket 空间）
- 显著性 bracket：主角 vs 各对照，阶梯高度 = `bracket_base(0.98*data_max) + (max(i,1)-1)*0.05*data_max`，
  `add_bracket(ax,x1,x2,y,label)` 画 `[x1,x1,x2,x2],[y,y+h,y+h,y]` 折线 + 中央 label（fontsize=6）
- `xticklabels(order, rotation=30, ha='right', fontsize=7)`；ylabel = `score_col.replace('_AUC','') + ' AUCell score'`

## 输出格式（4 种全出，投稿/预览都齐）
- `.png` dpi=300、`.svg`（fonttype none 可编辑）、`.pdf`（fonttype 42 矢量）、`.tiff` dpi=600
- 全部 `bbox_inches='tight'` + `facecolor='white'`；保存后打印 `os.path.getsize` 验证非空

## 5 亚群实例结果（fig_C1_5sub_vs_pure_v2.py，2026-08-20 实算）
| 主角亚群 | 打分列 | 中位数 | d vs Pure I/IIA/IIX | 星号 |
|---|---|---|---|---|
| LRP1B+(I) | AMPK_PGC1a | 0.196 | 0.21/0.33/0.68 | ns / * / ** |
| OTUD1+(I) | scoreInflammatory | 0.040 | 0.12/0.35/0.36 | ns / * / * |
| OTUD1+(II) | scoreAtrophy | 0.176 | 0.30/0.11/0.17 | 全 ns |
| RP_high(I) | scoreROS | 0.067 | 0.38/0.66/0.71 | * / ** / ** |
| RP_high(II) | Glycolysis | 0.067 | 0.49/0.14/0.39 | * / ns / * |

## ⛔ 用户给"期望中位数表"时：逐项核对实算值，差异必须披露
用户提供的表（图|亚群|top1基因集|中位数）与本项目实算中位数应逐格比对。本会话
RP_high(I)-scoreROS 用户给 0.077、实算 0.0667（其余 4 个完全一致）→ **差异须向用户披露**
并问口径（是否排除了某些细胞/子集），图按数据实算交付，不要默默改数。

## ⛔ 删除旧图 = 移入备份目录，不是物理删除
用户说"把之前的小提琴图都删掉"= 把旧图从 figures/ 移出、不再占据目录，但要遵守
"未经同意绝不删除"铁律 → **移动到 `figures/_backup_old_violin/`（可追溯），不 `os.remove`**。
删除前用 search_files 列出所有旧版本（含 `_by_subcluster`/`_v2`/模板 `_4sub` 及旧 5 亚群图），
核对后统一移动。交付清单里写明"旧图已移入备份、可追溯"。

## 展示性红线（辩论门控 L1 verdict=need_more_info/low）
细胞级 Cohen's d 受伪重复影响（伪精确、d 可能夸大），中位数 0.04-0.196 很小却可能标星。
这类图**只能作展示性对比**（方向 + 效应量参考），**不能当统计显著性主结论**；
作主结论必须个体级/pseudobulk 验证。汇报措辞注明"细胞级展示、效应量方向参考"。
