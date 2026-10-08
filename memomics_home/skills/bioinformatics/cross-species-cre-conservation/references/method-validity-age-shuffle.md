# 年龄标签 Shuffle（协变量置换检验）完整配方

检验「年龄效应是否真实」的置换检验——不同于「打乱 ortholog 配对」的置换检验。后者验跨物种同向性是否随机，前者验年龄↔可及性关联本身是否真实。两者互补，专利方法有效性论证缺一不可。

## 何时用

- 任何「协变量（年龄/疾病/剂量/时间）× 特征（tile/peak/基因）」的效应量需要证明「真信号 vs 技术/批次假象」时。
- 尤其当评分器（如 S 评分）的输入是「从样本级矩阵算出的逐特征效应量 r/Z」，需要证明这些 r/Z 不是年龄标签偶然排列产生。

## sparse 向量化 Pearson 相关（核心配方）

样本×feature 矩阵 M（dgCMatrix，n 样本 × T feature），年龄向量 age（n 维连续值）：

```r
library(Matrix)
M <- as(m, "dgCMatrix")          # 确保 sparse（n x T）
n <- nrow(M)
a <- age - mean(age)             # 中心化年龄
sx  <- colSums(M)                # 每 feature sum(x)
sx2 <- colSums(M * M)            # 每 feature sum(x²)；M*M 仍 sparse
denom <- sqrt((sx2 - sx^2/n) * sum(a^2))  # pearson 分母：cov 归一化
r_true <- as.vector(a %*% M) / denom      # 分子 = sum(x_i·a_i)，一次 sparse 乘向量
r_true[!is.finite(r_true)] <- 0  # var_x=0 的 feature（全零）相关无定义 → 置 0
```

推导：`cov(x,age) = sum(x_i·a_i)/n`（因 mean(a)=0）；`r = sum(x_i·a_i) / sqrt(sum((x−x̄)²)·sum(a²))`。`denom` 与 age 的**排序无关**（sum(a²) 在 permutation 下不变），故 shuffle 检验时 **denom 复用**，只重算分子，速度快。

```r
set.seed(42); Nperm <- 200; thr <- 0.5
obs <- sum(abs(r_true) > thr)
null <- numeric(Nperm)
for (i in 1:Nperm) {
  rp <- as.vector(sample(a) %*% M) / denom   # 只重算分子
  rp[!is.finite(rp)] <- 0
  null[i] <- sum(abs(rp) > thr)
}
p_emp <- mean(null >= obs)                    # 经验 p（单尾：真实 ≥ null）
cat("真实", obs, "null均值", mean(null), "比值", obs/mean(null), "p", p_emp)
```

**统计量选型**：用「|r|>阈值的 feature 数」最直观（可直接对照真实 vs null），也可用「|r| 的方差」「|r| 的 95% 分位」。阈值 r 的显著性界：n=20 样本时 |r|>0.5 ≈ p<0.024。

## 人猴海马实测（2026-09-04，供对照）

| 物种 | 粒度 | 真实 \|r\|>0.5 | null 均值(±sd) | 比值 | 经验 p | 结论 |
|---|---|---|---|---|---|---|
| 人 | peak 级（52.5 万 × 40 样本）| 6285 | 258.4(±1075) | **24.3×** | 0.005 | 年龄效应真实 |
| 猴 | 全 tile 级（608 万 × 20 样本）| 34128 | 147794(±233596) | 0.23× | 0.815 | ⚠️ 弱于随机（粒度错配，见下）|

## 必须警惕的粒度陷阱

猴侧全 tile 级 shuffle 显示「真实弱于 null」，**不代表猴侧年龄效应必然为假**——S 评分用的粒度是「启动子近端 TSS±2kb + Stouffer 聚合」的**基因级**效应，而全 tile 级（6M tile）含海量基因间/荒漠 tile，年龄信号被稀释到弱于 null。null sd（±233596）远超均值，说明 null 分布不稳、估计不可靠。

**正确流程**：先确认评分器在哪个粒度算 Z（tile / peak / 聚合后基因），再在**同一粒度**做 shuffle。粒度不一致的「真实<null」只能下「该粒度被稀释」的结论，必须回到原粒度复验。

## 数据覆盖度预检（shuffle 前必做，排除稀疏污染）

shuffle 前先查每 feature 有读数的样本数分布，确认「稀疏 tile 污染」不是「真实<null」的原因：

```r
nnz <- diff(M@p)          # dgCMatrix 每列非零数 = 每 feature 有读数的样本数
quantile(nnz, c(0, .25, .5, .75, .9, .99, 1))
mean(nnz >= 5)            # 覆盖度足够的 feature 占比
```

猴侧实测 91.75% tile ≥5 样本（覆盖度不低），排除了「大量荒漠 tile 污染」的假设 → 猴侧「真实<null」不是稀疏导致的数值假象，而是样本量（20）+ 年龄簇（4 簇：5/10-12/22-23/28-31 岁）导致的功效不足或真粒度错配。判断 key：先看 `mean(nnz>=5)` 是否足够高，再决定往哪个方向排查。

## 关联脚本/产物（本会话）

- `scripts/v8_age_shuffle.R`（或 execute_r 内联）→ `P3_L1_data/v8_age_shuffle_stats.rds`
- `scripts/v7_extrapolation_baseline.py` → `P3_L1_data/v7_extrapolation_baseline.json`（外推公式 + A/B baseline 对比）
- `scripts/v9_A_class_CRE_coords.py` → `P3_L1_data/v9_A_class_CRE_coords.csv`（402 A 级 chr:start-end 坐标对）