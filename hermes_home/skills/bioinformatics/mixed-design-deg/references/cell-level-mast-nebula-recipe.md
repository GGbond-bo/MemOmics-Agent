# 细胞级 MAST (glmer+供体随机效应) / NEBULA 实测配方

> 场景：混合设计（组间独立 + 组内配对）下 pseudobulk 检出过少，需用**细胞级**方法做敏感性分析 /
> 候选基因发现。2026-09-26 实测（人骨骼肌，24 供体 × Pre/Post = 48 样本，6 条件，10 亚群；MAST 1.32.0）。
> ⛔ **定位**：仅敏感性/候选，**不当主分析**（升级条件见 §5）。

---

## 1. MAST：已在真实数据跑通的版本

官方依据（读包自带 Rd，非记忆）：`zlm.Rd` → `method: character vector, either 'glm', 'glmer' or 'bayesglm'`。
⇒ `method="glmer"` 即随机效应通道，`ebayes=FALSE`。

```r
suppressPackageStartupMessages({library(Seurat); library(MAST); library(Matrix); library(lme4)})
GROUP_LEVELS <- c("Y_Pre","Y_Post","O_Pre","O_Post","OD_Pre","OD_Post")
CONTRASTS <- c(Aging="typeO_Pre - typeY_Pre", DM="typeOD_Pre - typeO_Pre",
  Ex_Young="typeY_Post - typeY_Pre", Ex_Old="typeO_Post - typeO_Pre",
  Ex_DM="typeOD_Post - typeOD_Pre",
  Ex_x_Aging="(typeO_Post - typeO_Pre) - (typeY_Post - typeY_Pre)",
  Ex_x_DM="(typeOD_Post - typeOD_Pre) - (typeO_Post - typeO_Pre)")

## 对比字符串 -> 因子水平权重（基准水平 Y_Pre 被截距吸收，不入系数）
parse_w <- function(s, lv) { w <- setNames(numeric(length(lv)), lv); s <- gsub("[()]", "", s)
  for (t in strsplit(s, "(?<=.)(?=[+-])", perl = TRUE)[[1]]) {
    sg <- if (startsWith(t, "-")) -1 else 1
    g <- trimws(gsub("^[+-]", "", t)); w[sub("^type", "", g)] <- w[sub("^type", "", g)] + sg }
  w }

## ① 数据准备：先 print(names(md)) —— 别假设 individual 列存在
obj <- readRDS(rds); counts <- LayerData(obj, assay="RNA", layer="counts"); md <- obj@meta.data
if (!"individual" %in% names(md)) md$individual <- sub("_[^_]+$", "", as.character(md$samplename))

idx <- which(md$annotation_L3 == sc); X <- counts[, idx]; mdx <- md[idx, ]
set.seed(1)                                  # ② 按供体降采样（无偏，控计算量）
kc <- unlist(lapply(split(seq_len(ncol(X)), mdx$individual),
                    function(ix) if (length(ix) > 30) sample(ix, 30) else ix))
X <- X[, kc]; mdx <- mdx[kc, ]
det <- Matrix::rowSums(X > 0); gk <- which(det >= 0.2 * ncol(X))          # ③ 基因过滤
gk <- sort(gk[order(Matrix::rowSums(X[gk,,drop=FALSE]), decreasing=TRUE)][1:3000]); X <- X[gk,]

cpm <- t(t(X)/Matrix::colSums(X))*1e6; e <- log2(as.matrix(cpm)+1)       # ④ log2(CPM+1)
cdata <- data.frame(wellKey=colnames(X), individual=factor(mdx$individual),
  type=factor(as.character(mdx$type), levels=GROUP_LEVELS),
  cngeneson=as.numeric(scale(Matrix::colSums(X>0))), row.names=colnames(X))
sca <- MAST::FromMatrix(e, cData=cdata,
  fData=data.frame(primerid=rownames(X), row.names=rownames(X)))
fit <- MAST::zlm(~ type + cngeneson + (1|individual), sca,
                 method="glmer", ebayes=FALSE, silent=TRUE)

## ⑤ 裸泛型 coef/vcov 手算 Wald（⚠️ coef/vcov 未导出；vcov 维度=(系数,系数,基因)）
res <- list()
for (cn in names(CONTRASTS)) { w <- parse_w(CONTRASTS[[cn]], GROUP_LEVELS)
  bn <- paste0("type", setdiff(GROUP_LEVELS, GROUP_LEVELS[1]))    # 5 个哑变量名
  for (comp in c("C","D")) {
    cc <- coef(fit, comp); vv <- vcov(fit, comp)                   # ← 不要写 MAST::
    av <- intersect(bn, colnames(cc)); avv <- intersect(bn, dimnames(vv)[[2]])
    orient <- if (length(intersect(dimnames(vv)[[3]], rownames(cc))) > 0.5*nrow(cc)) "ccg" else "gcc"
    wt_v <- w[sub("^type","",av)]; B <- cc[, av, drop=FALSE]; est <- as.numeric(B %*% wt_v)
    se <- vapply(seq_along(est), function(i) {
      Vi <- if (orient=="ccg") matrix(vv[avv,avv,i], nrow=length(avv))
            else               matrix(vv[i,avv,avv], nrow=length(avv))
      sqrt(as.numeric(t(wt_v) %*% Vi %*% wt_v)) }, numeric(1))
    res[[paste(cn,comp)]] <- data.frame(contrast=cn, component=comp, gene=rownames(B),
      logFC=est, se=se, z=est/se, P.Value=2*pnorm(-abs(est/se)), stringsAsFactors=FALSE) } }
big <- do.call(rbind, res)
big$adj.P.Val <- ave(as.numeric(big$P.Value), interaction(big$contrast, big$component),
                     FUN = function(p) p.adjust(p, "BH"))
```

**实测输出形状**：`coef(fit,"C")` = `3000 x 7`、列名 `(Intercept), typeY_Post, typeO_Pre,
typeO_Post, typeOD_Pre, typeOD_Post, cngeneson`；`vcov(fit,"C")` = `7 x 7 x 3000`（**基因在第 3 维**）。
7 对比 × 2 组件 × 3000 基因 = **42,000 行**。

---

## 2. 四个陷阱（原始报错文本，照此 grep）

| # | 写法 | 报错原文 | 正解 |
|---|---|---|---|
| 1 | `MAST::coef(fit,"C")` | `'coef' is not an exported object from 'namespace:MAST'` | 裸泛型 `coef(fit,"C")` / `vcov(fit,"C")` |
| 2 | `MAST::waldTest(fit, MAST::CoefficientHypothesis(x))` | `"MAST::CoefficientHypothesis" is not a defined class` | 不用 waldTest，coef+vcov 手算 Wald |
| 3 | 假设 vcov 是 (基因,系数,系数) | **不报错，静默取错值** | 自动判方向（见 §1 代码） |
| 4 | `split(..., md$individual)` | `group length is 0 but data length > 0` | 先 `print(names(md))`；由 samplename 剥离 |

诊断纪律（本轮 5 轮白烧换来的）：
- **execute_r 报错时 stdout 整块丢弃** ⇒ 诊断必须**写文件**（`L <- function(...) cat(..., file=logf, append=TRUE)`）再 `read_file`，否则每次只看到 stderr、不知道跑到哪一步。
- **不要「换个写法再试一次」逐步逼近**：连败 3 次即触发循环检测。第一次报错就读包自带 Rd / 打印 `dim` 实测。
- 报错落在 `.read` / 落单 `)` 处 → 先怀疑传输截断（execute_r 用 `source()`，不是 `exec(open().read())`）。

---

## 3. NEBULA（官方 README 原文核实）

```r
re <- nebula::nebula(count, id, pred = mm, offset = Matrix::colSums(count),
                     method = "LN", ncore = 8)
```
| 要点 | 内容 |
|---|---|
| `count` | **M(基因) × N(细胞)**，元素必须**整数**，支持 sparse `dgCMatrix` |
| `pred` | 必须是 `model.matrix` 结果，**必须含截距列**，列名唯一 |
| 细胞顺序 | 需**按 subject 连续排列** → `group_cell(count, id, pred, offset)` 负责重排 |
| `offset` | 正数向量（推荐细胞文库大小）；**输入已是 normalized counts 时不要传** |
| `method` | `'LN'` 更快、每受试者细胞数大时更准；`'HL'` 更慢但细胞级过度离散更准 |
| p 值 | **原始值，未校正 → 必须自行 BH** |
| ⚠️ | README 明确警告**二元变量过多会导致 separation** |

**让每个对比 = 单一系数**（免依赖协方差输出）：每对比在**相关子集**单独拟合一次 ——
`Aging` = 两 Pre 组 `~grp`；`DM` = 两 Pre 组 `~grp`；`Ex_*` = 单组 `~time`；`Ex_x_*` = 两组 × Pre/Post `~grp*time`
（**交互项即 DiD**，单一系数）。子集内仍有 `(1|subject)` ⇒ 配对结构保留。
`scToNeb(obj, assay, id, pred, offset)` 是官方的 Seurat/SCE 取数辅助函数。

---

## 4. 计算量与分工

- `glmer` 单基因一次优化 ≈ **0.05–0.5 s**（随细胞数增长）⇒ 50 万细胞**必须** `--max_cells_per_donor` 降采样。
  降采样**无偏**（同供体内细胞可交换），只损失功效；报告里写明用了多少。
- NEBULA 专为大规模多受试者设计，**可上全量**。
- 全量对象在集群、本机只有平衡子集时：本机跑子集**验证脚本跑通**，但**数字会随全量重跑变化**，交付必须声明。

---

## 5. 结果口径与升级条件

1. `C` 组件 = **表达量**（log2 尺度均值差）；`D` 组件 = **检出率**（log-odds）。**两种不同的量，⛔ 不能混着说"上调"**。
2. 检验族 = 「亚群内 × 该对比内 × 该组件内」BH（与 pseudobulk 口径对齐，便于比较）。
3. **统计显著 ≠ 可稳定检出**：报「设计可稳定检出的 |logFC| 下限」比只报显著数更有信息量。
4. **细胞级 n = 细胞数 ≠ 供体数** ⇒ p 值偏乐观。文献立场：Squair 2021（PMID 34584091）、
   Lee & Han 2024（PMID 39115884）、Gilis 2025（PMID 41053561「没有单一方法在所有情形最优」）
   均不支持把细胞级升为主分析。
5. **升级为结论的条件（缺一不可）**：随机效应方差 >0 且稳定 + **供体内条件标签置换 ≥100 次**显示超出零分布
   + 与 pseudobulk 方向一致 + 效应量达设计下限。
6. **双向收获**：两法都零的对比 = **稳健阴性**，比单方法可信（本例 `DM` 在 pseudobulk 与 MAST 下均为 0）。

---

## 6. 本次实测数字（平衡子集，Pure Type IIA，供参照，非全量结论）

7 对比 × 2 组件 = 42,000 行，FDR<0.05 共 787 个：

| 对比 | C（表达量） | D（检出率） | 对比 pseudobulk |
|---|---:|---:|---|
| Aging | 142 | 123 | 29,550（pseudobulk 强得多） |
| Ex_Old | 86 | 67 | 1,246 |
| Ex_x_DM（糖尿病 DiD） | 77 | 141 | — |
| Ex_x_Aging（衰老 DiD） | 71 | 11 | — |
| Ex_Young | 56 | 5 | **22**（细胞级更敏感） |
| Ex_DM | 5 | 3 | 4 |
| DM | **0** | **0** | 1（**两法皆零 → 稳健阴性**） |

⚠️ 单看「细胞级比 pseudobulk 多检出」**不能**据此升级方法 —— 见 §5 第 4/5 条。
⛔ 不要为「基因数变多」而换方法：本轮 L1 裁决为 `need_more_info`，决策是
**主分析保留 pseudobulk，MAST/NEBULA 降为敏感性**，DiD 的新发现标注**未确认**直至置换校准。

---

## 7. 环境选库（不是"包坏了"，是"包在哪个 R 的库里"）

`library(MAST)` 报 `there is no package called 'MAST'` 而 `check_env` 说已装 ⇒ **两者看的不是同一套库**
（execute_r 内核用的 R 版本 ≠ check_env 扫描的库）。处置：

```r
cat(R.version.string); print(.libPaths())          # 先确认内核的 R 版本与库
for (lib in c("E:/R-libs/R-4.5.3", "C:/Users/<u>/AppData/Local/R/R-4.4.2/library"))
  cat(lib, dir.exists(lib), paste(c("MAST","nebula","lme4")[
    file.exists(file.path(lib, c("MAST","nebula","lme4")))], collapse="|"), "\n")
```

实测：MAST 1.32.0 只在 R-4.4.2 用户库；**把该库 `.libPaths` 追加后 `library(MAST)` 可成功**
（纯 R 包可跨小版本借用）。⚠️ **含编译代码的包不可跨小版本借用**（会在 loadNamespace 阶段炸 DLL）。
`nebula` 含 C++（依赖 Rfast/GSL，v1.5.7+ 要求 R ≥ 4.4.0）⇒ 需能编译的环境（Linux 集群最省事），
Windows 无对应 Rtools 时不要硬刚，落脚本到集群跑。