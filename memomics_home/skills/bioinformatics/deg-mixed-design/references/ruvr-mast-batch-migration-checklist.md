# 逐亚群 RUVr+MAST 脚本「换一个数据集再跑」迁移清单

**触发**：用户手里已有一份跑通的 `RUVr + MAST` 逐亚群 DEG 脚本（`for celltype × for comparison` 双层循环），
现在给一个**新组织/新对象**的 rds，说「**就按这个代码替换一下，建个子目录，先探索数据再运行**」。

**核心判断：不要直接改路径就投。** 同一份脚本换数据集会踩的坑，按下面顺序核 —— 每一条都验过、都静默失败过。

---

## 0. 顺序（别反）：探测 → 定可跑组合 → 冒烟 → 全量

```
① 只读探测（读一次 rds 打表）→ ② 决定哪些 亚群 × 比较组 可跑 → ③ 冒烟（1 亚群 × 1 对比）→ ④ 全量 submit
```

实测锚点（同一份脚本，两个数据集）：

| 数据集 | 规模 | 亚群 | 组合 | 可跑 | 实出 |
|---|---|---|---|---|---|
| MuSC | 51227 × 15810 | 6 | 30 | 16 | **15** |
| Immune | 35896 × 19934 | 17 | 85 | **57** | 57（进行中） |

差的那 1 个是「过样本门但残差 df 不足」—— 所以**可跑数 ≠ 实出数，允许 −1 并主动解释**。

---

## 1. 换数据集必须逐项核的 5 件事

| # | 项 | 为什么必须实测 | MuSC 实测 | Immune 实测 |
|---|---|---|---|---|
| 1 | **分组列真实取值** | 可能是长名也可能已是短码，脚本 `factor(levels=)` 对不上就整批 NA → 全部「组别缺失」`exit=0` | `Young_normal` / `Old_diabete_Post`（需 recode） | **已是短码** `Y_Pre…OD_Post`（recode 原样保留） |
| 2 | **个体列在不在** | 不在才从 `samplename` 去 `_Pre/_Post` 推；在就直接用真实个体 | 无 `individual` → 推断得 24 | **有 `individual`** → 直接用（24） |
| 3 | **`counts` 层还在不在** | 做过 SCTransform 的对象 RNA assay 通常仍有 counts，但**必须实测**；缺层则 RUVr/MAST 全废 | RNA 有 counts | `[assays] RNA \| SCT` + `[layers] RNA: counts \| data` ✅ |
| 4 | **注释列名** | `annotation_L3` 不一定存在；列名不同整批 `sort(unique())` 得到 NA | `annotation_L3` | `annotation_L3`（17 类） |
| 5 | **输出前缀 / outdir** | 沿用旧前缀会与上一批结果混在一起 | `muscle_` | 改 `immune_` + `outdir="Immune"` |

### 1.1 `counts` 层守卫（读入即检，缺层 20 秒内停，别白跑一小时）

```r
muscle_rds <- readRDS(rds_path)
DefaultAssay(muscle_rds) <- "RNA"
cat("[assays]", paste(names(muscle_rds@assays), collapse = " | "), "\n")
rna_layers <- tryCatch(SeuratObject::Layers(muscle_rds[["RNA"]]),
                       error = function(e) names(muscle_rds[["RNA"]]@layers))
cat("[layers] RNA:", paste(rna_layers, collapse = " | "), "\n")
if (!"counts" %in% rna_layers)
  stop("RNA assay 缺 counts 层，现有层：", paste(rna_layers, collapse = ", "))
```

### 1.2 分组列映射：`recode` 未命中不报错，守卫必须用 `%in%`

```r
md$type <- dplyr::recode(as.character(md$type), "Young_normal" = "Y_Pre", ... )
short <- c("Y_Pre","Y_Post","O_Pre","O_Post","OD_Pre","OD_Post")
if (!all(md$type %in% short))            # ⛔ 不是 anyNA() —— recode 未命中会原样保留，不产生 NA
  stop("type 映射失败：", paste(setdiff(unique(md$type), short), collapse = ", "))
cat("[map] type 映射后取值：\n"); print(table(md$type))
```

⚠️ factor 里可能挂**计数为 0 的幽灵水平**（Immune 的 `Veryold` = 0 细胞）。`as.character()` 不带出来，
`table()` 会显示 0 —— 看到 0 就是安全的；**若有细胞，重设 `levels=` 时会静默变 NA**。

---

## 2. 探测脚本必出的四张表（口径与 DEG 脚本逐字对齐）

`min_cells`（本题 10）的口径：**达标样本 = 该样本在本亚群内 ≥ min_cells 个细胞**。

1. 亚群 × 组 **细胞数**
2. 亚群 × 组 **原始样本数**（该组有 ≥1 细胞）—— ⚠️ 常被误当可跑性依据
3. 亚群 × 组 **达标样本数** ← **唯一决定能不能跑**
4. 比较组 × 亚群 **两侧达标数 `n1/n2`**，`n1≥2 && n2≥2` 才可跑

落 4 个 csv + stdout 报告；**结论一句：「N 个组合中 M 个可跑，预计产出 M 个 sDEG.csv」** ——
先把这个数字告给用户，别等跑完再解释缺口。

---

## 3. 探测脚本自身的两个坑

| 症状 | 根因 | 修法 |
|---|---|---|
| `Error in cat(..., "\n", sep = "") : formal argument "sep" matched by multiple actual arguments` | 自定义 `CAT <- function(...) cat(..., "\n", sep="")` 里已固定 `sep`，调用处又传一次 `CAT(..., sep="")` | `CAT <- function(...) cat(..., "\n")`，调用处**不再**传 `sep` |
| `table()` 里出现计划外的水平 / 全 NA | 探测里套了 `factor(levels=预期短码)` | 探测阶段**一律 `as.character()`** 打原值，映射留到正式脚本 |

---

## 4. 冒烟版怎么切（2 行）

```r
celltypes <- head(celltypes, 1)          # 只跑第一个亚群
for (nm in names(COMPARISONS)[1]) {      # 只跑第一个对比
```

→ 1 亚群 × 1 对比，1–2 分钟出结果，验证：counts 层 / `type` 映射 / 配对 RE / `edgeR::cpm` 命名空间 / 写盘权限。
**首轮崩溃 1 分钟内暴露，远比全量跑几十轮后才发现省事。**

冒烟验收信号（Immune 实测）：`[meta] 细胞 19934 | 样本 47 | 个体 24 | 亚群 17` →
`[subset] 5705 基因 × 215 细胞 | 无RE` → `!! k 下调 10 → 7` → `[parallel] 16 核 | 12 块` → `OK | 基因 …`。

---

## 5. 全量投递后：一次早期核对，然后停手

```bash
ps -ef | grep -E '<脚本名>' | grep -v grep
tail -25 <工作盘>/<out>.log
ls <产物目录> | head
```

要点（都是实测）：
- `submit` 返回 `exit=124 / Command timed out after 20s` **但会带 PID** = **作业已经起来了**，不要判失败。
- **R 进程刚起时日志必然空、产物目录还没建** —— 因为 `library(Seurat) + MAST + lme4 + RUVSeq` 要二三十秒。
  此时 `ls` 报 `No such file or directory` **不代表脚本没跑**；看 `ps` 的 CPU 时间在涨即可。
- 日志出现正常进度行（`[layers] RNA:` / `[subset]` / `[MAST]` / `OK |`）→ **停止轮询**；见到 `Error` / `halted` → 立刻定位。
- 之后只在**用户问起**时再查一次（连发同类监控命令会被判循环失控）。

---

## 6. 结果判读：显著率异常先当报警信号

Immune 首批 3 个 csv 出来后，仍要按 `deg-mixed-design` 的判读表核：某对比 **70–90%** 基因 `fdr<0.05`
而另一对比只有 0.1% ⇒ 方差失控（`k` 饱和 / 组间细胞数失衡 / 细胞级伪重复），**不是生物学**。

日志里两个必看的 `!!`：`!! k 下调 10 → N`（`k_actual = min(nruv, df_resid-1)`，样本少时 RUV 因子吃满残差）
与 `!! 配对不完整 (3/7) → 不加 RE`（`(1|individual)` 降级为 `bayesglm`）。
两者都要落成结果列（`nRUV_used` / `method`），否则下游无法区分口径。