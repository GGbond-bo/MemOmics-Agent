# 伪时间/轨迹结论验证规程（Monocle3 × Slingshot）

**何时用**：任何"跑完轨迹后要下结论/写进报告/入库"的场合。目标是让每条结论都带**置信级别 + 强制限定语**，并且能被第三方复现检查。
**来源**：2026-09-24 人骨骼肌肌核（MF_2000，2132 核 × 51227 基因，48 样本 6 组）Monocle3 1.4.27 + Slingshot 实测 + 3 轮辩论裁决（L1 脚本设计 → L2 结果成立性 → L2 结论分级 = modify/medium）。

---

## 0. 结论分级表模板（直接套用）

| 结论 | 置信 | 关键数值 | 强制限定 |
|---|---|---|---|
| 主轴 = 哪个程序轴 | medium | 端标记基因 ρ、AUCell 程序 ρ（BH-FDR） | 方向依赖 root；多 seed 拓扑稳定性；不能当"细胞时钟" |
| 条件/分组同向 | low/探索性 | 细胞级 ρ + **样本级 ρ** + LOO + 校正链 | 群内 ρ≈0 → 以组成性为主；混杂箱；不可称核内推进 |
| 两法一致性 | medium/技术一致性 | **独立嵌入 ρ + bootstrap CI** | 共享嵌入膨胀；同源 count；非独立队列验证 |
| 敏感性分析矛盾 | 需先排除伪影 | root 校准前后对比 | 未校准前不得当反证 |
| 异常/新群的身份 | medium（描述性） | 比例-条件趋势 + 标记基因 + QC | 未排双胞/ambient；机制仅假说 |

---

## 1. resolution 网格 + 多 seed（拓扑稳定性）

```r
ari <- function(a,b){ tab<-table(a,b); n<-sum(tab); s<-sum(choose(tab,2))
  sa<-sum(choose(rowSums(tab),2)); sb<-sum(choose(colSums(tab),2))
  (s-sa*sb/choose(n,2))/((sa+sb)/2-sa*sb/choose(n,2)) }
for (r in c(1e-4,1e-3,3e-3,1e-2,3e-2)) { c2 <- cluster_cells(cds, resolution=r, random_seed=42)
  data.frame(res=r, n_partition=length(unique(c2@clusters$UMAP$partitions)),
             n_cluster=length(unique(c2@clusters$UMAP$clusters)),
             ARI=ari(c2@clusters$UMAP$clusters, as.character(meta$annotation_L3))) }
# 多 seed 复核 + seed 两两 ARI
for (s in c(1,7,42,123,2024)) cluster_cells(cds, resolution=3e-3, random_seed=s)
```
实测（2132 核）：partition 在 `1/1/2/1/1` 间跳变，无 3–6 区间；ARI(L3) 0.298–0.502；seed 两两 ARI 0.758–0.954。
→ 小数据（<5K 核）不要照搬 skill 里面向 60K 细胞的 `resolution=1e-4`；按"partition 数 + ARI + 跨 seed 稳定"选，并把"partition 随 resolution 跳变"写进限定语。

## 2. root-swap 与"镜像伪影"

```r
pg <- principal_graph(cds)[["UMAP"]]; cv <- as.matrix(cds@principal_graph_aux[["UMAP"]]$pr_graph_cell_proj_closest_vertex[colnames(cds),,drop=FALSE])
node <- igraph::V(pg)$name[cv[,1]]                       # 每个细胞最近的图节点
tab  <- data.frame(node=igraph::V(pg)$name, degree=as.numeric(igraph::degree(pg)),
                   n_cell=as.numeric(table(node)[igraph::V(pg)$name]))
# 端点评估：Young/条件富集、端标记基因均值、程序打分均值
for (v in unique(c(main_root, endpoints$node))) { p <- pseudotime(order_cells(cds, root_pr_nodes=v)); ... }
```
实测：同侧端点（Y_109/Y_2/Y_14/Y_49）ρ(MYH7)≈−0.5、ρ(MYH2)≈+0.35 一致；对侧端点（Y_5/Y_31/Y_35）符号整体翻转。
**判定**：对侧翻转 = 镜像（几何必然），不是矛盾；**只有把两侧 root 都校准到同一生物学端后仍不一致，才算真矛盾**。

## 3. 两法交叉验证（独立起点 + 独立嵌入）

```r
sce <- SingleCellExperiment(assays=list(counts=counts), colData=meta); reducedDim(sce,"UMAP") <- umap
sce <- slingshot(sce, clusterLabels="annotation_L3", reducedDim="UMAP", start.clus=start_l3)
spt <- slingPseudotime(sce)
# 主曲线选择：与端标记基因负相关（匹配主轴方向）者
main <- colnames(spt)[which.min(apply(spt,2,function(x) cor(x, myh7, method="spearman", use="complete.obs")))]
```
- **start.clus 独立规则**（严禁用 Monocle 的 root/伪时间）：`n≥30 & 条件A富集 > 条件B & 标记基因>中位数 & 反向标记<中位数 & 程序打分高 & SenMayo低`。实测选中 "Pure Type I"。
- 敏感性：`clusterLabels` 换一级注释（10 亚群 → 3 类）ρ=0.985 → 结果对簇标签稳健。
- **独立性折扣（必做）**：换嵌入重跑同一对方法。
  - 共享 harmony-UMAP：ρ=0.901，bootstrap 95%CI [0.890, 0.910]
  - **Monocle 自有 `reduce_dimension()` UMAP**（独立嵌入）：ρ=0.619，CI [0.586, 0.650] ← **报这个作主值**
  - 同法跨嵌入：Monocle 0.592；**Slingshot 仅 0.204**（说明它高度依赖嵌入几何）
  - 解释：两法共享同一 count 矩阵 + 同一嵌入 → 高 ρ 含冗余，不等于独立验证。

## 4. 伪重复与组成性（条件/年龄轴必做）

```r
# 伪重复：细胞级 vs 样本级 + ICC + LOO
sm <- data.frame(sample=names(tapply(pt, meta$samplename, mean)), mean_pt=as.numeric(tapply(pt, meta$samplename, mean)))
aov1 <- summary(aov(pt ~ factor(meta$samplename))); MSB <- aov1[[1]][,"Mean Sq"][1]; MSW <- aov1[[1]][,"Mean Sq"][2]
loo <- sapply(seq_len(nrow(sm)), function(i) cor(sm$mean_pt[-i], sm$age[-i], method="spearman"))

# 组成性 vs 核内推进
summary(lm(pt ~ age_ord))                                    # 未校正
summary(lm(pt ~ age_ord + celltype_v))                       # 校正组成
summary(lmer(pt ~ age_ord + celltype_v + (1|sample_v)))      # 加个体随机效应（lme4）
confint(m, parm="age_ord", method="Wald")                    # CI 是否含 0
# 分层 + 中介：群内 ρ、把样本级群体比例放进模型看 age 系数降幅
```
实测：细胞级 ρ=0.159（受伪重复灌水）→ 样本级 ρ=0.488（置换 p=0.0020，LOO 0.462–0.542）→ 校正 celltype 后系数 1.33→0.297 → 加随机效应 CI **[−0.027, 0.629] 含 0**（LRT p=0.077）→ 群内 ρ≈0（0.032/0.064/−0.064）→ 群体比例中介掉 36% ⇒ **组成性为主，写 low/探索性**。

## 5. 样本混杂分箱置换

```r
ordc <- names(sort(pt)); bins <- split(ordc, ceiling(seq_along(ordc)/20))
obs  <- sapply(bins, function(b) max(table(meta[b,"samplename"]))/length(b))   # ⚠️ meta[b,"col"] 不是 meta$col[b]
null <- replicate(500, { sh <- sample(meta$samplename)
  sapply(bins, function(b) max(table(sh[match(b, rownames(meta))]))/length(b)) })
thr <- quantile(null, 0.99); sum(obs > thr)   # 超阈箱数
```
实测：期望单样本占比 100/48≈2.1%；阈值（99% 分位）0.200；Monocle3 中位 0.150/最大 0.550 → 15/107 箱超阈；Slingshot 2/69。
**另做 leave-one-sample-out / 剔除超阈箱重算**：实测细胞级 ρ 0.159→0.119、样本级仍 0.467（p=8.1e-04）⇒ 写"部分区段受个体驱动"而不是全盘否定。

## 6. 内存与执行注意

- 2132 核的小数据也会 OOM（`无法分配大小为 6.7 Mb 的向量`）：Monocle3 CDS + Slingshot + lme4 同进程时尤其容易。
- **对策**：`gc()` 穿插在大步骤之间；把 bootstrap 等重活拆成**独立轻量 Rscript 进程**（一次只加载必要包，如 monocle3+igraph），别在一个 session 里既建 CDS 又跑 1000 次 bootstrap。
- 保存：`saveRDS(cds)` 必须在 `order_cells()` 之后（否则 `pseudotime()` 报 no pseudotime）；并行多 root 时最后要把主分析 root 复位重跑一次 `order_cells`。