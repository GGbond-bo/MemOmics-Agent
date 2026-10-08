---
name: archr-atac-analysis
description: >
  ArchR scATAC-seq 全流程：环境搭建 → Arrow 加载 → QC → LSI → 聚类 → Peak Calling
  → 差异可及性 → TF footprinting → motif 富集。支持跨物种 CRE 保守性评估。
  Signac 作为备选方案。触发：ATAC/ArchR/Signac/scATAC/peak calling/footprinting/染色质可及性/CRE保守性。
---

## 🔴 Windows 环境强制要求

### R 版本
- **必须 R 4.5.x**（不是 4.4.x 也不是 4.6.x）
  - 4.4.x：`TFMPvalue` 需要 R ≥ 4.5（Bioc 3.22+）
  - 4.6.x：无可用 Rtools 编译 GitHub 包
- R 4.5.x 安装到 `C:\Program Files\R\R-4.5.3\`
- Rtools45 安装到 **D 盘**（避免 C 盘空间不足）

### 库路径隔离
- `.Rprofile` **不得**硬编码路径 → 杀死多版本共存
- 正确做法：`R_LIBS_USER` 或 `.libPaths()` 按版本自动选择
- 本机配置：
  - R 4.4.2 库：`C:/Users/<user>/R/R-4.4.2-library`
  - R 4.5.3 库：`E:/R-libs/R-4.5.3`
  - R 4.6.1 库：`C:/Users/<user>/R/R-4.6.1-library`

### 🔴 致命陷阱：Bash 下 R segfault
- `terminal()` 在 Windows 上运行 bash (git-bash/MSYS)
- R 4.5.x 在 bash 下**必定 segfault**（Rcpp/RcppArmadillo 内存布局冲突）
- **唯一解**：所有 ArchR/Rscript 命令用 `cmd.exe /c` 包装
- 正确命令模板：
  ```
  cmd.exe /c "set PATH=D:\rtools45\x86_64-w64-mingw32.static.posix\bin;D:\rtools45\mingw64\bin;%PATH% && C:\PROGRA~1\R\R-4.5.3\bin\Rscript.exe --vanilla script.R"
  ```

---

## ArchR 安装流程（已验证）

### 1. 安装 R 4.5.3
```
# 从 CRAN 下载 R-4.5.3-win.exe，安装到 C:\Program Files\R\R-4.5.3
# 不勾选"添加到 PATH"
```

### 2. 安装 Rtools45 到 D 盘
```
# 下载 rtools45.exe → D:\rtools45
# 手动运行或静默安装：rtools45.exe //SILENT //DIR="D:\\rtools45"
# 验证：D:\rtools45\x86_64-w64-mingw32.static.posix\bin\gcc.exe --version
```

### 3. 安装 ArchR + 依赖
```r
.libPaths(c("E:/R-libs/R-4.5.3", .libPaths()))
Sys.setenv(BINPREF = "D:/rtools45/x86_64-w64-mingw32.static.posix/bin/")

# Bioconductor 依赖（全部走西湖镜像）
options(BioC_mirror = "https://mirrors.westlake.edu.cn/bioconductor")
BiocManager::install(c("TFMPvalue", "TFBSTools", "motifmatchr", "chromVAR",
  "ComplexHeatmap", "rhdf5", "BSgenome.Hsapiens.UCSC.hg38"))

# CRAN 依赖（走清华镜像）
options(repos = c(CRAN = "https://mirrors.tuna.tsinghua.edu.cn/CRAN"))
install.packages(c("devtools", "ggrepel", "gridExtra", "harmony", "plyr",
  "Seurat", "SeuratObject", "sparseMatrixStats", "uwot"))

# ArchR 本体 + chromVARmotifs
devtools::install_github("GreenleafLab/chromVARmotifs", upgrade="never")
devtools::install_github("GreenleafLab/ArchR", ref="master", upgrade="never")

# 验证
library(ArchR)  # 应输出 ASCII art 火炬 + 版本号
```

---

## 标准 ATAC 分析流水线

### Phase 1: 加载预制的 Arrow 文件
- 用户已提供 Arrow 文件 → 不需要 `createArrowFiles()`
- 直接 `ArchRProject(ArrowFiles, copyArrows=FALSE)`
- 不要 symlink（Windows 无管理员权限失败）→ 直接 copy 或使用原始路径

### Phase 2: QC
```r
# Arrow 文件已含预制 QC 指标：
#   TSSEnrichment, nFrags, DoubletScore, BlacklistRatio, PassQC
# 过滤：TSSEnrichment >= 4, nFrags > 1000
proj <- proj[proj$TSSEnrichment >= 4 & proj$nFrags > 1000, ]
```

### Phase 3: LSI + UMAP + 聚类
```r
proj <- addIterativeLSI(proj, useMatrix="TileMatrix", iterations=2,
  clusterParams=list(resolution=0.2, sampleCells=10000),
  varFeatures=25000, dimsToUse=1:30, force=TRUE)

proj <- addUMAP(proj, reducedDims="IterativeLSI", force=TRUE)
proj <- addClusters(proj, reducedDims="IterativeLSI", resolution=0.5, force=TRUE)
```

### Phase 4: Peak Calling（长任务，必须后台）
```r
proj <- addGroupCoverages(proj, groupBy="Clusters")
pathToMacs2 <- findMacs2()
proj <- addReproduciblePeakSet(proj, groupBy="Clusters", pathToMacs2=pathToMacs2)
```
- 预计耗时：~25 秒/组 × 集群数 × 样本数（如 21 群 × 3 样本 = 57 组 ≈ 25 分钟）
- 必须用 `terminal(background=TRUE, notify_on_complete=TRUE)` 或 Popen 脱离式
- 每步完成后 `saveRDS()` 保存 checkpoint

### ✅ Phase 4 官方参数默认值（formals() 实测 2026-08-29，勿凭记忆写）
用户会逐行对照 ArchR 官方文档（bookdown chapter 12）检查代码；多写/错写参数会被当场质疑。写参数前先实测：
```r
formals(ArchR::addGroupCoverages)        # 官方默认
formals(ArchR::addReproduciblePeakSet)
```

| 函数 | 参数名 | 官方默认值 |
|------|--------|-----------|
| `addGroupCoverages` | `minCells` | **40** |
| | `maxCells` | **500** |
| | `maxFragments` | **25*10^6**（⚠️ 曾误记为 8e7，实际 2500 万） |
| | `minReplicates` | 2 |
| | `maxReplicates` | 5 |
| | `sampleRatio` | 0.8 |
| `addReproduciblePeakSet` | `peakMethod` | "Macs2"（官方推荐，绝对推荐） |
| | `reproducibility` | "2"（至少 2 个 pseudo-bulk 重复有 peak） |
| | `peaksPerCell` | 500（防小群贡献低质量 peak） |
| | `minCells` | 25 |
| | `pathToMacs2` | `findMacs2()`（默认就是自动找） |
| | `shift` / `extsize` | -75 / 150（MACS2 经典 ATAC shift） |
| | `method` / `cutOff` | "q" / 0.1 |
| | `additionalParams` | "--nomodel --nolambda" |
| | `excludeChr` | c("chrM","chrY") |

**官方最小可跑代码**（bookdown 12.1+12.2 原样，只写 3 个参数，其余走默认）：
```r
pathToMacs2 <- findMacs2()
proj <- addGroupCoverages(ArchRProj = proj, groupBy = "celltype")
proj <- addReproduciblePeakSet(ArchRProj = proj, groupBy = "celltype", pathToMacs2 = pathToMacs2)
```
> groupBy 必须用 `colnames(proj@cellColData)` 里真实存在的列名（如 Clusters / cellType8 / 自己加的注释列）。

> 🔴 **官方顺序铁律（2026-08-29 用户逐行对照 bookdown 12.2 当场纠正）**：`findMacs2()` 必须**先**跑（12.2 第一个代码块），再 `addGroupCoverages()`（12.1 峰值前必跑），最后 `addReproduciblePeakSet()`。不要把 findMacs2 排到 addGroupCoverages 之后。
> ⛔ **只写官网出现的参数**：官方示例只有 3 个参数（ArchRProj/groupBy/pathToMacs2）；minCells/maxCells/maxFragments 等是函数默认值不是官网教程参数，文档对照场景不要主动加——多写/错写会被用户当场质疑。用户问起再讲默认值表。

#### 🔴 `findMacs2()` 找不到 MACS2 → 手动传绝对路径（2026-08-29 用户集群实测）

官网原文："If you have installed MACS2 but ArchR cannot find it, you should provide the path to the function via the `pathToMacs2` parameter." conda 环境装的 macs2 默认不在 PATH 里，`findMacs2()` 会扑空——不是没装，是找不着：

```r
# 方式 A（推荐）：手动指定绝对路径（bin/macs2 是带 shebang 的 Python 脚本，conda env 的 python 没坏就能跑）
pathToMacs2 <- "/hwfssz3/.../miniconda3/envs/MACS2/bin/macs2"   # which macs2 或 conda env 路径
system(paste(pathToMacs2, "--version"))   # 先验证能打印版本号，避免白跑 5-10 分钟
proj <- addReproduciblePeakSet(proj, groupBy="celltype", pathToMacs2=pathToMacs2)

# 方式 B：把 conda bin 塞进 PATH 再让 findMacs2() 自己找
Sys.setenv(PATH = paste0("/.../envs/MACS2/bin:", Sys.getenv("PATH")))
pathToMacs2 <- findMacs2()
```
集群上先 `ls -l <path>/macs2` + `<path>/macs2 --version` 自检（Permission denied → `chmod +x`）。

#### 🔴 集群所以为"卡死"实为正常：CPU 不忙 ≠ 没在跑（2026-08-29 用户问"cpu没有太大动静"）

| 阶段 | 实际在做什么 | 瓶颈 | CPU 表现 |
|------|-------------|------|---------|
| `addGroupCoverages` | 从所有 Arrow 读 fragments → 合并 pseudo-bulk 覆盖度 → 写临时文件 | **磁盘 I/O**（几十个 200MB+ Arrow，几百 GB 读写） | 🔇 低（等 IO） |
| `addReproduciblePeakSet` | 逐个 group 调 MACS2（单核程序） | 单核计算 + 读覆盖文件 | 🔉 中（只有 1-6 核在算，50 核看整体自然低） |
| `addPeakMatrix` | 全量细胞 × ~20 万 peak 构建计数矩阵 | **I/O 绑定的，CPU 再多不加速** | 🔇 低 |

- 判断是否在跑（另开终端）：`ps aux | grep macs2`（有=已到 MACS2 阶段）；`top -u $(whoami)` D 状态=等磁盘 IO（正常）；R 进程消失=可能崩了
- **只有 addGroupCoverages 支持 threads 参数并行读 Arrow**；MACS2 本身单线程（1 group 1 callpeak）；50 线程也帮不了 addPeakMatrix
- 20 万细胞 / 8 celltype / 50 线程总耗时 ≈ 30-60 min（组覆盖 10-20 + MACS2 3-8 + PeakMatrix 15-30）；`threads=16` 帮助前两步；RAM ≥128GB 才上 50 线程（每线程 1-2GB）

### Phase 5: 差异可及性 / Marker Features
```r
proj <- addPeakMatrix(proj, force=TRUE)
markers <- getMarkerFeatures(proj, useMatrix="PeakMatrix",
  groupBy="AgeGroup", bias=c("TSSEnrichment","nFrags"), testMethod="wilcoxon")
```

#### ⚠️ `getMarkerFeatures` OOM 陷阱（2026-08-25 实测）
- 16万细胞 × 30个 cluster = 435次两两比较 → **默认参数会 OOM 崩溃**
- 崩溃特征：日志在 ~5 分钟后突然停止，**无任何 error/warning**，进程消失，日志末尾缺少 "Completed Pairwise Tests"
- **根因**：Wilcoxon 检验需要将整个矩阵加载到内存，cluster 对数 = n*(n-1)/2 次加载
- **修复**（选一）：
  ```r
  # 方案 A：限制每组细胞数（内存降到 1/10）
  markers <- getMarkerFeatures(proj, useMatrix="GeneScoreMatrix",
    groupBy="Clusters", bias=c("TSSEnrichment","log10(nFrags)"),
    testMethod="wilcoxon", maxCells=500)
  # 方案 B：用 Gaussian 近似（快 3-5 倍，内存少一半）
  markers <- getMarkerFeatures(proj, useMatrix="GeneScoreMatrix",
    groupBy="Clusters", bias=c("TSSEnrichment","log10(nFrags)"),
    testMethod="G")
  ```
- **优先用 GeneScoreMatrix**（~2万基因）而非 PeakMatrix（~20-50万 peaks），计算量差 1-2 个数量级
- `testMethod="wilcoxon"` 是 ArchR 官方教程写法，**不是** `"U"`（虽然 `"U"` 也能用但不规范）

#### ATAC 细胞类型注释工作流（非 RNA 可及性打分）
ATAC 没有 `AddModuleScore`（那是 Seurat 的），正确做法：
```r
# 1. 提取 GeneScoreMatrix
mat <- getMatrixFromProject(proj, useMatrix="GeneScoreMatrix")
mat <- assays(mat)[[1]]  # 基因 × 细胞

# 2. 手算组合打分（= Seurat AddModuleScore 的等价操作）
sigs <- list(
  ExN   = c("SLC17A7","CAMK2A","NEUROD6"),
  InN   = c("GAD1","GAD2","SLC32A1"),
  Astro = c("GFAP","S100B","AQP4"),
  Oligo = c("MBP","PLP1","MOBP"),
  OPC   = c("PDGFRA","CSPG4","SOX10"),
  Micro = c("CX3CR1","P2RY12","TMEM119"),
  Endo  = c("FLT1","PECAM1","CLDN5")
)
for (name in names(sigs)) {
  idx <- which(rownames(mat) %in% sigs[[name]])
  if (length(idx) > 0) {
    proj <- addCellColData(proj, data=colMeans(mat[idx,]),
                           name=paste0("score_", name))
  }
}
# 3. 画 UMAP 看分布 → 每个 cluster 取最高 score 的大群
```

### 🔴 Phase 5b: DA tiles 伪bulk — 统计单元铁律（2026-09-01 专利多年龄组教训）

**`getGroupSE` 的 `groupBy` 只能是"聚合单元"（individual/样本），绝不能是"分组变量"（年龄组/条件）**。千问生成的代码用 `groupBy="age_group"` 被当场纠正（用户多轮追问"为什么复杂""要用个体的吗"）：

| 写法 | 伪bulk 列数 | 后果 |
|------|:---:|------|
| ❌ `groupBy="age_group"` | 4 列（每组 1 列） | n=4 伪重复 → DESeq2 无法估计组内 dispersion → p/FDR 虚高，审稿人必抓 |
| ✅ `groupBy="individual"` | 40/20 列（每个体 1 列） | n=40（猴 n=20）真实重复 → dispersion 可靠 |

- **年龄组是 DESeq2 的 design 因子**，不是聚合单元：`DESeqDataSet(se, design=~age_group)` + `test="LRT", reduced=~1`
- **⚠️ 方法选型（2026-09-01 用户拍板）**：对齐 Zemke Science 2026（GSE278576）→ 该文官方方法**不是 DESeq2**，而是**连续年龄 Pearson + shuffle ×5000 + FDR<0.1**。用户被问"你确定人家文章使用的是这个吗?"启发后明确选择 **Pearson + shuffle 版**：每个 tile `cor(log2CPM, Age)`（Age=供体连续年龄），FDR<0.1 且 r>0=Up / r<0=Down；shuffle 置换供体年龄标签×5000 得经验 p；四年龄组只作**下游展示层**（Up/Down tiles 按组画趋势）。50 万 tiles 用向量化 `apply(lcpm,1,cor)` + `pt()` 替代逐行 cor.test（快 1000 倍）。完整脚本 → `references/archr-da-tiles-4age.md`
- **剔除个体（如猴 M4）必须在 `getGroupSE` 之前**过滤 project 细胞（`proj <- proj[keep, ]`），否则被剔除个体成为 NA-age 列 → stopifnot 报错或污染数据底（与 L2 数据底 meta60=40人+20猴不一致）
- **PeakMatrix ≠ TileMatrix**：L2 已有的个体级 PeakMatrix SE 不能用于 DA tiles；DA 需在同一 project 上 `getGroupSE(useMatrix="TileMatrix", groupBy="individual")` 重新聚合（分钟级，不贵）
- **colData 贴分组用 `match()` 按个体名对齐**，不用行号（SE 列顺序与 meta 行顺序不一定一致）
- **猴侧坐标是 MFA8/T2T 非 hg38**：DA tiles 原样输出，下游 agent 负责 liftover 映射
- Exceptionally old 组个体 <2 → DESeq2 组内方差不可估报错 → 并入 Old 重跑（Pearson 版无此问题，连续年龄天然处理）
- 完整人/猴双版本脚本 → `references/archr-da-tiles-4age.md`

#### 🔴 getGroupSE 三大坑（2026-09-02 猴/人双侧 530 万 tiles 实测，源码级确认）

**坑1：`divideN` 默认 TRUE → counts 被除以细胞数 → 全被过滤**
```r
se <- getGroupSE(proj, useMatrix="TileMatrix", groupBy="individual",
                 scaleTo=NULL, divideN=FALSE)   # ★ divideN=FALSE 才返回原始总 counts
```
`scaleTo=NULL` 只关归一化；`divideN=TRUE`（默认）在 getGroupSE 源码里还执行 `groupMat <- t(t(groupMat)/as.vector(nCells))` → 每个 tile 得小数"每细胞平均计数" → `rowSums(cnt) >= 2*ncol(cnt)` 全不满足 → 报 **`All tiles filtered out!`**。报错时先查 divideN，别改阈值。

**坑2：`rowRanges(se)` 为空 → 坐标在 `rowData(se)`**
getGroupSE 源码 69-70 行：`SummarizedExperiment(assays=assayList, colData=cD, rowData=featureDF)` —— **不填 rowRanges**。`rowRanges(se)` 返回 length=0，防御检查 `stop("rowRanges mismatch: length=0 vs nrow=6,085,841")` 必炸。坐标改从 `as.data.frame(rowData(se))` 取。

**坑3：rowData 坐标是 per-chr tile 伪坐标，不是真实坐标（liftover 必错）**
`.addTileMat` 源码 44-48 行：`featureDF <- DataFrame(seqnames, idx=seq_len(...), start=(idx-1)*tileSize)`。**列顺序 = seqnames, idx, start**：第二列是每染色体内的 tile 序号 idx，第三列是 `(idx-1)*500`（0-based 起点），按染色体分组连续排。直接当 start/end 写 CSV → 值如 `chr1,1587,793000`（end/start≈500、start 连续 +1）→ liftover 全错位。换算：
```r
fr <- as.data.frame(rowData(se))[keep, , drop=FALSE][valid, , drop=FALSE]
out <- data.frame(chr  = fr[[1]],
                  start = fr[[3]] + 1,        # (idx-1)*500 + 1
                  end   = fr[[3]] + 500,      # idx*500
                  r = r, p = p, q = q)
```
**自检信号**：正常 500bp tile `end-start ≈ 500` 且 `start` 间隔 500；若出现 `end/start ≈ 500` 或 `start` 连续 +1（1587,1588,1589…）→ 就是 idx 伪坐标没换算。
- 上千~上万行 CSV 可直接**后处理**修坐标（统计列 r/p/q 与坐标无关，无需重跑 getGroupSE）；r>0=Up / r<0=Down / q<0.1 判定不受影响
- **猴侧 20 样本 + FDR q<0.1 常见 0 个显著 tiles**（530 万次检验 FDR 极严）——up/down csv 只有表头是正常结果不是报错；M3 秩保守比较用 all.csv 全部 r 值即可，显著集为空只影响"显著 tile 跨物种重叠"类分析，需改用秩保守设计

完整修正脚本（含 divideN + rowData 坐标换算）→ `references/archr-da-tiles-4age.md`（v2.1）

### Phase 6: TF Footprinting + Motif（专利核心）
```r
proj <- addMotifAnnotations(proj, motifSet="cisbp", name="Motif")
proj <- addBgdPeaks(proj)
proj <- addDeviationsMatrix(proj, peakAnnotation="Motif")

# Footprinting
motifPositions <- getPositions(proj)
proj <- addGroupCoverages(proj, groupBy="AgeGroup")
seFoot <- getFootprints(proj, positions=motifPositions, groupBy="AgeGroup")
```

---

## 跨物种 CRE 保守性评估（专利方向）
> 详见 `references/hippocampus-annotation-markers.md`（人+猴海马 marker 列表 + 对齐表 + 亚群命名规则）
> 详见 `references/table-s1-donor-age-mapping.md`（GSE278576 样本→年龄映射铁律：只准代码匹配 Table_S1，禁止手写占位——曾因手排 age_map 被用户当场抓错）
> 详见 `references/archr-peak-calling-cluster-pitfalls.md`（HDF5 写权限根因 / 官方参数实测 / 张潇 NHPABC cCRE 参数 / BSgenome 澄清 / CPU 现象 / 20万细胞时间估算 / 样本名→individual 提取）

### 需要的数据
| 数据 | 用途 |
|------|------|
| 猴 ATAC (Arrow files) | R2: CRE 可及性 + R3: TF footprinting |
| 人 ATAC (ENCODE/GEO) | 同猴流程 → liftOver 坐标映射 |
| phastCons/phyloP (UCSC) | R1: 序列保守性 |
| JASPAR motif 数据库 | L3: TF 结合位点保守性 |

### 三层评估框架（纯 ATAC，不需要 RNA）
```
L1: 序列保守性 → liftover + phastCons + motif 扫描
L2: CRE 可及性保守性 → peak overlap Jaccard + 信号 Spearman + 衰老动态 species×age
L3: TF 结合保守性 → footprinting + motif 富集 + 结合强度比较

A/B/C/D 四级分类（B 类 = 序列+可及性保守但 TF 结合不同 → 核心创新）
```

### 专利从权留口
- 从权中预留 RNA 层（SCENIC regulon 保守性）和 Hi-C 层（3D 结构保守性）
- 独权只覆盖纯 ATAC 三层，后续数据充足时拓展

---

## ArchR vs Signac 对比

| 功能 | ArchR (R) | Signac (R) |
|------|:---:|:---:|
| Arrow 兼容 | ✅ 原生 | ❌ 需 fragments |
| Peak calling | ✅ 内置 MACS2 | ✅ MACS2 |
| 差异可及性 | ✅ | ✅ FindMarkers |
| TF footprinting | ✅ | ✅ Footprint() |
| motif 富集 | ✅ | ✅ FindMotifs() |
| 共可及性 | ✅ 独占 | ❌ |
| 跨物种 peak overlap | ✅ | ✅ |
| **官方支持** | ✅ Greenleaf Lab | ✅ Stuart Lab |

- 首选 ArchR（Arrow 兼容 + 共可及性）
- 备选 Signac（R 4.4.2 已装，无需额外 R 环境）

### ArchR vs SnapATAC/SnapATAC2（2026-08 调研，中立 benchmark 证据）
- 聚类精度：**SnapATAC2 > ArchR**（尤其复杂脑组织亚型、稀有类型；Luo 2024 Genome Biol benchmark）
- 速度：SnapATAC2 最快；内存：ArchR 最省；SnapATAC v1 >2万细胞内存爆炸不可扩展
- **库大小偏差**：LSI（ArchR/Signac）嵌入与测序深度强相关，跨样本/跨年龄比较需警惕混杂；SnapATAC 系（Jaccard）几乎不受影响
- footprinting/共可及性：ArchR 独占强项；跨物种 CRE 专利实施例建立在 ArchR 输出上，勿轻易换管线
- 详见 `references/archr-vs-snapatac-benchmark.md`（全文证据 + Europe PMC 抓取路径）
- **引用核实（2026-08-11 实测）**：任务委托给的 PMID 31072930（实为 PNAS 纹状体论文）与 31061468（实为 Sci Rep 植物 RNAi 论文）均与 ArchR/SnapATAC 无关。正确引用：ArchR=PMID 33633365（Nat Genet 2021, DOI 10.1038/s41588-021-00790-6）；SnapATAC=PMID 33637727（Nat Commun 2021, DOI 10.1038/s41467-021-21583-9）；SnapATAC2=PMID 38191932（Nat Methods 2024, DOI 10.1038/s41592-023-02139-9，委托给的 10.1038/s41592-024-02229-8 无法匹配）；Luo benchmark=PMID 39152456。**铁律：委托中的 PMID/DOI 引用前必须先 query_ncbi/pubmed 核实**，报告中附勘误说明
- SnapATAC v1 确认 EOL（GitHub 最后 push 2023-04-27，README 自 2019-09 起推荐 v2）；SnapATAC2 无 Windows wheel、缺 footprinting/chromVAR deviations/co-accessibility 模块
- 完整 15 维度对比报告（含总览表+选择建议+对跨物种项目的专项建议）：`results/memomics-1f916507/archr_vs_snapatac_report.md`

---

## 常见错误速查

| 错误 | 原因 | 修复 |
|------|------|------|
| `gzfile cannot open` reading RDS | 上一步超时未保存 | 从上一个 checkpoint 重跑 |
| `plotMarkerHeatmap(...): unused arguments (ArchRProj=, useMatrix=, groupBy=, markerGenes=, name=)` | 函数签名不匹配（ArchR 版本不同）或 `plotMarkerHeatmap` 被其他包遮蔽 | ① 诊断：`find("plotMarkerHeatmap"); packageVersion("ArchR"); args(ArchR::plotMarkerHeatmap)` ② 显式命名空间 `ArchR::plotMarkerHeatmap(...)` 排除遮蔽 ③ 若签名无 `ArchRProj`（0.9.x 旧版）→ 走 `seMarker` 路线：先 `markers <- getMarkerFeatures(...)` 再 `plotMarkerHeatmap(seMarker=markers, markerGenes=..., groupBy=...)`（2026-08-16 猴侧 MarkerHeatmap 实测） |
| bash 下 R segfault | Rcpp 与 MSYS 冲突 | 用 `cmd.exe /c` 包装 |
| `library(ArchR)` 失败 | 缺 Rtools 编译 | 确保 Rtools45 在 PATH |
| `loadArrowFiles` 不存在（`exists("loadArrowFiles")` → FALSE） | ArchR 1.0.2 部分安装/版本问题未导出该函数 | `exists("loadArrowFiles")` 确认；若 FALSE → 用 `rhdf5` 直接读 HDF5（见下方「rhdf5 回退方案」） |
| `h5read(arrow, "Fragmentation/FragmentCounts")` 不存在 | 箭头文件内部路径因 ArchR 版本/构建不同而异，**不能硬编码假设** | **先 `h5ls(af, recursive=TRUE)` 探索完整 HDF5 结构**，再按实际路径读取 |
| `TFMPvalue` not found | R < 4.5 | 必须 R 4.5.x |
| coverage 600s 超时 | 57 组太多 | 用 background=True 后台跑 |
| symlink 失败 | Windows 无管理员 | 直接 copy Arrow 文件 |
| `.libPaths()` 劫持 | `.Rprofile` 硬编码 | 改为版本自适应 |
| `getMarkerFeatures` 跑 5 分钟后静默死亡 | 16万+细胞 × 30+ cluster = OOM，日志无 error | 加 `maxCells=500` 或改 `testMethod="G"` |
| `addGroupCoverages` 报 `H5Fcreate: HDF5. File accessibility. Unable to open file` | loadArchRProject 加载的是**他人 Project**（outputDirectory 指向没写权限的目录）→ 创建 coverage .h5 失败；次要：残留损坏 .h5、磁盘满、NFS 写锁 | ① `getOutputDirectory(proj)` 确认指向；`touch <dir>/__test.tmp` 验写权限 ② `copyArchRProject()` 复制到自己可写目录，或改 `proj@projectMetadata$outputDirectory` ③ `unlink("GroupCoverages", recursive=TRUE)` + `force=TRUE` 重跑。完整排查见 `references/archr-peak-calling-cluster-pitfalls.md` |
| ATAC marker "在好几个亚群高表达" | 用了谱系级 marker（SLC17A7）打亚群 | 分层注释：先大群 → 大群内亚聚类 → 亚群级 marker |
| `AddModuleScore` 报错 "no applicable method for ArchRProject" | Seurat 函数不能直接用于 ArchRProject | 先 `getMatrixFromProject()` 提取矩阵，手算 `colMeans(mat[idx,])` |
| 跨物种注释说"用 TransferData 预测" | Zhang Xiao 2026 实际是手动 canonical marker 注释 | 读原文 Methods，不要猜方法 |
| `getEmbedding(proj, "UMAP")` 报错 "Embedding not in computed embeddings" | Harmony 整合后 embedding 名称为 `UMAPHarmony` 而非 `UMAP` | 用 `getEmbedding(proj, embedding="UMAPHarmony")`；先 `names(proj@embeddings)` 查看可用 embedding 名称 |
| `no slot of name "cellEmbeddings" for this object of class "ArchRProject"` | ArchRProject 没有 `cellEmbeddings` slot（那是 Seurat 的） | 用 `getEmbedding(proj, embedding="UMAPHarmony")` 或 `proj@embeddings$UMAPHarmony$df` |
| `getMatrixFromProject(proj, useMatrix="TileMatrix")` 触发 `Cannot allocate vector ... 2^31-1` | 大项目（几十 arrow / 几十万细胞）TileMatrix cell 维太大，`Matrix` cbind 溢出 | 逐 arrow 建 project 聚合到 sample 维（samples × tiles 小矩阵），详见 `references/tilematrix-sample-aggregation.md` |
| `getMatrixFromProject(..., cellNames=...)` → `unused argument (cellNames=...)` | **该函数没有 `cellNames` 参数**（formals 仅 8 个），且读全部 arrow 后 cbind，无按 cell 子集读单 arrow 的能力 | 每个 arrow 单独 `ArchRProject(ArrowFiles=af[i])` 再取矩阵；`.availableCells` 要写 `ArchR:::.availableCells(...)`。详见 `references/tilematrix-sample-aggregation.md` |
| 产出 `样本 × ~1万` 矩阵、列名全是 `GSM...#barcode` 细胞条码、体积只有几 MB | `assay(se)` 是 **tile(行) × cell(列)**；用了 `colMeans` 对 cell 求均值 → 拿到 n_cells 长度、名字=条码的向量，不是 tile 覆盖 | **用 `Matrix::rowMeans(assay(se))`**（对行=tile 求均值 → n_tiles≈608万、名=`chr:start-end`、值域 0-1 覆盖比例）。人猴 L2 比对两侧须同口径=覆盖比例。真伪自检：维度 `样本×608万`、列名 tile 坐标、体积 ~400MB。详见 `references/tilematrix-sample-aggregation.md` |
| `Error in getMatrixFromProject(proj, useMatrix="PeakMatrix"): useMatrix is not in Available Matrices` | **`addPeakMatrix()` 从未执行**——`addReproduciblePeakSet` 只生成 peak **坐标集合**（PeakSet），不生成 细胞×peak **计数矩阵**（PeakMatrix）。保存的 project 若只有 PeakSet，getMatrixFromProject 必然报错（2026-08-30 用户集群实测） | ① `getAvailableMatrices(proj)` 确认缺 "PeakMatrix" ② `proj <- addPeakMatrix(proj, force=TRUE)`（需能访问 Arrow，20万细胞 15-30min，I/O 瓶颈）③ `saveArchRProject(proj, ..., load=TRUE)` ④ 再取矩阵。**给用户的 peak calling 指令必须四步一起给：addReproduciblePeakSet → addPeakMatrix → saveArchRProject → getMatrixFromProject**；不要让用户跑完 call peak 就停下来 |
| peak CSV 里 `end-start=500` 被误判"非501bp" | **ArchR GRanges 是闭区间**：`width = end - start + 1`，501bp 的 peak 导出后 `end-start=500` 完全正常（2026-08-30 本会话差点误报） | 校验宽度用 `end-start+1`（或 R 的 `width()`），不要用 `end-start`；bed 转 CSV/跨格式对比时注意 0-based/1-based ±1 |
| `getGroupSE(groupBy="age_group")` 检年龄相关 DA | 把年龄组当聚合单元 → 每组仅 1 列 → n=4 伪重复，DESeq2 dispersion 不可估，p/FDR 虚高 | `groupBy="individual"`（40 列），年龄组放 `design=~age_group` 做 LRT；剔除个体（M4）必须在聚合前过滤 project；详见 `references/archr-da-tiles-4age.md` |
| `All tiles filtered out!`（getGroupSE 后 rowSums 过滤剩 0） | `divideN=TRUE`（默认）把 counts 除以组内细胞数 → 小数计数全被 `rowSums >= 2*ncol` 过滤 | `getGroupSE(..., scaleTo=NULL, divideN=FALSE)` 才返回原始总 counts；先查 divideN，别改阈值 |
| `rowRanges mismatch: length=0 vs nrow=...` | getGroupSE 的 SE **不填 rowRanges**，坐标在 `rowData(se)`（源码 `SummarizedExperiment(..., rowData=featureDF)`） | 坐标用 `as.data.frame(rowData(se))`，不要用 `rowRanges(se)`；完整解析见 Phase 5b「getGroupSE 三大坑」 |
| DA tiles CSV 坐标错（end/start≈500 或 start 连续 +1） | rowData 第 2 列是 per-chr tile idx、第 3 列是 `(idx-1)*500` 伪坐标，被误当 start/end | 换算 `start=col3+1, end=col3+500`（tileSize=500）；统计列 r/p/q 不受影响，可直接后处理修坐标不重跑 |

## rhdf5 回退方案（`loadArrowFiles` 不可用时）

当 ArchR 未导出 `loadArrowFiles`（如 1.0.2），直接用 `rhdf5` 读箭头文件。

### ⚠️ ArchR Arrow 文件 HDF5 结构（已验证 1.0.2）

```
/
├── Fragments/
│   ├── chr1/
│   │   ├── Ranges        ← N×2 matrix [start, fragment_size]  ← 读这个
│   │   ├── RGLengths     ← 每个 cell 的 fragment 数
│   │   └── RGValues      ← cell 索引
│   ├── chr2/ ... chrY/
├── Metadata/
│   ├── CellNames, nFrags, TSSEnrichment, DoubletScore, PassQC ...
└── TileMatrix/
    └── chr1/ ... (sparse matrix: data/indices/indptr)
```

**关键发现**：`Ranges` 的两列是 `[start_position, fragment_size]`，**不是** `[start, end]`！
- col1 = 染色体坐标 (start)
- col2 = fragment 长度 (bp)，范围通常 10-2000
- 因此 fragment size 直接取 `col2`，**不需要** `col2 - col1`

### 完整代码模板

```r
library(rhdf5)
library(ggplot2)

af <- "path/to/sample.arrow"

# 1. 先探索结构（必做！不同版本路径不同）
top <- h5ls(af)
chrs <- top$name[top$group == "/Fragments"]
cat("Chromosomes:", paste(chrs, collapse = ", "), "\n")

# 2. 读取所有染色体的 fragment sizes
frag_sizes <- c()
for (chr in chrs) {
  ranges <- h5read(af, paste0("Fragments/", chr, "/Ranges"))
  frag_sizes <- c(frag_sizes, as.numeric(ranges[, 2]))  # col2 = fragment size
}

# 3. 统计
cat("Total:", length(frag_sizes), "\n")
cat("Median:", median(frag_sizes), "bp\n")
cat("100-200bp:", round(mean(frag_sizes >= 100 & frag_sizes <= 200) * 100, 1), "%\n")

# 4. 画 Fragment Size Distribution（用 hist 避免 data.frame 大向量问题）
frag_sub <- frag_sizes[frag_sizes >= 0 & frag_sizes <= 800]
brks <- seq(0, 800, by = 5)
h <- hist(frag_sub, breaks = brks, plot = FALSE)
df <- data.frame(size = h$mids, count = h$counts)

ggplot(df, aes(x = size, y = count)) +
  geom_col(fill = "steelblue", alpha = 0.8, width = 4.5) +
  geom_vline(xintercept = c(147, 294), linetype = "dashed", color = "red") +
  annotate("text", x = 147, y = max(df$count) * 1.05, label = "147bp\n(nucleosome)",
           vjust = -0.2, color = "red", size = 3) +
  annotate("text", x = 294, y = max(df$count) * 1.05, label = "294bp\n(di-nucleosome)",
           vjust = -0.2, color = "red", size = 3) +
  labs(title = "Fragment Size Distribution",
       subtitle = paste0("n=", length(frag_sizes), " | median=", median(frag_sizes), "bp"),
       x = "Fragment Size (bp)", y = "Count") +
  theme_bw(base_size = 12)
```

**经验法则**：
- `data.frame(size = frag_sizes)` 在 >1000万行时可能失败 → 用 `hist()` + `data.frame(mids, counts)` 代替
- Ranges 可能因 int64 报错 → 加 `as.numeric()` 转换
- 高质量 ATAC-seq：中位数 ~150-200bp，100-200bp 占比 >30%

### 其他 Metadata 可直接读取

```r
# QC 指标（已含在箭头文件中）
nFrags <- h5read(af, "Metadata/nFrags")
tss <- h5read(af, "Metadata/TSSEnrichment")
doublet <- h5read(af, "Metadata/DoubletScore")
cells <- h5read(af, "Metadata/CellNames")
sample <- h5read(af, "Metadata/Sample")
```

**关键铁律**：h5ls 输出中实际含 fragment 坐标的 group 名因箭头版本而异，绝不能假设固定路径。先 `h5ls()` 探索，再读取。

## 保存 plotEmbedding 多基因输出

`plotEmbedding(..., name=markerGenes)` 传入多个基因时返回 **named list**（每个元素一张 ggplot），不是单张图。

```r
# 逐张保存
dir.create("markerEmbedding", showWarnings = FALSE)
for(g in names(p)){
  ggsave(paste0("markerEmbedding/", g, ".png"), p[[g]], width=8, height=6, dpi=150)
}

# 拼一张大图全览
library(patchwork)
wrap_plots(p, ncol=4) |>
  ggsave("all_markers_UMAP.png", width=24, height=20, dpi=300)
```

---

## ⚠️ 远程服务器数据分析工作流

当用户提供远程服务器路径（如 `/data/input/...`、`/hwfssz3/...`）时：
- **禁止** 在本地 `terminal` 中 `cd` 到该路径（必然失败）
- **正确做法**：生成完整的自包含 R/Python 脚本，让用户复制到服务器上运行
- 脚本开头用 `af <- list.files(".", pattern="xxx.arrow", full.names=TRUE)` 自动发现，或接受用户指定的绝对路径
- 用户会把结果（`h5ls` 输出、日志、截图）贴回对话 → 根据输出继续给下一步脚本
- 分步给（不要一次性出整个管线），每步跑完贴输出回来核对

**经验**：这类远程协作场景下，`h5ls()` 探索结构的脚本必须自包含（library + 文件路径 + h5ls + 打印），用户粘贴即可执行。

**🔴 集群脚本极简铁律（2026-09-01 用户当场质疑"这一步为什么要这么复杂？"）**：
- 能从 project 元数据拿的分组信息，**不要读外部 CSV**。用户给 meta CSV 匹配列时要先想：`cellColData` 里是否已有同源列？有 → 直接 `unique(getCellColData(proj, c("individual","age_group")))` + `match()`，省掉外部文件依赖、还保证与 L2 同源零错位。`unique()` 是为了去重同个体的多细胞行（不加也行，只是不干净）。
- 用户偏好：脚本直接贴对话（不 write_file 保存、不封装函数、20 行内能跑就行），分步给，每步跑完贴输出回来核对。解释留给回复正文，代码保持极简。

---

## 自动拆分长任务

- coverage 57 组耗时 25 分钟以上 → 必须后台
- 脚本每步完成后 `saveRDS()` → 不怕超时
- 每个 Phase 单独写脚本 → 断点续跑

## 🔴 跨会话恢复 Checklist

**警告：task_plan.md 可能来自旧会话（如 CellBender），描述的是完全不同的已完成任务。恢复时必须四源交叉验证。**

### 恢复步骤
```bash
# 1. 检查进程（谁在跑？）
tasklist | grep -i "Rscript\|python"

# 2. 检查 GPU（CPU密集型还是GPU密集型？）
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader

# 3. 检查 RDS checkpoint 进度（ArchR pipeline 特有）
ls -lt E:/专利/ArchR_Output/project_*.rds
# project_raw.rds → Phase 1 完成
# project_qc.rds → Phase 2 完成
# project_lsi.rds → Phase 3 完成
# project_clustered.rds → Phase 4 完成
# project_final.rds → Phase 5-6 完成

# 4. 检查 coverage 进度（如果 Phase 4 在跑）
ls E:/专利/ArchR_Output/GroupCoverages/Clusters/ | wc -l
# 每组 ~2-3 个 .coverage.h5 文件，57 组 = 114-171 文件
# 文件按 C1→C57 顺序生成 → 最大编号 = 当前进度
```

### 从断点续跑
- 上一个 checkpoint RDS 存在且完整 → 从该 RDS 加载，跳过已完成 Phase
- 上一个 checkpoint 不存在 → 从最早的 RDS 重跑
- 正在写的 RDS（mtime 活跃）→ 等待当前 Phase 完成

详见 `windows-bioinformatics-batch-processing` skill 的 `references/session-resumption-stale-taskplan.md`。
---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="ATAC-seq 分析 —— {样本}",
     context="方法: {ArchR/Signac} | 参数: {peak calling参数} | 结果: {n} peaks {m} motifs",
     knowledge_base_info=<KB内容>,
   )
   辩论: peak质量如何？FRiP分数？motif富集合理吗？与RNA数据一致吗？
3. save_conclusions(module="03_advanced", topic="ATAC", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| - | - | - | 2026-08-27 | doublet_umap.R | - | - |  |
| - | - | - | 2026-08-29 |  Macs2 | - | - |  |
| - | - | - | 2026-08-29 | peak_calling_defaults_check.R | - | - |  |
