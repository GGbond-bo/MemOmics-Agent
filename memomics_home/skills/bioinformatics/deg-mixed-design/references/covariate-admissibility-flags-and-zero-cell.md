# 协变量准入判定与「混杂标记列」交付法（batch / 用药 / Sex / Age 四类实证）

> 2026-11-02/03 实测（Immune 免疫细胞 19,934 cells / 47 samplename / 24 individual / 17 个 L3 亚群）。
> 前置阅读：`references/covariate-availability-preflight.md`（三门预检）、
> `references/batch-design-matrix-and-negative-control.md`（批次负对照）。
> 本篇补的是**拿到完整表之后**那一段：完整表把问题从「覆盖不足」换成了「设计饱和」，
> 以及四类协变量各自的**不可识别原因**与**如何把这些判定交付出去**。

---

## 一、完整表到手 ≠ 能加：设计矩阵饱和算术

用户补齐 48 行批次表后（24 个体全覆盖、batch 1–4），覆盖率问题消失，但**Aging 仍然加不了**。
判据不是覆盖率，是一条减法：

```
非空格数 n_cells = 表里 (组 × 批次) 中 >0 的格子数
参数个数 n_params = 1(截距) + (组数−1) + (批次数−1)
剩余自由度 df_left = n_cells − n_params
        df_left < 1  → 不可入模（模型饱和，系数不可估）
        df_left < 3  → 可入模但警告（残差太小，SE 会被压低）
```

实测：

| 比较 | 非空格 | 参数 | 余 df | 判定 |
|---|---:|---:|---:|---|
| **Aging（Y_Pre vs O_Pre）** | 5 | 5 | **0** | ❌ 完全不能加 |
| **Diabetes（O_Pre vs OD_Pre）** | 5 | 4 | **1** | ⚠️ 等价饱和 |
| 三个配对比较 | — | — | — | ✅ 无需加 |

结构成因：Y 组 10/10 全在 batch 1/2/3、**batch4 一个都没有**；O 组 7 个体里 6 个在 batch4。
⇒ **「年龄差 40 岁」与「换一个建库批次」在这份数据里数学上不可分离**。这不是代码能修的，
只能在 Limitations 里声明，或做「batch2 内部 Y vs O（8 vs 2）」的敏感性分析（样本太少，只看向，不出结论）。

### ⚠️ Cramer's V 有两种口径，报**更保守**的那个

| 口径 | 值 | 说明 |
|---|---:|---|
| 样本级（47 行） | **0.898** | 看着极强，但样本数与细胞数不成比例时会虚高 |
| **个体级（24 行，生物学重复）** | **0.580**（χ² p=1.888e-05） | ✅ **论文/汇报应报这个** |

同一次分析两个口径都算得出来，早期我报了 0.898、后来实测个体级是 0.580 —— 主动更正并说明
「两种口径都对，但个体级才是生物学重复单位」。⛔ 别让读者以为你在挑数字好看的那个。

---

## 二、用药（medication）：四层不可辨识，逐层都要有实值证据

用户会直接问「用药要不要校正」。**先算交叉表，再开口**，并且把四层分开讲——
因为每一层的性质不同，混在一起讲会显得像借口。

### 第 1 层 · 配对比较：用了也白用

```
个体内 Medication 发生变化的个体数: 0 / 24
```

24 个个体 Pre/Post 用药**完全没变** ⇒ 在 `(1|individual)` 下是组内常量，被随机效应整份吸收。
再加进模型只会与 RE 争抢方差、导致 `glmer` 不收敛。
⚠️ 反过来要检查：**若有人在 Pre/Post 之间换过药**，它立刻变成随时间变化的真混杂，必须建模。
这个检查必须实测（`aggregate(med ~ individual)` 比 Pre/Post 两行），不能假定"吃药是长期的事"。

### 第 2 层 · 独立比较遇零格：**模型直接崩，而这个崩溃就是证据**

```
O_Pre  (n=7): 未用药 1 / 用药 6
OD_Pre (n=7): 未用药 0 / 用药 7     ← 零格
```

`table()` 在一个方向没有观测时**不会返回 0 列**，而是少一列，于是 `t[, "no"]` 报
`subscript out of bounds` —— 我第一次跑就是这样崩的。**这个崩溃本身是最有力的证据**：
零格 = 设计矩阵奇异 = 系数不可估。

修法（跑通并让判定可读）：

```r
# ✅ 强制保留两个水平，零格显式变成 0
tt <- table(factor(grp,  levels = c(g1, g2)),
            factor(med,  levels = c("no", "yes")))
med_confounded <- any(tt == 0)     # 零格 → 不可辨识
```

而且这类零格**不是巧合**：OD = `Old_diabetes`，糖尿病本身就是靠降糖药定义的（降糖药命中 6/7）。
「校正药物效应」在这里等于「校正掉糖尿病本身」—— **药物是疾病的下游中介，不是可分离的混杂**。
这一句要直接告诉用户，它比任何统计论证都清楚。

### 第 3 层 · 只是"没有零格"，仍然不可信

Y vs O：未用药 Y=7 / O=**1**。零格没有，但「用药系数」实际由**单个样本**（Old_5C）决定，
换个样本系数就翻 —— 这比不加更危险。判据不是"有没有零格"，而是"每格能不能撑起一个系数"。

### 第 4 层 · 语义不可比（最容易被忽略，但要讲）

探针把「用药=yes」两侧摊开看：

| 组 | 用药者实值 |
|---|---|
| Young | Fluoxetin（抗抑郁）／Metformin+口服避孕药／**肌酸、乳清蛋白、咖啡因（全是补剂）** |
| Old | 他汀、降压药、甲状腺素、维生素 D |
| OD | Metformin / Ozempic / Jardiance / Synjardy / Actos / Eucreas |

把「19 岁吃肌酸」和「78 岁吃四种降压+降糖药」合并成同一个二元协变量，系数没有任何生物学解释。
⇒ **即使用户要求"加进去看看"，也要先说明这一层**；否则出来的系数无法写进论文。

---

## 三、Sex / Age：两个"看起来该加"的经典陷阱

| 变量 | 实测 | 处置 |
|---|---|---|
| **Sex** | 48/48 全 Female，唯一值 = 1 | **零变异，绝不能进模型**（`contrasts` 直接报错或产生 NA 系数） |
| **Age** | Y: 18–21 / O: 61–83 / OD: 68–78 | 与分组定义**完全共线**（Y≤21 vs 老年≥61）⇒ 加进去必奇异；要谈年龄梯度只能用组内比较或连续建模 |

预检一行就能发现：`length(unique(na.omit(df$Sex)))`、`tapply(Age, grp, range)`。
⛔ 不要因为"性别/年龄是标准协变量"就默认加。

---

## 四、交付法：把判定写成结果表的**标记列**，而不是删结果

用户要的是"全部比较组都跑完"。做法是**照跑，但每张表自带混杂标记**，让下游能筛：

```r
confoundFlags <- function(one, grp1, grp2, is_paired){
  # one = 样本级唯一行（每 Sample 一行），含 grp / med_use / batch / individual
  # 🔴 is_paired 必须从调用方传进来（= 这一轮到底加没加 (1|individual)），
  #    两种设计的判定口径完全不同，用一套会漏判（见 §四bis）
  med_flag <- NA; med_reason <- "无用药信息"; n_changed <- NA_integer_
  if (is_paired) {
    # 配对：判「个体内有没有人换过药」—— 零变化 ⇒ 被 (1|individual) 完全吸收
    pr <- unique(one[, c("individual","grp","med_use")])
    tb <- table(pr$individual, pr$grp)
    both <- rownames(tb)[rowSums(tb > 0) == 2]        # 两侧都有的个体
    n_changed <- sum(vapply(both, function(id)
                   length(unique(as.character(pr$med_use[pr$individual == id]))) > 1,
                   logical(1)))
    med_flag <- n_changed < 2
  } else {
    # 独立：零格 **或** 最小格 <2 都不可估
    tt <- table(factor(one$grp, levels = c(grp1, grp2)),
                factor(one$med_use, levels = c("no","yes")))   # 强制保留两列
    med_flag <- any(tt == 0) || min(tt) < 2
  }
  # 批次：个体级 Cramer's V > 0.8 或某组只落在单一批次
  ctb <- table(one$grp, one$batch); v <- cramers_v(ctb)
  bt_flag <- (v > 0.8) || any(apply(ctb, 1, function(x) sum(x > 0)) < 2)
  list(med_confounded = med_flag, med_detail = "...", med_pair_n_changed = n_changed,
       batch_confounded = bt_flag, batch_detail = sprintf("V=%.3f 组内批次数 %s", v, n_per))
}
```

结果表新增四列：`med_confounded` / `med_detail` / `batch_confounded` / `batch_detail`
（detail 写**人可读的实值**，如 `O_Pre(yes=6/no=1); OD_Pre(yes=7/no=0) → 零格，用药不可入模`）。
另落一张 `medication_x_group_sample.csv`（用药×分组交叉表）供审计。

四条纪律：
1. **模型公式不因标记而改变** —— 标记是诊断，不是校正；改了公式就成了另一个分析，必须整批重跑。
2. **不要因为混杂就删掉该比较组**：用户要的是全量；判读时对着负对照水位说"这条可信度低"即可。
3. **配对比较的 batch 标记应为"被 RE 吸收"而不是"共线不可用"** —— 两者结论相反，别写错。
4. 换诊断列 ⇒ **输出文件名换版本后缀**（`_v4.csv` → `_v5.csv`），让断点续跑与旧结果互不干扰。

---

## 四bis、🔴 口径陷阱：**零格判据在配对设计里永远不会报警**（v5 → v6 实证，最值得记的一条）

第一版标记函数（上面 §四 的旧写法）**只用「2×2 零格」判用药**。配对比较直接漏判：

```
Y_Pre  (n=10)：yes=3 / no=7
Y_Post (n=10)：yes=3 / no=7      ← 两侧都非空 ⇒ any(tt == 0) == FALSE ⇒ 判"无零格，可辨识"
真实情况：24/24 个体 Pre/Post 用药零变化 ⇒ 被 (1|individual) 完全吸收 ⇒ 完全不可辨识
```

**根因不是数字算错，是判据选错**：`table(组, 用药)` 抹掉了「同一个体两行是否一致」这个维度。
配对设计里真正该问的是「**组内有没有人换过药**」，不是「组间有没有空格子」。

| 设计 | 正确的不可辨识判据 | 用错会怎样 |
|---|---|---|
| **配对**（加了 `(1\|individual)`） | 个体内 med_use **变化数** < 2 | 永远报"可辨识"，把 0/24 的彻底不可辨识说成没问题 |
| **独立**（无 RE） | 2×2 **零格** 或 **最小格 <2** | 只判零格 → O 组仅 1 人未用药（Old_5C）时被判"可辨识"，其实系数由单样本决定 |

⇒ **标记函数必须接受 `is_paired` 参数并分支**，且这个参数要从「本轮到底加没加 RE」的判定结果直接传进去
（本例 `use_re_here`），**不要在函数里另猜一遍**——两处逻辑一旦分叉，标记和模型就对不上。

交付上多一列 **`med_pair_n_changed`**（组内用药发生变化的个体数）。它是审稿人一问就能给答案的那个数：
`0` = 完全不可辨识；`1` = 由单样本决定；`≥2` 才够估一个系数。

自检三问（改完标记函数必跑）：
1. 三个配对比较里的 `med_confounded` 是不是 **TRUE**？（若全是 FALSE/FALSE，一定是又用了零格口径）
2. 两个独立比较（Y vs O、O vs OD）的 `med_confounded` 是不是 **TRUE**？（O vs OD 有零格必 TRUE）
3. `med_pair_n_changed` 是不是 **0**？三问对不上说明分支没生效。

---

## 五、判读时必须配"假阳性水位"

任何显著基因数都要并排给批次负对照基线（本例纯批次比较 3.6–7.5% vs 真实比较 1.30%）。
没有水位参照的显著基因数，用户无法判断这结果是信号还是批次残留。
详见 `references/batch-design-matrix-and-negative-control.md`。