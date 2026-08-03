---
name: cross-species-atac-conservation
description: >
  纯 ATAC-seq 跨物种 CRE 保守性定量评估方法（专利方案）。
  三层递进：L1 序列保守 → L2 染色质可及性保守 → L3 TF 结合动态保守。
  核心创新：B 类 CRE 检出（序列+可及性保守，但 TF 足迹分歧）。
  不需要 RNA/Hi-C/ChIP——纯 ATAC 数据即可运行完整评估。
  触发词：跨物种 CRE / ATAC 保守性 / CRE 可代替性 / 调控元件保守性评估 /
  cross-species ATAC / enhancer conservation / B类CRE / CRECS
trigger_level: RED 必触发
version: 1.0.0
---

# 跨物种 ATAC CRE 保守性评估（纯 ATAC）

## 一句话定位

用两个物种的 ATAC-seq 数据，定量评估每个调控元件（CRE）在物种间的保守程度，
输出 A/B/C/D 四级分类。**不需要 RNA-seq**。

## 三层评估框架

```
L1 序列保守性（不需要 ATAC 测序数据）
  ├─ liftover 坐标映射（rheMac10 → hg38）
  ├─ phastCons/phyloP 保守性分数
  └─ JASPAR motif 有无/位置/拷贝数比较
  输出: S_seq ∈ [0,1]

L2 染色质可及性保守性（需要两个物种的 ATAC）
  ├─ peak overlap: liftOver + Jaccard 指数
  ├─ 信号强度: Spearman ρ
  ├─ 细胞类型特异性可及性一致性
  └─ 衰老动态: species×age 混合效应模型 🔑
  输出: S_acc ∈ [0,1]

L3 TF 结合动态保守性（需要两个物种的 ATAC）
  ├─ TF footprinting 跨物种比较（HINT-ATAC / TOBIAS）
  ├─ 衰老变化中富集 motif 一致性
  └─ TF 结合强度衰老轨迹比较
  输出: S_tf ∈ [0,1]
```

## B 类 CRE —— 核心创新

```
A 类: S_seq 高 + S_acc 高 + S_tf 高 → ✅ 完全保守
B 类: S_seq 高 + S_acc 高 + S_tf 低 → 🔴 隐形炸弹！
      序列和染色质都保守，但 TF 结合模式不同。
      纯序列方法（phastCons/GERP）看不到 B 类。
      本方法是第一个能检出 B 类的方法。
C 类: S_seq 高 + S_acc 低 → 序列保守但不可及
D 类: S_seq 低 → 序列不保守
```

## 专利框架

- **独权**：三层递进整合（序列+可及性+TF结合）→ CRECS 综合评分 → A/B/C/D 分类
- **从权 2-4**：收窄物种/组织/统计方法
- **从权 5-6**：进化锚点校准法确定权重和阈值
- **从权 7**：输出形式（热图+分类标签）
- **从权 8**：细胞类型特异性评估
- **从权 9-10**：留口子——RNA 增强层、Hi-C 增强层（不做但从权里占位）

## A25 防御五锚点

| 锚点 | 防御逻辑 |
|------|---------|
| 数据绑定物理结构 | ATAC-seq peak 矩阵来自高通量测序仪的物理测量 |
| CRE 是分子实体 | 每个 CRE 对应基因组具体坐标，可实验验证 |
| 计算机不可省略 | 23万细胞×10万CRE×混合效应模型→人脑无法手动完成 |
| 产业技术效果 | 输出 B 类 CRE 清单→避免猴模型转化失败 |
| 错误检测机制 | 细胞类型锚定验证：跨物种细胞类型无法对齐→标记"仅供参考" |

## BNIP3 验证设计

- BNIP3 HRE 位点（-94bp）：人-小鼠已验证保守，人-猴首次比较
- 预期：三层全保守 → A 类
- 负对照：选已知灵长类调控分歧的 CRE → 预期判 B 类
- 一正一反验证方法的区分度

## 数据需求

| # | 数据 | 来源 | 用途 |
|---|------|------|------|
| 1 | 猴海马 ATAC-seq | 用户自有 | L2+L3 |
| 2 | 人海马 ATAC-seq | ENCODE/GEO 下载 | L2+L3 |
| 3 | 基因组序列+liftover链 | UCSC | L1 |
| 4 | phastCons/phyloP | UCSC | L1 |
| 5 | JASPAR motif | JASPAR | L1+L3 |

> 📍 **项目实时状态**（猴侧已完成/人侧下载进度/续跑路径）→ `references/project-status-human-dataset.md`
> 人海马 ATAC 选定数据集 = GSE278576（Science 2026，40 样本），用户手动下载中。

### 🔴 数据粒度匹配教训（2026-08-02 用户质疑"为什么给我亚群的ATAC"）

**猴侧是 region-level**：Arrow 文件名 `Y3_Hip_1/O1_Hip_1/Hip_2...` = 海马亚区（CA1/DG/CA2-CA3）水平的样本，不是细胞类型分选的。

**人侧 GSE278576 的文件命名有两种粒度，选错会直接不匹配**：
- ✅ **region×age 粒度**：`GSE278576_ATAC_CA1_age20-40.bw` / `_CA1_age60-80.bw`（= 亚区 × 年龄组）→ **与猴侧 Hip_1/2 匹配**，这是首选
- ⚠️ **cell-type 粒度**：`GSE278576_ATAC_Astro.bw` / `_Microglia.bw` / `_Oligo.bw`（= 全脑区按细胞类型分层）→ 与猴 region-level 粒度**不匹配**，只能用于"某细胞类型特异 CRE"的专项比较，不能直接做全 CRE 保守性评估

**教训**：给用户推荐下载文件前，先核对两侧数据的**生物学粒度**（region vs cell-type vs sample）是否对齐。用户数据是 region-level 就推荐 region×age 文件，不要默认推 cell-type 分层文件。GSE278576 完整 92 个 ATAC .bw 中优先下 `_CA1_/DG_/CA2-CA3_` 开头的 region×age 文件（每个 100-350MB），cell-type 文件留作从权/专项。

### 🔴 bw vs fragments：L3 footprinting 需要 fragment 级数据（2026-08-02 数据决策教训）

**用户问"fragments 要不要下载？bw 是什么东西？"——两者用途不同，决定专利能覆盖到哪一层：**

| 数据类型 | 是什么 | 能做 | 不能做 | 对应专利层 |
|---------|--------|------|--------|-----------|
| **bigWig (.bw)** | 聚合信号轨道（按细胞类型/年龄组） | peak 比较、信号强度、差异可及性、L2 | **TF footprinting** | **L2 可及性保守（独权核心）** |
| **fragments.tsv.gz** | 单细胞原始片段 | L2 + **真 footprinting（L3）** | — | **L3 TF 结合保守（从权/实施例）** |

**决策规则**：
- 目标=方法验证/拿受理 → bw 够用（L2 是独权核心）
- 目标=专利实施例完整（含 footprinting 实证）→ 必须补 fragments（2 年轻 + 2 老年 ≈ 10GB 即可 pilot）
- L3 若只有 bw → 只能用 motif 富集做**代理**（预测），审查员可能质疑"无实测证据"
- fragments 在 GSM 级不在 GSE 级（详见 public-data-download skill）

### 🔴 年龄组数量：2 组=方向，4 组=轨迹（2026-08-02 用户问"不需要40到60吗"）

**用户问"不需要 40-60 吗？"——正确答案取决于分析设计：**

| 设计 | 年龄组 | 能算什么 | 专利价值 |
|------|--------|---------|---------|
| 快速验证（Y vs O） | 2 组（20-40 + 60-80） | log2FC、方向 | 方法验证足够 |
| **完整专利实施例** | **4 组全要**（20-40/40-60/60-80/80-100） | species×age 交互、年龄轨迹、S335 年龄等效变换 | **独权核心 S340 混合效应模型需要≥3 个年龄点** |

**教训**：专利核心是"衰老动态的跨物种保守性"，混合效应模型 `accessibility ~ species + age + species:age` 需要连续年龄梯度。只下 2 个年龄组 → 猴侧 4 组（Y/M/O/V）浪费一半 + 审查时"只比较 2 个年龄点"被认为不充分。**分两批下：先 2 组跑通方法，再补全 4 组做完整轨迹。**

### 🔴 GSE278576 文件命名语义（用户多次困惑"这是什么"）

```
GSE278576_ATAC_CA1.bw              = 海马CA1亚区·全年龄合并
GSE278576_ATAC_CA1_age20-40.bw     = 海马CA1亚区·20-40岁组   ← 带 age = 做衰老对比用这个
GSE278576_ATAC_Astro.bw            = 星形胶质细胞·全年龄合并（cell-type 粒度）
GSE278576_ATAC_Astro_age60-80.bw   = 星形胶质细胞·60-80岁组
```

**海马解剖亚区（给不熟脑区的用户解释）**：CA1/CA2-CA3 = 锥体神经元区（海马角），DG = 齿状回（成体神经发生地，衰老中新生下降），SUB = 下托（海马输出枢纽）。海马信息流单向：DG→CA3→CA2→CA1→SUB。**这些亚区文件就是海马数据**——用户把"海马亚区命名"误读成"非海马脑区"，要主动解释清楚。

### 🔴 CRECS 权重必须数据驱动 — 为什么固定数字不能进独权（2026-08-02 用户追问"0.20 怎么来的"）

**用户问"CRECS = 0.20×序列 + 0.35×表观 + ... 里 0.2/0.35 怎么来的？"——诚实答案是"当时是拍的"。** 这在专利里是致命的：

```
审查员的标准动作：
"权利要求中的权重 0.20, 0.35 是如何确定的？"
→ "经验设定的" → A25 驳回（智力活动规则，主观判断）
→ "训练数据优化的" → 追问"什么训练数据？如何保证泛化？"
```

**铁律**：
- **固定权重数字永远不进独权**（授权后被人轻易绕开 + 审查阶段被驳回）
- 独权写法：`S500: 整合各层得分，通过进化锚点校准方法确定权重系数`（只写方法，不写数字）
- 权重确定方法进从权：**进化锚点校准法**（逻辑回归）—— 选取≥3 对已知进化距离的物种对（人-黑猩猩 600万年/人-恒河猴 2500万年/人-小鼠 9000万年），以各层得分为特征、已知保守性为标签训练可解释线性模型，系数归一化 = 权重
- **为什么是逻辑回归不是深度学习**：逻辑回归每个权重对应一个维度、可解释 → 审查员看得懂 → 可进独权；深度学习=黑盒 → 和 ESM-2 同理只能进从权
- **标签来源**：进化距离自动标注（大数据量）+ MPRA/STARR-seq 功能验证做验证集（小数据量但精确），证明模型预测与真实功能保守性一致

### 🔴 BNIP3 是靶基因不是 TF — motif 富集不会出现它（2026-08-02 用户问"有发现BINP6吗"）

**用户问"motif 富集结果里有 BNIP3 吗？"——正确回答是：BNIP3 是被调控的靶基因，不是转录因子，不会出现在 motif 富集里。** Motif 富集找的是"哪些 TF 的 DNA 结合序列在 DA 区域过头出现"。

正确排查链：
1. **查它的上游 TF**：BNIP3 已知受 HIF-1α/E2F1/FOXO3/p53 调控。motif 富集里看这些 TF——本会话实测 ARNT2（HIF-1β 同源，Old FC=3.50）出现了，暗示 HIF 通路在猴脑衰老中激活
2. **查 DA tiles 落在 BNIP3 附近**：下载猕猴 T2T 基因注释 GTF → 把 50+60 个 DA tiles 映射到最近基因 → 看 BNIP3 ±500kb 内有无 DA tile
3. **直接验证**：用 HIF1A/ARNT 的 JASPAR motif 在 DA tiles 上单独做 motif scanning（不是富集，是直接验证）

**这个区分（靶基因 vs TF）在跨物种 CRE 专利里很重要**：专利 L3 层证明的是"TF 结合模式是否保守"，靶基因（如 BNIP3）是 L2/L4 的验证对象，不是 L3 的输入。

## 工具链

| 层 | 工具 | 环境 |
|----|------|------|
| L1 | UCSC liftOver, phastCons, JASPAR API | Shell/Python |
| L2 | ArchR (peak calling, 差异可及性, mixed model) | R 4.6.1 |
| L3 | HINT-ATAC / TOBIAS (footprinting) | Python |
| 整合 | 逻辑回归（进化锚点校准）| Python/R |

## 项目结构

```
results/atac-cross-species/
├── data/               # 下载的人ATAC + 猴ATAC
├── archr/               # ArchR Arrow 文件
├── L1_sequence/         # liftover + phastCons 结果
├── L2_accessibility/    # peak overlap + 信号 + 衰老动态
├── L3_footprinting/     # TF footprinting 跨物种
├── L4_integration/      # CRECS 综合评分 + A/B/C/D 分类
├── figures/
├── patent/              # 交底书 + 独权草案
└── log/
```
---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="ATAC-seq 分析 —— {样本}",
     context="方法: {ArchR/Signac} | 参数: {peak calling参数} | 结果: {n} peaks {m} motifs",
     knowledge_base_info=<KB内容>,
   )
   辩论: peak质量如何？FRiP分数？motif富集合理吗？与RNA数据一致吗？
3. save_conclusions(module="03_advanced", topic="ATAC", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```
