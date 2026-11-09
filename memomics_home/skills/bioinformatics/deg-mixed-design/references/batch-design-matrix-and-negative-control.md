# 批次能不能进 DEG 模型：设计矩阵算术 + 批次负对照

> 来源：2026-11-02 会话（Immune / MuSC 运动队列，24 个体 × Pre/Post × 4 个建库批次）。
> 用户原话：「这是完整的批次，麻烦你带入代码，进行测试一下……**测试之前先给我看你改了什么**」。
>
> **结论先行**：批次不是「加不加协变量」的选择题，而是一道**算术题**——
> 先算「组×批次非空格数 vs 参数个数」，余 df<1 就没有任何讨论空间。
> 本例 **Aging 比较余 df = 0**（批次根本放不进去），Diabetes 余 df = 1（等价饱和），
> 三个配对比较**无需加**（被随机效应完整吸收）。
>
> 姊妹文档：`references/ruv-k-selection-batch-and-covariates.md`（k 怎么定 / RUV 与已知批次的分工 /
> 协变量预算表）。本文只讲「批次这个变量本身能不能进模型，以及放不进去时怎么办」。

---

## §0 触发场景

用户给出一张 `Batch × Sample` 对照表，要求「把批次带进 DEG 代码里」。
**⛔ 不要直接把它当协变量塞进公式然后投作业。** 先做下面三步判定，否则会
① 设计矩阵秩亏静默降级、② 跑完才发现批次被分组完全决定、③ 白烧一小时算力。

---

## §1 三步判定：交叉表 → 算术 → 结论

### 第 1 步：个体级 `batch × 分组` 交叉表

⚠️ **必须用「个体级」而不是「样本级」**：同一人 Pre/Post 通常同批次，
样本级表会把每个个体数两遍，掩盖真实的批次分布。

```r
ind <- unique(S[, c("individual","grp","batch")])
print(table(ind$grp, ind$batch))
```

### 第 2 步：按比较组分别算「非空格数 vs 参数个数」

**这是整篇文档的核心。** 对每个比较组（只取参与该比较的两个组、只取该时点）：

```
非空格数 = 组×批次 交叉表里 count > 0 的格子数
参数个数 = 1(截距) + (组数−1) + (批次水平数−1)
余 df    = 非空格数 − 参数个数
```

| 余 df | 判定 | 动作 |
|---:|---|---|
| **< 1** | 🔴 设计饱和 / 秩亏 | **拒绝入模**，标记 `batch_confounded = TRUE` |
| 1–2 | ⚠️ 勉强可估 | 可入模但必须打警告，结果解释力极弱 |
| ≥ 3 | ✅ 可入模 | 正常加入 |

**为什么是「非空格数」而不是「样本数」**：批次是样本级常数，它在设计矩阵里
只贡献「组×批次」这个交互层级的自由度。10 个样本落在 3 个格子里，也只提供 3 个格子的信息。

### 第 3 步：算该比较组自己的 Cramér's V

```r
ct <- table(d$grp, d$batch)
cs <- chisq.test(ct); v <- sqrt(as.numeric(cs$statistic) / (sum(ct) * (min(dim(ct)) - 1)))
# V > 0.8 = 强共线
```

---

## §2 实测数据（48 样本、24 个体、3 组、4 批次）

个体级 `batch × 分组`：

| 分组 | batch 1 | batch 2 | batch 3 | batch 4 | 个体数 |
|---|---:|---:|---:|---:|---:|
| Young（Y） | 2 | 4 | 4 | **0** | 10 |
| Old 对照（O） | **0** | 1 | **0** | **6** | 7 |
| Old 糖尿病（OD） | 2 | 2 | 0 | 3 | 7 |

**一眼可见的不平衡**：老年对照组 6/7 落在 batch 4，而青年组 10/10 全在 batch 1/2/3，
batch 4 一个青年都没有。

### 按比较组算出来的结果

| 比较 | 组×批次非空格 | 参数 | 余 df | 该比较组 Cramér's V | 判定 |
|---|---:|---:|---:|---:|---|
| **Aging（Y_pre vs O_pre）** | 5 | 5 | **0** | **0.90** | ❌ 完全不能入模 |
| **Diabetes（O_pre vs OD_pre）** | 5 | 4 | **1** | — | ⚠️ 勉强，等价饱和 |
| 三个配对比较 | — | — | — | — | ✅ 无需（见 §3） |

### 🔴 全局 V 会骗人

对全部 3 组算总 Cramér's V 只有 **0.586**（因为 OD 组横跨 batch 1/2/4，摊薄了）。
**只看全局 V 会误判「共线性不严重」**。必须按比较组分别算 —— Aging 单算就是 **0.90**。

⇒ 规则：**共线性永远在「实际要跑的那个比较」的层面上评估，不在全数据集层面评估。**

---

## §3 配对设计天然吸收批次（关键澄清，纠正一个常见误判）

早期担心「Pre/Post 分批建库 ⇒ 处理效应与批次效应不可分离」。**实测推翻了这个担心（对配对比较而言）**：

```r
for (g in c("Y","O","OD")) {
  d <- S[S$grp == g, ]
  same <- tapply(as.character(d$batch), d$individual, function(x) length(unique(x)))
  cat(g, "每个个体内部 batch 数 =", paste(sort(unique(same)), collapse=","), "\n")
}
# 输出：全部为 1  ⇒ Pre 与 Post 恒在同批次
```

**同一人的 Pre 与 Post 落在同一个 batch** ⇒ 批次在个体内是常数 ⇒
被 `(1|individual)` **完整吸收** ⇒ 配对比较**根本不需要**再加 batch
（加了反而与随机效应共线）。

### 真正的混杂在「跨组比较」里

| 设计 | 批次状态 | 动作 |
|---|---|---|
| 配对（Pre vs Post） | 个体内恒定，被 RE 吸收 | ✅ 不加 |
| 跨组（Y vs O、O vs OD） | 个体间不同，且常与分组共线 | ⚠️ 先过 §1 算术，多半加不进去 |

---

## §4 加不进去时的三条出路（按推荐度排序）

### 出路 1（首选）：批次负对照 —— 判定「信号到底是不是批次」

**这是把「加不进去」转化为「可判定」的关键设计。**

把 batch 当成**假分组**，在同一个 type 集合内部跑完全相同的 RUVr + MAST 流程，
看**纯批次差异**能造出多大比例的显著基因。

```r
# 在 Young 内部比 batch 2 vs batch 3（4 个体 vs 4 个体，最均衡）
BATCH_CONTRASTS <- list(
  Y_b2_vs_b3  = list(types = c("Y_Pre","Y_Post"),   b1 = 2, b2 = 3),
  Y_b1_vs_b2  = list(types = c("Y_Pre","Y_Post"),   b1 = 1, b2 = 2),
  Y_b1_vs_b3  = list(types = c("Y_Pre","Y_Post"),   b1 = 1, b2 = 3),
  OD_b1_vs_b2 = list(types = c("OD_Pre","OD_Post"), b1 = 1, b2 = 2),
  OD_b2_vs_b4 = list(types = c("OD_Pre","OD_Post"), b1 = 2, b2 = 4))
# stim = as.numeric(batch == b2)；不加 RE（两侧是不同个体）
```

**判读表**：

| 负对照结果 | 推论 |
|---|---|
| 也出现 60–80% 单向显著 | 🔴 **真实分组效应主体就是批次**，该比较组的 DEG 不可用 |
| 显著率 0.1–5%、双向混合 | ✅ 批次影响可控，真实分组结果可信 |

选对照的原则：**两组个体数尽量均衡**（4v4 远好于 2v4；1v6 不要用）。

### 出路 2：限制在共同批次内做敏感性分析

```r
# 只保留两组都有样本的批次水平
common <- intersect(unique(b1$batch), unique(b2$batch))
```
本例 Aging 的共同批次只有 batch 2（4 青年 vs 1 老年）⇒ 样本太少，不可行。
**先查共同批次里有几个个体，再决定要不要走这条路。**

### 出路 3：换 pseudobulk

批次的样本级变异在 pseudobulk 里可以被「批次作随机效应」或 limma 的
`duplicateCorrelation(block = batch)` 吸收 —— 因为那时 n = 样本数，设计不再挤在
「组×批次」5 个格子里。**这也是为什么跨组比较遇到批次共线时，默认答案就是换框架。**

---

## §5 可复用函数：`batchModelable()`

放进正式脚本，跑前打印判定结果，避免人工判断漂移：

```r
## 返回 usable / reason / df_left / warn
batchModelable <- function(smp_batch, smp_grp, grp_levels){
  ok <- !is.na(smp_batch) & smp_grp %in% grp_levels
  b <- as.character(smp_batch[ok]); g <- as.character(smp_grp[ok])
  if (length(unique(b)) < 2)
    return(list(usable = FALSE, reason = "批次水平 <2", df_left = NA))

  ct       <- table(g, b)
  n_per_grp <- apply(ct, 1, function(x) sum(x > 0))   # 每组占几个批次水平
  n_cells   <- sum(ct > 0)                            # 非空格数
  n_params  <- 1 + (length(unique(g)) - 1) + (length(unique(b)) - 1)
  df_left   <- n_cells - n_params

  # 某组只出现在 1 个批次水平 且 设计饱和 ⇒ 完全共线
  if (any(n_per_grp < 2) && n_cells <= n_params)
    return(list(usable = FALSE, df_left = df_left,
                reason = sprintf("批次与分组共线（组内水平 %s，非空格 %d ≤ 参数 %d）",
                                 paste(n_per_grp, collapse = "/"), n_cells, n_params)))
  if (df_left < 1)
    return(list(usable = FALSE, df_left = df_left,
                reason = sprintf("设计饱和（非空格 %d，参数 %d，剩 %d df）",
                                 n_cells, n_params, df_left)))
  if (df_left < 3)
    return(list(usable = TRUE, warn = TRUE, df_left = df_left,
                reason = sprintf("可入模但残差仅 %d df", df_left)))
  list(usable = TRUE, warn = FALSE, df_left = df_left,
       reason = sprintf("可入模（组内批次 %s，剩 %d df）",
                        paste(n_per_grp, collapse = "/"), df_left))
}
```

**必须落成结果列**（否则下游无法区分口径）：
`batch_used` / `batch_reason` / `n_batch_lv` / `df_resid`。

---

## §6 批次表本身要先对账（这一步最容易出错）

拿到批次表第一件事不是改代码，是**核对它和对象里的样本名能不能对上**：

| 检查 | 命令 | 实测教训 |
|---|---|---|
| 表里有几个样本 | `nrow(batch_tab)` | 用户第一次给的表只有 64 个文库（覆盖 16 个体），第二次补全才 96 文库 / 48 样本 |
| 命名格式是否一致 | 连字符 `Y16-1-1` vs 下划线 `Y16_1_1` | 旧脚本是按 library 匹配的，直接漏掉一半 |
| 合并键选哪个 | **按 `samplename` 合并**，不要按 `library` | `samplename` 才是分组/配对的单位；`library` 是一样本多文库 |
| 未命中数量 | `sum(is.na(md$batch))` | 必须打印；静默 NA 会让后面整组被跳过 |

### 🔴 「O」前缀不代表正常老年

实测该数据集里存在**两套老年个体命名**：

- `Old_1C` / `Old_2C` / `Old_4C` …（带 **C** 后缀）= 老年**对照**组
- `Old_2` / `Old_4` / `Old_5` …（无后缀）= 老年**糖尿病**组

⇒ **分组一律以对象里的 `type` 列为准，绝不从样本名推断**。
样本名只用来推个体（`sub("_(Pre|Post)$", "", samplename)`）。

---

## §7 用户偏好（本类任务的交付方式）

**改分析脚本前，先给「改了什么」的对照，再跑。**

用户原话：**「测试之前先给我看你改了什么」**。落地形式：

1. 逐条列 `v3 → v4` 的改动，每条附**代码片段前后对照**（不是「我加入了批次支持」这种概述）；
2. 每条说清**为什么改**（对应哪个已确认的问题）；
3. 改动若引出一个「结论会变」的发现（如本例"批次根本加不进去"），**放在改动清单之前**先说；
4. 此时作业可以已经在后台跑 —— 但**结论性发现必须先讲**，不要让用户等跑完才知道方向错了。

⚠️ 反面：直接把脚本改完投作业，跑完再汇报 ⇒ 用户会认为你在瞎跑。

---

## §8 坑

| 症状 | 根因 | 修法 |
|---|---|---|
| 全局 Cramér's V 看着不高（0.59），单个比较组却强共线（0.90） | 多组摊薄 | 按比较组分别算 |
| `table(grp, batch)` 每格都非空，就以为能加 | 该表是**样本级**（每人两行）而非个体级 | 先 `unique(individual)` 再去重 |
| 加了 batch 后 `glmer` 不收敛 / 系数 NA | 配对设计里 batch 与 individual 共线 | 配对比较直接不加 |
| 把 `Region` 这类别的组织才有的分层变量名照抄过来 | 变量名当成了通用概念 | 抽象成「与分组不平衡的已知技术分层变量」，再找本数据对应列 |
| terminal 里 `cat > x.R <<'EOF' ... EOF` 报「uses '&' backgrounding」 | heredoc 正文里含 `&` | 改用 `write_file` 落脚本，`terminal` 只负责执行 |

---

## §9 一句话速查

| 追问 | 一句话答 |
|---|---|
| 「把批次加进模型吧？」 | 先算 `非空格 − 参数`；余 df<1 就是不能加，先把算术结果给用户看 |
| 「配对还要加批次吗？」 | 不要 —— 同一人 Pre/Post 同批次时被 `(1|individual)` 完整吸收 |
| 「加不进去那怎么办？」 | 跑**批次负对照**（组内 batch A vs batch B），用纯批次的显著率去判定真实结果是否可用 |
| 「批次影响到底多大？」 | 看负对照的双向显著率：60–80% 单向 ⇒ 批次主导；0.1–5% 双向 ⇒ 可控 |