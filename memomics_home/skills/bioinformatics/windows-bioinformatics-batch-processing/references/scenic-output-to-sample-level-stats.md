# SCENIC 产出 → R 样本级统计：五个静默坑

> 2026-09-24 实测（人骨骼肌 2132 nuclei / 48 样本）。上游 `grn-pyscenic` 为**手工撰写 skill、curation 不可写**，
> 故把这些下游坑记在此处（跑完 SCENIC 进 R 做统计/出图时先扫一眼）。

---

## 0. 两张表的 TF 名**格式不一致**（最容易静默错的地方）

| 文件 | TF 列/列名形态 | 来源 |
|------|----------------|------|
| `regulons.csv` | **裸名**，如 `MAF`、`MEF2C` | `regulon.transcription_factor` |
| `aucell_matrix.csv` | **带修饰**，如 `MAF(+)`、`MEF2C(+)` | regulon 名 |

⇒ **跨文件比对（如"已知萎缩 TF 命中率"）必须先归一化**：`bare <- function(v) sub("\\(.*$", "", v)`
否则 `"MAF" %in% c("MAF(+)")` 恒为 FALSE，命中率虚低到 0。

`regulons.csv` 的列（实测）：`TF, target, weight, regulon_name`。

---

## 1. `as.data.frame()` 默认 `check.names=TRUE` 会改坏 regulon 名

```r
as.data.frame(t(sapply(...)))          # ❌ "MAF(+)" → "MAF..."
as.data.frame(t(sapply(...)), check.names = FALSE)   # ✅
```
后果：后续 `samp_all[[tf]]`（tf 仍是 `"MAF(+)"`）返回 **NULL** →
`cor.test(NULL, ...)` 被 tryCatch 吞掉 → **该口径静默产出 0 行**，脚本不报错、看着像"没结果"。
⇒ **凡是 regulon 名相关的 data.frame 构造，一律显式 `check.names = FALSE`**。

---

## 2. 矩阵用 `[[字符]]` 取列 → `subscript out of bounds`

`t(sapply(...))` 返回的是 **matrix**；`m[["MAF(+)"]]` 在 matrix 上不做列名匹配，直接报错。
⇒ 先 `as.data.frame(x, check.names = FALSE)` 再按名取列。`[ , "name"]` 在 matrix 上可用，`[[` 不行。

---

## 3. bootstrap 索引越界 → CI 全 NA（不报错）

```r
boot_ci <- function(f, B=2000) quantile(replicate(B, f(sample(seq_along(SS), replace=TRUE))), c(.025,.975))
#                                                                 ↑ SS = 全部 48 个样本
boot_ci(function(idx) cliffs_delta(y[idx], x))   # ❌ y 只有 ~16 个元素 → idx 越界 → 全 NA
```
⇒ **两组各自重抽**：
```r
boot_delta <- function(x, y, B = 2000) {
  v <- replicate(B, {
    xi <- sample(x, length(x), replace = TRUE)
    yi <- sample(y, length(y), replace = TRUE)
    cliffs_delta(yi, xi)
  })
  quantile(v, c(.025, .975), na.rm = TRUE)
}
```
**自检**：跑完打印 `mean(!is.na(res$ci_lo))`，明显 <1 即为索引 bug。

---

## 4. 长表构造不要用 `melt + rownames` 对齐分组

```r
long <- melt(as.data.frame(agg), ...)                            # ❌ 组合 1：names 被改
long$grp <- sub("_.*$", "", sgrp[match(rownames(agg), samp)])     # ❌ 组合 2：48 行去对齐 48×K 行 → 分组错位
```
⇒ 显式构造（列主序天然对齐）：
```r
long <- data.frame(
  TF   = rep(top_tf, each = nS),      # 与 as.vector(mat) 的列主序对齐
  AUC  = as.vector(agg),
  samp = rep(samp, times = nT)
)
long$grp <- sub("_.*$", "", sgrp[match(long$samp, samp)])
stopifnot(nrow(long) == nS * nT, !any(is.na(long$grp)))   # ← 必加自检
```
（`rep(each=n)` + `as.vector(mat)` 这一对是通用的"长表构造"正解，见 `reshape2::melt` 的替代。）

---

## 5. 统计单元：细胞级 p 值 = 伪重复（L2 辩论裁决）

2132 个细胞来自 **48 个样本** ⇒ 直接对细胞做组间检验，p 值被伪重复严重高估。
**裁决（verdict=modify）**：统计单元 = **48 个样本**；
① 先按样本聚合（每样本每 regulon 取均值）；
② 组间 Wilcoxon + Cliff's delta（含 bootstrap 95% CI）；
③ 多口径统一 BH-FDR；
④ 正方向统一定义并写进表头（如"正值 = 促萎缩"）。

---

## 6. 出图前的自检清单（防空图交付）

```r
stopifnot(length(top_tf) > 0)          # 选出的 TF 非空
cat("CI 非 NA 比例:", round(mean(!is.na(res$ci_lo)), 3), "\n")   # 应接近 1
cat("口径C 结果行数 =", nrow(resC), "（应 = regulon 总数；为 0 即列名保真失败）\n")
```
出图后按 `platform-execution-pitfalls` 的空白图判据（`getcolors` 颜色数 ≤1 ⇒ 空白）批量核一遍，
**批量核一次跑完**（逐张单发会触发循环检测）。