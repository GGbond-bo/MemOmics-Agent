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

## 五效应扩展版（2026-08-14 用户拍板："我有六组，展示衰老效应、糖尿病效应、三个运动组一起的打分热图"）

用户认可 Fig1（3 面板）后要求**五效应并排**：`Aging(O_Pre−Y_Pre) / T2D(OD_Pre−O_Pre) / ExYoung(Y_Post−Y_Pre) / ExOld(O_Post−O_Pre) / ExT2D(OD_Post−OD_Pre)`。核心科学问题 = 三运动组并排看"糖尿病是否拖累运动对衰老的逆转"。

**⛔ 格式复用铁律（用户原话："按照Figure1的格式出啊"）**：
- 用户说"按 XX 图格式出" = **原样复刻布局/配色/标注，只改用户要求的维度**（3面板→5面板）。**禁止自行创新布局**（曾自作主张改成"亚群×效应 50 列大宽图"被打回）。
- **正确做法：从 `results/<session>/log/system_log.jsonl` 提取原图生成代码**（search_files pattern=`Fig1_effect_matrix` → 命中行 json 的 args.code 即完整脚本），在它基础上加面板，而不是凭记忆重写。
- 用户认可的格式要素（五效应版实测）：1×6 gridspec `width_ratios=[0.26,1,1,1,1,1]`（左轴打分名 + 5 热图）；行分组色条（Metabolic 蓝 11 / Identity 黄 4 / Senescence 红 7）；`LinearSegmentedColormap.from_list('cns',['#2166AC','#F7F7F7','#B2182B'])` + `TwoSlopeNorm(vmin=-3, vcenter=0, vmax=3)`；星号 `*` FDR<0.05（BH）；面板标题含对比式（如 `O_Pre − Y_Pre`）；`png(dpi=300)+pdf+svg` 三格式导出。

**统计与图矩阵**：样本级聚合（479 行）→ 每 打分×亚群×效应 算 Cohen's d + Welch t + BH → `effect5_d_table.csv` / `effect5_q_table.csv`（22×50 行名=score, 列名=`亚群|效应`）。出图时 `col_order = [f"{s}|{e}" for s in subs for e in effs]` 重塑为 5 个 22×10 面板。实测 1100 项检验、93 项 FDR<0.05，d 范围 −4.73~+3.36。

**⚠️ 辩论裁决（L1，verdict=modify）**：样本级 Cohen's d + BH 适合展示效应方向/幅度；但 5 面板并排**缺乏组间差异检验**（ExOld vs ExT2D 未直接比较），**不能支撑"糖尿病拖累运动逆转"的因果推断**。热图定位=趋势展示，汇报措辞用"观察/提示"而非"证明"；若要因果结论需补交互项/置换检验 + Cohen's d 95%CI。产出 `Fig1_five_effects_matrix.png/pdf/svg`。

## 环境/执行教训（2026-08-14 当天血泪史）
- **R 库批量 DLL 损坏时最多修一轮，再坏直接转 Python**：`requireNamespace(p, quietly=TRUE)` 只查元数据不加载 DLL，坏包显示 TRUE 假象；真验证必须 `tryCatch(library(p), error=...)`。症状 = 多个包 `LoadLibrary failure` / `lazy-load database is corrupt`（digest/cluster/Matrix/vctrs/S7），分布在 E:/R-libs、Program Files、Users 三处库根。逐包重装 = 无底洞。**正确路径：中间表落盘 CSV → Python 出图，一次成功**。
- **⛔ 别在环境检查上打转（用户原话："你老是检查terminal干什么全是报错" / "你已经很久没有出图了"）**：连续 ≥2 轮无图/无文件/无明确结果 = 已在打转。立即要么出图、要么换栈、要么如实报阻塞点。用户说"找原因，先不执行" = 只诊断不改。

## 颜色语义问答（"红色代表谁上升"，2026-08-14 实测三步核实法）

用户拿到五效应热图问颜色含义时，**不能凭记忆答**。保存的 `.R` 脚本可能是 33 行读数据 stub（`aucell_cns_figure.R` 实测只有读 CSV + 列名确认），真正的出图代码在 execute_code 调用里——**从 `log/system_log.jsonl` 提取**（`grep -a TwoSlopeNorm` / search_files pattern=`Fig1_five_effects_matrix` → 命中行 json 的 args.code 即完整脚本）。保存的 `.R` 脚本可能是 33 行读数据 stub（`aucell_cns_figure.R` 实测只有读 CSV + 列名确认），真正的出图代码在 execute_code 调用里——**从 `log/system_log.jsonl` 提取**（`grep -a TwoSlopeNorm` / search_files pattern=`Fig1_five_effects_matrix` → 命中行 json 的 args.code 即完整脚本）。

**实测解码**（五效应版）：
- 配色：`LinearSegmentedColormap.from_list('cns', ['#2166AC','#F7F7F7','#B2182B'])` + `TwoSlopeNorm(vmin=-3, vcenter=0, vmax=3)` → 蓝=负 d，白=0，红=正 d
- 符号：`cohens_d(a, b) = (a.mean() - b.mean())/SDpooled`，调用 `a=eff_defs[eff][0]`（前项组）、`b=eff_defs[eff][1]`（后项组）→ **正 d = 前项组（效应组）更高 = 红色**
- eff_defs：Aging=(O_Pre,Y_Pre)、T2D=(OD_Pre,O_Pre)、ExYoung=(Y_Post,Y_Pre)、ExOld=(O_Post,O_Pre)、ExT2D=(OD_Post,OD_Pre)
- 答案模板：**Aging 列红 = 老年组打分高（衰老上调）；T2D 列红 = 糖尿病组高（糖尿病上调）；Ex* 列红 = 运动后高（运动上调）；蓝 = 效应组更低**

**验证步**：从 `effect5_d_table.csv` 抽生物学方向明确的行验证符号（如 scoreOxPhos_AUC 衰老应下降 → Aging 轴 d 全负，实测 −1.57~−4.73 ✅；scoreSenMayo_AUC 常规预期衰老上升，但实测 Aging 轴 d 全负 = 老年组 SenMayo 反而低于年轻组 ⚠️ 反直觉点，如实报告并建议确认打分方向/样本构成）。**符号约定随代码版本变**：Cliff's delta 约定正值=后者高（箱线图），Cohen's d 约定正=前项组高（效应矩阵）——两套并存，回答前必须读代码，不可套用。

## v5→v6 迭代定稿：tight_layout 与 add_axes 颜色条不兼容 → PNG/PDF 渲染分叉（2026-08-14 关键修复）

用户反馈链：v4 颜色对了但"亚群标签离热图太远"→ 改 y 后"PNG 没变，反倒是 PDF 是对的"。**根因不是缓存，是 matplotlib 布局系统**：

- **`plt.tight_layout()` 与 `fig.add_axes([...])` 手动颜色条不兼容**。tight_layout 只识别自动创建的 axes，手动 add_axes 的 colorbar 会被忽略且触发 `UserWarning: This figure includes Axes that are not compatible with tight_layout`。后果：**PNG 渲染时 bbox 计算错乱 → 底部亚群标签被裁剪/热图区域空白，而 PDF（矢量）不受影响**——用户看到"PNG 没变、PDF 对了"的分叉。
- **⛔ 修复：去掉 tight_layout，改用 `fig.subplots_adjust(left=, right=, bottom=, top=)` 手动布局**（v6 方案），再叠加 `bbox_inches="tight"` 时三种格式（PNG/PDF/SVG）渲染一致。同一脚本里同时用 `plt.tight_layout()` + `fig.add_axes()` = 埋雷。
- **验证 PNG 是否真的更新/渲染正确（不要只看文件大小或时间戳）**：`vision_describe` 看主色分布（热图区域不应 60%+ 是 `#e0e0e0` 灰白）+ 裁剪底部区域 OCR 确认亚群标签在热图底边附近（v6 实测：热图最后彩色行 y≈2105，标签 y≈2143-2225，间距仅 40-120px = 贴紧）。

**v6 最终布局参数（用户认可的 Fig1 五效应版）**：
- 行分组间隙：三组（Metabolic 11 / Fiber Identity 4 / Senescence 7）之间各插 **0.6 行窄间隙**（`ri += 0.6`，不要插整空行——v4 整空行被批"隔开这么多"）
- 面板间距：`PANEL_GAP = 1.8`（有距离但紧凑；v3 曾用 3.0 被批"隔开距离也大了"）
- 亚群标签：底部 45° 斜排，`y = -0.15`（贴热图底边；v4 用 -1.9 被批"离热图太远"），`ha="right", va="top"`，fontsize=6.8
- 行标签 = 22 个完整基因集名（scoreOxPhos…Fibrosis）+ 左侧三色分组带（Metabolic #2C7FB8 / Fiber Identity #F4A261 / Senescence #D64550）
- 配色 = RdBu_r + TwoSlopeNorm(-3, 0, 3)，星号 `*` FDR<0.05（BH）
- **Fig7（打分×亚群）必须转置：y 轴=22 个基因集名、x 轴=10 亚群**（用户明确："y轴是基因集名字，亚群是x轴"）——不要默认行=亚群列=打分
- 迭代纪律：用户每版反馈只调一个维度（间隙→面板距→标签位置），**一次只改用户点名的那一处**，其他保持 v1 样式契约不动；每版用递增版本号 v3/v4/v5/v6 并存，用户对比后挑。
- 中文注释/表头一律英文（DejaVu Sans 无 CJK，中文=方框）；交付汇报用中文。

## v6→v7 迭代定稿：小色块白色间隙根因 = CELL<1.0（2026-08-14 用户抓\"小色块之间不要有白色间隙，你看第一版就没有间隙\"）

**⛔ 用 `ax.add_patch(Rectangle(...))` 逐格画热图时，格子尺寸必须 `CELL=1.0` 填满整个单元格**。若 `CELL=0.94`（Fig1）或 `CELL2=0.82`（Fig7），相邻格子之间会留 0.06/0.18 宽的**白色缝隙**——用户一眼看出\"第一版没有间隙\"（v1 用的就是 CELL=1.0 紧贴样式），v6 手滑改成 0.94/0.82 后被打回。**根因 = 格子宽 < 单元格宽，与 edgecolor 无关**（`edgecolor=\"none\"` 已设仍留缝）。修复 = 行方向 `ri += 1` 与格子宽 1.0 严格匹配。

**最终参数（v7，用户认可的定稿值）**：
- **Fig1**：`CELL = 1.0`（无白色间隙）+ 行分组间隙 `ri += 0.2`（用户明确指定 0.2，比 v6 的 0.6 更近）+ `PANEL_GAP = 1.8` **保持不变**（用户：\"五个效应组距离不变\"）
- **Fig7**：`CELL2 = 1.0`（无白色间隙，同样修 0.82→1.0）
- 用户提\"Fig7 x/y 轴字体太远 + 亚群列宽调小\"时：优先调 `figsize`/`subplots_adjust`/xlim，**不要用 CELL<1.0 制造\"更窄\"**——那会同时产生白缝，用户随后会要求去掉。窄 = 整体图宽收窄（figsize 变小），格子保持 1.0。
- 交付前自查：格子宽 == 行间距（都 1.0）才无白缝；`fig_v7_final.py` 为最终可用脚本（复制自 v6，patch CELL/间隙后跑），v1 格式基准 = 用户认可的红蓝白 + 完整基因名 + 无缝隙紧贴。

## v7→v8：type×亚群 六组分布热图（2026-08-15 用户新增诉求，标签布局三连纠）

用户要求"再出一个 type 六组图，看看各基因集在不同 type 和亚群的分布"——**不是五效应差值版，而是 6 组原始打分 × 10 亚群的分布热图**。产物 `fig_type6_v8.py` → `Fig_type6_by_subcluster_v8.png/pdf/svg`。

**布局规格（与 Fig1/Fig7 同系列）**：
- 行 = 22 基因集（按 Metabolic 蓝 11 / Fiber identity 黄 4 / Senescence 红 7 分组，左侧功能色带 + 行分组间隙 0.2）
- 列 = 6 type × 10 亚群 = 60 列，**type 间留间隙 `GAP_C=1.2`，亚群间无间隙**（CELL=1.0）
- 值 = 样本级聚合均值，行内 z-score（每基因集跨 60 格标准化），RdBu 红蓝白 ±2 截断
- 配色 = `['#2166AC','#67A9CF','#F7F7F7','#EF8A62','#B2182B']`（5 锚点）+ TwoSlopeNorm(-2,0,2)

**⛔ 用户标签布局三连纠（v8 首版全踩）**：
1. **亚群标签必须在底部（45° 斜排），type 标签在顶部**——与 Fig1 五效应版一致；v8 首版把亚群和 type 混排被用户打回"亚群在下面，type 在上面"
2. **label 必须全部在图外**（用户原话："label 又在图内了"）——亚群标签底部 y 要远离热图底边：
   - 修正前：`y = HEAD_H + n_rows_real*CELL + 0.25` + `SUB_H=3.2` → 标签贴太近/进图内
   - 修正后：`y = HEAD_H + n_rows_real*CELL + 0.9` + **`SUB_H=5.0`**（加大底部留白）→ 标签明确在图外
3. **顶部 type 标题**保持 `HEAD_H-0.5`（灰色条 `HEAD_H-0.8` 高 0.6 + 粗体标题），行标签左侧、功能色带左侧——全部图外

**⚠️ 底部标签离图太远与进图内是一对矛盾，只调 y 不够，必须同时加大 SUB_H 预留**——底部留白不足时 y 再大也会被 `bbox_inches='tight'` 裁回图内（与 v6 tight_layout 坑同源：手动画布 + tight 导出 = 标签被裁）。正确做法 = 画布高度预留 `SUB_H` 足够大 + 标签 y 下移，两者同步。

**版本纪律**：v8 用独立脚本 `fig_type6_v8.py`（不复制 v7），每版反馈只改用户点名的一处（亚群标签位置），其他保持系列样式（无白缝 CELL=1.0、行分组 0.2、完整基因名、RdBu）不动。交付时说明"亚群标签在底部、type 标签在顶部、留白已加大"。

## v8→v9：type6 六组图重构为 Fig1 v7 多面板架构（2026-08-15 用户明确拍板）

用户对单张 60 列大矩阵的 v8 反复调标签位置后说：**"你能不能像 figure1 v7 那样呢？它的脚本是对的，出图也很好"**——这是关键转折：**与其在单矩阵布局里反复调标签，不如直接复用用户已认可的 Fig1 v7 多面板横排架构**。

- **v9 布局 = Fig1 v7 同架构**：6 个 type（Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post）各成一个面板横排，每面板 10 亚群列（`PANEL_GAP=1.8` 面板间隙、`CELL=1.0` 无白缝、亚群标签 45° 贴底 `y=-0.15`、行分组间隙 0.2、行标签 22 完整基因名 + 左侧三色带、`subplots_adjust` 手动布局不用 tight_layout）
- 脚本 = `fig_type6_v9.py`（从 `fig_v7_final.py` 复制改，不继续在 v8 上打补丁）——**当用户拿另一张已认可的图当基准时，直接复制那张图的脚本改数据源，而不是继续修当前的图**
- 用户确认 v9 布局完美（"很完美"）

**⛔ 用户要求"真实的 AUCell 分数"→ 不要卡死在窄区间，最终回到 z-score（2026-08-15 实测）**：
- 用户说"6组的需要真实的AUCell分数" → Agent 实现为绝对均值 + `TwoSlopeNorm(vmin=0, vcenter=0.05, vmax=0.20)` → 用户质疑"你确定这值是对的吗？" → 手动重算数值确认无误（值确实对）→ **但用户继续打回："肯定错啊，你把值卡死在0.2,其他的怎么办呢？还是z-score吧"**
- 教训：AUCell 绝对分数绝大部分集中在 0-0.2 窄区间（实测大部分格子 0.01~0.09，个别如 SMF 去神经 O_Post=0.176 接近上限），**vmax=0.2 等于把绝大多数格子压到同色，丢信息**。用户要"真实分数"时：① 要么用**全 0-1 或数据驱动的 max** 做映射（不要自作主张截断到 0.2）② 要么直接回到**行内 z-score**（用户最终拍板方案）。**z-score 仍是本类热图的默认与终态**；"真实分数"诉求若实现不当会被打回。
- 数值验证结论可先报：8 基因版去神经（CHRNA1/CHRNG/CHRND/SCN5A/KCNMB1/NCAM1/NGFR/RUNX1）Aging 均值 d=+0.73（SMF 最高 +1.10）、ExOld +1.01、ExT2D +0.80、T2D +0.03——净化后运动轴回落但未消失（NMJ 重塑共享基因），T2D 无信号。

**⛔ pandas MultiIndex × z-score 两大坑（2026-08-15 实测，回 z-score 时踩到）**：
1. **`Z_raw.apply(lambda r: zscore(r), axis=1)` 会把 DataFrame 变成 Series**——`scipy.stats.zscore` 返回 ndarray，apply(axis=1) 后 Z 的 MultiIndex 列丢失，随后 `Z.loc[name, (tp, sub)]` 报 `IndexingError: Too many indexers`。**不要用 apply + zscore**。
2. **`(Z_raw - Z_raw.mean(axis=1)) / Z_raw.std(axis=1)` 报 `cannot join with no overlapping index names`**——MultiIndex 列与 Series 广播触发 pandas 索引对齐错误。**不要用 pandas 层减法广播**。
3. **✅ 修复 = numpy 层向量化标准化，保留 DataFrame 骨架**：
```python
Z = Z_raw.copy()
_mu = Z_raw.values.mean(axis=1, keepdims=True)
_sd = Z_raw.values.std(axis=1, ddof=0, keepdims=True)
Z[:] = (Z_raw.values - _mu) / _sd
```
用 `.values` 取底层 numpy 数组做运算，再 `Z[:] = ...` 写回——MultiIndex 列索引完整保留，`Z.loc[name, (tp, sub)]` 正常。
- 改回 z-score 时同步改两处：数据层（上面的 numpy 标准化）+ 颜色层（`TwoSlopeNorm(vmin=-2, vcenter=0, vmax=2)` + colorbar 刻度 `[-2,-1,0,1,2]` + 标签 `row z-score`）。只改数据层不改颜色层 = 值对但颜色全截断。
