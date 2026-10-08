# AUCell / 基因集打分图全套约定（heatmap + violin）

> 来源：human/skeletal_muscle/aging MF_AUCell_meta.csv 项目（508k 细胞，22 打分 × 6 组 × 10 亚群），
> 用户多轮格式纠正沉淀。适用于 `score*_AUC` / `*_AUC` 列矩阵的任何 AUCell/AddModuleScore 打分可视化。
> 项目内 fig 脚本基线：fig_split_v10.py（FigA1-3/B1-3）、fig_C1_AMPK_violin_4sub.py、fig_type6_v9.py。

## 数据口径

- 细胞级 CSV：每行=1 细胞，打分列以 `_AUC` 结尾（`scoreOxPhos_AUC`、`Glycolysis_AUC`、`Denervation_AUC`）
- 样本级聚合 `agg_sample`：groupby(samplename, annotation_L3) 取均值（个体才是独立样本，伪重复门禁）
- 效应表：样本级配对 Cohen's d + BH-FDR；五效应 Aging/T2D/ExYoung/ExOld/ExT2D（O−Y / OD−O / Y Post−Pre / O Post−Pre / OD Post−Pre）
- 身份打分（scoreI/II/IIa/IIx）与亚群标签共线 → **不进主程序热图**，单独出 4 张验证小图（IIX 亚群应 scoreIIx 高）——用户确认的拆分方案：A 组 18 程序 × 3 图（6组/5效应/亚群）+ B 组 4 身份 × 3 图 = 6 张

## ⚠️ z-score 方向陷阱（本项目踩过，最易复发）

- 热图行内 z-score 正确方向：**每个基因集跨亚群/跨组标准化**（行=基因集：`Z = a.T; mu=Z.mean(axis=1); sd=Z.std(axis=1, ddof=0); Z=(Z-mu)/sd`）
- 若反着算（每个亚群跨基因集标准化）会退化出**无区分度伪 top1**：本项目 scoreSarcomeric（泛肌纤维结构程序）在全部 10 亚群 z≈3.2-3.5 → 所有亚群 top1 都是同一个基因集，画出来毫无意义
- 判定"亚群标志基因集"：行内 z + 生物学常识双确认；遇全亚群同 top1 → 改用"该亚群 vs 纯 type 对照组 Cohen's d 最大"来定义，**每张图独立选**（用户明确：每张图是独立的，不要跨图统一公式）
- 效应热图（五效应）用 Cohen's d（已聚合），原始打分热图（6组×亚群）用行内 z-score——不要混用

## 热图布局（用户 5+ 轮纠正的最终版）

- **CELL=1.0 格子填满、无白色格线**（`edgecolor='none'`）——用户对"格子之间有白缝"零容忍
- 行分组间隙 0.2（组间插空行）；多组/多效应面板间隙 PANEL_GAP≈1.8（太散/太平都不行；"拼图感"=有间隙但紧凑）
- 配色 RdBu_r（红=正效应/高、蓝=负效应/低、白=0），TwoSlopeNorm ±2~±3 截断，必带 colorbar 刻度
- 标签位置：**亚群标签底部 45° 斜排**（y 偏移要足够大，旋转文本 bbox 顶部会向上压进热图——`va='center'` + 偏移≥1-2 行距才能真正离开数据区）；**type/panel 标题在顶部图外**（灰色条 + 标题）；基因集名左侧**完整名**（scoreOxPhos…Fibrosis），不许简写
- 字体 ≥6pt；PNG(300dpi)/PDF/SVG 三格式同时出（投稿再加 TIFF 600dpi）

## ⚠️ matplotlib invert_yaxis 陷阱

- y 轴默认向上增长；坐标设计若把大 y 值给了底部标签、小 y 值给了顶部标题 → 整图上下颠倒（type 到底部、亚群到顶部）
- 修法：`ax.invert_yaxis()` 翻转，或干脆不翻转让行 0 在顶部、底部标签用小 y 偏移（v7 架构：行 0 顶部，亚群标签 y=-0.15 贴底）
- 改完必须 vision_describe OCR 验证 type 顶 / 亚群底；45° 小字 OCR 常抓不到 → 裁剪底部区域放大验证，不要因 OCR 空就断言标签缺失

## 小提琴 / 分布图（单基因集 × 多亚群）

- **Y 轴 = 原始 AUCell 分数（0-1），绝不截断**（用户原话："能跟看到完整的提琴图"；z-score 会拉平每个基因集自身分布、形状失真）
- 主角亚群 + 对照组（如 LRP1B+(I) vs Pure Type I/IIA/IIX）4 根以内，别堆 10 根占版面；10 亚群场景改用 ECDF 省 2/3 位置
- ⛔ **星号按 raw p 分级 + 效应量 Cohen's d 数值双标注（2026-08-20 用户最终拍板"raw p 星号 + 效应量标注"）**：用户明确改掉之前"按效应量 d 分级星号"的旧做法——**星号严格按 raw Wilcoxon p**（`*`<0.05/`**`<0.01/`***`<0.001），**效应量单独以数字标注在 bracket 上**（`***  d=+1.06` 这种"星号 + 数值"双标注）。之前的旧版（`|d|≥0.8→*** / ≥0.5→** / ≥0.3→* / ns`，即 fig_C1_AMPK_violin_4sub.py 用的效应量分级星号）**已被用户否决，不要再按效应量分级打星号**——星号永远反映 raw p，d 值单独写出来。
- ⛔ **"画不同基因集打分小提琴图"不算 FDR（2026-08-20 用户拍板）**：用户两次明确——基因集打分小提琴是探索性展示（非全基因组 DEG 假设检验），多基因集比较按文献惯例用 **raw Wilcoxon p 星号 + 效应量 d**，不做 BH-FDR 校正（校正过度惩罚）。早期文献（本参考曾写"算BH-FDR"）已被用户此最终决议取代。⚠️ 大样本 raw p 几乎全 <1e-6 → 星号必满格 `***` 失去区分度 → **真正判断信号靠效应量 d 与分布重叠，星号只做"确实不同"的形式确认**，交付时主动说明这一点
- **"该亚群自己显著高表达的基因集" = 亚群 vs 3 纯型的数据实算（非 memory/FigA3 top1，2026-08-20）**：对每个目标亚群 × 每个程序基因集算 vs Pure I/IIA/IIX 的 **avg Cohen's d**，选 **最大且为正** 的程序基因集。必须**排除 4 个身份打分（scoreI/II/IIa/IIx）**（定义纤维身份、天然高）；memory 里存的口径 A top1（FigA3 行内 z-score 签名）实测常"不算显著"（OTUD1+(I) scoreTNFA vs Pure I d≈0、RP_high(II) scoreInsulin vs IIA/IIX 为负）→ "自己显著的"要用数据实算口径 B，且与上轮选择有出入时先向用户披露差异让其拍板，不默默改
- 样式：组间**标准显著性 bracket（横线+星号）**，阶梯高度避免重叠且全部在图内（`bbox_inches='tight'` 会裁掉高处星号——bracket 基准 ≤ 数据 max*1.98 且 h 阶梯 ≤ 0.05*ymax）
- **不要**：高亮框框 / annotate 注释文字 / 中位数数值标注（用户原话："不要画框框标注，也不要文字，正常画就好"）
- 主刊尺寸：单栏 90mm×62mm / 双栏 183mm，7pt Arial，白底，TIFF 600dpi

## PDF/SVG vs PNG 渲染不一致

- `plt.tight_layout()` 与 `fig.add_axes` 颜色条不兼容（matplotlib 报警告）→ PNG 渲染异常（亚群标签被裁/空白），PDF 矢量正常 → 表现"PDF 对了 PNG 没变"
- 修法：`subplots_adjust` 手动布局代替 tight_layout，PNG/PDF/SVG 一致

## 图稿参数记忆（本项目，后续改图直接复用）

- Fig_type6_by_subcluster：亚群标签在图外底部 y=+2.2、SUB_H=6.5、type 标题顶部图外、RdBu 配色、无白色格线、CELL=1.0、行分组 0.2、面板间隙 1.8
- Fig_C1_AMPK_violin：LRP1B+(I) 主角、4 亚群、**raw p 星号 + Cohen's d 数值双标注**（2026-08-20 用户改版——旧版曾按效应量 d 分级 ns/*/**，已被用户改为 raw p 星号 + d 数值）、Y 轴 0-0.7 不截断、无框无注释。5 亚群综合版脚本 = `fig_C1_5sub_rawp_effsize.py`（LRP1B+=OxPhos/OTUD1+I=Denerv/OTUD1+II=Denerv/RP_highI=Sarcomeric/RP_highII=Sarcomeric）