# 慢肌类亚群 vs 纯纤维「自己显著高表达基因集」小提琴图

> 场景（2026-08-20，human/skeletal_muscle/aging，MF_AUCell_meta.csv 508k 细胞）：
> 给 5 个目标亚群，每个各匹配一个「自己显著高表达」的程序基因集，画小提琴图
> `[目标亚群 + Pure Type I + Pure Type IIA + Pure Type IIX]` 4 组。

## 数据源与亚群
- `E:/骨骼肌锻炼/MF_AUCell_meta.csv`：508,661 细胞 × 10 L3 亚群 × 48 样本 6 组配对
- AUCell 打分列：`score<名>_AUC`（18 程序）+ `<名>_AUC`（Glycolysis/FAO/Denervation/AMPK/Autophagy/Adipo/mTORC1/Fibrosis）
- **18 个程序基因集 = 全部打分列去掉 4 个身份打分（scoreI/II/IIa/IIx）**
- 目标亚群：LRP1B+(I)、OTUD1+(I)、OTUD1+(II)、RP_high(I)、RP_high(II)
- 纯纤维对照：Pure Type I / IIA / IIX（排除 RSS、SMF、以及作为目标的纯型）

## 选「自己显著高表达基因集」= 口径 B 数据实算
对每个目标亚群 × 每个程序基因集，算亚群 vs 3 纯纤维**逐个**的 Cohen's d 和 Mann-Whitney raw p，
取 d>0（亚群比纯型高）且 p<0.05 的，按均值 d 排序选 top1。（详细口径 A vs B 区分见 SKILL.md 主文
"画自己显著高表达的基因集"一节与 `references/subcluster-top1-violin.md`。）

**实测定稿（2026-08-20，raw p 均 <0.001）**：
| 亚群 | 首选基因集 | 均值 d | 生物学意涵 |
|------|-----------|:---:|-----------|
| LRP1B+(I) | OxPhos | +0.60 | 慢肌氧化代谢（vs Pure IIX d=+1.06 最强） |
| OTUD1+(I) | Denervation | +0.44 | 去神经化 |
| OTUD1+(II) | Denervation | +0.39 | 去神经化（两 OTUD1+ 共享） |
| RP_high(I) | Sarcomeric | +0.80 | 肌节蛋白 |
| RP_high(II) | Sarcomeric | +0.63 | 肌节蛋白（两 RP_high 共享） |

**注意**：OTUD1+ 两亚群共享 Denervation、RP_high 两亚群共享 Sarcomeric 是**数据事实**（真实共享 signature），
不是人为重复。选 d 最大者是数据驱动；向用户言明「共享」不是 bug。旧标准误选（OTUD1+=TNFA、RP_high+=Atrophy/Insulin）
vs 纯型 d≈0 甚至为负，必须按口径 B 修正并披露差异。

## 标注样式（用户 2026-08-20 明确拍板）
- **星号按 raw p 分级**：p<0.05→`*`、p<0.01→`**`、p<0.001→`***`（**不做 BH-FDR，不做效应量分级星号**）
- **效应量单独以数值标注在 bracket 上**：`***  d=+1.06`（星号 + d 数值双标注）
- 之前用的「|d|≥0.8→***」效应量分级星号被用户否决——**不要再按效应量分级打星号**

## 画法（复用 `fig_C1_5sub_rawp_effsize.py`）
- 每亚群一张：`ax.violinplot(4 组, widths=0.70)` + `ax.boxplot(内部窄箱线 widths=0.12 中位数+IQR)`
- `ax.set_ylim(0, ymax_data*1.38)` 只留 bracket 空间、不截断分布（用户主刊规则：不截 y 轴）
- bracket 阶梯避重：`y = bracket_base + k*ymax_data*0.075`；`add_bracket` 画 4 段折线 + `***  d=+x.xx` 文字
- 30° 旋转 x 标签、7pt Arial、`svg.fonttype='none'`/`pdf.fonttype=42`
- 导出 PNG/SVG/PDF/TIFF（TIFF 600dpi），PNG 57-67KB、TIFF 12MB
- 颜色：目标亚群统一浅蓝 `#A8D8EA`；Pure I `#5DADE2`/IIA `#FFB347`/IIX `#CC7A00`
- Perl 正则安全文件名：`re.sub(r'[^A-Za-z0-9]+', '_', sub)` → `LRP1B__I_`（+与括号都替换）

## ⚠️ 统计局限（辩论 need_more_info，必须披露）
- **细胞级 Mann-Whitney 伪重复**：508k 细胞来自 48 个体，同个体内细胞非独立 → 细胞级检验膨胀样本量、p 值失真
- **winner's curse**：按最大 d 选基因集有效应量高估
- **处理**：作为**展示性小提琴图**完全可用（分布可视化）；若要把「某亚群显著高表达某基因集」当**正式统计结论**
  写论文，必须补 **pseudobulk（个体聚合）+ DESeq2/limma + 多重比较校正**。交付时主动提示，不默认展示图当统计结论。

## 相关脚本
- `scripts/fig_C1_5sub_rawp_effsize.py`（5 亚群综合版，可复制改 gene 列与 config 亚群列表）
- 预选计算：每亚群×18 程序 vs 3 纯纤维的 d+p 表（`stats.mannwhitneyu(a, b, alternative='two-sided')`，`cohens_d` pooled-SD）
