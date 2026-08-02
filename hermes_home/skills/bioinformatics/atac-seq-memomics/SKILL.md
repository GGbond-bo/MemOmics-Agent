---
name: atac-seq-memomics
description: "ArchR scATAC-seq 全流程: 环境搭建→Arrow文件→QC→降维→聚类→Peak calling→Motif→Footprinting→差异可及性→共可及性→导出"
version: 3.0.0
prerequisites:
  r_packages: ["ArchR", "Signac", "Seurat", "chromVAR", "motifmatchr", "ChIPseeker", "BSgenome.Hsapiens.UCSC.hg38"]
  python_packages: ["MACS2 (optional — TileMatrix fallback if unavailable, see references/macs2-windows-fallback.md)"]
  system_requirements: "ArchR needs R >=4.5.0 (TFMPvalue dep). R 4.5.3 is the goldilocks version — R 4.4.2 is too old (no TFMPvalue), R 4.6.1 is too new (no Rtools46). See references/windows_archr_setup.md for proven dual-R setup. Java >=8, >=16GB RAM for >50K cells"
---

# ATAC-seq 分析 (ArchR)

## Windows 双 R 环境 (ArchR + Seurat/Signac 共存)

ArchR 依赖 TFMPvalue → 需要 R ≥ 4.5.0。但版本选择有讲究：

| R 版本 | Rtools | TFMPvalue | ArchR 能装？ | 原因 |
|--------|:---:|:---:|:---:|------|
| 4.4.2 | Rtools44 ✅ | ❌ Bioc 3.20 没这个包 | ❌ | TFMPvalue 最早出现在 Bioc 3.21 |
| **4.5.3** | **Rtools44 可用** ✅ | ✅ Bioc 3.22 | ✅ **首选** | Rtools45 安装器有 bug，Rtools44+符号链接更可靠 |
| 4.6.1 | Rtools46 未发布 ❌ | ✅ | ❌ | 没有编译工具，GitHub 包源码编译失败 |

> 🏆 **R 4.5.3 是黄金版本。** 安装到 `C:\Program Files\R\R-4.5.3`（本体小），R 包库放 `E:\R-libs\R-4.5.3`（包很大，放 E 盘）。

调用：普通脚本用 `Rscript`，ArchR 脚本用 `"C:/Program Files/R/R-4.5.3/bin/Rscript.exe"`。

完整安装指南见 `references/windows_archr_setup.md`。

## Signac vs ArchR 选择

| 功能 | Signac | ArchR |
|------|:---:|:---:|
| peak calling | ✅ (需 MACS2) | ✅ (MACS2 或 TileMatrix 无 MACS2) |
| 差异可及性 | ✅ FindMarkers | ✅ (PeakMatrix 或 TileMatrix) |
| TF footprinting | ✅ | ✅ |
| **共可及性 (co-accessibility)** | ❌ | ✅ **ArchR 独占** |
| peak-to-gene linkage | ✅ LinkPeaks | ✅ 更成熟 |

> 跨物种 CRE 保守性评估需要共可及性 → 必须用 ArchR。

## 已知问题

### 🔴 安装相关
- **Rtools45 安装器有 bug** — exit code 2/5，无法静默安装。**解决方案**：复用 Rtools44，在 ucrt64 目录创建 gcc/g++/gfortran 符号链接指向 x86_64-w64-mingw32.static.posix/bin/
- **`.Rprofile` 劫持库路径** — 如果 `~/.Rprofile` 硬编码了 `R-4.4.2-library`，所有 R 版本都会被劫持到错误路径。**解决方案**：改为 `R_version <- paste(R.version$major, R.version$minor, sep='.'); .libPaths(c(paste0('E:/R-libs/R-', R_version), .libPaths()))`
- **Bioconductor 镜像选择** — 清华镜像没有 Bioc 包，西湖大学 (`mirrors.westlake.edu.cn`) 可用。CRAN 用清华，Bioc 用西湖
- **R 包库分离** — R 本体放 C 盘（~100MB），包库放 E 盘（几 GB）。通过 `.libPaths()` 控制

### 🔴 DLL 连锁损坏（taskkill 杀 R 进程后）— 2026-07-29 已验证

**现象**：`taskkill` 杀 Rscript 后，`library(ArchR)` 报一连串 `LoadLibrary failure: 找不到指定的程序`：
```
rlang.dll → data.table.dll → Rcpp.dll → magrittr.dll → Biobase.dll → ...
```

**根因**：R 进程被杀时正在使用 `E:/R-libs/R-4.5.3/` 下的 DLL 文件 → Windows 文件锁未释放 → DLL 损坏。损坏是连锁的——ArchR 加载链上任何一环断了就全崩。

**⚠️ 先确认 R 版本**：`Rscript --version` 可能显示 **R 4.4.2**（PATH 默认），但 `E:/R-libs/R-4.5.3/` 的包是为 R 4.5.3 编译的。4.4.2 加载 4.5.3 DLL 也会报同样的错。**先用 `"C:/Program Files/R/R-4.5.3/bin/Rscript.exe" --version` 确认。**

**修复（批量重装受损包，必须 `type="win.binary"`）**：
```r
"C:/Program Files/R/R-4.5.3/bin/Rscript.exe" -e '
.libPaths(c("E:/R-libs/R-4.5.3", .libPaths()))
# 先修核心依赖，顺序重要：Rcpp → rlang → data.table
install.packages(c("Rcpp", "rlang", "data.table"), 
  repos="https://cloud.r-project.org", type="win.binary", lib="E:/R-libs/R-4.5.3")
# Bioconductor 包（Biobase, S4Vectors, etc.）用 BiocManager
BiocManager::install(c("Biobase", "S4Vectors", "GenomicRanges", "SummarizedExperiment"),
  lib="E:/R-libs/R-4.5.3", ask=FALSE)
'
```

**预防**：杀 R 进程前先确认没有 R 脚本正在跑（`tasklist | grep Rscript`），优先等脚本自然结束。

### 🔴 MACS2 在 Windows 上不可安装 → TileMatrix 替代方案
- **MACS2 pip install 失败** — Cython 3+ 不兼容 MACS2 的 `cimport numpy` 旧语法（`'numpy/uint32_t.pxd' not found`）
- **MACS3 也失败** — 需要 VC++ 14.0 构建工具
- **conda install 不可靠** — conda 环境损坏时会静默失败
- **解决方案**：用 ArchR 的 `addTileMatrix(tileSize=500)` 替代 `addReproduciblePeakSet()`，无需 MACS2。差异分析用 `useMatrix = "TileMatrix"`。详见 `references/macs2-windows-fallback.md`

### 🟡 运行相关
- **ArchR Arrow 文件是自定义格式** — 不是 Apache Arrow IPC 也不是 Parquet。只能用 ArchR 包读取，pyarrow 读不了
- **Windows 必须 threads=1** — ArchR 并行依赖 `mclapply`（Unix fork），Windows 无 fork → `addArchRThreads(threads=1)` 是强制要求。多线程会随机崩溃，日志无明确错误，极易误诊为内存问题。所有脚本开头必须显式设置
- **BiocManager::install 输出缓冲** — 大包下载时 R 缓冲所有输出，看起来像卡住了但实际在下载。通过检查库目录的包数量判断进度

### 🔴 Bash+R segfault (exit 139) — Windows 必用 cmd.exe 绕过

**现象**：在 MSYS2/git-bash 下跑 `Rscript` 偶发 segfault (exit code 139)，readRDS 大文件时概率最高。`terminal(background=True)` **不能** 解决此问题（已验证无效）。

**根因**：bash 与 R 的动态库加载器冲突，ArchR 加载 rhdf5/Matrix 等包时触发。

**唯一切实修复**：用 `cmd.exe /c` 调用 `.bat` 包装脚本，完全绕过 bash：

```bash
# ❌ 不行 — bash 中直接跑 R，高概率 segfault
Rscript script.R

# ✅ 可行 — cmd.exe 包装
cmd.exe /c "E:\path\to\run.bat"
```

`.bat` 包装模板：
```bat
@echo off
echo Started: %DATE% %TIME%
"C:\Program Files\R\R-4.5.3\bin\Rscript.exe" "E:\path\to\script.R" > "E:\path\to\output.log" 2>&1
echo EXIT_CODE=%ERRORLEVEL%
echo Finished: %DATE% %TIME%
```

Terminal 调用方式（Hermes）：
```
terminal(command='cmd.exe /c "E:\\path\\to\\run.bat"', background=True, notify_on_complete=True, timeout=3600)
```

> ⚠️ `terminal(background=True)` 仍走 bash → Rscript，segfault 照旧。**必须** cmd.exe 包装。

### 🔴 非人类基因组 / NCBI 染色体命名 — 2026-07-29 已验证

**现象**：
- `addTileMatrix()` → 明确报错 `Chromosome chr1 not in ArrowFile! Available: NC_088375.1, NC_088376.1, ...`
- `addGroupCoverages()` → **静默崩溃** exit_code=1，无报错信息，只完成了部分组（如 21/57）
- `addArchRGenome("hg38")` 调用时不报错，但所有下游函数失败

**根因**：Arrow 文件使用 NCBI RefSeq 染色体命名（如食蟹猴 T2T 组装的 `NC_088375.1`），而 `addArchRGenome("hg38")` 构建 UCSC 命名（`chr1`）。染色体名不匹配 → ArchR 找不到数据。

### 🔴 物种身份验证（染色体 accession → NCBI 查证）— 2026-08-02 已验证

**现象**：分析全程假设猴数据是 *Macaca mulatta*（猕猴），但 `query_ncbi(db="nuccore", query="NC_088375.1[Accession]")` 返回 **Macaca fascicularis**（食蟹猴）isolate 582-1 chromosome 1, **T2T-MFA8v1.1**，length 234,122,563。文件名/目录名/旧记忆都可能误导物种假设。

**影响**（跨物种专利/分析致命）：
- **LiftOver chain 选择错误** — rheMac10/rheMac8 是 *mulatta* 的 chain；*fascicularis* 需要 T2T-MFA8v1.1 → hg38 的 chain（UCSC 需按 MFA8 组装找）。用错 chain = 坐标映射全错。
- **直系同源映射错误** — ortholog 配对表按物种选择（human↔mulatta vs human↔fascicularis），用错物种丢失/错配直系同源 CRE。
- **专利权利要求物种错误** — 交底书/权利要求写"猕猴"而数据是"食蟹猴"→ 实施例与权要不一致，审查员可质疑。

**验证方法（每批新数据必须先做，<1 min）**：
```
query_ncbi(db="nuccore", query="<任意染色体 accession>[Accession]")
# 例: query="NC_088375.1[Accession]" → 返回 organism + assembly 名 + length
# 与 macaque_chrom_sizes.json / Arrow TileMatrix params 中的 length 对比确认同一组装
```

> ⚠️ **铁律**：**任何跨物种分析的物种身份，必须用染色体 accession 查 NCBI nuccore 确认**，不能靠文件夹名、GEO 摘要、旧记忆假设。物种错了，下游 chain/ortholog/权利要求全错。

**修复（最小侵入式 — 2026-07-29 食蟹猴 scATAC 验证）**：

```r
# ❌ 不要用 createGenomeAnnotation — 强制 BSgenome lookup → 报错退出
# ❌ 不要用 SimpleList — ArchR 内部方法不识别自定义 S3 类
# ✅ 直接替换已有 hg38 genome annotation 的 chromSizes（最小侵入）
library(ArchR); addArchRGenome("hg38")     # 初始化环境
proj <- readRDS("project_clustered.rds")

mac_chrom_gr <- GRanges(
  seqnames = c("NC_088375.1", "NC_088376.1", ...),
  ranges = IRanges(start=1, end=c(234122563, ...))
)
proj@genomeAnnotation$genome <- "Macaca_fascicularis"
proj@genomeAnnotation$chromSizes <- mac_chrom_gr
proj@geneAnnotation$genome <- "Macaca_fascicularis"
# ✅ addTileMatrix + getMarkerFeatures 全部正常工作
```

**染色体大小提取**：Python 脚本从 Arrow HDF5 读取 `TileMatrix/Info/Params`：
```python
import h5py, json
with h5py.File("sample.arrow", "r") as f:
    params = json.loads(f["TileMatrix"]["Info"]["Params"][()])
    chrom_sizes = {c: s for c, s in zip(params["chromosomes"], params["chromosomeLengths"])}
```

完整流程见 `references/custom-genome-non-ucsc.md`。

> ⚠️ **调试铁律**：优先测 `addTileMatrix` — 它有明确报错信息（`Chromosome chr1 not in ArrowFile! Available: NC_088...`）。`addGroupCoverages` **也会因为同样原因静默崩溃** — 以前被误诊为内存问题。2026-07-29 验证：修复基因组后 TileMatrix 3 样本×21 chr → 全部通过，getMarkerFeatures 6M tiles → 产出 50 个 DA tiles。

### 🟡 中文路径导致 terminal() workdir 被拦截

**两种崩溃模式**：

| 模式 | 现象 | 根因 |
|------|------|------|
| **Foreground 超时** | 跑到 18-23/57 后静默消失，无 error、无 coredump | `terminal()` foreground 600s 硬限 → 进程被系统 kill。57 组需 ~14 min |
| **Bash segfault** | 随机 exit 139，或"hang"（进程存活但日志停） | MSYS bash 与 R 动态库加载器冲突，多组时概率最高 |

**修复（必须 background + cmd.exe /c 双管齐下）**：

```bash
# ✅ 唯一可靠方式 — background + cmd.exe 绕过 bash + 超长 timeout
terminal(command='cmd.exe /c "\"C:/Program Files/R/R-4.5.3/bin/Rscript.exe\" script.R > log.txt 2>&1"',
         background=True, notify_on_complete=True, timeout=3600)
```

**修复（首选 groupBy="Sample" 减少组数）**：3 组 vs 57 组，~6min，且回避 bash 崩溃窗口
```r
# ✅ groupBy="Sample" 只需 3 组
proj <- addGroupCoverages(proj, groupBy = "Sample", force = TRUE)
saveRDS(proj, "project_cov.rds")
# TileMatrix + getMarkerFeatures(useMatrix="TileMatrix", groupBy="AgeGroup") 正常工作
```

**替代（必须 per-cluster 时）**：手动循环 1 个 cluster 1 次
```r
for(cl in unique(proj$Clusters)) {
  sub <- addGroupCoverages(proj[proj$Clusters==cl,], groupBy="Sample", force=TRUE)
  saveRDS(sub, paste0("cov_C", cl, ".rds"))
}
```

**⚠️ 已生成的 coverage .h5 无法被 `force=FALSE` 复用**：若 `project_clustered.rds` 在 `addGroupCoverages` 之前保存，重载后 ArchRProject 不含 coverage 元数据 → `force=FALSE` 检测不到已有文件 → 重新生成全部。结论：必须 `saveRDS(proj, "project_cov.rds")` 紧跟 `addGroupCoverages`。

**📡 进度监控与卡死检测**：addGroupCoverages 运行时，ArchRLogs 目录（`ArchRLogs/ArchR-addGroupCoverages-*.log`）包含逐染色体的详细进度（`Group X of Y : Processed Fragments Chr (A of 21)`），比 stdout 更精确。心跳脚本应监控 ArchR log 而非脚本 stdout。卡死判定：ArchR log 行数在 >2 个心跳间隔（>4 分钟）无变化。完整监控指南 → `references/coverage-progress-monitoring.md`

### 🟢 getMarkerFeatures 结果验收基准 — 2026-07-29 猕猴海马验证

**正常产出（食蟹猴 3 样本/36K cells/21 clusters，基因组修复后）**：
| 指标 | 值 |
|------|-----|
| TileMatrix tiles | 6,085,841 (500bp × 21 chr × 3 samples) |
| getMarkerFeatures 耗时 | ~3 min (2 pairwise comparisons) |
| DA tiles (strict: FDR<0.05, \|FC\|>0.5) | 50 (Old: 19 Up/31 Down) |
| DA tiles (loose: FDR<0.1, \|FC\|>0.25) | 122 (Old: 55, Young: 67) |
| markers_age_tiles.rds | 183MB |

> 如果 `getMarkerFeatures` 返回全零且你确认基因组正确 → 仍需排查。下面是全零诊断流程：

### 🟡 getMarkers 输出结构（DFrame 而非 GRanges）— BED 导出陷阱 — 2026-08-02 已验证

**现象**：`getMarkers(markers_age, cutOff=...)` 返回 `list(loose, strict)` → 每项是 `SimpleList(Old, Young)` → 元素是 **DFrame**（非 GRanges！），列为 `seqnames, idx, start, Log2FC, FDR, MeanDiff`。`as.data.frame(gr)[, c("seqnames","start","end")]` 会报错 — **没有 `end` 列**。

**正确的 BED 导出（跨物种 LiftOver 输入）**：
```r
da <- readRDS("da_tiles.rds")
loose <- da$loose                    # SimpleList
df <- as.data.frame(loose[["Old"]]) # DFrame → data.frame
# TileMatrix 500bp: end = start + 500 - 1
bed <- data.frame(chr=as.character(df$seqnames),
                  start=df$start - 1,   # BED 是 0-based
                  end=df$start + 500 - 1)
write.table(bed, "da_tiles_Old.bed", sep="\t", row.names=FALSE, col.names=FALSE, quote=FALSE)
```

> ⚠️ `da$loose[[grp]]` 这种链式 `$`+`[[` 在 SimpleList 上会报 "this S4 class is not subsettable" — 必须先 `loose <- da$loose` 再 `loose[[grp]]`。

### 🔴 getMarkerFeatures 全零结果诊断 — 2026-07-29 已验证

**现象**：`getMarkerFeatures(useMatrix="TileMatrix", groupBy="AgeGroup")` 返回**所有 tile log2FC=0, FDR=1, pval=1**，稀疏矩阵 5×5 全为空（`.`）。总 tile 数正常（25 万/染色体），但无任何差异可及性。

**已触发条件**（猴海马 scATAC, 2026-07-29）：
- 3 样本: Old=1 (O1_Hip_1), Young=2 (Y3_Hip_1, Y3_Hip_2)
- 35,879 cells, 21 clusters, nFrags>1000+TSS≥4
- `addTileMatrix(tileSize=500)` → `getMarkerFeatures(groupBy="AgeGroup", testMethod="wilcoxon")`
- 食蟹猴 T2T 基因组 (NCBI NC_088xxx), 非 UCSC 命名

**根因分析（3 种可能，按概率排序）**：

| # | 可能原因 | 概率 | 诊断方法 |
|---|---------|:---:|---------|
| 1 | **样本量不足** — Wilcoxon 对 Old=1 vs Young=2 无统计功效 | ⭐⭐⭐ | `table(proj$AgeGroup)` 看每组样本数 |
| 2 | **TileMatrix 过于稀疏** — 500bp tile 中 ATAC 信号极低（SparseMatrix `NonZeroEntries` 占比 <0.1%） | ⭐⭐ | 检查 `mean1`/`mean2` 列是否全为 0 — 全 0 说明矩阵真的是空 |
| 3 | **基因组命名不匹配** — `addArchRGenome("hg38")` 但 Arrow 是 NCBI 命名 → TileMatrix 建在错误坐标上 | ⭐ | `head(rownames(getMatrixFromProject(proj, "TileMatrix")))` 检查 tile 名 |

**修复流程**：

```r
# Step 1: 确认问题类型
markers_age <- readRDS("markers_age_tiles.rds")
assay(markers_age)[1:10, 1:5]  # 全 0? → 问题 1 或 2
rowData(markers_age)$mean[1:10]  # 全 0? → TileMatrix 真的是空 (问题 2)

# Step 2: 尝试放宽阈值检查是否有微弱信号
da_loose <- getMarkers(markers_age, cutOff = "FDR <= 0.1 & abs(Log2FC) >= 0.1")
# 如果 da_loose 也是空 → 确认是统计功效问题

# Step 3: 替代方案
# A. 改用 groupBy="Sample" (3组) 而非 "AgeGroup" (2组) — 提高 group 数
# B. 降 tileSize 到 100bp → 更密集、更灵敏
# C. 增加样本 (需要更多 Arrow 文件)
# D. 换 pseudobulk DESeq2 按个体聚合 → 每个 cluster×sample 一个 pseudobulk
```

> ⚠️ **不要直接断定"生物学无差异"** — 绝大多数全零结果是统计功效问题而非真阴性。先诊断再下结论。完整诊断决策树见 `references/getmarkerfeatures-all-zero-diagnostic.md`。

### 🔴 markerPlot DA 可视化崩溃 — 2026-07-29 已验证

**现象**：`markerPlot()` 对 TileMatrix SummarizedExperiment 产生 0 字节 PDF / 无输出 / 超时。

**根因**：
1. **markerPlot 已废用** — ArchR 1.0.3 明确警告 `markerPlot不再有用，请用'plotMarkers'`
2. markerPlot 对大 SE（>100 万 tile）不稳定。PDF 矢量格式为每个点生成独立路径 → 6M 点 = 130MB+ 文件 → 600s 超时

**回退方案**：从 `assay(se, "Log2FC"/"FDR")` 直接提取矩阵 → base R `plot()` 生成 PNG/PDF。<10 秒完成，无需 ggplot2。完整模板见 `references/da-plotting-fallback.md`。

```r
# 最小火山图（base R, <5s for 6M points）
markers <- readRDS("markers_age_tiles.rds")
comp_name <- colnames(assay(markers, "Log2FC"))[1]  # e.g. "Old"
log2fc <- assay(markers, "Log2FC")[, comp_name]
fdr <- assay(markers, "FDR")[, comp_name]
negLog10FDR <- -log10(fdr + 1e-300)

png("volcano.png", width=1600, height=1400, res=200)
sig <- rep(rgb(0.7,0.7,0.7,0.4), length(log2fc))
sig[fdr<0.05 & log2fc>0.5] <- rgb(0.9,0.2,0.2,0.6)
sig[fdr<0.05 & log2fc<(-0.5)] <- rgb(0.2,0.3,0.9,0.6)
plot(log2fc, negLog10FDR, col=sig, pch=16, cex=0.4,
     xlab="Log2FC", ylab="-log10(FDR)", main=comp_name)
abline(h=-log10(0.05), lty=2, col="grey40")
abline(v=c(-0.5,0.5), lty=2, col="grey40")
dev.off()
```

### 🔴 addGroupCoverages 命名不匹配陷阱

**现象**：之前成功生成过 coverage .h5 文件，重载 `project_clustered.rds` 后 `addGroupCoverages(force=FALSE)` 全部跳过，尝试重新生成所有文件 → 慢且可能崩溃。

**根因**：`project_clustered.rds` 在 `addGroupCoverages` **之前** 保存的。重载后 ArchRProject 不含 coverage 元数据，ArchR 不认识已有的 `.h5` 文件。即使文件存在磁盘上，`force=FALSE` 也无法跳过。

**修复策略**：
1. **分步保存 RDS**：每步完成后立即 `saveRDS`，不要等到分析结束
   ```r
   proj <- addGroupCoverages(proj, groupBy="Clusters")
   saveRDS(proj, "project_cov.rds")  # ← 立即保存！
   ```
2. 若已丢失 coverage 元数据 → 用 `force=TRUE` 从头重建（~15-20 min for 36K cells, 21 clusters）
3. 先运行诊断脚本检查：对比 `getCellColData(proj, "Sample")` 生成的文件名与磁盘上的 `.h5` 文件

### 🟡 Motif 富集分析 — 非 UCSC 基因组 + 小 DA tile 集

DA tiles 数量少（<100）时，Fisher 检验对 633 个 JASPAR motif 无统计效力 → 改用**得分排序法**（fg/bg mean score fold-change）。详见 `references/motif-analysis-non-ucsc-small-sets.md`：

- **JASPAR2020 而非 JASPAR2024** — 后者 `getMatrixSet` API 已损坏
- **NCBI→UCSC 映射 + BSgenome 边界检查** — T2T 坐标可超出 rheMac10 染色体末端
- **`name(motifs[[id]])` 将 MA 编号转 TF 名**
- 2026-07-29 验证：CEBPB (FC 5.28) Old 富集，HOXB8 (FC 8.38) Young 富集
- **跑完 ≠ 收尾**（2026-08-02 教训）：motif 分析完成后必须出 Top-TF 柱状图（Old 红 #E64B35 / Young 蓝 #4DBBD5）+ 用 anchor 插入法整合进已有 HTML 报告 + 更新 task_plan + record_run。可视化配方/HTML 追加代码/收尾协议见同一 reference 的 "Visualization + HTML Report Integration" 一节
- **跑完 ≠ 下一步可自动启动**（2026-08-02 唤醒验证）：Phase 全 complete 后系统唤醒/用户问进度时，必须走"停止命令检查 + 外部依赖门控 + 三源验证 + 汇报给选项"的唤醒门控协议，不自动启动跨物种对比等新任务。完整协议见 `references/post-completion-wakeup-gate.md`

### 🟢 可视化与 HTML 报告 (Phase 5)

Phase 4 (TileMatrix + getMarkerFeatures) 完成后进入收尾阶段。完整配方 → `references/phase5-visualization-report.md`：

1. **UMAP 3 面板**：Cluster / AgeGroup / Sample，`plotEmbedding` + `ggsave`
2. **细胞组成堆叠柱状图**：按 Old 比例降序排列 Cluster × Age 组成
3. **HTML 总结报告**：Python 手动构建，base64 嵌入所有 PNG，含 summary cards + timeline + 方法参数表 + 文件清单。预期 2-5MB。**禁止用 MemOmics 内建 `generate_report`（仅 ~40KB 空壳）。**

### 🟢 公共 GEO ATAC fragment 文件导入

从 GEO 导入预处理的 ATAC fragment 文件（`.tsv.gz` + `.tbi.gz` Tabix 索引格式）可直接构建 ArchR Arrow — 免除 fastq 比对。已知人类海马 ATAC 数据集（GSE278576 *Science* 2026 为最佳候选：40 ATAC 衰老海马样本）、ENCODE 人类脑 ATAC 缺失说明、GEOparse 元数据提取方法 → `references/public-geo-fragment-import.md`

**⚠️ bigwig vs fragments 粒度选择（2026-08-02）**：GSE278576 suppl 同时提供①亚群聚合 bigwig（细胞类型×年龄组，~100-350MB，够做 L2 可及性比较）和②GSM 级单细胞 fragments（~1.3GB/样本，才能做 L3 真 footprinting）。**GSM 级 fragments 单独可下，不需要 89GB 的 GSE278576_RAW.tar。** 下载后用 HTTP HEAD 对比 Content-Length 验证完整性（用户此前下载的 hc77/hc78 只有 2MB/0.7MB，真实是 1.31GB = 0.15% 完成度）。完整决策树（L2→bigwig / L3→fragments / 带宽现实）→ 同上 reference 的 "bigwig vs fragments" 一节。

### 🟢 用户偏好
- **禁止装到 C 盘** — R 包、基因组数据、分析产出全部放 E 盘。R 本体放 C 盘可以（~100MB）
- **安装必须主动监控** — 不能 fire-and-forget。每 30-60 秒轮询进程状态+库目录变化
- **优先使用 `pak::pak()` 装 GitHub 包**（而非 `devtools::install_github()` 或 `remotes::install_github()`）

### 🟢 分步保存铁律

ArchR 分析**每步操作后必须立即 `saveRDS`**，不能攒到最后。原因：

- addGroupCoverages 生成 coverage 元数据嵌入 ArchRProject — 不保存则重载丢失
- addTileMatrix、addIterativeLSI 等同理
- 单步崩溃时，已有 RDS 可恢复，不用从头重跑

```r
proj <- readRDS("project_clustered.rds")
proj <- addGroupCoverages(proj, groupBy="Clusters")
saveRDS(proj, "project_cov.rds")           # ← 必须

proj <- addTileMatrix(proj, tileSize=500)
saveRDS(proj, "project_tilemat.rds")       # ← 必须

markers <- getMarkerFeatures(proj, ...)
saveRDS(markers, "markers.rds")            # ← 必须
```
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
| macaca | hippocampus | aging | 2026-08-02 |  run_motif_figs.R | - | - |  |
