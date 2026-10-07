---
name: mixed-design-deg
description: "混合设计差异表达分析（组间独立比较 + 组内配对比较同存）：24 donors × 2 时间点的 aging/糖尿病/运动前后 DEG。pseudo-bulk + dream LMM (1|donor) 统一建模；cell-level MAST 的合法性取决于样本层变异是否进模型（见「细胞级方法的合法性条件」，含 Cell 2026 官方先例）。含同构高分文章源码证据库。"
when_to_use: "[mixed-design-deg] 多受试者实验含两组独立比较 + 同一受试者重复测量（pre/post、多时间点）时找 DEG：如 三组（Y/O/OD）× 运动前后、干预前后配对 + 组间比较、纵向随访组间对比。触发词：独立+配对、混合设计、配对比较、pre/post、重复测量、随机效应 donor"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [deg, mixed-design, lmm, dream, pseudobulk, paired, repeated-measures, 03_高级分析]
    difficulty: advanced
    language: R
    category: scRNA
prerequisites:
  r_packages: ["variancePartition", "DESeq2", "edgeR", "limma", "muscat"]
---

# 混合设计 DEG 分析（组间独立 + 组内配对）

## 适用场景

- 设计含两种比较：**组间独立**（如 Y_Pre vs O_Pre 衰老、O_Pre vs OD_Pre 糖尿病）+ **组内配对**（同一 donor 运动前后 Post−Pre）
- 典型结构：24 donors × 2 时间点 = 48 样本，3 组（Y=10 / O=7 / OD=7）
- 用户已用 MAST 但被质询"独立、配对、随机效应怎么处理"时 → 本 skill 是答案

## 核心结论（CNS 编辑视角）

**主分析 = pseudo-bulk counts → dream (variancePartition LMM)**，一个模型统一建模全部比较 + group:time 交互：

```r
# ① 按 donor × time × celltype 聚合 counts（edgeR::sumTechReps 或 rowsum）
# ② 每个 celltype 单独建模:
form <- ~ group + time + group:time + (1|donor)   # group: Y/O/OD; time: Pre/Post
fit  <- dream(dge, form, metadata)
# ③ 提取对比：
contrasts <- makeContrastsDream(form, metadata,
  Aging     = O_Pre - Y_Pre,                                  # 独立
  Diabetes  = OD_Pre - O_Pre,                                 # 独立
  Ex_Y      = Y_Post - Y_Pre, Ex_O = O_Post - O_Pre,          # 配对
  Interact  = (O_Post-O_Pre) - (Y_Post-Y_Pre))                # 组×时间交互（卖点）
fit <- eBayes(fit); res <- topTable(fit, coef="Aging", number=Inf)
```

**备选**（按稳健性排序）：
1. dream LMM（首选，`(1|donor)` 显式建模配对）
2. limma-voom + `block=donor`（duplicateCorrelation 估计重复测量相关）
3. muscat::pbDS（Crowell 2020 同场景现成封装）
4. DESeq2 `~ donor + condition` 独立 paired design（组间+组内全塞一个模型会耗自由度，配对比较建议单独跑）

## ⛔ 朴素 cell-level MAST 的 3 条硬伤（≠「禁止用细胞级」）

> 🔴 **2026-09-26 重要更正**：本节原标题是「为什么**不要** cell-level MAST 当主分析」，本 skill 的
> frontmatter 也曾写「禁止 cell-level MAST 当主分析」—— **这个绝对化表述是错的**，用户拿已发表实例
> 反证后已修正：**细胞级可以做主分析**，真正的红线是**样本层变异必须进模型**。
> 下面 3 条硬伤**只针对「没有任何样本层校正」的朴素细胞级检验**，不是针对细胞级本身。

### 细胞级方法的合法性条件（四条途径任选其一）

| 途径 | 检验单位 | 样本层结构怎么进模型 |
|---|---|---|
| 样本级 pseudobulk | 样本 | 单位本身就是样本 |
| 混合模型 | 细胞 | `(1\|sample)` / MAST `method="glmer"` |
| **RUV / SVA 因子当协变量** | 细胞 | 从样本级数据估出的因子作固定效应 |
| pseudobulk PC / 残差当协变量 | 细胞 | 同上 |

**官方先例（可引用；别再对用户说"细胞级不能当主分析"）**：Zhang X et al. *Cell* 2026
（PMID **42612631**，猕猴脑衰老图谱，2,955,873 核 / 23 只猴）**用细胞级 MAST 做主 DEG** ——
但先用**样本级 pseudobulk + edgeR deviance 残差**估 RUVr 因子（k=10），取**前 5 个作协变量**：
`zlm(~ Age + subtype_new + W_1..W_5)`（走默认 bayesglm）；基因过滤 `pctcut=0.1`、个体需 ≥10 个该亚型细胞。

🔴 **该篇阈值必须按模态引用（2026-09-29 更正我先前的错误引用，务必照抄更正版）**：

| 该篇分析 | 模态 | 原文阈值 |
|---|---|---|
| **sDAREs**（阶段特异差异可及性） | **ATAC** | `P < 0.05` 且 `log2FC > 0.25` ← **0.25 出自这里，不是 RNA DEG** |
| longDAREs（长寿相关） | ATAC | `P < 0.0002` 且 `\|log2FC\| > 1.1` |
| pDAREs（渐进性） | ATAC | `\|R\| > 0.5` + `P<0.05` + 置换 `P<0.1` + `\|age coef\| > 0.005` |
| pDEG / sDEG（**本类设计在仿的那套**） | RNA (MAST v1.12.0) | 官方代码只做 `p.adjust(p,'fdr')` + 剔 NA coef —— **无任何效应量阈值** |

⇒ ⛔ **不要写成「猴脑 DEG 用 Q<0.05 & \|log2FC\|>0.25」** —— 那是把 ATAC 可及性判据挂到 RNA DEG 名下，
审稿人一查即破。θ 取 0.2/0.25 的理由要另找（见 `enrichment-conclusion-validation` §门禁5）。

⚠️ **未解冲突（如实记录，别替作者圆）**：该篇 methods 原文有「…as a fixed effect, and sample was modeled
as a random effect」一句，指向 MAST 模型**含样本随机效应**；但从官方仓库 `RUV_MAST_pDEG_MBA.R` grep 到的
`zlm` 调用**没有 `method="glmer"`、公式里也没有 `(1|…)`**。文本与代码不一致 ⇒ **两方证据都留档、标明出处**，
不要在论文里替它断言随机效应有无，也**不要**拿这篇当 `(1|individual)` 的引用依据
（要引随机效应：自己给 `glmer` 实测，或引该篇**细胞比例**分析那句明写了 `(1|sample)` 的 Poisson GLMM）。
同一篇的**细胞比例**分析则用 Poisson GLMM `n ~ age + modality + (1|sample) + offset(log(total cell))`
—— 该用随机效应的地方它确实用了。代码：`github.com/3DC-STAR-Anthony/NHPABC` →
`snRNA/04.Identification_of_differentially_expressed_genes(DEGs)/RUV_MAST_pDEG_MBA.R`、`RUV-seq_sDEGs.R`。

⇒ **本类设计（多供体 / 每组 7–10 / Pre-Post 配对）的推荐仍是 pseudobulk + dream LMM**
（它同时建模配对与交互，口径最省事）；但**细胞级 + 样本层校正不是错的做法**，可作主分析的合法备选，
也可与 pseudobulk 互为正交验证。

⚠️ **附带最有价值的阈值教训**：本类设计的中位 `|logFC|` 常在 0.17–0.24（见 §3.5），此时拿习惯性的
1.0（2 倍）去讨论"能检出多大变化"会得出"几乎检不出、方法有问题"的错误结论 —— **先查目标领域
已发表/已接受的判据再定阈值**（θ=0.2/0.25 的取舍证据 + "同一 θ 在不同表上杀伤力完全不同"见
`enrichment-conclusion-validation` §门禁5；⛔ 不要再把 0.25 说成"猴脑 RNA DEG 判据"——
那是该篇 **ATAC sDARE** 口径）。
完整依据/配方 → `references/celllevel-inference-unit-and-sample-structure.md`

### 三条硬伤（仅适用于无样本层校正的朴素细胞级检验）

1. **假重复**：同 donor 数千细胞被当独立观测 → I 型错误暴涨（Zimmerman 2021 Nat Commun, 10.1038/s41467-021-21038-1；Squair 2021 Nat Commun, 10.1038/s41467-021-25960-2）
2. **配对未建模**：Pre/Post 同一人 = 重复测量，不建模被个体噪声淹没或虚假放大
3. **随机效应支持弱**：MAST hurdle + (1|donor) 的收敛/自由度业界不认可是金标准；拆开跑 N 次独立比较 → 多重检验不一致、无法回答 group:time 交互

MAST 保留为**细胞级敏感性分析**（注明假重复风险），两法交集 = 稳健 DEG。
⚠️ **但不要把这句话读成「细胞级不能用」**：若走细胞级主分析（RUV/SVA 因子协变量，或 `method="glmer"` +
`(1|donor)`），按上方「细胞级方法的合法性条件」执行 —— 有 Cell 2026 官方先例，是合法做法。

### 真跑细胞级 MAST / NEBULA 时的配方与四个 API 陷阱（2026-09-26 实测，连崩 6 次才定位）

**官方依据（读包自带 Rd 原文，非记忆）**：`zlm.Rd` → `method: character vector, either 'glm', 'glmer'
or 'bayesglm'` ⇒ **`method="glmer"` 就是随机效应通道**，公式可写 `~ type + cngeneson + (1|individual)`
（离散 logistic + 连续 gaussian 两部分都带供体随机截距），此时 **`ebayes=FALSE`**。
这也说明上面第 1 条硬伤**可被修好**：Squair 2021 批的是**不带随机效应**的朴素细胞级检验，不是细胞级本身
—— 🔴 **2026-09-26 更正**：加了样本层校正（随机效应 / RUV 协变量）之后，**细胞级可以作为主分析**
（Cell 2026 官方先例见本文档「细胞级方法的合法性条件」）；此前「不改变『不当主分析』的结论」的表述**已作废**。

| # | 陷阱 | 报错原文 | 正解 |
|---|---|---|---|
| 1 | `MAST::coef(fit, "C")` | `'coef' is not an exported object from 'namespace:MAST'` | `coef`/`vcov` 是 **S4 泛型但未从命名空间导出** ⇒ **裸调用** `coef(fit,"C")` / `vcov(fit,"C")`（`library(MAST)` 后自动分派） |
| 2 | `waldTest(fit, MAST::CoefficientHypothesis(...))` | `"MAST::CoefficientHypothesis" is not a defined class` | **不用 waldTest**，直接 `coef + vcov` 手算 Wald：`est = B %*% w`、`se = sqrt(t(w) %*% Vi %*% w)`、`p = 2*pnorm(-abs(est/se))` —— 支持任意线性对比、不依赖内部导出 |
| 3 | 假设 `vcov()` 维度是 (基因,系数,系数) | 不报错、**静默取错值** | 实测是 **(系数, 系数, 基因)**（`7 x 7 x 3000`，`dimnames[[3]]` 才是基因名）⇒ 代码里**自动判方向**：`orient <- if (length(intersect(dimnames(vv)[[3]], rownames(cc))) > 0.5*nrow(cc)) "ccg" else "gcc"` |
| 4 | 直接 `split(seq_len(n), md$individual)` | `group length is 0 but data length > 0` | **先 `print(names(md))` 再动手**（别假设列存在）；`individual <- sub("_[^_]+$", "", as.character(md$samplename))` |

⚠️ 陷阱 1–3 是同一族：**对包内部符号/返回结构的假设**。判据：**凡对包函数签名、导出状态、返回维度拿不准
⇒ 读该包自己安装的 Rd（`tools::Rd2txt(tools::Rd_db("<pkg>")[["<fn>.Rd"]])`）或直接 `print(dim/dimnames)` 实测，
禁止凭记忆写**；⛔ 报错后**不要「换个写法再试一次」逐步逼近**（连败即触发循环检测，本轮白烧 5 轮）。

**NEBULA 官方 API（读 README 原文核实）**：`nebula(count, id, pred = model.matrix, offset, method = 'LN'|'HL', ncore)`；
`count` 是 **M(基因) × N(细胞)**、元素必须为**整数**、支持 sparse `dgCMatrix`；`pred` 必须含**截距列**；
细胞需**按 subject 连续排列**（`group_cell()` 负责重排）；`offset` 传正数向量（推荐细胞文库大小）；
**返回原始 p 值，必须自行 BH**；⚠️ README 明确警告**二元变量过多会导致 separation**。
**让每个对比变成单一系数（免协方差输出依赖）**：每对比在**相关子集**上单独拟合一次 ——
Aging/DM = 两 Pre 组 `~grp`；Ex_Young/Old/DM = 单组 `~time`；DiD = 两组 × Pre/Post `~grp*time`（交互项即 DiD）。
子集内仍有供体随机效应 ⇒ 配对结构保留。

**计算量**：`glmer` 单基因一次优化（约 0.05–0.5 s，随细胞数增长）⇒ **50 万细胞全量必须按供体降采样**
（`--max_cells_per_donor`；同供体内细胞可交换 ⇒ **降采样无偏**，只损失功效）；NEBULA 专为大规模设计，可上全量。

**结果口径三条**：① `C` 组件 = **表达量**（log2 尺度均值差）、`D` 组件 = **检出率**（log-odds）——
**两种不同的量，⛔ 不能混着说"上调"**；② 检验族固定为「亚群内 × 该对比内 × 该组件内」BH（与 pseudobulk 口径对齐）；
③ **统计显著 ≠ 可稳定检出** —— 报「设计可稳定检出的 |logFC| 下限」比只报显著基因数更有信息量。

**升级条件（缺一不可，否则细胞级新发现只能写「候选/未确认」）**：样本层校正项有效且稳定（随机效应方差 >0 / RUV 因子解释到目标变异）
+ **供体内条件标签置换 ≥100 次**显示超出零分布 + 与 pseudobulk 方向一致 + 效应量达设计下限。
**双向收获**：两法都零的对比 = **稳健阴性**（如本例 DM），比单方法可信 —— 这是细胞级分析最实在的产出。

**本机 / 集群分工**：全量 50 万细胞对象在集群时，本机可用**平衡子集**（如每亚群 2000 细胞）验证脚本跑通，
但**数字会随全量重跑变化**，交付时必须声明。

> 📄 完整配方（四条陷阱的实测报错原文 + coef/vcov 手算 Wald 代码 + vcov 方向自动判定 + NEBULA 逐对比
> 子集设计 + 计算量外推 + 本机/集群分工 + 结果表形状）见 `references/cell-level-mast-nebula-recipe.md`。

## 参考文献与源码证据库

见 `references/mixed-design-deg-evidence.md`：
- Lovric 2022 Commun Biol（10.1038/s42003-022-04088-z）— 运动单细胞 3 人配对，源码用 cell-level Wilcoxon 无配对建模 = **反面教材**
- MoTrPAC 大鼠（Nature 2024）— bulk DESeq2 + RNA 质量协变量（RIN/globin/UMI dup）
- MoTrPAC 人类 meta 分析 — rma.mv `random = ~ V1|gse`（研究随机效应）+ `mods = ~ training + time` = 独立+配对+随机效应三者同时建模的正统示范
- Zemke 海马 aging — 连续年龄相关（用户专利参考）

## 找同构文章源码的 GitHub 工作流

1. `https://api.github.com/search/repositories?q=<关键词>&sort=stars`（未认证限流 60/h，遇 403 直接 clone 已知仓库）
2. `git clone --depth 1 <repo> /e/tmp/deg_source/<名>`（clone 不占 API）
3. search_files `*.R`/`*.ipynb` 定位 DEG 脚本；grep `DESeq|MAST|FindMarkers|dream|limma|pseudobulk`
4. 读核心函数（formula/contrasts/聚合代码），别只看 README
5. 关键词：`MoTrPAC` / `exercise+single+cell+skeletal+muscle` / `<tissue>+aging+single` + 作者名

## 效应量口径（别只修检验、不修 d）

混合设计出**效应量热图**时（多个面板共用同一色标），效应量必须按设计分派：

| 比较 | 该用 | ⛔ 不该用 |
|---|---|---|
| 组间独立（Aging / T2D） | Hedges' `g` = `d_s × J`，`J = 1 − 3/(4·df−1)` | 裸 Cohen's `d_s`（小 n 有正偏差） |
| 组内配对（Post − Pre） | `d_av` = `mean(diff)/√[(s_pre²+s_post²)/2]`（同尺度） | `d_z`（被 r 放大）；独立 pooled d |

`d_z/d_av ≈ 1/√(2(1−r))` → 同一受试者 r=0.8 时 `d_z` 虚高 **58%**，共色标图上会出现
「运动效应强于衰老效应」的**假象**。公式库 / 审计配方（含"出图脚本只读表、公式藏在建表脚本"、
`n₁=n₂` 时 pooled d ≡ d_av ⇒ **d 相同不能推断口径**、FDR 检验族必须同步复核）→
`references/effect-size-mixed-design.md`（⚠️ **跨 skill 引用**：该文件在姊妹 skill `deg-mixed-design`
目录下，本 skill 目录内没有）；出处 Lakens 2013，
**PMID 24324449 / DOI 10.3389/fpsyg.2013.00863**。

## 🔴 对比解读四大陷阱（本类设计专属；2026-09-25 实测）

### 1. 共享项伪相关：共用同一组均值的两个对比，估计量天然相关

**任意两个对比只要共享一个组均值且符号相反，其估计量结构性负相关**——这是设计矩阵的数学后果，不是生物学。

实测：`Aging = O_Pre − Y_Pre`、`Ex_Old = O_Post − O_Pre` 共享 `O_Pre`（符号相反）。按 48 样本设计
（n_O=7、n_Y=10）解析计算 `Cov(β̂)=(X'V⁻¹X)⁻¹`：

| 供体 ICC | corr(Ex_Old, Aging) | 纯伪影下 Ex_Old 显著基因的预期符号一致率 |
|---|---|---|
| 0.0 | −0.542 | 2.2% |
| 0.3 | −0.454 | 6.3% |
| 0.6 | −0.343 | 12.2% |

实测符号一致率 = **15.7%**（即 84% 方向相反）→ **落在纯伪影预期区间内** ⇒
⛔ **禁止把「Ex_Old 与 Aging 大部分方向相反」写成「运动使老年肌转录组向年轻模式靠拢」**。

⚠️ **DiD 并不豁免（易错点，我曾判断错）**：`Ex_x_Aging = (O_Post−O_Pre)−(Y_Post−Y_Pre)` 与 `Aging`
**同时**共享 `O_Pre` 和 `Y_Pre` 两组均值，实测 corr = **−0.59 ~ −0.71**。以为「DiD 无共享项」是错的。

✅ **要检验「向年轻靠拢」必须换工具**：按样本算到 Young 质心的距离，配对检验
`dist(O_Post → Young) < dist(O_Pre → Young)`（不依赖对比间的相关）。
计算器：`scripts/shared_term_artifact_calc.py`（改 GROUPS/CONTRASTS 即可）。

### 2. 批次项可识别性判据：完全嵌套于聚合单元 → 不可识别（先实查，别凭直觉）

问「要不要加 `(1|batch)`」时，三步实查（**不许凭"测序批次"想象**）：

```python
md.groupby('library')['samplename'].nunique()      # 每个 batch level 含几个样本
md.groupby('samplename')['library'].nunique()      # 每个样本含几个 batch level
pd.crosstab(md['library'], md['type'])             # 是否与分组/时间点混淆
print(names(md))                                   # 到底有没有 batch/run/lane/plate/date/chemistry
```

判据：
- **每个 batch level 恰含 1 个样本**（完全嵌套）→ pseudobulk 按样本聚合后每个 level 只剩 1 个观测
  → **`(1|batch)` 无自由度可估，不可识别**。这不是"加了没用"，是**加不进去**。
- 实测本例：`library` 96 个 = 48 样本 × 2（每样本恰 2 文库），6 组完全均衡、与 type 零混淆、
  meta 中无其它候选列 → **不加**；Methods 写法：「每个样本包含 2 个测序文库；pseudobulk 按样本合并，
  文库层面技术变异包含在样本级残差中。」
- **batch 与 group 完全共线时绝不能加随机效应**（会吸走组效应）→ 只能声明局限
- 可选敏感性：按 batch level 聚合到更细单元 + 嵌套随机效应，比主结果一致性（非必需）
- ⛔ 不要在细胞级做 Harmony/ComBat 再聚合（破坏整数 counts，且细胞级处理批次 = 伪重复）

### 3. 阴性对比的功效判读：名义 P<0.05 占比 vs 零假设 5%

逐对比算 `(P.Value < 0.05).mean()`，这是判断"无信号 vs 有信号但被 FDR 压掉"的最快电池检查：

| 口径 | 判读 |
|---|---|
| ≈ 5%（零假设期望） | **实质全阴性**；但先看同模型在其它对比有没有信号，排除模型失败 |
| 7–12% | 弱信号，功效不足 |
| > 15% | 真信号 |

实测本例：Aging **32.4%** / Ex_Old 16.2% / Ex_Young 9.9% / Ex_DM 7.1% / **DM 5.71%（≈零假设）**。
⇒ DM 对比 173,950 行仅 1 个 FDR<0.05，属**真阴性**（同模型在 Aging 上检出 32%，排除模型失败）。
措辞铁律：阴性对比写「**未检出**」，⛔ 禁写「无差异」；同时报方向性趋势（本例 IRS1/TBC1D4/PDK4 升、
CS 降，方向与 T2D 一致但 FDR 不达标）。

### 3.5 🔴 用户质疑「基因太少 / 方法是不是有问题」时的四步定量回应（2026-09-26 实测）

⛔ 不许用「这是生物学，效应就是小」当挡箭牌，⛔ 也不许用「方法没问题」当安慰。**四步全部算出数字**：

| 步 | 算什么 | 作用 |
|---|---|---|
| 1 **阳性对照自证** | 同一模型在已知大效应对比上的显著数 | 排除「公式/阈值/亚群静默丢失」最快的一条证据 |
| 2 **π1（Storey 估计）** | `1 − #{P∈[0.5,1]}/(0.5·m)` | **量化「到底有多少基因真变了」**，远强于名义 P 占比 |
| 3 **检测下限反推** | `min\|t\| among FDR<0.05` × 中位 SE | 量化「**这个设计能看见多大的效应**」——用户问题的定量答案 |
| 4 **效应量分布对比** | 各对比中位 \|logFC\| + `%\|logFC\|>1` | 解释跨对比显著数差异 |

**实测（173,950 行/对比 = 17,395 基因 × 10 亚群；48 样本）**

| 对比 | π1 | 中位 \|logFC\| | %\|logFC\|>1 | 名义 P<.05 | FDR<.05 | 检测下限 \|logFC\| |
|---|---:|---:|---:|---:|---:|---:|
| Aging | **48.7%** | 0.348 (1.27×) | 9.8% | 32.4% | 29,550 | 0.69 |
| Ex_Old | 27.2% | 0.235 (1.18×) | 3.5% | 16.2% | 1,246 | 0.91 |
| Ex_Young | **21.5%** | **0.170 (1.13×)** | **0.6%** | 9.9% | **22** | 0.92 |
| Ex_DM | 6.1% | 0.167 | 0.8% | 7.1% | 4 | 1.15 |
| DM | 1.8% | 0.187 | 1.9% | 5.7% | 1 | 1.65 |

⇒ **结论句式**：Ex_Young 有 **21.5% 的基因真变了**，但中位效应仅 **1.13 倍**，而设计只能稳定检出
**≥1.9 倍**（\|logFC\|≥0.92）；\|logFC\|>1 的只占 **0.6%** ⇒ **「基因少」是效应量 vs 检测下限的错配，不是方法坏**。

**⚠️ 对上表（§陷阱 3 名义 P 占比）的修正**：名义 P 占比只是粗筛。用 π1 复核后 **DM 不是「实质全阴性」**——
π1=1.8% > 0，只是最弱。措辞仍用「未检出显著证据」，但**不要断言「完全无响应」**。

### 3.6 ⛔ 面板富集检验的选择偏倚（我犯过并当众撤回，务必照抄正确做法）

**面板与全基因组必须用同一套取数口径**，否则产生虚假富集：

```python
# 【错误】面板取亚群间最小 P（10 次机会），全基因组却用池化率
panel_p = d[d.gene.isin(PANEL)].groupby('gene')['P.Value'].min()
genome_rate = (d['P.Value'] < 0.05).mean()        # 9.9%  → Ex_Young fold 3.15, p=2.47e-06 ← 假象！

# 【正确】全基因组每基因也取亚群间最小 P（匹配零假设）
gmin = d.groupby('gene')['P.Value'].min()
genome_rate = (gmin < 0.05).mean()                # 33.4% → Ex_Young fold 0.94, p=0.79  ← 不显著
```

**机理**：10 个亚群取最小 P，纯随机下 `P(min)<0.05` 的概率 = `1−0.95¹⁰ = 40%`，所以匹配后的零假设率
**本就该是 33–41%**。任何 `min-across-clusters` 的富集检验**必须**配同口径零假设。

实测匹配后 fold 全部 **0.94–1.27，Fisher p=0.24–0.79（全不显著）**；只有秩检验（Mann-Whitney）
在 Ex_Old (p=7.4e-4)、Ex_DM (p=4.5e-3) 上微弱显著。
⇒ **⛔ 不要把「面板富集」当方法有效性的证据**；靠 ① 阳性对照量级 ② **具名基因 + 方向 + 效应量**。
⇒ 另注：面板若混入**急性运动 IEG**（FOS/JUN/EGR1/NR4A），在**训练后静息活检**里本就不该升高
（实测全部 P>0.1）—— **先问活检时相**，用错时相的面板否定方法会把自己坑了。

### 3.7 🔴 pseudobulk 的两个结构性盲区（必写 Limitations）

**盲区 A｜响应异质性 → 效应量被稀释**：`观测 logFC ≈ 单细胞真实 logFC × 响应细胞比例`。
响应比例 20% ⇒ 观测效应只剩 1/5。这是 pseudobulk **换统计正确性的固有代价**，不是代码错，
但它是运动类单细胞数据效应量普遍偏小的**结构原因**。

**盲区 B｜🔴 细胞组成变化对「按亚群 pseudobulk DEG」完全不可见**（本例最重要发现）：

| 亚群 | Pre 细胞数 | Post | Post/Pre |
|---|---:|---:|---:|
| **Pure Type IIX** | 385.8 | **211.8** | **0.50** ⬇️ 腰斩 |
| OTUD1+(II) | 434.3 | 639.2 | 1.47 ⬆️ |
| Specialized MF | 588.5 | 878.7 | 1.49 ⬆️ |
| Pure Type IIA | 3752.2 | 3386.1 | 0.90 |
| Pure Type I | 3622.0 | 3325.8 | 0.92 |

**IIX 运动后腰斩 = 最经典最可重复的运动适应（IIX→IIA 转换）**，但按亚群做的 DEG 测的是**亚群内部**
表达水平 —— 亚群**之间**的比例变化对它是**结构性不可见**的。
⇒ 用户说「不可能运动前后基因都没改变」时，**先算组成**：肌肉很可能变得非常明显，只是变在比例上。
⇒ 必配两个补充分析：① **细胞比例检验**（配对 Pre/Post × 组）→ `celltype-proportion-comparison`；
② **AUCell 打分跨组差异**（meta 已有 `score*_AUC` 列时最快出真结果）——小幅协调变化基因级看不见、打分级看得见。
⚠️ 组成差异须**独立配对检验确认**再定性（n=10/组、方差大时均值比可能是抽样噪声）。

### 3.8 亚群细胞数 ≠ 功效（反直觉，别写错因果）

实测 pseudobulk 输入（中位细胞/样本，共 508,661 细胞 / 48 样本 / 10 亚群，亚群 min 低至 **2** 细胞）：
Pure Type I **3,403** > Pure Type IIA **3,184** > LRP1B+(I) 636 > OTUD1+(I) 446 > OTUD1+(II) 390 >
Specialized MF 373 > RP_high(II) 319 > Pure Type IIX 223 > RSS **182** > RP_high(I) **162**。

但 Ex_Young 的 FDR<0.05 是 **RSS 13**、Pure Type IIA 7、Pure Type I 1 —— **细胞最多的亚群反而不是命中最多的**。
⇒ `细胞数多 ⇒ 显著基因多` **不成立**；主导因素是**效应量定位**（哪些亚群真的在响应）。
⛔ 别把细胞数当功效代理量写进结论。

### 3.9 工作流：一次跑完整个诊断清单，别边跑边加

本轮连写 3 个诊断脚本（π1 → 组成 → 修正版）→ 触发系统**循环检测强制干预**，结论还分散在多轮里。
⇒ 用户抛「结果可疑」时，**先把 3.5–3.8 写成 ONE 脚本一次跑完**再解读。

**完整配方 + 逐项实测数字 + 撤回记录** → `references/weak-signal-diagnosis-and-composition-blindness.md`
**一键复跑诊断**（π1 / 检测下限 / 匹配零假设面板对照 / 组成变化 / 具名基因明细）→ `scripts/diagnose_weak_deg_signal.py`

### 4. `coef` 名 = `names(contrasts_vec)`：名字不对称会静默丢对比

```r
contrasts_vec  <- c(Aging_Pre = "typeO_Pre - typeY_Pre", ...)   # key 决定 coefficient 名
contrast_names <- c("Aging", ...)                               # topTable(coef="Aging") → 找不到
```
被自己的 `tryCatch` 吞掉后只会打印「0 个亚群返回结果」，**看起来像阈值太严的数据问题，实际是名字写错**。
硬断言（跑 topTable 前）：
- `rownames(makeContrastsDream(form, colData(pb), contrasts = contrasts_vec))` 必须等于 `contrast_names`
- 或从 `res[[1]]$coefficients` 反查系数名
- 修复只改 **key（标签）**，**绝不能动后面的表达式**（`typeO_Pre` 是 factor level 名，须逐字一致）

### 4b. 同一段 dreamlet 脚本里另外两处静默坑（2026-09-26 代码审查）

- **`form` 必须在 `processAssays()` 之前定义**：分文件跑没事，**整段 source 会 `object 'form' not found`**。
  且 step2（估 voom 权重）与 step3（建模）的公式必须**同源**——读同一份 `run_params.json`，
  别靠 `cat()` 打印肉眼比对（格式随版本变，静默错配不报错）。
- **`colData(pb)` 的行名不一定是裸 `samplename`**：`aggregateToPseudoBulk` 可能给 `sample_id` 与
  `cluster_id` 拼接的复合名（形如 `Old_10_Post_TypeII`）⇒ `match(rownames(cd), md$samplename)` 全 NA。
  **跑模型前先实测** `head(colnames(pb))` / `names(colData(pb))`；剥后缀用 `assayNames(pb)` 逐个
  `sub(paste0("_", ct, "$"), "", samp)`，比正则猜下划线稳。
- **`ddf="Kenward-Roger"` 在 10 亚群 × ~10k 基因 × 7 对比下极慢**（逐基因校正自由度）：先 `ddf="adaptive"`
  跑通全链路验证 pb→form→contrast→topTable→输出全部正确，再上 KR 做正式跑。
- 取结果时守住 `stopifnot(all(c("logFC","CI.L","CI.R","P.Value","adj.P.Val") %in% colnames(tt)))`
  —— CI 列缺失说明取数路径变了，**宁可炸也不要静默少两列**（这一点原脚本做得对，保留）。

### 附带两个报告口径

- **亚群基因数不等 → BH 家族大小不等**：实测 10 个亚群基因数 12,268–26,879（**2.2 倍差**），
  小亚群受罚更轻 ⇒ 跨亚群比"显著数"时必须先报基因数，否则把家族大小差异误读成生物学强度差
- **阳性对照方向性检查**：对照基因"在表内被检验但 0 个达 FDR"时，先看**方向 + 名义 P** 再定性。
  实测本例运动对照方向大体正确（ANKRD1 Ex_Old +2.01 P=0.010、FOS Ex_Young +1.93 P=0.068、
  PDK4/TFAM 方向对）⇒ 是效应量小 + 家族大，**不是伪影**。另：假基因（NPM1P29）与未注释
  `AC*` lncRNA 进主结论前须过注释/多映射/检测率筛查

细节配方与逐项实测数字 → `references/shared-term-artifact-and-batch-identifiability.md`

## 找重合 DEG（交集 / 集合显著性）—— 三条必做口径（2026-09-30 实测）

拿到多个对比的 DEG 表后，下一步几乎必然是「找重合基因」，且用户几乎必然问三件事：
**运动共同 DEG / 运动逆转衰老 / 运动逆转糖尿病**。⛔ **直接数交集个数会得到看起来漂亮但站不住的结论**：

1. **交集数必须对集合大小做校正** —— 随机重叠期望 `E[|A∩B|] = |A|×|B|/N`。
   实测：Aging 集 16,535（8 亚群口径）× 运动组 231 / N=27,015 → **期望重叠 141 个，占小集的 61%**。
   ⇒ 报原始交集数时**必须同时报** Jaccard + 每对 OR/Fisher p + **方向一致率**（同向 = 加剧，反向才可能是逆转）。
2. **主判据用阈值无关的排序法** `Rg = s_A × s_B`（s = 带符号效应量或 −log10P）。只报「FDR<0.05 的交集」
   同时犯两个错：漏掉效应温和的真基因 + 被阈值切片放大假重合。
3. **「逆转」不能用反向交集** —— 见上方 §对比解读陷阱 1（共享项伪相关使 84% 反向成为数学必然）
   ⇒ 必须走**距离分析**（样本到参照质心距离 + 配对检验），这是唯一站得住的写法。

**富集背景必须用实际检测基因 N**（本类实测：老法 17,395 / 新法 9,581），⛔ **不是全基因组**
（否则线粒体/核糖体基因淹掉所有通路）；小交集（几十个基因）用 **GSEA 主 / ORA 辅**，
ORA 只对 Tier1 集合并报 OR，⛔ 不报单个基因的 p。三个池子分开富集：共同运动 / 逆转 / 组特异。

**Tier 分级 = 写结论的唯一合法依据**：两法同向 = **Tier1**（可引用）；仅一法显著 = Tier2；
仅细胞级显著 = **Tier3**（须标注 SE 低估，只能写「候选」）。

**跨方法可比性红线**（回答「新方法是不是更好」时必写）：检验单位不同（供体 n=7–10 vs 细胞 n=数百–数万）
+ 基因池不同 ⇒ **显著数不可横向比优劣**。判膨胀用**方向偏倚指纹**：实测老法 Aging 上下调
均衡（15,390 / 14,160），新法 **57,568 / 2,113 = 43:1** ⇒ 对应 SE 低估 ~26 倍，是**膨胀指纹不是生物学**。

**还缺的对比要先要**：`Ex_x_Aging` / `Ex_x_DM` 两个 **DiD** 是回答「运动效应是否随衰老/糖尿病衰减」的关键，
缺了就只能用距离法间接答 —— 汇报时把缺口列成表要用户补，⛔ 不要自己造。

> 完整方案骨架（13 节：家底 → 全局红线 → 分步判据 → 脚本清单 → 文献 → Limitations → 缺口清单）
> 与「**只交方案文档、不跑分析**」的交付模式 → `references/deg-downstream-route-and-plan-delivery.md`
> md → docx 可编辑版转换 → `scripts/plan_md_to_docx.py`

## 🔴 单基因定位查询：「X 基因在哪个条件 / 哪个亚群变化了？」（2026-10-01 实测）

下游最高频的一问，也**最容易答错** —— 用户手上通常是**已过滤的交付表**，
而目标基因常常恰恰是被过滤掉的那批。

### 1. 先查过滤表，但⛔ 绝不停在那里 —— 回未过滤全量源表再下结论

过滤表是**双重筛除**（FDR 阈值 **和** 效应量阈值）。实测 MEF2C 在 `DEG_fdr05_coef025_*.xlsx` 里
**0 命中**，回原始表却有 **50 行**（5 对比 × 10 亚群），其中 44/50 显著、但 `|coef|` **全部 < 0.25**
⇒ 属于「**统计显著、幅度不够**」，与「没变化」是两件完全不同的事。

三步取证（缺一步就会给出错误结论）：
1. 过滤表 `gene == 目标` → 0 行 ⇒ **不停在这里**
2. 回未过滤源表（用户本地全量表 / `*_allraw_cache.pkl` / 上游统计脚本输出）取该基因**全部**行
3. **两条判据分别报**：`FDR 达标数` / `|effect|max` vs 效应量阈值 ⇒ 定性三选一：
   **真阴性** / **显著但幅度未达标** / **通过全部阈值**

### 2. 基因符号必须做家族模糊匹配，并把命中到的近亲一并报出

`gene == 'MEF2C'` 与 `gene.str.contains('MEF2C')` 结果天差地别。实测：**MEF2C 全 50 个检验无一显著**
（min FDR = 0.333），而同一基因座的反义 lncRNA **MEF2C-AS1 高度显著、幅度大得多**
（coef 0.257–0.812；O_EX 组 10/10 亚群全部上调）
⇒ **它进了共同 DEG 桑基图，MEF2C 进不去**。
⛔ 只精确匹配会漏掉 `-AS1` / `-DT` / `-IT1` 这类反义/内含子转录本，而**这往往正是用户的真实所指**
（他在桑基图上看到的就是 AS1）。⇒ 一律用 `contains` 扫一遍，近亲命中**作为副标题一起报**。

### 3. 方向必须从**原始统计列**读，⛔ 不从 `direction` 列推

该列实测对一个对比的 2.3 万行是**同一个值**（组级模板文本，形如 `OD_Post > OD_Pre (coef>0)`），
括号里的 `(coef>0)` 是**条件说明**、不是该行的判读 ⇒ 逐行按它读会**全错且不报错**。
判据：**任何列先算一遍 `nunique()`，等于 1 的列不能当逐行属性用**。
方向必须回到对比的**代数式**（`Aging = O_Pre − Y_Pre` ⇒ logFC > 0 = 老年高；
命名 `A_vs_B` 时 coef > 0 表示 **B > A**）。

### 4. 汇报骨架：一句话结论 + 效应量矩阵 + 符号一致性表

用户要的是「哪个条件 + 哪个亚群」，固定三件：
① 一句结论；② `10 亚群 × 5 条件`的效应量矩阵（★ 标 FDR<0.05）；
③ **按条件汇总表：符号一致性 n/10 + `|effect|` 均值 + 最接近显著的亚群**。
判「哪个条件真动了」看**符号一致性**，不是看单个最大格。实测 MEF2C：
衰老 **9/10 负**（老年偏低）· 老年运动 **9/10 正**（`|logFC|` 均值 0.251，最大）
· 糖尿病老年运动 **10/10 正** · 糖尿病方向混乱 · 青年运动幅度最小
⇒ 故事是「**衰老↓、运动回补，但幅度小、未达阈值**」。
⚠️ **无一对显著时措辞必须是「方向一致的趋势，未检出显著证据」**，⛔ 不可写「变化了」。

### 5. 同一项目并存两套 DEG 结果（FDR 差 100 个数量级）时怎么处理

本类项目常有**两套并行结果**（用户本地某 pipeline 的输出 + 平台/另一 pipeline 的输出）。

**识别是否同源 → 用 `n_cells` 指纹**：任意一格（gene × celltype × comparison）的细胞数在两张表里
**完全相等**（实测 `MEF2C-AS1 × Pure Type IIX × Y_EX = 4079`）⇒ 同源、可并置比较；
`n_cells` 不等 ⇒ **两套不同分析，⛔ 不能混用**。

实测两套的差异形态（要认得出来）：

| 检查项 | 口径 A（dreamlet + 供体随机效应） | 口径 B（RUV/glmer 那套） |
|---|---|---|
| 同一格效应量 | logFC = −0.142 | coef = −0.143（**逐行同号同量级，corr 0.61**） |
| 同一格 FDR | 0.712 | **4.6e-235** |
| "显著基因占比" | 27.8%（2,033 / 7,309） | **99.7%（7,289 / 7,309）** |

⇒ **效应量一致而 p 值崩塌 = 自由度 / 独立性口径问题，不是数据问题**（数据坏了效应量也会变）。
⇒ **99% 级别的"显著基因占比"是伪重复的指纹** —— 真实生物学不可能 99.7% 的基因都变。
⚠️ 这与上方「跨方法可比性红线」的**方向偏倚指纹**（43:1 上下调失衡 ⇒ SE 低估）是**两个独立指纹**，
命中任一个都指向检验单位问题，可互相印证。
处理：**两套都摆给用户**，说明哪套可信、为什么，并**主动提示**依赖另一套的下游结论（桑基图 / 共同 DEG）
需要复核；⛔ 不要自己悄悄挑一套了事。

> 完整取证配方（未过滤源表定位、家族匹配代码、两套口径逐格对照数字、汇报表格骨架）→
> `references/single-gene-lookup-and-cross-pipeline-conflict.md`

## 阈值筛选后的结果表交付（多 sheet xlsx；2026-09-29 实测）

用户给出筛选式（如 `fdr<0.05 & abs(coef)>0.25`）后要「**筛出来做成一个表，5 个 sheet 按比较组命名**」时：

- **属线性下游操作 → ⛔ 不辩论，直接做**（用户明确要求「不要什么都辩，该做就直接做」）
- `sheet_name` **从文件名派生**（`merged_<对比组>.xlsx` → sheet 名 = 对比组名），别信表内 `comparison` 列
- sheet 顺序按**生物学逻辑**（Aging → DM → 三组运动），不是字母序；表头冻结；数值列设 `number_format`
- 🔴 **源表的 `direction` 列是组级常量（实测 `nunique()==1`）**，只是"该对比组正向定义"的说明文本 ——
  拿它判逐行上下调会**全错且不报错**（实测 Aging 22,709 up / 469 down，而该列对这 23,178 行是同一个值）。
  ⇒ **必须自己派生 `regulation`（Up/Down，由 coef 符号决定）列**，并在汇报里点明该用哪个列。
  ⇒ 通用判据：**交付任何表前对每列算一次 `nunique()`**，等于 1 的列不能当逐行属性用。
- `fdr`/`p` 显示 **0 = float64 下溢**（<1e-308，实测占 4.2–19.3% 行），**不是缺失** —— 交付说明必须写清
- 导出后**强制 4 条自检**：阈值合规（`all(fdr<cut) & all(|coef|>cut)`）、sheet 数、无空 sheet、
  **行数与上游统计脚本一致**（两处数字打架是本类事故常客）；抽查时 `|coef|min` 应≈0.2499–0.2503
- manifest CSV 记 tested / fdr05 / kept / **kept_unique**（行数与去重基因数两个口径都出）
- 交付目录整洁：用户原话「**把不关 DEG 的图给我去掉，垃圾文件**」⇒ 非主题图移入 `_archive_not_deg/`
  （真删则先记 SHA256 到 log 再删、独立复核"残留 0"）

完整配方（代码骨架 / 逐表实测数字 / 交付目录清理规程 / `rail_review` 误判 `mv` 的处理）
→ `references/deg-threshold-table-export.md`

## 汇报规范

- 先给"统计单位是什么"的自答：group 对比用 donor 级聚合值，donor 是统计单位
- **用户问「要不要加 X / 这个参数行不行」时，先给决定 + 依据，不要先反问**（2026-09-25 用户纠正：
  「我只是想说，要不要加呢？」）。能从数据里实查的事实（meta 有哪些列、batch 是否嵌套、名义 P 分布）
  **自己去查**，把用户当"要结论的人"而不是"提供信息的来源"；只有**真的查不到**（文件在集群、列名不明）
  才问，且问的时候要带上"我查了 A/B/C 都没结论"。
- 交互（group:time）才是卖点，不要只报各组的运动前后 DEG
- 主分析 dream；MAST 作为敏感性分析，两法交集 = 稳健 DEG
- 每对对比单独跑、单独辩论（铁律：不准一次跑完所有对比组）

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | skeletal_muscle | aging | 2026-09-25 | audit_batch_library_MF_L3_meta.py | - | - |  |
| human | skeletal_muscle | aging | 2026-09-25 | audit_deg_tables_5contrasts.py | - | - |  |
| human | skeletal_muscle | aging | 2026-09-25 | audit_deg_signal_diagnostics.py | - | - |  |
| human | skeletal_muscle | aging | 2026-09-25 | shared_term_artifact_calc.py | - | - |  |
