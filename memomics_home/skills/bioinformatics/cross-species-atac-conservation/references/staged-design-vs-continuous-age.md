# 离散阶段 vs 连续年龄轴 —— 设计诊断、统计量选择与硬边界

> 触发场景：跨物种/跨条件 age-DA 结果不稳或测不出（"比不过随机"）时，
> 怀疑不是生物学没效应，而是**估计量用错了**；或用户提出"不做连续年龄，改做四个阶段"。
> 2026-09-13 完整核实路径（含实测数字与两个致命坑）。

---

## 一、先诊断：设计到底是连续轴还是离散阶段

枚举唯一的 `(individual, age)` 对。判据：

| 特征 | 连续设计 | 离散阶段设计 |
|---|---|---|
| 年龄取值 | 近似连续、组内分散 | **少数几个离散值**，组内高度聚集 |
| 组内方差 | 有 | **可能为 0**（如 4 只猴全是 5 岁） |
| 每阶段独立个体 | — | **≥4**（才够做阶段间检验） |

**本数据集实测（2026-09-13，逐个体实算）**：

| 阶段 | 人（40 供体） | 猴（21 只，剔 M4 → **20**） |
|---|---|---|
| Young | 20–38 岁 · n=10 | 5,5,5,5 · **n=4**（组内零方差） |
| Middle | 41–55 岁 · n=10 | 10,11,12,10 · **n=4**（M4=10 岁已剔；未剔时 n=5） |
| Old | 65–79 岁 · n=10 | 22,22,22,22,23,23 · n=6 |
| Exceptionally old | 82–89 岁 · n=10 | 28,29,29,29,31,31 · n=6 |

**两侧组名完全相同**（`Young / Middle / Old / Exceptionally old`）→ 严格对齐，可直接做阶段配对比较。这不是"近似对应"。

- 数据源：`E:/专利/human_meta.csv` 的 `age_group`（小写）/ `Age_label` / `Age`；`E:/专利/file/monkey_sample_age.csv` + `monkey_meta.csv` 的 `Age_group`（大写 A）/ `Age` / `Individual`+`individual` 双列。
- ⚠️ **n 必须从磁盘 meta 实算**（`unique(meta[, c("individual","Age","Age_group")])`），禁止凭印象或上一轮记忆。本会话曾口误人侧 n=9，实测为 10。
- ⚠️ 两侧列名大小写不一致，务必先探列名再写代码。

---

## 二、为什么连续回归在此是模型误设

1. **组内零方差**：猴 Young 组 4 只全是 5 岁 → 连续预测变量在该水平无组内变异，
   该组只贡献 1 个有效 x 点却占 4 个观测权重 → **杠杆点**。
2. **非等距**：5 → 11 → 22.5 → 29.5（间隔 6 / 11.5 / 7）。线性斜率由"哪个阶段恰好离群"主导。
3. **线性假设**：衰老通常非线性（后期加速），单一斜率会**稀释**真实效应 → p 值偏大、测不出。

表现：**估计量本身不稳**，而非效应不存在。

---

## 三、如何"实证"估计不稳（最有说服力的一招）

**同一数据、同一方法、重算两次，把两次的逐单元估计值求相关。**

本数据集实测（出自 `E:/专利/M2/V5_INPUT_VERDICT.md` 证据 3）：

| 指标 | 值 |
|---|---|
| 两次独立重算的 tile 级 r 相关 | **0.8906** |
| mean\|Δr\| | 0.1063 |
| max\|Δr\| | **0.611** |
| 下游 A 类数 | 1904 → **2335（+22.6%）** |
| 置换基线偏移 | +604.4 |

> 同一猴侧、同一连续 Pearson，重算一次就平均偏 10%。这是低功效 / 高方差的**直接实测**，
> 比任何"我们觉得不稳"的论证都硬。**凡是"结果不稳"的怀疑，先做这个复算相关性检验。**

---

## 四、🔴 改写致命坑：`Age` → `Age_group`（2026-09-13 R 实测）

把 `age` 从数值列换成阶段列后：

| 写法 | 实测结果 |
|---|---|
| `cor(x, md$Age_group)` | ❌ **报错**：`'y'必需是数值`（R 原文）→ 第一个 tile 就崩 |
| `cor(x, as.numeric(factor(md$Age_group)))` | ☠️ **静默灾难**：`factor()` 默认**字母序** → `Exceptionally old=1, Middle=2, Old=3, Young=4` → **完全反向**，全表 r 符号翻转，q 值照样"显著"，肉眼查不出 |

**正确写法（唯一改动，其余管线一字不动）：**

```r
stage <- factor(md[[AGE]], levels = c("Young","Middle","Old","Exceptionally old"))
age   <- as.numeric(stage)   # 有序 1..4
```

`cor()` / `pt()` / `p.adjust()` 全部照用。`divideN=FALSE`（否则全被过滤）保持不变。

⚠️ **坐标别用「前 3 列」位置法**（2026-09-13 实测修正）：
- TileMatrix 的 `se`：`rowData` 前 3 列**确实**是 chr/start/end（已验证 `20001/20500` 是真坐标）✅
- 但 **peak 级对象**的 `rowData` 是 `seqnames | idx | start | end` —— **第 2 列是 `idx` 不是 `start`**
  → `fr[[2]]` 会把 **idx 静默写进 start 列**，坐标全错却毫无报错 ☠️

统一**按列名取**，两级矩阵都安全：

```r
fr   <- as.data.frame(rowData(se))
pick <- function(c) { h <- intersect(c, colnames(fr)); if (length(h)) h[1] else NA_character_ }
C_CHR <- pick(c("seqnames","chr")); C_ST <- pick("start"); C_EN <- pick("end")
stopifnot(!is.na(C_CHR), !is.na(C_ST), !is.na(C_EN))
```

**自检**：`print(levels(factor(Age_group)))` 若第一项是 `"Exceptionally old"` 就说明没写 levels —— 立刻停。

> 这条比任何统计选择都重要：**它是唯一会产生"看起来正常的错结果"的坑**。

---

## 五、正确的统计量

在**个体级 pseudobulk** 上做**有序趋势检验**：

| ✅ 用 | ❌ 不要用 | 原因 |
|---|---|---|
| 有序码 Pearson（1–4，第 4 节写法）| 普通 ANOVA / Kruskal-Wallis | 丢顺序信息（组序打乱结果一样），3 df 白耗功效 |
| Jonckheere-Terpstra（`clinfun::jonckheere.test`）| 仅 Young vs Old 两组 Wilcoxon | 浪费 Middle / Exceptionally old 一半信息 |
| Cuzick 趋势检验 | 逐细胞检验 | 同一个体的细胞被当独立重复 → 伪重复，假性显著 |
| 有序因子线性对比（linear contrast）| — | — |

趋势检验只要求**秩单调**，不要求线性 → 对"平台期 + 后期加速"更敏感；秩变换抗离群。

⚠️ **`clinfun` 未必已安装**（本地实测 `requireNamespace("clinfun") = FALSE`）。不要默认可用；缺就用下面的手写实现。

### 五之一 🔴 手写 JT：**必须 mid-rank**，否则会伪造出「年龄相关下降」（2026-09-13 R 实测）

log-CPM 化后的稀疏单元有**大量 ties**。**严格版（ties 记 0 =「不支持上升」）会把稀疏单元系统性误判为随年龄下降** —— 这是会产出「方向正确、看着很合理」的假结果的 bug：

| 输入 | 严格版 (ties=0) | mid-rank (ties=0.5) |
|---|---|---|
| **全等**（所有值相同） | **z = −5 假显著** ☠️ | **z = 0** ✅ |
| 完美单调 | +5.00 | +5.00 |
| 随机 | ≈ 0 | ≈ 0（mean J = E[J] = 74） |

```r
jt_mid <- function(X, grp) {          # X: 单元 × 个体；grp: 1..K
  N <- ncol(X); J <- numeric(nrow(X))
  for (i in 1:(N - 1)) for (j in (i + 1):N) {
    if (grp[i] >= grp[j]) next         # 只对「组序号更小的一方」做减 → 循环次数 = 组间配对数
    d <- X[, i] - X[, j]
    J <- J + (d < 0) + 0.5 * (d == 0)  # ★ ties 记 0.5 —— 唯一的关键正确性所在
  }
  J
}
ni <- as.integer(table(grp)); Nn <- sum(ni)
EJ <- (Nn^2 - sum(ni^2)) / 4
VJ <- (Nn^2 * (2*Nn + 3) - sum(ni^2 * (2*ni + 3))) / 72
zJ <- (jt_mid(lcpm, grp) - EJ) / sqrt(VJ)
pJ <- 2 * pnorm(-abs(zJ))
```

性能实测：10 万单元 × 20 个体 ≈ **0.2 s**；30 万单元全量几秒～十几秒，不会成为瓶颈。

**必跑自检**（三条全 ✔ 才可信，尤其第 ③ 条专门抓 ties bug）：

```r
set.seed(1); ni <- c(4,4,6,6); gs <- rep(1:4, ni); Nn <- sum(ni)
EJ <- (Nn^2 - sum(ni^2))/4; VJ <- (Nn^2*(2*Nn+3) - sum(ni^2*(2*ni+3)))/72
Xs <- matrix(rnorm(2000*20), 2000, 20)
cat("① 随机     mean(J)=", round(mean(jt_mid(Xs,gs)),2), " (理论 EJ=", EJ, ")\n")   # ≈ 74
Xp <- matrix(0, 2000, 20); for (k in 1:4) Xp[, gs==k] <- k + matrix(rnorm(2000*ni[k],0,.01), 2000)
cat("② 完美单调 mean(z)=", round(mean((jt_mid(Xp,gs)-EJ)/sqrt(VJ)),2), "\n")          # ≈ +5.00
Xe <- matrix(1, 2000, 20)
cat("③ 全等     mean(z)=", round(mean((jt_mid(Xe,gs)-EJ)/sqrt(VJ)),2), "\n")          # 必须 = 0
```

---

## 六、🔴 硬边界：JT 的"最小可能 p"（小 n 的天花板，先算再许诺）

JT 统计量 U 的零分布**只取决于组大小、与数据无关** → 每组 n 定了，**单个 tile 能达到的最小 p 就定了**：

```
U_max  = Σ_{i<j} nᵢnⱼ = (N² − Σnᵢ²)/2
E[U]   = (N² − Σnᵢ²)/4
Var[U] = [N²(2N+3) − Σ nᵢ²(2nᵢ+3)] / 72
z_max  = (U_max − E[U]) / sqrt(Var[U])
```

| | 猴 n=(4,4,6,6), N=20 | 人 n=(10,10,10,10), N=40 |
|---|---|---|
| U_max | 148 | 600 |
| E[U] | 74 | 300 |
| sd | 14.80 | 41.43 |
| **z_max** | **5.00** | 7.24 |
| **最小双侧 p** | **5.7×10⁻⁷** | 4.4×10⁻¹³ |

**与 BH-FDR 门槛对照**：T 个单元、q<0.1 → 排第一的单元需 `p < 0.1/T`。
T≈3×10⁵ 时门槛 ≈ **3.3×10⁻⁷** —— **猴侧 p 下限（5.7×10⁻⁷）比门槛还大**：即使某 tile 四组排序**完美单调、零错位**，也几乎过不了 FDR。人侧下限低 6 个数量级，无此问题。

> 推论：**猴侧"阶段化后仍 0 显著"是可预期的**，不可读作"阶段化失败"。
> 旁证（磁盘实测）：连续版 `E:/专利/monkey_ageDA_up.csv` / `_down.csv` 均仅 **21 字节 = 光表头** → 猴侧 q<0.1 显著 tile 当前为 **0 个**。

---

## 七、有序检验专用过滤规则（别沿用总量门槛）

连续版常用 `rowSums(cnt) >= 2*ncol(cnt)`（**总量**门槛），它**允许"某组零覆盖"的单元混入** → 趋势被单组驱动。有序趋势检验应改为**每组至少 k 个个体非零**：

```r
g <- as.integer(stage)
MIN_NZ <- 2   # 每组至少这么多个体非零；=1 时趋势由单个体决定；猴侧 Young 仅 n=4，取 3 偏严
keep <- apply(sapply(1:4, function(i) rowSums(cnt[, g == i, drop = FALSE] > 0)),
              1, min) >= MIN_NZ
```

**效率**：先算总量门槛 → 再只在子集上算组覆盖，避免对 5.67M 行 × 20 列做稠密运算；
稀疏矩阵用 `Matrix::rowSums(cnt[idx, g == k, drop = FALSE] > 0)`（比较运算保稀疏）。
```

---

## 八、阶段化**不能**解决什么（诚实边界，必说）

- **不增加信息量**：n 不变（人 40 / 猴 20）。
- 若噪声源于 **ATAC 模态稀疏**（每 tile 读段少）→ 阶段化救不了。
- 若噪声源于 **每阶段个体数少**（4–6）→ 阶段化救不了，且会撞上第 6 节的 p 下限。
- **但它能排除并归因"线性误设"这个噪声源** —— 可检验、可归因，与模态噪声**可区分**。

> 别把"阶段化"说成万能解药。它只消除**模型误设 / 离群杠杆 / 线性违背**这三类；
> 稀疏性与样本量天花板它碰不到。

---

## 九、为什么值得做：判决性价值

| 结果 | 含义 | 对结论 |
|---|---|---|
| 参考侧（猴）阶段化后**测出**稳健年龄效应 | 原连续回归是**模型误设** | 原"参考侧方向不可信"被推翻 → 门控变量可用 |
| **仍测不出** | **数据 / 模态硬限制**，非模型问题 | 结论更硬：参考物种不宜作方向参考是**真实边界** → 结论按"评估方法"定位 |

**两种结果都有价值 → 零风险实验（归因实验）。** 比"说不清是算错还是真没效应"强得多。
交付话术定位：**这是归因实验，不是"救显著性"的手段。**

---

## 十、报告口径（小 n 必须换指标）

| ❌ 别再报 | ✅ 改报 |
|---|---|
| "q<0.1 有几个"（猴侧恒 0，指标失效） | **top-500 / top-2000 单元的方向一致性** + 效应量分位数 |
| 只有 p/q | 效应量 + 方向 + **p 的理论下限**（下限本身就是结果） |

---

## 十一、三角对照（推荐一次跑齐）

同一批单元、同一过滤、同一坐标系下同时出：
1. 连续年龄 Pearson（现状口径）
2. 有序码 Pearson（1–4）
3. 秩基有序趋势（JT / Cuzick）

一致 → 结论稳；分歧 → 分歧本身就是"线性误设 vs 数据分辨率"的判别信息。
**人猴必须同口径双跑**（都 tile 级、同过滤、同检验），否则跨物种比较不成立。

---

## 十二、重算配方（本项目，输入已核实）

| 侧 | ArchRProject | 可用矩阵 | 阶段标签 |
|---|---|---|---|
| 人 | `E:/专利/patent/human_Hf_ATAC_40_clustered.rds`（265,909 细胞） | **TileMatrix** | cellColData **无** individual → 从 `E:/专利/human_meta.csv`（265,909 行，与细胞数逐一对齐）回填 |
| 猴 | `E:/专利/patent/monkey_Hf_ATAC_final.rds`（161,497 细胞） | **TileMatrix** | cellColData **已有** `Age_group`（Young/Middle/Old/Exceptionally old）+ `Age` |

```r
# 个体级 pseudobulk（现有 01_l3_*_ageDA.R 已是此形式）
se  <- getGroupSE(proj, useMatrix="TileMatrix", groupBy=Individual,
                  scaleTo=NULL, divideN=FALSE)   # ⚠️ divideN=FALSE 必加
cnt <- assay(se); keep <- rowSums(cnt) >= 2*ncol(cnt)
lcpm <- log2(t(t(cnt[keep,])/colSums(cnt[keep,])*1e6) + 1)

# 连续（旧）→ 分阶段（新）
#   旧： r <- apply(lcpm, 1, function(x) cor(x, age))
#   新： stage <- as.numeric(factor(md[[AGE]], levels=c("Young","Middle","Old","Exceptionally old")))
#        r     <- apply(lcpm, 1, function(x) cor(x, stage))
```

**⚠️ `M2/*_ageDA_all.csv` 只有 `r/p/q`（连续回归汇总），没有个体级计数 → 无法从中重算。**
必须回到 ArchRProject 重建个体级矩阵。

**传数不传环境（省一趟集群）**：让用户顺手存个体级矩阵，之后可本地换多种检验口径反复验：

```r
saveRDS(se, "Monkey_file/monkey_GroupSE_byIndividual.rds")
```

⚠️ **这个 basename 在本项目已存在两份不同矩阵 —— 引用时必须带目录**（2026-09-13 实测）：

| 位置 | 矩阵 | 维度 |
|---|---|---|
| `P3_L1_data/file/` | **PeakMatrix** | 538,420 × 21 个体（**含 M4，仅 61 细胞**） |
| `Monkey_file/`（新存） | **TileMatrix** | 5,674,190 × 20 个体（M4 已删） |

（旧文件的 ~29MB 是 peak 级；tile 级大一个数量级。）`se` 全程未被子集化 → 存的是**完整 tile 矩阵**，下游可换任意过滤口径本地重算，不必再上集群。

**输出契约**：下游 M3 读 `chr, start, end, r, p, q` → **前 6 列的位置与名字都不能动**，
新增列（`J` / `z` / `p_trend`）追加在后，下游无感。
⚠️ 分阶段后 `r` = 与阶段序号 1..4 的相关 = **有序趋势强度**，不再是连续年龄回归
→ 交付说明里必须显式声明口径变了，否则会被当成同口径做跨代次比较。

**交付风格（本用户）**：用户要的是「**我自己会去确认的**」代码 → 给代码时**必须自带**
① 关键映射行的 `print()`（逐个体核对 stage / score）；② 独立自检块（五之一的三条）；
③ 文末「你核对时看这 N 处」清单，明确标出**唯一会静默出错的位置**。
只给代码不给自检 = 用户无法确认 = 等于没交付。

---

## 十三、ArchR 1.0.3 API 陷阱（本次踩到）

| 想查 | ❌ 错的 | ✅ 对的 |
|---|---|---|
| 项目可用矩阵 | `o@availableMatrices`（**无此 slot**，报错） | `getAvailableMatrices(o)` |
| 找 ArchR 项目文件 | `find -iname "ArchRProject"`（找不到） | 找 `Save-ArchR-Project.rds`，或 `readRDS(rds)` 后 `class(o)` 判定 |

`readRDS()` 得到的可以是**完整 ArchRProject**（含 TileMatrix / cellColData / reducedDims），**不必重建**。

- `getGroupSE()` 产出的 `SummarizedExperiment`，在 `Rscript --vanilla` 下 `readRDS()` 需**先** `library(SummarizedExperiment)`（或 `library(ArchR)`），否则 S4 类定义加载失败：`不存在叫'SummarizedExperiment'这个名称的程序包`。
- 探查类小脚本**一次批量写完再跑**（对象结构 + 个体计数 + 包可用性 + 行为验证塞进同一个脚本），避免多轮同质 probing。

---

## 十四、判决结果（2026-09-13 实跑完成 · 第十一节三角对照的猴侧落地）

第九节提出的「归因实验」已执行完毕。数据：猴侧 `P3_L1_data/file/monkey_GroupSE_byIndividual.rds`
（PeakMatrix，ArchR log 值，538,420 单元 × 20 个体，去 M4），n=(4,4,6,6)。

| 指标 | 连续 Pearson | 阶段 JT | 零假设期望 |
|---|---|---|---|
| p<0.05 | 2,555（**0.47%**） | 2,109（**0.39%**） | **26,921（5%）** |
| q<0.1 | 0 | 0 | — |
| 留一最差（20 次） | 0.894 | **0.937** | — |
| 留一极差 | 0.104 | **0.055** | — |
| 两版方向一致率 / r~z 相关 | 84.8% / 0.89 | | |
| 个体深度 vs 年龄 | rho=−0.154, p=0.516 → **无混淆** ✅ | | |

**判决**：
1. **阶段化确实更稳**（留一极差减半、最差 0.894→0.937）→ 承认「模型误设」贡献了一部分噪声。
2. **但没解决根本问题**：两版 q<0.1 均为 0，显著数都只有期望的 1/10。
3. → 指向**数据硬限制**而非方法不当。L1 辩论裁决 `support`，`confidence=medium`
   （missing：批次/性别/组成协变量、marker overlap 验证、效应量 power 模拟、独立猴群复现）。
4. 与第六节的 p 下限推论**互相印证**：猴侧 0 显著是可预期的，不可读作「阶段化失败」。

**交付话术升级**：把「猴不宜作方向参考」从「我们算不出来」升级为
「**已排除线性误设这一解释**」——这是归因实验的产出，价值高于显著性本身。

---

## 十五、🔴 诊断：显著数**远低于**零假设期望 5% = 检验保守，不是「无信号」

**这是本次最容易被误读的信号，务必先诊断再下结论。** 零假设下 p 应均匀，p<0.05 占比应 ≈5%。
实测 0.47%/0.39%（期望 5%）**不是「效应弱」的正常表现——正常无效应时应恰好 5%**。

先跑：

```r
sd(statistic) / theoretical_sd          # <1 = 统计量被收缩 → p 值系统性保守
```

| 口径 | 实测 sd | 理论 sd | 比值 |
|---|---|---|---|
| 连续 Pearson | 0.141 | 1/√18 = 0.236 | **0.60×** |
| 阶段 JT | 0.619 | 1 | **0.62×** |

辅证：p 值中位 0.67 / 0.64（应 ≈0.5）。

**机制定位（一步到位）**：

```r
pca <- prcomp(t(X[1:2000, ]), center = TRUE, scale. = FALSE)   # ★ 取行，X 是 单元×个体
summary(pca)$importance[2, 1]                                  # PC1 解释率 = 93.8%
cor(pca$x[, 1], age, method = "spearman")                      # PC1~年龄 rho = 0.162（不显著）
```

PC1 解释率 93.8% 且与年龄无关 → 主变异是**技术性共同成分**，
所有单元共享同一个个体排序形状 → 每个单元的年龄相关被挤进同一条窄带
→ 统计量 sd 收缩 → 显著数只有期望的 1/10。**换检验方法碰不到这一层。**

> ⚠️ **专利/论文限制栏必须写**：显著数 ≪5% 说明**现有 p 值口径不可靠**，
> 「测不出」≠「证明无效应」。正确表述 = 「现有数据与口径下检测不到，**且检验校准异常已定位**」。
> 漏掉这句 = 把保守检验当成阴性证据，是可被审查员一击的漏洞。

---

## 十六、R 陷阱：`rank()` 不接受矩阵（会卡死超时）

```r
rank(t(Z))   # ✗ Z 为 20×538420 时，rank 把矩阵 unlist 成 1.07 亿元素做【全局】排序
             #   → 既不是逐行秩（Spearman 需行内秩），又触发超大排序 + 内存交换 → 3600s 超时
```
逐行秩正确写法：`matrixStats::rowRanks(Z)` 或 `t(apply(Z, 1, rank))`。
**最优解：根本不要秩矩阵** —— 有序趋势统计量用 JT（纯公式 + 向量化），无任何排名步骤。
（本次即因误用 `rank(t(Z))` 触发 `R execution timed out after 3600s`。）

---

## 十七、拿到矩阵先判量纲（四件套，防整条判据静默跑偏）

```r
cat(dim(M), "\n"); print(range(colSums(M))); print(range(M)); print(all(M == round(M)))
```

| 观察 | 结论 | 过滤判据 |
|---|---|---|
| `colSums` 大、整数、值域 0–上万 | 原始 counts | `rowSums(cnt) >= 2*ncol(cnt)` ✅ |
| `colSums` ≈ scaleTo（默认 1e6） | 已归一化 | 上述判据**失效** |
| 值域 0–4、非整数、`colSums` ~10³–10⁴ | **ArchR log 值（已是 log2CPM+1）** | 改 `rowSums(M > 0) >= 2`；**且不可再做 log 转换** |

实测佐证：在归一化矩阵上误用总量判据 → 538,420 单元 **只剩 16 个**。

**运行产物（可复用，勿重跑）**：
`results/memomics-7839e23a/scripts/stage_vs_cont_monkey_peak.R`、
`results/stage_vs_cont_monkey_peak.rds`（含 20 次留一矩阵）、
`figures/stage_vs_cont_monkey_peaks.png`（4 面板：p 值分布 / 统计量收缩 / 留一稳定性 / 方向一致率）。
