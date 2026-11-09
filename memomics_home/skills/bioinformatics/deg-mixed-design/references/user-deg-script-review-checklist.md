# 用户提供的 RUVr + MAST 逐亚群 DEG 脚本 —— 评审清单

适用：用户丢来一份自己写的 DEG 脚本问「**这代码怎么样 / 综合评价一下**」。
脚本家族（同一骨架反复迭代）：`muscle_RUV_MAST*.R` / `MF_RUV_MAST_RE.R` /
`muscle_RUV_MAST_MuSC.R` + 对应的 `smoke_*.R`。

骨架特征：`COMPARISONS` 列表 × `annotation_L3` 亚群双层循环 → 样本级 pseudo-matrix →
edgeR TMM/GLM → `RUVr` 估 k 个因子 → MAST `zlm`（`glmer` 带 `(1|individual)` 或 `bayesglm`）
→ Wald 提取 `stim` → `p.adjust("fdr")` → 每组合写一个 `*_sDEG.csv`。

> **评审的第一句话永远是：这是「工程加固」还是「结果加固」？**
> 用户会默认「你改了代码 = 结果更可信」，必须当场拆开，否则他会以为重跑就有新结论。

---

## 1. 工程加固 vs 结果加固

| 类型 | 典型改动 | 解决什么 | **不**解决什么 |
|---|---|---|---|
| 工程加固 | 外层 `tryCatch`、`errors.log`、`component` 列、`n_samples` 列、显式 `pkg::fun()` | 不中断、可追溯、不静默错列 | **产出量不变、统计有效性不变** |
| 结果加固 | `k_actual` 上限、推断单位、BH 的「族」定义、`min_cells`、配对/RE 判定 | 显著数与结论可信度 | 崩溃与续跑 |

**必须主动交代**：只做工程加固的重跑，产出文件数通常**一个都不增加**（见 B3）。

---

## 2. 高频 bug（按「静默程度」降序 —— 越静默越危险）

### B1 主结果与 D 组件自合并 → `coef ≡ coef_D`（v1 真存在，最危险）

```r
main <- if (length(resC)) do.call(rbind, resC) else do.call(rbind, resD)  # resC 空 → main 已是 D
if (length(resD)) main <- merge(main, d[, c("gene","coef","p","fdr")],
                                by = "gene", suffixes = c("", "_D"))      # 再把 D 并一次
```

`resC` 全空时 `main` 本身就是 resD 的结果，二次 merge 后 `coef ≡ coef_D`、`p ≡ p_D`。
**不报错、不告警**，但下游任何「`coef_D` 显著而 `coef` 不显著 = 离散组件特异」的筛选结论全错。

修法：`from_C <- length(resC) > 0`，**只有 `from_C` 为真才并入 D**；`component` 列标 `C`/`D`。
加分：`merge(sort = FALSE)` + merge 后 `main[order(main$p), ]` 重排（否则 merge 打乱 p 排序）。
残留小损失：只取 `gene/coef/p/fdr` 会丢 `se_D/z_D`，不影响主结论但妨碍效应量合并 —— 要说明。

### B2 `next` 不触发 `error=` 处理器 → `errors.log` 只记异常，不记跳过

```r
ok <- tryCatch({ if (!all(grp %in% ...)) { cat("跳过：组别缺失\n"); next } ; ... },
               error = function(e) { writeLines(..., "errors.log", append = TRUE) })
```

`next` 是控制流跳转（不是 condition），**不经过 error handler**。
后果：`errors.log` 里只有真异常；「组别缺失 / 组内样本<2 / 残差 df 不足 / 数据太小」
这些**真正的产出缺口只留在 stdout 日志**。打开 errors.log 会误以为「没失败」。

→ 评审时讲清：**errors.log ≠ 失败清单**，跳过清单要去 stdout 数。
→ `ok <-` 赋值后通常从未被读取（死代码），一并指出。

### B3 断点续跑 + 数据性跳过 = 重跑零新增

```r
if (file.exists(fn)) { cat("跳过", nm, "：已存在\n"); next }
```

配合 B2 的数据性跳过：**重跑 = 已存在跳过 + 数据不足跳过 + 0 新文件**。
所以「加个 tryCatch 再跑一遍」多数情况是**无效劳动**。
要真提产出只能改统计口径（`min_cells` 10→5、放弃某组相关对比），并**另开 outdir 并列比较**，
绝不覆盖已有结果。

### B4 新增一列 → 表头列数变了 → 下游按列序解析错位

`n_samples` 这类「顺手加的可追溯列」让表头 **16 → 17 列**。
交付必须点名「表头变了，下游按列序/列数解析的脚本要同步」。放末尾风险最小，但仍要说。

### B5 `next` 在 `tryCatch` 内是**合法**的 —— 别误判成 bug

`for (...) { tryCatch({ ... next ... }, error = ...) }` 在 R 里**能工作**
（`next` 找的是 LOOP context，会正常 unwind 掉 TRY context）。
不要把它列为 bug；要列的是 B2 那个「跳出不进 errors.log」的后果。

### B6 依赖没进 `library()` 块

`dplyr::recode(...)` 用 `::` 能跑，但 dplyr 没进头部 `library()` —— 与其余包风格不一致，
且是隐式依赖。建议补 `library(dplyr)` 或头部注释声明。

### B7 `errors.log` 落进产物目录

和 `*.csv` 混放，人眼与 glob 都歧义。建议 `log/` 子目录或带时间戳命名。

---

## 3. 统计有效性（不改代码也存在，必须单列）

实测 MuSC（51,227 基因 × 15,810 细胞，6 组，47 样本）：

| 对比 | 显著 / 检出 | 占比 |
|---|---|---|
| zone2 Y_Pre_vs_O_Pre | 5064 / 5742 | **88%** |
| zone2 O_Pre_vs_OD_Pre | 5138 / 5893 | **87%** |
| zone1 O_Pre_vs_O_Post | 5316 / 6734 | 79% |
| zone3 Y_Pre_vs_O_Pre | 11 / 7501 | **0.1%** |

**两头都异常 ⇒ 不是生物学信号，是设计饱和。** 三个机制：

1. **`k_actual = min(nruv, df_resid - 1)` 吃光残差自由度。**
   16 样本 × 2 组 → `df_resid = 5` → `k = 4`：4 个 RUV 因子进 MAST 固定效应 =
   用 5 个残差 df 估 4 个 nuisance 方向 + `stim` → `stim` 的 SE 被系统性压低 → p 偏小。
   日志出现 `!! k 下调 10 → 4` 就是这条的指纹，**当红旗看**。
2. **推断单位 = 细胞**（伪重复）。`(1|individual)` 只吸收个体截距，不修正细胞级伪重复；
   细胞数千而样本 7–10 时 SE 严重低估。
3. **BH 的族 = 每个对比各自的 ~8000 基因**，没有跨对比统一族 ⇒ 多个 `*_sDEG.csv`
   之间的 FDR **不可横向比较**，不能直接拼表排序。

→ 交付口径：**「能不能下生物学结论」与「流程会不会崩」是两件事**，分开说。

---

## 4. 分组列映射（每换数据集都要前置核查）

MuSC 实测：rds 里 `type` 真值是
`Young_normal / Young_normal_Post / Old_normal / Old_normal_Post / Old_diabete / Old_diabete_Post`，
**不是**脚本硬编码的 `Y_Pre / Y_Post / …`。不映射 → `factor(type, levels=短码)` 全 NA →
整批「跳过：组别缺失」但 **退出码 0、零报错**。

⚠️ `dplyr::recode` 未命中值**原样保留、不产生 NA** ⇒ `anyNA()` 守卫抓不到漏映射。
守卫必须写成集合判定：

```r
short_codes <- c("Y_Pre","Y_Post","O_Pre","O_Post","OD_Pre","OD_Post")
if (!all(md$type %in% short_codes))
  stop("type 映射失败：", paste(setdiff(unique(md$type), short_codes), collapse = ", "))
print(table(md$type))    # 映射结果打出来，静默全 NA 一眼可见
```

---

## 5. 产出缺口用**样本表**解释，不要归因到代码

MuSC 30 次 → 15 个 csv。缺口全部由数据解释：

| 亚群 | 可跑 / 5 | 原因 |
|---|---|---|
| zone1 / zone2 | 5 / 5 | 10 Young + 7 Old + 7 OD 达标，满配 |
| CCND2+MuSC | 3 / 5 | OD_Pre 达标样本 = **0** |
| zone3 | 2 / 5 | 某侧达标样本 < 2 |
| dMuSC | 0 / 5 | 达标样本 0–1 |
| lpMuSC | 1/5 → 实出 0 | 2/3 过样本门，但 RUV+RE **残差 df 不足** |

「达标」= 该样本在本亚群内 ≥ `min_cells`(10) 个细胞。
交叉验证：先出「亚群 × 组 的 细胞数 / 原始样本数 / 达标样本数」三张矩阵 +
「比较组 × 亚群 两侧达标对数」表 → 反推应有几个 csv → 与实跑数对齐。
本次 表判 16 / 实出 15 → 差的正是 `lpMuSC Y_Pre_vs_Y_Post`（残差 df）。
**能逐条对上 = 缺口来自数据，不是 bug** —— 这条对照直接堵住「是不是你代码写错了」。

---

## 6. 评审交付骨架

1. 一句话定性：工程加固还是结果加固 + 产出量会不会变。
2. 逐项评价它做的改动（每项给「正确 / 正确但有副作用 / 其实是静默 bug」）。
3. 确认到的问题**按严重度 + 静默程度排序**，给「改法」不只给「问题」。
4. 统计有效性单列（不改代码也存在的那部分）。
5. 建议采纳顺序（采纳 / 何时不必重跑 / 想提产出该改什么 / 下游要同步什么）。

⛔ 不要为「响应评审」而重跑：只做工程加固时重跑产出为 0，先说清再问要不要跑。