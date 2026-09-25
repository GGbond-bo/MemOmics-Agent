# 案例：小鼠肌纤维横截面积（CSA）统计方案审查（2026-09-25 实测）

> 用户原话："帮我审一下这个统计方案：比较 3 组小鼠的肌纤维横截面积，每组 6 只，用 t 检验两两比较；
> 另外用 Pearson 相关分析单细胞比例与握力的关系。指出问题并给出正确做法。"
> 这是**审方案（discussion）**：用户未给数据 → 用模拟数据演示偏差，不建 task_plan、不跑分析管线。

## 1. 审查结论（可直接复用的口径）

两处 P0：① 分析单位错位（肌纤维不是独立实验单位，小鼠才是 n）；② 3 组两两 t 检验未校正（FWER 14.3%）。
P1：比例数据直接 Pearson（受限/组成型/二项误差）；跨 3 组合并相关（Simpson 悖论风险）；n=6/组 无功效说明。
P2：只报 P 无效应量/CI；比较族未定义。

## 2. 实测对照（模拟数据：3 组 × 6 只 × 16 根/只，真实效应 d=0.5）

| 口径 | A-B / A-C / B-C | 判定 |
|---|---|---|
| 纤维当 n=288，两两 t 检验（未校正） | 0.123 / **3.73e-05** / **1.65e-03** | ✗ 虚假显著 |
| 每只小鼠均值（n=6/组）+ ANOVA + Tukey | 0.783 / 0.174 / 0.457（p adj） | ✓ 全 n.s. |
| LMM `CSA ~ Group + (1\|Mouse)` | GroupC p=0.091；**ICC=0.313**（小鼠 0.431 / 残差 0.946） | ✓ 推荐 |
| 假设检查（均值法残差） | Shapiro p=0.599；Levene p=0.243 | 前提满足 |

功效（n=6/组，α=0.05）：d=0.5 → **0.12**；0.8 → 0.24；1.2 → 0.47；1.5 → 0.65；3 组 ANOVA（between.var=0.25、within.var=1）→ **0.27**。

相关部分（n=18 只小鼠，比例受组别影响）：raw Pearson r=0.91 → logit 后 Spearman ρ=0.94 → **控制组别的偏相关 r=0.88**
（说明分组合并会混入组别效应；偏相关用残差法实现，无需 ppcor）。

脚本产物：`results/<sid>/scripts/stats_review_demo_pseudoreplication.R`（三口径对照）+
`results/<sid>/scripts/stats_review_figures.R`（四联诊断图）。可复用探针见本 skill `scripts/stats_plan_audit_demo.R`。

## 3. 四联诊断图配方（base graphics，零依赖）

`png(f, width=2600, height=2100, res=200, type="cairo")` + `par(mfrow=c(2,2), family="Microsoft YaHei")`：

- **A 伪重复的代价**：`barplot(rbind(-log10(p_bad), -log10(p_tukey)), beside=TRUE)`，双色（错 #D9534F / 对 #4C72B0），
  `abline(h=-log10(0.05), lty=2)` 阈值线；`ylim = max*1.5` 给图例留位（否则图例压在高柱上）。
- **B 嵌套结构**：`boxplot(CSA ~ Mouse)` 逐鼠箱线（按组着色）+ `points(1:n, 鼠均值, pch=18)` ⇒ "鼠内散布 >> 鼠间差异"。
- **C 功效缺口**：`matplot(ns, pw, type="l")`（d=0.5/0.8/1.2 三条）+ `abline(v=6, h=0.8)`。
- **D 比例-表型散点**：按组着色 + 总体回归线 + `mtext()` 在底部一行写三口径数值。

**中文字体**：`family="Microsoft YaHei"` + `type="cairo"` 实测正常（无 `mbcsToSbcs` 警告、文件正常落盘）——
不必为此切 Python matplotlib。

## 4. 需向用户补充的问题（AUTHOR_INPUT_NEEDED 实例）

1. CSA 怎么量的：每只几根纤维、是否左右腿配对、有无按纤维类型（I/IIa/IIx）分层？
2. 3 组是什么关系？有序（剂量/年龄梯度）→ 应改趋势检验而非两两比较。
3. 单细胞与行为学是否同一批小鼠？每鼠捕获细胞数（决定比例精度）？握力测几次、如何取值？
4. 协变量：性别、体重（CSA 与体重强相关）、笼位/批次。

## 5. 文献锚点（已核验）

- Aarts et al. 2014, *Nat Neurosci*, DOI 10.1038/nn.3648（PMID 24671065，被引 598+）— 嵌套数据用多水平分析。
- McKinnon Reish et al. 2024, *Appl Environ Microbiol*, DOI 10.1128/aem.01033-24（PMID 39082810）— 宿主-微生物研究中的伪重复。
- Zhang et al. 2024, *Comput Struct Biotechnol J*, DOI 10.1016/j.csbj.2024.11.003（PMID 39624165）— 比例/组成数据变换。
- 失败模式分类（P0 伪重复 / 未校正多重比较 / 分析单位不匹配；P1 仅报显著性、小样本过度解读、相关过度解读）：
  skill `nature-statistics` → `references/common-failure-modes.md`。

## 6. 平台侧实测口径

- **debate 场景自动判为 `stats_design`**（裁判 rubric = 实验单位判定 / 伪重复控制 / 多重比较校正 / 效应量与区间 /
  相关有效性 / 功效论证 / 预注册）。传 `statistics_kb`（实验单位、FWER、组成数据变换、失败模式分类）比留空更有效。
- **L1 裁决**：verdict=modify、confidence=medium；recommended_params 与本审查一致（LMM 主分析 + 每鼠均值敏感性；
  logit/CLR + Spearman + 控制组别偏相关；报功效/MDE；冻结 SAP）。
  ⚠️ 该次 L1 **正反方角色只回 reasoning 草稿**（`pro_draft_only/con_draft_only: true`，即使传了显式 kb 也如此）
  ⇒ 汇报时必须写明"正反方未按契约输出、裁判依据上下文数据与规则裁决"，按中等置信处理。
- 裁决 `missing` 四项已在交付里如实转述：真实数据 ICC/残差诊断、比例分布与组别混杂、正式功效曲线、预注册 SAP。
- **rail_review(post)**：第一次不带图 → failed（`未生成任何图片`）；补四联诊断图后（`output_dir` 传会话根）→ passed、
  `figure_count=1`。属"产物口径/真实交付"类，补图正确；⚠️ 该图不是凑数，它是审查的证据本身。