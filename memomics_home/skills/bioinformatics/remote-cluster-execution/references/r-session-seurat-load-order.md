# 常驻会话内加载 Seurat 失败（RcppAnnoy / AnnoyAngular）—— 实测底稿

日期：2026-11-05 ｜ 节点：`node1` ｜ 输入：`/cluster/share/user/Muscle_96_38/Umap/EC_pericyte_exercise_clean_annotated.rds`（822 MB）
对应 SKILL.md：**铁规 6.5**（修法）与**铁规 6.6**（输出纪律）

---

## 1. 现象（原样回执）

`session_start(input=…)` 返回 `status: error`，`error` 字段写「读入失败」，但同一段 `output` 里
**第一行就说明 readRDS 成功了**：

```
已读入 /cluster/…/EC_pericyte_exercise_clean_annotated.rds -> ec（17.2 秒）
Loading required package: SeuratObject
Loading required package: sp
Attaching package: 'SeuratObject'
Loading required package: Seurat
Error: package or namespace load failed for 'Seurat' in .doLoadActions(where, attach):
 error in load action .__A__.1 for package RcppAnnoy:
 loadModule(module = "AnnoyAngular", what = TRUE, env = ns, loadNow = TRUE):
 Unable to load module "AnnoyAngular": attempt to apply non-function
```

同时 `state` 里 `readrds_calls: 1`、`objects` 非 0 —— **对象其实已经在 daemon 内存里**。
工具层把"其后加载 Seurat 失败"统一措辞成「读入失败：unable to find required package 'Seurat'」，
字面极易被读成「文件读不了 / 环境缺 Seurat」。

## 2. 排除过程（四步定因，别跳步）

| # | 测试 | 回执 | 结论 |
|---|---|---|---|
| 1 | `R4.41/bin/Rscript -e 'library(Seurat)'`（干净进程） | `SEURAT_OK 5.3.0  RcppAnnoy 0.0.22` | 环境是好的 |
| 2 | 扫全部 env 找能加载 Seurat 的 | `R4.41: 5.3.0`、`R4.3.3: 5.3.0`、`ARCHR: 5.3.0`、`R4.4.1_zb: 5.5.1`，其余 NO | 有多个候选，不缺环境 |
| 3 | 换 `R4.4.1_zb`（Seurat 5.5.1 / RcppAnnoy 0.0.23）重开 daemon | **同一句报错** | ⇒ 与 env、与 Seurat/RcppAnnoy 版本**无关** |
| 4 | daemon 内 `library(RcppAnnoy)` 单独加载 | `ANNOY_OK 0.0.23` | 包能装；问题在「被 Seurat 间接触发」这条路径 |

daemon 内 `loadedNamespaces()` 暴露了根因条件（干净 Rscript 没有这一层）：

```
digest, methods, RColorBrewer, progressr, dotCall64, codetools, Matrix, ROCR, lattice,
KernSmooth, parallel, generics, lifecycle, utils, cli, parallelly, future, grid, graphics,
RANN, grDevices, stats, compiler, base, globals, tools, RSpectra, sp, SeuratObject, listenv,
future.apply, Rcpp, rlang, MASS, spam, datasets
```

`Rcpp` 已加载，且 `RcppAnnoy`/`spam`/`RSpectra`/`SeuratObject` 都 import 它
（`unloadNamespace("Rcpp")` 会直接失败：`namespace 'Rcpp' is imported by … so cannot be unloaded`），
所以 Seurat 触发 `RcppAnnoy` 的 `loadModule` 时踩在已初始化的 Rcpp 上 → `attempt to apply non-function`。

## 3. 修法（两行，之后永久复用）

```r
suppressMessages(library(RcppAnnoy))
suppressMessages(library(Seurat))
```

实测回执：`SEURAT_OK 5.5.1` → 后续同一进程内 `DIM / ASSAYS / REDUCTIONS / META_COLS / DefaultAssay` 全部可读，
且 `readrds_calls` 始终 = 1。

`session_start` 另一处必须显式传参：自动探测只找 `~/miniconda3`、`~/anaconda3`、`/opt/conda`，
找不到 zhangxiao6 名下的 env →

```
error: 节点 node1 上没找到可用的 Rscript（env=R4.41）。 raw: NO_RSCRIPT
candidates: ~/miniconda3/envs/R4.41/bin/Rscript, ~/anaconda3/…, /opt/conda/…
```

→ 传 `rscript="/cluster/share/zhangxiao6/software/miniconda3/envs/R4.41/bin/Rscript"`
（自有可写环境 `/cluster/share/user/envs/R4.4.1_zb/bin/Rscript`）。

## 4. 可复用的「结构探针」模板

一条请求问全，避免多轮小探针（也躲开铁规 6 的循环判定）：

```r
suppressMessages(library(RcppAnnoy)); suppressMessages(library(Seurat))
cat("DIM:", nrow(ec), "genes x", ncol(ec), "cells\n")
cat("ASSAYS:", paste(Assays(ec), collapse=", "), "\n")
cat("REDUCTIONS:", paste(Reductions(ec), collapse=", "), "\n")
cat("DEFAULT_ASSAY:", DefaultAssay(ec), "\n")
cat("META_COLS:", paste(colnames(ec@meta.data), collapse=" | "), "\n")
cat("n_idents:", length(unique(Idents(ec))), "\n")     # ⛔ 绝不 print(Idents(ec))
print(table(ec$<分组列>))                               # 分组列只打频数
```

⛔ 反面教材：`cat(Idents(ec))` 输出 19,685 个值 = **44,095 字符**，被截断且挤掉了真正要看的字段。

## 5. 判据速记

- 「已读入 …秒」出现在错误回执里 ⇒ **数据没问题，是包加载问题**，别回读文件、别 pull 回本机。
- 同一报错在**两个不同 env** 都复现 ⇒ 加载路径问题，不是环境问题。
- 干净 `Rscript` OK 但 daemon 内失败 ⇒ 找**预加载的命名空间**（`loadedNamespaces()`），而不是重装包。
- 良性旁路：daemon 已把对象读进内存，修好加载顺序后**不丢任何已完成的工作**。