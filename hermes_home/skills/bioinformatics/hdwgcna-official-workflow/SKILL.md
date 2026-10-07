---
name: hdwgcna-official-workflow
description: "hdWGCNA 官方 workflow 端到端运行：SetupForWGCNA→Metacells→SetDatExpr→TestSoftPowers→ConstructNetwork→ModuleEigengenes→ModuleConnectivity→ModuleTraitCorrelation→7类官方标准图。含 Windows/R 4.4.2 实操坑（enrichR .onAttach 联网、future.globals.maxSize、TOMFiles 路径修复）。"
when_to_use: "[hdwgcna-official] 需要跑 hdWGCNA 官方完整 workflow、出官方标准图集、或遇到 hdWGCNA 加载失败/ModuleTraitCorrelation 报错/ModuleUMAPPlot future 超限/TOM 路径问题。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [hdwgcna, wgcna, co-expression, module, windows, official-workflow]
    difficulty: advanced
    language: R
    category: scRNA
prerequisites:
  r_packages: ["hdWGCNA", "Seurat", "WGCNA", "future"]
  python_packages: []
---

# hdWGCNA 官方 workflow（Windows 实操版）

端到端跑通 hdWGCNA 官方教程（Morabito et al. 2023 Cell Rep Methods）并出 7 类官方标准图。
已在骨骼肌 MF（20000 cells / 6524 metacells / 10176 genes）实测通过（2026-08-01，hdWGCNA 0.4.12，R 4.4.2）。

## 什么时候用
- 需要模块-性状关联（module-trait correlation）直接回答"哪个模块响应哪个效应"时
- 需要官方标准图集（软阈值/树状图/模块UMAP/hub网络等）时
- 遇到下述已知报错时

## 官方标准图集（7 类 14 文件）
01 softpower（TestSoftPowers→PlotSoftPowers）、02 dendrogram（PlotDendrogram）、
03 module_trait（ModuleTraitCorrelation→PlotModuleTraitCorrelation）、
04 module_umap（RunModuleUMAP→ModuleUMAPPlot）、05 module_features（ModuleFeaturePlot）、
06 hub_network（GetHubGenes→HubGeneNetworkPlot）、07 kmes（PlotKMEs）。
每类 PDF+PNG 双格式。

## 已验证的关键坑（Windows / R 4.4.2 / 0.4.12）

### 1. `library(hdWGCNA)` 失败：enrichR .onAttach 联网
- 症状：`package or namespace load failed for 'enrichR': Timeout was reached [maayanlab.cloud]`
- 根因：enrichR 是 hdWGCNA 的 Imports；其 .onAttach 先 nslookup 判定有网 → listEnrichrSites() 联网超时
- 修复：**用 loadNamespace 替代 library**（不触发依赖包 .onAttach），函数用前缀取
```r
suppressPackageStartupMessages({ library(Seurat); library(WGCNA) })
loadNamespace("hdWGCNA")
h <- asNamespace("hdWGCNA")
GETFN <- function(f) get(f, envir = h)
HModuleEigengenes <- GETFN("ModuleEigengenes")
# 后续所有 hdWGCNA 调用用 H 前缀
```

### 2. ModuleTraitCorrelation 的 traits 参数是 meta.data 列名，不是 data.frame
- 症状：`Some of the provided traits were not found in the Seurat obj: c(0,0,...)`
- 修复：先 AddMetaData 效应列，再传列名字符向量
```r
md <- obj@meta.data
md$Aging <- as.numeric(md$type %in% c("O_Pre","O_Post"))
obj <- AddMetaData(obj, metadata = md[, "Aging", drop=FALSE])
obj <- ModuleTraitCorrelation(obj, traits = c("Aging"), features = "hMEs",
                              cor_method = "pearson", wgcna_name = "MF_wgcna")
mtc <- GetModuleTraitCorrelation(obj, wgcna_name = "MF_wgcna")  # mtc$cor / mtc$pval
```

### 3. ModuleUMAPPlot future 并行传输 8+ GiB 超限
- 症状：`The total size of the 3 globals exported for future expression ('FUN()') is 8.36 GiB. This exceeds the maximum allowed size 500.00 MiB`
- 修复：
```r
options(future.globals.maxSize = 20 * 1024^3)
library(future); plan("sequential")
```

### 4. ModuleEigengenes 报 "Need to run ScaleData"
- 修复：先 `obj <- ScaleData(obj, features = GetWGCNAGenes(obj, wgcna_name="MF_wgcna"), verbose=FALSE)`

### 5. SetDatExpr 报 "Some groups in group_name are not found"
- 根因：group_name 必须是**具体组值向量**，不是列名
- 修复：`SetDatExpr(obj, group_name = sort(unique(obj$annotation_L3)), group.by = "annotation_L3", ...)`

### 6. NormalizeMetacells/ScaleMetacells 传主对象而非 metacell 对象
- 症状：`CheckWGCNAName 参数长度为零`
- 修复：`obj <- NormalizeMetacells(obj, wgcna_name="MF_wgcna")`（内部自动取 metacell）

### 7. 续跑时 TOM 路径重复拼接（BASE 拼两次）
- 症状：`TOM file .../BASE/BASE/TOM_official/... not found`
- 修复：直接改对象里的 TOMFiles
```r
obj@misc$MF_wgcna$wgcna_net$TOMFiles <- "E:/.../TOM_official/MF_wgcna_TOM.rda"
```

### 8. 抓 hdWGCNA 源码/文档：默认分支是 dev，不是 main
- 症状：`raw.githubusercontent.com/smorabit/hdWGCNA/main/...` 或 jsdelivr `@main` 全部 404 / "Couldn't find the requested file"
- 根因：hdWGCNA 仓库默认分支为 **dev**（api.github.com/repos/smorabit/hdWGCNA → default_branch=dev）
- 修复：`https://raw.githubusercontent.com/smorabit/hdWGCNA/dev/R/SoftPowers.R`、`.../dev/vignettes/basic_tutorial.Rmd`（vignettes 清单可用 `api.github.com/repos/smorabit/hdWGCNA/contents/vignettes` 列）
- 抓取兜底路径（smorabit.github.io / UCLA 站点 curl 常 SSL reset exit 35）：GitHub API → raw.githubusercontent → cdn.jsdelivr.net → web.archive.org（python urllib 带 ssl 宽松 ctx 也行）
- 核实参数默认值以**已装包为准**：`Rscript -e 'loadNamespace("hdWGCNA"); print(args(asNamespace("hdWGCNA")$SetDatExpr))'`——函数签名即文档，比查网页权威

### 9. 🔴🔴 execute_r 持久内核 = **R 4.5.3，不是 R 4.4.2**（2026-09-24 MF_120 会话实证，纠正本文档旧记载）
- 症状：`execute_r(code="library(WGCNA)")` → `there is no package called 'WGCNA'`；紧接着整个 R 进程 `exit code 3221225794 (0xC0000142 STATUS_DLL_INIT_FAILED)`，**没有任何 R 层报错**
- 实证：内核打印 `R version 4.5.3` + `.libPaths()` = `E:/R-libs/R-4.5.3 | C:/Program Files/R/R-4.5.3/library` —— **两个库都没有 hdWGCNA/WGCNA**
- ⚠️ 同一个会话里 `env_check.check_env(language="R")` 会返回 "installed / from_cache"，`rail_review(pre)` 却报 "Missing packages" → 因为 rail_review 调 check_env 时**不传 language**（默认 both），R 专用包走 R-查不到分支被误报；同时缓存里存在同名 R 条目造成"假可用"假象
- ✅ 正确做法：hdWGCNA 流程**一律用 terminal + R 4.4.2 全路径**，不要用 execute_r
```r
# 正确路径必须含 x64（少了 x64 会报"系统找不到指定的路径"）
# C:/Users/23136/AppData/Local/R/R-4.4.2/bin/x64/Rscript.exe
```
- R 4.4.2 库：`E:/R-libs/R-4.4.2` + `C:/Users/23136/R/R-4.4.2-library` + `AppData/Local/R/R-4.4.2/library`
- 版本实测：hdWGCNA 0.4.12 / WGCNA 1.74 / Seurat 5.5.0 / future 1.70.0 / enrichR 3.4

### 10. 🔴 metacell 对象键名 = `wgcna_metacell_obj`（不是 `metacell_obj`）
- 症状：`obj@misc[[wgcna_name]][["metacell_obj"]]` 返回 NULL → `ncol()`/`table()` 得到空 → **整批组合被误判为"metacell 构建失败"**（实际已成功）
- 实证 `names(obj@misc$MF_wgcna)` = `wgcna_genes, wgcna_metacell_obj, wgcna_params`
```r
m <- o@misc[[wgcna_name]][["wgcna_metacell_obj"]]   # ✅
# metacell 的 meta.data 列: orig.ident, nCount_RNA, nFeature_RNA, cells_merged, <group.by 同名列>
#   原始细胞列表列名 = cells_merged（逗号分隔）
```
- 也可用 `GetMetacellObject(obj, wgcna_name=)`

### 11. 🔴 `MetacellsByGroups` 后**必须**先 NormalizeMetacells + ScaleMetacells，否则 SetDatExpr 报错
- 症状：`SetDatExpr` → `在为函数"t"选择方法时计算参数"x"时出错：subscript out of bounds`，伴随警告 `Layer 'data' is empty`
- 根因：MetacellsByGroups 以 `mode="average"` 只填 counts，metacell 对象 RNA 的 `data` 层为空
- ✅ 官方顺序：`SetupForWGCNA → MetacellsByGroups → NormalizeMetacells → ScaleMetacells → SetDatExpr → TestSoftPowers → ConstructNetwork`
```r
o <- NormalizeMetacells(o, wgcna_name=WN)   # 传主对象, 内部自动取 metacell
o <- ScaleMetacells(o, wgcna_name=WN)
```

### 12. 小样本数据下 metacell 参数必须实测（官方默认不适用）
- `min_cells` 官方默认 **100**：分组细胞数只有 7–23 时会**跳过全部组** → 必须下调（本次 min_cells=5）
- `k` 官方默认 **25**：120 细胞只够 4–5 个 metacell → 无法建网；且 **k 必须 < 组内最小细胞数**
- `ConstructMetacells` 源码：当某组只能构造出 ≤1 个 metacell（`length(chosen) <= 1`）或 `combn()` 失败时 → `warning("Metacell failed")` 并 `return(NULL)`（该组静默丢失）
- 实测（120 细胞 / 6 组 type / 10 群 annotation_L3）：

| group.by | k=3 | k=5 | k=10 |
|---|---|---|---|
| type（16–23 细胞/组） | 55 mc | **37 mc** | FAIL（组内构不出 ≥2 mc） |
| annotation_L3（7–18 细胞/群） | 50 mc | 24 mc（2/10 群无 mc） | 未测 |

### 13. ConstructNetwork 在 ~1 万基因上远超 10 分钟 → 必须后台
- 实测：11,116 基因 × 37 metacell，前台 600s 超时（exit 124）
- ✅ `terminal(..., background=True, notify_on_complete=True)` + 日志重定向后再 tail
- 同时：**Windows/MSYS 下不要用 `grep|grep|grep|head` 多级管道**包裹 Rscript —— 会触发 `bash: fork: Resource temporarily unavailable (errno 11)` + `0xC0000142`。改为 shell 侧只做 1 次重定向 + 1 次 tail，过滤逻辑放进 R 脚本内部

### 14. 🔴 `GetModuleTraitCorrelation` 返回**类型不一致**：all_cells 组的 pval/fdr 是 data.frame，亚群组是 matrix
- 症状（三种报错同一根因，极易误判成数据结构坏了）：
  - `rbind` → `numbers of columns of arguments do not match`
  - `as.table()` → `cannot coerce to a table`
- 根因：`mtc$fdr[["all_cells"]]` 是 **data.frame**；`as.vector(data.frame)` 返回的是 **list**（每列一个元素）→ `data.frame(cor=<57 元素 list>)` 被展开成 **57 列** → 该组 df 有 62 列、其余组 6 列 → rbind 崩
- ✅ 统一取值助手（对 data.frame / matrix / vector 一视同仁）：
```r
vec1 <- function(x) {
  if (is.null(x)) return(NA_real_)
  if (is.data.frame(x)) return(as.vector(as.matrix(x)))
  if (is.matrix(x))     return(as.vector(x))
  as.vector(unlist(x))
}
# 组内矩阵列名本就是裸模块名（"yellow","green"...），不要用 sub("^<组名>\\.", ...) 剥前缀
# —— 组名含正则元字符（"LRP1B+(I)" / "RP_high(II)"）会让 sub() 抛 invalid regex
```
- 复核法：展开前先 `print(paste(class(cor), class(pval), class(fdr)))` 逐组打印，一次定位

### 15. 🔴 官方图集在 0.4.12 的 5 个实测坑（全部实测取证，非推测）

| 图型 | 症状 | ✅ 正解 |
|------|------|--------|
| `PlotModuleTraitCorrelation` | `参数没有用(scale = TRUE)` | 该版本**无 scale 参数**；真实签名 = `high_color="red", mid_color="grey90", low_color="blue", label=NULL/label_symbol="stars", text_size, text_digits, combine` |
| `PlotDendrogram` | 产出仅 **2.4KB** 的近空白图（无报错） | 改用 WGCNA 底图 API：`plotDendroAndColors(net$dendrograms[[1]], net$colors, "Module colors", dendroLabels=FALSE, hang=0.03, addGuide=TRUE, guideHang=0.05, marAll=c(1,5,2,1))` → 46KB 正常图 |
| `HubGeneNetworkPlot` | **无任何报错、无产出**（易被当成成功） | 它**返回 NULL 且向「当前设备」绘图** → Rscript 下默认设备是 pdf，全画进 `Rplots.pdf`。**必须显式 `png(f,...)` 包裹 + `dev.off()`**，并事后 `file.size()` 校验 |
| `ModuleFeaturePlot` | 产出 **空白图**（12KB，99.8% 背景色，仅渲染出 1 个词） | 改用 Seurat 原生：`o <- AddMetaData(o, as.data.frame(GetMEs(o, harmonized=TRUE)[, mods]))` → `FeaturePlot(o, features=mods, reduction="umap", ncol=2, order=TRUE, pt.size=1.2)`；该版本 `ModuleFeaturePlot` 的 formals **无 ncol 参数**（传了报 `参数没有用(ncol = 2)`） |
| `ModuleUMAPPlot` | 除 future 限值外，还有第二种失败 `参数长度为零`（0.4.12 内部逻辑错） | 放宽 future 上限后仍失败 → 判为可弃图型，用 ④ 的 FeaturePlot 替代交付，不要在此图反复烧时间 |

- 出图脚本**必须**统一加：`options(future.globals.maxSize = 8*1024^3)` + `plan("sequential")`（ModuleUMAPPlot / HubGeneNetworkPlot 都要传 ~0.99 GiB 的 hME 邻接矩阵，默认 500 MiB 上限必炸）
- TOM 路径二次拼接的**通用**修复（比手改单字段稳，命中数会打印出来）：
```r
fix_tom_paths <- function(o, WN, correct) {     # correct = 磁盘上真实 TOM rda 路径
  n <- 0L
  rec <- function(x) {
    if (is.character(x) && length(x) >= 1 && any(grepl("TOM\\.rda$", x))) {
      hit <- grepl("TOM\\.rda$", x); n <<- n + sum(hit); x[hit] <- correct; return(x) }
    if (is.list(x)) { for (i in seq_along(x)) if (!is.null(x[[i]])) x[[i]] <- rec(x[[i]]); return(x) }
    x }
  o@misc[[WN]] <- rec(o@misc[[WN]]); o
}
```
  实证 `hdWGCNA::GetTOM` 源码：读 `GetNetworkData(obj, wgcna_name)$TOMFiles[[1]]` → 该字段值被 `getwd()` 前缀过，故从别的工作目录读对象时必然双拼接

## 🔴 模块可信性判定（小样本 / 高基因:样本比 必做，出结论前强制）

**触发条件（任一）**：metacell 数 < 50；基因:样本比 > 100:1；模块数异常多（如 37 metacell 拆出 57 模块）；某一 group 的显著条目数远高于其他 group。

**高危信号（本次实测案例）**：FDR<0.05 共 341/11172（3.05%），其中 **all_cells 独占 270 条（该组检验的 26.3%）**，而 10 个亚群内仅 0–43 条（0–4.2%）。
→ 全库显著、亚群不显著的**极不对称分布** = 过分割（deepSplit=4 + minModuleSize=50 在小矩阵上）与循环性（模块由同一批 metacell 定义、又在同一批上算相关）的典型指纹。**此时禁止输出性状关联结论**，必须先跑稳定性协议。

**稳定性协议（5 类变体，全部用 `WGCNA::blockwiseModules`，参数与 `ConstructNetwork` 对齐 —— 参数逐项对齐后写进日志留证）**：

| 次序 | 变体 | 判读标准（2026-09-24 在 11116 基因 / 37 metacell 实测校准） |
|------|------|---------|
| 0 | **reproduce 对照**：同 datExpr 重跑 | ARI 应 ≈1。**实测常得 0.9515 / Jaccard 0.9657 / 56-57 模块 Jaccard≥0.5** —— 这已足够证明复现管线与 hdWGCNA 等价，[1]-[4] 的比较成立。⚠️ **别把"没到 1.0"判成失败**：`ConstructNetwork` 有固有随机性，用 [4] seed 对照区分"实现差异"vs"随机性" |
| 1 | **permuted 零模型**：**逐基因**在样本间打乱（`t(apply(datExpr, 2, sample))`） | 🔴 **判据不是"模块数变少"——它不会变少**。实测打乱后**仍产出 37 个非 grey 模块**，但 **grey 从 4651 掉到 524**。⇒ 在 300:1 基因:样本比下 WGCNA 会把基因硬塞进大量模块，**"模块数多"不构成信号证据**；能定论的只有 [2][3][4] 的一致性 |
| 2 | **split-half**：metacell 奇/偶各半独立建网 | 两半模块的 ARI/Jaccard = 直接可重复性。实测 0.15–0.21 → **不可重复**。🔴 **必须按行（`nrow` + `datExpr[idx, , drop=FALSE]`）分半**，见下方"两个静默 bug" |
| 3 | 参数变体：k=3/type、k=3/k=5 annotation_L3、**原细胞直接建网**（不经 metacell） | 与 primary 的 ARI/Jaccard。实测 0.017–0.083，Jaccard≥0.5 的模块 **0/57** ⇒ 参数敏感/过分割 |
| 4 | **seed 对照**：同 datExpr 仅改 `randomSeed` | 区分"与 hdWGCNA 实现差异" vs "建网固有随机性" |

**🔴 合判断（实测结论）**：除 [0] 外**全部扰动变体 ARI ≤ 0.21、mean Jaccard ≤ 0.19、Jaccard≥0.5 的模块仅 0–1/57**
⇒ 模块划分对参数极度敏感 → **禁止据此输出性状关联结论**（降级为探索性描述，或明确判定该数据集不适用 hdWGCNA 模块推断）。
这个"跑完稳定性再定稿"的顺序不是仪式：本次若直接采信 Phase 3 的 341 条 FDR<0.05，会交付一批不可重复的"衰老相关模块"。

### 🔴 两个静默 bug（本脚本 v1 自带，2026-09-24 发现并修复 —— 曾让整个 split-half 变体作废）

**bug-1 · split-half 按基因分半**：`seq(1, ncol(datExpr), by=2)` + `datExpr[, idx]`
→ 取的是**列（基因）**，实际切成「基因对半分」，根本不是「metacell 对半分」。
**指纹（一眼识别）**：日志打出 `半样本 odd: 5558 metacells` —— primary 只有 **37** 个 metacell，而 `5558 = 11116/2`（基因数一半）。
> 🔑 **通用判据：凡日志里的数字与其文本标签矛盾（样本文本写 "metacells"、数值却是基因数级），立刻回查 `nrow`/`ncol` 与 `[i, ]`/`[, j]` 的配对。**
修复 = `nrow(datExpr)` + `datExpr[idx, , drop=FALSE]`，并在载入 primary 后加**朝向断言**：
```r
stopifnot(ncol(datExpr) == length(primary_lab), nrow(datExpr) < ncol(datExpr))
```

**bug-2 · permuted 注释与实现不符**：注释写「逐基因打乱」，实现是 `t(apply(datExpr, 1, sample))`（**按行=样本**打乱）。
两者都破坏共表达，但只有 **per-gene 版**（`t(apply(datExpr, 2, sample))`，保持每个基因的表达分布）才是标准零模型。

**附带**：打日志时把 `nrow()`（=samples）写成 `"genes"` 标签也会误导排查（v1 打出过 `99 genes x 99 mc`，矩阵其实是对的）。
**行=样本、列=基因，日志标签必须与之一致。**

- 判定用 `ari()` 手写实现 + best-match Jaccard（避免依赖 mclust）
- 复跑脚本：`scripts/module_stability_ari.R`（**已于 2026-09-24 修掉上述两 bug + 加朝向断言 + 补 seed 变体**，可直接改基因集/参数复用）
- 明细与本会话完整数据（7 变体实测表 + bug 定位过程）：`references/module-credibility-and-figure-pitfalls.md`

## 关键教训：基因子集 ≠ 网络平坦
- ⚠️ 用 top3000 高变基因子集跑 WGCNA 会得到假平坦网络（R²=0.72@power1、单一 turquoise 模块）→ 误判"数据不适合 WGCNA"
- ✅ 改用**全部 WGCNA 基因（SetupForWGCNA fraction 0.05 → 10176）**后：power=10 R²=0.982，拆出 11 模块
- 教训：WGCNA 必须用完整基因集（或至少 >5000 基因），子集实验只用于参数预探
- ⚠️ 拆模块失败排查顺序：先换完整基因集重跑，再下"低异质性/均质"结论——NMF 可作互补验证（见 `references/limitations-and-literature.md`），但不可作为跳过完整基因集尝试的理由

## 环境备注（本机）
- R 4.4.2 在 `C:/Users/23136/AppData/Local/R/R-4.4.2/`，可执行文件必须写全 **`bin/x64/Rscript.exe`**（⚠️ 2026-09-24 修正：本文档原写"execute_r 和 PATH 的 Rscript 用这个"已过时 —— execute_r 内核实际跑 **R 4.5.3**，见坑 #9；Program Files 下只有 4.5.3/4.6.1，其中 R 4.5.3 的 Matrix.dll 已损坏——`loadNamespace` 任何依赖 Matrix 的包都会报 LoadLibrary failure，遇此直接用 `C:/Users/23136/AppData/Local/R/R-4.4.2/bin/Rscript.exe` 跑参数核实/诊断脚本）
- hdWGCNA 0.4.12 + WGCNA 1.74 + enrichR 3.4（.onAttach 联网不可达）已装进 AppData 库
- 网络：GitHub raw/codeload 有时可达，github.com 页面 curl 常 reset——R 包安装优先 pak 或已缓存

## 验证
- 🔴 **出图验收纪律：文件大小不是空白图的判据**。本次实测：2.4KB 树状图 = 真空白；**12KB 的 ModuleFeaturePlot 也是空白**（99.8% 为单一背景色，只渲染出 1 个词）；而 46KB/463KB 才是正常图。凡 `< 8KB` 一律先判 SUSPECT-BLANK；图集交付前**必须**用 `vision_describe(image_path=...)` 抽查关键图（看"主色占比 + 检出元素数 + OCR 文本"），空/黑底图一律删掉重做，不许交付
- ad-hoc 验证模式：Temp 目录写 hermes-verify-*.R，独立重算关键统计量（如 blue~Aging cor），结果持久化到 log/verify_*_status.txt 后清理临时脚本
- 独立重算示例：cor(GetMEs(obj)[,"blue"], aging_vector) 与 CSV 中 all_cells.blue Aging 值对比，误差 <0.02 通过


## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| 错误于 paste(signif(as.numeric(datExpr), 12), collaps | hdWGCNA 存进 Seurat 对象的 misc$<wgcna_name>$ | 在读取后立即 datExpr <- as.matrix(datExpr); storage.mode |
| ModuleUMAPPlot: The total size of the 3 globals ex | hdWGCNA 的 ModuleUMAPPlot / HubGeneNetwor | 在出图脚本开头加 options(future.globals.maxSize = 8*1024^3 |
| numbers of columns of arguments do not match (v1)  | 未定位完结（待 trace 结果）。已知排除项: mtc 数据结构正常、as.t | 诊断三步: ① 实测数据结构(phase3_mtc.rds: mtc$cor/pval/fdr 均为 |
| bash: fork: retry: Resource temporarily unavailabl | 0xC0000142 (STATUS_DLL_INIT_FAILED) 与 fo | 待处理：怀疑系统进程/句柄或内存耗尽（多管道 grep/grep/grep/head 加剧 fork |
| R exited with code 3221225794 (0xC0000142 STATUS_D | 待定：0xC0000142 是 Windows DLL 初始化失败码，出现在加载 | 定位中：怀疑 library(WGCNA) 或 loadNamespace("hdWGCNA") 触 |


## References
- 官方 tutorial: https://smorabit.github.io/hdWGCNA/articles/basic_tutorial.html
- hdWGCNA GitHub: https://github.com/smorabit/hdWGCNA
- `references/limitations-and-literature.md` — WGCNA/hdWGCNA 局限性文献核实版（19 条已核实 PMID/DOI：dropout 伪共表达、伪重复、共表达≠因果、metacell 聚合局限、NMF 适用边界判据、Zsummary 假阳性控制阈值、关键文献速查；2026-08-14 调研产出）
- `references/wgcna-vs-hdwgcna-parameters.md` — WGCNA vs hdWGCNA 官方参数默认值全量核实表（v1.74/0.4.12 已装包签名 + CRAN 手册 + 官方 vignettes/论文/FAQ）：含误区纠正（mergeCutHeight 0.15 非 0.25、minModuleSize min(20,ncol/2) 非 30、networkType unsigned vs signed、WGCNA 无 pickSoftThresholdFromBootstrap、metacell 数量无字面 >500 声明）、全参数对比表、适用场景速判、来源清单
- `references/module-credibility-and-figure-pitfalls.md` — 模块可信性判定实操档案（FDR 不对称指纹、**稳定性协议 7 变体完整实测表 + 判定结论**、**split-half 维度 bug 的指纹与修复**、permuted 零模型的正确读法（看 grey 占比而非模块数）、脏数据/类型不一致崩溃的完整 trace 定位过程、`future` 作为可选依赖包的登记）
- `scripts/module_stability_ari.R` — 可直接复用的模块稳定性评估脚本（ARI + best-match Jaccard；reproduce 对照 / permuted 严格零模型 / **split-half 按行分半** / 参数变体 / seed 对照，含 `stopifnot` 朝向断言，结果增量落盘 CSV）。**2026-09-24 已修掉 v1 自带的两个静默 bug**（ncol 分半、permuted 打乱方向）

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | skeletal_muscle | aging | 2026-09-24 | probe_MF120_structure.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | probe_MF120_reductions_layers.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | locate_hdwgcna_kernel_Rversion.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | env_canonical_r_versions.json | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | verify_R442_x64_Rscript.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_phase1_metacell_grid.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_debug_metacells.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_phase1_v2.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_probe_metacell_source.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_phase1_v3.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | probe_system_resources.sh | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | run_phase1_v4_logged.sh | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_phase1_v4.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_phase2_3_network_traits.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_phase2_3_network_traits.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase2_3_network_traits.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase3b_fdr_export_v5.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase5_stability.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase5_stability.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase6_figures.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase6_diag.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase6_figures_v2.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase6_figures_v3.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase6_figures_v4.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase6_figures_v5.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase6_figures_v5.R | - | - |  |
| - | - | - | 2026-09-24 | hdwgcna_phase6_figures_v6.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_phase5b_stability_fix.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_phase5d_probe_datExpr.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_phase5d_probe_datExpr.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_phase5d_zero_model_final.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | env_check_R_root_cause_diag.txt | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | hdwgcna_phase5d_zero_model_final.R | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | external_evidence_wgcna_faq+refs.txt | - | - |  |
| human | skeletal_muscle | aging | 2026-09-24 | europepmc_abstract_5refs_extract.py | - | - |  |
