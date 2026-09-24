# 轨迹结论稳健性硬门控 + 供体级统计配方

> 来源：2026-09-24 MF_2000.rds（人骨骼肌 2132 细胞，RSS 卫星细胞 / TypeI / TypeII，48 样本 24 供体 Pre-Post 配对）Monocle3 路径 A 实战。
> 核心教训：**伪时间轴 = 「你选的那个嵌入 + 你选的那个根」下算出来的量**。换嵌入或换根会改变方向、甚至翻转结论。跑完必须过四道闸，再写结论。

## 0. 跨 R 版本桥接（monocle3 与 Seurat 装在两个 R 里时）

本机实测：monocle3 只在 `C:/Users/<user>/AppData/Local/R/R-4.4.2/library`，Seurat 只在 R-4.5.3 的 `E:/R-libs/R-4.5.3`，平台 execute_r 内核固定走 4.5.3 ⇒ 内核里 `library(monocle3)` 必失败。**不要重装包**，用纯 RDS 桥接：

```r
# ① 在 Seurat 所在的 R（execute_r 内核）导出最小输入
cnt <- GetAssayData(obj, assay = "RNA", layer = "counts")
saveRDS(cnt, "data/traj_counts.rds"); saveRDS(obj@meta.data, "data/traj_meta.rds")
saveRDS(Embeddings(obj, "umap"), "data/traj_umap.rds")
```

```bash
# ② 用另一个 R 的 Rscript 绝对路径跑 monocle3（bash 里直调，不要 cmd //c 包装）
"C:/Users/23136/AppData/Local/R/R-4.4.2/bin/x64/Rscript.exe" \
  "E:/.../scripts/traj_02_monocle3.R" > log/traj_monocle3.log 2>&1
```

```r
# ③ 该 R 里不需要 Seurat：直接吃纯矩阵
cds <- new_cell_data_set(cnt, cell_metadata = md,
        gene_metadata = data.frame(gene_short_name = rownames(cnt), row.names = rownames(cnt)))
cds <- preprocess_cds(cds, num_dim = 50)
cds@int_colData$reducedDims$UMAP <- um[colnames(cds), ]
cds <- cluster_cells(cds, resolution = 1e-4); cds <- learn_graph(cds)
```

⚠️ 脚本里**不要 `library(igraph)`**（会遮蔽 `monocle3::clusters()` → `partitions()` 报 `Must provide a graph object`），只用 `igraph::` 前缀。
⚠️ `saveRDS(cds)` 的 annoy/hnsw warning 可忽略：`order_cells()` 换根、`plot_cells()` 都能在回读的 cds 上跑。

## 1. 闸①：多根枚举（换根敏感性）

```r
cds <- readRDS("data/cds_full.rds")            # learn_graph + order_cells 之后保存的
pg <- principal_graph(cds)[["UMAP"]]; nodes <- igraph::V(pg)$name
cv <- as.matrix(cds@principal_graph_aux[["UMAP"]]$pr_graph_cell_proj_closest_vertex[colnames(cds), ])
node_of_cell <- nodes[as.numeric(cv[, 1])]; cols <- as.data.frame(cds@colData)
pick <- function(mask) names(which.max(table(node_of_cell[mask])))
roots <- list(RSS_max = pick(cols$celltype == "RSS"), TypeI_max = pick(cols$celltype == "TypeI"),
              TypeII_max = pick(cols$celltype == "TypeII"), SpecMF_max = pick(cols$annotation == "Specialized MF"),
              high_degree = nodes[which.max(igraph::degree(pg))], random_node = sample(nodes, 1))
for (nm in names(roots)) { p <- pseudotime(order_cells(cds, root_pr_nodes = roots[[nm]]))
  write.csv(data.frame(cell = names(p), pseudotime = as.numeric(p)),
            file.path("results", paste0("pseudotime_root_", nm, ".csv")), row.names = FALSE) }
```

**方向归一化（关键）**：不同根给出方向相反的伪时间，直接比 Δ 会得出"结论翻转"的假象。先把每个根的伪时间对齐到基线方向再比：

```r
rho <- cor(p_alt$pseudotime, p_base$pseudotime, method = "spearman")
pt_oriented <- p_alt$pseudotime * ifelse(rho >= 0, 1, -1)   # 再算效应量
```

判据：与基线 `|rho|` 高（≥0.9）的根若效应同向 ⇒ 对该根稳健；**唯一反向的那个根常是"根插进了目标分支内部"**（本次 `TypeII_max` 与基线仅 rho=0.561，Δ 由 +1.65 翻成 −0.89）——报出该根位置与 rho，别把它当成反证。

## 2. 闸②：嵌入独立性（注入 UMAP 的必查项）

路径 A 注入 Seurat UMAP 后，`learn_graph()` 学的其实是**Seurat 的降维几何**。必须跑一次不注入的对照：

```r
cds_i <- new_cell_data_set(cnt, md, gene_metadata = ...)
cds_i <- preprocess_cds(cds_i, num_dim = 50)
cds_i <- reduce_dimension(cds_i, umap.metric = "cosine")   # 不注入
cds_i <- cluster_cells(cds_i, resolution = 1e-4); cds_i <- learn_graph(cds_i)
```

比三样：① 伪时间 Spearman rho（本次 **0.269**，几何差异大）；② **marker 锚定**——同一批 marker 在两条轴上的负载方向（本次 MYH7 +0.50/+0.40、TNNT1 +0.62/+0.31、MYH1 −0.51/−0.15 同向 ⇒ 轴生物学同源；MYH2 −0.44/+0.03 翻转）；③ 效应量方向（本次 TypeII Δ 由 +1.78 翻成 −1.78）。
**判读**：rho 低但 marker 同向 ⇒ 同源轴、几何不同；**效应方向在嵌入间翻转 ⇒ 该效应不可下结论**；替代嵌入下**多种细胞类型同向位移** ⇒ 更像整体/技术漂移（组成、深度、批次），不是某类型的特异效应。

## 3. 闸③：统计单位 = 供体/样本（禁止细胞级检验当结论）

```r
d <- pt %>% group_by(cohort, donor, timepoint) %>%
  summarise(n_cells = n(), mp = mean(pseudotime), .groups = "drop") %>% filter(n_cells >= 3)
# 配对 Wilcoxon + rank-biserial
rb <- function(pre, post) { dd <- post - pre; dd <- dd[dd != 0]; (sum(dd > 0) - length(dd)/2)/(length(dd)/2) }
# 符号翻转置换（不依赖分布假设）
obs <- mean(delta); p_perm <- mean(abs(replicate(20000, mean(sample(c(-1,1), length(delta), TRUE) * delta))) >= abs(obs))
# bootstrap 95% CI
ci <- quantile(replicate(10000, mean(sample(delta, length(delta), TRUE))), c(.025, .975))
# 供体固定效应模型（校正测序深度 + 每供体细胞数）：等价于配对 + 协变量
lm(mp ~ post + factor(donor) + n_cells + log1p(nCount_RNA), data = don)
```

细胞级 Spearman（如 marker vs 伪时间）可以报相关强度，但**它的 p 值受伪重复膨胀**（本次 2132 细胞给出 p=1e-224），写结论时须注明"细胞级相关，非独立检验"。

## 4. 闸④：固定多重检验族（含敏感性检验）

把**换根 × 细胞类型、队列拆分、替代嵌入**全部放进同一个 BH 家族，一次校正：

```r
fam <- rbind(data.frame(family="root_enumeration(6x3)", test=paste(rt$root, rt$celltype, sep="/"), p=rt$p),
             data.frame(family="cohort_celltype(11)",  test=paste(pw$cohort, pw$celltype, sep="/"), p=pw$p),
             data.frame(family="independent_UMAP(3)",  test=paste("indepUMAP", ind_tests$celltype, sep="/"), p=ind_tests$p))
fam$FDR <- p.adjust(fam$p, method = "BH")
```

⛔ **不准事后缩族**（"只看 TypeII 合并"= alpha 膨胀）。本次 32 检验全族内 TypeII 全部 FDR ≥ 0.112（0 个 < 0.05），因此未校正 p=0.011~0.021 只能写成探索性。

## 5. 判读规则：把"分化"和"身份差异"分开

| 观察 | 结论 |
|---|---|
| 肌生成程序（PAX7/MYF5/MYOD1/MYOG/MYH3）与伪时间无相关 + 谱系 marker（MYH7/MYH1/TNNT1）强相关 | 轴是**细胞身份/状态差**（如纤维型 TypeII↔TypeI），**不是分化轨迹**；1 partition 单一连通 ≠ 真实分化 |
| 根端细胞类型是人为指定的；去掉该类型重跑同一轴仍在（\|rho\| 高、方向反向） | 只能称"**计算根端/伪时间起点**"，不能称生物学分化起点 |
| 根端细胞类型本身是静息态（PAX7+ 但 MKI67 0%、MYOD1 极低） | 无增殖、无激活分化程序，支持"静息态被当作根端"的解读，别写成"分化起点" |
| 效应量在小细胞群（如 162 细胞分散 6 组、每供体 6–41 个） | 低功效 ⇒ 该结论应移出主结论，标"不可判定"而非"无效应" |

## 6. 结论分级交付（措辞纪律，经两轮 L2 + 一轮 L1 辩论裁决认可）

| 级别 | 写法 | 禁用词 |
|---|---|---|
| A 保留（限定） | "伪时间轴主要刻画**本嵌入下**的 X 身份/程序；根端为计算意义上的起点；单连通 ≠ 真实分化轨迹" | 分化起点 / 真实谱系轨迹 / 某诱导某转换 |
| B 不可判定 | "现有数据不能支持 X 沿该轴发生可下结论的位移：方向在基线、换根、独立降维间不稳定，全族 FDR ≥ 0.11。仅探索性，需 IHC/蛋白或独立队列验证" | "X 诱导 Y 转换"、把未校正 p 写成确认性结论 |
| C 移出主结论 | "低功效/不可判定，移至补充材料或限制段，不作主张" | 直接写成"无效应"（低功效 ≠ 无效应） |

配套必须一并给出：未排除混杂清单（根选择偏倚 / 注入 UMAP 的几何影响 / 单核 vs 单细胞模态 / 年龄性别批次深度未入模型 / 细胞级 FDR 膨胀）+ **最小验证集与失败阈值**（本次：配对活检 MYH7/MYH1/MYH2 免疫荧光；≥2 个独立验证不同向 ⇒ 淘汰 B）。

## 7. 本次实例数值（可作对照基线）

- 结构：1 partition / 19 节点；res 1e-5、1e-4 → 1 partition，1e-3 → 3 clusters；子集（剔除 RSS / 仅 TypeI / 仅 TypeII）均 1 partition。
- 伪时间中位数：RSS ≈0–7.3 < TypeII ≈7.7–11.1 < TypeI ≈20.8–24.4。
- marker vs 伪时间（Spearman，n=2132）：TNNT1 +0.619、MYH7 +0.497、MYH1 −0.511、MYH2 −0.438；PAX7 −0.009、MYF5 +0.010、MYOD1 −0.012、MYOG +0.044（均 ns）。
- 供体级配对（TypeII）：基线 Δ=+1.53 CI[0.46, 2.64]、置换 p=0.011、供体 FE p=0.011；独立降维 Δ=−1.78 CI[−3.77, −0.10]（TypeI 亦 −1.54）。
- 全族（32 检验）TypeII FDR 最小 0.112。
- RSS（168 细胞级）：PAX7 阳性率 10.5%、MKI67 0%、DLK1 4.3%、SPRY1 19.1% → 静息态；伪时间双峰（约一半在根节点、一半在 7.33 节点）。

## 8. 与辩论引擎的配合

- 结论合成/入库前必辩；辩前先 `search_papers()` 拿真实 PMID/DOI（无证据的论点会被裁判判为草稿）。
- 裁决的 `next_actions`（owner=ai）与 `blocks` 是**待办清单**：带 `blocks` 的动作没做完，别把该效应写进主结论——本次两轮 L2 都要先补"换根枚举""供体级协变量模型""独立降维""固定 FDR 族"，补完第三轮 L1 才 verdict=support。
- 裁决里 `recommended_params.A_status/B_status/C_status` 这类字段直接决定交付措辞，照抄其 allowed/forbidden terms 写结论。