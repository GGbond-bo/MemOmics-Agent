# 竖排分组名「太长」的量化处置 + 换短名的实测选法

> 实测来源：2026-10-20，FigA2 五效应程序热图（base graphics，零第三方依赖）。
> 用户原话：**「Decompensation 和 Inflamm-aging 这两个基因集分类太长了，有没有简短贴切的？」**

## 0. 为什么这类问题必须「先量再答」

用户说「名字太长」时，直觉答案（最像原文、最好的英文词）**往往是错的**。实测：
`Degeneration`（退行性变，语义最接近 Decompensation）量出 **0.768 in，仍超出该组色块 0.758 in 达 0.01 in** ——
凭感觉推荐会给出一个照样溢出的名字，改完白改。**先量，再推荐。**

## 1. 几何规则：竖排组名的可用空间 = 它所属那组的行高

轴名/组名用 `text(..., srt = 90)` 竖排时，**文字长度直接等于它占用的纵向高度**，
它与「该组的色块带」共处同一段纵向区间：

```
可用高度(avail) = 该组行数 × 行高
行高(row_in)    = axes_h_in / (NROWS + 1.5)        # ylim 高度 = NROWS + 1.5 单位，CELL = 1
axes_h_in       = dev_h - mai[1] - mai[3]
安全溢出上限     = 相邻组间隙 / 2
```

关键：**组名长度要跟它自己那组的行数比，不是跟画布比**。
实测 5 轴里 `Decompensation` 只有 **2 行**（成员 Atrophy + Fibrosis），
而 `Metabolism` / `Contractile` / `Inflamm-aging` 各 3 行、`Nutrient` 4 行
⇒ 同样字符数，行数少的组更容易溢出。**同一个图里只有一部分组会出问题。**

### 本次实测（fig_A2_5effects_drop2.R：16.5×8.4 in，mai=c(1.092,2.64,0.672,1.98)，NROWS=16，ps=9，cex=7.5/9，font=2）

`axes_h_in = 6.636`，`row_in = 0.379`，组间隙 0.25 单位 = **0.095 in**（安全溢出 0.047 in/侧）

| 候选 | 字符数 | 实宽 in | 该组可用 in | 结论 |
|---|---|---|---|---|
| **Decompensation**（现名） | 14 | **0.967** | 0.758 (2 行) | **溢出 0.21 in** ⚠️ 为安全上限的 4.4 倍，实际压到相邻 Contractile 标签区 |
| Wasting | 7 | 0.462 | 0.758 | 余 0.30 ✅ |
| Sarcopenia | 10 | 0.645 | 0.758 | 余 0.11 ✅ |
| End-stage | 9 | 0.610 | 0.758 | 余 0.15 ✅ |
| Remodeling | 10 | 0.687 | 0.758 | 余 0.07 — 贴边（安全线 0.047） |
| **Degeneration** | 12 | 0.768 | 0.758 | **仍溢 0.01 in** ❌ 直觉最佳答案，但不可用 |
| **Inflamm-aging**（现名） | 13 | 0.849 | 1.138 (3 行) | **未溢出**（余 0.29）—— 只是"看着长"，改它是取舍不是修复 |
| SASP | 4 | 0.327 | 1.138 | 余 0.81 ✅✅ |
| Inflammaging | 12 | 0.779 | 1.138 | 余 0.36 ✅ |

**产出话术的关键区分**：必须明确告诉用户「哪个是真缺陷（溢出）、哪个只是审美取舍」——
本次 `Decompensation` 是真溢出（非审美问题），`Inflamm-aging` 其实没溢出。不区分 = 用户以为两件都非改不可。

## 2. `strwidth` 的三个实测坑（我连踩两次）

| # | 症状 | 根因 | 修法 |
|---|---|---|---|
| 1 | `Error: plot.new has not been called yet` | `strwidth` 依赖**活动绘图区**；`pdf(NULL)` 之后还没 `plot.new()` | `plot.new(); plot.window(...)` 之后再量 |
| 2 | 量出的数值**小得离谱**（14 字符 = 0.063） | `strwidth(x)` 默认返回**用户坐标**，不是英寸。`plot.window(xlim=c(0,1))` 时 1 用户单位 = 整幅宽 | A：坐标系设成英寸 `par(mai=rep(0,4)); plot.new(); plot.window(xlim=c(0,W), ylim=c(0,H))`（最稳）<br>B：`strwidth(s, units="inches")`（须有活动设备，且 `par(ps=)` 与目标脚本一致） |
| 3 | 量的字与图上不一致 | `par(ps=)` / `cex=` / `font=` 没对齐目标脚本 | 脚本里 `cex = 7.5/9` → 探测器传 `--cex 0.8333`；`font=2` 也要传 |

现成工具：**`scripts/measure_text_in_inches.R`**（已封装上述全部要点，直接 `--labels/--bands/--row-in` 调用）。

## 3. 换词硬约束：贴切 ≠ 可用

最"贴切"的词恰恰不能用的情形，本会话出现两次：

| 轴 | 成员程序（热图行名） | 因此**禁用**的候选 |
|---|---|---|
| 终末失代偿轴 | `scoreAtrophy`、`Fibrosis` | **Atrophy** / **Fibrosis** / Fibro-atrophy |
| 炎症-衰老轴 | `scoreInflammatory`、`scoreTNFA`、`scoreROS` | **Inflammatory** / **Inflammation**（近似撞词） |

理由：轴名与成员名撞词 ⇒ 读者分不清「这是分组名还是程序名」，层级失效。
（同一约束在本项目早先已被记过一次：最贴切的 Atrophy / Fibrosis 恰不能用。）

**语义窄化要主动声明**：`SASP` 极短且是领域标准缩写，但该轴含 ROS —— 而 ROS 是 SASP 的**上游驱动**而非 SASP 本身，
用 SASP 会把"氧化应激"这条腿藏起来 ⇒ 交付时补一句「图注需加 SASP axis includes ROS」，把代价摆在明面。
`Wasting` 只覆盖 Atrophy 一侧、不含纤维化（⚠️ **本文件早前版本把 `Sarcopenia` 也一并说成「只覆盖 Atrophy 一侧」，该说法已被文献推翻 —— 见 §5，不要再引用旧说法**）；`End-stage` 保留了原词
`Terminal decompensation` 的"不可逆"方向性。

## 4. 交付：只 patch `AXES` 的 `name` 字段

改名属**最小改动类**请求（铁律 A/B 适用）：

```r
AXES <- list(
  list(name = "Metabolism",    color = "#2C7FB8", members = c(...)),
  list(name = "Wasting",       color = "#8C5FA8", members = c("scoreAtrophy", "Fibrosis")),  # ← 只改这一处
  ...)
```

- 绘图逻辑、几何、配色、字号、星号判据**一字不动**；轴名只出现在 `draw_group_stripes()` 的 `text(..., ax$name)`
- 同项目里的派生脚本（dz 版 / fibertype 版）用同名轴 ⇒ 改名前先问「要不要同步」，**不要自动批量改**
- 复选方案用 `ask_user(kind="plan")` 给互斥选项（每项附实测宽度与代价），**不要在正文末尾用问句**

## 5. 最终选词（2026-10-21 用户定稿）+ 决策用的「三关顺序筛」

用户勾选：**方案B = `Sarcopenia` + `Inflammaging`**，并补一句
「**我只要了解名字即可**，为什么你要选这两个词，给我理由」。

### 5.1 三关顺序筛（不是「看谁最短」）

```
第 1 关 不撞名     轴名不得与轴内成员程序名相同 → 直接淘汰 Atrophy / Fibrosis / Inflammatory
第 2 关 版式可行   竖排实宽 ≤ 自身色块高（含安全溢出 0.047 in） → 淘汰 Degeneration（0.768 > 0.758）
第 3 关 术语规范   领域标准术语 > 描述性词 → Sarcopenia / Inflammaging 胜出
```

**三关全过 = 唯一交集。** 顺序不能换：先过第 1 关再看第 2 关，
否则会为一个根本不能用的词白量半天宽度。

### 5.2 为什么是这两个（逐条理由，可直接复述给用户）

| 词 | 选它的理由 | 反例（为什么不用） |
|---|---|---|
| **Sarcopenia** | ① 是**诊断实体**不是描述词（EWGSOP/EWGSOP2 定义、ICD-10-CM `M62.84`）② 文献支持它同时覆盖本轴两个成员（肌萎缩+纤维化交互被写作 sarcopenia 的中心特征）③ 版式实测余 0.11 in | `Wasting` 临床绑 cachexia/恶病质语境 → 读偏；`Remodeling` 是中性词（可好可坏），而本轴两成员方向一致（都是不利改变）→ 削弱图的主张；`End-stage` 程度失配 |
| **Inflammaging** | ① 术语**收敛后的现行写法**（去连字符：原始词 2000 年写作 inflamm-aging，后续综述已统一为 inflammaging）② 与**用户自己的知识库口径一致**（`gene_sets.yaml` 的 `inflammation` 条目 description 就写 `inflammaging`）⇒ 图注/图/知识库三处同口径，写论文不必再解释拼写差异 | `SASP` 虽最短（0.327 in）但**语义窄化**：SASP 是细胞衰老的分泌表型，而本轴含 ROS —— ROS 是 SASP 的**上游驱动**、不属于 SASP 组成，用 SASP 会藏掉「氧化应激」这条腿 |

> 另有一条软性但用户认的判据：**这两个词都是"衰老领域专名"而非通用英文词**，
> 与同图其余三条轴名（Metabolism / Nutrient / Contractile）术语层级协调；
> 换成 Wasting / Remodeling 会显得像随手起的标签。

### 5.3 🔴 必须主动更正的一句话（复发风险最高）

**早前版本（本文件 §3 与 SKILL.md 正文）写过「`Sarcopenia` 只覆盖 Atrophy 一侧、不含纤维化」——
这句说窄了，已被文献检索推翻。**

严谨分层（**同一句话在两个层级上答案不同，引用前先想清楚在讲哪一层**）：

- **EWGSOP2 的临床诊断定义**：仍以肌量/肌力/功能三维为主，纤维化属伴随病理、非诊断必需项 → 旧说法在这层成立
- **作为轴名覆盖本轴双表型**：肌萎缩-纤维化交互被描述为 sarcopenia 的中心特征 → 旧说法在这层**不成立**

### 5.4 溯源状态（引用前须知）

上述 PMID 来自本会话 `search_papers` 的检索结果，**未逐条做二次联网复核**
（复核那一轮被"代码修改模式"门禁拦下）⇒ 写进论文/图注前再核一遍 URL 级出处。
⚠️ 姊妹参考 `go-enrichment-visualization/references/geneset-provenance-and-axis-classification.md`
已记过同类教训：**凭印象换 PMID 号就会失真**（Machado 2021 有两篇：
33609440 原始出处 + 34074577 方法学评论）。

### 5.5 交付边界：选了名字 ≠ 立即改图

用户明说「我只要了解名字即可」⇒ 本轮**只给理由，不 patch `AXES`、不出图**。
这类「先要理由、后要落地」的两段式请求在本项目反复出现
（对照：同项目「我只想了解参数含义」也出现过）——
**按用户当轮的话定动作范围，不要顺手把方案执行掉**；落地前再确认一次
（并一并问 dz 版 / fibertype 版是否同步）。