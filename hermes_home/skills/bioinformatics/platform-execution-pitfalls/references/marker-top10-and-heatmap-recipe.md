# 亚群特异 marker top10 + 热图：粒度确认、四道把关、供体级一致率

> 触发场景：用户给一个**已注释 Seurat .rds**，说「找出每种细胞类型的特异 marker，top10 列出来，再画一张热图」。
> 2026-09-24 实测样本：人骨骼肌 `MF_2000.rds`（2132 细胞 × 51227 基因，48 供体 × 6 组，RNA + SCT 双 assay，Seurat 5.5.1）。
> Step 5 的结论口径是 L2 辩论裁决的硬要求，不是建议。
> R 脚本执行方式（`source()` 而非 Python 的 `exec(open())`）见 SKILL.md 坑表对应行。

---

## Step 0（最高优先级）：先枚举注释粒度，再跑任何 marker 分析

**同一对象常有多套注释列，且对象默认 Idents 可能与名为 `celltype` 的那列完全不是同一粒度。**

```r
for (v in c("celltype","annotation","annotation_L2","annotation_L3",
            "leiden_1","seurat_clusters","SCT_snn_res.1")) {
  if (v %in% colnames(obj@meta.data)) {
    cat(sprintf("--- %s (%d 类) ---\n", v, length(unique(obj@meta.data[[v]]))))
    print(table(obj@meta.data[[v]]))
  }
}
```

MF_2000.rds 实测（**别照抄，每次都要重查**）：

| 列 | 类数 | 内容 |
|---|---|---|
| `celltype` | **3** | RSS 162 / TypeI 797 / TypeII 1173 ← 名字最像"细胞类型"，但**不是**主注释 |
| `annotation_L2` | 4 | RSS / Specialized MF / Type I / Type II |
| `annotation` | 5 | RSS / Specialized MF / Type I / Type IIA / Type IIX |
| `annotation_L3` | **10** | 10 个肌纤维亚群 = **对象默认 Idents** |

⇒ 用户说"每种细胞类型"时，若默认 Idents 是 10 亚群、而 `celltype` 只有 3 类，**两者结论完全不同**。
处置：按默认 Idents（最细主注释）出主结果，同时把粗粒度版也一并算出交付，并在汇报**开头**说明两种粒度；
改粒度成本极低（一次 FindAllMarkers），但选错粒度整份交付作废。

⚠️ 各列**互不一致**是常见的（本例 `celltype` 的 TypeI 797 ≠ `annotation_L2` 的 Type I 864）——
不要用一列去校验另一列，只能按"哪一列是主注释"来定。

## Step 1：FindAllMarkers 固定口径

```r
DefaultAssay(obj) <- "RNA"          # RNA data = LogNormalize；SCT 另行对照
Idents(obj) <- "annotation_L3"      # 显式指定，不依赖默认 Idents
set.seed(123)
m <- FindAllMarkers(obj, only.pos = TRUE, min.pct = 0.25,
                    logfc.threshold = 0.5, test.use = "wilcox", verbose = FALSE)
m$p_adj_BH <- ave(m$p_val, m$cluster, FUN = function(p) p.adjust(p, method = "BH"))
```

- 🔴 **Seurat 的 `p_val_adj` 默认是 Bonferroni**，`FindAllMarkers` 不接受 `p.adjust.method` ⇒ 必须自己 `ave()` 出 BH 列。
  本例同一份结果：Bonferroni<0.05 只有 1029 个，BH<0.05 有 2065 个 —— 口径差一倍，结论表述会跟着变。
- top10 选取：按 `avg_log2FC` **降序**（不是最小 p 值），再以 `p_adj_BH < 0.05` 过滤。
- 落盘：长表（`cluster, gene, avg_log2FC, p_val, p_val_adj, p_adj_BH, pct.1, pct.2`）+ 宽表（每类一行、逗号分隔 top10）+
  `sessionInfo()` 与 `packageVersion("Seurat")` 进日志。

## Step 2：四道质量把关（缺任何一道都不要写"特异 marker"）

| 把关 | 做法 | 反面信号 |
|---|---|---|
| ① 金标准命中 | 与已知 marker 对照（骨骼肌：MYH7/MYH2/MYH1/MYL2/MYL3/TNNT1/TNNT3/TNNI1/TNNI2/ATP2A1/ATP2A2/MYBPC1/2/ACTN3/MYLPF） | 经典 marker 掉出 top10 ⇒ 参数或注释有问题 |
| ② 参数敏感性 | RNA vs SCT、`logfc.threshold` 0.25 vs 0.5、按 p 值排序 vs 按 logFC 排序，各算 top10 重合数 | 按 p 排序重合只 1–7/10 ⇒ 排序口径敏感，必须写进结论边界 |
| ③ RP/MT 标注 | `grepl("^(RPL|RPS|RPLP|MRPL|MRPS|MT-|MTRNR|MTATP|MTND|MTCYB|MTCO)", gene)` | 核糖体/线粒体基因占位，且亚群名若就按 RP 命名 ⇒ **命名循环** |
| ④ 供体级一致率 | 见 Step 3（**本配方核心**） | 一致率 <0.6 ⇒ 少数供体驱动嫌疑 |

本例实测：② vs SCT 重合 7–10/10、vs logfc0.25 重合 10/10、**vs 按 p 排序仅 1–7/10**；
③ 100 个 top10 基因里 12 个 RP/MT，**全部**落在 `RP_high(I)/(II)`（该亚群本身按核糖体蛋白命名）。

## Step 3：供体级方向一致率（轻量伪重复探针，几秒出结果）

**问题**：细胞级 wilcox 把 2132 个细胞当独立样本，真实独立重复单位却是 48 个供体，
每亚群每供体中位仅 4 个细胞 ⇒ p 值被伪重复放大，top10 可能由少数供体驱动。
完整答案要 pseudobulk，但**这个探针能先回答"是不是少数供体驱动"**：

```r
# mat: 基因 × 细胞 log-normalized 矩阵；ctv: 每细胞亚群；donor_v: 每细胞供体；gene_ct: 每基因归属亚群
cons <- do.call(rbind, lapply(seq_along(genes), function(i) {
  g <- genes[i]; k <- gene_ct[i]
  ok <- sapply(donors, function(d) {
    ik <- which(ctv == k  & donor_v == d)          # 该供体在该亚群内的细胞
    io <- which(ctv != k  & donor_v == d)          # 该供体在其它亚群内的细胞
    if (length(ik) < 2 || length(io) < 2) return(NA)   # 两侧都需 >=2 细胞才算可评估
    mean(mat[g, ik]) > mean(mat[g, io])            # 方向一致 = 在该亚群更高
  })
  data.frame(cluster = k, gene = g,
             n_donor_evaluable = sum(!is.na(ok)),
             donor_consistency = round(mean(ok, na.rm = TRUE), 3))
}))
```

本例实测：可评估供体 34–45/48；10 亚群均值 0.58（Pure Type IIA）～ 0.83（LRP1B+(I)）；
金标准 marker 近 1.0（ATP2A1 / MYL2 / MYH1 = 1.000，ATP2A2 / MYH7B = 0.978）；
低一致率名单精确指向可疑项（IGFN1 0.326 / CDH20 0.395 / MYBPH 0.425）——**这些就不能当"特异 marker"写**。
⇒ 该列应直接并入交付表，比事后解释有用得多。

## Step 4：热图（ComplexHeatmap 双版）

- 图1 单细胞级：`100 基因 × N 细胞` 行 z-score，`row_split = 基因归属亚群`、`column_split = 细胞亚群`、
  顶部 `HeatmapAnnotation` 细胞类型色条、`use_raster = TRUE`、`show_column_names = FALSE`。
- 图2 亚群平均表达：`100 基因 × 10 亚群`，`t(scale(t(avg)))`，版式更干净、更适合放进汇报。
- 配色 `colorRamp2(c(-2, 0, 2), c("#2166AC", "#F7F7F7", "#B2182B"))`；亚群色条按 I 型偏蓝 / II 型偏橙红分色系。

### ComplexHeatmap 两个实测坑

| 报错/现象 | 根因 | 修复 |
|---|---|---|
| `draw()` 报 `number of observations in right annotation should be same as nrow of the matrix`（2026-09-24 实测：矩阵 100 行，注释只有 10 个亚群） | `rowAnnotation` / 右侧注释的**长度必须等于热图矩阵行数**——误按"分组数"（10 亚群）而不是"行数"（100 基因）构造 | 要按亚群加右侧注释，就把值 **expand 到每行**（`rep()` 到 nrow 或按基因归属映射）；亚群层面的数字（如每类细胞数）放交付表/列标题里，别塞进 rowAnnotation |
| 图导出后 `print(ht)` 无输出 / 只出一张图 | ComplexHeatmap 的 Heatmap 对象**不是 ggplot**，`print()` 不适用；且一个设备里画一次就消耗掉了 | 包一层 `draw_export <- function(mk, base, w_mm, h_mm){ pdf(...); draw(mk()); dev.off(); svglite(...); draw(mk()); dev.off(); png(...); draw(mk()); dev.off(); tiff(...); draw(mk()); dev.off() }`，**每个设备里重新 `draw(mk())`**（`mk` 是返回 Heatmap 的函数） |

## Step 5：结论口径（L2 辩论裁决 2026-09-24，硬要求）

| 能写 | 不能写 |
|---|---|
| 「候选 / 描述性 top marker」；表名可用 `candidate_top10` | 「亚群特异 marker」——**过供体级检验之前绝不能写** |
| 「经典肌纤维类型（Pure I/IIA/IIX、RP_high）与已知 marker 高度一致」 | 把 RP_high 的 RP/MT 基因当独立特异证据（命名循环） |
| 「RSS 含 NSG2/SLC14A2/RYR2 等神经元/离子通道特征，身份待验」 | 直接断言 RSS 是新亚群 / 去神经支配细胞 |

升级条件（写进交付件的 reopen condition）：供体级 pseudobulk/混合模型下 top10 多数供体同向且 FDR<0.05、
QC/组别校正及去 RP/MT 后仍稳定、且有独立数据/蛋白/空间验证 —— 才可升级为"特异 marker"。

## 常见误判

- 把「显著 marker 数」（本例 71–437/类）当交付重点 → 用户要 **top10**，宽表一行一类最实用。
- 用 `celltype` 列当主注释 → 见 Step 0。
- 只给结论不给敏感性/一致率 → 结论会被下一轮辩论判 `modify`，白跑一遍。
- 一次性写完整管线再跑 → 平台要求分步执行。