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

## 关键教训：基因子集 ≠ 网络平坦
- ⚠️ 用 top3000 高变基因子集跑 WGCNA 会得到假平坦网络（R²=0.72@power1、单一 turquoise 模块）→ 误判"数据不适合 WGCNA"
- ✅ 改用**全部 WGCNA 基因（SetupForWGCNA fraction 0.05 → 10176）**后：power=10 R²=0.982，拆出 11 模块
- 教训：WGCNA 必须用完整基因集（或至少 >5000 基因），子集实验只用于参数预探

## 环境备注（本机）
- R 4.4.2 在 `C:/Users/23136/AppData/Local/R/R-4.4.2/`（execute_r 和 PATH 的 Rscript 用这个；Program Files 下只有 4.5.3/4.6.1）
- hdWGCNA 0.4.12 + WGCNA 1.74 + enrichR 3.4（.onAttach 联网不可达）已装进 AppData 库
- 网络：GitHub raw/codeload 有时可达，github.com 页面 curl 常 reset——R 包安装优先 pak 或已缓存

## 验证
- ad-hoc 验证模式：Temp 目录写 hermes-verify-*.R，独立重算关键统计量（如 blue~Aging cor），结果持久化到 log/verify_*_status.txt 后清理临时脚本
- 独立重算示例：cor(GetMEs(obj)[,"blue"], aging_vector) 与 CSV 中 all_cells.blue Aging 值对比，误差 <0.02 通过

## References
- 官方 tutorial: https://smorabit.github.io/hdWGCNA/articles/basic_tutorial.html
- hdWGCNA GitHub: https://github.com/smorabit/hdWGCNA
