# 模块可信性判定 + 图集坑 · 实操档案

来源：2026-09-24 MF_120 会话（human skeletal muscle / aging / 120 细胞 × 51,227 基因 Seurat v5）
环境：Windows + R 4.4.2（`bin/x64/Rscript.exe`）+ hdWGCNA 0.4.12 / WGCNA 1.74 / Seurat 5.5.0

---

## 一、本次 primary 配置与产出

| 项 | 值 |
|---|---|
| metacell | `MetacellsByGroups(k=5, group.by="type", min_cells=5)` → **37 metacell** |
| 基因集 | `SetupForWGCNA(fraction=0.05)` → **11,116 基因** |
| 软阈值 | power=9（fraction 0.05 时 max R²=0.986；fraction 0.10→power14 R²=0.931；0.25→power17 R²=0.893） |
| 建网 | `ConstructNetwork(soft_power=9, networkType="signed", TOMType="signed", TOMDenom="min", minModuleSize=50, mergeCutHeight=0.2, deepSplit=4, pamStage=FALSE, randomSeed=12345)` → **13.1 min** |
| 模块 | **57 非 grey**（+ grey 未分配 4,465 基因），规模 50–302 |
| 关联 | `ModuleTraitCorrelation(traits=18, features="hMEs", cor_method="pearson")`，`ModuleEigengenes(group.by.vars=NULL)`（理由：目标性状就是分组变量本身，按 type 做 Harmony 会把要检验的衰老信号一并消除 = 循环消除） |

🔑 **基因:样本比 = 11,116 : 37 ≈ 300:1** —— 这是本次一切「不可重复」现象的总根源，选 primary 时就要意识到。

---

## 二、🔴 高危信号：FDR 显著性的极不对称分布

| group | FDR<0.05 | 检验数 | 占比 |
|---|---|---|---|
| **all_cells** | **270** | 1026 | **26.3%** |
| RSS | 43 | 1026 | 4.2% |
| Pure Type IIX | 18 | 1026 | 1.8% |
| Pure Type IIA | 5 | 1026 | 0.5% |
| OTUD1+(I) | 3 | 1026 | 0.3% |
| Pure Type I | 2 | 1026 | 0.2% |
| LRP1B+(I) / OTUD1+(II) / RP_high(I) / RP_high(II) / Specialized MF | 0 | 1026 | 0% |
| 合计 | 341 | 11172 | 3.05% |

最强命中：`scoreI_AUC ↔ darkolivegreen` r=0.87 · `scoreSarcomeric_AUC ↔ lightyellow` r=0.71 · `Aging ↔ lightpink4` r=−0.64 · `Age_num ↔ lightpink4` r=−0.62 · `Aging ↔ blue` r=−0.58 · `Diabetes ↔ white` r=−0.55。

**为什么这是高危信号（三重可疑）**
1. **过分割指纹**：37 metacell 拆出 57 模块（模块数 > 样本数），`deepSplit=4` + `minModuleSize=50` 在小矩阵上会把噪声切成等大碎块（模块规模高度均一 50–302 也是迹象）。
2. **循环性**：hME 与性状都在同一批 37 个 metacell 上计算，模块本身就是"共表达"定义出来的 → 与定义它的 AUCell 打分高度相关（如 scoreI_AUC r=0.87）近乎同义反复，不能当作生物学发现。
3. **功效不对称**：all_cells 用全部 37 metacell（功效最高）而亚群内只有部分 meta cell；但 26.3% vs 0–4.2% 的落差远超功效差异能解释的范围。

**处置纪律**：此状态下**不得**输出"某某模块与衰老显著相关"的结论，必须先过稳定性协议（见 SKILL.md「模块可信性判定」节 + `scripts/module_stability_ari.R`），再由 L2 辩论定稿。

---

## 三、稳定性协议实测结果（2026-09-24 完成，7 个变体）

| 变体 | 说明 | 非grey模块 | grey 基因 | **ARI vs primary** | mean Jaccard | Jaccard≥0.5 |
|---|---|---|---|---|---|---|
| **[0] reproduce** | 同 datExpr 重跑 | 56 | 4651 | **0.9515** | 0.9657 | **56/57 (98.2%)** |
| [1] permuted | 打乱共表达（零模型） | **37** | **524** | 0.0000 | 0.0171 | 0/57 |
| [2] split-half odd/even | ⚠️ **v1 实现错误，见第四节** | 33 / 26 | 2023 / 1592 | 0.2061 / 0.1456 | 0.1943 / 0.1640 | 1/57 |
| [3] k3_type | metacell k=3 (98 mc) | 47 | 3979 | 0.0825 | 0.1095 | 0/57 |
| [3] k3_L3 | L3 分组 k=3 (99 mc) | 49 | 4403 | 0.0449 | 0.0635 | 0/57 |
| [3] k5_L3 | L3 分组 k=5 (24 mc) | 65 | 2575 | 0.0176 | 0.0443 | 0/57 |
| [3] single_cell | 120 细胞直接建网 | 27 | 7744 (70%) | 0.0237 | 0.0481 | 0/57 |

**判定**：除 [0] 外**全部扰动变体 ARI ≤ 0.21、mean Jaccard ≤ 0.19、Jaccard≥0.5 的模块仅 0–1/57**
→ 模块划分对参数极度敏感，**不得据此输出性状关联结论**（降级为探索性描述 / 明确判定该数据集不适用）。

### 🔴 [1] permuted 的正确读法（本次最重要的方法学收获）

**别用「打乱后模块数变少」当判据 —— 它不会变少。**

实测打乱共表达后**仍产出 37 个非 grey 模块**，但 **grey 从 4651 掉到 524**。也就是说：

- 在 300:1 的基因:样本比下，WGCNA 会把基因**硬塞进大量模块**，模块数完全不能反映真实结构；
- **真正有信息量的是 grey 占比**：primary 留 4651 grey、零模型只留 524 → 真实数据的"难以归类"比例反而更高；
- 结论：**「模块数多」在极端维度下不构成信号证据**，能定论的只有 [2][3][4] 的一致性。

### 🔑 [0] reproduce 只有 0.9515，不是 1.0 —— 怎么解读

同 datExpr、同参数、同 randomSeed 重跑，ARI 仍只有 0.9515 → **`ConstructNetwork` / `blockwiseModules` 有固有随机性**（TOM 分块处理 + PAM 阶段）。

- ✅ 0.95 / Jaccard 0.966 / 56-57 模块 Jaccard≥0.5 = **复现管线与 hdWGCNA 的确等价**，[1]-[4] 的比较成立；
- ⚠️ 别把它判成"复现失败"。要区分"实现差异"和"固有随机性"，看 [4]（本次补跑）seed999 对照。

参数对齐实证（`ConstructNetwork` formals 原文，逐项抄进变体调用）：
```
maxBlockSize=30000, randomSeed=12345, corType="pearson", networkType="signed",
TOMType="signed", TOMDenom="min", deepSplit=4, pamStage=FALSE,
minModuleSize=50, mergeCutHeight=0.2
```
判据 `ari()` 与 `jac_stats()` 手写实现（不依赖 mclust）：见 `scripts/module_stability_ari.R`。

---

## 四、🔴🔴 split-half 的维度 bug：日志数字与文本标签对不上 = 指纹

**v1 实现（错的）**：
```r
idx <- if (half == "odd") seq(1, ncol(datExpr), by = 2) else seq(2, ncol(datExpr), by = 2)
cH  <- runBlock(datExpr[, idx, drop = FALSE], ...)     # 取【列】
# 标签还写着: sprintf("%s 半(%d samples)独立建网", half, length(idx))
```

`ncol(datExpr)` = **基因数 11116**，`datExpr[, idx]` = 取列 → **实际切成「基因对半分」**，
根本不是「metacell 对半分」。整个 [2] 变体无效，`length(idx)` 打出的 `5558 samples` 是假的。

**指纹（一眼识别法）**：
```
半样本 odd: 5558 metacells        ← 5558 = 11116/2（基因数一半）
```
primary 只有 **37** 个 metacell —— 任何 >37 的"metacell 数"都不可能真。**凡日志里的数字与其文本标签矛盾，立刻回查 `nrow`/`ncol` 与 `[i, ]`/`[, j]`。**

**修复**：
```r
idx <- if (half == "odd") seq(1, nrow(datExpr), by = 2) else seq(2, nrow(datExpr), by = 2)
cH  <- runBlock(datExpr[idx, , drop = FALSE], ...)     # 取【行】
```
并在载入 primary 后立刻加**朝向断言**（防复发，已写进脚本）：
```r
stopifnot(ncol(datExpr) == length(primary_lab), nrow(datExpr) < ncol(datExpr))
```

**同族 bug-2**：`permuted` 注释写「逐基因打乱」，实现却是 `t(apply(datExpr, 1, sample))` ——
`apply(..., 1, ...)` 是**按行=样本**打乱。两者都破坏共表达，但只有 **per-gene 版**
（`t(apply(datExpr, 2, sample))`，保持每个基因的表达分布）才是标准零模型。已修正。

**修复版验证证据**（Phase 5b 日志，LOG 确认朝向正确后才继续）：
```
primary datExpr: 37 samples(metacell) x 11116 genes
  （显式校验通过: 列数==模块标签数, 行数<列数 -> 朝向正确）
  半样本 odd: 取第 1-37 个 metacell, 共 19 个 | 子矩阵 19 samples x 11116 genes
```
⚠️ 修正版的 split-half 数值 + permuted_gene + seed999 三变体当时仍在跑（约 25 min），**不要凭 v1 的错误数值下结论**。

**附带小坑**：日志标签写错也会误导排查 —— v1 用 `TR(tag, ": ", nrow(r$de), " genes x ", r$n_mc, " mc")`
把**行数（samples）打成了 "genes"**（打出 `99 genes x 99 mc`），矩阵本身正确但读日志时极易误判成又一次转置事故。**打日志时行=样本、列=基因，标签必须与之一致。**

---

## 五、"连崩 3 版"的完整定位过程（可复用调试范式）

**现象**：同一个 FDR 导出脚本连崩三版 —— v1/v3 报 `numbers of columns of arguments do not match`、v2 报 `cannot coerce to a table`，且 `execute_r` **报错时不回传 stdout**，`cat()` 打点全部丢失，无法定位。

**排除顺序（先证伪，再定位）**
1. 读对象结构：`mtc$cor/pval/fdr` 均为 11 组 × 18 traits × 57 modules 的 matrix，`str()` 输出完全正常 → 排除"对象坏了"。
2. 隔离测试每个可疑操作：`as.table(matrix(1:6,2,3))` ✅、`data.frame(rep/as.vector)` ✅、`rbind` ✅、`as.data.frame(as.table())` ✅ → 排除"函数不可用"。
3. **改用磁盘 trace**（关键转折）：全程 `TR <- function(...) cat(..., file=con, sep="")` + `flush(con)`，每步包 `tryCatch` 且失败写 `FAIL@<step>` 后 `quit(status=1)` → **一次定位**：
   ```
   各 df 列数: 62,6,6,6,6,6,6,6,6,6,6     ← all_cells 组 62 列，其余 6 列
   FAIL@rbind: numbers of columns of arguments do not match
   ```
4. 逐组打印 `class(cor) / class(pval) / class(fdr)` → `all_cells` 的 **fdr 是 data.frame**，其余 10 组是 matrix。根因闭合。

**可复用范式**：在 `execute_r`（或任何"出错吞 stdout"的执行器）里调试，**不要靠 cat 打点，一律把 trace 写文件 + flush**，并把每一步包 tryCatch 记录 `FAIL@<step>`；再配上"隔离测试每个基元操作"的证伪步骤。

---

## 六、可选依赖包登记

`future` 不是 hdWGCNA 主流程必需，仅用于放宽并行传输上限（ModuleUMAPPlot / HubGeneNetworkPlot 会传 ~0.99 GiB 的 hME 邻接矩阵，默认 `maxSizeOfObjects = 500 MiB` 必炸）。已在 SKILL.md frontmatter 的 `r_packages` 声明，避免后续 `rail_review` 重复报 `UNREGISTERED_PACKAGES`。

---

## 七、图集交付清单（本次定稿 11 张）

3 张软阈值（fraction 0.05/0.10/0.25）+ `module_dendrogram`（46KB，WGCNA 底图 API）+ `module_trait_heatmap`（463KB，label=fdr 带星号）+ `kMEs`（222KB）+ 4 张 `hubnetwork_*`（38–56KB，显式 png 包裹）+ `hME_dotplot`（55KB）+ `hME_boxplot_by_group`（33KB）+ `module_featureplot`（52KB，Seurat 原生 FeaturePlot）。
被否掉的：`PlotDendrogram` 直接输出（2.4KB 空白）、`ModuleFeaturePlot`（12KB 空白）、`ModuleUMAPPlot`（0.4.12 内部 `参数长度为零`，放宽 future 上限后仍失败）——三者均替换为等价可用的官方/原生图型，未留白图。

## 八、L2 辩论用文献锚点（实测检索所得 PMID，可直接引用）

| 文献 | 用途 | PMID / DOI |
|---|---|---|
| Morabito et al. 2023, Cell Rep Methods — hdWGCNA 原文 | 方法学基线 | 37426759 / 10.1016/j.crmeth.2023.100498 |
| Baran et al. 2019, Genome Biol — MetaCell | metacell 构建原理（k-NN 图分区） | 31604482 / 10.1186/s13059-019-1812-2 |
| Zhang & Zhu 2025, PLoS Comput Biol — 文库大小稳定化 metacell | **metacell 质量直接影响共表达网络分析** | 41231963 / 10.1371/journal.pcbi.1013697 |
| Langfelder & Horvath 2008, BMC Bioinformatics — WGCNA | 软阈值/网络构建 | 19114008 / 10.1186/1471-2105-9-559 |
| Langfelder et al. 2011, PLoS Comput Biol — 模块 preserved & reproducible | **模块可重复性统计框架（Zsummary）** | 21283776 / 10.1371/journal.pcbi.1001057 |