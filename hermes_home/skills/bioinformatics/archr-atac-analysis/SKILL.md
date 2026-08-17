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
  - R 4.5.3 库：`USER_R_LIBS/R-4.5.3`
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
.libPaths(c("USER_R_LIBS/R-4.5.3", .libPaths()))
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

### Phase 5: 差异可及性
```r
proj <- addPeakMatrix(proj, force=TRUE)
markers <- getMarkerFeatures(proj, useMatrix="PeakMatrix",
  groupBy="AgeGroup", bias=c("TSSEnrichment","nFrags"), testMethod="wilcoxon")
```

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
| `TFMPvalue` not found | R < 4.5 | 必须 R 4.5.x |
| coverage 600s 超时 | 57 组太多 | 用 background=True 后台跑 |
| symlink 失败 | Windows 无管理员 | 直接 copy Arrow 文件 |
| `.libPaths()` 劫持 | `.Rprofile` 硬编码 | 改为版本自适应 |

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
