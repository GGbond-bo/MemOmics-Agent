---
name: hierarchical-annotation-rollup
description: 层级注释的双向规程：①向上回填/对账——把亚群（L2）注释按 barcode 打回大群（L1/Celltype）对象前，先用父对象频数表建基准做细胞数对账，并核实各亚群对象的 L2 列名与标签清单；②向下细分——在已注释的子集内用经典 marker 做更细的 L3。触发：打回亚群/L2注释回填/level2打回大群/亚群细胞数对不对得上/小群注释合并/annotation_L2 合并/层级注释/大群细分亚群/Level3注释/L3注释/更细颗粒度/注释更细致/EC pericyte 注释/亚群再细分。
when_to_use: 用户给出「一个父对象（含粗分类列）+ 每个大群一个亚群对象（含细分类列）」，要求核对细胞数、确认对应关系、列清单，或把细分类合并回父对象时；也适用于反向需求——用户给一个已注释的亚群对象，要求在子集内用经典 marker 做出比现有参考层更细的 L3（见铁律 9）。只要求「先调查确认」的核查轮同样适用（本 skill 的前 3 步就是核查轮的全部交付物）。
version: 1.1.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  memomics:
    tags: [annotation, hierarchy, subcluster, rollup, barcode-merge, reconciliation, scRNA]
    difficulty: intermediate
    language: R
    category: scRNA
prerequisites:
  r_packages: [Seurat, SeuratObject]
---

# 层级注释回填（亚群 L2 → 大群）

> 定位：这不是聚类，也不是注释——是**注释层级的合并与对账**。
> 上游 `scrna-clustering` 出「大群 + 各谱系亚群」，本 skill 负责把两者**对上、合起来、验得住**。

## 🔴 铁律 1：基准来自**父对象自己的频数表**，不是记忆、不是亚群反推

顺序错了（先合并、后核对）会把「细胞数对不上」变成事后返工。**第一步永远是拉父对象的粗分类频数**：

```r
tb <- sort(table(parent$Celltype), decreasing = TRUE)   # 父对象的粗分类列（L1）
print(tb); cat("total:", sum(tb), "\n")
```

拿这张表当**预期基准**，逐一对账每个亚群对象的 `ncol()`。

### 三件必答的事（用户核查轮的验收判据）

| # | 要答什么 | 怎么算 |
|---|---|---|
| 1 | **细胞数对得上吗** | 各亚群 `ncol()` 之和 ≈ 父对象**去掉被明确排除的类目后**的总数 |
| 2 | **对应关系对吗** | 逐个亚群对象归属哪个大群 —— 注意**可能不是一对一** |
| 3 | **L2 有哪些标签** | 逐对象打印 L2 列的 `table()`，标签清单给用户看 |

### ✅ 对账要做**六级**，只比 `ncol()` 是弱证据（2026-10-18 定案，六级全过）

只比细胞数**相等**有漏洞：两个不同的细胞集也可能恰好同数。真正能证明「对得上」的是 barcode 集合运算：

| 级别 | 算什么 | 本次实测 |
|---|---|---|
| ① 计数相等 | 亚群 `ncol()` == 父对象该大群细胞数 | ✅ 6/6 精确相等 |
| ② **barcode 交集** | `sum(bc %in% parent_bc)` | ✅ 6/6 = **100.0%** |
| ③ **反向覆盖** | `sum(parent_group_bc %in% bc) / 大群总数` | ✅ 6/6 = **100.0%**（无遗漏、无外来） |
| ④ **闭合校验** | Σ亚群 == 父总数 − 被排除类目 | ✅ 603,817 == ≈60 万 − 427 |
| ⑤ **中间层交叉验证** | 亚群对象的中间层 `celltype` 频数 vs 父对象同名列 | ✅ 11/11 逐一相等 |
| ⑥ **两级加和自洽** | 对象内 L2 各族之和 == 该对象 `ncol()` | ✅ 5/5 对象全部闭合 |

②③ 才是「对得上」的硬证据（③ 特别重要：证明父对象该大群里**没有**落在任何亚群对象之外的细胞）。
⑤ 是**独立的第二信源**：父对象 `celltype`(11 类) 与亚群对象内同名中间列逐一相等 →
即使 barcode 维度出问题，计数维度也能交叉兜底。两个维度同时过，才敢说「完全闭合」。

⚠️ **「去掉脂肪细胞」这类用户口径要照抄进算式**：实测父对象合计 ≈60 万，用户明确排除 Adipocyte(427)
→ 对账目标数是 **603,817**，不是 ≈60 万。拿错基数 = 差 427 就误判「对不上」。

⚠️ **亚群对象与大群不是一对一**：实测 `Vascular cells`（19,685）对应的是
**EC_pericyte 一个对象**（EC 11,472 + Pericyte 8,213 = 19,685），而父对象另有一列 11 类的 `celltype` 里
EC/Pericyte 是分开的。判定归属要看**列取值**，不要按对象名猜。

## 🔴 铁律 2：同一父对象常有两套粗细分类列，只差大小写 —— 别混用

实测该父对象 meta.data **同时**有：

- `Celltype`（6 类）= 用户口中的「大群」：Muscle fibers / Stromal cells / Immune cells / Vascular cells / Muscle stem cells / Adipocyte cells
- `celltype`（11 类）= **细一级**：TypeII / TypeI / FAP / MuSC / RSS / Myeloid / EC / Pericyte / Lym / MastCell / Adipocyte

`$Celltype` 与 `$celltype` **只差一个字母大小写**，写错就静默用错层级（不报错、结果看着还挺合理）。
→ 动手前 `table()` 两列**并排打一次**，确认自己用的是哪一层，并把「我用的哪列」写进交付说明。

同类风险还有 `Annotation`(10) / `Annotation_Level1`(6) / `leiden_*`(纯簇号，无生物学命名)。
**纯簇号列（`leiden_1`/`SCT_snn_res.*`）不能当注释交付**，只能当聚类层。

## 🔴 铁律 3：L2 列名**不要假定**，逐文件实测后如实报差异

用户说「里面应该都有一列 `annotation_L2`」——**「应该」= 待验证**。

```r
cat(paste(colnames(obj@meta.data), collapse = ", "), "\n")
grep("annotation|Annotation|Level|level|celltype|Celltype", colnames(obj@meta.data), value = TRUE)
```

### ⚠️ 实测结论：6 个对象里**只有 3 个**用 `annotation_L2`（2026-10-18 普查定案）

早前一轮只看到 `MuSC` 有 `annotation_L3` 就记下「MuSC 的列名是 L3、不是 L2」——**该结论是错的**：
完整普查显示 MuSC **同时有** `annotation_L2`(2 类) 和 `annotation_L3`(6 类)。
**「有 L3」不等于「没有 L2」**；`colnames()` 必须看全，别看到一列就下结论。

| 亚群对象 | 实际 L2 列名 | 类数 | 同对象其他层级 |
|---|---|---|---|
| `MF_clean_annotation_umap.rds` | `annotation_L2` | **3** | `annotation_L3`(10)、`annotation`(5)、`celltype`(3) |
| `MuSC_exercise_clean_dele_cluster_umap.rds` | `annotation_L2` | **2** | `annotation_L3`(6)、`annotation`(4) |
| `Immune_exercise_clean_umap.rds` | `annotation_L2` | **8** | `annotation_L3`(17)、`First_Annotation`(16) |
| `EC_pericyte_exercise_clean_annotated.rds` | ⚠️ 普查当时**无** `annotation_L2` → 用 `annotation` ｜**2026-11-05 复验已变**：重新注释后 `annotation_L2` 存在、`annotation` 消失（见铁律 9.2） | 5 | `celltype`(2) |
| `FAP_clean_annotation.rds`（user） | ⚠️ **无** `annotation_L2` → 用 `Annotation` | 6 | `annotation`(4) |
| `FAP.rds`（liuyuxuan3） | ⚠️ **无** `annotation_L2` → 用 `Annotation_Level2` | 4 | `Annotation`(4)、`annotation`(4) |

**推论（回填脚本必据）**：按单一列名 `annotation_L2` 取列 → **EC / FAP 三个对象整列取空**，
且**不报错、不成 NA，只是没有值**——是最难发现的一类静默失败。
回填必须走**显式映射表**（对象名 → 真实列名），并加守卫：

```r
if (!col %in% colnames(obj@meta.data)) stop("列名映射过期：", nm, " 没有 ", col)
if (anyDuplicated(rownames(md))) stop("barcode 重复")
```

→ 列名对不上时**先把差异报给用户**（哪个对象用哪列、标签是否同构），
**不要**自己 map 一个「最像的」，也**不要**假定两个对象可以无条件 `rbind` 标签。

### ⚠️ 分支：「L2」不一定是最细层 —— 先确认用户要的粒度

`MF` 的 `annotation_L2` 只有 **3 类**（Type I / Type II / non-canonical MF），明显偏粗；
它的 `annotation_L3` 才有 **10 类**（Subtype A / RUNX1+ / RP_high(I) …）。
所以「打回 L2」到底是 3 类还是 10 类，**取决于用户要的粒度，不能由列名替用户决定** ——
交付时把两条都列出来让用户挑（本次即如此：MF 3 类 vs L3 10 类）。

### ⚠️ 分支：同一批细胞、两个文件、两套 L2 **粒度不同** → 必须用户拍板

本次 FAP 两个候选**细胞数完全相同（各 39,727、barcode 同集）**，但 L2 划分不同：

| user `FAP_clean_annotation.rds`（6 类） | liuyuxuan3 `FAP.rds`（4 类） |
|---|---|
| MME+ FAP 19,098 / CD55+ FAP 12,482 / GPC3+ FAP 3,062 | MME+ FAP 20,158 / CD55+ FAP 11,589 |
| Hybrid 2,797 / Fibroblast-like cell 1,321 / RUNX2+ FAP 967 | GPC3+ FAP 6,905 / TNC+ FAP 1,075 |

→ 这**不是**「选个文件」，而是**选一套注释方案**（粒度/类目都不同）。
别按日期新或文件名顺眼自行挑 —— **`ask_user` 给选项让用户定**（细胞数相同，无法用数据判优劣）。

✅ **本次已定案（2026-10-18 用户勾选）**：用 `liuyuxuan3/Muscle/FAP.rds` 的 `Annotation_Level2`（4 类），
user 6 类版弃用 ⇒ 回填脚本 FAP 列名写 `Annotation_Level2`，**不要回退到 `Annotation`**（那是被弃那套口径）。

## 🔴 铁律 4：一个探针脚本 + 后台作业拿全，不要逐个交互式读

对象常有 20 GB 级（实测 `MF_clean_annotation_umap.rds` 23.5 GB），逐个 `readRDS` 交互式读会把
常驻会话内存吃满、且每读一个都要等几分钟。

- 集群上的做法：**一个脚本循环遍历全部对象**（`dim` + meta 列 + ≤80 唯一值的列频数 + 落 meta CSV）
  → `push` → `submit` 成后台作业 → 产物落工作盘 → 跨节点读日志/产物（见 `remote-cluster-execution` 铁规 12.1/12.3）。
- **脚本开头必加**（Seurat v4/v5 混放会差异式失败，v4 不加载 Seurat 就 `unable to find required package 'Seurat'`）：
  ```r
  if (requireNamespace("Seurat", quietly = TRUE)) suppressPackageStartupMessages(library(Seurat))
  ```
- **顺手落 meta CSV**（含 `barcode <- rownames(md)`）：后续合并/画图直接用，省一次全量重读。
  608,244 细胞对象的 meta CSV ≈ 360 MB，可接受。

## 🔴 铁律 5：回填按 **barcode**，不按行号；落回后跑三条守卫

亚群是 subset 出来的，**行序与父对象不同**，按行号合并 = 错配。合并键 = `rownames(meta.data)`（barcode）。

落回父对象后三条守卫，全过才算完成：

1. **非 NA 数** = 计划回填的细胞数（例：`sum(!is.na(parent$annotation_L2))`）；
2. **不跨行**：`table(parent$Celltype, parent$annotation_L2)` 里每个 L2 标签只应出现在它对应的父类目下，
   其他行必须为 0（出现非零 = 归属错配 / 有重叠 barcode）；
3. **总数不变**：`ncol(parent)` 合并前后一致（合并只加列，不筛细胞）。

⚠️ **「无 L2 来源的类目」怎么填 —— 问用户，别自己拍**：父对象里有的类目可能**没有任何亚群对象覆盖**
（本次 `Adipocyte cells` 427 细胞 = 0.07%）。两条合法口径：① 填自身群名（不丢细胞、不污染其他亚群 = 推荐默认）
② 留 `NA`。这决定交付表里有几类、NA 多少，**是口径不是细节** ⇒ 与同类决策（如 FAP 择一）**并进同一个
`ask_user` 表单**一次问完，不要拆成两轮。

⛔ 不要用 `dplyr::recode` 之外的手工 map 拼字符串：`recode` 未命中值**原样保留、不产生 NA**，
所以 `anyNA()` 守卫**抓不到漏映射** —— 守卫必须写 `%in%` 集合判定
（`stopifnot(all(vals %in% allowed))`）。

### ✅ 铁律 5.1：回填必带**溯源列** + 落三张对账表（2026-10-18 投递定案）

一次合格的回填**不只加一列标签** —— 同时加一列 **`L2_source`**（逐细胞记录这条 L2 来自哪个亚群对象 /
哪个占位来源）。否则过几天没人说得清某个标签是谁给的、哪一版口径。落盘产物四件套：

| 产物 | 内容 | 去处 |
|---|---|---|
| `<父对象>_annotation_L2_umap.rds` | 父对象 + `annotation_L2` + `L2_source`（细胞数不变） | **留集群**（实测 7 GB 主对象） |
| `annotation_L2_freq.csv` | L2 标签频数 → **这份就是给用户看的\"23 个标签细胞数清单\"** | `pull` 回 `results/<sid>/` |
| `L2_vs_L1_check.csv` | `table(L1, L2)` 交叉表 = 铁律 5 第 2 条守卫的可视化版（非零只该出现在对应行） | `pull` 回 |
| `L2_mapback_audit.csv` | 逐来源对象审计：对象 → 实测列名 → 细胞数 → 命中数 | `pull` 回 |

⛔ 后三张是**交付物不是调试垃圾** —— 跑完一并 `pull` 回本机（WebUI 只能浏览 work//results/），
父对象与 20 GB 级亚群对象留集群。耗时参照：读 7 GB 父对象 + 23.5 GB MF ⇒ **单作业 60–90 分钟**，
按长任务办（落地进程 + 落盘日志 + 一次阻塞等待，见 `remote-cluster-execution` 铁规 6.2/6.3）。

✅ **本次已定案（2026-10-18 用户勾选，后续同类直接沿用）**：
`Adipocyte` 427 细胞**填自身群名**（不丢细胞、不留 NA）；FAP 用 `liuyuxuan3/Muscle/FAP.rds` 的
`Annotation_Level2`(4 类) ⇒ 父对象最终 **23 个 L2 标签**
（MF 3 + MuSC 2 + EC 5 + FAP 4 + Immune 8 + Adipocyte 1），全部走**显式映射表**取列
（MF/MuSC/Immune → `annotation_L2`；EC → `annotation`；FAP → `Annotation_Level2`）。

## 🔴 铁律 6：核查轮的交付形态

用户说「**我只需要你确认这些信息**」时：交付 = 上面对账表 + 归属对照 + 每对象的 L2 标签清单 + 发现的差异。
⛔ 不要顺手生成研究方案/技术路线图/文献综述（即使系统路由提示了别的方向）——
**用户显式限定的范围优先于自动路由**。纯核查也**不要**弹意图确认表单（只读）。

## 🔴 铁律 7：回填作业的「执行期判读」—— saveRDS 阶段**没有进度行**，别判它卡死（2026-10-18 实测）

回填投出去之后，日志与磁盘的唯一可信时间线长这样（实测 node1 / PID 133910 / R4.41）：

| 时刻 | 日志 | 磁盘 | 该判什么 |
|---|---|---|---|
| T+0~10min | 读父对象中，`ps` 的 RSS 从 19.9 GB 涨到 37 GB | 只有脚本 | 在推进（RSS 单调上涨） |
| T+10min | 23 个 L2 标签的频数表**一次性打完** | 4 张小产物落盘（freq / audit / check + 标签向量 rds） | **计算部分已完成，当场可对账** |
| T+10min 起 | 末行 `#TASK:STAGE 保存对象`，**之后不再有任何输出** | `<父对象>_..._annotation_L2_umap.rds` 从 0 开始涨 | **正在 saveRDS，不是卡死** |

- ⛔ **不能用「日志没有新行」判失败/停滞**：`saveRDS` 全程静默，7 GB 级对象写盘要几十分钟。
  判据是**产物体积在增长**（实测 ≈160 MB/min ⇒ 7 GB 约 40 min）＋ `ps -o etime,pcpu,rss` 仍 ~100% CPU。
- 📏 **ETA 的参照物 = 原始父对象的体积**：同目录 `ls -lhL *.rds`（**glob，不点名单个大文件路径**，
  否则会被持久化硬闸拦下，见 `remote-cluster-execution` 铁规 10）拿到父对象实测 7.1 GB。
  新对象只多加一列字符 ⇒ 最终体积应与它同量级；涨到 654 MB 时只走了 ≈9%。
- ✅ **频数表打完就先把对账交付掉**，不必等 rds 写完：三张小产物已在盘上，逐 L1 群加和是否等于该群细胞数
  当场可验（本次 23 个标签加和 = ≈60 万 完全闭合、5 个亚群对象 barcode 匹配 100%）。
- 收尾核验（rds 写完）按铁律 5 三条守卫 + 铁律 5.1 四件套；`pull` 只拉**小表**
  （freq / audit / check / 脚本 / 日志），GB 级主对象留集群。
- 汇报形态（用户在跑动中最想要的就是这个）：**三源交叉（进程 / 日志 / 磁盘）+ L1→L2 加和闭合表**，
  而不是一句"还在跑"。

## 🔴 铁律 8：回填收尾 = **读回对象跑四条断言**，不是「日志说 ALL DONE 就交付」（2026-10-18 实测）

作业打 `=== ALL DONE ===` + 新 rds 体积与父对象同量级 ⇒ 只证明**写完了**，不证明**写对了**。
收尾必须再投**一个只读验证作业**读回 rds（实测 7 GB / ~2 min），跑四条断言：

```r
obj <- readRDS(F)
stopifnot(ncol(obj) == 600000)                       # ① 细胞数不变（只加列不筛细胞）
stopifnot(sum(is.na(obj$annotation_L2)) == 0)        # ② 无 NA（Adipocyte 占位也必须填）
stopifnot(length(unique(obj$annotation_L2)) == 23)   # ③ 标签数 = 计划数
tb <- table(obj$Celltype, obj$annotation_L2)         # ④ 每 L1 群内 L2 加和 == 该群细胞数
stopifnot(all(rowSums(tb) == as.integer(table(obj$Celltype))))
```

四条全 PASS 才算完成（本次实测：≈60 万 / NA=0 / 23 标签 / 6 群加和全等）；逐条写进
`verify_report.txt`（列 PASS/FAIL）并 `pull` 回 `results/<sid>/`。

⚠️ **验证作业的解释器写 `<conda_env>/bin/Rscript`，别写 `lib/R/bin/exec/R`** ——
后者实测报 `R home directory is not defined`（直接执行 R 前端需要 `R_HOME`），改
`…/miniconda3/envs/R4.41/bin/Rscript` 一次通过。同类坑见 `remote-cluster-execution` 铁规 2。

### ✅ 铁律 8.1：出图**不要重读 GB 级父对象** —— 抽一次精简坐标 CSV，之后在本机迭代

画 L2 UMAP 属于「版式要改好几轮」的活（用户习惯一次要 3–4 个变体挑）。
每轮都 ssh 读 7 GB 对象 = 每轮 10+ 分钟；正确做法是**一次导出、本机迭代**：

```r
# 集群一次性导出（跟着验证作业同一次跑完即可）
write.csv(data.frame(barcode = colnames(obj),
                     UMAP_1 = emb[,1], UMAP_2 = emb[,2],
                     annotation_L2 = obj$annotation_L2, Celltype = obj$Celltype),
          "coords_L2.csv", row.names = FALSE)   # 604k 行 ≈ 40–60 MB，可 pull
```

之后**本机**（matplotlib/R）反复出图：改配色/字号/标签位置都是秒级，不再 ssh、不再 `readRDS`。
⚠️ 只有「要看表达量/重算降维」时才回原对象；纯版式迭代永远用这份 CSV。

### ⚠️ 铁律 8.2：UMAP 上打 23 个簇名的版式约束（小簇重叠是必然，先设计再画）

604k 细胞 × 23 标签里，小簇（Adipocyte 427、B cell 442、NKT 731、SMC 834、TNC+ FAP 1,075）
在 UMAP 上是几个像素的团；**质心直接标名一定互相压字**。三条可用策略（选一套，不要混着堆）：
① 质心 + 简单重叠消解（沿簇间方向推开）；② **引线标签**（簇内点 + 短线段 + 图外文字，最稳）；
③ 小簇并入图外编号/清单（图上只标大簇名）。
标名一律用**英文标签**（`annotation_L2` 原文值），中文只进图注（matplotlib 默认字体无 CJK 字形）。

## 🔴 铁律 9：反向操作 —— **向下细分（L2 → L3）** 与向上回填是两套规程

> 铁律 1–8 是「亚群注释往回打」（自下而上合并 + 对账）；本节是**反方向**：
> 用户给一个**已注释的亚群对象**（如 `EC_pericyte_..._annotated.rds` + 参考列），
> 要求在**该子集内部**用经典 marker 做出**比现有更细**的 L3 颗粒度。
> 顺序、对账口径、交付物都不同，套错会白跑一轮。

### 9.1 先定「L3 是本子集局部的，还是要合并回全局」——这是口径，不是细节

两条合法路径，产物完全不同，**不要自己挑**：

| 路径 | 做法 | 产物 |
|---|---|---|
| **A. 子集局部 L3** | 只在该谱系对象内命名，写 `annotation_L3` 新列 | 该对象的注释表 + UMAP/DotPlot |
| **B. 全局 L3 层级** | 局部命名后按 barcode 回填父对象（走铁律 5 全流程 + `L3_source` 溯源列） | 父对象新列 + 三条守卫 + 读回断言（铁律 8） |

→ 用 `ask_user` 一次问清（并进同一个表单，不要拆两轮）。用户要 B 时本 skill 铁律 5/5.1/8 全部适用。

### 9.2 用户口中的列名 ≠ 实测列名：**这一列会随「重新注释另存」出现或消失**，每次开工当场复验

实测底表（2026-10-18 普查）里 `EC_pericyte_exercise_clean_annotated.rds` **没有** `annotation_L2`，
细分类列叫 `annotation`（5 类）+ `celltype`(2 类)。而用户完全可能说「我已经注释了 `annotation_L2`，
可以作为你的参考」——**「我已经注释了 X」= 待验证，不是列名保证**。

🔴 **2026-11-05 复验：同一路径的文件已被重新注释另存，列名换了一套** ——

| 观测日 | 细分类列 | 类数 | `annotation` 列 | 对象规模 |
|---|---|---|---|---|
| 2026-10-18 | `annotation` | 5 | 存在 | 19,685 细胞 |
| **2026-11-05** | **`annotation_L2`** | **5**（CapEC 8588 / Pericyte 6879 / ArtEC 2323 / VenEC 1061 / SMC 834） | **已不存在** | 36,085 × 19,685 |

⇒ 两件事同时成立：① 用户说"我注释了 `annotation_L2`"**这次是对的**，
② 但照 10-18 底表写死 `annotation` 会**整列取空且不报错**。
**底表只能当"曾经长这样"，不能当现状** —— 先 `colnames()` + 逐列 `table()`，再决定用哪列。
同理别看轻用户的话：「用户说错了」和「文件变了」是两种可能，先复验再判断。

### ⚠️ 9.2.1 同一对象的两套注释列**可能互相冲突** —— 细分前先做一致性核对

2026-11-05 实测 `celltype`(粗，2 类) 与 `annotation_L2`(细，5 类) **不是严格派生关系**：

| | CapEC | ArtEC | VenEC | Pericyte | SMC |
|---|---|---|---|---|---|
| `celltype=EC` | 8062 | 2298 | 1054 | 44 | 14 |
| `celltype=Pericyte` | **526** | 25 | 7 | 6835 | 820 |

→ **526 个 CapEC 在 `celltype` 里被标成 Pericyte**（反向另有 44/25/7/14），两边各差 500 个细胞。

处置口径：
- 细分（L3）以**更细的那一列**为准；
- **必须输出一张冲突细胞表留痕**（哪批细胞 / 两个标签各是什么 / 按什么依据定的）；
- ⛔ 不要静默二选一，也不要把差异说成"数据脏"——这是历史注释残留，**如实报给用户**即可。
  （用户对这类矛盾是欢迎被指出的，隐瞒会让后续所有比例统计都带错。）

```r
cat(paste(colnames(obj@meta.data), collapse = ", "), "\n")   # 先看全
grep("annotation|Annotation|Level|level|celltype|Celltype", colnames(obj@meta.data), value = TRUE)
```

三种结果三种处置：
- **有** `annotation_L2` → 直接当参考层，问题解决；
- **没有但 `annotation` 有 5 类** → 把它当参考层（用户口中的「L2」就是这个），并在交付里**显式写明**
  「本对象参考列实测为 `annotation`，共 5 类」，不要静默改名、也不要凭空新建一个空 `annotation_L2`；
- **两列都没有** → 停手问用户，别自己 map 一个「最像的」（铁律 3）。

⚠️ 用户可能已经**重新注释并另存**过该文件（同名路径、内容已更新）⇒ 上述底表是历史实测，
**每次开工仍要 `colnames()` + `table()` 当场复验一次**，不要拿底表当现状。

### 9.3 细分靠**经典 marker 判别**，不是重聚类全局

- 子集已经聚类过：思路是「**读出现有 cluster / 参考标签 → 逐簇算经典 marker 表达（DotPlot / 平均表达 / 阳性率）→ 按 marker 组合定 L3 名**」；
  **不要**为了「更细」把整个数据集重新聚类（会打乱已定的大群/亚群口径，也不可比）。
- 现有分辨率不足以分开目标亚型时，才在该子集内**提高分辨率局部重聚类**（不动父对象），并说明「L3 的簇号来自子集重聚类」。
- marker 判定要**成组看**（一个亚型 3–4 个阳性 marker + 明确的阴性 marker），单基因阳性不足以命名。
- 每个 L3 标签必须报**四件套**：细胞数 + 占比 + 定义性阳性 marker + 关键阴性 marker（缺一不叫注释）。


### 9.4 小标签的处置（细分最容易出的假象）

| 情况 | 处置 |
|---|---|
| 某 L3 候选 < 总细胞 1% 且 marker 不成组 | **不单列**，并入最近的父标签，表里注明"含 XX 细胞未细分" |
| 同一标签只在个别样本/个体出现 | 先排除单个体批次/个体效应（铁律 2 那类混淆），再决定是否保留 |
| 某参考标签内部 marker 完全均一 | 如实报「该层无更细结构」，**不要**为凑层级硬切 |

### 9.5 这一轮必须有可见交付，不能只给计划

细分任务的单轮**最小可见产出**（缺这个就等于没做）：

1. `colnames()` + 各候选参考列的 `table()`（证明用的哪一层、多少类）；
2. 对象规模（`dim` / 细胞数）与分组列是否能推个体（Pre/Post）；
3. **一句明确的下一步 + 一个待用户拍板的口径问题**（9.1 的 A/B）。

⛔ 长任务多轮里，"我先并行探测 A/B/C"这类**计划句不能当交付**；若本轮因故一步没跑，
就明说「本轮无产出 + 阻塞点 + 下一步需要你确认什么」，**不要**编造细胞数 / 标签名 / 文件路径充数。

### 🔴 9.6 写回新列 + 「到底按哪一列聚类」—— 四个**静默**错源（2026-11-05 实测，全部真踩）

#### (a) 命名向量赋给 `meta.data` → `No cell overlap between new meta data and Seurat object`

```r
l3 <- c("0"="CapEC_CD36", "1"="Pericyte_PDGFRB", ...)              # 簇号 → L3 名
ec$annotation_L3 <- factor(l3[as.character(ec$seurat_clusters)])   # ❌ 报错
```

`l3[as.character(...)]` 取出来的向量**带 names**（名字是簇号 "0"/"1"…）。Seurat 的 `$<-` 会把这些
names 当成 **cell barcode** 去和对象对齐 → 一个都匹配不上 → 抛上面那句。
此时**映射表对、长度对（19,685）、细胞也没丢**，纯粹是 names 属性惹的祸。

```r
v <- unname(l3[as.character(ec$seurat_clusters)])   # ✅ 去掉 names 再赋值
stopifnot(length(v) == ncol(ec), !anyNA(v))         # 赋值前先自检
ec$annotation_L3 <- factor(v, levels = lv)          # levels 显式给，图例顺序才稳定
```

🔍 **判读**：见到这句话**别去查 barcode 是否一致、别怀疑 subset 丢了细胞、也别重读对象** ——
先打 `names(v)`，非 `NULL` 就是它。（本次为此白丢一轮。）

#### (b) 一个对象常有 ≥2 套聚类列，**簇号语义互相矛盾**；`FindAllMarkers` 吃的是 `Idents()` 当前值

同一对象实测两套并存，且**同一簇号在两套里身份相反**：

| 聚类列 | 水平数 | 簇号 → 身份（节选） |
|---|---|---|
| `seurat_clusters` | **15** | `8` = **SMC**、`6` = **VenEC**、`13` = **TipEC** |
| `SCT_snn_res.1` | **19** | `8` = **VenEC**、`6` = 动脉中间态、`13` = **大动脉 EC** |

⇒ 两条硬纪律：

```r
Idents(ec) <- "seurat_clusters"                       # ① 显式指定，别靠默认
cat("n_clusters =", length(levels(Idents(ec))), "\n") # ② 水平数打出来（15，不是 19）
```

- 不指定时 `FindAllMarkers` / `DotPlot` / `AverageExpression` 静默用 `Idents()` 的**当前值**
  （对象自带的分辨率列，或上一个请求留下的）→ 结果属于**另一套编号**，**输出里毫无提示**
  （本次 `top` 对象是 19 簇那套，与交付用的 15 簇混在一起，差一步就错配）。
- 给用户报粒度的「现有 **N** 簇 → M 个亚型」**必须来自当场 `length(levels())`**，
  ⛔ 不能沿用上一轮、上一个分辨率列或历史底稿的 N。
  （本次一度按「19 簇」给用户报方案并让用户勾选，实际交付列只有 15 簇 —— 用户会拿这个数核对象。）

#### (c) 逐基因 min-max 缩放会把**近零表达基因**抬到 1.00（假阳性 marker）

把 `AverageExpression` 结果按基因 `(x-min)/(max-min)` 缩放到 0–1 以便 `t()` 打印，
会让**整体表达极低**的基因在它"最高"的簇上也显示 **1.00**。实测 `ADIPOQ`(脂肪) / `MYH1`(快肌) /
`PLP1`(神经) 在血管簇里冒出 1.00，看着像"这簇是脂肪/肌纤维污染"，其实是缩放假象。

- ✅ 缩放表**只用于排序找差异轴**，不能直接当"阳性"判据；
- ✅ 判定必须回**绝对平均表达 + 阳性率(`pct.1`)** 双证据（或 `DotPlot` 点大小）；
- ⚠️ 本次即因此把 92 细胞的小簇误读成「淋巴 LEC 候选（伴 ADIPOQ/MYH1 污染）」——
  换 15 簇口径复算后**没有任何 LEC 簇**，那是 adipocyte+myofiber 双高的小簇，不是 LEC。

#### (d) 双高混合簇：标 QC 类，别硬塞生物学名字

实测两簇 `PTPRC 0.98 / MYH1 0.81 / FABP4 0.69` 同时高（免疫 + 肌纤维双高），且任何单一谱系
marker 都不成组 → 合并标 **`LowQuality_Mixed`**，交付表里单列并注明细胞数；
**不要**为了"每簇都有名字"硬挑一个最像的。符合铁律 9.4，且用户欢迎这种如实标注。

## Pipeline

```
1. 父对象探针：table(粗分类列) + 并排打粗/细两列 + 记录总数与被排除类目
2. 对账：各亚群对象 dim/ncol() vs 基准（去掉被排除类目后的总数）
3. 归属：逐对象确认对应哪个大群（按列取值，不按对象名猜）
4. 列清单：逐对象实测 L2 列名 + table() 标签清单；列名不一致如实报
5. （用户确认后再做）按 barcode 回填父对象 + **加 `L2_source` 溯源列**
6. 三条守卫：非 NA 数 / 不跨行 / 总数不变
7. 交付：对账表 + 归属表 + L2 清单 + 差异说明（+ `annotation_L2_freq.csv` / `L2_vs_L1_check.csv` /
   `L2_mapback_audit.csv`，三张表 `pull` 回本机；父对象留集群）（见铁律 5.1）
8. **读回终检**：只读验证作业跑四条断言（细胞数 / NA / 标签数 / 每 L1 群内 L2 加和），
   出 `verify_report.txt` 并 `pull`（见铁律 8）
9. **出图**（用户要图时）：同一次导出精简坐标 CSV（`UMAP_1/2 + annotation_L2 + Celltype`）→ 本机迭代
   （见铁律 8.1）；23 簇名版式按铁律 8.2 先选策略再画
10. **（反方向）向下细分 L2→L3**：`colnames()`+`table()` 复验参考列 → 问清 A/B 路径（局部 or 回填全局）
    → 逐簇算经典 marker → 定 L3 名（四件套）→ 小标签按铁律 9.4 处置 → 出注释表 + UMAP/DotPlot（见铁律 9）
```

## Common Issues

| 现象 | 原因 | 解法 |
|---|---|---|
| 亚群之和与父对象差几百（如 427） | 拿父对象**总数**当基数，没用「去掉被排除类目」后的数 | 基数 = 总数 − 用户明确排除的类目（见铁律 1） |
| 「对不上」但只差 1 个谱系 | 一个亚群对象对应**多个**父类目（EC+Pericyte = Vascular cells） | 按列取值判归属，别按对象名一对一（铁律 1） |
| `celltype` 与 `Celltype` 结果不一致 | 父对象两套粗细列、只差大小写，用错层级 | 并排 `table()` 两列，交付里写明用的哪列（铁律 2） |
| 用户说 L2，实际只有 3/6 个对象用 `annotation_L2` | 「应该」≠ 实际；各对象列名不统一（EC→`annotation`、FAP→`Annotation`/`Annotation_Level2`） | 逐对象 `colnames()` 实测 + 显式映射表 + `stop()` 守卫，报差异后再动手（铁律 3） |
| 看到对象有 `annotation_L3` 就断定「没有 L2」 | 只看了 `grep` 命中的一列就下结论；L2/L3 可以**同时存在** | `colnames()` 看全（实测 MuSC 两列都有，早前误记为「只有 L3」）（铁律 3） |
| 「打回 L2」但 L2 比 L3 还粗 | `annotation_L2` 与 `annotation_L3` 是不同的分级体系，L2 不必然最细（MF: L2=3 类、L3=10 类） | 两条粒度都列给用户挑，别由列名替用户决定（铁律 3） |
| 同一批细胞两个文件、细胞数完全相同 | 两个候选是**两套注释方案**（FAP: 6 类 vs 4 类），不是同一份数据的两次保存 | 细胞数无法判优劣 → `ask_user` 给选项让用户拍板（铁律 3） |
| 用户说「我已注释了 `annotation_L2`」，实测该对象没有这一列 | 用户口头层级名 ≠ 实际列名（EC_pericyte 实测只有 `annotation` 5 类）；也可能文件已被重新注释另存过 | 当场 `colnames()` + `table()` 复验；没有就报「参考列实测为 X（n 类）」并继续，别静默改名/造空列（铁律 9.2） |
| 要做「比现有更细的 L3」，却打算重聚类整个数据集 | 重聚类会打乱已定的大群/亚群口径，且与已有注释不可比 | 子集内按经典 marker 细分；分辨率不够才在该子集**局部**提高分辨率重聚类（铁律 9.3） |
| 写 `obj$annotation_L3 <- factor(map[as.character(obj$cluster)])` 报 **`No cell overlap between new meta data and Seurat object`** | 右值是**命名向量**，names（簇号）被 Seurat 当成 cell barcode 去对齐 | 赋值前 `unname()` + `stopifnot(length(v)==ncol(obj), !anyNA(v))`；别去查 barcode/重读对象（铁律 9.6a） |
| 用户给的对象里「簇数」与历史底稿/上一轮不一致（19 vs 15） | 同一对象有 ≥2 套聚类列（`seurat_clusters` / `SCT_snn_res.*`），**簇号→身份互相矛盾**；`FindAllMarkers` 静默吃 `Idents()` 当前值 | 跑任何分组统计前 `Idents(obj)<-"<列名>"` + 打 `length(levels(Idents(obj)))`；报给用户的 N 必须来自当场输出（铁律 9.6b） |
| 缩放后的 marker 表里 `ADIPOQ`/`MYH1`/`PLP1` 在血管簇显示 1.00，误判"脂肪/肌纤维污染" | 逐基因 min-max 缩放把**近零表达基因**抬到 1.00（假阳性） | 缩放表只用于找差异轴；判定回绝对平均表达 + `pct.1` 双证据（铁律 9.6c） |
| 回填后某些对象整列空白（不报错、非 NA） | 按单一列名取列，未命中 = 静默空列 | 显式映射表 + `if (!col %in% colnames(...)) stop()`（铁律 3） |
| `anyNA()` 通过但仍漏映射 | `recode` 未命中值原样保留，不产生 NA | 守卫写 `%in%` 集合判定（铁律 5） |
| 一批 rds 里部分报 `unable to find required package 'Seurat'` | Seurat v4 对象需加载 Seurat 包（v5 走 SeuratObject）→ 差异式失败 | 脚本开头 `library(Seurat)`（铁律 4） |
| 回填后大量 NA / 标签错位 | 按行号合并（亚群 subset 后行序 ≠ 父对象） | 按 barcode 合并（铁律 5） |
| 日志停在 `#TASK:STAGE 保存对象` 后再无输出 → 以为作业卡死 | `saveRDS` 全程静默，GB 级对象写盘几十分钟 | 用**产物文件体积增长** + `ps` 仍高 CPU 判活；ETA 参照原始父对象体积（铁律 7） |
| 跑动中巡检 `remote_cluster run` 返回 `status=needs_persist` | 命令里点名了 ≥100MB 的 `.rds` 绝对路径（哪怕只是 `ls`） | 改用目录 `ls` 或 `ls -lhL *.rds` glob（顺带拿父对象体积当参照）；或先 `large_cache scan --remote` + `mark --remote`（铁律 7 + `remote-cluster-execution` 铁规 10） |
| 验证作业报 `R home directory is not defined` | 直接执行 `<env>/lib/R/bin/exec/R` 需要 `R_HOME`，与「集群环境缺 R」无关 | 用 `<conda_env>/bin/Rscript` 投验证作业（铁律 8） |
| 图要改好几轮，每轮都重读 GB 级父对象 | 版式迭代被绑在「读 7 GB 对象」上，每轮 10+ 分钟 | 抽一次精简坐标 CSV 拉回本机，之后本机秒级迭代（铁律 8.1） |
| UMAP 上 23 个簇名互相压字 | 小簇（<1.5k 细胞）只有几个像素，质心直标必然重叠 | 引线标签 / 重叠消解 / 小簇并入图外清单，三选一（铁律 8.2） |
| `rail_review(post)` 报找不到图 | `output_dir` 指向 `task2/`、图实际落在 `figures/` | `output_dir` 指**图真正所在目录**再复审（假失败，别重跑出图） |

## References

- `scripts/check_annotation_hierarchy.R` — **六级对账探针（可直接跑）**：读父对象建基准（父对象自己的频数表 + 并排打印所有分类列防用错层级）→ 逐对象算 barcode 交集/反向覆盖/计数 → 每个对象后立刻落 meta CSV 并 `rm+gc` → 结尾 `ALL DONE` 当跑完标记。用法见文件头注释。