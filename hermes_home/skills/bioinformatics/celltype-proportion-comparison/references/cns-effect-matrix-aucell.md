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

用户拿到五效应热图问颜色含义时，**不能凭记忆答**。保存的 `.R` 脚本可能是 33 行读数据 stub（`aucell_cns_figure.R` 实测只有读 CSV + 列名确认），真正的出图代码在 execute_code 调用里——**从 `log/system_log.jsonl` 提取**（`grep -a TwoSlopeNorm` / search_files pattern=`Fig1_five_effects_matrix` → 命中行 json 的 args.code 即完整脚本）。

**实测解码**（五效应版）：
- 配色：`LinearSegmentedColormap.from_list('cns', ['#2166AC','#F7F7F7','#B2182B'])` + `TwoSlopeNorm(vmin=-3, vcenter=0, vmax=3)` → 蓝=负 d，白=0，红=正 d
- 符号：`cohens_d(a, b) = (a.mean() - b.mean())/SDpooled`，调用 `a=eff_defs[eff][0]`（前项组）、`b=eff_defs[eff][1]`（后项组）→ **正 d = 前项组（效应组）更高 = 红色**
- eff_defs：Aging=(O_Pre,Y_Pre)、T2D=(OD_Pre,O_Pre)、ExYoung=(Y_Post,Y_Pre)、ExOld=(O_Post,O_Pre)、ExT2D=(OD_Post,OD_Pre)
- 答案模板：**Aging 列红 = 老年组打分高（衰老上调）；T2D 列红 = 糖尿病组高（糖尿病上调）；Ex* 列红 = 运动后高（运动上调）；蓝 = 效应组更低**

**验证步**：从 `effect5_d_table.csv` 抽生物学方向明确的行验证符号（如 scoreOxPhos_AUC 衰老应下降 → Aging 轴 d 全负，实测 −1.57~−4.73 ✅；scoreSenMayo_AUC 常规预期衰老上升，但实测 Aging 轴 d 全负 = 老年组 SenMayo 反而低于年轻组 ⚠️ 反直觉点，如实报告并建议确认打分方向/样本构成）。**符号约定随代码版本变**：Cliff's delta 约定正值=后者高（箱线图），Cohen's d 约定正=前项组高（效应矩阵）——两套并存，回答前必须读代码，不可套用。
