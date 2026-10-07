---
name: scrna-trajectory-analysis
description: "单细胞轨迹推断/拟时序分析：Monocle3 (R)、Slingshot (R)、scVelo RNA velocity (Python)、CellRank 命运映射 (Python)。从 Seurat/Scanpy 对象链接。"
when_to_use: "[trajectory-analysis] scRNA-seq 轨迹推断/拟时序分析/RNA velocity/发育分化。使用场景：已聚类的 scRNA-seq 数据，需重建发育/衰老/分化轨迹，伪时间排序，RNA velocity 分析。"
version: 1.1.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [trajectory, pseudotime, monocle3, slingshot, scvelo, rna-velocity, cellrank, cell-fate, 03_高级分析]
    difficulty: advanced
    languages: [R, Python]
    category: scRNA
prerequisites:
  r_packages:
    - monocle3
    - Seurat
    - slingshot
    - tradeSeq
    - SingleCellExperiment
    - SummarizedExperiment
  python_packages:
    - scvelo
    - scanpy
    - cellrank
    - anndata
    - numpy
    - pandas
    - matplotlib
---

# Trajectory Analysis — 轨迹推断全流程

本 skill 覆盖 4 种轨迹推断方法，按用户数据格式和需求选择对应路径。

## 方法选择决策树

```
用户数据格式？
  ├─ Seurat 对象 (R) ──→ 路径 A: Monocle3  或  路径 B: Slingshot + tradeSeq
  └─ AnnData 对象 (Python) ──→ 路径 C: scVelo  RNA velocity  或  路径 D: CellRank 命运映射

已有注释好的 Seurat 对象？
  └─ 是 → 跳过重新降维，用 Seurat 的 UMAP + 注释 → 路径 A 或 B
```

---

> 📚 **Monocle3 vs Slingshot 选型对比**（算法原理/拓扑假设/参数语义/适用场景/已核实 PMID+DOI 文献表/官方文档核实路径）：见 `references/monocle3-vs-slingshot.md`。做工具对比调研或写方法学部分时直接引用。

## 📌 通用铁律（所有路径适用）

| 规则 | 说明 |
|------|------|
| **已有 Seurat 注释 → 不跑 Monocle3 的 preprocess_cds/reduce_dimension** | `as.cell_data_set()` 自带 Seurat 的 PCA/UMAP/注释 |
| **先用 Seurat UMAP 建轨迹** | Monocle3 的 `reduce_dimension()` 只有简单 PCA→UMAP，没有 SCTransform/Harmony |
| **>100K 细胞先 subset** | `learn_graph()` 复杂度 O(n²)，>60K 细胞会卡死 |
| **有大分支才做分支分析** | 衰老数据通常线性（Young→Old），不一定有分叉；发育数据（干细胞→多种终末细胞）才有明显分叉 |
| **多 R 版本共存时先定位包的真身** | `check_env`/`rail_review` 报"已装"≠ execute_r 内核的库里有（实测：monocle3/slingshot 只在用户级 R-4.4.2 自带库，内核用的 `E:/R-libs/R-4.5.3` 没有）。先枚举所有 R 安装的 library 确认真身 → 在**有 monocle3 的 R** 跑轨迹、用**有 Seurat 的 R** 导出 counts/meta/UMAP 中转 → `references/multi-r-package-location.md` |

### 🔬 为什么绝不能用 Monocle3 UMAP？

| 维度 | Seurat UMAP | Monocle3 UMAP |
|------|------------|---------------|
| 归一化 | SCTransform residuals（正则化负二项） | `log(size_factor_norm + 1)` |
| 批次校正 | Harmony 已校正 | 无 / 简单 CCA（无正则化） |
| 技术噪声 | 已去除 | 保留（低深度细胞聚在一起） |
| 与注释一致性 | 一致 | 不一致（重新聚类，注释无处可放） |

**核心原理**：SCTransform 用正则化负二项回归将测序深度信号与生物学方差分离，提取 Pearson residuals 进 PCA→Harmony→UMAP。Monocle3 的 `log(norm+1) → PCA → UMAP` 保留了测序深度作为主信号，UMAP 空间被技术变量主导。在这个空间上建的轨迹图反映的是测序深度梯度，不是生物学轨迹。

---

## 路径 A: Monocle3（R，推荐 — Seurat 对象直接使用）

### 适用场景
- 已有注释好的 Seurat 对象
- 需要伪时间排序 + 轨迹图
- 数据量 < 100K 细胞（建议 subset 到 30-60K）

### `as.cell_data_set()` 自动带过来什么

| Seurat 内容 | CDS 中的位置 | 自动？ |
|------------|-------------|:---:|
| `counts` (RNA assay) | `counts(cds)` | ✅ |
| `reductions$pca` | `cds@int_colData$reducedDims$PCA` | ✅ |
| `reductions$umap` | `cds@int_colData$reducedDims$UMAP` | ✅ |
| `meta.data` | `colData(cds)` | ✅ |
| `Idents()` | `colData(cds)$cluster` | ✅ |

### 标准流程

```r
library(monocle3)
library(Seurat)
library(dplyr)

# ==== Step 1: 加载 Seurat + subset ====
seurat_obj <- readRDS("你的seurat对象.rds")
set.seed(42)
seurat_sub <- subset(seurat_obj, cells = sample(Cells(seurat_obj), 60000))

# ==== Step 2: Seurat → CDS (PCA+UMAP+注释 自动带入) ====
cds <- as.cell_data_set(seurat_sub)

# 验证 UMAP 来自 Seurat
"UMAP" %in% names(cds@int_colData$reducedDims)  # 应返回 TRUE

# ==== Step 3: 聚类 + 学习轨迹图 ⚠️ 跳过 preprocess_cds/reduce_dimension ====
# cluster_cells 内部调用 monocle3:::cluster_cells_umap_coords()，只依赖 UMAP
cds <- cluster_cells(cds, resolution = 1e-4)
cds <- learn_graph(cds)

# ==== Step 4: 可视化 ====
plot_cells(cds, color_cells_by = "cell_type",    # 你的 Seurat 注释列名
           label_groups_by_cluster = FALSE,
           label_leaves = TRUE,
           label_branch_points = TRUE,
           graph_label_size = 1.5)

# ==== Step 5: 伪时间排序（编程式指定根节点）====
get_earliest_principal_node <- function(cds, group_col, group_val) {
  cell_ids <- which(colData(cds)[, group_col] == group_val)
  closest_vertex <- as.matrix(
    cds@principal_graph_aux[["UMAP"]]$pr_graph_cell_proj_closest_vertex[colnames(cds), ]
  )
  root_node <- igraph::V(principal_graph(cds)[["UMAP"]])$name[
    as.numeric(names(which.max(table(closest_vertex[cell_ids, ]))))
  ]
  root_node
}

cds <- order_cells(cds, root_pr_nodes = get_earliest_principal_node(cds, "condition", "Young"))

plot_cells(cds, color_cells_by = "pseudotime",
           label_cell_groups = FALSE, label_leaves = TRUE,
           label_branch_points = TRUE, graph_label_size = 1.5)

# ==== Step 6: 轨迹差异表达 ====
pr_test_res <- graph_test(cds, neighbor_graph = "principal_graph", cores = 8)
pr_deg_ids <- row.names(subset(pr_test_res, q_value < 0.05))

# 共表达模块 + 热图
gene_module_df <- find_gene_modules(cds[pr_deg_ids, ], resolution = 1e-3)
cell_group_df <- tibble::tibble(
  cell = row.names(colData(cds)),
  cell_group = colData(cds)$cell_type
)
agg_mat <- aggregate_gene_expression(cds, gene_module_df, cell_group_df)
row.names(agg_mat) <- stringr::str_c("Module ", row.names(agg_mat))
pheatmap::pheatmap(agg_mat, scale = "column", clustering_method = "ward.D2")

# 单个基因沿伪时间表达
plot_cells(cds, genes = c("MYH7", "MYH1", "TNNT1"),
           show_trajectory_graph = FALSE, label_cell_groups = FALSE)
```

### Monocle3 常见坑

| 坑 | 解法 |
|---|---|
| Seurat UMAP 被 `reduce_dimension()` 覆盖 | 坚决不跑 `reduce_dimension()`；已覆盖时：`cds@int_colData$reducedDims$UMAP <- Embeddings(seurat_sub, "umap")[colnames(cds), ]` |
| `learn_graph()` 卡死 | 细胞 >60K → subset |
| `order_cells()` "no root node" | 用 `get_earliest_principal_node()` |
| partition 太碎 | `cluster_cells(resolution=1e-4)` |
| `as.cell_data_set()` deprecated 警告 | 正常，忽略 |
| PCA 缺失但 UMAP 存在 | `preprocess_cds(num_dim=50)` 再覆盖 UMAP |
| 知乎代码的手动替换 UMAP | 仅 Monocle3 < 1.3 需要；v1.3+ 自动带 UMAP |
| **cluster 是多起源混合群体（如 Specialized MF 含快慢肌两条路线）** | ⛔ 不能强行做单根 Monocle3。先 sub-cluster 拆开，或改用 scVelo/CellRank/条件间矢量场。详见 `references/composite-population-trajectory-pitfalls.md` |
| `pseudotime(cds)` 报 **"No pseudotime calculated for reduction_method = UMAP"** | `saveRDS(cds)` 落盘点放错：必须在 `order_cells()` **之后**保存（存图骨架不存伪时间槽）；读回后补跑 `order_cells(cds, root_pr_nodes=...)` 亦可。monocle3 另建议 `save_monocle_objects()`（保留 annoy/hnsw 索引） |
| 换一个端点当 root 后"方向整个反过来" | **root 镜像伪影，不是矛盾证据**：伪时间方向由 root 定义，对侧端点定根必然反号。跨方法/跨子集（如剔除某群后重跑）比较"方向是否一致"之前，必须先把两侧 root 校准到**同一生物学端**，否则会把镜像误读成分歧 |
| `lm(pt ~ age + celltype)` 报 **找不到对象'celltype'**；`meta$col[cells]` 取子集得全 NA / `-Inf` | data.frame 列没有行名 → 必须 `meta[cells, "col"]`；公式变量先落局部向量（`celltype_v <- as.character(meta$celltype)`），不能直接写列名 |

### 方法选择速查（含混合群体场景）

| 场景 | 推荐方法 |
|------|---------|
| 单一发育/分化过程，有明确根节点 | Monocle3 + 手动指定根节点 |
| 多起源混合群体，子群体可拆分 | sub-cluster → 分别 Monocle3 |
| 多起源混合群体，子群体不可拆分 | scVelo RNA velocity 或 CellRank |
| 关心"运动/药物/衰老把群推向哪个方向"，而不是伪时间 | 条件间矢量场（PCA 箭头图）——见 `references/composite-population-trajectory-pitfalls.md` |

---

## 路径 B: Slingshot (R，复杂分叉轨迹)

```r
library(slingshot); library(tradeSeq); library(SingleCellExperiment); library(Seurat)

sce <- as.SingleCellExperiment(seurat_sub)
sce <- slingshot(sce, clusterLabels = "cell_type", reducedDim = "UMAP", start.clus = "Satellite_Cell")

# 可视化
colors <- rainbow(length(unique(sce$cell_type)))
plot(reducedDims(sce)$UMAP, col = colors[sce$cell_type], pch = 16, cex = 0.5)
lines(SlingshotDataSet(sce), lwd = 2, col = "black")

# tradeSeq 分叉差异表达
sce <- fitGAM(sce, nknots = 6)
asso_res <- associationTest(sce)
```

---

## 路径 C: scVelo RNA velocity (Python)

```python
import scvelo as scv; import scanpy as sc

adata = sc.read_h5ad("your_data.h5ad")
scv.pp.filter_and_normalize(adata, min_shared_counts=20, n_top_genes=2000)
scv.pp.moments(adata, n_pcs=30, n_neighbors=30)
scv.tl.recover_dynamics(adata)
scv.tl.velocity(adata, mode="dynamical")
scv.tl.velocity_graph(adata)
scv.pl.velocity_embedding_stream(adata, basis="umap", color="cell_type")
scv.tl.velocity_pseudotime(adata)
```

---

## 路径 D: CellRank 命运映射 (Python)

```python
import cellrank as cr; import scvelo as scv

vk = cr.kernels.VelocityKernel(adata)
ck = cr.kernels.ConnectivityKernel(adata)
combined_kernel = 0.8 * vk + 0.2 * ck

g = cr.estimators.GPCCA(combined_kernel)
g.fit(cluster_key="cell_type")
g.compute_schur(n_components=20)
g.compute_macrostates(n_states=5, cluster_key="cell_type")
g.compute_fate_probabilities()
g.plot_fate_probabilities(same_plot=False, basis="umap")
```

---

## 常见问题排查

| 问题 | 原因 | 解法 |
|------|------|------|
| `as.cell_data_set()` "not a Seurat object" | Seurat v5 格式 | 升级 monocle3 |
| `learn_graph()` 轨迹乱线 | resolution 太大 | `cluster_cells(1e-5)` |
| 伪时间方向反向 | 根节点选错 | 改 `group_val` |
| `graph_test()` 全不显著 | 细胞太少 | 每分支 ≥200 cells |
| 想用 BEAM 做分支分析 | ⚠️ BEAM 是 Monocle2 的函数（Qiu 2017, PMID 28825705），Monocle3 没有 | 用 `graph_test(neighbor_graph="principal_graph")` + `choose_graph_segments()`（详见 `references/monocle3-vs-slingshot.md`） |
| scVelo `recover_dynamics` 慢 | 基因太多 | `n_top_genes=2000` |
| 查 Monocle3 官方文档 URL 404 | 旧 `/monocle3/reference/*.html` 已失效 | 新站为 `/monocle3/docs/{trajectories,clustering,differential,getting_started}/`（从页面 nav 链接找路径） |
| Windows 下 curl 抓 GitHub Pages 报 SSL error 35 | Schannel TLS 握手失败（`-k`/`--tlsv1.2` 无效，bioconductor.org 正常） | 改用 Python urllib + 关闭校验的 SSL context（OpenSSL 栈），见 `references/monocle3-vs-slingshot.md` |
| 需核实论文方法细节/PMID | 凭记忆不可靠 | Europe PMC fullTextXML REST + NCBI efetch 摘要核实（命令见 `references/monocle3-vs-slingshot.md`） |

## 🔬 伪时间结论验证规程（必须做，否则结论不得升级）

> 完整checklist + 实测数值范例：`references/pseudotime-validation-protocol.md`；多 R 版本下 monocle3/slingshot 装在哪、如何中转数据：`references/multi-r-package-location.md`

| # | 检查 | 做法 | 判读 |
|---|------|------|------|
| 1 | resolution 稳定性 | 网格 `1e-4/1e-3/3e-3/1e-2/3e-2` × 多 seed（1/7/42/123/2024），记 partition 数 / 簇数 / 与注释的 ARI + seed 两两 ARI | partition 随 resolution 剧烈跳变或 ARI<0.2 → 拓扑不稳，方向/连续性结论降级 |
| 2 | root 稳健性 | **root-swap**：把所有合格端点（degree=1 & n≥10）轮流当 root，重算 ρ(伪时间, 端标记基因) | 同侧端点一致、对侧镜像 = 正常；任何"方向"结论必须注明"依赖 root 校准" |
| 3 | 端点生物学端判定 | 用端标记基因（如 MYH7=TypeI / MYH2=TypeII）+ 程序打分 AUCell + 群体比例共同定根，别只用"某组细胞最多" | 端标签与本数据一致才可用；否则先做端注释 |
| 4 | 两法交叉验证 | Slingshot `reducedDim`/`clusterLabels`/`start.clus`；**start.clus 必须用独立规则选**（如"n≥30 + Young 富集 + MYH7>中位 + MYH2<中位 + 程序打分高/低"），⛔ 不许复用 Monocle 的 root/伪时间 | ρ≥0.7 强、0.5–0.7 中等、0.3–0.5 弱同轴、<0.3 不同轴；符号必须一致 |
| 5 | 独立性折扣 | 同一嵌入下算一次 ρ，再用**另一个嵌入**（Monocle 自己的 `reduce_dimension()` UMAP，或 PCA）重跑两法再算 ρ；两法跨嵌入自比 | 共享嵌入会膨胀一致度：实测同一对方法 共享 harmony-UMAP ρ=0.901 vs 独立嵌入 ρ=0.619（Slingshot 自身换嵌入仅 0.204）→ **报独立嵌入值为主值**，共享嵌入值只作"技术一致性" |
| 6 | 伪重复控制 | 细胞级 ρ 会被细胞数灌水：算每样本均值 ρ（样本级）+ ICC + LOO（逐个删样本） | 细胞级 ρ=0.159 / 样本级 ρ=0.488；ICC 0.058；LOO 稳定 = 样本级效应真实但幅度小 → 结论写"样本水平" |
| 7 | 组成性 vs 核内推进 | `lm(pt ~ age)` → `+celltype` → `lmer(pt ~ age + celltype + (1\|sample))`；再做细胞类型内分层 ρ + 中介（样本级比例进模型） | 校正后系数骤降/CI 含 0 且群内 ρ≈0 → 是**组成性比例变化**，不可写"核内衰老推进"（实测 1.33→0.297→CI[−0.03,0.63] 含 0；RSS 比例中介掉 36%） |
| 8 | 样本混杂 | 伪时间分箱（n≈20）+ 每箱最大单样本占比 vs **打乱样本标签的置换零分布**（≥500 次，99% 分位为阈值） | 实测 Monocle3 15/107 箱超阈（最大 0.55）、Slingshot 2/69 → 必须写"部分区段受个体驱动" |
| 9 | 结论分级 | 每条结论给 medium/low + 强制限定语（方向依赖 root / 非独立互证 / 组成性 / 无独立队列与分叉 DE） | 缺独立队列、缺分叉 DE、QC 未做双胞/ambient → 一律不得写 strong 或因果 |

**⚠️ 降级/反向陷阱**：剔除某个群重跑后方向翻转（实测 D3 剔 RSS 后 Spearman vs 主分析 −0.153）**先怀疑 root 落到了对侧端点**——把 root 校准到同一生物学端后实测 ψ(D3校准, D4)=0.834–0.940、ρ 与 Slingshot 0.818–0.870，反向即消失。做任何"敏感性分析矛盾了"的判断前，先做第 2/3 步的 root 校准。

## 输出目录结构

```
results/trajectory_monocle3_{date}/
├── figures/
│   ├── trajectory_celltype.png
│   ├── trajectory_pseudotime.png
│   └── module_heatmap.png
├── results/
│   ├── graph_test_results.csv
│   └── pseudotime.csv
├── scripts/
│   └── monocle3_analysis.R
└── data/
    └── cds.rds
```
---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="{当前分析} 参数与结果 —— {样本}",
     context="参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<KB内容>,
   )
3. save_conclusions(module="{模块}", topic="{分析名}", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。
⛔ debate confidence=low → 调整参数重跑。
