# hdWGCNA 官方 workflow 运行坑（release v0.4.12 全流程实测）

> 2026-08-01 追加。在 `hdwgcna-windows-install-and-api.md` 基础上，补充**用官方 API 跑完整 workflow（Setup→Metacells→SetDatExpr→TestSoftPowers→ConstructNetwork→ModuleEigengenes→ModuleTraitCorrelation→ModuleUMAPPlot→HubGeneNetworkPlot→PlotKMEs）**时遇到的坑。旧记录用自写 cor() 绕过了 ModuleTraitCorrelation；本记录用官方函数全流程验证。

## 1. 加载：enrichR .onAttach 联网检查

`library(hdWGCNA)` 会触发 enrichR（Imports）的 `.onAttach`，它去 maayanlab.cloud 检查站点，网络不通时**阻塞整个加载**（不是 warning 是卡住/报错）。这在运行官方 workflow（需要真调用 hdWGCNA 函数）时是硬伤，旧记录"纯读结果 base R readRDS"不够。

```r
# 绕过 .onAttach：loadNamespace 加载 namespace 但不跑 .onAttach
loadNamespace("hdWGCNA")
# 之后所有调用加前缀：hdWGCNA::SetupForWGCNA(...)、hdWGCNA::ModuleEigengenes(...)
# 不要 library(hdWGCNA)
```

## 2. ModuleTraitCorrelation：traits 参数是 meta.data 列名字符向量，不是 data.frame

release 0.4.12 的 `ModuleTraitCorrelation(seurat_obj, traits=...)` 要求 traits 是**字符向量**，它内部从 `seurat_obj@meta.data[, traits]` 取列。直接传 data.frame 会报错。

```r
# 正确：先把效应向量写入 meta.data 列，再传列名
obj@meta.data$Aging  <- ifelse(obj$type %in% c("O_Pre","O_Post","OD_Pre","OD_Post"), 1, 0)
obj@meta.data$T2D    <- ifelse(obj$type %in% c("OD_Pre","OD_Post"), 1, 0)
obj@meta.data$ExYoung <- ifelse(obj$type=="Y_Post", 1, 0)
obj@meta.data$ExOld   <- ifelse(obj$type=="O_Post", 1, 0)
obj@meta.data$ExT2D   <- ifelse(obj$type=="OD_Post", 1, 0)
hdWGCNA::ModuleTraitCorrelation(obj, traits=c("Aging","T2D","ExYoung","ExOld","ExT2D"), group.by="annotation_L3", wgcna_name="MF_wgcna")
# 输出宽表: 5 效应 × (模块 × 细胞分组) 列，如 all_cells.red / RSS.red / Pure.Type.IIA.red ...
# 提取 all-tissue 热图: 过滤列名 ^all_cells\\. 并去前缀；p 表同构（* / ** / *** 由 p 值生成）
```

⚠️ **统计陷阱**：细胞级二值 trait（同一样本所有细胞共享值）会造成伪重复——正式投稿前必须**个体级聚合**（n=个体数）重算 module-trait 相关，否则 p 值功效过剩（metacell 级 n=6524 几乎全显著）。

## 3. ModuleUMAPPlot / ModuleFeaturePlot：future 并行传输超限

大对象（metacell 对象 + 全部模块 UMAP）经 future 并行传输时可能报 "8.36 GiB > 500 MiB"。脚本开头：

```r
future::plan("sequential")   # 关闭并行，顺序执行
```

## 4. TOM 路径重复拼接 bug（RunModuleUMAP / ModuleFeaturePlot 阶段报 TOM 路径不存在）

`ConstructNetwork(tom_outdir=绝对路径)` 后，对象里存的 TOMFiles 可能被再次拼接成 `hdwgcna/E:/.../TOM_official/`（Windows 冒号路径 dir.create 失败）。修复：

```r
wg <- obj@misc$MF_wgcna
wg$wgcna_net$TOMFiles <- "E:/.../data/TOM/MF_wgcna_TOM.rda"  # 指向真实绝对路径
obj@misc$MF_wgcna <- wg
```

## 5. GetHubGenes 只返回 10 模块（grey 被官方排除）

grey 是未分配模块，`GetHubGenes` 默认 exclude_grey=TRUE，这是**官方正常行为**不是 bug。hub 输出是 `kME` 排序的 top 基因（gene_name/module/kME），kME 是 WGCNA 审稿人认可的 hub 定义（网络 degree 不是）。

## 6. 官方 workflow 的标准图集（Methods 可引用 Morabito 2023）

```
official_01_softpower.png      ← TestSoftPowers + PlotSoftPowers
official_02_dendrogram.png     ← PlotDendrogram
official_03_module_trait.png   ← PlotModuleTraitCorrelation
official_04_module_umap.png    ← ModuleUMAPPlot
official_05_module_features.png← ModuleFeaturePlot
official_06_hub_network.png    ← HubGeneNetworkPlot
official_07_kmes.png           ← PlotKMEs
```

## 7. GO/KEGG 必须按官方模块重跑

旧 `module_go.rds` 若是早期（底层/旧模块划分）版本，模块归属已变，**必须用官方模块表重跑** enrichGO(BP)/enrichKEGG（bitr SYMBOL→ENTREZID）。0 GO 注释的模块（如 purple n=60）不是失败，是"未表征的条件特异新模块"——照实描述。

## 8. 续跑策略：超过 execute_r 900s 超时的阶段

- TOM 计算（10176 基因 blockwise）> 900s → `terminal(background=true)` + `Rscript script.R > log 2>&1` + notify_on_complete
- `data/TOM/*.rda` 是 blockwiseModules 中间产物，被 kill 后可续跑（跳过 TOM 重算）
- 中途产物 checkpoint：`saveRDS(obj, "official_obj_stepN.rds")` 每阶段存，续跑脚本从某 step 载入继续（省去 TOM 重算）
