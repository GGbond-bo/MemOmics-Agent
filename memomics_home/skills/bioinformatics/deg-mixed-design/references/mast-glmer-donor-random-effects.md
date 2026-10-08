# 细胞级 MAST + 样本/供体随机效应（glmer）——可跑骨架与三个伪装型报错

> 2026-09-26 实测于真实数据（人骨骼肌，24 供体 / 48 样本 / 6 条件 / 10 亚群）
> 环境：R 4.5.3 + MAST 1.32.0 + lme4 2.0.6（MAST 从 R 4.4.2 用户库借用可用）
> 配套：`deg-mixed-design` §方案 C、`references/celllevel-inference-unit-and-sample-structure.md`

## 什么时候用这一页

需要**细胞级** MAST（而非 pseudobulk）做主/敏感性 DEG，且**同一供体贡献多细胞**。
先读「层次选型判据」——红线只有一条：**样本层变异必须进模型**，机制任选
（pseudobulk / `(1|subject)` / RUV-SVA 因子协变量 / pseudobulk 残差协变量）。
本页解决「选了 `(1|subject)` 这条」之后怎么落地。

---

## 一、可跑骨架

```r
suppressPackageStartupMessages({ library(Seurat); library(Matrix); library(MAST); library(lme4) })

## ① 取一个亚群 × 一个对比的 counts
X  <- LayerData(obj, assay = "RNA", layer = "counts")[, idx]   # 基因 × 细胞
m  <- md[idx, , drop = FALSE]
m$stim       <- as.numeric(as.character(m$type) == grp[2])     # 0/1 数值 → 系数名就叫 stim
m$individual <- factor(as.character(m$individual))             # ★ 必须存在且为 factor

## ② 基因过滤（检出率）+ 控计算量（glmer 慢，按总表达量取 top-N）
pct <- Matrix::rowSums(X > 0) / ncol(X)
X   <- X[names(pct)[pct > pctcut], , drop = FALSE]             # pctcut 常用 0.1
X   <- X[order(Matrix::rowSums(X), decreasing = TRUE)[1:max_genes], , drop = FALSE]

## ③ 控计算量：限每供体细胞数（无偏 —— 同供体内细胞可交换）
kc <- unlist(lapply(split(seq_len(ncol(X)), m$individual),
                    function(ix) if (length(ix) > max_cpd) sample(ix, max_cpd) else ix))
X  <- X[, kc]; m <- m[kc, ]

## ④ ★★ cData 必须含公式里【全部】变量 —— 见坑 1
covmat <- data.frame(stim = m$stim, row.names = colnames(X))
covmat$individual <- factor(as.character(m$individual))        # ← 缺这行会报假错误
covmat$wellKey    <- colnames(X)

## ⑤ log2(CPM+1)（MAST 连续部分要正态化表达量；CPM 分母用【全基因集】colSums，保证 chunk 间可比）
csm  <- Matrix::colSums(X)
norm <- log(sweep(as.matrix(X), 2, csm / 10000, "/") + 1)

sca <- MAST::FromMatrix(norm, cData = covmat,
         fData = data.frame(primerid = rownames(X), row.names = rownames(X)),
         check_sanity = TRUE)

## ⑥ 拟合：glmer + 随机截距；ebayes=FALSE（glmer 下不适用）
fit <- MAST::zlm(~ stim + (1 | individual), sca, method = "glmer", ebayes = FALSE, silent = TRUE)
```

---

## 二、三个伪装型报错（都极难定位，务必按此处理）

### 坑 1 ★ 最阴：cData 缺随机效应变量 → 报错伪装成 sca 类型问题

**现象**：
```
`sca` must inherit from `data.frame` or `SingleCellAssay`
```
公式没问题、`sca` 确实是 `SingleCellAssay`，但那行实际在抱怨 **cData 里找不到 `individual`**。

**根因**：照搬官方代码用 `model.matrix()` **预先展开固定效应**当 cData。NHPABC 原文的公式是
纯固定效应（`~ stim + W_1..W_5`），所以能这么写；一旦公式含 `(1|individual)`，
`individual` 就不在 cData 里 → MAST 内部取变量失败 → 异常类型不匹配被当成 sca 类型问题抛出。

```r
## ❌ 错（原文写法，公式有 RE 时必炸）
covmat <- data.frame(model.matrix(as.formula(paste("~ stim +", paste(wvars, collapse=" + "))), data = pathdf))
covmat$wellKey <- rownames(pathdf)

## ✅ 对：传【原始变量】，让 zlm 自己建设计矩阵
covmat <- data.frame(stim = pathdf$stim, row.names = rownames(pathdf))
for (w in wvars) covmat[[w]] <- pathdf[[w]]
if (use_re) covmat$individual <- factor(as.character(pathdf$individual))
covmat$wellKey <- rownames(pathdf)
stopifnot(all(c("stim", wvars) %in% names(covmat)))
if (use_re) stopifnot("individual" %in% names(covmat))   # ← 兜底断言
```

### 坑 2：glmer 下 **不能用** `summary(zlm.obj, doLRT=...)` 取结果

- `MAST::CoefficientHypothesis` **未被导出** → `waldTest` 这条路不通
- `coef()` / `vcov()` 是 **S4 泛型**，**绝不能加 `MAST::` 前缀**（报 `'coef' is not an exported object from 'namespace:MAST'`），
  `library(MAST)` 后直接裸调用即可分派
- ⇒ 改用 **`coef(fit, comp)` + `vcov(fit, comp)` 手算 Wald**（更可控，且不依赖内部导出）

```r
waldFromZlm <- function(fit, comp) {            # comp ∈ "C"(表达量) | "D"(检出率)
  cc <- tryCatch(coef(fit, comp), error = function(e) e)   # ★ 裸泛型，勿加 MAST::
  if (inherits(cc, "error")) return(list(err = paste("coef:", conditionMessage(cc))))
  vv <- tryCatch(vcov(fit, comp), error = function(e) e)
  if (inherits(vv, "error")) return(list(err = paste("vcov:", conditionMessage(vv))))
  cn <- colnames(cc); j <- grep("^stim", cn)
  if (!length(j)) return(list(err = paste("无 stim 系数:", paste(cn, collapse = ","))))
  j <- j[1]
  ## ★ vcov 维度实测为 (系数, 系数, 基因) —— 自动判定方向，两种都兼容
  orient <- if (length(intersect(dimnames(vv)[[3]], rownames(cc))) > 0.5 * nrow(cc)) "ccg" else "gcc"
  se <- vapply(seq_len(nrow(cc)), function(i) {
    Vi <- if (orient == "ccg") matrix(vv[j, j, i], 1) else matrix(vv[i, j, j], 1)
    sqrt(as.numeric(Vi))
  }, numeric(1))
  est <- cc[, j]
  ok  <- !is.na(est) & !is.na(se)               # ★ 见坑 3，NA 必须剔除并留痕
  data.frame(gene = rownames(cc)[ok], coef = est[ok], se = se[ok],
             z = est[ok] / se[ok], p = 2 * pnorm(-abs(est[ok] / se[ok])),
             n_na_gene = sum(!ok), row.names = NULL)
}
```

### 坑 3：D 组件（检出率）会有 NA —— 是数据特性，不是 bug

glmer 在二值响应上遇**完全分离**（某基因在某条件下近乎全 0 或全 1）时无法估计 → NA。
实测：D 组件 **16/40 基因 NA（40%）**；**C 组件 0 NA**。
⇒ 必须 `ok <- !is.na(est) & !is.na(se)` 过滤并**把 `n_na_gene` 写进输出/日志**
（静默输出 NA 行 = 下游 `sum(fdr<0.05)` 得到 NA，看不出原因）。

---

## 三、实测性能与对照（用于估算集群时间）

| 指标 | 实测值 |
|---|---|
| glmer 速度 | **0.13 s/基因** → 3000 基因约 **6.6 min**（每对比 × 每亚群） |
| 组件可取性 | C 与 D 均可取（`coef` 40×2 `[(Intercept),stim]`；`vcov` 2×2×40） |
| vcov 维度 | **(系数, 系数, 基因)** —— 与上面 `orient` 判定一致 |
| RE vs 无 RE 的 coef 相关 | **0.964**（高度一致 → 加 RE 不改变格局，主要改 SE/合法性） |
| SE 中位 | RE **0.050** vs 无 RE 0.052 |

⇒ **时间估算公式**：`6.6 min × 对比数 × 亚群数`（10 亚群 × 7 对比 ≈ 7.7 h，需分批/后台）。
降采样与限基因数**只损失功效、不引入偏倚**（同供体内细胞可交换）。

---

## 四、与 RUV 配合（配对设计必读）

RUV 的 design **也要放供体**，否则 RUVr 会把供体效应当 unwanted variation 吸收，
再叠加 `(1|individual)` 就是两者争抢同一份方差（表现为「加了 RE 反而更差」）。

- **配对比较** → RUV design `~stim + individual`（残差不再含供体效应）
- **组间比较** → `individual` 完全嵌套在 `stim` 内 ⇒ **秩亏** ⇒ 必须检测回退：

```r
rk <- qr(design)$rank
if (rk < ncol(design)) {            # 秩亏 → 回退并【写日志留痕】
  LOG("RUV design 秩亏 → 回退到 ~", pathvars[1])
  pathvars <- pathvars[1]; design <- model.matrix(asform(c("~", pathvars)), data = uqobs)
  if (qr(design)$rank < ncol(design)) stop("design 仍秩亏，请检查分组")
}
```

- `RUVr` 官方签名（RUVSeq 手册核实）：`RUVr(x, cIdx, k, residuals, center, round, …)`；
  `cIdx` 传**全基因**是 vignette 惯例（RUVr 靠残差找因子），
  `RUVr(counts, rownames(counts), k=nruv, res1)` 的位置参数匹配**正确**。
- RUV 用的 pseudobulk **只为估因子**，检验仍在细胞级 —— 别把它的输出当检验输入。

---

## 五、结果解读口径（写论文前必读）

1. **细胞级 n 是细胞数**，比 pseudobulk 的 n=样本数 大得多 ⇒ 灵敏度高、p 值可能偏乐观。
   与 pseudobulk 结果做**方向一致性交叉验证**，并在 methods 里说明推断单位。
2. **C（表达量）与 D（检出率）是两个不同的量** —— `D` 算的是 log-odds，**不能混着说「上调」**。
3. 双方法**同时为零**（如某对比在 pseudobulk 与 MAST 下都 0 显著）是一个**稳健的阴性结论**，
   比单方法可信，可以写「未检出差异表达信号」（但加上功效限定，别写「无差异」）。
4. 加 RE 后 **coef 与无 RE 版本高度相关（实测 0.964）** ⇒ 结论方向通常不变，
   改变的是**统计合法性与 SE**。别把「加了 RE」讲成「结论变了」，也别因为数值几乎没变就怀疑 RE 没生效
   （用 SE / p / 显著数分布证明生效）。