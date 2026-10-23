# 程序轴图的轴命名 与 代码交付形态（实测记录 2026-10-14）

本文是 `deg-mixed-design` SKILL.md「程序轴图的轴设计 / 轴命名 / 代码交付」一节的实测底稿。
场景：示例组织 MF AUCell 程序打分图（FigA2 五效应矩阵图 + FigA3 亚群矩阵图），
17 程序 / 5 轴 / 10 亚群，脚本 `fig_A2_5effects_v5_rawp.R`、`fig_A3_CNS_v6.R`。

---

## 1. `Decompensation` 换词请求的完整应答（用户问：「这个是什么意思？有没有更贴切的词，短一点的」）

### 1.1 先核事实：这条轴里到底装了什么

**别凭轴名猜内容** —— 从脚本/日志实证：

| 核实项 | 实测结果 |
|---|---|
| 该轴成员 | 仅 **2 个**：`scoreAtrophy`（萎缩）+ `Fibrosis`（纤维化） |
| 项目自己的分类文档原名 | 「Terminal decompensation / maladaptive remodeling」 |
| 依据 | PMID 31325479（萎缩泛素-蛋白酶体）+ Reactome 胶原形成 R-HSA-1650814 |
| 标签长度（图内对照） | `Decompensation` 13 > `Inflamm-aging` 12 > `Metabolism`/`Contractile` 10 > `Nutrient` 8 |

### 1.2 词源与临床原义

拉丁 `de-`（去除/反转）+ `compensatio`（代偿）→「**代偿机制失效**」。
临床原义是**功能结局**（器官储备耗尽后无法维持功能）：心衰失代偿、肝硬化失代偿、膀胱代偿失调。
⇒ 它是**结局词**，不是**分子机制词**。

### 1.3 领域用法证据（决定能不能借用）

PubMed 检索 `muscle decompensation` 命中 8 篇，逐篇归类：

| PMID | 实际语境 |
|---|---|
| 9833315 | 膀胱平滑肌代偿失调 |
| 30824479 | 二尖瓣反流相关心肌失代偿 |
| 35817498 | 心衰失代偿 |
| 40902438 / 41045465 | 失代偿期肝硬化 |
| 16912873 | 无创通气（失代偿呼吸） |

⇒ **0 篇**用于衰老肌肉的分子程序轴。「跨层级借用」在此有据可依地**不成立**。

### 1.4 候选替代词逐项对比（推荐度排序）

**硬约束先说**：轴内已有 `scoreAtrophy` 与 `Fibrosis` ⇒ 最贴切的两个词
（Atrophy / Fibrosis）**恰恰不能用，会撞名**。这条框定了整个候选范围。

| 候选 | 字符 | 含义 | 贴合度与证据 | 风险 |
|---|---|---|---|---|
| **Degeneration** | 12 | 退行性变 | 病理学通用词，同时涵盖肌纤维丢失 + 纤维化替代；`muscle degeneration` 为常规表述 | 中性偏泛；眼科「黄斑变性」占用该词，需上下文消歧 |
| **Remodeling** | 10 | 重塑 | 机制上最精确：萎缩 = 肌原纤维重塑、纤维化 = ECM 重塑；有直接锚点 PMID 34075679「maladaptive tissue remodeling」 | ⚠️ 单词偏中性/正面 —— 图含运动面板，读者可能误读为「运动良性重塑」；要消歧须写 `maladaptive`（21 字符，反而更长） |
| **Wasting** | 7 | 消耗/萎缩 | 最短，肌少症领域经典词（PMID 38574975） | 只覆盖萎缩、不覆盖纤维化 → 漏描述轴内 `Fibrosis` |
| **Sarcopenia** | 10 | 肌少症 | 是整套图的疾病名（含 atrophy + fibrosis，PMID 32096609） | ❌ 范畴错误：疾病名不能当五轴之一，会被审稿人指循环定义 |

**给出的三档建议**：要「一个词 + 明显更短 + 不撞名」→ `Degeneration`；
要最准确（可接受两词）→ `Fibro-degeneration` / `Maladaptive remodeling`（但都不更短）；
只看重短 → `Wasting`（须图注补纤维化说明）。

⚠️ 汇报时必须点明**改名牵动两张图**（FigA2 + FigA3 的 SVG 里都能 grep 到该文字）＝ 换词要重出这两张。

---

## 2. 身份轴分类决策（用户：「加入 typeI、type II 以及 typeIIX 的打分，你自己分类好」）

### 2.1 先核数据（不要假设要重算）

| 核实项 | 实测结果 |
|---|---|
| 打分列是否已在数据里 | ✅ `scoreI_AUC` / `scoreII_AUC` / `scoreIIa_AUC` / `scoreIIx_AUC`（`示例评分方法_meta.csv` 第 35–38 列） |
| 效应表是否已覆盖 | ✅ `effect5_effsize_v3.csv` 含 22 score × 5 效应 × 10 亚群 = **1100 行**完整效应量 + p |
| 结论 | **两版图都无需重算统计量**，只需重排行/轴 |

### 2.2 分类判断（用户授权"你自己分类好"，但依据要摊开）

现有 5 轴都是**功能程序**（代谢/营养/收缩机制/炎症/失代偿），
而 `scoreI/II/IIx` 是**肌纤维类型身份**打分（MyHC 亚型），且图上本来就有
`Pure Type I / Pure Type IIA / Pure Type IIX` 三个亚群与之一一对应。

⇒ 决策：**新建第 6 轴 `Fiber type` 并列，置顶，独立橙色 `#E6862B`**；
⛔ 不并入 `Contractile`（收缩机制 ≠ 纤维身份，合并会把一栏装成两种东西）。
轴名取 **10 字符**与 `Metabolism`/`Contractile` 同长 ⇒ 左缘版式零改动。

### 2.3 两版构成与产物

| 变体 | 构成 | 说明 |
|---|---|---|
| v6_drop2 | **15 程序 / 5 轴** | 删 `scoreSenMayo`（Inflamm-aging 4→3）+ `Adipogenesis`（Metabolism 4→3） |
| v7_fibertype | **18 程序 / 6 轴** | 在 drop2 基础上加 `Fiber type` 轴（`scoreI`/`scoreII`/`scoreIIx`） |

实绘星号（raw p<.05，未校正，分母已随程序数变化）：

| 效应 | drop2（分母 150） | fibertype（分母 180） |
|---|---|---|
| Aging | 77 | 90 |
| ExOld | 27 | 33 |
| ExYoung | 10 | 11 |
| ExT2D | 5 | 10 |
| T2D | 2 | 6 |

⚠️ 判读时**必须同时给分母** —— 两版分母不同（150 vs 180），只看分子会误判"加了轴效应变强"。

---

## 3. 「把代码给我」的交付形态（用户：「把你做五效应图的代码给我，要求掉两个基因集的脚本」）

### 3.1 用户要的是什么

**能直接跑的那一份单变体脚本，且代码贴在对话里。**
不是"包含所有变体的那一份"，也不是"给你个路径自己去开文件"。

### 3.2 交付六条（已在 SKILL.md 概述，此处给可复制骨架）

```r
#!/usr/bin/env Rscript
# ============================================================
# fig_A2_5effects_drop2.R —— FigA2 五效应图【去掉两个基因集版】
#   由 <双变体脚本> 精简而来（只留变体1，绘图逻辑一字未改）：
#     ✂ 删 scoreSenMayo(Inflamm-aging) + Adipogenesis(Metabolism)
#   版式 / 几何 / 配色 / 字号 / 边距 / 星号判据全部与 v5 一致。
# ============================================================
...
# ---- 5 个功能轴（已删 Adipogenesis 与 scoreSenMayo）----
AXES <- list(
  list(name = "Metabolism", color = "#2C7FB8",
       members = c("scoreOxPhos", "Glycolysis", "FattyAcidMetabolism")),   # ← 删 Adipogenesis
  list(name = "Inflamm-aging", color = "#D64550",
       members = c("scoreInflammatory", "scoreTNFA", "scoreROS")),         # ← 删 scoreSenMayo
  ...)

PROGRAM <- unlist(lapply(AXES, `[[`, "members"))
stopifnot(!anyDuplicated(PROGRAM),
          !any(c("scoreSenMayo", "Adipogenesis") %in% PROGRAM))   # 断言：确已剔除
```

⚠️ 保持"其他不变"的实操要点：
- **不重新定义 `CELL` / `PANEL_GAP` / `W` / `H` / `maiA` / 字号** —— 逐字沿用基线值，
  否则"只有轴构成变了"这句话就无法自证。
- 出图循环里**只让 `AXES` 成为变量**；`draw_grid` / `draw_group_stripes` / `draw_cbar`
  三个函数**整段照搬**。

### 3.3 汇报必须说清的四件事

1. **未重跑**：同名产物已在盘（本例 `figures/FigA2_program_5effects_drop2.{png,pdf,svg,tiff}`
   已于上一轮出过且非空），按铁律 13 复用不重跑。
2. **若你跑会覆盖哪几个文件**：点名 8 个（`figures/` + `figures/R_version/` 各 4 格式），
   其余版本不受影响。
3. **派生血缘**：由**已跑通**的双变体脚本机械精简（只删 fibertype 分支），不是未验证的新代码。
4. **统计量不用重算**：`effect5_effsize_v3.csv` 的 `p_np` 列就是 raw p，`eff` 列是
   Hedges' g（独立）/ `d_av`（配对）—— 见 SKILL.md §效应量口径。

---

## 4. 一句话备忘

**轴名是给别人读的分类标签，不是内部变量名** —— 它要同时满足
① 语义层级齐（全是机制词或全是身份词，别混）② 不与成员撞名 ③ 长度不破坏版式
④ 有领域用法证据。四项任一不满足，用户第一眼就会问出来（本例正是如此）。