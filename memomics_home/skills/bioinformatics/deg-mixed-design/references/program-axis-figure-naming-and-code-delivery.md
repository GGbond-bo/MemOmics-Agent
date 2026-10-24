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

> ⚠️ **本节结论已被 §5 修正，读完请直接看 §5**：此处推荐的 `Degeneration` 经**量宽实测仍溢出**
> （实宽 0.768 > 该轴色块 0.758 in）⇒ 已排除；此处判为「范畴错误、疾病名不能当轴名」的
> `Sarcopenia` **已撤回该否决**，并在 §5 被用户采纳为定稿（方案 B）。

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

---

## 5. 换词最终落地：先量宽定版式，再定稿方案 B（2026-10-15 实测）

触发：用户「`Decompensation` 和 `Inflamm-aging` 这两个基因集分类太长了，有没有简短贴切的？」
→ 我先量宽（本节 5.1–5.2）→ 用户拍板**方案 B：`Sarcopenia` + `Inflammaging`** → 用户追加
「**我只要了解名字即可**，方案 B，为什么你要选这两个词，给我理由」⇒ **只给理由、不动脚本不出图**。

### 5.1 量宽配方（R `strwidth`，三个坑全踩过一遍）

```r
# 坑① 不先建坐标系直接 strwidth → 报错（第一次尝试就死在这）
plot.new()
# 坑② strwidth 返回的是【用户坐标】不是英寸 ⇒ 必须把坐标系设成英寸才有可比性
#        （第二次尝试返回的是用户坐标，数值无意义）
par(usr = c(0, W_in, 0, H_in))              # 让 user unit == inch
# 坑③ cex 要与出图脚本同一约定（本脚本 cex = pt/9）才能量到真实字号
w <- strwidth("Decompensation", cex = 7.5 / 9, font = 2)
```

**判据 = 实宽 vs 该轴自身色块高**（不是全图最长名）——色块高 = 轴成员数 × 行高。

| 候选 | 字符 | 竖排实宽 in | 该轴色块高 in | 结论 |
|---|---|---|---|---|
| `Decompensation`（原名） | 14 | **0.967** | **0.758** | **溢出 0.21 in** ⚠️ 真缺陷 |
| `Wasting` | 7 | 0.462 | 0.758 | 余 0.30 ✅ |
| `Sarcopenia` | 10 | 0.645 | 0.758 | 余 0.11 ✅ |
| `End-stage` | 9 | 0.610 | 0.758 | 余 0.15 ✅ |
| `Remodeling` | 10 | 0.687 | 0.758 | 余 0.07 贴边 |
| **`Degeneration`** | 12 | **0.768** | 0.758 | **仍溢 0.01 ⇒ 出局** |
| `Inflamm-aging`（原名） | 13 | 0.849 | **1.138** | **未溢出**（余 0.29）|
| `SASP` | 4 | 0.327 | 1.138 | 余 0.81 ✅✅ |
| `Inflammaging` | 12 | 0.779 | 1.138 | 余 0.36 ✅ |

**可安全溢出预算仅 0.047 in/侧**（轴间隙 0.095 in）⇒ §1.4 推荐的 `Degeneration` 差 0.01 in 即出局。

🔴 **两个必须讲清的判读**：① `Decompensation` 是**真版式缺陷**（超出安全预算 4.4 倍），不是审美问题
——改它是修 bug；② `Inflamm-aging` **没溢出**，改它纯粹是术语取舍，**不要把它也说成缺陷**（会被用户
对照实测数字反问）。

### 5.2 判决顺序：三关，顺序不可换

**① 不撞名 → ② 版式装得下 → ③ 术语规范**。`Atrophy` / `Fibrosis` / `Inflammatory` 恰是这两条轴的
**成员程序名**，先被①排除 —— 即"最贴切"的三个词必不能用（这是 §1.4 已记的硬约束，本轮再次生效）。

### 5.3 方案 B 定稿与理由

**`Decompensation` → `Sarcopenia`**：

| 理由 | 证据 |
|---|---|
| **是诊断实体而非描述** | EWGSOP / EWGSOP2 正式定义、ICD-10-CM 收录（M62.84）⇒ 临床读者一眼可读，无需猜 |
| **文献支持它同时覆盖本轴两个成员** | PMID 40144669 原文："The interplay between **muscle atrophy and fibrosis** is a central feature of **sarcopenia**"；另有 sarcopenia 与肺纤维化共病（PMID 36057620） |
| 比其余候选语义更准 | `Wasting` 临床绑定恶病质/消耗（癌症、HIV 语境）⇒ 语义偏移；`Remodeling` 是中性词（可好可坏），而本轴两成员方向一致（Atrophy 降、Fibrosis 升）均属不利改变 ⇒ 中性词削弱表达 |

⚠️ **必须显式撤回 §1.4 的旧否决并给分层陈述**（我上一轮说"Sarcopenia 只覆盖 Atrophy 一侧"是说窄了，
用户会追问）：**EWGSOP2 的临床诊断定义**仍以肌量/肌力/功能三维为主，**纤维化属伴随病理、非诊断必需项**；
但作为**轴名**覆盖本轴双表型，有上述文献支持。⇒ 讲法是"作为轴名有据 + 作为诊断定义不含纤维化"，
两句话都要给，只给一句会被两边各驳一半。

**`Inflamm-aging` → `Inflammaging`**（去连字符）：

| 理由 | 证据 |
|---|---|
| **术语收敛后的规范写法** | Franceschi 2000 原始写法是 `inflamm-aging`（PMID 10911963）；Franceschi 本人参与的 2024 综述已用无连字符 `inflammaging`（PMID 39395575），"The Birth of Inflammaging" 同样（PMID 34536213） |
| **与用户自己的知识库口径一致** | `Homo_sapiens/skeletal_muscle/aging/01_生物学知识/gene_sets.yaml` 的 `inflammation:` 条目 description 直接写 `inflammaging` |
| ⛔ 为何不用最短的 `SASP`（0.327 in） | SASP = **细胞衰老的分泌表型**（细胞层产物）；而本轴三成员是 `scoreInflammatory` + `scoreTNFA` + `scoreROS`，其中 **ROS 是 SASP 的上游驱动、本身不是 SASP 成分** ⇒ 用 SASP 会把"氧化应激"这条腿藏起来 |

### 5.4 交付形态（本轮实测）

- 用户说"**只要了解名字即可**"⇒ **只回答理由，⛔ 不动脚本、不出图、不重跑**。这是**确认型回合**，
  要按 SKILL.md 要求**明说"本轮没有动脚本"**，不能含糊过去。
- 落地时只需改脚本 `AXES` 列表的**两个 `name` 字段**（本例 L36 / L38），**绘图逻辑与其余四个轴名一字不动**；
  改完**默认直接真跑**（用户在同类任务里紧接着就会说"你运行这个代码，跑出图给我看看"），重出 PNG/PDF/SVG/TIFF。
- 主动"提醒改别的版式"要克制：`Inflammaging` 只省 0.07 in，**别把它当版式修复卖**（见 5.1 🔴）。